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

AGENT_PROCESS_PHASE_ORDER = [
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

AGENT_PROCESS_PHASE_LABELS = {
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

AGENT_PROCESS_PHASE_ALIASES = {
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

AGENT_PROCESS_PHASE_ROLES = {
    "supervisor": "Plans the research task and applies goal, constraint, and memory guidance.",
    "literature_review": "Grounds the task in literature, PDF/fulltext, and knowledge-source evidence.",
    "generate": "Creates candidate hypotheses and integrates user-provided starting hypotheses.",
    "reflection": "Compares candidates against evidence, gaps, and literature context.",
    "review": "Critiques hypotheses for soundness, novelty, feasibility, relevance, and safety.",
    "ranking": "Compares hypotheses through pairwise tournament ranking and Elo-style provenance.",
    "meta_review": "Synthesizes cross-hypothesis themes, weaknesses, and strategic recommendations.",
    "evolve": "Refines top hypotheses using critique, feedback, and diversity guidance.",
    "proximity": "Clusters and deduplicates hypotheses to reduce repetition and mode collapse.",
}


def research_goal_readiness_surface_summary(
    request_preview: Any,
    *,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    request = _as_mapping(request_preview)
    if not request and isinstance(request_preview, str):
        request = {"research_goal": request_preview}
    research_goal = str(_first_value(request, ("research_goal", "goal", "input")) or "").strip()
    constraints = [str(item).strip() for item in _as_list(request.get("constraints")) if str(item).strip()]
    attributes = [str(item).strip() for item in _as_list(request.get("attributes")) if str(item).strip()]
    starting_hypotheses = [str(item).strip() for item in _as_list(request.get("starting_hypotheses")) if str(item).strip()]
    user_feedback = [_as_mapping(item) for item in _as_list(request.get("user_feedback"))]
    signals = _goal_readiness_signals(
        research_goal=research_goal,
        preferences=str(request.get("preferences") or ""),
        constraints=constraints,
        attributes=attributes,
        starting_hypotheses=starting_hypotheses,
    )
    missing = [key for key, available in signals.items() if not available]
    status = _goal_readiness_status(research_goal=research_goal, missing=missing)
    summary = {
        "status": status,
        "research_goal": _compact_text(research_goal, max_length=360),
        "signals": signals,
        "missing_elements": missing,
        "counts": {
            "constraints": len(constraints),
            "attributes": len(attributes),
            "starting_hypotheses": len(starting_hypotheses),
            "user_feedback": len(user_feedback),
        },
        "constraint_previews": _preview_list(constraints, max_items=3, max_length=140),
        "attribute_previews": _preview_list(attributes, max_items=6, max_length=80),
        "starting_hypothesis_previews": _preview_list(starting_hypotheses, max_items=3, max_length=180),
        "guidance": _goal_readiness_guidance(status=status, missing=missing),
        "next_actions": _goal_readiness_next_actions(status=status, missing=missing),
        "visibility_boundary": (
            "Research goal readiness summaries expose the goal, validation signals, missing elements, "
            "short previews, counts, and task guidance by default; raw RunRequest JSON, intent-router "
            "debug, full feedback text, internal IDs, and provider diagnostics require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "request_preview": dict(request),
            "parent_run_id": request.get("parent_run_id"),
            "library_id": request.get("library_id"),
            "memory_scope": request.get("memory_scope"),
        }
    return summary


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
    worker_recovery_action = _work_queue_surface_recovery_action(
        snapshot={},
        active_snapshot=active_snapshot,
        worker=worker,
        item_previews=[],
    )
    worker_recovery_action_counts = _work_queue_surface_recovery_action_counts(
        snapshot={},
        active_snapshot=active_snapshot,
        worker=worker,
    )
    execution_status = str(memory.get("status") or "not_available")
    service_counts = _service_counts(services)
    overall_status = _runtime_overall_status(
        worker_state=worker_state,
        execution_status=execution_status,
        service_counts=service_counts,
    )
    summary = {
        "status": overall_status,
        "audience": {
            "primary": "admin_or_expert",
            "default_researcher_surface": False,
            "placement": "runtime_admin_or_expert_inspector",
            "researcher_label": _runtime_researcher_label(overall_status),
        },
        "worker": {
            "enabled": worker_enabled,
            "state": worker_state,
            "concurrency": _safe_int(worker.get("concurrency")) or 0,
            "running_count": _safe_int(worker.get("running_count")) or counts["running"],
            "queue_counts": counts,
            "recovery_action": worker_recovery_action,
            "recovery_action_counts": worker_recovery_action_counts,
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
        "disclosure": {
            "default_state": "collapsed",
            "show_on_primary_researcher_surface": False,
            "safe_default_fields": [
                "status",
                "audience",
                "worker.state",
                "worker.queue_counts",
                "worker.recovery_action",
                "worker.recovery_action_counts",
                "execution_memory.status",
                "service_counts",
                "next_actions",
            ],
            "expert_fields": [
                "owner IDs",
                "lease timing",
                "service endpoints",
                "environment variables",
                "raw errors",
                "debug payloads",
            ],
        },
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


def work_queue_surface_summary(
    work_item_snapshot: Any = None,
    *,
    worker_status: Optional[Mapping[str, Any]] = None,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    snapshot = _as_mapping(work_item_snapshot)
    worker = _as_mapping(worker_status)
    active_snapshot = _as_mapping(worker.get("active_work_item_snapshot"))
    items = _record_items(
        snapshot.get("items")
        or active_snapshot.get("items")
        or worker.get("active_work_items")
        or worker.get("items")
    )
    counts = _work_queue_counts(snapshot=snapshot, worker=worker, items=items)
    worker_enabled = bool(worker.get("enabled")) if "enabled" in worker else True
    status = _work_queue_surface_status(
        counts=counts,
        worker_enabled=worker_enabled,
    )
    item_previews = [
        _work_queue_item_surface(item, index=index)
        for index, item in enumerate(items[:5])
    ]
    recovery_action = _work_queue_surface_recovery_action(
        snapshot=snapshot,
        active_snapshot=active_snapshot,
        worker=worker,
        item_previews=item_previews,
    )
    recovery_action_counts = _work_queue_surface_recovery_action_counts(
        snapshot=snapshot,
        active_snapshot=active_snapshot,
        worker=worker,
    )
    summary = {
        "status": status,
        "recovery_action": recovery_action,
        "recovery_action_counts": recovery_action_counts,
        "worker": {
            "enabled": worker_enabled,
            "concurrency": _safe_int(worker.get("concurrency")) or 0,
            "running_count": _safe_int(worker.get("running_count")) or counts["running"],
        },
        "counts": counts,
        "current_item": item_previews[0] if item_previews else None,
        "items_preview": item_previews,
        "next_actions": _work_queue_next_actions(status),
        "disclosure": {
            "default_state": "summary",
            "safe_default_fields": [
                "status",
                "worker.enabled",
                "worker.concurrency",
                "counts",
                "recovery_action",
                "recovery_action_counts",
                "current_item.status",
                "current_item.phase",
                "current_item.agent_role",
                "current_item.next_action",
            ],
            "expert_fields": [
                "work item IDs",
                "run IDs",
                "lease owners",
                "lease expiry",
                "raw arguments",
                "result references",
                "raw errors",
            ],
        },
        "visibility_boundary": (
            "Work queue summaries expose queue state, worker readiness, counts, phase, agent role, "
            "attempt counts, and next actions by default; work item IDs, run IDs, lease owners, "
            "lease timing, raw arguments, result references, and raw errors require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "work_item_ids": [
                _first_value(item, ("work_item_id", "id"))
                for item in items
                if _first_value(item, ("work_item_id", "id"))
            ],
            "run_ids": [
                _first_value(item, ("run_id",))
                for item in items
                if _first_value(item, ("run_id",))
            ],
            "lease_owners": [
                _first_value(item, ("lease_owner", "owner"))
                for item in items
                if _first_value(item, ("lease_owner", "owner"))
            ],
            "lease_expires_at": [
                _first_value(item, ("lease_expires_at",))
                for item in items
                if _first_value(item, ("lease_expires_at",))
            ],
            "error_messages": [
                _first_value(item, ("error_message", "error"))
                for item in items
                if _first_value(item, ("error_message", "error"))
            ],
            "raw_items": [dict(item) for item in items],
            "raw_worker_status": dict(worker),
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


def memory_surface_summary(
    memory_context: Any,
    *,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    envelope = _as_mapping(memory_context)
    source = _as_mapping(envelope.get("memory")) or envelope
    parent_run = _as_mapping(source.get("parent_run"))
    related_runs = _record_items(source.get("related_runs"))
    prior_hypotheses = _record_items(source.get("prior_hypotheses"))
    user_feedback = _record_items(source.get("user_feedback"))
    evidence_summaries = _record_items(source.get("evidence_summaries") or source.get("evidence_items"))
    execution_memory = _as_mapping(source.get("execution_memory"))
    injection_policy = _as_mapping(source.get("injection_policy"))
    evidence_collection = evidence_surface_collection(evidence_summaries)
    evidence_scope = _memory_evidence_scope(source=source, evidence_collection=evidence_collection)
    known_gaps = _surface_text_items(source.get("known_gaps"), max_items=5, max_length=180)
    counts = {
        "parent_run": 1 if parent_run else 0,
        "related_runs": len(related_runs),
        "prior_hypotheses": len(prior_hypotheses),
        "user_feedback": len(user_feedback),
        "evidence_sources": len(evidence_summaries),
        "known_gaps": len(known_gaps),
    }
    status = _memory_surface_status(
        counts=counts,
        evidence_status=str(evidence_scope.get("status") or "absent"),
        execution_status=str(execution_memory.get("status") or ""),
    )
    summary = {
        "status": status,
        "memory_scope": source.get("memory_scope") or "project",
        "memory_sources": list(source.get("memory_sources") or source.get("source_types") or []),
        "parent_run": _memory_parent_run_surface_summary(parent_run),
        "counts": counts,
        "feedback_summary": _feedback_surface_summary(user_feedback),
        "history_summary": _memory_history_summary(
            parent_run=parent_run,
            counts=counts,
            evidence_scope=evidence_scope,
        ),
        "evidence_scope": evidence_scope,
        "execution_memory": _memory_execution_surface_summary(execution_memory),
        "injection_policy": _memory_injection_policy_surface_summary(injection_policy),
        "known_gap_summaries": known_gaps[:3],
        "next_actions": _memory_next_actions(status=status, evidence_status=str(evidence_scope.get("status") or "")),
        "visibility_boundary": (
            "Memory surface summaries expose parent-run context, counts, evidence scope, execution-memory "
            "status, summary-only injection policy, and next actions by default; raw chat messages, exact "
            "feedback text, checkpoint refs, retrieval diagnostics, internal IDs, and raw memory JSON require "
            "expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "parent_run_id": _first_value(parent_run, ("run_id", "id")),
            "related_run_ids": [
                _first_value(item, ("run_id", "id"))
                for item in related_runs
                if _first_value(item, ("run_id", "id"))
            ],
            "feedback_ids": [
                _first_value(item, ("feedback_id", "id"))
                for item in user_feedback
                if _first_value(item, ("feedback_id", "id"))
            ],
            "hypothesis_ids": [
                _first_value(item, ("hypothesis_id", "id"))
                for item in prior_hypotheses
                if _first_value(item, ("hypothesis_id", "id"))
            ],
            "evidence_refs": [
                {
                    "paper_id": _first_value(item, ("paper_id", "source_id")),
                    "chunk_id": _first_value(item, ("chunk_id", "evidence_chunk_id")),
                    "library_id": _first_value(item, ("library_id",)),
                }
                for item in evidence_summaries[:10]
            ],
            "checkpoint_id": _memory_checkpoint_value(execution_memory, "checkpoint_id"),
            "checkpoint_ref": _memory_checkpoint_value(execution_memory, "checkpoint_ref"),
            "raw_injection_policy": dict(injection_policy),
            "raw_memory_context": dict(source),
        }
    return summary


def memory_prompt_packet_surface_summary(
    prompt_packet: Any,
    *,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    packet = _as_mapping(prompt_packet)
    sections = _record_items(packet.get("sections"))
    target_prompts = [
        _compact_text(item, max_length=40)
        for item in _as_list(packet.get("target_prompts"))
        if str(item).strip()
    ][:8]
    excluded_raw_fields = [
        _compact_text(item, max_length=80)
        for item in _as_list(packet.get("excluded_raw_fields"))
        if str(item).strip()
    ]
    raw_allowed = bool(packet.get("raw_injection_allowed"))
    mode = _compact_text(packet.get("mode") or ("raw" if raw_allowed else "summary_only"), max_length=80)
    section_summaries = [
        _prompt_packet_section_surface(section, index=index)
        for index, section in enumerate(sections[:8])
    ]
    section_count = _safe_int(packet.get("section_count")) or len(section_summaries)
    item_count = sum(int(item.get("item_count") or 0) for item in section_summaries)
    status = _prompt_packet_surface_status(
        packet_available=bool(packet),
        raw_allowed=raw_allowed,
        section_count=section_count,
    )
    summary = {
        "status": status,
        "mode": mode,
        "memory_scope": packet.get("memory_scope") or "project",
        "target_prompts": target_prompts,
        "section_count": section_count,
        "sections": section_summaries,
        "counts": {
            "sections": section_count,
            "items": item_count,
            "target_prompts": len(target_prompts),
            "excluded_raw_fields": len(excluded_raw_fields),
        },
        "raw_injection_allowed": raw_allowed,
        "excluded_raw_field_count": len(excluded_raw_fields),
        "excluded_raw_fields": excluded_raw_fields[:8],
        "application_boundary": (
            "Prompt memory packet is configured for raw injection; inspect expert details before running."
            if raw_allowed
            else "Prompt memory packet uses summary-only sections for generation guidance."
        ),
        "next_actions": _prompt_packet_next_actions(status),
        "visibility_boundary": (
            "Prompt packet summaries expose mode, memory scope, target prompts, section counts, "
            "and raw-field exclusions by default; section item payloads, exact references, checkpoint "
            "state, feedback text, hypothesis text, and raw packet JSON require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "raw_sections": [dict(section) for section in sections],
            "raw_prompt_packet": dict(packet),
            "section_item_counts": {
                str(_first_value(section, ("section", "name", "id")) or f"section_{index + 1}"): len(
                    _record_items(section.get("items"))
                )
                for index, section in enumerate(sections)
            },
        }
    return summary


def feedback_surface_summary(
    feedback_items: Any,
    *,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    records = _record_items(feedback_items)
    base = _feedback_surface_summary(records)
    status = "empty" if not records else "available"
    summary = {
        "status": status,
        "count": base["count"],
        "feedback_types": base["feedback_types"],
        "target_types": base["target_types"],
        "applies_to": base["applies_to"],
        "application_boundary": (
            "User feedback guides the next run or continuation. It is not presented as an immediate "
            "reversible edit to already completed hypotheses unless a durable continuation is explicitly started."
            if records
            else "No feedback has been recorded for a future run or continuation."
        ),
        "target_summary": _feedback_target_summary(records),
        "next_actions": _feedback_next_actions(records),
        "visibility_boundary": (
            "Feedback summaries expose counts, feedback type distribution, target type distribution, "
            "application boundary, and next actions by default; raw feedback text, target references, "
            "feedback IDs, run IDs, user IDs, and router debug require explicit expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "feedback_ids": [
                _first_value(item, ("feedback_id", "id"))
                for item in records
                if _first_value(item, ("feedback_id", "id"))
            ],
            "run_ids": [
                _first_value(item, ("run_id",))
                for item in records
                if _first_value(item, ("run_id",))
            ],
            "target_refs": [
                _first_value(item, ("target_ref", "target_ref_json", "target"))
                for item in records
                if _first_value(item, ("target_ref", "target_ref_json", "target"))
            ],
            "raw_feedback": [dict(item) for item in records],
        }
    return summary


def workspace_surface_summary(
    workspace_state: Any,
    *,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    source = _as_mapping(workspace_state)
    request = _as_mapping(_first_value(source, ("request", "run_request", "request_preview")))
    run = _as_mapping(source.get("run"))
    parent_run = _as_mapping(source.get("parent_run"))
    memory_context = _first_value(source, ("memory", "memory_context"))
    library = _first_value(source, ("library", "evidence_library"))
    papers = source.get("papers")
    parse_runs = source.get("parse_runs")
    worker_status = _as_mapping(source.get("worker_status"))
    execution_memory = _as_mapping(source.get("execution_memory"))
    service_statuses = _as_mapping(source.get("service_statuses"))
    process_trace = _first_value(source, ("agent_trace", "agent_trace_summary", "process_trace"))

    goal = research_goal_readiness_surface_summary(request)
    confirmation = (
        run_confirmation_surface_summary(
            request,
            parent_run_summary=parent_run,
            memory_summary=memory_context if isinstance(memory_context, Mapping) else None,
        )
        if request
        else None
    )
    run_summary = run_surface_summary(
        run,
        work_item_snapshot=_as_mapping(source.get("work_item_snapshot")),
        memory_summary=memory_context if isinstance(memory_context, Mapping) else None,
        recovery_policy=_as_mapping(source.get("recovery_policy")),
    ) if run else None
    memory = memory_surface_summary(memory_context) if memory_context is not None else None
    evidence_library = (
        evidence_library_surface_summary(library, papers=papers, parse_runs=parse_runs)
        if library is not None or papers is not None or parse_runs is not None
        else None
    )
    runtime = (
        runtime_readiness_surface_summary(
            worker_status=worker_status,
            execution_memory=execution_memory,
            service_statuses=service_statuses,
        )
        if worker_status or execution_memory or service_statuses
        else None
    )
    process = agent_process_surface_summary(process_trace) if process_trace is not None else None
    primary_surface = _workspace_primary_surface(
        goal_summary=goal,
        confirmation_summary=confirmation,
        run_summary=run_summary,
    )
    summary = {
        "status": _workspace_status(
            primary_surface=primary_surface,
            run_summary=run_summary,
            goal_summary=goal,
            runtime_summary=runtime,
        ),
        "primary_surface": primary_surface,
        "layout": {
            "shell": "three_panel_research_workspace",
            "left": "project_navigation",
            "center": primary_surface["surface"],
            "right": "collapsible_inspector",
        },
        "surfaces": {
            "goal": goal,
            "confirmation": confirmation,
            "run": run_summary,
            "memory": memory,
            "evidence_library": evidence_library,
            "process": process,
            "runtime": runtime,
        },
        "inspectors": _workspace_inspectors(
            memory_summary=memory,
            evidence_library_summary=evidence_library,
            runtime_summary=runtime,
            agent_trace_available=bool(process and process.get("status") != "absent"),
        ),
        "next_actions": primary_surface["next_actions"],
        "hidden_by_default": [
            "raw_run_request",
            "raw_memory_context",
            "agent_trace_payload",
            "worker_lease_details",
            "checkpoint_refs",
            "provider_diagnostics",
            "internal_ids",
        ],
        "visibility_boundary": (
            "Workspace summaries choose the task surface, layout regions, inspectors, and next actions "
            "for the researcher; raw requests, work items, memory JSON, trace payloads, checkpoint refs, "
            "provider diagnostics, and internal IDs require expert/debug disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "run_id": run.get("run_id"),
            "parent_run_id": request.get("parent_run_id") or parent_run.get("run_id"),
            "library_id": _as_mapping(library).get("library_id") if library is not None else None,
            "work_item_ids": [
                _first_value(item, ("work_item_id", "id"))
                for item in _record_items(_as_mapping(source.get("work_item_snapshot")).get("items"))
                if _first_value(item, ("work_item_id", "id"))
            ],
            "raw_workspace_state": dict(source),
        }
    return summary


def agent_process_surface_summary(
    trace_events: Any,
    *,
    registry: Optional[Mapping[str, Any]] = None,
    max_items: int = 12,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    records = _agent_process_records(trace_events)
    phase_index = _agent_process_phase_index(registry)
    items = [
        _agent_process_item(record, phase_index=phase_index, index=index)
        for index, record in enumerate(records)
    ]
    sorted_items = sorted(
        items,
        key=lambda item: _agent_process_sort_key(str(item.get("phase") or ""), fallback_index=int(item.get("index") or 0)),
    )
    displayed_items = sorted_items[: max(0, max_items)]
    counts = _agent_process_counts(sorted_items)
    phase_coverage = _agent_process_phase_coverage(sorted_items, phase_index=phase_index)
    counts["missing_phase"] = len(phase_coverage.get("missing_phases") or [])
    status = _agent_process_status(counts)
    summary = {
        "status": status,
        "trace_count": len(sorted_items),
        "displayed_trace_count": len(displayed_items),
        "truncated_trace_count": max(0, len(sorted_items) - len(displayed_items)),
        "phase_order": [item["phase"] for item in sorted_items],
        "phase_coverage": phase_coverage,
        "current_phase": _agent_process_current_phase(sorted_items),
        "counts": counts,
        "items": [_agent_process_default_item(item) for item in displayed_items],
        "next_actions": _agent_process_next_actions(status=status, counts=counts),
        "visibility_boundary": (
            "Agent process summaries expose research-step labels, roles, status, short output summaries, "
            "degradation flags, and tool-call counts by default; agent IDs, event IDs, prompt/template names, "
            "token usage, tool arguments/results, provider payloads, and raw trace JSON require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "agent_ids": [
                item.get("agent_id")
                for item in sorted_items
                if item.get("agent_id")
            ],
            "event_ids": [
                item.get("event_id")
                for item in sorted_items
                if item.get("event_id")
            ],
            "prompt_templates": [
                item.get("prompt_template")
                for item in sorted_items
                if item.get("prompt_template")
            ],
            "token_usage_by_phase": {
                str(item.get("phase")): item.get("token_usage")
                for item in sorted_items
                if item.get("token_usage")
            },
            "raw_trace_events": [dict(record) for record in records],
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


def report_surface_summary(
    report: Any,
    *,
    hypotheses: Optional[Iterable[Any]] = None,
    evidence_items: Optional[Iterable[Any]] = None,
    experiment: Any = None,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    source = _as_mapping(report)
    request = _as_mapping(source.get("request"))
    metrics = _as_mapping(source.get("metrics"))
    memory_summary = _as_mapping(source.get("memory_summary") or source.get("memory"))
    hypothesis_records = _record_items(hypotheses if hypotheses is not None else source.get("hypotheses"))
    evidence_records = _record_items(
        evidence_items
        if evidence_items is not None
        else _first_value(source, ("evidence_items", "evidence", "sources", "references"))
    )
    experiment_source = experiment if experiment is not None else _first_value(
        source,
        ("experiment_design", "experiment_plan", "experiment"),
    )
    if isinstance(experiment_source, str):
        experiment_source = {"experiment_plan": experiment_source, "title": source.get("title")}
    if not _as_mapping(experiment_source) and hypothesis_records:
        experiment_source = hypothesis_records[0]
    mode_boundary = _run_mode_boundary(request=request, metrics=metrics, memory_summary=memory_summary)
    hypothesis_collection = hypothesis_surface_collection(hypothesis_records)
    evidence_collection = evidence_surface_collection(evidence_records)
    experiment_summary = experiment_design_surface_summary(experiment_source, evidence_items=evidence_records)
    findings = _report_findings(source, hypothesis_collection.get("items", []))
    limitations = _report_limitations(
        source=source,
        mode_boundary=mode_boundary,
        evidence_boundary=evidence_collection.get("boundary"),
        experiment_summary=experiment_summary,
    )
    citation_qa = _citation_qa_surface_summary(source, evidence_collection)
    status = _report_status(
        findings=findings,
        evidence_boundary=evidence_collection.get("boundary"),
        experiment_status=str(experiment_summary.get("status") or "absent"),
        citation_qa=citation_qa,
    )
    summary = {
        "status": status,
        "title": _compact_text(
            _first_text(source, ("title", "report_title", "name"))
            or _first_text(request, ("research_goal", "goal"))
            or _first_text(source, ("research_goal", "goal"))
            or "Research report draft",
            max_length=180,
        ),
        "research_goal": _compact_text(
            _first_text(source, ("research_goal", "goal")) or _first_text(request, ("research_goal", "goal")),
            max_length=360,
        ),
        "mode_boundary": mode_boundary,
        "findings": findings,
        "hypotheses": {
            "hypothesis_count": hypothesis_collection.get("hypothesis_count", 0),
            "items": hypothesis_collection.get("items", [])[:5],
            "origin_counts": hypothesis_collection.get("origin_counts", {}),
            "support_level_counts": hypothesis_collection.get("support_level_counts", {}),
        },
        "evidence": {
            "evidence_count": evidence_collection.get("evidence_count", 0),
            "boundary": evidence_collection.get("boundary"),
            "support_level_counts": evidence_collection.get("support_level_counts", {}),
            "source_reliability_counts": evidence_collection.get("source_reliability_counts", {}),
        },
        "experiment": {
            "status": experiment_summary.get("status"),
            "plan_summary": experiment_summary.get("plan_summary"),
            "failure_conditions": experiment_summary.get("failure_conditions", []),
            "minimal_validation_path": experiment_summary.get("minimal_validation_path"),
            "missing_sections": experiment_summary.get("missing_sections", []),
        },
        "limitations": limitations,
        "citation_qa": citation_qa,
        "next_actions": _report_next_actions(status=status, citation_qa=citation_qa, limitations=limitations),
        "visibility_boundary": (
            "Report surface summaries expose findings, selected hypotheses, evidence boundary, experiment plan, "
            "limitations, citation QA, and export readiness by default; raw backend payloads, provider errors, "
            "tool result JSON, local paths, and internal IDs require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "run_id": source.get("run_id"),
            "report_id": _first_value(source, ("report_id", "id")),
            "hypothesis_ids": [
                _first_value(hypothesis, ("id", "hypothesis_id"))
                for hypothesis in hypothesis_records
                if _first_value(hypothesis, ("id", "hypothesis_id"))
            ],
            "raw_source": dict(source),
        }
    return summary


def evidence_library_surface_summary(
    library: Any = None,
    *,
    papers: Optional[Iterable[Any]] = None,
    parse_runs: Optional[Iterable[Any]] = None,
    evidence_items: Optional[Iterable[Any]] = None,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    source = _as_mapping(library)
    paper_records = _record_items(papers if papers is not None else _first_value(source, ("papers", "documents", "items")))
    parse_run_records = _record_items(parse_runs if parse_runs is not None else _first_value(source, ("parse_runs", "parseJobs", "jobs")))
    evidence_records = _record_items(evidence_items if evidence_items is not None else _first_value(source, ("evidence_items", "evidence", "chunks")))
    paper_items = [_library_paper_surface_summary(paper, index=index) for index, paper in enumerate(paper_records[:8])]
    all_parse_job_items = [_library_parse_job_surface_summary(item, index=index) for index, item in enumerate(parse_run_records)]
    parse_job_items = all_parse_job_items[:8]
    reliability_counts = _library_source_reliability_counts(paper_records, evidence_records)
    parse_counts = _parse_job_counts(all_parse_job_items)
    counts = {
        "papers": len(paper_records),
        "evidence_items": len(evidence_records),
        "parse_runs": len(parse_run_records),
        "parsed_fulltext_sources": reliability_counts.get("parsed_fulltext", 0),
        "experimental_chunks": _sum_int(paper_records, ("experimental_chunks_count", "experimental_support_count"))
        + _count_records_with_value(evidence_records, ("experiment_data_summary",), value_match=None),
        "chunks": _sum_int(paper_records, ("chunks_count", "chunk_count")),
    }
    status = _evidence_library_status(counts=counts, parse_counts=parse_counts, reliability_counts=reliability_counts)
    summary = {
        "status": status,
        "library": {
            "name": _compact_text(_first_text(source, ("name", "title", "label")) or "Current library", max_length=140),
            "scope": _compact_text(_first_text(source, ("scope", "memory_scope")) or "library", max_length=80),
        },
        "counts": counts,
        "source_reliability_counts": reliability_counts,
        "parse_jobs": {
            "counts": parse_counts,
            "items": parse_job_items,
        },
        "papers": {
            "items": paper_items,
            "displayed_count": len(paper_items),
            "truncated_count": max(0, len(paper_records) - len(paper_items)),
        },
        "readiness": _evidence_library_readiness(status=status, counts=counts, parse_counts=parse_counts),
        "next_actions": _evidence_library_next_actions(status=status, counts=counts, parse_counts=parse_counts),
        "visibility_boundary": (
            "Evidence library summaries expose library name, evidence readiness, source reliability counts, "
            "parse-job state, paper titles, chunk counts, and next actions by default; raw MCP payloads, "
            "SQLite/database paths, local file paths, paper IDs, parse run IDs, chunk IDs, and parser errors "
            "require expert disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "library_id": _first_value(source, ("library_id", "id")),
            "paper_ids": [
                _first_value(paper, ("paper_id", "id"))
                for paper in paper_records
                if _first_value(paper, ("paper_id", "id"))
            ],
            "parse_run_ids": [
                _first_value(item, ("parse_run_id", "id"))
                for item in parse_run_records
                if _first_value(item, ("parse_run_id", "id"))
            ],
            "local_paths": [
                _first_value(item, ("local_path", "path", "artifact_path", "database_path"))
                for item in [*paper_records, *parse_run_records]
                if _first_value(item, ("local_path", "path", "artifact_path", "database_path"))
            ],
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


def _goal_readiness_signals(
    *,
    research_goal: str,
    preferences: str,
    constraints: list[str],
    attributes: list[str],
    starting_hypotheses: list[str],
) -> Dict[str, bool]:
    combined = " ".join([research_goal, preferences, *constraints, *attributes, *starting_hypotheses]).lower()
    return {
        "mechanism_or_method": _contains_marker(
            combined,
            (
                "mechanism",
                "method",
                "protocol",
                "causal",
                "pathway",
                "intervention",
                "\u673a\u5236",
                "\u65b9\u6cd5",
                "\u8def\u5f84",
            ),
        ),
        "observable_variables": _contains_marker(
            combined,
            (
                "observable",
                "variable",
                "metric",
                "measure",
                "benchmark",
                "accuracy",
                "rate",
                "\u53d8\u91cf",
                "\u6307\u6807",
                "\u53ef\u89c2\u6d4b",
            ),
        ),
        "validation_path": _contains_marker(
            combined,
            (
                "experiment",
                "validate",
                "validation",
                "ablation",
                "baseline",
                "trial",
                "test",
                "\u5b9e\u9a8c",
                "\u9a8c\u8bc1",
                "\u5bf9\u7167",
            ),
        ),
        "failure_conditions": _contains_marker(
            combined,
            (
                "falsif",
                "failure",
                "fail",
                "negative control",
                "counter",
                "threshold",
                "\u8bc1\u4f2a",
                "\u5931\u8d25",
                "\u53cd\u8bc1",
            ),
        ),
        "evidence_scope": _contains_marker(
            combined,
            (
                "evidence",
                "fulltext",
                "citation",
                "dataset",
                "paper",
                "literature",
                "parsed",
                "\u8bc1\u636e",
                "\u6587\u732e",
                "\u5168\u6587",
                "\u6570\u636e",
            ),
        ),
    }


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _goal_readiness_status(*, research_goal: str, missing: list[str]) -> str:
    if len(research_goal.strip()) < 8:
        return "empty"
    if len(missing) >= 3:
        return "needs_refinement"
    if missing:
        return "partial"
    return "ready"


def _goal_readiness_guidance(*, status: str, missing: list[str]) -> str:
    if status == "empty":
        return "Add a concrete research goal before starting a run."
    if status == "ready":
        return "Goal is specific enough to review before starting or continuing a run."
    labels = {
        "mechanism_or_method": "mechanism or method",
        "observable_variables": "observable variables or metrics",
        "validation_path": "minimal validation path",
        "failure_conditions": "failure or falsification conditions",
        "evidence_scope": "evidence or literature scope",
    }
    missing_text = ", ".join(labels.get(item, item.replace("_", " ")) for item in missing[:3])
    return f"Refine the goal by adding {missing_text}."


def _goal_readiness_next_actions(*, status: str, missing: list[str]) -> list[str]:
    if status == "empty":
        return ["write_research_goal", "parse_evidence_first"]
    actions: list[str] = []
    if missing:
        actions.append("refine_research_goal")
    if "evidence_scope" in missing:
        actions.append("add_or_select_evidence")
    if "failure_conditions" in missing or "validation_path" in missing:
        actions.append("add_validation_constraints")
    actions.extend(["review_confirmation", "start_run"])
    return actions


def _sum_int(records: Iterable[Mapping[str, Any]], keys: tuple[str, ...]) -> int:
    total = 0
    for record in records:
        total += _safe_int(_first_value(record, keys)) or 0
    return total


def _count_records_with_value(
    records: Iterable[Mapping[str, Any]],
    keys: tuple[str, ...],
    *,
    value_match: Optional[str],
) -> int:
    total = 0
    for record in records:
        value = _first_value(record, keys)
        if value_match is None:
            total += 1 if value else 0
        elif str(value or "").lower() == value_match:
            total += 1
    return total


def _library_source_reliability_counts(
    paper_records: list[Mapping[str, Any]],
    evidence_records: list[Mapping[str, Any]],
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for record in [*paper_records, *evidence_records]:
        reliability = str(_first_value(record, ("source_reliability", "reliability")) or "unknown")
        counts[reliability] = counts.get(reliability, 0) + 1
    return counts


def _library_paper_surface_summary(paper: Mapping[str, Any], *, index: int) -> Dict[str, Any]:
    reliability = str(_first_value(paper, ("source_reliability", "reliability")) or "unknown")
    chunks_count = _safe_int(_first_value(paper, ("chunks_count", "chunk_count"))) or 0
    experimental_count = _safe_int(_first_value(paper, ("experimental_chunks_count", "experimental_support_count"))) or 0
    return {
        "index": index,
        "title": _compact_text(_first_text(paper, ("title", "paper_title", "document_title", "name")) or "Untitled paper", max_length=160),
        "source_type": str(_first_value(paper, ("source", "source_type", "kind")) or "unknown"),
        "source_reliability": reliability,
        "status": _library_paper_status(reliability=reliability, chunks_count=chunks_count),
        "chunks_count": chunks_count,
        "experimental_chunks_count": experimental_count,
        "next_actions": _library_paper_next_actions(reliability=reliability, chunks_count=chunks_count),
    }


def _library_paper_status(*, reliability: str, chunks_count: int) -> str:
    if reliability == "parsed_fulltext" and chunks_count > 0:
        return "ready"
    if reliability in {"metadata", "abstract", "snippet_only", "best_effort_public_search_snippet"} or chunks_count == 0:
        return "limited"
    return "available"


def _library_paper_next_actions(*, reliability: str, chunks_count: int) -> list[str]:
    actions = ["inspect_evidence"]
    if reliability != "parsed_fulltext" or chunks_count == 0:
        actions.insert(0, "parse_fulltext")
    actions.append("use_for_hypothesis_grounding")
    return actions


def _library_parse_job_surface_summary(parse_run: Mapping[str, Any], *, index: int) -> Dict[str, Any]:
    summary = _as_mapping(parse_run.get("parse_status_summary"))
    failed_items = _as_list(summary.get("failed_items"))
    raw_status = str(_first_value(parse_run, ("status", "state")) or "").lower()
    status = _parse_job_status(parse_run=parse_run, summary=summary, raw_status=raw_status, failed_items=failed_items)
    return {
        "index": index,
        "status": status,
        "source_title": _compact_text(_first_text(parse_run, ("title", "source_title", "filename", "input_name")) or "Parse job", max_length=140),
        "chunks_count": _safe_int(_first_value(parse_run, ("chunks_count", "chunk_count"))) or 0,
        "experimental_chunks_count": _safe_int(_first_value(parse_run, ("experimental_chunks_count", "experimental_support_count"))) or 0,
        "rag_search_ready": bool(parse_run.get("rag_search_ready")),
        "completion_rate": _safe_number(summary.get("completion_rate")),
        "failed_item_count": len(failed_items),
    }


def _parse_job_status(
    *,
    parse_run: Mapping[str, Any],
    summary: Mapping[str, Any],
    raw_status: str,
    failed_items: list[Any],
) -> str:
    if raw_status in {"queued", "running", "processing"}:
        return "processing"
    if raw_status in {"error", "failed"} or failed_items:
        return "error"
    if raw_status in {"warning", "partial"} or (summary.get("warning_items") or 0):
        return "warning"
    if raw_status in {"complete", "completed", "success"} or parse_run.get("rag_search_ready"):
        return "complete"
    return "unknown"


def _parse_job_counts(items: list[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {"processing": 0, "complete": 0, "warning": 0, "error": 0, "unknown": 0}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status if status in counts else "unknown"] += 1
    return counts


def _evidence_library_status(
    *,
    counts: Mapping[str, int],
    parse_counts: Mapping[str, int],
    reliability_counts: Mapping[str, int],
) -> str:
    if parse_counts.get("processing", 0):
        return "processing"
    if counts.get("papers", 0) == 0 and counts.get("evidence_items", 0) == 0:
        return "empty"
    if parse_counts.get("error", 0) and reliability_counts.get("parsed_fulltext", 0) == 0:
        return "needs_attention"
    if reliability_counts.get("parsed_fulltext", 0):
        return "ready"
    return "limited"


def _evidence_library_readiness(
    *,
    status: str,
    counts: Mapping[str, int],
    parse_counts: Mapping[str, int],
) -> Dict[str, Any]:
    return {
        "status": status,
        "parsed_fulltext_available": counts.get("parsed_fulltext_sources", 0) > 0,
        "experimental_evidence_available": counts.get("experimental_chunks", 0) > 0,
        "active_parse_jobs": parse_counts.get("processing", 0),
        "summary": {
            "empty": "No evidence has been added yet.",
            "processing": "Evidence parsing is in progress; results will become searchable after indexing.",
            "needs_attention": "Evidence parsing needs review before the library can ground research runs.",
            "limited": "Evidence exists, but parsed fulltext support is not available yet.",
            "ready": "Parsed fulltext evidence is available for grounding and verification.",
        }.get(status, "Inspect evidence readiness before using this library."),
    }


def _evidence_library_next_actions(
    *,
    status: str,
    counts: Mapping[str, int],
    parse_counts: Mapping[str, int],
) -> list[str]:
    if status == "empty":
        return ["upload_pdf", "add_web_evidence", "search_literature"]
    if status == "processing":
        return ["monitor_parse_jobs", "inspect_parse_results"]
    if status == "needs_attention":
        return ["inspect_parse_errors", "retry_parse", "add_web_evidence"]
    actions: list[str] = []
    if status == "limited":
        actions.extend(["parse_fulltext", "add_more_evidence"])
    if counts.get("experimental_chunks", 0) == 0:
        actions.append("add_experimental_evidence")
    actions.extend(["use_for_hypothesis_grounding", "verify_hypothesis_evidence"])
    if parse_counts.get("warning", 0):
        actions.append("inspect_parse_warnings")
    return actions


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


def _report_findings(source: Mapping[str, Any], hypothesis_items: list[Mapping[str, Any]]) -> list[str]:
    findings = _surface_text_items(
        _first_value(source, ("findings", "finding_summary", "key_findings", "claims")),
        max_items=6,
        max_length=260,
    )
    if findings:
        return findings
    return [
        _compact_text(item.get("plain_summary") or item.get("title"), max_length=220)
        for item in hypothesis_items[:3]
        if item.get("plain_summary") or item.get("title")
    ]


def _report_limitations(
    *,
    source: Mapping[str, Any],
    mode_boundary: Mapping[str, Any],
    evidence_boundary: Any,
    experiment_summary: Mapping[str, Any],
) -> list[str]:
    limitations = _surface_text_items(
        _first_value(source, ("limitations", "known_limitations", "known_gaps", "evidence_gaps")),
        max_items=8,
        max_length=220,
    )
    boundary = _as_mapping(evidence_boundary)
    mode = str(mode_boundary.get("mode") or "")
    if mode == "demo_only":
        limitations.append("Demo output is for workflow/schema validation only, not scientific evidence.")
    elif mode_boundary.get("evidence_status") in {"absent", "unknown", "limited"} and boundary.get("status") not in {
        "parsed_fulltext",
        "experimental_data",
    }:
        limitations.append("Evidence support is limited; treat findings as draft hypotheses until fulltext support is verified.")
    if boundary.get("status") == "contradicted":
        limitations.append("At least one evidence item contradicts or fails to support a reported claim.")
    elif boundary.get("status") == "absent":
        limitations.append("No evidence sources are attached to this report surface.")
    missing_experiment = _as_list(experiment_summary.get("missing_sections"))
    if missing_experiment:
        limitations.append(f"Experiment design is incomplete: {', '.join(str(item) for item in missing_experiment[:4])}.")
    return _dedupe_text_items(limitations)


def _citation_qa_surface_summary(source: Mapping[str, Any], evidence_collection: Mapping[str, Any]) -> Dict[str, Any]:
    qa = _as_mapping(_first_value(source, ("citation_qa", "citation_provenance_qa", "citationQa")))
    status = str(_first_value(qa, ("status", "result", "decision")) or "").strip().lower()
    evidence_count = _safe_int(evidence_collection.get("evidence_count")) or 0
    if status in {"passed", "pass", "checked", "ok", "complete"}:
        normalized = "passed"
    elif status in {"failed", "error", "citation_mismatch", "mismatch"}:
        normalized = "needs_review"
    elif evidence_count > 0:
        normalized = "available"
    else:
        normalized = "missing"
    return {
        "status": normalized,
        "checked": normalized in {"passed", "needs_review"},
        "evidence_count": evidence_count,
        "summary": _compact_text(_first_value(qa, ("summary", "message", "note")), max_length=220),
    }


def _report_status(
    *,
    findings: list[str],
    evidence_boundary: Any,
    experiment_status: str,
    citation_qa: Mapping[str, Any],
) -> str:
    if not findings:
        return "empty"
    boundary = _as_mapping(evidence_boundary)
    if boundary.get("status") == "contradicted" or citation_qa.get("status") == "needs_review":
        return "needs_review"
    if boundary.get("status") in {"absent", "limited"} or experiment_status in {"absent", "limited"}:
        return "draft"
    return "ready"


def _report_next_actions(*, status: str, citation_qa: Mapping[str, Any], limitations: list[str]) -> list[str]:
    if status == "empty":
        return ["select_hypotheses", "draft_findings"]
    actions = ["review_limitations"] if limitations else []
    if citation_qa.get("status") in {"missing", "available"}:
        actions.append("run_citation_qa")
    if status == "needs_review":
        actions.append("resolve_evidence_conflicts")
    actions.extend(["copy_report", "export_report"])
    return actions


def _dedupe_text_items(items: Iterable[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        compact = _compact_text(item, max_length=260)
        key = compact.lower()
        if compact and key not in seen:
            deduped.append(compact)
            seen.add(key)
    return deduped


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


def _work_queue_counts(
    *,
    snapshot: Mapping[str, Any],
    worker: Mapping[str, Any],
    items: list[Mapping[str, Any]],
) -> Dict[str, int]:
    active_snapshot = _as_mapping(worker.get("active_work_item_snapshot"))
    raw_counts = _as_mapping(snapshot.get("counts")) or _as_mapping(active_snapshot.get("counts"))
    queue_counts = _as_mapping(worker.get("queue_status_counts"))
    statuses = ("queued", "leased", "running", "retrying", "blocked", "complete", "error", "cancelled")
    counts: Dict[str, int] = {}
    for status in statuses:
        explicit = _first_value(raw_counts, (status,))
        if explicit is None:
            explicit = _first_value(queue_counts, (status, f"{status}_count"))
        value = _safe_int(explicit)
        if value is None:
            value = sum(1 for item in items if str(item.get("status") or "").lower() == status)
        counts[status] = max(0, value)
    active_explicit = _first_value(raw_counts, ("active", "active_work_items", "active_work_item_count"))
    if active_explicit is None:
        active_explicit = _first_value(queue_counts, ("active", "active_count", "active_work_item_count"))
    active = _safe_int(active_explicit)
    if active is None:
        active = sum(counts[status] for status in ("queued", "leased", "running", "retrying", "blocked"))
    counts["active"] = max(0, active)
    return counts


def _work_queue_surface_status(*, counts: Mapping[str, int], worker_enabled: bool) -> str:
    active = _safe_int(counts.get("active")) or 0
    if active == 0 and (_safe_int(counts.get("error")) or 0) == 0:
        return "empty"
    if not worker_enabled and active > 0:
        return "worker_disabled"
    if (_safe_int(counts.get("blocked")) or 0) > 0 or (_safe_int(counts.get("error")) or 0) > 0:
        return "needs_attention"
    if (_safe_int(counts.get("retrying")) or 0) > 0:
        return "retrying"
    if (_safe_int(counts.get("running")) or 0) > 0 or (_safe_int(counts.get("leased")) or 0) > 0:
        return "running"
    if (_safe_int(counts.get("queued")) or 0) > 0:
        return "queued"
    return "active"


def _work_queue_surface_recovery_action(
    *,
    snapshot: Mapping[str, Any],
    active_snapshot: Mapping[str, Any],
    worker: Mapping[str, Any],
    item_previews: list[Mapping[str, Any]],
) -> str:
    worker_user_status = _as_mapping(worker.get("user_facing_status"))
    action = (
        _first_value(snapshot, ("recovery_action",))
        or _first_value(active_snapshot, ("recovery_action",))
        or _first_value(worker_user_status, ("recovery_action",))
    )
    if action:
        return _compact_text(action, max_length=40)
    for item in item_previews:
        item_action = item.get("recovery_action")
        if item_action and str(item_action) != "none":
            return _compact_text(item_action, max_length=40)
    return "none"


def _work_queue_surface_recovery_action_counts(
    *,
    snapshot: Mapping[str, Any],
    active_snapshot: Mapping[str, Any],
    worker: Mapping[str, Any],
) -> Dict[str, int]:
    worker_user_status = _as_mapping(worker.get("user_facing_status"))
    raw_counts = (
        _as_mapping(snapshot.get("recovery_action_counts"))
        or _as_mapping(active_snapshot.get("recovery_action_counts"))
        or _as_mapping(worker_user_status.get("recovery_action_counts"))
    )
    return {
        action: _safe_int(raw_counts.get(action)) or 0
        for action in ("wait", "retry", "unblock", "escalate", "inspect", "none")
    }


def _work_queue_item_surface(item: Mapping[str, Any], *, index: int) -> Dict[str, Any]:
    status = str(_first_value(item, ("status",)) or "unknown").lower()
    attempt_count = _safe_int(_first_value(item, ("attempt_count", "attempts"))) or 0
    max_attempts = _safe_int(_first_value(item, ("max_attempts",))) or 0
    surface = {
        "index": index + 1,
        "status": status,
        "status_label": _first_value(item, ("status_label",)) or _work_queue_status_label(status),
        "workflow_name": _compact_text(
            _first_value(item, ("workflow_name", "workflow")) or "research_workflow",
            max_length=96,
        ),
        "phase": _compact_text(_first_value(item, ("phase",)) or "workflow", max_length=80),
        "agent_role": _compact_text(
            _first_value(item, ("agent_role", "role")) or "workflow_runner",
            max_length=80,
        ),
        "priority": _safe_int(item.get("priority")) or 0,
        "attempts": {"current": attempt_count, "max": max_attempts},
        "next_action": _first_value(item, ("next_action",)) or _work_queue_item_next_action(status),
    }
    recovery_action = _first_value(item, ("recovery_action",))
    if recovery_action:
        surface["recovery_action"] = _compact_text(recovery_action, max_length=40)
    return surface


def _work_queue_status_label(status: str) -> str:
    labels = {
        "queued": "Queued",
        "leased": "Preparing",
        "running": "Running",
        "retrying": "Retrying",
        "blocked": "Blocked",
        "complete": "Complete",
        "error": "Error",
        "cancelled": "Cancelled",
    }
    return labels.get(status, "Unknown")


def _work_queue_item_next_action(status: str) -> str:
    return {
        "queued": "Wait for the worker to pick up this task.",
        "leased": "Monitor worker startup for this task.",
        "running": "Monitor progress and process summary.",
        "retrying": "Wait for retry or inspect queue details.",
        "blocked": "Inspect blocker before retrying.",
        "error": "Inspect failure summary before retrying.",
        "complete": "Inspect run results.",
        "cancelled": "Start a new run if needed.",
    }.get(status, "Inspect queue state.")


def _work_queue_next_actions(status: str) -> list[str]:
    if status == "empty":
        return ["start_or_continue_research_run"]
    if status == "worker_disabled":
        return ["start_worker_or_manual_tick", "monitor_queue"]
    if status == "needs_attention":
        return ["inspect_queue", "retry_or_cancel_work_item"]
    if status == "retrying":
        return ["wait_for_retry", "inspect_queue"]
    if status == "running":
        return ["monitor_progress", "view_process_summary"]
    if status == "queued":
        return ["wait_for_worker", "check_worker_status"]
    return ["inspect_queue"]


def _runtime_researcher_label(status: str) -> str:
    return {
        "ready": "Research task infrastructure is ready.",
        "limited": "Research task infrastructure is available with limitations.",
        "offline": "Some required research services are offline.",
        "permission_denied": "A required research service needs authorization.",
    }.get(status, "Inspect runtime readiness before starting long-running work.")


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


def _feedback_target_summary(feedback_items: list[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    targets: Dict[str, int] = {}
    for item in feedback_items:
        target_type = str(item.get("target_type") or "unknown")
        feedback_type = str(item.get("feedback_type") or "unknown")
        key = f"{target_type}:{feedback_type}"
        targets[key] = targets.get(key, 0) + 1
    return [
        {
            "target_type": key.split(":", 1)[0],
            "feedback_type": key.split(":", 1)[1],
            "count": count,
        }
        for key, count in sorted(targets.items())
    ]


def _feedback_next_actions(feedback_items: list[Mapping[str, Any]]) -> list[str]:
    if not feedback_items:
        return ["add_feedback", "select_hypothesis_or_run"]
    actions = ["review_feedback_summary", "apply_to_next_run_or_continuation"]
    if any(str(item.get("target_type") or "") == "hypothesis" for item in feedback_items):
        actions.append("continue_or_revise_hypotheses")
    return actions


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
    recovery_action_counts = _work_queue_surface_recovery_action_counts(
        snapshot=work_snapshot,
        active_snapshot={},
        worker={},
    )
    summary = {
        "active_work_item_count": _safe_int(counts.get("active")) or 0,
        "queued_count": _safe_int(counts.get("queued")) or 0,
        "retrying_count": _safe_int(counts.get("retrying")) or 0,
        "running_count": _safe_int(counts.get("running")) or 0,
        "recovery_action": _work_queue_surface_recovery_action(
            snapshot=work_snapshot,
            active_snapshot={},
            worker={},
            item_previews=[work_item] if work_item else [],
        ),
        "recovery_action_counts": recovery_action_counts,
        "current_work_status": work_item.get("status"),
        "current_work_label": work_item.get("status_label"),
        "current_work_next_action": work_item.get("next_action"),
    }
    recovery_action = work_item.get("recovery_action")
    if recovery_action:
        summary["current_work_recovery_action"] = _compact_text(recovery_action, max_length=40)
    return summary


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


def _memory_parent_run_surface_summary(parent_run: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    if not parent_run:
        return None
    hypothesis_count = _safe_int(
        _first_value(parent_run, ("hypothesis_count", "hypotheses_count", "prior_hypothesis_count"))
    )
    if hypothesis_count is None:
        hypothesis_count = _list_length(parent_run.get("hypotheses"))
    return {
        "research_goal": _compact_text(
            _first_value(parent_run, ("research_goal", "goal", "summary")),
            max_length=260,
        ),
        "status": parent_run.get("status"),
        "hypothesis_count": hypothesis_count or 0,
        "updated_at": parent_run.get("updated_at"),
    }


def _memory_evidence_scope(
    *,
    source: Mapping[str, Any],
    evidence_collection: Mapping[str, Any],
) -> Dict[str, Any]:
    raw_boundary = _as_mapping(source.get("evidence_boundary"))
    reliability_counts = _as_mapping(evidence_collection.get("source_reliability_counts"))
    support_counts = _as_mapping(evidence_collection.get("support_level_counts"))
    evidence_items = _record_items(source.get("evidence_summaries") or source.get("evidence_items"))
    library_ids = {
        str(item.get("library_id"))
        for item in evidence_items
        if isinstance(item, Mapping) and item.get("library_id")
    }
    return {
        "status": raw_boundary.get("status") or _as_mapping(evidence_collection.get("boundary")).get("status") or "absent",
        "evidence_count": _safe_int(raw_boundary.get("evidence_count")) or evidence_collection.get("evidence_count") or 0,
        "parsed_fulltext_count": _safe_int(raw_boundary.get("parsed_fulltext_count"))
        or _safe_int(reliability_counts.get("parsed_fulltext"))
        or 0,
        "experimental_data_count": _safe_int(raw_boundary.get("experimental_data_count"))
        or _safe_int(support_counts.get("experimental_data"))
        or 0,
        "library_count": len(library_ids),
        "source_reliability_counts": dict(reliability_counts),
        "support_level_counts": dict(support_counts),
        "boundary_summary": _compact_text(
            raw_boundary.get("boundary") or _as_mapping(evidence_collection.get("boundary")).get("summary"),
            max_length=220,
        ),
    }


def _memory_execution_surface_summary(execution_memory: Mapping[str, Any]) -> Dict[str, Any]:
    status = execution_memory.get("status") or "not_available"
    resume_supported = bool(execution_memory.get("resume_supported"))
    can_resume = bool(execution_memory.get("can_resume")) if "can_resume" in execution_memory else resume_supported
    should_retry = (
        bool(execution_memory.get("should_retry"))
        if "should_retry" in execution_memory
        else str(status) == "limited" and not can_resume
    )
    recovery_action = execution_memory.get("recovery_action") or _memory_execution_recovery_action(str(status))
    return {
        "status": status,
        "phase": execution_memory.get("phase"),
        "resume_supported": resume_supported,
        "can_resume": can_resume,
        "should_retry": should_retry,
        "recovery_action": recovery_action,
        "next_actions": list(execution_memory.get("next_actions") or _memory_execution_next_actions(recovery_action)),
        "checkpoint_backend": execution_memory.get("checkpoint_backend"),
        "resume_mode": execution_memory.get("resume_mode"),
    }


def _memory_execution_recovery_action(status: str) -> str:
    if status == "ready":
        return "resume"
    if status == "limited":
        return "retry"
    return "none"


def _memory_execution_next_actions(recovery_action: Any) -> list[str]:
    if recovery_action == "resume":
        return ["resume_langgraph_thread", "monitor_progress"]
    if recovery_action == "retry":
        return ["retry_from_durable_queue", "inspect_checkpoint_metadata"]
    return ["continue_without_checkpoint"]


def _memory_injection_policy_surface_summary(policy: Mapping[str, Any]) -> Dict[str, Any]:
    if not policy:
        return {
            "status": "not_declared",
            "mode": "unknown",
            "raw_injection_allowed": False,
            "prompt_sections": [],
            "target_prompts": [],
            "excluded_raw_field_count": 0,
            "boundary_summary": "No memory injection policy was declared for this context.",
        }
    prompt_sections = [
        _compact_text(item, max_length=80)
        for item in _as_list(policy.get("prompt_sections"))
        if str(item).strip()
    ][:8]
    target_prompts = [
        _compact_text(item, max_length=40)
        for item in _as_list(policy.get("target_prompts"))
        if str(item).strip()
    ][:8]
    excluded_raw_fields = [
        _compact_text(item, max_length=80)
        for item in _as_list(policy.get("excluded_raw_fields"))
        if str(item).strip()
    ]
    raw_allowed = bool(policy.get("raw_injection_allowed"))
    return {
        "status": "raw_allowed" if raw_allowed else "summary_only",
        "mode": _compact_text(policy.get("mode") or "summary_only", max_length=80),
        "memory_scope": policy.get("memory_scope"),
        "memory_sources": _preview_list(_as_list(policy.get("memory_sources")), max_items=8, max_length=60),
        "prompt_sections": prompt_sections,
        "target_prompts": target_prompts,
        "counts": dict(_as_mapping(policy.get("counts"))),
        "evidence_status": policy.get("evidence_status"),
        "raw_injection_allowed": raw_allowed,
        "excluded_raw_field_count": len(excluded_raw_fields),
        "excluded_raw_fields": excluded_raw_fields[:8],
        "boundary_summary": (
            "Raw memory injection is enabled; inspect expert policy before running."
            if raw_allowed
            else "Memory injection uses summary-only guidance; raw memory payloads require expert disclosure."
        ),
    }


def _prompt_packet_section_surface(section: Mapping[str, Any], *, index: int) -> Dict[str, Any]:
    section_id = _compact_text(
        _first_value(section, ("section", "name", "id")) or f"section_{index + 1}",
        max_length=80,
    )
    item_count = len(_record_items(section.get("items")))
    return {
        "index": index + 1,
        "section": section_id,
        "label": _prompt_packet_section_label(section_id),
        "item_count": item_count,
        "default_state": "collapsed",
    }


def _prompt_packet_section_label(section_id: str) -> str:
    labels = {
        "parent_run_summary": "Parent run summary",
        "related_run_summaries": "Related run summaries",
        "prior_hypothesis_summaries": "Prior hypothesis summaries",
        "feedback_type_and_target_summary": "Feedback type and target summary",
        "execution_memory_summary": "Execution memory summary",
        "evidence_boundary_and_snippet_summaries": "Evidence boundary summaries",
        "memory_limitations": "Memory limitations",
    }
    return labels.get(section_id, section_id.replace("_", " ").title())


def _prompt_packet_surface_status(
    *,
    packet_available: bool,
    raw_allowed: bool,
    section_count: int,
) -> str:
    if not packet_available:
        return "absent"
    if raw_allowed:
        return "raw_allowed"
    if section_count <= 0:
        return "empty"
    return "summary_only"


def _prompt_packet_next_actions(status: str) -> list[str]:
    if status == "absent":
        return ["build_memory_context", "review_generation_request"]
    if status == "raw_allowed":
        return ["inspect_expert_prompt_packet", "disable_raw_memory_injection"]
    if status == "empty":
        return ["add_parent_run_feedback_or_evidence", "continue_without_memory"]
    return ["review_memory_summary", "start_or_continue_run"]


def _memory_surface_status(
    *,
    counts: Mapping[str, int],
    evidence_status: str,
    execution_status: str,
) -> str:
    total_context = sum(int(counts.get(key, 0)) for key in ("related_runs", "prior_hypotheses", "user_feedback", "evidence_sources"))
    total_context += int(counts.get("parent_run", 0))
    if total_context == 0:
        return "empty"
    if evidence_status == "contradicted":
        return "needs_review"
    if evidence_status in {"absent", "limited"} or execution_status in {"limited", "not_available"}:
        return "limited"
    return "ready"


def _memory_history_summary(
    *,
    parent_run: Mapping[str, Any],
    counts: Mapping[str, int],
    evidence_scope: Mapping[str, Any],
) -> list[str]:
    items: list[str] = []
    parent_goal = _compact_text(_first_value(parent_run, ("research_goal", "goal", "summary")), max_length=180)
    if parent_goal:
        items.append(f"Parent run context: {parent_goal}")
    if int(counts.get("prior_hypotheses", 0)) > 0:
        items.append(f"{counts.get('prior_hypotheses')} prior hypothesis summary item(s) are available.")
    if int(counts.get("user_feedback", 0)) > 0:
        items.append(f"{counts.get('user_feedback')} user feedback item(s) will guide the next run or continuation.")
    evidence_count = int(evidence_scope.get("evidence_count") or 0)
    if evidence_count > 0:
        items.append(f"{evidence_count} evidence summary item(s) matched the selected memory scope.")
    if int(counts.get("known_gaps", 0)) > 0:
        items.append(f"{counts.get('known_gaps')} known memory limitation(s) apply.")
    return items[:5]


def _memory_next_actions(*, status: str, evidence_status: str) -> list[str]:
    if status == "empty":
        return ["select_parent_run", "add_feedback", "parse_evidence"]
    if status == "needs_review":
        return ["inspect_memory_evidence", "revise_memory_scope", "continue_with_caution"]
    actions = ["review_context"]
    if evidence_status in {"absent", "limited"}:
        actions.append("add_or_parse_evidence")
    actions.append("continue_run")
    return actions


def _memory_checkpoint_value(execution_memory: Mapping[str, Any], key: str) -> Any:
    value = execution_memory.get(key)
    if value:
        return value
    latest = _as_mapping(execution_memory.get("latest_checkpoint"))
    return latest.get(key)


def _workspace_primary_surface(
    *,
    goal_summary: Mapping[str, Any],
    confirmation_summary: Optional[Mapping[str, Any]],
    run_summary: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    if run_summary:
        run_status = str(run_summary.get("status") or "")
        if run_status in {"complete", "completed"}:
            surface = "active_result_canvas"
            title = "Inspect research results"
        elif run_status in {"queued", "pending", "running", "retrying"}:
            surface = "run_progress"
            title = "Monitor research run"
        elif run_status in {"error", "failed", "stale"}:
            surface = "recovery_panel"
            title = "Recover research run"
        else:
            surface = "run_summary"
            title = "Review research run"
        return {
            "surface": surface,
            "title": title,
            "status": run_summary.get("status"),
            "next_actions": list(run_summary.get("next_actions") or ["inspect_run"]),
        }
    if confirmation_summary and confirmation_summary.get("status") == "pending":
        return {
            "surface": "run_confirmation_card",
            "title": "Confirm research task",
            "status": "pending_confirmation",
            "next_actions": list(confirmation_summary.get("next_actions") or ["confirm_start_run", "edit_request"]),
        }
    goal_status = str(goal_summary.get("status") or "empty")
    return {
        "surface": "research_goal_composer",
        "title": "Define research goal",
        "status": goal_status,
        "next_actions": list(goal_summary.get("next_actions") or ["write_research_goal"]),
    }


def _workspace_status(
    *,
    primary_surface: Mapping[str, Any],
    run_summary: Optional[Mapping[str, Any]],
    goal_summary: Mapping[str, Any],
    runtime_summary: Optional[Mapping[str, Any]],
) -> str:
    runtime_status = str(_as_mapping(runtime_summary).get("status") or "")
    if runtime_status in {"offline", "permission_denied"}:
        return "needs_attention"
    if run_summary:
        run_status = str(run_summary.get("status") or "")
        if run_status in {"error", "failed", "stale"}:
            return "needs_attention"
        if run_status in {"queued", "pending", "running", "retrying"}:
            return "in_progress"
        if run_status in {"complete", "completed"}:
            return "results_ready"
    if primary_surface.get("surface") == "run_confirmation_card":
        return "ready_to_start"
    if goal_summary.get("status") in {"empty", "needs_refinement"}:
        return "needs_goal"
    return "ready_to_start"


def _workspace_inspectors(
    *,
    memory_summary: Optional[Mapping[str, Any]],
    evidence_library_summary: Optional[Mapping[str, Any]],
    runtime_summary: Optional[Mapping[str, Any]],
    agent_trace_available: bool,
) -> list[Dict[str, Any]]:
    inspectors = [
        {
            "id": "memory",
            "label": "History context",
            "available": bool(memory_summary and memory_summary.get("status") != "empty"),
            "default_state": "collapsed",
        },
        {
            "id": "evidence",
            "label": "Evidence readiness",
            "available": bool(evidence_library_summary and evidence_library_summary.get("status") != "empty"),
            "default_state": "collapsed",
        },
        {
            "id": "process",
            "label": "Process and evidence",
            "available": agent_trace_available,
            "default_state": "collapsed",
        },
        {
            "id": "runtime",
            "label": "Runtime readiness",
            "available": bool(runtime_summary),
            "default_state": "collapsed",
        },
    ]
    return inspectors


def _agent_process_records(trace_events: Any) -> list[Mapping[str, Any]]:
    source = _as_mapping(trace_events)
    if source:
        for key in ("items", "agent_trace", "trace", "events"):
            records = _record_items(source.get(key))
            if records:
                return records
        trace_count = _safe_int(source.get("trace_count"))
        if trace_count and trace_count > 0:
            return [
                {
                    "phase": "process_summary",
                    "status": "complete",
                    "summary": f"{trace_count} process trace event(s) are available in details.",
                }
            ]
        if _first_value(source, ("phase", "label", "output_summary", "summary", "status")):
            return [source]
        return []
    return _record_items(trace_events)


def _agent_process_phase_index(registry: Optional[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    source = _as_mapping(registry)
    phase_index = _as_mapping(source.get("phase_index"))
    if phase_index:
        return {
            str(phase): _as_mapping(spec)
            for phase, spec in phase_index.items()
            if _as_mapping(spec)
        }
    agents = _record_items(source.get("agents"))
    return {
        str(agent.get("phase")): agent
        for agent in agents
        if agent.get("phase")
    }


def _agent_process_item(
    event: Mapping[str, Any],
    *,
    phase_index: Mapping[str, Mapping[str, Any]],
    index: int,
) -> Dict[str, Any]:
    raw_phase = str(_first_value(event, ("phase", "source_phase")) or "").strip()
    phase = _agent_process_canonical_phase(raw_phase) or raw_phase or "unknown"
    spec = _as_mapping(phase_index.get(phase))
    label = (
        _first_value(event, ("label", "phase_label"))
        or _first_value(spec, ("label",))
        or AGENT_PROCESS_PHASE_LABELS.get(phase)
        or phase.replace("_", " ").title()
    )
    role = (
        _first_value(event, ("role", "agent_role"))
        or _first_value(spec, ("role",))
        or AGENT_PROCESS_PHASE_ROLES.get(phase)
        or "Records a research workflow step."
    )
    return {
        "index": index,
        "phase": phase,
        "source_phase": raw_phase or None,
        "label": _compact_text(label, max_length=120),
        "role": _compact_text(role, max_length=220),
        "status": _agent_process_item_status(event),
        "output_summary": _agent_process_output_summary(event),
        "tool_call_count": _agent_process_tool_call_count(event),
        "synthetic": bool(event.get("synthetic")),
        "degradation_reason": _compact_text(event.get("degradation_reason"), max_length=180),
        "agent_id": _first_value(event, ("agent_id",)) or _first_value(spec, ("agent_id",)),
        "event_id": _first_value(event, ("event_id", "trace_id", "id")),
        "prompt_template": _first_value(event, ("prompt_template", "template_name"))
        or _first_value(spec, ("prompt_template",)),
        "token_usage": _first_value(event, ("token_usage", "usage")),
    }


def _agent_process_default_item(item: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "phase": item.get("phase"),
        "source_phase": item.get("source_phase"),
        "label": item.get("label"),
        "role": item.get("role"),
        "status": item.get("status"),
        "output_summary": item.get("output_summary"),
        "tool_call_count": item.get("tool_call_count"),
        "synthetic": bool(item.get("synthetic")),
        "degradation_reason": item.get("degradation_reason"),
    }


def _agent_process_canonical_phase(phase: str) -> Optional[str]:
    normalized = str(phase or "").strip()
    if not normalized:
        return None
    if normalized in AGENT_PROCESS_PHASE_ORDER:
        return normalized
    return AGENT_PROCESS_PHASE_ALIASES.get(normalized)


def _agent_process_sort_key(phase: str, *, fallback_index: int) -> tuple[int, int, str]:
    canonical = _agent_process_canonical_phase(phase)
    if canonical:
        return (AGENT_PROCESS_PHASE_ORDER.index(canonical), fallback_index, canonical)
    return (len(AGENT_PROCESS_PHASE_ORDER), fallback_index, str(phase or ""))


def _agent_process_item_status(event: Mapping[str, Any]) -> str:
    raw_status = str(event.get("status") or "").strip().lower()
    status_aliases = {
        "completed": "complete",
        "complete": "complete",
        "success": "complete",
        "ok": "complete",
        "running": "running",
        "in_progress": "running",
        "queued": "running",
        "pending": "running",
        "failed": "failed",
        "failure": "failed",
        "error": "failed",
        "degraded": "degraded",
        "skipped": "degraded",
        "synthetic": "synthetic",
        "demo": "synthetic",
    }
    if raw_status in status_aliases:
        return status_aliases[raw_status]
    if _first_value(event, ("error", "error_message", "exception")):
        return "failed"
    if event.get("degradation_reason"):
        return "degraded"
    if event.get("synthetic"):
        return "synthetic"
    if _agent_process_output_summary(event) or _agent_process_tool_call_count(event) > 0:
        return "complete"
    return "unknown"


def _agent_process_output_summary(event: Mapping[str, Any]) -> str:
    for key in ("output_summary", "summary", "output", "content", "message"):
        value = event.get(key)
        if not value:
            continue
        if isinstance(value, Mapping):
            nested = _first_value(value, ("summary", "text", "message", "title"))
            if nested:
                return _compact_text(nested, max_length=280)
            continue
        if isinstance(value, (list, tuple, set)):
            return f"{len(value)} output item(s)."
        return _compact_text(value, max_length=280)
    return ""


def _agent_process_tool_call_count(event: Mapping[str, Any]) -> int:
    explicit = _safe_int(event.get("tool_call_count"))
    if explicit is not None:
        return max(0, explicit)
    tool_calls = event.get("tool_calls")
    if isinstance(tool_calls, (list, tuple, set)):
        return len(tool_calls)
    tool_results = event.get("tool_results")
    if isinstance(tool_results, (list, tuple, set)):
        return len(tool_results)
    return 0


def _agent_process_counts(items: list[Mapping[str, Any]]) -> Dict[str, int]:
    unknown_phases = [
        item
        for item in items
        if _agent_process_canonical_phase(str(item.get("phase") or "")) is None
    ]
    return {
        "complete": sum(1 for item in items if item.get("status") == "complete"),
        "running": sum(1 for item in items if item.get("status") == "running"),
        "degraded": sum(1 for item in items if item.get("status") == "degraded"),
        "failed": sum(1 for item in items if item.get("status") == "failed"),
        "synthetic": sum(1 for item in items if item.get("synthetic") or item.get("status") == "synthetic"),
        "unknown_status": sum(1 for item in items if item.get("status") == "unknown"),
        "unknown_phase": len(unknown_phases),
    }


def _agent_process_status(counts: Mapping[str, int]) -> str:
    total = sum(int(counts.get(key, 0)) for key in ("complete", "running", "degraded", "failed", "synthetic", "unknown_status"))
    if total == 0:
        return "absent"
    if int(counts.get("failed", 0)) > 0:
        return "needs_attention"
    if int(counts.get("running", 0)) > 0:
        return "in_progress"
    if (
        int(counts.get("degraded", 0)) > 0
        or int(counts.get("missing_phase", 0)) > 0
        or int(counts.get("unknown_phase", 0)) > 0
        or int(counts.get("unknown_status", 0)) > 0
    ):
        return "partial"
    return "ready"


def _agent_process_current_phase(items: list[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    running = [item for item in items if item.get("status") == "running"]
    candidate = running[0] if running else (items[-1] if items else None)
    if not candidate:
        return None
    return {
        "phase": candidate.get("phase"),
        "label": candidate.get("label"),
        "status": candidate.get("status"),
    }


def _agent_process_phase_coverage(
    items: list[Mapping[str, Any]],
    *,
    phase_index: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    expected = [
        phase
        for phase in AGENT_PROCESS_PHASE_ORDER
        if phase in phase_index or not phase_index
    ]
    observed: list[str] = []
    for item in items:
        phase = _agent_process_canonical_phase(str(item.get("phase") or "")) or str(item.get("phase") or "")
        if phase and phase not in observed:
            observed.append(phase)
    missing = [phase for phase in expected if phase not in observed]
    return {
        "expected_phases": expected,
        "observed_phases": observed,
        "missing_phases": missing,
        "covered_count": len([phase for phase in expected if phase in observed]),
        "expected_count": len(expected),
        "complete": bool(expected) and not missing,
    }


def _agent_process_next_actions(*, status: str, counts: Mapping[str, int]) -> list[str]:
    if status == "absent":
        return ["run_research_task", "inspect_timeline"]
    if status == "needs_attention":
        return ["inspect_process_details", "retry_or_continue"]
    if status == "in_progress":
        return ["monitor_progress", "inspect_process_summary"]
    if status == "partial":
        actions = ["inspect_process_summary"]
        if int(counts.get("degraded", 0)) > 0:
            actions.append("review_capability_degradation")
        if int(counts.get("missing_phase", 0)) > 0:
            actions.append("inspect_missing_research_steps")
        if int(counts.get("unknown_phase", 0)) > 0:
            actions.append("inspect_unknown_steps")
        actions.append("inspect_evidence")
        return actions
    return ["inspect_results", "inspect_evidence", "design_experiment"]


def _run_recovery_summary(recovery: Mapping[str, Any]) -> Dict[str, Any]:
    recovery_mode = recovery.get("recovery_mode")
    recovery_action = recovery.get("recovery_action") or _run_recovery_action(str(recovery_mode or ""))
    return {
        "recovery_mode": recovery_mode,
        "label": recovery.get("label") or _run_recovery_label(str(recovery_mode or "")),
        "recovery_action": recovery_action,
        "can_resume": bool(recovery.get("can_resume")),
        "should_retry": bool(recovery.get("should_retry")),
        "next_action": recovery.get("next_action"),
    }


def _run_recovery_label(recovery_mode: str) -> str:
    return {
        "resume_from_checkpoint": "Run can resume from a checkpoint.",
        "metadata_guided_retry": "Run can retry with checkpoint metadata guidance.",
        "queue_retry_without_checkpoint": "Run can retry through the durable queue.",
        "checkpoint_thread_mismatch": "Run recovery needs attention.",
        "not_recoverable": "Run cannot be safely resumed.",
    }.get(recovery_mode, "Inspect run recovery state.")


def _run_recovery_action(recovery_mode: str) -> str:
    if recovery_mode == "resume_from_checkpoint":
        return "resume"
    if recovery_mode in {"metadata_guided_retry", "queue_retry_without_checkpoint"}:
        return "retry"
    if recovery_mode == "checkpoint_thread_mismatch":
        return "inspect"
    if recovery_mode == "not_recoverable":
        return "start_new_run"
    return "inspect"


def _phase_label(phase: str) -> Optional[str]:
    if not phase:
        return None
    return phase.replace("_", " ").title()
