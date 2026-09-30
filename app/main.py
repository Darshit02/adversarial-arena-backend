"""FastAPI application factory, lifespan hooks, CORS, RequestID middleware, and Prometheus metrics."""

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram
from redis.asyncio import Redis

from app.api.router import api_v1_router
from app.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import get_logger, setup_logging
from app.core.security import jwks_manager
from app.db.session import check_db_health

logger = get_logger(__name__)

# Prometheus metrics definition
RUNS_TOTAL = Counter("arena_runs_total", "Total benchmark evaluation runs", ["status"])
ATTACKS_TOTAL = Counter(
    "arena_attacks_total", "Total adversarial probe attempts", ["attack_type", "success"]
)
LLM_LATENCY = Histogram(
    "arena_llm_latency_seconds", "Latency of ModelUnderTest queries", ["provider", "model"]
)
DEFENSE_BLOCKS = Counter("arena_defense_blocks_total", "Total validator interventions", ["defense"])


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Lifespan context manager: initialization, connection check, and graceful teardown."""
    settings = get_settings()
    setup_logging()
    logger.info("Initializing Adversarial Arena backend", env=settings.APP_ENV)

    # 1. Warm Redis JWKS cache if online
    try:
        redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await redis.ping()
        logger.info("Connected to Redis 7")
        try:
            await jwks_manager.get_jwks(redis=redis)
        except Exception:
            pass
        await redis.close()
    except Exception as e:
        logger.warning("Redis not available on startup", error=str(e))

    # 2. Check Database health
    db_ok = await check_db_health()
    if db_ok:
        logger.info("PostgreSQL database connection verified")
    else:
        logger.warning("PostgreSQL database unavailable or pending startup")

    yield

    logger.info("Shutting down Adversarial Arena backend")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="Research-grade LLM jailbreak attack-defense experimentation and benchmarking platform",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. RequestID and Logging Middleware
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start_time) * 1000

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "HTTP request completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            latency_ms=round(latency_ms, 2),
        )
        return response

    # 3. Register RFC 7807 Error Handlers
    register_error_handlers(app)

    # 4. Prometheus metrics endpoint
    from fastapi import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    @app.get("/metrics", tags=["Observability"])
    async def metrics_endpoint():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # 5. Mount API routers
    app.include_router(api_v1_router)

    # Root redirect / health
    @app.get("/", include_in_schema=False)
    async def root():
        return {"app": settings.APP_NAME, "status": "running", "docs": "/docs"}

    return app


app = create_app()
