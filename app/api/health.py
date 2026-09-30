"""Health and readiness probe endpoints."""

from fastapi import APIRouter, Response, status
from redis.asyncio import Redis

from app.config import get_settings
from app.db.session import check_db_health

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe indicating application server is running."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(response: Response) -> dict[str, str]:
    """Readiness probe verifying PostgreSQL and Redis connections."""
    settings = get_settings()

    # 1. Database check
    db_ok = await check_db_health()

    # 2. Redis check
    redis_ok = False
    try:
        redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        ping_res = await redis.ping()
        redis_ok = bool(ping_res)
        await redis.close()
    except Exception:
        redis_ok = False

    is_ready = db_ok and redis_ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if is_ready else "degraded",
        "database": "ok" if db_ok else "fail",
        "redis": "ok" if redis_ok else "fail",
    }
