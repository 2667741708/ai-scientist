from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str, source_root: Path):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    os.environ["COSCIENTIST_SOURCE_EVIDENCE_ROOT"] = str(source_root)
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def persist_test_run(studio, run_id: str) -> None:
    record = studio.RunRecord(
        run_id=run_id,
        status="complete",
        created_at=1.0,
        updated_at=1.0,
        request=studio.RunRequest(research_goal="Validate source file evidence workflow"),
    )
    studio.persist_run_record(record)


def test_file_snapshot_workflow_requires_approval_and_persists_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source_root = Path(tmp) / "source"
        source_root.mkdir()
        source_file = source_root / "algorithm.py"
        source_file.write_text(
            "\n".join(
                [
                    "def score(values):",
                    "    return sum(values) / len(values)",
                    "",
                    "RESULT = score([1, 2, 3])",
                ]
            ),
            encoding="utf-8",
        )
        studio = load_studio(tmp, source_root)
        persist_test_run(studio, "run_file_snapshot")
        client = TestClient(studio.app)

        no_approval = client.post(
            "/api/tools/workflows/file-snapshot",
            json={"run_id": "run_file_snapshot", "source_path": "algorithm.py"},
        )
        assert no_approval.status_code == 428

        approved = client.post(
            "/api/tools/workflows/file-snapshot",
            json={
                "run_id": "run_file_snapshot",
                "source_path": "algorithm.py",
                "start_line": 2,
                "line_count": 2,
                "approval": {
                    "confirmed": True,
                    "scope": "file.source_snapshot",
                    "reason": "test source evidence",
                },
            },
        )
        assert approved.status_code == 200, approved.text
        payload = approved.json()
        assert payload["file_result"]["relative_path"] == "algorithm.py"
        assert "text" not in payload["file_result"]
        assert payload["file_result"]["line_count"] == 2
        assert payload["result_ref"]["result_id"]

        loaded = client.get(f"/api/tools/results/{payload['result_ref']['result_id']}")
        assert loaded.status_code == 200
        assert "2:     return sum(values)" in loaded.json()["content"]["text"]

        retrievals = client.get("/api/runs/run_file_snapshot/evidence-retrievals")
        assert retrievals.status_code == 200
        assert any(item["tool_name"] == "file.source_snapshot" for item in retrievals.json()["retrievals"])

        repeated = client.post(
            "/api/tools/workflows/file-snapshot",
            json={
                "run_id": "run_file_snapshot",
                "source_path": "algorithm.py",
                "start_line": 2,
                "line_count": 2,
                "approval": {
                    "confirmed": True,
                    "scope": "file.source_snapshot",
                },
            },
        )
        assert repeated.status_code == 409
        assert repeated.json()["detail"]["code"] == "repeated_identical_file_snapshot"


def test_file_snapshot_workflow_blocks_paths_outside_source_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source_root = Path(tmp) / "source"
        source_root.mkdir()
        outside = Path(tmp) / "outside.py"
        outside.write_text("print('outside')\n", encoding="utf-8")
        studio = load_studio(tmp, source_root)
        persist_test_run(studio, "run_file_guardrail")
        client = TestClient(studio.app)

        blocked = client.post(
            "/api/tools/workflows/file-snapshot",
            json={
                "run_id": "run_file_guardrail",
                "source_path": str(outside),
                "approval": {
                    "confirmed": True,
                    "scope": "file.source_snapshot",
                },
            },
        )
        assert blocked.status_code == 422
        assert blocked.json()["detail"]["code"] == "file_snapshot_guardrail_failed"


if __name__ == "__main__":
    test_file_snapshot_workflow_requires_approval_and_persists_result()
    test_file_snapshot_workflow_blocks_paths_outside_source_root()
    print("file snapshot workflow API tests passed")
