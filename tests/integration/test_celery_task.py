"""Integration tests for Celery tasks, RunService, and ReportService."""

import uuid
from datetime import datetime, timezone
import pytest
from app.engine.state import RunConfig, RunMetrics
from app.schemas.run import RunCreate
from app.services.evaluation_service import evaluation_service
from app.services.probe_service import probe_service
from app.services.report_service import report_service
from app.services.run_service import run_service


@pytest.mark.asyncio
async def test_report_service_pdf_generation_mock(monkeypatch):
    """Test ReportService generates non-empty PDF bytes and JSON report structure."""
    now = datetime.now(timezone.utc)
    fake_run_id = uuid.uuid4()
    fake_target_id = uuid.uuid4()

    class FakeRun:
        id = fake_run_id
        target_model_id = fake_target_id
        organization_id = uuid.uuid4()
        created_by_user_id = None
        attack_template_ids = ["pair"]
        defense_ids = []
        seed_prompts = ["Seed 1", "Seed 2"]
        name = "Synthetic Test Run"
        status = "completed"
        harm_category = "cybersecurity"
        started_at = now
        completed_at = now
        created_at = now
        updated_at = now
        error_message = None
        report_url = None
        target_model = type("TargetModel", (), {"id": fake_target_id, "name": "Test LLM", "provider": "openai"})()
        metrics = {"rfr": 0.25, "validator_blocks": 1, "average_latency_ms": 120.0}
        results = [
            type(
                "Result",
                (),
                {
                    "prompt_index": 0,
                    "attack_type": "pair",
                    "seed_prompt": "Seed 1",
                    "mutated_prompt": "Mutated prompt 1",
                    "target_response": "Refusal text",
                    "defense_verdict": {"allowed": True},
                    "is_jailbroken": False,
                    "jailbreak_score": 0.1,
                    "evaluation_reason": "Refused",
                    "latency_ms": 120.0,
                    "tokens_used": 20,
                },
            )(),
            type(
                "Result",
                (),
                {
                    "prompt_index": 1,
                    "attack_type": "pair",
                    "seed_prompt": "Seed 2",
                    "mutated_prompt": "Mutated prompt 2",
                    "target_response": "Detailed compliance text",
                    "defense_verdict": {"allowed": True},
                    "is_jailbroken": True,
                    "jailbreak_score": 0.9,
                    "evaluation_reason": "Complied",
                    "latency_ms": 130.0,
                    "tokens_used": 25,
                },
            )(),
        ]

    # Mock _fetch_run_with_results to return FakeRun without requiring live DB connection
    async def fake_fetch(session, run_id):
        return FakeRun(), FakeRun.results

    monkeypatch.setattr(report_service, "_fetch_run_with_results", fake_fetch)

    # Test PDF generation
    pdf_bytes = await report_service.generate_pdf_report(None, fake_run_id)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")

    # Test JSON generation
    json_data = await report_service.generate_json_report(None, fake_run_id)
    assert json_data["run_name"] == "Synthetic Test Run"
    assert len(json_data["attempts"]) == 2

    # Test CSV generation
    csv_str = await report_service.generate_csv_report(None, fake_run_id)
    assert "prompt_index,probe_type" in csv_str
    assert "Mutated prompt 1" in csv_str


@pytest.mark.asyncio
async def test_probe_service_validation():
    """Verify probe parameter validation rejects invalid hyperparameter configurations."""
    # Valid PAIR params
    probe_service.validate_probe_params("pair", {"n_iterations": 5, "n_streams": 2})

    # Invalid PAIR params (n_iterations < 1)
    with pytest.raises(Exception):
        probe_service.validate_probe_params("pair", {"n_iterations": -1})


@pytest.mark.asyncio
async def test_report_service_compare_runs(monkeypatch):
    """Test ReportService compares two benchmark runs and produces delta analysis."""
    run_a_id = uuid.uuid4()
    run_b_id = uuid.uuid4()

    def make_fake_run(run_id, name, rfr, latency):
        now = datetime.now(timezone.utc)
        return type(
            "FakeRun",
            (),
            {
                "id": run_id,
                "organization_id": uuid.uuid4(),
                "created_by_user_id": None,
                "target_model_id": uuid.uuid4(),
                "attack_template_ids": ["pair"],
                "defense_ids": [],
                "seed_prompts": ["test"],
                "name": name,
                "status": "completed",
                "harm_category": "general",
                "error_message": None,
                "report_url": None,
                "started_at": now,
                "completed_at": now,
                "created_at": now,
                "updated_at": now,
                "target_model": type("TargetModel", (), {"id": uuid.uuid4(), "name": "MUT", "provider": "openai"})(),
                "metrics": {"rfr": rfr, "average_latency_ms": latency},
                "results": [],
            },
        )()

    async def fake_fetch(session, run_id):
        if run_id == run_a_id:
            r = make_fake_run(run_a_id, "Run A", 0.10, 100.0)
        else:
            r = make_fake_run(run_b_id, "Run B", 0.35, 150.0)
        return r, []

    monkeypatch.setattr(report_service, "_fetch_run_with_results", fake_fetch)

    comp = await report_service.compare_runs(None, run_a_id, run_b_id)
    assert comp.delta_asr == 0.25
    assert comp.delta_latency_ms == 50.0
    assert "higher Robustness Failure Rate" in comp.conclusion
