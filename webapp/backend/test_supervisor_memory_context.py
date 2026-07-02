from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_supervisor_context_constraints_summarize_memory_without_raw_refs() -> None:
    from open_coscientist.nodes.supervisor import build_supervisor_context_constraints

    constraints = build_supervisor_context_constraints(
        ["Prioritize falsifiable experiments."],
        {
            "parent_run": {
                "run_id": "raw-parent-run-id",
                "summary": "Parent run favored evidence-linked hypotheses.",
            },
            "prior_hypotheses": [
                {
                    "hypothesis_id": "raw-hyp-id",
                    "text": "Prior hypothesis links parsed fulltext to ranking robustness.",
                    "support_level": "limited",
                }
            ],
            "user_feedback": [
                {
                    "feedback_id": "raw-feedback-id",
                    "target_ref": {"hypothesis_id": "raw-hyp-id"},
                    "feedback_type": "prefer",
                    "text": "Prefer hypotheses with explicit negative controls.",
                }
            ],
            "evidence_summaries": [
                {
                    "checkpoint_id": "raw-checkpoint-id",
                    "source_path": "D:/private/raw.pdf",
                    "title": "Parsed fulltext evidence summary",
                    "source_reliability": "parsed_fulltext",
                    "support_level": "limited",
                }
            ],
            "evidence_boundary": {
                "status": "parsed_fulltext",
                "evidence_count": 1,
                "parsed_fulltext_count": 1,
                "experimental_data_count": 0,
                "raw_debug_ref": "raw-boundary-ref",
            },
        },
        [
            {
                "target_ref": {"hypothesis_id": "raw-current-hyp-id"},
                "feedback_type": "constraint",
                "text": "Use feedback only for next-run planning.",
            }
        ],
        {
            "mode": "summary_only",
            "sections": [
                {
                    "section": "execution_memory_summary",
                    "items": [
                        {
                            "status": "limited",
                            "checkpoint_available": True,
                            "resume_supported": False,
                            "should_retry": True,
                            "recovery_action": "retry",
                            "resume_mode": "metadata_only_retry",
                            "phase": "review",
                            "checkpoint_id": "raw-prompt-checkpoint-id",
                            "checkpoint_ref": "D:/private/checkpoint.sqlite",
                        }
                    ],
                }
            ],
        },
    )

    joined = "\n".join(constraints)
    assert constraints[0] == "Prioritize falsifiable experiments."
    assert "[memory_parent_run]" in joined
    assert "[memory_prior_hypothesis]" in joined
    assert "[memory_user_feedback]" in joined
    assert "[memory_evidence]" in joined
    assert "[memory_evidence_boundary]" in joined
    assert "[memory_usage_policy]" in joined
    assert "[memory_prompt_packet]" in joined
    assert "[memory_prompt_packet_policy]" in joined
    assert "[user_feedback]" in joined
    assert "Parent run favored evidence-linked hypotheses" in joined
    assert "Prior hypothesis links parsed fulltext" in joined
    assert "Prefer hypotheses with explicit negative controls" in joined
    assert "Parsed fulltext evidence summary" in joined
    assert "status=parsed_fulltext" in joined
    assert "parsed_fulltext_count=1" in joined
    assert "section=execution_memory_summary" in joined
    assert "recovery_action=retry" in joined
    assert "resume_mode=metadata_only_retry" in joined
    assert "raw-parent-run-id" not in joined
    assert "raw-hyp-id" not in joined
    assert "raw-feedback-id" not in joined
    assert "raw-checkpoint-id" not in joined
    assert "raw-prompt-checkpoint-id" not in joined
    assert "raw-boundary-ref" not in joined
    assert "D:/private/raw.pdf" not in joined
    assert "D:/private/checkpoint.sqlite" not in joined
    assert "target_ref" not in joined
