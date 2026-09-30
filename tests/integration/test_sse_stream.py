"""Integration tests for Server-Sent Events (SSE) live progress stream."""

import json
import uuid

import pytest

from app.services.run_service import run_service


@pytest.mark.asyncio
async def test_sse_progress_stream_events(async_client, mock_redis, monkeypatch):
    """Verify SSE endpoint streams events in expected order from Redis pub/sub."""
    run_id = uuid.uuid4()

    # Mock get_run so authorization and ownership pass
    async def fake_get_run(session, r_id, org_id):
        return type("Run", (), {"id": run_id})()

    monkeypatch.setattr(run_service, "get_run", fake_get_run)

    channel_name = f"run:{run_id}"

    # Pre-populate messages into mock_redis
    await mock_redis.publish(
        channel_name,
        json.dumps({"event": "run.progress", "data": {"attempt_idx": 1, "total": 2, "rfr": 0.0}}),
    )
    await mock_redis.publish(
        channel_name,
        json.dumps({"event": "run.completed", "data": {"status": "completed", "rfr": 0.5}}),
    )

    response = await async_client.get(f"/api/v1/runs/{run_id}/stream")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    content = response.text
    assert "event: ping" in content
    assert "event: progress" in content
    assert "run.completed" in content
