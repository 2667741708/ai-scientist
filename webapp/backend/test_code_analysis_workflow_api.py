from __future__ import annotations

import importlib
import os
import sys
import tempfile
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
        request=studio.RunRequest(research_goal="Validate restricted code analysis workflow"),
    )
    studio.persist_run_record(record)


def test_code_analysis_workflow_requires_approval_and_persists_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        persist_test_run(studio, "run_code_analysis")
        client = TestClient(studio.app)

        no_approval = client.post(
            "/api/tools/workflows/code-analysis",
            json={
                "phase": "experiment_analysis",
                "run_id": "run_code_analysis",
                "code": "result = {'n': len([1, 2, 3])}",
            },
        )
        assert no_approval.status_code == 428

        approved = client.post(
            "/api/tools/workflows/code-analysis",
            json={
                "phase": "experiment_analysis",
                "run_id": "run_code_analysis",
                "timeout_seconds": 5,
                "code": "values = [1, 2, 3]\nresult = {'mean': statistics.mean(values)}\n",
                "approval": {
                    "confirmed": True,
                    "scope": "code.execute_analysis",
                    "reason": "test restricted analysis",
                },
            },
        )
        assert approved.status_code == 200, approved.text
        payload = approved.json()
        assert payload["analysis_result"]["status"] == "complete"
        assert payload["analysis_result"]["result_json"] == {"mean": 2}
        assert payload["result_ref"]["result_id"]

        loaded = client.get(f"/api/tools/results/{payload['result_ref']['result_id']}")
        assert loaded.status_code == 200
        assert loaded.json()["content"]["status"] == "complete"

        tool_calls = client.get("/api/runs/run_code_analysis/tool-calls")
        assert tool_calls.status_code == 200
        assert tool_calls.json()["count"] == 1
        assert tool_calls.json()["tool_calls"][0]["tool_name"] == "code.execute_analysis"

        repeated = client.post(
            "/api/tools/workflows/code-analysis",
            json={
                "phase": "experiment_analysis",
                "run_id": "run_code_analysis",
                "timeout_seconds": 5,
                "code": "values = [1, 2, 3]\nresult = {'mean': statistics.mean(values)}\n",
                "approval": {
                    "confirmed": True,
                    "scope": "code.execute_analysis",
                },
            },
        )
        assert repeated.status_code == 409
        assert repeated.json()["detail"]["code"] == "repeated_identical_code_analysis"


def test_code_analysis_workflow_records_guardrail_blocks_and_background_jobs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        persist_test_run(studio, "run_code_blocked")
        client = TestClient(studio.app)

        blocked = client.post(
            "/api/tools/workflows/code-analysis",
            json={
                "phase": "experiment_analysis",
                "run_id": "run_code_blocked",
                "code": "import os\nresult = os.listdir('.')\n",
                "approval": {
                    "confirmed": True,
                    "scope": "code.execute_analysis",
                    "reason": "test blocked analysis",
                },
            },
        )
        assert blocked.status_code == 200, blocked.text
        blocked_payload = blocked.json()
        assert blocked_payload["analysis_result"]["status"] == "blocked"
        assert blocked_payload["analysis_result"]["guardrail"]["allowed"] is False

        tool_calls = client.get("/api/runs/run_code_blocked/tool-calls")
        assert tool_calls.status_code == 200
        assert tool_calls.json()["tool_calls"][0]["status"] == "blocked"

        queued = client.post(
            "/api/tools/workflows/code-analysis/background",
            json={
                "phase": "experiment_analysis",
                "run_id": "run_code_blocked",
                "code": "values = [2, 4, 8]\nresult = {'total': sum(values)}\n",
                "approval": {
                    "confirmed": True,
                    "scope": "code.execute_analysis",
                    "reason": "test background analysis",
                },
            },
        )
        assert queued.status_code == 200, queued.text
        job_id = queued.json()["job"]["job_id"]
        loaded_job = client.get(f"/api/tools/background-jobs/{job_id}")
        assert loaded_job.status_code == 200
        assert loaded_job.json()["status"] == "complete"
        assert loaded_job.json()["result_ref"]["analysis_status"] == "complete"


if __name__ == "__main__":
    test_code_analysis_workflow_requires_approval_and_persists_result()
    test_code_analysis_workflow_records_guardrail_blocks_and_background_jobs()
    print("code analysis workflow API tests passed")
