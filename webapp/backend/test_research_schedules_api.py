from __future__ import annotations

import importlib
import asyncio
import os
import sys
import tempfile
import time
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
        request=studio.RunRequest(research_goal="Validate durable research schedules"),
    )
    studio.persist_run_record(record)


def test_research_schedules_api_creates_lists_and_updates_schedules() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        persist_test_run(studio, "run_schedule")
        client = TestClient(studio.app)

        created = client.post(
            "/api/research-schedules",
            json={
                "run_id": "run_schedule",
                "title": "Weekly citation provenance QA",
                "workflow_name": "citation_provenance_qa",
                "interval_hours": 168,
                "phase": "evidence_audit",
                "arguments": {"scope": "active_hypotheses"},
                "next_run_at": time.time() + 3600,
            },
        )
        assert created.status_code == 200, created.text
        schedule = created.json()["schedule"]
        assert schedule["phase"] == "evidence_audit"
        assert schedule["arguments"]["scope"] == "active_hypotheses"

        listed = client.get("/api/research-schedules", params={"run_id": "run_schedule", "status": "active"})
        assert listed.status_code == 200
        assert listed.json()["count"] == 1

        updated = client.patch(
            f"/api/research-schedules/{schedule['schedule_id']}",
            json={
                "status": "paused",
                "result_ref": {"task_id": "task_123"},
            },
        )
        assert updated.status_code == 200
        assert updated.json()["schedule"]["status"] == "paused"
        assert updated.json()["schedule"]["result_ref"]["task_id"] == "task_123"

        reactivated = client.patch(
            f"/api/research-schedules/{schedule['schedule_id']}",
            json={
                "status": "active",
                "next_run_at": time.time() + 3600,
                "result_ref": {},
            },
        )
        assert reactivated.status_code == 200

        no_approval = client.post(f"/api/research-schedules/{schedule['schedule_id']}/tick", json={})
        assert no_approval.status_code == 428

        not_due = client.post(
            f"/api/research-schedules/{schedule['schedule_id']}/tick",
            json={
                "approval": {
                    "confirmed": True,
                    "scope": "research_schedule.tick",
                }
            },
        )
        assert not_due.status_code == 409
        assert not_due.json()["detail"]["code"] == "research_schedule_not_due"

        ticked = client.post(
            f"/api/research-schedules/{schedule['schedule_id']}/tick",
            json={
                "force": True,
                "approval": {
                    "confirmed": True,
                    "scope": "research_schedule.tick",
                    "reason": "test forced schedule tick",
                },
            },
        )
        assert ticked.status_code == 200, ticked.text
        tick_payload = ticked.json()
        assert tick_payload["task"]["task_type"] == "scheduled_workflow"
        assert tick_payload["task"]["target_ref"]["workflow_name"] == "citation_provenance_qa"
        assert tick_payload["schedule"]["result_ref"]["task_id"] == tick_payload["task"]["task_id"]

        missing_run = client.post(
            "/api/research-schedules",
            json={
                "run_id": "missing_run",
                "title": "Invalid schedule",
                "workflow_name": "literature_refresh",
            },
        )
        assert missing_run.status_code == 404


def test_auto_schedule_creates_a_new_durable_research_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        client = TestClient(studio.app)

        missing_approval = client.post(
            "/api/research-schedules",
            json={
                "title": "Daily evidence-grounded research",
                "workflow_name": "workflow.open_coscientist_run",
                "auto_execute": True,
                "arguments": {
                    "run_request": {
                        "research_goal": "Test an automatically scheduled evidence research workflow",
                        "demo_mode": True,
                        "literature_review": False,
                        "auto_discover_papers": False,
                        "auto_ingest_papers": False,
                    }
                },
            },
        )
        assert missing_approval.status_code == 428

        created = client.post(
            "/api/research-schedules",
            json={
                "title": "Daily evidence-grounded research",
                "workflow_name": "workflow.open_coscientist_run",
                "auto_execute": True,
                "interval_hours": 24,
                "next_run_at": time.time() - 1,
                "arguments": {
                    "run_request": {
                        "research_goal": "Test an automatically scheduled evidence research workflow",
                        "demo_mode": True,
                        "literature_review": False,
                        "auto_discover_papers": False,
                        "auto_ingest_papers": False,
                    }
                },
                "approval": {
                    "confirmed": True,
                    "scope": "research_schedule.auto_execute",
                    "reason": "test recurring workflow",
                },
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["schedule"]["arguments"]["_automation"]["enabled"] is True

        dispatched = asyncio.run(studio.dispatch_due_research_schedules())
        assert dispatched["dispatched_count"] == 1
        assert dispatched["failed_count"] == 0
        run_id = dispatched["items"][0]["run_id"]
        task_id = dispatched["items"][0]["task_id"]
        assert studio.knowledge_base.get_research_run(run_id)["status"] == "queued"
        assert studio.knowledge_base.get_research_task(task_id)["status"] == "running"
        work_items = studio.knowledge_base.list_work_items(
            run_id=run_id,
            workflow_name="workflow.open_coscientist_run",
            limit=5,
        )
        assert len(work_items) == 1
        assert work_items[0]["status"] == "queued"
        repeated = asyncio.run(studio.dispatch_due_research_schedules())
        assert repeated["dispatched_count"] == 0


if __name__ == "__main__":
    test_research_schedules_api_creates_lists_and_updates_schedules()
    print("research schedules API tests passed")
