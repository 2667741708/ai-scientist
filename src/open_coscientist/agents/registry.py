from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, TypedDict


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


def get_agent_registry_payload(*, public: bool = True) -> Dict[str, Any]:
    agents = list_agent_specs(public=public)
    phases = [str(agent["phase"]) for agent in agents]
    return {
        "agents": agents,
        "count": len(agents),
        "phases": phases,
        "registry_version": "paper_level_v1",
        "boundary": "Static registry metadata; LangGraph nodes remain the runtime implementation.",
    }
