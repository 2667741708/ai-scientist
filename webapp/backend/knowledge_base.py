from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("abstract", re.compile(r"^(abstract|summary)\b", re.I)),
    ("introduction", re.compile(r"^(introduction|background)\b", re.I)),
    ("methods", re.compile(r"^(methods?|materials and methods|methodology|experimental procedures?)\b", re.I)),
    ("experiments", re.compile(r"^(experiments?|experimental setup|evaluation|benchmark)\b", re.I)),
    ("results", re.compile(r"^(results?|findings)\b", re.I)),
    ("discussion", re.compile(r"^(discussion|conclusion|limitations?)\b", re.I)),
    ("tables", re.compile(r"^(table|dataset|metrics?)\b", re.I)),
    ("references", re.compile(r"^(references|bibliography)\b", re.I)),
]

EXPERIMENT_HINTS = re.compile(
    r"\b("
    r"experiment|experimental|evaluation|benchmark|dataset|cohort|n\s*=\s*\d+|accuracy|auc|f1|precision|recall|"
    r"p\s*[<=>]\s*0?\.\d+|confidence interval|ablation|baseline|control|trial|table\s+\d+|figure\s+\d+"
    r")\b",
    re.I,
)

DEFAULT_LIBRARY_ID = "library_default"
DEFAULT_LIBRARY_NAME = "默认文献库"
ACTIVE_WORK_ITEM_STATUSES = ("queued", "leased", "running", "retrying", "blocked")
LEASEABLE_WORK_ITEM_STATUSES = ("queued", "retrying")


@dataclass
class KnowledgeChunk:
    chunk_id: str
    paper_id: str
    level: str
    section_type: str
    section_path: list[str]
    title: str
    text: str
    order: int
    parent_id: Optional[str] = None
    experiment_data_summary: Optional[str] = None
    support_level: str = "fulltext"
    parse_run_id: Optional[str] = None
    evidence_id: Optional[str] = None
    library_id: str = DEFAULT_LIBRARY_ID


@dataclass
class PaperDocument:
    paper_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    abstract: Optional[str] = None
    source: str = "user_upload"
    source_reliability: str = "user_provided"
    metadata: Dict[str, Any] = field(default_factory=dict)
    content: str = ""
    chunks: list[KnowledgeChunk] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    parse_run_id: Optional[str] = None
    library_id: str = DEFAULT_LIBRARY_ID


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return normalized[:48] or uuid.uuid4().hex[:10]


def _section_type(title: str) -> str:
    normalized = title.strip().lower()
    for section_type, pattern in SECTION_PATTERNS:
        if pattern.search(normalized):
            return section_type
    return "section"


def _summarize_experiment_data(text: str) -> Optional[str]:
    sentences = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    evidence_sentences = [s.strip() for s in sentences if EXPERIMENT_HINTS.search(s)]
    if not evidence_sentences:
        return None
    summary = " ".join(evidence_sentences[:3])
    return summary[:700]


def _split_markdown_sections(content: str) -> list[tuple[int, str, str]]:
    """Return (heading_level, title, body) sections without fixed-length slicing."""
    sections: list[tuple[int, str, list[str]]] = []
    current_level = 1
    current_title = "Document"
    current_body: list[str] = []

    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        match = heading_pattern.match(line)
        if match:
            if current_body or sections:
                sections.append((current_level, current_title, current_body))
            current_level = len(match.group(1))
            current_title = match.group(2).strip()
            current_body = []
        else:
            current_body.append(line)
    if current_body or not sections:
        sections.append((current_level, current_title, current_body))

    normalized: list[tuple[int, str, str]] = []
    for level, title, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if body:
            normalized.append((level, title, body))
    return normalized


def hierarchical_chunk_paper(paper: PaperDocument) -> list[KnowledgeChunk]:
    sections = _split_markdown_sections(paper.content)
    chunks: list[KnowledgeChunk] = []
    heading_stack: list[tuple[int, str]] = []
    order = 0

    if paper.abstract:
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"{paper.paper_id}:abstract",
                paper_id=paper.paper_id,
                level="abstract",
                section_type="abstract",
                section_path=["Abstract"],
                title="Abstract",
                text=paper.abstract.strip(),
                order=order,
                experiment_data_summary=_summarize_experiment_data(paper.abstract),
            )
        )
        order += 1

    for heading_level, title, body in sections:
        while heading_stack and heading_stack[-1][0] >= heading_level:
            heading_stack.pop()
        heading_stack.append((heading_level, title))
        section_path = [item[1] for item in heading_stack]
        section_type = _section_type(title)

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        if not paragraphs:
            continue

        # Preserve semantic section boundaries. Split only on paragraph groups for very
        # dense sections, never by a fixed character window.
        groups: list[list[str]] = []
        current_group: list[str] = []
        for paragraph in paragraphs:
            current_group.append(paragraph)
            is_table_like = paragraph.lower().startswith(("table ", "|")) or "\t" in paragraph
            if is_table_like or len(current_group) >= 4:
                groups.append(current_group)
                current_group = []
        if current_group:
            groups.append(current_group)

        for group_index, group in enumerate(groups, start=1):
            text = "\n\n".join(group)
            chunk_title = title if len(groups) == 1 else f"{title} · part {group_index}"
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{paper.paper_id}:{_slug(title)}:{group_index}",
                    paper_id=paper.paper_id,
                    level=f"h{heading_level}",
                    section_type=section_type,
                    section_path=section_path,
                    title=chunk_title,
                    text=text,
                    order=order,
                    parent_id=f"{paper.paper_id}:{_slug(section_path[-2])}" if len(section_path) > 1 else None,
                    experiment_data_summary=_summarize_experiment_data(text),
                )
            )
            order += 1

    return chunks


class KnowledgeBaseStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.documents_path = self.root / "papers.jsonl"
        self.db_path = Path(os.getenv("COSCIENTIST_KNOWLEDGE_DB_PATH", str(self.root / "knowledge.sqlite3")))
        self._init_db()
        self._import_legacy_jsonl_once()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterable[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS store_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS literature_libraries (
                    library_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    library_id TEXT NOT NULL DEFAULT 'library_default',
                    title TEXT NOT NULL,
                    authors_json TEXT NOT NULL,
                    year INTEGER,
                    doi TEXT,
                    url TEXT,
                    abstract TEXT,
                    source TEXT NOT NULL,
                    source_reliability TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    parse_run_id TEXT
                );

                CREATE TABLE IF NOT EXISTS paper_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    paper_id TEXT NOT NULL,
                    library_id TEXT NOT NULL DEFAULT 'library_default',
                    level TEXT NOT NULL,
                    section_type TEXT NOT NULL,
                    section_path_json TEXT NOT NULL,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    order_index INTEGER NOT NULL,
                    parent_id TEXT,
                    experiment_data_summary TEXT,
                    support_level TEXT NOT NULL,
                    parse_run_id TEXT,
                    evidence_id TEXT,
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS evidence_chunks_fts USING fts5(
                    library_id UNINDEXED,
                    chunk_id UNINDEXED,
                    paper_id UNINDEXED,
                    parse_run_id UNINDEXED,
                    parse_item_key UNINDEXED,
                    title,
                    section_path,
                    section_type,
                    text,
                    evidence_summary,
                    support_level UNINDEXED,
                    source_reliability UNINDEXED,
                    evidence_path UNINDEXED
                );

                CREATE TABLE IF NOT EXISTS paper_parse_runs (
                    parse_run_id TEXT PRIMARY KEY,
                    paper_id TEXT,
                    library_id TEXT NOT NULL DEFAULT 'library_default',
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_kind TEXT NOT NULL,
                    input_path TEXT NOT NULL,
                    pdf_path TEXT,
                    solve_dir TEXT,
                    page_count INTEGER,
                    chunks_count INTEGER NOT NULL DEFAULT 0,
                    experimental_chunks_count INTEGER NOT NULL DEFAULT 0,
                    knowledge_base_ingested INTEGER NOT NULL DEFAULT 0,
                    rag_search_ready INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_parse_items (
                    item_id TEXT PRIMARY KEY,
                    parse_run_id TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    evidence_summary TEXT NOT NULL,
                    evidence_id TEXT,
                    completed_at REAL,
                    error_message TEXT,
                    order_index INTEGER NOT NULL,
                    FOREIGN KEY (parse_run_id) REFERENCES paper_parse_runs(parse_run_id)
                );

                CREATE TABLE IF NOT EXISTS paper_parse_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    parse_run_id TEXT NOT NULL,
                    paper_id TEXT,
                    library_id TEXT NOT NULL DEFAULT 'library_default',
                    item_key TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    file_path TEXT,
                    chunk_id TEXT,
                    section_path_json TEXT NOT NULL,
                    text_preview TEXT,
                    media_preview TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (parse_run_id) REFERENCES paper_parse_runs(parse_run_id)
                );

                CREATE TABLE IF NOT EXISTS research_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    request_json TEXT NOT NULL,
                    research_plan_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    safety_gate_json TEXT NOT NULL,
                    citation_provenance_qa_json TEXT NOT NULL,
                    expert_feedback_json TEXT NOT NULL,
                    error TEXT,
                    record_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_run_timeline (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    order_index INTEGER NOT NULL,
                    time_label TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    event TEXT NOT NULL,
                    details TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES research_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS research_hypotheses (
                    hypothesis_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    hypothesis_index INTEGER NOT NULL,
                    title TEXT,
                    text TEXT,
                    explanation TEXT,
                    experiment TEXT,
                    score REAL,
                    rank_value REAL,
                    grounding_status TEXT,
                    literature_grounding TEXT,
                    citation_map_json TEXT NOT NULL,
                    hypothesis_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES research_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS hypothesis_evidence_links (
                    link_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    hypothesis_id TEXT NOT NULL,
                    hypothesis_index INTEGER NOT NULL,
                    evidence_id TEXT,
                    chunk_id TEXT,
                    paper_id TEXT,
                    parse_run_id TEXT,
                    section_type TEXT,
                    section_path_json TEXT NOT NULL,
                    support_level TEXT,
                    source_reliability TEXT,
                    evidence_summary TEXT,
                    experiment_data_summary TEXT,
                    text_preview TEXT,
                    evidence_path TEXT,
                    score REAL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES research_runs(run_id),
                    FOREIGN KEY (hypothesis_id) REFERENCES research_hypotheses(hypothesis_id)
                );

                CREATE TABLE IF NOT EXISTS evidence_retrievals (
                    retrieval_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    hypothesis_id TEXT,
                    hypothesis_index INTEGER,
                    tool_name TEXT NOT NULL,
                    query TEXT NOT NULL,
                    limit_value INTEGER NOT NULL,
                    result_count INTEGER NOT NULL,
                    results_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES research_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS research_agent_trace (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    parent_event_id TEXT,
                    order_index INTEGER NOT NULL,
                    agent TEXT NOT NULL,
                    role TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output TEXT NOT NULL,
                    tool_calls_json TEXT NOT NULL,
                    token_usage_json TEXT NOT NULL,
                    synthetic INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES research_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS research_tool_calls (
                    tool_call_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    trace_event_id TEXT,
                    order_index INTEGER NOT NULL,
                    agent TEXT,
                    phase TEXT,
                    tool_name TEXT NOT NULL,
                    status TEXT,
                    arguments_json TEXT NOT NULL,
                    result_summary TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES research_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS research_tool_results (
                    result_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    tool_name TEXT NOT NULL,
                    phase TEXT,
                    result_kind TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    content_size INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_background_jobs (
                    job_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    workflow_name TEXT NOT NULL,
                    phase TEXT,
                    status TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    result_ref_json TEXT NOT NULL,
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_work_items (
                    work_item_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    run_id TEXT,
                    workflow_name TEXT NOT NULL,
                    phase TEXT,
                    agent_role TEXT,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 3,
                    lease_owner TEXT,
                    lease_expires_at REAL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    arguments_json TEXT NOT NULL,
                    result_ref_json TEXT NOT NULL,
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    target_type TEXT NOT NULL,
                    target_ref_json TEXT NOT NULL,
                    feedback_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    phase TEXT,
                    status TEXT NOT NULL,
                    checkpoint_backend TEXT NOT NULL,
                    checkpoint_ref TEXT,
                    state_summary_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_tasks (
                    task_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    title TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    phase TEXT,
                    target_ref_json TEXT NOT NULL,
                    result_ref_json TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    blocked_reason TEXT,
                    due_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_schedules (
                    schedule_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    title TEXT NOT NULL,
                    workflow_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    interval_hours REAL NOT NULL,
                    phase TEXT,
                    arguments_json TEXT NOT NULL,
                    last_run_at REAL,
                    next_run_at REAL NOT NULL,
                    result_ref_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_delegations (
                    delegation_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    title TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    agents_json TEXT NOT NULL,
                    target_ref_json TEXT NOT NULL,
                    result_ref_json TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    run_id TEXT,
                    title TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_chat_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    message_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES research_chat_sessions(session_id)
                );

                CREATE TABLE IF NOT EXISTS research_chat_actions (
                    action_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    approval_scope TEXT,
                    execution_target TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    result_ref_json TEXT NOT NULL,
                    error_summary TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES research_chat_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper_id ON paper_chunks(paper_id);
                CREATE INDEX IF NOT EXISTS idx_paper_chunks_parse_run_id ON paper_chunks(parse_run_id);
                CREATE INDEX IF NOT EXISTS idx_parse_items_run ON paper_parse_items(parse_run_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_parse_evidence_run ON paper_parse_evidence(parse_run_id);
                CREATE INDEX IF NOT EXISTS idx_research_runs_updated ON research_runs(updated_at);
                CREATE INDEX IF NOT EXISTS idx_research_hypotheses_run ON research_hypotheses(run_id, hypothesis_index);
                CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_run ON hypothesis_evidence_links(run_id, hypothesis_index);
                CREATE INDEX IF NOT EXISTS idx_evidence_retrievals_run ON evidence_retrievals(run_id, hypothesis_index);
                CREATE INDEX IF NOT EXISTS idx_research_agent_trace_run ON research_agent_trace(run_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_research_tool_calls_run ON research_tool_calls(run_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_research_tool_results_run ON research_tool_results(run_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_research_background_jobs_run ON research_background_jobs(run_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_research_work_items_status ON research_work_items(status, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_research_work_items_run ON research_work_items(run_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_research_work_items_lease ON research_work_items(status, lease_expires_at);
                CREATE INDEX IF NOT EXISTS idx_research_feedback_run ON research_feedback(run_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_research_checkpoints_run ON research_checkpoints(run_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_research_tasks_run ON research_tasks(run_id, status, priority);
                CREATE INDEX IF NOT EXISTS idx_research_schedules_status ON research_schedules(status, next_run_at);
                CREATE INDEX IF NOT EXISTS idx_research_delegations_run ON research_delegations(run_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_research_chat_sessions_run ON research_chat_sessions(run_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_research_chat_messages_session ON research_chat_messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_research_chat_actions_session ON research_chat_actions(session_id, updated_at);
                """
            )
            self._migrate_library_schema(connection)
            self._migrate_research_runtime_schema(connection)

    def _table_columns(self, connection: sqlite3.Connection, table_name: str) -> set[str]:
        return {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}

    def _migrate_library_schema(self, connection: sqlite3.Connection) -> None:
        table_columns = {
            "papers": self._table_columns(connection, "papers"),
            "paper_chunks": self._table_columns(connection, "paper_chunks"),
            "paper_parse_runs": self._table_columns(connection, "paper_parse_runs"),
            "paper_parse_evidence": self._table_columns(connection, "paper_parse_evidence"),
        }
        if "library_id" not in table_columns["papers"]:
            connection.execute(f"ALTER TABLE papers ADD COLUMN library_id TEXT NOT NULL DEFAULT '{DEFAULT_LIBRARY_ID}'")
        if "library_id" not in table_columns["paper_chunks"]:
            connection.execute(f"ALTER TABLE paper_chunks ADD COLUMN library_id TEXT NOT NULL DEFAULT '{DEFAULT_LIBRARY_ID}'")
        if "library_id" not in table_columns["paper_parse_runs"]:
            connection.execute(f"ALTER TABLE paper_parse_runs ADD COLUMN library_id TEXT NOT NULL DEFAULT '{DEFAULT_LIBRARY_ID}'")
        if "library_id" not in table_columns["paper_parse_evidence"]:
            connection.execute(f"ALTER TABLE paper_parse_evidence ADD COLUMN library_id TEXT NOT NULL DEFAULT '{DEFAULT_LIBRARY_ID}'")

        now = time.time()
        connection.execute(
            """
            INSERT OR IGNORE INTO literature_libraries(library_id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                DEFAULT_LIBRARY_ID,
                DEFAULT_LIBRARY_NAME,
                "系统自动创建，用于兼容已有论文和解析记录。",
                now,
                now,
            ),
        )
        for table_name in ("papers", "paper_chunks", "paper_parse_runs", "paper_parse_evidence"):
            connection.execute(
                f"UPDATE {table_name} SET library_id = ? WHERE library_id IS NULL OR TRIM(library_id) = ''",
                (DEFAULT_LIBRARY_ID,),
            )

        fts_columns = self._table_columns(connection, "evidence_chunks_fts")
        if "library_id" not in fts_columns:
            connection.execute("DROP TABLE IF EXISTS evidence_chunks_fts")
            connection.execute(
                """
                CREATE VIRTUAL TABLE evidence_chunks_fts USING fts5(
                    library_id UNINDEXED,
                    chunk_id UNINDEXED,
                    paper_id UNINDEXED,
                    parse_run_id UNINDEXED,
                    parse_item_key UNINDEXED,
                    title,
                    section_path,
                    section_type,
                    text,
                    evidence_summary,
                    support_level UNINDEXED,
                    source_reliability UNINDEXED,
                    evidence_path UNINDEXED
                )
                """
            )
            self._rebuild_evidence_fts(connection)

    def _migrate_research_runtime_schema(self, connection: sqlite3.Connection) -> None:
        work_item_columns = self._table_columns(connection, "research_work_items")
        if "idempotency_key" not in work_item_columns:
            connection.execute("ALTER TABLE research_work_items ADD COLUMN idempotency_key TEXT")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_research_work_items_idempotency
            ON research_work_items(idempotency_key)
            WHERE idempotency_key IS NOT NULL AND TRIM(idempotency_key) != ''
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_research_work_items_active_open_run
            ON research_work_items(workflow_name, run_id)
            WHERE workflow_name = 'workflow.open_coscientist_run'
              AND run_id IS NOT NULL
              AND status IN ('queued', 'leased', 'running', 'retrying', 'blocked')
            """
        )

    def _rebuild_evidence_fts(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM evidence_chunks_fts")
        rows = connection.execute(
            """
            SELECT pc.library_id, pc.chunk_id, pc.paper_id, pc.parse_run_id, pc.title,
                   pc.section_path_json, pc.section_type, pc.text, pc.experiment_data_summary,
                   pc.support_level, p.source_reliability, p.url
            FROM paper_chunks pc
            JOIN papers p ON p.paper_id = pc.paper_id
            ORDER BY pc.order_index ASC
            """
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                INSERT INTO evidence_chunks_fts(
                    library_id, chunk_id, paper_id, parse_run_id, parse_item_key, title,
                    section_path, section_type, text, evidence_summary, support_level,
                    source_reliability, evidence_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["library_id"] or DEFAULT_LIBRARY_ID,
                    row["chunk_id"],
                    row["paper_id"],
                    row["parse_run_id"],
                    "rag_indexed",
                    row["title"],
                    " / ".join(json.loads(row["section_path_json"])),
                    row["section_type"],
                    row["text"],
                    row["experiment_data_summary"] or row["title"],
                    row["support_level"],
                    row["source_reliability"],
                    row["url"],
                ),
            )

    def _import_legacy_jsonl_once(self) -> None:
        if not self.documents_path.exists():
            return
        with self._connection() as connection:
            imported = connection.execute(
                "SELECT value FROM store_meta WHERE key = 'legacy_jsonl_imported'"
            ).fetchone()
            paper_count = connection.execute("SELECT COUNT(*) AS count FROM papers").fetchone()["count"]
            if imported or paper_count > 0:
                return

        documents: list[PaperDocument] = []
        with self.documents_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                raw = json.loads(line)
                raw["chunks"] = [KnowledgeChunk(**chunk) for chunk in raw.get("chunks", [])]
                documents.append(PaperDocument(**raw))

        with self._connection() as connection:
            for paper in documents:
                self._insert_document(connection, paper)
            connection.execute(
                "INSERT OR REPLACE INTO store_meta(key, value) VALUES('legacy_jsonl_imported', ?)",
                (str(time.time()),),
            )

    def resolve_library_id(self, library_id: Optional[str]) -> str:
        normalized = (library_id or DEFAULT_LIBRARY_ID).strip() or DEFAULT_LIBRARY_ID
        with self._connection() as connection:
            row = connection.execute(
                "SELECT library_id FROM literature_libraries WHERE library_id = ?",
                (normalized,),
            ).fetchone()
        if not row:
            raise ValueError(f"unknown literature library: {normalized}")
        return str(row["library_id"])

    def create_library(self, *, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        normalized_name = name.strip()
        if len(normalized_name) < 2:
            raise ValueError("library name is too short")
        library_id = f"library_{_slug(normalized_name)}_{uuid.uuid4().hex[:8]}"
        now = time.time()
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO literature_libraries(library_id, name, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (library_id, normalized_name, description or "", now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("library name already exists") from exc
        return self.get_library(library_id) or {
            "library_id": library_id,
            "name": normalized_name,
            "description": description or "",
            "created_at": now,
            "updated_at": now,
            "paper_count": 0,
            "parse_run_count": 0,
            "chunk_count": 0,
        }

    def get_library(self, library_id: str) -> Optional[Dict[str, Any]]:
        for library in self.list_libraries():
            if library["library_id"] == library_id:
                return library
        return None

    def list_libraries(self) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM literature_libraries ORDER BY created_at ASC"
            ).fetchall()
            libraries: list[Dict[str, Any]] = []
            for row in rows:
                library_id = row["library_id"]
                paper_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM papers WHERE library_id = ?",
                    (library_id,),
                ).fetchone()["count"]
                parse_run_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM paper_parse_runs WHERE library_id = ?",
                    (library_id,),
                ).fetchone()["count"]
                chunk_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM paper_chunks WHERE library_id = ?",
                    (library_id,),
                ).fetchone()["count"]
                libraries.append(
                    {
                        "library_id": library_id,
                        "name": row["name"],
                        "description": row["description"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "paper_count": paper_count,
                        "parse_run_count": parse_run_count,
                        "chunk_count": chunk_count,
                        "is_default": library_id == DEFAULT_LIBRARY_ID,
                    }
                )
        if not libraries:
            with self._connection() as connection:
                self._migrate_library_schema(connection)
            return self.list_libraries()
        return libraries

    def ingest(
        self,
        *,
        title: str,
        content: str,
        authors: Optional[list[str]] = None,
        year: Optional[int] = None,
        doi: Optional[str] = None,
        url: Optional[str] = None,
        abstract: Optional[str] = None,
        source: str = "user_upload",
        source_reliability: str = "user_provided",
        metadata: Optional[Dict[str, Any]] = None,
        library_id: Optional[str] = None,
    ) -> PaperDocument:
        metadata = metadata or {}
        resolved_library_id = self.resolve_library_id(library_id)
        metadata.setdefault("library_id", resolved_library_id)
        paper_id = f"paper_{_slug(doi or title)}_{uuid.uuid4().hex[:8]}"
        parse_run_id = metadata.get("parse_run_id") if isinstance(metadata.get("parse_run_id"), str) else None
        paper = PaperDocument(
            paper_id=paper_id,
            title=title.strip(),
            authors=authors or [],
            year=year,
            doi=doi,
            url=url,
            abstract=abstract,
            source=source,
            source_reliability=source_reliability,
            metadata=metadata,
            content=content,
            parse_run_id=parse_run_id,
            library_id=resolved_library_id,
        )
        paper.chunks = hierarchical_chunk_paper(paper)
        for chunk in paper.chunks:
            chunk.parse_run_id = parse_run_id
            chunk.support_level = "experimental_data" if chunk.experiment_data_summary else ("abstract" if chunk.level == "abstract" else "fulltext")
            chunk.evidence_id = f"evidence_{uuid.uuid4().hex[:12]}"
            chunk.library_id = resolved_library_id
        self._append_document(paper)
        return paper

    def _append_document(self, paper: PaperDocument) -> None:
        with self._connection() as connection:
            self._insert_document(connection, paper)

    def _insert_document(self, connection: sqlite3.Connection, paper: PaperDocument) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO papers(
                paper_id, library_id, title, authors_json, year, doi, url, abstract, source,
                source_reliability, metadata_json, content, created_at, parse_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper.paper_id,
                paper.library_id,
                paper.title,
                json.dumps(paper.authors, ensure_ascii=False),
                paper.year,
                paper.doi,
                paper.url,
                paper.abstract,
                paper.source,
                paper.source_reliability,
                json.dumps(paper.metadata, ensure_ascii=False),
                paper.content,
                paper.created_at,
                paper.parse_run_id,
            ),
        )
        connection.execute("DELETE FROM paper_chunks WHERE paper_id = ?", (paper.paper_id,))
        connection.execute("DELETE FROM evidence_chunks_fts WHERE paper_id = ?", (paper.paper_id,))
        for chunk in paper.chunks:
            connection.execute(
                """
                INSERT OR REPLACE INTO paper_chunks(
                    chunk_id, paper_id, library_id, level, section_type, section_path_json, title,
                    text, order_index, parent_id, experiment_data_summary, support_level,
                    parse_run_id, evidence_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    chunk.paper_id,
                    chunk.library_id,
                    chunk.level,
                    chunk.section_type,
                    json.dumps(chunk.section_path, ensure_ascii=False),
                    chunk.title,
                    chunk.text,
                    chunk.order,
                    chunk.parent_id,
                    chunk.experiment_data_summary,
                    chunk.support_level,
                    chunk.parse_run_id,
                    chunk.evidence_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO evidence_chunks_fts(
                    library_id, chunk_id, paper_id, parse_run_id, parse_item_key, title, section_path,
                    section_type, text, evidence_summary, support_level, source_reliability,
                    evidence_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.library_id,
                    chunk.chunk_id,
                    chunk.paper_id,
                    chunk.parse_run_id,
                    "rag_indexed",
                    chunk.title,
                    " / ".join(chunk.section_path),
                    chunk.section_type,
                    chunk.text,
                    chunk.experiment_data_summary or chunk.title,
                    chunk.support_level,
                    paper.source_reliability,
                    paper.url,
                ),
            )

    def list_documents(self, library_id: Optional[str] = None) -> list[PaperDocument]:
        documents: list[PaperDocument] = []
        resolved_library_id = self.resolve_library_id(library_id) if library_id else None
        with self._connection() as connection:
            if resolved_library_id:
                paper_rows = connection.execute(
                    "SELECT * FROM papers WHERE library_id = ? ORDER BY created_at DESC",
                    (resolved_library_id,),
                ).fetchall()
                chunk_rows = connection.execute(
                    "SELECT * FROM paper_chunks WHERE library_id = ? ORDER BY order_index ASC",
                    (resolved_library_id,),
                ).fetchall()
            else:
                paper_rows = connection.execute("SELECT * FROM papers ORDER BY created_at DESC").fetchall()
                chunk_rows = connection.execute("SELECT * FROM paper_chunks ORDER BY order_index ASC").fetchall()
        chunks_by_paper: dict[str, list[KnowledgeChunk]] = {}
        for row in chunk_rows:
            chunk = KnowledgeChunk(
                chunk_id=row["chunk_id"],
                paper_id=row["paper_id"],
                level=row["level"],
                section_type=row["section_type"],
                section_path=json.loads(row["section_path_json"]),
                title=row["title"],
                text=row["text"],
                order=row["order_index"],
                parent_id=row["parent_id"],
                experiment_data_summary=row["experiment_data_summary"],
                support_level=row["support_level"],
                parse_run_id=row["parse_run_id"],
                evidence_id=row["evidence_id"],
                library_id=row["library_id"] or DEFAULT_LIBRARY_ID,
            )
            chunks_by_paper.setdefault(chunk.paper_id, []).append(chunk)
        for row in paper_rows:
            documents.append(
                PaperDocument(
                    paper_id=row["paper_id"],
                    title=row["title"],
                    authors=json.loads(row["authors_json"]),
                    year=row["year"],
                    doi=row["doi"],
                    url=row["url"],
                    abstract=row["abstract"],
                    source=row["source"],
                    source_reliability=row["source_reliability"],
                    metadata=json.loads(row["metadata_json"]),
                    content=row["content"],
                    chunks=chunks_by_paper.get(row["paper_id"], []),
                    created_at=row["created_at"],
                    parse_run_id=row["parse_run_id"],
                    library_id=row["library_id"] or DEFAULT_LIBRARY_ID,
                )
            )
        return documents

    def iter_chunks(self, library_id: Optional[str] = None) -> Iterable[KnowledgeChunk]:
        for document in self.list_documents(library_id=library_id):
            yield from document.chunks

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
        normalized = query.strip()
        if not normalized:
            return []
        resolved_library_id = self.resolve_library_id(library_id) if library_id else None
        terms = re.findall(r"[A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", normalized)
        fts_query = " OR ".join(f'"{term}"' for term in terms[:12]) or normalized
        where = ["evidence_chunks_fts MATCH ?"]
        params: list[Any] = [fts_query]
        if resolved_library_id:
            where.append("library_id = ?")
            params.append(resolved_library_id)
        if paper_id:
            where.append("paper_id = ?")
            params.append(paper_id)
        if parse_item_key:
            where.append("parse_item_key = ?")
            params.append(parse_item_key)
        if support_level:
            where.append("support_level = ?")
            params.append(support_level)
        params.append(max(1, min(limit, 50)))
        sql = f"""
            SELECT rowid, chunk_id, paper_id, parse_run_id, parse_item_key, title,
                   library_id, section_path, section_type, text, evidence_summary, support_level,
                   source_reliability, evidence_path, bm25(evidence_chunks_fts) AS rank
            FROM evidence_chunks_fts
            WHERE {' AND '.join(where)}
            ORDER BY rank
            LIMIT ?
        """
        evidence_ids_by_chunk: Dict[str, Optional[str]] = {}
        try:
            with self._connection() as connection:
                rows = connection.execute(sql, params).fetchall()
                chunk_ids = [row["chunk_id"] for row in rows]
                if chunk_ids:
                    placeholders = ", ".join("?" for _ in chunk_ids)
                    evidence_rows = connection.execute(
                        f"SELECT chunk_id, evidence_id FROM paper_chunks WHERE chunk_id IN ({placeholders})",
                        chunk_ids,
                    ).fetchall()
                    evidence_ids_by_chunk = {
                        row["chunk_id"]: row["evidence_id"] for row in evidence_rows
                    }
        except sqlite3.OperationalError:
            return self._rag_search_fallback(
                normalized,
                limit=limit,
                paper_id=paper_id,
                library_id=resolved_library_id,
                parse_item_key=parse_item_key,
                support_level=support_level,
            )
        return [
            {
                "chunk_id": row["chunk_id"],
                "paper_id": row["paper_id"],
                "library_id": row["library_id"] or DEFAULT_LIBRARY_ID,
                "parse_run_id": row["parse_run_id"],
                "parse_item_key": row["parse_item_key"],
                "title": row["title"],
                "section_path": row["section_path"].split(" / ") if row["section_path"] else [],
                "section_type": row["section_type"],
                "text_preview": row["text"][:700],
                "evidence_summary": row["evidence_summary"],
                "support_level": row["support_level"],
                "source_reliability": row["source_reliability"],
                "evidence_path": row["evidence_path"],
                "evidence_id": evidence_ids_by_chunk.get(row["chunk_id"]),
                "score": float(row["rank"]),
            }
            for row in rows
        ]

    def _rag_search_fallback(
        self,
        query: str,
        *,
        limit: int,
        paper_id: Optional[str],
        library_id: Optional[str],
        parse_item_key: Optional[str],
        support_level: Optional[str],
    ) -> list[Dict[str, Any]]:
        if parse_item_key and parse_item_key not in {"rag_indexed", "rag_search_ready"}:
            return []
        terms = {term.lower() for term in re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", query)}
        results: list[tuple[int, Dict[str, Any]]] = []
        for document in self.list_documents(library_id=library_id):
            if paper_id and document.paper_id != paper_id:
                continue
            for chunk in document.chunks:
                if support_level and chunk.support_level != support_level:
                    continue
                haystack = f"{chunk.title} {' '.join(chunk.section_path)} {chunk.text}".lower()
                score = sum(1 for term in terms if term in haystack)
                if score <= 0:
                    continue
                results.append(
                    (
                        score,
                        {
                            "chunk_id": chunk.chunk_id,
                            "paper_id": document.paper_id,
                            "library_id": document.library_id,
                            "parse_run_id": chunk.parse_run_id,
                            "parse_item_key": "rag_indexed",
                            "title": document.title,
                            "section_path": chunk.section_path,
                            "section_type": chunk.section_type,
                            "text_preview": chunk.text[:700],
                            "evidence_summary": chunk.experiment_data_summary or chunk.title,
                            "support_level": chunk.support_level,
                            "source_reliability": document.source_reliability,
                            "evidence_path": document.url,
                            "evidence_id": chunk.evidence_id,
                            "score": score,
                        },
                    )
                )
        results.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in results[:limit]]

    def search_chunks(self, query: str, *, limit: int = 8, library_id: Optional[str] = None) -> list[Dict[str, Any]]:
        rag_results = self.rag_search(query, limit=limit, library_id=library_id)
        if rag_results:
            return [
                {
                    **result,
                    "doi": None,
                    "url": result.get("evidence_path"),
                    "source": "sqlite_fts",
                    "chunk_title": result.get("title"),
                    "experiment_data_summary": result.get("evidence_summary")
                    if result.get("support_level") == "experimental_data"
                    else None,
                }
                for result in rag_results
            ]
        terms = {term.lower() for term in re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", query)}
        if not terms:
            return []

        document_by_id = {doc.paper_id: doc for doc in self.list_documents(library_id=library_id)}
        scored: list[tuple[int, KnowledgeChunk]] = []
        for chunk in (chunk for doc in document_by_id.values() for chunk in doc.chunks):
            haystack = f"{chunk.title} {' '.join(chunk.section_path)} {chunk.text}".lower()
            score = sum(1 for term in terms if term in haystack)
            if EXPERIMENT_HINTS.search(chunk.text):
                score += 1
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: (item[0], bool(item[1].experiment_data_summary)), reverse=True)
        results: list[Dict[str, Any]] = []
        for score, chunk in scored[:limit]:
            doc = document_by_id[chunk.paper_id]
            results.append(
                {
                    "score": score,
                    "paper_id": doc.paper_id,
                    "library_id": doc.library_id,
                    "title": doc.title,
                    "doi": doc.doi,
                    "url": doc.url,
                    "source": doc.source,
                    "source_reliability": doc.source_reliability,
                    "chunk_id": chunk.chunk_id,
                    "section_type": chunk.section_type,
                    "section_path": chunk.section_path,
                    "chunk_title": chunk.title,
                    "support_level": chunk.support_level,
                    "parse_run_id": chunk.parse_run_id,
                    "evidence_id": chunk.evidence_id,
                    "experiment_data_summary": chunk.experiment_data_summary,
                    "text_preview": chunk.text[:500],
                }
            )
        return results

    def support_for_hypothesis(self, hypothesis: Dict[str, Any], *, limit: int = 6) -> list[Dict[str, Any]]:
        query_parts = [
            str(hypothesis.get("text", "")),
            str(hypothesis.get("explanation", "")),
            str(hypothesis.get("experiment", "")),
        ]
        return self.search_chunks(" ".join(query_parts), limit=limit)

    def record_research_run(self, record: Dict[str, Any]) -> None:
        run_id = str(record.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("research run record requires run_id")

        now = time.time()
        created_at = self._coerce_float(record.get("created_at"), now)
        updated_at = self._coerce_float(record.get("updated_at"), now)
        hypotheses = record.get("hypotheses") if isinstance(record.get("hypotheses"), list) else []
        timeline = record.get("timeline") if isinstance(record.get("timeline"), list) else []
        agent_trace = record.get("agent_trace") if isinstance(record.get("agent_trace"), list) else []

        with self._connection() as connection:
            for table in (
                "research_tool_calls",
                "research_agent_trace",
                "hypothesis_evidence_links",
                "research_hypotheses",
                "research_run_timeline",
            ):
                connection.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))
            connection.execute(
                """
                DELETE FROM evidence_retrievals
                WHERE run_id = ? AND retrieval_id LIKE ?
                """,
                (run_id, f"{run_id}:hypothesis:%:support_for_hypothesis"),
            )

            connection.execute(
                """
                INSERT OR REPLACE INTO research_runs(
                    run_id, status, created_at, updated_at, request_json, research_plan_json,
                    metrics_json, safety_gate_json, citation_provenance_qa_json,
                    expert_feedback_json, error, record_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    str(record.get("status") or "queued"),
                    created_at,
                    updated_at,
                    self._to_json(record.get("request", {})),
                    self._to_json(record.get("research_plan", {})),
                    self._to_json(record.get("metrics", {})),
                    self._to_json(record.get("safety_gate", {})),
                    self._to_json(record.get("citation_provenance_qa", {})),
                    self._to_json(record.get("expert_feedback", {})),
                    record.get("error"),
                    self._to_json(record),
                ),
            )

            for index, event in enumerate(timeline):
                if not isinstance(event, dict):
                    continue
                connection.execute(
                    """
                    INSERT INTO research_run_timeline(
                        event_id, run_id, order_index, time_label, stage, event, details, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{run_id}:timeline:{index:04d}",
                        run_id,
                        index,
                        str(event.get("time") or ""),
                        str(event.get("stage") or ""),
                        str(event.get("event") or ""),
                        str(event.get("details") or ""),
                        str(event.get("status") or "complete"),
                    ),
                )

            for index, hypothesis in enumerate(hypotheses):
                if not isinstance(hypothesis, dict):
                    continue
                hypothesis_id = self._hypothesis_id(run_id, index, hypothesis)
                citation_map = hypothesis.get("citation_map") if isinstance(hypothesis.get("citation_map"), dict) else {}
                support_items = hypothesis.get("knowledge_base_support")
                support_items = support_items if isinstance(support_items, list) else []
                connection.execute(
                    """
                    INSERT INTO research_hypotheses(
                        hypothesis_id, run_id, hypothesis_index, title, text, explanation,
                        experiment, score, rank_value, grounding_status, literature_grounding,
                        citation_map_json, hypothesis_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hypothesis_id,
                        run_id,
                        index,
                        self._first_text(hypothesis, ("title", "name", "id")),
                        self._first_text(hypothesis, ("text", "hypothesis", "technical_hypothesis")),
                        self._first_text(hypothesis, ("explanation", "plain_explanation", "rationale")),
                        self._first_text(hypothesis, ("experiment", "validation_plan", "experiment_plan")),
                        self._coerce_float(hypothesis.get("score")),
                        self._coerce_float(hypothesis.get("rank") or hypothesis.get("elo_rating")),
                        self._first_text(hypothesis, ("grounding_status",)),
                        self._first_text(hypothesis, ("literature_grounding",)),
                        self._to_json(citation_map),
                        self._to_json(hypothesis),
                        created_at,
                        updated_at,
                    ),
                )

                query = self._hypothesis_query(hypothesis)
                connection.execute(
                    """
                    INSERT OR REPLACE INTO evidence_retrievals(
                        retrieval_id, run_id, hypothesis_id, hypothesis_index, tool_name,
                        query, limit_value, result_count, results_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{run_id}:hypothesis:{index + 1:03d}:support_for_hypothesis",
                        run_id,
                        hypothesis_id,
                        index,
                        "knowledge_base.support_for_hypothesis",
                        query,
                        max(6, len(support_items)),
                        len(support_items),
                        self._to_json(support_items),
                        updated_at,
                    ),
                )

                for support in support_items:
                    if not isinstance(support, dict):
                        continue
                    connection.execute(
                        """
                        INSERT INTO hypothesis_evidence_links(
                            link_id, run_id, hypothesis_id, hypothesis_index, evidence_id,
                            chunk_id, paper_id, parse_run_id, section_type, section_path_json,
                            support_level, source_reliability, evidence_summary,
                            experiment_data_summary, text_preview, evidence_path, score, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"link_{uuid.uuid4().hex[:12]}",
                            run_id,
                            hypothesis_id,
                            index,
                            support.get("evidence_id"),
                            support.get("chunk_id"),
                            support.get("paper_id"),
                            support.get("parse_run_id"),
                            support.get("section_type"),
                            self._to_json(support.get("section_path") or []),
                            support.get("support_level"),
                            support.get("source_reliability"),
                            support.get("evidence_summary") or support.get("chunk_title"),
                            support.get("experiment_data_summary"),
                            support.get("text_preview"),
                            support.get("evidence_path") or support.get("url"),
                            self._coerce_float(support.get("score")),
                            updated_at,
                        ),
                    )

            for index, trace in enumerate(agent_trace):
                if not isinstance(trace, dict):
                    continue
                original_event_id = str(trace.get("event_id") or f"trace:{index:04d}")
                trace_event_id = f"{run_id}:{original_event_id}"
                parent_event_id = trace.get("parent_event_id")
                stored_parent_event_id = f"{run_id}:{parent_event_id}" if parent_event_id else None
                tool_calls = trace.get("tool_calls") if isinstance(trace.get("tool_calls"), list) else []
                connection.execute(
                    """
                    INSERT INTO research_agent_trace(
                        event_id, run_id, parent_event_id, order_index, agent, role, phase,
                        status, output, tool_calls_json, token_usage_json, synthetic, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace_event_id,
                        run_id,
                        stored_parent_event_id,
                        index,
                        str(trace.get("agent") or ""),
                        str(trace.get("role") or ""),
                        str(trace.get("phase") or ""),
                        str(trace.get("status") or "complete"),
                        str(trace.get("output") or ""),
                        self._to_json(tool_calls),
                        self._to_json(trace.get("token_usage", {})),
                        int(bool(trace.get("synthetic", True))),
                        self._coerce_float(trace.get("confidence"), 0.0),
                    ),
                )
                for tool_index, tool_call in enumerate(tool_calls):
                    if not isinstance(tool_call, dict):
                        continue
                    tool_name = str(tool_call.get("tool") or tool_call.get("name") or "unknown_tool")
                    connection.execute(
                        """
                        INSERT INTO research_tool_calls(
                            tool_call_id, run_id, trace_event_id, order_index, agent, phase,
                            tool_name, status, arguments_json, result_summary, metadata_json,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"toolcall_{uuid.uuid4().hex[:12]}",
                            run_id,
                            trace_event_id,
                            tool_index,
                            trace.get("agent"),
                            trace.get("phase"),
                            tool_name,
                            tool_call.get("status"),
                            self._to_json(
                                tool_call.get("arguments")
                                or tool_call.get("args")
                                or tool_call.get("parameters")
                                or {}
                            ),
                            self._first_text(tool_call, ("result_summary", "summary", "output")),
                            self._to_json(tool_call),
                            updated_at,
                        ),
                    )

    def get_research_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record_json FROM research_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["record_json"])

    def list_research_runs(self, *, limit: int = 50) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT run_id, status, created_at, updated_at, request_json, metrics_json,
                       citation_provenance_qa_json, error
                FROM research_runs
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "request": json.loads(row["request_json"]),
                "metrics": json.loads(row["metrics_json"]),
                "citation_provenance_qa": json.loads(row["citation_provenance_qa_json"]),
                "error": row["error"],
            }
            for row in rows
        ]

    def upsert_research_chat_session(
        self,
        *,
        session_id: str,
        mode: str,
        run_id: Optional[str],
        title: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = time.time()
        safe_title = (title.strip() or "Research chat")[:180]
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT created_at FROM research_chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            created_at = float(existing["created_at"]) if existing else now
            connection.execute(
                """
                INSERT OR REPLACE INTO research_chat_sessions(
                    session_id, mode, run_id, title, context_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    mode or "workspace",
                    run_id,
                    safe_title,
                    self._to_json(context),
                    created_at,
                    now,
                ),
            )
        return {
            "session_id": session_id,
            "mode": mode or "workspace",
            "run_id": run_id,
            "title": safe_title,
            "context": context,
            "created_at": created_at,
            "updated_at": now,
        }

    def record_research_chat_message(
        self,
        *,
        session_id: str,
        role: str,
        text: str,
        message: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = time.time()
        message_id = f"chatmsg_{uuid.uuid4().hex[:12]}"
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO research_chat_messages(
                    message_id, session_id, role, text, message_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    session_id,
                    role,
                    text[:4000],
                    self._to_json(message),
                    now,
                ),
            )
            connection.execute(
                "UPDATE research_chat_sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
        return {
            "message_id": message_id,
            "session_id": session_id,
            "role": role,
            "text": text[:4000],
            "message": message,
            "created_at": now,
        }

    def upsert_research_chat_action(
        self,
        *,
        action_id: str,
        session_id: str,
        status: str,
        proposal: Dict[str, Any],
        result_ref: Optional[Dict[str, Any]] = None,
        error_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        intent = str(proposal.get("intent") or "")
        approval_scope = proposal.get("approvalScope")
        execution_target = str(proposal.get("executionTarget") or "")
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT created_at FROM research_chat_actions WHERE action_id = ?",
                (action_id,),
            ).fetchone()
            created_at = float(existing["created_at"]) if existing else now
            connection.execute(
                """
                INSERT OR REPLACE INTO research_chat_actions(
                    action_id, session_id, status, intent, approval_scope, execution_target,
                    proposal_json, result_ref_json, error_summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    session_id,
                    status,
                    intent,
                    approval_scope,
                    execution_target,
                    self._to_json(proposal),
                    self._to_json(result_ref or {}),
                    error_summary,
                    created_at,
                    now,
                ),
            )
            connection.execute(
                "UPDATE research_chat_sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
        return {
            "action_id": action_id,
            "session_id": session_id,
            "status": status,
            "intent": intent,
            "approval_scope": approval_scope,
            "execution_target": execution_target,
            "proposal": proposal,
            "result_ref": result_ref or {},
            "error_summary": error_summary,
            "created_at": created_at,
            "updated_at": now,
        }

    def get_research_chat_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_chat_actions WHERE action_id = ?",
                (action_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "action_id": row["action_id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "intent": row["intent"],
            "approval_scope": row["approval_scope"],
            "execution_target": row["execution_target"],
            "proposal": json.loads(row["proposal_json"]),
            "result_ref": json.loads(row["result_ref_json"]),
            "error_summary": row["error_summary"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_research_chat_sessions(self, *, run_id: Optional[str] = None, limit: int = 30) -> list[Dict[str, Any]]:
        max_items = max(1, min(limit, 100))
        with self._connection() as connection:
            if run_id:
                rows = connection.execute(
                    """
                    SELECT session_id, mode, run_id, title, context_json, created_at, updated_at
                    FROM research_chat_sessions
                    WHERE run_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (run_id, max_items),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT session_id, mode, run_id, title, context_json, created_at, updated_at
                    FROM research_chat_sessions
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (max_items,),
                ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "mode": row["mode"],
                "run_id": row["run_id"],
                "title": row["title"],
                "context": json.loads(row["context_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_research_chat_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            session_row = connection.execute(
                """
                SELECT session_id, mode, run_id, title, context_json, created_at, updated_at
                FROM research_chat_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if not session_row:
                return None
            message_rows = connection.execute(
                """
                SELECT message_id, role, text, message_json, created_at
                FROM research_chat_messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
            action_rows = connection.execute(
                """
                SELECT action_id, status, intent, approval_scope, execution_target,
                       proposal_json, result_ref_json, error_summary, created_at, updated_at
                FROM research_chat_actions
                WHERE session_id = ?
                ORDER BY updated_at DESC
                """,
                (session_id,),
            ).fetchall()
        return {
            "session_id": session_row["session_id"],
            "mode": session_row["mode"],
            "run_id": session_row["run_id"],
            "title": session_row["title"],
            "context": json.loads(session_row["context_json"]),
            "created_at": session_row["created_at"],
            "updated_at": session_row["updated_at"],
            "messages": [
                {
                    "message_id": row["message_id"],
                    "role": row["role"],
                    "text": row["text"],
                    "message": json.loads(row["message_json"]),
                    "created_at": row["created_at"],
                }
                for row in message_rows
            ],
            "actions": [
                {
                    "action_id": row["action_id"],
                    "status": row["status"],
                    "intent": row["intent"],
                    "approval_scope": row["approval_scope"],
                    "execution_target": row["execution_target"],
                    "proposal": json.loads(row["proposal_json"]),
                    "result_ref": json.loads(row["result_ref_json"]),
                    "error_summary": row["error_summary"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in action_rows
            ],
        }

    def get_hypothesis_evidence_links(self, run_id: str) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM hypothesis_evidence_links
                WHERE run_id = ?
                ORDER BY hypothesis_index ASC, created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [self._hypothesis_evidence_link_from_row(row) for row in rows]

    def get_evidence_retrievals(self, run_id: str) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM evidence_retrievals
                WHERE run_id = ?
                ORDER BY hypothesis_index ASC, created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "retrieval_id": row["retrieval_id"],
                "run_id": row["run_id"],
                "hypothesis_id": row["hypothesis_id"],
                "hypothesis_index": row["hypothesis_index"],
                "tool_name": row["tool_name"],
                "query": row["query"],
                "limit_value": row["limit_value"],
                "result_count": row["result_count"],
                "results": json.loads(row["results_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def record_research_tool_call(
        self,
        *,
        run_id: str,
        tool_name: str,
        phase: Optional[str],
        status: str,
        arguments: Dict[str, Any],
        result_summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_event_id: Optional[str] = None,
        agent: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS max_order FROM research_tool_calls WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            order_index = int(row["max_order"]) + 1
            connection.execute(
                """
                INSERT INTO research_tool_calls(
                    tool_call_id, run_id, trace_event_id, order_index, agent, phase,
                    tool_name, status, arguments_json, result_summary, metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"toolcall_{uuid.uuid4().hex[:12]}",
                    run_id,
                    trace_event_id,
                    order_index,
                    agent,
                    phase,
                    tool_name,
                    status,
                    self._to_json(arguments),
                    result_summary,
                    self._to_json(metadata or {}),
                    now,
                ),
            )

    def count_matching_tool_calls(
        self,
        *,
        run_id: str,
        tool_name: str,
        phase: Optional[str],
        arguments: Dict[str, Any],
    ) -> int:
        args_json = self._to_json(arguments)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM research_tool_calls
                WHERE run_id = ?
                  AND tool_name = ?
                  AND COALESCE(phase, '') = COALESCE(?, '')
                  AND arguments_json = ?
                """,
                (run_id, tool_name, phase, args_json),
            ).fetchone()
        return int(row["count"]) if row else 0

    def record_evidence_retrieval(
        self,
        *,
        run_id: str,
        tool_name: str,
        query: str,
        limit_value: int,
        results: list[Dict[str, Any]],
        hypothesis_id: Optional[str] = None,
        hypothesis_index: Optional[int] = None,
        retrieval_id: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO evidence_retrievals(
                    retrieval_id, run_id, hypothesis_id, hypothesis_index, tool_name,
                    query, limit_value, result_count, results_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    retrieval_id or f"retrieval_{uuid.uuid4().hex[:12]}",
                    run_id,
                    hypothesis_id,
                    hypothesis_index,
                    tool_name,
                    query,
                    limit_value,
                    len(results),
                    self._to_json(results),
                    now,
                ),
            )

    def store_tool_result(
        self,
        *,
        tool_name: str,
        phase: Optional[str],
        content: Any,
        run_id: Optional[str] = None,
        result_kind: str = "json",
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        content_json = self._to_json(content)
        result_id = f"tool_result_{uuid.uuid4().hex[:12]}"
        summary_text = summary or f"{tool_name} result stored as {result_kind}."
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO research_tool_results(
                    result_id, run_id, tool_name, phase, result_kind, summary,
                    content_json, content_size, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    run_id,
                    tool_name,
                    phase,
                    result_kind,
                    summary_text,
                    content_json,
                    len(content_json.encode("utf-8")),
                    now,
                ),
            )
        return {
            "result_id": result_id,
            "run_id": run_id,
            "tool_name": tool_name,
            "phase": phase,
            "result_kind": result_kind,
            "summary": summary_text,
            "content_size": len(content_json.encode("utf-8")),
            "created_at": now,
        }

    def get_tool_result(self, result_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_tool_results WHERE result_id = ?",
                (result_id,),
            ).fetchone()
        if not row:
            return None
        return self._tool_result_from_row(row, include_content=True)

    def list_tool_results(self, run_id: str, *, limit: int = 50) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM research_tool_results
                WHERE run_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (run_id, max(1, min(limit, 200))),
            ).fetchall()
        return [self._tool_result_from_row(row, include_content=False) for row in rows]

    def _tool_result_from_row(self, row: sqlite3.Row, *, include_content: bool) -> Dict[str, Any]:
        payload = {
            "result_id": row["result_id"],
            "run_id": row["run_id"],
            "tool_name": row["tool_name"],
            "phase": row["phase"],
            "result_kind": row["result_kind"],
            "summary": row["summary"],
            "content_size": row["content_size"],
            "created_at": row["created_at"],
        }
        if include_content:
            payload["content"] = json.loads(row["content_json"])
        return payload

    def create_background_job(
        self,
        *,
        job_id: str,
        workflow_name: str,
        phase: Optional[str],
        arguments: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO research_background_jobs(
                    job_id, run_id, workflow_name, phase, status, arguments_json,
                    result_ref_json, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    job_id,
                    run_id,
                    workflow_name,
                    phase,
                    "queued",
                    self._to_json(arguments),
                    self._to_json({}),
                    now,
                    now,
                ),
            )
        return self.get_background_job(job_id) or {}

    def update_background_job(
        self,
        job_id: str,
        *,
        status: str,
        result_ref: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE research_background_jobs
                SET status = ?, result_ref_json = ?, error_message = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    status,
                    self._to_json(result_ref or {}),
                    error_message,
                    time.time(),
                    job_id,
                ),
            )

    def get_background_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_background_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._background_job_from_row(row) if row else None

    def list_background_jobs(
        self,
        *,
        run_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            if run_id:
                rows = connection.execute(
                    """
                    SELECT * FROM research_background_jobs
                    WHERE run_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (run_id, max(1, min(limit, 200))),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM research_background_jobs
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (max(1, min(limit, 200)),),
                ).fetchall()
        return [self._background_job_from_row(row) for row in rows]

    def _background_job_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "run_id": row["run_id"],
            "workflow_name": row["workflow_name"],
            "phase": row["phase"],
            "status": row["status"],
            "arguments": json.loads(row["arguments_json"]),
            "result_ref": json.loads(row["result_ref_json"]),
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def enqueue_work_item(
        self,
        *,
        workflow_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        phase: Optional[str] = None,
        agent_role: Optional[str] = None,
        priority: int = 3,
        max_attempts: int = 3,
        work_item_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_workflow = workflow_name.strip()
        if not normalized_workflow:
            raise ValueError("work item requires workflow_name")
        normalized_run_id = (run_id or "").strip() or None
        normalized_id = (work_item_id or "").strip() or f"work_{uuid.uuid4().hex[:12]}"
        normalized_priority = max(1, min(int(priority or 3), 5))
        normalized_max_attempts = max(1, int(max_attempts or 1))
        if idempotency_key is None and normalized_workflow == "workflow.open_coscientist_run" and normalized_run_id:
            idempotency_key = f"{normalized_workflow}:{normalized_run_id}"
        now = time.time()

        with self._connection() as connection:
            existing = self._active_work_item_row(
                connection,
                workflow_name=normalized_workflow,
                run_id=normalized_run_id,
            )
            if existing:
                return self._work_item_from_row(existing)
            try:
                connection.execute(
                    """
                    INSERT INTO research_work_items(
                        work_item_id, idempotency_key, run_id, workflow_name, phase,
                        agent_role, status, priority, lease_owner, lease_expires_at,
                        attempt_count, max_attempts, arguments_json, result_ref_json,
                        error_message, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        normalized_id,
                        idempotency_key,
                        normalized_run_id,
                        normalized_workflow,
                        phase,
                        agent_role,
                        "queued",
                        normalized_priority,
                        normalized_max_attempts,
                        self._to_json(arguments or {}),
                        self._to_json({}),
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                row = None
                if idempotency_key:
                    row = connection.execute(
                        "SELECT * FROM research_work_items WHERE idempotency_key = ?",
                        (idempotency_key,),
                    ).fetchone()
                row = row or self._active_work_item_row(
                    connection,
                    workflow_name=normalized_workflow,
                    run_id=normalized_run_id,
                )
                if row:
                    return self._work_item_from_row(row)
                raise
        return self.get_work_item(normalized_id) or {}

    def get_work_item(self, work_item_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_work_items WHERE work_item_id = ?",
                (work_item_id,),
            ).fetchone()
        return self._work_item_from_row(row) if row else None

    def list_work_items(
        self,
        *,
        status: Optional[str] = None,
        run_id: Optional[str] = None,
        workflow_name: Optional[str] = None,
        limit: int = 50,
    ) -> list[Dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if workflow_name:
            clauses.append("workflow_name = ?")
            params.append(workflow_name)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 200)))
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM research_work_items
                {where}
                ORDER BY priority ASC, updated_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._work_item_from_row(row) for row in rows]

    def work_item_status_counts(
        self,
        *,
        run_id: Optional[str] = None,
        workflow_name: Optional[str] = None,
    ) -> Dict[str, int]:
        clauses: list[str] = []
        params: list[Any] = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if workflow_name:
            clauses.append("workflow_name = ?")
            params.append(workflow_name)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT status, COUNT(*) AS count
                FROM research_work_items
                {where}
                GROUP BY status
                """,
                tuple(params),
            ).fetchall()
        counts = {
            status: 0
            for status in ("queued", "leased", "running", "retrying", "blocked", "complete", "error", "cancelled")
        }
        for row in rows:
            counts[str(row["status"])] = int(row["count"])
        counts["active"] = sum(counts.get(status, 0) for status in ACTIVE_WORK_ITEM_STATUSES)
        return counts

    def active_work_item_snapshot(
        self,
        *,
        run_id: Optional[str] = None,
        workflow_name: Optional[str] = None,
        limit: int = 20,
        include_internal_refs: bool = False,
    ) -> Dict[str, Any]:
        """Return a UI-safe summary of active work without raw arguments/results."""
        clauses = [f"status IN ({', '.join('?' for _ in ACTIVE_WORK_ITEM_STATUSES)})"]
        params: list[Any] = [*ACTIVE_WORK_ITEM_STATUSES]
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if workflow_name:
            clauses.append("workflow_name = ?")
            params.append(workflow_name)
        params.append(max(1, min(limit, 100)))
        where = f"WHERE {' AND '.join(clauses)}"
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM research_work_items
                {where}
                ORDER BY priority ASC, updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return {
            "generated_at": time.time(),
            "filters": {
                "run_id": run_id if include_internal_refs else bool(run_id),
                "workflow_name": workflow_name,
                "limit": max(1, min(limit, 100)),
            },
            "counts": self.work_item_status_counts(run_id=run_id, workflow_name=workflow_name),
            "active_statuses": list(ACTIVE_WORK_ITEM_STATUSES),
            "items": [
                self._work_item_snapshot_from_row(row, include_internal_refs=include_internal_refs)
                for row in rows
            ],
            "visibility_boundary": (
                "Default snapshot omits work item arguments, result payloads, worker internals, "
                "and raw IDs unless include_internal_refs is explicitly enabled."
            ),
        }

    def lease_work_items(self, *, owner: str, limit: int = 1, lease_seconds: int = 300) -> list[Dict[str, Any]]:
        normalized_owner = owner.strip()
        if not normalized_owner:
            raise ValueError("work item lease requires owner")
        now = time.time()
        lease_until = now + max(1, int(lease_seconds or 1))
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT work_item_id
                FROM research_work_items
                WHERE status IN (?, ?)
                  AND attempt_count < max_attempts
                ORDER BY priority ASC, created_at ASC
                LIMIT ?
                """,
                (*LEASEABLE_WORK_ITEM_STATUSES, max(1, min(limit, 50))),
            ).fetchall()
            work_item_ids = [row["work_item_id"] for row in rows]
            for work_item_id in work_item_ids:
                connection.execute(
                    """
                    UPDATE research_work_items
                    SET status = 'leased',
                        lease_owner = ?,
                        lease_expires_at = ?,
                        attempt_count = attempt_count + 1,
                        updated_at = ?
                    WHERE work_item_id = ?
                      AND status IN (?, ?)
                    """,
                    (normalized_owner, lease_until, now, work_item_id, *LEASEABLE_WORK_ITEM_STATUSES),
                )
            leased_rows = []
            if work_item_ids:
                placeholders = ", ".join("?" for _ in work_item_ids)
                leased_rows = connection.execute(
                    f"SELECT * FROM research_work_items WHERE work_item_id IN ({placeholders})",
                    work_item_ids,
                ).fetchall()
            connection.commit()
            return [self._work_item_from_row(row) for row in leased_rows]
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_work_item_running(self, work_item_id: str, owner: str) -> bool:
        now = time.time()
        with self._connection() as connection:
            result = connection.execute(
                """
                UPDATE research_work_items
                SET status = 'running', updated_at = ?
                WHERE work_item_id = ?
                  AND lease_owner = ?
                  AND status IN ('leased', 'running')
                  AND (lease_expires_at IS NULL OR lease_expires_at > ?)
                """,
                (now, work_item_id, owner, now),
            )
        return result.rowcount > 0

    def renew_work_item_lease(self, work_item_id: str, owner: str, lease_seconds: int = 300) -> bool:
        now = time.time()
        lease_until = now + max(1, int(lease_seconds or 1))
        with self._connection() as connection:
            result = connection.execute(
                """
                UPDATE research_work_items
                SET lease_expires_at = ?,
                    updated_at = ?
                WHERE work_item_id = ?
                  AND lease_owner = ?
                  AND status IN ('leased', 'running')
                  AND (lease_expires_at IS NULL OR lease_expires_at > ?)
                """,
                (lease_until, now, work_item_id, owner, now),
            )
        return result.rowcount > 0

    def complete_work_item(self, work_item_id: str, result_ref: Optional[Dict[str, Any]] = None) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE research_work_items
                SET status = 'complete',
                    result_ref_json = ?,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_message = NULL,
                    updated_at = ?
                WHERE work_item_id = ?
                """,
                (self._to_json(result_ref or {}), time.time(), work_item_id),
            )

    def fail_work_item(self, work_item_id: str, error: str, *, retryable: bool = True) -> None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT attempt_count, max_attempts FROM research_work_items WHERE work_item_id = ?",
                (work_item_id,),
            ).fetchone()
            if not row:
                return
            should_retry = retryable and int(row["attempt_count"]) < int(row["max_attempts"])
            connection.execute(
                """
                UPDATE research_work_items
                SET status = ?,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_message = ?,
                    updated_at = ?
                WHERE work_item_id = ?
                """,
                ("retrying" if should_retry else "error", error, time.time(), work_item_id),
            )

    def block_work_item(self, work_item_id: str, reason: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE research_work_items
                SET status = 'blocked',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_message = ?,
                    updated_at = ?
                WHERE work_item_id = ?
                """,
                (reason, time.time(), work_item_id),
            )

    def unblock_work_item(self, work_item_id: str, reason: str = "Unblocked for retry.") -> bool:
        with self._connection() as connection:
            result = connection.execute(
                """
                UPDATE research_work_items
                SET status = 'retrying',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_message = ?,
                    updated_at = ?
                WHERE work_item_id = ?
                  AND status = 'blocked'
                """,
                (reason, time.time(), work_item_id),
            )
        return result.rowcount > 0

    def cancel_work_item(self, work_item_id: str, reason: str = "cancelled") -> bool:
        placeholders = ", ".join("?" for _ in ACTIVE_WORK_ITEM_STATUSES)
        with self._connection() as connection:
            result = connection.execute(
                f"""
                UPDATE research_work_items
                SET status = 'cancelled',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_message = ?,
                    updated_at = ?
                WHERE work_item_id = ?
                  AND status IN ({placeholders})
                """,
                (reason, time.time(), work_item_id, *ACTIVE_WORK_ITEM_STATUSES),
            )
        return result.rowcount > 0

    def recover_expired_leases(self, now: Optional[float] = None) -> int:
        current_time = time.time() if now is None else float(now)
        with self._connection() as connection:
            retry_result = connection.execute(
                """
                UPDATE research_work_items
                SET status = 'retrying',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_message = COALESCE(error_message, 'Lease expired before completion.'),
                    updated_at = ?
                WHERE status IN ('leased', 'running')
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= ?
                  AND attempt_count < max_attempts
                """,
                (current_time, current_time),
            )
            error_result = connection.execute(
                """
                UPDATE research_work_items
                SET status = 'error',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    error_message = COALESCE(error_message, 'Lease expired and retry budget is exhausted.'),
                    updated_at = ?
                WHERE status IN ('leased', 'running')
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= ?
                  AND attempt_count >= max_attempts
                """,
                (current_time, current_time),
            )
        return max(0, retry_result.rowcount) + max(0, error_result.rowcount)

    def store_feedback_item(
        self,
        *,
        text: str,
        target_type: str = "run",
        feedback_type: str = "critique",
        target_ref: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        source: str = "user",
        feedback_id: Optional[str] = None,
        created_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        normalized_text = text.strip()
        if not normalized_text:
            raise ValueError("feedback text cannot be empty")
        normalized_id = (feedback_id or "").strip() or f"feedback_{uuid.uuid4().hex[:12]}"
        timestamp = time.time() if created_at is None else float(created_at)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO research_feedback(
                    feedback_id, run_id, target_type, target_ref_json, feedback_type,
                    text, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_id,
                    run_id,
                    target_type,
                    self._to_json(target_ref or {}),
                    feedback_type,
                    normalized_text,
                    source,
                    timestamp,
                ),
            )
        return self.get_feedback_item(normalized_id) or {}

    def get_feedback_item(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_feedback WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        return self._feedback_from_row(row) if row else None

    def list_feedback_items(
        self,
        *,
        run_id: Optional[str] = None,
        target_type: Optional[str] = None,
        feedback_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[Dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if target_type:
            clauses.append("target_type = ?")
            params.append(target_type)
        if feedback_type:
            clauses.append("feedback_type = ?")
            params.append(feedback_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 200)))
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM research_feedback
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._feedback_from_row(row) for row in rows]

    def persist_checkpoint_metadata(
        self,
        *,
        run_id: str,
        thread_id: str,
        status: str,
        checkpoint_backend: str,
        phase: Optional[str] = None,
        checkpoint_ref: Optional[str] = None,
        state_summary: Optional[Dict[str, Any]] = None,
        checkpoint_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_run_id = run_id.strip()
        normalized_thread_id = thread_id.strip()
        if not normalized_run_id or not normalized_thread_id:
            raise ValueError("checkpoint metadata requires run_id and thread_id")
        normalized_id = (checkpoint_id or "").strip() or f"checkpoint_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT created_at FROM research_checkpoints WHERE checkpoint_id = ?",
                (normalized_id,),
            ).fetchone()
            created_at = float(existing["created_at"]) if existing else now
            connection.execute(
                """
                INSERT OR REPLACE INTO research_checkpoints(
                    checkpoint_id, run_id, thread_id, phase, status, checkpoint_backend,
                    checkpoint_ref, state_summary_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_id,
                    normalized_run_id,
                    normalized_thread_id,
                    phase,
                    status,
                    checkpoint_backend,
                    checkpoint_ref,
                    self._to_json(state_summary or {}),
                    created_at,
                    now,
                ),
            )
        return self.get_checkpoint_metadata(normalized_id) or {}

    def persist_checkpoint_metadata_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(record or {})
        run_id = str(normalized.get("run_id") or "").strip()
        thread_id = str(normalized.get("thread_id") or "").strip()
        if not run_id or not thread_id:
            raise ValueError("checkpoint metadata record requires run_id and thread_id")
        if thread_id != run_id:
            raise ValueError("checkpoint metadata record requires thread_id to match run_id")
        return self.persist_checkpoint_metadata(
            checkpoint_id=str(normalized.get("checkpoint_id") or "").strip() or None,
            run_id=run_id,
            thread_id=thread_id,
            phase=str(normalized.get("phase") or "").strip() or None,
            status=str(normalized.get("status") or "saved").strip() or "saved",
            checkpoint_backend=str(normalized.get("checkpoint_backend") or "sqlite_metadata").strip(),
            checkpoint_ref=normalized.get("checkpoint_ref"),
            state_summary=normalized.get("state_summary") if isinstance(normalized.get("state_summary"), dict) else {},
        )

    def get_checkpoint_metadata(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
        return self._checkpoint_from_row(row) if row else None

    def list_checkpoint_metadata(self, *, run_id: str, limit: int = 20) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM research_checkpoints
                WHERE run_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (run_id, max(1, min(limit, 200))),
            ).fetchall()
        return [self._checkpoint_from_row(row) for row in rows]

    def latest_checkpoint_metadata(self, run_id: str) -> Optional[Dict[str, Any]]:
        checkpoints = self.list_checkpoint_metadata(run_id=run_id, limit=1)
        return checkpoints[0] if checkpoints else None

    def checkpoint_status_summary(self, run_id: str) -> Dict[str, Any]:
        normalized_run_id = (run_id or "").strip()
        latest = self.latest_checkpoint_metadata(normalized_run_id) if normalized_run_id else None
        if not latest:
            return {
                "status": "not_available",
                "run_id": normalized_run_id or None,
                "checkpoint_available": False,
                "resume_supported": False,
                "resume_mode": "none",
                "latest_checkpoint": None,
                "resume_config_fields": [],
                "boundary": "No checkpoint metadata has been persisted for this run.",
            }

        backend = str(latest.get("checkpoint_backend") or "")
        resume_supported = backend == "langgraph_sqlite"
        return {
            "status": "ready" if resume_supported else "limited",
            "run_id": normalized_run_id,
            "thread_id": latest.get("thread_id"),
            "checkpoint_available": True,
            "resume_supported": resume_supported,
            "resume_mode": "langgraph_thread_resume" if resume_supported else "metadata_only_retry",
            "latest_checkpoint": {
                "checkpoint_id": latest.get("checkpoint_id"),
                "phase": latest.get("phase"),
                "status": latest.get("status"),
                "checkpoint_backend": backend,
                "checkpoint_ref": latest.get("checkpoint_ref"),
                "updated_at": latest.get("updated_at"),
                "state_summary": latest.get("state_summary") or {},
            },
            "resume_config_fields": ["thread_id", "checkpoint_id", "checkpoint_ns"] if resume_supported else ["thread_id"],
            "boundary": (
                "Latest checkpoint can be used with LangGraph thread resume."
                if resume_supported
                else "Checkpoint metadata is available for audit/retry guidance, but full LangGraph state resume remains limited."
            ),
        }

    def build_memory_context(
        self,
        *,
        research_goal: str,
        parent_run_id: Optional[str] = None,
        library_id: Optional[str] = None,
        memory_scope: str = "project",
        max_runs: int = 5,
        max_hypotheses: int = 8,
        max_evidence: int = 8,
    ) -> Dict[str, Any]:
        normalized_scope = memory_scope if memory_scope in {"current_run", "project", "library", "global"} else "project"
        parent_run = self.get_research_run(parent_run_id) if parent_run_id else None
        recent_runs = [] if normalized_scope == "current_run" else self.list_research_runs(limit=max_runs + 1)
        related_runs = [
            self._run_memory_summary(item)
            for item in recent_runs
            if item.get("run_id") and item.get("run_id") != parent_run_id
        ][:max(0, max_runs)]
        prior_hypotheses = []
        if isinstance(parent_run, dict):
            hypotheses = parent_run.get("hypotheses") if isinstance(parent_run.get("hypotheses"), list) else []
            prior_hypotheses = [self._hypothesis_memory_summary(item) for item in hypotheses[: max(0, max_hypotheses)]]

        feedback_run_id = parent_run_id if parent_run_id else None
        feedback_items = self.list_feedback_items(run_id=feedback_run_id, limit=20) if feedback_run_id else []
        execution_memory = (
            self.checkpoint_status_summary(parent_run_id)
            if parent_run_id
            else self.checkpoint_status_summary("")
        )
        if normalized_scope == "current_run":
            evidence_summaries = []
            known_gaps = ["current_run scope does not retrieve project, library, or global evidence memory."]
        else:
            evidence_library_id = (library_id or DEFAULT_LIBRARY_ID) if normalized_scope == "library" else None
            retrieved_evidence = self.search_chunks(
                research_goal,
                limit=max(1, max_evidence),
                library_id=evidence_library_id,
            )
            prioritized_evidence = [
                item
                for _, item in sorted(
                    enumerate(retrieved_evidence),
                    key=lambda pair: (-self._evidence_memory_priority(pair[1]), pair[0]),
                )
            ]
            evidence_summaries = [
                self._evidence_memory_summary(item)
                for item in prioritized_evidence
            ]
            known_gaps = []
        memory_sources = self._memory_source_types(
            parent_run=parent_run,
            related_runs=related_runs,
            prior_hypotheses=prior_hypotheses,
            feedback_items=feedback_items,
            evidence_summaries=evidence_summaries,
            known_gaps=known_gaps,
        )
        return {
            "memory_scope": normalized_scope,
            "parent_run": self._run_memory_summary(parent_run) if isinstance(parent_run, dict) else None,
            "related_runs": related_runs,
            "prior_hypotheses": prior_hypotheses,
            "user_feedback": feedback_items,
            "execution_memory": execution_memory,
            "evidence_summaries": evidence_summaries,
            "memory_sources": memory_sources,
            "evidence_boundary": self._evidence_memory_boundary(evidence_summaries),
            "known_gaps": known_gaps,
            "injection_policy": self._memory_injection_policy(
                memory_scope=normalized_scope,
                memory_sources=memory_sources,
                parent_run=parent_run,
                related_runs=related_runs,
                prior_hypotheses=prior_hypotheses,
                feedback_items=feedback_items,
                evidence_summaries=evidence_summaries,
                known_gaps=known_gaps,
            ),
            "memory_boundary": "Summaries only; raw records are not injected.",
        }

    def memory_context_surface_summary(
        self,
        memory_context: Dict[str, Any],
        *,
        include_internal_refs: bool = False,
    ) -> Dict[str, Any]:
        parent_run = memory_context.get("parent_run")
        execution_memory = (
            memory_context.get("execution_memory")
            if isinstance(memory_context.get("execution_memory"), dict)
            else {}
        )
        evidence_boundary = (
            memory_context.get("evidence_boundary")
            if isinstance(memory_context.get("evidence_boundary"), dict)
            else {}
        )
        user_feedback = (
            memory_context.get("user_feedback")
            if isinstance(memory_context.get("user_feedback"), list)
            else []
        )
        prior_hypotheses = (
            memory_context.get("prior_hypotheses")
            if isinstance(memory_context.get("prior_hypotheses"), list)
            else []
        )
        related_runs = (
            memory_context.get("related_runs")
            if isinstance(memory_context.get("related_runs"), list)
            else []
        )
        evidence_summaries = (
            memory_context.get("evidence_summaries")
            if isinstance(memory_context.get("evidence_summaries"), list)
            else []
        )
        known_gaps = (
            memory_context.get("known_gaps")
            if isinstance(memory_context.get("known_gaps"), list)
            else []
        )
        summary = {
            "memory_scope": memory_context.get("memory_scope") or "project",
            "memory_sources": list(memory_context.get("memory_sources") or []),
            "parent_run": self._memory_surface_parent_run(parent_run, include_internal_refs=include_internal_refs),
            "counts": {
                "related_runs": len(related_runs),
                "prior_hypotheses": len(prior_hypotheses),
                "user_feedback": len(user_feedback),
                "evidence_sources": len(evidence_summaries),
                "known_gaps": len(known_gaps),
            },
            "feedback_types": self._feedback_type_counts(user_feedback),
            "execution_memory": self._execution_memory_surface_summary(
                execution_memory,
                include_internal_refs=include_internal_refs,
            ),
            "evidence_boundary": {
                "status": evidence_boundary.get("status") or "absent",
                "evidence_count": int(evidence_boundary.get("evidence_count") or 0),
                "parsed_fulltext_count": int(evidence_boundary.get("parsed_fulltext_count") or 0),
                "experimental_data_count": int(evidence_boundary.get("experimental_data_count") or 0),
            },
            "known_gap_summaries": [self._safe_work_item_text(str(item), max_length=160) for item in known_gaps[:3]],
            "visibility_boundary": (
                "Memory surface summaries expose counts and boundaries by default; raw feedback text, "
                "hypothesis text, checkpoint refs, and retrieval diagnostics require explicit expert disclosure."
            ),
        }
        if include_internal_refs:
            summary["internal_refs"] = {
                "feedback_ids": [
                    item.get("feedback_id")
                    for item in user_feedback
                    if isinstance(item, dict) and item.get("feedback_id")
                ],
                "hypothesis_ids": [
                    item.get("hypothesis_id")
                    for item in prior_hypotheses
                    if isinstance(item, dict) and item.get("hypothesis_id")
                ],
                "evidence_refs": [
                    {
                        "paper_id": item.get("paper_id"),
                        "chunk_id": item.get("chunk_id"),
                        "library_id": item.get("library_id"),
                    }
                    for item in evidence_summaries
                    if isinstance(item, dict)
                ][:10],
            }
        return summary

    def _active_work_item_row(
        self,
        connection: sqlite3.Connection,
        *,
        workflow_name: str,
        run_id: Optional[str],
    ) -> Optional[sqlite3.Row]:
        if not run_id or workflow_name != "workflow.open_coscientist_run":
            return None
        placeholders = ", ".join("?" for _ in ACTIVE_WORK_ITEM_STATUSES)
        return connection.execute(
            f"""
            SELECT * FROM research_work_items
            WHERE workflow_name = ?
              AND run_id = ?
              AND status IN ({placeholders})
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (workflow_name, run_id, *ACTIVE_WORK_ITEM_STATUSES),
        ).fetchone()

    def _work_item_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "work_item_id": row["work_item_id"],
            "idempotency_key": row["idempotency_key"],
            "run_id": row["run_id"],
            "workflow_name": row["workflow_name"],
            "phase": row["phase"],
            "agent_role": row["agent_role"],
            "status": row["status"],
            "priority": row["priority"],
            "lease_owner": row["lease_owner"],
            "lease_expires_at": row["lease_expires_at"],
            "attempt_count": row["attempt_count"],
            "max_attempts": row["max_attempts"],
            "arguments": json.loads(row["arguments_json"]),
            "result_ref": json.loads(row["result_ref_json"]),
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _work_item_snapshot_from_row(
        self,
        row: sqlite3.Row,
        *,
        include_internal_refs: bool = False,
    ) -> Dict[str, Any]:
        status = str(row["status"])
        attempt_count = int(row["attempt_count"] or 0)
        max_attempts = int(row["max_attempts"] or 0)
        snapshot = {
            "workflow_name": row["workflow_name"],
            "workflow_label": self._work_item_workflow_label(row["workflow_name"]),
            "phase": row["phase"],
            "agent_role": row["agent_role"],
            "status": status,
            "status_label": self._work_item_status_label(status),
            "priority": int(row["priority"] or 0),
            "attempts": {
                "current": attempt_count,
                "max": max_attempts,
                "remaining": max(0, max_attempts - attempt_count),
            },
            "recoverable": status in {"queued", "retrying", "blocked"},
            "next_action": self._work_item_next_action(status),
            "error_summary": self._safe_work_item_text(row["error_message"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if include_internal_refs:
            snapshot.update(
                {
                    "work_item_id": row["work_item_id"],
                    "idempotency_key": row["idempotency_key"],
                    "run_id": row["run_id"],
                    "lease_owner": row["lease_owner"],
                    "lease_expires_at": row["lease_expires_at"],
                }
            )
        return snapshot

    @staticmethod
    def _work_item_status_label(status: str) -> str:
        return {
            "queued": "Queued for background execution",
            "leased": "Claimed by a worker",
            "running": "Running",
            "retrying": "Waiting to retry",
            "blocked": "Waiting for manual recovery",
            "complete": "Complete",
            "error": "Failed",
            "cancelled": "Cancelled",
        }.get(status, status.replace("_", " ").title())

    @staticmethod
    def _work_item_next_action(status: str) -> str:
        return {
            "queued": "Wait for a worker tick or start the background worker.",
            "leased": "Wait for the active worker to start execution.",
            "running": "Monitor progress from the run timeline.",
            "retrying": "Wait for retry or inspect the previous failure.",
            "blocked": "Resolve the manual recovery condition, then unblock the task.",
            "complete": "Open the completed run or result.",
            "error": "Inspect the failure and enqueue a new task if appropriate.",
            "cancelled": "Create a new task if the work is still needed.",
        }.get(status, "Inspect the task state before taking action.")

    @staticmethod
    def _work_item_workflow_label(workflow_name: str) -> str:
        return {
            "workflow.open_coscientist_run": "Research run",
            "workflow.demo_coscientist_run": "Demo research run",
            "tool.pdf_parse": "PDF parsing",
            "tool.web_evidence": "Web evidence capture",
        }.get(workflow_name, workflow_name.replace("_", " ").replace(".", " / "))

    @staticmethod
    def _safe_work_item_text(value: Optional[str], *, max_length: int = 180) -> Optional[str]:
        if not value:
            return None
        compact = re.sub(r"\s+", " ", str(value)).strip()
        if len(compact) <= max_length:
            return compact
        return f"{compact[: max_length - 3].rstrip()}..."

    def _memory_surface_parent_run(
        self,
        parent_run: Any,
        *,
        include_internal_refs: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(parent_run, dict):
            return None
        summary = {
            "research_goal": parent_run.get("research_goal") or "",
            "status": parent_run.get("status"),
            "hypothesis_count": int(parent_run.get("hypothesis_count") or 0),
            "updated_at": parent_run.get("updated_at"),
        }
        if include_internal_refs:
            summary["run_id"] = parent_run.get("run_id")
        return summary

    def _execution_memory_surface_summary(
        self,
        execution_memory: Dict[str, Any],
        *,
        include_internal_refs: bool = False,
    ) -> Dict[str, Any]:
        latest_checkpoint = (
            execution_memory.get("latest_checkpoint")
            if isinstance(execution_memory.get("latest_checkpoint"), dict)
            else {}
        )
        summary = {
            "status": execution_memory.get("status") or "not_available",
            "checkpoint_available": bool(execution_memory.get("checkpoint_available")),
            "resume_supported": bool(execution_memory.get("resume_supported")),
            "resume_mode": execution_memory.get("resume_mode"),
            "phase": latest_checkpoint.get("phase"),
        }
        if include_internal_refs:
            summary["checkpoint_id"] = latest_checkpoint.get("checkpoint_id")
            summary["checkpoint_backend"] = latest_checkpoint.get("checkpoint_backend")
            summary["checkpoint_ref"] = latest_checkpoint.get("checkpoint_ref")
        return summary

    @staticmethod
    def _feedback_type_counts(feedback_items: list[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in feedback_items:
            if not isinstance(item, dict):
                continue
            feedback_type = str(item.get("feedback_type") or "unknown")
            counts[feedback_type] = counts.get(feedback_type, 0) + 1
        return counts

    def _feedback_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "feedback_id": row["feedback_id"],
            "run_id": row["run_id"],
            "target_type": row["target_type"],
            "target_ref": json.loads(row["target_ref_json"]),
            "feedback_type": row["feedback_type"],
            "text": row["text"],
            "source": row["source"],
            "created_at": row["created_at"],
        }

    def _checkpoint_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "checkpoint_id": row["checkpoint_id"],
            "run_id": row["run_id"],
            "thread_id": row["thread_id"],
            "phase": row["phase"],
            "status": row["status"],
            "checkpoint_backend": row["checkpoint_backend"],
            "checkpoint_ref": row["checkpoint_ref"],
            "state_summary": json.loads(row["state_summary_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _run_memory_summary(self, run: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not run:
            return None
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        hypotheses = run.get("hypotheses") if isinstance(run.get("hypotheses"), list) else []
        return {
            "run_id": run.get("run_id"),
            "research_goal": request.get("research_goal", ""),
            "status": run.get("status"),
            "hypothesis_count": len(hypotheses),
            "summary": metrics.get("summary") or metrics.get("completion_summary") or "",
            "updated_at": run.get("updated_at"),
        }

    def _hypothesis_memory_summary(self, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "hypothesis_id": hypothesis.get("id") or hypothesis.get("hypothesis_id"),
            "text": self._first_text(hypothesis, ("text", "hypothesis", "technical_hypothesis"))[:1000],
            "explanation": self._first_text(hypothesis, ("explanation", "plain_explanation", "rationale"))[:700],
            "elo_rating": hypothesis.get("elo_rating") or hypothesis.get("elo"),
            "support_level": hypothesis.get("support_level") or hypothesis.get("evidence_support_level"),
        }

    def _evidence_memory_summary(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "paper_id": evidence.get("paper_id"),
            "library_id": evidence.get("library_id"),
            "chunk_id": evidence.get("chunk_id"),
            "title": evidence.get("title"),
            "section_type": evidence.get("section_type"),
            "source_reliability": evidence.get("source_reliability"),
            "support_level": evidence.get("support_level"),
            "snippet": str(evidence.get("text") or evidence.get("snippet") or evidence.get("text_preview") or "")[:700],
            "experiment_data_summary": evidence.get("experiment_data_summary"),
            "memory_priority": self._evidence_memory_priority(evidence),
        }

    def _evidence_memory_priority(self, evidence: Dict[str, Any]) -> int:
        support_level = str(evidence.get("support_level") or "")
        source_reliability = str(evidence.get("source_reliability") or "")
        if support_level == "experimental_data":
            return 40
        if source_reliability == "parsed_fulltext":
            return 30
        if support_level == "fulltext":
            return 20
        if support_level == "abstract":
            return 10
        return 0

    def _memory_source_types(
        self,
        *,
        parent_run: Optional[Dict[str, Any]],
        related_runs: list[Dict[str, Any]],
        prior_hypotheses: list[Dict[str, Any]],
        feedback_items: list[Dict[str, Any]],
        evidence_summaries: list[Dict[str, Any]],
        known_gaps: list[str],
    ) -> list[str]:
        sources: list[str] = []
        if isinstance(parent_run, dict):
            sources.append("parent_run")
        if related_runs:
            sources.append("related_runs")
        if prior_hypotheses:
            sources.append("prior_hypotheses")
        if feedback_items:
            sources.append("chat_feedback")
        if evidence_summaries:
            sources.append("knowledge_base")
        if known_gaps:
            sources.append("memory_limitations")
        return sources

    def _memory_injection_policy(
        self,
        *,
        memory_scope: str,
        memory_sources: list[str],
        parent_run: Optional[Dict[str, Any]],
        related_runs: list[Dict[str, Any]],
        prior_hypotheses: list[Dict[str, Any]],
        feedback_items: list[Dict[str, Any]],
        evidence_summaries: list[Dict[str, Any]],
        known_gaps: list[str],
    ) -> Dict[str, Any]:
        evidence_boundary = self._evidence_memory_boundary(evidence_summaries)
        prompt_sections: list[str] = []
        if isinstance(parent_run, dict):
            prompt_sections.append("parent_run_summary")
        if related_runs:
            prompt_sections.append("related_run_summaries")
        if prior_hypotheses:
            prompt_sections.append("prior_hypothesis_summaries")
        if feedback_items:
            prompt_sections.append("feedback_type_and_target_summary")
        if evidence_summaries:
            prompt_sections.append("evidence_boundary_and_snippet_summaries")
        if known_gaps:
            prompt_sections.append("memory_limitations")
        return {
            "mode": "summary_only",
            "memory_scope": memory_scope,
            "memory_sources": list(memory_sources),
            "prompt_sections": prompt_sections,
            "counts": {
                "related_runs": len(related_runs),
                "prior_hypotheses": len(prior_hypotheses),
                "feedback_items": len(feedback_items),
                "evidence_summaries": len(evidence_summaries),
                "known_gaps": len(known_gaps),
            },
            "evidence_status": evidence_boundary["status"],
            "raw_injection_allowed": False,
            "excluded_raw_fields": [
                "chat_message_bodies",
                "feedback_text",
                "hypothesis_full_text",
                "checkpoint_state",
                "tool_result_json",
                "provider_payloads",
                "full_pdf_chunks",
            ],
            "target_prompts": ["supervisor", "generate", "review", "ranking"],
            "boundary": (
                "Memory injection uses summary-only guidance for planning, generation, review, and ranking; "
                "raw chat, feedback, checkpoint, tool result, provider, and fulltext payloads stay out of prompts."
            ),
        }

    def _evidence_memory_boundary(self, evidence_summaries: list[Dict[str, Any]]) -> Dict[str, Any]:
        source_reliability_counts: Dict[str, int] = {}
        support_level_counts: Dict[str, int] = {}
        for evidence in evidence_summaries:
            reliability = str(evidence.get("source_reliability") or "unknown")
            support_level = str(evidence.get("support_level") or "unknown")
            source_reliability_counts[reliability] = source_reliability_counts.get(reliability, 0) + 1
            support_level_counts[support_level] = support_level_counts.get(support_level, 0) + 1

        evidence_count = len(evidence_summaries)
        parsed_fulltext_count = source_reliability_counts.get("parsed_fulltext", 0)
        experimental_data_count = support_level_counts.get("experimental_data", 0)
        status = "absent"
        if evidence_count:
            status = "parsed_fulltext" if parsed_fulltext_count else "limited"
            if experimental_data_count:
                status = "experimental_data"

        return {
            "status": status,
            "evidence_count": evidence_count,
            "parsed_fulltext_count": parsed_fulltext_count,
            "experimental_data_count": experimental_data_count,
            "source_reliability_counts": source_reliability_counts,
            "support_level_counts": support_level_counts,
            "boundary": (
                "Evidence memory is summary-only. parsed_fulltext and experimental_data are stronger "
                "than abstract, metadata, public_html, or unknown sources; absent evidence is not support."
            ),
        }

    def create_research_task(
        self,
        *,
        task_id: str,
        title: str,
        task_type: str,
        status: str = "backlog",
        priority: int = 3,
        phase: Optional[str] = None,
        run_id: Optional[str] = None,
        target_ref: Optional[Dict[str, Any]] = None,
        result_ref: Optional[Dict[str, Any]] = None,
        notes: str = "",
        blocked_reason: Optional[str] = None,
        due_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO research_tasks(
                    task_id, run_id, title, task_type, status, priority, phase,
                    target_ref_json, result_ref_json, notes, blocked_reason,
                    due_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    run_id,
                    title,
                    task_type,
                    status,
                    priority,
                    phase,
                    self._to_json(target_ref or {}),
                    self._to_json(result_ref or {}),
                    notes,
                    blocked_reason,
                    due_at,
                    now,
                    now,
                ),
            )
        return self.get_research_task(task_id) or {}

    def update_research_task(
        self,
        task_id: str,
        *,
        title: Optional[str] = None,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        phase: Optional[str] = None,
        target_ref: Optional[Dict[str, Any]] = None,
        result_ref: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        blocked_reason: Optional[str] = None,
        due_at: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        current = self.get_research_task(task_id)
        if not current:
            return None
        updated = {
            "title": current["title"] if title is None else title,
            "task_type": current["task_type"] if task_type is None else task_type,
            "status": current["status"] if status is None else status,
            "priority": current["priority"] if priority is None else priority,
            "phase": current["phase"] if phase is None else phase,
            "target_ref": current["target_ref"] if target_ref is None else target_ref,
            "result_ref": current["result_ref"] if result_ref is None else result_ref,
            "notes": current["notes"] if notes is None else notes,
            "blocked_reason": current["blocked_reason"] if blocked_reason is None else blocked_reason,
            "due_at": current["due_at"] if due_at is None else due_at,
        }
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE research_tasks
                SET title = ?, task_type = ?, status = ?, priority = ?, phase = ?,
                    target_ref_json = ?, result_ref_json = ?, notes = ?,
                    blocked_reason = ?, due_at = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    updated["title"],
                    updated["task_type"],
                    updated["status"],
                    updated["priority"],
                    updated["phase"],
                    self._to_json(updated["target_ref"]),
                    self._to_json(updated["result_ref"]),
                    updated["notes"],
                    updated["blocked_reason"],
                    updated["due_at"],
                    time.time(),
                    task_id,
                ),
            )
        return self.get_research_task(task_id)

    def get_research_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._research_task_from_row(row) if row else None

    def list_research_tasks(
        self,
        *,
        run_id: Optional[str] = None,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if run_id:
            where.append("run_id = ?")
            params.append(run_id)
        if status:
            where.append("status = ?")
            params.append(status)
        if task_type:
            where.append("task_type = ?")
            params.append(task_type)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(max(1, min(limit, 300)))
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM research_tasks
                {where_clause}
                ORDER BY priority ASC, updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._research_task_from_row(row) for row in rows]

    def _research_task_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "task_id": row["task_id"],
            "run_id": row["run_id"],
            "title": row["title"],
            "task_type": row["task_type"],
            "status": row["status"],
            "priority": row["priority"],
            "phase": row["phase"],
            "target_ref": json.loads(row["target_ref_json"]),
            "result_ref": json.loads(row["result_ref_json"]),
            "notes": row["notes"],
            "blocked_reason": row["blocked_reason"],
            "due_at": row["due_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_research_schedule(
        self,
        *,
        schedule_id: str,
        title: str,
        workflow_name: str,
        interval_hours: float,
        next_run_at: float,
        status: str = "active",
        phase: Optional[str] = None,
        run_id: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
        result_ref: Optional[Dict[str, Any]] = None,
        last_run_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO research_schedules(
                    schedule_id, run_id, title, workflow_name, status,
                    interval_hours, phase, arguments_json, last_run_at,
                    next_run_at, result_ref_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule_id,
                    run_id,
                    title,
                    workflow_name,
                    status,
                    interval_hours,
                    phase,
                    self._to_json(arguments or {}),
                    last_run_at,
                    next_run_at,
                    self._to_json(result_ref or {}),
                    now,
                    now,
                ),
            )
        return self.get_research_schedule(schedule_id) or {}

    def update_research_schedule(
        self,
        schedule_id: str,
        *,
        title: Optional[str] = None,
        workflow_name: Optional[str] = None,
        status: Optional[str] = None,
        interval_hours: Optional[float] = None,
        phase: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
        last_run_at: Optional[float] = None,
        next_run_at: Optional[float] = None,
        result_ref: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        current = self.get_research_schedule(schedule_id)
        if not current:
            return None
        updated = {
            "title": current["title"] if title is None else title,
            "workflow_name": current["workflow_name"] if workflow_name is None else workflow_name,
            "status": current["status"] if status is None else status,
            "interval_hours": current["interval_hours"] if interval_hours is None else interval_hours,
            "phase": current["phase"] if phase is None else phase,
            "arguments": current["arguments"] if arguments is None else arguments,
            "last_run_at": current["last_run_at"] if last_run_at is None else last_run_at,
            "next_run_at": current["next_run_at"] if next_run_at is None else next_run_at,
            "result_ref": current["result_ref"] if result_ref is None else result_ref,
        }
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE research_schedules
                SET title = ?, workflow_name = ?, status = ?, interval_hours = ?,
                    phase = ?, arguments_json = ?, last_run_at = ?, next_run_at = ?,
                    result_ref_json = ?, updated_at = ?
                WHERE schedule_id = ?
                """,
                (
                    updated["title"],
                    updated["workflow_name"],
                    updated["status"],
                    updated["interval_hours"],
                    updated["phase"],
                    self._to_json(updated["arguments"]),
                    updated["last_run_at"],
                    updated["next_run_at"],
                    self._to_json(updated["result_ref"]),
                    time.time(),
                    schedule_id,
                ),
            )
        return self.get_research_schedule(schedule_id)

    def get_research_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_schedules WHERE schedule_id = ?",
                (schedule_id,),
            ).fetchone()
        return self._research_schedule_from_row(row) if row else None

    def list_research_schedules(
        self,
        *,
        run_id: Optional[str] = None,
        status: Optional[str] = None,
        workflow_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if run_id:
            where.append("run_id = ?")
            params.append(run_id)
        if status:
            where.append("status = ?")
            params.append(status)
        if workflow_name:
            where.append("workflow_name = ?")
            params.append(workflow_name)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(max(1, min(limit, 300)))
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM research_schedules
                {where_clause}
                ORDER BY next_run_at ASC, updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._research_schedule_from_row(row) for row in rows]

    def _research_schedule_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "schedule_id": row["schedule_id"],
            "run_id": row["run_id"],
            "title": row["title"],
            "workflow_name": row["workflow_name"],
            "status": row["status"],
            "interval_hours": row["interval_hours"],
            "phase": row["phase"],
            "arguments": json.loads(row["arguments_json"]),
            "last_run_at": row["last_run_at"],
            "next_run_at": row["next_run_at"],
            "result_ref": json.loads(row["result_ref_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_research_delegation(
        self,
        *,
        delegation_id: str,
        title: str,
        phase: str,
        strategy: str,
        agents: List[Dict[str, Any]],
        status: str = "planned",
        run_id: Optional[str] = None,
        target_ref: Optional[Dict[str, Any]] = None,
        result_ref: Optional[Dict[str, Any]] = None,
        summary: str = "",
    ) -> Dict[str, Any]:
        now = time.time()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO research_delegations(
                    delegation_id, run_id, title, phase, strategy, status,
                    agents_json, target_ref_json, result_ref_json, summary,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delegation_id,
                    run_id,
                    title,
                    phase,
                    strategy,
                    status,
                    self._to_json(agents),
                    self._to_json(target_ref or {}),
                    self._to_json(result_ref or {}),
                    summary,
                    now,
                    now,
                ),
            )
        return self.get_research_delegation(delegation_id) or {}

    def update_research_delegation(
        self,
        delegation_id: str,
        *,
        title: Optional[str] = None,
        phase: Optional[str] = None,
        strategy: Optional[str] = None,
        status: Optional[str] = None,
        agents: Optional[List[Dict[str, Any]]] = None,
        target_ref: Optional[Dict[str, Any]] = None,
        result_ref: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        current = self.get_research_delegation(delegation_id)
        if not current:
            return None
        updated = {
            "title": current["title"] if title is None else title,
            "phase": current["phase"] if phase is None else phase,
            "strategy": current["strategy"] if strategy is None else strategy,
            "status": current["status"] if status is None else status,
            "agents": current["agents"] if agents is None else agents,
            "target_ref": current["target_ref"] if target_ref is None else target_ref,
            "result_ref": current["result_ref"] if result_ref is None else result_ref,
            "summary": current["summary"] if summary is None else summary,
        }
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE research_delegations
                SET title = ?, phase = ?, strategy = ?, status = ?, agents_json = ?,
                    target_ref_json = ?, result_ref_json = ?, summary = ?, updated_at = ?
                WHERE delegation_id = ?
                """,
                (
                    updated["title"],
                    updated["phase"],
                    updated["strategy"],
                    updated["status"],
                    self._to_json(updated["agents"]),
                    self._to_json(updated["target_ref"]),
                    self._to_json(updated["result_ref"]),
                    updated["summary"],
                    time.time(),
                    delegation_id,
                ),
            )
        return self.get_research_delegation(delegation_id)

    def get_research_delegation(self, delegation_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_delegations WHERE delegation_id = ?",
                (delegation_id,),
            ).fetchone()
        return self._research_delegation_from_row(row) if row else None

    def list_research_delegations(
        self,
        *,
        run_id: Optional[str] = None,
        status: Optional[str] = None,
        strategy: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if run_id:
            where.append("run_id = ?")
            params.append(run_id)
        if status:
            where.append("status = ?")
            params.append(status)
        if strategy:
            where.append("strategy = ?")
            params.append(strategy)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(max(1, min(limit, 300)))
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM research_delegations
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._research_delegation_from_row(row) for row in rows]

    def _research_delegation_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "delegation_id": row["delegation_id"],
            "run_id": row["run_id"],
            "title": row["title"],
            "phase": row["phase"],
            "strategy": row["strategy"],
            "status": row["status"],
            "agents": json.loads(row["agents_json"]),
            "target_ref": json.loads(row["target_ref_json"]),
            "result_ref": json.loads(row["result_ref_json"]),
            "summary": row["summary"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def search_research_sessions(
        self,
        query: str,
        *,
        run_id: Optional[str] = None,
        result_types: Optional[List[str]] = None,
        limit: int = 50,
    ) -> list[Dict[str, Any]]:
        normalized = query.strip()
        if len(normalized) < 2:
            return []
        result_type_filter = set(result_types or [])
        max_results = max(1, min(limit, 100))
        like = f"%{normalized}%"
        results: list[Dict[str, Any]] = []

        def allowed(result_type: str) -> bool:
            return not result_type_filter or result_type in result_type_filter

        def add(result: Dict[str, Any]) -> None:
            if len(results) < max_results:
                results.append(result)

        with self._connection() as connection:
            if allowed("run") and len(results) < max_results:
                if run_id:
                    rows = connection.execute(
                        """
                        SELECT run_id, status, request_json, research_plan_json, metrics_json,
                               updated_at, error
                        FROM research_runs
                        WHERE run_id = ? AND (
                            run_id LIKE ? OR request_json LIKE ? OR research_plan_json LIKE ?
                            OR metrics_json LIKE ? OR error LIKE ?
                        )
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        (run_id, like, like, like, like, like, max_results - len(results)),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT run_id, status, request_json, research_plan_json, metrics_json,
                               updated_at, error
                        FROM research_runs
                        WHERE run_id LIKE ? OR request_json LIKE ? OR research_plan_json LIKE ?
                              OR metrics_json LIKE ? OR error LIKE ?
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        (like, like, like, like, like, max_results - len(results)),
                    ).fetchall()
                for row in rows:
                    request_payload = json.loads(row["request_json"])
                    add(
                        {
                            "type": "run",
                            "id": row["run_id"],
                            "run_id": row["run_id"],
                            "title": request_payload.get("research_goal") or row["run_id"],
                            "status": row["status"],
                            "snippet": self._build_search_snippet(
                                normalized,
                                " ".join(
                                    [
                                        str(request_payload.get("research_goal", "")),
                                        row["research_plan_json"],
                                        row["metrics_json"],
                                        row["error"] or "",
                                    ]
                                ),
                            ),
                            "updated_at": row["updated_at"],
                            "target_ref": {"run_id": row["run_id"]},
                        }
                    )

            if allowed("hypothesis") and len(results) < max_results:
                params: list[Any] = [like, like, like, like]
                where = "(hypothesis_id LIKE ? OR title LIKE ? OR text LIKE ? OR experiment LIKE ?)"
                if run_id:
                    where = f"run_id = ? AND {where}"
                    params.insert(0, run_id)
                params.append(max_results - len(results))
                rows = connection.execute(
                    f"""
                    SELECT hypothesis_id, run_id, hypothesis_index, title, text, experiment,
                           grounding_status, updated_at
                    FROM research_hypotheses
                    WHERE {where}
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
                for row in rows:
                    add(
                        {
                            "type": "hypothesis",
                            "id": row["hypothesis_id"],
                            "run_id": row["run_id"],
                            "title": row["title"] or row["text"][:120],
                            "status": row["grounding_status"],
                            "snippet": self._build_search_snippet(
                                normalized,
                                " ".join([row["title"] or "", row["text"] or "", row["experiment"] or ""]),
                            ),
                            "updated_at": row["updated_at"],
                            "target_ref": {
                                "run_id": row["run_id"],
                                "hypothesis_id": row["hypothesis_id"],
                                "hypothesis_index": row["hypothesis_index"],
                            },
                        }
                    )

            if allowed("tool_result") and len(results) < max_results:
                params = [like, like, like]
                where = "(tool_name LIKE ? OR summary LIKE ? OR content_json LIKE ?)"
                if run_id:
                    where = f"run_id = ? AND {where}"
                    params.insert(0, run_id)
                params.append(max_results - len(results))
                rows = connection.execute(
                    f"""
                    SELECT result_id, run_id, tool_name, phase, result_kind, summary,
                           content_size, created_at
                    FROM research_tool_results
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
                for row in rows:
                    add(
                        {
                            "type": "tool_result",
                            "id": row["result_id"],
                            "run_id": row["run_id"],
                            "title": f"{row['tool_name']} / {row['result_kind']}",
                            "status": row["phase"],
                            "snippet": self._build_search_snippet(normalized, row["summary"] or ""),
                            "updated_at": row["created_at"],
                            "target_ref": {
                                "run_id": row["run_id"],
                                "result_id": row["result_id"],
                                "tool_name": row["tool_name"],
                                "content_size": row["content_size"],
                            },
                        }
                    )

            if allowed("task") and len(results) < max_results:
                params = [like, like, like, like]
                where = "(title LIKE ? OR task_type LIKE ? OR notes LIKE ? OR blocked_reason LIKE ?)"
                if run_id:
                    where = f"run_id = ? AND {where}"
                    params.insert(0, run_id)
                params.append(max_results - len(results))
                rows = connection.execute(
                    f"""
                    SELECT task_id, run_id, title, task_type, status, notes,
                           blocked_reason, updated_at
                    FROM research_tasks
                    WHERE {where}
                    ORDER BY priority ASC, updated_at DESC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
                for row in rows:
                    add(
                        {
                            "type": "task",
                            "id": row["task_id"],
                            "run_id": row["run_id"],
                            "title": row["title"],
                            "status": row["status"],
                            "snippet": self._build_search_snippet(
                                normalized,
                                " ".join([row["task_type"], row["notes"], row["blocked_reason"] or ""]),
                            ),
                            "updated_at": row["updated_at"],
                            "target_ref": {"run_id": row["run_id"], "task_id": row["task_id"]},
                        }
                    )

            if allowed("background_job") and len(results) < max_results:
                params = [like, like, like]
                where = "(workflow_name LIKE ? OR arguments_json LIKE ? OR error_message LIKE ?)"
                if run_id:
                    where = f"run_id = ? AND {where}"
                    params.insert(0, run_id)
                params.append(max_results - len(results))
                rows = connection.execute(
                    f"""
                    SELECT job_id, run_id, workflow_name, phase, status,
                           error_message, updated_at
                    FROM research_background_jobs
                    WHERE {where}
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
                for row in rows:
                    add(
                        {
                            "type": "background_job",
                            "id": row["job_id"],
                            "run_id": row["run_id"],
                            "title": row["workflow_name"],
                            "status": row["status"],
                            "snippet": self._build_search_snippet(normalized, row["error_message"] or row["phase"] or ""),
                            "updated_at": row["updated_at"],
                            "target_ref": {"run_id": row["run_id"], "job_id": row["job_id"]},
                        }
                    )

            if allowed("schedule") and len(results) < max_results:
                params = [like, like, like]
                where = "(title LIKE ? OR workflow_name LIKE ? OR arguments_json LIKE ?)"
                if run_id:
                    where = f"run_id = ? AND {where}"
                    params.insert(0, run_id)
                params.append(max_results - len(results))
                rows = connection.execute(
                    f"""
                    SELECT schedule_id, run_id, title, workflow_name, status,
                           next_run_at, updated_at
                    FROM research_schedules
                    WHERE {where}
                    ORDER BY next_run_at ASC, updated_at DESC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
                for row in rows:
                    add(
                        {
                            "type": "schedule",
                            "id": row["schedule_id"],
                            "run_id": row["run_id"],
                            "title": row["title"],
                            "status": row["status"],
                            "snippet": self._build_search_snippet(normalized, row["workflow_name"]),
                            "updated_at": row["updated_at"],
                            "target_ref": {
                                "run_id": row["run_id"],
                                "schedule_id": row["schedule_id"],
                                "next_run_at": row["next_run_at"],
                            },
                        }
                    )

            if allowed("delegation") and len(results) < max_results:
                params = [like, like, like, like]
                where = "(title LIKE ? OR strategy LIKE ? OR agents_json LIKE ? OR summary LIKE ?)"
                if run_id:
                    where = f"run_id = ? AND {where}"
                    params.insert(0, run_id)
                params.append(max_results - len(results))
                rows = connection.execute(
                    f"""
                    SELECT delegation_id, run_id, title, phase, strategy, status,
                           summary, updated_at
                    FROM research_delegations
                    WHERE {where}
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
                for row in rows:
                    add(
                        {
                            "type": "delegation",
                            "id": row["delegation_id"],
                            "run_id": row["run_id"],
                            "title": row["title"],
                            "status": row["status"],
                            "snippet": self._build_search_snippet(
                                normalized,
                                " ".join([row["strategy"], row["phase"], row["summary"] or ""]),
                            ),
                            "updated_at": row["updated_at"],
                            "target_ref": {
                                "run_id": row["run_id"],
                                "delegation_id": row["delegation_id"],
                                "strategy": row["strategy"],
                            },
                        }
                    )

        return sorted(results, key=lambda item: item.get("updated_at") or 0, reverse=True)[:max_results]

    @staticmethod
    def _build_search_snippet(query: str, text: str, *, radius: int = 120) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        if not compact:
            return ""
        lower_text = compact.lower()
        index = lower_text.find(query.lower())
        if index < 0:
            return compact[: radius * 2]
        start = max(0, index - radius)
        end = min(len(compact), index + len(query) + radius)
        prefix = "..." if start else ""
        suffix = "..." if end < len(compact) else ""
        return f"{prefix}{compact[start:end]}{suffix}"

    def get_research_tool_calls(self, run_id: str) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM research_tool_calls
                WHERE run_id = ?
                ORDER BY order_index ASC, created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "tool_call_id": row["tool_call_id"],
                "run_id": row["run_id"],
                "trace_event_id": row["trace_event_id"],
                "order_index": row["order_index"],
                "agent": row["agent"],
                "phase": row["phase"],
                "tool_name": row["tool_name"],
                "status": row["status"],
                "arguments": json.loads(row["arguments_json"]),
                "result_summary": row["result_summary"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _hypothesis_evidence_link_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "link_id": row["link_id"],
            "run_id": row["run_id"],
            "hypothesis_id": row["hypothesis_id"],
            "hypothesis_index": row["hypothesis_index"],
            "evidence_id": row["evidence_id"],
            "chunk_id": row["chunk_id"],
            "paper_id": row["paper_id"],
            "parse_run_id": row["parse_run_id"],
            "section_type": row["section_type"],
            "section_path": json.loads(row["section_path_json"]),
            "support_level": row["support_level"],
            "source_reliability": row["source_reliability"],
            "evidence_summary": row["evidence_summary"],
            "experiment_data_summary": row["experiment_data_summary"],
            "text_preview": row["text_preview"],
            "evidence_path": row["evidence_path"],
            "score": row["score"],
            "created_at": row["created_at"],
        }

    def _hypothesis_id(self, run_id: str, index: int, hypothesis: Dict[str, Any]) -> str:
        explicit = hypothesis.get("id") or hypothesis.get("hypothesis_id")
        if explicit:
            return str(explicit)
        return f"{run_id}:hypothesis:{index + 1:03d}"

    def _hypothesis_query(self, hypothesis: Dict[str, Any]) -> str:
        return " ".join(
            part.strip()
            for part in (
                self._first_text(hypothesis, ("text", "hypothesis", "technical_hypothesis")),
                self._first_text(hypothesis, ("explanation", "plain_explanation", "rationale")),
                self._first_text(hypothesis, ("experiment", "validation_plan", "experiment_plan")),
            )
            if part.strip()
        )

    def _first_text(self, value: Dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            item = value.get(key)
            if item is None:
                continue
            if isinstance(item, (str, int, float, bool)):
                return str(item)
        return ""

    def _coerce_float(self, value: Any, default: Optional[float] = None) -> Optional[float]:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _to_json(self, value: Any) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)

    def record_parse_run(
        self,
        *,
        parse_run_id: str,
        paper_id: Optional[str],
        library_id: Optional[str] = None,
        title: str,
        status: str,
        input_kind: str,
        input_path: str,
        pdf_path: Optional[str],
        solve_dir: Optional[str],
        page_count: Optional[int],
        chunks_count: int,
        experimental_chunks_count: int,
        knowledge_base_ingested: bool,
        rag_search_ready: bool,
        items: list[Dict[str, Any]],
        evidence: list[Dict[str, Any]],
    ) -> None:
        now = time.time()
        resolved_library_id = self.resolve_library_id(library_id)
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT created_at FROM paper_parse_runs WHERE parse_run_id = ?",
                (parse_run_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            connection.execute(
                """
                INSERT OR REPLACE INTO paper_parse_runs(
                    parse_run_id, paper_id, library_id, title, status, input_kind, input_path, pdf_path,
                    solve_dir, page_count, chunks_count, experimental_chunks_count,
                    knowledge_base_ingested, rag_search_ready, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    parse_run_id,
                    paper_id,
                    resolved_library_id,
                    title,
                    status,
                    input_kind,
                    input_path,
                    pdf_path,
                    solve_dir,
                    page_count,
                    chunks_count,
                    experimental_chunks_count,
                    int(knowledge_base_ingested),
                    int(rag_search_ready),
                    created_at,
                    now,
                ),
            )
            connection.execute("DELETE FROM paper_parse_items WHERE parse_run_id = ?", (parse_run_id,))
            connection.execute("DELETE FROM paper_parse_evidence WHERE parse_run_id = ?", (parse_run_id,))
            for index, item in enumerate(items):
                connection.execute(
                    """
                    INSERT INTO paper_parse_items(
                        item_id, parse_run_id, item_key, label, status, evidence_type,
                        evidence_summary, evidence_id, completed_at, error_message, order_index
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"item_{uuid.uuid4().hex[:12]}",
                        parse_run_id,
                        item["item_key"],
                        item["label"],
                        item["status"],
                        item["evidence_type"],
                        item["evidence_summary"],
                        item.get("evidence_id"),
                        item.get("completed_at"),
                        item.get("error_message"),
                        index,
                    ),
                )
            for item in evidence:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO paper_parse_evidence(
                        evidence_id, parse_run_id, paper_id, library_id, item_key, evidence_type, label,
                        file_path, chunk_id, section_path_json, text_preview, media_preview,
                        metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["evidence_id"],
                        parse_run_id,
                        item.get("paper_id"),
                        resolved_library_id,
                        item["item_key"],
                        item["evidence_type"],
                        item["label"],
                        item.get("file_path"),
                        item.get("chunk_id"),
                        json.dumps(item.get("section_path", []), ensure_ascii=False),
                        item.get("text_preview"),
                        item.get("media_preview"),
                        json.dumps(item.get("metadata", {}), ensure_ascii=False),
                        item.get("created_at", now),
                    ),
                )

    def list_parse_runs(self, library_id: Optional[str] = None) -> list[Dict[str, Any]]:
        resolved_library_id = self.resolve_library_id(library_id) if library_id else None
        with self._connection() as connection:
            if resolved_library_id:
                rows = connection.execute(
                    "SELECT * FROM paper_parse_runs WHERE library_id = ? ORDER BY updated_at DESC",
                    (resolved_library_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM paper_parse_runs ORDER BY updated_at DESC"
                ).fetchall()
        return [self._parse_run_summary_from_row(row) for row in rows]

    def get_parse_run(self, parse_run_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM paper_parse_runs WHERE parse_run_id = ?",
                (parse_run_id,),
            ).fetchone()
            if not row:
                return None
            items = connection.execute(
                "SELECT * FROM paper_parse_items WHERE parse_run_id = ? ORDER BY order_index ASC",
                (parse_run_id,),
            ).fetchall()
            evidence_rows = connection.execute(
                "SELECT * FROM paper_parse_evidence WHERE parse_run_id = ? ORDER BY created_at ASC",
                (parse_run_id,),
            ).fetchall()
        result = self._parse_run_summary_from_row(row)
        evidence_by_id = {item["evidence_id"]: self._evidence_from_row(item) for item in evidence_rows}
        result["items"] = [
            {
                "item_key": item["item_key"],
                "label": item["label"],
                "status": item["status"],
                "evidence_type": item["evidence_type"],
                "evidence_summary": item["evidence_summary"],
                "evidence_id": item["evidence_id"],
                "completed_at": item["completed_at"],
                "error_message": item["error_message"],
                "evidence": evidence_by_id.get(item["evidence_id"]) if item["evidence_id"] else None,
            }
            for item in items
        ]
        result["evidence"] = list(evidence_by_id.values())
        return result

    def _parse_run_summary_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "parse_run_id": row["parse_run_id"],
            "paper_id": row["paper_id"],
            "library_id": row["library_id"] or DEFAULT_LIBRARY_ID,
            "title": row["title"],
            "status": row["status"],
            "input_kind": row["input_kind"],
            "input_path": row["input_path"],
            "pdf_path": row["pdf_path"],
            "solve_dir": row["solve_dir"],
            "page_count": row["page_count"],
            "chunks_count": row["chunks_count"],
            "experimental_chunks_count": row["experimental_chunks_count"],
            "knowledge_base_ingested": bool(row["knowledge_base_ingested"]),
            "rag_search_ready": bool(row["rag_search_ready"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "items": [],
        }

    def _evidence_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "evidence_id": row["evidence_id"],
            "parse_run_id": row["parse_run_id"],
            "paper_id": row["paper_id"],
            "library_id": row["library_id"] or DEFAULT_LIBRARY_ID,
            "item_key": row["item_key"],
            "evidence_type": row["evidence_type"],
            "label": row["label"],
            "file_path": row["file_path"],
            "chunk_id": row["chunk_id"],
            "section_path": json.loads(row["section_path_json"]),
            "text_preview": row["text_preview"],
            "media_preview": row["media_preview"],
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    def update_media_region_audit(self, parse_run_id: str, media_assets: list[Dict[str, Any]]) -> None:
        total = len(media_assets)
        review = sum(1 for asset in media_assets if asset.get("risk_level") == "review")
        high = sum(1 for asset in media_assets if asset.get("risk_level") == "high")
        ok = total - review - high
        status = "warning" if review or high or total == 0 else "success"
        summary = (
            f"图表区域审计完成：可信 {ok} 张，建议复核 {review} 张，高风险 {high} 张。"
            if total
            else "未生成图表截图，无法进行图表区域审计；不影响全文 chunk RAG。"
        )
        evidence_id = f"evidence_{parse_run_id}_media_region_quality_checked"
        now = time.time()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT paper_id, library_id, status FROM paper_parse_runs WHERE parse_run_id = ?",
                (parse_run_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"parse run not found: {parse_run_id}")
            paper_id = row["paper_id"]
            library_id = row["library_id"] or DEFAULT_LIBRARY_ID
            existing_item = connection.execute(
                "SELECT item_id FROM paper_parse_items WHERE parse_run_id = ? AND item_key = 'media_region_quality_checked'",
                (parse_run_id,),
            ).fetchone()
            if existing_item:
                connection.execute(
                    """
                    UPDATE paper_parse_items
                    SET status = ?, evidence_summary = ?, evidence_id = ?, completed_at = ?, error_message = NULL
                    WHERE parse_run_id = ? AND item_key = 'media_region_quality_checked'
                    """,
                    (status, summary, evidence_id, now, parse_run_id),
                )
            else:
                max_order = connection.execute(
                    "SELECT COALESCE(MAX(order_index), -1) AS max_order FROM paper_parse_items WHERE parse_run_id = ?",
                    (parse_run_id,),
                ).fetchone()["max_order"]
                connection.execute(
                    """
                    INSERT INTO paper_parse_items(
                        item_id, parse_run_id, item_key, label, status, evidence_type,
                        evidence_summary, evidence_id, completed_at, error_message, order_index
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        f"item_{uuid.uuid4().hex[:12]}",
                        parse_run_id,
                        "media_region_quality_checked",
                        "图表区域质量已审计",
                        status,
                        "media",
                        summary,
                        evidence_id,
                        now,
                        int(max_order) + 1,
                    ),
                )

            connection.execute(
                "DELETE FROM paper_parse_evidence WHERE parse_run_id = ? AND item_key = 'media_region_quality_checked'",
                (parse_run_id,),
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO paper_parse_evidence(
                    evidence_id, parse_run_id, paper_id, library_id, item_key, evidence_type, label,
                    file_path, chunk_id, section_path_json, text_preview, media_preview,
                    metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?)
                """,
                (
                    evidence_id,
                    parse_run_id,
                    paper_id,
                    library_id,
                    "media_region_quality_checked",
                    "media",
                    "图表区域质量审计",
                    media_assets[0].get("path") if media_assets else None,
                    json.dumps([], ensure_ascii=False),
                    media_assets[0].get("caption_preview") if media_assets else None,
                    json.dumps(
                        {
                            "quality_summary": {"total": total, "ok": ok, "review": review, "high": high},
                            "media_assets": media_assets,
                        },
                        ensure_ascii=False,
                    ),
                    now,
                ),
            )
            for asset in media_assets:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO paper_parse_evidence(
                        evidence_id, parse_run_id, paper_id, library_id, item_key, evidence_type, label,
                        file_path, chunk_id, section_path_json, text_preview, media_preview,
                        metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?)
                    """,
                    (
                        f"evidence_{parse_run_id}_{asset.get('asset_id', uuid.uuid4().hex[:8])}_quality",
                        parse_run_id,
                        paper_id,
                        library_id,
                        "media_region_quality_checked",
                        "media",
                        f"{asset.get('kind', 'media')} p{asset.get('page', '')}",
                        asset.get("path"),
                        json.dumps([], ensure_ascii=False),
                        asset.get("caption_preview"),
                        json.dumps(asset, ensure_ascii=False),
                        now,
                    ),
                )
            if status == "warning" and row["status"] != "error":
                connection.execute(
                    "UPDATE paper_parse_runs SET status = ?, updated_at = ? WHERE parse_run_id = ?",
                    ("warning", now, parse_run_id),
                )


def reliability_for_source(source: str) -> str:
    normalized = source.lower()
    if "google_scholar" in normalized or "scholar" in normalized:
        return "best_effort_public_html"
    if "pubmed" in normalized or "pmc" in normalized:
        return "stable_biomedical_index"
    if "arxiv" in normalized:
        return "preprint_repository"
    return "user_provided"
