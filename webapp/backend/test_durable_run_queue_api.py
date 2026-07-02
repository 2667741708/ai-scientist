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
        assert worker_status["execution_memory"]["thread_id_source"] == "run_id"
        assert worker_status["execution_memory"]["status"] in {"limited", "ready"}


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
