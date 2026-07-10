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


def test_session_search_api_returns_cross_object_references() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        record = studio.RunRecord(
            run_id="run_session_search",
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=studio.RunRequest(research_goal="Searchable citation provenance workspace"),
            hypotheses=[
                {
                    "id": "HYP-CITATION",
                    "text": "Citation provenance search finds weak evidence claims.",
                    "grounding_status": "knowledge_base_supported",
                    "citation_map": {},
                }
            ],
            research_plan={"strategy": "session search API test"},
        )
        studio.persist_run_record(record)
        studio.knowledge_base.store_tool_result(
            run_id="run_session_search",
            tool_name="knowledge_base.rag_search",
            phase="literature_review",
            content=[{"text": "citation provenance evidence"}],
            result_kind="evidence_results",
            summary="Stored citation provenance evidence search result.",
        )
        studio.knowledge_base.create_research_task(
            task_id="task_citation",
            run_id="run_session_search",
            title="Audit citation provenance",
            task_type="citation_qa",
            notes="Check weak public HTML evidence.",
        )
        client = TestClient(studio.app)

        response = client.get(
            "/api/session-search",
            params={
                "q": "citation provenance",
                "run_id": "run_session_search",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["count"] >= 3
        result_types = {item["type"] for item in payload["results"]}
        assert {"run", "hypothesis", "tool_result", "task"}.issubset(result_types)
        assert all("target_ref" in item for item in payload["results"])

        filtered = client.get(
            "/api/session-search",
            params={
                "q": "citation",
                "types": "task",
            },
        )
        assert filtered.status_code == 200
        assert filtered.json()["count"] == 1
        assert filtered.json()["results"][0]["type"] == "task"

        too_short = client.get("/api/session-search", params={"q": "c"})
        assert too_short.status_code == 422


if __name__ == "__main__":
    test_session_search_api_returns_cross_object_references()
    print("session search API tests passed")
