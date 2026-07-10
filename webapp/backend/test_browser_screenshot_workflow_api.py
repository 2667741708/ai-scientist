from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


class FakeBrowserCaptureResult:
    def __init__(self, url: str) -> None:
        self.payload = {
            "artifact_id": "browser_fake",
            "requested_url": url,
            "final_url": url,
            "title": "Evidence screenshot page",
            "status_code": 200,
            "viewport": {"width": 1365, "height": 768},
            "full_page": True,
            "duration_seconds": 0.1,
            "screenshot_path": "fake/screenshot.png",
            "metadata_path": "fake/metadata.json",
            "artifact_dir": "fake",
            "console_count": 1,
            "console_messages": [{"type": "log", "text": "ready"}],
            "source_reliability": "browser_snapshot",
            "guardrail": {"normalized_url": url},
        }

    def public_payload(self):
        payload = dict(self.payload)
        payload.pop("console_messages", None)
        return payload


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
        request=studio.RunRequest(research_goal="Validate browser screenshot workflow"),
    )
    studio.persist_run_record(record)


def test_browser_screenshot_workflow_requires_approval_and_persists_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        studio.capture_browser_screenshot = lambda url, **kwargs: FakeBrowserCaptureResult(url)
        persist_test_run(studio, "run_browser_screenshot")
        client = TestClient(studio.app)

        no_approval = client.post(
            "/api/tools/workflows/browser-screenshot",
            json={
                "run_id": "run_browser_screenshot",
                "url": "https://example.org/evidence",
            },
        )
        assert no_approval.status_code == 428

        approved = client.post(
            "/api/tools/workflows/browser-screenshot",
            json={
                "run_id": "run_browser_screenshot",
                "phase": "evidence_audit",
                "url": "https://example.org/evidence",
                "approval": {
                    "confirmed": True,
                    "scope": "browser.capture_screenshot",
                    "reason": "test browser evidence",
                },
            },
        )
        assert approved.status_code == 200, approved.text
        payload = approved.json()
        assert payload["browser_result"]["screenshot_path"] == "fake/screenshot.png"
        assert "console_messages" not in payload["browser_result"]
        assert payload["result_ref"]["result_id"]

        loaded = client.get(f"/api/tools/results/{payload['result_ref']['result_id']}")
        assert loaded.status_code == 200
        assert loaded.json()["content"]["console_messages"][0]["text"] == "ready"

        retrievals = client.get("/api/runs/run_browser_screenshot/evidence-retrievals")
        assert retrievals.status_code == 200
        assert any(item["tool_name"] == "browser.capture_screenshot" for item in retrievals.json()["retrievals"])

        repeated = client.post(
            "/api/tools/workflows/browser-screenshot",
            json={
                "run_id": "run_browser_screenshot",
                "phase": "evidence_audit",
                "url": "https://example.org/evidence",
                "approval": {
                    "confirmed": True,
                    "scope": "browser.capture_screenshot",
                },
            },
        )
        assert repeated.status_code == 409
        assert repeated.json()["detail"]["code"] == "repeated_identical_browser_screenshot"


if __name__ == "__main__":
    test_browser_screenshot_workflow_requires_approval_and_persists_result()
    print("browser screenshot workflow API tests passed")
