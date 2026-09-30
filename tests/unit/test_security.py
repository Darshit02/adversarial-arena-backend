"""Unit tests for security utilities: JWT verification, JWKS caching, Fernet encryption, and Svix webhooks."""

import pytest

from app.core.errors import AuthenticationError
from app.core.security import FernetManager, JWKSManager, verify_clerk_webhook_signature


@pytest.mark.asyncio
async def test_fernet_encryption_roundtrip():
    """Verify FernetManager symmetrically encrypts and decrypts secret keys."""
    fm = FernetManager()
    plain_secret = "sk-live-super-secret-key-12345"
    encrypted = fm.encrypt(plain_secret)

    assert encrypted != plain_secret
    assert len(encrypted) > 20

    decrypted = fm.decrypt(encrypted)
    assert decrypted == plain_secret


@pytest.mark.asyncio
async def test_jwt_verification_valid_token(rsa_keypair, token_factory, mock_redis, monkeypatch):
    """Verify valid token against mocked JWKS."""
    _, public_jwk = rsa_keypair
    jm = JWKSManager()

    async def mock_get_jwks(redis=None, force_refresh=False):
        return {"keys": [public_jwk]}

    monkeypatch.setattr(jm, "get_jwks", mock_get_jwks)

    token = token_factory(sub="user_abc_999", exp_delta=3600)
    payload = await jm.verify_token(token, redis=mock_redis)  # type: ignore

    assert payload["sub"] == "user_abc_999"
    assert payload["first_name"] == "Test"


@pytest.mark.asyncio
async def test_jwt_verification_expired_token(rsa_keypair, token_factory, mock_redis, monkeypatch):
    """Verify expired token raises AuthenticationError."""
    _, public_jwk = rsa_keypair
    jm = JWKSManager()

    async def mock_get_jwks(redis=None, force_refresh=False):
        return {"keys": [public_jwk]}

    monkeypatch.setattr(jm, "get_jwks", mock_get_jwks)

    expired_token = token_factory(exp_delta=-60)  # expired 60 seconds ago
    with pytest.raises(AuthenticationError) as exc_info:
        await jm.verify_token(expired_token, redis=mock_redis)  # type: ignore

    assert (
        "Signature has expired" in str(exc_info.value.detail)
        or "expired" in str(exc_info.value.detail).lower()
    )


@pytest.mark.asyncio
async def test_jwt_verification_unknown_kid(rsa_keypair, token_factory, mock_redis, monkeypatch):
    """Verify token with unknown kid claim raises AuthenticationError."""
    _, public_jwk = rsa_keypair
    jm = JWKSManager()

    async def mock_get_jwks(redis=None, force_refresh=False):
        return {"keys": [public_jwk]}  # only has test-kid-1

    monkeypatch.setattr(jm, "get_jwks", mock_get_jwks)

    bad_token = token_factory(kid="unknown-nonexistent-kid")
    with pytest.raises(AuthenticationError) as exc_info:
        await jm.verify_token(bad_token, redis=mock_redis)  # type: ignore

    assert "not found in public JWKS" in str(exc_info.value.detail)


def test_clerk_webhook_signature_failure():
    """Verify invalid Svix webhook signature is rejected with AuthenticationError."""
    payload = b'{"type": "user.created", "data": {"id": "user_123"}}'
    headers = {
        "svix-id": "msg_test",
        "svix-timestamp": "1234567890",
        "svix-signature": "v1,invalid_signature",
    }
    with pytest.raises(AuthenticationError):
        verify_clerk_webhook_signature(
            payload_body=payload,
            headers=headers,
            webhook_secret="whsec_test_secret_key_123",
        )
