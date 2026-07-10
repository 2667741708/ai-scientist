from __future__ import annotations

import asyncio
import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str, experiment_root: Path):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    os.environ["COSCIENTIST_EXPERIMENT_ROOT"] = str(experiment_root)
    os.environ["COSCIENTIST_WORKER_ENABLED"] = "0"
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def persist_completed_run(studio, run_id: str) -> None:
    record = studio.RunRecord(
        run_id=run_id,
        status="complete",
        created_at=1.0,
        updated_at=2.0,
        request=studio.RunRequest(
            research_goal="Test a durable evidence and experiment research loop",
            demo_mode=True,
            literature_review=False,
            min_references=1,
            auto_discover_papers=False,
            auto_ingest_papers=False,
        ),
        hypotheses=[
            {
                "hypothesis_id": "hypothesis_1",
                "text": "The preregistered metric reaches the target threshold.",
                "experiment": "Run the fixed benchmark and compare the total metric against five.",
                "elo_rating": 1250,
                "evidence_packet": {
                    "status": "ready",
                    "snapshot_id": "evidence_packet_1",
                    "item_count": 1,
                    "parsed_fulltext_count": 1,
                    "experimental_data_count": 0,
                    "relationship_counts": {"support": 1},
                    "items": [
                        {
                            "evidence_id": "evidence_1",
                            "paper_id": "paper_1",
                            "chunk_id": "chunk_1",
                            "parse_run_id": "parse_1",
                            "title": "Benchmark evidence",
                            "support_level": "fulltext",
                            "source_reliability": "parsed_fulltext",
                            "relationship": "support",
                            "text_preview": "The benchmark metric is reproducible.",
                        }
                    ],
                },
            }
        ],
        evidence_snapshot={
            "status": "ready",
            "snapshot_id": "snapshot_1",
            "evidence_item_count": 1,
        },
    )
    studio.apply_citation_provenance_qa(record)
    record.research_outcome = studio.build_research_outcome(record)
    studio.persist_run_record(record)


def test_autopilot_creates_protocol_and_waits_for_compute_target() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        experiment_root = Path(tmp) / "experiments"
        experiment_root.mkdir()
        studio = load_studio(tmp, experiment_root)
        persist_completed_run(studio, "run_autopilot_plan")
        client = TestClient(studio.app)

        started = client.post(
            "/api/runs/run_autopilot_plan/autopilot",
            json={
                "policy": {
                    "mode": "guarded",
                    "auto_evidence": False,
                    "auto_plan": True,
                    "auto_execute": False,
                }
            },
        )
        assert started.status_code == 200, started.text
        item = studio.knowledge_base.list_work_items(
            run_id="run_autopilot_plan",
            workflow_name=studio.AUTOPILOT_WORKFLOW,
            limit=1,
        )[0]

        result = asyncio.run(studio.execute_research_autopilot_work_item(item))

        assert result["status"] == "awaiting_input"
        loaded = client.get("/api/runs/run_autopilot_plan/autopilot").json()["research_loop"]
        assert loaded["current_stage"] == "execute"
        assert loaded["experiment_protocol"]["source_refs"][0]["chunk_id"] == "chunk_1"
        run = client.get("/api/runs/run_autopilot_plan").json()
        assert run["hypotheses"][0]["experiment_protocol"]["status"] == "draft_needs_metric"


def test_autopilot_executes_once_interprets_metric_and_updates_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        experiment_root = Path(tmp) / "experiments"
        experiment_root.mkdir()
        script = experiment_root / "autopilot_metric.py"
        script.write_text(
            "import json\nprint('__RESULT_JSON__' + json.dumps({'total': 5}))\n",
            encoding="utf-8",
        )
        studio = load_studio(tmp, experiment_root)
        persist_completed_run(studio, "run_autopilot_execute")
        record = studio.load_run_record("run_autopilot_execute")
        assert record is not None
        queued = studio.enqueue_research_autopilot(
            record,
            {
                "mode": "autonomous_compute",
                "auto_evidence": False,
                "auto_execute": True,
                "auto_interpret": True,
                "auto_rerank": False,
                "compute": {
                    "kind": "local_python",
                    "script_path": "autopilot_metric.py",
                    "timeout_seconds": 10,
                },
                "evaluation": {"metric_path": "total", "operator": ">=", "threshold": 5},
                "grants": [
                    {"confirmed": True, "scope": "experiment.background_job", "max_uses": 1},
                    {"confirmed": True, "scope": "experiment.feedback", "max_uses": 1},
                ],
            },
        )

        result = asyncio.run(studio.execute_research_autopilot_work_item(queued["work_item"]))

        assert result["status"] == "complete"
        loaded = studio.load_run_record("run_autopilot_execute")
        assert loaded is not None
        assert loaded.research_loop["interpretation"]["verdict"] == "support"
        assert loaded.research_loop["execution"]["executor"] == "local_python"
        packet = loaded.hypotheses[0]["evidence_packet"]
        assert packet["relationship_counts"]["support"] == 2
        assert any(
            item.get("source_channel") == "policy_evaluated_experiment"
            for item in packet["items"]
        )
        grants = {
            grant["scope"]: grant
            for grant in loaded.research_loop["policy"]["grants"]
        }
        assert grants["experiment.background_job"]["used"] == 1
        assert grants["experiment.feedback"]["used"] == 1

        repeated = asyncio.run(studio.execute_research_autopilot_work_item(queued["work_item"]))
        assert repeated["status"] == "complete"
        jobs = studio.knowledge_base.list_background_jobs(run_id="run_autopilot_execute", limit=20)
        assert len(jobs) == 1
        feedback = studio.knowledge_base.list_feedback_items(
            run_id="run_autopilot_execute",
            limit=20,
        )
        assert len(feedback) == 1

        client = TestClient(studio.app)
        duplicate_start = client.post(
            "/api/runs/run_autopilot_execute/autopilot",
            json={"policy": {"mode": "guarded"}},
        )
        assert duplicate_start.status_code == 409
        public_run = client.get("/api/runs/run_autopilot_execute").json()
        assert "script_path" not in public_run["research_loop"]["policy"]["compute"]


def test_uncertain_execution_intent_stops_instead_of_replaying_command() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        experiment_root = Path(tmp) / "experiments"
        experiment_root.mkdir()
        studio = load_studio(tmp, experiment_root)
        persist_completed_run(studio, "run_autopilot_uncertain")
        record = studio.load_run_record("run_autopilot_uncertain")
        assert record is not None
        queued = studio.enqueue_research_autopilot(
            record,
            {
                "mode": "autonomous_compute",
                "auto_evidence": False,
                "auto_execute": True,
                "auto_interpret": True,
                "auto_rerank": False,
                "compute": {"kind": "local_python", "script_path": "never_replay.py"},
                "evaluation": {"metric_path": "total", "operator": ">=", "threshold": 5},
                "grants": [
                    {"confirmed": True, "scope": "experiment.background_job", "max_uses": 1},
                    {"confirmed": True, "scope": "experiment.feedback", "max_uses": 1},
                ],
            },
        )
        record = studio.load_run_record("run_autopilot_uncertain")
        assert record is not None
        winner_index, winner = studio.selected_loop_hypothesis(record)
        protocol = studio.build_experiment_protocol(
            winner,
            winner["evidence_packet"],
            record.research_loop["policy"],
        )
        job_id = studio.autopilot_execution_job_id(record, protocol)
        record.research_loop["execution"] = {
            "job_id": job_id,
            "status": "running",
            "protocol_id": protocol["protocol_id"],
            "hypothesis_index": winner_index,
        }
        studio.persist_run_record(record)
        studio.knowledge_base.create_background_job(
            job_id=job_id,
            run_id=record.run_id,
            workflow_name="experiment.background_job",
            phase="experiment_execution",
            arguments={"script_path": "never_replay.py", "autopilot": True},
        )
        studio.knowledge_base.update_background_job(job_id, status="running")

        result = asyncio.run(studio.execute_research_autopilot_work_item(queued["work_item"]))

        assert result["status"] == "awaiting_human"
        assert result["research_loop"]["current_stage"] == "execute"
        jobs = studio.knowledge_base.list_background_jobs(
            run_id="run_autopilot_uncertain",
            limit=20,
        )
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == job_id


def test_autopilot_rejects_inline_ssh_secrets_before_persistence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        experiment_root = Path(tmp) / "experiments"
        experiment_root.mkdir()
        studio = load_studio(tmp, experiment_root)
        persist_completed_run(studio, "run_autopilot_secret")
        client = TestClient(studio.app)

        response = client.post(
            "/api/runs/run_autopilot_secret/autopilot",
            json={
                "policy": {
                    "mode": "autonomous_compute",
                    "compute": {
                        "kind": "ssh",
                        "server_id": "c201-4090",
                        "command": "API_KEY=supersecret python train.py",
                    },
                }
            },
        )

        assert response.status_code == 422
        stored = studio.load_run_record("run_autopilot_secret")
        assert stored is not None
        assert stored.research_loop == {}


def test_resume_adds_compute_threshold_and_exact_grant_from_checkpoint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        experiment_root = Path(tmp) / "experiments"
        experiment_root.mkdir()
        (experiment_root / "resume_metric.py").write_text(
            "import json\nprint('__RESULT_JSON__' + json.dumps({'total': 7}))\n",
            encoding="utf-8",
        )
        studio = load_studio(tmp, experiment_root)
        persist_completed_run(studio, "run_autopilot_resume")
        client = TestClient(studio.app)
        started = client.post(
            "/api/runs/run_autopilot_resume/autopilot",
            json={
                "policy": {
                    "mode": "guarded",
                    "auto_evidence": False,
                    "continue_on_limited_evidence": True,
                }
            },
        )
        assert started.status_code == 200
        first_item_id = started.json()["work_item"]["work_item_id"]
        first_item = studio.knowledge_base.list_work_items(
            run_id="run_autopilot_resume",
            workflow_name=studio.AUTOPILOT_WORKFLOW,
            limit=1,
        )[0]
        planned = asyncio.run(studio.execute_research_autopilot_work_item(first_item))
        assert planned["status"] == "awaiting_input"

        resumed = client.post(
            "/api/runs/run_autopilot_resume/autopilot/resume",
            json={
                "compute": {
                    "kind": "local_python",
                    "script_path": "resume_metric.py",
                    "timeout_seconds": 10,
                },
                "evaluation": {"metric_path": "total", "operator": ">=", "threshold": 7},
                "grants": [
                    {
                        "confirmed": True,
                        "scope": "experiment.background_job",
                        "reason": "Explicit test approval",
                        "max_uses": 1,
                    }
                ],
                "auto_interpret": False,
                "auto_rerank": True,
            },
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["work_item"]["work_item_id"] != first_item_id
        resumed_item = studio.knowledge_base.list_work_items(
            run_id="run_autopilot_resume",
            workflow_name=studio.AUTOPILOT_WORKFLOW,
            limit=1,
        )[0]

        result = asyncio.run(studio.execute_research_autopilot_work_item(resumed_item))

        assert result["status"] == "awaiting_human"
        assert result["research_loop"]["current_stage"] == "review"
        jobs = studio.knowledge_base.list_background_jobs(
            run_id="run_autopilot_resume",
            limit=20,
        )
        assert len(jobs) == 1
