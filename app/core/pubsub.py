"""Redis pub/sub helpers for benchmark run execution progress events."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis

from app.core.redis import get_redis_client


async def publish_run_event(run_id: str, event: dict[str, Any], redis: Redis | None = None) -> None:
    """Publish a run progress event to channel f"run:{run_id}"."""
    client = redis or get_redis_client()
    payload = json.dumps(event)
    await client.publish(f"run:{run_id}", payload)


async def subscribe_run(run_id: str, redis: Redis | None = None) -> AsyncIterator[dict[str, Any]]:
    """Subscribe to channel f"run:{run_id}", yielding parsed events until terminal event."""
    client = redis or get_redis_client()
    pubsub = client.pubsub()
    channel = f"run:{run_id}"
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if not isinstance(message, dict) or message.get("type") != "message":
                continue
            raw_data = message.get("data")
            if not raw_data:
                continue
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
            event = json.loads(raw_data)
            yield event

            event_type = event.get("type") or event.get("event")
            if event_type in (
                "completed",
                "failed",
                "aborted",
                "run.completed",
                "run.failed",
                "run.aborted",
            ):
                break
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        try:
            if hasattr(pubsub, "aclose"):
                await pubsub.aclose()
            elif hasattr(pubsub, "close"):
                res = pubsub.close()
                if asyncio.iscoroutine(res):
                    await res
        except Exception:
            pass


async def is_aborted(run_id: str, redis: Redis | None = None) -> bool:
    """Check if an abort flag key exists in Redis for the given run."""
    client = redis or get_redis_client()
    return await client.exists(f"run:{run_id}:abort") == 1
