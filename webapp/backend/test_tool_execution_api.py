from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def test_read_tool_execution_api_enforces_phase_and_risk() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
        sys.modules.pop("app", None)
        studio = importlib.import_module("app")

        studio.knowledge_base.ingest(
            title="Durable provenance execution",
            content=(
                "# Abstract\n\nSQL evidence retrieval supports durable hypothesis provenance.\n\n"
                "## Results\n\nA benchmark with n=24 reports accuracy 0.9 for provenance recovery."
            ),
            abstract="SQL evidence retrieval supports durable hypothesis provenance.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
        )
        record = studio.RunRecord(
            run_id="run_tool_exec",
            status="complete",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(research_goal="Validate tool execution audit path"),
        )
        studio.persist_run_record(record)

        client = TestClient(studio.app)
        rag_response = client.post(
            "/api/tools/execute",
            json={
                "tool_name": "knowledge_base.rag_search",
                "phase": "literature_review",
                "run_id": "run_tool_exec",
                "arguments": {"query": "SQL durable provenance accuracy", "limit": 4},
            },
        )
        assert rag_response.status_code == 200
        assert rag_response.json()["result_count"] >= 1
        result_ref = rag_response.json()["result_ref"]
        assert result_ref["result_id"]

        support_response = client.post(
            "/api/tools/execute",
            json={
                "tool_name": "knowledge_base.support_for_hypothesis",
                "phase": "review_critique",
                "arguments": {
                    "hypothesis": {"text": "SQL evidence retrieval supports durable provenance."},
                    "limit": 4,
                },
            },
        )
        assert support_response.status_code == 200
        assert support_response.json()["result_count"] >= 1

        phase_denied = client.post(
            "/api/tools/execute",
            json={
                "tool_name": "knowledge_base.rag_search",
                "phase": "experiment_execution",
                "arguments": {"query": "SQL durable provenance"},
            },
        )
        assert phase_denied.status_code == 403
        assert phase_denied.json()["detail"]["code"] == "tool_phase_not_allowed"

        write_denied = client.post(
            "/api/tools/execute",
            json={
                "tool_name": "provenance.record_run",
                "phase": "supervisor",
                "arguments": {"run_record": {}},
            },
        )
        assert write_denied.status_code == 403
        assert write_denied.json()["detail"]["code"] == "tool_requires_dedicated_workflow"

        tool_calls = client.get("/api/runs/run_tool_exec/tool-calls")
        assert tool_calls.status_code == 200
        assert tool_calls.json()["count"] == 1
        assert tool_calls.json()["tool_calls"][0]["tool_name"] == "knowledge_base.rag_search"

        retrievals = client.get("/api/runs/run_tool_exec/evidence-retrievals")
        assert retrievals.status_code == 200
        assert retrievals.json()["count"] >= 1
        assert any(
            item["tool_name"] == "knowledge_base.rag_search"
            for item in retrievals.json()["retrievals"]
        )

        tool_results = client.get("/api/runs/run_tool_exec/tool-results")
        assert tool_results.status_code == 200
        assert tool_results.json()["count"] == 1
        loaded_result = client.get(f"/api/tools/results/{result_ref['result_id']}")
        assert loaded_result.status_code == 200
        assert loaded_result.json()["content"][0]["paper_id"]

        second_rag_response = client.post(
            "/api/tools/execute",
            json={
                "tool_name": "knowledge_base.rag_search",
                "phase": "literature",
                "run_id": "run_tool_exec",
                "arguments": {"query": "SQL durable provenance accuracy", "limit": 4},
            },
        )
        assert second_rag_response.status_code == 200

        repeated_denied = client.post(
            "/api/tools/execute",
            json={
                "tool_name": "knowledge_base.rag_search",
                "phase": "literature_review",
                "run_id": "run_tool_exec",
                "arguments": {"query": "SQL durable provenance accuracy", "limit": 4},
            },
        )
        assert repeated_denied.status_code == 409
        assert repeated_denied.json()["detail"]["code"] == "repeated_identical_tool_call"

        policies = client.get("/api/tools/policies")
        assert policies.status_code == 200
        assert any(item["phase"] == "literature_review" for item in policies.json()["policies"])


if __name__ == "__main__":
    test_read_tool_execution_api_enforces_phase_and_risk()
    print("tool execution API tests passed")
