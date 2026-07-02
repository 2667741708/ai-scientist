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
