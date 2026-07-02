from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_generation_coordinator_returns_phase_message(monkeypatch) -> None:
    from open_coscientist.models import Hypothesis
    from open_coscientist.nodes.generation import coordinator

    async def fake_execute_generation_tasks(*_args, **_kwargs):
        return coordinator.GenerationResults(
            tools_hypotheses=[],
            debate_with_lit_hypotheses=[],
            debate_only_hypotheses=[Hypothesis(text="A falsifiable generated hypothesis.")],
            debate_transcripts=[],
        )

    async def skip_enrichment(*_args, **_kwargs):
        return None

    monkeypatch.setattr(coordinator, "_execute_generation_tasks", fake_execute_generation_tasks)
    monkeypatch.setattr(coordinator, "_enrich_hypotheses", skip_enrichment)

    result = asyncio.run(
        coordinator.generate_hypotheses(
            {
                "supervisor_guidance": {"workflow_plan": {"strategy": "test"}},
                "initial_hypotheses_count": 1,
                "mcp_available": False,
                "articles_with_reasoning": None,
                "enable_tool_calling_generation": False,
            }
        )
    )

    assert result["hypothesis_count"] == 1
    assert result["messages"][0]["content"].startswith("Generated 1 hypotheses")

    metadata = result["messages"][0]["metadata"]
    assert metadata["phase"] == "generate"
    assert metadata["hypotheses_count"] == 1
    assert metadata["debate_only_count"] == 1
    assert metadata["degraded_mode"] is True
