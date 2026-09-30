"""Celery background tasks for orchestrating benchmark runs and generating reports."""

import asyncio
import uuid
from typing import Any
from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.models.run import Run
from app.db.session import async_session_factory
from app.engine.runner import execute_run
from app.services.report_service import report_service
from app.workers.celery_app import celery_app

task_logger = get_task_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def run_evaluation_suite(self: Any, run_id: str) -> dict[str, Any]:
    """Execute adversarial evaluation benchmark suite in Celery background worker."""
    task_logger.info("Executing evaluation suite task for run: %s", run_id)
    try:
        metrics = asyncio.run(execute_run(run_id))
        # Trigger background report generation upon successful completion
        generate_report.delay(run_id, "pdf")
        return {"status": "completed", "run_id": run_id, "metrics": metrics.model_dump()}
    except Exception as exc:
        task_logger.error("Error executing run %s: %s", run_id, str(exc))
        # Retry with exponential backoff if transient
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise exc


@celery_app.task
def generate_report(run_id: str, fmt: str = "pdf") -> str:
    """Generate benchmark evaluation report artifact and persist URL to run record."""
    task_logger.info("Generating report artifact (format=%s) for run: %s", fmt, run_id)

    async def _async_generate() -> str:
        async with async_session_factory() as session:
            run_uuid = uuid.UUID(run_id)
            if fmt == "pdf":
                content = await report_service.generate_pdf_report(session, run_uuid)
            elif fmt == "csv":
                content = await report_service.generate_csv_report(session, run_uuid)
            else:
                json_data = await report_service.generate_json_report(session, run_uuid)
                import json
                content = json.dumps(json_data)

            url = await report_service.upload_report(run_uuid, content, fmt)

            # Update run record with report URL
            stmt = select(Run).where(Run.id == run_uuid)
            res = await session.execute(stmt)
            run = res.scalar_one_or_none()
            if run:
                run.report_url = url
                await session.commit()

            return url

    return asyncio.run(_async_generate())
