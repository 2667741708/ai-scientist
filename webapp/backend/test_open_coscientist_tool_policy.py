from __future__ import annotations

import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from open_coscientist import HypothesisGenerator
from open_coscientist.config import ToolRegistry


def test_open_coscientist_workflow_policy_filters_yaml_tools() -> None:
    baseline = ToolRegistry(skip_user_config=True)
    baseline_tools = baseline.get_tools_for_workflow("literature_review")
    assert baseline_tools

    denied_tool = baseline_tools[0]
    registry = ToolRegistry(
        skip_user_config=True,
        workflow_tool_policy={
            "literature_review": {
                "denied_tools": [denied_tool],
            }
        },
    )

    filtered_tools = registry.get_tools_for_workflow("literature_review")
    assert denied_tool not in filtered_tools
    assert len(filtered_tools) == len(baseline_tools) - 1
    audit = registry.audit_workflow_tool_policy()
    assert denied_tool not in audit["workflows"]["literature_review"]["enabled_tools_after_policy"]


def test_hypothesis_generator_accepts_workflow_tool_policy() -> None:
    generator = HypothesisGenerator(
        model_name="test/model",
        initial_hypotheses_count=1,
        max_iterations=0,
        workflow_tool_policy={
            "literature_review": {
                "allowed_categories": ["search", "search_with_content"],
            }
        },
    )

    policy = generator._tool_registry.get_workflow_tool_policy()
    assert policy["literature_review"]["allowed_categories"] == ["search", "search_with_content"]


def test_tool_registry_supports_disabled_stdio_ssh_mcp_templates() -> None:
    os.environ.pop("COSCIENTIST_SSH_MCP_C201_5080_ENABLED", None)
    baseline = ToolRegistry(skip_user_config=True)
    server = baseline.get_server("ssh_c201_5080")
    assert server
    assert server.transport == "stdio"
    assert server.command == "ssh"
    assert server.args == ["c201-5080", "coscientist-ssh-mcp"]
    assert server.enabled is False
    assert "ssh_c201_5080" not in baseline.get_server_configs_for_langchain()

    os.environ["COSCIENTIST_SSH_MCP_C201_5080_ENABLED"] = "true"
    try:
        enabled = ToolRegistry(skip_user_config=True)
        configs = enabled.get_server_configs_for_langchain()
        assert configs["ssh_c201_5080"]["transport"] == "stdio"
        assert configs["ssh_c201_5080"]["command"] == "ssh"
        assert configs["ssh_c201_5080"]["args"] == ["c201-5080", "coscientist-ssh-mcp"]
    finally:
        os.environ.pop("COSCIENTIST_SSH_MCP_C201_5080_ENABLED", None)


if __name__ == "__main__":
    test_open_coscientist_workflow_policy_filters_yaml_tools()
    test_hypothesis_generator_accepts_workflow_tool_policy()
    test_tool_registry_supports_disabled_stdio_ssh_mcp_templates()
    print("open-coscientist workflow tool policy tests passed")
