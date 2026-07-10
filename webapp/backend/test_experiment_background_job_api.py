from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str, experiment_root: Path):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    os.environ["COSCIENTIST_EXPERIMENT_ROOT"] = str(experiment_root)
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def persist_test_run(studio, run_id: str) -> None:
    record = studio.RunRecord(
        run_id=run_id,
        status="complete",
        created_at=1.0,
        updated_at=1.0,
        request=studio.RunRequest(
            research_goal="Validate restricted experiment background job",
            demo_mode=True,
            literature_review=False,
        ),
        hypotheses=[
            {
                "text": "The metric job output supports a reproducible benchmark result.",
                "elo_rating": 1200,
                "evidence_packet": {"status": "absent", "items": [], "item_count": 0},
            }
        ],
    )
    studio.persist_run_record(record)


def test_experiment_background_job_requires_approval_and_persists_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        experiment_root = Path(tmp) / "experiments"
        experiment_root.mkdir()
        script = experiment_root / "metric_job.py"
        script.write_text(
            "\n".join(
                [
                    "import json",
                    "values = [int(item) for item in __import__('sys').argv[1:]]",
                    "print('experiment ready')",
                    "print('__RESULT_JSON__' + json.dumps({'total': sum(values), 'n': len(values)}))",
                ]
            ),
            encoding="utf-8",
        )
        studio = load_studio(tmp, experiment_root)
        persist_test_run(studio, "run_experiment_job")
        client = TestClient(studio.app)

        no_approval = client.post(
            "/api/tools/workflows/experiment-job",
            json={
                "run_id": "run_experiment_job",
                "hypothesis_index": 0,
                "script_path": "metric_job.py",
                "args": ["2", "3"],
            },
        )
        assert no_approval.status_code == 428

        approved = client.post(
            "/api/tools/workflows/experiment-job",
            json={
                "run_id": "run_experiment_job",
                "hypothesis_index": 0,
                "phase": "experiment_execution",
                "script_path": "metric_job.py",
                "args": ["2", "3"],
                "timeout_seconds": 10,
                "approval": {
                    "confirmed": True,
                    "scope": "experiment.background_job",
                    "reason": "test restricted experiment runner",
                },
            },
        )
        assert approved.status_code == 200, approved.text
        job_id = approved.json()["job"]["job_id"]
        loaded_job = client.get(f"/api/tools/background-jobs/{job_id}")
        assert loaded_job.status_code == 200
        assert loaded_job.json()["status"] == "complete"
        result_id = loaded_job.json()["result_ref"]["tool_result"]["result_id"]

        loaded_result = client.get(f"/api/tools/results/{result_id}")
        assert loaded_result.status_code == 200
        assert loaded_result.json()["content"]["result_json"] == {"total": 5, "n": 2}
        assert loaded_result.json()["content"]["stdout"] == "experiment ready\n"

        attached_run = client.get("/api/runs/run_experiment_job")
        experiment_runs = attached_run.json()["hypotheses"][0]["experiment_runs"]
        assert experiment_runs[0]["job_id"] == job_id
        assert experiment_runs[0]["interpretation_status"] == "awaiting_human_interpretation"

        no_feedback_approval = client.post(
            "/api/runs/run_experiment_job/experiment-feedback",
            json={
                "job_id": job_id,
                "hypothesis_index": 0,
                "verdict": "support",
                "rationale": "The expected metric total was reproduced.",
                "rerank": True,
            },
        )
        assert no_feedback_approval.status_code == 428

        feedback = client.post(
            "/api/runs/run_experiment_job/experiment-feedback",
            json={
                "job_id": job_id,
                "hypothesis_index": 0,
                "verdict": "support",
                "rationale": "The expected metric total was reproduced.",
                "rerank": True,
                "approval": {
                    "confirmed": True,
                    "scope": "experiment.feedback",
                    "reason": "human reviewed the experiment output",
                },
            },
        )
        assert feedback.status_code == 200, feedback.text
        assert feedback.json()["evidence_item"]["relationship"] == "support"
        assert feedback.json()["rerank_error"] is None
        rerank_run = feedback.json()["rerank_run"]
        assert rerank_run["parent_run_id"] == "run_experiment_job"
        continued = client.get(f"/api/runs/{rerank_run['run_id']}")
        assert continued.status_code == 200
        assert continued.json()["request"]["parent_run_id"] == "run_experiment_job"

        interpreted_run = client.get("/api/runs/run_experiment_job").json()
        packet = interpreted_run["hypotheses"][0]["evidence_packet"]
        assert packet["relationship_counts"]["support"] == 1
        assert packet["experimental_data_count"] == 1

        tool_calls = client.get("/api/runs/run_experiment_job/tool-calls")
        assert tool_calls.status_code == 200
        assert any(
            item["tool_name"] == "experiment.background_job"
            for item in tool_calls.json()["tool_calls"]
        ), tool_calls.json()

        repeated = client.post(
            "/api/tools/workflows/experiment-job",
            json={
                "run_id": "run_experiment_job",
                "hypothesis_index": 0,
                "phase": "experiment_execution",
                "script_path": "metric_job.py",
                "args": ["2", "3"],
                "timeout_seconds": 10,
                "approval": {
                    "confirmed": True,
                    "scope": "experiment.background_job",
                },
            },
        )
        assert repeated.status_code == 409
        assert repeated.json()["detail"]["code"] == "repeated_identical_experiment_job"


def test_experiment_background_job_blocks_scripts_outside_experiment_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        experiment_root = Path(tmp) / "experiments"
        experiment_root.mkdir()
        outside = Path(tmp) / "outside.py"
        outside.write_text("print('blocked')\n", encoding="utf-8")
        studio = load_studio(tmp, experiment_root)
        persist_test_run(studio, "run_experiment_guardrail")
        client = TestClient(studio.app)

        blocked = client.post(
            "/api/tools/workflows/experiment-job",
            json={
                "run_id": "run_experiment_guardrail",
                "script_path": str(outside),
                "approval": {
                    "confirmed": True,
                    "scope": "experiment.background_job",
                },
            },
        )
        assert blocked.status_code == 422
        assert blocked.json()["detail"]["code"] == "experiment_guardrail_failed"


if __name__ == "__main__":
    test_experiment_background_job_requires_approval_and_persists_result()
    test_experiment_background_job_blocks_scripts_outside_experiment_root()
    print("experiment background job API tests passed")
