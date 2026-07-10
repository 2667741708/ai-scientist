from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


class FakeMcpClient:
    async def call_tool(self, tool_name: str, **kwargs):
        return {
            "tool_name": tool_name,
            "arguments": kwargs,
            "results": [
                {
                    "title": "Policy-gated MCP result",
                    "abstract": "A fake scholarly result for workflow testing.",
                }
            ],
        }


def test_mcp_tool_workflow_requires_policy_approval_and_persists_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
        sys.modules.pop("app", None)
        studio = importlib.import_module("app")

        async def fake_get_mcp_client(_tool_registry):
            return FakeMcpClient()

        studio.get_policy_limited_mcp_client = fake_get_mcp_client
        record = studio.RunRecord(
            run_id="run_mcp_tool",
            status="complete",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(research_goal="Validate MCP network workflow provenance"),
        )
        studio.persist_run_record(record)
        client = TestClient(studio.app)

        no_approval = client.post(
            "/api/tools/workflows/mcp-call",
            json={
                "workflow_name": "literature_review",
                "tool_id": "arxiv_search",
                "phase": "literature_review",
                "run_id": "run_mcp_tool",
                "arguments": {"query": "weak supervision", "max_results": 2},
            },
        )
        assert no_approval.status_code == 428

        approved = client.post(
            "/api/tools/workflows/mcp-call",
            json={
                "workflow_name": "literature_review",
                "tool_id": "arxiv_search",
                "phase": "literature_review",
                "run_id": "run_mcp_tool",
                "arguments": {"query": "weak supervision", "max_results": 2},
                "approval": {
                    "confirmed": True,
                    "scope": "mcp.literature_review",
                    "reason": "test network workflow",
                },
            },
        )
        assert approved.status_code == 200, approved.text
        payload = approved.json()
        assert payload["mcp_tool_name"] == "search_arxiv"
        assert payload["result_ref"]["result_id"]

        denied = client.post(
            "/api/tools/workflows/mcp-call",
            json={
                "workflow_name": "literature_review",
                "mcp_tool_name": "query_drug_info",
                "phase": "literature_review",
                "run_id": "run_mcp_tool",
                "arguments": {"drug": "aspirin"},
                "approval": {
                    "confirmed": True,
                    "scope": "mcp.literature_review",
                },
            },
        )
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == "mcp_tool_not_allowed_by_workflow_policy"

        tool_calls = client.get("/api/runs/run_mcp_tool/tool-calls")
        assert tool_calls.status_code == 200
        assert any(item["tool_name"] == "mcp.search_arxiv" for item in tool_calls.json()["tool_calls"])

        retrievals = client.get("/api/runs/run_mcp_tool/evidence-retrievals")
        assert retrievals.status_code == 200
        assert any(item["tool_name"] == "mcp.search_arxiv" for item in retrievals.json()["retrievals"])

        loaded_result = client.get(f"/api/tools/results/{payload['result_ref']['result_id']}")
        assert loaded_result.status_code == 200
        assert loaded_result.json()["content"]["tool_name"] == "search_arxiv"


def test_mcp_observer_persists_internal_tool_call_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
        sys.modules.pop("app", None)
        studio = importlib.import_module("app")
        record = studio.RunRecord(
            run_id="run_mcp_observer",
            status="complete",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(research_goal="Validate MCP observer persistence"),
        )
        studio.persist_run_record(record)

        observer = studio.build_mcp_tool_observer("run_mcp_observer")
        observer(
            {
                "tool_name": "search_arxiv",
                "arguments": {"query": "observer provenance"},
                "status": "complete",
                "result": {"results": [{"title": "Observed MCP result"}]},
                "duration_seconds": 0.01,
                "call_path": "call_tool",
            }
        )

        tool_calls = studio.knowledge_base.get_research_tool_calls("run_mcp_observer")
        assert tool_calls
        assert tool_calls[0]["tool_name"] == "mcp.search_arxiv"
        result_ref = tool_calls[0]["metadata"]["result_ref"]
        assert result_ref["result_id"]
        stored = studio.knowledge_base.get_tool_result(result_ref["result_id"])
        assert stored
        assert stored["content"]["results"][0]["title"] == "Observed MCP result"


if __name__ == "__main__":
    test_mcp_tool_workflow_requires_policy_approval_and_persists_result()
    test_mcp_observer_persists_internal_tool_call_event()
    print("MCP tool workflow API tests passed")
