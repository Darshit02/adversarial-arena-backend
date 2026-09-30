"""FastAPI dependency injection: database session, Clerk JWT authentication, and rate limiting."""

from collections.abc import AsyncGenerator, Callable

from fastapi import Depends, Header, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AuthenticationError, NotFoundError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import jwks_manager
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


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Provide an async Redis connection client."""
    client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.close()


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> User:
    """Verify Clerk JWT against cached JWKS and retrieve or synchronize User record."""
    if not authorization or not authorization.startswith("Bearer "):
        # In test environment, allow mock test token header
        if settings.is_test and authorization == "Bearer test-jwt-token":
            # Return demo test user
            stmt = select(User).limit(1)
            user = (await session.execute(stmt)).scalar_one_or_none()
            if user:
                return user

        raise AuthenticationError("Missing or malformed Authorization header with Bearer token.")

    token = authorization.split("Bearer ", 1)[1].strip()
    payload = await jwks_manager.verify_token(token, redis=redis)
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise AuthenticationError("Token payload missing subject ('sub') claim.")

    # Fetch user from database
    stmt = select(User).where(User.clerk_user_id == clerk_user_id)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if not user:
        # Check if organization ID is present or resolve default org
        clerk_org_id = payload.get("org_id") or "org_default"
        org_stmt = select(Organization).where(Organization.clerk_org_id == clerk_org_id)
        org = (await session.execute(org_stmt)).scalar_one_or_none()

        if not org:
            org = Organization(
                clerk_org_id=clerk_org_id,
                name="Default Research Organization",
                slug=f"org-{clerk_org_id[:8]}",
            )
            session.add(org)
            await session.flush()

        # Create synchronized user record
        email = payload.get("email") or f"{clerk_user_id}@clerk.user"
        user = User(
            clerk_user_id=clerk_user_id,
            email=email,
            first_name=payload.get("first_name"),
            last_name=payload.get("last_name"),
            role="member",
            organization_id=org.id,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    return user


async def get_current_org(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Organization:
    """Retrieve organization belonging to the authenticated user."""
    stmt = select(Organization).where(Organization.id == current_user.organization_id)
    org = (await session.execute(stmt)).scalar_one_or_none()
    if not org:
        raise NotFoundError("User organization not found.")
    return org


def rate_limit(scope: str = "default", limit: int = 60, window: int = 60) -> Callable:
    """Dependency factory enforcing rate limits on endpoints."""

    async def _rate_limit_dependency(
        _request: Request,
        current_user: User = Depends(get_current_user),
        redis: Redis = Depends(get_redis),
    ) -> None:
        identifier = f"{scope}:{current_user.id}"
        rate_limiter.redis = redis
        await rate_limiter.enforce(identifier=identifier, limit=limit, window_seconds=window)

    return _rate_limit_dependency
