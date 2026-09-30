"""Target Models (ModelUnderTest) configuration and connectivity test endpoints."""

import time
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.security import fernet_manager
from app.db.models.organization import Organization
from app.db.models.target_model import TargetModelConfig
from app.dependencies import get_current_org, get_db
from app.schemas.common import ResponseEnvelope
from app.schemas.model import (
    TargetModelCreate,
    TargetModelResponse,
    TestConnectionRequest,
    TestConnectionResponse,
)
from app.targets.factory import target_model_factory

router = APIRouter(prefix="/models", tags=["Models"])


@router.get("", response_model=ResponseEnvelope[list[TargetModelResponse]])
async def list_models(
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[list[TargetModelResponse]]:
    """List all ModelUnderTest configurations for the current organization."""
    stmt = (
        select(TargetModelConfig)
        .where(TargetModelConfig.organization_id == org.id)
        .order_by(TargetModelConfig.created_at.desc())
    )
    models = (await session.execute(stmt)).scalars().all()

    data = [
        TargetModelResponse(
            id=m.id,
            organization_id=m.organization_id,
            name=m.name,
            provider=m.provider,
            model_identifier=m.model_identifier,
            endpoint_url=m.endpoint_url,
            default_temperature=m.default_temperature,
            default_max_tokens=m.default_max_tokens,
            is_whitebox=m.is_whitebox,
            is_active=m.is_active,
            metadata_json=m.metadata_json,
            has_api_key=bool(m.encrypted_api_key),
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in models
    ]
    return ResponseEnvelope.success(data)


@router.post(
    "", response_model=ResponseEnvelope[TargetModelResponse], status_code=status.HTTP_201_CREATED
)
async def create_model(
    payload: TargetModelCreate,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[TargetModelResponse]:
    """Create ModelUnderTest configuration, securely encrypting API credentials at rest."""
    encrypted_key = fernet_manager.encrypt(payload.api_key) if payload.api_key else None

    model_config = TargetModelConfig(
        organization_id=org.id,
        name=payload.name,
        provider=payload.provider,
        model_identifier=payload.model_identifier,
        endpoint_url=payload.endpoint_url,
        encrypted_api_key=encrypted_key,
        default_temperature=payload.default_temperature,
        default_max_tokens=payload.default_max_tokens,
        is_whitebox=payload.is_whitebox,
        is_active=payload.is_active,
        metadata_json=payload.metadata_json,
    )
    session.add(model_config)
    await session.commit()
    await session.refresh(model_config)

    res = TargetModelResponse(
        id=model_config.id,
        organization_id=model_config.organization_id,
        name=model_config.name,
        provider=model_config.provider,
        model_identifier=model_config.model_identifier,
        endpoint_url=model_config.endpoint_url,
        default_temperature=model_config.default_temperature,
        default_max_tokens=model_config.default_max_tokens,
        is_whitebox=model_config.is_whitebox,
        is_active=model_config.is_active,
        metadata_json=model_config.metadata_json,
        has_api_key=bool(model_config.encrypted_api_key),
        created_at=model_config.created_at,
        updated_at=model_config.updated_at,
    )
    return ResponseEnvelope.success(res)


@router.post("/{id}/test", response_model=ResponseEnvelope[TestConnectionResponse])
async def test_model_connectivity(
    id: uuid.UUID,
    payload: TestConnectionRequest = TestConnectionRequest(),
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[TestConnectionResponse]:
    """Verify live connectivity and latency against ModelUnderTest endpoint."""
    stmt = select(TargetModelConfig).where(
        TargetModelConfig.id == id,
        TargetModelConfig.organization_id == org.id,
    )
    model_config = (await session.execute(stmt)).scalar_one_or_none()
    if not model_config:
        raise NotFoundError(f"Target model '{id}' not found.")

    start_time = time.perf_counter()
    try:
        mut = target_model_factory.create_from_config(model_config)
        gen_result = await mut.generate(payload.prompt)
        latency = (time.perf_counter() - start_time) * 1000

        data = TestConnectionResponse(
            success=True,
            status_code=200,
            latency_ms=round(latency, 2),
            output=gen_result.text[:500],
            error=None,
        )
    except Exception as e:
        latency = (time.perf_counter() - start_time) * 1000
        data = TestConnectionResponse(
            success=False,
            status_code=502,
            latency_ms=round(latency, 2),
            output=None,
            error=str(e),
        )

    return ResponseEnvelope.success(data)


@router.delete("/{id}", response_model=ResponseEnvelope[dict[str, str]])
async def delete_model(
    id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[dict[str, str]]:
    """Delete a ModelUnderTest configuration."""
    stmt = select(TargetModelConfig).where(
        TargetModelConfig.id == id,
        TargetModelConfig.organization_id == org.id,
    )
    model_config = (await session.execute(stmt)).scalar_one_or_none()
    if not model_config:
        raise NotFoundError(f"Target model '{id}' not found.")

    await session.delete(model_config)
    await session.commit()
    return ResponseEnvelope.success({"message": f"Model '{id}' deleted successfully."})
