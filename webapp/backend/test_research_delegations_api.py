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


def persist_test_run(studio, run_id: str) -> None:
    record = studio.RunRecord(
        run_id=run_id,
        status="complete",
        created_at=1.0,
        updated_at=1.0,
        request=studio.RunRequest(research_goal="Validate durable research delegations"),
    )
    studio.persist_run_record(record)


def test_research_delegations_api_creates_lists_updates_runs_and_searches(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        persist_test_run(studio, "run_delegation")
        client = TestClient(studio.app)

        created = client.post(
            "/api/research-delegations",
            json={
                "run_id": "run_delegation",
                "title": "MoA evidence and contradiction review",
                "phase": "review",
                "strategy": "moa_review",
                "agents": [
                    {
                        "role": "Evidence Agent",
                        "brief": "Check whether the hypothesis has parsed fulltext support.",
                        "skill_ids": ["evidence-grounding-rubric"],
                        "target_ref": {"hypothesis_id": "HYP-001"},
                    },
                    {
                        "role": "Contradiction Agent",
                        "brief": "Find counter-evidence and failure conditions.",
                        "skill_ids": ["falsifiability-review"],
                    },
                ],
                "target_ref": {"hypothesis_id": "HYP-001"},
            },
        )
        assert created.status_code == 200, created.text
        delegation = created.json()["delegation"]
        assert delegation["phase"] == "review_critique"
        assert delegation["agents"][0]["role"] == "Evidence Agent"

        listed = client.get(
            "/api/research-delegations",
            params={"run_id": "run_delegation", "strategy": "moa_review"},
        )
        assert listed.status_code == 200
        assert listed.json()["count"] == 1

        updated = client.patch(
            f"/api/research-delegations/{delegation['delegation_id']}",
            json={
                "status": "completed",
                "summary": "MoA review completed and stored as a result reference.",
                "result_ref": {"tool_result_id": "result_moa"},
            },
        )
        assert updated.status_code == 200
        assert updated.json()["delegation"]["status"] == "completed"
        assert updated.json()["delegation"]["result_ref"]["tool_result_id"] == "result_moa"

        async def fake_call_delegation_llm(*, prompt: str, model_name: str, max_tokens: int, temperature: float) -> str:
            role = "Evidence Agent" if "Evidence Agent" in prompt else "Contradiction Agent"
            return f"## Assessment\n{role} completed grounded review.\n\n## Confidence\n0.8"

        monkeypatch.setattr(studio, "has_model_provider_key", lambda _model_name: True)
        monkeypatch.setattr(studio, "call_delegation_llm", fake_call_delegation_llm)

        no_approval = client.post(
            f"/api/research-delegations/{delegation['delegation_id']}/run",
            json={"model_name": "test/model"},
        )
        assert no_approval.status_code == 428

        run_response = client.post(
            f"/api/research-delegations/{delegation['delegation_id']}/run",
            json={
                "model_name": "test/model",
                "approval": {
                    "confirmed": True,
                    "scope": "research_delegation.run",
                    "reason": "test real delegation runner",
                },
            },
        )
        assert run_response.status_code == 200, run_response.text
        run_payload = run_response.json()
        assert run_payload["delegation"]["status"] == "completed"
        assert len(run_payload["agent_outputs"]) == 2
        assert run_payload["result_ref"]["result_id"]

        loaded_result = client.get(f"/api/tools/results/{run_payload['result_ref']['result_id']}")
        assert loaded_result.status_code == 200
        assert loaded_result.json()["content"]["synthetic"] is False
        assert loaded_result.json()["content"]["agent_outputs"][0]["status"] == "completed"

        tool_calls = client.get("/api/runs/run_delegation/tool-calls")
        assert tool_calls.status_code == 200
        assert any(item["tool_name"] == "research.delegation_runner" for item in tool_calls.json()["tool_calls"])

        search = client.get("/api/session-search", params={"q": "contradiction", "types": "delegation"})
        assert search.status_code == 200
        assert search.json()["count"] == 1
        assert search.json()["results"][0]["type"] == "delegation"

        missing_run = client.post(
            "/api/research-delegations",
            json={
                "run_id": "missing_run",
                "title": "Invalid delegation",
                "agents": [{"role": "Evidence Agent", "brief": "Check evidence."}],
            },
        )
        assert missing_run.status_code == 404


if __name__ == "__main__":
    from _pytest.monkeypatch import MonkeyPatch

    test_research_delegations_api_creates_lists_updates_runs_and_searches(MonkeyPatch())
    print("research delegations API tests passed")
