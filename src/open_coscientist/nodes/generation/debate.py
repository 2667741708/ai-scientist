"""
Debate generation strategy - generate hypotheses through adversarial debates.

Each debate runs multiple turns between experts to generate a single hypothesis.
Multiple debates can run in parallel.
"""

import asyncio
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from .citations import ReferenceIndex, resolve_citation_keys
from ...constants import (
    DEBATE_MAX_TURNS,
    EXTENDED_MAX_TOKENS,
    HIGH_TEMPERATURE,
    INITIAL_ELO_RATING,
)
from ...llm import call_llm, call_llm_json
from ...models import Hypothesis
from ...prompts import get_debate_generation_prompt, save_prompt_to_disk
from ...state import WorkflowState

logger = logging.getLogger(__name__)


def _short_generation_guidance(value: Any, limit: int = 360) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."


def _focus_area_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if str(value or "").strip():
        return [str(value).strip()]
    return []


def _append_generation_feedback_focus(focus_areas: List[str], feedback_items: Any, label: str) -> int:
    if not isinstance(feedback_items, list):
        return 0

    appended = 0
    for item in feedback_items[:5]:
        if not isinstance(item, dict):
            continue
        text = _short_generation_guidance(item.get("text"))
        if not text:
            continue
        feedback_type = _short_generation_guidance(item.get("feedback_type") or "critique", 80)
        focus_areas.append(f"[{label}] type={feedback_type}; feedback={text}.")
        appended += 1
    return appended


def augment_generation_supervisor_guidance(
    supervisor_guidance: Dict[str, Any] | None,
    starting_hypotheses: Any,
    memory_context: Any,
    user_feedback: Any,
) -> Dict[str, Any] | None:
    generated_focus: List[str] = []

    if isinstance(starting_hypotheses, list):
        for hypothesis in starting_hypotheses[:5]:
            text = _short_generation_guidance(hypothesis)
            if text:
                generated_focus.append(f"[user_starting_hypothesis] {text}")

    if isinstance(memory_context, dict):
        prior_hypotheses = memory_context.get("prior_hypotheses")
        if isinstance(prior_hypotheses, list):
            for hypothesis in prior_hypotheses[:3]:
                if not isinstance(hypothesis, dict):
                    continue
                text = _short_generation_guidance(
                    hypothesis.get("text")
                    or hypothesis.get("hypothesis")
                    or hypothesis.get("summary")
                )
                if text:
                    support = _short_generation_guidance(
                        hypothesis.get("support_level") or "unknown", 80
                    )
                    generated_focus.append(
                        f"[memory_prior_hypothesis] support={support}; summary={text}."
                    )

        _append_generation_feedback_focus(
            generated_focus,
            memory_context.get("user_feedback"),
            "memory_user_feedback",
        )

    _append_generation_feedback_focus(generated_focus, user_feedback, "user_feedback")
    if not generated_focus:
        return supervisor_guidance

    augmented = deepcopy(supervisor_guidance) if isinstance(supervisor_guidance, dict) else {}
    workflow_plan = dict(augmented.get("workflow_plan") or {})
    generation_phase = dict(workflow_plan.get("generation_phase") or {})
    focus_areas = _focus_area_list(generation_phase.get("focus_areas"))
    focus_areas.extend(generated_focus)
    focus_areas.append(
        "[memory_generation_policy] Treat memory and feedback as summary-only guidance; "
        "do not expose raw ids or claim unsupported evidence."
    )
    generation_phase["focus_areas"] = focus_areas
    workflow_plan["generation_phase"] = generation_phase
    augmented["workflow_plan"] = workflow_plan
    return augmented


def _match_papers_to_grounding(articles, literature_grounding):
    """Match lit review articles against a hypothesis's literature_grounding text.

    Uses author last name + year matching against citation patterns like
    "(Roepert et al., 2020; Erba et al., 2021)" in the grounding text.

    Returns empty list if no grounding text or no matches.
    """
    from .papers import articles_to_candidates, filter_papers_by_grounding

    candidates = articles_to_candidates(articles)
    return filter_papers_by_grounding(candidates, literature_grounding)


async def _run_single_debate(
    state: WorkflowState,
    debate_id: Optional[int] = None,
    num_turns: int = DEBATE_MAX_TURNS,
    articles_with_reasoning: Optional[str] = None,
    reference_index: Optional[ReferenceIndex] = None,
) -> Tuple[Hypothesis, str]:
    """
    Generate a single hypothesis using multi-turn debate strategy

    args:
        state: current workflow state
        debate_id: id for this debate (used for tracking and identification)
        num_turns: number of debate turns to run (default from constants)
        articles_with_reasoning: optional literature review context for debate
        reference_index: citation key → source mapping for structured citations

    returns:
        Tuple of (single generated Hypothesis object, debate transcript string)
    """
    ref_idx = reference_index or ReferenceIndex(text="", sources={})
    count = 1  # each debate generates exactly 1 hypothesis
    debate_label = f"debate {debate_id}" if debate_id is not None else "debate"

    supervisor_guidance = augment_generation_supervisor_guidance(
        state.get("supervisor_guidance"),
        state.get("starting_hypotheses"),
        state.get("memory_context"),
        state.get("user_feedback"),
    )
    preferences = state.get("preferences")
    attributes = state.get("attributes")

    transcript = ""

    for turn in range(1, num_turns + 1):
        is_final = turn == num_turns

        prompt, schema = get_debate_generation_prompt(
            research_goal=state["research_goal"],
            hypotheses_count=count,
            transcript=transcript,
            supervisor_guidance=supervisor_guidance,
            preferences=preferences,
            attributes=attributes,
            is_final_turn=is_final,
            articles_with_reasoning=articles_with_reasoning,
            articles=state.get("articles"),
            tool_registry=state.get("tool_registry"),
            reference_list=ref_idx.text,
        )

        if is_final:
            save_prompt_to_disk(
                run_id=state.get("run_id", "unknown"),
                prompt_name=f"generate_debate_{debate_id}_final",
                content=prompt,
                metadata={
                    "debate_id": debate_id,
                    "turn": turn,
                    "has_literature": articles_with_reasoning is not None,
                    "reference_keys": list(ref_idx.sources.keys()),
                    "prompt_length_chars": len(prompt),
                },
            )
            scaled_max_tokens = min(EXTENDED_MAX_TOKENS + 4000, 20000)

            response = await call_llm_json(
                prompt=prompt,
                model_name=state["model_name"],
                max_tokens=scaled_max_tokens,
                temperature=HIGH_TEMPERATURE,
                json_schema=schema,
            )

            hypotheses_data = response.get("hypotheses", [])
            if not hypotheses_data:
                raise ValueError(f"{debate_label} failed to generate hypothesis")

            hyp_data = hypotheses_data[0]

            hypothesis_text = hyp_data.get("hypothesis") or hyp_data.get("text", "")
            explanation = hyp_data.get("explanation")
            literature_grounding = hyp_data.get("literature_grounding")
            experiment = hyp_data.get("experiment")

            citation_map = resolve_citation_keys(literature_grounding, ref_idx.sources)

            hypothesis = Hypothesis(
                text=hypothesis_text,
                explanation=explanation,
                literature_grounding=literature_grounding,
                experiment=experiment,
                score=0.0,
                elo_rating=INITIAL_ELO_RATING,
                generation_method="debate",
                debate_id=debate_id,
                citation_map=citation_map,
            )

            return hypothesis, transcript
        else:
            response_text = await call_llm(
                prompt=prompt,
                model_name=state["model_name"],
                max_tokens=EXTENDED_MAX_TOKENS,
                temperature=HIGH_TEMPERATURE,
            )

            transcript += f"\n\nTurn {turn}:\n{response_text}"

    raise ValueError(f"{debate_label} ended without final turn")


async def generate_with_debate(
    state: WorkflowState,
    count: int,
    articles_with_reasoning: Optional[str] = None,
    reference_index: Optional[ReferenceIndex] = None,
) -> Tuple[List[Hypothesis], List[Dict[str, Any]]]:
    """
    Generate hypotheses using parallel debate strategy

    Each debate generates 1 hypothesis through multi-turn expert discussion

    args:
        state: current workflow state
        count: number of debates to run (= number of hypotheses to generate)
        articles_with_reasoning: optional literature review context for debates
        reference_index: citation key → source mapping for structured citations

    returns:
        tuple of (debate_hypotheses, debate_transcripts)
    """
    if count == 0:
        return [], []

    logger.info(f"Running {count} parallel debates")

    debate_tasks = [
        _run_single_debate(
            state,
            debate_id=i,
            articles_with_reasoning=articles_with_reasoning,
            reference_index=reference_index,
        )
        for i in range(count)
    ]

    debate_results = await asyncio.gather(*debate_tasks)

    debate_hypotheses = [hyp for hyp, _ in debate_results]
    debate_transcripts = [
        {
            "debate_id": i,
            "transcript": transcript,
            "hypothesis_text": debate_hypotheses[i].text
        }
        for i, (_, transcript) in enumerate(debate_results)
    ]

    logger.info(f"Generated {len(debate_hypotheses)} hypotheses from debates")
    return debate_hypotheses, debate_transcripts
