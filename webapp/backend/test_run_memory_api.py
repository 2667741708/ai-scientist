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


def test_run_memory_endpoint_returns_ui_summary_without_raw_details(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir, TestClient(studio.app) as client:
        parent_request = studio.RunRequest(
            research_goal="Parent run for memory summary",
            demo_mode=True,
            literature_review=False,
        )
        parent = studio.RunRecord(
            run_id="parent-memory-api",
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=parent_request,
            hypotheses=[
                {
                    "id": "hyp_parent",
                    "text": "Prior hypothesis should appear only as summarized memory.",
                    "explanation": "Parent explanation",
                    "support_level": "limited",
                }
            ],
            metrics={"summary": "Parent run established a useful prior direction."},
        )
        studio.persist_run_record(parent)
        studio.knowledge_base.store_feedback_item(
            run_id="parent-memory-api",
            target_type="hypothesis",
            target_ref={"hypothesis_id": "hyp_parent", "internal_note": "raw target ref stays in memory"},
            feedback_type="prefer",
            text="Use stronger evidence provenance next time.",
            source="chat",
        )
        studio.knowledge_base.ingest(
            title="Safe memory summary fulltext evidence",
            content=(
                "# Abstract\n\n"
                "Child run safe memory summary workflows should expose only summarized parsed fulltext evidence. "
                "# Results\n\n"
                "Parsed fulltext evidence improves provenance while avoiding raw JSON disclosure."
            ),
            source="local_pdf",
            source_reliability="parsed_fulltext",
        )

        child = studio.RunRecord(
            run_id="child-memory-api",
            status="queued",
            created_at=3.0,
            updated_at=3.0,
            request=studio.RunRequest(
                research_goal="Child run should expose safe memory summary",
                demo_mode=False,
                literature_review=False,
                parent_run_id="parent-memory-api",
            ),
        )
        studio.persist_run_record(child)

        response = client.get("/api/runs/child-memory-api/memory")

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["run_id"] == "child-memory-api"
        summary = payload["summary"]
        assert summary["has_parent_run"] is True
        assert summary["parent_run_id"] == "parent-memory-api"
        assert summary["prior_hypotheses_count"] == 1
        assert summary["user_feedback_count"] == 1
        assert summary["evidence_summary_count"] >= 1
        assert "parent_run" in summary["source_types"]
        assert "prior_hypotheses" in summary["source_types"]
        assert "chat_feedback" in summary["source_types"]
        assert "knowledge_base" in summary["source_types"]
        assert {section["type"] for section in summary["sections"]} >= {
            "parent_run",
            "prior_hypotheses",
            "chat_feedback",
            "knowledge_base",
        }
        evidence_section = next(section for section in summary["sections"] if section["type"] == "knowledge_base")
        assert evidence_section["source_reliability_counts"]["parsed_fulltext"] >= 1
        assert evidence_section["support_level_counts"]["fulltext"] >= 1
        assert "Summary-only memory view" in summary["boundary"]
        assert "raw JSON" in summary["boundary"]
        assert "target_ref" not in summary

        memory = payload["memory"]
        assert memory["user_feedback"][0]["target_ref"]["hypothesis_id"] == "hyp_parent"
        assert memory["evidence_summaries"][0]["source_reliability"] == "parsed_fulltext"


def test_run_memory_summary_reports_current_run_limitations(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir, TestClient(studio.app) as client:
        record = studio.RunRecord(
            run_id="current-run-memory-limitations",
            status="queued",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(
                research_goal="Current run memory scope should expose limitations",
                demo_mode=True,
                literature_review=False,
                memory_scope="current_run",
            ),
        )
        studio.persist_run_record(record)

        response = client.get("/api/runs/current-run-memory-limitations/memory")

        assert response.status_code == 200, response.text
        summary = response.json()["summary"]
        assert summary["memory_scope"] == "current_run"
        assert summary["known_gaps_count"] == 1
        assert "memory_limitations" in summary["source_types"]
        limitation_section = next(
            section for section in summary["sections"] if section["type"] == "memory_limitations"
        )
        assert limitation_section["count"] == 1
        assert "current_run scope" in limitation_section["items"][0]
