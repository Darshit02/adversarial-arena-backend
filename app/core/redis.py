"""Shared asynchronous Redis client and FastAPI dependency."""

from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from app.config import get_settings

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Retrieve or initialize the singleton async Redis client."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def init_redis_client(url: str | None = None) -> Redis:
    """Initialize and verify the shared async Redis client."""
    global _redis_client
    settings = get_settings()
    target_url = url or settings.REDIS_URL
    _redis_client = Redis.from_url(target_url, decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    """Gracefully close the shared async Redis client."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding the shared Redis client."""
    yield get_redis_client()
