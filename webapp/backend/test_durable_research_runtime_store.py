from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from knowledge_base import DEFAULT_LIBRARY_ID, KnowledgeBaseStore


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


def test_research_work_item_lease_can_be_renewed_by_owner() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.long_running",
            arguments={},
        )
        leased = store.lease_work_items(owner="worker-renew", limit=1, lease_seconds=1)[0]
        assert store.renew_work_item_lease(item["work_item_id"], "other-worker", lease_seconds=30) is False

        assert store.renew_work_item_lease(item["work_item_id"], "worker-renew", lease_seconds=30) is True
        renewed = store.get_work_item(item["work_item_id"])
        assert renewed["lease_owner"] == "worker-renew"
        assert renewed["lease_expires_at"] > leased["lease_expires_at"]

        store.complete_work_item(item["work_item_id"], {"ok": True})
        assert store.renew_work_item_lease(item["work_item_id"], "worker-renew", lease_seconds=30) is False

        expired = store.enqueue_work_item(
            workflow_name="workflow.expired",
            arguments={},
        )
        store.lease_work_items(owner="worker-expired", limit=1, lease_seconds=1)
        with store._connection() as connection:
            connection.execute(
                """
                UPDATE research_work_items
                SET lease_expires_at = ?
                WHERE work_item_id = ?
                """,
                (0, expired["work_item_id"]),
            )
        assert store.renew_work_item_lease(expired["work_item_id"], "worker-expired", lease_seconds=30) is False


def test_research_work_item_can_be_blocked_for_manual_recovery() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.needs_approval",
            arguments={"approval": "required"},
            max_attempts=3,
        )
        leased = store.lease_work_items(owner="worker-block", limit=1)
        assert leased[0]["status"] == "leased"

        store.block_work_item(item["work_item_id"], "Waiting for expert approval.")

        blocked = store.get_work_item(item["work_item_id"])
        counts = store.work_item_status_counts()
        assert blocked["status"] == "blocked"
        assert blocked["lease_owner"] is None
        assert blocked["lease_expires_at"] is None
        assert blocked["error_message"] == "Waiting for expert approval."
        assert counts["blocked"] == 1
        assert counts["active"] == 1
        assert store.lease_work_items(owner="worker-block", limit=1) == []


def test_blocked_work_item_can_be_unblocked_for_retry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.needs_approval",
            arguments={"approval": "required"},
            max_attempts=3,
        )
        store.lease_work_items(owner="worker-block", limit=1)
        store.block_work_item(item["work_item_id"], "Waiting for expert approval.")

        assert store.unblock_work_item(item["work_item_id"], "Expert approval granted.") is True
        unblocked = store.get_work_item(item["work_item_id"])
        assert unblocked["status"] == "retrying"
        assert unblocked["error_message"] == "Expert approval granted."
        assert store.work_item_status_counts()["retrying"] == 1

        leased_again = store.lease_work_items(owner="worker-after-approval", limit=1)
        assert leased_again[0]["work_item_id"] == item["work_item_id"]
        assert leased_again[0]["attempt_count"] == 2

        store.complete_work_item(item["work_item_id"], {"done": True})
        assert store.unblock_work_item(item["work_item_id"]) is False
        assert store.get_work_item(item["work_item_id"])["status"] == "complete"


def test_work_item_status_counts_can_scope_worker_progress() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        queued = store.enqueue_work_item(
            workflow_name="workflow.open_coscientist_run",
            run_id="run-counts",
            arguments={},
            priority=5,
        )
        leased = store.enqueue_work_item(
            workflow_name="workflow.other",
            run_id="run-counts",
            arguments={},
            priority=1,
        )
        completed = store.enqueue_work_item(
            workflow_name="workflow.other",
            run_id="run-done",
            arguments={},
        )
        cancelled = store.enqueue_work_item(
            workflow_name="workflow.cancelled",
            run_id="run-cancelled",
            arguments={},
        )
        store.lease_work_items(owner="worker-counts", limit=1)
        store.complete_work_item(completed["work_item_id"], {"ok": True})
        store.cancel_work_item(cancelled["work_item_id"])

        counts = store.work_item_status_counts()
        scoped_counts = store.work_item_status_counts(run_id="run-counts")
        workflow_counts = store.work_item_status_counts(workflow_name="workflow.open_coscientist_run")

        assert counts["queued"] == 1
        assert counts["leased"] == 1
        assert counts["complete"] == 1
        assert counts["cancelled"] == 1
        assert counts["active"] == 2
        assert scoped_counts["queued"] == 1
        assert scoped_counts["leased"] == 1
        assert scoped_counts["complete"] == 0
        assert scoped_counts["active"] == 2
        assert workflow_counts["queued"] == 1
        assert workflow_counts["leased"] == 0
        assert workflow_counts["active"] == 1
        assert store.get_work_item(queued["work_item_id"])["status"] == "queued"
        assert store.get_work_item(leased["work_item_id"])["status"] == "leased"


def test_active_work_item_snapshot_hides_internal_refs_by_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.open_coscientist_run",
            run_id="run-snapshot",
            phase="ranking",
            agent_role="ranking_agent",
            arguments={"provider_payload": "do-not-show"},
            max_attempts=3,
        )
        store.lease_work_items(owner="worker-secret", limit=1)
        store.fail_work_item(
            item["work_item_id"],
            "Previous failure\nwith internal details " + ("x" * 240),
            retryable=True,
        )

        snapshot = store.active_work_item_snapshot(run_id="run-snapshot")
        assert snapshot["counts"]["retrying"] == 1
        assert snapshot["counts"]["active"] == 1
        assert snapshot["filters"]["run_id"] is True
        assert snapshot["items"][0]["status"] == "retrying"
        assert snapshot["items"][0]["workflow_label"] == "Research run"
        assert snapshot["items"][0]["phase"] == "ranking"
        assert snapshot["items"][0]["agent_role"] == "ranking_agent"
        assert snapshot["items"][0]["attempts"]["remaining"] == 2
        assert snapshot["items"][0]["error_summary"].endswith("...")
        assert "work_item_id" not in snapshot["items"][0]
        assert "run_id" not in snapshot["items"][0]
        assert "lease_owner" not in snapshot["items"][0]
        assert "arguments" not in snapshot["items"][0]
        assert "provider_payload" not in str(snapshot)

        expert_snapshot = store.active_work_item_snapshot(
            run_id="run-snapshot",
            include_internal_refs=True,
        )
        assert expert_snapshot["filters"]["run_id"] == "run-snapshot"
        assert expert_snapshot["items"][0]["work_item_id"] == item["work_item_id"]
        assert expert_snapshot["items"][0]["run_id"] == "run-snapshot"


def test_cancel_work_item_does_not_override_terminal_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        item = store.enqueue_work_item(
            workflow_name="workflow.terminal",
            arguments={},
        )
        assert store.cancel_work_item(item["work_item_id"], "User cancelled.") is True
        assert store.get_work_item(item["work_item_id"])["status"] == "cancelled"

        completed = store.enqueue_work_item(
            workflow_name="workflow.terminal",
            arguments={},
        )
        store.complete_work_item(completed["work_item_id"], {"ok": True})

        assert store.cancel_work_item(completed["work_item_id"], "Too late.") is False
        still_completed = store.get_work_item(completed["work_item_id"])
        assert still_completed["status"] == "complete"
        assert still_completed["error_message"] is None


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
        store.store_feedback_item(
            run_id="run_memory",
            target_type="run",
            target_ref={},
            feedback_type="critique",
            text="Run-level critique should not match hypothesis preference filters.",
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
        hypothesis_preferences = store.list_feedback_items(
            run_id="run_memory",
            target_type="hypothesis",
            feedback_type="prefer",
        )
        assert [item["feedback_id"] for item in hypothesis_preferences] == [feedback["feedback_id"]]
        assert store.latest_checkpoint_metadata("run_memory")["checkpoint_id"] == checkpoint["checkpoint_id"]

        memory = store.build_memory_context(
            research_goal="retrieval evidence tracing",
            parent_run_id="run_memory",
            memory_scope="project",
        )
        assert memory["parent_run"]["run_id"] == "run_memory"
        assert memory["prior_hypotheses"][0]["hypothesis_id"] == "hyp_1"
        assert {item["feedback_type"] for item in memory["user_feedback"]} == {"critique", "prefer"}
        assert memory["execution_memory"]["status"] == "limited"
        assert memory["execution_memory"]["latest_checkpoint"]["checkpoint_id"] == checkpoint["checkpoint_id"]
        assert memory["memory_sources"] == [
            "parent_run",
            "prior_hypotheses",
            "chat_feedback",
        ]
        assert memory["evidence_boundary"]["status"] == "absent"
        assert memory["evidence_boundary"]["evidence_count"] == 0
        assert "absent evidence is not support" in memory["evidence_boundary"]["boundary"]
        assert memory["memory_boundary"] == "Summaries only; raw records are not injected."


def test_checkpoint_status_summary_reports_resume_boundary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))

        missing = store.checkpoint_status_summary("run_missing")
        assert missing["status"] == "not_available"
        assert missing["checkpoint_available"] is False
        assert missing["resume_supported"] is False

        store.persist_checkpoint_metadata(
            checkpoint_id="checkpoint_limited",
            run_id="run_checkpoint",
            thread_id="run_checkpoint",
            phase="review",
            status="saved",
            checkpoint_backend="metadata_only",
            state_summary={"completed_phase": "review"},
        )
        limited = store.checkpoint_status_summary("run_checkpoint")
        assert limited["status"] == "limited"
        assert limited["resume_mode"] == "metadata_only_retry"
        assert limited["resume_config_fields"] == ["thread_id"]
        assert limited["latest_checkpoint"]["state_summary"]["completed_phase"] == "review"
        assert "full LangGraph state resume remains limited" in limited["boundary"]

        store.persist_checkpoint_metadata(
            checkpoint_id="checkpoint_ready",
            run_id="run_checkpoint",
            thread_id="run_checkpoint",
            phase="ranking",
            status="saved",
            checkpoint_backend="langgraph_sqlite",
            checkpoint_ref="checkpoint-ready-ref",
            state_summary={"completed_phase": "ranking"},
        )
        ready = store.checkpoint_status_summary("run_checkpoint")
        assert ready["status"] == "ready"
        assert ready["resume_supported"] is True
        assert ready["resume_mode"] == "langgraph_thread_resume"
        assert ready["resume_config_fields"] == ["thread_id", "checkpoint_id", "checkpoint_ns"]
        assert ready["latest_checkpoint"]["checkpoint_id"] == "checkpoint_ready"
        assert ready["latest_checkpoint"]["checkpoint_ref"] == "checkpoint-ready-ref"


def test_current_run_memory_scope_does_not_retrieve_project_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        store.ingest(
            title="Project evidence that should stay out of current-run memory",
            content="Retrieval evidence tracing appears in the broader project knowledge base.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
        )

        current_memory = store.build_memory_context(
            research_goal="retrieval evidence tracing",
            memory_scope="current_run",
        )
        project_memory = store.build_memory_context(
            research_goal="retrieval evidence tracing",
            memory_scope="project",
        )

        assert current_memory["evidence_summaries"] == []
        assert current_memory["memory_sources"] == ["memory_limitations"]
        assert current_memory["evidence_boundary"]["status"] == "absent"
        assert current_memory["execution_memory"]["status"] == "not_available"
        assert "current_run scope" in current_memory["known_gaps"][0]
        assert project_memory["evidence_summaries"]
        assert "knowledge_base" in project_memory["memory_sources"]
        assert project_memory["evidence_boundary"]["status"] == "parsed_fulltext"
        assert project_memory["evidence_boundary"]["parsed_fulltext_count"] >= 1
        assert "Retrieval evidence tracing" in project_memory["evidence_summaries"][0]["snippet"]


def test_memory_scope_library_filters_evidence_without_narrowing_project_or_global() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        primary_library = store.create_library(name="Primary library")["library_id"]
        secondary_library = store.create_library(name="Secondary library")["library_id"]
        query = "crosslibrary retrieval marker"
        store.ingest(
            title="Primary scoped evidence",
            content=f"{query} supports the first library-specific context.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
            library_id=primary_library,
        )
        store.ingest(
            title="Secondary scoped evidence",
            content=f"{query} supports the second library-specific context.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
            library_id=secondary_library,
        )

        library_memory = store.build_memory_context(
            research_goal=query,
            memory_scope="library",
            library_id=primary_library,
            max_evidence=10,
        )
        project_memory = store.build_memory_context(
            research_goal=query,
            memory_scope="project",
            library_id=primary_library,
            max_evidence=10,
        )
        global_memory = store.build_memory_context(
            research_goal=query,
            memory_scope="global",
            library_id=primary_library,
            max_evidence=10,
        )

        library_ids = {item["library_id"] for item in library_memory["evidence_summaries"]}
        project_library_ids = {item["library_id"] for item in project_memory["evidence_summaries"]}
        global_library_ids = {item["library_id"] for item in global_memory["evidence_summaries"]}

        assert library_ids == {primary_library}
        assert {primary_library, secondary_library}.issubset(project_library_ids)
        assert {primary_library, secondary_library}.issubset(global_library_ids)


def test_memory_context_prioritizes_grounded_evidence_summaries() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        query = "prioritymarker evidence retrieval"
        store.ingest(
            title="User note evidence",
            content=f"# Notes\n\n{query} appears in a low reliability note.",
            source="note",
            source_reliability="user_provided",
        )
        store.ingest(
            title="Parsed fulltext evidence",
            content=f"# Results\n\n{query} appears in a parsed fulltext result section.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
        )

        memory = store.build_memory_context(
            research_goal=query,
            memory_scope="project",
            max_evidence=4,
        )

        assert len(memory["evidence_summaries"]) >= 2
        assert memory["evidence_summaries"][0]["source_reliability"] == "parsed_fulltext"
        assert memory["evidence_summaries"][0]["memory_priority"] > memory["evidence_summaries"][1]["memory_priority"]


def test_library_memory_scope_without_library_id_uses_default_library() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        other_library = store.create_library(name="Other library")["library_id"]
        query = "default library scoped retrieval marker"
        store.ingest(
            title="Default library evidence",
            content=f"{query} should be visible for default library memory.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
        )
        store.ingest(
            title="Other library evidence",
            content=f"{query} should stay out when no explicit library is selected.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
            library_id=other_library,
        )

        memory = store.build_memory_context(
            research_goal=query,
            memory_scope="library",
            max_evidence=10,
        )

        assert {item["library_id"] for item in memory["evidence_summaries"]} == {DEFAULT_LIBRARY_ID}


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
