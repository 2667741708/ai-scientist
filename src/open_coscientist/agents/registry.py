from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping, Optional, TypedDict


class AgentSpec(TypedDict):
    agent_id: str
    phase: str
    role: str
    input_contract: Dict[str, Any]
    output_contract: Dict[str, Any]
    prompt_template: str
    tool_policy: Dict[str, Any]
    failure_policy: Dict[str, Any]
    observability_fields: List[str]
    configurable: bool
    degradation_when_disabled: str


class PhaseStatus(TypedDict):
    phase: str
    label: str
    agent_id: str
    enabled: bool
    configurable: bool
    degradation_reason: Optional[str]


BASE_OBSERVABILITY_FIELDS = [
    "phase",
    "agent_id",
    "role",
    "prompt_template",
    "tool_calls",
    "token_usage",
    "output_summary",
    "confidence",
    "synthetic",
    "degradation_reason",
]


PHASE_ORDER = [
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


TRACE_PHASE_ORDER_INDEX = {phase: index for index, phase in enumerate(PHASE_ORDER)}


PHASE_LABELS = {
    "supervisor": "Research planning",
    "literature_review": "Literature grounding",
    "generate": "Hypothesis generation",
    "reflection": "Evidence reflection",
    "review": "Scientific critique",
    "ranking": "Tournament ranking",
    "meta_review": "Meta-review synthesis",
    "evolve": "Hypothesis evolution",
    "proximity": "Diversity control",
}


TRACE_PHASE_ALIASES = {
    "literature": "literature_review",
    "lit_review": "literature_review",
    "generation": "generate",
    "hypothesis_generation": "generate",
    "rank": "ranking",
    "tournament": "ranking",
    "metareview": "meta_review",
    "meta": "meta_review",
    "evolution": "evolve",
    "dedupe": "proximity",
    "dedup": "proximity",
    "diversity": "proximity",
}


TRACE_REQUIRED_FIELDS = [
    "phase",
    "agent_id",
    "role",
    "prompt_template",
    "output_summary",
]


TRACE_OPTIONAL_FIELDS = [
    "tool_calls",
    "token_usage",
    "confidence",
    "synthetic",
    "degradation_reason",
]


AGENT_REGISTRY: list[AgentSpec] = [
    {
        "agent_id": "supervisor_agent",
        "phase": "supervisor",
        "role": "Research planning, constraint extraction, and workflow guidance.",
        "input_contract": {
            "required": ["research_goal"],
            "optional": ["preferences", "attributes", "constraints", "memory_context", "starting_hypotheses"],
        },
        "output_contract": {
            "required": ["research_plan", "supervisor_guidance"],
            "optional": ["phase_guidance", "quality_rubric", "safety_notes"],
        },
        "prompt_template": "prompts/supervisor.md",
        "tool_policy": {"direct_tool_calls": False, "allowed_phase": "supervisor"},
        "failure_policy": {"retryable": True, "fallback": "fail_run"},
        "observability_fields": BASE_OBSERVABILITY_FIELDS,
        "configurable": False,
        "degradation_when_disabled": "not_supported",
    },
    {
        "agent_id": "literature_grounding_agent",
        "phase": "literature_review",
        "role": "MCP, PDF, fulltext, and knowledge-source grounding for the research goal.",
        "input_contract": {
            "required": ["research_goal"],
            "optional": ["starting_hypotheses", "tool_registry", "library_id", "memory_context"],
        },
        "output_contract": {
            "required": ["articles_with_reasoning"],
            "optional": ["article_metadata", "citation_context", "tool_results", "evidence_boundary"],
        },
        "prompt_template": "nodes/literature_review.py",
        "tool_policy": {"direct_tool_calls": True, "allowed_phase": "literature_review"},
        "failure_policy": {"retryable": True, "fallback": "latent_knowledge_boundary"},
        "observability_fields": BASE_OBSERVABILITY_FIELDS,
        "configurable": True,
        "degradation_when_disabled": "latent_knowledge_generation_without_literature_grounding",
    },
    {
        "agent_id": "hypothesis_generation_agent",
        "phase": "generate",
        "role": "Generate model candidates and integrate user-provided starting hypotheses.",
        "input_contract": {
            "required": ["research_goal", "research_plan"],
            "optional": ["literature", "starting_hypotheses", "preferences", "constraints", "memory_context"],
        },
        "output_contract": {
            "required": ["hypotheses"],
            "optional": ["citation_map", "debate_transcripts", "origin_metadata"],
        },
        "prompt_template": "prompts/generation.md",
        "tool_policy": {"direct_tool_calls": False, "allowed_phase": "generate"},
        "failure_policy": {"retryable": True, "fallback": "fail_run"},
        "observability_fields": BASE_OBSERVABILITY_FIELDS,
        "configurable": False,
        "degradation_when_disabled": "not_supported",
    },
    {
        "agent_id": "reflection_agent",
        "phase": "reflection",
        "role": "Compare generated hypotheses against literature reasoning and evidence gaps.",
        "input_contract": {"required": ["hypotheses"], "optional": ["articles_with_reasoning", "literature"]},
        "output_contract": {"required": ["reflection_notes"], "optional": ["gap_analysis", "hypothesis_annotations"]},
        "prompt_template": "prompts/reflection.md",
        "tool_policy": {"direct_tool_calls": False, "allowed_phase": "reflection"},
        "failure_policy": {"retryable": True, "fallback": "skip_when_no_literature"},
        "observability_fields": BASE_OBSERVABILITY_FIELDS,
        "configurable": True,
        "degradation_when_disabled": "reflection_skipped_without_literature_context",
    },
    {
        "agent_id": "hypothesis_review_agent",
        "phase": "review",
        "role": "Critique hypotheses for soundness, novelty, relevance, feasibility, and safety.",
        "input_contract": {"required": ["hypotheses"], "optional": ["supervisor_guidance", "meta_review", "user_feedback"]},
        "output_contract": {"required": ["reviews", "scores"], "optional": ["safety_ethical_concerns", "constructive_feedback"]},
        "prompt_template": "prompts/review.md",
        "tool_policy": {"direct_tool_calls": False, "allowed_phase": "review"},
        "failure_policy": {"retryable": True, "fallback": "fail_run"},
        "observability_fields": BASE_OBSERVABILITY_FIELDS,
        "configurable": False,
        "degradation_when_disabled": "not_supported",
    },
    {
        "agent_id": "ranking_agent",
        "phase": "ranking",
        "role": "Run pairwise tournament comparisons and update Elo ranking provenance.",
        "input_contract": {"required": ["reviewed_hypotheses"], "optional": ["tournament_history", "proximity_clusters"]},
        "output_contract": {"required": ["ranked_hypotheses", "tournament_matchups"], "optional": ["elo_updates"]},
        "prompt_template": "prompts/ranking.md",
        "tool_policy": {"direct_tool_calls": False, "allowed_phase": "ranking"},
        "failure_policy": {"retryable": True, "fallback": "score_sort_without_tournament"},
        "observability_fields": BASE_OBSERVABILITY_FIELDS,
        "configurable": False,
        "degradation_when_disabled": "not_supported",
    },
    {
        "agent_id": "meta_review_agent",
        "phase": "meta_review",
        "role": "Synthesize cross-hypothesis strengths, weaknesses, themes, and recommendations.",
        "input_contract": {"required": ["reviews", "ranked_hypotheses"], "optional": ["reflection_notes", "tournament_matchups"]},
        "output_contract": {"required": ["meta_review"], "optional": ["strategic_recommendations", "emerging_themes"]},
        "prompt_template": "prompts/meta_review.md",
        "tool_policy": {"direct_tool_calls": False, "allowed_phase": "meta_review"},
        "failure_policy": {"retryable": True, "fallback": "skip_iteration"},
        "observability_fields": BASE_OBSERVABILITY_FIELDS,
        "configurable": True,
        "degradation_when_disabled": "iteration_disabled_when_max_iterations_is_zero",
    },
    {
        "agent_id": "evolution_agent",
        "phase": "evolve",
        "role": "Refine top hypotheses using review, meta-review, feedback, and diversity guidance.",
        "input_contract": {"required": ["ranked_hypotheses", "reviews"], "optional": ["meta_review", "reflection_notes", "user_feedback"]},
        "output_contract": {"required": ["evolved_hypotheses"], "optional": ["evolution_history", "lineage"]},
        "prompt_template": "prompts/evolve.md",
        "tool_policy": {"direct_tool_calls": False, "allowed_phase": "evolve"},
        "failure_policy": {"retryable": True, "fallback": "retain_original_hypotheses"},
        "observability_fields": BASE_OBSERVABILITY_FIELDS,
        "configurable": True,
        "degradation_when_disabled": "iteration_disabled_when_max_iterations_is_zero",
    },
    {
        "agent_id": "proximity_agent",
        "phase": "proximity",
        "role": "Cluster similar hypotheses, remove duplicates, and reduce mode collapse.",
        "input_contract": {"required": ["hypotheses"], "optional": ["evolution_history", "similarity_threshold"]},
        "output_contract": {"required": ["deduplicated_hypotheses"], "optional": ["clusters", "removed_duplicates"]},
        "prompt_template": "prompts/proximity.md",
        "tool_policy": {"direct_tool_calls": False, "allowed_phase": "proximity"},
        "failure_policy": {"retryable": True, "fallback": "retain_all_hypotheses"},
        "observability_fields": BASE_OBSERVABILITY_FIELDS,
        "configurable": True,
        "degradation_when_disabled": "iteration_disabled_when_max_iterations_is_zero",
    },
]


def list_agent_specs(*, public: bool = False) -> list[AgentSpec] | list[Dict[str, Any]]:
    specs = deepcopy(AGENT_REGISTRY)
    if not public:
        return specs
    return [
        {
            "agent_id": spec["agent_id"],
            "phase": spec["phase"],
            "role": spec["role"],
            "input_contract": spec["input_contract"],
            "output_contract": spec["output_contract"],
            "prompt_template": spec["prompt_template"],
            "tool_policy": spec["tool_policy"],
            "failure_policy": spec["failure_policy"],
            "observability_fields": spec["observability_fields"],
            "configurable": spec["configurable"],
            "degradation_when_disabled": spec["degradation_when_disabled"],
        }
        for spec in specs
    ]


def get_agent_spec(agent_id: str) -> Optional[AgentSpec]:
    for spec in AGENT_REGISTRY:
        if spec["agent_id"] == agent_id:
            return deepcopy(spec)
    return None


def canonical_trace_phase(phase: str) -> Optional[str]:
    normalized = str(phase or "").strip()
    if not normalized:
        return None
    if normalized in PHASE_ORDER:
        return normalized
    return TRACE_PHASE_ALIASES.get(normalized)


def trace_phase_sort_key(phase: str, *, fallback_index: int = 0) -> tuple[int, int, str]:
    canonical = canonical_trace_phase(phase)
    if canonical is None:
        return (len(PHASE_ORDER), fallback_index, str(phase or "").strip())
    return (TRACE_PHASE_ORDER_INDEX[canonical], fallback_index, canonical)


def agent_trace_surface_summary(
    trace_events: list[Any],
    *,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    specs_by_phase = {spec["phase"]: spec for spec in AGENT_REGISTRY}
    items: list[Dict[str, Any]] = []
    for index, event in enumerate(trace_events or []):
        raw_phase = str(_trace_value(event, "phase") or "").strip()
        canonical_phase = canonical_trace_phase(raw_phase)
        phase_key = canonical_phase or raw_phase or "unknown"
        spec = specs_by_phase.get(canonical_phase or "")
        degradation_reason = _trace_value(event, "degradation_reason")
        synthetic = bool(_trace_value(event, "synthetic"))
        item = {
            "phase": phase_key,
            "source_phase": raw_phase or None,
            "label": PHASE_LABELS.get(phase_key, phase_key.replace("_", " ").title()),
            "agent_id": _trace_value(event, "agent_id") or (spec["agent_id"] if spec else None),
            "role": _trace_value(event, "role") or (spec["role"] if spec else None),
            "status": "degraded" if degradation_reason else ("synthetic" if synthetic else "complete"),
            "output_summary": _trace_output_summary(event),
            "tool_call_count": _trace_tool_call_count(event),
            "synthetic": synthetic,
            "degradation_reason": degradation_reason,
        }
        if include_internal_refs:
            item.update(
                {
                    "event_id": _trace_value(event, "event_id"),
                    "prompt_template": _trace_value(event, "prompt_template")
                    or (spec["prompt_template"] if spec else None),
                    "confidence": _trace_value(event, "confidence"),
                    "token_usage": _trace_value(event, "token_usage"),
                }
            )
        items.append(item)

    sorted_items = [
        item
        for _, item in sorted(
            enumerate(items),
            key=lambda pair: trace_phase_sort_key(pair[1]["phase"], fallback_index=pair[0]),
        )
    ]
    degraded_phases = [
        {"phase": item["phase"], "label": item["label"], "reason": item["degradation_reason"]}
        for item in sorted_items
        if item.get("degradation_reason")
    ]
    unknown_phases = [
        item["phase"]
        for item in sorted_items
        if canonical_trace_phase(str(item.get("phase") or "")) is None
    ]
    return {
        "trace_count": len(sorted_items),
        "phase_order": [item["phase"] for item in sorted_items],
        "items": sorted_items,
        "degradation_count": len(degraded_phases),
        "degraded_phases": degraded_phases,
        "synthetic_count": sum(1 for item in sorted_items if item.get("synthetic")),
        "unknown_phases": unknown_phases,
        "visibility_boundary": (
            "Agent process summaries expose phase, role, status, output summary, and tool counts by default; "
            "event IDs, prompt templates, token usage, and raw tool/provider payloads require expert disclosure."
        ),
    }


def get_trace_contract_payload() -> Dict[str, Any]:
    agents = list_agent_specs(public=True)
    phase_index = {
        str(agent["phase"]): {
            "agent_id": agent["agent_id"],
            "role": agent["role"],
            "prompt_template": agent["prompt_template"],
            "observability_fields": agent["observability_fields"],
        }
        for agent in agents
    }
    return {
        "phase_order": PHASE_ORDER,
        "phase_labels": PHASE_LABELS,
        "phase_aliases": TRACE_PHASE_ALIASES,
        "phase_order_index": TRACE_PHASE_ORDER_INDEX,
        "unknown_phase_order": "after_known_phases",
        "phase_index": phase_index,
        "required_fields": TRACE_REQUIRED_FIELDS,
        "optional_fields": TRACE_OPTIONAL_FIELDS,
        "surface_summary_fields": [
            "phase",
            "label",
            "agent_id",
            "role",
            "status",
            "output_summary",
            "tool_call_count",
            "synthetic",
            "degradation_reason",
        ],
        "observability_contract": BASE_OBSERVABILITY_FIELDS,
        "boundary": (
            "Trace summaries expose phase, agent identity, prompt template, output summary, "
            "and degradation metadata; raw prompts, raw provider payloads, and full tool results "
            "stay outside the default trace contract."
        ),
    }


def get_phase_status_payload(*, disabled_phases: Optional[List[str]] = None) -> Dict[str, Any]:
    disabled = {str(phase) for phase in (disabled_phases or [])}
    specs_by_phase = {spec["phase"]: spec for spec in AGENT_REGISTRY}
    invalid_disabled_phases: list[Dict[str, str]] = []
    phase_statuses: list[PhaseStatus] = []

    for phase in PHASE_ORDER:
        spec = specs_by_phase[phase]
        requested_disabled = phase in disabled
        enabled = not requested_disabled or not spec["configurable"]
        degradation_reason = spec["degradation_when_disabled"] if requested_disabled and spec["configurable"] else None
        if requested_disabled and not spec["configurable"]:
            invalid_disabled_phases.append(
                {
                    "phase": phase,
                    "label": PHASE_LABELS.get(phase, phase),
                    "reason": "required_phase_cannot_be_disabled",
                }
            )
        phase_statuses.append(
            {
                "phase": phase,
                "label": PHASE_LABELS.get(phase, phase),
                "agent_id": spec["agent_id"],
                "enabled": enabled,
                "configurable": spec["configurable"],
                "degradation_reason": degradation_reason,
            }
        )

    degraded_phases = [
        status
        for status in phase_statuses
        if not status["enabled"] and status["degradation_reason"]
    ]
    return {
        "phase_statuses": phase_statuses,
        "degraded_phases": degraded_phases,
        "degradation_count": len(degraded_phases),
        "invalid_disabled_phases": invalid_disabled_phases,
        "boundary": (
            "Disabled configurable phases must be shown as capability degradation; "
            "required phases remain enabled."
        ),
    }


def get_agent_registry_payload(*, public: bool = True) -> Dict[str, Any]:
    agents = list_agent_specs(public=public)
    phases = [str(agent["phase"]) for agent in agents]
    phase_status_payload = get_phase_status_payload()
    phase_index = {
        str(agent["phase"]): {
            "agent_id": agent["agent_id"],
            "role": agent["role"],
            "prompt_template": agent["prompt_template"],
            "configurable": agent["configurable"],
            "degradation_when_disabled": agent["degradation_when_disabled"],
        }
        for agent in agents
    }
    configurable_phases = [
        str(agent["phase"])
        for agent in agents
        if bool(agent["configurable"])
    ]
    return {
        "agents": agents,
        "count": len(agents),
        "phases": phases,
        "phase_order": PHASE_ORDER,
        "phase_labels": PHASE_LABELS,
        "configurable_phases": configurable_phases,
        "required_phases": [
            phase for phase in PHASE_ORDER if phase not in configurable_phases
        ],
        "phase_index": phase_index,
        "phase_statuses": phase_status_payload["phase_statuses"],
        "degraded_phases": phase_status_payload["degraded_phases"],
        "degradation_count": phase_status_payload["degradation_count"],
        "invalid_disabled_phases": phase_status_payload["invalid_disabled_phases"],
        "phase_status_boundary": phase_status_payload["boundary"],
        "observability_contract": BASE_OBSERVABILITY_FIELDS,
        "trace_contract": get_trace_contract_payload(),
        "registry_version": "paper_level_v1",
        "boundary": "Static registry metadata; LangGraph nodes remain the runtime implementation.",
    }


def _trace_value(event: Any, key: str) -> Any:
    if isinstance(event, Mapping):
        return event.get(key)
    return getattr(event, key, None)


def _trace_output_summary(event: Any) -> str:
    for key in ("output_summary", "summary", "output", "content"):
        value = _trace_value(event, key)
        if value:
            return _compact_trace_text(value)
    return ""


def _trace_tool_call_count(event: Any) -> int:
    tool_calls = _trace_value(event, "tool_calls")
    if isinstance(tool_calls, list):
        return len(tool_calls)
    if isinstance(tool_calls, tuple):
        return len(tool_calls)
    if isinstance(tool_calls, int):
        return max(0, tool_calls)
    tool_count = _trace_value(event, "tool_call_count")
    if isinstance(tool_count, int):
        return max(0, tool_count)
    return 0


def _compact_trace_text(value: Any, *, max_length: int = 280) -> str:
    compact = " ".join(str(value).split())
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 3].rstrip()}..."
