from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


class FakeWebEvidenceResult:
    def __init__(self, url: str) -> None:
        self.payload = {
            "artifact_id": "web_fake",
            "requested_url": url,
            "final_url": url,
            "status_code": 200,
            "content_type": "text/html",
            "content_hash": f"hash-{Path(url).name or 'root'}",
            "fetched_at": 1.0,
            "title": "Benchmark evidence page",
            "text_char_count": 120,
            "captured_text_char_count": 120,
            "response_truncated": False,
            "text_truncated": False,
            "snapshot_path": "fake/snapshot.txt",
            "metadata_path": "fake/metadata.json",
            "artifact_dir": "fake",
            "link_count": 2,
            "links": [{"url": "https://example.org/paper.pdf", "text": "PDF"}],
            "pdf_links": [{"url": "https://example.org/paper.pdf", "text": "PDF"}],
            "supplementary_links": [{"url": "https://example.org/code", "text": "supplementary code"}],
            "source_reliability": "best_effort_public_html",
            "guardrail": {"normalized_url": url},
            "text_preview": "Novel benchmark evidence reports an accuracy gain with reproducible artifacts.",
            "extracted_text": (
                "# Benchmark evidence page\n\n"
                "Novel benchmark evidence reports an accuracy gain with reproducible artifacts."
            ),
        }

    def public_payload(self):
        return {key: value for key, value in self.payload.items() if key != "extracted_text"}


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
        request=studio.RunRequest(research_goal="Validate web evidence extraction workflow"),
    )
    studio.persist_run_record(record)


def test_web_extract_workflow_requires_approval_and_persists_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        studio.extract_web_evidence = lambda url, **kwargs: FakeWebEvidenceResult(url)
        persist_test_run(studio, "run_web_extract")
        client = TestClient(studio.app)

        no_approval = client.post(
            "/api/tools/workflows/web-extract",
            json={
                "phase": "literature_review",
                "run_id": "run_web_extract",
                "url": "https://example.org/benchmark",
            },
        )
        assert no_approval.status_code == 428

        approved = client.post(
            "/api/tools/workflows/web-extract",
            json={
                "phase": "literature_review",
                "run_id": "run_web_extract",
                "url": "https://example.org/benchmark",
                "approval": {
                    "confirmed": True,
                    "scope": "browser.web_extract",
                    "reason": "test public web evidence",
                },
            },
        )
        assert approved.status_code == 200, approved.text
        payload = approved.json()
        assert payload["web_result"]["title"] == "Benchmark evidence page"
        assert "extracted_text" not in payload["web_result"]
        assert payload["web_result"]["knowledge_base_paper_id"]
        assert payload["result_ref"]["result_id"]

        loaded_result = client.get(f"/api/tools/results/{payload['result_ref']['result_id']}")
        assert loaded_result.status_code == 200
        assert "Novel benchmark evidence" in loaded_result.json()["content"]["extracted_text"]

        documents = studio.knowledge_base.list_documents()
        assert any(item.source == "web_evidence" for item in documents)

        retrievals = client.get("/api/runs/run_web_extract/evidence-retrievals")
        assert retrievals.status_code == 200
        assert any(item["tool_name"] == "browser.web_extract" for item in retrievals.json()["retrievals"])

        repeated = client.post(
            "/api/tools/workflows/web-extract",
            json={
                "phase": "literature_review",
                "run_id": "run_web_extract",
                "url": "https://example.org/benchmark",
                "approval": {
                    "confirmed": True,
                    "scope": "browser.web_extract",
                },
            },
        )
        assert repeated.status_code == 409
        assert repeated.json()["detail"]["code"] == "repeated_identical_web_extract"


def test_web_extract_background_job_persists_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        studio.extract_web_evidence = lambda url, **kwargs: FakeWebEvidenceResult(url)
        persist_test_run(studio, "run_web_background")
        client = TestClient(studio.app)

        queued = client.post(
            "/api/tools/workflows/web-extract/background",
            json={
                "phase": "literature_review",
                "run_id": "run_web_background",
                "url": "https://example.org/leaderboard",
                "approval": {
                    "confirmed": True,
                    "scope": "browser.web_extract",
                    "reason": "test web background",
                },
            },
        )
        assert queued.status_code == 200, queued.text
        job_id = queued.json()["job"]["job_id"]

        loaded_job = client.get(f"/api/tools/background-jobs/{job_id}")
        assert loaded_job.status_code == 200
        assert loaded_job.json()["status"] == "complete"
        assert loaded_job.json()["result_ref"]["tool_result"]["result_id"]


if __name__ == "__main__":
    test_web_extract_workflow_requires_approval_and_persists_evidence()
    test_web_extract_background_job_persists_status()
    print("web extract workflow API tests passed")
