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


def test_continue_run_creates_child_work_item_with_parent_context(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir, TestClient(studio.app) as client:
        parent_response = client.post(
            "/api/runs",
            json={
                "research_goal": "Find falsifiable mechanisms for retrieval drift",
                "model_name": "deepseek/deepseek-v4-pro",
                "demo_mode": True,
                "literature_review": False,
                "initial_hypotheses": 2,
                "iterations": 0,
                "min_references": 0,
                "max_references": 2,
                "preferences": "Prefer compact validation.",
                "constraints": ["Use local benchmark first."],
                "starting_hypotheses": ["Parent hypothesis should remain available."],
            },
        )
        assert parent_response.status_code == 200, parent_response.text
        parent_run_id = parent_response.json()["run_id"]

        child_response = client.post(
            f"/api/runs/{parent_run_id}/continue",
            json={
                "research_goal": "Find falsifiable mechanisms for retrieval drift under PDF parsing",
                "constraints": ["Focus on parsed fulltext evidence."],
                "starting_hypotheses": ["PDF section loss drives citation drift."],
                "user_feedback": [
                    {
                        "target_type": "run",
                        "feedback_type": "critique",
                        "text": "Revise toward evidence provenance failures.",
                    }
                ],
                "refinement_mode": "revise_hypotheses",
            },
        )
        assert child_response.status_code == 200, child_response.text
        child_payload = child_response.json()
        assert child_payload["parent_run_id"] == parent_run_id
        assert child_payload["work_item_id"]

        child_run = client.get(f"/api/runs/{child_payload['run_id']}").json()
        child_request = child_run["request"]
        assert child_run["status"] == "queued"
        assert child_request["parent_run_id"] == parent_run_id
        assert child_request["refinement_mode"] == "revise_hypotheses"
        assert child_request["preferences"] == "Prefer compact validation."
        assert child_request["constraints"] == [
            "Use local benchmark first.",
            "Focus on parsed fulltext evidence.",
        ]
        assert child_request["starting_hypotheses"] == [
            "Parent hypothesis should remain available.",
            "PDF section loss drives citation drift.",
        ]

        feedback = client.get(f"/api/runs/{child_payload['run_id']}/feedback").json()
        assert feedback["count"] == 1
        assert feedback["feedback"][0]["source"] == "run_request"
