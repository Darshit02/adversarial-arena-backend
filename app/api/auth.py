"""Authentication and current user endpoints."""

from typing import Any
from fastapi import APIRouter, Depends

from app.dependencies import get_current_org, get_current_user
from app.db.models.organization import Organization
from app.db.models.user import User
from app.schemas.common import ResponseEnvelope

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=ResponseEnvelope[dict[str, Any]])
async def get_me(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> ResponseEnvelope[dict[str, Any]]:
    """Return currently authenticated user and organization profile."""
    data = {
        "user": {
            "id": str(current_user.id),
            "clerk_user_id": current_user.clerk_user_id,
            "email": current_user.email,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "role": current_user.role,
        },
        "organization": {
            "id": str(org.id),
            "clerk_org_id": org.clerk_org_id,
            "name": org.name,
            "slug": org.slug,
        },
    }
    return ResponseEnvelope.success(data)
