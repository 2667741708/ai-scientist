from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_ranking_guidance_includes_memory_prompt_packet_without_raw_refs() -> None:
    from open_coscientist.nodes.ranking import augment_ranking_supervisor_guidance

    guidance = augment_ranking_supervisor_guidance(
        {"research_goal_analysis": {"key_areas": ["mechanistic novelty"]}},
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
                            "phase": "ranking",
                            "checkpoint_id": "raw-ranking-checkpoint-id",
                            "checkpoint_ref": "D:/private/ranking-checkpoint.sqlite",
                        }
                    ],
                }
            ],
        },
    )

    key_areas = guidance["research_goal_analysis"]["key_areas"]
    joined = "\n".join(key_areas)
    assert key_areas[0] == "mechanistic novelty"
    assert "[memory_prompt_packet]" in joined
    assert "[memory_prompt_packet_policy]" in joined
    assert "section=execution_memory_summary" in joined
    assert "recovery_action=retry" in joined
    assert "resume_mode=metadata_only_retry" in joined
    assert "raw-ranking-checkpoint-id" not in joined
    assert "D:/private/ranking-checkpoint.sqlite" not in joined
