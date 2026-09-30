"""Integration tests for models, validators, and reports API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.db.models.defense_config import DefenseConfig
from app.db.models.target_model import TargetModelConfig
from app.services.report_service import report_service


@pytest.mark.asyncio
async def test_models_api_lifecycle(async_client, mock_db_session):
    """Verify listing, creating, testing, and deleting target models."""
    now = datetime.now(UTC)
    model_id = uuid.uuid4()
    org_id = uuid.uuid4()

    sample_model = TargetModelConfig(
        id=model_id,
        organization_id=org_id,
        name="Mock GPT-4",
        provider="mock",
        model_identifier="mock-model",
        endpoint_url=None,
        encrypted_api_key=None,
        default_temperature=0.7,
        default_max_tokens=500,
        is_whitebox=False,
        is_active=True,
        metadata_json={},
        created_at=now,
        updated_at=now,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sample_model]
    mock_result.scalar_one_or_none.return_value = sample_model
    mock_db_session.execute.return_value = mock_result

    # 1. List models
    res_list = await async_client.get("/api/v1/models")
    assert res_list.status_code == 200
    assert len(res_list.json()["data"]) == 1

    # 2. Create model
    create_payload = {
        "name": "New GPT-4 Target",
        "provider": "openai",
        "model_identifier": "gpt-4o",
        "api_key": "sk-mock-key-12345",
        "default_temperature": 0.7,
        "default_max_tokens": 1000,
        "is_whitebox": False,
        "is_active": True,
    }
    res_create = await async_client.post("/api/v1/models", json=create_payload)
    assert res_create.status_code == 201
    assert res_create.json()["data"]["name"] == "New GPT-4 Target"

    # 3. Test connectivity
    res_test = await async_client.post(
        f"/api/v1/models/{model_id}/test",
        json={"prompt": "Test connection ping"},
    )
    assert res_test.status_code == 200
    assert res_test.json()["data"]["success"] is True

    # 4. Delete model
    res_del = await async_client.delete(f"/api/v1/models/{model_id}")
    assert res_del.status_code == 200
    assert "deleted successfully" in res_del.json()["data"]["message"]


@pytest.mark.asyncio
async def test_validators_api_lifecycle(async_client, mock_db_session):
    """Verify validator registry, list, create, update, and delete endpoints."""
    now = datetime.now(UTC)
    val_id = uuid.uuid4()
    org_id = uuid.uuid4()

    sample_val = DefenseConfig(
        id=val_id,
        organization_id=org_id,
        name="Production Keyword Filter",
        defense_type="keyword_filter",
        description="Filter keywords",
        parameters={"blocked_keywords": ["jailbreak"]},
        priority=1,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [sample_val]
    mock_result.scalar_one_or_none.return_value = sample_val
    mock_db_session.execute.return_value = mock_result

    # 1. Registry
    res_reg = await async_client.get("/api/v1/validators/registry")
    assert res_reg.status_code == 200
    assert len(res_reg.json()["data"]) >= 3

    # 2. List
    res_list = await async_client.get("/api/v1/validators")
    assert res_list.status_code == 200
    assert len(res_list.json()["data"]) == 1

    # 3. Create
    create_payload = {
        "name": "New LLM Judge",
        "defense_type": "llm_judge",
        "description": "Evaluates policies",
        "parameters": {"judge_model": "gpt-4o-mini"},
        "priority": 2,
        "is_active": True,
    }
    res_create = await async_client.post("/api/v1/validators", json=create_payload)
    assert res_create.status_code == 201
    assert res_create.json()["data"]["name"] == "New LLM Judge"

    # 4. Update
    res_update = await async_client.patch(
        f"/api/v1/validators/{val_id}",
        json={"name": "Updated Keyword Filter", "priority": 5},
    )
    assert res_update.status_code == 200
    assert res_update.json()["data"]["name"] == "Updated Keyword Filter"

    # 5. Delete
    res_delete = await async_client.delete(f"/api/v1/validators/{val_id}")
    assert res_delete.status_code == 200
    assert "deleted successfully" in res_delete.json()["data"]["message"]


@pytest.mark.asyncio
async def test_reports_api_endpoints(async_client, monkeypatch):
    """Verify JSON, PDF, and compare endpoints on reports router."""
    run_id = uuid.uuid4()

    async def fake_json_report(session, r_id):
        return {"run_id": str(r_id), "metrics": {"rfr": 0.25}}

    async def fake_pdf_report(session, r_id):
        return b"%PDF-1.4 mock binary pdf stream"

    async def fake_compare(session, r_a, r_b):
        return {
            "run_a": {
                "id": str(r_a),
                "organization_id": str(uuid.uuid4()),
                "created_by_user_id": None,
                "name": "Run A",
                "status": "completed",
                "harm_category": "cybersecurity",
                "target_model_id": str(uuid.uuid4()),
                "attack_template_ids": ["pair"],
                "defense_ids": [],
                "seed_prompts": ["p1"],
                "metrics": {"asr": 0.5, "rfr": 0.5},
                "error_message": None,
                "report_url": None,
                "started_at": None,
                "completed_at": None,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            "run_b": {
                "id": str(r_b),
                "organization_id": str(uuid.uuid4()),
                "created_by_user_id": None,
                "name": "Run B",
                "status": "completed",
                "harm_category": "cybersecurity",
                "target_model_id": str(uuid.uuid4()),
                "attack_template_ids": ["pair"],
                "defense_ids": [],
                "seed_prompts": ["p1"],
                "metrics": {"asr": 0.2, "rfr": 0.2},
                "error_message": None,
                "report_url": None,
                "started_at": None,
                "completed_at": None,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            "delta_asr": -0.3,
            "delta_latency_ms": 15.0,
            "category_comparison": {},
            "conclusion": "Run B shows improved safety robustness.",
        }

    monkeypatch.setattr(report_service, "generate_json_report", fake_json_report)
    monkeypatch.setattr(report_service, "generate_pdf_report", fake_pdf_report)
    monkeypatch.setattr(report_service, "compare_runs", fake_compare)

    # 1. JSON report
    res_json = await async_client.get(f"/api/v1/reports/{run_id}")
    assert res_json.status_code == 200
    assert res_json.json()["data"]["run_id"] == str(run_id)

    # 2. PDF report
    res_pdf = await async_client.get(f"/api/v1/reports/{run_id}/pdf")
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"
    assert res_pdf.content.startswith(b"%PDF")

    # 3. Compare runs
    res_compare = await async_client.get(
        f"/api/v1/reports/compare?run_a={run_id}&run_b={uuid.uuid4()}"
    )
    assert res_compare.status_code == 200
    assert res_compare.json()["data"]["delta_asr"] == -0.3
