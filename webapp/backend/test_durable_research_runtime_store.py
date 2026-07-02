from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from knowledge_base import KnowledgeBaseStore


def test_research_work_items_enqueue_lease_complete_and_recover() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))

        item = store.enqueue_work_item(
            workflow_name="workflow.open_coscientist_run",
            run_id="run_queue",
            arguments={"demo_mode": True},
            priority=2,
            max_attempts=2,
        )
        duplicate = store.enqueue_work_item(
            workflow_name="workflow.open_coscientist_run",
            run_id="run_queue",
            arguments={"demo_mode": True},
        )
        assert duplicate["work_item_id"] == item["work_item_id"]

        leased = store.lease_work_items(owner="worker-a", limit=2, lease_seconds=1)
        assert len(leased) == 1
        assert leased[0]["status"] == "leased"
        assert leased[0]["lease_owner"] == "worker-a"
        assert leased[0]["attempt_count"] == 1

        store.mark_work_item_running(item["work_item_id"], "worker-a")
        assert store.get_work_item(item["work_item_id"])["status"] == "running"

        recovered = store.recover_expired_leases(now=leased[0]["lease_expires_at"] + 1)
        assert recovered == 1
        assert store.get_work_item(item["work_item_id"])["status"] == "retrying"

        leased_again = store.lease_work_items(owner="worker-b", limit=1, lease_seconds=60)
        assert leased_again[0]["attempt_count"] == 2
        store.complete_work_item(item["work_item_id"], {"run_id": "run_queue"})

        completed = store.get_work_item(item["work_item_id"])
        assert completed["status"] == "complete"
        assert completed["result_ref"]["run_id"] == "run_queue"
        assert completed["lease_owner"] is None


def test_research_work_item_failure_uses_retry_budget() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))

        item = store.enqueue_work_item(
            workflow_name="tool.pdf_parse",
            arguments={"input": "paper.pdf"},
            max_attempts=1,
        )
        leased = store.lease_work_items(owner="worker-a", limit=1)
        assert leased[0]["work_item_id"] == item["work_item_id"]

        store.fail_work_item(item["work_item_id"], "parse failed", retryable=True)
        failed = store.get_work_item(item["work_item_id"])
        assert failed["status"] == "error"
        assert failed["error_message"] == "parse failed"


def test_research_feedback_checkpoints_and_memory_context() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        store.record_research_run(
            {
                "run_id": "run_memory",
                "status": "complete",
                "created_at": 1.0,
                "updated_at": 2.0,
                "request": {"research_goal": "Find falsifiable retrieval hypotheses"},
                "metrics": {"summary": "Generated and ranked one hypothesis."},
                "hypotheses": [
                    {
                        "id": "hyp_1",
                        "text": "Section-aware retrieval improves evidence tracing.",
                        "explanation": "Preserving sections reduces provenance loss.",
                        "elo_rating": 1040,
                        "support_level": "limited",
                    }
                ],
            }
        )

        feedback = store.store_feedback_item(
            run_id="run_memory",
            target_type="hypothesis",
            target_ref={"hypothesis_index": 0},
            feedback_type="prefer",
            text="Prefer this because it is easier to falsify.",
        )
        checkpoint = store.persist_checkpoint_metadata(
            checkpoint_id="checkpoint_memory",
            run_id="run_memory",
            thread_id="run_memory",
            phase="review",
            status="saved",
            checkpoint_backend="metadata_only",
            state_summary={"completed_phase": "review"},
        )

        assert store.get_feedback_item(feedback["feedback_id"])["target_ref"]["hypothesis_index"] == 0
        assert store.latest_checkpoint_metadata("run_memory")["checkpoint_id"] == checkpoint["checkpoint_id"]

        memory = store.build_memory_context(
            research_goal="retrieval evidence tracing",
            parent_run_id="run_memory",
            memory_scope="project",
        )
        assert memory["parent_run"]["run_id"] == "run_memory"
        assert memory["prior_hypotheses"][0]["hypothesis_id"] == "hyp_1"
        assert memory["user_feedback"][0]["feedback_type"] == "prefer"
        assert memory["memory_boundary"] == "Summaries only; raw records are not injected."


def test_research_runtime_schema_migrates_legacy_work_item_table() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "knowledge.sqlite3"
        connection = sqlite3.connect(db_path)
        try:
            connection.execute(
                """
                CREATE TABLE research_work_items (
                    work_item_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    workflow_name TEXT NOT NULL,
                    phase TEXT,
                    agent_role TEXT,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 3,
                    lease_owner TEXT,
                    lease_expires_at REAL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    arguments_json TEXT NOT NULL,
                    result_ref_json TEXT NOT NULL,
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.open_coscientist_run",
            run_id="run_legacy",
            arguments={},
        )

        assert item["idempotency_key"] == "workflow.open_coscientist_run:run_legacy"
