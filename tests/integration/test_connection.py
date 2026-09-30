"""Integration tests for connection layer: CORS, Clerk JWT verification, JWKS caching, SSE streaming, and health checks."""

import json
import time
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.config import get_settings
from app.core.pubsub import is_aborted, publish_run_event, subscribe_run
from app.core.redis import get_redis
from app.core.security import jwks_manager
from app.db.models.organization import Organization
from app.db.models.run import Run
from app.db.models.user import User
from app.dependencies import get_current_org, get_db
from app.main import create_app
from app.services.run_service import run_service

settings = get_settings()


@pytest.fixture
def connection_app(rsa_keypair, mock_redis, mock_db_session, monkeypatch):
    """FastAPI app instance configured for connection layer tests."""
    _, public_jwk = rsa_keypair

    # Mock JWKS fetch to return public JWK for token signature verification
    async def mock_fetch_jwks(redis=None, force_refresh=False):
        data = {"keys": [public_jwk]}
        if redis is not None:
            await redis.setex(
                jwks_manager.REDIS_JWKS_KEY,
                settings.JWKS_CACHE_TTL_SECONDS,
                json.dumps(data),
            )
        return data

    monkeypatch.setattr(jwks_manager, "get_jwks", mock_fetch_jwks)

    async def fake_get_db():
        yield mock_db_session

    app = create_app()
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_db] = fake_get_db
    return app


@pytest.fixture
async def conn_client(connection_app):
    """AsyncClient wired to connection_app."""
    async with AsyncClient(
        transport=ASGITransport(app=connection_app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def auth_token(token_factory):
    """Generate a valid Clerk JWT token."""
    return token_factory(sub="user_clerk_123", org_id="org_test_123")


@pytest.mark.asyncio
async def test_health_returns_ok(conn_client):
    """GET /health returns 200 with status ok and version 0.4.2."""
    response = await conn_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.4.2"}


@pytest.mark.asyncio
async def test_ready_checks_db_and_redis(conn_client, monkeypatch):
    """GET /ready returns 200 when DB and Redis are ok, 503 if either fails."""

    # 1. Healthy state
    async def healthy_db():
        return True

    monkeypatch.setattr("app.api.health.check_db_health", healthy_db)
    response = await conn_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"db": "ok", "redis": "ok"}

    # 2. Database failure simulation
    async def failing_db():
        return False

    monkeypatch.setattr("app.api.health.check_db_health", failing_db)
    fail_response = await conn_client.get("/ready")
    assert fail_response.status_code == 503
    assert fail_response.json() == {"db": "fail", "redis": "ok"}


@pytest.mark.asyncio
async def test_cors_allows_frontend_origin(conn_client):
    """CORS middleware allows configured frontend origin on OPTIONS preflight."""
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization, Content-Type, X-Request-ID",
    }
    response = await conn_client.options("/api/v1/runs", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "GET" in allow_methods
    assert "OPTIONS" in allow_methods


@pytest.mark.asyncio
async def test_cors_rejects_unknown_origin(conn_client):
    """CORS middleware does not permit unlisted untrusted origin."""
    headers = {
        "Origin": "http://unauthorized-evil-site.com",
        "Access-Control-Request-Method": "GET",
    }
    response = await conn_client.options("/api/v1/runs", headers=headers)
    allow_origin = response.headers.get("access-control-allow-origin")
    assert allow_origin != "http://unauthorized-evil-site.com"


@pytest.mark.asyncio
async def test_auth_missing_token_returns_401_problem_json(conn_client):
    """Requests to protected endpoints without token return 401 with RFC 7807 problem details."""
    response = await conn_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers.get("content-type") == "application/problem+json"
    body = response.json()
    assert body["status"] == 401
    assert body["type"] == "https://adversarial-arena.com/errors/unauthorized"
    assert body["title"] == "Unauthorized"
    assert "token" in body["detail"].lower() or "authorization" in body["detail"].lower()


@pytest.mark.asyncio
async def test_auth_invalid_token_returns_401(conn_client):
    """Requests with malformed or invalid JWT signature return 401 problem details."""
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    response = await conn_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.headers.get("content-type") == "application/problem+json"
    body = response.json()
    assert body["status"] == 401
    assert body["type"] == "https://adversarial-arena.com/errors/unauthorized"
    assert body["title"] == "Unauthorized"


@pytest.mark.asyncio
async def test_auth_valid_token_returns_user(conn_client, auth_token):
    """Requests with valid JWT in Authorization header return user and org profile."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = await conn_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "user" in body
    assert body["user"]["id"] == "user_clerk_123"
    assert "org" in body


@pytest.mark.asyncio
async def test_auth_accepts_token_from_query_param(conn_client, auth_token):
    """Authentication accepts fallback ?token= query parameter (for SSE streams)."""
    response = await conn_client.get(f"/api/v1/auth/me?token={auth_token}")
    assert response.status_code == 200
    body = response.json()
    assert "user" in body
    assert body["user"]["id"] == "user_clerk_123"


@pytest.mark.asyncio
async def test_sse_streams_events_for_running_run(conn_client, auth_token, mock_redis, monkeypatch):
    """SSE endpoint streams events from Redis pub/sub for an active benchmark run."""
    run_id = uuid.uuid4()
    org_id = uuid.uuid4()

    mock_run = type("Run", (), {"id": run_id, "status": "running", "organization_id": org_id})()

    async def fake_get_run(session, r_id, o_id):
        return mock_run

    monkeypatch.setattr(run_service, "get_run", fake_get_run)

    # Publish progress and terminal events into mock_redis
    channel_name = f"run:{run_id}"
    await mock_redis.publish(
        channel_name,
        json.dumps({"type": "progress", "data": {"step": 1, "total": 3, "rfr": 0.0}}),
    )
    await mock_redis.publish(
        channel_name,
        json.dumps({"type": "completed", "data": {"status": "completed", "rfr": 0.33}}),
    )

    response = await conn_client.get(
        f"/api/v1/runs/{run_id}/stream",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert "no-cache" in response.headers.get("cache-control", "")
    assert response.headers.get("x-accel-buffering") == "no"

    content = response.text
    assert "event: ping" in content
    assert "event: progress" in content
    assert "event: completed" in content
    assert "0.33" in content


@pytest.mark.asyncio
async def test_sse_returns_final_state_for_completed_run(conn_client, auth_token, monkeypatch):
    """SSE endpoint immediately replays final state and closes if run is already completed."""
    run_id = uuid.uuid4()
    org_id = uuid.uuid4()

    completed_run = type(
        "Run",
        (),
        {
            "id": run_id,
            "status": "completed",
            "organization_id": org_id,
            "metrics": {"rfr": 0.25, "total_attempts": 10},
        },
    )()

    async def fake_get_run(session, r_id, o_id):
        return completed_run

    monkeypatch.setattr(run_service, "get_run", fake_get_run)

    response = await conn_client.get(f"/api/v1/runs/{run_id}/stream?token={auth_token}")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert response.headers.get("cache-control") == "no-cache, no-transform"

    content = response.text
    assert "event: completed" in content
    assert "0.25" in content


@pytest.mark.asyncio
async def test_jwks_is_cached_in_redis(rsa_keypair, mock_redis, monkeypatch):
    """Clerk JWKS keys are fetched and cached in Redis with key 'clerk:jwks' and 1h TTL."""
    _, public_jwk = rsa_keypair
    jm = jwks_manager

    # Clear mock storage
    await mock_redis.delete(jm.REDIS_JWKS_KEY)

    # Mock HTTP response
    fake_jwks = {"keys": [public_jwk]}

    async def mock_http_get(*args, **kwargs):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return fake_jwks

        return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient.get", mock_http_get)

    # 1. Fetch JWKS with empty cache -> caches to Redis
    jwks = await jm.get_jwks(redis=mock_redis, force_refresh=True)
    assert jwks == fake_jwks

    # 2. Verify Redis has the key 'clerk:jwks'
    cached_raw = await mock_redis.get(jm.REDIS_JWKS_KEY)
    assert cached_raw is not None
    cached_data = json.loads(cached_raw)
    assert cached_data == fake_jwks

    # 3. Verify next read hits Redis cache directly
    monkeypatch.setattr(
        "httpx.AsyncClient.get", AsyncMock(side_effect=Exception("Should not fetch"))
    )
    jwks_from_cache = await jm.get_jwks(redis=mock_redis, force_refresh=False)
    assert jwks_from_cache == fake_jwks


@pytest.mark.asyncio
async def test_pubsub_helpers(mock_redis):
    """Verify publish_run_event, subscribe_run, and is_aborted helpers."""
    test_run_id = str(uuid.uuid4())

    # 1. Check is_aborted is False initially
    assert await is_aborted(test_run_id, redis=mock_redis) is False

    # 2. Set abort key and verify is_aborted is True
    await mock_redis.set(f"run:{test_run_id}:abort", "1")
    assert await is_aborted(test_run_id, redis=mock_redis) is True

    # 3. Publish run event
    event = {"type": "progress", "data": {"step": 2}}
    await publish_run_event(test_run_id, event, redis=mock_redis)
    assert len(mock_redis.published_messages) == 1
    ch, msg = mock_redis.published_messages[0]
    assert ch == f"run:{test_run_id}"
    assert json.loads(msg) == event
