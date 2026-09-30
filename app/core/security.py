"""Security utilities: Fernet encryption, Clerk JWKS verification, and authentication dependencies."""

import json
import time
from typing import Any

import httpx
from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException, Query, status
from jose import jwt
from jose.exceptions import JWTError
from redis.asyncio import Redis
from svix.webhooks import Webhook, WebhookVerificationError

from app.config import get_settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger(__name__)


class AuthUser(dict):
    """Authenticated user info dictionary with attribute access."""

    @property
    def id(self) -> str:
        return self.get("user_id") or ""

    @property
    def user_id(self) -> str:
        return self.get("user_id") or ""

    @property
    def org_id(self) -> str:
        return self.get("org_id") or ""

    @property
    def email(self) -> str | None:
        return self.get("email")

    @property
    def session_id(self) -> str | None:
        return self.get("session_id")


class FernetManager:
    """Symmetric encryption manager for encrypting sensitive target model API keys at rest."""

    def __init__(self, key: str | None = None) -> None:
        encryption_key = key or get_settings().ENCRYPTION_KEY
        self.fernet = Fernet(encryption_key.encode())

    def encrypt(self, secret: str) -> str:
        """Encrypt plain text into an encrypted url-safe string."""
        if not secret:
            return ""
        return self.fernet.encrypt(secret.encode()).decode()

    def decrypt(self, token: str) -> str:
        """Decrypt cipher token back into original plain text."""
        if not token:
            return ""
        return self.fernet.decrypt(token.encode()).decode()


class JWKSManager:
    """Clerk JWKS fetching, Redis caching (1h TTL, key "clerk:jwks"), and JWT verification."""

    REDIS_JWKS_KEY = "clerk:jwks"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._in_memory_jwks: dict[str, Any] | None = None
        self._in_memory_jwks_expiry: float = 0.0

    async def get_jwks(
        self, redis: Redis | None = None, force_refresh: bool = False
    ) -> dict[str, Any]:
        """Fetch JWKS keys from Redis cache or Clerk endpoint with 1h TTL."""
        now = time.time()

        if not force_refresh:
            if redis is not None:
                try:
                    cached_jwks = await redis.get(self.REDIS_JWKS_KEY)
                    if cached_jwks:
                        if isinstance(cached_jwks, bytes):
                            cached_jwks = cached_jwks.decode("utf-8")
                        return json.loads(cached_jwks)
                except Exception as e:
                    logger.warning(
                        "Redis error reading JWKS cache, falling back to in-memory",
                        error=str(e),
                    )

            if self._in_memory_jwks and now < self._in_memory_jwks_expiry:
                return self._in_memory_jwks

        # Fetch fresh JWKS from Clerk
        logger.info("Fetching fresh JWKS from Clerk endpoint", url=self.settings.CLERK_JWKS_URL)
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(self.settings.CLERK_JWKS_URL)
                response.raise_for_status()
                jwks = response.json()
            except Exception as e:
                logger.error("Failed to fetch Clerk JWKS", error=str(e))
                if self._in_memory_jwks:
                    return self._in_memory_jwks
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unable to retrieve public JWKS for token verification",
                ) from e

        # Update in-memory cache
        self._in_memory_jwks = jwks
        self._in_memory_jwks_expiry = now + self.settings.JWKS_CACHE_TTL_SECONDS

        # Update Redis cache with 1-hour TTL
        if redis is not None:
            try:
                await redis.setex(
                    self.REDIS_JWKS_KEY,
                    self.settings.JWKS_CACHE_TTL_SECONDS,
                    json.dumps(jwks),
                )
            except Exception as e:
                logger.warning("Failed to cache JWKS in Redis", error=str(e))

        return jwks

    async def verify_token(self, token: str, redis: Redis | None = None) -> dict[str, Any]:
        """Verify Clerk JWT against public JWKS with RS256 and issuer validation."""
        try:
            unverified_header = jwt.get_unverified_header(token)
        except JWTError as e:
            raise AuthenticationError(
                detail=f"Invalid JWT header format: {e}",
            ) from e

        kid = unverified_header.get("kid")
        if not kid:
            raise AuthenticationError(
                detail="JWT header missing 'kid' claim",
            )

        jwks = await self.get_jwks(redis=redis, force_refresh=False)
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

        if key is None:
            logger.info("Token 'kid' not in cached JWKS, forcing refresh", kid=kid)
            jwks = await self.get_jwks(redis=redis, force_refresh=True)
            key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

        if key is None:
            raise AuthenticationError(
                detail=f"Signing key with kid '{kid}' not found in public JWKS",
            )

        try:
            options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": bool(self.settings.CLERK_AUDIENCE),
                "verify_iss": bool(self.settings.CLERK_ISSUER),
            }
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.settings.CLERK_ISSUER if self.settings.CLERK_ISSUER else None,
                audience=self.settings.CLERK_AUDIENCE if self.settings.CLERK_AUDIENCE else None,
                options=options,
            )
            return payload
        except JWTError as e:
            raise AuthenticationError(
                detail=f"Token signature verification failed: {e}",
            ) from e


def verify_clerk_webhook_signature(
    payload_body: bytes,
    headers: dict[str, str],
    webhook_secret: str,
) -> dict[str, Any]:
    """Verify Svix webhook signature for Clerk sync events."""
    try:
        wh = Webhook(webhook_secret)
        verified: Any = wh.verify(payload_body, headers)
        if isinstance(verified, dict):
            return verified
        return json.loads(payload_body.decode("utf-8"))
    except WebhookVerificationError as e:
        logger.warning("Clerk webhook signature verification failed", error=str(e))
        raise AuthenticationError(
            detail="Invalid Clerk webhook signature",
        ) from e


# Global instances
fernet_manager = FernetManager()
jwks_manager = JWKSManager()


def _extract_token(authorization: str | None = None, token: str | None = None) -> str | None:
    """Extract raw bearer token from Authorization header or ?token= query parameter."""
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        elif len(parts) == 1 and not token:
            # Fallback if bare token was sent in authorization header
            return parts[0]
    if token:
        return token.strip()
    return None


async def get_current_user(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
    redis: Redis = Depends(get_redis),
) -> AuthUser:
    """FastAPI dependency for verifying Clerk JWT and returning authenticated user dict.

    - Reads bearer token from Authorization header
    - Falls back to ?token= query param (for SSE)
    - Verifies signature against JWKS (RS256)
    - Verifies issuer === settings.CLERK_ISSUER
    - Returns dict: { user_id, org_id, email, session_id }
    - Raises HTTPException(401) with RFC 7807 body on failure
    """
    raw_token = _extract_token(authorization=authorization, token=token)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header with Bearer token.",
        )

    payload = await jwks_manager.verify_token(raw_token, redis=redis)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing subject ('sub') claim.",
        )

    return AuthUser(
        user_id=user_id,
        org_id=payload.get("org_id"),
        email=payload.get("email"),
        session_id=payload.get("sid"),
    )


async def get_current_user_optional(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
    redis: Redis = Depends(get_redis),
) -> AuthUser | None:
    """Optional authentication dependency; returns AuthUser if valid, otherwise None."""
    raw_token = _extract_token(authorization=authorization, token=token)
    if not raw_token:
        return None

    try:
        payload = await jwks_manager.verify_token(raw_token, redis=redis)
        user_id = payload.get("sub")
        if not user_id:
            return None
        return AuthUser(
            user_id=user_id,
            org_id=payload.get("org_id"),
            email=payload.get("email"),
            session_id=payload.get("sid"),
        )
    except Exception:
        return None
