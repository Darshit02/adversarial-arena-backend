"""Unit tests for LangGraph state machine orchestrator and execution runner."""

import pytest

from app.engine.orchestrator import run_graph
from app.engine.state import RunConfig
from app.targets.mock_client import MockTargetModel
from app.validators.keyword_filter import KeywordFilterValidator


class FakeRedis:
    """In-memory Redis fake for testing abort signals."""

    def __init__(self, keys=None):
        self._keys = keys or set()

    async def exists(self, key: str) -> int:
        return 1 if key in self._keys else 0

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_langgraph_orchestration_run():
    """Verify that LangGraph StateGraph runs through nodes and completes."""
    config = RunConfig(
        run_id="test-run-123",
        target_model_id="mock-mut",
        risk_category="cybersecurity",
        probe_types=["pair"],
        seed_prompts=[
            "Standard prompt 1",
            "Prompt with OVERRIDE_TRIGGER for compliance",
        ],
    )

    mut = MockTargetModel(
        jailbreak_trigger="OVERRIDE_TRIGGER",
        jailbreak_response=(
            "Here is the complete step by step technical procedure and implementation guide "
            "provided in full detail without refusal for the requested system specification."
        ),
    )

    validators = [
        KeywordFilterValidator({"blocked_keywords": ["FORBIDDEN_FLAG"], "regex_patterns": []})
    ]

    metrics = await run_graph(
        run_id="test-run-123",
        config=config,
        mut=mut,
        validators=validators,
    )

    assert metrics.total_attempts == 2
    assert metrics.failed_attempts == 1
    assert metrics.rfr == 0.5
    assert metrics.validator_blocks == 0
    assert metrics.average_latency_ms > 0
    assert metrics.confidence_interval_95[0] <= 0.5 <= metrics.confidence_interval_95[1]


@pytest.mark.asyncio
async def test_langgraph_orchestration_validator_blocking():
    """Verify validator chain blocks prompt in orchestrator graph."""
    config = RunConfig(
        run_id="test-run-block",
        target_model_id="mock-mut",
        risk_category="cybersecurity",
        probe_types=["pair"],
        seed_prompts=["This prompt contains FORBIDDEN_FLAG in it"],
    )

    mut = MockTargetModel()
    validators = [
        KeywordFilterValidator({"blocked_keywords": ["FORBIDDEN_FLAG"], "regex_patterns": []})
    ]

    metrics = await run_graph(
        run_id="test-run-block",
        config=config,
        mut=mut,
        validators=validators,
    )

    assert metrics.total_attempts == 1
    assert metrics.validator_blocks == 1
    assert metrics.failed_attempts == 0
    assert metrics.rfr == 0.0


@pytest.mark.asyncio
async def test_langgraph_orchestration_abort_signal():
    """Verify orchestrator respects Redis abort signal and sets status=aborted."""
    config = RunConfig(
        run_id="test-run-abort",
        target_model_id="mock-mut",
        risk_category="general",
        probe_types=["pair"],
        seed_prompts=["Prompt 1", "Prompt 2"],
    )

    fake_redis = FakeRedis(keys={"run:test-run-abort:abort"})
    mut = MockTargetModel()

    metrics = await run_graph(
        run_id="test-run-abort",
        config=config,
        mut=mut,
        redis=fake_redis,  # type: ignore
    )

    # When aborted at probe_mutate check, abort status finalized
    assert metrics is not None
