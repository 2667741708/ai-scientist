from __future__ import annotations

from evidence_verification_agent import EvidenceVerificationAgent


def test_evidence_verification_agent_marks_missing_evidence_ungrounded() -> None:
    agent = EvidenceVerificationAgent()
    report = agent.verify(
        hypothesis_text="A new mechanism improves auditability.",
        local_results=[],
    )
    assert report["verdict"] == "ungrounded"
    assert report["support_level"] == "none"
    assert report["missingEvidence"]
    assert report["externalCheck"]["status"] == "not_requested"


def test_evidence_verification_agent_detects_support_and_counter_markers() -> None:
    agent = EvidenceVerificationAgent()
    report = agent.verify(
        hypothesis_text="Parsed fulltext evidence improves auditability for hypothesis support.",
        local_results=[
            {
                "chunk_id": "chunk_1",
                "paper_id": "paper_1",
                "title": "Auditability benchmark",
                "text_preview": "Parsed fulltext evidence improves auditability for hypothesis support in a benchmark.",
                "support_level": "experimental_data",
                "source_reliability": "parsed_fulltext",
            },
            {
                "chunk_id": "chunk_2",
                "paper_id": "paper_2",
                "title": "Replication note",
                "text_preview": "A failed replication reports no effect in a smaller benchmark.",
                "support_level": "external_literature_candidate",
                "source_reliability": "external_mcp_best_effort",
                "source_channel": "external_mcp",
            },
        ],
        external_check={"status": "complete", "summary": "External check completed."},
    )
    assert report["verdict"] in {"supported", "limited", "contradicted"}
    assert report["support_level"] == "experimental_data"
    assert report["possibleCounterEvidence"]
    assert report["sourceReliabilitySummary"]["externalMcpEvidenceCount"] == 1


def test_evidence_verification_agent_classifies_item_stance() -> None:
    agent = EvidenceVerificationAgent()
    hypothesis = "Parsed fulltext retrieval improves citation auditability in benchmark evaluation"
    classified = agent.classify_evidence_items(
        hypothesis_text=hypothesis,
        evidence_items=[
            {
                "chunk_id": "support",
                "title": "Citation auditability benchmark",
                "text_preview": "Parsed fulltext retrieval improves citation auditability in benchmark evaluation.",
                "support_level": "experimental_data",
                "source_reliability": "parsed_fulltext",
            },
            {
                "chunk_id": "counter",
                "title": "Failed replication",
                "text_preview": "A failed replication found no effect of fulltext retrieval on citation auditability.",
                "source_reliability": "parsed_fulltext",
            },
            {
                "chunk_id": "irrelevant",
                "title": "Unrelated microscopy result",
                "text_preview": "Cell morphology changed after staining.",
                "source_reliability": "parsed_fulltext",
            },
        ],
    )

    assert classified[0]["relationship"] == "support"
    assert classified[1]["relationship"] == "contradict"
    assert classified[2]["relationship"] == "irrelevant"
    assert all(item["relationship_rationale"] for item in classified)


if __name__ == "__main__":
    test_evidence_verification_agent_marks_missing_evidence_ungrounded()
    test_evidence_verification_agent_detects_support_and_counter_markers()
    print("evidence verification agent tests passed")
