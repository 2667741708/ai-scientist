from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_review_guidance_includes_feedback_memory_without_raw_refs() -> None:
    from open_coscientist.nodes.review import augment_review_supervisor_guidance

    guidance = augment_review_supervisor_guidance(
        {
            "workflow_plan": {
                "review_phase": {
                    "critical_criteria": ["scientific soundness"],
                    "review_depth": "comparative",
                }
            }
        },
        {
            "user_feedback": [
                {
                    "feedback_id": "raw-memory-feedback-id",
                    "target_ref": {"hypothesis_id": "raw-memory-hyp-id"},
                    "feedback_type": "prefer",
                    "text": "Prefer hypotheses with falsifiable negative controls.",
                }
            ],
            "evidence_summaries": [
                {
                    "checkpoint_id": "raw-checkpoint-id",
                    "source_path": "D:/private/source.pdf",
                    "title": "Parsed fulltext support is limited.",
                    "source_reliability": "parsed_fulltext",
                    "support_level": "limited",
                }
            ],
        },
        [
            {
                "feedback_id": "raw-current-feedback-id",
                "target_ref": {"hypothesis_id": "raw-current-hyp-id"},
                "feedback_type": "constraint",
                "text": "Penalize hypotheses without a clear failure condition.",
            }
        ],
    )

    review_phase = guidance["workflow_plan"]["review_phase"]
    criteria = review_phase["critical_criteria"]
    joined = "\n".join(criteria + [review_phase["review_depth"]])
    assert criteria[0] == "scientific soundness"
    assert "[memory_user_feedback]" in joined
    assert "[memory_evidence_boundary]" in joined
    assert "[user_feedback]" in joined
    assert "Prefer hypotheses with falsifiable negative controls" in joined
    assert "Parsed fulltext support is limited" in joined
    assert "Penalize hypotheses without a clear failure condition" in joined
    assert "comparative" in review_phase["review_depth"]
    assert "instant rewrite" in review_phase["review_depth"]
    assert "raw-memory-feedback-id" not in joined
    assert "raw-memory-hyp-id" not in joined
    assert "raw-current-feedback-id" not in joined
    assert "raw-current-hyp-id" not in joined
    assert "raw-checkpoint-id" not in joined
    assert "D:/private/source.pdf" not in joined
    assert "target_ref" not in joined
