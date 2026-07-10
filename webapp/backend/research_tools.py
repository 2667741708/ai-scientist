from __future__ import annotations

import importlib.util
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

try:
    from backend.web_search import web_search_status as public_web_search_status
except ModuleNotFoundError:
    from web_search import web_search_status as public_web_search_status


AvailabilityCheck = Callable[[], Dict[str, Any]]


PHASE_ALIASES: Dict[str, str] = {
    "literature": "literature_review",
    "generate": "hypothesis_generation",
    "generation": "hypothesis_generation",
    "review": "review_critique",
    "critique": "review_critique",
    "rank": "ranking",
    "experiment": "experiment_design",
    "terminal": "operator_diagnostics",
    "shell": "operator_diagnostics",
}


@dataclass(frozen=True)
class PhaseToolPolicy:
    phase: str
    allowed_toolsets: tuple[str, ...]
    allowed_risk_levels: tuple[str, ...]
    description: str

    def describe(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "allowed_toolsets": list(self.allowed_toolsets),
            "allowed_risk_levels": list(self.allowed_risk_levels),
            "description": self.description,
        }


PHASE_TOOL_POLICIES: Dict[str, PhaseToolPolicy] = {
    "supervisor": PhaseToolPolicy(
        phase="supervisor",
        allowed_toolsets=("provenance",),
        allowed_risk_levels=("read", "write"),
        description="Supervisor may persist workflow state but should not fetch external evidence directly.",
    ),
    "paper_reading": PhaseToolPolicy(
        phase="paper_reading",
        allowed_toolsets=("pdf", "metadata", "knowledge_base"),
        allowed_risk_levels=("read", "write", "network"),
        description="Paper reading can parse PDFs and enrich metadata through dedicated workflows.",
    ),
    "literature_review": PhaseToolPolicy(
        phase="literature_review",
        allowed_toolsets=("knowledge_base", "pdf", "mcp", "metadata", "browser", "web_search"),
        allowed_risk_levels=("read", "write", "network"),
        description="Literature review may use local evidence and controlled external literature sources.",
    ),
    "hypothesis_generation": PhaseToolPolicy(
        phase="hypothesis_generation",
        allowed_toolsets=("knowledge_base", "provenance"),
        allowed_risk_levels=("read", "write"),
        description="Hypothesis generation should read grounded evidence and persist provenance.",
    ),
    "review_critique": PhaseToolPolicy(
        phase="review_critique",
        allowed_toolsets=("knowledge_base", "provenance"),
        allowed_risk_levels=("read", "write"),
        description="Critique can inspect evidence and record audit artifacts.",
    ),
    "ranking": PhaseToolPolicy(
        phase="ranking",
        allowed_toolsets=("knowledge_base", "provenance"),
        allowed_risk_levels=("read", "write"),
        description="Ranking can read evidence and persist tournament provenance.",
    ),
    "experiment_design": PhaseToolPolicy(
        phase="experiment_design",
        allowed_toolsets=("knowledge_base", "code_execution", "experiment", "ssh_training", "file"),
        allowed_risk_levels=("read", "sandboxed_write", "background_write", "remote_background_write"),
        description="Experiment design can use evidence and controlled execution surfaces, including approved remote training planning.",
    ),
    "experiment_execution": PhaseToolPolicy(
        phase="experiment_execution",
        allowed_toolsets=("experiment", "code_execution", "ssh_training"),
        allowed_risk_levels=("background_write", "sandboxed_write", "remote_background_write"),
        description="Experiment execution requires dedicated local or SSH background job workflow and approval.",
    ),
    "experiment_analysis": PhaseToolPolicy(
        phase="experiment_analysis",
        allowed_toolsets=("knowledge_base", "code_execution", "provenance"),
        allowed_risk_levels=("read", "sandboxed_write", "write"),
        description="Experiment analysis can read evidence, run sandboxed analysis, and persist results.",
    ),
    "evidence_audit": PhaseToolPolicy(
        phase="evidence_audit",
        allowed_toolsets=("knowledge_base", "browser", "file", "provenance", "web_search"),
        allowed_risk_levels=("read", "network", "write"),
        description="Evidence audit may inspect local evidence and controlled browser evidence captures.",
    ),
    "operator_diagnostics": PhaseToolPolicy(
        phase="operator_diagnostics",
        allowed_toolsets=("terminal",),
        allowed_risk_levels=("terminal_exec",),
        description=(
            "Local terminal execution is available only through the permission-gated terminal workflow, "
            "with command risk classification and durable audit artifacts."
        ),
    ),
    "writing": PhaseToolPolicy(
        phase="writing",
        allowed_toolsets=("knowledge_base", "file", "provenance"),
        allowed_risk_levels=("read", "write"),
        description="Writing should use persisted evidence and provenance, not new untracked external tools.",
    ),
}


def canonical_phase(phase: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", phase.strip().lower()).strip("_")
    return PHASE_ALIASES.get(normalized, normalized)


def list_phase_tool_policies() -> list[Dict[str, Any]]:
    return [policy.describe() for _, policy in sorted(PHASE_TOOL_POLICIES.items())]


def get_phase_tool_policy(phase: str) -> Optional[PhaseToolPolicy]:
    return PHASE_TOOL_POLICIES.get(canonical_phase(phase))


def authorize_tool_for_phase(spec: "ResearchToolSpec", phase: str) -> Dict[str, Any]:
    canonical = canonical_phase(phase)
    policy = get_phase_tool_policy(canonical)
    if not policy:
        return {
            "allowed": False,
            "code": "tool_phase_unknown",
            "message": "未知科研 phase，没有可执行工具授权策略。",
            "phase": canonical,
        }
    if canonical not in {canonical_phase(item) for item in spec.phases}:
        return {
            "allowed": False,
            "code": "tool_phase_not_allowed",
            "message": "这个工具没有被授权用于当前科研 phase。",
            "phase": canonical,
            "allowed_phases": list(spec.phases),
        }
    if spec.toolset not in policy.allowed_toolsets:
        return {
            "allowed": False,
            "code": "toolset_not_allowed_for_phase",
            "message": "当前科研 phase 没有授权这个 toolset。",
            "phase": canonical,
            "toolset": spec.toolset,
            "allowed_toolsets": list(policy.allowed_toolsets),
        }
    if spec.risk_level not in policy.allowed_risk_levels:
        return {
            "allowed": False,
            "code": "risk_level_not_allowed_for_phase",
            "message": "当前科研 phase 没有授权这个工具风险级别。",
            "phase": canonical,
            "risk_level": spec.risk_level,
            "allowed_risk_levels": list(policy.allowed_risk_levels),
        }
    return {
        "allowed": True,
        "phase": canonical,
        "policy": policy.describe(),
    }


def canonical_tool_arguments(arguments: Dict[str, Any]) -> str:
    return json.dumps(arguments or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ResearchToolSpec:
    name: str
    toolset: str
    description: str
    phases: tuple[str, ...]
    risk_level: str = "read"
    requires: tuple[str, ...] = ()
    input_schema: Dict[str, Any] = field(default_factory=dict)
    availability_check: Optional[AvailabilityCheck] = None

    def describe(self) -> Dict[str, Any]:
        availability = (
            self.availability_check()
            if self.availability_check
            else {
                "available": True,
                "mode": "ready",
                "reason": "No runtime dependency declared.",
                "checked_at": time.time(),
            }
        )
        return {
            "name": self.name,
            "toolset": self.toolset,
            "description": self.description,
            "phases": list(self.phases),
            "risk_level": self.risk_level,
            "requires": list(self.requires),
            "input_schema": self.input_schema,
            "availability": availability,
        }


class ResearchToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ResearchToolSpec] = {}

    def register(self, spec: ResearchToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate research tool: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ResearchToolSpec]:
        return self._tools.get(name)

    def list_tools(
        self,
        *,
        phase: Optional[str] = None,
        toolset: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        normalized_phase = phase.strip().lower() if phase else None
        normalized_toolset = toolset.strip().lower() if toolset else None
        tools = sorted(self._tools.values(), key=lambda item: (item.toolset, item.name))
        results: list[Dict[str, Any]] = []
        for spec in tools:
            if normalized_phase and normalized_phase not in {item.lower() for item in spec.phases}:
                continue
            if normalized_toolset and normalized_toolset != spec.toolset.lower():
                continue
            results.append(spec.describe())
        return results

    def list_toolsets(self) -> list[Dict[str, Any]]:
        grouped: Dict[str, list[ResearchToolSpec]] = {}
        for spec in self._tools.values():
            grouped.setdefault(spec.toolset, []).append(spec)
        return [
            {
                "toolset": toolset,
                "tools": sorted(spec.name for spec in specs),
                "risk_levels": sorted({spec.risk_level for spec in specs}),
                "phases": sorted({phase for spec in specs for phase in spec.phases}),
            }
            for toolset, specs in sorted(grouped.items())
        ]

    def list_phase_tools(self, phase: str) -> Dict[str, Any]:
        tools = self.list_tools(phase=phase)
        return {
            "phase": phase,
            "tools": tools,
            "toolsets": sorted({tool["toolset"] for tool in tools}),
            "count": len(tools),
        }

    def names(self) -> list[str]:
        return sorted(self._tools)


def _status(
    *,
    available: bool,
    mode: str,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "available": available,
        "mode": mode,
        "reason": reason,
        "checked_at": time.time(),
    }
    if metadata:
        payload["metadata"] = metadata
    return payload


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def build_default_research_tool_registry(
    knowledge_base: Any,
    *,
    mcp_probe: Optional[AvailabilityCheck] = None,
    ssh_training_probe: Optional[AvailabilityCheck] = None,
) -> ResearchToolRegistry:
    registry = ResearchToolRegistry()

    def knowledge_base_status() -> Dict[str, Any]:
        documents = knowledge_base.list_documents()
        return _status(
            available=True,
            mode="ready_with_documents" if documents else "ready_empty",
            reason=(
                f"SQLite knowledge base is ready with {len(documents)} papers."
                if documents
                else "SQLite knowledge base is ready but has no papers yet."
            ),
            metadata={"database_path": str(knowledge_base.db_path), "papers": len(documents)},
        )

    def provenance_status() -> Dict[str, Any]:
        return _status(
            available=True,
            mode="ready",
            reason="Research run provenance tables are managed in the knowledge SQLite database.",
            metadata={"database_path": str(knowledge_base.db_path)},
        )

    def pdf_status() -> Dict[str, Any]:
        has_fitz = _module_available("fitz")
        return _status(
            available=has_fitz,
            mode="ready" if has_fitz else "missing_dependency",
            reason="PyMuPDF / fitz is installed." if has_fitz else "PyMuPDF / fitz is not importable.",
            metadata={"database_path": str(knowledge_base.db_path)},
        )

    def mcp_status() -> Dict[str, Any]:
        if not mcp_probe:
            return _status(
                available=False,
                mode="not_configured",
                reason="No MCP probe callback is configured for this process.",
            )
        return mcp_probe()

    def requests_status() -> Dict[str, Any]:
        has_requests = _module_available("requests")
        return _status(
            available=has_requests,
            mode="ready" if has_requests else "missing_dependency",
            reason="requests is installed." if has_requests else "requests is not importable.",
        )

    def web_search_status() -> Dict[str, Any]:
        return public_web_search_status()

    def playwright_status() -> Dict[str, Any]:
        has_playwright = _module_available("playwright")
        return _status(
            available=has_playwright,
            mode="ready" if has_playwright else "missing_dependency",
            reason="Playwright is installed." if has_playwright else "Playwright is not importable.",
        )

    def restricted_python_status() -> Dict[str, Any]:
        return _status(
            available=True,
            mode="restricted_python_ready",
            reason="Restricted Python analysis executor is available with AST guard and timeout.",
        )

    def experiment_runner_status() -> Dict[str, Any]:
        return _status(
            available=True,
            mode="restricted_python_script_ready",
            reason="Restricted Python experiment runner is available for scripts inside the configured experiment root.",
        )

    def ssh_training_runner_status() -> Dict[str, Any]:
        if not ssh_training_probe:
            return _status(
                available=False,
                mode="not_configured",
                reason="No SSH training probe callback is configured for this process.",
        )
        return ssh_training_probe()

    def terminal_command_status() -> Dict[str, Any]:
        return _status(
            available=True,
            mode="permission_gated",
            reason=(
                "Local terminal command workflow is enabled behind command permission modes, "
                "risk classification, output redaction, and audit artifacts."
            ),
        )

    registry.register(
        ResearchToolSpec(
            name="knowledge_base.rag_search",
            toolset="knowledge_base",
            description="Search semantic PDF/fulltext chunks in the local SQLite FTS evidence store.",
            phases=("literature_review", "hypothesis_generation", "review_critique", "writing"),
            risk_level="read",
            requires=("knowledge.sqlite3",),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "paper_id": {"type": "string"},
                    "support_level": {"type": "string"},
                },
                "required": ["query"],
            },
            availability_check=knowledge_base_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="knowledge_base.support_for_hypothesis",
            toolset="knowledge_base",
            description="Retrieve support chunks for a generated hypothesis and expose source reliability.",
            phases=("hypothesis_generation", "review_critique", "ranking", "writing"),
            risk_level="read",
            requires=("knowledge.sqlite3",),
            input_schema={
                "type": "object",
                "properties": {
                    "hypothesis": {"type": "object"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["hypothesis"],
            },
            availability_check=knowledge_base_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="provenance.record_run",
            toolset="provenance",
            description="Persist run, hypothesis, evidence, retrieval, trace, and tool-call provenance.",
            phases=("supervisor", "literature_review", "hypothesis_generation", "review_critique", "ranking", "writing"),
            risk_level="write",
            requires=("knowledge.sqlite3",),
            input_schema={"type": "object", "properties": {"run_record": {"type": "object"}}, "required": ["run_record"]},
            availability_check=provenance_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="pdf.parse_to_knowledge_base",
            toolset="pdf",
            description="Parse an accessible PDF into solve artifacts, semantic chunks, media assets, and the evidence store.",
            phases=("literature_review", "paper_reading"),
            risk_level="write",
            requires=("PyMuPDF", "requests", "knowledge.sqlite3"),
            input_schema={
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string"},
                    "fetch_metadata": {"type": "boolean"},
                    "ingest_to_knowledge_base": {"type": "boolean"},
                },
                "required": ["pdf_path"],
            },
            availability_check=pdf_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="mcp.literature_review",
            toolset="mcp",
            description="Use the configured literature MCP service for external paper and knowledge-graph grounding.",
            phases=("literature_review",),
            risk_level="network",
            requires=("MCP_SERVER_URL",),
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            availability_check=mcp_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="metadata.crossref_lookup",
            toolset="metadata",
            description="Best-effort DOI/Crossref metadata lookup for parsed papers.",
            phases=("literature_review", "paper_reading"),
            risk_level="network",
            requires=("requests",),
            input_schema={"type": "object", "properties": {"doi": {"type": "string"}}, "required": ["doi"]},
            availability_check=requests_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="web.search_public",
            toolset="web_search",
            description=(
                "Search a controlled public web or scholarly index and return provenance-bearing "
                "snippets, source URLs, and retrieval metadata."
            ),
            phases=("literature_review", "evidence_audit"),
            risk_level="network",
            requires=("configured web search provider", "dedicated workflow", "result storage"),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    "domains": {"type": "array", "items": {"type": "string"}},
                    "recency_days": {"type": "integer", "minimum": 1, "maximum": 3650},
                },
                "required": ["query"],
            },
            availability_check=web_search_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="file.source_snapshot",
            toolset="file",
            description="Capture a paginated, hashed text snapshot of a local source file inside the configured evidence root.",
            phases=("evidence_audit", "experiment_design", "writing"),
            risk_level="read",
            requires=("source evidence root", "SQLite result storage"),
            input_schema={
                "type": "object",
                "properties": {
                    "source_path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "line_count": {"type": "integer", "minimum": 1, "maximum": 2000},
                    "max_bytes": {"type": "integer", "minimum": 1024, "maximum": 5_000_000},
                },
                "required": ["source_path"],
            },
            availability_check=lambda: _status(
                available=True,
                mode="ready",
                reason="Source file snapshot workflow is available with path guardrails and pagination.",
            ),
        )
    )
    registry.register(
        ResearchToolSpec(
            name="browser.web_extract",
            toolset="browser",
            description="Extract textual evidence, PDF links, supplementary links, and provenance metadata from public HTTP(S) pages.",
            phases=("literature_review", "evidence_audit"),
            risk_level="network",
            requires=("requests",),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_bytes": {"type": "integer", "minimum": 4096, "maximum": 3_000_000},
                    "max_text_chars": {"type": "integer", "minimum": 1000, "maximum": 200_000},
                    "ingest_to_knowledge_base": {"type": "boolean"},
                },
                "required": ["url"],
            },
            availability_check=requests_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="browser.capture_screenshot",
            toolset="browser",
            description="Capture a Playwright/Chromium screenshot and browser metadata for public HTTP(S) evidence pages.",
            phases=("literature_review", "evidence_audit"),
            risk_level="network",
            requires=("playwright", "chromium browser"),
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "viewport_width": {"type": "integer", "minimum": 320, "maximum": 3840},
                    "viewport_height": {"type": "integer", "minimum": 240, "maximum": 2160},
                    "full_page": {"type": "boolean"},
                    "timeout_ms": {"type": "integer", "minimum": 1000, "maximum": 60000},
                },
                "required": ["url"],
            },
            availability_check=playwright_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="code.execute_analysis",
            toolset="code_execution",
            description="Run restricted Python analysis for batch evidence reduction, statistics, and experiment-log summaries.",
            phases=("experiment_design", "experiment_analysis"),
            risk_level="sandboxed_write",
            requires=("python", "AST guard", "timeout"),
            input_schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
                },
                "required": ["code"],
            },
            availability_check=restricted_python_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="experiment.background_job",
            toolset="experiment",
            description="Run an approved Python experiment script from the configured experiment root as a background job.",
            phases=("experiment_design", "experiment_execution"),
            risk_level="background_write",
            requires=("approval workflow", "python", "experiment root", "background job store"),
            input_schema={
                "type": "object",
                "properties": {
                    "script_path": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 3600},
                },
                "required": ["script_path"],
            },
            availability_check=experiment_runner_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="ssh.training_command",
            toolset="ssh_training",
            description="Run an approved remote training command on a whitelisted SSH server as a tracked background job.",
            phases=("experiment_design", "experiment_execution"),
            risk_level="remote_background_write",
            requires=("OpenSSH client", "workspace SSH host aliases", "approval workflow", "background job store"),
            input_schema={
                "type": "object",
                "properties": {
                    "server_id": {
                        "type": "string",
                        "enum": ["c201-4090", "c201-5080", "d437"],
                    },
                    "command": {"type": "string"},
                    "workdir": {"type": "string"},
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 86400},
                },
                "required": ["server_id", "command"],
            },
            availability_check=ssh_training_runner_status,
        )
    )
    registry.register(
        ResearchToolSpec(
            name="terminal.command",
            toolset="terminal",
            description=(
                "Run a local PowerShell/bash command through the command permission policy. "
                "The workflow stores stdout, stderr, manifest, guardrail, and tool-result provenance."
            ),
            phases=("operator_diagnostics",),
            risk_level="terminal_exec",
            requires=("command permission mode", "audit log", "destructive-command guardrail"),
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "workdir": {"type": "string"},
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 3600},
                },
                "required": ["command"],
            },
            availability_check=terminal_command_status,
        )
    )
    return registry
