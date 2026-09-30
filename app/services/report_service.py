"""Report generation service producing JSON, CSV, and PDF benchmark artifacts."""

import csv
import io
import os
import uuid
from typing import Any
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.errors import NotFoundError
from app.db.models.attack_result import AttackResult
from app.db.models.run import Run
from app.schemas.run import RunComparisonResponse, RunResponse


class ReportService:
    """Generates analytical report artifacts in PDF, JSON, and CSV formats."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def _fetch_run_with_results(self, session: AsyncSession, run_id: uuid.UUID) -> tuple[Run, list[AttackResult]]:
        stmt = (
            select(Run)
            .options(selectinload(Run.target_model), selectinload(Run.results))
            .where(Run.id == run_id)
        )
        res = await session.execute(stmt)
        run_record = res.scalar_one_or_none()
        if not run_record:
            raise NotFoundError(f"Run '{run_id}' not found.")
        return run_record, run_record.results

    async def generate_json_report(self, session: AsyncSession, run_id: uuid.UUID) -> dict[str, Any]:
        """Produce structured JSON evaluation report."""
        run, results = await self._fetch_run_with_results(session, run_id)
        return {
            "report_id": str(uuid.uuid4()),
            "run_id": str(run.id),
            "run_name": run.name,
            "status": run.status,
            "risk_category": run.harm_category,
            "target_model": {
                "id": str(getattr(run, "target_model_id", getattr(run.target_model, "id", "unknown"))),
                "name": run.target_model.name if run.target_model else "Unknown",
                "provider": run.target_model.provider if run.target_model else "Unknown",
            },
            "metrics": run.metrics,
            "total_attempts": len(results),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "attempts": [
                {
                    "prompt_index": r.prompt_index,
                    "probe_type": r.attack_type,
                    "seed_prompt": r.seed_prompt,
                    "prompt": r.mutated_prompt,
                    "response": r.target_response,
                    "validator_verdict": r.defense_verdict,
                    "is_failure": r.is_jailbroken,
                    "score": r.jailbreak_score,
                    "evaluation_reason": r.evaluation_reason,
                    "latency_ms": r.latency_ms,
                    "tokens_used": r.tokens_used,
                }
                for r in results
            ],
        }

    async def generate_csv_report(self, session: AsyncSession, run_id: uuid.UUID) -> str:
        """Produce CSV export of all prompt attempts."""
        _, results = await self._fetch_run_with_results(session, run_id)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "prompt_index",
                "probe_type",
                "seed_prompt",
                "prompt",
                "response",
                "validator_allowed",
                "is_failure",
                "score",
                "evaluation_reason",
                "latency_ms",
                "tokens_used",
            ]
        )
        for r in results:
            allowed = r.defense_verdict.get("allowed", True) if r.defense_verdict else True
            writer.writerow(
                [
                    r.prompt_index,
                    r.attack_type,
                    r.seed_prompt,
                    r.mutated_prompt,
                    r.target_response,
                    allowed,
                    r.is_jailbroken,
                    r.jailbreak_score,
                    r.evaluation_reason or "",
                    r.latency_ms,
                    r.tokens_used,
                ]
            )
        return output.getvalue()

    async def generate_pdf_report(self, session: AsyncSession, run_id: uuid.UUID) -> bytes:
        """Generate high-resolution PDF evaluation report using ReportLab."""
        run, results = await self._fetch_run_with_results(session, run_id)
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1A202C"),
            spaceAfter=12,
        )
        heading2_style = ParagraphStyle(
            "Heading2",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#2D3748"),
            spaceBefore=12,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#4A5568"),
        )

        elements = []
        elements.append(Paragraph("Adversarial Arena — Robustness Benchmark Report", title_style))
        elements.append(Spacer(1, 10))

        # Executive Metadata Table
        model_name = run.target_model.name if run.target_model else "Unknown MUT"
        meta_data = [
            ["Run Name:", run.name, "Status:", run.status.upper()],
            ["Model Under Test:", model_name, "Risk Category:", run.harm_category],
            ["Started At:", str(run.started_at or "N/A"), "Completed At:", str(run.completed_at or "N/A")],
        ]
        meta_table = Table(meta_data, colWidths=[120, 160, 100, 160])
        meta_table.setStyle(
            TableStyle(
                [
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#2D3748")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(meta_table)
        elements.append(Spacer(1, 16))

        # Metrics Card
        metrics = run.metrics or {}
        rfr = metrics.get("rfr", 0.0)
        total = len(results)
        fails = sum(1 for r in results if r.is_jailbroken)
        blocks = metrics.get("validator_blocks", 0)
        avg_lat = metrics.get("average_latency_ms", 0.0)

        elements.append(Paragraph("Executive Summary", heading2_style))
        summary_data = [
            ["Robustness Failure Rate (RFR)", "Total Probes", "Failed Probes", "Validator Blocks", "Avg Latency"],
            [f"{rfr * 100:.1f}%", str(total), str(fails), str(blocks), f"{avg_lat:.1f} ms"],
        ]
        summary_table = Table(summary_data, colWidths=[160, 90, 90, 100, 100])
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF2F7")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#2D3748")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
                    ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#FFF5F5") if rfr > 0.3 else colors.HexColor("#F0FFF4")),
                    ("TEXTCOLOR", (0, 1), (0, 1), colors.HexColor("#C53030") if rfr > 0.3 else colors.HexColor("#22543D")),
                    ("FONTNAME", (0, 1), (0, 1), "Helvetica-Bold"),
                ]
            )
        )
        elements.append(summary_table)
        elements.append(Spacer(1, 16))

        # Attempt Breakdown Table
        elements.append(Paragraph("Attempt Breakdown (First 15 Probes)", heading2_style))
        sample_rows = [["#", "Type", "Outcome", "Score", "Latency", "Reason"]]
        for idx, r in enumerate(results[:15]):
            outcome = "FAILURE" if r.is_jailbroken else "PASSED"
            sample_rows.append(
                [
                    str(idx + 1),
                    r.attack_type,
                    outcome,
                    f"{r.jailbreak_score:.2f}",
                    f"{r.latency_ms:.0f} ms",
                    (r.evaluation_reason or "N/A")[:35],
                ]
            )
        attempts_table = Table(sample_rows, colWidths=[24, 75, 65, 45, 55, 276])
        attempts_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF2F7")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("ALIGN", (0, 0), (4, -1), "CENTER"),
                ]
            )
        )
        elements.append(attempts_table)

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    async def compare_runs(
        self, session: AsyncSession, run_a_id: uuid.UUID, run_b_id: uuid.UUID
    ) -> RunComparisonResponse:
        """Compute head-to-head comparison between two evaluation runs."""
        run_a, _ = await self._fetch_run_with_results(session, run_a_id)
        run_b, _ = await self._fetch_run_with_results(session, run_b_id)

        metrics_a = run_a.metrics or {}
        metrics_b = run_b.metrics or {}

        rfr_a = metrics_a.get("rfr", 0.0)
        rfr_b = metrics_b.get("rfr", 0.0)
        delta_rfr = round(rfr_b - rfr_a, 4)

        lat_a = metrics_a.get("average_latency_ms", 0.0)
        lat_b = metrics_b.get("average_latency_ms", 0.0)
        delta_lat = round(lat_b - lat_a, 2)

        # Conclusion summary
        if delta_rfr > 0.05:
            conclusion = f"Model B exhibits significantly higher Robustness Failure Rate (+{delta_rfr * 100:.1f}%) compared to Model A."
        elif delta_rfr < -0.05:
            conclusion = f"Model B demonstrates stronger robustness resistance, reducing failure rate by {abs(delta_rfr) * 100:.1f}% compared to Model A."
        else:
            conclusion = "Both models demonstrate comparable robustness resistance levels (within 5% variance)."

        return RunComparisonResponse(
            run_a=RunResponse.model_validate(run_a),
            run_b=RunResponse.model_validate(run_b),
            delta_asr=delta_rfr,
            delta_latency_ms=delta_lat,
            category_comparison={
                "rfr": {"run_a": rfr_a, "run_b": rfr_b, "delta": delta_rfr},
                "latency_ms": {"run_a": lat_a, "run_b": lat_b, "delta": delta_lat},
            },
            conclusion=conclusion,
        )

    async def upload_report(self, run_id: uuid.UUID, content: bytes | str, fmt: str) -> str:
        """Store report artifact to local disk or S3 and return resource URI."""
        storage_dir = self.settings.STORAGE_LOCAL_DIR
        os.makedirs(storage_dir, exist_ok=True)
        file_path = os.path.join(storage_dir, f"report_{run_id}.{fmt}")

        mode = "wb" if isinstance(content, bytes) else "w"
        with open(file_path, mode) as f:
            f.write(content)

        return f"file://{file_path}"


report_service = ReportService()
