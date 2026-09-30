"""Health and readiness probe endpoints."""

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis

from app.core.redis import get_redis
from app.db.session import check_db_health

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe indicating application server is running."""
    return {"status": "ok", "version": "0.4.2"}


@router.get("/ready")
async def readiness_check(response: Response, redis: Redis = Depends(get_redis)) -> dict[str, str]:
    """Readiness probe verifying PostgreSQL and Redis connections."""
    # 1. Database check
    db_ok = await check_db_health()

    # 2. Redis check
    redis_ok = False
    try:
        ping_res = await redis.ping()
        redis_ok = bool(ping_res)
    except Exception:
        redis_ok = False

    is_ready = db_ok and redis_ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "db": "ok" if db_ok else "fail",
        "redis": "ok" if redis_ok else "fail",
    }
