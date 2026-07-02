from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def planner_json(
    intent: str,
    *,
    capability_id: str | None = None,
    execution_mode: str = "read_only",
    inputs: dict | None = None,
    grounding_boundary: str = "knowledge_base",
):
    if capability_id is None:
        capability_id = {
            "check_hypothesis_grounding": "evidence.check_hypothesis_grounding",
            "verify_evidence_with_literature": "evidence.verify_with_literature",
        }.get(intent)
    return json.dumps(
        {
            "intent": intent,
            "capability_id": capability_id,
            "executionMode": execution_mode,
            "inputs": inputs or {},
            "missingInputs": [],
            "confidence": 0.92,
            "groundingBoundary": grounding_boundary,
            "requiresConfirmation": execution_mode == "approval_required",
            "answerStrategy": f"test planner selected {intent}",
        },
        ensure_ascii=False,
    )


def planner_sequence(*plans: str):
    items = list(plans)

    async def fake_call_research_chat_planner_llm(**kwargs):
        if not items:
            raise AssertionError("planner_sequence exhausted")
        return items.pop(0)

    return fake_call_research_chat_planner_llm


def test_research_chat_evidence_verification_two_stage_workflow() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
        sys.modules.pop("app", None)
        studio = importlib.import_module("app")

        studio.knowledge_base.ingest(
            title="Evidence verification study",
            content=(
                "# Abstract\n\nEvidence verification agents improve auditability for hypothesis support.\n\n"
                "## Results\n\nA benchmark with n=24 reports that parsed fulltext evidence improves audit accuracy."
            ),
            abstract="Evidence verification agents improve auditability for hypothesis support.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
        )
        record = studio.RunRecord(
            run_id="run_verify_chat",
            status="complete",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(research_goal="Validate evidence verification chat workflow"),
        )
        studio.persist_run_record(record)

        async def fake_mcp_tool_workflow(request):
            return {
                "tool_name": "mcp.literature_review",
                "mcp_tool_name": "pubmed_search_with_fulltext",
                "tool_id": "pubmed_fulltext",
                "workflow_name": request.workflow_name,
                "phase": request.phase,
                "run_id": request.run_id,
                "approval": {"confirmed": True, "scope": request.approval.scope},
                "result_ref": {"result_id": "tool_result_fake", "run_id": request.run_id},
                "result_preview": "External literature reports one failed replication and one supporting fulltext candidate.",
                "result_size": 91,
            }

        studio.execute_mcp_tool_workflow = fake_mcp_tool_workflow
        client = TestClient(studio.app)
        hypothesis_text = "Evidence verification agents improve auditability for hypothesis support."

        async def fake_call_research_chat_llm(**kwargs):
            return "模型化证据核验回答。"

        original_has_key = studio.has_model_provider_key
        original_planner = studio.call_research_chat_planner_llm
        original_llm = studio.call_research_chat_llm
        studio.has_model_provider_key = lambda model_name: True
        studio.call_research_chat_llm = fake_call_research_chat_llm
        studio.call_research_chat_planner_llm = planner_sequence(
            planner_json(
                "check_hypothesis_grounding",
                inputs={"hypothesis_text": hypothesis_text},
            ),
            planner_json(
                "verify_evidence_with_literature",
                execution_mode="approval_required",
                grounding_boundary="literature_mcp_audit",
                inputs={"hypothesis_text": hypothesis_text},
            ),
        )

        try:
            local = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "这个假设有没有足够证据支撑：Evidence verification agents improve auditability for hypothesis support.",
                    "context": {"run_id": "run_verify_chat", "language": "zh"},
                },
            )
            proposed = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "用外部文献反证检查这个假设：Evidence verification agents improve auditability for hypothesis support.",
                    "context": {"run_id": "run_verify_chat", "language": "zh"},
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_planner_llm = original_planner
            studio.call_research_chat_llm = original_llm

        assert local.status_code == 200, local.text
        local_result = local.json()["assistant_message"]["result"]
        assert local_result["agent"] == "evidence_verification_agent"
        assert local_result["resultRef"]["result_id"]
        assert proposed.status_code == 200, proposed.text
        proposal = proposed.json()["assistant_message"]["proposal"]
        assert proposal["approvalScope"] == "mcp.literature_review"
        assert proposal["executionTarget"] == "workflow.evidence_literature_verification"

        denied = client.post(
            f"/api/research-chat/actions/{proposal['actionId']}/confirm",
            json={"approval": {"confirmed": False, "scope": ""}},
        )
        assert denied.status_code == 428

        confirmed = client.post(
            f"/api/research-chat/actions/{proposal['actionId']}/confirm",
            json={"approval": {"confirmed": True, "scope": "mcp.literature_review", "reason": "test"}},
        )
        assert confirmed.status_code == 200, confirmed.text
        result = confirmed.json()["assistant_message"]["result"]
        assert result["externalCheck"]["status"] == "complete"
        assert result["mcpResultRef"]["result_id"] == "tool_result_fake"


if __name__ == "__main__":
    test_research_chat_evidence_verification_two_stage_workflow()
    print("research chat evidence verification tests passed")
