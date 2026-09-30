"""Pytest configuration and shared test fixtures."""

import time
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jose import jwt
from jose.jwk import RSAKey

from app.config import get_settings
from app.core.security import jwks_manager
from app.db.models.organization import Organization
from app.db.models.user import User
from app.dependencies import get_current_org, get_current_user, get_db, get_redis
from app.main import create_app
from app.targets.mock_client import MockTargetModel


class MockRedis:
    """In-memory mock Redis supporting key-value, sorted sets, and pub/sub."""

    def __init__(self) -> None:
        self.storage: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.published_messages: list[tuple[str, str]] = []

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)

    async def set(self, key: str, value: str) -> bool:
        self.storage[key] = value
        return True

    async def setex(self, key: str, time_sec: int, value: str) -> bool:
        self.storage[key] = value
        return True

    async def exists(self, key: str) -> int:
        return 1 if (key in self.storage or key in self.zsets) else 0

    async def delete(self, key: str) -> int:
        removed = 0
        if key in self.storage:
            del self.storage[key]
            removed = 1
        if key in self.zsets:
            del self.zsets[key]
            removed = 1
        return removed

    async def publish(self, channel: str, message: str) -> int:
        self.published_messages.append((channel, message))
        return 1

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def pipeline(self) -> "MockRedisPipeline":
        return MockRedisPipeline(self)

    def pubsub(self) -> "MockPubSub":
        return MockPubSub(self)


class MockRedisPipeline:
    def __init__(self, redis: MockRedis) -> None:
        self.redis = redis
        self.commands: list[tuple[str, tuple, dict]] = []

    def zremrangebyscore(self, key: str, min_s: float, max_s: float):
        self.commands.append(("zremrangebyscore", (key, min_s, max_s), {}))
        return self

    def zcard(self, key: str):
        self.commands.append(("zcard", (key,), {}))
        return self

    def zadd(self, key: str, mapping: dict[str, float]):
        self.commands.append(("zadd", (key, mapping), {}))
        return self

    def expire(self, key: str, time_sec: int):
        self.commands.append(("expire", (key, time_sec), {}))
        return self

    async def execute(self) -> list[Any]:
        results = []
        for cmd, args, _kwargs in self.commands:
            if cmd == "zremrangebyscore":
                key, min_s, max_s = args
                z = self.redis.zsets.get(key, {})
                to_del = [m for m, s in z.items() if min_s <= s <= max_s]
                for m in to_del:
                    del z[m]
                results.append(len(to_del))
            elif cmd == "zcard":
                key = args[0]
                results.append(len(self.redis.zsets.get(key, {})))
            elif cmd == "zadd":
                key, mapping = args
                if key not in self.redis.zsets:
                    self.redis.zsets[key] = {}
                self.redis.zsets[key].update(mapping)
                results.append(len(mapping))
            elif cmd == "expire":
                results.append(1)
        self.commands.clear()
        return results


class MockPubSub:
    def __init__(self, redis: MockRedis) -> None:
        self.redis = redis
        self.subscribed_channels: set[str] = set()

    async def subscribe(self, channel: str) -> None:
        self.subscribed_channels.add(channel)

    async def unsubscribe(self, channel: str) -> None:
        self.subscribed_channels.discard(channel)

    async def get_message(
        self, ignore_subscribe_messages: bool = True, timeout: float = 1.0
    ) -> dict | None:
        if self.redis.published_messages:
            ch, msg = self.redis.published_messages.pop(0)
            return {"type": "message", "channel": ch, "data": msg}
        return None

    async def aclose(self) -> None:
        pass


@pytest.fixture(scope="session")
def rsa_keypair():
    """Generate RSA keypair for testing JWKS token signing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    rsa_jwk = RSAKey(key=private_pem, algorithm="RS256").to_dict()
    public_jwk = {
        "kty": rsa_jwk.get("kty"),
        "n": rsa_jwk.get("n"),
        "e": rsa_jwk.get("e"),
        "kid": "test-kid-1",
        "use": "sig",
        "alg": "RS256",
    }
    return private_pem, public_jwk


@pytest.fixture
def token_factory(rsa_keypair):
    """Factory creating signed JWT tokens."""
    private_pem, _ = rsa_keypair

    def _create(
        sub: str = "user_clerk_123",
        org_id: str = "org_clerk_456",
        exp_delta: int = 3600,
        kid: str = "test-kid-1",
    ) -> str:
        now = int(time.time())
        payload = {
            "sub": sub,
            "org_id": org_id,
            "email": f"{sub}@example.com",
            "first_name": "Test",
            "last_name": "Researcher",
            "iat": now,
            "nbf": now,
            "exp": now + exp_delta,
            "iss": get_settings().CLERK_ISSUER,
        }
        return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})

    return _create


@pytest.fixture
def mock_redis():
    return MockRedis()


@pytest.fixture
def mock_mut():
    return MockTargetModel()


@pytest.fixture
def demo_org():
    return Organization(
        id=uuid.uuid4(),
        clerk_org_id="org_test_123",
        name="Test Research Organization",
        slug="test-research-org",
    )


@pytest.fixture
def demo_user(demo_org):
    return User(
        id=uuid.uuid4(),
        clerk_user_id="user_clerk_123",
        email="researcher@example.com",
        first_name="Jane",
        last_name="Doe",
        role="security_lead",
        organization_id=demo_org.id,
    )


@pytest.fixture
def mock_db_session():
    """In-memory mock AsyncSession for fast offline unit/integration testing."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    mock_session.commit = AsyncMock()
    mock_session.delete = AsyncMock()

    async def fake_refresh(instance):
        if not getattr(instance, "id", None):
            instance.id = uuid.uuid4()
        if not getattr(instance, "created_at", None):
            instance.created_at = datetime.now(UTC)
        if not getattr(instance, "updated_at", None):
            instance.updated_at = datetime.now(UTC)

    mock_session.refresh = AsyncMock(side_effect=fake_refresh)
    mock_session.add = MagicMock()
    return mock_session


@pytest.fixture
def app_with_mocks(rsa_keypair, mock_redis, mock_db_session, demo_user, demo_org, monkeypatch):
    """FastAPI application instance configured with in-memory test mocks."""
    _, public_jwk = rsa_keypair

    # Mock JWKS endpoint return
    async def mock_get_jwks(redis=None, force_refresh=False):
        return {"keys": [public_jwk]}

    monkeypatch.setattr(jwks_manager, "get_jwks", mock_get_jwks)

    async def fake_get_db():
        yield mock_db_session

    app = create_app()
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_current_user] = lambda: demo_user
    app.dependency_overrides[get_current_org] = lambda: demo_org
    app.dependency_overrides[get_db] = fake_get_db
    return app


@pytest.fixture
async def async_client(app_with_mocks):
    """Async HTTP client for testing API routes."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as client:
        yield client
