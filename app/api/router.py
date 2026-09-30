"""Main API router aggregating all resource sub-routers under settings.API_BASE_PATH."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.models import router as models_router
from app.api.probes import router as probes_router
from app.api.reports import router as reports_router
from app.api.runs import router as runs_router
from app.api.validators import router as validators_router
from app.api.webhooks import router as webhooks_router
from app.config import get_settings

settings = get_settings()
api_v1_router = APIRouter(prefix=settings.API_BASE_PATH)

# Mount resource endpoints (Note: /health and /ready are mounted at root in main.py)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(probes_router)
api_v1_router.include_router(models_router)
api_v1_router.include_router(validators_router)
api_v1_router.include_router(runs_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(webhooks_router)

# Neutral aliases for backward compatibility with initial spec routes
api_v1_router.include_router(probes_router, prefix="/attacks", tags=["Attacks (Alias)"])
api_v1_router.include_router(validators_router, prefix="/defenses", tags=["Defenses (Alias)"])
