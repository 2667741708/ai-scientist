from __future__ import annotations

from surface_models import hypothesis_surface_collection, hypothesis_surface_summary


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
