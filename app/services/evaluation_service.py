"""Evaluation service computing aggregate benchmarks, validator effectiveness, and miss profiles."""

import uuid
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models.attack_result import AttackResult
from app.db.models.run import Run
from app.engine.evaluator import (
    aggregate_by_category,
    aggregate_by_model,
    compute_rfr,
    confidence_interval,
)
from app.engine.state import RunMetrics
from app.probes.base import ProbeResult


class MissProfile(BaseModel):
    """Detailed pattern analysis for successful probe bypasses (robustness failures)."""

    total_failures: int
    avg_prompt_tokens: float
    avg_response_tokens: float
    dominant_categories: list[tuple[str, int]]
    failure_prompts: list[dict[str, Any]]
    bypassed_validators: list[str]


class EvaluationService:
    """Computes analytical metrics and diagnostics over benchmark results."""

    async def aggregate_run_metrics(self, session: AsyncSession, run_id: uuid.UUID) -> RunMetrics:
        """Compute full benchmark metrics from stored prompt results."""
        stmt = select(AttackResult).where(AttackResult.run_id == run_id)
        results = (await session.execute(stmt)).scalars().all()
        if not results:
            raise NotFoundError(f"No results found for run '{run_id}'.")

        # Convert to ProbeResult objects for evaluator functions
        probe_results = [
            ProbeResult(
                attempt_index=r.prompt_index,
                probe_type=r.attack_type,
                seed_prompt=r.seed_prompt,
                prompt=r.mutated_prompt,
                response=r.target_response,
                validator_verdict=r.defense_verdict,
                is_failure=r.is_jailbroken,
                score=r.jailbreak_score,
                evaluation_reason=r.evaluation_reason or "",
                latency_ms=r.latency_ms,
                tokens_used=r.tokens_used,
                turn_history=[{"category": "general", "score": r.jailbreak_score}],
            )
            for r in results
        ]

        total = len(probe_results)
        failures = sum(1 for r in probe_results if r.is_failure)
        blocks = sum(1 for r in probe_results if not r.validator_verdict.get("allowed", True))
        total_tokens = sum(r.tokens_used for r in probe_results)
        avg_latency = (sum(r.latency_ms for r in probe_results) / total) if total > 0 else 0.0

        rfr = compute_rfr(probe_results)
        ci = confidence_interval(failures, total)
        cat_rfr = aggregate_by_category(probe_results)

        return RunMetrics(
            rfr=rfr,
            total_attempts=total,
            failed_attempts=failures,
            validator_blocks=blocks,
            average_latency_ms=round(avg_latency, 2),
            total_tokens=total_tokens,
            category_rfr=cat_rfr,
            confidence_interval_95=ci,
        )

    async def compute_validator_effectiveness(
        self, session: AsyncSession, run_id: uuid.UUID
    ) -> dict[str, Any]:
        """Compute block rate and per-validator intervention statistics."""
        stmt = select(AttackResult).where(AttackResult.run_id == run_id)
        results = (await session.execute(stmt)).scalars().all()
        total = len(results)
        if total == 0:
            return {"block_rate": 0.0, "total_attempts": 0, "validators": {}}

        validator_counts: dict[str, int] = {}
        total_blocks = 0

        for r in results:
            v_dict = r.defense_verdict or {}
            if not v_dict.get("allowed", True):
                total_blocks += 1
                v_name = v_dict.get("validator_name") or v_dict.get("defense_name") or "unknown_validator"
                validator_counts[v_name] = validator_counts.get(v_name, 0) + 1

        block_rate = round(total_blocks / total, 4)
        return {
            "block_rate": block_rate,
            "total_attempts": total,
            "total_blocks": total_blocks,
            "validators": {
                name: {
                    "blocks": count,
                    "share_of_blocks": round(count / total_blocks, 4) if total_blocks > 0 else 0.0,
                }
                for name, count in validator_counts.items()
            },
        }

    async def get_miss_profile(self, session: AsyncSession, run_id: uuid.UUID) -> MissProfile:
        """Inspect characteristics of prompts that bypassed all validators and provoked compliance."""
        stmt = select(AttackResult).where(
            AttackResult.run_id == run_id,
            AttackResult.is_jailbroken.is_(True),
        )
        failures = (await session.execute(stmt)).scalars().all()
        total_failures = len(failures)

        if total_failures == 0:
            return MissProfile(
                total_failures=0,
                avg_prompt_tokens=0.0,
                avg_response_tokens=0.0,
                dominant_categories=[],
                failure_prompts=[],
                bypassed_validators=[],
            )

        avg_prompt_tok = sum(len(f.mutated_prompt.split()) for f in failures) / total_failures
        avg_resp_tok = sum(len(f.target_response.split()) for f in failures) / total_failures

        # Collect sample failure prompts
        sample_prompts = [
            {
                "probe_type": f.attack_type,
                "prompt": f.mutated_prompt[:250],
                "response": f.target_response[:250],
                "score": f.jailbreak_score,
            }
            for f in failures[:5]
        ]

        return MissProfile(
            total_failures=total_failures,
            avg_prompt_tokens=round(avg_prompt_tok, 1),
            avg_response_tokens=round(avg_resp_tok, 1),
            dominant_categories=[("general", total_failures)],
            failure_prompts=sample_prompts,
            bypassed_validators=[],
        )


evaluation_service = EvaluationService()
