from __future__ import annotations

import importlib
import sys
import tempfile

from fastapi.testclient import TestClient


EXPECTED_PHASES = {
    "supervisor",
    "literature_review",
    "generate",
    "reflection",
    "review",
    "ranking",
    "meta_review",
    "evolve",
    "proximity",
}


def load_studio_app(monkeypatch, knowledge_base_dir: str):
    monkeypatch.setenv("COSCIENTIST_KNOWLEDGE_BASE_DIR", knowledge_base_dir)
    monkeypatch.setenv("COSCIENTIST_WORKER_ENABLED", "0")
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_agent_registry_module_describes_specialized_agents(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        from open_coscientist.agents import get_agent_registry_payload

        payload = get_agent_registry_payload(public=True)
        assert payload["registry_version"] == "paper_level_v1"
        assert payload["count"] == 9
        assert set(payload["phases"]) == EXPECTED_PHASES

        agents = {agent["agent_id"]: agent for agent in payload["agents"]}
        supervisor = agents["supervisor_agent"]
        assert supervisor["phase"] == "supervisor"
        assert "research_goal" in supervisor["input_contract"]["required"]
        assert "prompt_template" in supervisor
        assert "observability_fields" in supervisor
        assert "tool_calls" in supervisor["observability_fields"]

        literature = agents["literature_grounding_agent"]
        assert literature["configurable"] is True
        assert literature["tool_policy"]["direct_tool_calls"] is True
        assert "latent_knowledge" in literature["degradation_when_disabled"]


def test_agent_registry_endpoint_returns_auditable_payload(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir, TestClient(studio.app) as client:
        response = client.get("/api/agents/registry")
        assert response.status_code == 200, response.text

        payload = response.json()
        assert payload["count"] == 9
        assert set(payload["phases"]) == EXPECTED_PHASES

        agents = {agent["agent_id"]: agent for agent in payload["agents"]}
        review = agents["hypothesis_review_agent"]
        assert review["phase"] == "review"
        assert "safety" in review["role"].lower()
        assert review["failure_policy"]["fallback"] == "fail_run"
        assert review["prompt_template"] == "prompts/review.md"
