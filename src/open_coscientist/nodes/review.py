"""
Review node - adaptive peer review strategy based on hypothesis count.

- Small batches (≤5): Comparative batch review for differentiated scores
- Large batches (>5): Parallel individual reviews for scalability
"""

import asyncio
import logging
from copy import deepcopy
from typing import Any, Dict, List

from ..constants import (
    THINKING_MAX_TOKENS,
    EXTENDED_MAX_TOKENS,
    HIGH_TEMPERATURE,
    PROGRESS_REVIEW_START,
    PROGRESS_REVIEW_COMPLETE,
    COMPARATIVE_BATCH_THRESHOLD,
)
from ..llm import call_llm_json
from ..models import Hypothesis, HypothesisReview, create_metrics_update
from ..prompts import get_review_batch_prompt, get_review_prompt
from ..state import WorkflowState
from .evidence_grounding import format_hypothesis_with_evidence

logger = logging.getLogger(__name__)


def _short_review_guidance(value: Any, limit: int = 360) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."


def _review_criteria_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if str(value or "").strip():
        return [str(value).strip()]
    return []


def _append_review_feedback_criteria(criteria: List[str], feedback_items: Any, label: str) -> int:
    if not isinstance(feedback_items, list):
        return 0

    appended = 0
    for item in feedback_items[:5]:
        if not isinstance(item, dict):
            continue
        text = _short_review_guidance(item.get("text"))
        if not text:
            continue
        feedback_type = _short_review_guidance(item.get("feedback_type") or "critique", 80)
        criteria.append(f"[{label}] type={feedback_type}; feedback={text}.")
        appended += 1
    return appended


_REVIEW_PACKET_FIELDS = (
    "status",
    "support_level",
    "summary",
    "feedback_type",
    "target_type",
    "source",
    "source_reliability",
    "checkpoint_available",
    "resume_supported",
    "should_retry",
    "recovery_action",
    "resume_mode",
    "phase",
)


def _append_review_memory_prompt_packet_criteria(
    criteria: List[str],
    memory_prompt_packet: Any,
) -> int:
    if not isinstance(memory_prompt_packet, dict):
        return 0
    sections = memory_prompt_packet.get("sections")
    if not isinstance(sections, list):
        return 0

    appended = 0
    for section in sections[:6]:
        if not isinstance(section, dict):
            continue
        section_name = _short_review_guidance(section.get("section") or "memory_section", 80)
        items = section.get("items") if isinstance(section.get("items"), list) else []
        for item in items[:2]:
            if not isinstance(item, dict):
                continue
            fields: List[str] = []
            for key in _REVIEW_PACKET_FIELDS:
                value = item.get(key)
                if value in (None, "", []):
                    continue
                if isinstance(value, list):
                    value = ", ".join(_short_review_guidance(entry, 80) for entry in value[:4])
                fields.append(f"{key}={_short_review_guidance(value, 180)}")
            if fields:
                criteria.append(
                    f"[memory_prompt_packet] section={section_name}; "
                    f"{'; '.join(fields[:8])}."
                )
                appended += 1
    return appended


def augment_review_supervisor_guidance(
    supervisor_guidance: Dict[str, Any] | None,
    memory_context: Any,
    user_feedback: Any,
    memory_prompt_packet: Any = None,
) -> Dict[str, Any] | None:
    feedback_criteria: List[str] = []

    if isinstance(memory_context, dict):
        _append_review_feedback_criteria(
            feedback_criteria,
            memory_context.get("user_feedback"),
            "memory_user_feedback",
        )

        evidence_summaries = memory_context.get("evidence_summaries")
        if isinstance(evidence_summaries, list):
            for evidence in evidence_summaries[:3]:
                if not isinstance(evidence, dict):
                    continue
                title = _short_review_guidance(
                    evidence.get("title")
                    or evidence.get("source_title")
                    or evidence.get("summary"),
                    160,
                )
                if not title:
                    continue
                reliability = _short_review_guidance(
                    evidence.get("source_reliability") or "unknown", 80
                )
                support = _short_review_guidance(evidence.get("support_level") or "unknown", 80)
                feedback_criteria.append(
                    "[memory_evidence_boundary] "
                    f"source_reliability={reliability}; support={support}; summary={title}."
                )

        evidence_boundary = memory_context.get("evidence_boundary")
        if isinstance(evidence_boundary, dict):
            status = _short_review_guidance(evidence_boundary.get("status") or "unknown", 80)
            evidence_count = int(evidence_boundary.get("evidence_count") or 0)
            parsed_fulltext_count = int(evidence_boundary.get("parsed_fulltext_count") or 0)
            experimental_data_count = int(evidence_boundary.get("experimental_data_count") or 0)
            feedback_criteria.append(
                "[memory_evidence_boundary] "
                f"status={status}; evidence_count={evidence_count}; "
                f"parsed_fulltext_count={parsed_fulltext_count}; "
                f"experimental_data_count={experimental_data_count}."
            )

    _append_review_feedback_criteria(feedback_criteria, user_feedback, "user_feedback")
    prompt_packet_count = _append_review_memory_prompt_packet_criteria(
        feedback_criteria,
        memory_prompt_packet,
    )
    if not feedback_criteria:
        return supervisor_guidance

    augmented = deepcopy(supervisor_guidance) if isinstance(supervisor_guidance, dict) else {}
    workflow_plan = dict(augmented.get("workflow_plan") or {})
    review_phase = dict(workflow_plan.get("review_phase") or {})
    criteria = _review_criteria_list(review_phase.get("critical_criteria"))
    criteria.extend(feedback_criteria)
    review_phase["critical_criteria"] = criteria

    existing_depth = _short_review_guidance(review_phase.get("review_depth"), 240)
    feedback_policy = (
        "Use human feedback and memory evidence boundaries as review guidance; "
        "do not present feedback as an instant rewrite of completed results."
    )
    if prompt_packet_count:
        feedback_policy = (
            f"{feedback_policy} Use summary-only memory prompt packet fields for review; "
            "do not expose checkpoint refs, raw tool payloads, provider payloads, or internal ids."
        )
    review_phase["review_depth"] = f"{existing_depth} {feedback_policy}".strip()
    workflow_plan["review_phase"] = review_phase
    augmented["workflow_plan"] = workflow_plan
    return augmented


async def review_single_hypothesis(
    hypothesis_text: str,
    research_goal: str,
    model_name: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    meta_review: Dict[str, Any] | None = None,
    run_id: str | None = None,
    hypothesis_index: int | None = None,
    tool_registry: Any | None = None,
) -> HypothesisReview:
    """
    Review a single hypothesis.

    Args:
        hypothesis_text: The hypothesis to review
        research_goal: The research goal for context
        model_name: LLM model to use
        run_id: Optional run ID for saving prompts
        hypothesis_index: Optional index for naming saved prompts

    Returns:
        HypothesisReview object
    """
    # Note: meta_review is not available in this function
    # They would need to be passed as parameters if needed
    prompt, schema = get_review_prompt(
        research_goal=research_goal,
        hypothesis_text=hypothesis_text,
        supervisor_guidance=supervisor_guidance,
        meta_review=meta_review,
        tool_registry=tool_registry,
    )

    # save prompt to disk for debugging
    if run_id:
        from ..prompts import save_prompt_to_disk

        filename = (
            f"review_individual_{hypothesis_index}"
            if hypothesis_index is not None
            else "review_individual"
        )
        save_prompt_to_disk(
            run_id=run_id,
            prompt_name=filename,
            content=prompt,
            metadata={
                "hypothesis_index": hypothesis_index,
                "prompt_length_chars": len(prompt),
            },
        )

    response = await call_llm_json(
        prompt=prompt,
        model_name=model_name,
        max_tokens=EXTENDED_MAX_TOKENS,
        temperature=HIGH_TEMPERATURE,
        json_schema=schema,
    )

    # Calculate overall_score from criterion scores (more consistent than LLM-provided)
    scores = response.get("scores", {})
    if scores:
        overall_score = sum(scores.values()) / len(scores)
    else:
        overall_score = response.get("overall_score", 0.0)

    return HypothesisReview(
        review_summary=response.get("review_summary", ""),
        scores=scores,
        safety_ethical_concerns=response.get("safety_ethical_concerns", ""),
        detailed_feedback=response.get("detailed_feedback", {}),
        constructive_feedback=response.get("constructive_feedback", ""),
        overall_score=overall_score,
    )


async def review_parallel_individual(
    hypotheses: List[Hypothesis],
    research_goal: str,
    model_name: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    meta_review: Dict[str, Any] | None = None,
    run_id: str | None = None,
    tool_registry: Any | None = None,
) -> List[HypothesisReview]:
    """
    Review hypotheses in parallel (original approach).

    Each hypothesis is reviewed independently without seeing others.
    Fast but may produce similar scores for high-quality hypotheses.

    Args:
        hypotheses: List of hypotheses to review
        research_goal: Research goal for context
        model_name: LLM model to use
        run_id: Optional run ID for saving prompts

    Returns:
        List of reviews (one per hypothesis)
    """
    review_tasks = [
        review_single_hypothesis(
            hypothesis_text=format_hypothesis_with_evidence(hyp),
            research_goal=research_goal,
            model_name=model_name,
            supervisor_guidance=supervisor_guidance,
            meta_review=meta_review,
            run_id=run_id,
            hypothesis_index=i,
            tool_registry=tool_registry,
        )
        for i, hyp in enumerate(hypotheses)
    ]

    return await asyncio.gather(*review_tasks)


async def review_comparative_batch(
    hypotheses: List[Hypothesis],
    research_goal: str,
    model_name: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    meta_review: Dict[str, Any] | None = None,
    run_id: str | None = None,
    tool_registry: Any | None = None,
) -> List[HypothesisReview]:
    """
    Review hypotheses in a single comparative batch.

    All hypotheses are shown to one LLM call for relative comparison.
    Produces more differentiated scores but limited by token constraints.

    Args:
        hypotheses: List of hypotheses to review
        research_goal: Research goal for context
        model_name: LLM model to use
        run_id: Optional run ID for saving prompts

    Returns:
        List of reviews (one per hypothesis)
    """
    # Format hypotheses for batch review
    hypotheses_list = "\n\n".join(
        [
            f"**Hypothesis {i}:**\n{format_hypothesis_with_evidence(hyp)}"
            for i, hyp in enumerate(hypotheses)
        ]
    )

    # Call batch review
    prompt, schema = get_review_batch_prompt(
        research_goal=research_goal,
        hypotheses_list=hypotheses_list,
        supervisor_guidance=supervisor_guidance,
        meta_review=meta_review,
        tool_registry=tool_registry,
    )

    # save prompt to disk for debugging
    if run_id:
        from ..prompts import save_prompt_to_disk

        scaled_max_tokens = min(THINKING_MAX_TOKENS + (max(0, len(hypotheses) - 5) * 1500), 24000)
        save_prompt_to_disk(
            run_id=run_id,
            prompt_name="review_batch",
            content=prompt,
            metadata={
                "hypotheses_count": len(hypotheses),
                "scaled_max_tokens": scaled_max_tokens,
                "prompt_length_chars": len(prompt),
            },
        )
        logger.debug(f"saved batch review prompt to .coscientist_prompts/{run_id}/review_batch.txt")

    # scale max_tokens based on hypothesis count in batch
    # base: 18000 (THINKING_MAX_TOKENS), add 1500 per hypothesis beyond 5
    hypothesis_count = len(hypotheses)
    scaled_max_tokens = min(
        THINKING_MAX_TOKENS + (max(0, hypothesis_count - 5) * 1500),
        24000,  # reasonable upper limit for batch review
    )

    logger.debug(f"batch review: {hypothesis_count} hypotheses, max_tokens={scaled_max_tokens}")

    response = await call_llm_json(
        prompt=prompt,
        model_name=model_name,
        max_tokens=scaled_max_tokens,
        temperature=HIGH_TEMPERATURE,
        json_schema=schema,
        max_attempts=7 if hypothesis_count > 10 else 5,  # increase retries for large batches
    )

    # extract reviews from response
    reviews_data = response.get("reviews", [])

    # debug logging
    logger.info(f"Batch review response keys: {list(response.keys())}")
    logger.info(
        f"Reviews data type: {type(reviews_data)}, length: {len(reviews_data) if isinstance(reviews_data, list) else 'N/A'}"
    )
    logger.info(f"Expected {len(hypotheses)} reviews, received {len(reviews_data)}")

    if len(reviews_data) != len(hypotheses):
        logger.error(
            f"MISMATCH: Expected {len(hypotheses)} reviews but got {len(reviews_data)}. "
            f"This indicates the LLM may have hit output token limits or failed to generate all reviews. "
            f"Check the saved prompt at .coscientist_prompts/{run_id}/review_batch.txt"
        )

    # Convert to HypothesisReview objects
    reviews = []
    for i in range(len(hypotheses)):
        if i < len(reviews_data):
            review_data = reviews_data[i]
            scores = review_data.get("scores", {})

            # Calculate overall score from criterion scores
            if scores:
                overall_score = sum(scores.values()) / len(scores)
            else:
                overall_score = 0.0

            review = HypothesisReview(
                review_summary=review_data.get("review_summary", ""),
                scores=scores,
                safety_ethical_concerns=review_data.get("safety_ethical_concerns", ""),
                detailed_feedback=review_data.get("detailed_feedback", {}),
                constructive_feedback=review_data.get("constructive_feedback", ""),
                overall_score=overall_score,
            )
            reviews.append(review)
        else:
            # missing review - create empty one
            logger.error(f"No review data for hypothesis {i}")
            reviews.append(
                HypothesisReview(
                    review_summary="Review unavailable",
                    scores={},
                    safety_ethical_concerns="",
                    detailed_feedback={},
                    constructive_feedback="",
                    overall_score=0.0,
                )
            )

    return reviews


async def review_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Review all hypotheses using adaptive strategy.

    Strategy selection:
    - Small batches (≤5): Comparative batch review for differentiated scores
    - Large batches (>5): Parallel individual reviews for scalability

    Args:
        state: Current workflow state

    Returns:
        Dictionary with updated state fields
    """
    logger.info("Starting review node")

    hypotheses = state["hypotheses"]
    num_hypotheses = len(hypotheses)

    logger.info(f"Reviewing {num_hypotheses} hypotheses")

    # Choose strategy based on count
    use_comparative = num_hypotheses <= COMPARATIVE_BATCH_THRESHOLD

    if use_comparative:
        logger.info(
            f"Reviewing {num_hypotheses} hypotheses via comparative batch (≤{COMPARATIVE_BATCH_THRESHOLD})"
        )
        strategy_name = "comparative batch"
    else:
        logger.info(
            f"Reviewing {num_hypotheses} hypotheses via parallel individual (>{COMPARATIVE_BATCH_THRESHOLD})"
        )
        strategy_name = "parallel"

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "review_start",
            {
                "message": f"Reviewing {num_hypotheses} hypotheses...",
                "progress": PROGRESS_REVIEW_START,
            },
        )

    # Get supervisor guidance and meta_review from state
    supervisor_guidance = augment_review_supervisor_guidance(
        state.get("supervisor_guidance"),
        state.get("memory_context"),
        state.get("user_feedback"),
        state.get("memory_prompt_packet"),
    )
    meta_review = state.get("meta_review")

    # Execute chosen strategy
    tool_registry = state.get("tool_registry")

    if use_comparative:
        reviews = await review_comparative_batch(
            hypotheses=hypotheses,
            research_goal=state["research_goal"],
            model_name=state["model_name"],
            supervisor_guidance=supervisor_guidance,
            meta_review=meta_review,
            run_id=state.get("run_id"),
            tool_registry=tool_registry,
        )
        llm_calls = 1  # Single batch call
    else:
        reviews = await review_parallel_individual(
            hypotheses=hypotheses,
            research_goal=state["research_goal"],
            model_name=state["model_name"],
            supervisor_guidance=supervisor_guidance,
            meta_review=meta_review,
            run_id=state.get("run_id"),
            tool_registry=tool_registry,
        )
        llm_calls = num_hypotheses  # One call per hypothesis

    # validate reviews before continuing
    invalid_reviews = [i for i, r in enumerate(reviews) if r.review_summary == "Review unavailable"]
    if invalid_reviews:
        error_msg = f"review node failed: {len(invalid_reviews)}/{len(reviews)} reviews invalid"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Attach reviews to hypotheses
    for hypothesis, review in zip(hypotheses, reviews):
        hypothesis.reviews.append(review)
        hypothesis.score = review.overall_score

    logger.info(f"Completed {len(reviews)} reviews using {strategy_name} strategy")

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "review_complete",
            {
                "message": f"Completed {len(reviews)} reviews",
                "progress": PROGRESS_REVIEW_COMPLETE,
                "reviews_count": len(reviews),
            },
        )

    # Update metrics (deltas only, merge_metrics will add to existing state)
    metrics = create_metrics_update(reviews_count_delta=len(reviews), llm_calls_delta=llm_calls)
    logger.debug(
        f"review node creating metrics delta: reviews={len(reviews)}, llm_calls={llm_calls}"
    )

    return {
        "hypotheses": hypotheses,
        "metrics": metrics,
        "messages": [
            {
                "role": "assistant",
                "content": f"Reviewed {len(reviews)} hypotheses ({strategy_name})",
                "metadata": {"phase": "review", "strategy": strategy_name},
            }
        ],
    }
