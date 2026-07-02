from __future__ import annotations

import importlib
import sys
import tempfile


def load_studio_app(monkeypatch, knowledge_base_dir: str):
    monkeypatch.setenv("COSCIENTIST_KNOWLEDGE_BASE_DIR", knowledge_base_dir)
    monkeypatch.setenv("COSCIENTIST_WORKER_ENABLED", "0")
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def make_record(studio):
    return studio.RunRecord(
        run_id="trace-run",
        status="complete",
        created_at=1.0,
        updated_at=1.0,
        request=studio.RunRequest(
            research_goal="Trace LangGraph phase metadata from live messages",
            demo_mode=False,
            literature_review=False,
        ),
    )


def test_live_agent_trace_reads_top_level_metadata(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        traces = studio.build_live_agent_trace(
            make_record(studio),
            {"messages": [{"content": "Supervisor planned the run.", "metadata": {"phase": "supervisor"}}]},
        )

    assert len(traces) == 1
    assert traces[0].phase == "supervisor"
    assert traces[0].agent == "Supervisor"
    assert traces[0].synthetic is False


def test_live_agent_trace_reads_additional_kwargs_metadata(monkeypatch) -> None:
    tempdir = tempfile.TemporaryDirectory()
    studio = load_studio_app(monkeypatch, tempdir.name)

    with tempdir:
        traces = studio.build_live_agent_trace(
            make_record(studio),
            {
                "messages": [
                    {
                        "content": "Ranking completed pairwise Elo comparisons.",
                        "additional_kwargs": {"metadata": {"phase": "ranking", "top_elo": 1280}},
                    }
                ]
            },
        )

    assert len(traces) == 1
    assert traces[0].phase == "ranking"
    assert traces[0].agent == "Ranking"
    assert "Elo" in traces[0].output
