from __future__ import annotations

import importlib
import sys
import tempfile
import time

from fastapi.testclient import TestClient


def load_studio_app(monkeypatch, knowledge_base_dir: str):
    monkeypatch.setenv("COSCIENTIST_KNOWLEDGE_BASE_DIR", knowledge_base_dir)
    monkeypatch.setenv("COSCIENTIST_WORKER_ENABLED", "0")
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_run_lifecycle_persists_checkpoint_metadata(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir, TestClient(studio.app) as client:
        create_response = client.post(
            "/api/runs",
            json={
                "research_goal": "Find checkpoint metadata lifecycle semantics",
                "model_name": "deepseek/deepseek-v4-pro",
                "demo_mode": True,
                "literature_review": False,
                "initial_hypotheses": 1,
                "iterations": 0,
                "min_references": 0,
                "max_references": 1,
            },
        )
        assert create_response.status_code == 200, create_response.text
        payload = create_response.json()
        run_id = payload["run_id"]

        queued = studio.knowledge_base.latest_checkpoint_metadata(run_id)
        assert queued["status"] == "queued"
        assert queued["phase"] == "queue"
        assert queued["thread_id"] == run_id
        assert queued["checkpoint_backend"] == "sqlite_metadata"
        assert queued["checkpoint_ref"] == payload["work_item_id"]
        assert "metadata index only" in queued["state_summary"]["boundary"]

        tick_response = client.post("/api/worker/tick")
        assert tick_response.status_code == 200, tick_response.text

        run = {}
        for _ in range(40):
            run = client.get(f"/api/runs/{run_id}").json()
            if run["status"] == "complete":
                break
            time.sleep(0.2)
        assert run["status"] == "complete"

        checkpoints = studio.knowledge_base.list_checkpoint_metadata(run_id=run_id, limit=10)
        statuses = {item["status"] for item in checkpoints}
        assert {"queued", "running", "complete"}.issubset(statuses)

        latest = studio.knowledge_base.latest_checkpoint_metadata(run_id)
        assert latest["status"] == "complete"
        assert latest["phase"] == "complete"
        assert latest["state_summary"]["hypothesis_count"] == 1

        api_response = client.get(f"/api/runs/{run_id}/checkpoints")
        assert api_response.status_code == 200, api_response.text
        api_payload = api_response.json()
        assert api_payload["run_id"] == run_id
        assert api_payload["count"] >= 3
        assert api_payload["summary"]["status"] == "metadata_only"
        assert api_payload["summary"]["latest_status"] == "complete"
        assert api_payload["summary"]["has_langgraph_summary"] is False
        assert "metadata index only" in api_payload["boundary"]


def test_checkpoint_metadata_helper_persists_langgraph_summary(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        request = studio.RunRequest(
            research_goal="Verify LangGraph checkpoint metadata summaries",
            demo_mode=False,
            literature_review=False,
            initial_hypotheses=1,
            iterations=0,
            min_references=0,
            max_references=1,
        )
        record = studio.RunRecord(
            run_id="run-langgraph-summary",
            status="complete",
            created_at=1.0,
            updated_at=1.0,
            request=request,
        )
        summary = {
            "thread_id": "run-langgraph-summary",
            "checkpoint_id": "checkpoint-123",
            "metadata": {"source": "loop", "step": 2},
            "channel_keys": ["hypotheses", "metrics"],
            "boundary": "LangGraph checkpoint summary only; raw channel values are not exposed.",
        }

        studio.persist_run_checkpoint_metadata(
            record,
            status="complete",
            phase="langgraph",
            checkpoint_backend="langgraph_sqlite",
            checkpoint_ref="checkpoint-123",
            checkpoint_id="run-langgraph-summary:langgraph:checkpoint-123",
            state_summary=summary,
        )

        checkpoint = studio.knowledge_base.get_checkpoint_metadata(
            "run-langgraph-summary:langgraph:checkpoint-123"
        )
        assert checkpoint is not None
        assert checkpoint["checkpoint_backend"] == "langgraph_sqlite"
        assert checkpoint["checkpoint_ref"] == "checkpoint-123"
        assert checkpoint["phase"] == "langgraph"
        assert checkpoint["state_summary"]["channel_keys"] == ["hypotheses", "metrics"]
        assert "channel_values" not in checkpoint["state_summary"]
        assert "raw channel values are not exposed" in checkpoint["state_summary"]["boundary"]

        studio.persist_run_record(record)
        with TestClient(studio.app) as client:
            api_response = client.get("/api/runs/run-langgraph-summary/checkpoints")
        assert api_response.status_code == 200, api_response.text
        api_payload = api_response.json()
        assert api_payload["count"] == 1
        assert api_payload["summary"]["status"] == "ready"
        assert api_payload["summary"]["has_langgraph_summary"] is True
        assert api_payload["summary"]["checkpoint_backend"] == "langgraph_sqlite"
        assert "LangGraph checkpoint summaries" in api_payload["boundary"]
        assert "raw channel values are not exposed" in api_payload["boundary"]


def test_checkpoint_endpoint_reports_not_available_without_metadata(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir, TestClient(studio.app) as client:
        record = studio.RunRecord(
            run_id="run-no-checkpoints",
            status="queued",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(
                research_goal="Inspect checkpoint readiness when metadata is absent",
                demo_mode=True,
                literature_review=False,
            ),
        )
        studio.persist_run_record(record)

        response = client.get("/api/runs/run-no-checkpoints/checkpoints")

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["count"] == 0
        assert payload["checkpoints"] == []
        assert payload["summary"]["status"] == "not_available"
        assert payload["summary"]["checkpoint_count"] == 0
        assert payload["summary"]["latest_status"] is None
        assert payload["summary"]["resume_boundary"] == "No checkpoint metadata is available for this run."
