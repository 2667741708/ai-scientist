from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_research_outcome_persists_winner_and_exact_evidence_refs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        record = studio.RunRecord(
            run_id="run_outcome",
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=studio.RunRequest(
                research_goal="Identify an evidence-grounded calibration mechanism",
                demo_mode=False,
                literature_review=True,
                min_references=1,
                auto_discover_papers=False,
            ),
            hypotheses=[
                {
                    "text": "The intervention improves calibration under distribution shift.",
                    "literature_grounding": "The mechanism is consistent with the reported result [P1].",
                    "experiment": "Compare expected calibration error on held-out shifts.",
                    "elo_rating": 1260,
                    "score": 8.5,
                    "citation_map": {
                        "P1": {
                            "title": "Calibration under shift",
                            "fulltext": "A sufficiently long parsed fulltext result.",
                            "source_reliability": "parsed_fulltext",
                        }
                    },
                    "evidence_packet": {
                        "status": "ready",
                        "snapshot_id": "evidence_packet_1",
                        "item_count": 1,
                        "parsed_fulltext_count": 1,
                        "experimental_data_count": 1,
                        "items": [
                            {
                                "paper_id": "paper_1",
                                "chunk_id": "chunk_1",
                                "evidence_id": "evidence_1",
                                "parse_run_id": "parse_1",
                                "title": "Calibration under shift",
                                "support_level": "experimental_data",
                                "source_reliability": "parsed_fulltext",
                                "relationship": "support",
                                "text_preview": "Calibration error decreased on held-out shifts.",
                            }
                        ],
                    },
                },
                {
                    "text": "A weaker alternative mechanism.",
                    "elo_rating": 1180,
                    "score": 6.0,
                },
            ],
            evidence_snapshot={"status": "ready", "snapshot_id": "snapshot_run_1"},
        )
        studio.annotate_hypothesis_origins(record)
        studio.apply_citation_provenance_qa(record)
        record.research_outcome = studio.build_research_outcome(record)
        studio.persist_run_record(record)

        response = TestClient(studio.app).get("/api/runs/run_outcome/outcome")

        assert response.status_code == 200, response.text
        outcome = response.json()["research_outcome"]
        assert outcome["winner_id"] == "run_outcome:hypothesis:001"
        assert outcome["evidence_gate"]["status"] == "passed"
        assert outcome["paper_ids"] == ["paper_1"]
        assert outcome["parse_run_ids"] == ["parse_1"]
        assert outcome["evidence_ids"] == ["evidence_1"]
        assert outcome["knowledge_chunks"][0]["chunk_id"] == "chunk_1"
