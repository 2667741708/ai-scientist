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
        assert len(payload["phase_statuses"]) == 9
        assert payload["degraded_phases"] == []
        assert payload["degradation_count"] == 0
        assert payload["invalid_disabled_phases"] == []
        assert payload["phase_statuses"][0] == {
            "phase": "supervisor",
            "label": "Research planning",
            "agent_id": "supervisor_agent",
            "enabled": True,
            "configurable": False,
            "degradation_reason": None,
        }
        assert "required phases remain enabled" in payload["phase_status_boundary"]
        assert "tool_calls" in payload["observability_contract"]
        assert "degradation_reason" in payload["observability_contract"]
        registry_audit = payload["registry_contract_audit"]
        assert registry_audit["status"] == "ready"
        assert registry_audit["expected_phase_count"] == 9
        assert registry_audit["counts"] == {
            "agents": 9,
            "missing_fields": 0,
            "contract_gaps": 0,
            "missing_observability": 0,
            "duplicate_agent_ids": 0,
            "duplicate_phases": 0,
            "missing_phases": 0,
            "extra_phases": 0,
        }
        assert registry_audit["items"][0]["agent_id"] == "supervisor_agent"
        assert registry_audit["items"][0]["contract_gaps"] == []
        assert registry_audit["items"][0]["missing_observability_fields"] == []
        assert "raw prompts" in registry_audit["boundary"]

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


def test_agent_registry_contract_audit_flags_incomplete_specs(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        from open_coscientist.agents.registry import agent_registry_contract_audit, list_agent_specs

        specs = list_agent_specs(public=True)
        broken = dict(specs[0])
        broken["agent_id"] = "broken_agent"
        broken["phase"] = "supervisor"
        broken["input_contract"] = {}
        broken["tool_policy"] = {"direct_tool_calls": False, "allowed_phase": "wrong_phase"}
        broken["failure_policy"] = {"retryable": True}
        broken["observability_fields"] = ["phase", "agent_id"]
        broken["configurable"] = False
        broken["degradation_when_disabled"] = "unexpected_degradation"
        audit = agent_registry_contract_audit([broken, *specs])

        assert audit["status"] == "needs_attention"
        assert audit["counts"]["agents"] == 10
        assert audit["counts"]["contract_gaps"] >= 1
        assert audit["counts"]["missing_observability"] >= 1
        assert audit["counts"]["duplicate_phases"] == 1
        assert audit["duplicate_phases"] == ["supervisor"]
        assert audit["missing_phases"] == []
        assert audit["extra_phases"] == []
        broken_item = audit["items"][0]
        assert broken_item["agent_id"] == "broken_agent"
        assert broken_item["contract_gaps"] == [
            "input_contract.required",
            "tool_policy.allowed_phase_mismatch",
            "failure_policy.fallback",
            "required_phase_degradation_boundary",
        ]
        assert "prompt_template" in broken_item["missing_observability_fields"]
        assert broken_item["tool_policy_valid"] is False
        assert broken_item["failure_policy_valid"] is False
        assert "unexpected_degradation" not in str(audit)


def test_agent_trace_contract_canonicalizes_runtime_phase_aliases(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        from open_coscientist.agents import canonical_trace_phase as exported_canonical_phase
        from open_coscientist.agents import get_trace_contract_payload as exported_trace_contract
        from open_coscientist.agents import trace_phase_sort_key as exported_trace_sort_key
        from open_coscientist.agents.registry import (
            canonical_trace_phase,
            get_trace_contract_payload,
            trace_phase_sort_key,
        )

        contract = get_trace_contract_payload()
        runtime_phases = ["unknown_vendor_phase", "rank", "supervisor", "literature"]
        ordered_phases = [
            phase
            for index, phase in sorted(
                enumerate(runtime_phases),
                key=lambda item: trace_phase_sort_key(item[1], fallback_index=item[0]),
            )
        ]

        assert canonical_trace_phase("rank") == "ranking"
        assert canonical_trace_phase("literature") == "literature_review"
        assert canonical_trace_phase("generation") == "generate"
        assert canonical_trace_phase("unknown") is None
        assert ordered_phases == ["supervisor", "literature", "rank", "unknown_vendor_phase"]
        assert exported_canonical_phase("rank") == "ranking"
        assert exported_trace_sort_key("generation")[0] == contract["phase_order_index"]["generate"]
        assert exported_trace_contract()["phase_index"]["ranking"]["agent_id"] == "ranking_agent"
        assert contract["unknown_phase_order"] == "after_known_phases"
        assert contract["phase_aliases"]["dedupe"] == "proximity"
        assert contract["phase_index"]["review"]["agent_id"] == "hypothesis_review_agent"
        assert contract["phase_index"]["review"]["prompt_template"] == "prompts/review.md"
        assert contract["required_fields"] == [
            "phase",
            "agent_id",
            "role",
            "prompt_template",
            "output_summary",
        ]
        assert "degradation_reason" in contract["optional_fields"]
        assert "raw provider payloads" in contract["boundary"]


def test_agent_trace_surface_summary_hides_expert_details_by_default(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        from open_coscientist.agents import agent_trace_surface_summary as exported_trace_summary
        from open_coscientist.agents.registry import agent_trace_surface_summary

        trace = [
            {
                "event_id": "event-secret-review",
                "phase": "review",
                "agent_id": "hypothesis_review_agent",
                "output": "Reviewed soundness and feasibility for the candidate.",
                "prompt_template": "prompts/review.md",
                "tool_calls": [{"args": {"raw": "SECRET TOOL ARG"}}],
                "token_usage": {"total_tokens": 1234},
                "confidence": 0.8,
            },
            {
                "event_id": "event-secret-literature",
                "phase": "literature",
                "output_summary": "Literature grounding is unavailable.",
                "degradation_reason": "literature_review_disabled_latent_knowledge_boundary",
                "synthetic": True,
            },
            {
                "event_id": "event-secret-unknown",
                "phase": "vendor_extra",
                "output": "Vendor extra trace event.",
            },
        ]

        summary = agent_trace_surface_summary(trace)

        assert summary["phase_order"] == ["literature_review", "review", "vendor_extra"]
        assert summary["trace_count"] == 3
        assert summary["counts"] == {
            "complete": 2,
            "degraded": 1,
            "synthetic": 1,
            "unknown_phase": 1,
            "with_tool_calls": 1,
        }
        assert summary["degradation_count"] == 1
        assert summary["synthetic_count"] == 1
        assert summary["unknown_phases"] == ["vendor_extra"]
        assert summary["items"][0]["status"] == "degraded"
        assert summary["items"][0]["label"] == "Literature grounding"
        assert summary["items"][1]["tool_call_count"] == 1
        assert "prompt_template" not in summary["items"][1]
        assert "event_id" not in summary["items"][1]
        assert "token_usage" not in summary["items"][1]
        assert "SECRET TOOL ARG" not in str(summary)
        assert "event-secret" not in str(summary)
        assert exported_trace_summary(trace)["phase_order"] == summary["phase_order"]

        expert_summary = agent_trace_surface_summary(trace, include_internal_refs=True)
        assert expert_summary["items"][1]["event_id"] == "event-secret-review"
        assert expert_summary["items"][1]["prompt_template"] == "prompts/review.md"
        assert expert_summary["items"][1]["token_usage"] == {"total_tokens": 1234}
        assert expert_summary["items"][1]["confidence"] == 0.8


def test_agent_trace_contract_audit_reports_metadata_coverage_without_raw_payload(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        from open_coscientist.agents import agent_trace_contract_audit as exported_audit
        from open_coscientist.agents.registry import agent_trace_contract_audit, get_trace_contract_payload

        ready_trace = [
            {
                "phase": "supervisor",
                "output_summary": "Research plan and constraints were prepared.",
                "tool_calls": [],
            },
            {
                "phase": "rank",
                "agent_id": "ranking_agent",
                "role": "Tournament ranking role.",
                "prompt_template": "prompts/ranking.md",
                "output_summary": "Pairwise Elo tournament completed.",
                "tool_calls": [{"name": "ranker", "args": {"secret": "SECRET TOOL ARG"}}],
                "raw_provider_response": {"debug": "SECRET PROVIDER PAYLOAD"},
            },
        ]

        ready = agent_trace_contract_audit(ready_trace)
        exported_ready = exported_audit(ready_trace)

        assert ready["status"] == "partial"
        assert exported_ready["status"] == ready["status"]
        assert exported_ready["phase_order"] == ready["phase_order"]
        assert ready["trace_count"] == 2
        assert ready["phase_order"] == ["supervisor", "ranking"]
        assert ready["counts"] == {
            "missing_required": 0,
            "unknown_phase": 0,
            "raw_payload_risk": 1,
            "degraded": 0,
            "synthetic": 0,
            "with_tool_calls": 1,
        }
        assert ready["items"][0]["agent_id"] == "supervisor_agent"
        assert ready["items"][0]["has_role"] is True
        assert ready["items"][0]["has_prompt_template"] is True
        assert ready["items"][1]["phase"] == "ranking"
        assert ready["items"][1]["raw_payload_keys"] == ["raw_provider_response"]
        assert "SECRET" not in str(ready)
        assert "raw-payload risk keys only" in ready["boundary"]

        contract = get_trace_contract_payload()
        assert "raw_provider_response" in contract["raw_payload_risk_keys"]
        assert "debug_payload" in contract["raw_payload_risk_keys"]


def test_agent_trace_contract_audit_flags_missing_and_unknown_trace_metadata(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        from open_coscientist.agents.registry import agent_trace_contract_audit

        audit = agent_trace_contract_audit(
            [
                {
                    "phase": "vendor_extra",
                    "output_summary": "Vendor extra event is visible as an unknown phase.",
                    "debug_payload": {"secret": "SECRET DEBUG PAYLOAD"},
                },
                {
                    "phase": "",
                    "raw_json": {"secret": "SECRET RAW JSON"},
                },
            ]
        )

        assert audit["status"] == "needs_attention"
        assert audit["trace_count"] == 2
        assert audit["phase_order"] == ["vendor_extra", "unknown"]
        assert audit["counts"]["missing_required"] == 2
        assert audit["counts"]["unknown_phase"] == 2
        assert audit["counts"]["raw_payload_risk"] == 2
        assert audit["items"][0]["missing_required_fields"] == [
            "agent_id",
            "role",
            "prompt_template",
        ]
        assert audit["items"][0]["raw_payload_keys"] == ["debug_payload"]
        assert audit["items"][1]["missing_required_fields"] == [
            "phase",
            "agent_id",
            "role",
            "prompt_template",
            "output_summary",
        ]
        assert audit["items"][1]["raw_payload_keys"] == ["raw_json"]
        assert "SECRET" not in str(audit)


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
        assert payload["degradation_count"] == 0
        assert payload["degraded_phases"] == []
        assert payload["phase_statuses"][0]["phase"] == "supervisor"
        assert payload["phase_statuses"][0]["enabled"] is True
        assert payload["trace_contract"]["phase_aliases"]["rank"] == "ranking"
        assert payload["trace_contract"]["phase_index"]["ranking"]["agent_id"] == "ranking_agent"
        assert "output_summary" in payload["trace_contract"]["required_fields"]

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
