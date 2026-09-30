"""Unit tests for execution runner and event streaming."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.runner import execute_run
from app.engine.state import RunConfig, RunMetrics


@pytest.mark.asyncio
async def test_execute_run_with_mock_config():
    """Verify execute_run handles lifecycle with injected config and mock redis."""
    fake_redis = MagicMock()
    fake_redis.publish = AsyncMock()
    fake_redis.aclose = AsyncMock()

    config = RunConfig(
        run_id="test-run-123",
        target_model_id="mock-model",
        risk_category="cybersecurity",
        probe_types=["pair"],
        seed_prompts=["How to bypass safety barriers"],
    )

    with patch("app.engine.runner.run_graph") as mock_run_graph:
        expected_metrics = RunMetrics(
            rfr=0.0,
            total_attempts=1,
            failed_attempts=0,
            validator_blocks=1,
            average_latency_ms=120.0,
            total_tokens=45,
            category_rfr={"cybersecurity": 0.0},
        )
        mock_run_graph.return_value = expected_metrics

        metrics = await execute_run(
            run_id="test-run-123",
            redis=fake_redis,
            mock_run_config=config,
        )

        assert metrics.rfr == 0.0
        assert metrics.total_attempts == 1
        assert fake_redis.publish.await_count >= 2

        # Check published events
        first_call = fake_redis.publish.await_args_list[0]
        assert first_call[0][0] == "run:test-run-123"
        payload = json.loads(first_call[0][1])
        assert payload["event"] == "run.started"


@pytest.mark.asyncio
async def test_execute_run_failure_handling():
    """Verify execute_run handles and publishes failures gracefully."""
    fake_redis = MagicMock()
    fake_redis.publish = AsyncMock()
    fake_redis.aclose = AsyncMock()

    config = RunConfig(
        run_id="failing-run",
        target_model_id="mock-model",
        probe_types=["pair"],
        seed_prompts=["Test prompt"],
    )

    with patch("app.engine.runner.run_graph", side_effect=RuntimeError("Simulated graph failure")):
        with pytest.raises(RuntimeError, match="Simulated graph failure"):
            await execute_run(
                run_id="failing-run",
                redis=fake_redis,
                mock_run_config=config,
            )

        # Check that run.failed was published
        failed_calls = [c for c in fake_redis.publish.await_args_list if "run.failed" in c[0][1]]
        assert len(failed_calls) == 1
