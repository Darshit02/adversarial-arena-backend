"""Integration tests verifying HTTP API endpoints, health probes, Prometheus metrics, and error handling."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def test_app():
    return create_app()


@pytest.mark.asyncio
async def test_health_endpoint(test_app):
    """Verify liveness probe returns status ok."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_endpoint(test_app):
    """Verify readiness probe returns connectivity status."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/ready")
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "redis" in data


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint(test_app):
    """Verify Prometheus metrics are exported at /metrics."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert "arena_runs_total" in response.text


@pytest.mark.asyncio
async def test_probe_registry_endpoint(test_app):
    """Verify probe registry endpoint returns all registered probe algorithms and schemas."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/probes/registry")
        assert response.status_code == 200
        body = response.json()
        assert body["error"] is None
        data = body["data"]
        names = {p["name"] for p in data}
        assert "pair" in names
        assert "multiround" in names
        assert "autodan" in names
        assert "gcg" in names
        assert "knowledge_decomp" in names


@pytest.mark.asyncio
async def test_unauthenticated_request_rfc7807(test_app):
    """Verify protected routes return RFC 7807 problem details when unauthenticated."""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["status"] == 401
        assert body["title"] == "Authentication Failed"
        assert "Bearer" in body["detail"]
