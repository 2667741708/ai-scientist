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


def runtime_readiness_surface_summary(
    *,
    worker_status: Optional[Mapping[str, Any]] = None,
    execution_memory: Optional[Mapping[str, Any]] = None,
    service_statuses: Optional[Mapping[str, Any]] = None,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    worker = _as_mapping(worker_status)
    memory = _as_mapping(execution_memory)
    services = _service_surface_items(_as_mapping(service_statuses))
    queue_counts = _as_mapping(worker.get("queue_status_counts"))
    active_snapshot = _as_mapping(worker.get("active_work_item_snapshot"))
    active_counts = _as_mapping(active_snapshot.get("counts"))
    counts = {
        "active_work_items": _safe_int(active_counts.get("active") or queue_counts.get("active")) or 0,
        "queued": _safe_int(active_counts.get("queued") or queue_counts.get("queued")) or 0,
        "running": _safe_int(active_counts.get("running") or queue_counts.get("running")) or 0,
        "retrying": _safe_int(active_counts.get("retrying") or queue_counts.get("retrying")) or 0,
        "error": _safe_int(active_counts.get("error") or queue_counts.get("error")) or 0,
    }
    worker_enabled = bool(worker.get("enabled"))
    worker_state = _worker_readiness_state(worker_enabled=worker_enabled, counts=counts)
    execution_status = str(memory.get("status") or "not_available")
    service_counts = _service_counts(services)
    overall_status = _runtime_overall_status(
        worker_state=worker_state,
        execution_status=execution_status,
        service_counts=service_counts,
    )
    summary = {
        "status": overall_status,
        "worker": {
            "enabled": worker_enabled,
            "state": worker_state,
            "concurrency": _safe_int(worker.get("concurrency")) or 0,
            "running_count": _safe_int(worker.get("running_count")) or counts["running"],
            "queue_counts": counts,
            "guidance": _worker_guidance(worker_state),
        },
        "execution_memory": {
            "status": execution_status,
            "resume_supported": bool(memory.get("resume_supported")),
            "checkpoint_backend": memory.get("checkpoint_backend"),
            "resume_mode": memory.get("resume_mode"),
        },
        "services": services,
        "service_counts": service_counts,
        "next_actions": _runtime_next_actions(
            overall_status=overall_status,
            worker_state=worker_state,
            service_counts=service_counts,
            execution_status=execution_status,
        ),
        "visibility_boundary": (
            "Runtime readiness summaries expose worker state, queue counts, execution-memory state, "
            "service availability, and recovery actions by default; owner IDs, endpoints, environment "
            "variables, raw errors, and debug payloads require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "worker_owner": worker.get("owner"),
            "lease_seconds": worker.get("lease_seconds"),
            "poll_seconds": worker.get("poll_seconds"),
            "last_tick_at": worker.get("last_tick_at"),
            "last_error": worker.get("last_error"),
            "service_debug": {
                name: _as_mapping(status)
                for name, status in _as_mapping(service_statuses).items()
            },
        }
    return summary


def run_confirmation_surface_summary(
    request_preview: Any,
    *,
    parent_run_summary: Optional[Mapping[str, Any]] = None,
    memory_summary: Optional[Mapping[str, Any]] = None,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    request = _as_mapping(request_preview)
    memory = _as_mapping(memory_summary)
    parent = _as_mapping(parent_run_summary)
    starting_hypotheses = _as_list(request.get("starting_hypotheses"))
    user_feedback = [_as_mapping(item) for item in _as_list(request.get("user_feedback"))]
    constraints = [str(item).strip() for item in _as_list(request.get("constraints")) if str(item).strip()]
    attributes = [str(item).strip() for item in _as_list(request.get("attributes")) if str(item).strip()]
    preferences = str(request.get("preferences") or "").strip()
    research_goal = str(request.get("research_goal") or "").strip()
    refinement_mode = str(request.get("refinement_mode") or "new_run")
    has_parent = bool(request.get("parent_run_id") or parent)
    mode_boundary = _run_mode_boundary(request=request, metrics={}, memory_summary=memory)
    validity = _confirmation_validity(research_goal=research_goal, mode_boundary=mode_boundary)

    summary = {
        "research_goal": _compact_text(research_goal, max_length=360),
        "status": validity["status"],
        "blocking_issues": validity["blocking_issues"],
        "mode_boundary": mode_boundary,
        "refinement_mode": refinement_mode,
        "is_continuation": has_parent or refinement_mode in {"continue_from_run", "revise_hypotheses"},
        "counts": {
            "starting_hypotheses": len(starting_hypotheses),
            "constraints": len(constraints),
            "attributes": len(attributes),
            "user_feedback": len(user_feedback),
        },
        "starting_hypothesis_previews": _preview_list(starting_hypotheses, max_items=3, max_length=180),
        "constraint_previews": _preview_list(constraints, max_items=3, max_length=140),
        "preferences_summary": _compact_text(preferences, max_length=180),
        "attribute_previews": _preview_list(attributes, max_items=6, max_length=80),
        "feedback_summary": _feedback_surface_summary(user_feedback),
        "parent_run": _confirmation_parent_summary(parent),
        "memory": _run_memory_summary_for_surface(memory),
        "next_actions": _confirmation_next_actions(validity["status"], has_parent=has_parent),
        "visibility_boundary": (
            "Confirmation summaries expose the research goal, counts, short previews, mode boundary, "
            "and continuation context by default; raw request JSON, intent-router debug, parent IDs, "
            "and full feedback text require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "parent_run_id": request.get("parent_run_id") or parent.get("run_id"),
            "library_id": request.get("library_id"),
            "memory_scope": request.get("memory_scope"),
            "request_preview": dict(request),
        }
    return summary


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


def ranking_surface_summary(
    matchups: Optional[Iterable[Any]] = None,
    *,
    hypotheses: Optional[Iterable[Any]] = None,
    max_items: int = 8,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    matchup_records = _record_items(matchups)
    hypothesis_records = _record_items(hypotheses)
    items = [
        _ranking_matchup_surface_summary(matchup, index=index)
        for index, matchup in enumerate(matchup_records[:max(0, max_items)])
    ]
    status = _ranking_status(items, matchup_count=len(matchup_records))
    summary = {
        "status": status,
        "ranking_method": "pairwise_tournament_elo" if matchup_records else "not_available",
        "matchup_count": len(matchup_records),
        "displayed_matchup_count": len(items),
        "truncated_matchup_count": max(0, len(matchup_records) - len(items)),
        "items": items,
        "ranked_hypotheses": _ranking_hypothesis_summaries(hypothesis_records),
        "confidence": _ranking_confidence_summary(items),
        "next_actions": _ranking_next_actions(status),
        "visibility_boundary": (
            "Ranking surface summaries expose pairwise winners, losers, confidence, Elo before/after, "
            "delta, and short reasoning summaries by default; raw matchup payloads, matchup IDs, "
            "provider traces, and full tournament JSON require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "matchup_ids": [
                _first_value(matchup, ("matchup_id", "id"))
                for matchup in matchup_records
                if _first_value(matchup, ("matchup_id", "id"))
            ],
            "hypothesis_ids": [
                _first_value(hypothesis, ("id", "hypothesis_id"))
                for hypothesis in hypothesis_records
                if _first_value(hypothesis, ("id", "hypothesis_id"))
            ],
            "raw_matchups": [dict(matchup) for matchup in matchup_records],
        }
    return summary


def experiment_design_surface_summary(
    experiment: Any,
    *,
    evidence_items: Optional[Iterable[Any]] = None,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    source = _as_mapping(experiment)
    plan_text = _first_text(source, ("experiment_plan", "experiment", "validation_plan", "plan", "summary"))
    evidence_collection = evidence_surface_collection(
        evidence_items if evidence_items is not None else _first_value(source, ("experimental_support_summaries", "evidence_items", "evidence")),
        include_internal_refs=include_internal_refs,
    )
    sections = {
        "observable_variables": _surface_text_items(
            _first_value(source, ("observable_variables", "observables", "variables", "measured_variables")),
            max_items=6,
            max_length=140,
        ),
        "controls": _surface_text_items(
            _first_value(source, ("controls", "control_conditions", "baselines", "negative_controls")),
            max_items=6,
            max_length=140,
        ),
        "metrics": _surface_text_items(
            _first_value(source, ("metrics", "key_metrics", "success_metrics", "evaluation_metrics")),
            max_items=6,
            max_length=140,
        ),
        "failure_conditions": _surface_text_items(
            _first_value(source, ("failure_conditions", "failure_criteria", "falsification_criteria", "falsification_tests", "failure_modes")),
            max_items=8,
            max_length=180,
        ),
        "alternative_explanations": _surface_text_items(
            _first_value(source, ("alternative_explanations", "confounds", "counter_hypotheses", "alternative_explanation_tests")),
            max_items=6,
            max_length=180,
        ),
        "required_data": _surface_text_items(
            _first_value(source, ("required_data", "data_requirements", "needed_evidence", "datasets")),
            max_items=6,
            max_length=160,
        ),
    }
    minimal_path = _first_text(source, ("minimal_validation_path", "minimum_viable_experiment", "validation_path", "next_step"))
    if not minimal_path:
        minimal_path = _compact_text(plan_text, max_length=220)
    missing_sections = _experiment_missing_sections(plan_text=plan_text, sections=sections, minimal_path=minimal_path)
    status = _experiment_design_status(missing_sections=missing_sections, evidence_boundary=evidence_collection.get("boundary"))
    summary = {
        "status": status,
        "hypothesis": hypothesis_surface_summary(source) if source else None,
        "plan_summary": _compact_text(plan_text, max_length=420),
        "observable_variables": sections["observable_variables"],
        "controls": sections["controls"],
        "metrics": sections["metrics"],
        "failure_conditions": sections["failure_conditions"],
        "alternative_explanations": sections["alternative_explanations"],
        "required_data": sections["required_data"],
        "minimal_validation_path": _compact_text(minimal_path, max_length=260),
        "evidence": {
            "evidence_count": evidence_collection.get("evidence_count", 0),
            "boundary": evidence_collection.get("boundary"),
            "support_level_counts": evidence_collection.get("support_level_counts", {}),
        },
        "missing_sections": missing_sections,
        "next_actions": _experiment_next_actions(status=status, missing_sections=missing_sections),
        "visibility_boundary": (
            "Experiment design summaries expose the selected hypothesis, plan summary, variables, controls, "
            "metrics, failure conditions, alternative explanations, required data, and evidence boundary by default; "
            "execution job IDs, scripts, local paths, raw tool payloads, and provider diagnostics require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "hypothesis_id": _first_value(source, ("id", "hypothesis_id")),
            "experiment_id": _first_value(source, ("experiment_id", "job_id", "experiment_job_id")),
            "script_path": _first_value(source, ("script_path", "local_path", "artifact_path")),
            "raw_source": dict(source),
        }
    return summary


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


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [] if value is None else [value]


def _record_items(values: Any) -> list[Mapping[str, Any]]:
    if values is None or isinstance(values, (str, bytes)):
        candidates: list[Any] = []
    elif isinstance(values, Mapping):
        candidates = [values]
    else:
        try:
            candidates = list(values)
        except TypeError:
            candidates = [values]
    return [item for item in (_as_mapping(value) for value in candidates) if item]


def _surface_text_items(value: Any, *, max_items: int, max_length: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        candidates = [f"{key}: {item}" for key, item in value.items() if item is not None and item != ""]
    elif isinstance(value, (list, tuple, set)):
        candidates = list(value)
    else:
        candidates = [value]
    return [
        compact
        for compact in (_compact_text(item, max_length=max_length) for item in candidates)
        if compact
    ][:max_items]


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


def _ranking_matchup_surface_summary(matchup: Mapping[str, Any], *, index: int) -> Dict[str, Any]:
    winner_key = _first_value(matchup, ("winner_id", "winner_hypothesis_id", "winnerHypothesisId", "winner"))
    loser_key = _first_value(matchup, ("loser_id", "loser_hypothesis_id", "loserHypothesisId", "loser"))
    winner_label = _first_value(matchup, ("winner_label", "winner_title", "winner_name")) or winner_key
    loser_label = _first_value(matchup, ("loser_label", "loser_title", "loser_name")) or loser_key
    before = _as_mapping(_first_value(matchup, ("before_elo", "elo_before", "ratings_before", "beforeElo")))
    after = _as_mapping(_first_value(matchup, ("after_elo", "elo_after", "ratings_after", "afterElo")))
    delta = _as_mapping(_first_value(matchup, ("elo_delta", "rating_delta", "delta", "eloDelta")))
    winner_before = _safe_number(_first_value(matchup, ("winner_elo_before", "winnerBeforeElo")))
    if winner_before is None:
        winner_before = _rating_lookup(before, winner_key, winner_label, matchup.get("winner"))
    winner_after = _safe_number(_first_value(matchup, ("winner_elo_after", "winnerAfterElo")))
    if winner_after is None:
        winner_after = _rating_lookup(after, winner_key, winner_label, matchup.get("winner"))
    winner_delta = _safe_number(_first_value(matchup, ("winner_elo_delta", "winnerEloDelta")))
    if winner_delta is None:
        winner_delta = _rating_lookup(delta, winner_key, winner_label, matchup.get("winner"))
    loser_before = _safe_number(_first_value(matchup, ("loser_elo_before", "loserBeforeElo")))
    if loser_before is None:
        loser_before = _rating_lookup(before, loser_key, loser_label, matchup.get("loser"))
    loser_after = _safe_number(_first_value(matchup, ("loser_elo_after", "loserAfterElo")))
    if loser_after is None:
        loser_after = _rating_lookup(after, loser_key, loser_label, matchup.get("loser"))
    loser_delta = _safe_number(_first_value(matchup, ("loser_elo_delta", "loserEloDelta")))
    if loser_delta is None:
        loser_delta = _rating_lookup(delta, loser_key, loser_label, matchup.get("loser"))
    if winner_delta is None and winner_before is not None and winner_after is not None:
        winner_delta = winner_after - winner_before
    if loser_delta is None and loser_before is not None and loser_after is not None:
        loser_delta = loser_after - loser_before
    return {
        "index": index,
        "winner": _compact_text(winner_label, max_length=120),
        "loser": _compact_text(loser_label, max_length=120),
        "confidence": _safe_number(_first_value(matchup, ("confidence", "judge_confidence", "confidence_score"))),
        "winner_elo": {
            "before": winner_before,
            "after": winner_after,
            "delta": winner_delta,
        },
        "loser_elo": {
            "before": loser_before,
            "after": loser_after,
            "delta": loser_delta,
        },
        "reasoning_summary": _compact_text(
            _first_value(matchup, ("reasoning", "rationale", "decision_reasoning", "summary")),
            max_length=260,
        ),
        "comparison_mode": _first_value(matchup, ("comparison_mode", "mode", "comparisonMode")),
    }


def _rating_lookup(ratings: Mapping[str, Any], *keys: Any) -> Optional[float]:
    for key in keys:
        if key is None:
            continue
        value = ratings.get(str(key))
        if value is None:
            value = ratings.get(key)
        number = _safe_number(value)
        if number is not None:
            return number
    return None


def _ranking_status(items: list[Mapping[str, Any]], *, matchup_count: int) -> str:
    if matchup_count == 0:
        return "absent"
    for item in items:
        if not item.get("winner") or not item.get("loser"):
            return "limited"
    return "ready"


def _ranking_hypothesis_summaries(hypotheses: list[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    sorted_hypotheses = sorted(
        hypotheses,
        key=lambda item: _safe_number(_first_value(item, ("elo_rating", "elo", "rating"))) or 0,
        reverse=True,
    )
    return [
        hypothesis_surface_summary(hypothesis, index=index)
        for index, hypothesis in enumerate(sorted_hypotheses[:5])
    ]


def _ranking_confidence_summary(items: list[Mapping[str, Any]]) -> Dict[str, Any]:
    values = [
        value
        for value in (_safe_number(item.get("confidence")) for item in items)
        if value is not None
    ]
    if not values:
        return {"available": False, "average": None, "minimum": None}
    return {
        "available": True,
        "average": round(sum(values) / len(values), 4),
        "minimum": min(values),
    }


def _ranking_next_actions(status: str) -> list[str]:
    if status == "absent":
        return ["run_ranking_phase", "inspect_review_scores"]
    if status == "limited":
        return ["inspect_matchup_details", "rerun_ranking_if_needed"]
    return ["inspect_top_ranked_hypotheses", "inspect_matchup_details", "design_experiment"]


def _experiment_missing_sections(
    *,
    plan_text: str,
    sections: Mapping[str, list[str]],
    minimal_path: str,
) -> list[str]:
    missing: list[str] = []
    if not plan_text:
        missing.append("plan_summary")
    for section in ("observable_variables", "controls", "metrics", "failure_conditions", "alternative_explanations", "required_data"):
        if not sections.get(section):
            missing.append(section)
    if not minimal_path:
        missing.append("minimal_validation_path")
    return missing


def _experiment_design_status(*, missing_sections: list[str], evidence_boundary: Any) -> str:
    boundary = _as_mapping(evidence_boundary)
    if "plan_summary" in missing_sections:
        return "absent"
    if boundary.get("status") == "contradicted":
        return "needs_review"
    required_sections = {"observable_variables", "controls", "metrics", "failure_conditions", "minimal_validation_path"}
    if required_sections.intersection(missing_sections):
        return "limited"
    return "ready"


def _experiment_next_actions(*, status: str, missing_sections: list[str]) -> list[str]:
    if status == "absent":
        return ["draft_experiment_plan", "select_hypothesis"]
    actions: list[str] = []
    if missing_sections:
        actions.append("complete_missing_sections")
    if status == "needs_review":
        actions.append("inspect_counter_evidence")
    actions.extend(["inspect_evidence", "export_to_report"])
    if status == "ready":
        actions.insert(1, "prepare_execution_workflow")
    return actions


def _worker_readiness_state(*, worker_enabled: bool, counts: Mapping[str, int]) -> str:
    if not worker_enabled:
        return "disabled"
    if int(counts.get("error", 0)) > 0:
        return "needs_attention"
    if int(counts.get("retrying", 0)) > 0:
        return "retrying"
    if int(counts.get("running", 0)) > 0:
        return "running"
    return "ready"


def _worker_guidance(worker_state: str) -> str:
    return {
        "disabled": "Background worker is disabled; queued runs need an admin worker or manual tick.",
        "needs_attention": "Some work items failed; inspect failures before retrying.",
        "retrying": "Retryable work is waiting for the next worker tick.",
        "running": "Worker is actively processing queued research work.",
        "ready": "Worker is available for durable background execution.",
    }.get(worker_state, "Inspect worker readiness before starting long-running work.")


def _service_surface_items(service_statuses: Mapping[str, Any]) -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    for name, raw_status in service_statuses.items():
        status = _as_mapping(raw_status)
        available = bool(status.get("available", status.get("ready", False)))
        state = str(status.get("status") or ("ready" if available else "limited"))
        items.append(
            {
                "service": str(name),
                "status": state,
                "available": available,
                "summary": _compact_text(status.get("summary") or status.get("message") or "", max_length=180),
                "required": bool(status.get("required", False)),
            }
        )
    return items


def _service_counts(services: list[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"ready": 0, "limited": 0, "offline": 0, "permission_denied": 0, "required_unavailable": 0}
    for service in services:
        status = str(service.get("status") or "limited")
        if status in counts:
            counts[status] += 1
        elif service.get("available"):
            counts["ready"] += 1
        else:
            counts["limited"] += 1
        if service.get("required") and not service.get("available"):
            counts["required_unavailable"] += 1
    return counts


def _runtime_overall_status(
    *,
    worker_state: str,
    execution_status: str,
    service_counts: Mapping[str, int],
) -> str:
    if service_counts.get("permission_denied", 0):
        return "permission_denied"
    if service_counts.get("required_unavailable", 0) or service_counts.get("offline", 0):
        return "offline"
    if worker_state == "disabled":
        return "limited"
    if worker_state in {"needs_attention", "retrying"}:
        return "limited"
    if execution_status in {"limited", "not_available"} or service_counts.get("limited", 0):
        return "limited"
    return "ready"


def _runtime_next_actions(
    *,
    overall_status: str,
    worker_state: str,
    service_counts: Mapping[str, int],
    execution_status: str,
) -> list[str]:
    actions: list[str] = []
    if worker_state == "disabled":
        actions.append("start_worker_or_manual_tick")
    if worker_state in {"needs_attention", "retrying"}:
        actions.append("inspect_queue")
    if service_counts.get("required_unavailable", 0) or service_counts.get("offline", 0):
        actions.append("restore_required_services")
    if service_counts.get("permission_denied", 0):
        actions.append("resolve_permissions")
    if execution_status in {"limited", "not_available"}:
        actions.append("continue_with_metadata_only_execution_memory")
    if not actions:
        actions.append("start_or_continue_research_run" if overall_status == "ready" else "inspect_readiness_details")
    return actions


def _confirmation_validity(*, research_goal: str, mode_boundary: Mapping[str, Any]) -> Dict[str, Any]:
    issues: list[str] = []
    if len(research_goal) < 8:
        issues.append("research_goal_too_short")
    if mode_boundary.get("mode") == "live_model" and mode_boundary.get("evidence_status") in {"absent", "unknown"}:
        issues.append("literature_grounding_not_enabled")
    return {
        "status": "invalid" if any(item == "research_goal_too_short" for item in issues) else "pending",
        "blocking_issues": issues,
    }


def _preview_list(values: Iterable[Any], *, max_items: int, max_length: int) -> list[str]:
    previews: list[str] = []
    for value in values:
        compact = _compact_text(value, max_length=max_length)
        if compact:
            previews.append(compact)
        if len(previews) >= max_items:
            break
    return previews


def _feedback_surface_summary(feedback_items: list[Mapping[str, Any]]) -> Dict[str, Any]:
    feedback_types: Dict[str, int] = {}
    target_types: Dict[str, int] = {}
    for item in feedback_items:
        feedback_type = str(item.get("feedback_type") or "unknown")
        target_type = str(item.get("target_type") or "unknown")
        feedback_types[feedback_type] = feedback_types.get(feedback_type, 0) + 1
        target_types[target_type] = target_types.get(target_type, 0) + 1
    return {
        "count": len(feedback_items),
        "feedback_types": feedback_types,
        "target_types": target_types,
        "applies_to": "next_run_or_continuation" if feedback_items else None,
    }


def _confirmation_parent_summary(parent: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if not parent:
        return None
    return {
        "research_goal": _compact_text(parent.get("research_goal"), max_length=240),
        "status": parent.get("status"),
        "hypothesis_count": _safe_int(parent.get("hypothesis_count")) or 0,
        "updated_at": parent.get("updated_at"),
    }


def _confirmation_next_actions(status: str, *, has_parent: bool) -> list[str]:
    if status == "invalid":
        return ["edit_research_goal", "cancel"]
    actions = ["confirm_continuation" if has_parent else "confirm_start_run", "edit_request", "cancel"]
    return actions


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
