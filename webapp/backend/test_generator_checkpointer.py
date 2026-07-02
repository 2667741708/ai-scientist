from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_generator_prepare_generation_accepts_checkpointer() -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    from open_coscientist.generator import HypothesisGenerator

    async def prepare_with_checkpointer():
        generator = HypothesisGenerator(max_iterations=0, initial_hypotheses_count=1)
        state, _start_time, run_id = await generator._prepare_generation(
            "Find recoverable LangGraph checkpoint semantics",
            progress_callback=lambda *_args: None,
            opts={"enable_literature_review_node": False, "checkpointer": InMemorySaver()},
            run_id="run-checkpointer-test",
        )
        return generator, state, run_id

    generator, state, run_id = asyncio.run(prepare_with_checkpointer())
    assert run_id == "run-checkpointer-test"
    assert state["run_id"] == "run-checkpointer-test"
    assert state["progress_callback"] is None
    assert state["tool_registry"] is None
    assert generator._graph is not None
    assert generator._graph_checkpointer_enabled is True


def test_generator_rebuilds_graph_when_checkpoint_mode_changes() -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    from open_coscientist.generator import HypothesisGenerator

    async def prepare_twice():
        generator = HypothesisGenerator(max_iterations=0, initial_hypotheses_count=1)
        await generator._prepare_generation(
            "Find recoverable LangGraph checkpoint semantics",
            opts={"enable_literature_review_node": False, "checkpointer": InMemorySaver()},
            run_id="run-checkpointer-on",
        )
        graph_with_checkpointer = generator._graph
        await generator._prepare_generation(
            "Find recoverable LangGraph checkpoint semantics",
            opts={"enable_literature_review_node": False},
            run_id="run-checkpointer-off",
        )
        return generator, graph_with_checkpointer

    generator, graph_with_checkpointer = asyncio.run(prepare_twice())
    assert generator._graph is not graph_with_checkpointer
    assert generator._graph_checkpointer_enabled is False
