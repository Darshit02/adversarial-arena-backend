"""Integration tests for probe templates CRUD endpoints."""

import uuid
from datetime import UTC, datetime

import pytest

from app.db.models.attack_template import AttackTemplate
from app.services.probe_service import probe_service


@pytest.mark.asyncio
async def test_list_probes_endpoint(async_client, monkeypatch):
    """Verify GET /api/v1/probes returns paginated templates."""
    now = datetime.now(UTC)
    sample_template = AttackTemplate(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Test PAIR Template",
        attack_type="pair",
        harm_category="cybersecurity",
        default_parameters={"n_iterations": 3},
        is_builtin=False,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    async def fake_list(session, org_id, page=1, per_page=50):
        return [sample_template], 1

    monkeypatch.setattr(probe_service, "list_templates", fake_list)

    response = await async_client.get("/api/v1/probes")
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert len(body["data"]) == 1
    assert body["data"][0]["name"] == "Test PAIR Template"
    assert body["meta"]["total"] == 1


@pytest.mark.asyncio
async def test_create_probe_endpoint(async_client, monkeypatch):
    """Verify POST /api/v1/probes creates a new template and returns 201."""
    template_id = uuid.uuid4()

    async def fake_create(session, org_id, payload):
        return AttackTemplate(
            id=template_id,
            organization_id=org_id,
            name=payload.name,
            attack_type=payload.attack_type,
            harm_category=payload.harm_category,
            default_parameters=payload.default_parameters,
            is_builtin=False,
            is_active=payload.is_active,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    monkeypatch.setattr(probe_service, "create_template", fake_create)

    payload = {
        "name": "Custom PAIR Experiment",
        "attack_type": "pair",
        "harm_category": "fraud",
        "default_parameters": {"n_iterations": 5},
        "is_active": True,
    }
    response = await async_client.post("/api/v1/probes", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["data"]["id"] == str(template_id)
    assert body["data"]["name"] == "Custom PAIR Experiment"


@pytest.mark.asyncio
async def test_probe_detail_update_delete(async_client, monkeypatch):
    """Verify GET, PATCH, and DELETE endpoints on /api/v1/probes/{id}."""
    template_id = uuid.uuid4()
    now = datetime.now(UTC)

    template = AttackTemplate(
        id=template_id,
        organization_id=uuid.uuid4(),
        name="Probe V1",
        attack_type="pair",
        harm_category="cybersecurity",
        default_parameters={"n_iterations": 3},
        is_builtin=False,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    async def fake_get(session, t_id, org_id):
        return template

    async def fake_update(session, t_id, org_id, payload):
        template.name = payload.name or template.name
        return template

    async def fake_delete(session, t_id, org_id):
        return None

    monkeypatch.setattr(probe_service, "get_template", fake_get)
    monkeypatch.setattr(probe_service, "update_template", fake_update)
    monkeypatch.setattr(probe_service, "delete_template", fake_delete)

    # 1. GET
    res_get = await async_client.get(f"/api/v1/probes/{template_id}")
    assert res_get.status_code == 200
    assert res_get.json()["data"]["name"] == "Probe V1"

    # 2. PATCH
    res_patch = await async_client.patch(
        f"/api/v1/probes/{template_id}",
        json={"name": "Probe V2 Updated"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["data"]["name"] == "Probe V2 Updated"

    # 3. DELETE
    res_del = await async_client.delete(f"/api/v1/probes/{template_id}")
    assert res_del.status_code == 200
    assert "deleted successfully" in res_del.json()["data"]["message"]
