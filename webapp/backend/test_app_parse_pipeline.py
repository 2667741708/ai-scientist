from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from test_pdf_parser import create_sample_pdf


def test_pdf_parse_endpoint_persists_rag_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")

        sys.modules.pop("app", None)
        studio = importlib.import_module("app")

        pdf = Path(tmp) / "paper.pdf"
        create_sample_pdf(pdf)
        client = TestClient(studio.app)

        response = client.post(
            "/api/knowledge/pdf/parse",
            json={
                "pdf_path": str(pdf),
                "fetch_metadata": False,
                "ingest_to_knowledge_base": True,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["parse_run_id"]
        assert payload["paper_id"]
        assert len(payload["items"]) == 13
        assert any(item["item_key"] == "media_region_quality_checked" for item in payload["items"])
        assert any(item["item_key"] == "ragflow_embedding_indexed" for item in payload["items"])
        assert payload["chunks_count"] > 0
        assert payload["rag_search_ready"] is True

        search_response = client.get(
            "/api/knowledge/search",
            params={"q": "accuracy baseline parsing", "limit": 4},
        )
        assert search_response.status_code == 200
        results = search_response.json()["results"]
        assert results
        assert results[0]["parse_run_id"] == payload["parse_run_id"]
        assert results[0]["evidence_id"]


if __name__ == "__main__":
    test_pdf_parse_endpoint_persists_rag_evidence()
    print("app parse pipeline tests passed")
