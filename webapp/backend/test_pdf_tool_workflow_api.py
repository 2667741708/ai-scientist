from __future__ import annotations

import importlib
import os
import sys
import time
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from test_pdf_parser import create_sample_pdf


def test_pdf_parse_tool_workflow_requires_approval_and_persists_audit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
        sys.modules.pop("app", None)
        studio = importlib.import_module("app")

        pdf = Path(tmp) / "paper.pdf"
        create_sample_pdf(pdf)
        record = studio.RunRecord(
            run_id="run_pdf_tool",
            status="complete",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(research_goal="Validate approval backed PDF tool workflow"),
        )
        studio.persist_run_record(record)

        client = TestClient(studio.app)
        no_approval = client.post(
            "/api/tools/workflows/pdf-parse",
            json={
                "pdf_path": str(pdf),
                "phase": "paper_reading",
                "run_id": "run_pdf_tool",
                "fetch_metadata": False,
                "ingest_to_knowledge_base": True,
            },
        )
        assert no_approval.status_code == 428
        assert no_approval.json()["detail"]["code"] == "tool_workflow_approval_required"

        approved = client.post(
            "/api/tools/workflows/pdf-parse",
            json={
                "pdf_path": str(pdf),
                "phase": "paper_reading",
                "run_id": "run_pdf_tool",
                "fetch_metadata": False,
                "ingest_to_knowledge_base": True,
                "approval": {
                    "confirmed": True,
                    "scope": "pdf.parse_to_knowledge_base",
                    "reason": "test writes parse artifacts and knowledge base rows",
                },
            },
        )
        assert approved.status_code == 200, approved.text
        payload = approved.json()
        assert payload["parse_result"]["parse_run_id"]
        assert payload["parse_result"]["paper_id"]
        assert payload["parse_result"]["rag_search_ready"] is True
        assert payload["result_ref"]["result_id"]

        tool_calls = client.get("/api/runs/run_pdf_tool/tool-calls")
        assert tool_calls.status_code == 200
        assert any(
            item["tool_name"] == "pdf.parse_to_knowledge_base"
            for item in tool_calls.json()["tool_calls"]
        )

        tool_results = client.get("/api/runs/run_pdf_tool/tool-results")
        assert tool_results.status_code == 200
        assert tool_results.json()["count"] == 1
        loaded_result = client.get(f"/api/tools/results/{payload['result_ref']['result_id']}")
        assert loaded_result.status_code == 200
        assert loaded_result.json()["content"]["parse_run_id"] == payload["parse_result"]["parse_run_id"]

        repeated = client.post(
            "/api/tools/workflows/pdf-parse",
            json={
                "pdf_path": str(pdf),
                "phase": "paper_reading",
                "run_id": "run_pdf_tool",
                "fetch_metadata": False,
                "ingest_to_knowledge_base": True,
                "approval": {
                    "confirmed": True,
                    "scope": "pdf.parse_to_knowledge_base",
                },
            },
        )
        assert repeated.status_code == 409
        assert repeated.json()["detail"]["code"] == "repeated_identical_tool_workflow"


def test_background_pdf_parse_tool_workflow_records_job_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
        sys.modules.pop("app", None)
        studio = importlib.import_module("app")

        pdf = Path(tmp) / "background-paper.pdf"
        create_sample_pdf(pdf)
        record = studio.RunRecord(
            run_id="run_pdf_background",
            status="complete",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(research_goal="Validate background PDF parse workflow"),
        )
        studio.persist_run_record(record)

        client = TestClient(studio.app)
        response = client.post(
            "/api/tools/workflows/pdf-parse/background",
            json={
                "pdf_path": str(pdf),
                "phase": "paper_reading",
                "run_id": "run_pdf_background",
                "fetch_metadata": False,
                "ingest_to_knowledge_base": True,
                "approval": {
                    "confirmed": True,
                    "scope": "pdf.parse_to_knowledge_base",
                    "reason": "background parse test",
                },
            },
        )
        assert response.status_code == 200, response.text
        job_id = response.json()["job"]["job_id"]

        job_payload = None
        for _ in range(20):
            job_response = client.get(f"/api/tools/background-jobs/{job_id}")
            assert job_response.status_code == 200
            job_payload = job_response.json()
            if job_payload["status"] in {"complete", "error"}:
                break
            time.sleep(0.05)

        assert job_payload
        assert job_payload["status"] == "complete"
        assert job_payload["result_ref"]["parse_run_id"]
        assert job_payload["result_ref"]["tool_result"]["result_id"]

        jobs = client.get("/api/tools/background-jobs", params={"run_id": "run_pdf_background"})
        assert jobs.status_code == 200
        assert jobs.json()["count"] == 1


if __name__ == "__main__":
    test_pdf_parse_tool_workflow_requires_approval_and_persists_audit()
    test_background_pdf_parse_tool_workflow_records_job_result()
    print("PDF tool workflow API tests passed")
