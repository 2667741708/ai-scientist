from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

try:
    from backend.knowledge_base import KnowledgeBaseStore
except ModuleNotFoundError:
    from knowledge_base import KnowledgeBaseStore


class PaperParseEvidenceStore:
    """SQLite source of truth for paper parse status, evidence, and RAG chunks.

    This is a focused facade over KnowledgeBaseStore so PDF parsing, paper
    interpretation, and RAG retrieval share one local database.
    """

    def __init__(self, root: Path):
        self.store = KnowledgeBaseStore(root)
        self.database_path = self.store.db_path

    def get_parse_status(self, paper_id: str) -> Optional[Dict[str, Any]]:
        for summary in self.store.list_parse_runs():
            if summary.get("paper_id") == paper_id:
                return self.store.get_parse_run(summary["parse_run_id"])
        return None

    def rag_search(
        self,
        query: str,
        *,
        limit: int = 8,
        paper_id: Optional[str] = None,
        library_id: Optional[str] = None,
        parse_item_key: Optional[str] = None,
        support_level: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        return self.store.rag_search(
            query,
            limit=limit,
            paper_id=paper_id,
            library_id=library_id,
            parse_item_key=parse_item_key,
            support_level=support_level,
        )
