from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import TypedDict


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from open_coscientist.models import ExecutionMetrics, Hypothesis


def test_execution_memory_status_reports_sqlite_saver_boundary() -> None:
    from open_coscientist.checkpointing import execution_memory_status

    status = execution_memory_status()
    assert status["thread_id_required"] is True
    assert status["thread_id_source"] == "run_id"
    assert status["checkpoint_backend"] in {"sqlite_metadata", "langgraph_sqlite"}
    assert status["checkpointer_package"] == "langgraph-checkpoint-sqlite"
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
