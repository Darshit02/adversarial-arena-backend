"""Reports router delivering JSON structured benchmarks, PDF artifact downloads, and comparisons."""

import io
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.organization import Organization
from app.dependencies import get_current_org, get_db
from app.schemas.common import ResponseEnvelope
from app.schemas.run import RunComparisonResponse
from app.services.report_service import report_service

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/compare", response_model=ResponseEnvelope[RunComparisonResponse])
async def compare_runs(
    run_a: uuid.UUID = Query(description="UUID of baseline run"),
    run_b: uuid.UUID = Query(description="UUID of comparison run"),
    org: Organization = Depends(get_current_org),  # noqa: ARG001
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[RunComparisonResponse]:
    """Generate comparative delta analysis between two benchmark runs."""
    comparison = await report_service.compare_runs(session, run_a, run_b)
    return ResponseEnvelope.success(comparison)


@router.get("/{run_id}", response_model=ResponseEnvelope[dict[str, Any]])
async def get_json_report(
    run_id: uuid.UUID,
    org: Organization = Depends(get_current_org),  # noqa: ARG001
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[dict[str, Any]]:
    """Download full structured JSON benchmark evaluation report."""
    report_data = await report_service.generate_json_report(session, run_id)
    return ResponseEnvelope.success(report_data)


@router.get("/{run_id}/pdf")
async def download_pdf_report(
    run_id: uuid.UUID,
    org: Organization = Depends(get_current_org),  # noqa: ARG001
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download printable PDF benchmark report artifact."""
    pdf_bytes = await report_service.generate_pdf_report(session, run_id)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{run_id}.pdf"},
    )
