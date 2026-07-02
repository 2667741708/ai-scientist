from __future__ import annotations

import importlib
import sys
import tempfile

from fastapi.testclient import TestClient


def load_studio_app(monkeypatch, knowledge_base_dir: str):
    monkeypatch.setenv("COSCIENTIST_KNOWLEDGE_BASE_DIR", knowledge_base_dir)
    monkeypatch.setenv("COSCIENTIST_WORKER_ENABLED", "0")
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_create_run_enqueues_durable_work_item(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir, TestClient(studio.app) as client:
        response = client.post(
            "/api/runs",
            json={
                "research_goal": "Find falsifiable mechanisms for retrieval evidence drift",
                "model_name": "deepseek/deepseek-v4-pro",
                "demo_mode": True,
                "literature_review": False,
                "initial_hypotheses": 2,
                "iterations": 0,
                "min_references": 0,
                "max_references": 2,
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["run_id"]
        assert payload["work_item_id"]

        run_response = client.get(f"/api/runs/{payload['run_id']}")
        assert run_response.status_code == 200
        assert run_response.json()["status"] == "queued"

        worker_status = client.get("/api/worker/status").json()
        assert worker_status["auto_start_enabled"] is False
        assert worker_status["queued_count"] >= 1
        assert worker_status["queue_health"] == "backlog"
        assert worker_status["active_work_item_count"] >= 1
        active = worker_status["active_work_items"][0]
        assert active["work_item_id"] == payload["work_item_id"]
        assert active["run_id"] == payload["run_id"]
        assert active["workflow_name"] == "workflow.open_coscientist_run"
        assert active["status"] == "queued"
        assert "arguments" not in active
        assert "result_ref" not in active
        assert "arguments and result payloads are intentionally omitted" in worker_status["boundary"]
        assert worker_status["execution_memory"]["thread_id_source"] == "run_id"
        assert worker_status["execution_memory"]["status"] in {"limited", "ready"}

        tick_status = client.post("/api/worker/tick").json()
        assert tick_status["auto_start_enabled"] is False
        assert tick_status["execution_memory"]["thread_id_source"] == "run_id"
        assert tick_status["execution_memory"]["status"] in {"limited", "ready"}
        assert tick_status["queue_health"] in {"backlog", "running"}


def test_chat_confirmation_persists_starting_hypothesis(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)
    message = (
        "研究目标：找出检索证据漂移的可证伪机制；"
        "我的假设是 section 丢失导致 citation provenance 断裂；"
        "偏好：优先最小验证实验；"
        "约束：先用本地 benchmark；"
        "请一起评审排序"
    )

    with tempdir, TestClient(studio.app) as client:
        turn = client.post(
            "/api/research-chat/turn",
            json={"message": message, "context": {"mode": "workspace", "language": "zh"}},
        )
        assert turn.status_code == 200, turn.text
        proposal = turn.json()["assistant_message"]["proposal"]
        preview = proposal["requestPreview"]
        assert proposal["executionTarget"] == "workflow.start_run"
        assert preview["research_goal"] == "找出检索证据漂移的可证伪机制"
        assert preview["starting_hypotheses_count"] == 1

        confirm = client.post(
            f"/api/research-chat/actions/{proposal['actionId']}/confirm",
            json={"approval": {"confirmed": True, "scope": proposal["approvalScope"], "reason": "test"}},
        )
        assert confirm.status_code == 200, confirm.text
        run_id = confirm.json()["assistant_message"]["result"]["runId"]

        run = client.get(f"/api/runs/{run_id}").json()
        assert run["request"]["starting_hypotheses"] == ["section 丢失导致 citation provenance 断裂"]
        assert run["request"]["constraints"] == ["先用本地 benchmark"]
        assert run["request"]["preferences"] == "优先最小验证实验"


def test_continue_run_enqueues_child_with_parent_memory(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir, TestClient(studio.app) as client:
        parent = studio.RunRecord(
            run_id="parent-continuation-api",
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=studio.RunRequest(
                research_goal="Find falsifiable mechanisms for continuation memory",
                demo_mode=True,
                literature_review=False,
                constraints=["keep provenance explicit"],
                starting_hypotheses=["Parent seed hypothesis about evidence provenance."],
            ),
            hypotheses=[
                {
                    "id": "hyp-parent-continuation",
                    "text": "Parent hypothesis should guide the continuation as summarized context.",
                    "explanation": "The prior run identified a useful continuation direction.",
                    "support_level": "limited",
                }
            ],
            metrics={"summary": "Parent run favored provenance-aware continuation."},
        )
        studio.persist_run_record(parent)

        feedback = client.post(
            "/api/runs/parent-continuation-api/feedback",
            json={
                "target_type": "hypothesis",
                "target_ref": {"hypothesis_id": "hyp-parent-continuation"},
                "feedback_type": "prefer",
                "text": "Prefer continuation hypotheses with falsifiable evidence checks.",
            },
        )
        assert feedback.status_code == 200, feedback.text

        response = client.post(
            "/api/runs/parent-continuation-api/continue",
            json={
                "research_goal": "Continue falsifiable mechanisms with stricter evidence checks",
                "constraints": ["avoid raw JSON in ordinary UI"],
                "starting_hypotheses": ["Child seed hypothesis about summary-only memory."],
                "user_feedback": [
                    {
                        "target_type": "run",
                        "target_ref": {"source": "continuation_request"},
                        "feedback_type": "constraint",
                        "text": "Use feedback only for the next run, not as instant result editing.",
                    }
                ],
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["parent_run_id"] == "parent-continuation-api"
        assert payload["run_id"]
        assert payload["work_item_id"]

        child = client.get(f"/api/runs/{payload['run_id']}").json()
        request = child["request"]
        assert child["status"] == "queued"
        assert request["parent_run_id"] == "parent-continuation-api"
        assert request["refinement_mode"] == "continue_from_run"
        assert request["constraints"] == [
            "keep provenance explicit",
            "avoid raw JSON in ordinary UI",
        ]
        assert request["starting_hypotheses"] == [
            "Parent seed hypothesis about evidence provenance.",
            "Child seed hypothesis about summary-only memory.",
        ]
        assert request["user_feedback"][0]["feedback_type"] == "constraint"

        child_feedback = client.get(f"/api/runs/{payload['run_id']}/feedback").json()
        assert child_feedback["count"] == 1
        assert child_feedback["feedback"][0]["text"].startswith("Use feedback only")

        memory = client.get(f"/api/runs/{payload['run_id']}/memory").json()
        summary = memory["summary"]
        assert summary["has_parent_run"] is True
        assert summary["prior_hypotheses_count"] == 1
        assert summary["user_feedback_count"] == 1
        assert "parent_run" in summary["source_types"]
        assert "chat_feedback" in summary["source_types"]
        assert "raw JSON" in summary["boundary"]

        worker_status = client.get("/api/worker/status").json()
        active_child_items = [
            item
            for item in worker_status["active_work_items"]
            if item["run_id"] == payload["run_id"]
        ]
        assert active_child_items
        assert active_child_items[0]["work_item_id"] == payload["work_item_id"]
