from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import TypedDict

import pytest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from open_coscientist.models import ExecutionMetrics, Hypothesis


def test_langgraph_thread_config_uses_run_id_as_thread_id() -> None:
    from open_coscientist.checkpointing import langgraph_thread_config

    config = langgraph_thread_config(
        " run-thread-config ",
        recursion_limit=42,
        checkpoint_ns="execution-memory",
    )

    assert config == {
        "recursion_limit": 42,
        "configurable": {
            "thread_id": "run-thread-config",
            "checkpoint_ns": "execution-memory",
        },
    }
    assert "channel_values" not in repr(config)


def test_langgraph_thread_config_rejects_blank_run_id() -> None:
    from open_coscientist.checkpointing import langgraph_thread_config

    with pytest.raises(ValueError, match="run_id is required"):
        langgraph_thread_config("   ")


def test_langgraph_resume_config_adds_checkpoint_identity() -> None:
    from open_coscientist.checkpointing import langgraph_resume_config

    config = langgraph_resume_config(
        " run-resume-config ",
        checkpoint_id=" checkpoint-123 ",
        checkpoint_ns="execution-memory",
        recursion_limit=17,
    )

    assert config == {
        "recursion_limit": 17,
        "configurable": {
            "thread_id": "run-resume-config",
            "checkpoint_ns": "execution-memory",
            "checkpoint_id": "checkpoint-123",
        },
    }


def test_execution_memory_status_reports_sqlite_saver_boundary() -> None:
    from open_coscientist.checkpointing import execution_memory_status

    status = execution_memory_status()
    assert status["thread_id_required"] is True
    assert status["thread_id_source"] == "run_id"
    assert status["checkpoint_backend"] in {"sqlite_metadata", "langgraph_sqlite"}
    assert status["checkpointer_package"] == "langgraph-checkpoint-sqlite"
    assert status["resume_config_fields"] == ["thread_id", "checkpoint_id", "checkpoint_ns"]
    assert "progress_callback" in status["runtime_only_state_keys"]
    assert "tool_registry" in status["runtime_only_state_keys"]
    if status["langgraph_checkpoint_sqlite_available"]:
        assert status["status"] == "ready"
        assert status["resume_supported"] is True
        assert status["resume_mode"] == "langgraph_thread_resume"
        assert "thread_id=run_id" in status["resume_boundary"]
    else:
        assert status["status"] == "limited"
        assert status["resume_supported"] is False
        assert status["resume_mode"] == "metadata_only_retry"
        assert "full LangGraph state resume remains limited" in status["resume_boundary"]
        assert "metadata-only" in status["boundary"]


def test_execution_recovery_policy_summarizes_resume_and_retry_modes() -> None:
    from open_coscientist.checkpointing import execution_recovery_policy

    ready = execution_recovery_policy(
        {
            "status": "ready",
            "checkpoint_available": True,
            "resume_supported": True,
            "resume_config_fields": ["thread_id", "checkpoint_id", "checkpoint_ns"],
        },
        work_item_status="running",
    )
    assert ready["recovery_mode"] == "resume_from_checkpoint"
    assert ready["can_resume"] is True
    assert ready["should_retry"] is False
    assert ready["resume_config_fields"] == ["thread_id", "checkpoint_id", "checkpoint_ns"]
    assert "channel values" in ready["boundary"]

    limited = execution_recovery_policy(
        {
            "status": "limited",
            "checkpoint_available": True,
            "resume_supported": False,
        },
        work_item_status="retrying",
    )
    assert limited["recovery_mode"] == "metadata_guided_retry"
    assert limited["can_resume"] is False
    assert limited["should_retry"] is True
    assert limited["work_item_recoverable"] is True

    queued_without_checkpoint = execution_recovery_policy(None, work_item_status="queued")
    assert queued_without_checkpoint["recovery_mode"] == "queue_retry_without_checkpoint"
    assert queued_without_checkpoint["should_retry"] is True
    assert queued_without_checkpoint["resume_config_fields"] == ["thread_id"]

    failed_without_checkpoint = execution_recovery_policy(None, work_item_status="error")
    assert failed_without_checkpoint["recovery_mode"] == "not_recoverable"
    assert failed_without_checkpoint["should_retry"] is False
    assert failed_without_checkpoint["work_item_recoverable"] is False


def test_execution_resume_readiness_combines_checkpoint_and_work_item_state() -> None:
    from open_coscientist.checkpointing import execution_resume_readiness

    readiness = execution_resume_readiness(
        run_id=" run-resume-ready ",
        execution_memory={
            "status": "ready",
            "checkpoint_backend": "langgraph_sqlite",
            "resume_supported": True,
            "resume_config_fields": ["thread_id", "checkpoint_id", "checkpoint_ns"],
        },
        checkpoint_metadata={
            "run_id": "run-resume-ready",
            "thread_id": "run-resume-ready",
            "checkpoint_id": "checkpoint-secret",
            "checkpoint_ns": "execution-memory",
            "checkpoint_backend": "langgraph_sqlite",
            "phase": "review",
            "status": "saved",
            "state_summary": {"raw": "SECRET STATE"},
        },
        work_item={"status": "running", "lease_owner": "worker-secret"},
    )

    assert readiness["status"] == "ready_to_resume"
    assert readiness["run_id"] == "run-resume-ready"
    assert readiness["thread_id"] == "run-resume-ready"
    assert readiness["thread_id_matches_run_id"] is True
    assert readiness["checkpoint_available"] is True
    assert readiness["checkpoint_backend"] == "langgraph_sqlite"
    assert readiness["checkpoint_phase"] == "review"
    assert readiness["checkpoint_status"] == "saved"
    assert readiness["work_item_status"] == "running"
    assert readiness["work_item_recoverable"] is True
    assert readiness["recovery_mode"] == "resume_from_checkpoint"
    assert readiness["can_resume"] is True
    assert readiness["should_retry"] is False
    assert readiness["resume_config"]["configurable"] == {
        "thread_id": "run-resume-ready",
        "checkpoint_ns": "execution-memory",
        "checkpoint_id": "checkpoint-secret",
    }
    assert readiness["next_actions"] == ["resume_langgraph_thread", "monitor_progress"]
    assert "SECRET STATE" not in str(readiness)
    assert "worker-secret" not in str(readiness)
    assert "raw checkpoint channel values" in readiness["boundary"]


def test_execution_resume_readiness_reports_metadata_retry_and_thread_mismatch() -> None:
    from open_coscientist.checkpointing import execution_resume_readiness

    metadata_retry = execution_resume_readiness(
        run_id="run-metadata-retry",
        execution_memory={
            "status": "limited",
            "checkpoint_backend": "sqlite_metadata",
            "resume_supported": False,
        },
        checkpoint_metadata={
            "thread_id": "run-metadata-retry",
            "checkpoint_id": "checkpoint-metadata",
            "phase": "ranking",
            "status": "saved",
        },
        work_item={"status": "retrying"},
    )

    assert metadata_retry["status"] == "metadata_guided_retry"
    assert metadata_retry["recovery_mode"] == "metadata_guided_retry"
    assert metadata_retry["can_resume"] is False
    assert metadata_retry["should_retry"] is True
    assert metadata_retry["resume_config"]["configurable"] == {
        "thread_id": "run-metadata-retry",
        "checkpoint_id": "checkpoint-metadata",
    }
    assert metadata_retry["next_actions"] == ["retry_work_item", "monitor_progress"]

    mismatch = execution_resume_readiness(
        run_id="run-a",
        execution_memory={"status": "ready", "resume_supported": True},
        checkpoint_metadata={"thread_id": "run-b", "checkpoint_id": "checkpoint-secret"},
        work_item={"status": "running"},
    )

    assert mismatch["status"] == "needs_attention"
    assert mismatch["thread_id_matches_run_id"] is False
    assert mismatch["recovery_mode"] == "checkpoint_thread_mismatch"
    assert mismatch["can_resume"] is False
    assert mismatch["should_retry"] is False
    assert mismatch["resume_config"]["configurable"] == {"thread_id": "run-a"}
    assert mismatch["next_actions"] == ["inspect_checkpoint_thread_mismatch", "start_new_run_or_requeue"]


def test_build_checkpoint_metadata_record_hides_raw_workflow_state() -> None:
    from open_coscientist.checkpointing import build_checkpoint_metadata_record

    record = build_checkpoint_metadata_record(
        run_id=" run-checkpoint-metadata ",
        phase=" review ",
        status=" saved ",
        checkpoint_ref="checkpoint-ref-secret",
        state_summary={
            "research_goal": "SECRET RESEARCH GOAL should not be persisted in metadata summary.",
            "hypotheses": [
                {"text": "SECRET HYPOTHESIS TEXT"},
                {"text": "Another hidden hypothesis"},
            ],
            "messages": [{"content": "SECRET MESSAGE"}],
            "tournament_matchups": [{"winner": "hidden"}],
            "evolution_details": [{"lineage": "hidden"}],
            "memory_context": {"raw": "SECRET MEMORY"},
            "starting_hypotheses": ["SECRET USER SEED"],
            "current_iteration": 2,
            "progress_callback": lambda *_args: None,
            "tool_registry": object(),
        },
        checkpoint_tuple_summary={
            "checkpoint_id": " checkpoint-secret ",
            "checkpoint_ns": " execution-memory ",
            "parent_checkpoint_id": "parent-checkpoint-secret",
            "checkpoint_ts": "2026-07-02T00:00:00Z",
            "channel_keys": ["hypotheses", "messages", "research_goal"],
            "pending_writes_count": 3,
        },
    )

    assert record["run_id"] == "run-checkpoint-metadata"
    assert record["thread_id"] == "run-checkpoint-metadata"
    assert record["thread_id_matches_run_id"] is True
    assert record["phase"] == "review"
    assert record["status"] == "saved"
    assert record["checkpoint_id"] == "checkpoint-secret"
    assert record["checkpoint_ns"] == "execution-memory"
    assert record["checkpoint_backend"] == "langgraph_sqlite"
    assert record["resume_config"]["configurable"] == {
        "thread_id": "run-checkpoint-metadata",
        "checkpoint_ns": "execution-memory",
        "checkpoint_id": "checkpoint-secret",
    }
    assert record["checkpoint_tuple"]["parent_checkpoint_id"] == "parent-checkpoint-secret"
    assert record["checkpoint_tuple"]["channel_keys"] == ["hypotheses", "messages", "research_goal"]
    assert record["checkpoint_tuple"]["pending_writes_count"] == 3
    assert record["state_summary"]["hypothesis_count"] == 2
    assert record["state_summary"]["message_count"] == 1
    assert record["state_summary"]["tournament_matchup_count"] == 1
    assert record["state_summary"]["evolution_detail_count"] == 1
    assert record["state_summary"]["current_iteration"] == 2
    assert record["state_summary"]["has_memory_context"] is True
    assert record["state_summary"]["has_starting_hypotheses"] is True
    assert record["state_summary"]["omitted_runtime_only_keys"] == [
        "progress_callback",
        "tool_registry",
    ]
    assert "SECRET" not in str(record["state_summary"])
    assert "SECRET" not in record["visibility_boundary"]


def test_build_checkpoint_metadata_record_enforces_thread_id_run_id_contract() -> None:
    from open_coscientist.checkpointing import build_checkpoint_metadata_record

    with pytest.raises(ValueError, match="thread_id to match run_id"):
        build_checkpoint_metadata_record(
            run_id="run-a",
            thread_id="run-b",
        )

    with pytest.raises(ValueError, match="run_id is required"):
        build_checkpoint_metadata_record(run_id="   ")


def test_sanitize_workflow_state_removes_runtime_only_values() -> None:
    from open_coscientist.checkpointing import sanitize_workflow_state_for_checkpoint

    state = {
        "run_id": "run-123",
        "research_goal": "Find a recoverable execution memory design",
        "progress_callback": lambda *_args: None,
        "tool_registry": object(),
        "metrics": ExecutionMetrics(hypothesis_count=1),
        "hypotheses": [Hypothesis(text="Serializable hypothesis")],
    }

    sanitized, metadata = sanitize_workflow_state_for_checkpoint(state)
    assert sanitized["run_id"] == "run-123"
    assert "progress_callback" not in sanitized
    assert "tool_registry" not in sanitized
    assert metadata["omitted_keys"] == {
        "progress_callback": "runtime_only",
        "tool_registry": "runtime_only",
    }


def test_sanitized_checkpoint_state_is_jsonplus_serializable() -> None:
    from open_coscientist.checkpointing import (
        checkpoint_state_serializability,
        sanitize_workflow_state_for_checkpoint,
    )

    raw_state = {
        "run_id": "run-serializable",
        "metrics": ExecutionMetrics(hypothesis_count=1),
        "hypotheses": [Hypothesis(text="Checkpoint serialization test")],
        "progress_callback": lambda *_args: None,
    }
    sanitized, metadata = sanitize_workflow_state_for_checkpoint(raw_state)
    serializability = checkpoint_state_serializability(sanitized)
    assert metadata["omitted_keys"]["progress_callback"] == "runtime_only"
    assert serializability["serializable"] is True


def test_unsanitized_runtime_callback_is_not_serializable() -> None:
    from open_coscientist.checkpointing import checkpoint_state_serializability

    serializability = checkpoint_state_serializability({"progress_callback": lambda *_args: None})
    assert serializability["serializable"] is False


def test_open_sqlite_checkpointer_creates_async_saver() -> None:
    from open_coscientist.checkpointing import open_sqlite_checkpointer

    async def run_probe(db_path: Path) -> None:
        async with open_sqlite_checkpointer(db_path) as saver:
            assert hasattr(saver, "aput")
            assert hasattr(saver, "aget_tuple")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "checkpoints.sqlite"
        asyncio.run(run_probe(db_path))
        assert db_path.exists()


def test_langgraph_checkpoint_summary_hides_raw_channel_values() -> None:
    from langgraph.graph import END, START, StateGraph

    from open_coscientist.checkpointing import (
        open_sqlite_checkpointer,
        summarize_langgraph_checkpoint_tuple,
    )

    class ProbeState(TypedDict):
        value: str

    def add_suffix(state: ProbeState) -> ProbeState:
        return {"value": f"{state['value']}-complete"}

    async def run_probe(db_path: Path) -> None:
        async with open_sqlite_checkpointer(db_path) as saver:
            workflow = StateGraph(ProbeState)
            workflow.add_node("add_suffix", add_suffix)
            workflow.add_edge(START, "add_suffix")
            workflow.add_edge("add_suffix", END)
            graph = workflow.compile(checkpointer=saver)

            await graph.ainvoke(
                {"value": "raw-secret-state"},
                config={"configurable": {"thread_id": "run-checkpoint-summary"}},
            )

            checkpoint_tuple = None
            async for candidate in saver.alist(
                {"configurable": {"thread_id": "run-checkpoint-summary"}}
            ):
                checkpoint_tuple = candidate
                break

            assert checkpoint_tuple is not None
            summary = summarize_langgraph_checkpoint_tuple(checkpoint_tuple)
            assert summary["thread_id"] == "run-checkpoint-summary"
            assert summary["checkpoint_id"]
            assert summary["metadata"]["step"] is not None
            assert "value" in summary["channel_keys"]
            assert "channel_values" not in summary
            assert "raw-secret-state" not in repr(summary)
            assert "raw channel values are not exposed" in summary["boundary"]

    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(run_probe(Path(tmp) / "checkpoints.sqlite"))
