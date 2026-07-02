from __future__ import annotations

from surface_models import (
    agent_process_surface_summary,
    evidence_library_surface_summary,
    evidence_surface_collection,
    evidence_surface_summary,
    experiment_design_surface_summary,
    feedback_surface_summary,
    hypothesis_surface_collection,
    hypothesis_surface_summary,
    memory_surface_summary,
    memory_prompt_packet_surface_summary,
    ranking_surface_summary,
    research_goal_readiness_surface_summary,
    report_surface_summary,
    runtime_readiness_surface_summary,
    run_confirmation_surface_summary,
    run_surface_summary,
    work_queue_surface_summary,
    workspace_surface_summary,
)


def test_research_goal_readiness_surface_summary_marks_ready_goal_without_raw_request() -> None:
    request = {
        "research_goal": (
            "Develop a causal retrieval-audit mechanism to reduce citation drift; "
            "measure support precision and contradiction rate against a parsed fulltext benchmark; "
            "validate with an ablation baseline and fail if support precision remains below 0.70."
        ),
        "preferences": "Use parsed fulltext evidence before model priors.",
        "constraints": ["Use local fulltext evidence first.", "Report failure thresholds."],
        "attributes": ["falsifiable", "evidence-grounded"],
        "starting_hypotheses": ["A claim-gating mechanism reduces unsupported citations."],
        "user_feedback": [
            {
                "feedback_id": "feedback-secret",
                "text": "SECRET FEEDBACK",
                "feedback_type": "prefer",
            }
        ],
        "parent_run_id": "parent-secret",
        "library_id": "library-secret",
        "memory_scope": "project",
    }

    summary = research_goal_readiness_surface_summary(request)

    assert summary["status"] == "ready"
    assert all(summary["signals"].values())
    assert summary["missing_elements"] == []
    assert summary["counts"] == {
        "constraints": 2,
        "attributes": 2,
        "starting_hypotheses": 1,
        "user_feedback": 1,
    }
    assert summary["next_actions"] == ["review_confirmation", "start_run"]
    assert summary["constraint_previews"] == [
        "Use local fulltext evidence first.",
        "Report failure thresholds.",
    ]
    assert summary["attribute_previews"] == ["falsifiable", "evidence-grounded"]
    assert summary["starting_hypothesis_previews"] == [
        "A claim-gating mechanism reduces unsupported citations."
    ]
    assert "internal_refs" not in summary
    assert "feedback-secret" not in str(summary)
    assert "SECRET FEEDBACK" not in str(summary)
    assert "parent-secret" not in str(summary)
    assert "library-secret" not in str(summary)

    expert_summary = research_goal_readiness_surface_summary(
        request,
        include_internal_refs=True,
    )
    assert expert_summary["internal_refs"]["parent_run_id"] == "parent-secret"
    assert expert_summary["internal_refs"]["library_id"] == "library-secret"
    assert expert_summary["internal_refs"]["memory_scope"] == "project"
    assert expert_summary["internal_refs"]["request_preview"]["user_feedback"][0]["feedback_id"] == "feedback-secret"


def test_research_goal_readiness_surface_summary_guides_refinement_and_empty_goal() -> None:
    vague = research_goal_readiness_surface_summary("Improve AI research")

    assert vague["status"] == "needs_refinement"
    assert vague["missing_elements"] == [
        "mechanism_or_method",
        "observable_variables",
        "validation_path",
        "failure_conditions",
        "evidence_scope",
    ]
    assert "mechanism or method" in vague["guidance"]
    assert vague["next_actions"] == [
        "refine_research_goal",
        "add_or_select_evidence",
        "add_validation_constraints",
        "review_confirmation",
        "start_run",
    ]

    empty = research_goal_readiness_surface_summary({"research_goal": "short"})

    assert empty["status"] == "empty"
    assert empty["next_actions"] == ["write_research_goal", "parse_evidence_first"]
    assert empty["counts"] == {
        "constraints": 0,
        "attributes": 0,
        "starting_hypotheses": 0,
        "user_feedback": 0,
    }


def test_runtime_readiness_surface_summary_hides_internal_refs_by_default() -> None:
    worker_status = {
        "enabled": False,
        "owner": "owner-secret",
        "concurrency": 2,
        "lease_seconds": 300,
        "poll_seconds": 2,
        "last_error": "SECRET STACK TRACE",
        "queue_status_counts": {"active": 2, "queued": 2, "running": 0, "retrying": 1, "error": 0},
        "active_work_item_snapshot": {
            "counts": {"active": 2, "queued": 2, "running": 0, "retrying": 1, "error": 0},
            "recovery_action": "wait",
            "recovery_action_counts": {"wait": 1, "retry": 1, "unblock": 0, "escalate": 0, "inspect": 0, "none": 0},
        },
    }
    execution_memory = {
        "status": "limited",
        "resume_supported": False,
        "checkpoint_backend": "sqlite_metadata",
        "resume_mode": "metadata_only_retry",
    }
    service_statuses = {
        "llm": {
            "available": False,
            "status": "permission_denied",
            "summary": "Model provider needs authorization.",
            "endpoint": "https://secret-provider.example",
            "env": "SECRET_PROVIDER_KEY",
            "required": True,
        },
        "pdf": {
            "available": True,
            "status": "ready",
            "summary": "Parser ready.",
            "endpoint": "file://secret-parser",
        },
    }

    summary = runtime_readiness_surface_summary(
        worker_status=worker_status,
        execution_memory=execution_memory,
        service_statuses=service_statuses,
    )

    assert summary["status"] == "permission_denied"
    assert summary["audience"] == {
        "primary": "admin_or_expert",
        "default_researcher_surface": False,
        "placement": "runtime_admin_or_expert_inspector",
        "researcher_label": "A required research service needs authorization.",
    }
    assert summary["disclosure"]["default_state"] == "collapsed"
    assert summary["disclosure"]["show_on_primary_researcher_surface"] is False
    assert "service endpoints" in summary["disclosure"]["expert_fields"]
    assert "raw errors" in summary["disclosure"]["expert_fields"]
    assert summary["worker"]["state"] == "disabled"
    assert summary["worker"]["queue_counts"]["queued"] == 2
    assert summary["worker"]["recovery_action"] == "wait"
    assert summary["worker"]["recovery_action_counts"]["retry"] == 1
    assert "worker.recovery_action" in summary["disclosure"]["safe_default_fields"]
    assert "worker.recovery_action_counts" in summary["disclosure"]["safe_default_fields"]
    assert summary["execution_memory"]["resume_supported"] is False
    assert summary["service_counts"]["permission_denied"] == 1
    assert "start_worker_or_manual_tick" in summary["next_actions"]
    assert "resolve_permissions" in summary["next_actions"]
    assert "continue_with_metadata_only_execution_memory" in summary["next_actions"]
    assert "internal_refs" not in summary
    assert "owner-secret" not in str(summary)
    assert "SECRET" not in str(summary)
    assert "https://secret-provider.example" not in str(summary)
    assert "file://secret-parser" not in str(summary)

    expert_summary = runtime_readiness_surface_summary(
        worker_status=worker_status,
        execution_memory=execution_memory,
        service_statuses=service_statuses,
        include_internal_refs=True,
    )
    assert expert_summary["internal_refs"]["worker_owner"] == "owner-secret"
    assert expert_summary["internal_refs"]["last_error"] == "SECRET STACK TRACE"
    assert expert_summary["internal_refs"]["service_debug"]["llm"]["endpoint"] == "https://secret-provider.example"


def test_runtime_readiness_surface_summary_reports_ready_state() -> None:
    summary = runtime_readiness_surface_summary(
        worker_status={
            "enabled": True,
            "concurrency": 1,
            "running_count": 0,
            "queue_status_counts": {"active": 0, "queued": 0, "running": 0, "retrying": 0, "error": 0},
        },
        execution_memory={
            "status": "ready",
            "resume_supported": True,
            "checkpoint_backend": "langgraph_sqlite",
            "resume_mode": "langgraph_thread_resume",
        },
        service_statuses={
            "llm": {"available": True, "status": "ready"},
            "pdf": {"available": True, "status": "ready"},
        },
    )

    assert summary["status"] == "ready"
    assert summary["audience"]["primary"] == "admin_or_expert"
    assert summary["audience"]["default_researcher_surface"] is False
    assert summary["audience"]["researcher_label"] == "Research task infrastructure is ready."
    assert summary["disclosure"]["show_on_primary_researcher_surface"] is False
    assert summary["worker"]["state"] == "ready"
    assert summary["worker"]["concurrency"] == 1
    assert summary["execution_memory"]["resume_supported"] is True
    assert summary["service_counts"]["ready"] == 2
    assert summary["next_actions"] == ["start_or_continue_research_run"]


def test_work_queue_surface_summary_hides_raw_work_items_by_default() -> None:
    snapshot = {
        "counts": {"active": 2, "queued": 1, "running": 1, "retrying": 0, "error": 0},
        "recovery_action": "wait",
        "recovery_action_counts": {"wait": 2, "retry": 0, "unblock": 0, "escalate": 0, "inspect": 0, "none": 0},
        "items": [
            {
                "work_item_id": "work-secret-1",
                "run_id": "run-secret",
                "workflow_name": "workflow.open_coscientist_run",
                "phase": "review",
                "agent_role": "review_agent",
                "status": "running",
                "recovery_action": "wait",
                "priority": 4,
                "attempt_count": 1,
                "max_attempts": 3,
                "lease_owner": "owner-secret",
                "lease_expires_at": "2026-07-02T10:00:00Z",
                "arguments_json": {"provider_key": "SECRET PROVIDER KEY"},
                "result_ref_json": {"path": "D:/secret/result.json"},
                "error_message": "SECRET ERROR TEXT",
            },
            {
                "work_item_id": "work-secret-2",
                "run_id": "run-secret",
                "phase": "ranking",
                "agent_role": "ranking_agent",
                "status": "queued",
                "priority": 2,
            },
        ],
    }
    worker_status = {
        "enabled": True,
        "concurrency": 2,
        "running_count": 1,
        "owner": "owner-secret",
    }

    summary = work_queue_surface_summary(snapshot, worker_status=worker_status)

    assert summary["status"] == "running"
    assert summary["recovery_action"] == "wait"
    assert summary["recovery_action_counts"]["wait"] == 2
    assert "recovery_action" in summary["disclosure"]["safe_default_fields"]
    assert "recovery_action_counts" in summary["disclosure"]["safe_default_fields"]
    assert summary["worker"] == {"enabled": True, "concurrency": 2, "running_count": 1}
    assert summary["counts"]["active"] == 2
    assert summary["counts"]["queued"] == 1
    assert summary["counts"]["running"] == 1
    assert summary["current_item"] == {
        "index": 1,
        "status": "running",
        "status_label": "Running",
        "workflow_name": "workflow.open_coscientist_run",
        "phase": "review",
        "agent_role": "review_agent",
        "priority": 4,
        "attempts": {"current": 1, "max": 3},
        "next_action": "Monitor progress and process summary.",
        "recovery_action": "wait",
    }
    assert summary["items_preview"][1]["phase"] == "ranking"
    assert summary["next_actions"] == ["monitor_progress", "view_process_summary"]
    assert "internal_refs" not in summary
    assert "work-secret" not in str(summary)
    assert "run-secret" not in str(summary)
    assert "owner-secret" not in str(summary)
    assert "SECRET" not in str(summary)
    assert "D:/secret" not in str(summary)

    expert_summary = work_queue_surface_summary(
        snapshot,
        worker_status=worker_status,
        include_internal_refs=True,
    )

    assert expert_summary["internal_refs"]["work_item_ids"] == ["work-secret-1", "work-secret-2"]
    assert expert_summary["internal_refs"]["run_ids"] == ["run-secret", "run-secret"]
    assert expert_summary["internal_refs"]["lease_owners"] == ["owner-secret"]
    assert expert_summary["internal_refs"]["lease_expires_at"] == ["2026-07-02T10:00:00Z"]
    assert expert_summary["internal_refs"]["error_messages"] == ["SECRET ERROR TEXT"]
    assert expert_summary["internal_refs"]["raw_items"][0]["arguments_json"]["provider_key"] == "SECRET PROVIDER KEY"


def test_work_queue_surface_summary_reports_disabled_and_empty_states() -> None:
    disabled = work_queue_surface_summary(
        {"counts": {"active": 2, "queued": 2, "running": 0, "retrying": 0, "error": 0}},
        worker_status={"enabled": False, "concurrency": 0},
    )

    assert disabled["status"] == "worker_disabled"
    assert disabled["worker"]["enabled"] is False
    assert disabled["counts"]["queued"] == 2
    assert disabled["current_item"] is None
    assert disabled["next_actions"] == ["start_worker_or_manual_tick", "monitor_queue"]

    empty = work_queue_surface_summary(
        {"counts": {"active": 0, "queued": 0, "running": 0, "retrying": 0, "error": 0}},
        worker_status={"enabled": True, "concurrency": 1},
    )

    assert empty["status"] == "empty"
    assert empty["current_item"] is None
    assert empty["items_preview"] == []
    assert empty["next_actions"] == ["start_or_continue_research_run"]


def test_run_confirmation_surface_summary_counts_feedback_and_hides_raw_request() -> None:
    request = {
        "research_goal": "Study whether retrieval-grounded hypothesis generation improves review quality",
        "demo_mode": False,
        "literature_review": True,
        "preferences": "Prefer falsifiable mechanisms with simple validation.",
        "attributes": ["soundness", "novelty"],
        "constraints": ["Use parsed fulltext evidence first."],
        "starting_hypotheses": [
            "SECRET STARTING HYPOTHESIS one should be previewed only briefly.",
            "Second candidate hypothesis.",
        ],
        "user_feedback": [
            {
                "feedback_id": "feedback-secret",
                "target_type": "hypothesis",
                "feedback_type": "critique",
                "text": "SECRET FEEDBACK TEXT should not be displayed by default.",
            }
        ],
        "parent_run_id": "parent-secret",
        "library_id": "library-secret",
        "memory_scope": "project",
        "refinement_mode": "continue_from_run",
    }
    memory_summary = {
        "memory_scope": "project",
        "memory_sources": ["parent_run", "chat_feedback", "knowledge_base"],
        "counts": {"user_feedback": 1, "prior_hypotheses": 2, "evidence_sources": 3},
        "execution_memory": {"status": "limited"},
        "evidence_boundary": {"status": "parsed_fulltext"},
    }

    summary = run_confirmation_surface_summary(
        request,
        parent_run_summary={"run_id": "parent-secret", "research_goal": "Parent goal", "hypothesis_count": 4},
        memory_summary=memory_summary,
    )

    assert summary["status"] == "pending"
    assert summary["is_continuation"] is True
    assert summary["mode_boundary"]["mode"] == "literature_grounded"
    assert summary["counts"] == {
        "starting_hypotheses": 2,
        "constraints": 1,
        "attributes": 2,
        "user_feedback": 1,
    }
    assert len(summary["starting_hypothesis_previews"]) == 2
    assert summary["constraint_previews"] == ["Use parsed fulltext evidence first."]
    assert summary["feedback_summary"]["feedback_types"] == {"critique": 1}
    assert summary["feedback_summary"]["target_types"] == {"hypothesis": 1}
    assert summary["feedback_summary"]["applies_to"] == "next_run_or_continuation"
    assert summary["parent_run"]["research_goal"] == "Parent goal"
    assert summary["parent_run"]["hypothesis_count"] == 4
    assert summary["memory"]["feedback_count"] == 1
    assert summary["next_actions"] == ["confirm_continuation", "edit_request", "cancel"]
    assert "internal_refs" not in summary
    assert "parent-secret" not in str(summary)
    assert "library-secret" not in str(summary)
    assert "feedback-secret" not in str(summary)
    assert "SECRET FEEDBACK TEXT" not in str(summary)

    expert_summary = run_confirmation_surface_summary(
        request,
        parent_run_summary={"run_id": "parent-secret", "research_goal": "Parent goal", "hypothesis_count": 4},
        memory_summary=memory_summary,
        include_internal_refs=True,
    )
    assert expert_summary["internal_refs"]["parent_run_id"] == "parent-secret"
    assert expert_summary["internal_refs"]["library_id"] == "library-secret"
    assert expert_summary["internal_refs"]["memory_scope"] == "project"
    assert expert_summary["internal_refs"]["request_preview"]["user_feedback"][0]["feedback_id"] == "feedback-secret"


def test_run_confirmation_surface_summary_marks_short_goal_invalid() -> None:
    summary = run_confirmation_surface_summary({"research_goal": "short", "demo_mode": True})

    assert summary["status"] == "invalid"
    assert summary["blocking_issues"] == ["research_goal_too_short"]
    assert summary["next_actions"] == ["edit_research_goal", "cancel"]


def test_run_surface_summary_hides_internal_refs_and_reports_queue_state() -> None:
    run = {
        "run_id": "run-secret",
        "status": "queued",
        "created_at": 1.0,
        "updated_at": 2.0,
        "request": {
            "demo_mode": True,
            "literature_review": False,
            "starting_hypotheses": ["User seed"],
            "user_feedback": [{"text": "SECRET FEEDBACK"}],
            "parent_run_id": "parent-secret",
        },
    }
    work_snapshot = {
        "counts": {"active": 1, "queued": 1, "retrying": 0, "running": 0},
        "recovery_action": "retry",
        "recovery_action_counts": {"wait": 0, "retry": 1, "unblock": 0, "escalate": 0, "inspect": 0, "none": 0},
        "items": [
            {
                "work_item_id": "work-secret",
                "status": "queued",
                "status_label": "Queued",
                "phase": "generate",
                "recovery_action": "wait",
                "next_action": "Wait for worker.",
            }
        ],
    }
    memory_summary = {
        "memory_scope": "project",
        "memory_sources": ["parent_run", "chat_feedback"],
        "counts": {"user_feedback": 1, "prior_hypotheses": 2, "evidence_sources": 3},
        "execution_memory": {"status": "limited"},
        "evidence_boundary": {"status": "parsed_fulltext"},
    }
    recovery_policy = {
        "recovery_mode": "queue_retry_without_checkpoint",
        "can_resume": False,
        "should_retry": True,
        "next_action": "Continue through queue.",
    }

    summary = run_surface_summary(
        run,
        work_item_snapshot=work_snapshot,
        memory_summary=memory_summary,
        recovery_policy=recovery_policy,
    )

    assert summary["status"] == "queued"
    assert summary["status_label"] == "Queued"
    assert summary["phase"] == "generate"
    assert summary["phase_label"] == "Generate"
    assert summary["mode_boundary"]["mode"] == "demo_only"
    assert summary["mode_boundary"]["scientific_claim_level"] == "not_scientific_evidence"
    assert summary["recoverable"] is True
    assert summary["next_actions"] == ["monitor_queue", "check_worker_status"]
    assert summary["counts"] == {"hypotheses": 0, "starting_hypotheses": 1, "user_feedback": 1}
    assert summary["queue"]["active_work_item_count"] == 1
    assert summary["queue"]["recovery_action"] == "retry"
    assert summary["queue"]["recovery_action_counts"]["retry"] == 1
    assert summary["queue"]["current_work_status"] == "queued"
    assert summary["queue"]["current_work_recovery_action"] == "wait"
    assert summary["memory"]["feedback_count"] == 1
    assert summary["memory"]["evidence_source_count"] == 3
    assert summary["memory"]["execution_memory_status"] == "limited"
    assert summary["recovery"]["recovery_mode"] == "queue_retry_without_checkpoint"
    assert summary["recovery"]["label"] == "Run can retry through the durable queue."
    assert summary["recovery"]["recovery_action"] == "retry"
    assert "internal_refs" not in summary
    assert "run-secret" not in str(summary)
    assert "work-secret" not in str(summary)
    assert "parent-secret" not in str(summary)
    assert "SECRET FEEDBACK" not in str(summary)

    expert_summary = run_surface_summary(
        run,
        work_item_snapshot=work_snapshot,
        recovery_policy={"latest_checkpoint": {"checkpoint_id": "checkpoint-secret"}},
        include_internal_refs=True,
    )
    assert expert_summary["internal_refs"]["run_id"] == "run-secret"
    assert expert_summary["internal_refs"]["parent_run_id"] == "parent-secret"
    assert expert_summary["internal_refs"]["work_item_ids"] == ["work-secret"]
    assert expert_summary["internal_refs"]["checkpoint_id"] == "checkpoint-secret"


def test_run_surface_summary_distinguishes_complete_grounded_and_error_modes() -> None:
    complete = run_surface_summary(
        {
            "status": "complete",
            "hypotheses": [{"id": "h1"}, {"id": "h2"}],
            "request": {"demo_mode": False, "literature_review": True},
        },
        memory_summary={"evidence_boundary": {"status": "experimental_data"}},
    )
    assert complete["mode_boundary"]["mode"] == "literature_grounded"
    assert complete["counts"]["hypotheses"] == 2
    assert complete["next_actions"] == ["inspect_hypotheses", "inspect_evidence", "design_experiment"]

    failed = run_surface_summary(
        {"status": "error", "request": {"demo_mode": False, "literature_review": False}},
        recovery_policy={"can_resume": False, "should_retry": False},
    )
    assert failed["mode_boundary"]["mode"] == "live_model"
    assert failed["recoverable"] is False
    assert failed["next_actions"] == ["start_new_run", "inspect_failure_summary"]


def test_memory_surface_summary_hides_raw_context_by_default() -> None:
    memory_context = {
        "memory_scope": "project",
        "memory_sources": ["parent_run", "prior_hypotheses", "chat_feedback", "knowledge_base"],
        "parent_run": {
            "run_id": "parent-secret",
            "research_goal": "Evaluate retrieval-grounded hypothesis generation",
            "status": "complete",
            "hypothesis_count": 3,
            "updated_at": 2.0,
        },
        "related_runs": [{"run_id": "related-secret", "research_goal": "Related hidden run"}],
        "prior_hypotheses": [
            {
                "hypothesis_id": "hyp-secret",
                "text": "SECRET HYPOTHESIS TEXT should stay behind expert disclosure.",
            }
        ],
        "user_feedback": [
            {
                "feedback_id": "feedback-secret",
                "feedback_type": "critique",
                "target_type": "hypothesis",
                "text": "SECRET FEEDBACK TEXT should not appear by default.",
            }
        ],
        "evidence_summaries": [
            {
                "paper_id": "paper-secret",
                "chunk_id": "chunk-secret",
                "library_id": "library-secret",
                "title": "Parsed fulltext support",
                "source_reliability": "parsed_fulltext",
                "support_level": "experimental_data",
                "matched_snippet": "SECRET FULLTEXT MATCH should not appear in memory summary.",
            }
        ],
        "execution_memory": {
            "status": "ready",
            "phase": "review",
            "resume_supported": True,
            "checkpoint_backend": "langgraph_sqlite",
            "resume_mode": "thread_resume",
            "latest_checkpoint": {
                "checkpoint_id": "checkpoint-secret",
                "checkpoint_ref": "checkpoint-secret-ref",
            },
        },
        "injection_policy": {
            "mode": "summary_only",
            "memory_scope": "project",
            "memory_sources": ["parent_run", "chat_feedback", "knowledge_base"],
            "prompt_sections": [
                "parent_run_summary",
                "feedback_type_and_target_summary",
                "evidence_boundary_and_snippet_summaries",
            ],
            "target_prompts": ["supervisor", "generate", "review", "ranking"],
            "counts": {
                "prior_hypotheses": 1,
                "feedback_items": 1,
                "evidence_summaries": 1,
            },
            "evidence_status": "experimental_data",
            "raw_injection_allowed": False,
            "excluded_raw_fields": [
                "chat_message_bodies",
                "feedback_text",
                "hypothesis_full_text",
                "checkpoint_state",
                "tool_result_json",
                "provider_payloads",
                "full_pdf_chunks",
            ],
            "boundary": "SECRET RAW POLICY DETAIL should be truncated and safe.",
        },
        "known_gaps": ["Need replication evidence before treating this as validated."],
    }

    summary = memory_surface_summary(memory_context)

    assert summary["status"] == "ready"
    assert summary["memory_scope"] == "project"
    assert summary["memory_sources"] == ["parent_run", "prior_hypotheses", "chat_feedback", "knowledge_base"]
    assert summary["parent_run"] == {
        "research_goal": "Evaluate retrieval-grounded hypothesis generation",
        "status": "complete",
        "hypothesis_count": 3,
        "updated_at": 2.0,
    }
    assert summary["counts"] == {
        "parent_run": 1,
        "related_runs": 1,
        "prior_hypotheses": 1,
        "user_feedback": 1,
        "evidence_sources": 1,
        "known_gaps": 1,
    }
    assert summary["feedback_summary"]["feedback_types"] == {"critique": 1}
    assert summary["feedback_summary"]["target_types"] == {"hypothesis": 1}
    assert summary["evidence_scope"]["status"] == "parsed_fulltext"
    assert summary["evidence_scope"]["evidence_count"] == 1
    assert summary["evidence_scope"]["parsed_fulltext_count"] == 1
    assert summary["evidence_scope"]["experimental_data_count"] == 1
    assert summary["evidence_scope"]["library_count"] == 1
    assert summary["execution_memory"] == {
        "status": "ready",
        "phase": "review",
        "resume_supported": True,
        "can_resume": True,
        "should_retry": False,
        "recovery_action": "resume",
        "next_actions": ["resume_langgraph_thread", "monitor_progress"],
        "checkpoint_backend": "langgraph_sqlite",
        "resume_mode": "thread_resume",
    }
    assert summary["injection_policy"] == {
        "status": "summary_only",
        "mode": "summary_only",
        "memory_scope": "project",
        "memory_sources": ["parent_run", "chat_feedback", "knowledge_base"],
        "prompt_sections": [
            "parent_run_summary",
            "feedback_type_and_target_summary",
            "evidence_boundary_and_snippet_summaries",
        ],
        "target_prompts": ["supervisor", "generate", "review", "ranking"],
        "counts": {
            "prior_hypotheses": 1,
            "feedback_items": 1,
            "evidence_summaries": 1,
        },
        "evidence_status": "experimental_data",
        "raw_injection_allowed": False,
        "excluded_raw_field_count": 7,
        "excluded_raw_fields": [
            "chat_message_bodies",
            "feedback_text",
            "hypothesis_full_text",
            "checkpoint_state",
            "tool_result_json",
            "provider_payloads",
            "full_pdf_chunks",
        ],
        "boundary_summary": "Memory injection uses summary-only guidance; raw memory payloads require expert disclosure.",
    }
    assert summary["known_gap_summaries"] == ["Need replication evidence before treating this as validated."]
    assert summary["next_actions"] == ["review_context", "continue_run"]
    assert "internal_refs" not in summary
    assert "SECRET" not in str(summary)
    assert "parent-secret" not in str(summary)
    assert "related-secret" not in str(summary)
    assert "hyp-secret" not in str(summary)
    assert "feedback-secret" not in str(summary)
    assert "paper-secret" not in str(summary)
    assert "chunk-secret" not in str(summary)
    assert "checkpoint-secret" not in str(summary)
    assert "raw_memory_context" not in str(summary)

    expert_summary = memory_surface_summary(memory_context, include_internal_refs=True)

    assert expert_summary["internal_refs"]["parent_run_id"] == "parent-secret"
    assert expert_summary["internal_refs"]["related_run_ids"] == ["related-secret"]
    assert expert_summary["internal_refs"]["feedback_ids"] == ["feedback-secret"]
    assert expert_summary["internal_refs"]["hypothesis_ids"] == ["hyp-secret"]
    assert expert_summary["internal_refs"]["evidence_refs"] == [
        {"paper_id": "paper-secret", "chunk_id": "chunk-secret", "library_id": "library-secret"}
    ]
    assert expert_summary["internal_refs"]["checkpoint_id"] == "checkpoint-secret"
    assert expert_summary["internal_refs"]["checkpoint_ref"] == "checkpoint-secret-ref"
    assert expert_summary["internal_refs"]["raw_injection_policy"]["mode"] == "summary_only"
    assert expert_summary["internal_refs"]["raw_memory_context"]["user_feedback"][0]["text"].startswith("SECRET")


def test_memory_surface_summary_reports_empty_limited_and_conflicted_states() -> None:
    empty = memory_surface_summary({})

    assert empty["status"] == "empty"
    assert empty["parent_run"] is None
    assert empty["next_actions"] == ["select_parent_run", "add_feedback", "parse_evidence"]

    limited = memory_surface_summary(
        {
            "parent_run": {
                "run_id": "parent-limited-secret",
                "research_goal": "Continue sparse prior run",
            },
            "execution_memory": {"status": "limited"},
            "evidence_boundary": {"status": "absent"},
        }
    )

    assert limited["status"] == "limited"
    assert limited["counts"]["parent_run"] == 1
    assert limited["evidence_scope"]["status"] == "absent"
    assert limited["next_actions"] == ["review_context", "add_or_parse_evidence", "continue_run"]
    assert "parent-limited-secret" not in str(limited)

    conflicted = memory_surface_summary(
        {
            "evidence_summaries": [
                {
                    "paper_id": "paper-conflict-secret",
                    "chunk_id": "chunk-conflict-secret",
                    "title": "Counter evidence",
                    "source_reliability": "parsed_fulltext",
                    "support_level": "contradicted",
                }
            ]
        }
    )

    assert conflicted["status"] == "needs_review"
    assert conflicted["evidence_scope"]["status"] == "contradicted"
    assert conflicted["next_actions"] == [
        "inspect_memory_evidence",
        "revise_memory_scope",
        "continue_with_caution",
    ]
    assert "paper-conflict-secret" not in str(conflicted)
    assert "chunk-conflict-secret" not in str(conflicted)


def test_memory_prompt_packet_surface_summary_hides_section_payloads_by_default() -> None:
    packet = {
        "mode": "summary_only",
        "memory_scope": "project",
        "target_prompts": ["supervisor", "generate", "review", "ranking"],
        "section_count": 4,
        "sections": [
            {
                "section": "parent_run_summary",
                "items": [
                    {
                        "run_id": "parent-secret",
                        "research_goal": "SECRET parent goal should not be displayed by default.",
                    }
                ],
            },
            {
                "section": "feedback_type_and_target_summary",
                "items": [
                    {
                        "feedback_id": "feedback-secret",
                        "feedback_type": "critique",
                        "target_type": "hypothesis",
                        "text": "SECRET feedback text should stay hidden.",
                    }
                ],
            },
            {
                "section": "evidence_boundary_and_snippet_summaries",
                "items": [
                    {
                        "paper_id": "paper-secret",
                        "chunk_id": "chunk-secret",
                        "summary": "SECRET fulltext snippet should stay hidden.",
                    },
                    {
                        "checkpoint_id": "checkpoint-secret",
                        "summary": "SECRET checkpoint detail should stay hidden.",
                    },
                ],
            },
            {
                "section": "memory_limitations",
                "items": [{"summary": "SECRET limitation text should stay hidden."}],
            },
        ],
        "raw_injection_allowed": False,
        "excluded_raw_fields": [
            "feedback_text",
            "hypothesis_full_text",
            "checkpoint_state",
            "tool_result_json",
        ],
        "boundary": "SECRET raw packet boundary should not be displayed by default.",
    }

    summary = memory_prompt_packet_surface_summary(packet)

    assert summary["status"] == "summary_only"
    assert summary["mode"] == "summary_only"
    assert summary["memory_scope"] == "project"
    assert summary["target_prompts"] == ["supervisor", "generate", "review", "ranking"]
    assert summary["section_count"] == 4
    assert summary["counts"] == {
        "sections": 4,
        "items": 5,
        "target_prompts": 4,
        "excluded_raw_fields": 4,
    }
    assert summary["sections"] == [
        {
            "index": 1,
            "section": "parent_run_summary",
            "label": "Parent run summary",
            "item_count": 1,
            "default_state": "collapsed",
        },
        {
            "index": 2,
            "section": "feedback_type_and_target_summary",
            "label": "Feedback type and target summary",
            "item_count": 1,
            "default_state": "collapsed",
        },
        {
            "index": 3,
            "section": "evidence_boundary_and_snippet_summaries",
            "label": "Evidence boundary summaries",
            "item_count": 2,
            "default_state": "collapsed",
        },
        {
            "index": 4,
            "section": "memory_limitations",
            "label": "Memory limitations",
            "item_count": 1,
            "default_state": "collapsed",
        },
    ]
    assert summary["raw_injection_allowed"] is False
    assert summary["excluded_raw_field_count"] == 4
    assert "summary-only sections" in summary["application_boundary"]
    assert summary["next_actions"] == ["review_memory_summary", "start_or_continue_run"]
    assert "internal_refs" not in summary
    assert "SECRET" not in str(summary)
    assert "parent-secret" not in str(summary)
    assert "feedback-secret" not in str(summary)
    assert "paper-secret" not in str(summary)
    assert "checkpoint-secret" not in str(summary)
    assert "raw_prompt_packet" not in str(summary)

    expert_summary = memory_prompt_packet_surface_summary(packet, include_internal_refs=True)

    assert expert_summary["internal_refs"]["section_item_counts"] == {
        "parent_run_summary": 1,
        "feedback_type_and_target_summary": 1,
        "evidence_boundary_and_snippet_summaries": 2,
        "memory_limitations": 1,
    }
    assert expert_summary["internal_refs"]["raw_sections"][0]["items"][0]["run_id"] == "parent-secret"
    assert expert_summary["internal_refs"]["raw_prompt_packet"]["boundary"].startswith("SECRET raw packet")


def test_memory_prompt_packet_surface_summary_reports_absent_and_raw_allowed_states() -> None:
    absent = memory_prompt_packet_surface_summary({})

    assert absent["status"] == "absent"
    assert absent["section_count"] == 0
    assert absent["sections"] == []
    assert absent["next_actions"] == ["build_memory_context", "review_generation_request"]

    raw_allowed = memory_prompt_packet_surface_summary(
        {
            "mode": "raw",
            "raw_injection_allowed": True,
            "sections": [],
            "excluded_raw_fields": [],
        }
    )

    assert raw_allowed["status"] == "raw_allowed"
    assert raw_allowed["raw_injection_allowed"] is True
    assert raw_allowed["application_boundary"] == (
        "Prompt memory packet is configured for raw injection; inspect expert details before running."
    )
    assert raw_allowed["next_actions"] == [
        "inspect_expert_prompt_packet",
        "disable_raw_memory_injection",
    ]


def test_feedback_surface_summary_hides_raw_feedback_by_default() -> None:
    feedback = [
        {
            "feedback_id": "feedback-secret-1",
            "run_id": "run-secret",
            "target_type": "hypothesis",
            "target_ref": {"hypothesis_id": "hyp-secret", "local_path": "D:/secret/raw.json"},
            "feedback_type": "critique",
            "text": "SECRET FEEDBACK TEXT should not appear by default.",
            "user_id": "user-secret",
        },
        {
            "feedback_id": "feedback-secret-2",
            "run_id": "run-secret",
            "target_type": "run",
            "target_ref": {"run_id": "run-secret"},
            "feedback_type": "prefer",
            "text": "SECRET PREFERENCE TEXT should not appear by default.",
        },
    ]

    summary = feedback_surface_summary(feedback)

    assert summary["status"] == "available"
    assert summary["count"] == 2
    assert summary["feedback_types"] == {"critique": 1, "prefer": 1}
    assert summary["target_types"] == {"hypothesis": 1, "run": 1}
    assert summary["applies_to"] == "next_run_or_continuation"
    assert "next run or continuation" in summary["application_boundary"]
    assert summary["target_summary"] == [
        {"target_type": "hypothesis", "feedback_type": "critique", "count": 1},
        {"target_type": "run", "feedback_type": "prefer", "count": 1},
    ]
    assert summary["next_actions"] == [
        "review_feedback_summary",
        "apply_to_next_run_or_continuation",
        "continue_or_revise_hypotheses",
    ]
    assert "internal_refs" not in summary
    assert "feedback-secret" not in str(summary)
    assert "run-secret" not in str(summary)
    assert "hyp-secret" not in str(summary)
    assert "D:/secret" not in str(summary)
    assert "SECRET" not in str(summary)

    expert_summary = feedback_surface_summary(feedback, include_internal_refs=True)

    assert expert_summary["internal_refs"]["feedback_ids"] == ["feedback-secret-1", "feedback-secret-2"]
    assert expert_summary["internal_refs"]["run_ids"] == ["run-secret", "run-secret"]
    assert expert_summary["internal_refs"]["target_refs"][0]["hypothesis_id"] == "hyp-secret"
    assert expert_summary["internal_refs"]["raw_feedback"][0]["text"].startswith("SECRET")


def test_feedback_surface_summary_reports_empty_state() -> None:
    summary = feedback_surface_summary([])

    assert summary["status"] == "empty"
    assert summary["count"] == 0
    assert summary["feedback_types"] == {}
    assert summary["target_types"] == {}
    assert summary["applies_to"] is None
    assert summary["target_summary"] == []
    assert summary["next_actions"] == ["add_feedback", "select_hypothesis_or_run"]
    assert "No feedback has been recorded" in summary["application_boundary"]


def test_workspace_surface_summary_chooses_confirmation_layout_without_raw_details() -> None:
    state = {
        "request": {
            "research_goal": (
                "Develop a causal fulltext retrieval audit mechanism; measure contradiction rate, "
                "validate with an ablation benchmark, and fail if citation support remains below 0.70."
            ),
            "demo_mode": False,
            "literature_review": True,
            "starting_hypotheses": ["A retrieval audit mechanism should reduce unsupported citations."],
            "user_feedback": [
                {
                    "feedback_id": "feedback-secret",
                    "feedback_type": "critique",
                    "text": "SECRET FEEDBACK should not appear in workspace summary.",
                }
            ],
            "parent_run_id": "parent-secret",
            "library_id": "library-secret",
        },
        "parent_run": {
            "run_id": "parent-secret",
            "research_goal": "Parent run goal",
            "status": "complete",
            "hypothesis_count": 2,
        },
        "memory_context": {
            "memory_scope": "project",
            "memory_sources": ["parent_run", "chat_feedback", "knowledge_base"],
            "parent_run": {"run_id": "parent-secret", "research_goal": "Parent run goal"},
            "user_feedback": [{"feedback_id": "feedback-secret", "feedback_type": "critique"}],
            "evidence_summaries": [
                {
                    "paper_id": "paper-secret",
                    "chunk_id": "chunk-secret",
                    "library_id": "library-secret",
                    "title": "Parsed evidence",
                    "source_reliability": "parsed_fulltext",
                    "support_level": "fulltext",
                }
            ],
            "execution_memory": {"status": "ready"},
            "counts": {"user_feedback": 1, "prior_hypotheses": 0, "evidence_sources": 1},
            "evidence_boundary": {"status": "parsed_fulltext", "evidence_count": 1},
        },
        "library": {"library_id": "library-secret", "name": "Evidence library"},
        "papers": [
            {
                "paper_id": "paper-secret",
                "title": "Parsed evidence",
                "source_reliability": "parsed_fulltext",
                "chunks_count": 4,
            }
        ],
        "worker_status": {
            "enabled": True,
            "queue_status_counts": {"active": 0, "queued": 0, "running": 0, "retrying": 0, "error": 0},
        },
        "execution_memory": {"status": "ready", "resume_supported": True},
        "service_statuses": {"llm": {"available": True, "status": "ready"}},
        "agent_trace_summary": {"trace_count": 1},
    }

    summary = workspace_surface_summary(state)

    assert summary["status"] == "ready_to_start"
    assert summary["primary_surface"]["surface"] == "run_confirmation_card"
    assert summary["layout"] == {
        "shell": "three_panel_research_workspace",
        "left": "project_navigation",
        "center": "run_confirmation_card",
        "right": "collapsible_inspector",
    }
    assert summary["surfaces"]["confirmation"]["is_continuation"] is True
    assert summary["surfaces"]["memory"]["status"] == "ready"
    assert summary["surfaces"]["evidence_library"]["status"] == "ready"
    assert summary["surfaces"]["process"]["status"] == "partial"
    assert summary["surfaces"]["process"]["phase_order"] == ["process_summary"]
    assert summary["surfaces"]["runtime"]["status"] == "ready"
    inspectors = {item["id"]: item for item in summary["inspectors"]}
    assert inspectors["memory"]["available"] is True
    assert inspectors["evidence"]["available"] is True
    assert inspectors["process"]["available"] is True
    assert inspectors["runtime"]["available"] is True
    assert all(item["default_state"] == "collapsed" for item in summary["inspectors"])
    assert summary["next_actions"] == ["confirm_continuation", "edit_request", "cancel"]
    assert "raw_memory_context" in summary["hidden_by_default"]
    assert "internal_refs" not in summary
    assert "SECRET" not in str(summary)
    assert "parent-secret" not in str(summary)
    assert "library-secret" not in str(summary)
    assert "paper-secret" not in str(summary)
    assert "feedback-secret" not in str(summary)

    expert_summary = workspace_surface_summary(state, include_internal_refs=True)

    assert expert_summary["internal_refs"]["parent_run_id"] == "parent-secret"
    assert expert_summary["internal_refs"]["library_id"] == "library-secret"
    assert expert_summary["internal_refs"]["raw_workspace_state"]["request"]["parent_run_id"] == "parent-secret"


def test_workspace_surface_summary_prefers_run_progress_for_queued_run() -> None:
    state = {
        "request": {"research_goal": "Run queued durable research task", "demo_mode": True},
        "run": {
            "run_id": "run-secret",
            "status": "queued",
            "request": {"demo_mode": True},
        },
        "work_item_snapshot": {
            "counts": {"active": 1, "queued": 1},
            "items": [{"work_item_id": "work-secret", "status": "queued", "phase": "generate"}],
        },
    }

    summary = workspace_surface_summary(state)

    assert summary["status"] == "in_progress"
    assert summary["primary_surface"]["surface"] == "run_progress"
    assert summary["layout"]["center"] == "run_progress"
    assert summary["surfaces"]["run"]["queue"]["current_work_status"] == "queued"
    assert summary["next_actions"] == ["monitor_queue", "check_worker_status"]
    assert "run-secret" not in str(summary)
    assert "work-secret" not in str(summary)

    expert_summary = workspace_surface_summary(state, include_internal_refs=True)

    assert expert_summary["internal_refs"]["run_id"] == "run-secret"
    assert expert_summary["internal_refs"]["work_item_ids"] == ["work-secret"]


def test_agent_process_surface_summary_uses_phase_labels_without_raw_provider_payload() -> None:
    trace = [
        {
            "event_id": "event-secret-rank",
            "phase": "rank",
            "agent_id": "ranking-agent-secret",
            "output_summary": "Pairwise ranking completed with evidence-aware comparison.",
            "prompt_template": "prompts/ranking.md",
            "token_usage": {"total_tokens": 987},
            "raw_provider_response": {"debug": "SECRET PROVIDER PAYLOAD"},
        },
        {
            "event_id": "event-secret-review",
            "phase": "review",
            "output": "Reviewed soundness, feasibility, and safety for the candidate.",
            "tool_calls": [{"args": {"raw": "SECRET TOOL ARG"}}],
            "prompt_template": "prompts/review.md",
            "token_usage": {"total_tokens": 1234},
        },
        {
            "event_id": "event-secret-literature",
            "phase": "literature",
            "output_summary": "Literature grounding is unavailable; continue with a latent-knowledge boundary.",
            "degradation_reason": "literature_review_disabled_latent_knowledge_boundary",
            "synthetic": True,
        },
    ]
    registry = {
        "phase_index": {
            "literature_review": {
                "role": "Ground evidence for the run.",
            },
            "review": {
                "agent_id": "review-agent-secret",
                "role": "Custom review role from registry.",
                "prompt_template": "registry/review.md",
            },
            "ranking": {
                "role": "Compare hypotheses.",
            },
            "evolve": {
                "role": "Refine hypotheses.",
            },
        }
    }

    summary = agent_process_surface_summary(trace, registry=registry)

    assert summary["status"] == "partial"
    assert summary["trace_count"] == 3
    assert summary["phase_order"] == ["literature_review", "review", "ranking"]
    assert summary["phase_coverage"] == {
        "expected_phases": ["literature_review", "review", "ranking", "evolve"],
        "observed_phases": ["literature_review", "review", "ranking"],
        "missing_phases": ["evolve"],
        "covered_count": 3,
        "expected_count": 4,
        "complete": False,
    }
    assert summary["counts"]["complete"] == 2
    assert summary["counts"]["degraded"] == 1
    assert summary["counts"]["synthetic"] == 1
    assert summary["counts"]["unknown_phase"] == 0
    assert summary["current_phase"] == {
        "phase": "ranking",
        "label": "Tournament ranking",
        "status": "complete",
    }
    assert summary["items"][0]["label"] == "Literature grounding"
    assert summary["items"][0]["status"] == "degraded"
    assert summary["items"][1]["label"] == "Scientific critique"
    assert summary["items"][1]["role"] == "Custom review role from registry."
    assert summary["items"][1]["tool_call_count"] == 1
    assert summary["items"][2]["label"] == "Tournament ranking"
    assert summary["counts"]["missing_phase"] == 1
    assert summary["next_actions"] == [
        "inspect_process_summary",
        "review_capability_degradation",
        "inspect_missing_research_steps",
        "inspect_evidence",
    ]
    assert "internal_refs" not in summary
    assert "event-secret" not in str(summary)
    assert "ranking-agent-secret" not in str(summary)
    assert "review-agent-secret" not in str(summary)
    assert "prompts/" not in str(summary)
    assert "registry/review.md" not in str(summary)
    assert "total_tokens" not in str(summary)
    assert "SECRET" not in str(summary)

    expert_summary = agent_process_surface_summary(
        trace,
        registry=registry,
        include_internal_refs=True,
    )

    assert expert_summary["internal_refs"]["event_ids"] == [
        "event-secret-literature",
        "event-secret-review",
        "event-secret-rank",
    ]
    assert expert_summary["internal_refs"]["agent_ids"] == [
        "review-agent-secret",
        "ranking-agent-secret",
    ]
    assert expert_summary["internal_refs"]["prompt_templates"] == [
        "prompts/review.md",
        "prompts/ranking.md",
    ]
    assert expert_summary["internal_refs"]["token_usage_by_phase"] == {
        "review": {"total_tokens": 1234},
        "ranking": {"total_tokens": 987},
    }
    assert expert_summary["internal_refs"]["raw_trace_events"][1]["tool_calls"][0]["args"]["raw"] == "SECRET TOOL ARG"


def test_agent_process_surface_summary_handles_absent_and_summary_only_trace() -> None:
    absent = agent_process_surface_summary([])

    assert absent["status"] == "absent"
    assert absent["trace_count"] == 0
    assert absent["items"] == []
    assert absent["next_actions"] == ["run_research_task", "inspect_timeline"]

    summary_only = agent_process_surface_summary({"trace_count": 2})

    assert summary_only["status"] == "partial"
    assert summary_only["trace_count"] == 1
    assert summary_only["phase_order"] == ["process_summary"]
    assert summary_only["counts"]["missing_phase"] == 9
    assert summary_only["counts"]["unknown_phase"] == 1
    assert summary_only["items"][0]["label"] == "Process Summary"
    assert summary_only["items"][0]["output_summary"] == "2 process trace event(s) are available in details."
    assert summary_only["next_actions"] == [
        "inspect_process_summary",
        "inspect_missing_research_steps",
        "inspect_unknown_steps",
        "inspect_evidence",
    ]


def test_evidence_surface_summary_hides_internal_refs_by_default() -> None:
    evidence = {
        "paper_id": "paper-secret",
        "chunk_id": "chunk-secret",
        "library_id": "library-secret",
        "parse_run_id": "parse-secret",
        "artifact_path": "D:/secret/artifact.png",
        "title": "Parsed evidence paper",
        "text": "SECRET FULLTEXT should be summarized, not shown as an internal reference.",
        "source": "local_pdf",
        "source_reliability": "parsed_fulltext",
        "support_level": "fulltext",
        "experiment_data_summary": "n=42 benchmark improved accuracy.",
        "citation_map": [{"doi": "10.0000/example"}],
    }

    summary = evidence_surface_summary(evidence, index=0)

    assert summary["index"] == 0
    assert summary["source_title"] == "Parsed evidence paper"
    assert summary["status"] == "supported"
    assert summary["source_reliability"] == "parsed_fulltext"
    assert summary["support_level"] == "fulltext"
    assert summary["source_type"] == "local_pdf"
    assert "parse_fulltext" not in summary["next_actions"]
    assert "internal_refs" not in summary
    assert "paper-secret" not in str(summary)
    assert "chunk-secret" not in str(summary)
    assert "D:/secret" not in str(summary)
    assert "citation_map" not in str(summary)

    expert_summary = evidence_surface_summary(
        evidence,
        index=0,
        include_internal_refs=True,
    )
    assert expert_summary["internal_refs"]["paper_id"] == "paper-secret"
    assert expert_summary["internal_refs"]["chunk_id"] == "chunk-secret"
    assert expert_summary["internal_refs"]["artifact_path"] == "D:/secret/artifact.png"
    assert expert_summary["internal_refs"]["citation_count"] == 1


def test_evidence_surface_collection_reports_boundaries_and_next_actions() -> None:
    evidence_items = [
        {
            "title": "Metadata-only source",
            "snippet": "Only metadata was available.",
            "source_reliability": "metadata",
            "support_level": "limited",
        },
        {
            "title": "Parsed source",
            "snippet": "Parsed fulltext supports the claim.",
            "source_reliability": "parsed_fulltext",
            "support_level": "fulltext",
        },
        {
            "title": "Counter evidence",
            "snippet": "This source contradicts the claim.",
            "source_reliability": "parsed_fulltext",
            "support_level": "contradicted",
        },
    ]

    collection = evidence_surface_collection(evidence_items)

    assert collection["evidence_count"] == 3
    assert collection["support_level_counts"] == {"limited": 1, "fulltext": 1, "contradicted": 1}
    assert collection["source_reliability_counts"] == {"metadata": 1, "parsed_fulltext": 2}
    assert collection["boundary"]["status"] == "contradicted"
    assert collection["items"][0]["status"] == "limited"
    assert "parse_fulltext" in collection["items"][0]["next_actions"]
    assert collection["items"][1]["status"] == "supported"
    assert collection["items"][2]["status"] == "contradicted"


def test_evidence_library_surface_summary_reports_readiness_without_internal_refs() -> None:
    library = {"library_id": "library-secret", "name": "Mechanistic papers"}
    papers = [
        {
            "paper_id": "paper-secret-1",
            "title": "Parsed fulltext benchmark",
            "source": "local_pdf",
            "source_reliability": "parsed_fulltext",
            "chunks_count": 12,
            "experimental_chunks_count": 2,
            "local_path": "D:/secret/paper.pdf",
        },
        {
            "paper_id": "paper-secret-2",
            "title": "Metadata only source",
            "source": "web",
            "source_reliability": "metadata",
            "chunks_count": 0,
        },
    ]
    parse_runs = [
        {
            "parse_run_id": "parse-secret-1",
            "title": "Parsed fulltext benchmark",
            "status": "complete",
            "chunks_count": 12,
            "experimental_chunks_count": 2,
            "rag_search_ready": True,
            "database_path": "D:/secret/kb.sqlite",
            "parse_status_summary": {"completion_rate": 1.0, "failed_items": []},
        }
    ]

    summary = evidence_library_surface_summary(library, papers=papers, parse_runs=parse_runs)

    assert summary["status"] == "ready"
    assert summary["library"] == {"name": "Mechanistic papers", "scope": "library"}
    assert summary["counts"]["papers"] == 2
    assert summary["counts"]["parsed_fulltext_sources"] == 1
    assert summary["counts"]["experimental_chunks"] == 2
    assert summary["counts"]["chunks"] == 12
    assert summary["source_reliability_counts"] == {"parsed_fulltext": 1, "metadata": 1}
    assert summary["readiness"]["parsed_fulltext_available"] is True
    assert summary["readiness"]["experimental_evidence_available"] is True
    assert summary["parse_jobs"]["counts"]["complete"] == 1
    assert summary["papers"]["items"][0]["status"] == "ready"
    assert summary["papers"]["items"][1]["next_actions"][0] == "parse_fulltext"
    assert summary["next_actions"] == ["use_for_hypothesis_grounding", "verify_hypothesis_evidence"]
    assert "internal_refs" not in summary
    assert "library-secret" not in str(summary)
    assert "paper-secret" not in str(summary)
    assert "parse-secret" not in str(summary)
    assert "D:/secret" not in str(summary)

    expert_summary = evidence_library_surface_summary(
        library,
        papers=papers,
        parse_runs=parse_runs,
        include_internal_refs=True,
    )
    assert expert_summary["internal_refs"]["library_id"] == "library-secret"
    assert expert_summary["internal_refs"]["paper_ids"] == ["paper-secret-1", "paper-secret-2"]
    assert expert_summary["internal_refs"]["parse_run_ids"] == ["parse-secret-1"]
    assert "D:/secret/paper.pdf" in expert_summary["internal_refs"]["local_paths"]


def test_evidence_library_surface_summary_reports_empty_processing_and_error_states() -> None:
    empty = evidence_library_surface_summary()
    assert empty["status"] == "empty"
    assert empty["next_actions"] == ["upload_pdf", "add_web_evidence", "search_literature"]

    processing = evidence_library_surface_summary(
        {"name": "Processing library"},
        papers=[{"title": "Metadata candidate", "source_reliability": "metadata", "chunks_count": 0}],
        parse_runs=[{"parse_run_id": "parse-running-secret", "title": "Pending parse", "status": "running"}],
    )
    assert processing["status"] == "processing"
    assert processing["readiness"]["active_parse_jobs"] == 1
    assert processing["next_actions"] == ["monitor_parse_jobs", "inspect_parse_results"]
    assert "parse-running-secret" not in str(processing)

    needs_attention = evidence_library_surface_summary(
        {"name": "Broken library"},
        papers=[{"title": "Broken PDF", "source_reliability": "metadata", "chunks_count": 0}],
        parse_runs=[
            {
                "parse_run_id": "parse-error-secret",
                "title": "Broken PDF",
                "status": "error",
                "parse_status_summary": {
                    "failed_items": [{"error_message": "SECRET parse stack"}],
                },
            }
        ],
    )
    assert needs_attention["status"] == "needs_attention"
    assert needs_attention["parse_jobs"]["counts"]["error"] == 1
    assert needs_attention["next_actions"] == ["inspect_parse_errors", "retry_parse", "add_web_evidence"]
    assert "SECRET parse stack" not in str(needs_attention)


def test_hypothesis_surface_summary_marks_origin_and_hides_raw_details() -> None:
    hypothesis = {
        "id": "hyp-secret-user",
        "text": "SECRET TECHNICAL HYPOTHESIS TEXT should stay behind details. " * 8,
        "explanation": "A concise user-facing explanation.",
        "origin": "user_seeded",
        "origin_evidence": "matched starting_hypotheses",
        "elo_rating": "1042.5",
        "rank": "1",
        "support_level": "limited",
        "citation_map": [{"source": "paper-1"}],
    }

    summary = hypothesis_surface_summary(hypothesis, index=0)

    assert summary["index"] == 0
    assert summary["origin"] == "user_seeded"
    assert summary["origin_label"] == "user seeded"
    assert summary["rank"] == 1
    assert summary["elo_rating"] == 1042.5
    assert summary["support_level"] == "limited"
    assert summary["status"] == "limited"
    assert "verify_evidence" in summary["next_actions"]
    assert "technical_text" not in summary
    assert "internal_refs" not in summary
    assert "hyp-secret-user" not in str(summary)
    assert "SECRET TECHNICAL" not in str(summary)

    expert_summary = hypothesis_surface_summary(
        hypothesis,
        index=0,
        include_internal_refs=True,
    )
    assert expert_summary["internal_refs"]["hypothesis_id"] == "hyp-secret-user"
    assert expert_summary["internal_refs"]["origin_evidence"] == "matched starting_hypotheses"
    assert expert_summary["internal_refs"]["citation_count"] == 1
    assert "SECRET TECHNICAL" in expert_summary["technical_text"]


def test_hypothesis_surface_collection_counts_model_evolved_and_tool_origins() -> None:
    hypotheses = [
        {
            "text": "Model generated hypothesis.",
            "support_level": "fulltext",
        },
        {
            "text": "Evolved hypothesis.",
            "generation_method": "demo-evolved",
            "evolution_history": ["Original hypothesis."],
            "support_level": "limited",
        },
        {
            "text": "Tool grounded hypothesis.",
            "generation_method": "literature tool grounded",
            "support_level": "experimental_data",
            "review": {"soundness": "reasonable"},
        },
    ]

    collection = hypothesis_surface_collection(hypotheses)

    assert collection["hypothesis_count"] == 3
    assert collection["origin_counts"] == {
        "model_generated": 1,
        "evolved": 1,
        "tool_generated": 1,
    }
    assert collection["support_level_counts"]["fulltext"] == 1
    assert collection["support_level_counts"]["limited"] == 1
    assert collection["support_level_counts"]["experimental_data"] == 1
    assert collection["items"][0]["origin_label"] == "model generated"
    assert collection["items"][1]["origin_label"] == "evolved"
    assert collection["items"][2]["origin_label"] == "tool grounded"
    assert "inspect_review" in collection["items"][2]["next_actions"]
    assert "citation_map" not in str(collection)


def test_experiment_design_surface_summary_requires_falsifiable_sections() -> None:
    experiment = {
        "id": "hyp-exp-secret",
        "title": "Retrieval-audited generation protocol",
        "text": "A candidate hypothesis for retrieval-audited generation.",
        "experiment_job_id": "experiment-job-secret",
        "script_path": "D:/secret/experiment.py",
        "experiment_plan": "Compare a retrieval-audited generator against a flat generator on held-out claims.",
        "observable_variables": ["claim support precision", "contradiction rate"],
        "controls": ["flat generator baseline", "metadata-only retrieval baseline"],
        "metrics": {"support_precision": ">= 0.80", "contradiction_rate": "<= 0.10"},
        "failure_conditions": ["Fails if support precision stays below 0.70 after fulltext retrieval."],
        "alternative_explanations": ["Reviewer preference may reflect wording rather than evidence quality."],
        "required_data": ["held-out paper fulltext set", "claim-level citation labels"],
        "minimal_validation_path": "Run a 50-claim pilot before any expensive benchmark.",
        "experimental_support_summaries": [
            {
                "paper_id": "paper-secret",
                "chunk_id": "chunk-secret",
                "title": "Evidence benchmark paper",
                "source_reliability": "parsed_fulltext",
                "support_level": "experimental_data",
                "experiment_data_summary": "Benchmark reports claim support precision.",
            }
        ],
        "raw_tool_payload": {"debug": "provider-secret"},
    }

    summary = experiment_design_surface_summary(experiment)

    assert summary["status"] == "ready"
    assert summary["hypothesis"]["title"] == "Retrieval-audited generation protocol"
    assert summary["plan_summary"] == "Compare a retrieval-audited generator against a flat generator on held-out claims."
    assert summary["observable_variables"] == ["claim support precision", "contradiction rate"]
    assert summary["controls"] == ["flat generator baseline", "metadata-only retrieval baseline"]
    assert summary["metrics"] == ["support_precision: >= 0.80", "contradiction_rate: <= 0.10"]
    assert summary["failure_conditions"] == ["Fails if support precision stays below 0.70 after fulltext retrieval."]
    assert summary["alternative_explanations"] == ["Reviewer preference may reflect wording rather than evidence quality."]
    assert summary["required_data"] == ["held-out paper fulltext set", "claim-level citation labels"]
    assert summary["minimal_validation_path"] == "Run a 50-claim pilot before any expensive benchmark."
    assert summary["evidence"]["evidence_count"] == 1
    assert summary["evidence"]["boundary"]["status"] == "parsed_fulltext"
    assert summary["missing_sections"] == []
    assert summary["next_actions"] == ["inspect_evidence", "prepare_execution_workflow", "export_to_report"]
    assert "internal_refs" not in summary
    assert "hyp-exp-secret" not in str(summary)
    assert "experiment-job-secret" not in str(summary)
    assert "D:/secret" not in str(summary)
    assert "provider-secret" not in str(summary)
    assert "chunk-secret" not in str(summary)

    expert_summary = experiment_design_surface_summary(experiment, include_internal_refs=True)
    assert expert_summary["internal_refs"]["hypothesis_id"] == "hyp-exp-secret"
    assert expert_summary["internal_refs"]["experiment_id"] == "experiment-job-secret"
    assert expert_summary["internal_refs"]["script_path"] == "D:/secret/experiment.py"
    assert expert_summary["internal_refs"]["raw_source"]["raw_tool_payload"]["debug"] == "provider-secret"


def test_experiment_design_surface_summary_reports_absent_plan() -> None:
    summary = experiment_design_surface_summary({"title": "Candidate without experiment"})

    assert summary["status"] == "absent"
    assert "plan_summary" in summary["missing_sections"]
    assert "observable_variables" in summary["missing_sections"]
    assert summary["plan_summary"] == ""
    assert summary["next_actions"] == ["draft_experiment_plan", "select_hypothesis"]


def test_report_surface_summary_composes_auditable_output_without_raw_payload() -> None:
    report = {
        "run_id": "run-report-secret",
        "report_id": "report-secret",
        "request": {"research_goal": "Audit retrieval-grounded hypothesis generation", "demo_mode": False, "literature_review": True},
        "findings": ["Retrieval-grounded candidates show clearer evidence boundaries."],
        "limitations": ["Pilot-scale evidence only."],
        "citation_provenance_qa": {"status": "passed", "summary": "All displayed citations have source metadata."},
        "raw_tool_result": {"debug": "provider-secret"},
    }
    hypotheses = [
        {
            "id": "hyp-report-secret",
            "title": "Retrieval audit protocol",
            "explanation": "A protocol that forces claims through evidence and experiment gates.",
            "elo_rating": 1532,
            "support_level": "fulltext",
            "experiment_plan": "Run a 50-claim pilot against a flat baseline.",
            "observable_variables": ["claim support precision"],
            "controls": ["flat baseline"],
            "metrics": ["support precision"],
            "failure_conditions": ["Fails if support precision stays below 0.70."],
            "alternative_explanations": ["Reviewer wording preference."],
            "required_data": ["parsed fulltext corpus"],
            "minimal_validation_path": "Run a 50-claim pilot.",
        }
    ]
    evidence = [
        {
            "paper_id": "paper-report-secret",
            "chunk_id": "chunk-report-secret",
            "title": "Fulltext benchmark",
            "source_reliability": "parsed_fulltext",
            "support_level": "experimental_data",
            "experiment_data_summary": "Benchmark includes citation support precision.",
        }
    ]

    summary = report_surface_summary(report, hypotheses=hypotheses, evidence_items=evidence)

    assert summary["status"] == "ready"
    assert summary["title"] == "Audit retrieval-grounded hypothesis generation"
    assert summary["findings"] == ["Retrieval-grounded candidates show clearer evidence boundaries."]
    assert summary["hypotheses"]["hypothesis_count"] == 1
    assert summary["evidence"]["boundary"]["status"] == "parsed_fulltext"
    assert summary["experiment"]["status"] == "ready"
    assert summary["experiment"]["failure_conditions"] == ["Fails if support precision stays below 0.70."]
    assert summary["limitations"] == ["Pilot-scale evidence only."]
    assert summary["citation_qa"]["status"] == "passed"
    assert summary["next_actions"] == ["review_limitations", "copy_report", "export_report"]
    assert "internal_refs" not in summary
    assert "run-report-secret" not in str(summary)
    assert "report-secret" not in str(summary)
    assert "hyp-report-secret" not in str(summary)
    assert "paper-report-secret" not in str(summary)
    assert "chunk-report-secret" not in str(summary)
    assert "provider-secret" not in str(summary)

    expert_summary = report_surface_summary(
        report,
        hypotheses=hypotheses,
        evidence_items=evidence,
        include_internal_refs=True,
    )
    assert expert_summary["internal_refs"]["run_id"] == "run-report-secret"
    assert expert_summary["internal_refs"]["report_id"] == "report-secret"
    assert expert_summary["internal_refs"]["hypothesis_ids"] == ["hyp-report-secret"]
    assert expert_summary["internal_refs"]["raw_source"]["raw_tool_result"]["debug"] == "provider-secret"


def test_report_surface_summary_flags_citation_or_evidence_conflicts() -> None:
    summary = report_surface_summary(
        {
            "findings": ["A candidate claim may not survive citation QA."],
            "citation_provenance_qa": {"status": "citation_mismatch", "summary": "Claim and citation do not align."},
            "experiment_plan": "Compare against baseline.",
        },
        evidence_items=[
            {
                "title": "Counter evidence",
                "source_reliability": "parsed_fulltext",
                "support_level": "contradicted",
                "snippet": "A replication found no effect.",
            }
        ],
    )

    assert summary["status"] == "needs_review"
    assert summary["citation_qa"]["status"] == "needs_review"
    assert any("contradicts" in item for item in summary["limitations"])
    assert "resolve_evidence_conflicts" in summary["next_actions"]


def test_ranking_surface_summary_exposes_elo_audit_without_raw_payload() -> None:
    matchups = [
        {
            "matchup_id": "matchup-secret",
            "winner_id": "hyp-a-secret",
            "loser_id": "hyp-b-secret",
            "winner_label": "Hypothesis A",
            "loser_label": "Hypothesis B",
            "confidence": 0.76,
            "before_elo": {"hyp-a-secret": 1500, "hyp-b-secret": 1500},
            "after_elo": {"hyp-a-secret": 1532, "hyp-b-secret": 1468},
            "elo_delta": {"hyp-a-secret": 32, "hyp-b-secret": -32},
            "reasoning": "Hypothesis A has stronger parsed-fulltext support and a clearer falsification path.",
            "comparison_mode": "single_turn",
            "raw_provider_response": {"debug": "provider-secret"},
        }
    ]
    hypotheses = [
        {
            "id": "hyp-b-secret",
            "title": "Second candidate",
            "explanation": "A weaker but plausible candidate.",
            "elo_rating": 1468,
            "support_level": "limited",
        },
        {
            "id": "hyp-a-secret",
            "title": "Top candidate",
            "explanation": "Best current candidate by pairwise tournament.",
            "elo_rating": 1532,
            "support_level": "fulltext",
        },
    ]

    summary = ranking_surface_summary(matchups, hypotheses=hypotheses)

    assert summary["status"] == "ready"
    assert summary["ranking_method"] == "pairwise_tournament_elo"
    assert summary["matchup_count"] == 1
    assert summary["confidence"] == {"available": True, "average": 0.76, "minimum": 0.76}
    assert summary["next_actions"] == [
        "inspect_top_ranked_hypotheses",
        "inspect_matchup_details",
        "design_experiment",
    ]
    assert summary["ranked_hypotheses"][0]["title"] == "Top candidate"
    matchup = summary["items"][0]
    assert matchup["winner"] == "Hypothesis A"
    assert matchup["loser"] == "Hypothesis B"
    assert matchup["confidence"] == 0.76
    assert matchup["winner_elo"] == {"before": 1500.0, "after": 1532.0, "delta": 32.0}
    assert matchup["loser_elo"] == {"before": 1500.0, "after": 1468.0, "delta": -32.0}
    assert "parsed-fulltext support" in matchup["reasoning_summary"]
    assert "internal_refs" not in summary
    assert "matchup-secret" not in str(summary)
    assert "hyp-a-secret" not in str(summary)
    assert "provider-secret" not in str(summary)

    expert_summary = ranking_surface_summary(matchups, hypotheses=hypotheses, include_internal_refs=True)
    assert expert_summary["internal_refs"]["matchup_ids"] == ["matchup-secret"]
    assert expert_summary["internal_refs"]["hypothesis_ids"] == ["hyp-b-secret", "hyp-a-secret"]
    assert expert_summary["internal_refs"]["raw_matchups"][0]["raw_provider_response"]["debug"] == "provider-secret"


def test_ranking_surface_summary_reports_absent_tournament() -> None:
    summary = ranking_surface_summary([])

    assert summary["status"] == "absent"
    assert summary["ranking_method"] == "not_available"
    assert summary["matchup_count"] == 0
    assert summary["items"] == []
    assert summary["confidence"] == {"available": False, "average": None, "minimum": None}
    assert summary["next_actions"] == ["run_ranking_phase", "inspect_review_scores"]
