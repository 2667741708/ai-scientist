from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    os.environ["COSCIENTIST_WORKER_ENABLED"] = "0"
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_research_chat_records_critique_feedback_for_target_hypothesis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        record = studio.RunRecord(
            run_id="run_chat_feedback",
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=studio.RunRequest(
                research_goal="Compare candidate hypotheses with human feedback memory",
                demo_mode=True,
                literature_review=False,
            ),
            hypotheses=[
                {"id": "hyp_1", "text": "First hypothesis is better grounded."},
                {"id": "hyp_2", "text": "Second hypothesis lacks falsification detail."},
            ],
        )
        studio.persist_run_record(record)
        client = TestClient(studio.app)

        response = client.post(
            "/api/research-chat/turn",
            json={
                "message": "第 2 个假设太弱，因为缺少可证伪实验设计，请把这条反馈用于下一轮。",
                "context": {"run_id": "run_chat_feedback", "mode": "workspace", "language": "zh"},
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["state"] == "complete"
        result = payload["assistant_message"]["result"]
        assert result["intent"] == "critique_generated_hypothesis"
        assert result["targetType"] == "hypothesis"
        assert result["targetRef"]["hypothesis_index"] == 1
        assert result["targetRef"]["hypothesis_id"] == "hyp_2"
        assert result["feedback"]["source"] == "chat"
        assert result["feedback"]["feedback_type"] == "critique"
        assert "下一次 run 或 continuation" in result["summary"]

        feedback_response = client.get("/api/runs/run_chat_feedback/feedback")
        assert feedback_response.status_code == 200, feedback_response.text
        feedback_payload = feedback_response.json()
        assert feedback_payload["count"] == 1
        assert feedback_payload["feedback"][0]["target_ref"]["hypothesis_id"] == "hyp_2"

        run_response = client.get("/api/runs/run_chat_feedback")
        assert run_response.status_code == 200, run_response.text
        run_payload = run_response.json()
        assert run_payload["expert_feedback"]["status"] == "feedback_recorded"
        assert run_payload["expert_feedback"]["feedback_items"][0]["source"] == "chat"


def test_research_chat_records_preference_feedback_from_selected_context() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        record = studio.RunRecord(
            run_id="run_chat_selected_feedback",
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=studio.RunRequest(
                research_goal="Use selected hypothesis context for feedback",
                demo_mode=True,
                literature_review=False,
            ),
            hypotheses=[
                {"id": "hyp_selected", "text": "Selected hypothesis should be preferred."},
            ],
        )
        studio.persist_run_record(record)
        client = TestClient(studio.app)

        response = client.post(
            "/api/research-chat/turn",
            json={
                "message": "这个假设我更偏好，因为它更容易设计对照实验。",
                "context": {
                    "run_id": "run_chat_selected_feedback",
                    "selected_hypothesis_index": 0,
                    "mode": "workspace",
                    "language": "zh",
                },
            },
        )

        assert response.status_code == 200, response.text
        result = response.json()["assistant_message"]["result"]
        assert result["intent"] == "apply_expert_feedback"
        assert result["feedback"]["feedback_type"] == "prefer"
        assert result["targetRef"]["hypothesis_id"] == "hyp_selected"


def test_research_chat_feedback_enters_continuation_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        parent = studio.RunRecord(
            run_id="run_chat_feedback_memory_parent",
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=studio.RunRequest(
                research_goal="Use chat feedback as continuation memory",
                demo_mode=True,
                literature_review=False,
            ),
            hypotheses=[
                {"id": "hyp_memory", "text": "Hypothesis should carry chat feedback into continuation."},
            ],
        )
        studio.persist_run_record(parent)
        client = TestClient(studio.app)

        feedback_response = client.post(
            "/api/research-chat/turn",
            json={
                "message": "第 1 个假设我更偏好，因为它能设计最小反证实验。",
                "context": {"run_id": "run_chat_feedback_memory_parent", "mode": "workspace", "language": "zh"},
            },
        )
        assert feedback_response.status_code == 200, feedback_response.text

        continuation = client.post(
            "/api/runs/run_chat_feedback_memory_parent/continue",
            json={
                "research_goal": "Continue with the preferred falsifiable hypothesis",
                "starting_hypotheses": ["Continuation should use chat feedback memory."],
            },
        )
        assert continuation.status_code == 200, continuation.text
        child_run_id = continuation.json()["run_id"]

        memory_response = client.get(f"/api/runs/{child_run_id}/memory")
        assert memory_response.status_code == 200, memory_response.text
        memory_payload = memory_response.json()
        assert memory_payload["summary"]["has_parent_run"] is True
        assert memory_payload["summary"]["user_feedback_count"] == 1
        assert "chat_feedback" in memory_payload["summary"]["source_types"]
        feedback_texts = {item["text"] for item in memory_payload["memory"]["user_feedback"]}
        assert "第 1 个假设我更偏好，因为它能设计最小反证实验。" in feedback_texts


def test_research_chat_capabilities_include_feedback_memory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        client = TestClient(studio.app)

        response = client.get("/api/research-chat/capabilities")

        assert response.status_code == 200, response.text
        capabilities = response.json()["capabilities"]
        feedback = next(item for item in capabilities if item["id"] == "hypothesis.feedback")
        assert feedback["intent"] == "apply_expert_feedback"
        assert feedback["taskArea"] == "hypothesis_audit"
        assert "下一轮" in feedback["availability"]["summary"]

        continuation = next(item for item in capabilities if item["id"] == "research.continue_run")
        assert continuation["intent"] == "continue_or_revise_run"
        assert continuation["executionMode"] == "approval_required"
        assert continuation["approvalScope"] == "research.start_live_run"
        assert "摘要形式注入" in continuation["availability"]["summary"]
