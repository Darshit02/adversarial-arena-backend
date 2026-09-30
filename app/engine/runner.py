"""Async execution runner coordinating database persistence, Redis pub/sub streaming, and the orchestrator."""

import json
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.logging import get_logger
from app.db.models.defense_config import DefenseConfig
from app.db.models.run import Run
from app.db.session import async_session_factory
from app.engine.orchestrator import run_graph
from app.engine.state import RunConfig, RunMetrics
from app.targets.factory import target_model_factory
from app.validators.registry import get_validator_class

logger = get_logger(__name__)


async def execute_run(
    run_id: str,
    redis: Redis | None = None,
    mock_run_config: RunConfig | None = None,
) -> RunMetrics:
    """Execute end-to-end benchmark evaluation run.

    Coordinates:
    1. Loading Run configuration and ModelUnderTest credentials from DB
    2. Publishing 'run.started' to Redis pub/sub channel run:{run_id}
    3. Invoking LangGraph orchestrator
    4. Streaming real-time progress events
    5. Persisting final metrics and detailed attempts to DB
    6. Publishing 'run.completed'
    """
    settings = get_settings()
    log = logger.bind(run_id=run_id)
    log.info("Starting benchmark run execution")

    # Connect to Redis if not injected
    redis_client = redis
    should_close_redis = False
    if redis_client is None:
        try:
            redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
            should_close_redis = True
        except Exception as e:
            log.warning("Could not connect to Redis for run events", error=str(e))
            redis_client = None

    channel_name = f"run:{run_id}"

    async def _publish_event(event_type: str, data: dict):
        if redis_client is not None:
            try:
                payload = json.dumps(
                    {
                        "event": event_type,
                        "run_id": run_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "data": data,
                    }
                )
                await redis_client.publish(channel_name, payload)
            except Exception as e:
                log.warning(
                    "Failed to publish Redis run event", event_type=event_type, error=str(e)
                )

    try:
        # 1. Load run from DB (or use mock_run_config for tests)
        run_record = None
        target_model = None
        validators = []

        if mock_run_config is not None:
            config = mock_run_config
        else:
            async with async_session_factory() as session:
                stmt = select(Run).options(selectinload(Run.target_model)).where(Run.id == run_id)
                res = await session.execute(stmt)
                run_record = res.scalar_one_or_none()

                if not run_record:
                    raise ValueError(f"Run with ID '{run_id}' not found in database.")

                # Mark run as running
                run_record.status = "running"
                run_record.started_at = datetime.now(UTC)
                await session.commit()

                # Instantiate ModelUnderTest from DB config
                target_model = target_model_factory.create_from_config(run_record.target_model)

                # Load validators from DB
                if run_record.defense_ids:
                    v_stmt = select(DefenseConfig).where(
                        DefenseConfig.id.in_(run_record.defense_ids)
                    )
                    v_res = await session.execute(v_stmt)
                    for v_model in v_res.scalars():
                        v_cls = get_validator_class(v_model.defense_type)
                        validators.append(v_cls(v_model.parameters))

                config = RunConfig(
                    run_id=str(run_record.id),
                    target_model_id=str(run_record.target_model_id),
                    risk_category=run_record.harm_category,
                    probe_types=run_record.attack_template_ids or ["pair"],
                    seed_prompts=run_record.seed_prompts or ["Test prompt"],
                )

        # 2. Publish run.started event
        await _publish_event(
            "run.started",
            {"status": "running", "total_prompts": len(config.seed_prompts)},
        )

        # 3. Execute LangGraph orchestrator
        metrics = await run_graph(
            run_id=run_id,
            config=config,
            mut=target_model,
            validators=validators,
            redis=redis_client,
        )

        # 4. Update database with final metrics
        if run_record is not None:
            async with async_session_factory() as session:
                stmt = select(Run).where(Run.id == run_id)
                res = await session.execute(stmt)
                db_run = res.scalar_one()
                db_run.status = "completed"
                db_run.completed_at = datetime.now(UTC)
                db_run.metrics = metrics.model_dump()
                await session.commit()

        # 5. Publish run.completed event
        await _publish_event(
            "run.completed",
            {"status": "completed", "metrics": metrics.model_dump()},
        )
        log.info("Benchmark run completed successfully", rfr=metrics.rfr)
        return metrics

    except Exception as e:
        log.error("Execution failed for run", error=str(e))
        if redis_client is not None:
            await _publish_event("run.failed", {"status": "failed", "error": str(e)})

        # Update run status in DB
        try:
            async with async_session_factory() as session:
                stmt = select(Run).where(Run.id == run_id)
                res = await session.execute(stmt)
                failed_db_run = res.scalar_one_or_none()
                if failed_db_run:
                    failed_db_run.status = "failed"
                    failed_db_run.error_message = str(e)
                    failed_db_run.completed_at = datetime.now(UTC)
                    await session.commit()
        except Exception:
            pass

        raise

    finally:
        if should_close_redis and redis_client is not None:
            await redis_client.close()
