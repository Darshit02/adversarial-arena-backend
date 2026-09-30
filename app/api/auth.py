"""Authentication and current user profile endpoints."""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me")
async def get_me(
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Return currently authenticated user and organization profile."""
    user_id = getattr(current_user, "id", None) or (
        current_user.get("user_id") if isinstance(current_user, dict) else str(current_user)
    )
    clerk_user_id = getattr(current_user, "clerk_user_id", None) or (
        current_user.get("user_id") if isinstance(current_user, dict) else str(current_user)
    )
    email = getattr(current_user, "email", None) or (
        current_user.get("email") if isinstance(current_user, dict) else None
    )
    first_name = getattr(current_user, "first_name", None) or (
        current_user.get("first_name") if isinstance(current_user, dict) else None
    )
    last_name = getattr(current_user, "last_name", None) or (
        current_user.get("last_name") if isinstance(current_user, dict) else None
    )
    role = getattr(current_user, "role", None) or (
        current_user.get("role") if isinstance(current_user, dict) else "member"
    )
    session_id = current_user.get("session_id") if isinstance(current_user, dict) else None

    org_id = getattr(current_user, "organization_id", None) or (
        current_user.get("org_id") if isinstance(current_user, dict) else None
    )

    return {
        "user": {
            "id": str(user_id) if user_id else None,
            "clerk_user_id": str(clerk_user_id) if clerk_user_id else None,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "role": role,
            "session_id": session_id,
        },
        "org": {
            "id": str(org_id) if org_id else None,
        },
    }
