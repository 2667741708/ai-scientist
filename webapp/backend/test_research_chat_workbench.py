from __future__ import annotations

import importlib
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    sys.modules.pop("app", None)
    return importlib.import_module("app")


class FakeSshChatResult:
    status = "complete"
    server_id = "c201-5080"
    ssh_alias = "c201-5080"
    command = "hostname"
    workdir = None
    run_dir = "fake-ssh-chat-run"
    stdout = "c201-MS-7E06"
    stderr = ""
    returncode = 0
    duration_seconds = 0.01
    artifacts = {"stdout": "stdout.txt", "stderr": "stderr.txt", "manifest": "manifest.json"}
    guardrail = {"allowed": True, "server_id": "c201-5080"}

    def to_dict(self):
        return {
            "status": self.status,
            "server_id": self.server_id,
            "ssh_alias": self.ssh_alias,
            "command": self.command,
            "workdir": self.workdir,
            "run_dir": self.run_dir,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "artifacts": self.artifacts,
            "guardrail": self.guardrail,
        }


class FakeWebSearchChatResult:
    payload = {
        "provider": "test",
        "query": "open-coscientist github",
        "result_count": 1,
        "results": [
            {
                "rank": 1,
                "title": "Open Coscientist",
                "url": "https://example.org/open-coscientist",
                "display_url": "example.org",
                "snippet": "A source URL returned by fake public search.",
                "source": "test",
            }
        ],
        "results_path": "results.json",
        "metadata_path": "metadata.json",
    }


def planner_json(
    intent: str,
    *,
    capability_id: str | None = None,
    execution_mode: str = "read_only",
    inputs: dict | None = None,
    missing_inputs: list[str] | None = None,
    confidence: float = 0.91,
    grounding_boundary: str = "knowledge_base",
    requires_confirmation: bool | None = None,
):
    if capability_id is None:
        capability_id = {
            "ask_project_ai": "project.answer_with_rag",
            "discover_capabilities": "project.discover_capabilities",
            "start_research_run": "research.start_run",
            "explain_current_run": "research.explain_run",
            "inspect_hypothesis": "hypothesis.inspect",
            "explain_ranking": "ranking.explain_elo",
            "parse_pdf_to_knowledge_base": "evidence.parse_pdf",
            "search_public_web": "evidence.web_search_public",
            "search_knowledge_evidence": "evidence.search_knowledge",
            "check_hypothesis_grounding": "evidence.check_hypothesis_grounding",
            "verify_evidence_with_literature": "evidence.verify_with_literature",
            "design_experiment": "experiment.design",
            "draft_report": "report.draft",
            "search_session_history": "history.session_search",
            "run_terminal_command": "runtime.terminal_command",
            "run_ssh_training_command": "runtime.ssh_training_command",
        }.get(intent)
    if requires_confirmation is None:
        requires_confirmation = execution_mode == "approval_required"
    return json.dumps(
        {
            "intent": intent,
            "capability_id": capability_id,
            "executionMode": execution_mode,
            "inputs": inputs or {},
            "missingInputs": missing_inputs or [],
            "confidence": confidence,
            "groundingBoundary": grounding_boundary,
            "requiresConfirmation": requires_confirmation,
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


def test_research_chat_capabilities_sessions_and_start_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        client = TestClient(studio.app)

        capabilities = client.get("/api/research-chat/capabilities")
        assert capabilities.status_code == 200, capabilities.text
        intents = {item["intent"] for item in capabilities.json()["capabilities"]}
        assert {"discover_capabilities", "start_research_run", "explain_ranking", "parse_pdf_to_knowledge_base"}.issubset(intents)

        prompts: list[str] = []

        def fake_has_model_provider_key(model_name: str) -> bool:
            return model_name == "openai/mimo-v2.5"

        async def fake_call_research_chat_llm(**kwargs):
            prompts.append(kwargs["prompt"])
            return "项目能力问答现在会先检索 SQL 知识库，再把上下文交给模型回答。"

        original_has_key = studio.has_model_provider_key
        original_llm = studio.call_research_chat_llm
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = fake_has_model_provider_key
        studio.call_research_chat_llm = fake_call_research_chat_llm
        studio.call_research_chat_planner_llm = planner_sequence(
            planner_json("discover_capabilities"),
            planner_json(
                "start_research_run",
                execution_mode="approval_required",
                grounding_boundary="live_model_workflow",
                inputs={"research_goal": "验证 chat-first workbench 能生成合理候选假设"},
            ),
        )
        try:
            capability_turn = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "这个项目现在能做什么？",
                    "context": {"mode": "project_help", "model_name": "openai/mimo-v2.5", "language": "zh"},
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_llm = original_llm
            studio.call_research_chat_planner_llm = original_planner

        assert capability_turn.status_code == 200, capability_turn.text
        session_id = capability_turn.json()["session_id"]
        result = capability_turn.json()["assistant_message"]["result"]
        assert result["intent"] == "discover_capabilities"
        assert result["status"] == "complete"
        assert result["groundingBoundary"] == "model_plus_knowledge_base"
        assert "SQL 知识库" in capability_turn.json()["assistant_message"]["text"]
        assert prompts
        assert "Project AI answer pipeline" in prompts[0]

        sessions = client.get("/api/research-chat/sessions")
        assert sessions.status_code == 200
        assert any(item["session_id"] == session_id for item in sessions.json()["sessions"])

        session = client.get(f"/api/research-chat/sessions/{session_id}")
        assert session.status_code == 200
        assert len(session.json()["messages"]) >= 2

        original_has_key = studio.has_model_provider_key
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = fake_has_model_provider_key
        studio.call_research_chat_planner_llm = planner_sequence(
            planner_json(
                "start_research_run",
                execution_mode="approval_required",
                grounding_boundary="live_model_workflow",
                inputs={"research_goal": "验证 chat-first workbench 能生成合理候选假设"},
            )
        )
        try:
            proposed = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "研究目标：验证 chat-first workbench 能生成合理候选假设",
                    "context": {
                        "mode": "workspace",
                        "demo_mode": True,
                        "literature_review": False,
                        "initial_hypotheses": 1,
                        "iterations": 0,
                        "language": "zh",
                    },
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_planner_llm = original_planner
        assert proposed.status_code == 200, proposed.text
        proposal = proposed.json()["assistant_message"]["proposal"]
        assert proposal["approvalScope"] == "research.start_live_run"
        assert proposal["executionTarget"] == "workflow.start_run"

        denied = client.post(
            f"/api/research-chat/actions/{proposal['actionId']}/confirm",
            json={"approval": {"confirmed": False, "scope": ""}},
        )
        assert denied.status_code == 428

        confirmed = client.post(
            f"/api/research-chat/actions/{proposal['actionId']}/confirm",
            json={"approval": {"confirmed": True, "scope": "research.start_live_run", "reason": "test"}},
        )
        assert confirmed.status_code == 200, confirmed.text
        run_result = confirmed.json()["assistant_message"]["result"]
        assert run_result["intent"] == "start_research_run"
        assert run_result["runId"]

        action = studio.knowledge_base.get_research_chat_action(proposal["actionId"])
        assert action["status"] == "complete"
        assert action["result_ref"]["run_id"] == run_result["runId"]


def test_research_chat_general_turn_uses_llm_with_knowledge_context() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        prompts: list[str] = []

        def fake_has_model_provider_key(model_name: str) -> bool:
            return model_name == "openai/mimo-v2.5"

        async def fake_call_research_chat_llm(**kwargs):
            prompts.append(kwargs["prompt"])
            return "可以。这个入口会由后端把知识库片段和工作台约束拼成 prompt，再调用真实模型回答。"

        def fake_rag_search(query: str, **kwargs):
            return [
                {
                    "title": "Workbench integration note",
                    "section_path": ["Architecture", "Research chat"],
                    "source_reliability": "parsed_fulltext",
                    "support_level": "fulltext",
                    "text_preview": "Research chat should call the backend model proxy with retrieved knowledge snippets.",
                }
            ]

        original_has_key = studio.has_model_provider_key
        original_llm = studio.call_research_chat_llm
        original_planner = studio.call_research_chat_planner_llm
        original_rag_search = studio.paper_parse_store.rag_search
        studio.has_model_provider_key = fake_has_model_provider_key
        studio.call_research_chat_llm = fake_call_research_chat_llm
        studio.call_research_chat_planner_llm = planner_sequence(planner_json("ask_project_ai"))
        studio.paper_parse_store.rag_search = fake_rag_search
        try:
            client = TestClient(studio.app)
            response = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "你好，项目里实际的大模型回复链路应该怎么接？",
                    "context": {
                        "mode": "workspace",
                        "model_name": "openai/mimo-v2.5",
                        "language": "zh",
                    },
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_llm = original_llm
            studio.call_research_chat_planner_llm = original_planner
            studio.paper_parse_store.rag_search = original_rag_search

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["state"] == "complete"
        result = payload["assistant_message"]["result"]
        assert result["status"] == "complete"
        assert result["groundingBoundary"] == "model_plus_knowledge_base"
        assert result["knowledgeHitCount"] >= 1
        assert "真实模型回答" in payload["assistant_message"]["text"]
        assert prompts
        assert "Research chat should call the backend model proxy" in prompts[0]
        assert "不要直接执行命令" in prompts[0]


def test_research_chat_elo_concept_uses_rag_llm_not_ranking_template() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        prompts: list[str] = []

        async def fake_call_research_chat_llm(**kwargs):
            prompts.append(kwargs["prompt"])
            return "Elo 是一种基于成对比较结果更新相对评分的排序方法。"

        original_has_key = studio.has_model_provider_key
        original_llm = studio.call_research_chat_llm
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = lambda model_name: True
        studio.call_research_chat_llm = fake_call_research_chat_llm
        studio.call_research_chat_planner_llm = planner_sequence(planner_json("ask_project_ai"))
        try:
            client = TestClient(studio.app)
            response = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "什么是elo?",
                    "context": {"mode": "project_help", "model_name": "openai/mimo-v2.5", "language": "zh"},
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_llm = original_llm
            studio.call_research_chat_planner_llm = original_planner

        assert response.status_code == 200, response.text
        payload = response.json()
        result = payload["assistant_message"]["result"]
        assert result["intent"] == "ask_project_ai"
        assert result["status"] == "complete"
        assert "Elo 是一种" in payload["assistant_message"]["text"]
        assert prompts
        assert "Elo and tournament ranking" in prompts[0]


def test_research_chat_read_only_run_and_report_are_modelized() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        record = studio.RunRecord(
            run_id="run_modelized_read_only",
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=studio.RunRequest(
                research_goal="Modelize read-only research chat answers",
                demo_mode=True,
                literature_review=False,
            ),
            hypotheses=[
                {
                    "id": "hyp_report_1",
                    "text": "Read-only branches should build structured context before model generation.",
                    "elo_rating": 1512.0,
                }
            ],
        )
        studio.persist_run_record(record)
        prompts: list[str] = []

        async def fake_call_research_chat_llm(**kwargs):
            prompts.append(kwargs["prompt"])
            return f"模型化只读回答 {len(prompts)}"

        original_has_key = studio.has_model_provider_key
        original_llm = studio.call_research_chat_llm
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = lambda model_name: True
        studio.call_research_chat_llm = fake_call_research_chat_llm
        studio.call_research_chat_planner_llm = planner_sequence(
            planner_json("explain_current_run"),
            planner_json("draft_report"),
        )
        try:
            client = TestClient(studio.app)
            run_response = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "解释当前运行",
                    "context": {"run_id": "run_modelized_read_only", "mode": "workspace", "language": "zh"},
                },
            )
            report_response = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "整理报告草稿",
                    "context": {"run_id": "run_modelized_read_only", "mode": "workspace", "language": "zh"},
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_llm = original_llm
            studio.call_research_chat_planner_llm = original_planner

        assert run_response.status_code == 200, run_response.text
        run_payload = run_response.json()
        assert run_payload["assistant_message"]["text"] == "模型化只读回答 1"
        run_result = run_payload["assistant_message"]["result"]
        assert run_result["intent"] == "explain_current_run"
        assert run_result["runId"] == "run_modelized_read_only"
        assert run_result["modelName"]

        assert report_response.status_code == 200, report_response.text
        report_payload = report_response.json()
        assert report_payload["assistant_message"]["text"] == "模型化只读回答 2"
        report_result = report_payload["assistant_message"]["result"]
        assert report_result["intent"] == "draft_report"
        assert "Candidate hypotheses and rationale" in report_result["sections"]
        assert prompts
        assert "Modelize read-only research chat answers" in prompts[0]
        assert "Candidate hypotheses and rationale" in prompts[1]


def test_research_chat_greeting_without_model_does_not_route_to_tool_picker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        original_has_key = studio.has_model_provider_key
        studio.has_model_provider_key = lambda model_name: False
        try:
            client = TestClient(studio.app)
            response = client.post(
                "/api/research-chat/turn",
                json={"message": "你好？", "context": {"mode": "workspace", "language": "zh"}},
            )
        finally:
            studio.has_model_provider_key = original_has_key

        assert response.status_code == 200, response.text
        payload = response.json()
        text = payload["assistant_message"]["text"]
        result = payload["assistant_message"]["result"]
        assert payload["state"] == "needs_input"
        assert result["status"] == "model_missing"
        assert result["plannerStatus"] == "model_missing"
        assert result["routingSource"] == "fallback_error"
        assert "模型规划器不可用" in result["title"]
        assert "模型 planner" in text
        assert "解析 PDF、抓取网页、搜索知识库，还是检查假设支撑" not in text


def test_research_chat_explicit_web_search_without_planner_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        original_has_key = studio.has_model_provider_key
        studio.has_model_provider_key = lambda model_name: False
        try:
            client = TestClient(studio.app)
            response = client.post(
                "/api/research-chat/turn",
                json={"message": "联网搜索：open-coscientist github", "context": {"mode": "workspace", "language": "zh"}},
            )
        finally:
            studio.has_model_provider_key = original_has_key

        assert response.status_code == 200, response.text
        payload = response.json()
        assistant = payload["assistant_message"]
        assert payload["state"] == "needs_input"
        assert "proposal" not in assistant
        result = assistant["result"]
        assert result["status"] == "model_missing"
        assert result["routingSource"] == "fallback_error"


def test_research_chat_invalid_planner_schema_does_not_propose_tool() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        original_has_key = studio.has_model_provider_key
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = lambda model_name: True
        studio.call_research_chat_planner_llm = planner_sequence(
            json.dumps(
                {
                    "intent": "search_public_web",
                    "capability_id": "runtime.terminal_command",
                    "executionMode": "approval_required",
                    "inputs": {"query": "open-coscientist github"},
                    "missingInputs": [],
                    "confidence": 0.9,
                    "groundingBoundary": "public_web_search",
                    "requiresConfirmation": True,
                    "answerStrategy": "bad schema should be rejected",
                },
                ensure_ascii=False,
            )
        )
        try:
            client = TestClient(studio.app)
            response = client.post(
                "/api/research-chat/turn",
                json={"message": "联网搜索：open-coscientist github", "context": {"mode": "workspace", "language": "zh"}},
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_planner_llm = original_planner

        assert response.status_code == 200, response.text
        payload = response.json()
        assistant = payload["assistant_message"]
        assert payload["state"] == "error"
        assert "proposal" not in assistant
        result = assistant["result"]
        assert result["status"] == "planner_error"
        assert result["routingSource"] == "fallback_error"


def test_research_goal_prefix_routes_to_start_run_confirmation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        client = TestClient(studio.app)
        original_has_key = studio.has_model_provider_key
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = lambda model_name: True
        studio.call_research_chat_planner_llm = planner_sequence(
            planner_json(
                "start_research_run",
                execution_mode="approval_required",
                grounding_boundary="live_model_workflow",
                inputs={"research_goal": "为 VLA 模型在长时序机器人任务中的泛化失败生成可证伪假设"},
            )
        )

        try:
            response = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "研究目标：为 VLA 模型在长时序机器人任务中的泛化失败生成可证伪假设",
                    "context": {
                        "mode": "workspace",
                        "demo_mode": True,
                        "literature_review": False,
                        "language": "zh",
                    },
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_planner_llm = original_planner
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["state"] == "awaiting_confirmation"
        proposal = payload["assistant_message"]["proposal"]
        assert proposal["intent"] == "start_research_run"
        assert proposal["executionTarget"] == "workflow.start_run"


def test_hypothesis_planning_advice_does_not_trigger_conditional_web_search() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        client = TestClient(studio.app)
        prompts: list[str] = []

        def fake_has_model_provider_key(model_name: str) -> bool:
            return model_name == "openai/mimo-v2.5"

        async def fake_call_research_chat_llm(**kwargs):
            prompts.append(kwargs["prompt"])
            return "当前没有绑定具体运行；应先补充研究目标约束、已有 PDF/fulltext 证据和失败条件，然后再启动 literature-grounded workflow。"

        original_has_key = studio.has_model_provider_key
        original_llm = studio.call_research_chat_llm
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = fake_has_model_provider_key
        studio.call_research_chat_llm = fake_call_research_chat_llm
        studio.call_research_chat_planner_llm = planner_sequence(planner_json("ask_project_ai"))
        try:
            response = client.post(
                "/api/research-chat/turn",
                json={
                    "message": (
                        "我想基于当前项目和最近对话生成候选假设。请告诉我现在最应该补充哪些证据、"
                        "研究目标还缺哪些约束，以及下一步应启动哪种 workflow。请基于下面的当前对话上下文回答，"
                        "不要只给通用说明；如果下一步需要解析 PDF、联网搜索或调用外部文献服务，请先返回确认卡或明确说明需要我确认。"
                        " - 当前页面: /project-chat - 当前没有绑定具体运行"
                    ),
                    "context": {"mode": "project_help", "model_name": "openai/mimo-v2.5", "language": "zh"},
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_llm = original_llm
            studio.call_research_chat_planner_llm = original_planner

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["state"] == "complete"
        assistant = payload["assistant_message"]
        assert "proposal" not in assistant
        result = assistant["result"]
        assert result["intent"] == "ask_project_ai"
        assert result["modelName"] == "openai/mimo-v2.5"
        assert "当前没有绑定具体运行" in assistant["text"]
        assert prompts
        assert "intent: ask_project_ai" in prompts[0]


def test_research_chat_can_propose_and_confirm_command_workflows() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        studio = load_studio(tmp)
        studio.ssh_training_status = lambda: {
            "available": True,
            "mode": "test_ready",
            "reason": "test ssh ready",
            "checked_at": 1.0,
        }
        studio.run_ssh_training_command = lambda **kwargs: FakeSshChatResult()
        studio.search_public_web = lambda *args, **kwargs: FakeWebSearchChatResult()
        original_has_key = studio.has_model_provider_key
        original_llm = studio.call_research_chat_llm
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = lambda model_name: True
        studio.call_research_chat_llm = lambda **kwargs: asyncio.sleep(0, result="fake synthesized answer")
        studio.call_research_chat_planner_llm = planner_sequence(
            planner_json("run_terminal_command", execution_mode="approval_required", grounding_boundary="local_terminal_audit", inputs={"command": "echo chat_terminal_ok"}),
            planner_json("run_ssh_training_command", execution_mode="approval_required", grounding_boundary="remote_ssh_audit", inputs={"server_id": "c201-5080", "command": "hostname"}),
            planner_json("run_terminal_command", execution_mode="approval_required", grounding_boundary="local_terminal_audit", inputs={"command": "ssh some-new-host hostname"}),
            planner_json("search_public_web", execution_mode="approval_required", grounding_boundary="public_web_search", inputs={"query": "open-coscientist github"}),
        )
        client = TestClient(studio.app)

        try:
            terminal_turn = client.post(
                "/api/research-chat/turn",
                json={"message": "执行本地命令：echo chat_terminal_ok", "context": {"mode": "workspace", "language": "zh"}},
            )
            assert terminal_turn.status_code == 200, terminal_turn.text
            terminal_proposal = terminal_turn.json()["assistant_message"]["proposal"]
            assert terminal_proposal["intent"] == "run_terminal_command"
            assert terminal_proposal["approvalScope"] == "terminal.command"
            assert terminal_proposal["executionTarget"] == "workflow.terminal_command"

            terminal_confirmed = client.post(
                f"/api/research-chat/actions/{terminal_proposal['actionId']}/confirm",
                json={"approval": {"confirmed": True, "scope": "terminal.command", "reason": "test terminal command"}},
            )
            assert terminal_confirmed.status_code == 200, terminal_confirmed.text
            terminal_result = terminal_confirmed.json()["assistant_message"]["result"]
            assert terminal_result["intent"] == "run_terminal_command"
            assert terminal_result["jobId"]
            terminal_job = client.get(f"/api/tools/background-jobs/{terminal_result['jobId']}")
            assert terminal_job.status_code == 200
            assert terminal_job.json()["status"] == "complete"

            ssh_turn = client.post(
                "/api/research-chat/turn",
                json={"message": "在 c201-5080 执行命令：hostname", "context": {"mode": "workspace", "language": "zh"}},
            )
            assert ssh_turn.status_code == 200, ssh_turn.text
            ssh_proposal = ssh_turn.json()["assistant_message"]["proposal"]
            assert ssh_proposal["intent"] == "run_ssh_training_command"
            assert ssh_proposal["approvalScope"] == "ssh.training_command"
            assert ssh_proposal["executionTarget"] == "workflow.ssh_training_command"

            ssh_confirmed = client.post(
                f"/api/research-chat/actions/{ssh_proposal['actionId']}/confirm",
                json={"approval": {"confirmed": True, "scope": "ssh.training_command", "reason": "test ssh command"}},
            )
            assert ssh_confirmed.status_code == 200, ssh_confirmed.text
            ssh_result = ssh_confirmed.json()["assistant_message"]["result"]
            assert ssh_result["intent"] == "run_ssh_training_command"
            assert ssh_result["serverId"] == "c201-5080"
            assert ssh_result["jobId"]

            arbitrary_ssh_turn = client.post(
                "/api/research-chat/turn",
                json={"message": "执行本地命令：ssh some-new-host hostname", "context": {"mode": "workspace", "language": "zh"}},
            )
            assert arbitrary_ssh_turn.status_code == 200, arbitrary_ssh_turn.text
            arbitrary_ssh_proposal = arbitrary_ssh_turn.json()["assistant_message"]["proposal"]
            assert arbitrary_ssh_proposal["intent"] == "run_terminal_command"
            assert arbitrary_ssh_proposal["approvalScope"] == "terminal.command"
            assert arbitrary_ssh_proposal["requestPreview"]["command"] == "ssh some-new-host hostname"

            web_turn = client.post(
                "/api/research-chat/turn",
                json={"message": "联网搜索：open-coscientist github", "context": {"mode": "workspace", "language": "zh"}},
            )
            assert web_turn.status_code == 200, web_turn.text
            web_proposal = web_turn.json()["assistant_message"]["proposal"]
            assert web_proposal["intent"] == "search_public_web"
            assert web_proposal["approvalScope"] == "web.search_public"
            assert web_proposal["executionTarget"] == "workflow.web_search"

            web_confirmed = client.post(
                f"/api/research-chat/actions/{web_proposal['actionId']}/confirm",
                json={"approval": {"confirmed": True, "scope": "web.search_public", "reason": "test public search"}},
            )
            assert web_confirmed.status_code == 200, web_confirmed.text
            web_result = web_confirmed.json()["assistant_message"]["result"]
            assert web_result["intent"] == "search_public_web"
            assert web_result["resultCount"] == 1
            assert web_result["items"][0]["url"] == "https://example.org/open-coscientist"
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_llm = original_llm
            studio.call_research_chat_planner_llm = original_planner


def test_literature_capability_uses_registered_mcp_tool() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        studio.probe_mcp_server = lambda: {
            "available": True,
            "mode": "reachable",
            "reason": "test MCP reachable",
            "checked_at": 1.0,
        }
        client = TestClient(studio.app)

        capabilities = client.get("/api/research-chat/capabilities")
        assert capabilities.status_code == 200, capabilities.text
        literature = next(
            item
            for item in capabilities.json()["capabilities"]
            if item["intent"] == "verify_evidence_with_literature"
        )
        assert literature["availability"]["available"] is True
        assert literature["availability"]["summary"] == "test MCP reachable"


def test_hypothesis_correctness_routes_to_public_literature_verification() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        client = TestClient(studio.app)
        original_has_key = studio.has_model_provider_key
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = lambda model_name: True
        studio.call_research_chat_planner_llm = planner_sequence(
            planner_json(
                "verify_evidence_with_literature",
                execution_mode="approval_required",
                grounding_boundary="literature_mcp_audit",
                inputs={"hypothesis_text": "VLA token 序列可以通过层级动作语法稳定转换为机器臂可执行动作"},
            )
        )

        try:
            response = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "检验这个假设是否正确：VLA token 序列可以通过层级动作语法稳定转换为机器臂可执行动作",
                    "context": {
                        "mode": "workspace",
                        "language": "zh",
                    },
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_planner_llm = original_planner
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["state"] == "awaiting_confirmation"
        proposal = payload["assistant_message"]["proposal"]
        assert proposal["intent"] == "verify_evidence_with_literature"
        assert proposal["approvalScope"] == "mcp.literature_review"
        assert proposal["executionTarget"] == "workflow.evidence_literature_verification"
        assert "PubMed" in " ".join(proposal["operationSummary"])
        assert "arXiv" in " ".join(proposal["operationSummary"])
        assert "Google Scholar" in " ".join(proposal["operationSummary"])


def test_literature_verification_uses_public_validation_sources() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        calls = []

        async def fake_mcp_workflow(request):
            calls.append(
                {
                    "workflow_name": request.workflow_name,
                    "tool_id": request.tool_id,
                    "arguments": request.arguments,
                }
            )
            return {
                "mcp_tool_name": request.tool_id,
                "result_preview": f"{request.tool_id} candidate negative result",
                "result_size": 128,
                "result_ref": {"result_id": f"result_{request.tool_id}"},
            }

        studio.execute_mcp_tool_workflow = fake_mcp_workflow

        payload = asyncio.run(
            studio.execute_evidence_literature_verification_workflow(
                studio.EvidenceVerificationWorkflowRequest(
                    hypothesis_text="VLA token sequences can be deterministically converted into executable robot actions.",
                    max_papers=3,
                    approval=studio.ToolWorkflowApproval(
                        confirmed=True,
                        scope="mcp.literature_review",
                        reason="test",
                    ),
                )
            )
        )

        assert [item["tool_id"] for item in calls] == [
            "pubmed_fulltext",
            "arxiv_search",
            "google_scholar_search",
        ]
        assert all(item["workflow_name"] == "validation" for item in calls)
        assert calls[0]["arguments"]["slug"]
        assert calls[1]["arguments"]["max_results"] == 3
        report = payload["verification_report"]
        statuses = report["externalCheck"]["sourceStatuses"]
        assert [item["toolId"] for item in statuses] == [
            "pubmed_fulltext",
            "arxiv_search",
            "google_scholar_search",
        ]
        assert report["externalCheck"]["status"] == "complete"


def test_literature_discovery_search_engine_can_query_all_public_sources() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        calls = []

        class FakeMcpClient:
            async def call_tool(self, mcp_tool_name, **arguments):
                calls.append({"mcp_tool_name": mcp_tool_name, "arguments": arguments})
                source = {
                    "pubmed_search_with_fulltext": "pubmed",
                    "search_arxiv": "arxiv",
                    "search_google_scholar": "google_scholar",
                }[mcp_tool_name]
                return {
                    "results": [
                        {
                            "title": f"{source} VLA action token paper",
                            "url": f"https://example.org/{source}",
                            "pdf_url": f"https://example.org/{source}.pdf" if source == "arxiv" else None,
                            "abstract": "Candidate literature search result.",
                            "source_id": f"{source}_1",
                            "source": source,
                            "year": 2026,
                        }
                    ]
                }

        async def fake_get_client(tool_registry):
            return FakeMcpClient()

        studio.get_policy_limited_mcp_client = fake_get_client
        studio.probe_mcp_server = lambda: {
            "available": True,
            "mode": "reachable",
            "reason": "test MCP reachable",
            "checked_at": 1.0,
        }
        client = TestClient(studio.app)

        response = client.post(
            "/api/literature-libraries/discover",
            json={
                "query": "VLA token sequence executable robot action",
                "library_id": "library_default",
                "preferred_source": "all",
                "max_results": 6,
                "approval": {
                    "confirmed": True,
                    "scope": "mcp.literature_review",
                    "reason": "test search engine",
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert [item["mcp_tool_name"] for item in calls] == [
            "pubmed_search_with_fulltext",
            "search_arxiv",
            "search_google_scholar",
        ]
        assert payload["status"] == "ready"
        assert len(payload["candidates"]) == 3
        assert {item["tool_id"] for item in payload["source_statuses"]} == {
            "pubmed_fulltext",
            "arxiv_search",
            "google_scholar_search",
        }


def test_stale_running_runs_are_marked_failed_in_history() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        record = studio.RunRecord(
            run_id="stale_running",
            status="running",
            created_at=1.0,
            updated_at=1.0,
            request=studio.RunRequest(
                research_goal="Stale run should not block the home priority panel",
                demo_mode=False,
                literature_review=True,
            ),
        )
        studio.persist_run_record(record)
        studio.persist_run_record(
            studio.RunRecord(
                run_id="latest_empty_run",
                status="complete",
                created_at=3.0,
                updated_at=4.0,
                request=studio.RunRequest(
                    research_goal="A newer empty run should not hide useful hypothesis history",
                    demo_mode=True,
                    literature_review=False,
                ),
                hypotheses=[],
            )
        )
        client = TestClient(studio.app)

        history = client.get("/api/runs")
        assert history.status_code == 200, history.text
        stale = next(item for item in history.json()["runs"] if item["run_id"] == "stale_running")
        assert stale["status"] == "error"
        assert "timeout window" in stale["error"]


def test_research_chat_pdf_proposal_and_ranking_regression() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        record = studio.RunRecord(
            run_id="run_chat_ranking",
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=studio.RunRequest(
                research_goal="Audit complete tournament ranking details",
                demo_mode=True,
                literature_review=False,
            ),
            hypotheses=[
                {
                    "id": "hyp_1",
                    "text": "Hypothesis one wins because it is more falsifiable.",
                    "elo_rating": 1532.0,
                    "score": 0.81,
                },
                {
                    "id": "hyp_2",
                    "text": "Hypothesis two has weaker validation details.",
                    "elo_rating": 1468.0,
                    "score": 0.67,
                },
            ],
            tournament_matchups=[
                {
                    "matchup_id": "match_1",
                    "winner_id": "hyp_1",
                    "loser_id": "hyp_2",
                    "confidence": 0.76,
                    "elo_before": {"hyp_1": 1500.0, "hyp_2": 1500.0},
                    "elo_after": {"hyp_1": 1532.0, "hyp_2": 1468.0},
                    "elo_delta": {"hyp_1": 32.0, "hyp_2": -32.0},
                    "reasoning": "hyp_1 includes clearer falsification criteria.",
                    "comparison_mode": "pairwise_debate",
                }
            ],
        )
        studio.persist_run_record(record)
        prompts: list[str] = []

        async def fake_call_research_chat_llm(**kwargs):
            prompts.append(kwargs["prompt"])
            return "模型化回答：这次 Elo 排名来自真实 tournament matchups。"

        original_has_key = studio.has_model_provider_key
        original_llm = studio.call_research_chat_llm
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = lambda model_name: True
        studio.call_research_chat_llm = fake_call_research_chat_llm
        studio.call_research_chat_planner_llm = planner_sequence(planner_json("explain_ranking"))
        client = TestClient(studio.app)
        try:
            ranking = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "解释当前 Elo 锦标赛排名，展示 winner/loser、confidence、before/after Elo",
                    "context": {"run_id": "run_chat_ranking", "mode": "workspace", "language": "zh"},
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_llm = original_llm
            studio.call_research_chat_planner_llm = original_planner
        assert ranking.status_code == 200, ranking.text
        payload = ranking.json()
        assert "模型化回答" in payload["assistant_message"]["text"]
        result = payload["assistant_message"]["result"]
        assert result["intent"] == "explain_ranking"
        assert result["status"] == "complete"
        assert result["tournamentCount"] == 1
        matchup = result["tournamentMatchups"][0]
        assert matchup["winner"] == "hyp_1"
        assert matchup["loser"] == "hyp_2"
        assert matchup["confidence"] == 0.76
        assert matchup["beforeElo"]["hyp_1"] == 1500.0
        assert matchup["afterElo"]["hyp_1"] == 1532.0
        assert matchup["eloDelta"]["hyp_2"] == -32.0
        assert result["groundingBoundary"] == "model_plus_knowledge_base"
        assert prompts
        assert "hyp_1 includes clearer falsification criteria" in prompts[0]

        original_has_key = studio.has_model_provider_key
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = lambda model_name: True
        studio.call_research_chat_planner_llm = planner_sequence(
            planner_json(
                "parse_pdf_to_knowledge_base",
                execution_mode="approval_required",
                grounding_boundary="parsed_pdf_fulltext",
                inputs={"pdf_path": r"D:\papers\paper.pdf"},
            )
        )
        try:
            proposed_pdf = client.post(
                "/api/research-chat/turn",
                json={"message": r"帮我解析 D:\papers\paper.pdf 并加入知识库", "context": {"language": "zh"}},
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_planner_llm = original_planner
        assert proposed_pdf.status_code == 200, proposed_pdf.text
        pdf_proposal = proposed_pdf.json()["assistant_message"]["proposal"]
        assert pdf_proposal["approvalScope"] == "pdf.parse_to_knowledge_base"
        assert pdf_proposal["executionTarget"] == "workflow.pdf_parse"


def test_research_chat_explains_existing_hypothesis_list_without_starting_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        record = studio.RunRecord(
            run_id="run_three_hypotheses",
            status="complete",
            created_at=1.0,
            updated_at=2.0,
            request=studio.RunRequest(
                research_goal="Explore VLA token-to-action conversion mechanisms",
                demo_mode=False,
                literature_review=False,
            ),
            hypotheses=[
                {
                    "id": "hyp_1",
                    "text": "A hierarchical action grammar can map VLA tokens to executable robot primitives.",
                    "plain_explanation": "把 token 先归纳成动作语法，再落到机器人原语。",
                    "validation_plan": "Compare execution success against a flat token decoder.",
                    "elo_rating": 1540.0,
                },
                {
                    "id": "hyp_2",
                    "text": "Temporal chunking reduces compounding control errors in long-horizon VLA tasks.",
                    "plain_explanation": "把长任务切段能减少误差累积。",
                    "validation_plan": "Ablate chunk size and measure completion rate.",
                    "elo_rating": 1510.0,
                },
                {
                    "id": "hyp_3",
                    "text": "Failure recovery tokens act as latent checkpoints for robust manipulation.",
                    "plain_explanation": "恢复 token 可以像检查点一样帮助纠错。",
                    "validation_plan": "Inject perturbations and compare recovery success.",
                    "elo_rating": 1480.0,
                },
            ],
        )
        studio.persist_run_record(record)
        prompts: list[str] = []

        async def fake_call_research_chat_llm(**kwargs):
            prompts.append(kwargs["prompt"])
            return "模型化回答：这三个候选假设分别对应动作语法、时序分块和恢复 checkpoint。"

        original_has_key = studio.has_model_provider_key
        original_llm = studio.call_research_chat_llm
        original_planner = studio.call_research_chat_planner_llm
        studio.has_model_provider_key = lambda model_name: True
        studio.call_research_chat_llm = fake_call_research_chat_llm
        studio.call_research_chat_planner_llm = planner_sequence(
            planner_json("inspect_hypothesis", inputs={"list_all": True})
        )
        client = TestClient(studio.app)
        try:
            response = client.post(
                "/api/research-chat/turn",
                json={
                    "message": "帮我解释一下这3个候选假设是什么可以吗？",
                    "context": {"mode": "project_help", "language": "zh"},
                },
            )
        finally:
            studio.has_model_provider_key = original_has_key
            studio.call_research_chat_llm = original_llm
            studio.call_research_chat_planner_llm = original_planner

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["state"] == "complete"
        assistant = payload["assistant_message"]
        assert "proposal" not in assistant
        assert "模型化回答" in assistant["text"]
        result = assistant["result"]
        assert result["intent"] == "inspect_hypothesis"
        assert result["runId"] == "run_three_hypotheses"
        assert result["hypothesisCount"] == 3
        assert len(result["hypotheses"]) == 3
        assert result["hypotheses"][0]["title"].startswith("A hierarchical action grammar")
        assert prompts
        assert "Temporal chunking reduces compounding control errors" in prompts[0]


if __name__ == "__main__":
    test_research_chat_capabilities_sessions_and_start_run()
    test_research_chat_pdf_proposal_and_ranking_regression()
    print("research chat workbench tests passed")
