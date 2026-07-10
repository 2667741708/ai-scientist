from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def persist_test_run(studio, run_id: str) -> None:
    record = studio.RunRecord(
        run_id=run_id,
        status="complete",
        created_at=1.0,
        updated_at=1.0,
        request=studio.RunRequest(research_goal="Validate durable research task board"),
    )
    studio.persist_run_record(record)


def test_research_task_board_api_creates_lists_and_updates_tasks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        persist_test_run(studio, "run_task_board")
        client = TestClient(studio.app)

        created = client.post(
            "/api/research-tasks",
            json={
                "run_id": "run_task_board",
                "title": "Review parsed evidence for HYP-001",
                "task_type": "evidence_review",
                "status": "ready",
                "priority": 1,
                "phase": "review",
                "target_ref": {"hypothesis_id": "HYP-001"},
                "notes": "Check support level and contradiction risk.",
            },
        )
        assert created.status_code == 200, created.text
        task = created.json()["task"]
        assert task["phase"] == "review_critique"
        assert task["target_ref"]["hypothesis_id"] == "HYP-001"

        listed = client.get("/api/research-tasks", params={"run_id": "run_task_board", "status": "ready"})
        assert listed.status_code == 200
        assert listed.json()["count"] == 1

        updated = client.patch(
            f"/api/research-tasks/{task['task_id']}",
            json={
                "status": "blocked",
                "blocked_reason": "Need fulltext PDF before review.",
                "result_ref": {"background_job_id": "job_123"},
            },
        )
        assert updated.status_code == 200
        assert updated.json()["task"]["status"] == "blocked"
        assert updated.json()["task"]["result_ref"]["background_job_id"] == "job_123"

        loaded = client.get(f"/api/research-tasks/{task['task_id']}")
        assert loaded.status_code == 200
        assert loaded.json()["task"]["blocked_reason"] == "Need fulltext PDF before review."

        missing_run = client.post(
            "/api/research-tasks",
            json={
                "run_id": "missing_run",
                "title": "Invalid run task",
                "task_type": "other",
            },
        )
        assert missing_run.status_code == 404


if __name__ == "__main__":
    test_research_task_board_api_creates_lists_and_updates_tasks()
    print("research task board API tests passed")
