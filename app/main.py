"""FastAPI application factory, lifespan hooks, CORS, RequestID middleware, and Prometheus metrics."""

import secrets
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app.api.health import router as health_router
from app.api.router import api_v1_router
from app.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis_client, init_redis_client
from app.core.security import jwks_manager
from app.db.session import check_db_health, close_db_engine

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

basic_security = HTTPBasic(auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager: initialization, connection check, and graceful teardown."""
    settings = get_settings()
    setup_logging()
    logger.info("Initializing Adversarial Arena backend", env=settings.ENVIRONMENT)

    # 1. Startup: Init Redis pool and store on app.state.redis
    try:
        redis_client = await init_redis_client()
        app.state.redis = redis_client
        await redis_client.ping()
        logger.info("Connected to Redis")
        # Warm JWKS cache in Redis
        try:
            await jwks_manager.get_jwks(redis=redis_client)
            logger.info("JWKS cache warmed in Redis")
        except Exception as e:
            logger.warning("JWKS cache warm-up failed", error=str(e))
    except Exception as e:
        logger.warning("Redis initialization failed on startup", error=str(e))
        app.state.redis = None

    # 2. Startup: Verify database connection
    db_ok = await check_db_health()
    if db_ok:
        logger.info("PostgreSQL database connection verified")
    else:
        logger.warning("PostgreSQL database unavailable or pending startup")

    yield

    # Teardown: Close Redis and DB engine
    logger.info("Shutting down Adversarial Arena backend")
    try:
        await close_redis_client()
    except Exception as e:
        logger.warning("Error closing Redis client", error=str(e))

    try:
        await close_db_engine()
    except Exception as e:
        logger.warning("Error disposing DB engine", error=str(e))


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    is_dev = settings.ENVIRONMENT == "dev" or settings.APP_ENV == "development"

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.4.2",
        description="Research-grade LLM jailbreak attack-defense experimentation and benchmarking platform",
        docs_url="/docs" if is_dev else None,
        redoc_url="/redoc" if is_dev else None,
        openapi_url="/openapi.json" if is_dev else None,
        lifespan=lifespan,
    )

    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
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
            request_id=request_id,
        )
        return response

    # 3. Register RFC 7807 Error Handlers
    register_error_handlers(app)

    # 4. Prometheus metrics endpoint (no auth in dev, basic auth in prod via env)
    @app.get("/metrics", tags=["Observability"])
    async def metrics_endpoint(
        credentials: HTTPBasicCredentials | None = Depends(basic_security),
    ):
        is_prod = settings.ENVIRONMENT == "prod" or settings.APP_ENV == "production"
        if is_prod and settings.METRICS_USER and settings.METRICS_PASSWORD:
            if not credentials:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required for metrics in production",
                    headers={"WWW-Authenticate": "Basic"},
                )
            correct_user = secrets.compare_digest(credentials.username, settings.METRICS_USER)
            correct_pass = secrets.compare_digest(credentials.password, settings.METRICS_PASSWORD)
            if not (correct_user and correct_pass):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid metrics credentials",
                    headers={"WWW-Authenticate": "Basic"},
                )
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # 5. Mount health and ready endpoints at root (NOT under API_BASE_PATH)
    app.include_router(health_router)

    # 6. Mount all other resource routers under API_BASE_PATH
    app.include_router(api_v1_router)

    # Root redirect / status
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "app": settings.APP_NAME,
            "status": "running",
            "version": "0.4.2",
            "docs": "/docs" if is_dev else None,
        }

    return app


app = create_app()
