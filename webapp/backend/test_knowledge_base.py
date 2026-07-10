from __future__ import annotations

import tempfile
import os
from pathlib import Path

from knowledge_base import KnowledgeBaseStore, hierarchical_chunk_paper, PaperDocument


SAMPLE_PAPER = """# Abstract

We evaluate adaptive retrieval for hypothesis generation on a 120-paper corpus.

## Introduction

Fixed windows can split methods from results and make evidence provenance weak.

## Methods

The study uses a controlled benchmark with n=48 expert-scored hypotheses and a baseline retriever.

### Experiment Setup

We compare semantic section chunks against 1,000-character fixed chunks on the same corpus.

## Results

Table 1 reports accuracy 0.82 versus 0.71 for the fixed baseline, with p<0.05 in paired evaluation.

## Discussion

The result suggests that preserving section hierarchy improves review-time evidence tracing.
"""


def test_hierarchical_chunking_is_not_fixed_length() -> None:
    paper = PaperDocument(
        paper_id="paper_test",
        title="Adaptive knowledge chunking",
        abstract="A benchmark with n=48 shows section-aware retrieval improves evidence traceability.",
        content=SAMPLE_PAPER,
    )
    chunks = hierarchical_chunk_paper(paper)
    lengths = {len(chunk.text) for chunk in chunks}
    section_types = {chunk.section_type for chunk in chunks}

    assert len(chunks) >= 5
    assert len(lengths) > 2
    assert {"abstract", "methods", "experiments", "results"}.issubset(section_types)
    assert any(chunk.experiment_data_summary for chunk in chunks)


def test_ingest_search_and_hypothesis_support() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        paper = store.ingest(
            title="Adaptive knowledge chunking",
            content=SAMPLE_PAPER,
            abstract="A benchmark with n=48 shows section-aware retrieval improves evidence traceability.",
            source="user_upload",
        )

        assert paper.paper_id
        assert len(store.list_documents()) == 1

        search_results = store.search_chunks("section hierarchy accuracy fixed baseline", limit=4)
        assert search_results
        assert any(result["section_type"] == "results" for result in search_results)

        support = store.support_for_hypothesis(
            {
                "text": "Semantic section chunks improve hypothesis evidence tracing over fixed windows.",
                "experiment": "Compare against fixed baseline using accuracy and expert-scored hypotheses.",
            }
        )
        assert support
        assert any(item["experiment_data_summary"] for item in support)


def test_literature_libraries_scope_documents_and_rag_search() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        vla_library = store.create_library(name="VLA 入门")
        bio_library = store.create_library(name="生物医学")

        vla_paper = store.ingest(
            title="Open VLA Robot Policies",
            content="# Abstract\n\nVision language action models transfer robot policies across embodiments.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
            library_id=vla_library["library_id"],
        )
        bio_paper = store.ingest(
            title="Cancer Biomarker Study",
            content="# Abstract\n\nClinical biomarker cohorts evaluate response in patients.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
            library_id=bio_library["library_id"],
        )

        store.record_parse_run(
            parse_run_id="parse_vla",
            paper_id=vla_paper.paper_id,
            library_id=vla_library["library_id"],
            title=vla_paper.title,
            status="success",
            input_kind="local_path",
            input_path="vla.pdf",
            pdf_path="vla.pdf",
            solve_dir="solve",
            page_count=4,
            chunks_count=len(vla_paper.chunks),
            experimental_chunks_count=0,
            knowledge_base_ingested=True,
            rag_search_ready=True,
            items=[],
            evidence=[],
        )

        assert len(store.list_documents(library_id=vla_library["library_id"])) == 1
        assert len(store.list_documents(library_id=bio_library["library_id"])) == 1
        assert store.list_documents(library_id=vla_library["library_id"])[0].paper_id == vla_paper.paper_id
        assert store.list_parse_runs(library_id=vla_library["library_id"])[0]["library_id"] == vla_library["library_id"]

        vla_results = store.rag_search("robot policies embodiments", library_id=vla_library["library_id"])
        bio_results = store.rag_search("robot policies embodiments", library_id=bio_library["library_id"])
        assert vla_results
        assert vla_results[0]["paper_id"] == vla_paper.paper_id
        assert not any(result["paper_id"] == bio_paper.paper_id for result in vla_results)
        assert bio_results == []


def test_parse_run_evidence_is_rag_searchable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        parse_run_id = "parse_test"
        paper = store.ingest(
            title="Adaptive knowledge chunking",
            content=SAMPLE_PAPER,
            abstract="A benchmark with n=48 shows section-aware retrieval improves evidence traceability.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
            metadata={"parse_run_id": parse_run_id},
        )
        first_chunk = paper.chunks[0]
        store.record_parse_run(
            parse_run_id=parse_run_id,
            paper_id=paper.paper_id,
            title=paper.title,
            status="success",
            input_kind="local_path",
            input_path="paper.pdf",
            pdf_path="paper.pdf",
            solve_dir="solve",
            page_count=8,
            chunks_count=len(paper.chunks),
            experimental_chunks_count=sum(1 for chunk in paper.chunks if chunk.experiment_data_summary),
            knowledge_base_ingested=True,
            rag_search_ready=True,
            items=[
                {
                    "item_key": "rag_search_ready",
                    "label": "RAG 检索已就绪",
                    "status": "success",
                    "evidence_type": "rag",
                    "evidence_summary": "后续候选假设可通过知识库检索调用这些证据。",
                    "evidence_id": first_chunk.evidence_id,
                    "completed_at": 1.0,
                }
            ],
            evidence=[
                {
                    "evidence_id": first_chunk.evidence_id,
                    "paper_id": paper.paper_id,
                    "item_key": "rag_search_ready",
                    "evidence_type": "chunk",
                    "label": first_chunk.title,
                    "chunk_id": first_chunk.chunk_id,
                    "section_path": first_chunk.section_path,
                    "text_preview": first_chunk.text[:500],
                    "metadata": {"support_level": first_chunk.support_level},
                }
            ],
        )

        parse_runs = store.list_parse_runs()
        assert parse_runs[0]["parse_run_id"] == parse_run_id
        parse_run = store.get_parse_run(parse_run_id)
        assert parse_run
        assert parse_run["items"][0]["evidence"]["evidence_id"] == first_chunk.evidence_id

        support = store.support_for_hypothesis({"text": "section hierarchy evidence tracing"})
        assert support
        assert support[0]["parse_run_id"] == parse_run_id
        assert support[0]["evidence_id"]


def test_ragflow_hash_embedding_reindex_and_hybrid_search() -> None:
    old_env = {
        key: os.environ.get(key)
        for key in (
            "COSCIENTIST_RAG_EMBEDDING_PROVIDER",
            "COSCIENTIST_RAG_EMBEDDING_MODEL",
            "COSCIENTIST_RAG_VECTOR_WEIGHT",
        )
    }
    os.environ["COSCIENTIST_RAG_EMBEDDING_PROVIDER"] = "hash"
    os.environ["COSCIENTIST_RAG_EMBEDDING_MODEL"] = "hash-test"
    os.environ["COSCIENTIST_RAG_VECTOR_WEIGHT"] = "0.5"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            store = KnowledgeBaseStore(Path(tmp))
            paper = store.ingest(
                title="Adaptive knowledge chunking",
                content=SAMPLE_PAPER,
                abstract="A benchmark with n=48 shows section-aware retrieval improves evidence traceability.",
                source="local_pdf",
                source_reliability="parsed_fulltext",
            )
            status = store.ragflow_status()
            assert status["embedding"]["enabled"] is True
            assert status["embedding"]["indexed_chunks"] == len(paper.chunks)

            results = store.rag_search("semantic section chunk baseline accuracy", limit=4)
            assert results
            assert any(result.get("vector_similarity") is not None for result in results)
            assert all(result.get("retrieval_method") for result in results)

            reindex = store.reindex_embeddings()
            assert reindex["status"] == "complete"
            assert reindex["ragflow"]["embedding"]["indexed_chunks"] == len(paper.chunks)
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_research_run_provenance_is_persisted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        paper = store.ingest(
            title="Adaptive knowledge chunking",
            content=SAMPLE_PAPER,
            abstract="A benchmark with n=48 shows section-aware retrieval improves evidence traceability.",
            source="local_pdf",
            source_reliability="parsed_fulltext",
        )
        support = store.support_for_hypothesis(
            {
                "text": "Semantic section chunks improve hypothesis evidence tracing over fixed windows.",
                "experiment": "Compare section-aware retrieval with a fixed baseline.",
            }
        )
        assert support

        run_record = {
            "run_id": "run_test",
            "status": "complete",
            "created_at": 1.0,
            "updated_at": 2.0,
            "request": {"research_goal": "Test durable evidence provenance", "demo_mode": True},
            "timeline": [
                {
                    "time": "12:00:00",
                    "stage": "Generate",
                    "event": "Hypothesis generated",
                    "details": "One hypothesis created",
                    "status": "complete",
                }
            ],
            "hypotheses": [
                {
                    "id": "HYP-001",
                    "text": "Semantic section chunks improve hypothesis evidence tracing over fixed windows.",
                    "experiment": "Compare section-aware retrieval with a fixed baseline.",
                    "grounding_status": "knowledge_base_supported",
                    "citation_map": {},
                    "knowledge_base_support": support,
                    "experimental_support_summaries": [
                        item for item in support if item.get("experiment_data_summary")
                    ],
                }
            ],
            "research_plan": {"strategy": "durable provenance smoke test"},
            "agent_trace": [
                {
                    "event_id": "trace-kb",
                    "agent": "Literature",
                    "role": "Evidence retriever",
                    "phase": "literature_grounding",
                    "status": "complete",
                    "output": "Retrieved supporting chunks",
                    "tool_calls": [{"tool": "knowledge_base.support_for_hypothesis", "status": "complete"}],
                    "token_usage": {},
                    "synthetic": False,
                    "confidence": 0.9,
                }
            ],
            "tournament_matchups": [],
            "metrics": {"hypothesis_count": 1},
            "safety_gate": {"status": "passed"},
            "citation_provenance_qa": {"status": "passed"},
            "expert_feedback": {},
            "error": None,
        }

        store.record_research_run(run_record)

        loaded = store.get_research_run("run_test")
        assert loaded
        assert loaded["run_id"] == "run_test"
        assert store.list_research_runs()[0]["run_id"] == "run_test"

        links = store.get_hypothesis_evidence_links("run_test")
        assert links
        assert links[0]["hypothesis_id"] == "HYP-001"
        assert links[0]["paper_id"] == paper.paper_id
        assert links[0]["evidence_id"]

        retrievals = store.get_evidence_retrievals("run_test")
        assert retrievals
        assert retrievals[0]["tool_name"] == "knowledge_base.support_for_hypothesis"
        assert retrievals[0]["result_count"] == len(support)

        store.record_research_tool_call(
            run_id="run_test",
            tool_name="knowledge_base.rag_search",
            phase="literature_review",
            status="complete",
            arguments={"query": "section hierarchy evidence tracing"},
            result_summary="knowledge_base.rag_search returned results.",
            metadata={"result_count": 1},
        )
        tool_calls = store.get_research_tool_calls("run_test")
        assert tool_calls
        assert tool_calls[-1]["tool_name"] == "knowledge_base.rag_search"
        assert tool_calls[-1]["metadata"]["result_count"] == 1

        result_ref = store.store_tool_result(
            run_id="run_test",
            tool_name="knowledge_base.rag_search",
            phase="literature_review",
            content=support,
            result_kind="evidence_results",
            summary="Stored support evidence.",
        )
        listed_results = store.list_tool_results("run_test")
        assert listed_results[0]["result_id"] == result_ref["result_id"]
        loaded_result = store.get_tool_result(result_ref["result_id"])
        assert loaded_result
        assert loaded_result["content"][0]["paper_id"] == paper.paper_id


def test_research_task_board_is_persisted_and_filterable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        task = store.create_research_task(
            task_id="task_parse_pdf",
            run_id="run_test",
            title="Parse supporting PDF",
            task_type="parse_pdf",
            status="ready",
            priority=1,
            phase="paper_reading",
            target_ref={"pdf_path": "paper.pdf"},
            notes="Parse fulltext before hypothesis review.",
        )
        assert task["task_id"] == "task_parse_pdf"
        assert task["target_ref"]["pdf_path"] == "paper.pdf"

        updated = store.update_research_task(
            "task_parse_pdf",
            status="done",
            result_ref={"parse_run_id": "parse_123"},
        )
        assert updated
        assert updated["status"] == "done"
        assert updated["result_ref"]["parse_run_id"] == "parse_123"

        tasks = store.list_research_tasks(run_id="run_test", status="done")
        assert len(tasks) == 1
        assert tasks[0]["task_type"] == "parse_pdf"


def test_research_schedule_is_persisted_and_filterable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        schedule = store.create_research_schedule(
            schedule_id="sched_literature_refresh",
            run_id="run_test",
            title="Refresh related literature",
            workflow_name="literature_refresh",
            interval_hours=24.0,
            phase="literature_review",
            arguments={"query": "weak supervision evidence"},
            next_run_at=1000.0,
        )
        assert schedule["schedule_id"] == "sched_literature_refresh"
        assert schedule["arguments"]["query"] == "weak supervision evidence"

        updated = store.update_research_schedule(
            "sched_literature_refresh",
            status="paused",
            result_ref={"background_job_id": "job_123"},
        )
        assert updated
        assert updated["status"] == "paused"
        assert updated["result_ref"]["background_job_id"] == "job_123"

        schedules = store.list_research_schedules(run_id="run_test", status="paused")
        assert len(schedules) == 1
        assert schedules[0]["workflow_name"] == "literature_refresh"


def test_session_search_finds_provenance_objects_without_large_payloads() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        run_record = {
            "run_id": "run_search",
            "status": "complete",
            "created_at": 1.0,
            "updated_at": 2.0,
            "request": {"research_goal": "Searchable weak supervision evidence audit", "demo_mode": True},
            "timeline": [],
            "hypotheses": [
                {
                    "id": "HYP-SEARCH",
                    "text": "Weak supervision evidence audit can find unsupported claims.",
                    "experiment": "Measure retrieval precision.",
                    "grounding_status": "knowledge_base_supported",
                    "citation_map": {},
                    "knowledge_base_support": [],
                }
            ],
            "research_plan": {"strategy": "session search test"},
            "agent_trace": [],
            "tournament_matchups": [],
            "metrics": {"hypothesis_count": 1},
            "safety_gate": {},
            "citation_provenance_qa": {},
            "expert_feedback": {},
            "error": None,
        }
        store.record_research_run(run_record)
        result_ref = store.store_tool_result(
            run_id="run_search",
            tool_name="browser.web_extract",
            phase="literature_review",
            content={"extracted_text": "weak supervision leaderboard evidence" * 50},
            result_kind="web_evidence_extract",
            summary="Captured weak supervision leaderboard evidence.",
        )
        store.create_research_task(
            task_id="task_search",
            run_id="run_search",
            title="Review weak supervision evidence",
            task_type="evidence_review",
            notes="Confirm support level before writing.",
        )
        store.create_research_schedule(
            schedule_id="sched_search",
            run_id="run_search",
            title="Refresh weak supervision citations",
            workflow_name="literature_refresh",
            interval_hours=24.0,
            arguments={"query": "weak supervision"},
            next_run_at=1000.0,
        )
        store.create_research_delegation(
            delegation_id="deleg_search",
            run_id="run_search",
            title="Parallel weak supervision critique",
            phase="review_critique",
            strategy="parallel_review",
            agents=[
                {
                    "role": "Contradiction Agent",
                    "brief": "Find weak supervision counter-evidence.",
                    "skill_ids": ["citation-provenance-qa"],
                }
            ],
            target_ref={"hypothesis_id": "HYP-SEARCH"},
        )

        results = store.search_research_sessions("weak supervision", run_id="run_search")
        result_types = {item["type"] for item in results}
        assert {"run", "hypothesis", "tool_result", "task", "schedule", "delegation"}.issubset(result_types)
        tool_result = next(item for item in results if item["type"] == "tool_result")
        assert tool_result["target_ref"]["result_id"] == result_ref["result_id"]
        assert "extracted_text" not in tool_result
        assert len(tool_result["snippet"]) < 260


def test_research_delegation_is_persisted_and_filterable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = KnowledgeBaseStore(Path(tmp))
        delegation = store.create_research_delegation(
            delegation_id="deleg_review",
            run_id="run_test",
            title="Parallel hypothesis review",
            phase="review_critique",
            strategy="parallel_review",
            agents=[
                {
                    "role": "Critique Agent",
                    "brief": "Review scientific soundness.",
                    "skill_ids": ["falsifiability-review"],
                },
                {
                    "role": "Evidence Agent",
                    "brief": "Check citation provenance.",
                    "skill_ids": ["citation-provenance-qa"],
                },
            ],
            target_ref={"hypothesis_id": "HYP-001"},
        )
        assert delegation["agents"][0]["role"] == "Critique Agent"

        updated = store.update_research_delegation(
            "deleg_review",
            status="completed",
            result_ref={"tool_result_id": "result_123"},
            summary="Two-agent review completed.",
        )
        assert updated
        assert updated["status"] == "completed"
        assert updated["result_ref"]["tool_result_id"] == "result_123"

        delegations = store.list_research_delegations(run_id="run_test", status="completed")
        assert len(delegations) == 1
        assert delegations[0]["strategy"] == "parallel_review"


if __name__ == "__main__":
    test_hierarchical_chunking_is_not_fixed_length()
    test_ingest_search_and_hypothesis_support()
    test_literature_libraries_scope_documents_and_rag_search()
    test_parse_run_evidence_is_rag_searchable()
    test_ragflow_hash_embedding_reindex_and_hybrid_search()
    test_research_run_provenance_is_persisted()
    test_research_task_board_is_persisted_and_filterable()
    test_research_schedule_is_persisted_and_filterable()
    test_session_search_finds_provenance_objects_without_large_payloads()
    test_research_delegation_is_persisted_and_filterable()
    print("knowledge_base tests passed")
