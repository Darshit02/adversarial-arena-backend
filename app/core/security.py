"""Security utilities: Fernet encryption, Clerk JWKS verification, and Svix webhook validation."""

import json
import time
from typing import Any

import httpx
from cryptography.fernet import Fernet
from jose import jwt
from jose.exceptions import JWTError
from redis.asyncio import Redis
from svix.webhooks import Webhook, WebhookVerificationError

from app.config import get_settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger

logger = get_logger(__name__)


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
    """Clerk JWKS fetching, Redis caching (1h TTL), and JWT verification."""

    REDIS_JWKS_KEY = "clerk:jwks:cache"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._in_memory_jwks: dict[str, Any] | None = None
        self._in_memory_jwks_expiry: float = 0.0

    async def get_jwks(
        self, redis: Redis | None = None, force_refresh: bool = False
    ) -> dict[str, Any]:
        """Fetch JWKS keys, attempting Redis cache first, then falling back to HTTP request."""
        now = time.time()

        if not force_refresh:
            # Try Redis cache if available
            if redis is not None:
                try:
                    cached_jwks = await redis.get(self.REDIS_JWKS_KEY)
                    if cached_jwks:
                        return json.loads(cached_jwks)
                except Exception as e:
                    logger.warning(
                        "Redis error reading JWKS cache, falling back to in-memory", error=str(e)
                    )

            # Try in-memory cache
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
                # If we have an existing stale JWKS in memory, use it as fallback
                if self._in_memory_jwks:
                    return self._in_memory_jwks
                raise AuthenticationError(
                    f"Unable to retrieve public JWKS for token verification: {e}"
                ) from e

        # Update in-memory cache
        self._in_memory_jwks = jwks
        self._in_memory_jwks_expiry = now + self.settings.JWKS_CACHE_TTL_SECONDS

        # Update Redis cache with 1 hour TTL
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
        """Verify Clerk JWT against public JWKS with kid lookup and key rotation handling."""
        try:
            unverified_header = jwt.get_unverified_header(token)
        except JWTError as e:
            raise AuthenticationError(f"Invalid JWT header format: {e}") from e

        kid = unverified_header.get("kid")
        if not kid:
            raise AuthenticationError("JWT header missing 'kid' claim")

        jwks = await self.get_jwks(redis=redis, force_refresh=False)
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

        # If key not found, refresh JWKS once to accommodate recently rotated keys
        if key is None:
            logger.info("Token 'kid' not in cached JWKS, forcing fresh JWKS fetch", kid=kid)
            jwks = await self.get_jwks(redis=redis, force_refresh=True)
            key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

        if key is None:
            raise AuthenticationError(f"Signing key with kid '{kid}' not found in public JWKS")

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
            raise AuthenticationError(f"JWT signature verification failed: {e}") from e


def verify_clerk_webhook_signature(
    payload_body: bytes,
    headers: dict[str, str],
    webhook_secret: str,
) -> dict[str, Any]:
    """Verify Svix webhook signature for Clerk sync events."""
    try:
        wh = Webhook(webhook_secret)
        # svix requires svix-id, svix-timestamp, svix-signature in headers
        verified: Any = wh.verify(payload_body, headers)  # type: ignore[func-returns-value]
        if isinstance(verified, dict):
            return verified
        return json.loads(payload_body.decode("utf-8"))
    except WebhookVerificationError as e:
        logger.warning("Clerk webhook signature verification failed", error=str(e))
        raise AuthenticationError("Invalid Clerk webhook signature") from e


# Global instances
fernet_manager = FernetManager()
jwks_manager = JWKSManager()
