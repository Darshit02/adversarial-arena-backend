"""Runs router: submission, status querying, results pagination, abortion, and SSE progress streaming."""

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.organization import Organization
from app.db.models.user import User
from app.dependencies import (
    get_current_org,
    get_current_user,
    get_db,
    get_redis,
    rate_limit,
)
from app.schemas.common import ResponseEnvelope
from app.schemas.run import (
    AttackResultResponse,
    RunCreate,
    RunFilterParams,
    RunResponse,
    RunSummary,
)
from app.services.run_service import run_service

router = APIRouter(prefix="/runs", tags=["Runs"])


@router.post(
    "",
    response_model=ResponseEnvelope[dict[str, Any]],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit(scope="post_runs", limit=10, window=60))],
)
async def submit_run(
    payload: RunCreate,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[dict[str, Any]]:
    """Submit a new evaluation benchmark run (Returns 202 Accepted with run_id)."""
    run = await run_service.create_run(
        session=session,
        user_id=current_user.id,
        org_id=org.id,
        payload=payload,
    )
    return ResponseEnvelope.success(
        {
            "run_id": str(run.id),
            "status": run.status,
            "message": "Evaluation suite accepted and enqueued for execution.",
        }
    )


@router.get("", response_model=ResponseEnvelope[list[RunSummary]])
async def list_runs(
    status: str | None = None,
    target_model_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=500),
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[list[RunSummary]]:
    """List historical benchmark runs with filters and pagination."""
    filters = RunFilterParams(status=status, target_model_id=target_model_id)  # type: ignore
    runs, total = await run_service.list_runs(
        session, org.id, filters=filters, page=page, per_page=per_page
    )

    data = [
        RunSummary(
            id=r.id,
            name=r.name,
            status=r.status,  # type: ignore
            harm_category=r.harm_category,
            target_model_id=r.target_model_id,
            target_model_name=r.target_model.name if r.target_model else None,
            asr=r.metrics.get("rfr", 0.0) if r.metrics else 0.0,
            total_prompts=len(r.seed_prompts) if r.seed_prompts else 0,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]
    return ResponseEnvelope.paginated(data=data, page=page, per_page=per_page, total=total)


@router.get("/{id}", response_model=ResponseEnvelope[RunResponse])
async def get_run_detail(
    id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[RunResponse]:
    """Retrieve full run status and summary metrics."""
    run = await run_service.get_run(session, id, org.id)
    return ResponseEnvelope.success(RunResponse.model_validate(run))


@router.get("/{id}/results", response_model=ResponseEnvelope[list[AttackResultResponse]])
async def get_run_results(
    id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=500),
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[list[AttackResultResponse]]:
    """Retrieve paginated prompt-level attempts and evaluation results."""
    results, total = await run_service.get_run_results(
        session, id, org.id, page=page, per_page=per_page
    )
    data = [AttackResultResponse.model_validate(r) for r in results]
    return ResponseEnvelope.paginated(data=data, page=page, per_page=per_page, total=total)


@router.get("/{id}/stream")
async def stream_run_progress(
    id: uuid.UUID,
    request: Request,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    """Server-Sent Events (SSE) streaming live benchmark execution progress from Redis pub/sub."""
    # Verify run exists and belongs to org
    await run_service.get_run(session, id, org.id)

    channel_name = f"run:{id}"

    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel_name)
        try:
            # Yield initial connect event
            yield f'event: ping\ndata: {{"status": "connected", "run_id": "{id}"}}\n\n'

            while True:
                if await request.is_disconnected():
                    break

                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    raw_data = message.get("data", "")
                    yield f"event: progress\ndata: {raw_data}\n\n"

                    try:
                        parsed = json.loads(raw_data)
                        if parsed.get("event") in ("run.completed", "run.failed"):
                            break
                    except Exception:
                        pass
                else:
                    # SSE keep-alive ping
                    yield ": keep-alive\n\n"
                    await asyncio.sleep(0.5)
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{id}/abort", response_model=ResponseEnvelope[RunResponse])
async def abort_run(
    id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ResponseEnvelope[RunResponse]:
    """Abort an active evaluation run."""
    run = await run_service.abort_run(session, id, org.id, redis=redis)
    return ResponseEnvelope.success(RunResponse.model_validate(run))


@router.delete("/{id}", response_model=ResponseEnvelope[dict[str, str]])
async def delete_run(
    id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[dict[str, str]]:
    """Delete an evaluation run record."""
    await run_service.delete_run(session, id, org.id)
    return ResponseEnvelope.success({"message": f"Run '{id}' deleted successfully."})
