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
        from open_coscientist.agents import get_agent_registry_payload, get_phase_status_payload

        payload = get_agent_registry_payload(public=True)
        assert payload["registry_version"] == "paper_level_v1"
        assert payload["count"] == 9
        assert set(payload["phases"]) == EXPECTED_PHASES
        assert payload["phase_order"] == [
            "supervisor",
            "literature_review",
            "generate",
            "reflection",
            "review",
            "ranking",
            "meta_review",
            "evolve",
            "proximity",
        ]
        assert payload["phase_labels"]["ranking"] == "Tournament ranking"
        assert "literature_review" in payload["configurable_phases"]
        assert "review" in payload["required_phases"]
        assert set(payload["phase_index"]) == EXPECTED_PHASES
        assert payload["phase_index"]["review"]["agent_id"] == "hypothesis_review_agent"
        assert payload["phase_index"]["review"]["prompt_template"] == "prompts/review.md"
        assert "tool_calls" in payload["observability_contract"]
        assert "degradation_reason" in payload["observability_contract"]

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

        status_payload = get_phase_status_payload(disabled_phases=["literature_review", "supervisor"])
        statuses = {item["phase"]: item for item in status_payload["phase_statuses"]}
        assert statuses["literature_review"]["enabled"] is False
        assert "latent_knowledge" in statuses["literature_review"]["degradation_reason"]
        assert statuses["supervisor"]["enabled"] is True
        assert statuses["supervisor"]["degradation_reason"] is None
        assert status_payload["degradation_count"] == 1
        assert status_payload["degraded_phases"][0]["phase"] == "literature_review"
        assert status_payload["invalid_disabled_phases"] == [
            {
                "phase": "supervisor",
                "label": "Research planning",
                "reason": "required_phase_cannot_be_disabled",
            }
        ]
        assert "required phases remain enabled" in status_payload["boundary"]


def test_agent_registry_endpoint_returns_auditable_payload(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir, TestClient(studio.app) as client:
        response = client.get("/api/agents/registry")
        assert response.status_code == 200, response.text

        payload = response.json()
        assert payload["count"] == 9
        assert set(payload["phases"]) == EXPECTED_PHASES
        assert payload["phase_order"][0] == "supervisor"
        assert payload["phase_labels"]["literature_review"] == "Literature grounding"
        assert "proximity" in payload["configurable_phases"]
        assert "supervisor" in payload["required_phases"]
        assert payload["phase_index"]["ranking"]["agent_id"] == "ranking_agent"
        assert payload["phase_index"]["ranking"]["prompt_template"] == "prompts/ranking.md"
        assert payload["phase_index"]["literature_review"]["configurable"] is True
        assert "latent_knowledge" in payload["phase_index"]["literature_review"]["degradation_when_disabled"]

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


def test_agent_trace_endpoint_returns_stable_phase_summary(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir, TestClient(studio.app) as client:
        record = studio.RunRecord(
            run_id="run-trace-summary",
            status="complete",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(
                research_goal="Verify agent trace endpoint summary",
                demo_mode=False,
                literature_review=False,
            ),
            agent_trace=[
                studio.agent_trace_from_registry(
                    agent="Ranking",
                    event_id="trace-ranking",
                    phase="rank",
                    output="Ranked hypotheses.",
                    confidence=1.0,
                ),
                studio.agent_trace_from_registry(
                    agent="Review",
                    event_id="trace-review",
                    phase="review",
                    output="Reviewed hypotheses.",
                    confidence=1.0,
                ),
                studio.agent_trace_from_registry(
                    agent="Literature",
                    event_id="trace-literature",
                    phase="literature_review",
                    output="Literature review disabled.",
                    confidence=1.0,
                    degradation_reason="literature_review_disabled_latent_knowledge_boundary",
                ),
            ],
        )
        studio.persist_run_record(record)

        response = client.get("/api/runs/run-trace-summary/trace")

        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload["agent_trace"]) == 3
        summary = payload["summary"]
        assert summary["trace_count"] == 3
        assert summary["phase_order"] == ["literature_review", "review", "ranking"]
        assert summary["phase_labels"][0] == {"phase": "literature_review", "label": "Literature grounding"}
        assert summary["degradation_count"] == 1
        assert summary["degraded_phases"][0]["phase"] == "literature_review"
        assert summary["degraded_phases"][0]["label"] == "Literature grounding"
        assert "raw provider payloads" in summary["boundary"]
