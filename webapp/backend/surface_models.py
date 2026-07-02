from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping, Optional


HYPOTHESIS_ORIGIN_LABELS = {
    "user_seeded": "user seeded",
    "model_generated": "model generated",
    "evolved": "evolved",
    "tool_generated": "tool grounded",
    "tool_grounded": "tool grounded",
}


RUN_STATUS_LABELS = {
    "queued": "Queued",
    "pending": "Pending",
    "running": "Running",
    "complete": "Complete",
    "completed": "Complete",
    "error": "Error",
    "failed": "Error",
    "cancelled": "Cancelled",
    "stale": "Needs recovery",
}


def run_surface_summary(
    run: Any,
    *,
    work_item_snapshot: Optional[Mapping[str, Any]] = None,
    memory_summary: Optional[Mapping[str, Any]] = None,
    recovery_policy: Optional[Mapping[str, Any]] = None,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    source = _as_mapping(run)
    request = _as_mapping(source.get("request"))
    metrics = _as_mapping(source.get("metrics"))
    work_snapshot = _as_mapping(work_item_snapshot)
    memory = _as_mapping(memory_summary)
    recovery = _as_mapping(recovery_policy)
    status = str(source.get("status") or "unknown").strip() or "unknown"
    work_item = _first_work_item(work_snapshot)
    phase = str(
        _first_value(work_item, ("phase",))
        or _first_value(metrics, ("current_phase", "phase"))
        or source.get("current_phase")
        or ""
    ).strip()
    mode_boundary = _run_mode_boundary(request=request, metrics=metrics, memory_summary=memory)
    recoverable = _run_recoverable(status=status, work_item=work_item, recovery_policy=recovery)
    hypothesis_count = _list_length(source.get("hypotheses"))
    if hypothesis_count == 0:
        hypothesis_count = _safe_int(metrics.get("hypothesis_count")) or 0

    summary = {
        "status": status,
        "status_label": RUN_STATUS_LABELS.get(status, status.replace("_", " ").title()),
        "phase": phase or None,
        "phase_label": _phase_label(phase),
        "mode_boundary": mode_boundary,
        "recoverable": recoverable,
        "next_actions": _run_next_actions(status=status, recoverable=recoverable, mode_boundary=mode_boundary),
        "counts": {
            "hypotheses": hypothesis_count,
            "starting_hypotheses": _list_length(request.get("starting_hypotheses")),
            "user_feedback": _list_length(request.get("user_feedback")),
        },
        "queue": _run_queue_summary(work_snapshot, work_item),
        "memory": _run_memory_summary_for_surface(memory),
        "recovery": _run_recovery_summary(recovery),
        "created_at": source.get("created_at"),
        "updated_at": source.get("updated_at"),
        "visibility_boundary": (
            "Run surface summaries expose task state, mode boundary, queue counts, memory counts, "
            "and recovery guidance by default; raw request JSON, run IDs, work item IDs, checkpoint "
            "refs, and provider diagnostics require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "run_id": source.get("run_id"),
            "parent_run_id": request.get("parent_run_id"),
            "work_item_ids": [
                item.get("work_item_id")
                for item in (work_snapshot.get("items") if isinstance(work_snapshot.get("items"), list) else [])
                if isinstance(item, Mapping) and item.get("work_item_id")
            ],
            "checkpoint_id": _as_mapping(recovery.get("latest_checkpoint")).get("checkpoint_id")
            or recovery.get("checkpoint_id"),
        }
    return summary


def hypothesis_surface_summary(
    hypothesis: Any,
    *,
    index: Optional[int] = None,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    source = _as_mapping(hypothesis)
    origin = _canonical_origin(
        _first_value(source, ("origin", "source_origin", "hypothesis_origin"))
        or _infer_origin(source)
    )
    rank = _first_value(source, ("rank", "ranking", "position"))
    elo_rating = _first_value(source, ("elo_rating", "elo", "rating"))
    support_level = _first_value(source, ("support_level", "evidence_support_level", "grounding_status"))
    title = _first_text(source, ("title", "name"))
    technical_text = _first_text(source, ("technical_hypothesis", "hypothesis", "text"))
    plain_summary = _first_text(source, ("plain_explanation", "explanation", "summary", "rationale"))
    if not title:
        title = _title_from_text(plain_summary or technical_text or f"Hypothesis {index + 1 if index is not None else ''}")
    if not plain_summary:
        plain_summary = _compact_text(technical_text, max_length=220)

    summary = {
        "index": index,
        "title": title,
        "plain_summary": _compact_text(plain_summary, max_length=280),
        "origin": origin,
        "origin_label": HYPOTHESIS_ORIGIN_LABELS.get(origin, origin.replace("_", " ")),
        "rank": _safe_int(rank),
        "elo_rating": _safe_number(elo_rating),
        "support_level": str(support_level or "unknown"),
        "status": _hypothesis_status(source, support_level),
        "next_actions": _hypothesis_next_actions(source, support_level),
        "visibility_boundary": (
            "Hypothesis surface summaries expose scan-friendly title, summary, origin, ranking, "
            "support level, and next actions; full technical text, reviews, tournament payloads, "
            "and lineage refs require explicit detail disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "hypothesis_id": _first_value(source, ("id", "hypothesis_id")),
            "origin_evidence": _first_value(source, ("origin_evidence", "generation_method")),
            "evolution_history_count": _list_length(_first_value(source, ("evolution_history", "lineage"))),
            "citation_count": _citation_count(source),
        }
        summary["technical_text"] = _compact_text(technical_text, max_length=1400)
    return summary


def hypothesis_surface_collection(
    hypotheses: Iterable[Any],
    *,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    items = [
        hypothesis_surface_summary(
            hypothesis,
            index=index,
            include_internal_refs=include_internal_refs,
        )
        for index, hypothesis in enumerate(hypotheses or [])
    ]
    origin_counts: Dict[str, int] = {}
    support_counts: Dict[str, int] = {}
    for item in items:
        origin = str(item.get("origin") or "unknown")
        support = str(item.get("support_level") or "unknown")
        origin_counts[origin] = origin_counts.get(origin, 0) + 1
        support_counts[support] = support_counts.get(support, 0) + 1
    return {
        "hypothesis_count": len(items),
        "origin_counts": origin_counts,
        "support_level_counts": support_counts,
        "items": items,
        "visibility_boundary": (
            "Collection summary is safe for default hypothesis lists; raw reviews, citations, "
            "and tournament matchups remain behind per-hypothesis detail views."
        ),
    }


def evidence_surface_summary(
    evidence: Any,
    *,
    index: Optional[int] = None,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    source = _as_mapping(evidence)
    title = _first_text(source, ("source_title", "paper_title", "title", "document_title"))
    if not title:
        title = "Untitled evidence source"
    reliability = str(_first_value(source, ("source_reliability", "reliability")) or "unknown")
    support_level = str(_first_value(source, ("support_level", "verdict", "grounding_status")) or "unknown")
    snippet = _first_text(source, ("matched_snippet", "snippet", "text_preview", "text", "content"))
    experiment_summary = _first_text(source, ("experiment_data_summary", "experiment_summary", "benchmark_summary"))
    summary = {
        "index": index,
        "source_title": _compact_text(title, max_length=140),
        "support_level": support_level,
        "source_reliability": reliability,
        "status": _evidence_status(support_level=support_level, reliability=reliability),
        "matched_snippet_summary": _compact_text(snippet, max_length=360),
        "experiment_data_summary": _compact_text(experiment_summary, max_length=240),
        "source_type": str(_first_value(source, ("source", "source_type", "kind")) or "unknown"),
        "next_actions": _evidence_next_actions(support_level=support_level, reliability=reliability),
        "visibility_boundary": (
            "Evidence surface summaries expose source title, support level, reliability, and short snippets by default; "
            "chunk IDs, artifact paths, citation maps, and parser internals require explicit detail disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "paper_id": _first_value(source, ("paper_id", "source_id")),
            "chunk_id": _first_value(source, ("chunk_id", "evidence_chunk_id")),
            "library_id": _first_value(source, ("library_id",)),
            "parse_run_id": _first_value(source, ("parse_run_id",)),
            "artifact_path": _first_value(source, ("artifact_path", "media_path", "local_path")),
            "citation_count": _citation_count(source),
        }
    return summary


def evidence_surface_collection(
    evidence_items: Iterable[Any],
    *,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    items = [
        evidence_surface_summary(
            evidence,
            index=index,
            include_internal_refs=include_internal_refs,
        )
        for index, evidence in enumerate(evidence_items or [])
    ]
    support_counts: Dict[str, int] = {}
    reliability_counts: Dict[str, int] = {}
    for item in items:
        support = str(item.get("support_level") or "unknown")
        reliability = str(item.get("source_reliability") or "unknown")
        support_counts[support] = support_counts.get(support, 0) + 1
        reliability_counts[reliability] = reliability_counts.get(reliability, 0) + 1
    return {
        "evidence_count": len(items),
        "support_level_counts": support_counts,
        "source_reliability_counts": reliability_counts,
        "items": items,
        "boundary": _evidence_collection_boundary(items),
        "visibility_boundary": (
            "Evidence collection summaries are safe for default reference drawers; raw chunks, "
            "media paths, parser artifacts, and full citation maps remain in details."
        ),
    }


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    data = getattr(value, "model_dump", None)
    if callable(data):
        dumped = data()
        if isinstance(dumped, Mapping):
            return dumped
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}


def _first_value(source: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and value != "":
            return value
    return None


def _first_text(source: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    value = _first_value(source, keys)
    return str(value or "").strip()


def _canonical_origin(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized == "tool_grounded":
        return "tool_generated"
    if normalized in HYPOTHESIS_ORIGIN_LABELS:
        return normalized
    return "model_generated"


def _infer_origin(source: Mapping[str, Any]) -> str:
    method = str(_first_value(source, ("generation_method", "method", "source")) or "").lower()
    if any(marker in method for marker in ("user", "seed")):
        return "user_seeded"
    if any(marker in method for marker in ("evolve", "mutation", "refine", "revised")):
        return "evolved"
    if any(marker in method for marker in ("tool", "evidence", "literature", "ground")):
        return "tool_generated"
    if _list_length(_first_value(source, ("evolution_history", "lineage"))) > 0:
        return "evolved"
    return "model_generated"


def _hypothesis_status(source: Mapping[str, Any], support_level: Any) -> str:
    if _first_value(source, ("error", "error_message")):
        return "error"
    support = str(support_level or "").lower()
    if support in {"contradicted", "unsupported"}:
        return "needs_review"
    if support in {"limited", "ungrounded", "unknown", ""}:
        return "limited"
    return "ready"


def _hypothesis_next_actions(source: Mapping[str, Any], support_level: Any) -> list[str]:
    actions = ["inspect_evidence", "design_experiment", "add_feedback"]
    support = str(support_level or "").lower()
    if support in {"limited", "ungrounded", "unknown", ""}:
        actions.insert(1, "verify_evidence")
    if _list_length(_first_value(source, ("reviews", "review_feedback", "review"))) > 0:
        actions.append("inspect_review")
    return actions


def _title_from_text(value: str) -> str:
    compact = _compact_text(value, max_length=96)
    if not compact:
        return "Untitled hypothesis"
    sentence = re.split(r"(?<=[.!?])\s+", compact, maxsplit=1)[0].strip()
    return sentence or compact


def _compact_text(value: Any, *, max_length: int = 280) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 3].rstrip()}..."


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _list_length(value: Any) -> int:
    if isinstance(value, (list, tuple, set)):
        return len(value)
    if isinstance(value, Mapping):
        return len(value)
    return 1 if value else 0


def _citation_count(source: Mapping[str, Any]) -> int:
    citations = _first_value(source, ("citation_map", "citations", "evidence_links"))
    return _list_length(citations)


def _evidence_status(*, support_level: str, reliability: str) -> str:
    support = support_level.lower()
    source_reliability = reliability.lower()
    if support in {"contradicted", "unsupported"}:
        return "contradicted"
    if support in {"experimental_data", "supported"}:
        return "supported"
    if source_reliability == "parsed_fulltext" or support == "fulltext":
        return "supported"
    if support in {"limited", "abstract", "metadata", "unknown", "ungrounded", ""}:
        return "limited"
    return "limited"


def _evidence_next_actions(*, support_level: str, reliability: str) -> list[str]:
    actions = ["inspect_source"]
    status = _evidence_status(support_level=support_level, reliability=reliability)
    if status in {"limited", "contradicted"}:
        actions.append("verify_more_evidence")
    if reliability != "parsed_fulltext":
        actions.append("parse_fulltext")
    actions.append("use_in_experiment_design")
    return actions


def _evidence_collection_boundary(items: list[Dict[str, Any]]) -> Dict[str, Any]:
    if not items:
        return {
            "status": "absent",
            "summary": "No evidence has been attached to this surface.",
        }
    if any(item.get("status") == "contradicted" for item in items):
        return {
            "status": "contradicted",
            "summary": "At least one evidence item contradicts or fails to support the claim.",
        }
    if any(item.get("source_reliability") == "parsed_fulltext" for item in items):
        return {
            "status": "parsed_fulltext",
            "summary": "At least one source is backed by parsed fulltext evidence.",
        }
    return {
        "status": "limited",
        "summary": "Evidence is limited to metadata, abstract, snippets, or unparsed sources.",
    }


def _first_work_item(work_snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    items = work_snapshot.get("items")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, Mapping):
            return first
    return {}


def _run_mode_boundary(
    *,
    request: Mapping[str, Any],
    metrics: Mapping[str, Any],
    memory_summary: Mapping[str, Any],
) -> Dict[str, Any]:
    demo_mode = bool(request.get("demo_mode"))
    literature_review = bool(request.get("literature_review"))
    evidence_boundary = _as_mapping(memory_summary.get("evidence_boundary"))
    evidence_status = str(
        evidence_boundary.get("status")
        or _as_mapping(metrics.get("evidence_boundary")).get("status")
        or "absent"
    )
    if demo_mode:
        mode = "demo_only"
        label = "Demo simulation"
        scientific_claim_level = "not_scientific_evidence"
    elif literature_review or evidence_status in {"parsed_fulltext", "experimental_data"}:
        mode = "literature_grounded"
        label = "Literature-grounded"
        scientific_claim_level = "source_backed_limited_by_evidence"
    else:
        mode = "live_model"
        label = "Live model"
        scientific_claim_level = "model_without_literature_grounding"
    return {
        "mode": mode,
        "label": label,
        "evidence_status": evidence_status,
        "scientific_claim_level": scientific_claim_level,
    }


def _run_recoverable(
    *,
    status: str,
    work_item: Mapping[str, Any],
    recovery_policy: Mapping[str, Any],
) -> bool:
    if recovery_policy:
        return bool(recovery_policy.get("can_resume") or recovery_policy.get("should_retry"))
    work_status = str(work_item.get("status") or "")
    if work_status in {"queued", "leased", "running", "retrying", "blocked"}:
        return True
    return status in {"queued", "pending", "running", "stale"}


def _run_next_actions(
    *,
    status: str,
    recoverable: bool,
    mode_boundary: Mapping[str, Any],
) -> list[str]:
    if status in {"complete", "completed"}:
        actions = ["inspect_hypotheses", "inspect_evidence", "design_experiment"]
        if mode_boundary.get("mode") == "demo_only":
            actions.append("rerun_live_or_grounded")
        return actions
    if status in {"queued", "pending"}:
        return ["monitor_queue", "check_worker_status"]
    if status == "running":
        return ["monitor_progress", "view_process_summary"]
    if status in {"error", "failed", "stale"}:
        return ["resume_or_retry" if recoverable else "start_new_run", "inspect_failure_summary"]
    if status == "cancelled":
        return ["start_new_run"]
    return ["inspect_run"]


def _run_queue_summary(work_snapshot: Mapping[str, Any], work_item: Mapping[str, Any]) -> Dict[str, Any]:
    counts = _as_mapping(work_snapshot.get("counts"))
    return {
        "active_work_item_count": _safe_int(counts.get("active")) or 0,
        "queued_count": _safe_int(counts.get("queued")) or 0,
        "retrying_count": _safe_int(counts.get("retrying")) or 0,
        "running_count": _safe_int(counts.get("running")) or 0,
        "current_work_status": work_item.get("status"),
        "current_work_label": work_item.get("status_label"),
        "current_work_next_action": work_item.get("next_action"),
    }


def _run_memory_summary_for_surface(memory: Mapping[str, Any]) -> Dict[str, Any]:
    counts = _as_mapping(memory.get("counts"))
    execution_memory = _as_mapping(memory.get("execution_memory"))
    evidence_boundary = _as_mapping(memory.get("evidence_boundary"))
    return {
        "memory_scope": memory.get("memory_scope"),
        "memory_sources": list(memory.get("memory_sources") or []),
        "feedback_count": _safe_int(counts.get("user_feedback")) or 0,
        "prior_hypothesis_count": _safe_int(counts.get("prior_hypotheses")) or 0,
        "evidence_source_count": _safe_int(counts.get("evidence_sources")) or 0,
        "execution_memory_status": execution_memory.get("status"),
        "evidence_status": evidence_boundary.get("status"),
    }


def _run_recovery_summary(recovery: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "recovery_mode": recovery.get("recovery_mode"),
        "can_resume": bool(recovery.get("can_resume")),
        "should_retry": bool(recovery.get("should_retry")),
        "next_action": recovery.get("next_action"),
    }


def _phase_label(phase: str) -> Optional[str]:
    if not phase:
        return None
    return phase.replace("_", " ").title()
