from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from open_coscientist import llm
from open_coscientist.schema_sanitizer import sanitize_response_schema, sanitize_tools_for_model


def test_schema_sanitizer_removes_provider_fragile_keywords() -> None:
    schema = {
        "name": "bad schema name!",
        "strict": False,
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "title": "Fragile",
            "properties": {
                "status": {"const": "ok", "default": "ok"},
                "note": {
                    "anyOf": [
                        {"type": "string", "format": "date-time"},
                        {"type": "null"},
                    ]
                },
            },
            "required": ["status", "missing"],
        },
    }

    sanitized = sanitize_response_schema(schema, model_name="qwen/qwen-plus")
    body = sanitized["schema"]
    assert sanitized["name"] == "bad_schema_name"
    assert "$schema" not in body
    assert "title" not in body
    assert body["properties"]["status"] == {"enum": ["ok"]}
    assert body["properties"]["note"]["type"] == "string"
    assert "format" not in body["properties"]["note"]
    assert body["required"] == ["status"]
    assert body["additionalProperties"] is False


def test_tool_schema_sanitizer_cleans_function_names_and_parameters() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "123 bad tool",
                "description": "x" * 1200,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "examples": ["weak supervision"]},
                    },
                    "required": ["query", "missing"],
                },
            },
        }
    ]

    sanitized = sanitize_tools_for_model(tools, model_name="anthropic/claude-sonnet")
    function = sanitized[0]["function"]
    assert function["name"] == "schema_123_bad_tool"
    assert len(function["description"]) == 1024
    assert "examples" not in function["parameters"]["properties"]["query"]
    assert function["parameters"]["required"] == ["query"]
    assert function["parameters"]["additionalProperties"] is False


def test_call_llm_sends_sanitized_response_format(monkeypatch) -> None:
    captured = {}

    class FakeMessage:
        content = '{"ok": true}'

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    prompt = f"return json {uuid.uuid4().hex}"
    response = asyncio.run(
        llm.call_llm(
            prompt,
            model_name="openai/gpt-4o-mini",
            json_schema={
                "name": "test schema",
                "schema": {
                    "type": "object",
                    "title": "Fragile",
                    "properties": {"ok": {"type": "boolean", "default": True}},
                    "required": ["ok"],
                },
            },
        )
    )

    assert response == '{"ok": true}'
    sent_schema = captured["response_format"]["json_schema"]
    assert sent_schema["name"] == "test_schema"
    assert "title" not in sent_schema["schema"]
    assert "default" not in sent_schema["schema"]["properties"]["ok"]


if __name__ == "__main__":
    test_schema_sanitizer_removes_provider_fragile_keywords()
    test_tool_schema_sanitizer_cleans_function_names_and_parameters()
    print("schema sanitizer tests passed")
