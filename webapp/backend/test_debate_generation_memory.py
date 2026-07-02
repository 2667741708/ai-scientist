from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_debate_generation_guidance_includes_memory_without_raw_refs() -> None:
    from open_coscientist.nodes.generation.debate import augment_generation_supervisor_guidance

    guidance = augment_generation_supervisor_guidance(
        {
            "workflow_plan": {
                "generation_phase": {
                    "focus_areas": ["mechanistic specificity"],
                }
            }
        },
        ["User seed hypothesis should guide debate generation."],
        {
            "prior_hypotheses": [
                {
                    "hypothesis_id": "raw-prior-hyp-id",
                    "text": "Prior hypothesis links parsed evidence to ranking stability.",
                    "support_level": "limited",
                }
            ],
            "user_feedback": [
                {
                    "feedback_id": "raw-memory-feedback-id",
                    "target_ref": {"hypothesis_id": "raw-prior-hyp-id"},
                    "feedback_type": "prefer",
                    "text": "Prefer hypotheses with explicit counter-evidence checks.",
                }
            ],
        },
        [
            {
                "feedback_id": "raw-current-feedback-id",
                "target_ref": {"hypothesis_id": "raw-current-hyp-id"},
                "feedback_type": "constraint",
                "text": "Generate candidates that can fail under a minimal experiment.",
            }
        ],
    )

    focus_areas = guidance["workflow_plan"]["generation_phase"]["focus_areas"]
    joined = "\n".join(focus_areas)
    assert focus_areas[0] == "mechanistic specificity"
    assert "[user_starting_hypothesis]" in joined
    assert "[memory_prior_hypothesis]" in joined
    assert "[memory_user_feedback]" in joined
    assert "[user_feedback]" in joined
    assert "[memory_generation_policy]" in joined
    assert "User seed hypothesis should guide debate generation" in joined
    assert "Prior hypothesis links parsed evidence" in joined
    assert "Prefer hypotheses with explicit counter-evidence checks" in joined
    assert "Generate candidates that can fail" in joined
    assert "raw-prior-hyp-id" not in joined
    assert "raw-memory-feedback-id" not in joined
    assert "raw-current-feedback-id" not in joined
    assert "raw-current-hyp-id" not in joined
    assert "target_ref" not in joined
