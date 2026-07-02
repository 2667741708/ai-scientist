from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path


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
    assert "progress_callback" in status["runtime_only_state_keys"]
    assert "tool_registry" in status["runtime_only_state_keys"]
    if status["langgraph_checkpoint_sqlite_available"]:
        assert status["status"] == "ready"
    else:
        assert status["status"] == "limited"
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
