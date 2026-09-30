"""FastAPI dependency injection: database session, Clerk JWT authentication, and rate limiting."""

import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.redis import get_redis
from app.core.security import get_current_user
from app.db.models.organization import Organization
from app.db.models.user import User
from app.db.session import async_session_factory

settings = get_settings()

# Global rate limiter instance
rate_limiter = SlidingWindowRateLimiter()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an asynchronous database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_org(
    current_user: Any = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Organization:
    """Retrieve organization belonging to the authenticated user."""
    # 1. If current_user has organization_id (e.g. User ORM model from tests/fixtures)
    if hasattr(current_user, "organization_id") and current_user.organization_id:
        stmt = select(Organization).where(Organization.id == current_user.organization_id)
        org = (await session.execute(stmt)).scalar_one_or_none()
        if org:
            return org

    # 2. Extract org identifier from dict / AuthUser
    clerk_org_id = current_user.get("org_id") if isinstance(current_user, dict) else None
    if not clerk_org_id:
        clerk_org_id = "org_default"

    # Try UUID lookup first if clerk_org_id happens to be UUID
    try:
        org_uuid = uuid.UUID(str(clerk_org_id))
        stmt = select(Organization).where(
            (Organization.id == org_uuid) | (Organization.clerk_org_id == str(clerk_org_id))
        )
    except (ValueError, TypeError):
        stmt = select(Organization).where(Organization.clerk_org_id == str(clerk_org_id))

    org = (await session.execute(stmt)).scalar_one_or_none()
    if not org:
        org = Organization(
            clerk_org_id=str(clerk_org_id),
            name="Default Research Organization",
            slug=f"org-{str(clerk_org_id)[:8]}",
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)

    return org


async def get_current_user_record(
    current_user: Any = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Retrieve or synchronize database User ORM record for authenticated user."""
    if isinstance(current_user, User):
        return current_user

    clerk_user_id = (
        current_user.get("user_id") if isinstance(current_user, dict) else str(current_user)
    )
    stmt = select(User).where(User.clerk_user_id == clerk_user_id)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if not user:
        org = await get_current_org(current_user=current_user, session=session)
        email = (
            current_user.get("email")
            if isinstance(current_user, dict)
            else f"{clerk_user_id}@clerk.user"
        )
        user = User(
            clerk_user_id=clerk_user_id,
            email=email or f"{clerk_user_id}@clerk.user",
            first_name=current_user.get("first_name") if isinstance(current_user, dict) else None,
            last_name=current_user.get("last_name") if isinstance(current_user, dict) else None,
            role="member",
            organization_id=org.id,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


def rate_limit(scope: str = "default", limit: int = 60, window: int = 60) -> Callable:
    """Dependency factory enforcing rate limits on endpoints."""

    async def _rate_limit_dependency(
        _request: Request,
        current_user: Any = Depends(get_current_user),
        redis: Redis = Depends(get_redis),
    ) -> None:
        user_id = getattr(current_user, "id", None) or (
            current_user.get("user_id") if isinstance(current_user, dict) else str(current_user)
        )
        identifier = f"{scope}:{user_id}"
        rate_limiter.redis = redis
        await rate_limiter.enforce(identifier=identifier, limit=limit, window_seconds=window)

    return _rate_limit_dependency
