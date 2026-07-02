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
