from __future__ import annotations

import tempfile
import time
from pathlib import Path

from knowledge_base import KnowledgeBaseStore
from paper_parse_store import PaperParseEvidenceStore


def test_parse_store_records_status_and_rag_search() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = KnowledgeBaseStore(root)
        parse_run_id = "parse_test_001"
        paper = store.ingest(
            title="RAG evidence paper",
            content=(
                "# Abstract\nSemantic chunking supports RAG evidence retrieval.\n\n"
                "# Experiments\nA benchmark on CIFAR-10 reached accuracy 0.91 and AUC 0.88."
            ),
            source="local_pdf_interpretation",
            source_reliability="parsed_fulltext",
            metadata={"parse_run_id": parse_run_id},
        )
        items = [
            {
                "item_key": "pdf_accessible",
                "label": "PDF 可访问",
                "status": "success",
                "evidence_type": "file",
                "evidence_summary": "PDF opened",
                "evidence_id": "evidence_pdf_accessible",
                "completed_at": time.time(),
                "error_message": None,
            },
            {
                "item_key": "rag_indexed",
                "label": "RAG 索引入库",
                "status": "success",
                "evidence_type": "rag",
                "evidence_summary": "indexed chunks",
                "evidence_id": "evidence_rag_indexed",
                "completed_at": time.time(),
                "error_message": None,
            },
        ]
        evidence = [
            {
                "evidence_id": "evidence_rag_indexed",
                "parse_run_id": parse_run_id,
                "paper_id": paper.paper_id,
                "item_key": "rag_indexed",
                "evidence_type": "rag",
                "label": "RAG indexed",
                "file_path": None,
                "chunk_id": paper.chunks[0].chunk_id,
                "section_path": paper.chunks[0].section_path,
                "text_preview": paper.chunks[0].text[:200],
                "media_preview": None,
                "metadata": {"support_level": paper.chunks[0].support_level},
                "created_at": time.time(),
            }
        ]
        store.record_parse_run(
            parse_run_id=parse_run_id,
            paper_id=paper.paper_id,
            title=paper.title,
            status="success",
            input_kind="local_path",
            input_path="paper.pdf",
            pdf_path="paper.pdf",
            solve_dir=str(root),
            page_count=1,
            chunks_count=len(paper.chunks),
            experimental_chunks_count=sum(1 for chunk in paper.chunks if chunk.experiment_data_summary),
            knowledge_base_ingested=True,
            rag_search_ready=True,
            items=items,
            evidence=evidence,
        )

        facade = PaperParseEvidenceStore(root)
        status = facade.get_parse_status(paper.paper_id)
        assert status is not None
        assert status["paper_id"] == paper.paper_id
        assert {item["item_key"] for item in status["items"]} == {"pdf_accessible", "rag_indexed"}

        results = facade.rag_search("CIFAR-10 accuracy", paper_id=paper.paper_id)
        assert results
        assert results[0]["paper_id"] == paper.paper_id
        assert results[0]["source_reliability"] == "parsed_fulltext"


if __name__ == "__main__":
    test_parse_store_records_status_and_rag_search()
    print("paper_parse_store tests passed")
