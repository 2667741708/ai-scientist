"""
Ranking node - Elo-based pairwise comparison of hypotheses.
"""

import asyncio
import hashlib
import logging
import math
import re
from copy import deepcopy
from itertools import combinations
from typing import Any, Dict, List, Tuple

from ..constants import (
    INITIAL_ELO_RATING,
    ELO_K_FACTOR,
    THINKING_MAX_TOKENS,
    LOW_TEMPERATURE,
    MAX_CONCURRENT_LLM_CALLS,
)
from ..llm import call_llm_json
from ..models import Hypothesis, create_metrics_update
from ..prompts import get_ranking_prompt
from ..state import WorkflowState
from .evidence_grounding import format_hypothesis_with_evidence

logger = logging.getLogger(__name__)

# Semaphore to limit concurrent LLM calls (avoid rate limits)
_ranking_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)


def hypothesis_identifier(hypothesis: Hypothesis) -> str:
    """Return a stable audit identifier for a hypothesis."""
    digest = hashlib.sha1(hypothesis.text.encode("utf-8")).hexdigest()[:10].upper()
    return f"HYP-{digest}"


def confidence_to_score(confidence_level: str | None) -> float:
    """Convert the judge's qualitative confidence into a compact audit score."""
    normalized = (confidence_level or "").strip().lower()
    if normalized == "high":
        return 0.85
    if normalized == "medium":
        return 0.6
    if normalized == "low":
        return 0.35
    return 0.0


def _hypothesis_newness_score(hypothesis: Hypothesis) -> float:
    """Approximate the paper's newer-hypothesis priority with local metadata."""
    method = (hypothesis.generation_method or "").lower()
    if hypothesis.evolution_history or "evol" in method or "new" in method:
        return 1.0
    if hypothesis.debate_id is not None:
        return 0.5
    return 0.0


def _token_similarity(text_a: str, text_b: str) -> float:
    tokens_a = set(re.findall(r"[A-Za-z0-9_]+", text_a.lower()))
    tokens_b = set(re.findall(r"[A-Za-z0-9_]+", text_b.lower()))
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _similarity_priority(hypothesis_a: Hypothesis, hypothesis_b: Hypothesis) -> float:
    cluster_a = hypothesis_a.similarity_cluster_id
    cluster_b = hypothesis_b.similarity_cluster_id
    if cluster_a and cluster_b and cluster_a == cluster_b:
        return 2.0
    return _token_similarity(hypothesis_a.text, hypothesis_b.text)


def _top_ranked_cutoff(hypothesis_count: int) -> int:
    return max(2, min(5, math.ceil(hypothesis_count * 0.4)))


def _comparison_mode(
    hypothesis_a: Hypothesis,
    hypothesis_b: Hypothesis,
    index_by_object: Dict[int, int],
    hypothesis_count: int,
) -> Tuple[str, int]:
    top_cutoff = _top_ranked_cutoff(hypothesis_count)
    if (
        index_by_object[id(hypothesis_a)] < top_cutoff
        and index_by_object[id(hypothesis_b)] < top_cutoff
    ):
        return "debate", 3
    return "single_turn", 0


def _pair_priority(
    hypothesis_a: Hypothesis,
    hypothesis_b: Hypothesis,
    index_by_object: Dict[int, int],
    hypothesis_count: int,
) -> Dict[str, float]:
    index_a = index_by_object[id(hypothesis_a)]
    index_b = index_by_object[id(hypothesis_b)]
    top_ranked = ((hypothesis_count - index_a) + (hypothesis_count - index_b)) / (
        2 * hypothesis_count
    )
    newer = (_hypothesis_newness_score(hypothesis_a) + _hypothesis_newness_score(hypothesis_b)) / 2
    proximity = _similarity_priority(hypothesis_a, hypothesis_b)
    return {
        "proximity": round(proximity, 3),
        "newer_hypotheses": round(newer, 3),
        "top_ranked": round(top_ranked, 3),
    }


def _pair_sort_key(
    pair: Tuple[Hypothesis, Hypothesis],
    index_by_object: Dict[int, int],
    hypothesis_count: int,
    seed_string: str,
) -> Tuple[float, float, float, str]:
    hypothesis_a, hypothesis_b = pair
    priority = _pair_priority(hypothesis_a, hypothesis_b, index_by_object, hypothesis_count)
    pair_seed = "|".join(
        sorted([hypothesis_identifier(hypothesis_a), hypothesis_identifier(hypothesis_b)])
    )
    tiebreaker = hashlib.md5(f"{seed_string}:{pair_seed}".encode()).hexdigest()
    return (
        -priority["proximity"],
        -priority["newer_hypotheses"],
        -priority["top_ranked"],
        tiebreaker,
    )


def _short_ranking_guidance(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."


_RANKING_PACKET_FIELDS = (
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


def _ranking_key_area_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if str(value or "").strip():
        return [str(value).strip()]
    return []


def augment_ranking_supervisor_guidance(
    supervisor_guidance: Dict[str, Any] | None,
    memory_prompt_packet: Any,
) -> Dict[str, Any] | None:
    if not isinstance(memory_prompt_packet, dict):
        return supervisor_guidance
    sections = memory_prompt_packet.get("sections")
    if not isinstance(sections, list):
        return supervisor_guidance

    memory_key_areas: List[str] = []
    for section in sections[:6]:
        if not isinstance(section, dict):
            continue
        section_name = _short_ranking_guidance(section.get("section") or "memory_section", 80)
        items = section.get("items") if isinstance(section.get("items"), list) else []
        for item in items[:2]:
            if not isinstance(item, dict):
                continue
            fields: List[str] = []
            for key in _RANKING_PACKET_FIELDS:
                value = item.get(key)
                if value in (None, "", []):
                    continue
                if isinstance(value, list):
                    value = ", ".join(_short_ranking_guidance(entry, 80) for entry in value[:4])
                fields.append(f"{key}={_short_ranking_guidance(value, 160)}")
            if fields:
                memory_key_areas.append(
                    f"[memory_prompt_packet] section={section_name}; "
                    f"{'; '.join(fields[:8])}."
                )

    if not memory_key_areas:
        return supervisor_guidance

    augmented = deepcopy(supervisor_guidance) if isinstance(supervisor_guidance, dict) else {}
    goal_analysis = dict(augmented.get("research_goal_analysis") or {})
    key_areas = _ranking_key_area_list(goal_analysis.get("key_areas"))
    key_areas.extend(memory_key_areas)
    key_areas.append(
        "[memory_prompt_packet_policy] Use summary-only memory packet fields as ranking context; "
        "do not expose checkpoint refs, raw tool payloads, provider payloads, or internal ids."
    )
    goal_analysis["key_areas"] = key_areas
    augmented["research_goal_analysis"] = goal_analysis
    return augmented


def calculate_tournament_rounds(hypothesis_count: int) -> int:
    """Choose a bounded tournament size while keeping small pools exhaustive."""
    if hypothesis_count < 2:
        return 0
    total_unique_pairs = hypothesis_count * (hypothesis_count - 1) // 2
    if hypothesis_count <= 6:
        return total_unique_pairs
    return min(total_unique_pairs, max(hypothesis_count, hypothesis_count * 2))


def build_tournament_pairings(
    hypotheses: List[Hypothesis],
    seed_string: str,
    max_rounds: int | None = None,
) -> List[Tuple[Hypothesis, Hypothesis]]:
    """
    Build deterministic tournament pairings that match the paper-derived priorities.

    The scheduler prefers similar, newer, and top-ranked hypotheses, while ensuring every
    hypothesis competes at least once when the tournament budget allows it.
    """
    if len(hypotheses) < 2:
        return []

    index_by_object = {id(hypothesis): index for index, hypothesis in enumerate(hypotheses)}
    total_unique_pairs = len(hypotheses) * (len(hypotheses) - 1) // 2
    rounds = max_rounds or calculate_tournament_rounds(len(hypotheses))
    rounds = min(rounds, total_unique_pairs)

    candidate_pairs = list(combinations(hypotheses, 2))
    candidate_pairs.sort(
        key=lambda pair: _pair_sort_key(pair, index_by_object, len(hypotheses), seed_string)
    )

    selected_pairs: List[Tuple[Hypothesis, Hypothesis]] = []
    selected_keys: set[Tuple[str, str]] = set()
    covered: set[int] = set()

    def add_pair(pair: Tuple[Hypothesis, Hypothesis]) -> None:
        key = tuple(sorted([hypothesis_identifier(pair[0]), hypothesis_identifier(pair[1])]))
        if key in selected_keys or len(selected_pairs) >= rounds:
            return
        selected_pairs.append(pair)
        selected_keys.add(key)
        covered.add(id(pair[0]))
        covered.add(id(pair[1]))

    for pair in candidate_pairs:
        if len(covered) == len(hypotheses):
            break
        if id(pair[0]) not in covered or id(pair[1]) not in covered:
            add_pair(pair)

    for pair in candidate_pairs:
        if len(selected_pairs) >= rounds:
            break
        add_pair(pair)

    return selected_pairs


def calculate_elo_update(
    winner_elo: int, loser_elo: int, k_factor: int = ELO_K_FACTOR
) -> Tuple[int, int]:
    """
    Calculate updated Elo ratings for winner and loser.

    Args:
        winner_elo: Current Elo rating of winner
        loser_elo: Current Elo rating of loser
        k_factor: K-factor for Elo calculation (default 24)

    Returns:
        Tuple of (new_winner_elo, new_loser_elo)
    """
    # Calculate expected scores
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_loser = 1 / (1 + 10 ** ((winner_elo - loser_elo) / 400))

    # Calculate new ratings
    new_winner_elo = winner_elo + k_factor * (1 - expected_winner)
    new_loser_elo = loser_elo + k_factor * (0 - expected_loser)

    return int(new_winner_elo), int(new_loser_elo)


async def judge_matchup(
    hypothesis_a: Hypothesis,
    hypothesis_b: Hypothesis,
    research_goal: str,
    model_name: str,
    supervisor_guidance: Dict[str, Any] | None = None,
    run_id: str | None = None,
    matchup_index: int | None = None,
    tool_registry: Any | None = None,
    comparison_mode: str = "single_turn",
    debate_turns_requested: int = 0,
) -> Tuple[str, Dict[str, Any]]:
    """
    Have LLM judge which hypothesis is superior.

    Args:
        hypothesis_a: First hypothesis
        hypothesis_b: Second hypothesis
        research_goal: Research goal for context
        model_name: LLM model to use

    Returns:
        Tuple of (winner, full_response) where winner is "a" or "b"
    """
    # Extract review data if available
    review_a = None
    review_b = None
    if hypothesis_a.reviews:
        latest_review_a = hypothesis_a.reviews[-1]
        review_a = {
            "scores": latest_review_a.scores,
            "overall_score": latest_review_a.overall_score,
        }
    if hypothesis_b.reviews:
        latest_review_b = hypothesis_b.reviews[-1]
        review_b = {
            "scores": latest_review_b.scores,
            "overall_score": latest_review_b.overall_score,
        }

    # Extract reflection notes if available
    reflection_notes_a = hypothesis_a.reflection_notes
    reflection_notes_b = hypothesis_b.reflection_notes

    logger.debug("\n→ Ranking Tournament Matchup")

    if reflection_notes_a:
        # extract classification from notes
        classification_a = "unknown"
        if "Classification:" in reflection_notes_a:
            classification_a = (
                reflection_notes_a.split("Classification:")[-1].strip().split("\n")[0]
            )
        logger.debug(
            f"hypothesis A: has reflection ({len(reflection_notes_a)} chars, classification: {classification_a})"
        )
        logger.debug(f"hypothesis A reflection: {reflection_notes_a[:200]}...")
    else:
        logger.debug("hypothesis A: missing reflection notes")

    if reflection_notes_b:
        # extract classification from notes
        classification_b = "unknown"
        if "Classification:" in reflection_notes_b:
            classification_b = (
                reflection_notes_b.split("Classification:")[-1].strip().split("\n")[0]
            )
        logger.debug(
            f"hypothesis B: has reflection ({len(reflection_notes_b)} chars, classification: {classification_b})"
        )
        logger.debug(f"hypothesis B reflection: {reflection_notes_b[:200]}...")
    else:
        logger.debug("hypothesis B: missing reflection notes")

    prompt, schema = get_ranking_prompt(
        research_goal=research_goal,
        hypothesis_a=format_hypothesis_with_evidence(hypothesis_a),
        hypothesis_b=format_hypothesis_with_evidence(hypothesis_b),
        supervisor_guidance=supervisor_guidance,
        review_a=review_a,
        review_b=review_b,
        reflection_notes_a=reflection_notes_a,
        reflection_notes_b=reflection_notes_b,
        tool_registry=tool_registry,
        comparison_mode=comparison_mode,
        debate_turns_requested=debate_turns_requested,
    )

    # save prompt to disk for debugging
    if run_id:
        from ..prompts import save_prompt_to_disk

        filename = (
            f"ranking_matchup_{matchup_index}" if matchup_index is not None else "ranking_matchup"
        )
        save_prompt_to_disk(
            run_id=run_id,
            prompt_name=filename,
            content=prompt,
            metadata={
                "matchup_index": matchup_index,
                "prompt_length_chars": len(prompt),
                "has_reflection_a": bool(reflection_notes_a),
                "has_reflection_b": bool(reflection_notes_b),
                "comparison_mode": comparison_mode,
                "debate_turns_requested": debate_turns_requested,
            },
        )

    if reflection_notes_a or reflection_notes_b:
        if "Reflection Notes" in prompt:
            logger.debug("prompt includes 'Reflection Notes' section")
        else:
            logger.debug("warning: Reflection notes provided but not found in prompt")

    # Use semaphore to limit concurrent calls (avoid rate limits)
    async with _ranking_semaphore:
        response = await call_llm_json(
            prompt=prompt,
            model_name=model_name,
            max_tokens=THINKING_MAX_TOKENS,
            temperature=LOW_TEMPERATURE,
            json_schema=schema,
        )

    winner = response.get("winner", "a").lower()
    if winner not in ["a", "b"]:
        logger.warning(f"Invalid winner '{winner}', defaulting to 'a'")
        winner = "a"

    return winner, response


async def ranking_node(state: WorkflowState) -> Dict[str, Any]:
    """
    Run tournament-style pairwise comparisons with Elo rating updates.

    This node runs multiple rounds of random pairwise matchups where an LLM
    judges which hypothesis is superior. Elo ratings are updated after each
    matchup to reflect relative quality.

    Tournament rounds are unique pairwise comparisons. Small pools are exhaustive;
    larger pools are bounded while prioritizing similar, newer, and top-ranked hypotheses.

    deterministic seeding: the random pairings are seeded using research_goal
    and current_iteration to ensure cache consistency across runs. this allows
    identical inputs to produce identical tournament results, enabling proper
    cache hits in subsequent iterations.

    Args:
        state: Current workflow state

    Returns:
        Dictionary with updated state fields (hypotheses sorted by Elo)
    """
    hypotheses = state["hypotheses"]
    logger.info(f"Starting ranking tournament with {len(hypotheses)} hypotheses")

    hypotheses_with_reflection = sum(1 for h in hypotheses if h.reflection_notes)
    logger.debug("\n=== ranking tournament debug ===")
    logger.debug(f"total hypotheses: {len(hypotheses)}")
    logger.debug(
        f"hypotheses with reflection notes: {hypotheses_with_reflection}/{len(hypotheses)}"
    )

    if hypotheses_with_reflection == 0:
        logger.debug("warning: No hypotheses have reflection notes!")
    elif hypotheses_with_reflection < len(hypotheses):
        logger.debug("warning: Some hypotheses missing reflection notes")
    else:
        logger.debug("all hypotheses have reflection notes")

    if len(hypotheses) < 2:
        logger.warning("Need at least 2 hypotheses for tournament")
        return {"hypotheses": hypotheses}

    # Sort hypotheses by review score before tournament
    # This provides initial ordering based on review scores
    # Use hypothesis text as tiebreaker for deterministic ordering when scores are equal
    hypotheses.sort(key=lambda h: (h.score, h.text), reverse=True)
    logger.info(f"Sorted hypotheses by review score (top score: {hypotheses[0].score:.2f})")

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "tournament_start",
            {"message": f"Running tournament with {len(hypotheses)} hypotheses...", "progress": 65},
        )

    # Initialize Elo ratings if not already set
    for hyp in hypotheses:
        if hyp.elo_rating == INITIAL_ELO_RATING:  # Default value from dataclass
            hyp.elo_rating = INITIAL_ELO_RATING

    # Get supervisor guidance and tool registry from state
    supervisor_guidance = augment_ranking_supervisor_guidance(
        state.get("supervisor_guidance"),
        state.get("memory_prompt_packet"),
    )
    tool_registry = state.get("tool_registry")

    # Set deterministic pair scheduling context based on research goal and iteration.
    # This ensures same inputs produce same tournament pairings for cache consistency.
    research_goal = state["research_goal"]
    current_iteration = state.get("current_iteration", 0)
    seed_string = f"{research_goal}_{current_iteration}"

    # Prepare prioritized, non-duplicated pairwise matchups and judge them in parallel
    pairings = build_tournament_pairings(hypotheses, seed_string=seed_string)
    tournament_rounds = len(pairings)
    logger.info(f"Running {tournament_rounds} tournament rounds")
    index_by_object = {id(hypothesis): index for index, hypothesis in enumerate(hypotheses)}

    results = await asyncio.gather(
        *[
            judge_matchup(
                a,
                b,
                state["research_goal"],
                state["model_name"],
                supervisor_guidance,
                run_id=state.get("run_id"),
                matchup_index=i,
                tool_registry=tool_registry,
                comparison_mode=_comparison_mode(a, b, index_by_object, len(hypotheses))[0],
                debate_turns_requested=_comparison_mode(a, b, index_by_object, len(hypotheses))[1],
            )
            for i, (a, b) in enumerate(pairings)
        ]
    )

    # Apply Elo updates based on judged results and collect matchup details
    llm_calls = tournament_rounds
    matchup_details = []

    for matchup_number, ((hyp_a, hyp_b), (winner, response)) in enumerate(
        zip(pairings, results), start=1
    ):
        winner_hyp, loser_hyp = (hyp_a, hyp_b) if winner == "a" else (hyp_b, hyp_a)
        loser = "b" if winner == "a" else "a"
        old_a_elo = hyp_a.elo_rating
        old_b_elo = hyp_b.elo_rating
        old_winner_elo = winner_hyp.elo_rating
        old_loser_elo = loser_hyp.elo_rating

        new_winner_elo, new_loser_elo = calculate_elo_update(
            winner_elo=winner_hyp.elo_rating,
            loser_elo=loser_hyp.elo_rating,
            k_factor=ELO_K_FACTOR
        )
        logger.debug(
            f"Matchup result: Winner {winner_hyp.elo_rating} → {new_winner_elo}, "
            f"Loser {loser_hyp.elo_rating} → {new_loser_elo}"
        )

        # Store matchup details for display
        # Extract reasoning from response (can be decision_summary or judgment_explanation)
        reasoning = response.get("decision_summary", "")
        if not reasoning and "judgment_explanation" in response:
            # Fallback: combine judgment details if decision_summary is missing
            judgment = response["judgment_explanation"]
            reasoning = " | ".join([f"{k}: {v}" for k, v in judgment.items() if v])
        if not reasoning:
            reasoning = "No reasoning provided"

        hypothesis_a_id = hypothesis_identifier(hyp_a)
        hypothesis_b_id = hypothesis_identifier(hyp_b)
        winner_id = hypothesis_identifier(winner_hyp)
        loser_id = hypothesis_identifier(loser_hyp)
        confidence_level = response.get("confidence_level", "Unknown")
        comparison_mode, debate_turns_requested = _comparison_mode(
            hyp_a, hyp_b, index_by_object, len(hypotheses)
        )
        priority = _pair_priority(hyp_a, hyp_b, index_by_object, len(hypotheses))
        after_a_elo = new_winner_elo if winner == "a" else new_loser_elo
        after_b_elo = new_winner_elo if winner == "b" else new_loser_elo

        matchup_details.append(
            {
                "matchup_id": f"matchup-{matchup_number:03d}",
                "round": matchup_number,
                "hypothesis_a": hyp_a.text[:200] + "..." if len(hyp_a.text) > 200 else hyp_a.text,
                "hypothesis_b": hyp_b.text[:200] + "..." if len(hyp_b.text) > 200 else hyp_b.text,
                "hypothesis_a_id": hypothesis_a_id,
                "hypothesis_b_id": hypothesis_b_id,
                "winner": winner,
                "loser": loser,
                "winner_id": winner_id,
                "loser_id": loser_id,
                "winner_label": "Hypothesis A" if winner == "a" else "Hypothesis B",
                "loser_label": "Hypothesis B" if winner == "a" else "Hypothesis A",
                "reasoning": reasoning,
                "confidence": confidence_level,
                "confidence_level": confidence_level,
                "confidence_score": confidence_to_score(confidence_level),
                "comparison_mode": comparison_mode,
                "debate_turns_requested": debate_turns_requested,
                "pairing_priority": priority,
                "before_elo": {
                    hypothesis_a_id: old_a_elo,
                    hypothesis_b_id: old_b_elo,
                },
                "after_elo": {
                    hypothesis_a_id: after_a_elo,
                    hypothesis_b_id: after_b_elo,
                },
                "elo_delta": {
                    winner_id: new_winner_elo - old_winner_elo,
                    loser_id: new_loser_elo - old_loser_elo,
                },
                "winner_elo_before": old_winner_elo,
                "winner_elo_after": new_winner_elo,
                "winner_elo_delta": new_winner_elo - old_winner_elo,
                "loser_elo_before": old_loser_elo,
                "loser_elo_after": new_loser_elo,
                "loser_elo_delta": new_loser_elo - old_loser_elo,
                "debate_trace": response.get("debate_trace", []),
            }
        )

        winner_hyp.elo_rating = new_winner_elo
        loser_hyp.elo_rating = new_loser_elo
        winner_hyp.win_count += 1
        loser_hyp.loss_count += 1

    # Sort hypotheses by Elo rating (highest first)
    # Use hypothesis text as tiebreaker for deterministic ordering when Elo ratings are equal
    hypotheses.sort(key=lambda h: (h.elo_rating, h.text), reverse=True)

    logger.info(f"Tournament complete. Top Elo: {hypotheses[0].elo_rating}")
    logger.info(f"Top hypothesis: {hypotheses[0].text[:100]}...")

    # Emit progress
    if state.get("progress_callback"):
        await state["progress_callback"](
            "tournament_complete",
            {
                "message": f"Tournament complete ({tournament_rounds} rounds)",
                "progress": 80,
                "top_elo": hypotheses[0].elo_rating,
                "top_hypothesis": hypotheses[0].text[:200],
            },
        )

    # Update metrics (deltas only, merge_metrics will add to existing state)
    metrics = create_metrics_update(
        llm_calls_delta=llm_calls, tournaments_count_delta=tournament_rounds
    )
    logger.debug(
        f"ranking node creating metrics delta: tournaments={tournament_rounds}, llm_calls={llm_calls}"
    )

    return {
        "hypotheses": hypotheses,  # Now sorted by Elo rating
        "tournament_matchups": matchup_details,
        "metrics": metrics,
        "messages": [
            {
                "role": "assistant",
                "content": f"Completed {tournament_rounds} tournament rounds",
                "metadata": {
                    "phase": "ranking",
                    "rounds": tournament_rounds,
                    "top_elo": hypotheses[0].elo_rating,
                },
            }
        ],
    }
