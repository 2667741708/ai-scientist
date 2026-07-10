from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from open_coscientist.mcp_client import (
    MCPToolClient,
    reset_mcp_tool_call_observer,
    set_mcp_tool_call_observer,
)


class FakeTool:
    async def ainvoke(self, kwargs):
        return {"ok": True, "kwargs": kwargs}


def test_mcp_client_call_tool_emits_context_observer_event() -> None:
    events = []
    token = set_mcp_tool_call_observer(events.append)
    try:
        client = MCPToolClient(server_configs={"fake": {"transport": "streamable_http", "url": "http://fake/mcp"}})
        client._tools_dict = {"fake_search": FakeTool()}
        client._tool_to_server = {"fake_search": "fake"}

        result = asyncio.run(client.call_tool("fake_search", query="observer test"))
        assert result["ok"] is True
        assert events
        event = events[0]
        assert event["tool_name"] == "fake_search"
        assert event["arguments"] == {"query": "observer test"}
        assert event["status"] == "complete"
        assert event["server"] == "fake"
        assert event["call_path"] == "call_tool"
    finally:
        reset_mcp_tool_call_observer(token)


if __name__ == "__main__":
    test_mcp_client_call_tool_emits_context_observer_event()
    print("MCP client observer tests passed")
