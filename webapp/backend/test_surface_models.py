from __future__ import annotations

from surface_models import (
    evidence_surface_collection,
    evidence_surface_summary,
    hypothesis_surface_collection,
    hypothesis_surface_summary,
    run_confirmation_surface_summary,
    run_surface_summary,
)


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
        "items": [
            {
                "work_item_id": "work-secret",
                "status": "queued",
                "status_label": "Queued",
                "phase": "generate",
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
    assert summary["queue"]["current_work_status"] == "queued"
    assert summary["memory"]["feedback_count"] == 1
    assert summary["memory"]["evidence_source_count"] == 3
    assert summary["memory"]["execution_memory_status"] == "limited"
    assert summary["recovery"]["recovery_mode"] == "queue_retry_without_checkpoint"
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
