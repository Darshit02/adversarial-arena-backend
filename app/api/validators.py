"""Validator configurations CRUD endpoints."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models.defense_config import DefenseConfig
from app.db.models.organization import Organization
from app.dependencies import get_current_org, get_db
from app.schemas.common import ResponseEnvelope
from app.schemas.defense import (
    DefenseConfigCreate,
    DefenseConfigResponse,
    DefenseConfigUpdate,
)
from app.validators.registry import list_registered_validators

router = APIRouter(prefix="/validators", tags=["Validators"])


@router.get("/registry", response_model=ResponseEnvelope[list[dict]])
async def get_validator_registry() -> ResponseEnvelope[list[dict]]:
    """List available safety validator algorithms and their parameter schemas."""
    return ResponseEnvelope.success(list_registered_validators())


@router.get("", response_model=ResponseEnvelope[list[DefenseConfigResponse]])
async def list_validators(
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[list[DefenseConfigResponse]]:
    """List all active validator rules configured for the organization."""
    stmt = (
        select(DefenseConfig)
        .where(DefenseConfig.organization_id == org.id)
        .order_by(DefenseConfig.priority.asc())
    )
    items = (await session.execute(stmt)).scalars().all()
    data = [DefenseConfigResponse.model_validate(v) for v in items]
    return ResponseEnvelope.success(data)


@router.post(
    "", response_model=ResponseEnvelope[DefenseConfigResponse], status_code=status.HTTP_201_CREATED
)
async def create_validator(
    payload: DefenseConfigCreate,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[DefenseConfigResponse]:
    """Register a new validator rule in the organization pipeline."""
    config = DefenseConfig(
        organization_id=org.id,
        name=payload.name,
        defense_type=payload.defense_type,
        description=payload.description,
        parameters=payload.parameters,
        priority=payload.priority,
        is_active=payload.is_active,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return ResponseEnvelope.success(DefenseConfigResponse.model_validate(config))


@router.patch("/{id}", response_model=ResponseEnvelope[DefenseConfigResponse])
async def update_validator(
    id: uuid.UUID,
    payload: DefenseConfigUpdate,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[DefenseConfigResponse]:
    """Update validator hyperparameters or priority ordering."""
    stmt = select(DefenseConfig).where(
        DefenseConfig.id == id,
        DefenseConfig.organization_id == org.id,
    )
    config = (await session.execute(stmt)).scalar_one_or_none()
    if not config:
        raise NotFoundError(f"Validator '{id}' not found.")

    if payload.name is not None:
        config.name = payload.name
    if payload.description is not None:
        config.description = payload.description
    if payload.parameters is not None:
        config.parameters = payload.parameters
    if payload.priority is not None:
        config.priority = payload.priority
    if payload.is_active is not None:
        config.is_active = payload.is_active

    await session.commit()
    await session.refresh(config)
    return ResponseEnvelope.success(DefenseConfigResponse.model_validate(config))


@router.delete("/{id}", response_model=ResponseEnvelope[dict[str, str]])
async def delete_validator(
    id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[dict[str, str]]:
    """Delete a validator rule."""
    stmt = select(DefenseConfig).where(
        DefenseConfig.id == id,
        DefenseConfig.organization_id == org.id,
    )
    config = (await session.execute(stmt)).scalar_one_or_none()
    if not config:
        raise NotFoundError(f"Validator '{id}' not found.")

    await session.delete(config)
    await session.commit()
    return ResponseEnvelope.success({"message": f"Validator '{id}' deleted successfully."})
