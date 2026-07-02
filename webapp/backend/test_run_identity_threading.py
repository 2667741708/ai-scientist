from __future__ import annotations

import asyncio
import importlib
import sys
import tempfile


def load_studio_app(monkeypatch, knowledge_base_dir: str):
    monkeypatch.setenv("COSCIENTIST_KNOWLEDGE_BASE_DIR", knowledge_base_dir)
    monkeypatch.setenv("COSCIENTIST_WORKER_ENABLED", "0")
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def test_generator_run_config_uses_langgraph_thread_id(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        from open_coscientist.generator import HypothesisGenerator

        config = HypothesisGenerator._workflow_run_config("run-thread-123")
        assert config["recursion_limit"] == 100
        assert config["configurable"]["thread_id"] == "run-thread-123"


def test_run_real_passes_record_run_id_to_generator(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)
    captured: dict[str, object] = {}

    class FakeHypothesisGenerator:
        def __init__(self, **kwargs):
            captured["init_kwargs"] = kwargs

        async def generate_hypotheses(self, **kwargs):
            captured["generate_kwargs"] = kwargs
            return {
                "hypotheses": [],
                "research_plan": {},
                "tournament_matchups": [],
                "metrics": {},
                "workflow_tool_policy": {},
            }

    with tempdir:
        import open_coscientist

        monkeypatch.setattr(open_coscientist, "HypothesisGenerator", FakeHypothesisGenerator)

        request = studio.RunRequest(
            research_goal="Find falsifiable mechanisms for checkpoint thread identity",
            demo_mode=False,
            literature_review=False,
            initial_hypotheses=1,
            iterations=0,
            min_references=0,
            max_references=1,
        )
        record = studio.RunRecord(
            run_id="run-webapp-identity",
            status="queued",
            created_at=1.0,
            updated_at=1.0,
            request=request,
        )

        asyncio.run(studio.run_real(record))

    assert record.status == "complete"
    generate_kwargs = captured["generate_kwargs"]
    assert generate_kwargs["run_id"] == "run-webapp-identity"
    assert generate_kwargs["stream"] is False
    assert generate_kwargs["opts"]["enable_literature_review_node"] is False
    if record.metrics["execution_memory"]["langgraph_checkpoint_sqlite_available"]:
        assert generate_kwargs["opts"]["checkpointer"] is not None
    else:
        assert "checkpointer" not in generate_kwargs["opts"]
