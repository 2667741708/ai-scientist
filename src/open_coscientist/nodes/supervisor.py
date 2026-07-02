"""
Supervisor node - create research plan and workflow guidance.
"""

import logging
from typing import Any, Dict, List, Optional

from ..constants import (
    EXTENDED_MAX_TOKENS,
    MEDIUM_TEMPERATURE,
    PROGRESS_SUPERVISOR_START,
    PROGRESS_SUPERVISOR_COMPLETE,
)
from ..llm import call_llm_json
from ..models import create_metrics_update
from ..prompts import get_supervisor_prompt
from ..state import WorkflowState

logger = logging.getLogger(__name__)


def _short_guidance_text(value: Any, limit: int = 360) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."


def _append_feedback_guidance(
    constraints: List[str],
    feedback_items: Any,
    *,
    prefix: str,
) -> None:
    if not isinstance(feedback_items, list):
        return

    appended = 0
    for item in feedback_items[:5]:
        if not isinstance(item, dict):
            continue
        text = _short_guidance_text(item.get("text"))
        if not text:
            continue
        feedback_type = _short_guidance_text(item.get("feedback_type") or "critique", 80)
        constraints.append(f"[{prefix}] type={feedback_type}; feedback={text}.")
        appended += 1

    if appended:
        constraints.append(
            f"[{prefix}_policy] Treat human feedback as guidance for this run or continuation; "
            "do not claim it instantly rewrites already completed results."
        )


def build_supervisor_context_constraints(
    constraints: Optional[List[str]],
    memory_context: Any,
    user_feedback: Any,
) -> List[str]:
    combined = [item for item in (constraints or []) if str(item).strip()]

    if isinstance(memory_context, dict):
        parent_run = memory_context.get("parent_run")
        if isinstance(parent_run, dict):
            summary = _short_guidance_text(
                parent_run.get("summary") or parent_run.get("research_goal")
            )
            if summary:
                combined.append(f"[memory_parent_run] Prior run summary: {summary}.")

        prior_hypotheses = memory_context.get("prior_hypotheses")
        if isinstance(prior_hypotheses, list):
            for hypothesis in prior_hypotheses[:3]:
                if not isinstance(hypothesis, dict):
                    continue
                text = _short_guidance_text(
                    hypothesis.get("text")
                    or hypothesis.get("hypothesis")
                    or hypothesis.get("summary")
                )
                if not text:
                    continue
                support_level = _short_guidance_text(
                    hypothesis.get("support_level") or "unknown", 80
                )
                combined.append(
                    f"[memory_prior_hypothesis] support={support_level}; summary={text}."
                )

        _append_feedback_guidance(
            combined,
            memory_context.get("user_feedback"),
            prefix="memory_user_feedback",
        )

        evidence_summaries = memory_context.get("evidence_summaries")
        if isinstance(evidence_summaries, list):
            for evidence in evidence_summaries[:3]:
                if not isinstance(evidence, dict):
                    continue
                title = _short_guidance_text(
                    evidence.get("title")
                    or evidence.get("source_title")
                    or evidence.get("summary"),
                    160,
                )
                reliability = _short_guidance_text(
                    evidence.get("source_reliability") or "unknown", 80
                )
                support = _short_guidance_text(evidence.get("support_level") or "unknown", 80)
                if title:
                    combined.append(
                        "[memory_evidence] "
                        f"source_reliability={reliability}; support={support}; summary={title}."
                    )

        if len(combined) > len(constraints or []):
            combined.append(
                "[memory_usage_policy] Memory is summary-only planning context. "
                "Do not treat cache hits, internal ids, or unstated evidence as scientific support."
            )

    _append_feedback_guidance(combined, user_feedback, prefix="user_feedback")
    return combined


async def supervisor_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Create research plan and provide workflow guidance.

    This node analyzes the research goal and configures an appropriate
    research plan, setting parameters and providing guidance for the
    entire workflow.

    Args:
        state: Current workflow state

    Returns:
        Dictionary with updated state fields (supervisor_guidance)
    """
    research_goal = state["research_goal"]
    logger.info(f"Supervisor analyzing research goal: {research_goal[:100]}...")

    # extract optional user inputs from state
    preferences = state.get("preferences")
    attributes = state.get("attributes")
    constraints = build_supervisor_context_constraints(
        state.get("constraints"),
        state.get("memory_context"),
        state.get("user_feedback"),
    )
    user_hypotheses = state.get("starting_hypotheses")
    user_literature = state.get("literature")

    # extract user configuration for workflow
    initial_hypotheses_count = state.get("initial_hypotheses_count")
    max_iterations = state.get("max_iterations")
    evolution_max_count = state.get("evolution_max_count")
    mcp_available = state.get("mcp_available", False)
    pubmed_available = state.get("pubmed_available", False)

    # emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "supervisor_start",
            {
                "message": "Analyzing research goal and creating plan...",
                "progress": PROGRESS_SUPERVISOR_START,
            },
        )

    # call llm to create research plan with all context
    prompt, schema = get_supervisor_prompt(
        research_goal=research_goal,
        preferences=preferences,
        attributes=attributes,
        constraints=constraints,
        user_hypotheses=user_hypotheses,
        user_literature=user_literature,
        initial_hypotheses_count=initial_hypotheses_count,
        max_iterations=max_iterations,
        evolution_max_count=evolution_max_count,
        mcp_available=mcp_available,
        pubmed_available=pubmed_available,
        tool_registry=state.get("tool_registry"),
    )

    # save prompt to disk for debugging
    from ..prompts import save_prompt_to_disk

    save_prompt_to_disk(
        run_id=state.get("run_id", "unknown"),
        prompt_name="supervisor",
        content=prompt,
        metadata={
            "prompt_length_chars": len(prompt),
        },
    )

    response = await call_llm_json(
        prompt=prompt,
        model_name=state["model_name"],
        max_tokens=EXTENDED_MAX_TOKENS,
        temperature=MEDIUM_TEMPERATURE,
        json_schema=schema,
    )

    supervisor_guidance = {
        "research_goal_analysis": response.get("research_goal_analysis", {}),
        "workflow_plan": response.get("workflow_plan", {}),
        "performance_assessment": response.get("performance_assessment", {}),
        "adjustment_recommendations": response.get("adjustment_recommendations", []),
        "output_preparation": response.get("output_preparation", {}),
    }

    logger.info("Supervisor plan created")

    # Log key insights from supervisor
    goal_analysis = supervisor_guidance.get("research_goal_analysis", {})
    key_areas = goal_analysis.get("key_areas", [])
    if key_areas:
        logger.info(f"Key research areas identified: {', '.join(key_areas[:3])}")

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "supervisor_complete",
            {
                "message": "Research plan created",
                "progress": PROGRESS_SUPERVISOR_COMPLETE,
                "key_areas": len(key_areas),
            },
        )

    # Update metrics (deltas only, merge_metrics will add to existing state)
    metrics = create_metrics_update(llm_calls_delta=1)

    return {
        "supervisor_guidance": supervisor_guidance,
        "metrics": metrics,
        "messages": [
            {
                "role": "assistant",
                "content": "Created research plan and workflow guidance",
                "metadata": {"phase": "supervisor", "key_areas": len(key_areas)},
            }
        ],
    }
