"""Run service managing benchmark lifecycle, pagination, abortion, and Celery task dispatch."""

import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.db.models.attack_result import AttackResult
from app.db.models.run import Run
from app.db.models.target_model import TargetModelConfig
from app.schemas.run import RunCreate, RunFilterParams


class RunService:
    """Business logic for orchestrating benchmark evaluation runs."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def create_run(
        self,
        session: AsyncSession,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID,
        payload: RunCreate,
    ) -> Run:
        """Create a new run record and enqueue the Celery execution task."""
        # 1. Verify ModelUnderTest exists and belongs to the organization
        stmt = select(TargetModelConfig).where(
            TargetModelConfig.id == payload.target_model_id,
            TargetModelConfig.organization_id == org_id,
        )
        mut = (await session.execute(stmt)).scalar_one_or_none()
        if not mut:
            raise NotFoundError(f"Target model '{payload.target_model_id}' not found.")

        # 2. Persist new Run entity
        run = Run(
            organization_id=org_id,
            created_by_user_id=user_id,
            target_model_id=payload.target_model_id,
            name=payload.name,
            status="pending",
            harm_category=payload.harm_category,
            seed_prompts=payload.seed_prompts,
            attack_template_ids=[str(t) for t in payload.attack_template_ids],
            defense_ids=[str(d) for d in payload.defense_ids],
            metrics={},
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)

        # 3. Enqueue Celery task asynchronously
        try:
            from app.workers.tasks import run_evaluation_suite

            run_evaluation_suite.delay(str(run.id))
        except Exception:
            # If broker is offline during local test execution, keep run pending
            pass

        return run

    async def get_run(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> Run:
        """Fetch single run record by ID, verifying organizational ownership."""
        stmt = (
            select(Run)
            .options(selectinload(Run.target_model))
            .where(Run.id == run_id, Run.organization_id == org_id)
        )
        run = (await session.execute(stmt)).scalar_one_or_none()
        if not run:
            raise NotFoundError(f"Run '{run_id}' not found.")
        return run

    async def list_runs(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        filters: RunFilterParams | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[Run], int]:
        """List historical benchmark runs with dynamic filters and pagination."""
        offset = (page - 1) * per_page
        query = select(Run).where(Run.organization_id == org_id)

        if filters:
            if filters.status:
                query = query.where(Run.status == filters.status)
            if filters.target_model_id:
                query = query.where(Run.target_model_id == filters.target_model_id)
            if filters.from_date:
                query = query.where(Run.created_at >= filters.from_date)
            if filters.to_date:
                query = query.where(Run.created_at <= filters.to_date)

        # Count total
        count_stmt = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        # Execute paginated query
        paged_query = (
            query.options(selectinload(Run.target_model))
            .order_by(Run.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        runs = (await session.execute(paged_query)).scalars().all()
        return list(runs), total

    async def get_run_results(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        org_id: uuid.UUID,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[AttackResult], int]:
        """Fetch paginated prompt-level results for a specific run."""
        # Ensure run exists and belongs to org
        await self.get_run(session, run_id, org_id)

        offset = (page - 1) * per_page
        base_stmt = select(AttackResult).where(AttackResult.run_id == run_id)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = base_stmt.order_by(AttackResult.prompt_index.asc()).offset(offset).limit(per_page)
        results = (await session.execute(stmt)).scalars().all()
        return list(results), total

    async def abort_run(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        org_id: uuid.UUID,
        redis: Redis | None = None,
    ) -> Run:
        """Signal abortion of an active evaluation run via Redis key."""
        run = await self.get_run(session, run_id, org_id)
        if run.status in ("completed", "failed", "aborted"):
            raise ValidationError(f"Cannot abort run with terminal status '{run.status}'.")

        # Set Redis abort key
        redis_client = redis
        should_close = False
        if redis_client is None:
            try:
                redis_client = Redis.from_url(self.settings.REDIS_URL, decode_responses=True)
                should_close = True
            except Exception:
                redis_client = None

        if redis_client is not None:
            try:
                await redis_client.setex(f"run:{run_id}:abort", 3600, "1")
            finally:
                if should_close:
                    await redis_client.close()

        run.status = "aborted"
        run.completed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(run)
        return run

    async def delete_run(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> None:
        """Delete run and cascade prompt results."""
        run = await self.get_run(session, run_id, org_id)
        await session.delete(run)
        await session.commit()


run_service = RunService()
