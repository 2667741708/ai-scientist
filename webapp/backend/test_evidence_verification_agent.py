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


if __name__ == "__main__":
    test_evidence_verification_agent_marks_missing_evidence_ungrounded()
    test_evidence_verification_agent_detects_support_and_counter_markers()
    print("evidence verification agent tests passed")
