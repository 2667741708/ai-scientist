from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_draft_generation_reads_workflow_starting_hypotheses(monkeypatch) -> None:
    from open_coscientist.nodes.generation.literature_tools import draft

    captured: dict[str, object] = {}

    class FakeToolRegistry:
        def get_tools_for_workflow(self, workflow_name: str):
            assert workflow_name == "draft_generation"
            return []

        def get_mcp_tool_names(self, tool_ids):
            assert tool_ids == []
            return []

    class FakeProvider:
        def __init__(self, **_kwargs):
            pass

        def get_tools(self, **_kwargs):
            return {}, []

        async def execute_tool_call(self, _tool_call):
            raise AssertionError("No tool calls are expected in this unit test")

    def fake_prompt_builder(**kwargs):
        captured["user_hypotheses"] = kwargs["user_hypotheses"]
        captured["preferences"] = kwargs["preferences"]
        captured["attributes"] = kwargs["attributes"]
        return "draft prompt", {}

    async def fake_llm_with_tools(**_kwargs):
        return (
            '{"drafts":[{"hypothesis":"Draft preserves user seed.","gap_reasoning":"test","literature_sources":[]}]}',
            [],
        )

    monkeypatch.setattr(draft, "HybridToolProvider", FakeProvider)
    monkeypatch.setattr(draft, "get_draft_prompt_with_tools", fake_prompt_builder)
    monkeypatch.setattr(draft, "call_llm_with_tools", fake_llm_with_tools)
    monkeypatch.setattr("open_coscientist.prompts.save_prompt_to_disk", lambda **_kwargs: True)

    state = {
        "run_id": "run-draft-starting-hypotheses",
        "research_goal": "Use user hypotheses in tool-based draft generation",
        "model_name": "test-model",
        "supervisor_guidance": {},
        "articles_with_reasoning": None,
        "preferences": "Prefer falsifiable candidates.",
        "attributes": ["grounded", "testable"],
        "starting_hypotheses": ["User seed hypothesis should enter draft generation."],
        "articles": [],
    }

    drafts = asyncio.run(
        draft.draft_hypotheses(
            state,
            count=1,
            mcp_client=object(),
            tool_registry=FakeToolRegistry(),
        )
    )

    assert drafts[0]["hypothesis"] == "Draft preserves user seed."
    assert captured["user_hypotheses"] == [
        "User seed hypothesis should enter draft generation."
    ]
    assert captured["preferences"] == "Prefer falsifiable candidates."
    assert captured["attributes"] == ["grounded", "testable"]
