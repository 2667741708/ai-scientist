from __future__ import annotations

import tempfile
from pathlib import Path

from knowledge_base import KnowledgeBaseStore
from research_tools import (
    authorize_tool_for_phase,
    build_default_research_tool_registry,
    canonical_phase,
    get_phase_tool_policy,
)


def test_research_tool_registry_groups_and_filters_tools() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        registry = build_default_research_tool_registry(
            store,
            mcp_probe=lambda: {
                "available": False,
                "mode": "unreachable",
                "reason": "test MCP offline",
                "checked_at": 1.0,
            },
            ssh_training_probe=lambda: {
                "available": True,
                "mode": "test_ready",
                "reason": "test SSH configured",
                "checked_at": 1.0,
            },
        )

        names = registry.names()
        assert "knowledge_base.rag_search" in names
        assert "provenance.record_run" in names
        assert "mcp.literature_review" in names
        assert "ssh.training_command" in names
        assert "web.search_public" in names
        assert "terminal.command" in names

        literature_tools = registry.list_tools(phase="literature_review")
        literature_names = {tool["name"] for tool in literature_tools}
        assert "knowledge_base.rag_search" in literature_names
        assert "pdf.parse_to_knowledge_base" in literature_names
        assert "mcp.literature_review" in literature_names
        assert "web.search_public" in literature_names

        kb_tools = registry.list_tools(toolset="knowledge_base")
        assert {tool["toolset"] for tool in kb_tools} == {"knowledge_base"}
        assert kb_tools[0]["availability"]["available"] is True
        assert kb_tools[0]["availability"]["mode"] == "ready_empty"

        web_search = registry.get("web.search_public")
        assert web_search
        assert isinstance(web_search.describe()["availability"]["available"], bool)
        assert authorize_tool_for_phase(web_search, "literature_review")["allowed"] is True

        terminal_command = registry.get("terminal.command")
        assert terminal_command
        assert terminal_command.describe()["availability"]["mode"] == "permission_gated"
        terminal_authorization = authorize_tool_for_phase(terminal_command, "terminal")
        assert terminal_authorization["allowed"] is True

        toolsets = registry.list_toolsets()
        assert any(item["toolset"] == "provenance" for item in toolsets)
        assert any(item["toolset"] == "knowledge_base" for item in toolsets)
        assert any(item["toolset"] == "ssh_training" for item in toolsets)
        assert any(item["toolset"] == "web_search" for item in toolsets)
        assert any(item["toolset"] == "terminal" for item in toolsets)

        phase_payload = registry.list_phase_tools("review_critique")
        assert phase_payload["count"] >= 1
        assert "knowledge_base" in phase_payload["toolsets"]

        assert canonical_phase("review") == "review_critique"
        policy = get_phase_tool_policy("review")
        assert policy
        assert "knowledge_base" in policy.allowed_toolsets

        spec = registry.get("knowledge_base.rag_search")
        assert spec
        authorization = authorize_tool_for_phase(spec, "literature")
        assert authorization["allowed"] is True
        denied = authorize_tool_for_phase(spec, "experiment_execution")
        assert denied["allowed"] is False
        assert denied["code"] in {"tool_phase_not_allowed", "toolset_not_allowed_for_phase"}


if __name__ == "__main__":
    test_research_tool_registry_groups_and_filters_tools()
    print("research tool registry tests passed")
