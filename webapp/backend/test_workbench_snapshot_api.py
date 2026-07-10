from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str, *, require_auth: bool = False, rate_limit: int = 0):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    os.environ["COSCIENTIST_REQUIRE_AUTH"] = "1" if require_auth else "0"
    os.environ["COSCIENTIST_RATE_LIMIT_PER_MINUTE"] = str(rate_limit)
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_workbench_snapshot_artifacts_and_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        run_id = "run_snapshot"
        record = studio.RunRecord(
            run_id=run_id,
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=studio.RunRequest(
                research_goal="Validate the workbench snapshot contract",
                demo_mode=False,
                literature_review=True,
            ),
            hypotheses=[
                {
                    "title": "Evidence-linked candidate",
                    "text": "A measurable mechanism should improve the target metric.",
                    "citation_map": {"C1": {"title": "Paper", "url": r"D:\private\paper.pdf"}},
                    "literature_grounding": "limited fulltext",
                }
            ],
        )
        studio.persist_run_record(record)
        studio.knowledge_base.ingest(
            title="A real paper",
            content="Methods and experiments show a measurable target metric.",
            authors=["Researcher"],
            year=2025,
            url=r"D:\private\paper.pdf",
            source="local_pdf",
            source_reliability="parsed_fulltext",
        )
        client = TestClient(studio.app)

        snapshot = client.get("/api/workbench/snapshot", params={"run_id": run_id})
        assert snapshot.status_code == 200, snapshot.text
        payload = snapshot.json()
        assert payload["schema_version"] == "workbench.snapshot.v1"
        assert payload["project"]["id"] == run_id
        assert payload["current_run"]["run_id"] == run_id
        assert payload["papers"][0]["url"] is None
        assert payload["current_run"]["hypotheses"][0]["citation_map"]["C1"]["url"] is None

        saved = client.post(
            f"/api/projects/{run_id}/artifacts",
            json={
                "run_id": run_id,
                "artifact_type": "hypothesis",
                "target_ref": {"hypothesis_index": 0},
                "title": "保存到项目",
                "payload": {"decision": "review"},
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["artifact"]["artifact_type"] == "hypothesis"

        artifacts = client.get(f"/api/projects/{run_id}/artifacts")
        assert artifacts.status_code == 200
        assert artifacts.json()["artifacts"][0]["payload"]["decision"] == "review"

        experiment = client.post(
            f"/api/projects/{run_id}/experiment-plans",
            json={"run_id": run_id, "hypothesis_index": 0},
        )
        assert experiment.status_code == 200, experiment.text
        assert experiment.json()["experiment_plan"]["intent"] == "design_experiment"
        assert experiment.json()["artifact"]["artifact_type"] == "experiment_plan"

        events = client.get(f"/api/runs/{run_id}/events")
        assert events.status_code == 200
        assert "event: run" in events.text
        assert "event: done" in events.text

        recovery = client.get(f"/api/runs/{run_id}/recovery")
        assert recovery.status_code == 200
        assert recovery.json()["recovery"]["category"] == "none"


def test_optional_api_auth_boundary() -> None:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            studio = load_studio(tmp, require_auth=True)
            client = TestClient(studio.app)
            assert client.get("/api/health").status_code == 200
            assert client.get("/api/workbench/snapshot").status_code == 401
    finally:
        os.environ["COSCIENTIST_REQUIRE_AUTH"] = "0"


def test_optional_api_rate_limit_boundary() -> None:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            studio = load_studio(tmp, rate_limit=2)
            client = TestClient(studio.app)
            assert client.get("/api/health").status_code == 200
            assert client.get("/api/health").status_code == 200
            limited = client.get("/api/health")
            assert limited.status_code == 429
            assert limited.headers["retry-after"]
    finally:
        os.environ["COSCIENTIST_RATE_LIMIT_PER_MINUTE"] = "0"


if __name__ == "__main__":
    test_workbench_snapshot_artifacts_and_events()
    print("workbench snapshot API tests passed")
