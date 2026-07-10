from __future__ import annotations

from open_coscientist.models import Hypothesis
from open_coscientist.nodes.evidence_grounding import (
    evidence_grounding_node,
    format_hypothesis_with_evidence,
)


async def test_evidence_grounding_freezes_hypothesis_packets_before_review() -> None:
    hypotheses = [Hypothesis(text="A retrieval-grounded mechanism improves calibration")]

    async def resolver(_hypothesis):
        return {
            "library_id": "library_test",
            "items": [
                {
                    "paper_id": "paper_1",
                    "chunk_id": "chunk_1",
                    "evidence_id": "evidence_1",
                    "parse_run_id": "parse_1",
                    "title": "Calibration study",
                    "support_level": "experimental_data",
                    "source_reliability": "parsed_fulltext",
                    "text_preview": "The intervention improved calibration in the held-out evaluation.",
                }
            ],
        }

    result = await evidence_grounding_node(
        {
            "hypotheses": hypotheses,
            "progress_callback": None,
        },
        resolver,
    )

    packet = result["hypotheses"][0].evidence_packet
    assert packet["item_count"] == 1
    assert packet["parsed_fulltext_count"] == 1
    assert packet["experimental_data_count"] == 1
    assert packet["items"][0]["evidence_id"] == "evidence_1"
    assert result["evidence_snapshot"]["status"] == "ready"
    assert result["evidence_snapshot"]["evidence_item_count"] == 1

    prompt_packet = format_hypothesis_with_evidence(result["hypotheses"][0])
    assert "Calibration study" in prompt_packet
    assert "parsed_fulltext" in prompt_packet
    assert "retrieved relevance is not proof" in prompt_packet


async def test_evidence_grounding_marks_absent_evidence_without_inventing_support() -> None:
    hypothesis = Hypothesis(text="An unsupported mechanism")

    result = await evidence_grounding_node(
        {"hypotheses": [hypothesis], "progress_callback": None},
        lambda _hypothesis: [],
    )

    assert result["evidence_snapshot"]["status"] == "limited"
    assert hypothesis.evidence_packet["status"] == "absent"
    assert "do not infer support from absence" in format_hypothesis_with_evidence(hypothesis)
