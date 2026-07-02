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


def test_run_real_passes_parent_memory_summary_constraints(monkeypatch) -> None:
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

        parent_request = studio.RunRequest(
            research_goal="Find parent memory mechanisms for durable research continuation",
            demo_mode=False,
            literature_review=False,
            initial_hypotheses=1,
            iterations=0,
            min_references=0,
            max_references=1,
        )
        parent_record = studio.RunRecord(
            run_id="parent-run-memory",
            status="complete",
            created_at=1.0,
            updated_at=1.0,
            request=parent_request,
            hypotheses=[
                {
                    "id": "hyp-parent-1",
                    "text": "Parent hypothesis should be reused as summarized context.",
                    "explanation": "The earlier run found a plausible continuation path.",
                    "support_level": "limited",
                }
            ],
            metrics={"summary": "Parent run favored falsifiable continuation hypotheses."},
        )
        studio.persist_run_record(parent_record)
        studio.knowledge_base.store_feedback_item(
            run_id="parent-run-memory",
            target_type="hypothesis",
            target_ref={"hypothesis_id": "hyp-parent-1"},
            feedback_type="prefer",
            text="Prefer hypotheses that keep evidence provenance explicit.",
            source="user",
        )

        request = studio.RunRequest(
            research_goal="Continue parent memory mechanisms with stricter provenance",
            demo_mode=False,
            literature_review=False,
            initial_hypotheses=1,
            iterations=0,
            min_references=0,
            max_references=1,
            parent_run_id="parent-run-memory",
        )
        record = studio.RunRecord(
            run_id="child-run-memory",
            status="queued",
            created_at=2.0,
            updated_at=2.0,
            request=request,
        )

        asyncio.run(studio.run_real(record))

    constraints = captured["generate_kwargs"]["opts"]["constraints"]
    joined_constraints = "\n".join(constraints)
    assert "[memory_parent_run]" in joined_constraints
    assert "Parent run favored falsifiable continuation hypotheses" in joined_constraints
    assert "[memory_prior_hypothesis]" in joined_constraints
    assert "Parent hypothesis should be reused" in joined_constraints
    assert "[memory_user_feedback]" in joined_constraints
    assert "Prefer hypotheses that keep evidence provenance explicit" in joined_constraints
    assert "[memory_usage_policy]" in joined_constraints
    assert "parent-run-memory" not in joined_constraints


def test_run_real_passes_current_request_feedback_constraints(monkeypatch) -> None:
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
            research_goal="Use current request feedback for continuation guidance",
            demo_mode=False,
            literature_review=False,
            initial_hypotheses=1,
            iterations=0,
            min_references=0,
            max_references=1,
            user_feedback=[
                studio.FeedbackItem(
                    target_type="hypothesis",
                    target_ref={"hypothesis_id": "raw-target-hidden"},
                    feedback_type="critique",
                    text="Revise toward hypotheses with stronger falsification tests.",
                )
            ],
        )
        record = studio.RunRecord(
            run_id="run-current-feedback",
            status="queued",
            created_at=1.0,
            updated_at=1.0,
            request=request,
        )

        asyncio.run(studio.run_real(record))

    constraints = captured["generate_kwargs"]["opts"]["constraints"]
    joined_constraints = "\n".join(constraints)
    assert "[user_feedback]" in joined_constraints
    assert "Revise toward hypotheses with stronger falsification tests" in joined_constraints
    assert "[user_feedback_policy]" in joined_constraints
    assert "immediate reversible edit" in joined_constraints
    assert "raw-target-hidden" not in joined_constraints


def test_run_real_annotates_hypothesis_origins(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    class FakeHypothesisGenerator:
        def __init__(self, **kwargs):
            pass

        async def generate_hypotheses(self, **kwargs):
            return {
                "hypotheses": [
                    {"id": "hyp_user", "text": "User seed hypothesis about provenance-aware ranking."},
                    {"id": "hyp_model", "text": "Model-only hypothesis about evidence triage."},
                    {
                        "id": "hyp_evolved",
                        "text": "Evolved hypothesis about feedback-guided validation.",
                        "generation_method": "evolved_from_review",
                    },
                ],
                "research_plan": {},
                "tournament_matchups": [],
                "metrics": {},
                "workflow_tool_policy": {},
            }

    with tempdir:
        import open_coscientist

        monkeypatch.setattr(open_coscientist, "HypothesisGenerator", FakeHypothesisGenerator)

        request = studio.RunRequest(
            research_goal="Annotate hypothesis origins for UI audit badges",
            demo_mode=False,
            literature_review=False,
            initial_hypotheses=3,
            iterations=0,
            min_references=0,
            max_references=1,
            starting_hypotheses=["User seed hypothesis about provenance-aware ranking."],
        )
        record = studio.RunRecord(
            run_id="run-origin-badges",
            status="queued",
            created_at=1.0,
            updated_at=1.0,
            request=request,
        )

        asyncio.run(studio.run_real(record))

    assert record.status == "complete"
    origins = {item["id"]: item["origin"] for item in record.hypotheses}
    assert origins == {
        "hyp_user": "user_seeded",
        "hyp_model": "model_generated",
        "hyp_evolved": "evolved",
    }
    assert record.hypotheses[0]["origin_label"] == "user seeded"
    assert record.metrics["hypothesis_origin_counts"] == {
        "user_seeded": 1,
        "model_generated": 1,
        "evolved": 1,
    }
    assert "not scientific evidence" in record.metrics["hypothesis_origin_boundary"]
