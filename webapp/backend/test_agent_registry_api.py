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


def test_agent_trace_entries_include_registry_metadata(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        demo_trace = studio.demo_agent_trace("Audit trace metadata")
        by_phase = {trace.phase: trace for trace in demo_trace}
        assert by_phase["supervisor"].agent_id == "supervisor_agent"
        assert by_phase["supervisor"].prompt_template == "prompts/supervisor.md"
        assert by_phase["literature"].agent_id == "literature_grounding_agent"
        assert by_phase["rank"].agent_id == "ranking_agent"

        record = studio.RunRecord(
            run_id="run_trace_registry",
            status="complete",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(
                research_goal="Verify live trace registry metadata",
                demo_mode=False,
                literature_review=False,
            ),
        )
        live_trace = studio.build_live_agent_trace(
            record,
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Reviewed candidate soundness and safety.",
                        "metadata": {"phase": "review"},
                    }
                ]
            },
        )

        by_live_phase = {trace.phase: trace for trace in live_trace}
        assert by_live_phase["review"].agent_id == "hypothesis_review_agent"
        assert by_live_phase["review"].prompt_template == "prompts/review.md"
        assert by_live_phase["review"].synthetic is False
        assert by_live_phase["literature_review"].agent_id == "literature_grounding_agent"
        assert by_live_phase["literature_review"].degradation_reason == "literature_review_disabled_latent_knowledge_boundary"
        assert "not evidence" in by_live_phase["literature_review"].output
