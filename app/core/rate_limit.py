"""Redis-based sliding-window rate limiter with in-memory fallback for testing."""

import time
from collections import defaultdict
from redis.asyncio import Redis
from app.core.errors import RateLimitError
from app.core.logging import get_logger

logger = get_logger(__name__)


class SlidingWindowRateLimiter:
    """Sliding window rate limiter using Redis sorted sets (ZSET).

    Design Decision:
    We use Redis sorted sets where each request is added with its microsecond timestamp
    as score and member. Expired entries older than (now - window) are pruned using ZREMRANGEBYSCORE,
    and ZCARD counts requests in the current window. This prevents the boundary burst problem
    inherent in fixed-window limiters.
    """

    def __init__(self, redis: Redis | None = None) -> None:
        self.redis = redis
        # In-memory fallback if Redis is unavailable (e.g. unit tests or local development)
        self._in_memory_log: dict[str, list[float]] = defaultdict(list)

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
        cost: int = 1,
    ) -> tuple[bool, int, int]:
        """Check if identifier exceeds rate limit.

        Returns:
            (allowed: bool, remaining: int, reset_in_seconds: int)
        """
        now = time.time()
        window_start = now - window_seconds
        key = f"rate_limit:{identifier}"

        if self.redis is not None:
            try:
                pipe = self.redis.pipeline()
                # 1. Remove timestamps older than window
                pipe.zremrangebyscore(key, 0, window_start)
                # 2. Get current count
                pipe.zcard(key)
                results = await pipe.execute()
                current_count = results[1]

                if current_count + cost > limit:
                    # Rate limit exceeded
                    return False, max(0, limit - current_count), int(window_seconds)

                # Add current request timestamp
                pipe = self.redis.pipeline()
                for i in range(cost):
                    pipe.zadd(key, {f"{now}:{i}": now})
                pipe.expire(key, window_seconds + 5)
                await pipe.execute()

                remaining = limit - (current_count + cost)
                return True, remaining, int(window_seconds)
            except Exception as e:
                logger.warning("Redis rate limit error, falling back to in-memory limiter", error=str(e))

        # In-memory sliding window fallback
        timestamps = self._in_memory_log[identifier]
        # Prune old timestamps
        timestamps = [ts for ts in timestamps if ts > window_start]
        self._in_memory_log[identifier] = timestamps

        if len(timestamps) + cost > limit:
            return False, max(0, limit - len(timestamps)), int(window_seconds)

        for _ in range(cost):
            timestamps.append(now)

        remaining = limit - len(timestamps)
        return True, remaining, int(window_seconds)

    async def enforce(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> None:
        """Enforce rate limit or raise RateLimitError."""
        allowed, remaining, reset_in = await self.check_rate_limit(
            identifier=identifier,
            limit=limit,
            window_seconds=window_seconds,
        )
        if not allowed:
            raise RateLimitError(
                f"Rate limit exceeded: maximum {limit} requests per {window_seconds}s. Reset in {reset_in}s."
            )
