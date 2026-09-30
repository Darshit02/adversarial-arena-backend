"""Probe templates CRUD and discovery registry endpoints."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.organization import Organization
from app.dependencies import get_current_org, get_db
from app.schemas.attack import (
    AttackTemplateCreate,
    AttackTemplateResponse,
    AttackTemplateUpdate,
)
from app.schemas.common import ResponseEnvelope
from app.services.probe_service import probe_service

router = APIRouter(prefix="/probes", tags=["Probes"])


@router.get("/registry", response_model=ResponseEnvelope[list[dict[str, Any]]])
async def get_probe_registry() -> ResponseEnvelope[list[dict[str, Any]]]:
    """List all available probe algorithms registered in the engine with their parameter schemas."""
    catalog = probe_service.list_probe_types()
    return ResponseEnvelope.success(catalog)


@router.get("", response_model=ResponseEnvelope[list[AttackTemplateResponse]])
async def list_probes(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=500),
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[list[AttackTemplateResponse]]:
    """List custom and built-in probe templates with pagination."""
    templates, total = await probe_service.list_templates(
        session, org.id, page=page, per_page=per_page
    )
    data = [AttackTemplateResponse.model_validate(t) for t in templates]
    return ResponseEnvelope.paginated(data=data, page=page, per_page=per_page, total=total)


@router.post(
    "", response_model=ResponseEnvelope[AttackTemplateResponse], status_code=status.HTTP_201_CREATED
)
async def create_probe(
    payload: AttackTemplateCreate,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[AttackTemplateResponse]:
    """Create a new custom probe template."""
    template = await probe_service.create_template(session, org.id, payload)
    return ResponseEnvelope.success(AttackTemplateResponse.model_validate(template))


@router.get("/{id}", response_model=ResponseEnvelope[AttackTemplateResponse])
async def get_probe_detail(
    id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[AttackTemplateResponse]:
    """Retrieve details for a specific probe template."""
    template = await probe_service.get_template(session, id, org.id)
    return ResponseEnvelope.success(AttackTemplateResponse.model_validate(template))


@router.patch("/{id}", response_model=ResponseEnvelope[AttackTemplateResponse])
async def update_probe(
    id: uuid.UUID,
    payload: AttackTemplateUpdate,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[AttackTemplateResponse]:
    """Update a custom probe template."""
    template = await probe_service.update_template(session, id, org.id, payload)
    return ResponseEnvelope.success(AttackTemplateResponse.model_validate(template))


@router.delete("/{id}", response_model=ResponseEnvelope[dict[str, str]])
async def delete_probe(
    id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[dict[str, str]]:
    """Delete a custom probe template."""
    await probe_service.delete_template(session, id, org.id)
    return ResponseEnvelope.success({"message": f"Probe template '{id}' deleted successfully."})
