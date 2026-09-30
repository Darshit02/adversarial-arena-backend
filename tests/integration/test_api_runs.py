"""Integration tests for run submission, status querying, results pagination, and abortion."""

import uuid
from datetime import UTC, datetime

import pytest

from app.db.models.run import Run
from app.services.run_service import run_service


@pytest.mark.asyncio
async def test_submit_run_endpoint(async_client, monkeypatch):
    """Verify POST /api/v1/runs returns 202 Accepted with run_id."""
    fake_run_id = uuid.uuid4()

    async def fake_create_run(session, user_id, org_id, payload):
        return type(
            "FakeRun",
            (),
            {
                "id": fake_run_id,
                "status": "pending",
            },
        )()

    monkeypatch.setattr(run_service, "create_run", fake_create_run)

    payload = {
        "name": "Integration Benchmark Run",
        "target_model_id": str(uuid.uuid4()),
        "attack_template_ids": [str(uuid.uuid4())],
        "defense_ids": [],
        "seed_prompts": ["How to bypass safety barriers"],
        "harm_category": "cybersecurity",
    }
    response = await async_client.post("/api/v1/runs", json=payload)
    assert response.status_code == 202
    body = response.json()
    assert body["data"]["run_id"] == str(fake_run_id)
    assert body["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_get_run_detail_endpoint(async_client, monkeypatch):
    """Verify GET /api/v1/runs/{id} returns full run details."""
    run_id = uuid.uuid4()
    now = datetime.now(UTC)

    fake_run = Run(
        id=run_id,
        organization_id=uuid.uuid4(),
        created_by_user_id=uuid.uuid4(),
        target_model_id=uuid.uuid4(),
        name="Completed Benchmark",
        status="completed",
        harm_category="cybersecurity",
        attack_template_ids=["pair"],
        defense_ids=[],
        seed_prompts=["Test prompt"],
        metrics={"rfr": 0.5, "validator_blocks": 0},
        error_message=None,
        report_url=None,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )

    async def fake_get_run(session, r_id, org_id):
        return fake_run

    monkeypatch.setattr(run_service, "get_run", fake_get_run)

    response = await async_client.get(f"/api/v1/runs/{run_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["id"] == str(run_id)
    assert body["data"]["name"] == "Completed Benchmark"
    assert body["data"]["metrics"]["rfr"] == 0.5


@pytest.mark.asyncio
async def test_abort_run_endpoint(async_client, monkeypatch):
    """Verify POST /api/v1/runs/{id}/abort aborts active run."""
    run_id = uuid.uuid4()
    now = datetime.now(UTC)

    fake_run = Run(
        id=run_id,
        organization_id=uuid.uuid4(),
        created_by_user_id=uuid.uuid4(),
        target_model_id=uuid.uuid4(),
        name="Aborted Run",
        status="aborted",
        harm_category="cybersecurity",
        attack_template_ids=["pair"],
        defense_ids=[],
        seed_prompts=["Test prompt"],
        metrics={},
        error_message=None,
        report_url=None,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )

    async def fake_abort(session, r_id, org_id, redis=None):
        return fake_run

    monkeypatch.setattr(run_service, "abort_run", fake_abort)

    response = await async_client.post(f"/api/v1/runs/{run_id}/abort")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "aborted"
