"""Probe service handling template CRUD, parameter validation, and algorithm discovery."""

from typing import Any
import uuid
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.db.models.attack_template import AttackTemplate
from app.probes.registry import get_probe_class, list_registered_probes
from app.schemas.attack import (
    AttackTemplateCreate,
    AttackTemplateUpdate,
    RegisteredAttackInfo,
)


class ProbeService:
    """Manages probe templates and parameter validation."""

    def list_probe_types(self) -> list[dict[str, Any]]:
        """List all available probe algorithms registered in the engine."""
        return list_registered_probes()

    def validate_probe_params(self, probe_type: str, params: dict[str, Any]) -> None:
        """Validate parameter dictionary against probe algorithm's Pydantic schema."""
        try:
            probe_cls = get_probe_class(probe_type)
        except KeyError:
            raise ValidationError(f"Unknown probe type '{probe_type}'.")

        if hasattr(probe_cls, "param_schema") and probe_cls.param_schema:
            try:
                probe_cls.param_schema(**params)
            except Exception as e:
                raise ValidationError(f"Invalid parameters for probe '{probe_type}': {e}")

    async def list_templates(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[AttackTemplate], int]:
        """List templates belonging to the organization or system built-in presets."""
        offset = (page - 1) * per_page
        condition = or_(
            AttackTemplate.organization_id == org_id,
            AttackTemplate.is_builtin.is_(True),
        )

        count_stmt = select(func.count(AttackTemplate.id)).where(condition)
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(AttackTemplate)
            .where(condition)
            .order_by(AttackTemplate.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        templates = (await session.execute(stmt)).scalars().all()
        return list(templates), total

    async def get_template(
        self,
        session: AsyncSession,
        template_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> AttackTemplate:
        """Get template by ID, verifying organizational ownership or built-in access."""
        stmt = select(AttackTemplate).where(
            AttackTemplate.id == template_id,
            or_(AttackTemplate.organization_id == org_id, AttackTemplate.is_builtin.is_(True)),
        )
        result = (await session.execute(stmt)).scalar_one_or_none()
        if not result:
            raise NotFoundError(f"Probe template '{template_id}' not found.")
        return result

    async def create_template(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        data: AttackTemplateCreate,
    ) -> AttackTemplate:
        """Create a new custom probe template after parameter validation."""
        self.validate_probe_params(data.attack_type, data.default_parameters)

        template = AttackTemplate(
            organization_id=org_id,
            name=data.name,
            attack_type=data.attack_type,
            description=data.description,
            harm_category=data.harm_category,
            default_parameters=data.default_parameters,
            is_builtin=False,
            is_active=data.is_active,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template

    async def update_template(
        self,
        session: AsyncSession,
        template_id: uuid.UUID,
        org_id: uuid.UUID,
        data: AttackTemplateUpdate,
    ) -> AttackTemplate:
        """Update an existing custom probe template."""
        template = await self.get_template(session, template_id, org_id)
        if template.is_builtin:
            raise ValidationError("Cannot modify built-in system probe templates.")

        if data.default_parameters is not None:
            self.validate_probe_params(template.attack_type, data.default_parameters)
            template.default_parameters = data.default_parameters

        if data.name is not None:
            template.name = data.name
        if data.description is not None:
            template.description = data.description
        if data.harm_category is not None:
            template.harm_category = data.harm_category
        if data.is_active is not None:
            template.is_active = data.is_active

        await session.commit()
        await session.refresh(template)
        return template

    async def delete_template(
        self,
        session: AsyncSession,
        template_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> None:
        """Soft delete or remove a custom probe template."""
        template = await self.get_template(session, template_id, org_id)
        if template.is_builtin:
            raise ValidationError("Cannot delete built-in system probe templates.")

        await session.delete(template)
        await session.commit()


probe_service = ProbeService()
