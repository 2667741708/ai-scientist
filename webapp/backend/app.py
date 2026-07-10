from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import requests

try:
    from backend.analysis_executor import execute_restricted_python
    from backend.auth_store import (
        authenticate,
        create_account,
        get_recovery_challenge,
        init_auth_store,
        list_accounts,
        record_local_account_secret,
        require_permission,
        require_user,
        reset_account_password,
        reset_password_with_recovery,
        role_rows,
        set_account_status,
    )
    from backend.mcp_runtime import (
        literature_mcp_runtime_status,
        start_literature_mcp_service,
    )
    from backend.browser_capture import (
        BrowserCaptureError,
        capture_browser_screenshot,
    )
    from backend.command_permissions import (
        classify_command_risk,
        command_requires_approval,
        get_command_permission_policy,
        set_command_permission_policy,
    )
    from backend.evidence_verification_agent import EvidenceVerificationAgent
    from backend.experiment_runner import (
        ExperimentRunnerError,
        run_python_experiment,
        validate_experiment_script,
    )
    from backend.file_evidence import FileEvidenceError, snapshot_source_file
    from backend.knowledge_base import DEFAULT_LIBRARY_ID, KnowledgeBaseStore, reliability_for_source
    from backend.paper_interpreter import interpret_paper_pdf, result_to_dict
    from backend.paper_parse_store import PaperParseEvidenceStore
    from backend.pdf_region_audit import summarize_media_region_quality
    from backend.pdf_parser import parse_pdf_to_solve
    from backend.research_tools import (
        authorize_tool_for_phase,
        build_default_research_tool_registry,
        canonical_phase,
        list_phase_tool_policies,
    )
    from backend.research_skills import get_research_skill, list_research_skills
    from backend.research_autopilot import (
        AutopilotValidationError,
        build_experiment_protocol,
        build_loop_state,
        consume_exact_grant,
        evaluate_experiment_result,
        exact_grant,
        execution_scope,
        normalize_policy,
        parse_result_json_marker,
        update_loop_stage,
    )
    from backend.remote_workspace import (
        RemoteWorkspaceError,
        create_tmux_session,
        delete_profile as delete_remote_workspace_profile,
        get_project_remote_root,
        import_ssh_config_profile,
        kill_tmux_session,
        list_profiles as list_remote_workspace_profiles,
        list_remote_directory,
        list_tmux_sessions,
        parse_ssh_config,
        remote_workspace_status,
        rename_tmux_session,
        save_profile as save_remote_workspace_profile,
        set_project_remote_root,
    )
    from backend.ssh_training import (
        SshTrainingError,
        build_ssh_mcp_server_templates,
        list_ssh_training_servers,
        redact_sensitive_text,
        run_ssh_training_command,
        ssh_training_status,
        validate_ssh_training_command,
    )
    from backend.terminal_command import (
        TerminalCommandError,
        run_terminal_command,
        terminal_command_status,
        validate_terminal_command,
    )
    from backend.web_terminal import (
        WebTerminalError,
        close_web_terminal_session,
        create_web_terminal_session,
        get_web_terminal_session,
        list_web_terminal_sessions,
        web_terminal_status,
    )
    from backend.web_evidence import WebEvidenceError, extract_web_evidence
    from backend.web_search import WebSearchError, search_public_web
    from backend.worker_runtime import ResearchWorkerRuntime, default_worker_owner
except ModuleNotFoundError:
    from analysis_executor import execute_restricted_python
    from auth_store import (
        authenticate,
        create_account,
        get_recovery_challenge,
        init_auth_store,
        list_accounts,
        record_local_account_secret,
        require_permission,
        require_user,
        reset_account_password,
        reset_password_with_recovery,
        role_rows,
        set_account_status,
    )
    from mcp_runtime import (
        literature_mcp_runtime_status,
        start_literature_mcp_service,
    )
    from browser_capture import BrowserCaptureError, capture_browser_screenshot
    from command_permissions import (
        classify_command_risk,
        command_requires_approval,
        get_command_permission_policy,
        set_command_permission_policy,
    )
    from evidence_verification_agent import EvidenceVerificationAgent
    from experiment_runner import ExperimentRunnerError, run_python_experiment, validate_experiment_script
    from file_evidence import FileEvidenceError, snapshot_source_file
    from knowledge_base import DEFAULT_LIBRARY_ID, KnowledgeBaseStore, reliability_for_source
    from paper_interpreter import interpret_paper_pdf, result_to_dict
    from paper_parse_store import PaperParseEvidenceStore
    from pdf_region_audit import summarize_media_region_quality
    from pdf_parser import parse_pdf_to_solve
    from research_tools import (
        authorize_tool_for_phase,
        build_default_research_tool_registry,
        canonical_phase,
        list_phase_tool_policies,
    )
    from research_skills import get_research_skill, list_research_skills
    from research_autopilot import (
        AutopilotValidationError,
        build_experiment_protocol,
        build_loop_state,
        consume_exact_grant,
        evaluate_experiment_result,
        exact_grant,
        execution_scope,
        normalize_policy,
        parse_result_json_marker,
        update_loop_stage,
    )
    from remote_workspace import (
        RemoteWorkspaceError,
        create_tmux_session,
        delete_profile as delete_remote_workspace_profile,
        get_project_remote_root,
        import_ssh_config_profile,
        kill_tmux_session,
        list_profiles as list_remote_workspace_profiles,
        list_remote_directory,
        list_tmux_sessions,
        parse_ssh_config,
        remote_workspace_status,
        rename_tmux_session,
        save_profile as save_remote_workspace_profile,
        set_project_remote_root,
    )
    from ssh_training import (
        SshTrainingError,
        build_ssh_mcp_server_templates,
        list_ssh_training_servers,
        redact_sensitive_text,
        run_ssh_training_command,
        ssh_training_status,
        validate_ssh_training_command,
    )
    from terminal_command import (
        TerminalCommandError,
        run_terminal_command,
        terminal_command_status,
        validate_terminal_command,
    )
    from web_terminal import (
        WebTerminalError,
        close_web_terminal_session,
        create_web_terminal_session,
        get_web_terminal_session,
        list_web_terminal_sessions,
        web_terminal_status,
    )
    from web_evidence import WebEvidenceError, extract_web_evidence
    from web_search import WebSearchError, search_public_web
    from worker_runtime import ResearchWorkerRuntime, default_worker_owner

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class FeedbackItem(BaseModel):
    feedback_id: Optional[str] = None
    target_type: Literal["run", "hypothesis", "ranking", "evidence", "experiment"] = "run"
    target_ref: Dict[str, Any] = Field(default_factory=dict)
    feedback_type: Literal["accept", "reject", "edit", "prefer", "critique", "constraint"] = "critique"
    text: str = Field(..., min_length=1, max_length=4000)
    created_at: Optional[float] = None


class RunRequest(BaseModel):
    research_goal: str = Field(..., min_length=8)
    model_name: str = "deepseek/deepseek-v4-pro"
    demo_mode: bool = True
    literature_review: bool = False
    initial_hypotheses: int = Field(3, ge=1, le=8)
    iterations: int = Field(0, ge=0, le=3)
    min_references: int = Field(2, ge=0, le=12)
    max_references: int = Field(6, ge=0, le=12)
    preferences: Optional[str] = Field(default=None, max_length=4000)
    attributes: List[str] = Field(default_factory=list, max_length=20)
    constraints: List[str] = Field(default_factory=list, max_length=40)
    starting_hypotheses: List[str] = Field(default_factory=list, max_length=20)
    user_feedback: List[FeedbackItem] = Field(default_factory=list, max_length=50)
    parent_run_id: Optional[str] = Field(default=None, max_length=80)
    refinement_mode: Literal["new_run", "continue_from_run", "revise_hypotheses"] = "new_run"
    memory_scope: Literal["current_run", "project", "library", "global"] = "project"
    library_id: Optional[str] = Field(default=None, max_length=120)
    auto_discover_papers: bool = True
    auto_ingest_papers: bool = True
    paper_discovery_limit: int = Field(default=8, ge=1, le=20)
    paper_ingest_limit: int = Field(default=4, ge=0, le=12)
    autopilot: Dict[str, Any] = Field(default_factory=dict)


class ContinueRunRequest(BaseModel):
    research_goal: Optional[str] = Field(default=None, min_length=8)
    model_name: Optional[str] = None
    demo_mode: Optional[bool] = None
    literature_review: Optional[bool] = None
    initial_hypotheses: Optional[int] = Field(default=None, ge=1, le=8)
    iterations: Optional[int] = Field(default=None, ge=0, le=3)
    min_references: Optional[int] = Field(default=None, ge=0, le=12)
    max_references: Optional[int] = Field(default=None, ge=0, le=12)
    preferences: Optional[str] = Field(default=None, max_length=4000)
    attributes: List[str] = Field(default_factory=list, max_length=20)
    constraints: List[str] = Field(default_factory=list, max_length=40)
    starting_hypotheses: List[str] = Field(default_factory=list, max_length=20)
    user_feedback: List[FeedbackItem] = Field(default_factory=list, max_length=40)
    refinement_mode: Literal["new_run", "continue_from_run", "revise_hypotheses"] = "continue_from_run"
    memory_scope: Optional[Literal["current_run", "project", "library", "global"]] = None
    library_id: Optional[str] = Field(default=None, max_length=120)
    auto_discover_papers: Optional[bool] = None
    auto_ingest_papers: Optional[bool] = None
    paper_discovery_limit: Optional[int] = Field(default=None, ge=1, le=20)
    paper_ingest_limit: Optional[int] = Field(default=None, ge=0, le=12)


class ResearchAutopilotRequest(BaseModel):
    policy: Dict[str, Any] = Field(default_factory=dict)


class ResearchAutopilotResumeRequest(BaseModel):
    grants: List[Dict[str, Any]] = Field(default_factory=list, max_length=20)
    compute: Optional[Dict[str, Any]] = None
    evaluation: Optional[Dict[str, Any]] = None
    continue_on_limited_evidence: Optional[bool] = None
    auto_interpret: Optional[bool] = None
    auto_rerank: Optional[bool] = None


class TranslationRequest(BaseModel):
    model_name: str = "deepseek/deepseek-v4-pro"
    text: str = Field(..., min_length=1)
    explanation: Optional[str] = None
    experiment: Optional[str] = None
    target_language: str = Field(default="zh-Hans", max_length=20)
    provider: Literal["auto", "microsoft", "model"] = "auto"


class AuthLoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=180)
    password: str = Field(..., min_length=1, max_length=200)


class AuthRegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=180)
    password: str = Field(..., min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=120)
    recovery_question: str = Field(default="", max_length=200)
    recovery_answer: str = Field(default="", max_length=200)


class AuthRecoveryChallengeRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=180)


class AuthRecoveryResetRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=180)
    answer: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)


class AdminAccountCreateRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=180)
    password: str = Field(..., min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=120)
    role: Literal["researcher", "admin"] = "researcher"


class AdminAccountStatusRequest(BaseModel):
    status: Literal["active", "disabled"]


class AdminAccountPasswordRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=200)


class PaperIngestRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    content: str = Field(..., min_length=20, max_length=400_000)
    authors: List[str] = Field(default_factory=list, max_length=20)
    year: Optional[int] = Field(default=None, ge=1500, le=2200)
    doi: Optional[str] = Field(default=None, max_length=160)
    url: Optional[str] = Field(default=None, max_length=600)
    abstract: Optional[str] = Field(default=None, max_length=20_000)
    source: str = Field(default="user_upload", max_length=80)
    source_reliability: Optional[str] = Field(default=None, max_length=80)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    library_id: Optional[str] = Field(default=None, max_length=120)


class PdfParseRequest(BaseModel):
    pdf_path: str = Field(..., min_length=4, max_length=1200)
    fetch_metadata: bool = True
    ingest_to_knowledge_base: bool = True
    library_id: Optional[str] = Field(default=None, max_length=120)


class RagflowReindexRequest(BaseModel):
    library_id: Optional[str] = Field(default=None, max_length=120)
    paper_id: Optional[str] = Field(default=None, max_length=160)


class LiteratureLibraryCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)


class PaperInterpretRequest(BaseModel):
    pdf_path: str = Field(..., min_length=4, max_length=1200)
    output_name: str = Field(..., min_length=1, max_length=120)
    model_name: str = "deepseek/deepseek-v4-pro"
    fetch_metadata: bool = True


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., min_length=3, max_length=120)
    phase: str = Field(default="literature_review", min_length=2, max_length=80)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    run_id: Optional[str] = Field(default=None, max_length=80)
    hypothesis_id: Optional[str] = Field(default=None, max_length=120)
    hypothesis_index: Optional[int] = Field(default=None, ge=0)


class ToolWorkflowApproval(BaseModel):
    confirmed: bool = False
    scope: str = Field(default="", max_length=120)
    reason: Optional[str] = Field(default=None, max_length=500)


class LiteratureDiscoveryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    library_id: Optional[str] = Field(default=None, max_length=120)
    preferred_source: Literal["auto", "all", "arxiv", "pubmed", "scholar"] = "auto"
    max_results: int = Field(default=12, ge=1, le=20)
    planning_mode: Literal["llm", "rules"] = "llm"
    model_name: Optional[str] = Field(default=None, max_length=120)
    auto_discover_pdf_links: bool = True
    auto_ingest_pdfs: bool = False
    auto_ingest_limit: int = Field(default=4, ge=0, le=12)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class LiteratureCitationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    source: Optional[str] = Field(default=None, max_length=160)
    source_id: Optional[str] = Field(default=None, max_length=300)
    doi: Optional[str] = Field(default=None, max_length=300)
    arxiv_id: Optional[str] = Field(default=None, max_length=120)
    url: Optional[str] = Field(default=None, max_length=1200)
    pdf_url: Optional[str] = Field(default=None, max_length=1200)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class PdfParseToolWorkflowRequest(BaseModel):
    pdf_path: str = Field(..., min_length=4, max_length=1200)
    phase: str = Field(default="paper_reading", min_length=2, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    fetch_metadata: bool = True
    ingest_to_knowledge_base: bool = True
    library_id: Optional[str] = Field(default=None, max_length=120)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class McpToolWorkflowRequest(BaseModel):
    workflow_name: str = Field(default="literature_review", min_length=2, max_length=120)
    tool_id: Optional[str] = Field(default=None, max_length=120)
    mcp_tool_name: Optional[str] = Field(default=None, max_length=160)
    phase: str = Field(default="literature_review", min_length=2, max_length=80)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    run_id: Optional[str] = Field(default=None, max_length=80)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class EvidenceVerificationWorkflowRequest(BaseModel):
    hypothesis_text: str = Field(..., min_length=8, max_length=4000)
    run_id: Optional[str] = Field(default=None, max_length=80)
    paper_id: Optional[str] = Field(default=None, max_length=120)
    library_id: Optional[str] = Field(default=None, max_length=120)
    max_papers: int = Field(default=5, ge=1, le=10)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class WebExtractWorkflowRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=1200)
    phase: str = Field(default="literature_review", min_length=2, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    max_bytes: int = Field(default=1_000_000, ge=4096, le=3_000_000)
    max_text_chars: int = Field(default=80_000, ge=1000, le=200_000)
    ingest_to_knowledge_base: bool = True
    library_id: Optional[str] = Field(default=None, max_length=120)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class WebSearchWorkflowRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=600)
    phase: str = Field(default="literature_review", min_length=2, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    limit: int = Field(default=10, ge=1, le=20)
    domains: List[str] = Field(default_factory=list, max_length=8)
    recency_days: Optional[int] = Field(default=None, ge=1, le=3650)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class BrowserScreenshotWorkflowRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=1200)
    phase: str = Field(default="evidence_audit", min_length=2, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    viewport_width: int = Field(default=1365, ge=320, le=3840)
    viewport_height: int = Field(default=768, ge=240, le=2160)
    full_page: bool = True
    timeout_ms: int = Field(default=30_000, ge=1000, le=60_000)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class FileSnapshotWorkflowRequest(BaseModel):
    source_path: str = Field(..., min_length=1, max_length=1200)
    phase: str = Field(default="evidence_audit", min_length=2, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    start_line: int = Field(default=1, ge=1)
    line_count: int = Field(default=200, ge=1, le=2000)
    max_bytes: int = Field(default=1_000_000, ge=1024, le=5_000_000)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class ProjectToolRegistrationRequest(BaseModel):
    tool_name: str = Field(..., min_length=2, max_length=120)
    user_title: Optional[str] = Field(default=None, max_length=160)
    description: str = Field(..., min_length=4, max_length=1200)
    toolset: str = Field(default="project_custom", min_length=2, max_length=80)
    phases: List[str] = Field(default_factory=lambda: ["evidence_audit"], max_length=8)
    risk_level: Literal["read", "network", "write", "sandboxed_write", "background_write"] = "read"
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    execution_boundary: str = Field(default="schema_registered_only", max_length=1000)
    run_id: Optional[str] = Field(default=None, max_length=80)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class CodeAnalysisWorkflowRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=20_000)
    phase: str = Field(default="experiment_analysis", min_length=2, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class ExperimentBackgroundJobRequest(BaseModel):
    script_path: str = Field(..., min_length=1, max_length=1200)
    args: List[str] = Field(default_factory=list, max_length=50)
    phase: str = Field(default="experiment_execution", min_length=2, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    hypothesis_index: Optional[int] = Field(default=None, ge=0, le=200)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class ExperimentFeedbackRequest(BaseModel):
    job_id: str = Field(..., min_length=3, max_length=120)
    hypothesis_index: int = Field(..., ge=0, le=200)
    verdict: Literal["support", "contradict", "inconclusive"]
    rationale: str = Field(..., min_length=3, max_length=4000)
    rerank: bool = True
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class SshTrainingJobRequest(BaseModel):
    server_id: str = Field(..., min_length=2, max_length=80)
    command: str = Field(..., min_length=1, max_length=20_000)
    workdir: Optional[str] = Field(default=None, max_length=600)
    phase: str = Field(default="experiment_execution", min_length=2, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    timeout_seconds: int = Field(default=3600, ge=1, le=86400)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class CommandPermissionUpdateRequest(BaseModel):
    mode: Literal["request_approval", "approve_safe", "full_access"]


class TerminalCommandWorkflowRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=20_000)
    workdir: Optional[str] = Field(default=None, max_length=1200)
    phase: str = Field(default="operator_diagnostics", min_length=2, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class WebTerminalSessionCreateRequest(BaseModel):
    profile: Optional[str] = Field(default=None, max_length=80)
    cwd: Optional[str] = Field(default=None, max_length=1200)
    cols: int = Field(default=100, ge=20, le=400)
    rows: int = Field(default=30, ge=8, le=120)
    ssh_target: Optional[str] = Field(default=None, max_length=300)
    ssh_remote_cwd: Optional[str] = Field(default=None, max_length=1200)
    ssh_tmux_session: Optional[str] = Field(default=None, max_length=120)


class RemoteWorkspaceProfileRequest(BaseModel):
    profile_id: Optional[str] = Field(default=None, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    host: Optional[str] = Field(default=None, max_length=300)
    port: int = Field(default=22, ge=1, le=65535)
    username: Optional[str] = Field(default=None, max_length=120)
    auth_type: Literal["ssh_config", "password", "private_key", "agent"] = "agent"
    password: Optional[str] = Field(default=None, max_length=2000)
    private_key_path: Optional[str] = Field(default=None, max_length=1200)
    passphrase: Optional[str] = Field(default=None, max_length=2000)
    ssh_config_alias: Optional[str] = Field(default=None, max_length=240)
    default_remote_path: Optional[str] = Field(default=None, max_length=1200)


class RemoteWorkspaceImportRequest(BaseModel):
    alias: str = Field(..., min_length=1, max_length=240)
    password: Optional[str] = Field(default=None, max_length=2000)
    default_remote_path: Optional[str] = Field(default=None, max_length=1200)


class ProjectRemoteRootRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=80)
    remote_path: str = Field(..., min_length=1, max_length=1200)
    label: Optional[str] = Field(default=None, max_length=160)


class RemoteTmuxCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    workdir: Optional[str] = Field(default=None, max_length=1200)


class RemoteTmuxRenameRequest(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=120)


TaskStatus = Literal["backlog", "ready", "running", "blocked", "done", "archived"]
ScheduleStatus = Literal["active", "paused", "archived"]
DelegationStatus = Literal["planned", "running", "completed", "blocked", "archived"]


class ResearchTaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=240)
    task_type: str = Field(default="other", min_length=2, max_length=80)
    status: TaskStatus = "backlog"
    priority: int = Field(default=3, ge=1, le=5)
    phase: Optional[str] = Field(default=None, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    target_ref: Dict[str, Any] = Field(default_factory=dict)
    result_ref: Dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=4000)
    blocked_reason: Optional[str] = Field(default=None, max_length=1000)
    due_at: Optional[float] = None


class ResearchTaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=240)
    task_type: Optional[str] = Field(default=None, min_length=2, max_length=80)
    status: Optional[TaskStatus] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    phase: Optional[str] = Field(default=None, max_length=80)
    target_ref: Optional[Dict[str, Any]] = None
    result_ref: Optional[Dict[str, Any]] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    blocked_reason: Optional[str] = Field(default=None, max_length=1000)
    due_at: Optional[float] = None


class ResearchScheduleCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=240)
    workflow_name: str = Field(..., min_length=2, max_length=120)
    status: ScheduleStatus = "active"
    interval_hours: float = Field(default=24.0, ge=0.1, le=8760)
    phase: Optional[str] = Field(default=None, max_length=80)
    run_id: Optional[str] = Field(default=None, max_length=80)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    next_run_at: Optional[float] = None
    auto_execute: bool = False
    approval: Optional[ToolWorkflowApproval] = None


class ResearchScheduleUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=240)
    workflow_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    status: Optional[ScheduleStatus] = None
    interval_hours: Optional[float] = Field(default=None, ge=0.1, le=8760)
    phase: Optional[str] = Field(default=None, max_length=80)
    arguments: Optional[Dict[str, Any]] = None
    last_run_at: Optional[float] = None
    next_run_at: Optional[float] = None
    result_ref: Optional[Dict[str, Any]] = None


class ResearchScheduleTickRequest(BaseModel):
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)
    force: bool = False


class DelegationAgentBrief(BaseModel):
    role: str = Field(..., min_length=2, max_length=120)
    brief: str = Field(..., min_length=3, max_length=2000)
    skill_ids: List[str] = Field(default_factory=list, max_length=12)
    target_ref: Dict[str, Any] = Field(default_factory=dict)


class ResearchDelegationCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=240)
    phase: str = Field(default="review_critique", min_length=2, max_length=80)
    strategy: str = Field(default="parallel_review", min_length=2, max_length=80)
    status: DelegationStatus = "planned"
    run_id: Optional[str] = Field(default=None, max_length=80)
    agents: List[DelegationAgentBrief] = Field(..., min_length=1, max_length=12)
    target_ref: Dict[str, Any] = Field(default_factory=dict)
    result_ref: Dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(default="", max_length=4000)


class ResearchDelegationUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=240)
    phase: Optional[str] = Field(default=None, min_length=2, max_length=80)
    strategy: Optional[str] = Field(default=None, min_length=2, max_length=80)
    status: Optional[DelegationStatus] = None
    agents: Optional[List[DelegationAgentBrief]] = Field(default=None, min_length=1, max_length=12)
    target_ref: Optional[Dict[str, Any]] = None
    result_ref: Optional[Dict[str, Any]] = None
    summary: Optional[str] = Field(default=None, max_length=4000)


class ResearchDelegationRunRequest(BaseModel):
    model_name: str = "deepseek/deepseek-v4-pro"
    max_tokens: int = Field(default=1600, ge=300, le=6000)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class ResearchChatContext(BaseModel):
    page: Optional[str] = Field(default=None, max_length=80)
    page_path: Optional[str] = Field(default=None, max_length=240)
    mode: Literal["workspace", "project_help", "evidence"] = "workspace"
    run_id: Optional[str] = Field(default=None, max_length=80)
    paper_id: Optional[str] = Field(default=None, max_length=120)
    library_id: Optional[str] = Field(default=None, max_length=120)
    selected_hypothesis_id: Optional[str] = Field(default=None, max_length=160)
    selected_hypothesis_index: Optional[int] = Field(default=None, ge=0, le=200)
    selected_source_ref: Optional[str] = Field(default=None, max_length=240)
    model_name: Optional[str] = Field(default=None, max_length=120)
    literature_review: bool = True
    demo_mode: bool = False
    initial_hypotheses: int = Field(default=3, ge=1, le=8)
    iterations: int = Field(default=0, ge=0, le=3)
    min_references: int = Field(default=2, ge=0, le=12)
    max_references: int = Field(default=6, ge=0, le=12)
    language: Literal["zh", "en"] = "zh"


class ResearchChatTurnRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, max_length=80)
    message: str = Field(..., min_length=1, max_length=4000)
    context: ResearchChatContext = Field(default_factory=ResearchChatContext)


class ResearchChatConfirmRequest(BaseModel):
    approval: ToolWorkflowApproval = Field(default_factory=ToolWorkflowApproval)


class TimelineEvent(BaseModel):
    time: str
    stage: str
    event: str
    details: str
    status: Literal["queued", "active", "complete", "error"] = "complete"


class AgentTrace(BaseModel):
    event_id: str
    parent_event_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent: str
    role: str
    phase: str
    prompt_template: Optional[str] = None
    status: Literal["queued", "active", "complete", "error"] = "complete"
    output: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    token_usage: Dict[str, int] = Field(default_factory=dict)
    degradation_reason: Optional[str] = None
    synthetic: bool = True
    confidence: float = Field(..., ge=0, le=1)


class RunRecord(BaseModel):
    run_id: str
    status: Literal["queued", "running", "complete", "error"]
    created_at: float
    updated_at: float
    request: RunRequest
    timeline: List[TimelineEvent] = Field(default_factory=list)
    hypotheses: List[Dict[str, Any]] = Field(default_factory=list)
    research_plan: Dict[str, Any] = Field(default_factory=dict)
    agent_trace: List[AgentTrace] = Field(default_factory=list)
    tournament_matchups: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    safety_gate: Dict[str, Any] = Field(default_factory=dict)
    citation_provenance_qa: Dict[str, Any] = Field(default_factory=dict)
    evidence_snapshot: Dict[str, Any] = Field(default_factory=dict)
    research_outcome: Dict[str, Any] = Field(default_factory=dict)
    research_loop: Dict[str, Any] = Field(default_factory=dict)
    expert_feedback: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class ProjectArtifactRequest(BaseModel):
    run_id: str = Field(..., min_length=1, max_length=80)
    artifact_type: Literal["hypothesis", "evidence_link", "experiment_plan"]
    target_ref: Dict[str, Any] = Field(default_factory=dict)
    title: str = Field(default="", max_length=240)
    payload: Dict[str, Any] = Field(default_factory=dict)


class ExperimentPlanRequest(BaseModel):
    run_id: str = Field(..., min_length=1, max_length=80)
    hypothesis_index: int = Field(0, ge=0, le=200)


app = FastAPI(title="Open Coscientist Studio API")


def _configured_cors_origins() -> list[str]:
    defaults = [
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:5175",
        "http://localhost:5175",
        "http://127.0.0.1:4174",
        "http://localhost:4174",
    ] + [f"http://127.0.0.1:{port}" for port in range(8001, 8031)] + [
        f"http://localhost:{port}" for port in range(8001, 8031)
    ]
    configured = [
        origin.strip()
        for origin in os.getenv("COSCIENTIST_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    return list(dict.fromkeys([*defaults, *configured]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_configured_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REQUIRE_API_AUTH = os.getenv("COSCIENTIST_REQUIRE_AUTH", "0").lower() in {"1", "true", "yes", "on"}
API_RATE_LIMIT_PER_MINUTE = max(0, int(os.getenv("COSCIENTIST_RATE_LIMIT_PER_MINUTE", "0")))
API_RATE_LIMIT_WINDOW_SECONDS = 60.0
_api_rate_limit_hits: Dict[str, deque[float]] = defaultdict(deque)
PUBLIC_API_PATHS = {
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/recovery/challenge",
    "/api/auth/recovery/reset",
    "/api/health",
}


@app.middleware("http")
async def optional_api_auth(request, call_next):
    """Enable a production auth boundary without changing local demo defaults."""
    path = request.url.path
    if API_RATE_LIMIT_PER_MINUTE > 0 and path.startswith("/api/") and request.method != "OPTIONS":
        client_host = request.client.host if request.client else "unknown"
        rate_key = f"{client_host}:{path}"
        now = time.monotonic()
        hits = _api_rate_limit_hits[rate_key]
        while hits and now - hits[0] >= API_RATE_LIMIT_WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= API_RATE_LIMIT_PER_MINUTE:
            retry_after = max(1, int(API_RATE_LIMIT_WINDOW_SECONDS - (now - hits[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "api rate limit exceeded", "retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
    if REQUIRE_API_AUTH and path.startswith("/api/") and path not in PUBLIC_API_PATHS and request.method != "OPTIONS":
        try:
            require_user(request.headers.get("authorization"))
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, (str, dict, list)) else "unauthorized"
            return JSONResponse(status_code=exc.status_code, content={"detail": detail})
    return await call_next(request)

runs: Dict[str, RunRecord] = {}
research_chat_action_proposals: Dict[str, Dict[str, Any]] = {}

RUN_TIMEOUT_SECONDS = int(os.getenv("COSCIENTIST_RUN_TIMEOUT_SECONDS", "900"))
STALE_RUN_GRACE_SECONDS = RUN_TIMEOUT_SECONDS + 30
WORKER_AUTOSTART_ENABLED = os.getenv("COSCIENTIST_WORKER_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
WORKER_CONCURRENCY = max(1, int(os.getenv("COSCIENTIST_WORKER_CONCURRENCY", "1")))
WORKER_LEASE_SECONDS = max(1, int(os.getenv("COSCIENTIST_WORKER_LEASE_SECONDS", "300")))
WORKER_POLL_SECONDS = max(0.1, float(os.getenv("COSCIENTIST_WORKER_POLL_SECONDS", "2")))
WORKER_OWNER = os.getenv("COSCIENTIST_WORKER_OWNER") or default_worker_owner()
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8888/mcp")
MCP_AUTOSTART = os.getenv("COSCIENTIST_MCP_AUTOSTART", "1").lower() in {"1", "true", "yes", "on"}
KB_ROOT = Path(os.getenv("COSCIENTIST_KNOWLEDGE_BASE_DIR", str(ROOT / "webapp" / ".knowledge_base")))
init_auth_store()
knowledge_base = KnowledgeBaseStore(KB_ROOT)
paper_parse_store = PaperParseEvidenceStore(KB_ROOT)
evidence_verifier = EvidenceVerificationAgent()
EXPERIMENT_ROOT = Path(os.getenv("COSCIENTIST_EXPERIMENT_ROOT", str(ROOT / "webapp" / ".experiments")))
EXPERIMENT_ARTIFACT_ROOT = KB_ROOT / "experiment_jobs"
SSH_TRAINING_ARTIFACT_ROOT = KB_ROOT / "ssh_training_jobs"
TERMINAL_COMMAND_ARTIFACT_ROOT = KB_ROOT / "terminal_command_jobs"
SOURCE_EVIDENCE_ROOT = Path(os.getenv("COSCIENTIST_SOURCE_EVIDENCE_ROOT", str(ROOT)))
PROJECT_TOOL_DRAFTS_PATH = KB_ROOT / "project_tool_drafts.json"
REMOTE_WORKSPACE_STORE_PATH = KB_ROOT / "remote_workspaces.json"
worker_runtime: Optional[ResearchWorkerRuntime] = None
research_chat_llm_module: Optional[Any] = None

WEAK_SUPPORT_LEVELS = {"metadata", "abstract", "unknown"}
WEAK_SOURCE_RELIABILITY = {"best_effort_public_html"}
PDF_PATTERN = re.compile(
    r"(?P<value>(?:[a-zA-Z]:\\[^\s\"'<>]+?\.pdf|https?://[^\s\"'<>]+?\.pdf)(?:[?#][^\s\"'<>]+)?)",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"(?P<value>https?://[^\s\"'<>]+)", re.IGNORECASE)
SOURCE_FILE_PATTERN = re.compile(
    r"(?P<value>(?:[a-zA-Z]:\\[^\r\n\"'<>]+|(?:\.{1,2}[\\/]|[A-Za-z0-9_.-]+[\\/])"
    r"[^\r\n\"'<>]+))",
    re.IGNORECASE,
)
COMMAND_CODE_BLOCK_PATTERN = re.compile(
    r"```(?:powershell|pwsh|bash|sh|shell|cmd|terminal)?\s*\n(?P<command>[\s\S]+?)```",
    re.IGNORECASE,
)
WEB_SEARCH_SITE_PATTERN = re.compile(
    r"(?:^|\s)site:(?P<domain>[A-Za-z0-9][A-Za-z0-9.-]{0,250}[A-Za-z0-9])",
    re.IGNORECASE,
)
PROJECT_CHAT_KNOWLEDGE_VERSION = "project-chat-rag-v3"


def _path_summary(value: str) -> str:
    parsed = urllib.parse.urlparse(value.strip())
    if parsed.scheme in {"http", "https"}:
        host = parsed.netloc or "remote PDF"
        name = Path(urllib.parse.unquote(parsed.path)).name or host
        return f"{host} / {name}"
    return Path(value.strip()).name or "本机 PDF"


def _url_summary(value: str) -> str:
    parsed = urllib.parse.urlparse(value.strip())
    return parsed.netloc or value[:120]


def _clean_public_url_candidate(value: str) -> str:
    return value.strip().rstrip(".,;:，。；：、)]}）】")


def _extract_public_urls(text: str, *, limit: int = 5) -> List[str]:
    urls: List[str] = []
    seen: set[str] = set()
    for match in URL_PATTERN.finditer(text):
        url = _clean_public_url_candidate(match.group("value"))
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _clean_command_candidate(value: str) -> str:
    command = (value or "").strip(" \t\r\n：:。")
    command = re.sub(r"^(?:命令|command|cmd)\s*[:：]\s*", "", command, flags=re.IGNORECASE).strip()
    if len(command) >= 2 and command[0] == command[-1] and command[0] in {"'", '"', "`"}:
        command = command[1:-1].strip()
    return command[:20_000]


def _extract_code_block_command(text: str) -> Optional[str]:
    match = COMMAND_CODE_BLOCK_PATTERN.search(text)
    if not match:
        return None
    return _clean_command_candidate(match.group("command"))


def _extract_workdir(text: str) -> Optional[str]:
    match = re.search(r"(?:cwd|workdir|工作目录)\s*[:=：]\s*(?P<workdir>[^\r\n]+)", text, re.IGNORECASE)
    if not match:
        return None
    value = match.group("workdir").strip().strip("'\"`")
    return value[:1200] if value else None


def _clean_source_file_candidate(value: str) -> str:
    candidate = (value or "").strip(" \t\r\n：:。")
    candidate = re.split(
        r"\s+(?:start_line|line_count|max_bytes|起始行|开始行|行数|读取|快照)\b",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    candidate = candidate.strip().strip("'\"`").rstrip("，。,;；")
    return candidate[:1200]


def _extract_positive_int_after(text: str, terms: List[str], *, default: Optional[int] = None) -> Optional[int]:
    for term in terms:
        match = re.search(rf"{re.escape(term)}\s*[:=：]?\s*(?P<value>\d+)", text, re.IGNORECASE)
        if match:
            return max(1, int(match.group("value")))
    return default


def _extract_source_file_request(text: str) -> Optional[Dict[str, Any]]:
    if not _contains_any(
        text,
        [
            "文件快照",
            "读取文件",
            "读取本地文件",
            "查看本地文件",
            "本地文件快照",
            "source snapshot",
            "file snapshot",
            "local file",
            "source_path",
        ],
    ):
        return None
    source_path = ""
    explicit = re.search(
        r"(?:source_path|file|path|文件|路径)\s*[:=：]\s*(?P<path>[^\r\n]+)",
        text,
        re.IGNORECASE,
    )
    if explicit:
        source_path = _clean_source_file_candidate(explicit.group("path"))
    if not source_path:
        match = SOURCE_FILE_PATTERN.search(text)
        if match:
            source_path = _clean_source_file_candidate(match.group("value"))
    if not source_path:
        return {}
    payload: Dict[str, Any] = {"source_path": source_path}
    start_line = _extract_positive_int_after(text, ["start_line", "起始行", "开始行"])
    line_count = _extract_positive_int_after(text, ["line_count", "行数", "读取行数"])
    if start_line is not None:
        payload["start_line"] = start_line
    if line_count is not None:
        payload["line_count"] = line_count
    return payload


def _extract_tool_registration_request(text: str) -> Optional[Dict[str, Any]]:
    if not _contains_any(text, ["注册工具", "新增工具", "添加工具", "创建工具", "register tool", "add tool"]):
        return None
    payload: Dict[str, Any] = {}
    name_match = re.search(
        r"(?:tool_name|工具名|工具 ID|工具id|name)\s*[:=：]\s*(?P<name>[A-Za-z0-9_.-]{2,120})",
        text,
        re.IGNORECASE,
    )
    if name_match:
        payload["tool_name"] = name_match.group("name").strip()
    purpose_match = re.search(
        r"(?:description|描述|用途|purpose)\s*[:=：]\s*(?P<description>[^\r\n]+)",
        text,
        re.IGNORECASE,
    )
    if purpose_match:
        payload["description"] = purpose_match.group("description").strip()[:1200]
    return payload


def _extract_terminal_command_request(text: str) -> Optional[Dict[str, Any]]:
    lowered = text.lower()
    if re.match(r"^\s*ssh\s+[A-Za-z0-9_.@:-]+(?:\s+.+)?$", text, re.IGNORECASE | re.S):
        command = _clean_command_candidate(text)
        return {"command": command} if command else None
    fenced = _extract_code_block_command(text)
    if fenced and _contains_any(text, ["执行", "运行", "跑", "命令", "command", "terminal", "shell", "bash", "powershell", "cmd"]):
        return {"command": fenced, "workdir": _extract_workdir(text)}
    command_terms = [
        "执行命令",
        "运行命令",
        "跑命令",
        "本地命令",
        "终端命令",
        "terminal command",
        "shell command",
        "bash command",
        "powershell command",
        "cmd command",
        "命令:",
        "命令：",
        "command:",
        "command：",
        "cmd:",
        "cmd：",
        "powershell:",
        "powershell：",
        "bash:",
        "bash：",
        "shell:",
        "shell：",
        "terminal:",
        "terminal：",
    ]
    if not any(term in lowered or term in text for term in command_terms):
        return None
    patterns = [
        r"(?:执行|运行|跑|调用|run)\s*(?:一下|这个|本地|local|terminal|shell|bash|powershell|pwsh|cmd|命令|command)?\s*(?:命令|command|cmd)?\s*[:：]\s*(?P<command>.+)$",
        r"(?:执行|运行|跑|调用|run)\s*(?:一下|这个)?\s*(?:本地|local)?\s*(?:命令|command|cmd)\s+(?P<command>.+)$",
        r"(?:本地命令|终端命令|terminal command|shell command|bash command|powershell command|PowerShell 命令)\s*[:：]\s*(?P<command>.+)$",
        r"(?:命令|command|cmd|powershell|pwsh|bash|shell|terminal)\s*[:：]\s*(?P<command>.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.S)
        if match:
            command = _clean_command_candidate(match.group("command"))
            if command:
                return {"command": command, "workdir": _extract_workdir(text)}
    return None


def _ssh_alias_map() -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    try:
        servers = list_ssh_training_servers()
    except Exception:
        return aliases
    for server in servers:
        server_id = str(server.get("server_id") or "").strip()
        if not server_id:
            continue
        aliases[server_id.lower()] = server_id
        aliases[str(server.get("ssh_alias") or server_id).lower()] = server_id
        for alias in server.get("aliases") or []:
            aliases[str(alias).lower()] = server_id
    return aliases


def _extract_managed_ssh_request(text: str) -> Optional[Dict[str, Any]]:
    lowered = text.lower()
    if "ssh" not in lowered and not any(term in text for term in ["连接到", "登录到", "登陆到", "在"]):
        return None
    if "本地命令" in text and re.search(r"\bssh\s+", text, re.IGNORECASE):
        return None
    aliases = _ssh_alias_map()
    if not aliases:
        return None
    for alias, server_id in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        alias_pattern = re.escape(alias)
        match = re.search(
            rf"(?:\bssh\s+|(?:在|到|连接到|登录到|登陆到)\s*){alias_pattern}"
            rf"(?:\s*(?:上|服务器|机器|节点|host))?"
            rf"\s*(?:帮我|请)?\s*(?:执行|运行|跑|run)?"
            rf"\s*(?:一下|这个)?\s*(?:命令|command|cmd)?\s*[:：]?\s*(?P<command>.+)?$",
            text,
            re.IGNORECASE | re.S,
        )
        if match:
            command = _clean_command_candidate(match.group("command") or "")
            payload: Dict[str, Any] = {"server_id": server_id}
            if command:
                payload["command"] = command
                workdir = _extract_workdir(text)
                if workdir:
                    payload["workdir"] = workdir
            return payload
    return None


def _extract_arbitrary_ssh_terminal_request(text: str) -> Optional[Dict[str, Any]]:
    aliases = _ssh_alias_map()
    explicit = re.search(r"\bssh\s+(?P<target>[A-Za-z0-9_.@:-]+)(?:\s+(?P<remote>.+))?$", text, re.IGNORECASE | re.S)
    if explicit:
        target = explicit.group("target").lower()
        if target in aliases:
            return None
        command = _clean_command_candidate(text[explicit.start() :])
        return {"command": command, "workdir": _extract_workdir(text)} if command else None
    natural = re.search(
        r"(?:在|到|连接到|登录到|登陆到)\s+(?P<target>[A-Za-z0-9_.@:-]{2,160})"
        r"(?:\s*(?:上|服务器|机器|节点|host))?\s*(?:帮我|请)?\s*(?:执行|运行|跑|run)"
        r"\s*(?:一下|这个)?\s*(?:命令|command|cmd)?\s*[:：]?\s*(?P<remote>.+)$",
        text,
        re.IGNORECASE | re.S,
    )
    if not natural:
        return None
    target = natural.group("target").strip()
    if target.lower() in aliases:
        return None
    remote = _clean_command_candidate(natural.group("remote"))
    if not remote:
        return {"target": target}
    return {"command": f"ssh {target} {remote}", "workdir": _extract_workdir(text), "ssh_target": target}


def _extract_web_search_request(text: str) -> Optional[Dict[str, Any]]:
    lowered = text.lower()
    if _looks_like_conditional_tool_boundary(text):
        return None
    if not (
        "websearch" in lowered
        or "web search" in lowered
        or "联网搜索" in text
        or "网上搜索" in text
        or "网页搜索" in text
        or "网络搜索" in text
        or "搜索网络" in text
        or "通用搜索" in text
        or "公开搜索" in text
    ):
        return None
    patterns = [
        r"(?:websearch|web search|联网搜索|网上搜索|网页搜索|网络搜索|搜索网络|通用搜索|公开搜索)\s*[:：]\s*(?P<query>.+)$",
        r"(?:websearch|web search)\s+(?P<query>.+)$",
        r"(?:帮我|请)?\s*(?:联网|网上|网页|网络|公开|web)\s*搜索\s*(?P<query>.+)$",
        r"(?:帮我|请)?\s*搜索网络\s*(?P<query>.+)$",
    ]
    query = ""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.S)
        if match:
            query = match.group("query").strip()
            break
    if not query:
        return {}
    domains = [match.group("domain").lower() for match in WEB_SEARCH_SITE_PATTERN.finditer(query)]
    clean_query = WEB_SEARCH_SITE_PATTERN.sub(" ", query)
    clean_query = re.sub(r"\s+", " ", clean_query).strip(" ：:\n\t")
    return {
        "query": clean_query or query[:600],
        "domains": domains[:8],
    }


def _looks_like_conditional_tool_boundary(text: str) -> bool:
    return bool(
        re.search(
            r"(?:如果|若|如需|需要时|下一步需要|下一步如果).{0,120}"
            r"(?:联网搜索|网上搜索|网页搜索|网络搜索|web\s*search|公开\s*web\s*search|解析\s*PDF|调用外部文献服务|外部文献服务|MCP)"
            r".{0,120}(?:先返回确认卡|返回确认卡|先.*确认|需要.*确认|授权)",
            text,
            re.IGNORECASE | re.S,
        )
    )


def _looks_like_live_public_web_question(text: str) -> bool:
    if not text.strip() or URL_PATTERN.search(text) or PDF_PATTERN.search(text):
        return False
    if _contains_any(
        text,
        [
            "当前运行",
            "运行状态",
            "当前 run",
            "当前假设",
            "当前项目",
            "项目现在",
            "这个项目",
            "this project",
            "current run",
            "selected hypothesis",
        ],
    ):
        return False
    has_temporal_signal = _contains_any(
        text,
        [
            "最新",
            "目前",
            "现在",
            "今天",
            "今日",
            "实时",
            "刚刚",
            "最近",
            "当前消息",
            "latest",
            "current",
            "today",
            "now",
            "recent",
            "real-time",
            "realtime",
        ],
    )
    if not has_temporal_signal:
        return False
    has_public_topic = _contains_any(
        text,
        [
            "世界杯",
            "比赛",
            "赛况",
            "比分",
            "冠军",
            "新闻",
            "天气",
            "股价",
            "股票",
            "价格",
            "汇率",
            "政策",
            "法规",
            "版本",
            "发布",
            "更新",
            "榜单",
            "排名",
            "公司",
            "ceo",
            "president",
            "election",
            "score",
            "match",
            "game",
            "news",
            "weather",
            "stock",
            "price",
            "release",
            "version",
        ],
    )
    asks_public_status = _contains_any(
        text,
        [
            "如何了",
            "怎么样",
            "什么情况",
            "进展",
            "结果",
            "多少",
            "谁赢",
            "谁领先",
            "what happened",
            "how is",
            "who won",
            "status",
        ],
    )
    return has_public_topic or asks_public_status


def _extract_live_public_web_question(text: str) -> Dict[str, Any]:
    query = re.sub(r"^(?:帮我|请|查一下|查询|检索一下|搜一下)\s*", "", text.strip(), flags=re.IGNORECASE)
    query = re.sub(r"\s+", " ", query).strip(" ：:\n\t")
    return {"query": query[:600] or text.strip()[:600], "domains": []}


def _safe_chat_error(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message")
        if isinstance(message, str) and message.strip():
            return message
        if code == "repeated_identical_tool_workflow":
            return "同一研究上下文里已经执行过相同 PDF 解析任务，系统已阻止重复写入。"
        if code == "repeated_identical_web_extract":
            return "同一研究上下文里已经执行过相同网页证据抓取，系统已阻止重复抓取。"
        if code == "repeated_identical_web_search":
            return "同一研究上下文里已经执行过相同公开搜索，系统已阻止重复检索。"
        if code == "repeated_identical_terminal_command":
            return "同一研究上下文里已经执行过相同本地命令，系统已阻止重复提交。"
        if code == "repeated_identical_ssh_training_job":
            return "同一研究上下文里已经执行过相同 SSH 命令，系统已阻止重复提交。"
        if code == "repeated_identical_mcp_tool_call":
            return "同一研究上下文里已经执行过相同 MCP 文献检查，系统已阻止重复调用。"
        if code == "mcp_tool_call_failed":
            return "外部文献 MCP 调用失败，请检查 MCP 服务状态或稍后重试。"
    if exc.status_code == 428:
        return "这个任务需要先在确认卡片中明确授权。"
    if exc.status_code == 404:
        return "没有找到对应资源，请检查输入后重试。"
    if exc.status_code == 424:
        return "所需工具当前不可用，请先检查运行准备状态。"
    return "任务暂时未能完成，请检查输入、服务状态或稍后重试。"


def _tool_capability_status(tool_name: str) -> Dict[str, Any]:
    try:
        spec = research_tool_registry().get(tool_name)
        if not spec:
            return {"available": False, "status": "unavailable", "summary": "能力未注册。"}
        availability = spec.describe().get("availability", {})
        available = bool(availability.get("available"))
        return {
            "available": available,
            "status": "ready" if available else "limited",
            "summary": availability.get("reason") or ("已可用" if available else "当前不可用"),
        }
    except Exception:
        return {"available": False, "status": "limited", "summary": "运行准备状态暂时不可读。"}


def _tool_registration_capability_status() -> Dict[str, Any]:
    return {
        "available": True,
        "status": "ready",
        "summary": "可注册项目工具 schema 草案；不会安装执行器或写入任意代码。",
    }


def _virtual_tool_register_spec() -> Dict[str, Any]:
    return {
        "name": "tool.register_draft",
        "toolset": "tool_management",
        "description": "Register a schema-only project tool draft after explicit user confirmation.",
        "phases": ["supervisor", "operator_diagnostics"],
        "risk_level": "write",
        "requires": ["explicit approval", "schema validation", "project audit log"],
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"},
                "user_title": {"type": "string"},
                "description": {"type": "string"},
                "toolset": {"type": "string"},
                "phases": {"type": "array", "items": {"type": "string"}},
                "risk_level": {"type": "string"},
                "input_schema": {"type": "object"},
                "execution_boundary": {"type": "string"},
            },
            "required": ["tool_name", "description"],
        },
        "availability": {
            "available": True,
            "mode": "schema_draft_only",
            "reason": "Registers tool metadata only; execution adapter remains unavailable until implemented and reviewed.",
            "checked_at": time.time(),
        },
    }


def _load_project_tool_drafts() -> List[Dict[str, Any]]:
    try:
        if not PROJECT_TOOL_DRAFTS_PATH.exists():
            return []
        with PROJECT_TOOL_DRAFTS_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        print(f"Project tool draft load failed: {exc}", file=sys.stderr)
        return []
    drafts = payload.get("drafts") if isinstance(payload, dict) else payload
    if not isinstance(drafts, list):
        return []
    return [item for item in drafts if isinstance(item, dict)]


def _save_project_tool_drafts(drafts: List[Dict[str, Any]]) -> None:
    PROJECT_TOOL_DRAFTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "updated_at": time.time(), "drafts": drafts}
    with PROJECT_TOOL_DRAFTS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)


def _slug_project_tool_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_.-]+", "_", value.strip().lower()).strip("._-")
    normalized = re.sub(r"_+", "_", normalized)
    if not normalized:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_project_tool_name", "message": "工具名必须包含可稳定保存的英文字母、数字、点、下划线或短横线。"},
        )
    if not normalized.startswith("project."):
        normalized = f"project.{normalized}"
    if len(normalized) > 120 or not re.match(r"^project\.[a-z0-9][a-z0-9_.-]{1,111}$", normalized):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_project_tool_name", "message": "工具名必须形如 project.my_tool，且只能包含 a-z、0-9、点、下划线或短横线。"},
        )
    return normalized


def _normalize_project_toolset(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "_", value.strip().lower()).strip("_-")
    return normalized[:80] if normalized else "project_custom"


def _normalize_project_tool_phases(phases: List[str]) -> List[str]:
    known = {item["phase"] for item in list_phase_tool_policies()}
    normalized: List[str] = []
    for phase in phases or ["evidence_audit"]:
        canonical = canonical_phase(str(phase or ""))
        if canonical not in known:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_project_tool_phase", "message": f"未知 phase：{phase}。"},
            )
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized[:8] or ["evidence_audit"]


def _normalize_project_tool_input_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    if not schema:
        normalized: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    elif not isinstance(schema, dict):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_project_tool_schema", "message": "input_schema 必须是 JSON object。"},
        )
    else:
        normalized = dict(schema)
    blocked_keys = {"implementation", "script", "code", "command", "handler", "entrypoint", "python", "shell"}
    if any(key in normalized for key in blocked_keys):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "project_tool_schema_contains_execution",
                "message": "工具草案只能注册 schema，不能包含 implementation/script/command/handler 等执行字段。",
            },
        )
    normalized["type"] = "object"
    properties = normalized.get("properties") or {}
    if not isinstance(properties, dict):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_project_tool_schema", "message": "input_schema.properties 必须是 object。"},
        )
    cleaned_properties: Dict[str, Any] = {}
    for key, value in properties.items():
        prop_key = str(key)
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_-]{0,80}$", prop_key):
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_project_tool_schema_property", "message": f"非法 schema 字段名：{prop_key}。"},
            )
        cleaned_properties[prop_key] = value if isinstance(value, dict) else {"type": "string", "description": str(value)[:300]}
    required = normalized.get("required") or []
    if not isinstance(required, list):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_project_tool_schema", "message": "input_schema.required 必须是数组。"},
        )
    cleaned_required = [str(item) for item in required if str(item) in cleaned_properties]
    normalized["properties"] = cleaned_properties
    normalized["required"] = cleaned_required
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) > 12_000:
        raise HTTPException(
            status_code=422,
            detail={"code": "project_tool_schema_too_large", "message": "工具 schema 过大，请精简字段和描述。"},
        )
    return normalized


def _project_tool_draft_to_registry_tool(draft: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": draft.get("name"),
        "toolset": draft.get("toolset") or "project_custom",
        "description": draft.get("description") or "",
        "phases": list(draft.get("phases") or []),
        "risk_level": draft.get("risk_level") or "read",
        "requires": ["registered project tool draft", "execution adapter review"],
        "input_schema": draft.get("input_schema") or {"type": "object", "properties": {}, "required": []},
        "availability": {
            "available": False,
            "mode": "registered_draft",
            "reason": "This project tool is registered as schema only. Execution requires a reviewed adapter.",
            "checked_at": draft.get("registered_at") or time.time(),
        },
        "metadata": {
            "user_title": draft.get("user_title"),
            "execution_boundary": draft.get("execution_boundary"),
            "registered_at": draft.get("registered_at"),
            "result_ref": draft.get("result_ref"),
        },
    }


def _project_tool_registry_tools(*, phase: Optional[str] = None, toolset: Optional[str] = None) -> List[Dict[str, Any]]:
    normalized_phase = canonical_phase(phase) if phase else None
    normalized_toolset = toolset.strip().lower() if toolset else None
    tools: List[Dict[str, Any]] = []
    for draft in _load_project_tool_drafts():
        tool = _project_tool_draft_to_registry_tool(draft)
        phases = {canonical_phase(item) for item in tool.get("phases") or []}
        if normalized_phase and normalized_phase not in phases:
            continue
        if normalized_toolset and normalized_toolset != str(tool.get("toolset") or "").lower():
            continue
        tools.append(tool)
    return tools


def _virtual_tool_matches_filters(tool: Dict[str, Any], *, phase: Optional[str], toolset: Optional[str]) -> bool:
    if phase and canonical_phase(phase) not in {canonical_phase(item) for item in tool.get("phases") or []}:
        return False
    if toolset and toolset.strip().lower() != str(tool.get("toolset") or "").lower():
        return False
    return True


def _chat_capabilities() -> List[Dict[str, Any]]:
    pdf_status = _tool_capability_status("pdf.parse_to_knowledge_base")
    web_status = _tool_capability_status("browser.web_extract")
    web_search_status = _tool_capability_status("web.search_public")
    mcp_status = _tool_capability_status("mcp.literature_review")
    terminal_status = _tool_capability_status("terminal.command")
    ssh_status = _tool_capability_status("ssh.training_command")
    file_status = _tool_capability_status("file.source_snapshot")
    tool_register_status = _tool_registration_capability_status()
    return [
        {
            "id": "project.answer_with_rag",
            "userTitle": "项目 AI 问答",
            "userSummary": "基于当前页面、最近对话、SQL 知识库、run/audit 上下文回答普通研究问题；不会直接执行外部动作。",
            "intent": "ask_project_ai",
            "taskArea": "project_help",
            "executionMode": "read_only",
            "requiredInputs": [],
            "expectedOutputs": ["grounded answer", "evidence boundary", "safe next steps"],
            "groundingBoundary": "knowledge_base",
            "availability": {"available": True, "status": "ready", "summary": "普通问答默认走 SQL RAG + LLM。"},
        },
        {
            "id": "project.discover_capabilities",
            "userTitle": "询问这个项目能做什么",
            "userSummary": "用任务语言解释工作台能力、页面职责、demo/live/literature-grounded 边界和下一步。",
            "intent": "discover_capabilities",
            "taskArea": "project_help",
            "executionMode": "read_only",
            "requiredInputs": [],
            "expectedOutputs": ["capability map", "safe next steps", "mode boundaries"],
            "groundingBoundary": "project_capability_registry",
            "availability": {"available": True, "status": "ready", "summary": "项目能力表已可查询。"},
        },
        {
            "id": "research.start_run",
            "userTitle": "通过对话启动研究流程",
            "userSummary": "根据明确 research goal 生成候选假设，并保留 planning、review、ranking、evolution 和 trace。",
            "intent": "start_research_run",
            "taskArea": "research_run",
            "executionMode": "approval_required",
            "approvalScope": "research.start_live_run",
            "requiredInputs": [{"key": "research_goal", "label": "研究目标", "type": "text", "required": True}],
            "expectedOutputs": ["run", "hypotheses", "reviews", "tournament ranking", "timeline"],
            "groundingBoundary": "live_model_workflow",
            "availability": {"available": True, "status": "ready", "summary": "启动前仍会检查模型 key、MCP 和 safety gate。"},
        },
        {
            "id": "research.explain_run",
            "userTitle": "解释当前运行",
            "userSummary": "总结当前 run 的状态、阶段、假设数量、证据边界和下一步。",
            "intent": "explain_current_run",
            "taskArea": "research_run",
            "executionMode": "read_only",
            "requiredInputs": [{"key": "run_id", "label": "当前运行", "type": "run_ref", "required": False}],
            "expectedOutputs": ["run summary", "phase state", "next actions"],
            "groundingBoundary": "run_audit",
            "availability": {"available": True, "status": "ready", "summary": "可读取当前或最近一次 run。"},
        },
        {
            "id": "project.summarize_artifacts",
            "userTitle": "汇总项目论文、假设、实验和报告",
            "userSummary": "读取当前 run audit、本地证据链接和工具检索摘要，汇总这个项目已有的论文/网页证据、候选假设、实验计划和报告草稿边界。",
            "intent": "summarize_project_artifacts",
            "taskArea": "project_help",
            "executionMode": "read_only",
            "requiredInputs": [{"key": "run_id", "label": "当前运行", "type": "run_ref", "required": False}],
            "expectedOutputs": ["artifact inventory", "hypotheses", "evidence sources", "experiment plans", "report outline"],
            "groundingBoundary": "run_audit",
            "availability": {"available": True, "status": "ready", "summary": "只读取当前 run 和本地知识库索引，不执行外部工具。"},
        },
        {
            "id": "research.continue_run",
            "userTitle": "基于当前结果继续研究",
            "userSummary": "把当前 run、历史假设、用户反馈和证据摘要作为下一轮 continuation/refinement 的上下文。",
            "intent": "continue_or_revise_run",
            "taskArea": "research_run",
            "executionMode": "approval_required",
            "approvalScope": "research.start_live_run",
            "requiredInputs": [
                {"key": "run_id", "label": "当前运行", "type": "run_ref", "required": True},
                {"key": "research_goal", "label": "继续后的研究目标", "type": "text", "required": False},
            ],
            "expectedOutputs": ["continuation run", "memory summary", "queued work item", "refined hypotheses"],
            "groundingBoundary": "run_audit",
            "availability": {
                "available": True,
                "status": "ready",
                "summary": "继续运行会创建新的 queued run；历史上下文以摘要形式注入，不会即时改写当前结果。",
            },
        },
        {
            "id": "hypothesis.inspect",
            "userTitle": "检查某条假设",
            "userSummary": "解释候选假设、评分、review、证据边界、实验计划和后续动作。",
            "intent": "inspect_hypothesis",
            "taskArea": "hypothesis_audit",
            "executionMode": "read_only",
            "requiredInputs": [{"key": "hypothesis_index", "label": "假设序号", "type": "text", "required": False}],
            "expectedOutputs": ["hypothesis summary", "review summary", "evidence boundary", "experiment next step"],
            "groundingBoundary": "run_audit",
            "availability": {"available": True, "status": "ready", "summary": "依赖当前 run 的 hypotheses/reviews/evidence。"},
        },
        {
            "id": "hypothesis.feedback",
            "userTitle": "记录专家反馈",
            "userSummary": "把研究者对候选假设的接受、偏好、批评或修订意见保存为下一轮 continuation/refinement 的反馈记忆。",
            "intent": "apply_expert_feedback",
            "taskArea": "hypothesis_audit",
            "executionMode": "read_only",
            "requiredInputs": [
                {"key": "run_id", "label": "当前运行", "type": "run_ref", "required": True},
                {"key": "feedback_text", "label": "反馈内容", "type": "text", "required": True},
            ],
            "expectedOutputs": ["feedback memory item", "target hypothesis ref", "next-run refinement context"],
            "groundingBoundary": "run_audit",
            "availability": {"available": True, "status": "ready", "summary": "反馈会进入下一轮 run 或 continuation，不会即时改写当前结果。"},
        },
        {
            "id": "ranking.explain_elo",
            "userTitle": "解释 Elo 锦标赛排名",
            "userSummary": "从真实 tournament_matchups 解释 winner/loser、confidence、before/after Elo 和排序依据。",
            "intent": "explain_ranking",
            "taskArea": "ranking_audit",
            "executionMode": "read_only",
            "requiredInputs": [{"key": "run_id", "label": "当前运行", "type": "run_ref", "required": False}],
            "expectedOutputs": ["ranking explanation", "matchups", "Elo before/after", "confidence"],
            "groundingBoundary": "tournament_audit",
            "availability": {"available": True, "status": "ready", "summary": "依赖 run 的 tournament_matchups。"},
        },
        {
            "id": "evidence.parse_pdf",
            "userTitle": "解析 PDF 并写入知识库",
            "userSummary": "把服务器可访问的 PDF 转成全文、metadata、语义片段和证据记录。",
            "intent": "parse_pdf_to_knowledge_base",
            "taskArea": "evidence",
            "executionMode": "approval_required",
            "approvalScope": "pdf.parse_to_knowledge_base",
            "requiredInputs": [{"key": "pdf_path", "label": "PDF 文件路径或 PDF URL", "type": "pdf_path", "required": True}],
            "expectedOutputs": ["parse run", "knowledge paper", "evidence chunks", "solve artifacts"],
            "groundingBoundary": "parsed_fulltext",
            "availability": pdf_status,
        },
        {
            "id": "evidence.extract_web_page",
            "userTitle": "抓取网页证据",
            "userSummary": "保存公开 HTTP(S) 网页文本、PDF 链接和 supplementary 链接。",
            "intent": "extract_web_evidence",
            "taskArea": "evidence",
            "executionMode": "approval_required",
            "approvalScope": "browser.web_extract",
            "requiredInputs": [{"key": "url", "label": "公开网页 URL", "type": "url", "required": True}],
            "expectedOutputs": ["web evidence snapshot", "knowledge paper", "tool result"],
            "groundingBoundary": "public_html_best_effort",
            "availability": web_status,
        },
        {
            "id": "evidence.web_search_public",
            "userTitle": "通用 Web Search",
            "userSummary": "对公开 Web 做 best-effort 搜索，返回 URL、snippet、retrieval metadata 和 result ref。",
            "intent": "search_public_web",
            "taskArea": "evidence",
            "executionMode": "approval_required",
            "approvalScope": "web.search_public",
            "requiredInputs": [{"key": "query", "label": "搜索 query", "type": "text", "required": True}],
            "expectedOutputs": ["search results", "source URLs", "snippets", "tool result provenance"],
            "groundingBoundary": "public_web_search",
            "availability": web_search_status,
        },
        {
            "id": "evidence.search_knowledge",
            "userTitle": "搜索知识库证据",
            "userSummary": "在已解析全文和入库网页中查找支持片段。",
            "intent": "search_knowledge_evidence",
            "taskArea": "knowledge_search",
            "executionMode": "read_only",
            "requiredInputs": [{"key": "query", "label": "要检索的机制、术语或假设", "type": "text", "required": True}],
            "expectedOutputs": ["evidence summaries", "support levels", "source reliability"],
            "groundingBoundary": "knowledge_base",
            "availability": {"available": True, "status": "ready", "summary": "读取本地知识库，不调用外部服务。"},
        },
        {
            "id": "evidence.check_hypothesis_grounding",
            "userTitle": "本地核验假设证据",
            "userSummary": "调用证据核验智能体，基于本地知识库和 run evidence 判断 supported、limited、contradicted 或 ungrounded。",
            "intent": "check_hypothesis_grounding",
            "taskArea": "hypothesis_audit",
            "executionMode": "read_only",
            "requiredInputs": [{"key": "hypothesis_text", "label": "假设文本", "type": "hypothesis_text", "required": True}],
            "expectedOutputs": ["verification report", "claim checks", "evidence gaps", "falsification tests"],
            "groundingBoundary": "run_audit",
            "availability": {"available": True, "status": "ready", "summary": "读取本地 run 和知识库证据。"},
        },
        {
            "id": "evidence.verify_with_literature",
            "userTitle": "外部文献反证检查",
            "userSummary": "在本地核验后，经授权调用文献 MCP 搜索潜在反证、负面结果和 failed replication。",
            "intent": "verify_evidence_with_literature",
            "taskArea": "hypothesis_audit",
            "executionMode": "approval_required",
            "approvalScope": "mcp.literature_review",
            "requiredInputs": [{"key": "hypothesis_text", "label": "假设文本", "type": "hypothesis_text", "required": True}],
            "expectedOutputs": ["external literature check", "counter-evidence candidates", "verification report", "tool result provenance"],
            "groundingBoundary": "literature_mcp_audit",
            "availability": mcp_status,
        },
        {
            "id": "experiment.design",
            "userTitle": "生成实验设计下一步",
            "userSummary": "把候选假设整理为可证伪实验、失败条件、所需数据和评估指标。",
            "intent": "design_experiment",
            "taskArea": "experiment",
            "executionMode": "read_only",
            "requiredInputs": [{"key": "hypothesis_index", "label": "假设序号或假设文本", "type": "hypothesis_text", "required": False}],
            "expectedOutputs": ["experiment plan", "failure criteria", "metrics"],
            "groundingBoundary": "run_audit",
            "availability": {"available": True, "status": "ready", "summary": "V1 基于当前 run 内容生成任务化建议，不执行实验。"},
        },
        {
            "id": "report.draft",
            "userTitle": "生成报告草稿结构",
            "userSummary": "按当前 run 结果生成摘要、假设对比、证据边界和后续实验段落。",
            "intent": "draft_report",
            "taskArea": "report",
            "executionMode": "read_only",
            "requiredInputs": [{"key": "run_id", "label": "当前运行", "type": "run_ref", "required": False}],
            "expectedOutputs": ["report outline", "evidence caveats", "next steps"],
            "groundingBoundary": "run_audit",
            "availability": {"available": True, "status": "ready", "summary": "V1 生成结构化草稿，不宣称科学发现。"},
        },
        {
            "id": "history.session_search",
            "userTitle": "搜索历史研究过程",
            "userSummary": "跨 run、hypothesis、tool result、task 和 background job 搜索历史记录摘要。",
            "intent": "search_session_history",
            "taskArea": "history",
            "executionMode": "read_only",
            "requiredInputs": [{"key": "query", "label": "搜索关键词", "type": "text", "required": True}],
            "expectedOutputs": ["session search hits", "target refs"],
            "groundingBoundary": "session_search",
            "availability": {"available": True, "status": "ready", "summary": "只返回摘要和跳转引用，不铺开大型结果。"},
        },
        {
            "id": "file.source_snapshot",
            "userTitle": "读取本地文件快照",
            "userSummary": "经用户确认后读取配置证据根目录内的本地源码/文本文件片段，生成分页、hash 和审计记录。",
            "intent": "snapshot_local_file",
            "taskArea": "evidence",
            "executionMode": "approval_required",
            "approvalScope": "file.source_snapshot",
            "requiredInputs": [{"key": "source_path", "label": "本地文件路径", "type": "file", "required": True}],
            "expectedOutputs": ["source file snapshot", "line range", "content hash", "tool result provenance"],
            "groundingBoundary": "local_file_snapshot",
            "availability": file_status,
        },
        {
            "id": "tool.register_draft",
            "userTitle": "注册项目工具草案",
            "userSummary": "经用户确认后保存一个 schema-only 项目工具草案；不会安装执行器、不会写入任意工具代码。",
            "intent": "register_project_tool",
            "taskArea": "tool_management",
            "executionMode": "approval_required",
            "approvalScope": "tool.register_draft",
            "requiredInputs": [
                {"key": "tool_name", "label": "工具 ID", "type": "text", "required": True},
                {"key": "description", "label": "工具用途", "type": "text", "required": True},
            ],
            "expectedOutputs": ["project tool draft", "validated input schema", "audit result", "registry visibility"],
            "groundingBoundary": "tool_registry_draft",
            "availability": tool_register_status,
        },
        {
            "id": "runtime.terminal_command",
            "userTitle": "执行本地终端命令",
            "userSummary": "通过 permission-gated terminal workflow 执行本机 PowerShell/bash 命令，并保存 stdout/stderr artifact。",
            "intent": "run_terminal_command",
            "taskArea": "runtime_tools",
            "executionMode": "approval_required",
            "approvalScope": "terminal.command",
            "requiredInputs": [{"key": "command", "label": "命令", "type": "command", "required": True}],
            "expectedOutputs": ["background job", "stdout/stderr artifacts", "tool result provenance", "guardrail summary"],
            "groundingBoundary": "local_terminal_audit",
            "availability": terminal_status,
        },
        {
            "id": "runtime.ssh_training_command",
            "userTitle": "连接 SSH 服务器执行命令",
            "userSummary": "在已配置训练主机上执行远程命令；任意 SSH alias 可通过本地 terminal.command 的 ssh 命令执行。",
            "intent": "run_ssh_training_command",
            "taskArea": "runtime_tools",
            "executionMode": "approval_required",
            "approvalScope": "ssh.training_command",
            "requiredInputs": [
                {"key": "server_id", "label": "服务器", "type": "text", "required": True},
                {"key": "command", "label": "远程命令", "type": "command", "required": True},
            ],
            "expectedOutputs": ["background job", "remote stdout/stderr artifacts", "tool result provenance", "guardrail summary"],
            "groundingBoundary": "remote_ssh_audit",
            "availability": ssh_status,
        },
    ]


def _ensure_project_chat_knowledge_index() -> None:
    try:
        for document in knowledge_base.list_documents():
            metadata = document.metadata if isinstance(document.metadata, dict) else {}
            if (
                metadata.get("knowledge_kind") == "project_chat_system"
                and metadata.get("version") == PROJECT_CHAT_KNOWLEDGE_VERSION
            ):
                return
        capability_lines = [
            f"- {item['userTitle']}: {item['userSummary']} intent={item['intent']} mode={item['executionMode']} boundary={item['groundingBoundary']}"
            for item in _chat_capabilities()
        ]
        content = "\n\n".join(
            [
                "# Open Co-Scientist Workbench Project Knowledge",
                "## Project AI answer pipeline",
                "普通项目问答应先检索本地 SQLite knowledge_base / FTS5 证据片段，再把命中的片段、当前 run context、能力入口和用户问题拼接成 prompt，交给 live model 回答。不要用静态模板伪装成 AI 问答。",
                "执行类动作仍然必须走确认卡，包括启动 live research workflow、解析 PDF、抓取网页证据、外部 Web Search、MCP 文献检查、本地 terminal 命令和 SSH 命令。",
                "## Keyboard interaction",
                "研究聊天输入框使用 Enter 换行，Ctrl+Enter 或 Cmd+Enter 发送。这个约定适用于项目 AI、研究工作台命令中心和侧边聊天。",
                "## Evidence boundary",
                "回答必须区分 project system knowledge、parsed fulltext、knowledge base snippets、run audit、tournament audit 和 model_without_local_evidence。Demo simulation 只能验证 UI/schema/流程，不能当作真实科学证据。",
                "证据核验报告中的当前证据来自三类来源：SQL RAG/parsed fulltext 检索片段、当前 run 的 hypothesis_evidence_links、以及用户确认后写入 provenance 的外部 MCP 文献候选。possible counter-evidence 是从这些片段中检测到 negative/failed/contradictory 等负面标记，必须提示人工复核。",
                "## Elo and tournament ranking",
                "Elo 是一种基于成对比较结果更新相对评分的排序方法。在本工作台里，候选假设会通过 pairwise / tournament 比较产生 winner、loser、confidence、before/after Elo 和 delta。Elo 不是绝对真理分数，只是当前评审条件和证据边界下的相对优先级信号。",
                "如果某条假设在 ranking 中是 winner，但后续 evidence audit 发现潜在反证，必须明确说明：winner 表示 tournament 阶段的相对优先级，不表示该假设已被证据支撑；后续应优先审计反证来源、更新证据边界，必要时重新 ranking。",
                "## User-facing task map",
                "\n".join(capability_lines),
            ]
        )
        knowledge_base.ingest(
            title="Open Co-Scientist Workbench Project Knowledge",
            content=content,
            authors=["open-coscientist"],
            source="project_system",
            source_reliability="project_runtime_contract",
            metadata={"knowledge_kind": "project_chat_system", "version": PROJECT_CHAT_KNOWLEDGE_VERSION},
            library_id=DEFAULT_LIBRARY_ID,
        )
    except Exception as exc:
        print(f"Failed to index project chat knowledge: {exc}", file=sys.stderr)


def _contains_any(text: str, terms: List[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _looks_like_start_research_run_request(text: str) -> bool:
    if not _extract_research_goal(text):
        return False
    return _contains_any(
        text,
        [
            "生成",
            "候选假设",
            "评审",
            "排序",
            "一起",
            "纳入",
            "启动",
            "开始",
            "start",
            "run",
            "rank",
            "review",
            "workflow",
        ],
    )


def _looks_like_current_project_inventory_question(text: str) -> bool:
    if not _contains_any(text, ["当前这个项目", "当前项目", "这个项目", "指定项目", "项目里", "project"]):
        return False
    return _contains_any(
        text,
        [
            "能做什么",
            "可以实现什么",
            "有什么",
            "有哪些",
            "产出",
            "论文",
            "假设",
            "实验",
            "报告",
            "artifact",
            "inventory",
            "papers",
            "hypotheses",
            "experiments",
            "reports",
        ],
    )


def _looks_like_concept_question(text: str) -> bool:
    return _contains_any(
        text,
        [
            "什么是",
            "是什么",
            "什么意思",
            "怎么理解",
            "解释一下",
            "介绍一下",
            "概念",
            "define",
            "what is",
            "what does",
            "explain",
        ],
    )


def _extract_hypothesis_index(text: str) -> Optional[int]:
    digit_match = re.search(r"(?:第\s*)?(\d+)\s*(?:个|条)?\s*(?:假设|候选|hypothesis)", text, re.IGNORECASE)
    if digit_match:
        return max(0, int(digit_match.group(1)) - 1)
    chinese_digits = {
        "一": 0,
        "二": 1,
        "三": 2,
        "四": 3,
        "五": 4,
        "六": 5,
        "七": 6,
        "八": 7,
    }
    chinese_match = re.search(r"第\s*([一二三四五六七八])\s*(?:个|条)?\s*(?:假设|候选)", text)
    if chinese_match:
        return chinese_digits.get(chinese_match.group(1))
    return None


def _extract_research_goal(text: str) -> Optional[str]:
    patterns = [
        r"(?:研究目标|research goal|goal)\s*[:：]\s*(?P<goal>.+)$",
        r"(?:开始|启动|运行|生成|run)\s*(?:一次|一个|候选假设|研究流程|workflow)?\s*[:：]?\s*(?P<goal>.+)$",
        r"(?:我想|帮我|请)\s*(?:研究|生成候选假设|设计假设)\s*(?P<goal>.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.S)
        if match:
            goal = match.group("goal").strip(" ：:\n\t")
            goal = re.split(
                r"[；;。\n]+(?:我的假设|初始假设|偏好|约束|限制|请|一起|starting hypothes|preferences?|constraints?)",
                goal,
                maxsplit=1,
                flags=re.I,
            )[0].strip(" ：:\n\t")
            if len(goal) >= 8:
                return goal[:1200]
    if len(text.strip()) >= 18 and _contains_any(text, ["研究", "hypothesis", "假设", "机制", "experiment", "实验"]):
        return text.strip()[:1200]
    return None


def _split_user_clauses(text: str) -> list[str]:
    return [part.strip(" \n\t；;。.") for part in re.split(r"[；;。\n]+", text) if part.strip(" \n\t；;。.")]


def _extract_starting_hypotheses(text: str) -> list[str]:
    hypotheses: list[str] = []
    for clause in _split_user_clauses(text):
        if "研究目标" in clause or "research goal" in clause.lower():
            continue
        if not _contains_any(clause, ["我的假设", "初始假设", "starting hypothesis", "starting hypotheses", "hypothesis is"]):
            continue
        cleaned = re.sub(
            r"^(?:我的)?(?:初始)?假设(?:是|为)?\s*[:：]?\s*",
            "",
            clause,
            flags=re.I,
        ).strip(" ：:")
        cleaned = re.sub(r"^starting hypothes(?:is|es)\s*(?:is|are)?\s*[:：]?\s*", "", cleaned, flags=re.I)
        if len(cleaned) >= 8:
            hypotheses.append(cleaned[:1200])
    return hypotheses[:20]


def _extract_labeled_list(text: str, labels: tuple[str, ...], *, max_items: int = 20) -> list[str]:
    results: list[str] = []
    label_pattern = "|".join(re.escape(label) for label in sorted(labels, key=len, reverse=True))
    for clause in _split_user_clauses(text):
        lowered = clause.lower()
        matched_label = next((label for label in labels if label.lower() in lowered), None)
        if not matched_label:
            continue
        cleaned = re.sub(
            rf"^(?:{label_pattern})\s*[:：]?\s*",
            "",
            clause,
            flags=re.I,
        ).strip(" ：:")
        if len(cleaned) >= 2:
            results.append(cleaned[:800])
    return results[:max_items]


def _looks_like_hypothesis_verification_request(text: str) -> bool:
    lowered = text.lower()
    if len(text.strip()) < 12:
        return False
    if _contains_any(text, ["研究目标", "research goal"]) and _contains_any(
        text,
        ["生成", "候选假设", "评审", "排序", "一起", "纳入", "启动", "开始", "start", "run", "rank", "review"],
    ):
        return False
    has_hypothesis = _contains_any(
        text,
        [
            "假设",
            "命题",
            "结论",
            "claim",
            "hypothesis",
            "proposal",
        ],
    )
    asks_verification = _contains_any(
        text,
        [
            "是否正确",
            "是否成立",
            "是否可靠",
            "是否为真",
            "正不正确",
            "成不成立",
            "对不对",
            "检验这个假设",
            "检验该假设",
            "验证这个假设",
            "验证该假设",
            "核验这个假设",
            "核验该假设",
            "检验",
            "验证",
            "核验",
            "反证",
            "correct",
            "true",
            "valid",
            "verify",
            "validate",
            "falsify",
            "contradict",
        ],
    )
    explicit_external_source = any(source in lowered for source in ("arxiv", "pubmed", "scholar", "google scholar", "mcp"))
    return has_hypothesis and (asks_verification or explicit_external_source)


def _looks_like_hypothesis_inspection_request(text: str) -> bool:
    if len(text.strip()) < 4:
        return False
    if _contains_any(text, ["研究目标", "research goal"]) and _contains_any(text, ["生成", "启动", "开始", "run", "workflow"]):
        return False
    if _contains_any(text, ["生成候选", "生成假设", "启动", "开始运行", "run workflow"]):
        return False
    has_hypothesis_ref = _contains_any(
        text,
        [
            "候选假设",
            "这些假设",
            "这几个假设",
            "这3个假设",
            "这三个假设",
            "这 3 个假设",
            "这三条假设",
            "这几条假设",
            "hypotheses",
            "candidate hypotheses",
        ],
    )
    asks_to_read = _contains_any(
        text,
        [
            "解释",
            "说明",
            "是什么",
            "有哪些",
            "列出",
            "总结",
            "概括",
            "查看",
            "检查",
            "讲讲",
            "read",
            "explain",
            "summarize",
            "list",
        ],
    )
    return bool(_extract_hypothesis_index(text) is not None or (has_hypothesis_ref and asks_to_read))


def _extract_feedback_type(text: str) -> Literal["accept", "reject", "edit", "prefer", "critique", "constraint"]:
    if _contains_any(text, ["更偏好", "偏好", "优先", "prefer", "prioritize"]):
        return "prefer"
    if _contains_any(text, ["接受", "同意", "支持", "保留", "accept", "agree", "support", "keep"]):
        return "accept"
    if _contains_any(text, ["拒绝", "不要", "不接受", "错误", "不成立", "reject", "discard", "wrong", "invalid"]):
        return "reject"
    if _contains_any(text, ["修改", "改成", "重写", "修订", "edit", "rewrite", "revise"]):
        return "edit"
    if _contains_any(text, ["约束", "限制", "必须", "不能", "constraint", "must", "should not"]):
        return "constraint"
    return "critique"


def _looks_like_hypothesis_feedback_request(text: str) -> bool:
    has_hypothesis_ref = _extract_hypothesis_index(text) is not None or _contains_any(
        text,
        [
            "这个假设",
            "这条假设",
            "当前假设",
            "选中假设",
            "selected hypothesis",
            "this hypothesis",
        ],
    )
    if not has_hypothesis_ref:
        return False
    return _contains_any(
        text,
        [
            "太弱",
            "不够",
            "不成立",
            "错误",
            "问题",
            "风险",
            "反馈",
            "偏好",
            "更偏好",
            "接受",
            "拒绝",
            "修改",
            "修订",
            "critique",
            "feedback",
            "prefer",
            "accept",
            "reject",
            "revise",
            "weak",
            "risky",
        ],
    )


def _asks_for_all_hypotheses(text: str) -> bool:
    return _contains_any(
        text,
        [
            "这3个",
            "这 3 个",
            "这三个",
            "这几",
            "这些",
            "全部",
            "所有",
            "候选假设是什么",
            "有哪些假设",
            "列出",
            "list",
            "all hypotheses",
        ],
    )


def _looks_like_hypothesis_planning_advice_request(text: str) -> bool:
    if _contains_any(
        text,
        [
            "补充哪些证据",
            "哪些证据",
            "证据还缺",
            "缺哪些约束",
            "约束还缺",
            "下一步应启动",
            "下一步应该启动",
            "应启动哪种 workflow",
            "应该启动哪种 workflow",
            "基于当前项目和最近对话",
            "基于当前对话上下文",
        ],
    ):
        return True
    return _contains_any(text, ["生成候选假设", "候选假设"]) and _contains_any(
        text,
        ["告诉我", "建议", "应该", "从哪里开始", "哪里开始", "补充", "还缺", "缺哪些", "下一步"],
    )


def _route_research_chat_intent(message: str) -> Dict[str, Any]:
    """Fail-closed legacy shim.

    Natural-language routing is handled by the async LLM planner. This
    synchronous helper is kept only for older imports and must not select
    side-effecting tools from keywords.
    """
    text = message.strip()
    return {
        "intent": "ask_project_ai",
        "confidence": 0.0,
        "extractedInputs": {"query": text},
        "missingInputs": [],
        "userFacingReason": "Legacy deterministic router is disabled; natural-language routing requires the model planner.",
        "plannerStatus": "legacy_disabled",
        "plannerConfidence": 0.0,
        "routingSource": "fallback_error",
    }
    text = message.strip()
    lowered = text.lower()
    pdf_match = PDF_PATTERN.search(text)
    url_match = URL_PATTERN.search(text)
    pdf_value = pdf_match.group("value") if pdf_match else None
    url_value = url_match.group("value") if url_match else None
    hypothesis_index = _extract_hypothesis_index(text)

    if _contains_any(text, ["能做什么", "有哪些功能", "有什么功能", "怎么用", "帮助", "功能列表", "what can you do", "capabilities"]):
        return {
            "intent": "discover_capabilities",
            "confidence": 0.95,
            "extractedInputs": {"query": text},
            "missingInputs": [],
            "userFacingReason": "用户询问项目能力和可执行任务。",
        }
    managed_ssh = _extract_managed_ssh_request(text)
    if managed_ssh is not None:
        missing_inputs = []
        if not managed_ssh.get("server_id"):
            missing_inputs.append("server_id")
        if not managed_ssh.get("command"):
            missing_inputs.append("command")
        return {
            "intent": "run_ssh_training_command",
            "confidence": 0.9 if not missing_inputs else 0.68,
            "extractedInputs": managed_ssh,
            "missingInputs": missing_inputs,
            "userFacingReason": "用户请求连接已配置 SSH 训练主机并执行远程命令。",
        }
    arbitrary_ssh = _extract_arbitrary_ssh_terminal_request(text)
    if arbitrary_ssh is not None:
        return {
            "intent": "run_terminal_command",
            "confidence": 0.86 if arbitrary_ssh.get("command") else 0.65,
            "extractedInputs": arbitrary_ssh,
            "missingInputs": [] if arbitrary_ssh.get("command") else ["command"],
            "userFacingReason": "用户请求通过本机 ssh 客户端连接任意 SSH alias/host 执行命令。",
        }
    terminal_command = _extract_terminal_command_request(text)
    if terminal_command is not None:
        return {
            "intent": "run_terminal_command",
            "confidence": 0.86,
            "extractedInputs": terminal_command,
            "missingInputs": [] if terminal_command.get("command") else ["command"],
            "userFacingReason": "用户请求执行本地 terminal/bash/PowerShell 命令。",
        }
    if _looks_like_hypothesis_planning_advice_request(text):
        return {
            "intent": "ask_project_ai",
            "confidence": 0.88,
            "extractedInputs": {"query": text},
            "missingInputs": [],
            "userFacingReason": "用户请求基于当前项目上下文给出候选假设生成前的证据、约束和 workflow 建议，应走只读 RAG 回答。",
        }
    web_search = _extract_web_search_request(text)
    if web_search is not None:
        return {
            "intent": "search_public_web",
            "confidence": 0.84 if web_search.get("query") else 0.66,
            "extractedInputs": web_search,
            "missingInputs": [] if web_search.get("query") else ["query"],
            "userFacingReason": "用户请求通用公开 Web Search。",
        }
    if _looks_like_live_public_web_question(text):
        return {
            "intent": "search_public_web",
            "confidence": 0.74,
            "extractedInputs": _extract_live_public_web_question(text),
            "missingInputs": [],
            "userFacingReason": "用户询问实时公网事实或状态，应先请求授权后执行通用 Web Search。",
        }
    if _contains_any(text, ["elo", "锦标赛", "tournament"]) and _looks_like_concept_question(text):
        return {
            "intent": "ask_project_ai",
            "confidence": 0.86,
            "extractedInputs": {"query": text},
            "missingInputs": [],
            "userFacingReason": "用户在询问项目概念，应检索 SQL 知识库后交给 live model 回答。",
        }
    if _contains_any(text, ["锦标赛", "tournament", "winner", "loser", "排名", "为什么排", "排序依据", "审计 Elo", "Elo 排名", "elo ranking"]):
        return {
            "intent": "explain_ranking",
            "confidence": 0.92,
            "extractedInputs": {"hypothesis_index": hypothesis_index} if hypothesis_index is not None else {},
            "missingInputs": [],
            "userFacingReason": "用户请求解释 tournament ranking / Elo 细节。",
        }
    if _contains_any(text, ["当前运行", "运行状态", "进度", "timeline", "trace", "总结当前", "解释当前", "run status"]):
        return {
            "intent": "explain_current_run",
            "confidence": 0.86,
            "extractedInputs": {},
            "missingInputs": [],
            "userFacingReason": "用户请求解释当前研究运行状态。",
        }
    if _looks_like_hypothesis_feedback_request(text):
        feedback_type = _extract_feedback_type(text)
        return {
            "intent": "apply_expert_feedback" if feedback_type in {"accept", "prefer", "constraint"} else "critique_generated_hypothesis",
            "confidence": 0.84,
            "extractedInputs": {
                "hypothesis_index": hypothesis_index,
                "feedback_type": feedback_type,
                "feedback_text": text,
            },
            "missingInputs": [],
            "userFacingReason": "用户正在对候选假设提供专家反馈，反馈应进入下一轮 continuation/refinement。",
        }
    if _looks_like_hypothesis_inspection_request(text):
        extracted: Dict[str, Any] = {}
        if hypothesis_index is not None:
            extracted["hypothesis_index"] = hypothesis_index
        if _asks_for_all_hypotheses(text):
            extracted["list_all"] = True
        return {
            "intent": "inspect_hypothesis",
            "confidence": 0.86,
            "extractedInputs": extracted,
            "missingInputs": [],
            "userFacingReason": "用户请求解释当前 run 中的候选假设，而不是启动新的研究流程。",
        }
    if _looks_like_hypothesis_verification_request(text):
        return {
            "intent": "verify_evidence_with_literature",
            "confidence": 0.88,
            "extractedInputs": {"hypothesis_text": text},
            "missingInputs": [],
            "userFacingReason": "用户请求检验假设是否成立，应先查本地知识库，再经确认检索 PubMed、arXiv 和 Google Scholar 等公开文献源。",
        }
    research_goal = _extract_research_goal(text)
    if research_goal and _contains_any(text, ["研究目标", "我想研究", "开始", "启动", "运行", "生成", "候选假设", "research goal", "run", "workflow"]):
        starting_hypotheses = _extract_starting_hypotheses(text)
        constraints = _extract_labeled_list(text, ("约束", "限制", "constraint", "constraints"), max_items=40)
        preferences = _extract_labeled_list(text, ("偏好", "preference", "preferences"), max_items=1)
        attributes = _extract_labeled_list(text, ("属性", "评价维度", "attribute", "attributes"), max_items=20)
        return {
            "intent": "start_research_run",
            "confidence": 0.9,
            "extractedInputs": {
                "research_goal": research_goal,
                "starting_hypotheses": starting_hypotheses,
                "constraints": constraints,
                "preferences": preferences[0] if preferences else None,
                "attributes": attributes,
            },
            "missingInputs": [],
            "userFacingReason": "用户通过对话提供 research goal 并请求启动研究流程。",
        }
    if _contains_any(text, ["开始", "启动", "运行", "生成候选", "research goal", "start run", "run workflow"]):
        return {
            "intent": "start_research_run",
            "confidence": 0.68,
            "extractedInputs": {},
            "missingInputs": ["research_goal"],
            "userFacingReason": "用户想启动研究流程，但还缺少明确 research goal。",
        }
    if pdf_value or ("pdf" in lowered and any(word in text for word in ("解析", "入库", "导入", "保存"))):
        return {
            "intent": "parse_pdf_to_knowledge_base",
            "confidence": 0.94 if pdf_value else 0.7,
            "extractedInputs": {"pdf_path": pdf_value} if pdf_value else {},
            "missingInputs": [] if pdf_value else ["pdf_path"],
            "userFacingReason": "用户请求解析 PDF 并形成可检索证据。",
        }
    web_extract_urls = _extract_public_urls(text, limit=5)
    if url_value and any(word in text for word in ("网页", "证据", "抓取", "保存", "链接", "文章", "读取", "打开", "聚合", "整理")):
        if len(web_extract_urls) > 1 or _contains_any(text, ["高相关", "前几个", "前 3", "前3", "聚合", "整理", "汇总"]):
            return {
                "intent": "extract_web_evidence_batch",
                "confidence": 0.9,
                "extractedInputs": {"urls": web_extract_urls[:3], "query": text},
                "missingInputs": [],
                "userFacingReason": "用户请求抓取多个公开网页并整理正文证据。",
            }
        return {
            "intent": "extract_web_evidence",
            "confidence": 0.88,
            "extractedInputs": {"url": web_extract_urls[0] if web_extract_urls else url_value},
            "missingInputs": [],
            "userFacingReason": "用户请求保存公开网页证据。",
        }
    if any(word in text for word in ("外部", "文献", "mcp", "MCP", "反证", "负面结果", "failed replication")) and any(
        word in text for word in ("假设", "核验", "验证", "支撑", "检查", "grounded", "ungrounded")
    ):
        return {
            "intent": "verify_evidence_with_literature",
            "confidence": 0.84,
            "extractedInputs": {"hypothesis_text": text} if len(text) >= 12 else {},
            "missingInputs": [] if len(text) >= 12 else ["hypothesis_text"],
            "userFacingReason": "用户请求在本地核验后调用外部文献/MCP 检查潜在反证。",
        }
    if _contains_any(text, ["实验设计", "可证伪", "validation plan", "experiment plan", "实验计划", "失败条件"]):
        return {
            "intent": "design_experiment",
            "confidence": 0.82,
            "extractedInputs": {"hypothesis_index": hypothesis_index} if hypothesis_index is not None else {"query": text},
            "missingInputs": [],
            "userFacingReason": "用户请求把候选假设转成可证伪实验设计。",
        }
    if _contains_any(text, ["报告", "草稿", "论文", "draft", "report", "写作", "总结成文"]):
        return {
            "intent": "draft_report",
            "confidence": 0.78,
            "extractedInputs": {"query": text},
            "missingInputs": [],
            "userFacingReason": "用户请求把当前研究结果整理成报告结构。",
        }
    if _contains_any(text, ["历史", "以前", "之前", "session", "搜索记录", "找回"]):
        return {
            "intent": "search_session_history",
            "confidence": 0.78,
            "extractedInputs": {"query": text},
            "missingInputs": [],
            "userFacingReason": "用户请求搜索历史研究过程。",
        }
    if any(word in text for word in ("证据够", "支撑", "grounded", "ungrounded")) and len(text) >= 12:
        return {
            "intent": "check_hypothesis_grounding",
            "confidence": 0.78,
            "extractedInputs": {"hypothesis_text": text},
            "missingInputs": [],
            "userFacingReason": "用户请求检查假设证据支撑状态。",
        }
    if hypothesis_index is not None or _contains_any(text, ["解释假设", "检查假设", "这条假设", "这个假设", "候选假设"]):
        return {
            "intent": "inspect_hypothesis",
            "confidence": 0.75,
            "extractedInputs": {"hypothesis_index": hypothesis_index} if hypothesis_index is not None else {},
            "missingInputs": [],
            "userFacingReason": "用户请求检查当前 run 中的候选假设。",
        }
    if any(word in text for word in ("找", "搜索", "检索", "支持", "相关", "证据", "文献")):
        return {
            "intent": "search_knowledge_evidence",
            "confidence": 0.76,
            "extractedInputs": {"query": text},
            "missingInputs": [],
            "userFacingReason": "用户请求搜索知识库证据。",
        }
    return {
        "intent": "ask_project_ai",
        "confidence": 0.62,
        "extractedInputs": {"query": text},
        "missingInputs": [],
        "userFacingReason": "普通项目问答默认走 SQL 知识库检索和 live model prompt。",
    }


def _context_dict(context: ResearchChatContext) -> Dict[str, Any]:
    if hasattr(context, "model_dump"):
        return context.model_dump()
    return context.dict()


def _chat_session_mode(context: ResearchChatContext) -> str:
    if context.mode:
        return context.mode
    page = (context.page_path or context.page or "").lower()
    if "project-chat" in page:
        return "project_help"
    if "data" in page or "tools" in page:
        return "evidence"
    return "workspace"


def _ensure_chat_session(session_id: str, request: ResearchChatTurnRequest) -> None:
    title = request.message.strip().replace("\n", " ")[:120] or "Research chat"
    try:
        knowledge_base.upsert_research_chat_session(
            session_id=session_id,
            mode=_chat_session_mode(request.context),
            run_id=request.context.run_id,
            title=title,
            context=_context_dict(request.context),
        )
    except Exception as exc:
        print(f"Research chat session persistence failed for {session_id}: {exc}", file=sys.stderr)


def _record_chat_message(session_id: str, role: str, text: str, message: Dict[str, Any]) -> None:
    try:
        knowledge_base.record_research_chat_message(
            session_id=session_id,
            role=role,
            text=text,
            message=message,
        )
    except Exception as exc:
        print(f"Research chat message persistence failed for {session_id}: {exc}", file=sys.stderr)


def _chat_turn_response(
    *,
    session_id: str,
    assistant_message: Dict[str, Any],
    state: str,
) -> Dict[str, Any]:
    _record_chat_message(session_id, "assistant", str(assistant_message.get("text") or ""), assistant_message)
    return {
        "session_id": session_id,
        "assistant_message": assistant_message,
        "state": state,
    }


ResearchChatProgressCallback = Callable[[Dict[str, Any]], Awaitable[None]]


async def _emit_research_chat_progress(
    progress: Optional[ResearchChatProgressCallback],
    phase: str,
    message: str,
    **payload: Any,
) -> None:
    if progress is None:
        return
    event = {
        "phase": phase,
        "message": message,
        "createdAt": time.time(),
        **payload,
    }
    await progress(event)


def _research_chat_sse_event(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(serialize_value(data), ensure_ascii=False)}\n\n"


def _research_chat_request_with_session(request: ResearchChatTurnRequest, session_id: str) -> ResearchChatTurnRequest:
    payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
    payload["session_id"] = session_id
    return ResearchChatTurnRequest(**payload)


def _active_run_record(context: ResearchChatContext) -> Optional[RunRecord]:
    if context.run_id:
        return load_run_record(context.run_id)
    recent = knowledge_base.list_research_runs(limit=1)
    if recent:
        return load_run_record(str(recent[0]["run_id"]))
    return None


def _active_run_record_with_hypotheses(context: ResearchChatContext) -> Optional[RunRecord]:
    if context.run_id:
        return load_run_record(context.run_id)
    for item in knowledge_base.list_research_runs(limit=20):
        record = load_run_record(str(item["run_id"]))
        if record and record.hypotheses:
            return record
    return _active_run_record(context)


def _summarize_mode_boundary(record: Optional[RunRecord]) -> str:
    if not record:
        return "当前没有选中的研究运行。Demo、Live model 和 Literature-grounded 的边界会在启动前确认。"
    if record.request.demo_mode:
        return "Demo simulation：只能验证 UI、流程和 schema，不能当作科学证据。"
    if record.request.literature_review:
        return "Literature-grounded workflow：会尝试接入文献/MCP/fulltext，但证据不足时仍必须标记 limited 或 ungrounded。"
    return "Live model workflow：使用真实模型生成和排序，但未启用文献审查的结论不能伪装成文献支撑。"


def _run_summary_result(context: ResearchChatContext) -> Dict[str, Any]:
    record = _active_run_record(context)
    if not record:
        return {
            "intent": "explain_current_run",
            "title": "还没有当前研究运行",
            "summary": "你可以先用一句明确 research goal 启动研究流程，或询问这个项目能做什么。",
            "verdict": "limited",
            "nextActions": ["询问项目能力", "输入 research goal", "先解析相关 PDF"],
            "groundingBoundary": "run_audit",
        }
    timeline_tail = [serialize_value(item) for item in record.timeline[-4:]]
    return {
        "intent": "explain_current_run",
        "title": "当前研究运行",
        "summary": f"这次运行状态为 {record.status}，已有 {len(record.hypotheses)} 条候选假设和 {len(record.tournament_matchups)} 条锦标赛比较记录。",
        "status": record.status,
        "runId": record.run_id,
        "researchGoal": record.request.research_goal,
        "hypothesisCount": len(record.hypotheses),
        "tournamentCount": len(record.tournament_matchups),
        "timeline": timeline_tail,
        "modeBoundary": _summarize_mode_boundary(record),
        "nextActions": ["检查排名最高的假设", "解释 Elo 排名", "查看证据边界", "生成实验设计"],
        "groundingBoundary": "run_audit",
    }


def _plain_markdown_label(value: str) -> str:
    label = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    label = re.sub(r"[*_`#>]+", "", label)
    label = re.sub(r"\s+", " ", label).strip()
    return label


def _hypothesis_title(hypothesis: Dict[str, Any], index: int) -> str:
    title = (
        str(hypothesis.get("title") or "").strip()
        or str(hypothesis.get("text") or hypothesis.get("hypothesis") or hypothesis.get("technical_hypothesis") or "").strip()[:100]
        or str(hypothesis.get("id") or hypothesis.get("hypothesis_id") or "").strip()
        or f"候选假设 {index + 1}"
    )
    return _plain_markdown_label(title)


def _hypothesis_text(hypothesis: Dict[str, Any]) -> str:
    return str(hypothesis.get("text") or hypothesis.get("hypothesis") or hypothesis.get("technical_hypothesis") or "").strip()


def _hypothesis_brief(hypothesis: Dict[str, Any], index: int) -> Dict[str, Any]:
    review = hypothesis.get("review") or hypothesis.get("review_feedback") or hypothesis.get("critique") or {}
    if isinstance(review, dict):
        review_summary = review.get("summary") or review.get("constructive_feedback") or review.get("scientific_soundness") or ""
    else:
        review_summary = str(review)
    return {
        "index": index,
        "title": _hypothesis_title(hypothesis, index),
        "text": _hypothesis_text(hypothesis)[:900],
        "plainExplanation": hypothesis.get("explanation") or hypothesis.get("plain_explanation"),
        "experimentPlan": hypothesis.get("experiment") or hypothesis.get("experiment_plan") or hypothesis.get("validation_plan"),
        "score": hypothesis.get("score"),
        "eloRating": hypothesis.get("elo_rating"),
        "reviewSummary": str(review_summary)[:700],
        "groundingStatus": hypothesis.get("grounding_status"),
    }


def _selected_hypothesis(record: RunRecord, context: ResearchChatContext, inputs: Dict[str, Any]) -> tuple[Optional[int], Optional[Dict[str, Any]]]:
    if not record.hypotheses:
        return None, None
    requested_index = inputs.get("hypothesis_index")
    if requested_index is None:
        requested_index = context.selected_hypothesis_index
    if isinstance(requested_index, int):
        index = max(0, min(requested_index, len(record.hypotheses) - 1))
        return index, record.hypotheses[index]
    if context.selected_hypothesis_id:
        for index, hypothesis in enumerate(record.hypotheses):
            if str(hypothesis.get("id") or hypothesis.get("hypothesis_id") or "") == context.selected_hypothesis_id:
                return index, hypothesis
    return 0, record.hypotheses[0]


def _inspect_hypothesis_result(context: ResearchChatContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    record = _active_run_record_with_hypotheses(context)
    if not record:
        return {
            "intent": "inspect_hypothesis",
            "title": "还没有可检查的假设",
            "summary": "当前没有选中的 run。先启动研究流程，或打开一个历史运行。",
            "verdict": "limited",
            "nextActions": ["启动研究流程", "打开历史运行", "先解析证据 PDF"],
            "groundingBoundary": "run_audit",
        }
    if inputs.get("list_all"):
        hypotheses = [
            _hypothesis_brief(hypothesis, index)
            for index, hypothesis in enumerate(record.hypotheses)
            if isinstance(hypothesis, dict)
        ]
        return {
            "intent": "inspect_hypothesis",
            "title": f"当前 {len(hypotheses)} 条候选假设",
            "summary": (
                f"这次运行围绕“{record.request.research_goal}”生成了 {len(hypotheses)} 条候选假设。"
                "下面是每条假设的技术表述、通俗解释/验证计划摘要和排序信号；这些内容来自 run audit，不是重新启动 workflow。"
            ),
            "status": record.status,
            "runId": record.run_id,
            "researchGoal": record.request.research_goal,
            "hypothesisCount": len(hypotheses),
            "hypotheses": hypotheses,
            "verdict": "limited",
            "modeBoundary": _summarize_mode_boundary(record),
            "nextActions": ["查看 Elo 排名", "检查第 1 个假设证据", "为某条假设生成实验设计", "解析 fulltext PDF 补证据"],
            "groundingBoundary": "run_audit",
        }
    index, hypothesis = _selected_hypothesis(record, context, inputs)
    if hypothesis is None or index is None:
        return {
            "intent": "inspect_hypothesis",
            "title": "当前 run 没有候选假设",
            "summary": "这次运行尚未产出候选假设，可能仍在排队/运行中或已失败。",
            "status": record.status,
            "runId": record.run_id,
            "nextActions": ["查看运行状态", "重新启动研究流程"],
            "groundingBoundary": "run_audit",
        }
    support = hypothesis.get("knowledge_base_support") if isinstance(hypothesis.get("knowledge_base_support"), list) else []
    review = hypothesis.get("review") or hypothesis.get("review_feedback") or hypothesis.get("critique") or {}
    if isinstance(review, dict):
        review_summary = review.get("summary") or review.get("constructive_feedback") or review.get("scientific_soundness") or ""
    else:
        review_summary = str(review)
    return {
        "intent": "inspect_hypothesis",
        "title": f"候选假设 {index + 1}",
        "summary": _hypothesis_title(hypothesis, index),
        "runId": record.run_id,
        "hypothesisIndex": index,
        "hypothesisPreview": _hypothesis_text(hypothesis)[:900],
        "plainExplanation": hypothesis.get("explanation") or hypothesis.get("plain_explanation"),
        "experimentPlan": hypothesis.get("experiment") or hypothesis.get("experiment_plan") or hypothesis.get("validation_plan"),
        "score": hypothesis.get("score"),
        "eloRating": hypothesis.get("elo_rating"),
        "reviewSummary": str(review_summary)[:900],
        "items": support[:6],
        "verdict": "grounded" if any(item.get("source_reliability") == "parsed_fulltext" for item in support if isinstance(item, dict)) else "limited",
        "modeBoundary": _summarize_mode_boundary(record),
        "nextActions": ["解释 Elo 排名", "本地核验证据支撑", "生成可证伪实验设计", "解析更多 fulltext PDF"],
        "groundingBoundary": "run_audit",
    }


def _record_hypothesis_feedback_result(context: ResearchChatContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    record = _active_run_record(context)
    if not record:
        return {
            "intent": inputs.get("intent") or "apply_expert_feedback",
            "status": "needs_run",
            "title": "还没有可记录反馈的研究运行",
            "summary": "请先打开一个已有 run，或在假设详情中选中一条候选假设后再提交反馈。",
            "nextActions": ["打开历史运行", "启动研究流程", "选中一个候选假设"],
            "groundingBoundary": "human_feedback_memory",
        }

    index, hypothesis = _selected_hypothesis(record, context, inputs)
    target_ref: Dict[str, Any] = {}
    target_type: Literal["run", "hypothesis"] = "run"
    hypothesis_title = "当前 run"
    if hypothesis is not None and index is not None:
        target_type = "hypothesis"
        hypothesis_id = hypothesis.get("id") or hypothesis.get("hypothesis_id")
        target_ref = {
            "hypothesis_index": index,
            "hypothesis_id": hypothesis_id,
            "hypothesis_title": _hypothesis_title(hypothesis, index)[:240],
        }
        hypothesis_title = f"候选假设 {index + 1}"
    elif context.selected_hypothesis_id:
        target_type = "hypothesis"
        target_ref = {"hypothesis_id": context.selected_hypothesis_id}
        hypothesis_title = "选中假设"

    feedback_text = str(inputs.get("feedback_text") or "").strip()[:4000]
    feedback_type = str(inputs.get("feedback_type") or "critique")
    item = knowledge_base.store_feedback_item(
        run_id=record.run_id,
        target_type=target_type,
        target_ref=target_ref,
        feedback_type=feedback_type,
        text=feedback_text,
        source="chat",
    )
    if not isinstance(record.expert_feedback, dict) or not record.expert_feedback:
        initialize_expert_feedback_state(record)
    feedback_items = record.expert_feedback.get("feedback_items")
    if not isinstance(feedback_items, list):
        feedback_items = []
    feedback_items.append(item)
    record.expert_feedback["status"] = "feedback_recorded"
    record.expert_feedback["feedback_items"] = feedback_items[-50:]
    record.expert_feedback["latest_feedback_id"] = item.get("feedback_id")
    record.updated_at = time.time()
    persist_run_record(record)

    return {
        "intent": inputs.get("intent") or "apply_expert_feedback",
        "status": "complete",
        "title": "反馈已记录",
        "summary": (
            f"我已把你对{hypothesis_title}的反馈保存到本地反馈记忆。"
            "这条反馈会影响下一次 run 或 continuation，不会伪装成正在运行中的即时改写。"
        ),
        "runId": record.run_id,
        "targetType": target_type,
        "targetRef": target_ref,
        "feedback": item,
        "nextActions": ["基于当前 run 继续", "修订候选假设", "查看本 run 的反馈记录"],
        "groundingBoundary": "human_feedback_memory",
    }


def _matchup_value(matchup: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in matchup and matchup.get(key) is not None:
            return matchup.get(key)
    return None


def _ranking_explanation_result(context: ResearchChatContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    record = _active_run_record(context)
    if not record:
        return {
            "intent": "explain_ranking",
            "title": "还没有 Elo 排名可解释",
            "summary": "当前没有选中的 run。启动研究流程后，ranking phase 会生成 pairwise/tournament 记录。",
            "verdict": "limited",
            "nextActions": ["启动研究流程", "打开历史运行"],
            "groundingBoundary": "tournament_audit",
        }
    matchups = [item for item in record.tournament_matchups if isinstance(item, dict)]
    if not matchups:
        return {
            "intent": "explain_ranking",
            "title": "这次运行尚无 tournament matchups",
            "summary": "没有找到 winner/loser 级别的 Elo 比较记录。可能 ranking phase 未运行、运行尚未完成，或当前记录来自旧 schema。",
            "runId": record.run_id,
            "verdict": "limited",
            "nextActions": ["查看运行状态", "重新运行包含 ranking 的 workflow"],
            "groundingBoundary": "tournament_audit",
        }
    normalized: List[Dict[str, Any]] = []
    for index, matchup in enumerate(matchups[:12]):
        before = _matchup_value(matchup, "elo_before", "ratings_before", "before_elo", "beforeElo") or {}
        after = _matchup_value(matchup, "elo_after", "ratings_after", "after_elo", "afterElo") or {}
        delta = _matchup_value(matchup, "elo_delta", "rating_delta", "delta", "eloDelta") or {}
        winner = _matchup_value(matchup, "winner_id", "winner", "winner_hypothesis_id", "winnerHypothesisId")
        loser = _matchup_value(matchup, "loser_id", "loser", "loser_hypothesis_id", "loserHypothesisId")
        confidence = _matchup_value(matchup, "confidence", "judge_confidence", "confidence_score")
        normalized.append(
            {
                "matchupIndex": index + 1,
                "winner": winner,
                "loser": loser,
                "confidence": confidence,
                "beforeElo": before,
                "afterElo": after,
                "eloDelta": delta,
                "reasoning": _matchup_value(matchup, "reasoning", "rationale", "decision_reasoning", "summary"),
                "comparisonMode": _matchup_value(matchup, "comparison_mode", "mode", "comparisonMode"),
            }
        )
    ranked = sorted(
        [
            {
                "index": index,
                "title": _hypothesis_title(hypothesis, index),
                "eloRating": hypothesis.get("elo_rating") or hypothesis.get("rank") or hypothesis.get("score"),
            }
            for index, hypothesis in enumerate(record.hypotheses)
            if isinstance(hypothesis, dict)
        ],
        key=lambda item: float(item.get("eloRating") or 0),
        reverse=True,
    )
    return {
        "intent": "explain_ranking",
        "title": "Elo 锦标赛排名依据",
        "summary": f"这次运行保留了 {len(matchups)} 场 pairwise/tournament 比较。下面展示 winner/loser、confidence、before/after Elo 和 delta，便于审计排序是否符合论文式 tournament ranking。",
        "runId": record.run_id,
        "tournamentCount": len(matchups),
        "tournamentMatchups": normalized,
        "rankedHypotheses": ranked[:8],
        "verdict": "grounded",
        "nextActions": ["检查最高 Elo 假设", "查看完整 Ranking tab", "用证据核验获胜假设"],
        "groundingBoundary": "tournament_audit",
    }


def _capability_map_result() -> Dict[str, Any]:
    capabilities = _chat_capabilities()
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for capability in capabilities:
        grouped.setdefault(str(capability.get("taskArea") or "other"), []).append(capability)
    return {
        "intent": "discover_capabilities",
        "title": "这个项目可以通过对话完成的任务",
        "summary": "你可以直接用自然语言启动研究、解释当前 run、检查假设、审计 Elo 排名、解析 PDF/网页证据、搜索历史记录，写入型或外部工具动作会先给确认卡。",
        "capabilityGroups": grouped,
        "capabilities": capabilities,
        "modeBoundary": "Demo simulation 只验证 UI/schema；Live model 使用真实模型但未必有文献支撑；Literature-grounded 必须依赖 MCP、PDF fulltext 或知识库证据。",
        "nextActions": ["输入 research goal", "问我解释 Elo 排名", "解析一篇 PDF", "检查某条假设证据"],
        "groundingBoundary": "project_capability_registry",
    }


def _experiment_design_result(context: ResearchChatContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    base = _inspect_hypothesis_result(context, inputs)
    hypothesis_preview = base.get("hypothesisPreview") or str(inputs.get("query") or "")[:900]
    return {
        "intent": "design_experiment",
        "title": "可证伪实验设计草案",
        "summary": "V1 会把当前假设整理为实验任务，不直接执行实验。正式执行仍应进入受限 experiment workflow 并保留 provenance。",
        "hypothesisPreview": hypothesis_preview,
        "experimentPlan": base.get("experimentPlan") or "定义可观测变量、对照条件、失败标准和最小可行数据集后再执行。",
        "falsificationTests": [
            "列出至少一个会推翻该假设的负面结果。",
            "指定与替代理论区分开的关键指标。",
            "先用小样本或公开数据做可重复性检查。",
        ],
        "missingEvidence": ["需要 parsed fulltext 或实验数据片段支撑实验前提。"],
        "nextActions": ["创建待实验任务", "补充数据集/benchmark", "核验证据支撑", "生成报告草稿"],
        "groundingBoundary": "run_audit",
    }


def _report_draft_result(context: ResearchChatContext) -> Dict[str, Any]:
    record = _active_run_record(context)
    if not record:
        return {
            "intent": "draft_report",
            "title": "还没有可整理的研究结果",
            "summary": "先启动研究流程或打开历史运行，再生成报告结构。",
            "verdict": "limited",
            "nextActions": ["启动研究流程", "打开历史运行"],
            "groundingBoundary": "run_audit",
        }
    top_titles = [_hypothesis_title(hypothesis, index) for index, hypothesis in enumerate(record.hypotheses[:3]) if isinstance(hypothesis, dict)]
    return {
        "intent": "draft_report",
        "title": "报告草稿结构",
        "summary": "这是一份基于当前 run 的写作结构，不是科学发现声明。证据不足的部分应标注 limited 或 ungrounded。",
        "runId": record.run_id,
        "researchGoal": record.request.research_goal,
        "sections": [
            "Research goal and constraints",
            "Candidate hypotheses and rationale",
            "Tournament ranking and Elo audit",
            "Evidence grounding and limitations",
            "Falsifiable experiments and failure criteria",
            "Next research tasks",
        ],
        "items": [{"title": title, "source_channel": "run_hypothesis"} for title in top_titles],
        "modeBoundary": _summarize_mode_boundary(record),
        "nextActions": ["检查引用证据", "导出候选假设", "生成实验设计"],
        "groundingBoundary": "run_audit",
    }


def _compact_artifact_text(value: Any, *, limit: int = 700) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _append_project_artifact_evidence(
    items: List[Dict[str, Any]],
    seen: set[str],
    raw: Dict[str, Any],
    *,
    source_channel: str,
    hypothesis_index: Optional[int] = None,
) -> None:
    if not isinstance(raw, dict):
        return
    title = _compact_artifact_text(
        raw.get("title")
        or raw.get("chunk_title")
        or raw.get("source")
        or raw.get("evidence_summary")
        or raw.get("query")
        or "未命名证据线索",
        limit=180,
    )
    url = _compact_artifact_text(raw.get("url") or raw.get("evidence_path") or raw.get("link") or "", limit=600)
    evidence_id = _compact_artifact_text(raw.get("evidence_id") or raw.get("chunk_id") or raw.get("result_id") or "", limit=160)
    paper_id = _compact_artifact_text(raw.get("paper_id") or raw.get("parse_run_id") or "", limit=160)
    summary = _compact_artifact_text(
        raw.get("evidence_summary")
        or raw.get("snippet")
        or raw.get("text_preview")
        or raw.get("abstract")
        or raw.get("summary")
        or raw.get("content")
        or "",
        limit=850,
    )
    key = "|".join(part for part in (url, evidence_id, paper_id, title) if part) or title
    if key in seen:
        return
    seen.add(key)
    item = {
        "title": title,
        "url": url,
        "paper_id": paper_id or None,
        "evidence_id": evidence_id or None,
        "source_channel": source_channel,
        "source_reliability": raw.get("source_reliability") or raw.get("reliability") or raw.get("type"),
        "support_level": raw.get("support_level"),
        "evidence_summary": summary,
        "text_preview": summary,
        "hypothesis_index": raw.get("hypothesis_index", hypothesis_index),
        "created_at": raw.get("created_at"),
    }
    items.append({key: value for key, value in item.items() if value not in (None, "", [])})


def _run_evidence_inventory(record: RunRecord, *, limit: int = 16) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    counts = {
        "hypothesisEvidenceLinks": 0,
        "evidenceRetrievals": 0,
        "citationMapItems": 0,
        "knowledgeSupportItems": 0,
        "toolResultSummaries": 0,
        "parsedFulltextItems": 0,
        "webEvidenceItems": 0,
    }

    try:
        links = knowledge_base.get_hypothesis_evidence_links(record.run_id)
    except Exception:
        links = []
    counts["hypothesisEvidenceLinks"] = len(links)
    for link in links:
        if isinstance(link, dict):
            _append_project_artifact_evidence(items, seen, link, source_channel="run_evidence_link")

    for hypothesis_index, hypothesis in enumerate(record.hypotheses):
        if not isinstance(hypothesis, dict):
            continue
        support = hypothesis.get("knowledge_base_support")
        if isinstance(support, list):
            counts["knowledgeSupportItems"] += len([item for item in support if isinstance(item, dict)])
            for item in support:
                if isinstance(item, dict):
                    _append_project_artifact_evidence(
                        items,
                        seen,
                        item,
                        source_channel="hypothesis_knowledge_support",
                        hypothesis_index=hypothesis_index,
                    )
        citation_map = hypothesis.get("citation_map")
        if isinstance(citation_map, dict):
            for citation_key, citation in citation_map.items():
                counts["citationMapItems"] += 1
                if isinstance(citation, dict):
                    payload = {"evidence_id": citation_key, **citation}
                else:
                    payload = {"evidence_id": citation_key, "title": str(citation)}
                _append_project_artifact_evidence(
                    items,
                    seen,
                    payload,
                    source_channel="hypothesis_citation_map",
                    hypothesis_index=hypothesis_index,
                )

    try:
        retrievals = knowledge_base.get_evidence_retrievals(record.run_id)
    except Exception:
        retrievals = []
    counts["evidenceRetrievals"] = len(retrievals)
    for retrieval in retrievals:
        if not isinstance(retrieval, dict):
            continue
        for result in retrieval.get("results") or []:
            if isinstance(result, dict):
                _append_project_artifact_evidence(
                    items,
                    seen,
                    {
                        "query": retrieval.get("query"),
                        "hypothesis_index": retrieval.get("hypothesis_index"),
                        **result,
                    },
                    source_channel=str(retrieval.get("tool_name") or "evidence_retrieval"),
                )

    try:
        tool_results = knowledge_base.list_tool_results(record.run_id, limit=12)
    except Exception:
        tool_results = []
    counts["toolResultSummaries"] = len(tool_results)
    for result in tool_results:
        if isinstance(result, dict):
            _append_project_artifact_evidence(
                items,
                seen,
                {
                    "title": f"{result.get('tool_name') or 'tool'} / {result.get('result_kind') or 'result'}",
                    "summary": result.get("summary"),
                    "result_id": result.get("result_id"),
                    "created_at": result.get("created_at"),
                },
                source_channel="tool_result_summary",
            )

    counts["parsedFulltextItems"] = sum(1 for item in items if item.get("source_reliability") == "parsed_fulltext")
    counts["webEvidenceItems"] = sum(
        1
        for item in items
        if "web" in str(item.get("source_channel") or "").lower()
        or "html" in str(item.get("source_reliability") or "").lower()
    )
    return items[:limit], counts


def _run_experiment_inventory(record: RunRecord, *, limit: int = 8) -> List[Dict[str, Any]]:
    experiments: List[Dict[str, Any]] = []
    for index, hypothesis in enumerate(record.hypotheses):
        if not isinstance(hypothesis, dict):
            continue
        plan = _compact_artifact_text(
            hypothesis.get("experiment") or hypothesis.get("experiment_plan") or hypothesis.get("validation_plan"),
            limit=1200,
        )
        reviews = hypothesis.get("reviews") if isinstance(hypothesis.get("reviews"), list) else []
        review_obj = hypothesis.get("review") or hypothesis.get("review_feedback") or hypothesis.get("critique") or (reviews[0] if reviews else {})
        falsification = []
        if isinstance(review_obj, dict):
            raw_falsification = (
                review_obj.get("falsification_criteria")
                or review_obj.get("failure_conditions")
                or review_obj.get("falsification_tests")
                or []
            )
            if isinstance(raw_falsification, list):
                falsification = [_compact_artifact_text(item, limit=220) for item in raw_falsification if str(item).strip()]
        if plan or falsification:
            experiments.append(
                {
                    "index": len(experiments),
                    "hypothesisIndex": index,
                    "title": _hypothesis_title(hypothesis, index),
                    "experimentPlan": plan or "当前假设尚未包含完整实验计划，需要继续补可观测变量、对照组、失败条件和最小验证路径。",
                    "falsificationTests": falsification[:4],
                    "source_channel": "run_hypothesis_experiment_plan",
                }
            )
        if len(experiments) >= limit:
            break
    return experiments


def _project_artifacts_summary_result(context: ResearchChatContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
    record = _active_run_record_with_hypotheses(context)
    if not record:
        return {
            "intent": "summarize_project_artifacts",
            "title": "还没有可汇总的项目产物",
            "summary": "当前没有选中的 run，也没有找到带候选假设的历史运行。先启动研究流程，或打开一个已有项目运行。",
            "verdict": "limited",
            "nextActions": ["启动研究流程", "打开历史运行", "解析论文 PDF 后再生成假设"],
            "groundingBoundary": "run_audit",
        }

    hypotheses = [
        _hypothesis_brief(hypothesis, index)
        for index, hypothesis in enumerate(record.hypotheses)
        if isinstance(hypothesis, dict)
    ]
    evidence_items, evidence_counts = _run_evidence_inventory(record)
    experiments = _run_experiment_inventory(record)
    report_sections = [
        "Research goal and constraints",
        "Candidate hypotheses and rationale",
        "Tournament ranking and Elo audit",
        "Evidence grounding and limitations",
        "Falsifiable experiments and failure criteria",
        "Next research tasks",
    ]
    reports = [
        {
            "title": "报告草稿结构",
            "summary": "当前报告是从 run audit 派生的结构化草稿，不是已经导出的最终论文或科学发现声明。",
            "sections": report_sections,
            "source_channel": "derived_run_report",
        }
    ]
    evidence_count = len(evidence_items)
    verdict = "grounded" if evidence_counts.get("parsedFulltextItems", 0) else ("limited" if evidence_count else "ungrounded")
    summary = (
        f"当前 run 状态为 {record.status}；可读取 {len(hypotheses)} 条候选假设、"
        f"{evidence_count} 条论文/网页/PDF 证据线索、{len(experiments)} 条实验计划草案，"
        "并可按当前 run 派生报告草稿结构。"
    )
    if not evidence_count:
        summary += " 暂未发现已解析 fulltext 或已抓取网页证据，论文层面的回答应标记为 evidence-limited。"

    return {
        "intent": "summarize_project_artifacts",
        "title": "项目论文、假设、实验和报告清单",
        "summary": summary,
        "status": record.status,
        "runId": record.run_id,
        "researchGoal": record.request.research_goal,
        "hypothesisCount": len(hypotheses),
        "hypotheses": hypotheses[:8],
        "items": evidence_items[:8],
        "papers": evidence_items[:8],
        "experiments": experiments[:8],
        "reports": reports,
        "sections": report_sections,
        "artifactCounts": {
            "hypotheses": len(hypotheses),
            "evidenceItems": evidence_count,
            "experiments": len(experiments),
            "reports": len(reports),
            **evidence_counts,
        },
        "modeBoundary": _summarize_mode_boundary(record),
        "verdict": verdict,
        "query": str(inputs.get("query") or "").strip(),
        "nextActions": [
            "列出所有候选假设",
            "围绕第 1 条假设生成实验设计",
            "检查引用证据是否足够",
            "生成报告草稿",
        ],
        "groundingBoundary": "run_audit",
    }


def _session_search_result(context: ResearchChatContext, query: str) -> Dict[str, Any]:
    results = knowledge_base.search_research_sessions(
        query,
        run_id=context.run_id,
        limit=8,
    )
    return {
        "intent": "search_session_history",
        "title": f"找到 {len(results)} 条历史记录",
        "summary": "历史搜索只返回摘要和 target_ref，完整工具结果、PDF 全文和大型 payload 不会铺到默认对话里。",
        "query": query,
        "items": results,
        "nextActions": ["打开相关 run", "查看工具结果详情", "继续追问某条记录"],
        "groundingBoundary": "session_search",
    }


def _proposal_response(
    *,
    session_id: str,
    action_id: str,
    intent: str,
    title: str,
    summary: str,
    input_summary: str,
    operation_summary: List[str],
    risk_summary: str,
    expected_result_summary: List[str],
    approval_scope: str,
    execution_target: str,
    request_preview: Dict[str, Any],
) -> Dict[str, Any]:
    proposal = {
        "actionId": action_id,
        "intent": intent,
        "title": title,
        "summary": summary,
        "inputSummary": input_summary,
        "operationSummary": operation_summary,
        "riskSummary": risk_summary,
        "expectedResultSummary": expected_result_summary,
        "approvalRequired": True,
        "approvalScope": approval_scope,
        "executionTarget": execution_target,
        "requestPreview": request_preview,
    }
    research_chat_action_proposals[action_id] = {
        "session_id": session_id,
        "status": "proposed",
        "proposal": proposal,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    try:
        knowledge_base.upsert_research_chat_action(
            action_id=action_id,
            session_id=session_id,
            status="proposed",
            proposal=proposal,
        )
    except Exception as exc:
        print(f"Research chat action persistence failed for {action_id}: {exc}", file=sys.stderr)
    assistant_message = {
        "kind": "action_proposal",
        "text": summary,
        "proposal": proposal,
    }
    _record_chat_message(session_id, "assistant", summary, assistant_message)
    return {
        "session_id": session_id,
        "assistant_message": assistant_message,
        "state": "awaiting_confirmation",
    }


SAFE_RESEARCH_CHAT_APPROVAL_SCOPES = {
    "file.source_snapshot",
    "tool.register_draft",
}


def _research_chat_action_risk(proposal: Dict[str, Any]) -> Dict[str, Any]:
    scope = str(proposal.get("approvalScope") or "")
    target = str(proposal.get("executionTarget") or "")
    preview = proposal.get("requestPreview") if isinstance(proposal.get("requestPreview"), dict) else {}
    if target in {"workflow.terminal_command", "workflow.ssh_training_command"}:
        command_risk = preview.get("command_risk") if isinstance(preview.get("command_risk"), dict) else None
        if command_risk:
            return command_risk
        return classify_command_risk(str(preview.get("command") or ""))
    if scope in SAFE_RESEARCH_CHAT_APPROVAL_SCOPES:
        return {
            "allowed": True,
            "risk_level": "safe",
            "code": "safe_project_ai_action",
            "message": "This Project AI action is constrained to a schema-validated local workflow.",
        }
    return {
        "allowed": True,
        "risk_level": "review",
        "code": "project_ai_action_requires_review",
        "message": "This Project AI action may access external services, consume model resources, or write project artifacts.",
    }


def _research_chat_action_policy_decision(proposal: Dict[str, Any]) -> Dict[str, Any]:
    policy = get_command_permission_policy(KB_ROOT)
    risk = _research_chat_action_risk(proposal)
    mode = str(policy.get("mode") or "request_approval")
    risk_level = str(risk.get("risk_level") or "review")
    auto_approved = False
    if bool(risk.get("allowed", True)):
        auto_approved = mode == "full_access" or (mode == "approve_safe" and risk_level == "safe")
    return {
        "mode": mode,
        "label": policy.get("label"),
        "source": policy.get("source"),
        "approvalPolicy": policy.get("approval_policy"),
        "risk": risk,
        "autoApproved": auto_approved,
        "requiresApproval": not auto_approved,
    }


async def _proposal_or_auto_response(
    *,
    session_id: str,
    action_id: str,
    intent: str,
    title: str,
    summary: str,
    input_summary: str,
    operation_summary: List[str],
    risk_summary: str,
    expected_result_summary: List[str],
    approval_scope: str,
    execution_target: str,
    request_preview: Dict[str, Any],
) -> Dict[str, Any]:
    response = _proposal_response(
        session_id=session_id,
        action_id=action_id,
        intent=intent,
        title=title,
        summary=summary,
        input_summary=input_summary,
        operation_summary=operation_summary,
        risk_summary=risk_summary,
        expected_result_summary=expected_result_summary,
        approval_scope=approval_scope,
        execution_target=execution_target,
        request_preview=request_preview,
    )
    proposal = response.get("assistant_message", {}).get("proposal")
    if not isinstance(proposal, dict):
        return response
    decision = _research_chat_action_policy_decision(proposal)
    proposal["actionPolicyDecision"] = decision
    if decision.get("requiresApproval", True):
        return response
    approval = ToolWorkflowApproval(
        confirmed=True,
        scope=approval_scope,
        reason=f"Auto-approved by Project AI action policy: {decision.get('mode')}",
        granted_by="project_ai_action_policy",
        permission_mode=decision.get("mode"),
        command_risk=decision.get("risk") if isinstance(decision.get("risk"), dict) else None,
    )
    background_tasks = BackgroundTasks()
    confirmed = await confirm_research_chat_action(
        action_id,
        ResearchChatConfirmRequest(approval=approval),
        background_tasks,
    )
    if background_tasks.tasks:
        await background_tasks()
    result = confirmed.get("assistant_message", {}).get("result")
    if isinstance(result, dict):
        result["autoApproval"] = decision
    assistant_message = confirmed.get("assistant_message")
    if isinstance(assistant_message, dict):
        assistant_message["autoApproval"] = decision
    return confirmed


def _rag_result_summary(query: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {
            "title": "没有找到匹配证据",
            "summary": "当前知识库没有返回可用片段。建议换用更具体的术语，或先解析更多 PDF/fulltext。",
            "items": [],
            "verdict": "ungrounded",
            "nextActions": ["解析相关 PDF", "换一个更具体的检索词", "检查文献服务状态"],
        }
    parsed_fulltext_count = sum(1 for item in results if item.get("source_reliability") == "parsed_fulltext")
    return {
        "title": f"找到 {len(results)} 条候选证据",
        "summary": (
            f"其中 {parsed_fulltext_count} 条来自 parsed fulltext。"
            if parsed_fulltext_count
            else "当前结果不含 parsed fulltext，请谨慎作为文献支撑。"
        ),
        "items": results[:6],
        "verdict": "grounded" if parsed_fulltext_count >= 2 else "limited",
        "nextActions": ["查看证据详情", "继续解析 PDF", "用这些证据检查假设"],
    }


def _is_research_chat_llm_enabled() -> bool:
    return os.getenv("COSCIENTIST_RESEARCH_CHAT_LLM_ENABLED", "1").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _research_chat_model_name(context: ResearchChatContext) -> str:
    configured = os.getenv("COSCIENTIST_RESEARCH_CHAT_MODEL") or context.model_name
    if configured:
        return configured
    if has_provider_key("MIMO_API_KEY", "XIAOMI_MIMO_API_KEY", "MIMOCODE_API_KEY"):
        return "openai/mimo-v2.5"
    if has_provider_key("DEEPSEEK_API_KEY"):
        return "deepseek/deepseek-chat"
    return "deepseek/deepseek-v4-pro"


def _get_research_chat_llm_module() -> Any:
    global research_chat_llm_module
    if research_chat_llm_module is None:
        from open_coscientist import llm as llm_module

        research_chat_llm_module = llm_module
    return research_chat_llm_module


def _looks_like_plain_greeting(message: str) -> bool:
    normalized = re.sub(r"[\s,，。.!！?？~～]+", "", message.strip().lower())
    return normalized in {
        "你好",
        "您好",
        "hello",
        "hi",
        "hey",
        "你好啊",
        "在吗",
    }


def _format_research_chat_knowledge_context(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "当前知识库没有命中片段。"
    formatted: List[str] = []
    for index, item in enumerate(results[:5], start=1):
        section_path = " / ".join(str(value) for value in item.get("section_path") or [] if value)
        title = str(item.get("title") or item.get("chunk_title") or "Untitled source")
        reliability = str(item.get("source_reliability") or "unknown")
        support_level = str(item.get("support_level") or "unknown")
        preview = str(item.get("text_preview") or "").strip().replace("\n", " ")
        formatted.append(
            "\n".join(
                [
                    f"[K{index}] {title}",
                    f"section: {section_path or 'unknown'}",
                    f"source_reliability: {reliability}; support_level: {support_level}",
                    f"snippet: {preview[:900] or 'empty'}",
                ]
            )
        )
    return "\n\n".join(formatted)


def _format_research_chat_run_context(context: ResearchChatContext) -> str:
    record = _active_run_record(context)
    if not record:
        return "当前没有可用 run context。"
    evidence_items, evidence_counts = _run_evidence_inventory(record, limit=5)
    experiments = _run_experiment_inventory(record, limit=5)
    top_hypotheses: List[str] = []
    for index, hypothesis in enumerate(record.hypotheses[:3], start=1):
        if not isinstance(hypothesis, dict):
            continue
        title = _hypothesis_title(hypothesis, index - 1)
        score = hypothesis.get("elo_rating") or hypothesis.get("rank") or hypothesis.get("score")
        top_hypotheses.append(f"{index}. {title} (score={score or 'n/a'})")
    return "\n".join(
        [
            f"run_id: {record.run_id}",
            f"status: {record.status}",
            f"research_goal: {record.request.research_goal}",
            f"hypotheses_count: {len(record.hypotheses)}",
            f"evidence_items_count: {len(evidence_items)}",
            f"parsed_fulltext_items_count: {evidence_counts.get('parsedFulltextItems', 0)}",
            f"experiment_plans_count: {len(experiments)}",
            "report_draft_available: yes (derived from run audit)",
            "top_hypotheses:",
            "\n".join(top_hypotheses) or "none",
        ]
    )


def _dedupe_knowledge_results(results: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        key = str(item.get("chunk_id") or item.get("evidence_id") or item.get("title") or item.get("text_preview") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _project_chat_knowledge_fallback(*, limit: int = 2) -> List[Dict[str, Any]]:
    fallback: List[Dict[str, Any]] = []
    for document in knowledge_base.list_documents():
        metadata = document.metadata if isinstance(document.metadata, dict) else {}
        if (
            metadata.get("knowledge_kind") != "project_chat_system"
            or metadata.get("version") != PROJECT_CHAT_KNOWLEDGE_VERSION
        ):
            continue
        for chunk in document.chunks[:limit]:
            fallback.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "paper_id": document.paper_id,
                    "library_id": document.library_id,
                    "parse_run_id": document.parse_run_id,
                    "parse_item_key": "project_chat_system",
                    "title": document.title,
                    "section_path": chunk.section_path,
                    "section_type": chunk.section_type,
                    "text_preview": chunk.text[:700],
                    "evidence_summary": chunk.experiment_data_summary or chunk.title,
                    "support_level": chunk.support_level,
                    "source_reliability": document.source_reliability,
                    "evidence_path": document.url,
                    "evidence_id": chunk.evidence_id,
                    "rank": 0,
                }
            )
            if len(fallback) >= limit:
                return fallback
    return fallback


def _research_chat_knowledge_results(message: str, context: ResearchChatContext, *, limit: int = 6) -> List[Dict[str, Any]]:
    _ensure_project_chat_knowledge_index()
    results = paper_parse_store.rag_search(
        message,
        limit=limit,
        paper_id=context.paper_id,
        library_id=context.library_id,
    )
    if context.paper_id or context.library_id:
        results.extend(paper_parse_store.rag_search(message, limit=limit, paper_id=None, library_id=None))
    results.extend(_project_chat_knowledge_fallback(limit=2))
    return _dedupe_knowledge_results(results, limit=limit)


def _format_research_chat_structured_context(structured_context: Optional[Dict[str, Any]]) -> str:
    if not structured_context:
        return "当前没有额外结构化上下文。"
    try:
        payload = serialize_value(structured_context)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:
        text = str(structured_context)
    return text[:8000]


def _build_research_chat_llm_prompt(
    *,
    message: str,
    context: ResearchChatContext,
    knowledge_results: List[Dict[str, Any]],
    routed: Dict[str, Any],
    structured_context: Optional[Dict[str, Any]] = None,
) -> str:
    language = "中文" if context.language == "zh" else "English"
    capabilities = _chat_capabilities()
    capability_lines = [
        f"- {item['userTitle']}: {item['userSummary']} (mode={item['executionMode']})"
        for item in capabilities[:12]
    ]
    return f"""
你是这个本地 open-coscientist research workbench 的研究助手，回答语言：{language}。

行为约束：
- 你可以解释项目能力、当前工作台状态、知识库命中片段、prompt/template 接入方式和下一步研究操作。
- 不要声称这是 Google 官方闭源 AI co-scientist；只能称为基于公开思想的本地 open adaptation/workbench。
- 不要把 demo/synthetic 输出当成真实科学证据。
- 事实性科研结论必须区分 parsed fulltext / knowledge base / run audit / ungrounded。
- 不要直接执行命令、访问外部 Web、解析 PDF 或启动 live workflow；这些动作必须让用户通过确认卡授权。
- 如果知识库没有命中，就明确说证据不足，并建议解析 PDF、抓取网页证据或启动 literature-grounded workflow。
- 如果结构化上下文与知识库片段不一致，要说明证据边界，不要把结构化 run audit 当作外部文献事实。
- 如果结构化上下文包含 evidenceSourceExplanation 或 rankingCaveat，必须解释“当前证据如何获得”以及“Elo winner 不等于该假设已被证据支撑”。
- 最终回答文本必须由你基于上下文生成；不要照抄旧模板或 raw JSON。
- 回答保持简洁、可操作，优先给当前用户下一步。

当前 route:
intent: {routed.get("intent")}
reason: {routed.get("userFacingReason")}
routing_source: {routed.get("routingSource")}

最近对话:
{_format_recent_research_chat_context(routed.get("recentMessages") if isinstance(routed.get("recentMessages"), list) else [])}

当前 run context:
{_format_research_chat_run_context(context)}

结构化上下文:
{_format_research_chat_structured_context(structured_context)}

知识库检索片段:
{_format_research_chat_knowledge_context(knowledge_results)}

可用任务入口:
{chr(10).join(capability_lines)}

用户问题:
{message}
""".strip()


async def call_research_chat_llm(
    *,
    prompt: str,
    model_name: str,
    max_tokens: int = 900,
    temperature: float = 0.2,
    transport_attempts: int = 2,
) -> str:
    llm_module = _get_research_chat_llm_module()

    return await llm_module.call_llm(
        prompt,
        model_name=model_name,
        max_tokens=max_tokens,
        temperature=temperature,
        transport_attempts=transport_attempts,
    )


async def call_research_chat_planner_llm(*, prompt: str, model_name: str) -> str:
    llm_module = _get_research_chat_llm_module()
    return await llm_module.call_llm(
        prompt,
        model_name=model_name,
        max_tokens=900,
        temperature=0.0,
        transport_attempts=1,
    )


def _research_chat_capabilities_by_intent() -> Dict[str, Dict[str, Any]]:
    return {str(item.get("intent")): item for item in _chat_capabilities()}


def _research_chat_capabilities_by_id() -> Dict[str, Dict[str, Any]]:
    return {str(item.get("id")): item for item in _chat_capabilities()}


PLANNER_ALLOWED_INPUTS: Dict[str, set[str]] = {
    "ask_project_ai": {"query"},
    "discover_capabilities": {"query"},
    "summarize_project_artifacts": {"run_id", "query"},
    "start_research_run": {"research_goal", "starting_hypotheses", "constraints", "preferences", "attributes"},
    "explain_current_run": {"run_id", "query"},
    "continue_or_revise_run": {"run_id", "research_goal", "starting_hypotheses", "constraints", "preferences", "attributes"},
    "inspect_hypothesis": {"hypothesis_index", "hypothesis_id", "list_all", "query"},
    "apply_expert_feedback": {"hypothesis_index", "feedback_type", "feedback_text"},
    "critique_generated_hypothesis": {"hypothesis_index", "feedback_type", "feedback_text"},
    "explain_ranking": {"run_id", "hypothesis_index", "query"},
    "parse_pdf_to_knowledge_base": {"pdf_path"},
    "extract_web_evidence": {"url"},
    "extract_web_evidence_batch": {"urls", "query"},
    "search_public_web": {"query", "domains"},
    "search_knowledge_evidence": {"query"},
    "check_hypothesis_grounding": {"hypothesis_text"},
    "verify_evidence_with_literature": {"hypothesis_text", "query"},
    "design_experiment": {"hypothesis_index", "hypothesis_text", "query"},
    "draft_report": {"run_id", "query"},
    "search_session_history": {"query"},
    "run_terminal_command": {"command", "workdir"},
    "run_ssh_training_command": {"server_id", "command", "workdir"},
    "snapshot_local_file": {"source_path", "start_line", "line_count", "max_bytes", "run_id"},
    "register_project_tool": {
        "tool_name",
        "user_title",
        "description",
        "toolset",
        "phases",
        "risk_level",
        "input_schema",
        "execution_boundary",
        "run_id",
    },
    "clarify": {"question", "query"},
    "unsupported": {"query"},
}


def _recent_research_chat_context(session_id: Optional[str], *, limit: int = 6) -> List[Dict[str, Any]]:
    if not session_id:
        return []
    try:
        session = knowledge_base.get_research_chat_session(session_id)
    except Exception as exc:
        print(f"Research chat recent context load failed for {session_id}: {exc}", file=sys.stderr)
        return []
    messages = session.get("messages") if isinstance(session, dict) else []
    recent: List[Dict[str, Any]] = []
    for item in (messages or [])[-max(1, limit) :]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        recent.append(
            {
                "role": str(item.get("role") or "unknown"),
                "text": text[:900],
                "created_at": item.get("created_at"),
            }
        )
    return recent


def _format_recent_research_chat_context(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return "当前没有可用的最近对话。"
    return "\n".join(f"- {item.get('role')}: {str(item.get('text') or '')[:900]}" for item in messages[-6:])


def _research_chat_literal_refs(message: str) -> Dict[str, Any]:
    pdf_match = PDF_PATTERN.search(message)
    urls = _extract_public_urls(message, limit=5)
    terminal = _extract_terminal_command_request(message)
    managed_ssh = _extract_managed_ssh_request(message)
    arbitrary_ssh = _extract_arbitrary_ssh_terminal_request(message)
    explicit_web_search = _extract_web_search_request(message)
    source_file = _extract_source_file_request(message)
    tool_registration = _extract_tool_registration_request(message)
    refs: Dict[str, Any] = {
        "pdf_path": pdf_match.group("value") if pdf_match else None,
        "urls": urls,
        "hypothesis_index": _extract_hypothesis_index(message),
        "research_goal": _extract_research_goal(message),
        "web_search": explicit_web_search,
        "source_file": source_file,
        "tool_registration": tool_registration,
        "terminal_command": terminal,
        "managed_ssh": managed_ssh,
        "arbitrary_ssh": arbitrary_ssh,
        "conditional_tool_boundary": _looks_like_conditional_tool_boundary(message),
        "starting_hypotheses": _extract_starting_hypotheses(message),
        "constraints": _extract_labeled_list(message, ("约束", "限制", "constraint", "constraints"), max_items=40),
        "attributes": _extract_labeled_list(message, ("评价维度", "属性", "attribute", "attributes"), max_items=20),
        "preferences": (_extract_labeled_list(message, ("偏好", "preference", "preferences"), max_items=1) or [None])[0],
    }
    return {key: value for key, value in refs.items() if value not in (None, [], {})}


def _planner_capability_schema() -> List[Dict[str, Any]]:
    allowed_intents = {
        "ask_project_ai",
        "discover_capabilities",
        "summarize_project_artifacts",
        "start_research_run",
        "explain_current_run",
        "inspect_hypothesis",
        "explain_ranking",
        "parse_pdf_to_knowledge_base",
        "extract_web_evidence",
        "extract_web_evidence_batch",
        "search_public_web",
        "search_knowledge_evidence",
        "check_hypothesis_grounding",
        "verify_evidence_with_literature",
        "run_terminal_command",
        "run_ssh_training_command",
        "snapshot_local_file",
        "register_project_tool",
        "design_experiment",
        "draft_report",
        "search_session_history",
    }
    schema: List[Dict[str, Any]] = []
    for item in _chat_capabilities():
        intent = str(item.get("intent") or "")
        if intent not in allowed_intents:
            continue
        schema.append(
            {
                "id": item.get("id"),
                "intent": intent,
                "title": item.get("userTitle"),
                "summary": item.get("userSummary"),
                "executionMode": item.get("executionMode"),
                "approvalScope": item.get("approvalScope"),
                "requiredInputs": item.get("requiredInputs") or [],
                "groundingBoundary": item.get("groundingBoundary"),
                "availability": item.get("availability"),
            }
        )
    return schema


def _build_research_chat_planner_prompt(
    *,
    message: str,
    context: ResearchChatContext,
    session_id: str,
    literal_refs: Dict[str, Any],
    recent_messages: List[Dict[str, Any]],
) -> str:
    language = "中文" if context.language == "zh" else "English"
    context_payload = {
        "page": context.page or context.page_path,
        "mode": context.mode,
        "run_id": context.run_id,
        "paper_id": context.paper_id,
        "library_id": context.library_id,
        "selected_hypothesis_index": context.selected_hypothesis_index,
        "language": context.language,
    }
    return f"""
你是 Open Co-Scientist 项目聊天的 planner。你的任务只是在 tool schema 中选择一个能力或选择普通 RAG 问答，不要生成最终回答。

硬性规则:
- 除非用户明确要求执行外部动作，否则优先选择 ask_project_ai。
- 条件边界句不是工具请求。例如“如果下一步需要解析 PDF、联网搜索或调用外部文献服务，请先确认”只能表示安全要求，不能选择 Web Search/PDF/MCP。
- approval_required 能力只允许生成确认卡，不能直接执行。
- terminal/SSH 必须只有在用户明确要求执行命令时选择。
- snapshot_local_file 必须只有在用户明确要求读取/快照某个本地文件且能提供 source_path 时选择；模糊地“查找本地文件”应选择 ask_project_ai 或 clarify。
- register_project_tool 必须只有在用户明确要求注册/新增工具能力时选择；它只能注册 schema 草案，不能生成、安装或执行工具代码。
- 如果缺少 requiredInputs，把缺少字段放入 missingInputs。
- 如果只是询问概念、证据缺口、项目状态、工作流建议、Elo、候选假设解释，选择 read_only 能力。
- 如果用户询问“这个指定项目/当前项目里有哪些论文、证据、候选假设、实验、报告、产出”，选择 summarize_project_artifacts。
- 如果用户询问“当前这个项目可以实现什么/能做什么/有什么”，且当前上下文有 run_id，也选择 summarize_project_artifacts；不要因为句子里出现“反证检查”前缀就选择外部文献工具。
- 输出语言相关字段使用{language}，但最终必须只输出 JSON，不要 markdown，不要解释。

输出 JSON schema:
{{
  "intent": "ask_project_ai | discover_capabilities | summarize_project_artifacts | start_research_run | explain_current_run | inspect_hypothesis | explain_ranking | parse_pdf_to_knowledge_base | extract_web_evidence | extract_web_evidence_batch | search_public_web | search_knowledge_evidence | check_hypothesis_grounding | verify_evidence_with_literature | run_terminal_command | run_ssh_training_command | snapshot_local_file | register_project_tool | design_experiment | draft_report | search_session_history | clarify | unsupported",
  "capability_id": "tool schema id or null",
  "executionMode": "read_only | approval_required | unsupported",
  "inputs": {{}},
  "missingInputs": [],
  "confidence": 0.0,
  "groundingBoundary": "knowledge_base",
  "requiresConfirmation": false,
  "answerStrategy": "one short sentence describing why this route was selected"
}}

当前上下文:
{json.dumps(serialize_value(context_payload), ensure_ascii=False)}

最近对话:
{_format_recent_research_chat_context(recent_messages)}

literal refs extracted by guard code:
{json.dumps(serialize_value(literal_refs), ensure_ascii=False)}

tool/capability schema:
{json.dumps(serialize_value(_planner_capability_schema()), ensure_ascii=False)}

用户消息:
{message}
""".strip()


def _extract_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        raise ValueError("Planner did not return a JSON object.")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Planner JSON root is not an object.")
    return parsed


def _planner_failure_route(
    *,
    message: str,
    status: str,
    title: str,
    summary: str,
    model_name: str,
    recent_messages: Optional[List[Dict[str, Any]]] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "intent": "ask_project_ai",
        "confidence": 0.0,
        "extractedInputs": {"query": message},
        "missingInputs": [],
        "userFacingReason": summary,
        "status": status,
        "title": title,
        "summary": summary,
        "plannerStatus": status,
        "plannerReason": reason,
        "plannerConfidence": 0.0,
        "modelName": model_name,
        "routingSource": "fallback_error",
        "recentMessages": recent_messages or [],
    }


def _normalize_planner_inputs(intent: str, inputs: Dict[str, Any], literal_refs: Dict[str, Any], message: str) -> Dict[str, Any]:
    normalized = dict(inputs or {})
    if intent in {"ask_project_ai", "discover_capabilities", "summarize_project_artifacts", "search_knowledge_evidence", "search_session_history"}:
        normalized["query"] = str(normalized.get("query") or message).strip()
    if intent == "parse_pdf_to_knowledge_base" and not normalized.get("pdf_path"):
        normalized["pdf_path"] = literal_refs.get("pdf_path")
    if intent == "extract_web_evidence" and not normalized.get("url"):
        urls = literal_refs.get("urls") if isinstance(literal_refs.get("urls"), list) else []
        if urls:
            normalized["url"] = urls[0]
    if intent == "extract_web_evidence_batch" and not normalized.get("urls"):
        urls = literal_refs.get("urls") if isinstance(literal_refs.get("urls"), list) else []
        normalized["urls"] = urls[:3]
    if intent == "search_public_web":
        explicit = literal_refs.get("web_search") if isinstance(literal_refs.get("web_search"), dict) else {}
        normalized["query"] = str(normalized.get("query") or explicit.get("query") or "").strip()
        domains = normalized.get("domains") or explicit.get("domains") or []
        normalized["domains"] = [str(item).strip() for item in domains if str(item).strip()][:8] if isinstance(domains, list) else []
    if intent == "run_terminal_command":
        terminal = literal_refs.get("terminal_command") if isinstance(literal_refs.get("terminal_command"), dict) else {}
        arbitrary = literal_refs.get("arbitrary_ssh") if isinstance(literal_refs.get("arbitrary_ssh"), dict) else {}
        normalized["command"] = str(normalized.get("command") or terminal.get("command") or arbitrary.get("command") or "").strip()
        normalized["workdir"] = normalized.get("workdir") or terminal.get("workdir") or arbitrary.get("workdir")
    if intent == "run_ssh_training_command":
        managed = literal_refs.get("managed_ssh") if isinstance(literal_refs.get("managed_ssh"), dict) else {}
        normalized["server_id"] = str(normalized.get("server_id") or managed.get("server_id") or "").strip()
        normalized["command"] = str(normalized.get("command") or managed.get("command") or "").strip()
        normalized["workdir"] = normalized.get("workdir") or managed.get("workdir")
    if intent == "snapshot_local_file":
        source_file = literal_refs.get("source_file") if isinstance(literal_refs.get("source_file"), dict) else {}
        normalized["source_path"] = str(normalized.get("source_path") or source_file.get("source_path") or "").strip()
        for key, default, minimum, maximum in (
            ("start_line", 1, 1, 1_000_000),
            ("line_count", 200, 1, 2000),
            ("max_bytes", 1_000_000, 1024, 5_000_000),
        ):
            if normalized.get(key) is not None or source_file.get(key) is not None:
                normalized[key] = bounded_int(normalized.get(key) or source_file.get(key), default, minimum, maximum)
    if intent == "register_project_tool":
        draft = literal_refs.get("tool_registration") if isinstance(literal_refs.get("tool_registration"), dict) else {}
        normalized["tool_name"] = str(normalized.get("tool_name") or draft.get("tool_name") or "").strip()
        normalized["description"] = str(normalized.get("description") or draft.get("description") or "").strip()
        normalized["user_title"] = str(normalized.get("user_title") or "").strip()
        normalized["toolset"] = str(normalized.get("toolset") or "project_custom").strip()
        phases = normalized.get("phases")
        normalized["phases"] = [str(item).strip() for item in phases if str(item).strip()] if isinstance(phases, list) else []
        normalized["risk_level"] = str(normalized.get("risk_level") or "read").strip()
        if not isinstance(normalized.get("input_schema"), dict):
            normalized["input_schema"] = {}
        normalized["execution_boundary"] = str(normalized.get("execution_boundary") or "schema_registered_only").strip()
    if intent == "start_research_run":
        literal_research_goal = literal_refs.get("research_goal")
        if literal_research_goal and _looks_like_start_research_run_request(message):
            normalized["research_goal"] = str(literal_research_goal or "").strip()
        else:
            normalized["research_goal"] = str(normalized.get("research_goal") or literal_research_goal or "").strip()
        for key in ("starting_hypotheses", "constraints", "attributes"):
            value = normalized.get(key)
            literal_value = literal_refs.get(key)
            source_value = value if isinstance(value, list) and value else literal_value
            normalized[key] = [str(item).strip() for item in source_value if str(item).strip()] if isinstance(source_value, list) else []
        if normalized.get("preferences") is not None:
            normalized["preferences"] = str(normalized.get("preferences") or "").strip()
        elif literal_refs.get("preferences"):
            normalized["preferences"] = str(literal_refs.get("preferences") or "").strip()
    if intent in {"inspect_hypothesis", "explain_ranking", "design_experiment"} and normalized.get("hypothesis_index") is None:
        normalized["hypothesis_index"] = literal_refs.get("hypothesis_index")
    if intent in {"check_hypothesis_grounding", "verify_evidence_with_literature"}:
        normalized["hypothesis_text"] = str(normalized.get("hypothesis_text") or "").strip()
        if not normalized["hypothesis_text"] and len(message.strip()) >= 12:
            normalized["hypothesis_text"] = message.strip()
    if intent in {"apply_expert_feedback", "critique_generated_hypothesis"}:
        normalized["feedback_text"] = str(normalized.get("feedback_text") or message).strip()
    return {key: value for key, value in normalized.items() if value not in (None, "", [])}


def _validate_planner_route(
    *,
    raw_plan: Dict[str, Any],
    message: str,
    context: ResearchChatContext,
    literal_refs: Dict[str, Any],
    recent_messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    capabilities_by_intent = _research_chat_capabilities_by_intent()
    capabilities_by_id = _research_chat_capabilities_by_id()
    intent = str(raw_plan.get("intent") or "ask_project_ai").strip()
    if context.run_id and _looks_like_current_project_inventory_question(message) and intent in {
        "ask_project_ai",
        "discover_capabilities",
        "verify_evidence_with_literature",
        "check_hypothesis_grounding",
    }:
        intent = "summarize_project_artifacts"
        raw_plan = {
            **raw_plan,
            "intent": intent,
            "capability_id": "project.summarize_artifacts",
            "inputs": {"query": message},
            "executionMode": "read_only",
            "answerStrategy": "用户请求当前指定项目的产物和能力概览，应读取当前 run audit，而不是启动外部文献反证工具。",
        }
    planner_requested_execution = (
        str(raw_plan.get("executionMode") or raw_plan.get("execution_mode") or "").strip() == "approval_required"
        or bool(raw_plan.get("requiresConfirmation") is True)
    )
    if planner_requested_execution and _looks_like_start_research_run_request(message) and intent in {
        "ask_project_ai",
        "discover_capabilities",
        "search_knowledge_evidence",
        "check_hypothesis_grounding",
        "verify_evidence_with_literature",
        "clarify",
    }:
        intent = "start_research_run"
        raw_plan = {
            **raw_plan,
            "intent": intent,
            "capability_id": "research.start_run",
            "inputs": {
                "research_goal": literal_refs.get("research_goal"),
                "starting_hypotheses": literal_refs.get("starting_hypotheses") or [],
                "preferences": literal_refs.get("preferences"),
                "constraints": literal_refs.get("constraints") or [],
                "attributes": literal_refs.get("attributes") or [],
            },
            "executionMode": "approval_required",
            "answerStrategy": "用户提供了明确研究目标并请求评审/排序，应生成启动确认卡。",
        }
    capability_id = raw_plan.get("capability_id")
    capability = capabilities_by_intent.get(intent)
    if capability_id:
        selected = capabilities_by_id.get(str(capability_id))
        if selected is None or str(selected.get("intent")) != intent:
            raise ValueError(f"Planner selected invalid capability_id for intent: {capability_id}")
        capability = selected
    if intent in {"clarify", "unsupported"}:
        return {
            "intent": intent,
            "confidence": float(raw_plan.get("confidence") or 0.0),
            "extractedInputs": {"query": message},
            "missingInputs": list(raw_plan.get("missingInputs") or []),
            "userFacingReason": str(raw_plan.get("answerStrategy") or "Planner requested clarification."),
            "plannerStatus": "complete",
            "plannerConfidence": float(raw_plan.get("confidence") or 0.0),
            "capabilityId": capability_id,
            "routingSource": "llm_planner",
            "recentMessages": recent_messages,
        }
    if capability is None:
        raise ValueError(f"Planner selected unknown intent: {intent}")
    inputs_raw = raw_plan.get("inputs") if isinstance(raw_plan.get("inputs"), dict) else {}
    allowed_inputs = PLANNER_ALLOWED_INPUTS.get(intent, set())
    unknown_inputs = sorted(key for key in inputs_raw if key not in allowed_inputs)
    if unknown_inputs:
        raise ValueError(f"Planner returned unknown input keys for {intent}: {unknown_inputs}")
    inputs = _normalize_planner_inputs(intent, inputs_raw, literal_refs, message)
    missing = [str(item.get("key")) for item in capability.get("requiredInputs") or [] if item.get("required") and not inputs.get(str(item.get("key")))]
    missing.extend(str(item) for item in raw_plan.get("missingInputs") or [] if str(item) and str(item) not in missing)
    execution_mode = str(capability.get("executionMode") or raw_plan.get("executionMode") or "read_only")
    if execution_mode == "approval_required" and not capability.get("approvalScope"):
        raise ValueError(f"Approval-required capability has no approvalScope: {intent}")
    if intent == "run_terminal_command" and inputs.get("command"):
        command_risk = classify_command_risk(str(inputs["command"]))
        if command_risk.get("allowed") is False or command_risk.get("risk_level") == "blocked":
            raise ValueError("Planner selected a blocked terminal command.")
    return {
        "intent": intent,
        "confidence": float(raw_plan.get("confidence") or 0.0),
        "extractedInputs": inputs,
        "missingInputs": missing,
        "userFacingReason": str(raw_plan.get("answerStrategy") or capability.get("userSummary") or "LLM planner selected this route."),
        "plannerStatus": "complete",
        "plannerConfidence": float(raw_plan.get("confidence") or 0.0),
        "capabilityId": str(capability.get("id") or capability_id or ""),
        "executionMode": execution_mode,
        "requiresConfirmation": execution_mode == "approval_required",
        "groundingBoundary": capability.get("groundingBoundary") or raw_plan.get("groundingBoundary"),
        "routingSource": "llm_planner",
        "recentMessages": recent_messages,
    }


async def _plan_research_chat_route(
    *,
    request: ResearchChatTurnRequest,
    session_id: str,
    progress: Optional[ResearchChatProgressCallback] = None,
) -> Dict[str, Any]:
    model_name = _research_chat_model_name(request.context)
    recent_messages = _recent_research_chat_context(session_id)
    literal_refs = _research_chat_literal_refs(request.message)
    await _emit_research_chat_progress(
        progress,
        "planner_start",
        "正在用模型 planner 结合 tool schema 判断意图和安全边界。",
        modelName=model_name,
    )
    if not _is_research_chat_llm_enabled():
        route = _planner_failure_route(
            message=request.message,
            status="model_disabled",
            title="模型规划器未启用",
            summary="项目聊天现在需要模型 planner 才能解释自然语言和选择工具；当前模型问答未启用，因此不会用关键词规则触发工具。",
            model_name=model_name,
            recent_messages=recent_messages,
        )
        await _emit_research_chat_progress(progress, "planner_error", route["summary"], modelName=model_name)
        return route
    if not has_model_provider_key(model_name):
        route = _planner_failure_route(
            message=request.message,
            status="model_missing",
            title="模型规划器不可用",
            summary="项目聊天现在需要模型 planner 才能解释自然语言和选择工具；当前模型凭据不可用，因此不会用关键词规则触发工具。",
            model_name=model_name,
            recent_messages=recent_messages,
        )
        await _emit_research_chat_progress(progress, "planner_error", route["summary"], modelName=model_name)
        return route
    prompt = _build_research_chat_planner_prompt(
        message=request.message,
        context=request.context,
        session_id=session_id,
        literal_refs=literal_refs,
        recent_messages=recent_messages,
    )
    try:
        raw = await call_research_chat_planner_llm(prompt=prompt, model_name=model_name)
        plan = _extract_json_object(raw)
        routed = _validate_planner_route(
            raw_plan=plan,
            message=request.message,
            context=request.context,
            literal_refs=literal_refs,
            recent_messages=recent_messages,
        )
        await _emit_research_chat_progress(
            progress,
            "planner_complete",
            f"模型 planner 已选择：{routed.get('intent')}。",
            intent=routed.get("intent"),
            modelName=model_name,
            missingInputs=list(routed.get("missingInputs") or []),
        )
        return routed
    except Exception as exc:
        route = _planner_failure_route(
            message=request.message,
            status="planner_error",
            title="模型规划器返回不可用",
            summary="模型 planner 没有返回可验证的 tool schema JSON，因此没有触发任何工具动作。请重试或把请求拆成更明确的一步。",
            model_name=model_name,
            recent_messages=recent_messages,
            reason=str(exc),
        )
        await _emit_research_chat_progress(
            progress,
            "planner_error",
            route["summary"],
            modelName=model_name,
            error=str(exc)[:240],
        )
        return route


def _extract_litellm_stream_delta(chunk: Any) -> str:
    try:
        choices = getattr(chunk, "choices", None)
        if choices:
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None)
            if content:
                return str(content)
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None)
            if content:
                return str(content)
        if isinstance(chunk, dict):
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            content = delta.get("content") or (choice.get("message") or {}).get("content")
            return str(content or "")
    except Exception:
        return ""
    return ""


async def call_research_chat_llm_stream(
    *,
    prompt: str,
    model_name: str,
    progress: Optional[ResearchChatProgressCallback],
    max_tokens: int = 900,
    temperature: float = 0.2,
) -> str:
    llm_module = _get_research_chat_llm_module()

    completion_args = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "drop_params": True,
        "stream": True,
    }
    completion_args.update(llm_module.transport_resilience_overrides(model_name))
    completion_args.update(llm_module.mimo_completion_overrides(model_name))

    chunks: List[str] = []
    response = await llm_module.litellm.acompletion(**completion_args)
    async for chunk in response:
        delta = _extract_litellm_stream_delta(chunk)
        if not delta:
            continue
        chunks.append(delta)
        await _emit_research_chat_progress(
            progress,
            "answer_delta",
            "正在生成回答正文。",
            delta=delta,
            modelName=model_name,
        )
    content = "".join(chunks).strip()
    if not content:
        raise ValueError(f"LLM stream returned empty content. Model: {model_name}")
    return content


def _research_chat_response_max_tokens(routed: Dict[str, Any]) -> int:
    intent = str(routed.get("intent") or "")
    if intent in {"ask_project_ai", "discover_capabilities", "search_knowledge_evidence", "explain_current_run"}:
        return 560
    if intent == "summarize_project_artifacts":
        return 1000
    if intent in {"explain_ranking", "inspect_hypothesis", "design_experiment", "critique_generated_hypothesis"}:
        return 760
    if intent == "draft_report":
        return 1200
    return 700


def _format_web_search_results_for_synthesis(web_search: Dict[str, Any], *, limit: int = 5) -> str:
    results = web_search.get("results") if isinstance(web_search.get("results"), list) else []
    formatted: List[str] = []
    for index, item in enumerate(results[:limit], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "Untitled result").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("snippet") or item.get("content") or "").strip().replace("\n", " ")
        source = str(item.get("source") or item.get("provider") or "").strip()
        formatted.append(
            "\n".join(
                [
                    f"[S{index}] {title}",
                    f"url: {url or 'unknown'}",
                    f"source: {source or 'public web search'}",
                    f"snippet: {snippet[:420] or 'empty'}",
                ]
            )
        )
    return "\n\n".join(formatted) or "搜索 provider 没有返回可整理的 snippet。"


def _web_search_synthesis_model_name(model_name: str) -> str:
    configured = os.getenv("COSCIENTIST_RESEARCH_CHAT_SYNTHESIS_MODEL")
    if configured:
        return configured
    if model_name.startswith("deepseek/"):
        return "deepseek/deepseek-chat"
    return model_name


async def _synthesize_web_search_answer(
    *,
    query: str,
    web_search: Dict[str, Any],
    model_name: str,
) -> Optional[str]:
    if not _is_research_chat_llm_enabled() or not has_model_provider_key(model_name):
        return None
    prompt = f"""
你是 Open Co-Scientist 项目 AI。用户授权执行了公开 Web Search，现在需要你把搜索结果整理成可读回答。

硬性边界:
- 只能基于下面的 search snippets、标题和 URL 做整理。
- 必须明确说明这些结果是 snippets-only 线索，不是全文证据或已验证结论。
- 如果 snippets 互相冲突或不足，要说“不足以确认”，并给出下一步抓取网页、解析 PDF 或调用文献 MCP 的建议。
- 不要编造没有出现在 snippets 里的比分、日期、机构、论文结论或 URL。
- 用中文回答，结构紧凑。

用户问题:
{query}

搜索结果:
{_format_web_search_results_for_synthesis(web_search)}

输出格式:
1. 直接回答: 用 2-3 句概括目前从 snippets 能看到什么。
2. 线索来源: 列出 2-4 条最相关 URL 标题和为什么相关。
3. 证据边界与下一步: 一句话说明 snippets-only 限制和下一步。
""".strip()
    try:
        return await asyncio.wait_for(
            call_research_chat_llm(
                prompt=prompt,
                model_name=model_name,
                max_tokens=420,
                temperature=0.15,
                transport_attempts=1,
            ),
            timeout=60,
        )
    except Exception as exc:
        print(f"Web search synthesis failed: {exc}", file=sys.stderr)
        return None


def _format_web_extract_results_for_synthesis(web_results: List[Dict[str, Any]], *, limit: int = 3) -> str:
    formatted: List[str] = []
    for index, item in enumerate(web_results[:limit], start=1):
        title = str(item.get("title") or item.get("final_url") or f"网页 {index}").strip()
        url = str(item.get("final_url") or item.get("requested_url") or "").strip()
        reliability = str(item.get("source_reliability") or "best_effort_public_html")
        preview = str(item.get("text_preview") or "").strip().replace("\n", " ")
        formatted.append(
            "\n".join(
                [
                    f"[W{index}] {title}",
                    f"url: {url or 'unknown'}",
                    f"source_reliability: {reliability}",
                    f"content_preview: {preview[:1000] or 'empty'}",
                ]
            )
        )
    return "\n\n".join(formatted) or "没有抓取到可整理的网页正文。"


def _fallback_web_extract_answer(query: str, web_results: List[Dict[str, Any]], errors: List[Dict[str, str]]) -> str:
    lines = [f"已抓取 {len(web_results)} 个公开网页正文，并按 best-effort public HTML 证据处理。"]
    if query:
        lines.append(f"原始问题/目标：{query[:240]}")
    for index, item in enumerate(web_results[:3], start=1):
        title = str(item.get("title") or item.get("final_url") or f"网页 {index}").strip()
        url = str(item.get("final_url") or item.get("requested_url") or "").strip()
        preview = str(item.get("text_preview") or "").strip().replace("\n", " ")
        lines.append(f"{index}. {title}\n{url}\n{preview[:360] or '没有抽取到正文 preview。'}")
    if errors:
        lines.append("部分网页未能抓取：" + "；".join(f"{item.get('url')}: {item.get('error')}" for item in errors[:3]))
    lines.append("证据边界：这些是网页正文的 best-effort 抽取结果，仍建议优先抓取官方文档、PDF 或权威来源做最终核验。")
    return "\n\n".join(lines)


async def _synthesize_web_extract_answer(
    *,
    query: str,
    web_results: List[Dict[str, Any]],
    errors: List[Dict[str, str]],
    model_name: str,
) -> Optional[str]:
    if not web_results or not _is_research_chat_llm_enabled() or not has_model_provider_key(model_name):
        return None
    error_block = "\n".join(f"- {item.get('url')}: {item.get('error')}" for item in errors[:5]) or "无。"
    prompt = f"""
你是 Open Co-Scientist 项目 AI。用户授权抓取了公开网页正文，现在需要你基于网页正文 preview 聚合回答。

硬性边界:
- 只能基于下面的网页正文 preview、标题和 URL 作答。
- 这些是 best-effort public HTML 抽取，不等于权威全文审查；需要标注证据边界。
- 如果网页内容不足或互相冲突，要明确指出不足，并建议抓取官方文档、PDF 或更权威来源。
- 不要编造没有出现在网页正文里的细节。
- 用中文回答，结构紧凑。

用户问题/目标:
{query}

已抓取网页:
{_format_web_extract_results_for_synthesis(web_results)}

抓取失败:
{error_block}

输出格式:
1. 聚合回答: 用 3-5 句回答用户问题。
2. 来源依据: 列出 2-3 个网页标题/URL 与支撑点。
3. 证据边界与下一步: 说明局限和下一步。
""".strip()
    try:
        return await asyncio.wait_for(
            call_research_chat_llm(
                prompt=prompt,
                model_name=model_name,
                max_tokens=620,
                temperature=0.15,
                transport_attempts=1,
            ),
            timeout=75,
        )
    except Exception as exc:
        print(f"Web extract synthesis failed: {exc}", file=sys.stderr)
        return None


async def _research_chat_llm_result(
    *,
    message: str,
    context: ResearchChatContext,
    routed: Dict[str, Any],
    structured_context: Optional[Dict[str, Any]] = None,
    knowledge_results: Optional[List[Dict[str, Any]]] = None,
    progress: Optional[ResearchChatProgressCallback] = None,
) -> Dict[str, Any]:
    started_at = time.perf_counter()
    model_name = _research_chat_model_name(context)
    await _emit_research_chat_progress(
        progress,
        "route",
        "已识别问题类型，正在准备知识库检索。",
        intent=routed.get("intent", "clarify"),
        modelName=model_name,
    )
    await _emit_research_chat_progress(
        progress,
        "rag_start",
        "正在检索 SQL 知识库、PDF/fulltext 片段和项目系统知识。",
        scoped=bool(context.paper_id or context.library_id or context.run_id),
    )
    resolved_knowledge_results = (
        _dedupe_knowledge_results(knowledge_results, limit=8)
        if knowledge_results is not None
        else _research_chat_knowledge_results(message, context, limit=6)
    )
    await _emit_research_chat_progress(
        progress,
        "rag_complete",
        f"知识库检索完成，命中 {len(resolved_knowledge_results)} 条可用片段。",
        knowledgeHitCount=len(resolved_knowledge_results),
        elapsedMs=round((time.perf_counter() - started_at) * 1000),
    )
    base_result: Dict[str, Any] = dict(structured_context or {})
    routing_metadata = {
        key: routed.get(key)
        for key in ("plannerStatus", "plannerConfidence", "capabilityId", "routingSource")
        if routed.get(key) is not None
    }
    if not _is_research_chat_llm_enabled():
        await _emit_research_chat_progress(
            progress,
            "model_skipped",
            "模型问答未启用，返回明确的 model_disabled 状态。",
            modelName=model_name,
        )
        return {
            **base_result,
            **routing_metadata,
            "intent": routed.get("intent", "clarify"),
            "title": "模型问答未启用",
            "summary": "模型问答当前未启用，因此无法生成 SQL RAG + LLM 回答。写入型动作仍可通过确认卡准备，启用模型后请重新发送问题。",
            "status": "model_disabled",
            "verdict": "limited",
            "items": resolved_knowledge_results[:5],
            "knowledgeHitCount": len(resolved_knowledge_results),
            "modelName": model_name,
            "structuredContext": serialize_value(structured_context) if structured_context else None,
            "nextActions": ["配置模型问答开关", "输入 research goal", "解析 PDF 并入库"],
            "groundingBoundary": "knowledge_base" if resolved_knowledge_results else "model_without_local_evidence",
        }
    if not has_model_provider_key(model_name):
        await _emit_research_chat_progress(
            progress,
            "model_skipped",
            "模型凭据不可用，返回明确的 model_missing 状态。",
            modelName=model_name,
        )
        return {
            **base_result,
            **routing_metadata,
            "intent": routed.get("intent", "clarify"),
            "title": "模型通道尚未配置",
            "summary": "这个问题需要由 live model 基于 SQL 知识库检索片段回答，但当前后端没有可用模型凭据。请配置模型 API 后重新发送；写入型动作仍会通过确认卡处理。",
            "status": "model_missing",
            "verdict": "limited",
            "items": resolved_knowledge_results[:5],
            "knowledgeHitCount": len(resolved_knowledge_results),
            "modelName": model_name,
            "structuredContext": serialize_value(structured_context) if structured_context else None,
            "nextActions": ["配置模型 API 环境变量", "选择对应模型", "重启 FastAPI bridge", "重新发送问题"],
            "groundingBoundary": "knowledge_base" if resolved_knowledge_results else "model_without_local_evidence",
        }

    await _emit_research_chat_progress(
        progress,
        "context_ready",
        "已完成结构化上下文和检索片段拼接，准备调用模型生成回答。",
        knowledgeHitCount=len(resolved_knowledge_results),
        modelName=model_name,
    )
    prompt = _build_research_chat_llm_prompt(
        message=message,
        context=context,
        knowledge_results=resolved_knowledge_results,
        routed=routed,
        structured_context=structured_context,
    )
    try:
        max_tokens = _research_chat_response_max_tokens(routed)
        await _emit_research_chat_progress(
            progress,
            "model_start",
            "正在等待模型基于知识库片段生成回答。",
            modelName=model_name,
            maxTokens=max_tokens,
        )
        if progress is not None:
            try:
                answer = await call_research_chat_llm_stream(
                    prompt=prompt,
                    model_name=model_name,
                    progress=progress,
                    max_tokens=max_tokens,
                )
            except Exception as stream_exc:
                print(f"Research chat streaming LLM call fell back to non-streaming: {stream_exc}", file=sys.stderr)
                await _emit_research_chat_progress(
                    progress,
                    "model_stream_fallback",
                    "当前模型通道不支持稳定正文流，已回退为完整回答返回。",
                    modelName=model_name,
                )
                answer = await call_research_chat_llm(prompt=prompt, model_name=model_name, max_tokens=max_tokens)
        else:
            answer = await call_research_chat_llm(prompt=prompt, model_name=model_name, max_tokens=max_tokens)
        await _emit_research_chat_progress(
            progress,
            "model_complete",
            "模型回答已生成，正在保存对话结果。",
            modelName=model_name,
            elapsedMs=round((time.perf_counter() - started_at) * 1000),
        )
    except Exception as exc:
        print(f"Research chat LLM call failed: {exc}", file=sys.stderr)
        await _emit_research_chat_progress(
            progress,
            "model_error",
            "模型调用失败，返回可恢复的 model_error 状态。",
            modelName=model_name,
            elapsedMs=round((time.perf_counter() - started_at) * 1000),
        )
        return {
            **base_result,
            **routing_metadata,
            "intent": routed.get("intent", "clarify"),
            "title": "模型回答暂时不可用",
            "summary": "SQL 知识库检索已完成，但 live model 调用失败，因此没有生成模型回答。请检查模型服务、key、网络或稍后重试；写入型任务仍会通过确认卡执行。",
            "status": "model_error",
            "verdict": "limited",
            "items": resolved_knowledge_results[:5],
            "knowledgeHitCount": len(resolved_knowledge_results),
            "modelName": model_name,
            "structuredContext": serialize_value(structured_context) if structured_context else None,
            "nextActions": ["检查模型配置", "改用项目能力入口", "搜索知识库证据"],
            "groundingBoundary": "knowledge_base" if resolved_knowledge_results else "model_without_local_evidence",
        }

    return {
        **base_result,
        **routing_metadata,
        "intent": routed.get("intent", "clarify"),
        "title": base_result.get("title") or "研究助手回答",
        "summary": answer.strip(),
        "status": "complete",
        "verdict": base_result.get("verdict") or ("grounded" if resolved_knowledge_results else "limited"),
        "items": resolved_knowledge_results[:5],
        "knowledgeHitCount": len(resolved_knowledge_results),
        "modelName": model_name,
        "structuredContext": serialize_value(structured_context) if structured_context else None,
        "nextActions": base_result.get("nextActions") or ["继续追问", "解析更多 PDF 作为证据", "启动 research workflow"],
        "groundingBoundary": "model_plus_knowledge_base" if resolved_knowledge_results else "model_without_local_evidence",
    }


async def _chat_turn_llm_response(
    *,
    session_id: str,
    request: ResearchChatTurnRequest,
    routed: Dict[str, Any],
    structured_context: Optional[Dict[str, Any]] = None,
    knowledge_results: Optional[List[Dict[str, Any]]] = None,
    progress: Optional[ResearchChatProgressCallback] = None,
) -> Dict[str, Any]:
    result = await _research_chat_llm_result(
        message=request.message,
        context=request.context,
        routed=routed,
        structured_context=structured_context,
        knowledge_results=knowledge_results,
        progress=progress,
    )
    state = "needs_input" if result.get("status") in {"model_missing", "model_disabled"} else "complete"
    return _chat_turn_response(
        session_id=session_id,
        assistant_message={
            "kind": "result_summary",
            "text": result["summary"],
            "result": result,
            "suggestions": _chat_capabilities(),
        },
        state=state,
    )


def _hypothesis_grounding_summary(hypothesis_text: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    parsed_fulltext_count = sum(1 for item in results if item.get("source_reliability") == "parsed_fulltext")
    experimental_count = sum(1 for item in results if item.get("support_level") == "experimental_data")
    if not results:
        verdict = "ungrounded"
        summary = "没有在当前知识库中找到支撑片段。这只能作为 ungrounded model-generated proposal。"
    elif parsed_fulltext_count >= 2 or experimental_count >= 1:
        verdict = "grounded"
        summary = "当前知识库存在 parsed fulltext 或实验线索支撑，但仍需要人工检查可证伪实验和反证。"
    else:
        verdict = "limited"
        summary = "找到了一些候选片段，但 fulltext 或实验支撑不足，不能当作完整文献审查结论。"
    return {
        "title": "假设证据支撑检查",
        "summary": summary,
        "verdict": verdict,
        "hypothesisPreview": hypothesis_text[:500],
        "items": results[:6],
        "nextActions": [
            "解析更多 fulltext PDF",
            "抓取公开网页证据",
            "把假设拆成可证伪实验",
        ],
    }


def _build_evidence_verification_report(
    *,
    hypothesis_text: str,
    context: ResearchChatContext,
    external_packets: Optional[List[Dict[str, Any]]] = None,
    external_check: Optional[Dict[str, Any]] = None,
    store_report: bool = True,
) -> Dict[str, Any]:
    results = paper_parse_store.rag_search(
        hypothesis_text,
        limit=8,
        paper_id=context.paper_id,
        library_id=context.library_id,
    )
    run_record = load_run_record(context.run_id) if context.run_id else None
    run_evidence_links: List[Dict[str, Any]] = []
    run_evidence_retrievals: List[Dict[str, Any]] = []
    if context.run_id and run_record:
        run_evidence_links = knowledge_base.get_hypothesis_evidence_links(context.run_id)[:16]
        run_evidence_retrievals = knowledge_base.get_evidence_retrievals(context.run_id)[:16]
        knowledge_base.record_evidence_retrieval(
            run_id=context.run_id,
            tool_name="evidence.verification_agent.local_rag",
            query=hypothesis_text[:1200],
            limit_value=8,
            results=results,
        )

    report = evidence_verifier.verify(
        hypothesis_text=hypothesis_text,
        local_results=results,
        run_evidence_links=run_evidence_links,
        run_evidence_retrievals=run_evidence_retrievals,
        external_packets=external_packets or [],
        run_id=context.run_id if run_record else None,
        paper_id=context.paper_id,
        external_check=external_check,
    )
    report["query"] = hypothesis_text
    if context.run_id and run_record and store_report:
        result_ref = knowledge_base.store_tool_result(
            run_id=context.run_id,
            tool_name="evidence.verification_agent",
            phase="evidence_audit",
            content=report,
            result_kind="evidence_verification_report",
            summary=report.get("summary") or "Evidence verification report stored.",
        )
        knowledge_base.record_research_tool_call(
            run_id=context.run_id,
            tool_name="evidence.verification_agent",
            phase="evidence_audit",
            status="complete",
            arguments={
                "hypothesis_text": hypothesis_text[:700],
                "paper_id": context.paper_id,
                "external_check_status": (external_check or {}).get("status", "not_requested"),
            },
            result_summary=report.get("summary"),
            metadata={
                "result_ref": result_ref,
                "verdict": report.get("verdict"),
                "support_level": report.get("support_level"),
            },
            agent="evidence_verification_agent",
        )
        report["resultRef"] = result_ref
    return report


PUBLIC_LITERATURE_VERIFICATION_TOOLS = (
    "pubmed_fulltext",
    "arxiv_search",
    "google_scholar_search",
)


def _safe_literature_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return (slug[:80] or "hypothesis_verification").strip("_")


def _literature_verification_tool_arguments(
    *,
    tool_id: str,
    query: str,
    request: EvidenceVerificationWorkflowRequest,
) -> Dict[str, Any]:
    per_source_limit = max(1, min(int(request.max_papers or 5), 10))
    if tool_id == "pubmed_fulltext":
        return {
            "query": query,
            "slug": f"{_safe_literature_slug(request.hypothesis_text)[:48]}_{uuid.uuid4().hex[:8]}",
            "max_papers": per_source_limit,
            "recency_years": 0,
            "run_id": request.run_id,
        }
    if tool_id == "arxiv_search":
        return {
            "query": query,
            "max_results": per_source_limit,
        }
    if tool_id == "google_scholar_search":
        return {
            "query": query,
            "max_results": per_source_limit,
        }
    return {
        "query": query,
        "max_papers": per_source_limit,
    }


def _available_public_literature_tool_ids() -> List[str]:
    tool_registry = build_policy_limited_tool_registry()
    validation_tools = set(tool_registry.get_tools_for_workflow("validation"))
    return [tool_id for tool_id in PUBLIC_LITERATURE_VERIFICATION_TOOLS if tool_id in validation_tools]


async def execute_evidence_literature_verification_workflow(
    request: EvidenceVerificationWorkflowRequest,
) -> Dict[str, Any]:
    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="mcp.literature_review",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    context = ResearchChatContext(run_id=request.run_id, paper_id=request.paper_id, library_id=request.library_id)
    query = evidence_verifier.build_counter_evidence_query(request.hypothesis_text)
    local_report = _build_evidence_verification_report(
        hypothesis_text=request.hypothesis_text,
        context=context,
        store_report=False,
    )
    external_check: Dict[str, Any] = {
        "status": "running",
        "query": query,
        "mcpTool": "validation_public_literature",
        "sources": list(PUBLIC_LITERATURE_VERIFICATION_TOOLS),
        "approval": approval,
        "localVerdictBeforeExternalCheck": local_report.get("verdict"),
    }
    external_packets: List[Dict[str, Any]] = []
    mcp_payloads: List[Dict[str, Any]] = []
    source_statuses: List[Dict[str, Any]] = []
    try:
        tool_ids = _available_public_literature_tool_ids()
        if not tool_ids:
            raise HTTPException(
                status_code=424,
                detail={
                    "code": "no_public_literature_tools_available",
                    "message": "当前 validation workflow 没有可用的 PubMed、arXiv 或 Google Scholar 文献检索工具。",
                },
            )
        for tool_id in tool_ids:
            try:
                mcp_payload = await execute_mcp_tool_workflow(
                    McpToolWorkflowRequest(
                        workflow_name="validation",
                        tool_id=tool_id,
                        phase="literature_review",
                        arguments=_literature_verification_tool_arguments(
                            tool_id=tool_id,
                            query=query,
                            request=request,
                        ),
                        run_id=request.run_id,
                        approval=request.approval,
                    )
                )
                mcp_payloads.append(mcp_payload)
                external_packets.extend(
                    evidence_verifier.external_packets_from_mcp_payload(
                        payload=mcp_payload,
                        query=query,
                    )
                )
                source_statuses.append(
                    {
                        "toolId": tool_id,
                        "mcpToolName": mcp_payload.get("mcp_tool_name"),
                        "status": "complete",
                        "resultRef": mcp_payload.get("result_ref"),
                        "resultSize": mcp_payload.get("result_size"),
                    }
                )
            except HTTPException as source_exc:
                if source_exc.status_code == 428:
                    raise
                source_statuses.append(
                    {
                        "toolId": tool_id,
                        "status": "failed",
                        "summary": _safe_chat_error(source_exc),
                        "errorCode": source_exc.detail.get("code") if isinstance(source_exc.detail, dict) else None,
                    }
                )
        completed_payloads = [payload for payload in mcp_payloads if payload]
        if not completed_payloads:
            raise HTTPException(
                status_code=424,
                detail={
                    "code": "all_public_literature_sources_failed",
                    "message": "PubMed、arXiv 和 Google Scholar 文献检索都未成功完成。",
                    "source_statuses": source_statuses,
                },
            )
        external_check = {
            **external_check,
            "status": "complete",
            "summary": "外部文献/MCP 反证检查已按 validation policy 检索 PubMed、arXiv 和 Google Scholar；成功来源已作为候选 evidence packet 进入核验报告。",
            "resultRef": completed_payloads[0].get("result_ref"),
            "resultRefs": [payload.get("result_ref") for payload in completed_payloads if payload.get("result_ref")],
            "resultPreview": "\n\n".join(str(payload.get("result_preview") or "")[:700] for payload in completed_payloads)[:1600],
            "resultSize": sum(int(payload.get("result_size") or 0) for payload in completed_payloads),
            "mcpToolName": "validation_public_literature",
            "sourceStatuses": source_statuses,
        }
    except HTTPException as exc:
        if exc.status_code == 428:
            raise
        external_check = {
            **external_check,
            "status": "failed",
            "summary": _safe_chat_error(exc),
            "errorCode": exc.detail.get("code") if isinstance(exc.detail, dict) else None,
            "sourceStatuses": source_statuses or exc.detail.get("source_statuses") if isinstance(exc.detail, dict) else source_statuses,
        }

    final_report = _build_evidence_verification_report(
        hypothesis_text=request.hypothesis_text,
        context=context,
        external_packets=external_packets,
        external_check=external_check,
        store_report=True,
    )
    return {
        "tool_name": "evidence.verification_agent",
        "phase": "evidence_audit",
        "run_id": request.run_id,
        "paper_id": request.paper_id,
        "approval": approval,
        "query": query,
        "mcp_result_ref": (mcp_payloads[0] if mcp_payloads else {}).get("result_ref"),
        "mcp_result_refs": [payload.get("result_ref") for payload in mcp_payloads if payload.get("result_ref")],
        "verification_report": final_report,
        "result_ref": final_report.get("resultRef"),
    }


def resolve_pdf_input(pdf_path: str) -> Path:
    normalized = pdf_path.strip()
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme in {"http", "https"}:
        cache_dir = KB_ROOT / "pdf_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        basename = Path(urllib.parse.unquote(parsed.path)).name
        if not basename.lower().endswith(".pdf"):
            basename = f"paper_{uuid.uuid4().hex[:10]}.pdf"
        target = cache_dir / re.sub(r"[^a-zA-Z0-9._-]+", "_", basename)
        if not target.exists():
            response = requests.get(normalized, timeout=30)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and not response.content.startswith(b"%PDF"):
                raise ValueError("URL did not return a PDF document")
            target.write_bytes(response.content)
        return target
    return Path(normalized)


def safe_upload_filename(filename: str) -> str:
    name = Path(filename or "paper.pdf").name
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("._") or "paper.pdf"
    return safe if safe.lower().endswith(".pdf") else f"{safe}.pdf"


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _parse_evidence(
    *,
    parse_run_id: str,
    paper_id: Optional[str],
    item_key: str,
    evidence_type: str,
    label: str,
    file_path: Optional[str] = None,
    chunk_id: Optional[str] = None,
    section_path: Optional[List[str]] = None,
    text_preview: Optional[str] = None,
    media_preview: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    evidence_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "evidence_id": evidence_id or f"evidence_{uuid.uuid4().hex[:12]}",
        "parse_run_id": parse_run_id,
        "paper_id": paper_id,
        "item_key": item_key,
        "evidence_type": evidence_type,
        "label": label,
        "file_path": file_path,
        "chunk_id": chunk_id,
        "section_path": section_path or [],
        "text_preview": text_preview,
        "media_preview": media_preview,
        "metadata": metadata or {},
        "created_at": time.time(),
    }


def _parse_item(
    *,
    item_key: str,
    label: str,
    status: Literal["pending", "running", "success", "warning", "error"],
    evidence_type: str,
    evidence_summary: str,
    evidence_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "item_key": item_key,
        "label": label,
        "status": status,
        "evidence_type": evidence_type,
        "evidence_summary": evidence_summary,
        "evidence_id": evidence_id,
        "completed_at": time.time() if status in {"success", "warning", "error"} else None,
        "error_message": error_message,
    }


def parse_status_summary(parse_run: Dict[str, Any], *, database_path: Optional[str] = None) -> Dict[str, Any]:
    items = parse_run.get("items", [])
    total = len(items)
    completed = sum(1 for item in items if item.get("status") == "success")
    warning = sum(1 for item in items if item.get("status") == "warning")
    failed = [item for item in items if item.get("status") == "error"]
    rag_indexed_chunks_count = int(parse_run.get("chunks_count") or 0) if parse_run.get("rag_search_ready") else 0
    return {
        "total_items": total,
        "completed_items": completed,
        "warning_items": warning,
        "failed_items": [
            {
                "item_key": item.get("item_key"),
                "label": item.get("label"),
                "error_message": item.get("error_message") or item.get("evidence_summary"),
            }
            for item in failed
        ],
        "completion_rate": round(completed / total, 3) if total else 0,
        "rag_indexed_chunks_count": rag_indexed_chunks_count,
        "database_path": database_path or str(knowledge_base.db_path),
    }


def build_interpret_record_payload(
    *,
    parse_run_id: str,
    result: Any,
    paper_id: Optional[str],
    chunks: List[Any],
    output_name: str,
) -> Dict[str, Any]:
    evidence: List[Dict[str, Any]] = []
    experimental_chunks = [chunk for chunk in chunks if getattr(chunk, "experiment_data_summary", None)]

    def add_item(
        item_key: str,
        label: str,
        status: Literal["success", "warning", "error"],
        evidence_type: str,
        summary: str,
        *,
        file_path: Optional[str] = None,
        text_preview: Optional[str] = None,
        media_preview: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        evidence_id = f"evidence_{parse_run_id}_{item_key}"
        evidence.append(
            _parse_evidence(
                parse_run_id=parse_run_id,
                paper_id=paper_id,
                item_key=item_key,
                evidence_type=evidence_type,
                label=label,
                file_path=file_path,
                text_preview=text_preview,
                media_preview=media_preview,
                metadata=metadata,
                evidence_id=evidence_id,
            )
        )
        return _parse_item(
            item_key=item_key,
            label=label,
            status=status,
            evidence_type=evidence_type,
            evidence_summary=summary,
            evidence_id=evidence_id,
            error_message=error_message,
        )

    markdown_text = Path(result.markdown_path).read_text(encoding="utf-8") if Path(result.markdown_path).exists() else ""
    extracted_text = Path(result.extracted_text_path).read_text(encoding="utf-8") if Path(result.extracted_text_path).exists() else ""
    items = [
        add_item("pdf_accessible", "PDF 可访问", "success", "file", f"已读取 PDF：{result.pdf_path}", file_path=result.pdf_path),
        add_item(
            "metadata_extracted",
            "元数据抽取",
            "success",
            "metadata",
            f"官方元数据 plain text：{result.official_metadata_path}",
            file_path=result.official_metadata_path,
            metadata={"title": result.title, "doi": result.doi},
        ),
        add_item(
            "doi_detected",
            "DOI 识别",
            "success" if result.doi else "warning",
            "metadata",
            f"DOI：{result.doi}" if result.doi else "未识别 DOI。",
            metadata={"doi": result.doi},
        ),
        add_item(
            "bibtex_fetched",
            "BibTeX 获取",
            "success" if result.bibtex_path else "warning",
            "file",
            f"BibTeX 来源：{result.bibtex_source}" if result.bibtex_path else "未生成 BibTeX。",
            file_path=result.bibtex_path,
            metadata={"bibtex_source": result.bibtex_source},
        ),
        add_item(
            "official_metadata_plain_text",
            "官方元数据 plain text",
            "success",
            "file",
            f"已保存：{result.official_metadata_path}",
            file_path=result.official_metadata_path,
        ),
        add_item(
            "local_pdf_fulltext_extracted",
            "本地 PDF 全文抽取",
            "success" if extracted_text.strip() else "error",
            "file",
            f"已保存抽取全文：{result.extracted_text_path}",
            file_path=result.extracted_text_path,
            text_preview=extracted_text[:500],
            error_message=None if extracted_text.strip() else "PDF 未抽取到全文文本。",
        ),
        add_item(
            "chinese_structured_translation",
            "中文结构化译稿",
            "success" if markdown_text.strip() else "error",
            "file",
            f"已生成中文译稿：{result.markdown_path}",
            file_path=result.markdown_path,
            text_preview=markdown_text[:500],
            error_message=None if markdown_text.strip() else "中文译稿未生成。",
        ),
        add_item(
            "media_assets_rendered",
            "媒介截图",
            "success" if result.media_assets else "warning",
            "media",
            f"已保存 {len(result.media_assets)} 张媒介截图。",
            file_path=result.media_assets[0].path if result.media_assets else None,
            media_preview=result.media_assets[0].caption_preview if result.media_assets else None,
            metadata={"media_assets": [asset.__dict__ for asset in result.media_assets[:12]]},
        ),
        add_item(
            "markdown_image_links_checked",
            "Markdown 图片链接校验",
            "success" if not result.missing_image_links else "error",
            "file",
            f"checked {result.image_links_checked} image links; missing {len(result.missing_image_links)}.",
            file_path=result.markdown_path,
            metadata={"missing_image_links": result.missing_image_links},
            error_message="存在缺失图片链接。" if result.missing_image_links else None,
        ),
        add_item(
            "hierarchical_chunks_created",
            "层级知识切分",
            "success" if chunks else "error",
            "chunk",
            f"已生成 {len(chunks)} 个知识片段。",
            text_preview=chunks[0].text[:500] if chunks else None,
            error_message=None if chunks else "没有生成可检索 chunk。",
        ),
        add_item(
            "database_persisted",
            "数据库入库",
            "success" if paper_id else "error",
            "database",
            f"SQLite paper_id：{paper_id}" if paper_id else "未写入 SQLite。",
            metadata={"paper_id": paper_id, "output_name": output_name},
            error_message=None if paper_id else "论文解读结果未能写入数据库。",
        ),
        add_item(
            "rag_indexed",
            "RAG 索引入库",
            "success" if chunks else "error",
            "rag",
            f"FTS 索引可检索 chunk：{len(chunks)}。" if chunks else "没有可检索 chunk。",
            metadata={"chunks_count": len(chunks), "experimental_chunks_count": len(experimental_chunks)},
            error_message=None if chunks else "RAG 索引没有可调用证据。",
        ),
    ]
    for chunk in chunks:
        evidence.append(
            _parse_evidence(
                parse_run_id=parse_run_id,
                paper_id=paper_id,
                item_key="rag_indexed",
                evidence_type="chunk",
                label=chunk.title,
                chunk_id=chunk.chunk_id,
                section_path=chunk.section_path,
                text_preview=chunk.text[:500],
                metadata={
                    "support_level": chunk.support_level,
                    "section_type": chunk.section_type,
                    "experiment_data_summary": chunk.experiment_data_summary,
                },
                evidence_id=chunk.evidence_id,
            )
        )
    has_error = any(item["status"] == "error" for item in items)
    has_warning = any(item["status"] == "warning" for item in items)
    return {
        "status": "error" if has_error else ("warning" if has_warning else "success"),
        "items": items,
        "evidence": evidence,
        "experimental_chunks_count": len(experimental_chunks),
    }


def build_parse_record_payload(
    *,
    parse_run_id: str,
    parsed: Any,
    paper_id: Optional[str],
    chunks: List[Any],
    input_kind: Literal["upload", "local_path"],
    input_path: str,
    knowledge_base_ingested: bool,
) -> Dict[str, Any]:
    evidence: List[Dict[str, Any]] = []
    experimental_chunks = [chunk for chunk in chunks if getattr(chunk, "experiment_data_summary", None)]
    media_quality = summarize_media_region_quality([asset.__dict__ for asset in parsed.media_assets])

    def add_item(
        item_key: str,
        label: str,
        status: Literal["success", "warning", "error"],
        evidence_type: str,
        summary: str,
        *,
        file_path: Optional[str] = None,
        text_preview: Optional[str] = None,
        media_preview: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        evidence_id = f"evidence_{parse_run_id}_{item_key}"
        evidence.append(
            _parse_evidence(
                parse_run_id=parse_run_id,
                paper_id=paper_id,
                item_key=item_key,
                evidence_type=evidence_type,
                label=label,
                file_path=file_path,
                text_preview=text_preview,
                media_preview=media_preview,
                metadata=metadata,
                evidence_id=evidence_id,
            )
        )
        return _parse_item(
            item_key=item_key,
            label=label,
            status=status,
            evidence_type=evidence_type,
            evidence_summary=summary,
            evidence_id=evidence_id,
            error_message=error_message,
        )

    items = [
        add_item(
            "input_pdf_resolved",
            "PDF 输入已定位",
            "success",
            "file",
            f"已读取 PDF：{parsed.pdf_path}",
            file_path=parsed.pdf_path,
            metadata={"input_kind": input_kind, "input_path": input_path},
        ),
        add_item(
            "text_extracted",
            "全文文本已抽取",
            "success" if parsed.content.strip() else "error",
            "file",
            f"全文文本已保存：{parsed.extracted_text_path}",
            file_path=parsed.extracted_text_path,
            text_preview=parsed.content[:500],
            error_message=None if parsed.content.strip() else "PDF 没有可抽取文本。",
        ),
        add_item(
            "metadata_extracted",
            "元数据已保存",
            "success",
            "metadata",
            f"元数据 JSON：{parsed.metadata_json_path}",
            file_path=parsed.metadata_json_path,
            metadata={"metadata_text_path": parsed.metadata_text_path},
        ),
        add_item(
            "doi_detected",
            "DOI 已识别",
            "success" if parsed.doi else "warning",
            "metadata",
            f"DOI：{parsed.doi}" if parsed.doi else "未识别 DOI；不影响全文入库和 RAG 检索。",
            metadata={"doi": parsed.doi},
        ),
        add_item(
            "abstract_extracted",
            "摘要已提取",
            "success" if parsed.abstract else "warning",
            "metadata",
            "摘要已写入论文记录。" if parsed.abstract else "未定位摘要段；RAG 将使用全文 chunk。",
            text_preview=parsed.abstract[:500] if parsed.abstract else None,
        ),
        add_item(
            "bibtex_fetched",
            "BibTeX 已获取",
            "success" if parsed.bibtex_path else "warning",
            "file",
            f"BibTeX：{parsed.bibtex_path}" if parsed.bibtex_path else "未获取 BibTeX；不影响全文 chunk 入库。",
            file_path=parsed.bibtex_path,
        ),
        add_item(
            "media_assets_rendered",
            "图表截图已生成",
            "success" if parsed.media_assets else "warning",
            "media",
            (
                f"已保存 {media_quality['total']} 张截图；需复核 {media_quality['review']} 张；"
                f"高风险 {media_quality['high']} 张。"
            )
            if parsed.media_assets
            else "未检测到可截图的 Figure/Table/Algorithm caption；不影响文本 RAG。",
            file_path=parsed.media_assets[0].path if parsed.media_assets else None,
            media_preview=parsed.media_assets[0].caption_preview if parsed.media_assets else None,
            metadata={"media_assets": [asset.__dict__ for asset in parsed.media_assets[:12]]},
        ),
        add_item(
            "media_region_quality_checked",
            "图表区域质量已审计",
            "warning" if media_quality["review"] or media_quality["high"] or not parsed.media_assets else "success",
            "media",
            (
                f"图表区域审计完成：可信 {media_quality['ok']} 张，建议复核 {media_quality['review']} 张，高风险 {media_quality['high']} 张。"
                if parsed.media_assets
                else "未生成图表截图，无法进行图表区域审计；不影响全文 chunk RAG。"
            ),
            file_path=parsed.media_assets[0].path if parsed.media_assets else None,
            media_preview=parsed.media_assets[0].caption_preview if parsed.media_assets else None,
            metadata={
                "quality_summary": media_quality,
                "media_assets": [asset.__dict__ for asset in parsed.media_assets[:12]],
            },
        ),
        add_item(
            "hierarchical_chunks_created",
            "层级片段已生成",
            "success" if chunks else "error",
            "chunk",
            f"已生成 {len(chunks)} 个层级片段。",
            file_path=parsed.chunks_json_path,
            text_preview=chunks[0].text[:500] if chunks else None,
            error_message=None if chunks else "没有生成可检索 chunk。",
        ),
        add_item(
            "experiment_evidence_detected",
            "实验线索已检测",
            "success" if experimental_chunks else "warning",
            "chunk",
            f"检测到 {len(experimental_chunks)} 个含实验/评估线索的片段。"
            if experimental_chunks
            else "未发现明显实验线索；后续假设证据仍可检索全文 chunk。",
            text_preview=experimental_chunks[0].experiment_data_summary if experimental_chunks else None,
        ),
        add_item(
            "database_persisted",
            "数据库入库",
            "success" if knowledge_base_ingested and paper_id else "error",
            "database",
            f"论文记录已写入 SQLite：{paper_id}" if paper_id else "论文未写入知识库。",
            metadata={"paper_id": paper_id},
            error_message=None if paper_id else "ingest_to_knowledge_base=false 或写入失败。",
        ),
        add_item(
            "rag_indexed",
            "RAG 索引入库",
            "success" if knowledge_base_ingested and chunks else "error",
            "rag",
            "后续候选假设可通过知识库检索调用这些证据。"
            if knowledge_base_ingested and chunks
            else "缺少可检索 chunk，暂不能作为 RAG 证据调用。",
            metadata={"chunks_count": len(chunks), "experimental_chunks_count": len(experimental_chunks)},
        ),
    ]

    for chunk in chunks:
        evidence.append(
            _parse_evidence(
                parse_run_id=parse_run_id,
                paper_id=paper_id,
                item_key="rag_indexed",
                evidence_type="chunk",
                label=chunk.title,
                chunk_id=chunk.chunk_id,
                section_path=chunk.section_path,
                text_preview=chunk.text[:500],
                metadata={
                    "support_level": chunk.support_level,
                    "section_type": chunk.section_type,
                    "experiment_data_summary": chunk.experiment_data_summary,
                },
                evidence_id=chunk.evidence_id,
            )
        )

    for asset in parsed.media_assets:
        evidence.append(
            _parse_evidence(
                parse_run_id=parse_run_id,
                paper_id=paper_id,
                item_key="media_region_quality_checked",
                evidence_type="media",
                label=f"{asset.kind} p{asset.page}",
                file_path=asset.path,
                section_path=[],
                text_preview=None,
                media_preview=asset.caption_preview,
                metadata={
                    "asset_id": asset.asset_id,
                    "page": asset.page,
                    "rect": asset.rect,
                    "width": asset.width,
                    "height": asset.height,
                    "file_size_bytes": asset.file_size_bytes,
                    "confidence": asset.confidence,
                    "risk_level": asset.risk_level,
                    "risk_flags": asset.risk_flags,
                    "review_required": asset.review_required,
                },
                evidence_id=f"evidence_{parse_run_id}_{asset.asset_id}_quality",
            )
        )

    has_error = any(item["status"] == "error" for item in items)
    has_warning = any(item["status"] == "warning" for item in items)
    return {
        "status": "error" if has_error else ("warning" if has_warning else "success"),
        "items": items,
        "evidence": evidence,
        "experimental_chunks_count": len(experimental_chunks),
        "experimental_support_summaries": [
            {
                "chunk_id": chunk.chunk_id,
                "section_path": chunk.section_path,
                "summary": chunk.experiment_data_summary,
                "evidence_id": chunk.evidence_id,
            }
            for chunk in experimental_chunks[:5]
        ],
    }


async def parse_pdf_and_record(
    *,
    parse_run_id: str,
    pdf_path: Path,
    input_kind: Literal["upload", "local_path"],
    input_path: str,
    fetch_metadata: bool,
    ingest_to_knowledge_base: bool,
    library_id: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_library_id = knowledge_base.resolve_library_id(library_id)
    parsed = await asyncio.to_thread(
        parse_pdf_to_solve,
        pdf_path,
        fetch_metadata=fetch_metadata,
    )

    paper_id: Optional[str] = None
    chunks: List[Any] = []
    if ingest_to_knowledge_base:
        paper = knowledge_base.ingest(
            title=parsed.title,
            content=parsed.content,
            doi=parsed.doi,
            url=parsed.pdf_path,
            abstract=parsed.abstract,
            source="local_pdf",
            source_reliability="parsed_fulltext",
            metadata={
                "parse_run_id": parse_run_id,
                "pdf_path": parsed.pdf_path,
                "solve_dir": parsed.solve_dir,
                "metadata_json_path": parsed.metadata_json_path,
                "chunks_json_path": parsed.chunks_json_path,
                "media_assets": [asset.__dict__ for asset in parsed.media_assets],
                "library_id": resolved_library_id,
            },
            library_id=resolved_library_id,
        )
        paper_id = paper.paper_id
        chunks = paper.chunks

    payload = build_parse_record_payload(
        parse_run_id=parse_run_id,
        parsed=parsed,
        paper_id=paper_id,
        chunks=chunks,
        input_kind=input_kind,
        input_path=input_path,
        knowledge_base_ingested=ingest_to_knowledge_base,
    )
    embedding_index_status = (
        knowledge_base.index_embeddings_for_paper(paper_id)
        if paper_id
        else {"status": "skipped", "reason": "paper_not_ingested", "indexed_count": 0}
    )
    embedding_item_status: Literal["success", "warning", "error"] = (
        "success" if embedding_index_status.get("status") == "ready" else "warning"
    )
    embedding_evidence_id = f"evidence_{parse_run_id}_ragflow_embedding_indexed"
    embedding_summary = (
        f"RAGFlow-style embedding 已就绪：{embedding_index_status.get('indexed_count', 0)} 个 chunk。"
        if embedding_index_status.get("status") == "ready"
        else f"向量索引未启用或未完成：{embedding_index_status.get('reason') or embedding_index_status.get('error') or embedding_index_status.get('status')}；仍可使用 SQLite FTS/BM25 检索。"
    )
    payload["items"].append(
        _parse_item(
            item_key="ragflow_embedding_indexed",
            label="RAGFlow 向量索引",
            status=embedding_item_status,
            evidence_type="rag",
            evidence_summary=embedding_summary,
            evidence_id=embedding_evidence_id,
        )
    )
    payload["evidence"].append(
        _parse_evidence(
            parse_run_id=parse_run_id,
            paper_id=paper_id,
            item_key="ragflow_embedding_indexed",
            evidence_type="rag",
            label="RAGFlow 向量索引",
            metadata=embedding_index_status,
            evidence_id=embedding_evidence_id,
        )
    )
    if payload["status"] == "success" and embedding_item_status == "warning":
        payload["status"] = "warning"
    knowledge_base.record_parse_run(
        parse_run_id=parse_run_id,
        paper_id=paper_id,
        library_id=resolved_library_id,
        title=parsed.title,
        status=payload["status"],
        input_kind=input_kind,
        input_path=input_path,
        pdf_path=parsed.pdf_path,
        solve_dir=parsed.solve_dir,
        page_count=parsed.page_count,
        chunks_count=len(chunks),
        experimental_chunks_count=payload["experimental_chunks_count"],
        knowledge_base_ingested=ingest_to_knowledge_base and paper_id is not None,
        rag_search_ready=ingest_to_knowledge_base and bool(chunks),
        items=payload["items"],
        evidence=payload["evidence"],
    )
    parse_run = knowledge_base.get_parse_run(parse_run_id)
    summary_source = parse_run or {"items": payload["items"], "chunks_count": len(chunks), "rag_search_ready": ingest_to_knowledge_base and bool(chunks)}
    return {
        "parse_run_id": parse_run_id,
        "paper_id": paper_id,
        "library_id": resolved_library_id,
        "title": parsed.title,
        "doi": parsed.doi,
        "page_count": parsed.page_count,
        "solve_dir": parsed.solve_dir,
        "extracted_text_path": parsed.extracted_text_path,
        "metadata_json_path": parsed.metadata_json_path,
        "metadata_text_path": parsed.metadata_text_path,
        "chunks_json_path": parsed.chunks_json_path,
        "bibtex_path": parsed.bibtex_path,
        "media_assets": [asset.__dict__ for asset in parsed.media_assets],
        "chunks_count": len(chunks),
        "experimental_chunks_count": payload["experimental_chunks_count"],
        "experimental_support_summaries": payload["experimental_support_summaries"],
        "knowledge_base_ingested": ingest_to_knowledge_base and paper_id is not None,
        "source_reliability": "parsed_fulltext",
        "rag_search_ready": ingest_to_knowledge_base and bool(chunks),
        "status": payload["status"],
        "items": parse_run["items"] if parse_run else payload["items"],
        "parse_status_summary": parse_status_summary(summary_source),
        "rag_indexed_chunks_count": len(chunks) if ingest_to_knowledge_base and chunks else 0,
        "embedding_index_status": embedding_index_status,
        "ragflow": knowledge_base.ragflow_status(),
        "database_path": str(knowledge_base.db_path),
    }


def provider_for_model(model_name: str) -> Dict[str, Any]:
    """Return the provider key contract required by the selected LiteLLM model."""
    if (
        model_name.startswith("openai/mimo-")
        or model_name.startswith("mimo/")
        or model_name.startswith("xiaomi/")
    ):
        return {
            "provider": "mimo",
            "env_vars": ["MIMO_API_KEY", "XIAOMI_MIMO_API_KEY", "MIMOCODE_API_KEY"],
            "repair_hint": '$env:MIMO_API_KEY="your-key"',
        }
    if model_name.startswith("gemini/"):
        return {
            "provider": "gemini",
            "env_vars": ["GEMINI_API_KEY"],
            "repair_hint": '$env:GEMINI_API_KEY="your-key"',
        }
    if model_name.startswith("dashscope/"):
        return {
            "provider": "qwen_dashscope",
            "env_vars": ["DASHSCOPE_API_KEY", "QWEN_API_KEY"],
            "repair_hint": '$env:DASHSCOPE_API_KEY="your-key"',
        }
    if model_name.startswith("deepseek/"):
        return {
            "provider": "deepseek",
            "env_vars": ["DEEPSEEK_API_KEY"],
            "repair_hint": '$env:DEEPSEEK_API_KEY="your-key"',
        }
    if model_name.startswith("claude"):
        return {
            "provider": "anthropic",
            "env_vars": ["ANTHROPIC_API_KEY"],
            "repair_hint": '$env:ANTHROPIC_API_KEY="your-key"',
        }
    return {
        "provider": "openai",
        "env_vars": ["OPENAI_API_KEY"],
        "repair_hint": '$env:OPENAI_API_KEY="your-key"',
    }


def evaluate_safety_gate(research_goal: str) -> Dict[str, Any]:
    """Deterministic pre-run screen for adversarial or unsafe research goals."""
    normalized = research_goal.lower()
    blocked_terms = [
        "bioweapon",
        "weaponize",
        "pathogen enhancement",
        "gain of function",
        "explosive",
        "malware",
        "ransomware",
        "credential theft",
        "bypass authentication",
        "steal data",
        "制备武器",
        "武器化",
        "恶意软件",
        "勒索软件",
        "窃取凭据",
        "绕过认证",
    ]
    review_terms = [
        "dual-use",
        "human subjects",
        "clinical trial",
        "gene editing",
        "biosecurity",
        "adversarial",
        "网络攻击",
        "人体试验",
        "基因编辑",
        "生物安全",
        "对抗性",
    ]
    blocked_matches = [term for term in blocked_terms if term in normalized]
    review_matches = [term for term in review_terms if term in normalized]
    if blocked_matches:
        return {
            "status": "blocked",
            "reason": "Research goal matched unsafe or adversarial intent terms before workflow execution.",
            "matched_terms": blocked_matches,
            "requires_human_review": True,
        }
    return {
        "status": "needs_review" if review_matches else "passed",
        "reason": (
            "Research goal contains dual-use or regulated-domain language; results require expert review."
            if review_matches
            else "No blocked adversarial intent detected by the pre-run safety gate."
        ),
        "matched_terms": review_matches,
        "requires_human_review": bool(review_matches),
    }


def get_source_support_level(source: Any) -> str:
    if not isinstance(source, dict):
        return "metadata"
    text_fields = " ".join(str(source.get(key, "")) for key in ("fulltext", "full_text", "text", "abstract", "source_code"))
    if source.get("source_code") or "source_code" in str(source.get("type", "")):
        return "source-code"
    if source.get("fulltext") or source.get("full_text") or len(text_fields) > 1200:
        return "fulltext"
    if source.get("abstract") or source.get("summary"):
        return "abstract"
    if source.get("url") or source.get("title") or source.get("doi") or source.get("pmid"):
        return "metadata"
    return "unknown"


def get_source_reliability(source: Any) -> str:
    if not isinstance(source, dict):
        return "unknown"
    explicit = source.get("source_reliability")
    if explicit:
        return str(explicit)
    return reliability_for_source(str(source.get("source") or source.get("type") or ""))


def citation_keys_from_text(text: str) -> set[str]:
    import re

    return {match.group(1) for match in re.finditer(r"\[?([A-Z]\d+)\]?", text or "")}


def apply_citation_provenance_qa(record: RunRecord) -> None:
    hypothesis_reports: List[Dict[str, Any]] = []
    total_claimed = 0
    total_resolved = 0
    strongest_levels: set[str] = set()
    has_limited_support = False

    for index, hypothesis in enumerate(record.hypotheses):
        citation_map = hypothesis.get("citation_map") if isinstance(hypothesis, dict) else {}
        if not isinstance(citation_map, dict):
            citation_map = {}
        grounding = str(hypothesis.get("literature_grounding", "")) if isinstance(hypothesis, dict) else ""
        claimed = citation_keys_from_text(grounding)
        resolved = claimed.intersection(set(citation_map.keys()))
        orphaned = sorted(claimed.difference(set(citation_map.keys())))
        unused = sorted(set(citation_map.keys()).difference(claimed))
        support_levels = {
            key: get_source_support_level(value)
            for key, value in citation_map.items()
        }
        source_reliability = {
            key: get_source_reliability(value)
            for key, value in citation_map.items()
        }
        evidence_packet = hypothesis.get("evidence_packet") if isinstance(hypothesis, dict) else {}
        packet_items = evidence_packet.get("items") if isinstance(evidence_packet, dict) else []
        kb_support = (
            [item for item in packet_items if isinstance(item, dict)]
            if isinstance(packet_items, list) and packet_items
            else knowledge_base.support_for_hypothesis(
                hypothesis,
                limit=6,
                library_id=record.request.library_id,
            )
            if isinstance(hypothesis, dict)
            else []
        )
        experiment_summaries = [
            item
            for item in kb_support
            if item.get("experiment_data_summary")
        ]
        relationship_counts = {
            relationship: sum(
                1
                for item in kb_support
                if isinstance(item, dict) and item.get("relationship") == relationship
            )
            for relationship in ("support", "contradict", "irrelevant", "insufficient")
        }
        strongest_levels.update(support_levels.values())
        if experiment_summaries:
            strongest_levels.add("experimental_data")
        for key in resolved:
            if support_levels.get(key) in WEAK_SUPPORT_LEVELS:
                has_limited_support = True
            if source_reliability.get(key) in WEAK_SOURCE_RELIABILITY:
                has_limited_support = True
        total_claimed += len(claimed)
        total_resolved += len(resolved)

        if isinstance(hypothesis, dict):
            if not citation_map:
                has_limited_support = True
                hypothesis["grounding_status"] = "knowledge_base_supported" if kb_support else "ungrounded"
                hypothesis["literature_grounding"] = (
                    f"{grounding}\n\nGrounding limitation: no resolvable citation_map sources were returned."
                ).strip()
            elif relationship_counts["contradict"]:
                has_limited_support = True
                hypothesis["grounding_status"] = "contradicted"
            elif orphaned:
                has_limited_support = True
                hypothesis["grounding_status"] = "citation_mismatch"
            elif (
                "fulltext" not in support_levels.values()
                and "source-code" not in support_levels.values()
                and not experiment_summaries
            ):
                has_limited_support = True
                hypothesis["grounding_status"] = "limited_fulltext"
                hypothesis["literature_grounding"] = (
                    f"{grounding}\n\nGrounding limitation: available support is metadata/abstract-level, not fulltext-verified."
                ).strip()
            else:
                hypothesis["grounding_status"] = "provenance_checked"
            hypothesis["citation_support_levels"] = support_levels
            hypothesis["citation_source_reliability"] = source_reliability
            hypothesis["knowledge_base_support"] = kb_support
            hypothesis["experimental_support_summaries"] = experiment_summaries
            hypothesis["evidence_relationship_counts"] = relationship_counts

        hypothesis_reports.append(
            {
                "hypothesis_index": index,
                "claimed_citations": sorted(claimed),
                "resolved_citations": sorted(resolved),
                "orphaned_citations": orphaned,
                "unused_citation_map_keys": unused,
                "support_levels": support_levels,
                "source_reliability": source_reliability,
                "knowledge_base_support_count": len(kb_support),
                "experimental_support_count": len(experiment_summaries),
                "supporting_chunks": kb_support,
                "relationship_counts": relationship_counts,
            }
        )

    record.citation_provenance_qa = {
        "status": (
            "passed"
            if total_claimed == total_resolved and total_resolved > 0 and not has_limited_support
            else "limited"
        ),
        "claimed_citations": total_claimed,
        "resolved_citations": total_resolved,
        "support_levels_present": sorted(strongest_levels),
        "knowledge_base_documents": len(knowledge_base.list_documents()),
        "limitation_policy": (
            "Fulltext or experiment-data support is required for strong provenance. "
            "Abstract, metadata, and best-effort public HTML sources are marked as limited."
        ),
        "hypotheses": hypothesis_reports,
    }


def initialize_expert_feedback_state(record: RunRecord) -> None:
    record.expert_feedback = {
        "status": "awaiting_review",
        "applies_to": ["hypothesis_review", "ranking", "evolution"],
        "feedback_items": [],
        "next_iteration_policy": (
            "Human accept/reject/edit/prefer feedback is preserved here and must be "
            "folded into the next evolution or ranking pass before claiming a closed expert loop."
        ),
    }


def validate_ingest_metadata(metadata: Dict[str, Any]) -> None:
    if len(metadata) > 40:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "metadata_too_large",
                "message": "Paper metadata is too large for local ingest.",
            },
        )
    serialized = json.dumps(metadata, ensure_ascii=False)
    if len(serialized) > 20_000:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "metadata_too_large",
                "message": "Paper metadata is too large for local ingest.",
            },
        )

    def check_value(value: Any, depth: int = 0) -> bool:
        if depth > 1:
            return False
        if value is None or isinstance(value, (bool, int, float)):
            return True
        if isinstance(value, str):
            return len(value) <= 1_000
        if isinstance(value, list):
            return len(value) <= 20 and all(check_value(item, depth + 1) for item in value)
        if isinstance(value, dict):
            return len(value) <= 20 and all(
                isinstance(key, str)
                and len(key) <= 80
                and check_value(item, depth + 1)
                for key, item in value.items()
            )
        return False

    if not all(isinstance(key, str) and len(key) <= 80 and check_value(value) for key, value in metadata.items()):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "metadata_shape_unsupported",
                "message": "Paper metadata must be shallow and size-limited.",
            },
        )


def validate_ingest_authors(authors: List[str]) -> None:
    if any(len(author) > 160 for author in authors):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "authors_too_large",
                "message": "Author names are too large for local ingest.",
            },
        )


def normalize_provider_env() -> None:
    """Allow QWEN_API_KEY as a local alias for LiteLLM's DashScope key name."""
    if not os.getenv("DASHSCOPE_API_KEY") and os.getenv("QWEN_API_KEY"):
        os.environ["DASHSCOPE_API_KEY"] = os.environ["QWEN_API_KEY"]
    if not os.getenv("MIMO_API_KEY"):
        for alias in ("XIAOMI_MIMO_API_KEY", "MIMOCODE_API_KEY"):
            if os.getenv(alias):
                os.environ["MIMO_API_KEY"] = os.environ[alias]
                break


def has_provider_key(*names: str) -> bool:
    normalize_provider_env()
    return any(bool(os.getenv(name)) for name in names)


def has_model_provider_key(model_name: str) -> bool:
    provider = provider_for_model(model_name)
    return has_provider_key(*provider["env_vars"])


def probe_mcp_server() -> Dict[str, Any]:
    """Probe the literature MCP endpoint without requiring MCP client imports."""
    checked_at = time.time()
    parsed = urllib.parse.urlparse(MCP_SERVER_URL)
    host = parsed.hostname or "127.0.0.1"
    if host == "localhost":
        host = "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=0.2):
            pass
        return {
            "url": MCP_SERVER_URL,
            "available": True,
            "mode": "reachable",
            "reason": f"TCP {host}:{port} is accepting connections",
            "repair_hint": "Keep the Literature review toggle enabled only when this MCP server is reachable.",
            "checked_at": checked_at,
        }
    except Exception as exc:
        local_mcp = parsed.scheme in {"http", "https"} and host in {"127.0.0.1", "::1"} and port == 8888
        if MCP_AUTOSTART and local_mcp:
            runtime = start_literature_mcp_service()
            if runtime.get("running"):
                return {
                    "url": MCP_SERVER_URL,
                    "available": True,
                    "mode": "autostarted" if runtime.get("started") else "reachable",
                    "reason": "Local literature MCP service is running.",
                    "repair_hint": "Keep the Literature review toggle enabled when this status is available.",
                    "checked_at": time.time(),
                    "runtime": {
                        "pid": runtime.get("pid"),
                        "started": runtime.get("started"),
                        "stdout_log": runtime.get("stdout_log"),
                        "stderr_log": runtime.get("stderr_log"),
                    },
                }
            return {
                "url": MCP_SERVER_URL,
                "available": False,
                "mode": "autostart_failed",
                "reason": runtime.get("message") or str(exc),
                "repair_hint": runtime.get("stderr_log")
                or "From open-coscientist, run: uvicorn mcp_server.server:app --host 127.0.0.1 --port 8888",
                "checked_at": time.time(),
                "runtime": {
                    "pid": runtime.get("pid"),
                    "started": runtime.get("started"),
                    "stdout_log": runtime.get("stdout_log"),
                    "stderr_log": runtime.get("stderr_log"),
                },
            }
        return {
            "url": MCP_SERVER_URL,
            "available": False,
            "mode": "unreachable",
            "reason": str(exc),
            "repair_hint": "From open-coscientist, run: uvicorn mcp_server.server:app --host 0.0.0.0 --port 8888",
            "checked_at": checked_at,
        }


def research_tool_registry():
    return build_default_research_tool_registry(
        knowledge_base,
        mcp_probe=probe_mcp_server,
        ssh_training_probe=ssh_training_status,
    )


def default_live_workflow_tool_policy() -> Dict[str, Dict[str, Any]]:
    scholarly_source_types = [
        "academic",
        "preprint",
        "scholarly",
        "crossref",
        "pubmed",
        "arxiv",
    ]
    search_categories = ["search", "search_with_content", "read", "utility"]
    return {
        "literature_review": {
            "allowed_categories": search_categories,
            "allowed_source_types": scholarly_source_types,
            "denied_categories": ["action", "write", "messaging", "browser_control"],
        },
        "draft_generation": {
            "allowed_categories": ["search", "search_with_content"],
            "allowed_source_types": scholarly_source_types,
            "denied_categories": ["action", "write", "messaging", "browser_control"],
        },
        "validation": {
            "allowed_categories": ["search", "search_with_content"],
            "allowed_source_types": scholarly_source_types,
            "denied_categories": ["action", "write", "messaging", "browser_control"],
        },
        "reflection": {
            "allowed_categories": ["read", "utility", "search", "search_with_content"],
            "allowed_source_types": scholarly_source_types,
            "denied_categories": ["action", "write", "messaging", "browser_control"],
        },
    }


def build_policy_limited_tool_registry():
    from open_coscientist.config import ToolRegistry

    return ToolRegistry(workflow_tool_policy=default_live_workflow_tool_policy())


async def get_policy_limited_mcp_client(tool_registry: Any):
    from open_coscientist.mcp_client import get_mcp_client

    return await get_mcp_client(tool_registry=tool_registry, force_new=True)


async def call_delegation_llm(
    *,
    prompt: str,
    model_name: str,
    max_tokens: int,
    temperature: float,
) -> str:
    from open_coscientist.llm import call_llm

    return await call_llm(
        prompt=prompt,
        model_name=model_name,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def delegation_evidence_context(run_id: Optional[str], target_ref: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not run_id:
        return []
    links = knowledge_base.get_hypothesis_evidence_links(run_id)
    hypothesis_id = target_ref.get("hypothesis_id")
    hypothesis_index = target_ref.get("hypothesis_index")
    if hypothesis_id:
        links = [item for item in links if item.get("hypothesis_id") == hypothesis_id]
    if hypothesis_index is not None:
        links = [item for item in links if item.get("hypothesis_index") == hypothesis_index]
    return [
        {
            "evidence_id": item.get("evidence_id"),
            "paper_id": item.get("paper_id"),
            "support_level": item.get("support_level"),
            "source_reliability": item.get("source_reliability"),
            "evidence_summary": item.get("evidence_summary"),
            "text_preview": item.get("text_preview"),
        }
        for item in links[:8]
    ]


def build_delegation_agent_prompt(
    *,
    delegation: Dict[str, Any],
    agent: Dict[str, Any],
    run_record: Optional[RunRecord],
    evidence_context: List[Dict[str, Any]],
) -> str:
    skill_payloads = [
        skill
        for skill_id in agent.get("skill_ids", [])
        if (skill := get_research_skill(str(skill_id)))
    ]
    research_goal = run_record.request.research_goal if run_record else "No run research goal was provided."
    target_ref = {
        **(delegation.get("target_ref") or {}),
        **(agent.get("target_ref") or {}),
    }
    return (
        "You are executing one delegated scientific review role inside an AI co-scientist workbench.\n"
        "Do not invent citations, tool calls, or completed experiments. Use only the supplied target refs, "
        "evidence refs, and skill checklist. If evidence is insufficient, state the limitation and next task.\n\n"
        f"Research goal:\n{research_goal}\n\n"
        f"Delegation title: {delegation.get('title')}\n"
        f"Delegation strategy: {delegation.get('strategy')}\n"
        f"Phase: {delegation.get('phase')}\n"
        f"Target ref: {json.dumps(target_ref, ensure_ascii=False)}\n\n"
        f"Your role: {agent.get('role')}\n"
        f"Your brief: {agent.get('brief')}\n\n"
        f"Relevant skills:\n{json.dumps(skill_payloads, ensure_ascii=False, indent=2)}\n\n"
        f"Evidence context:\n{json.dumps(evidence_context, ensure_ascii=False, indent=2)}\n\n"
        "Return a concise structured Markdown report with these headings: Assessment, Evidence Used, "
        "Limitations, Failure Conditions, Next Action. Include confidence as a 0-1 number."
    )


async def execute_delegation_agent(
    *,
    delegation: Dict[str, Any],
    agent: Dict[str, Any],
    run_record: Optional[RunRecord],
    model_name: str,
    max_tokens: int,
    temperature: float,
) -> Dict[str, Any]:
    evidence_context = delegation_evidence_context(
        delegation.get("run_id"),
        {
            **(delegation.get("target_ref") or {}),
            **(agent.get("target_ref") or {}),
        },
    )
    prompt = build_delegation_agent_prompt(
        delegation=delegation,
        agent=agent,
        run_record=run_record,
        evidence_context=evidence_context,
    )
    output = await call_delegation_llm(
        prompt=prompt,
        model_name=model_name,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return {
        "role": agent.get("role"),
        "brief": agent.get("brief"),
        "skill_ids": agent.get("skill_ids", []),
        "target_ref": agent.get("target_ref", {}),
        "status": "completed",
        "output": output,
        "evidence_refs": [
            {
                "evidence_id": item.get("evidence_id"),
                "paper_id": item.get("paper_id"),
                "support_level": item.get("support_level"),
                "source_reliability": item.get("source_reliability"),
            }
            for item in evidence_context
        ],
    }


def build_mcp_tool_observer(run_id: str):
    def observe(event: Dict[str, Any]) -> None:
        tool_name = str(event.get("tool_name") or "unknown_mcp_tool")
        status = str(event.get("status") or "complete")
        phase = str(event.get("phase") or "mcp_internal")
        result_ref: Optional[Dict[str, Any]] = None
        if status == "complete":
            result_ref = knowledge_base.store_tool_result(
                run_id=run_id,
                tool_name=f"mcp.{tool_name}",
                phase=phase,
                content=event.get("result"),
                result_kind="mcp_tool_result",
                summary=f"MCP tool {tool_name} completed via {event.get('call_path', 'unknown')}.",
            )
        knowledge_base.record_research_tool_call(
            run_id=run_id,
            tool_name=f"mcp.{tool_name}",
            phase=phase,
            status=status,
            arguments=event.get("arguments") if isinstance(event.get("arguments"), dict) else {},
            result_summary=(
                f"MCP tool {tool_name} completed in {event.get('duration_seconds')}s."
                if status == "complete"
                else f"MCP tool {tool_name} failed: {event.get('error')}"
            ),
            metadata={
                key: value
                for key, value in event.items()
                if key not in {"result", "arguments"}
            }
            | {"result_ref": result_ref},
        )

    return observe


def evaluate_tool_execution_guardrail(
    *,
    run_id: Optional[str],
    tool_name: str,
    phase: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    if tool_name == "knowledge_base.rag_search":
        query = str(arguments.get("query") or arguments.get("q") or "").strip()
        if len(query) < 2:
            return {
                "allowed": False,
                "code": "empty_or_too_short_query",
                "message": "RAG 检索 query 过短，不能形成有效证据检索。",
            }
    if tool_name == "knowledge_base.support_for_hypothesis":
        hypothesis = arguments.get("hypothesis")
        if not isinstance(hypothesis, dict):
            return {
                "allowed": False,
                "code": "invalid_hypothesis_argument",
                "message": "Hypothesis support 检索需要结构化 hypothesis 对象。",
            }
        hypothesis_text = " ".join(
            str(hypothesis.get(key, ""))
            for key in ("text", "hypothesis", "technical_hypothesis", "explanation", "experiment")
        ).strip()
        if len(hypothesis_text) < 8:
            return {
                "allowed": False,
                "code": "hypothesis_text_too_short",
                "message": "Hypothesis 文本过短，不能形成可靠的证据检索 query。",
            }

    if run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=run_id,
            tool_name=tool_name,
            phase=phase,
            arguments=arguments,
        )
        if repeated >= 2:
            return {
                "allowed": False,
                "code": "repeated_identical_tool_call",
                "message": "同一 run、phase、tool 和参数已重复执行，guardrail 阻止继续消耗上下文和检索资源。",
                "repeat_count": repeated,
            }

    return {"allowed": True}


def require_tool_workflow_approval(
    approval: ToolWorkflowApproval,
    *,
    expected_scope: str,
) -> Dict[str, Any]:
    if not approval.confirmed or approval.scope != expected_scope:
        raise HTTPException(
            status_code=428,
            detail={
                "code": "tool_workflow_approval_required",
                "message": "这个工具会访问外部服务、写入本机文件或知识库，必须通过专用 workflow 显式确认。",
                "expected_scope": expected_scope,
            },
        )
    return {
        "confirmed": True,
        "scope": approval.scope,
        "reason": approval.reason,
        "checked_at": time.time(),
    }


def resolve_command_workflow_approval(
    approval: ToolWorkflowApproval,
    *,
    expected_scope: str,
    command: str,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    policy = get_command_permission_policy(KB_ROOT)
    risk = classify_command_risk(command)
    if not risk.get("allowed"):
        raise HTTPException(
            status_code=422,
            detail={
                "code": risk.get("code", "blocked_command"),
                "message": risk.get("message", "Command blocked by guardrail."),
                "command_risk": risk,
                "permission_policy": {key: value for key, value in policy.items() if key != "modes"},
            },
        )
    if command_requires_approval(policy, risk):
        resolved = require_tool_workflow_approval(approval, expected_scope=expected_scope)
        resolved["granted_by"] = "explicit_user_approval"
    else:
        resolved = {
            "confirmed": True,
            "scope": expected_scope,
            "reason": f"Auto-approved by command permission mode: {policy['mode']}",
            "checked_at": time.time(),
            "granted_by": "command_permission_mode",
        }
    resolved["permission_mode"] = policy["mode"]
    resolved["command_risk"] = risk
    return resolved, policy, risk


def public_mcp_status(status: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "available": bool(status.get("available")),
        "mode": status.get("mode", "unknown"),
        "reason": (
            "文献支撑服务可用于本次研究。"
            if status.get("available")
            else "文献支撑服务当前不可用，请在专家诊断中检查服务状态。"
        ),
        "checked_at": status.get("checked_at", time.time()),
    }


def _first_text_field(value: Dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        item = value.get(key)
        if item is None:
            continue
        if isinstance(item, list):
            joined = ", ".join(str(part).strip() for part in item[:8] if str(part).strip())
            if joined:
                return joined
        elif isinstance(item, (str, int, float)):
            text = str(item).strip()
            if text:
                return text
    return ""


DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def _normalize_doi(value: Optional[str]) -> str:
    if not value:
        return ""
    text = urllib.parse.unquote(str(value).strip())
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.I)
    text = re.sub(r"^doi:\s*", "", text, flags=re.I)
    match = DOI_PATTERN.search(text)
    return match.group(0).rstrip(".,;") if match else ""


def _doi_from_citation_request(request: LiteratureCitationRequest) -> str:
    for value in (request.doi, request.source_id, request.url, request.pdf_url):
        doi = _normalize_doi(value)
        if doi:
            return doi
    return ""


def _trusted_citation_candidates_for_doi(doi: str) -> List[Dict[str, Any]]:
    quoted_path = urllib.parse.quote(doi, safe="/")
    quoted_segment = urllib.parse.quote(doi, safe="")
    return [
        {
            "source": "doi_content_negotiation",
            "url": f"https://doi.org/{quoted_path}",
            "headers": {"Accept": "application/x-bibtex"},
            "description": "DOI content negotiation",
        },
        {
            "source": "crossref_transform",
            "url": f"https://api.crossref.org/works/{quoted_segment}/transform/application/x-bibtex",
            "headers": {"Accept": "application/x-bibtex"},
            "description": "Crossref transform",
        },
        {
            "source": "datacite_content_negotiation",
            "url": f"https://data.datacite.org/application/x-bibtex/{quoted_path}",
            "headers": {"Accept": "application/x-bibtex"},
            "description": "DataCite content negotiation",
        },
    ]


def _fetch_trusted_bibtex_for_doi(doi: str) -> Dict[str, Any]:
    attempts: List[Dict[str, Any]] = []
    for candidate in _trusted_citation_candidates_for_doi(doi):
        try:
            response = requests.get(
                candidate["url"],
                headers={
                    **candidate["headers"],
                    "User-Agent": "open-coscientist-local-workbench/0.1",
                },
                timeout=15,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            attempts.append({"source": candidate["source"], "status": "network_error", "message": str(exc)[:160]})
            continue
        text = response.text.strip()
        attempts.append({"source": candidate["source"], "status": response.status_code})
        if response.ok and text.startswith("@") and "{" in text:
            return {
                "available": True,
                "source": candidate["source"],
                "source_label": candidate["description"],
                "source_url": candidate["url"],
                "bibtex": text if text.endswith("\n") else f"{text}\n",
                "attempts": attempts,
            }
    return {"available": False, "attempts": attempts}


def _coerce_mcp_result_payload(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return {"text": stripped}
    return value


def _iter_candidate_dicts(value: Any) -> List[Dict[str, Any]]:
    payload = _coerce_mcp_result_payload(value)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("results", "papers", "items", "documents", "entries"):
        nested = payload.get(key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if isinstance(nested, dict):
            return [item for item in nested.values() if isinstance(item, dict)]
    dict_values = [item for item in payload.values() if isinstance(item, dict)]
    if dict_values and any("title" in item for item in dict_values):
        return dict_values
    return [payload] if "title" in payload else []


def _normalize_pdf_url(value: str) -> Optional[str]:
    url = value.strip()
    if not url:
        return None
    if url.lower().endswith(".pdf") or "/pdf/" in url.lower():
        return url
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.endswith("arxiv.org") and "/abs/" in parsed.path:
        arxiv_id = parsed.path.rsplit("/abs/", 1)[-1].strip("/")
        if arxiv_id:
            return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return None


def _candidate_pdf_url(item: Dict[str, Any]) -> Optional[str]:
    for key in ("pdf_url", "pdf", "pdfUrl", "download_url", "downloadUrl"):
        value = item.get(key)
        if isinstance(value, str):
            normalized = _normalize_pdf_url(value)
            if normalized:
                return normalized
    for key in ("pdf_links", "pdfLinks"):
        value = item.get(key)
        if isinstance(value, list):
            for candidate in value:
                if isinstance(candidate, str):
                    normalized = _normalize_pdf_url(candidate)
                    if normalized:
                        return normalized
                if isinstance(candidate, dict):
                    normalized = _normalize_pdf_url(_first_text_field(candidate, ("url", "href", "pdf_url")))
                    if normalized:
                        return normalized
    url = _first_text_field(item, ("url", "source_url", "landing_url", "link"))
    return _normalize_pdf_url(url)


def _literature_candidate_from_item(item: Dict[str, Any], *, tool_id: str, index: int) -> Optional[Dict[str, Any]]:
    title = _first_text_field(item, ("title", "name"))
    if not title:
        return None
    url = _first_text_field(item, ("url", "source_url", "landing_url", "link"))
    pdf_url = _candidate_pdf_url(item)
    doi = _first_text_field(item, ("doi", "DOI"))
    arxiv_id = _first_text_field(item, ("arxiv_id", "arxivId", "arxiv"))
    source_id = _first_text_field(item, ("arxiv_id", "pmid", "pmc_id", "doi", "source_id", "id", "key"))
    if not doi and source_id.lower().startswith("10."):
        doi = source_id
    if not arxiv_id and "arxiv" in tool_id and source_id:
        arxiv_id = source_id
    source = _first_text_field(item, ("source", "venue", "primary_category")) or ("arxiv" if "arxiv" in tool_id else "pubmed")
    abstract = _first_text_field(item, ("abstract", "summary", "description"))
    authors = _first_text_field(item, ("authors", "author"))
    year = _first_text_field(item, ("year", "published", "date", "date_revised"))
    can_parse = bool(pdf_url)
    download_method = (
        "可直接下载 PDF 并解析入库"
        if can_parse
        else "只有论文落地页；可先抓取网页证据或手动补充 PDF URL"
        if url
        else "仅有元数据；需要研究员补充可访问地址"
    )
    return {
        "candidate_id": f"candidate_{tool_id}_{index}",
        "title": title[:300],
        "authors": authors,
        "year": year,
        "source": source,
        "source_id": source_id,
        "doi": doi or None,
        "arxiv_id": arxiv_id or None,
        "abstract": abstract[:1200],
        "url": url or pdf_url,
        "pdf_url": pdf_url,
        "download_method": download_method,
        "can_parse_pdf": can_parse,
        "status": "ready_to_parse" if can_parse else ("landing_page_only" if url else "metadata_only"),
        "tool_id": tool_id,
    }


def _literature_candidates_from_mcp_result(value: Any, *, tool_id: str, max_results: int) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for index, item in enumerate(_iter_candidate_dicts(value), start=1):
        candidate = _literature_candidate_from_item(item, tool_id=tool_id, index=index)
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= max_results:
            break
    return candidates


def _collect_pdf_urls_from_value(value: Any) -> List[str]:
    urls: List[str] = []
    seen: set[str] = set()

    def add_url(candidate: Any) -> None:
        if not isinstance(candidate, str):
            return
        for match in re.findall(r"https?://[^\s\"'<>]+", candidate):
            normalized = _normalize_pdf_url(match.rstrip(").,;]"))
            if normalized and normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)
        normalized = _normalize_pdf_url(candidate)
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)

    def walk(node: Any) -> None:
        if isinstance(node, str):
            add_url(node)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if isinstance(node, dict):
            for key in ("pdf_url", "pdf", "download_url", "url", "href"):
                add_url(node.get(key))
            for key in ("pdf_urls", "pdf_links", "links", "results", "items", "candidates"):
                if key in node:
                    walk(node.get(key))
            return

    walk(_coerce_mcp_result_payload(value))
    return urls


async def _discover_pdf_links_for_candidates(
    *,
    client: Any,
    tool_registry: Any,
    candidates: List[Dict[str, Any]],
    source_statuses: List[Dict[str, Any]],
    max_pages: int,
) -> List[Dict[str, Any]]:
    find_tool = tool_registry.get_tool("find_pdf_links")
    if not find_tool or max_pages <= 0:
        return []
    discovery_results: List[Dict[str, Any]] = []
    attempted = 0
    for candidate in candidates:
        if candidate.get("pdf_url") or not candidate.get("url"):
            continue
        attempted += 1
        if attempted > max_pages:
            break
        url = str(candidate.get("url") or "")
        try:
            raw_result = await client.call_tool(find_tool.mcp_tool_name, url=url)
            pdf_urls = _collect_pdf_urls_from_value(raw_result)
        except Exception as exc:
            discovery_results.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "url": url,
                    "status": "failed",
                    "message": str(exc)[:200],
                    "pdf_url": None,
                }
            )
            continue
        if pdf_urls:
            candidate["pdf_url"] = pdf_urls[0]
            candidate["can_parse_pdf"] = True
            candidate["status"] = "ready_to_parse"
            candidate["download_method"] = "已从论文落地页发现 PDF，可直接解析入库"
            candidate["pdf_discovery"] = {
                "status": "ready",
                "tool_id": "find_pdf_links",
                "mcp_tool_name": find_tool.mcp_tool_name,
                "pdf_urls": pdf_urls[:5],
            }
            discovery_results.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "url": url,
                    "status": "ready",
                    "pdf_url": pdf_urls[0],
                    "count": len(pdf_urls),
                }
            )
        else:
            candidate["pdf_discovery"] = {
                "status": "limited",
                "tool_id": "find_pdf_links",
                "mcp_tool_name": find_tool.mcp_tool_name,
                "pdf_urls": [],
            }
            discovery_results.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "url": url,
                    "status": "limited",
                    "pdf_url": None,
                    "count": 0,
                }
            )
    if discovery_results:
        ready_count = sum(1 for item in discovery_results if item.get("status") == "ready")
        source_statuses.append(
            {
                "tool_id": "find_pdf_links",
                "mcp_tool_name": find_tool.mcp_tool_name,
                "display_name": find_tool.display_name,
                "status": "ready" if ready_count else "limited",
                "message": f"已为 {len(discovery_results)} 个落地页查找 PDF，发现 {ready_count} 个可解析链接。",
            }
        )
    return discovery_results


async def _auto_ingest_discovered_pdfs(
    *,
    candidates: List[Dict[str, Any]],
    library_id: str,
    limit: int,
) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    results: List[Dict[str, Any]] = []
    for candidate in candidates:
        if len(results) >= limit:
            break
        pdf_url = str(candidate.get("pdf_url") or "").strip()
        if not pdf_url:
            continue
        ingest_result: Dict[str, Any] = {
            "candidate_id": candidate.get("candidate_id"),
            "title": candidate.get("title"),
            "pdf_url": pdf_url,
            "status": "pending",
        }
        try:
            resolved_pdf = await asyncio.to_thread(resolve_pdf_input, pdf_url)
            parse_run_id = f"parse_{uuid.uuid4().hex[:12]}"
            payload = await parse_pdf_and_record(
                parse_run_id=parse_run_id,
                pdf_path=resolved_pdf,
                input_kind="local_path",
                input_path=pdf_url,
                fetch_metadata=True,
                ingest_to_knowledge_base=True,
                library_id=library_id,
            )
            ingest_result.update(
                {
                    "status": "ingested" if payload.get("knowledge_base_ingested") else "limited",
                    "paper_id": payload.get("paper_id"),
                    "parse_run_id": payload.get("parse_run_id"),
                    "chunks_count": payload.get("chunks_count"),
                    "rag_search_ready": payload.get("rag_search_ready"),
                }
            )
        except Exception as exc:
            ingest_result.update({"status": "failed", "message": str(exc)[:240]})
        candidate["auto_ingest"] = ingest_result
        results.append(ingest_result)
    return results


def _preferred_literature_tools(query: str, preferred_source: str) -> List[str]:
    if preferred_source == "arxiv":
        return ["arxiv_search"]
    if preferred_source == "pubmed":
        return ["pubmed_fulltext"]
    if preferred_source == "scholar":
        return ["google_scholar_search"]
    if preferred_source == "all":
        return ["pubmed_fulltext", "arxiv_search", "google_scholar_search"]
    biomedical_terms = ("cell", "gene", "protein", "cancer", "clinical", "patient", "drug", "disease", "biomarker")
    return ["pubmed_fulltext"] if any(term in query.lower() for term in biomedical_terms) else ["arxiv_search"]


def _default_discovery_model_name() -> str:
    configured = os.getenv("COSCIENTIST_LITERATURE_DISCOVERY_MODEL")
    if configured:
        return configured
    chat_model = os.getenv("COSCIENTIST_RESEARCH_CHAT_MODEL")
    if chat_model:
        return _discovery_planner_model_name(chat_model)
    if has_provider_key("MIMO_API_KEY", "XIAOMI_MIMO_API_KEY", "MIMOCODE_API_KEY"):
        return "openai/mimo-v2.5"
    if has_provider_key("DEEPSEEK_API_KEY"):
        return "deepseek/deepseek-chat"
    if has_provider_key("DASHSCOPE_API_KEY", "QWEN_API_KEY"):
        return "dashscope/qwen-plus"
    if has_provider_key("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    if has_provider_key("GEMINI_API_KEY"):
        return "gemini/gemini-1.5-flash"
    if has_provider_key("ANTHROPIC_API_KEY"):
        return "claude-3-5-haiku-20241022"
    return "deepseek/deepseek-v4-pro"


def _discovery_planner_model_name(model_name: str) -> str:
    if model_name.startswith("deepseek/") and model_name != "deepseek/deepseek-chat":
        return "deepseek/deepseek-chat"
    return model_name


def _literature_tool_scope_for_source(preferred_source: str) -> List[str]:
    if preferred_source == "arxiv":
        return ["arxiv_search"]
    if preferred_source == "pubmed":
        return ["pubmed_fulltext"]
    if preferred_source == "scholar":
        return ["google_scholar_search"]
    return ["arxiv_search", "pubmed_fulltext", "google_scholar_search"]


def _extract_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.S)
        if not match:
            raise
        value = json.loads(match.group(0))
    return value if isinstance(value, dict) else {}


def _rules_literature_discovery_plan(query: str, preferred_source: str, *, reason: str) -> Dict[str, Any]:
    tool_ids = _preferred_literature_tools(query, preferred_source)
    return {
        "mode": "rules",
        "model_name": None,
        "intent_summary": query,
        "reason": reason,
        "tool_queries": [
            {
                "tool_id": tool_id,
                "query": query,
                "rationale": "规则回退：按用户选择的来源或基础领域关键词选择检索工具。",
            }
            for tool_id in tool_ids
        ],
        "fallback_used": True,
    }


def _normalize_literature_discovery_plan(
    plan: Dict[str, Any],
    *,
    query: str,
    preferred_source: str,
    model_name: str,
) -> Dict[str, Any]:
    allowed_tools = set(_literature_tool_scope_for_source(preferred_source))
    raw_tool_queries = plan.get("tool_queries")
    if not isinstance(raw_tool_queries, list):
        raw_tool_queries = []

    normalized_queries: List[Dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for item in raw_tool_queries:
        if not isinstance(item, dict):
            continue
        tool_id = str(item.get("tool_id") or "").strip()
        if tool_id not in allowed_tools:
            continue
        planned_query = str(item.get("query") or query).strip()
        if not planned_query:
            planned_query = query
        pair = (tool_id, planned_query.lower())
        if pair in seen_pairs:
            continue
        normalized_queries.append(
            {
                "tool_id": tool_id,
                "query": planned_query[:500],
                "rationale": str(item.get("rationale") or "模型建议该来源适合当前研究主题。")[:500],
            }
        )
        seen_pairs.add(pair)

    if not normalized_queries:
        return _rules_literature_discovery_plan(
            query,
            preferred_source,
            reason="模型没有返回可执行的文献检索计划，已回退到规则检索。",
        )

    return {
        "mode": "llm",
        "model_name": model_name,
        "intent_summary": str(plan.get("intent_summary") or query)[:800],
        "reason": str(plan.get("reason") or "模型已根据研究主题生成检索计划。")[:800],
        "domain": str(plan.get("domain") or "unknown")[:120],
        "tool_queries": normalized_queries[:5],
        "fallback_used": False,
    }


async def _plan_literature_discovery(
    *,
    query: str,
    preferred_source: str,
    max_results: int,
    planning_mode: str,
    model_name: Optional[str],
) -> Dict[str, Any]:
    if planning_mode == "rules":
        return _rules_literature_discovery_plan(query, preferred_source, reason="用户选择规则检索模式。")

    selected_model = _discovery_planner_model_name(model_name) if model_name else _default_discovery_model_name()
    if not has_model_provider_key(selected_model):
        return _rules_literature_discovery_plan(
            query,
            preferred_source,
            reason=f"未配置 {selected_model} 的模型 key，已回退到规则检索。",
        )

    source_hint = {
        "auto": "模型可以选择 arxiv_search、pubmed_fulltext、google_scholar_search，并可为同一来源生成多个互补 query。",
        "all": "用户要求覆盖全部公开来源，模型应为 arxiv_search、pubmed_fulltext、google_scholar_search 分别生成互补 query。",
        "arxiv": "用户明确选择 arXiv，只能使用 arxiv_search，但可以生成多个 arXiv query。",
        "pubmed": "用户明确选择 PubMed，只能使用 pubmed_fulltext，但可以生成多个 PubMed query。",
        "scholar": "用户明确选择 Scholar，只能使用 google_scholar_search，但可以生成多个 Scholar query。",
    }.get(preferred_source, "模型可以选择合适的公开文献来源。")
    allowed_tools = ", ".join(_literature_tool_scope_for_source(preferred_source))
    prompt = f"""
你是科研文献检索规划器。你的任务不是回答研究问题，而是把用户的自然语言研究主题转成可执行的 MCP 文献检索计划。

用户主题：
{query}

用户选择的来源模式：{preferred_source}
来源约束：{source_hint}
允许的 tool_id：{allowed_tools}
最大候选数：{max_results}

请输出严格 JSON，不要 Markdown，不要解释文本。Schema：
{{
  "intent_summary": "用中文总结用户真正想找的论文方向",
  "domain": "computer_vision | machine_learning | biomedicine | interdisciplinary | other",
  "reason": "为什么这样选来源和改写 query",
  "tool_queries": [
    {{
      "tool_id": "arxiv_search | pubmed_fulltext | google_scholar_search",
      "query": "适合该来源的英文检索式，必要时保留关键中文名词",
      "rationale": "为什么这个来源和 query 合适"
    }}
  ]
}}

规划规则：
- 视觉、图像、音频驱动数字人、生成模型、CV/ML 主题优先 arxiv_search，可加 google_scholar_search 扩展。
- 如果主题是音频驱动数字人/说话人脸/虚拟人生成，至少覆盖这些互补方向中的 3 个：talking head generation、lip sync、audio-driven avatar、speech-driven facial animation、talking face diffusion model、neural rendering talking head。
- 生物医学、临床、药物、基因、疾病主题优先 pubmed_fulltext。
- 宽泛中文主题必须改写为具体英文关键词，避免只搜索原句。
- 不要输出未在允许列表中的 tool_id。
- tool_queries 输出 3-5 条；同一个 tool_id 可以出现多次，但 query 必须互补。
""".strip()

    try:
        raw = await call_research_chat_planner_llm(prompt=prompt, model_name=selected_model)
        return _normalize_literature_discovery_plan(
            _extract_json_object(raw),
            query=query,
            preferred_source=preferred_source,
            model_name=selected_model,
        )
    except Exception as exc:
        return _rules_literature_discovery_plan(
            query,
            preferred_source,
            reason=f"模型检索规划失败，已回退到规则检索：{str(exc)[:160]}",
        )


def _discovery_tool_arguments(tool_id: str, query: str, max_results: int, library_id: str) -> Dict[str, Any]:
    if tool_id == "arxiv_search":
        return {"query": query, "max_results": max_results}
    if tool_id == "google_scholar_search":
        return {"query": query, "max_results": max_results}
    if tool_id == "pubmed_fulltext":
        return {
            "query": query,
            "slug": f"library_{library_id}_{uuid.uuid4().hex[:8]}",
            "max_papers": max_results,
            "recency_years": 0,
        }
    return {"query": query, "max_papers": max_results}


def public_provider_status(
    configured: bool,
    *,
    mode: str,
    reason_ready: str,
    reason_missing: str,
    verified: bool = False,
) -> Dict[str, Any]:
    return {
        "configured": configured,
        "usable": configured,
        "mode": mode if configured else "missing",
        "reason": reason_ready if configured else reason_missing,
        "checked_at": time.time(),
        "verified": verified,
    }


async def build_health_payload(*, debug: bool = False) -> Dict[str, Any]:
    gemini_key = has_provider_key("GEMINI_API_KEY")
    openai_key = has_provider_key("OPENAI_API_KEY")
    anthropic_key = has_provider_key("ANTHROPIC_API_KEY")
    deepseek_key = has_provider_key("DEEPSEEK_API_KEY")
    dashscope_key = has_provider_key("DASHSCOPE_API_KEY", "QWEN_API_KEY")
    mimo_key = has_provider_key("MIMO_API_KEY", "XIAOMI_MIMO_API_KEY", "MIMOCODE_API_KEY")

    mcp_status = await asyncio.to_thread(probe_mcp_server)
    public_payload: Dict[str, Any] = {
        "status": "ok",
        "run_timeout_seconds": RUN_TIMEOUT_SECONDS,
        "literature_mcp": public_mcp_status(mcp_status),
        "has_gemini_key": gemini_key,
        "has_openai_key": openai_key,
        "has_anthropic_key": anthropic_key,
        "has_deepseek_key": deepseek_key,
        "has_dashscope_key": dashscope_key,
        "has_mimo_key": mimo_key,
        "has_local_agent_key": True,
        "local_agent_provider": "local-simulation",
        "ragflow_knowledge": knowledge_base.ragflow_status(),
        "providers": {
            "local": public_provider_status(
                True,
                mode="demo_synthetic",
                reason_ready="本地演示模拟可用于产品流程检查，不能作为科学证据。",
                reason_missing="本地演示模拟不可用。",
                verified=True,
            ),
            "gemini": public_provider_status(
                gemini_key,
                mode="configured_not_called",
                reason_ready="Gemini 实时模型通道已具备调用条件。",
                reason_missing="Gemini 实时模型通道尚未配置。",
            ),
            "openai": public_provider_status(
                openai_key,
                mode="configured_not_called",
                reason_ready="OpenAI 实时模型通道已具备调用条件。",
                reason_missing="OpenAI 实时模型通道尚未配置。",
            ),
            "anthropic": public_provider_status(
                anthropic_key,
                mode="configured_not_called",
                reason_ready="Anthropic 实时模型通道已具备调用条件。",
                reason_missing="Anthropic 实时模型通道尚未配置。",
            ),
            "deepseek": public_provider_status(
                deepseek_key,
                mode="configured_not_called",
                reason_ready="DeepSeek 实时模型通道已具备调用条件。",
                reason_missing="DeepSeek 实时模型通道尚未配置。",
            ),
            "qwen_dashscope": public_provider_status(
                dashscope_key,
                mode="configured_not_called",
                reason_ready="Qwen 实时模型通道已具备调用条件。",
                reason_missing="Qwen 实时模型通道尚未配置。",
            ),
            "mimo": public_provider_status(
                mimo_key,
                mode="configured_not_called",
                reason_ready="MiMo 实时模型通道已具备调用条件。",
                reason_missing="MiMo 实时模型通道尚未配置。",
            ),
        },
    }
    if not debug:
        return public_payload

    startup_command = (
        '[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); '
        '$OutputEncoding = [System.Text.UTF8Encoding]::new(); npm run api'
    )
    public_payload.update(
        {
            "api_endpoint": "http://127.0.0.1:8787",
            "startup": {
                "powershell_utf8_command": startup_command,
                "working_directory": str(ROOT / "webapp"),
            },
            "literature_mcp": mcp_status,
            "providers": {
                "local": {
                    "configured": True,
                    "usable": True,
                    "mode": "demo_synthetic",
                    "reason": "Built-in local agent simulation; no external secret required.",
                    "repair_hint": "Use this mode for a first walkthrough. Do not treat synthetic grounding as scientific evidence.",
                    "verified": True,
                    "checked_at": time.time(),
                },
                "gemini": {
                    "configured": gemini_key,
                    "usable": gemini_key,
                    "mode": "configured_not_called" if gemini_key else "missing",
                    "reason": "Environment variable GEMINI_API_KEY",
                    "repair_hint": '$env:GEMINI_API_KEY="your-key"',
                    "verified": False,
                    "checked_at": time.time(),
                },
                "openai": {
                    "configured": openai_key,
                    "usable": openai_key,
                    "mode": "configured_not_called" if openai_key else "missing",
                    "reason": "Environment variable OPENAI_API_KEY",
                    "repair_hint": '$env:OPENAI_API_KEY="your-key"',
                    "verified": False,
                    "checked_at": time.time(),
                },
                "anthropic": {
                    "configured": anthropic_key,
                    "usable": anthropic_key,
                    "mode": "configured_not_called" if anthropic_key else "missing",
                    "reason": "Environment variable ANTHROPIC_API_KEY",
                    "repair_hint": '$env:ANTHROPIC_API_KEY="your-key"',
                    "verified": False,
                    "checked_at": time.time(),
                },
                "deepseek": {
                    "configured": deepseek_key,
                    "usable": deepseek_key,
                    "mode": "configured_not_called" if deepseek_key else "missing",
                    "reason": "Environment variable DEEPSEEK_API_KEY",
                    "repair_hint": '$env:DEEPSEEK_API_KEY="your-key"',
                    "verified": False,
                    "checked_at": time.time(),
                },
                "qwen_dashscope": {
                    "configured": dashscope_key,
                    "usable": dashscope_key,
                    "mode": "configured_not_called" if dashscope_key else "missing",
                    "reason": "Environment variable DASHSCOPE_API_KEY; QWEN_API_KEY is normalized as an alias.",
                    "repair_hint": '$env:DASHSCOPE_API_KEY="your-key"',
                    "verified": False,
                    "checked_at": time.time(),
                },
                "mimo": {
                    "configured": mimo_key,
                    "usable": mimo_key,
                    "mode": "configured_not_called" if mimo_key else "missing",
                    "reason": "Environment variable MIMO_API_KEY; XIAOMI_MIMO_API_KEY and MIMOCODE_API_KEY are accepted as aliases.",
                    "repair_hint": '$env:MIMO_API_KEY="your-key"',
                    "verified": False,
                    "checked_at": time.time(),
                },
            },
        }
    )
    return public_payload


def now_label() -> str:
    return time.strftime("%H:%M:%S")


def serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        return serialize_value(value.model_dump())
    if hasattr(value, "dict"):
        return serialize_value(value.dict())
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {
            key: serialize_value(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return str(value)


def run_record_payload(record: RunRecord) -> Dict[str, Any]:
    return serialize_value(record)


_PRIVATE_PATH_KEYS = {
    "database_path",
    "evidence_path",
    "file_path",
    "input_path",
    "pdf_path",
    "solve_dir",
    "script_path",
    "workdir",
    "run_dir",
}

_PRIVATE_COMMAND_KEYS = {"command", "raw_command"}


def _is_local_path(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.match(r"^(?:[a-zA-Z]:[\\/]|\\\\|/)", value.strip()))


def _public_snapshot_value(value: Any, *, key: str = "") -> Any:
    """Remove machine-local paths from the public workbench facade."""
    if key.lower() in _PRIVATE_PATH_KEYS:
        return None
    if key.lower() in _PRIVATE_COMMAND_KEYS:
        return "[redacted command]" if value else value
    if isinstance(value, dict):
        return {
            str(child_key): _public_snapshot_value(child_value, key=str(child_key))
            for child_key, child_value in value.items()
            if str(child_key).lower() not in _PRIVATE_PATH_KEYS
        }
    if isinstance(value, list):
        return [_public_snapshot_value(item, key=key) for item in value]
    if key.lower() == "url" and _is_local_path(value):
        return None
    return value


def _public_paper_summary(paper: Any) -> Dict[str, Any]:
    return {
        "paper_id": paper.paper_id,
        "library_id": paper.library_id,
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "doi": paper.doi,
        "url": None if _is_local_path(paper.url) else paper.url,
        "source": paper.source,
        "source_reliability": paper.source_reliability,
        "parse_run_id": paper.parse_run_id,
        "chunks_count": len(paper.chunks),
        "section_types": sorted({chunk.section_type for chunk in paper.chunks}),
        "experimental_chunks_count": sum(
            1 for chunk in paper.chunks if chunk.experiment_data_summary
        ),
        "created_at": paper.created_at,
        "source_ref": f"paper:{paper.paper_id}",
    }


def _public_run_summary(record: RunRecord) -> Dict[str, Any]:
    return {
        "run_id": record.run_id,
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "research_goal": record.request.research_goal,
        "model_name": record.request.model_name,
        "demo_mode": record.request.demo_mode,
        "literature_review": record.request.literature_review,
        "hypothesis_count": len(record.hypotheses),
        "evidence_count": sum(
            len(hypothesis.get("citation_map") or {})
            for hypothesis in record.hypotheses
            if isinstance(hypothesis, dict)
        ),
        "error": record.error,
    }


def _run_recovery_summary(record: RunRecord) -> Dict[str, Any]:
    error = (record.error or "").lower()
    if "json" in error or "parse llm" in error:
        return {
            "category": "structured_output",
            "summary": "模型结构化输出没有通过解析或 schema 校验。建议减少候选数、降低上下文长度或切换到更稳定的模型。",
            "retryable": True,
            "next_actions": ["retry_run", "reduce_hypotheses", "switch_model", "inspect_phase_trace"],
        }
    if any(token in error for token in ("timeout", "timed out", "exceeded")):
        return {
            "category": "timeout",
            "summary": "后台运行超过等待窗口。建议先检查 worker 和 provider，再以较小规模重新运行。",
            "retryable": True,
            "next_actions": ["inspect_worker", "reduce_iterations", "retry_run"],
        }
    if any(token in error for token in ("decompression", "connection", "ssl", "gateway", "remote protocol")):
        return {
            "category": "transport",
            "summary": "模型或文献服务传输异常。建议检查网络/provider 状态后重试。",
            "retryable": True,
            "next_actions": ["check_provider", "check_literature_service", "retry_run"],
        }
    return {
        "category": "unknown" if record.status == "error" else "none",
        "summary": "当前运行没有可归类的失败原因。请打开过程记录检查最后一个 phase。"
        if record.status == "error"
        else "当前运行没有失败。",
        "retryable": record.status == "error",
        "next_actions": ["inspect_phase_trace", "retry_run"] if record.status == "error" else [],
    }


def _short_prompt_text(value: Any, limit: int = 420) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def memory_context_prompt_constraints(memory_context: Dict[str, Any]) -> List[str]:
    constraints: List[str] = []
    parent_run = memory_context.get("parent_run")
    if isinstance(parent_run, dict):
        goal = _short_prompt_text(parent_run.get("research_goal"), 220)
        summary = _short_prompt_text(parent_run.get("summary"), 360)
        constraints.append(
            "[memory_parent_run] "
            f"Prior run status={parent_run.get('status') or 'unknown'}; "
            f"hypothesis_count={parent_run.get('hypothesis_count') or 0}; "
            f"goal={goal or 'not summarized'}; summary={summary or 'not summarized'}."
        )

    for hypothesis in memory_context.get("prior_hypotheses") or []:
        if not isinstance(hypothesis, dict):
            continue
        text = _short_prompt_text(hypothesis.get("text"), 360)
        explanation = _short_prompt_text(hypothesis.get("explanation"), 220)
        support = _short_prompt_text(hypothesis.get("support_level"), 80) or "unknown"
        if text:
            constraints.append(
                "[memory_prior_hypothesis] "
                f"{text}; support={support}; explanation={explanation or 'not summarized'}."
            )

    for feedback in memory_context.get("user_feedback") or []:
        if not isinstance(feedback, dict):
            continue
        text = _short_prompt_text(feedback.get("text"), 360)
        if text:
            constraints.append(
                "[memory_user_feedback] "
                f"type={feedback.get('feedback_type') or 'unspecified'}; "
                f"target={feedback.get('target_type') or 'run'}; feedback={text}."
            )

    for evidence in memory_context.get("evidence_summaries") or []:
        if not isinstance(evidence, dict):
            continue
        title = _short_prompt_text(evidence.get("title"), 180) or "untitled source"
        reliability = _short_prompt_text(evidence.get("source_reliability"), 80) or "unknown"
        support = _short_prompt_text(evidence.get("support_level"), 80) or "unknown"
        snippet = _short_prompt_text(evidence.get("snippet"), 420)
        if snippet:
            constraints.append(
                "[memory_evidence_summary] "
                f"title={title}; reliability={reliability}; support={support}; snippet={snippet}."
            )

    if constraints:
        constraints.append(
            "[memory_usage_policy] Use these memory entries as summary-only guidance. "
            "Do not treat them as scientific evidence unless source reliability and support level justify it."
        )
    return constraints[:18]


def run_request_feedback_prompt_constraints(feedback_items: List[FeedbackItem]) -> List[str]:
    constraints: List[str] = []
    for feedback in feedback_items:
        text = _short_prompt_text(feedback.text, 360)
        if not text:
            continue
        constraints.append(
            "[user_feedback] "
            f"type={feedback.feedback_type}; target={feedback.target_type}; feedback={text}."
        )
    if constraints:
        constraints.append(
            "[user_feedback_policy] Use user feedback as guidance for this run or continuation. "
            "Do not present it as an immediate reversible edit to an already completed result."
        )
    return constraints[:12]


def memory_context_user_summary(memory_context: Dict[str, Any]) -> Dict[str, Any]:
    parent_run = memory_context.get("parent_run") if isinstance(memory_context.get("parent_run"), dict) else None
    prior_hypotheses = memory_context.get("prior_hypotheses") if isinstance(memory_context.get("prior_hypotheses"), list) else []
    user_feedback = memory_context.get("user_feedback") if isinstance(memory_context.get("user_feedback"), list) else []
    evidence_summaries = (
        memory_context.get("evidence_summaries")
        if isinstance(memory_context.get("evidence_summaries"), list)
        else []
    )
    related_runs = memory_context.get("related_runs") if isinstance(memory_context.get("related_runs"), list) else []
    known_gaps = memory_context.get("known_gaps") if isinstance(memory_context.get("known_gaps"), list) else []
    source_types: List[str] = []
    evidence_library_ids = {
        str(item.get("library_id"))
        for item in evidence_summaries
        if isinstance(item, dict) and item.get("library_id")
    }
    if parent_run:
        source_types.append("parent_run")
    if prior_hypotheses:
        source_types.append("prior_hypotheses")
    if user_feedback:
        source_types.append("chat_feedback")
    if evidence_summaries:
        source_types.append("knowledge_base")
    if related_runs:
        source_types.append("related_runs")
    if known_gaps:
        source_types.append("memory_limitations")

    sections: List[Dict[str, Any]] = []
    if parent_run:
        sections.append(
            {
                "type": "parent_run",
                "title": "Parent run",
                "summary": _short_prompt_text(
                    parent_run.get("summary") or parent_run.get("research_goal") or "Parent run context available.",
                    260,
                ),
                "count": 1,
            }
        )
    if prior_hypotheses:
        sections.append(
            {
                "type": "prior_hypotheses",
                "title": "Prior hypotheses",
                "summary": f"{len(prior_hypotheses)} prior hypothesis summaries are available.",
                "count": len(prior_hypotheses),
            }
        )
    if user_feedback:
        sections.append(
            {
                "type": "chat_feedback",
                "title": "User feedback",
                "summary": f"{len(user_feedback)} feedback item(s) are available for the next run.",
                "count": len(user_feedback),
            }
        )
    if evidence_summaries:
        reliability_counts: Dict[str, int] = {}
        support_counts: Dict[str, int] = {}
        for item in evidence_summaries:
            if not isinstance(item, dict):
                continue
            reliability = str(item.get("source_reliability") or "unknown")
            support = str(item.get("support_level") or "unknown")
            reliability_counts[reliability] = reliability_counts.get(reliability, 0) + 1
            support_counts[support] = support_counts.get(support, 0) + 1
        sections.append(
            {
                "type": "knowledge_base",
                "title": "Evidence memory",
                "summary": f"{len(evidence_summaries)} knowledge-base evidence summary item(s) matched this run.",
                "count": len(evidence_summaries),
                "library_count": len(evidence_library_ids),
                "source_reliability_counts": reliability_counts,
                "support_level_counts": support_counts,
            }
        )
    if known_gaps:
        summarized_gaps = [
            _short_prompt_text(gap, 180)
            for gap in known_gaps[:5]
            if _short_prompt_text(gap, 180)
        ]
        sections.append(
            {
                "type": "memory_limitations",
                "title": "Memory limitations",
                "summary": f"{len(known_gaps)} memory limitation(s) apply to this run.",
                "count": len(known_gaps),
                "items": summarized_gaps,
            }
        )

    return {
        "memory_scope": memory_context.get("memory_scope"),
        "source_types": source_types,
        "has_parent_run": bool(parent_run),
        "parent_run_id": parent_run.get("run_id") if parent_run else None,
        "prior_hypotheses_count": len(prior_hypotheses),
        "user_feedback_count": len(user_feedback),
        "evidence_summary_count": len(evidence_summaries),
        "evidence_library_count": len(evidence_library_ids),
        "related_run_count": len(related_runs),
        "known_gaps_count": len(known_gaps),
        "sections": sections,
        "boundary": (
            "Summary-only memory view for UI disclosure. Raw chat messages, raw records, "
            "internal paths, and raw JSON are not included."
        ),
    }


def include_current_run_feedback_in_memory(
    memory_context: Dict[str, Any],
    *,
    run_id: str,
    parent_run_id: Optional[str],
) -> None:
    if not parent_run_id or parent_run_id == run_id:
        return
    existing_ids = {
        str(item.get("feedback_id"))
        for item in memory_context.get("user_feedback", [])
        if isinstance(item, dict) and item.get("feedback_id")
    }
    current_feedback = [
        item
        for item in knowledge_base.list_feedback_items(run_id=run_id, limit=20)
        if str(item.get("feedback_id")) not in existing_ids
    ]
    if current_feedback:
        memory_context.setdefault("user_feedback", []).extend(current_feedback)


def persist_run_record(record: RunRecord) -> None:
    try:
        knowledge_base.record_research_run(run_record_payload(record))
    except Exception as exc:
        print(f"Research run persistence failed for {record.run_id}: {exc}", file=sys.stderr)


def persist_run_checkpoint_metadata(
    record: RunRecord,
    *,
    status: str,
    phase: str,
    checkpoint_ref: Optional[str] = None,
    checkpoint_backend: str = "sqlite_metadata",
    checkpoint_id: Optional[str] = None,
    state_summary: Optional[Dict[str, Any]] = None,
) -> None:
    summary = state_summary or {
        "run_status": status,
        "record_status": record.status,
        "timeline_count": len(record.timeline),
        "hypothesis_count": len(record.hypotheses),
        "error": record.error,
        "boundary": "Execution metadata index only; LangGraph state saver is not enabled.",
    }
    try:
        knowledge_base.persist_checkpoint_metadata(
            checkpoint_id=checkpoint_id or f"{record.run_id}:{status}:{phase}",
            run_id=record.run_id,
            thread_id=record.run_id,
            status=status,
            phase=phase,
            checkpoint_backend=checkpoint_backend,
            checkpoint_ref=checkpoint_ref,
            state_summary=summary,
        )
    except Exception as exc:
        print(f"Research checkpoint metadata failed for {record.run_id}: {exc}", file=sys.stderr)


def is_stale_run_state(status: str, updated_at: Any) -> bool:
    if status not in {"queued", "running"}:
        return False
    try:
        updated = float(updated_at or 0)
    except (TypeError, ValueError):
        updated = 0.0
    return updated > 0 and (time.time() - updated) > STALE_RUN_GRACE_SECONDS


def stale_run_error_message() -> str:
    return (
        "Run did not report completion before the backend timeout window. "
        "It may have failed during model JSON parsing or the backend may have restarted; please rerun from Workspace."
    )


def has_active_run_work_item(run_id: str) -> bool:
    try:
        items = knowledge_base.list_work_items(
            run_id=run_id,
            workflow_name="workflow.open_coscientist_run",
            limit=5,
        )
    except Exception:
        return False
    return any(item.get("status") in {"queued", "leased", "running", "retrying", "blocked"} for item in items)


def mark_stale_run_record(record: RunRecord) -> RunRecord:
    if not is_stale_run_state(record.status, record.updated_at):
        return record
    if has_active_run_work_item(record.run_id):
        record.metrics["stale_recovery_deferred_to_queue"] = True
        return record
    original_updated_at = record.updated_at
    record.status = "error"
    record.error = record.error or stale_run_error_message()
    record.timeline.append(
        TimelineEvent(
            time=now_label(),
            stage="Timeout",
            event="Stale run recovered",
            details="The persisted run was still queued/running after the timeout window, so it was marked as failed for UI recovery.",
            status="error",
        )
    )
    record.metrics["stale_recovered"] = True
    record.metrics["timeout_seconds"] = RUN_TIMEOUT_SECONDS
    record.updated_at = original_updated_at
    persist_run_record(record)
    return record


def normalize_run_summary_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if is_stale_run_state(str(payload.get("status") or ""), payload.get("updated_at")):
        run_id = str(payload.get("run_id") or "")
        record = load_run_record(run_id) if run_id else None
        if record:
            payload = run_record_payload(record)
        else:
            payload = dict(payload)
            payload["status"] = "error"
            payload["error"] = payload.get("error") or stale_run_error_message()
    return payload


def load_run_record(run_id: str) -> Optional[RunRecord]:
    if run_id in runs:
        return mark_stale_run_record(runs[run_id])
    payload = knowledge_base.get_research_run(run_id)
    if not payload:
        return None
    record = RunRecord(**payload)
    record = mark_stale_run_record(record)
    runs[run_id] = record
    return record


def add_event(
    record: RunRecord,
    stage: str,
    event: str,
    details: str,
    status: Literal["queued", "active", "complete", "error"] = "complete",
) -> None:
    record.timeline.append(
        TimelineEvent(
            time=now_label(),
            stage=stage,
            event=event,
            details=details,
            status=status,
        )
    )
    record.updated_at = time.time()
    persist_run_record(record)


def slug_label(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value)
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or "phase"


AGENT_TRACE_PHASE_ALIASES = {
    "literature": "literature_review",
    "literature_review": "literature_review",
    "lit_review": "literature_review",
    "generate": "generate",
    "generation": "generate",
    "review": "review",
    "rank": "ranking",
    "ranking": "ranking",
    "meta": "meta_review",
    "meta_review": "meta_review",
    "evolution": "evolve",
    "evolve": "evolve",
    "proximity": "proximity",
    "reflection": "reflection",
    "supervisor": "supervisor",
    "planning": "supervisor",
}

AGENT_TRACE_STABLE_PHASE_ORDER = [
    "supervisor",
    "literature_review",
    "generate",
    "reflection",
    "review",
    "ranking",
    "meta_review",
    "evolve",
    "proximity",
]

AGENT_TRACE_PHASE_LABELS = {
    "supervisor": "Research planning",
    "literature_review": "Literature grounding",
    "generate": "Hypothesis generation",
    "reflection": "Reflection and gap analysis",
    "review": "Scientific review",
    "ranking": "Tournament ranking",
    "meta_review": "Meta-review synthesis",
    "evolve": "Hypothesis evolution",
    "proximity": "Diversity and deduplication",
}


def registry_agent_for_phase(phase: str) -> Optional[Dict[str, Any]]:
    canonical_phase = AGENT_TRACE_PHASE_ALIASES.get(str(phase).lower(), str(phase).lower())
    try:
        from open_coscientist.agents.registry import list_agent_specs

        for spec in list_agent_specs(public=True):
            if spec.get("phase") == canonical_phase:
                return spec
    except Exception:
        return None
    return None


def agent_trace_from_registry(**kwargs: Any) -> AgentTrace:
    phase = str(kwargs.get("phase") or "")
    spec = registry_agent_for_phase(phase)
    if spec:
        kwargs.setdefault("agent_id", spec.get("agent_id"))
        kwargs.setdefault("prompt_template", spec.get("prompt_template"))
        kwargs.setdefault("role", spec.get("role") or "Specialized research agent")
        if kwargs.get("degradation_reason") is None:
            kwargs["degradation_reason"] = None
    return AgentTrace(**kwargs)


def canonical_trace_phase(phase: Any) -> str:
    normalized = str(phase or "").lower()
    return AGENT_TRACE_PHASE_ALIASES.get(normalized, normalized or "unknown")


def trace_phase_label(phase: Any) -> str:
    canonical_phase = canonical_trace_phase(phase)
    return AGENT_TRACE_PHASE_LABELS.get(canonical_phase, canonical_phase.replace("_", " ").title())


def agent_trace_user_summary(traces: List[AgentTrace]) -> Dict[str, Any]:
    seen_phases = {canonical_trace_phase(trace.phase) for trace in traces}
    ordered_phases = [phase for phase in AGENT_TRACE_STABLE_PHASE_ORDER if phase in seen_phases]
    ordered_phases.extend(sorted(phase for phase in seen_phases if phase not in set(ordered_phases)))
    degraded = [
        {
            "phase": canonical_trace_phase(trace.phase),
            "label": trace_phase_label(trace.phase),
            "agent_id": trace.agent_id,
            "degradation_reason": trace.degradation_reason,
        }
        for trace in traces
        if trace.degradation_reason
    ]
    return {
        "trace_count": len(traces),
        "phase_order": ordered_phases,
        "phase_labels": [{"phase": phase, "label": trace_phase_label(phase)} for phase in ordered_phases],
        "degraded_phases": degraded,
        "degradation_count": len(degraded),
        "boundary": (
            "Phase order is a user-facing summary. Full trace entries remain available for expert audit; "
            "raw provider payloads and prompts are not exposed here."
        ),
    }


def extract_trace_metadata(message: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Any] = [
        message.get("metadata"),
        message.get("additional_kwargs", {}).get("metadata")
        if isinstance(message.get("additional_kwargs"), dict)
        else None,
        message.get("kwargs", {}).get("metadata") if isinstance(message.get("kwargs"), dict) else None,
        message.get("kwargs", {}).get("additional_kwargs", {}).get("metadata")
        if isinstance(message.get("kwargs"), dict)
        and isinstance(message.get("kwargs", {}).get("additional_kwargs"), dict)
        else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return {}


def build_live_agent_trace(record: RunRecord, result: Dict[str, Any]) -> List[AgentTrace]:
    traces: List[AgentTrace] = []
    messages = serialize_value(result.get("messages", []))

    disabled_literature_trace = (
        agent_trace_from_registry(
            agent="Literature Grounding",
            role="Live workflow phase",
            event_id="trace-live-literature-disabled",
            phase="literature_review",
            status="complete",
            synthetic=False,
            output=(
                "Literature review was disabled for this run. Hypothesis generation may use "
                "model priors, user-provided context, and retrieved memory summaries, but this "
                "trace is not evidence that an external literature grounding phase executed."
            ),
            tool_calls=[],
            token_usage={},
            confidence=1.0,
            degradation_reason="literature_review_disabled_latent_knowledge_boundary",
        )
        if not record.request.literature_review
        else None
    )

    if isinstance(messages, list):
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue

            metadata = extract_trace_metadata(message)
            phase = str(
                metadata.get("phase")
                or message.get("name")
                or message.get("role")
                or f"message-{index + 1}"
            )
            output = serialize_value(message.get("content", ""))
            output_text = output if isinstance(output, str) else str(output)

            if not output_text.strip():
                continue

            traces.append(
                agent_trace_from_registry(
                    agent=phase.replace("_", " ").title(),
                    role="Live LangGraph node",
                    event_id=f"trace-live-message-{index + 1}-{slug_label(phase)}",
                    phase=phase,
                    synthetic=False,
                    output=output_text,
                    tool_calls=[],
                    token_usage={},
                    confidence=1.0,
                )
            )

    if traces:
        if disabled_literature_trace and not any(trace.phase == "literature_review" for trace in traces):
            traces.append(disabled_literature_trace)
        return traces

    for index, event in enumerate(record.timeline):
        status = event.status
        if record.status == "complete" and status == "active":
            status = "complete"

        traces.append(
            agent_trace_from_registry(
                agent=event.stage,
                role="Live workflow phase",
                event_id=f"trace-live-event-{index + 1}-{slug_label(event.stage)}",
                phase=slug_label(event.stage).replace("-", "_"),
                status=status,
                synthetic=False,
                output=f"{event.event}: {event.details}",
                tool_calls=[],
                token_usage={},
                confidence=1.0 if status != "error" else 0.0,
            )
        )

    if disabled_literature_trace and not any(trace.phase == "literature_review" for trace in traces):
        traces.append(disabled_literature_trace)

    return traces or [
        agent_trace_from_registry(
            agent="Open Coscientist",
            role="Live workflow",
            event_id="trace-live-workflow",
            phase="complete",
            synthetic=False,
            output="Live model workflow completed through HypothesisGenerator.",
            confidence=1.0,
        )
    ]


def _normalize_hypothesis_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _hypothesis_origin_for(record: RunRecord, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
    explicit_origin = hypothesis.get("origin") or hypothesis.get("source_origin") or hypothesis.get("hypothesis_origin")
    if explicit_origin in {"user_seeded", "model_generated", "evolved", "tool_generated"}:
        return {"origin": explicit_origin, "origin_label": explicit_origin.replace("_", " ")}

    text = _normalize_hypothesis_text(_hypothesis_text(hypothesis))
    seed_texts = {
        _normalize_hypothesis_text(seed)
        for seed in record.request.starting_hypotheses
        if str(seed).strip()
    }
    if text and any(text == seed or seed in text or text in seed for seed in seed_texts):
        return {
            "origin": "user_seeded",
            "origin_label": "user seeded",
            "origin_evidence": "matched starting_hypotheses",
        }

    generation_method = str(hypothesis.get("generation_method") or hypothesis.get("method") or "").lower()
    evolution_markers = ("evolved", "evolution", "mutation", "refinement", "revised")
    if any(marker in generation_method for marker in evolution_markers) or hypothesis.get("evolution_history"):
        return {
            "origin": "evolved",
            "origin_label": "evolved",
            "origin_evidence": "generation_method/evolution_history",
        }

    tool_markers = ("tool", "mcp", "literature", "retrieval")
    if any(marker in generation_method for marker in tool_markers) or hypothesis.get("tool_calls"):
        return {
            "origin": "tool_generated",
            "origin_label": "tool grounded",
            "origin_evidence": "generation_method/tool_calls",
        }

    return {
        "origin": "model_generated",
        "origin_label": "model generated",
        "origin_evidence": "default_model_generation",
    }


def annotate_hypothesis_origins(record: RunRecord) -> None:
    annotated: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    for index, hypothesis in enumerate(record.hypotheses):
        if not isinstance(hypothesis, dict):
            annotated.append(hypothesis)
            continue
        origin = _hypothesis_origin_for(record, hypothesis)
        merged = {
            **hypothesis,
            "hypothesis_id": str(
                hypothesis.get("hypothesis_id")
                or hypothesis.get("id")
                or f"{record.run_id}:hypothesis:{index + 1:03d}"
            ),
            **origin,
        }
        counts[str(merged["origin"])] = counts.get(str(merged["origin"]), 0) + 1
        annotated.append(merged)
    record.hypotheses = annotated
    record.metrics["hypothesis_origin_counts"] = counts
    record.metrics["hypothesis_origin_boundary"] = (
        "Origins are inferred from user starting hypotheses, generation metadata, and evolution hints. "
        "They are UI/audit labels, not scientific evidence."
    )


def build_research_outcome(record: RunRecord) -> Dict[str, Any]:
    """Build one durable, auditable result package for the top Elo hypothesis."""
    if not record.hypotheses:
        return {
            "status": "absent",
            "run_id": record.run_id,
            "evidence_gate": {"status": "failed", "reasons": ["no_hypotheses"]},
        }

    winner_index, winner = max(
        enumerate(record.hypotheses),
        key=lambda pair: float(pair[1].get("elo_rating") or pair[1].get("score") or 0),
    )
    packet = winner.get("evidence_packet") if isinstance(winner.get("evidence_packet"), dict) else {}
    packet_items = packet.get("items") if isinstance(packet.get("items"), list) else []
    provenance_hypotheses = record.citation_provenance_qa.get("hypotheses")
    provenance_hypotheses = provenance_hypotheses if isinstance(provenance_hypotheses, list) else []
    provenance = next(
        (
            item
            for item in provenance_hypotheses
            if isinstance(item, dict) and item.get("hypothesis_index") == winner_index
        ),
        {},
    )
    minimum_evidence = int(record.request.min_references or 0)
    support_count = sum(
        1
        for item in packet_items
        if isinstance(item, dict) and item.get("relationship") == "support"
    )
    contradiction_count = sum(
        1
        for item in packet_items
        if isinstance(item, dict) and item.get("relationship") == "contradict"
    )
    strong_count = sum(
        1
        for item in packet_items
        if isinstance(item, dict)
        and item.get("relationship") == "support"
        and (
            item.get("source_reliability") == "parsed_fulltext"
            or item.get("support_level") == "experimental_data"
        )
    )
    reasons: List[str] = []
    if len(packet_items) < minimum_evidence:
        reasons.append("below_minimum_evidence_count")
    if support_count < minimum_evidence:
        reasons.append("below_minimum_supporting_evidence_count")
    if contradiction_count:
        reasons.append("contradictory_evidence_requires_review")
    if record.request.literature_review and strong_count == 0:
        reasons.append("no_parsed_fulltext_or_experimental_evidence")
    if provenance.get("orphaned_citations"):
        reasons.append("orphaned_citations")
    if not packet_items:
        reasons.append("no_hypothesis_specific_evidence")

    paper_ids = list(
        dict.fromkeys(
            str(item.get("paper_id"))
            for item in packet_items
            if isinstance(item, dict) and item.get("paper_id")
        )
    )
    parse_run_ids = list(
        dict.fromkeys(
            str(item.get("parse_run_id"))
            for item in packet_items
            if isinstance(item, dict) and item.get("parse_run_id")
        )
    )
    evidence_ids = list(
        dict.fromkeys(
            str(item.get("evidence_id") or item.get("chunk_id"))
            for item in packet_items
            if isinstance(item, dict) and (item.get("evidence_id") or item.get("chunk_id"))
        )
    )
    return {
        "status": "ready" if not reasons else "limited",
        "run_id": record.run_id,
        "winner_id": winner.get("hypothesis_id"),
        "winner_index": winner_index,
        "winner_hypothesis": winner,
        "elo_rating": winner.get("elo_rating"),
        "score": winner.get("score"),
        "evidence_snapshot_id": record.evidence_snapshot.get("snapshot_id"),
        "evidence_packet_snapshot_id": packet.get("snapshot_id"),
        "evidence_gate": {
            "status": "passed" if not reasons else "limited",
            "minimum_evidence_count": minimum_evidence,
            "retrieved_evidence_count": len(packet_items),
            "strong_evidence_count": strong_count,
            "supporting_evidence_count": support_count,
            "contradicting_evidence_count": contradiction_count,
            "reasons": reasons,
            "boundary": (
                "A passed gate means provenance requirements were met for ranking. "
                "It does not mean the hypothesis has been experimentally validated."
            ),
        },
        "paper_ids": paper_ids,
        "parse_run_ids": parse_run_ids,
        "evidence_ids": evidence_ids,
        "knowledge_chunks": packet_items,
        "citation_map": winner.get("citation_map") or {},
        "citation_provenance": provenance,
        "tournament_matchups": record.tournament_matchups,
        "experiment_plan": winner.get("experiment"),
    }


def refresh_run_evidence_snapshot(record: RunRecord) -> None:
    packets = [
        hypothesis.get("evidence_packet")
        for hypothesis in record.hypotheses
        if isinstance(hypothesis, dict) and isinstance(hypothesis.get("evidence_packet"), dict)
    ]
    packet_ids = sorted(str(packet.get("snapshot_id") or "") for packet in packets)
    digest = hashlib.sha256("|".join(packet_ids).encode("utf-8")).hexdigest()[:16]
    relationship_counts = {
        relationship: sum(
            int((packet.get("relationship_counts") or {}).get(relationship, 0))
            for packet in packets
        )
        for relationship in ("support", "contradict", "irrelevant", "insufficient", "relevant")
    }
    record.evidence_snapshot = {
        "snapshot_id": f"snapshot_{digest}",
        "status": "ready" if any(int(packet.get("item_count") or 0) for packet in packets) else "limited",
        "hypothesis_count": len(record.hypotheses),
        "packet_count": len(packets),
        "evidence_item_count": sum(int(packet.get("item_count") or 0) for packet in packets),
        "parsed_fulltext_count": sum(
            int(packet.get("parsed_fulltext_count") or 0) for packet in packets
        ),
        "experimental_data_count": sum(
            int(packet.get("experimental_data_count") or 0) for packet in packets
        ),
        "relationship_counts": relationship_counts,
        "packet_snapshot_ids": packet_ids,
        "boundary": "Snapshot includes approved experiment interpretations and literature evidence packets.",
    }


def apply_experiment_feedback_to_record(
    record: RunRecord,
    request: ExperimentFeedbackRequest,
    job: Dict[str, Any],
    *,
    source_channel: str = "approved_experiment_feedback",
    relationship_confidence: float = 1.0,
    persist_loop_marker: bool = False,
) -> Dict[str, Any]:
    """Attach a human-approved experiment interpretation as structured evidence."""
    if request.hypothesis_index >= len(record.hypotheses):
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    hypothesis = record.hypotheses[request.hypothesis_index]
    experiment_runs = hypothesis.get("experiment_runs")
    experiment_runs = experiment_runs if isinstance(experiment_runs, list) else []
    matching_run = next(
        (item for item in experiment_runs if isinstance(item, dict) and item.get("job_id") == request.job_id),
        None,
    )
    if matching_run is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "experiment_not_attached_to_hypothesis",
                "message": "这个实验任务没有绑定到所选假设，不能写入科学解释。",
            },
        )
    relationship = "insufficient" if request.verdict == "inconclusive" else request.verdict
    result_ref = job.get("result_ref") if isinstance(job.get("result_ref"), dict) else {}
    tool_result_ref = result_ref.get("tool_result") if isinstance(result_ref.get("tool_result"), dict) else {}
    evidence_item = {
        "evidence_id": f"experiment:{request.job_id}",
        "chunk_id": f"experiment:{request.job_id}",
        "title": f"Experiment result {request.job_id}",
        "support_level": "experimental_data",
        "source_reliability": "experiment_run",
        "relationship": relationship,
        "relationship_confidence": max(0.0, min(float(relationship_confidence), 1.0)),
        "relationship_rationale": request.rationale,
        "text_preview": (
            f"Human interpretation: {request.rationale} "
            f"Execution status: {job.get('status')}; result_ref: {tool_result_ref.get('result_id') or 'stored'}."
        ),
        "experiment_data_summary": request.rationale,
        "source_channel": source_channel,
        "job_id": request.job_id,
        "result_id": tool_result_ref.get("result_id"),
    }
    packet = hypothesis.get("evidence_packet")
    packet = packet if isinstance(packet, dict) else {}
    items = [item for item in (packet.get("items") or []) if isinstance(item, dict)]
    items = [item for item in items if item.get("evidence_id") != evidence_item["evidence_id"]]
    items.append(evidence_item)

    from open_coscientist.models import Hypothesis
    from open_coscientist.nodes.evidence_grounding import normalize_evidence_packet

    hypothesis["evidence_packet"] = normalize_evidence_packet(
        {
            "status": "ready",
            "query": packet.get("query") or hypothesis.get("text"),
            "library_id": packet.get("library_id") or record.request.library_id,
            "items": items,
        },
        hypothesis=Hypothesis(text=str(hypothesis.get("text") or "")),
    )
    matching_run.update(
        {
            "interpretation_status": "complete",
            "verdict": request.verdict,
            "rationale": request.rationale,
            "evidence_id": evidence_item["evidence_id"],
        }
    )
    hypothesis["experiment_runs"] = experiment_runs
    if persist_loop_marker and isinstance(record.research_loop, dict):
        record.research_loop["interpretation_evidence_id"] = evidence_item["evidence_id"]
    refresh_run_evidence_snapshot(record)
    apply_citation_provenance_qa(record)
    record.research_outcome = build_research_outcome(record)
    record.updated_at = time.time()
    add_event(
        record,
        "Experiment",
        "Experiment interpretation recorded",
        f"Experiment {request.job_id} was marked {request.verdict} for hypothesis {request.hypothesis_index + 1}.",
        "complete",
    )
    persist_run_record(record)
    return evidence_item


AUTOPILOT_WORKFLOW = "workflow.research_autopilot"


def selected_winner(record: RunRecord) -> tuple[int, Dict[str, Any]]:
    if not record.hypotheses:
        raise ValueError("Research autopilot requires at least one hypothesis.")
    requested = record.research_outcome.get("winner_index")
    if isinstance(requested, int) and 0 <= requested < len(record.hypotheses):
        return requested, record.hypotheses[requested]
    return max(
        enumerate(record.hypotheses),
        key=lambda pair: float(pair[1].get("elo_rating") or pair[1].get("score") or 0),
    )


def selected_loop_hypothesis(record: RunRecord) -> tuple[int, Dict[str, Any]]:
    """Keep an autopilot cycle bound to the hypothesis selected when it was enqueued."""
    selected_index = record.research_loop.get("selected_hypothesis_index")
    selected_id = str(record.research_loop.get("selected_hypothesis_id") or "")
    if isinstance(selected_index, int) and 0 <= selected_index < len(record.hypotheses):
        hypothesis = record.hypotheses[selected_index]
        hypothesis_id = str(hypothesis.get("hypothesis_id") or hypothesis.get("id") or "")
        if not selected_id or not hypothesis_id or selected_id == hypothesis_id:
            return selected_index, hypothesis
    return selected_winner(record)


def validate_autopilot_policy_for_persistence(policy: Dict[str, Any]) -> Dict[str, Any]:
    """Reject inline SSH secrets before a durable policy is written to the project database."""
    normalized = normalize_policy(policy)
    compute = normalized.get("compute") if isinstance(normalized.get("compute"), dict) else {}
    command = str(compute.get("command") or "")
    if compute.get("kind") == "ssh" and command and redact_sensitive_text(command) != command:
        raise AutopilotValidationError(
            "SSH commands cannot contain inline passwords, tokens, or API keys. "
            "Configure secrets on the registered server and reference them by environment name."
        )
    return normalized


def consume_autopilot_grant(
    record: RunRecord,
    policy: Dict[str, Any],
    scope: str,
    *,
    server_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Consume and audit one bounded mission grant before its side effect begins."""
    updated = consume_exact_grant(policy, scope, server_id)
    history = list(record.research_loop.get("approval_history") or [])
    history.append(
        {
            "scope": scope,
            "server_id": server_id,
            "status": "consumed",
            "used_at": time.time(),
            "reason": "Consumed immediately before the approved autopilot side effect.",
        }
    )
    record.research_loop["policy"] = updated
    record.research_loop["approval_history"] = history[-100:]
    record.updated_at = time.time()
    persist_run_record(record)
    return updated


def autopilot_execution_job_id(record: RunRecord, protocol: Dict[str, Any]) -> str:
    payload = (
        f"{record.run_id}|{record.research_loop.get('cycle') or 1}|"
        f"{protocol.get('protocol_id') or ''}"
    )
    return f"job_autopilot_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def find_autopilot_rerank_child(parent_run_id: str, job_id: str) -> Optional[RunRecord]:
    """Recover a continuation created before the parent persisted its child reference."""
    for summary in knowledge_base.list_research_runs(limit=200):
        child = load_run_record(str(summary.get("run_id") or ""))
        if not child or child.request.parent_run_id != parent_run_id:
            continue
        for item in child.request.user_feedback:
            target_ref = (
                item.target_ref
                if isinstance(item, FeedbackItem)
                else item.get("target_ref", {}) if isinstance(item, dict) else {}
            )
            if str(target_ref.get("job_id") or "") == job_id:
                return child
    return None


def persist_loop_stage(
    record: RunRecord,
    stage: str,
    status: str,
    summary: str,
    *,
    details: Optional[Dict[str, Any]] = None,
    loop_status: Optional[str] = None,
) -> Dict[str, Any]:
    state = update_loop_stage(
        record.research_loop,
        stage,
        status,
        summary=summary,
        details=details or {},
    )
    if loop_status:
        state["status"] = loop_status
    record.research_loop = state
    record.updated_at = time.time()
    persist_run_record(record)
    return state


def enqueue_research_autopilot(
    record: RunRecord,
    raw_policy: Optional[Dict[str, Any]] = None,
    *,
    resume: bool = False,
) -> Dict[str, Any]:
    policy = validate_autopilot_policy_for_persistence(
        raw_policy or record.request.autopilot or {}
    )
    if not resume or not record.research_loop:
        state = build_loop_state(policy, run_id=record.run_id)
        evidence_first = record.metrics.get("evidence_first") if isinstance(record.metrics, dict) else {}
        state = update_loop_stage(
            state,
            "discover",
            "complete" if isinstance(evidence_first, dict) and evidence_first.get("candidate_count") else "limited",
            summary=(
                f"发现 {int(evidence_first.get('candidate_count') or 0)} 个论文候选。"
                if isinstance(evidence_first, dict)
                else "当前 run 没有独立的论文发现摘要。"
            ),
        )
        state = update_loop_stage(
            state,
            "acquire_parse",
            "complete" if isinstance(evidence_first, dict) and evidence_first.get("ingested_count") else "limited",
            summary=(
                f"已解析入库 {int(evidence_first.get('ingested_count') or 0)} 篇论文。"
                if isinstance(evidence_first, dict)
                else "将使用当前知识库内容。"
            ),
        )
        state = update_loop_stage(
            state,
            "ground",
            "complete" if record.evidence_snapshot.get("evidence_item_count") else "limited",
            summary=f"证据快照包含 {int(record.evidence_snapshot.get('evidence_item_count') or 0)} 条证据。",
        )
        state = update_loop_stage(
            state,
            "generate_rank",
            "complete",
            summary=f"已生成 {len(record.hypotheses)} 条假设和 {len(record.tournament_matchups)} 场比较。",
        )
    else:
        state = dict(record.research_loop)
        state["policy"] = policy
        state["status"] = "queued"
        state["pending_approvals"] = []
        state["resume_count"] = int(state.get("resume_count") or 0) + 1
    winner_index, winner = (
        selected_loop_hypothesis(record)
        if resume and record.research_loop.get("selected_hypothesis_index") is not None
        else selected_winner(record)
    )
    state["selected_hypothesis_index"] = winner_index
    state["selected_hypothesis_id"] = winner.get("hypothesis_id")
    state["status"] = "queued"
    record.research_loop = state
    record.updated_at = time.time()
    persist_run_record(record)

    work_item = knowledge_base.enqueue_work_item(
        workflow_name=AUTOPILOT_WORKFLOW,
        run_id=record.run_id,
        phase="research_autopilot",
        agent_role="autopilot_supervisor",
        arguments={"run_id": record.run_id, "policy": policy},
        idempotency_key=(
            f"{AUTOPILOT_WORKFLOW}:{record.run_id}:{int(state.get('cycle') or 0)}:"
            f"{int(state.get('resume_count') or 0)}"
        ),
    )
    existing_tasks = knowledge_base.list_research_tasks(
        run_id=record.run_id,
        task_type="research_autopilot",
        limit=20,
    )
    active_task = next(
        (task for task in existing_tasks if task.get("status") in {"ready", "running", "blocked"}),
        None,
    )
    if active_task:
        knowledge_base.update_research_task(
            str(active_task["task_id"]),
            status="ready",
            blocked_reason="",
            result_ref={"work_item_id": work_item.get("work_item_id"), "status": "queued"},
        )
    else:
        knowledge_base.create_research_task(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            run_id=record.run_id,
            title="Research Autopilot closed loop",
            task_type="research_autopilot",
            status="ready",
            priority=1,
            phase="research_autopilot",
            target_ref={"hypothesis_index": winner_index},
            result_ref={"work_item_id": work_item.get("work_item_id"), "status": "queued"},
            notes="Durable controller for evidence, experiment execution, interpretation, and reranking.",
        )
    return {"research_loop": state, "work_item": work_item}


def demo_hypotheses(goal: str) -> List[Dict[str, Any]]:
    subject = goal.strip().rstrip(".")
    return [
        {
            "hypothesis_id": "HYP-001",
            "text": f"We want to develop a retrieval-audited generation protocol for {subject} by forcing every claim to traverse evidence, counterexample, and experiment-design checkpoints before acceptance.",
            "explanation": "The system turns hypothesis generation into a staged review process instead of a single answer. Each candidate must expose what evidence supports it, what could falsify it, and how it would be tested.",
            "literature_grounding": "Demo mode uses synthetic grounding. Run with model credentials and literature review enabled to resolve real sources.",
            "experiment": "Compare the protocol against a baseline generator on a curated benchmark. Measure claim support precision, contradiction rate, reviewer preference, and reproducibility of proposed experiments.",
            "score": 0.87,
            "elo_rating": 1512,
            "generation_method": "demo-evolved",
            "win_count": 5,
            "loss_count": 1,
            "reviews": [
                {
                    "review_summary": "Strongest candidate because it binds generation to falsifiable evidence checkpoints.",
                    "reviewer_agent": "Reviewer",
                    "scores": {
                        "scientific_soundness": 8,
                        "novelty": 8,
                        "relevance": 9,
                        "testability": 9,
                        "clarity": 8,
                        "potential_impact": 9,
                    },
                    "weaknesses": [
                        "Requires a well-curated claim-support benchmark.",
                        "May add latency if every claim waits for evidence checks.",
                    ],
                    "falsification_criteria": [
                        "No reduction in unsupported claim rate versus baseline.",
                        "Reviewer preference does not improve under blind evaluation.",
                    ],
                    "evidence_refs": ["S1", "R1"],
                    "confidence": 0.86,
                    "overall_score": 8.5,
                }
            ],
            "citation_map": {
                "S1": {"type": "local_agent_simulation", "title": "Supervisor evidence checkpoint"},
                "R1": {"type": "local_agent_simulation", "title": "Reviewer falsification critique"},
            },
        },
        {
            "hypothesis_id": "HYP-002",
            "text": f"We want to evolve a population of diverse candidate mechanisms for {subject} using tournament selection plus proximity penalties to prevent repeated variants from dominating.",
            "explanation": "The method keeps multiple plausible directions alive while ranking stronger candidates. Similar hypotheses are penalized so the search does not collapse into one repeated idea.",
            "literature_grounding": "Demo mode shows the output structure without querying PubMed or MCP tools.",
            "experiment": "Run ablations with and without proximity penalties. Track hypothesis diversity, expert novelty ratings, and downstream experiment pass rate.",
            "score": 0.82,
            "elo_rating": 1500,
            "generation_method": "demo-generated",
            "win_count": 4,
            "loss_count": 2,
            "reviews": [
                {
                    "review_summary": "Useful exploration strategy; needs a stronger external novelty screen before live use.",
                    "reviewer_agent": "Reviewer",
                    "scores": {
                        "scientific_soundness": 8,
                        "novelty": 7,
                        "relevance": 8,
                        "testability": 8,
                        "clarity": 8,
                        "potential_impact": 8,
                    },
                    "weaknesses": [
                        "Population search may optimize for judge preference rather than scientific validity.",
                        "Diversity metrics can preserve superficially different but weak candidates.",
                    ],
                    "falsification_criteria": [
                        "Diversity increases while expert novelty ratings stay flat.",
                        "Tournament winners fail independent experiment-plan review.",
                    ],
                    "evidence_refs": ["G1", "P1"],
                    "confidence": 0.8,
                    "overall_score": 7.8,
                }
            ],
            "citation_map": {
                "G1": {"type": "local_agent_simulation", "title": "Generator diversity proposal"},
                "P1": {"type": "local_agent_simulation", "title": "Proximity deduplication signal"},
            },
        },
        {
            "hypothesis_id": "HYP-003",
            "text": f"We want to attach falsification-first experiment plans to each hypothesis about {subject}, so weak ideas are rejected before expensive validation.",
            "explanation": "The system asks what observation would disprove the hypothesis before it asks how to make the hypothesis sound compelling.",
            "literature_grounding": "No real literature is consulted in demo mode.",
            "experiment": "Have independent reviewers score whether each plan contains clear reject criteria, measurable metrics, and an executable minimum experiment.",
            "score": 0.78,
            "elo_rating": 1488,
            "generation_method": "demo-review",
            "win_count": 3,
            "loss_count": 3,
            "reviews": [
                {
                    "review_summary": "Good safety valve for expensive experiments, but less complete as a standalone discovery strategy.",
                    "reviewer_agent": "Reviewer",
                    "scores": {
                        "scientific_soundness": 8,
                        "novelty": 6,
                        "relevance": 8,
                        "testability": 9,
                        "clarity": 8,
                        "potential_impact": 7,
                    },
                    "weaknesses": [
                        "Acts more like a quality gate than a discovery mechanism.",
                        "Needs domain-specific reject criteria to avoid generic plans.",
                    ],
                    "falsification_criteria": [
                        "Plans fail to specify measurable reject thresholds.",
                        "Rejected candidates later outperform accepted ones in blind tests.",
                    ],
                    "evidence_refs": [],
                    "confidence": 0.78,
                    "overall_score": 7.7,
                }
            ],
            "citation_map": {},
        },
    ]


def demo_agent_trace(goal: str) -> List[AgentTrace]:
    subject = goal.strip().rstrip(".")
    return [
        agent_trace_from_registry(
            event_id="trace-supervisor",
            agent="Supervisor",
            role="Research planner",
            phase="supervisor",
            output=(
                "I decomposed the goal into three work packages: claim grounding, "
                "candidate diversity, and falsification-first evaluation."
            ),
            tool_calls=[{"tool": "goal_decomposition", "status": "synthetic"}],
            token_usage={"prompt": 0, "completion": 0},
            confidence=0.91,
        ),
        agent_trace_from_registry(
            event_id="trace-literature",
            parent_event_id="trace-supervisor",
            agent="Literature Scout",
            role="Evidence mapper",
            phase="literature",
            output=(
                "No external corpus was queried in local simulation mode. I created a synthetic "
                "evidence map so the UI can show where real MCP/PubMed citations would attach."
            ),
            tool_calls=[{"tool": "synthetic_reference_index", "status": "complete"}],
            token_usage={"prompt": 0, "completion": 0},
            confidence=0.72,
        ),
        agent_trace_from_registry(
            event_id="trace-generator",
            parent_event_id="trace-supervisor",
            agent="Generator",
            role="Hypothesis proposer",
            phase="generate",
            output=(
                f"I generated candidates for {subject} by varying the mechanism: audited "
                "retrieval, population evolution, and falsification-gated experiment design."
            ),
            tool_calls=[{"tool": "hypothesis_population_seed", "status": "complete"}],
            token_usage={"prompt": 0, "completion": 0},
            confidence=0.84,
        ),
        agent_trace_from_registry(
            event_id="trace-reviewer",
            parent_event_id="trace-generator",
            agent="Reviewer",
            role="Rubric critic",
            phase="review",
            output=(
                "I scored each candidate on scientific soundness, novelty, relevance, "
                "testability, clarity, and impact, then attached concise critique summaries."
            ),
            tool_calls=[{"tool": "rubric_review", "status": "complete"}],
            token_usage={"prompt": 0, "completion": 0},
            confidence=0.86,
        ),
        agent_trace_from_registry(
            event_id="trace-ranker",
            parent_event_id="trace-reviewer",
            agent="Ranker",
            role="Tournament judge",
            phase="rank",
            output=(
                "I preferred the retrieval-audited protocol because it has the clearest "
                "measurement path and the lowest risk of ungrounded claims."
            ),
            tool_calls=[{"tool": "pairwise_tournament", "rounds": 2, "status": "complete"}],
            token_usage={"prompt": 0, "completion": 0},
            confidence=0.88,
        ),
        agent_trace_from_registry(
            event_id="trace-proximity",
            parent_event_id="trace-ranker",
            agent="Proximity",
            role="Diversity guard",
            phase="proximity",
            output=(
                "The candidates cover three distinct intervention points, so no duplicate "
                "collapse was detected in this simulated run."
            ),
            tool_calls=[{"tool": "similarity_cluster", "status": "complete"}],
            token_usage={"prompt": 0, "completion": 0},
            confidence=0.81,
        ),
    ]


async def run_demo(record: RunRecord) -> None:
    stages = [
        ("Supervisor", "Local agent key accepted", "Codex simulation provider initialized"),
        ("Literature", "Evidence scaffold built", "Synthetic citation slots prepared for MCP/PubMed replacement"),
        ("Generate", "Hypotheses generated", f"{record.request.initial_hypotheses} initial candidates drafted"),
        ("Review", "Peer review completed", "Scientific soundness, novelty, relevance, testability, clarity, and impact scored"),
        ("Rank", "Tournament updated", "Pairwise preference ranking produced Elo scores"),
        ("Proximity", "Diversity checked", "Candidate population checked for near-duplicate collapse"),
        ("Metrics", "Run finalized", "Local multi-agent simulation results prepared for inspection"),
    ]
    record.status = "running"
    for stage, event, details in stages:
        add_event(record, stage, event, details, "active")
        await asyncio.sleep(0.45)
        record.timeline[-1].status = "complete"
        record.updated_at = time.time()

    record.hypotheses = demo_hypotheses(record.request.research_goal)[: record.request.initial_hypotheses]
    record.agent_trace = demo_agent_trace(record.request.research_goal)
    record.research_plan = {
        "provider": "local-codex-simulation",
        "strategy": "Use a fake API-key path to inspect the product workflow before connecting a live model.",
        "supervisor_plan": [
            "Define the scientific claim type and measurable failure modes.",
            "Generate diverse candidate mechanisms instead of variants of one idea.",
            "Review each hypothesis with a rubric and rank via pairwise tournament.",
            "Expose citations, critique, and metrics in the UI for human inspection.",
        ],
        "recommended_next_step": "Open runtime readiness, choose an available live model, and keep literature support enabled before treating results as scientific evidence.",
    }

    def demo_hypothesis_text(index: int, fallback: str) -> str:
        if index >= len(record.hypotheses):
            return fallback
        hypothesis = record.hypotheses[index]
        return str(hypothesis.get("text") or hypothesis.get("hypothesis") or fallback)

    record.tournament_matchups = [
        {
            "matchup_id": "matchup-001",
            "round": 1,
            "hypothesis_a": demo_hypothesis_text(0, "Hypothesis 1"),
            "hypothesis_b": demo_hypothesis_text(1, "Hypothesis 2"),
            "hypothesis_a_id": "HYP-001",
            "hypothesis_b_id": "HYP-002",
            "winner": "a",
            "loser": "b",
            "winner_id": "HYP-001",
            "loser_id": "HYP-002",
            "winner_label": "Hypothesis A",
            "loser_label": "Hypothesis B",
            "judge_agent": "Ranker",
            "criteria": ["testability", "claim grounding", "failure-mode clarity"],
            "margin": 0.18,
            "before_elo": {"HYP-001": 1500, "HYP-002": 1500},
            "after_elo": {"HYP-001": 1512, "HYP-002": 1488},
            "winner_elo_before": 1500,
            "winner_elo_after": 1512,
            "winner_elo_delta": 12,
            "loser_elo_before": 1500,
            "loser_elo_after": 1488,
            "loser_elo_delta": -12,
            "elo_delta": {"HYP-001": 12, "HYP-002": -12},
            "confidence": "Medium",
            "confidence_level": "Medium",
            "confidence_score": 0.6,
            "comparison_mode": "debate",
            "debate_turns_requested": 3,
            "pairing_priority": {"proximity": 0.62, "newer_hypotheses": 0.0, "top_ranked": 1.0},
            "reasoning": "Higher testability and stronger falsification design.",
        },
        {
            "matchup_id": "matchup-002",
            "round": 2,
            "hypothesis_a": demo_hypothesis_text(1, "Hypothesis 2"),
            "hypothesis_b": demo_hypothesis_text(2, "Hypothesis 3"),
            "hypothesis_a_id": "HYP-002",
            "hypothesis_b_id": "HYP-003",
            "winner": "a",
            "loser": "b",
            "winner_id": "HYP-002",
            "loser_id": "HYP-003",
            "winner_label": "Hypothesis A",
            "loser_label": "Hypothesis B",
            "judge_agent": "Ranker",
            "criteria": ["novelty", "population diversity", "search leverage"],
            "margin": 0.09,
            "before_elo": {"HYP-002": 1488, "HYP-003": 1500},
            "after_elo": {"HYP-002": 1500, "HYP-003": 1488},
            "winner_elo_before": 1488,
            "winner_elo_after": 1500,
            "winner_elo_delta": 12,
            "loser_elo_before": 1500,
            "loser_elo_after": 1488,
            "loser_elo_delta": -12,
            "elo_delta": {"HYP-002": 12, "HYP-003": -12},
            "confidence": "Low",
            "confidence_level": "Low",
            "confidence_score": 0.35,
            "comparison_mode": "single_turn",
            "debate_turns_requested": 0,
            "pairing_priority": {"proximity": 0.44, "newer_hypotheses": 0.0, "top_ranked": 0.67},
            "reasoning": "Better population-level diversity control.",
        },
    ]
    record.metrics = {
        "total_time": round(time.time() - record.created_at, 2),
        "hypothesis_count": len(record.hypotheses),
        "reviews_count": len(record.hypotheses),
        "tournaments_count": 2,
        "evolutions_count": 0,
        "llm_calls": 0,
        "mode": "local-agent-simulation",
        "fake_api_key": "enabled",
    }
    annotate_hypothesis_origins(record)
    apply_citation_provenance_qa(record)
    record.evidence_snapshot = {
        "status": "synthetic_demo",
        "snapshot_id": f"demo_{record.run_id}",
        "boundary": "Demo evidence is synthetic and was not used as scientific grounding.",
    }
    record.research_outcome = build_research_outcome(record)
    initialize_expert_feedback_state(record)
    record.status = "complete"
    record.updated_at = time.time()
    persist_run_record(record)


def build_knowledge_base_evidence_resolver(record: RunRecord):
    """Create the webapp adapter used by the core evidence-grounding node."""

    def inherited_experiment_items(hypothesis: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not record.request.parent_run_id:
            return []
        parent = load_run_record(record.request.parent_run_id)
        if not parent:
            return []
        query_text = _normalize_hypothesis_text(hypothesis.get("text"))
        query_terms = set(re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", query_text))
        best: Optional[Dict[str, Any]] = None
        best_score = 0.0
        for candidate in parent.hypotheses:
            if not isinstance(candidate, dict):
                continue
            candidate_terms = set(
                re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", str(candidate.get("text") or "").lower())
            )
            union = query_terms.union(candidate_terms)
            score = len(query_terms.intersection(candidate_terms)) / max(1, len(union))
            if score > best_score:
                best, best_score = candidate, score
        if best is None or best_score < 0.35:
            return []
        best_text = _normalize_hypothesis_text(best.get("text"))
        exact_lineage = bool(query_text and query_text == best_text)
        packet = best.get("evidence_packet") if isinstance(best.get("evidence_packet"), dict) else {}
        packet_items = packet.get("items") if isinstance(packet.get("items"), list) else []
        inherited: List[Dict[str, Any]] = []
        for item in packet_items:
            if not (
                isinstance(item, dict)
                and item.get("support_level") == "experimental_data"
                and item.get("source_channel") in {
                    "approved_experiment_feedback",
                    "policy_evaluated_experiment",
                }
            ):
                continue
            copied = {
                **item,
                "inherited_from_run_id": parent.run_id,
                "inherited_from_hypothesis_id": best.get("hypothesis_id"),
                "lineage_similarity": round(best_score, 4),
                "lineage_status": "exact" if exact_lineage else "review_required",
            }
            if not exact_lineage:
                copied["original_relationship"] = copied.get("relationship")
                copied["relationship"] = "insufficient"
                copied["source_channel"] = "inherited_experiment_context"
                copied["relationship_rationale"] = (
                    "Experiment came from a text-similar parent hypothesis; applicability to the revised claim "
                    "requires explicit review."
                )
            inherited.append(copied)
        return inherited

    async def resolve(hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        items = await asyncio.to_thread(
            knowledge_base.support_for_hypothesis,
            hypothesis,
            limit=max(6, int(record.request.max_references or 0)),
            library_id=record.request.library_id,
        )
        items = evidence_verifier.classify_evidence_items(
            hypothesis_text=str(hypothesis.get("text") or ""),
            evidence_items=items,
        )
        inherited = inherited_experiment_items(hypothesis)
        existing_ids = {
            str(item.get("evidence_id") or item.get("chunk_id") or "")
            for item in items
            if isinstance(item, dict)
        }
        items.extend(
            item
            for item in inherited
            if str(item.get("evidence_id") or item.get("chunk_id") or "") not in existing_ids
        )
        return {
            "status": "ready" if items else "absent",
            "query": " ".join(
                str(hypothesis.get(key) or "")
                for key in ("text", "explanation", "experiment")
            ).strip(),
            "library_id": record.request.library_id,
            "items": items,
        }

    return resolve


async def run_real(record: RunRecord) -> None:
    observer_token = None
    evidence_first_summary = (
        serialize_value(record.metrics.get("evidence_first"))
        if isinstance(record.metrics, dict) and record.metrics.get("evidence_first")
        else None
    )
    try:
        normalize_provider_env()
        from open_coscientist import HypothesisGenerator
        from open_coscientist.checkpointing import (
            execution_memory_status,
            open_sqlite_checkpointer,
            summarize_langgraph_checkpoint_tuple,
        )
        from open_coscientist.mcp_client import (
            reset_mcp_tool_call_observer,
            set_mcp_tool_call_observer,
        )

        record.status = "running"
        add_event(record, "Supervisor", "Run started", "Live open-coscientist workflow started", "active")
        observer_token = set_mcp_tool_call_observer(build_mcp_tool_observer(record.run_id))

        async def progress_callback(phase: str, data: dict) -> None:
            add_event(
                record,
                phase.replace("_", " ").title(),
                data.get("message") or phase,
                f"Progress {data.get('progress', 0)}%",
                "active",
            )

        generator = HypothesisGenerator(
            model_name=record.request.model_name,
            max_iterations=record.request.iterations,
            initial_hypotheses_count=record.request.initial_hypotheses,
            evolution_max_count=max(1, min(3, record.request.initial_hypotheses)),
            enable_cache=True,
            workflow_tool_policy=default_live_workflow_tool_policy(),
            evidence_resolver=build_knowledge_base_evidence_resolver(record),
        )
        reference_constraints = (
            f"For each generated hypothesis, target between {record.request.min_references} "
            f"and {record.request.max_references} distinct, high-quality literature references. "
            "Populate citation_map with source metadata whenever available. If the available "
            "literature evidence is below the requested minimum, explicitly mark the evidence "
            "gap instead of overstating certainty."
        )
        memory_context = knowledge_base.build_memory_context(
            research_goal=record.request.research_goal,
            parent_run_id=record.request.parent_run_id,
            library_id=record.request.library_id,
            memory_scope=record.request.memory_scope,
        )
        memory_prompt_packet = knowledge_base.memory_context_prompt_packet(memory_context)
        combined_constraints = [
            f"[user_constraint] {constraint}"
            for constraint in record.request.constraints
            if constraint.strip()
        ]
        combined_constraints.append(f"[reference_policy] {reference_constraints}")
        combined_constraints.append("[memory_boundary] Memory context is summary-only; raw records are not injected.")
        if evidence_first_summary:
            combined_constraints.append(
                "[evidence_first] Before hypothesis generation, the system attempted automatic literature "
                f"discovery and knowledge-base ingestion for library_id={evidence_first_summary.get('library_id')}. "
                f"candidate_count={evidence_first_summary.get('candidate_count')}; "
                f"ingested_count={evidence_first_summary.get('ingested_count')}. Use the supplied evidence memory "
                "and citation_map for grounding, and explicitly mark gaps when the evidence is insufficient."
            )
        combined_constraints.extend(run_request_feedback_prompt_constraints(record.request.user_feedback))
        combined_constraints.extend(memory_context_prompt_constraints(memory_context))

        generation_opts = {
            "enable_literature_review_node": record.request.literature_review,
            "enable_tool_calling_generation": False,
            "preferences": record.request.preferences,
            "attributes": record.request.attributes,
            "constraints": combined_constraints,
            "memory_context": memory_context,
            "memory_prompt_packet": memory_prompt_packet,
            "user_feedback": [item.model_dump() for item in record.request.user_feedback],
            "user_inputs": {
                "starting_hypotheses": record.request.starting_hypotheses,
                "literature": memory_context.get("evidence_summaries", []),
            },
        }
        checkpoint_status = execution_memory_status()
        langgraph_checkpoint_summary: Optional[Dict[str, Any]] = None

        if checkpoint_status.get("langgraph_checkpoint_sqlite_available"):
            async with open_sqlite_checkpointer(KB_ROOT / "langgraph_checkpoints.sqlite") as checkpointer:
                generation_opts["checkpointer"] = checkpointer
                result = await generator.generate_hypotheses(
                    research_goal=record.request.research_goal,
                    progress_callback=progress_callback,
                    opts=generation_opts,
                    run_id=record.run_id,
                    stream=False,
                )
                async for checkpoint_tuple in checkpointer.alist(
                    {"configurable": {"thread_id": record.run_id}}
                ):
                    langgraph_checkpoint_summary = summarize_langgraph_checkpoint_tuple(checkpoint_tuple)
                    break
        else:
            result = await generator.generate_hypotheses(
                research_goal=record.request.research_goal,
                progress_callback=progress_callback,
                opts=generation_opts,
                run_id=record.run_id,
                stream=False,
            )

        record.hypotheses = serialize_value(result.get("hypotheses", []))
        record.research_plan = serialize_value(result.get("research_plan", {}))
        if not isinstance(record.research_plan, dict):
            record.research_plan = {"raw_plan": record.research_plan}
        record.research_plan["tool_policy"] = {
            "bridge_phase_policy": list_phase_tool_policies(),
            "open_coscientist_workflow_policy": serialize_value(result.get("workflow_tool_policy", {})),
            "direct_tool_calling_generation": False,
            "policy_boundary": (
                "The webapp bridge disables direct generation-phase tool calling. "
                "MCP literature tools are limited by the open-coscientist workflow policy."
            ),
        }
        record.tournament_matchups = serialize_value(result.get("tournament_matchups", []))
        record.evidence_snapshot = serialize_value(result.get("evidence_snapshot", {}))
        record.metrics = serialize_value(result.get("metrics", {}))
        if evidence_first_summary:
            record.metrics["evidence_first"] = evidence_first_summary
        record.metrics["execution_memory"] = checkpoint_status
        record.metrics["workflow_tool_policy_enforced"] = True
        record.metrics["direct_tool_calling_generation"] = False
        record.metrics["memory_context_used"] = {
            "memory_scope": memory_context.get("memory_scope"),
            "parent_run_id": record.request.parent_run_id,
            "feedback_count": len(record.request.user_feedback),
            "starting_hypotheses_count": len(record.request.starting_hypotheses),
            "evidence_summary_count": len(memory_context.get("evidence_summaries", [])),
            "memory_prompt_packet_section_count": int(memory_prompt_packet.get("section_count") or 0),
        }
        if evidence_first_summary:
            record.research_plan["evidence_first"] = evidence_first_summary
        annotate_hypothesis_origins(record)
        apply_citation_provenance_qa(record)
        record.research_outcome = build_research_outcome(record)
        initialize_expert_feedback_state(record)
        add_event(record, "Complete", "Run finalized", f"{len(record.hypotheses)} hypotheses returned", "complete")
        record.status = "complete"
        record.agent_trace = build_live_agent_trace(record, result)
        record.updated_at = time.time()
        if langgraph_checkpoint_summary:
            latest_checkpoint_id = langgraph_checkpoint_summary.get("checkpoint_id")
            persist_run_checkpoint_metadata(
                record,
                status="complete",
                phase="langgraph",
                checkpoint_backend="langgraph_sqlite",
                checkpoint_ref=str(latest_checkpoint_id) if latest_checkpoint_id else None,
                checkpoint_id=f"{record.run_id}:langgraph:{latest_checkpoint_id or 'latest'}",
                state_summary=langgraph_checkpoint_summary,
            )
        persist_run_record(record)
    except Exception as exc:
        record.status = "error"
        record.error = str(exc)
        add_event(record, "Error", "Run failed", str(exc), "error")
        record.updated_at = time.time()
        persist_run_record(record)
    finally:
        if observer_token is not None:
            try:
                reset_mcp_tool_call_observer(observer_token)
            except Exception:
                pass


async def run_with_guard(record: RunRecord, task) -> None:
    persist_run_checkpoint_metadata(record, status="running", phase="workflow")
    try:
        await asyncio.wait_for(task, timeout=RUN_TIMEOUT_SECONDS)
        persist_run_checkpoint_metadata(
            record,
            status=record.status,
            phase="complete" if record.status == "complete" else "terminal",
        )
    except asyncio.TimeoutError:
        record.status = "error"
        record.error = f"Run exceeded {RUN_TIMEOUT_SECONDS} seconds"
        add_event(
            record,
            "Timeout",
            "Run timed out",
            "The backend stopped this run so the UI does not spin forever.",
            "error",
        )
        record.metrics["timeout_seconds"] = RUN_TIMEOUT_SECONDS
        record.updated_at = time.time()
        persist_run_record(record)
        persist_run_checkpoint_metadata(record, status="error", phase="timeout")
    except Exception as exc:
        record.status = "error"
        record.error = str(exc)
        add_event(record, "Error", "Run failed", str(exc), "error")
        record.updated_at = time.time()
        persist_run_record(record)
        persist_run_checkpoint_metadata(record, status="error", phase="exception")


def summarize_evidence_first_discovery(payload: Dict[str, Any], *, library_id: str) -> Dict[str, Any]:
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    auto_ingest = payload.get("auto_ingest") if isinstance(payload.get("auto_ingest"), list) else []
    source_statuses = payload.get("source_statuses") if isinstance(payload.get("source_statuses"), list) else []
    ingested = [item for item in auto_ingest if isinstance(item, dict) and item.get("status") == "ingested"]
    failed = [item for item in auto_ingest if isinstance(item, dict) and item.get("status") == "failed"]
    ready_pdf_count = sum(1 for item in candidates if isinstance(item, dict) and item.get("pdf_url"))
    return {
        "status": payload.get("status") or "limited",
        "library_id": library_id,
        "query": payload.get("query"),
        "message": payload.get("message"),
        "candidate_count": len(candidates),
        "ready_pdf_count": ready_pdf_count,
        "ingested_count": len(ingested),
        "failed_ingest_count": len(failed),
        "source_count": len(source_statuses),
        "tool_count": len(payload.get("tools") or []),
        "auto_ingest": auto_ingest,
        "source_statuses": source_statuses,
        "boundary": (
            "Automatic evidence-first preparation stores discoverable PDF papers in the selected "
            "RAGFlow-style knowledge library before hypothesis generation."
        ),
    }


async def prepare_evidence_first_run(record: RunRecord) -> None:
    request = record.request
    if request.demo_mode or not request.literature_review or not request.auto_discover_papers:
        return

    try:
        library_id = knowledge_base.resolve_library_id(request.library_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "一键研究需要写入目标资料库，但没有找到这个资料库。",
            },
        ) from exc

    request.library_id = library_id
    record.status = "running"
    record.updated_at = time.time()
    add_event(
        record,
        "Evidence",
        "Searching papers",
        "正在按研究主题自动检索论文，并把可解析 PDF 写入当前资料库。",
        "active",
    )
    record.metrics["evidence_first"] = {
        "status": "running",
        "library_id": library_id,
        "candidate_count": 0,
        "ingested_count": 0,
    }
    persist_run_record(record)

    try:
        payload = await discover_literature_for_library(
            LiteratureDiscoveryRequest(
                query=request.research_goal,
                library_id=library_id,
                preferred_source="auto",
                max_results=request.paper_discovery_limit,
                planning_mode="llm",
                model_name=request.model_name,
                auto_discover_pdf_links=True,
                auto_ingest_pdfs=request.auto_ingest_papers,
                auto_ingest_limit=request.paper_ingest_limit,
                approval=ToolWorkflowApproval(
                    confirmed=True,
                    scope="mcp.literature_review",
                    reason="one_click_evidence_first_run",
                ),
            )
        )
        summary = summarize_evidence_first_discovery(payload, library_id=library_id)
        record.metrics["evidence_first"] = summary
        record.research_plan["evidence_first"] = summary
        add_event(
            record,
            "Evidence",
            "Evidence library prepared",
            (
                f"找到 {summary['candidate_count']} 个论文候选，"
                f"发现 {summary['ready_pdf_count']} 个 PDF，"
                f"自动入库 {summary['ingested_count']} 篇。"
            ),
            "complete",
        )
    except Exception as exc:
        summary = {
            "status": "failed",
            "library_id": library_id,
            "query": request.research_goal,
            "message": str(exc)[:500],
            "candidate_count": 0,
            "ingested_count": 0,
            "boundary": "The run continues with the literature review node, but pre-run knowledge-base ingestion failed.",
        }
        record.metrics["evidence_first"] = summary
        record.research_plan["evidence_first"] = summary
        add_event(record, "Evidence", "Evidence preparation limited", summary["message"], "error")
    finally:
        record.updated_at = time.time()
        persist_run_record(record)


async def run_real_evidence_first(record: RunRecord) -> None:
    await prepare_evidence_first_run(record)
    await run_real(record)


def update_autopilot_task(
    run_id: str,
    *,
    status: TaskStatus,
    result_ref: Optional[Dict[str, Any]] = None,
    blocked_reason: Optional[str] = None,
) -> None:
    tasks = knowledge_base.list_research_tasks(
        run_id=run_id,
        task_type="research_autopilot",
        limit=20,
    )
    if not tasks:
        return
    knowledge_base.update_research_task(
        str(tasks[0]["task_id"]),
        status=status,
        result_ref=result_ref or tasks[0].get("result_ref") or {},
        blocked_reason="" if blocked_reason is None else blocked_reason,
    )


async def refresh_run_evidence_packets(record: RunRecord) -> None:
    """Re-ground the stable hypothesis pool after targeted paper acquisition."""
    from open_coscientist.models import Hypothesis
    from open_coscientist.nodes.evidence_grounding import normalize_evidence_packet

    resolver = build_knowledge_base_evidence_resolver(record)
    for hypothesis in record.hypotheses:
        if not isinstance(hypothesis, dict):
            continue
        previous_packet = hypothesis.get("evidence_packet") if isinstance(hypothesis.get("evidence_packet"), dict) else {}
        approved_experiments = [
            dict(item)
            for item in (previous_packet.get("items") or [])
            if isinstance(item, dict)
            and item.get("support_level") == "experimental_data"
            and item.get("source_channel") in {
                "approved_experiment_feedback",
                "policy_evaluated_experiment",
            }
        ]
        resolved = await resolver(hypothesis)
        resolved_items = [item for item in (resolved.get("items") or []) if isinstance(item, dict)]
        known_ids = {
            str(item.get("evidence_id") or item.get("chunk_id") or "")
            for item in resolved_items
        }
        resolved["items"] = [
            *resolved_items,
            *[
                item
                for item in approved_experiments
                if str(item.get("evidence_id") or item.get("chunk_id") or "") not in known_ids
            ],
        ]
        hypothesis["evidence_packet"] = normalize_evidence_packet(
            resolved,
            hypothesis=Hypothesis(text=str(hypothesis.get("text") or "")),
        )
    refresh_run_evidence_snapshot(record)
    apply_citation_provenance_qa(record)
    record.research_outcome = build_research_outcome(record)
    record.updated_at = time.time()
    persist_run_record(record)


async def execute_autopilot_compute(
    record: RunRecord,
    *,
    hypothesis_index: int,
    policy: Dict[str, Any],
    protocol: Dict[str, Any],
    job_id: str,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    compute = dict(policy.get("compute") or {})
    kind = str(compute.get("kind") or "none")
    manifest_compute = dict(compute)
    raw_command = manifest_compute.pop("command", None)
    if isinstance(raw_command, str) and raw_command:
        manifest_compute["command_sha256"] = hashlib.sha256(
            raw_command.encode("utf-8")
        ).hexdigest()
        manifest_compute["command_configured"] = True
    manifest = {"protocol": protocol, "compute": manifest_compute}
    if kind == "local_python":
        tool_name = "experiment.background_job"
        script_path = str(compute.get("script_path") or "")
        guardrail = validate_experiment_script(script_path, experiment_root=EXPERIMENT_ROOT)
        arguments = {
            "script_path": guardrail["script_path"],
            "args": list(compute.get("args") or [])[:50],
            "hypothesis_index": hypothesis_index,
            "autopilot": True,
        }
        existing_job = knowledge_base.get_background_job(job_id)
        if existing_job and existing_job.get("status") != "queued":
            raise ValueError(
                "A durable execution intent already left the queued state; refusing to repeat compute."
            )
        if not existing_job:
            knowledge_base.create_background_job(
                job_id=job_id,
                run_id=record.run_id,
                workflow_name=tool_name,
                phase="experiment_execution",
                arguments=arguments,
            )
        knowledge_base.update_background_job(job_id, status="running")
        result = await asyncio.to_thread(
            run_python_experiment,
            script_path,
            experiment_root=EXPERIMENT_ROOT,
            artifact_root=EXPERIMENT_ARTIFACT_ROOT,
            args=arguments["args"],
            timeout_seconds=int(compute.get("timeout_seconds") or 300),
        )
        result_payload = result.to_dict()
        result_kind = "experiment_run"
        result_summary = f"Autopilot local experiment finished with status={result.status}."
    elif kind == "ssh":
        tool_name = "ssh.training_command"
        server_id = str(compute.get("server_id") or "")
        command = str(compute.get("command") or "")
        workdir = str(compute.get("workdir") or "").strip() or None
        guardrail = validate_ssh_training_command(command, server_id=server_id, workdir=workdir)
        if not guardrail.get("allowed"):
            raise SshTrainingError(str(guardrail.get("message") or "SSH command blocked by guardrail."))
        arguments = {
            "server_id": server_id,
            "command": redact_sensitive_text(command),
            "workdir": workdir,
            "hypothesis_index": hypothesis_index,
            "autopilot": True,
        }
        existing_job = knowledge_base.get_background_job(job_id)
        if existing_job and existing_job.get("status") != "queued":
            raise ValueError(
                "A durable execution intent already left the queued state; refusing to repeat compute."
            )
        if not existing_job:
            knowledge_base.create_background_job(
                job_id=job_id,
                run_id=record.run_id,
                workflow_name=tool_name,
                phase="experiment_execution",
                arguments=arguments,
            )
        knowledge_base.update_background_job(job_id, status="running")
        result = await asyncio.to_thread(
            run_ssh_training_command,
            server_id=server_id,
            command=command,
            workdir=workdir,
            artifact_root=SSH_TRAINING_ARTIFACT_ROOT,
            timeout_seconds=int(compute.get("timeout_seconds") or 3600),
            job_id=job_id,
        )
        result_payload = result.to_dict()
        try:
            result_payload["result_json"] = parse_result_json_marker(str(result_payload.get("stdout") or ""))
        except AutopilotValidationError as exc:
            result_payload["result_json"] = None
            result_payload["result_contract_error"] = str(exc)
        result_kind = "ssh_training_run"
        result_summary = f"Autopilot SSH experiment on {server_id} finished with status={result.status}."
    else:
        raise ValueError("Autopilot compute kind must be local_python or ssh before execution.")

    result_ref = knowledge_base.store_tool_result(
        run_id=record.run_id,
        tool_name=tool_name,
        phase="experiment_execution",
        content={**result_payload, "experiment_manifest": manifest},
        result_kind=result_kind,
        summary=result_summary,
    )
    knowledge_base.record_research_tool_call(
        run_id=record.run_id,
        tool_name=tool_name,
        phase="experiment_execution",
        status=str(result_payload.get("status") or "complete"),
        arguments=arguments,
        result_summary=result_summary,
        metadata={
            "result_ref": result_ref,
            "guardrail": result_payload.get("guardrail") or guardrail,
            "artifacts": result_payload.get("artifacts") or {},
            "approval": {
                "scope": execution_scope(compute),
                "status": "consumed_before_execution",
            },
            "autopilot": True,
        },
    )
    job_result_ref = {
        "tool_result": result_ref,
        "executor": kind,
        "status": result_payload.get("status"),
        "returncode": result_payload.get("returncode"),
        "artifacts": result_payload.get("artifacts") or {},
    }
    knowledge_base.update_background_job(
        job_id,
        status=str(result_payload.get("status") or "complete"),
        result_ref=job_result_ref,
    )
    attach_compute_execution_result(
        run_id=record.run_id,
        hypothesis_index=hypothesis_index,
        job_id=job_id,
        result_payload=result_payload,
        result_ref=result_ref,
        executor=kind,
        manifest=manifest,
    )
    return knowledge_base.get_background_job(job_id) or {}, result_payload, result_ref


async def execute_research_autopilot_work_item(item: Dict[str, Any]) -> Dict[str, Any]:
    run_id = str(item.get("run_id") or item.get("arguments", {}).get("run_id") or "").strip()
    record = load_run_record(run_id)
    if not record:
        raise ValueError(f"Run not found for research autopilot: {run_id}")
    if record.research_loop.get("status") in {"paused", "cancelled", "complete", "reranking"}:
        return {"run_id": run_id, "status": record.research_loop.get("status")}

    policy = validate_autopilot_policy_for_persistence(
        record.research_loop.get("policy") or item.get("arguments", {}).get("policy") or {}
    )
    winner_index, winner = selected_loop_hypothesis(record)
    update_autopilot_task(run_id, status="running")
    evidence_gate = record.research_outcome.get("evidence_gate") if isinstance(record.research_outcome, dict) else {}
    needs_more_evidence = not isinstance(evidence_gate, dict) or evidence_gate.get("status") != "passed"
    expansion = record.research_loop.get("evidence_expansion") if isinstance(record.research_loop, dict) else {}
    expansion_done = isinstance(expansion, dict) and expansion.get("status") == "complete"
    if (
        policy.get("auto_evidence")
        and needs_more_evidence
        and record.request.literature_review
        and not record.request.demo_mode
        and not expansion_done
    ):
        evidence_scope = "mcp.literature_review"
        if not exact_grant(policy, evidence_scope):
            if not policy.get("continue_on_limited_evidence"):
                record.research_loop["pending_approvals"] = [
                    {
                        "scope": evidence_scope,
                        "stage": "acquire_parse",
                        "reason": "Targeted counter-evidence discovery may access the network and write parsed papers to the project library.",
                    }
                ]
                state = persist_loop_stage(
                    record,
                    "acquire_parse",
                    "awaiting_approval",
                    "当前冠军假设证据仍有限；等待任务级文献检索与入库授权。",
                    details={"required_scope": evidence_scope},
                    loop_status="awaiting_approval",
                )
                update_autopilot_task(
                    run_id,
                    status="blocked",
                    blocked_reason=f"Awaiting mission-scoped approval: {evidence_scope}",
                )
                return {"run_id": run_id, "status": state["status"], "research_loop": state}
            persist_loop_stage(
                record,
                "acquire_parse",
                "limited",
                "未授予补充文献检索权限；按策略继续生成实验协议，但不会把证据缺口视为支持。",
                loop_status="running",
            )
        else:
            policy = consume_autopilot_grant(record, policy, evidence_scope)
            record = load_run_record(run_id) or record
            persist_loop_stage(
                record,
                "discover",
                "running",
                "正在围绕冠军假设及其潜在反证执行第二轮定向文献检索。",
                loop_status="running",
            )
            try:
                library_id = knowledge_base.resolve_library_id(record.request.library_id)
                discovery = await discover_literature_for_library(
                    LiteratureDiscoveryRequest(
                        query=(
                            f"{str(winner.get('text') or '')} contradictory evidence failed replication "
                            "negative result alternative explanation"
                        )[:500],
                        library_id=library_id,
                        preferred_source="auto",
                        max_results=record.request.paper_discovery_limit,
                        planning_mode="llm",
                        model_name=record.request.model_name,
                        auto_discover_pdf_links=True,
                        auto_ingest_pdfs=True,
                        auto_ingest_limit=record.request.paper_ingest_limit,
                        approval=ToolWorkflowApproval(
                            confirmed=True,
                            scope=evidence_scope,
                            reason="mission-scoped research autopilot grant",
                        ),
                    )
                )
                expansion_summary = summarize_evidence_first_discovery(discovery, library_id=library_id)
                expansion_summary["status"] = "complete"
                record = load_run_record(run_id) or record
                record.research_loop["evidence_expansion"] = expansion_summary
                persist_loop_stage(
                    record,
                    "acquire_parse",
                    "complete",
                    (
                        f"定向检索得到 {expansion_summary['candidate_count']} 个候选，"
                        f"新增解析 {expansion_summary['ingested_count']} 篇。"
                    ),
                    details=expansion_summary,
                    loop_status="running",
                )
                await refresh_run_evidence_packets(record)
                record = load_run_record(run_id) or record
                persist_loop_stage(
                    record,
                    "ground",
                    "complete" if record.evidence_snapshot.get("evidence_item_count") else "limited",
                    "已用扩展后的知识库重新定位每条假设的支持、反证与证据不足片段。",
                    details={"evidence_snapshot_id": record.evidence_snapshot.get("snapshot_id")},
                    loop_status="running",
                )
                winner_index, winner = selected_loop_hypothesis(record)
            except Exception as exc:
                record = load_run_record(run_id) or record
                record.research_loop["evidence_expansion"] = {
                    "status": "error",
                    "message": str(exc)[:500],
                }
                if not policy.get("continue_on_limited_evidence"):
                    state = persist_loop_stage(
                        record,
                        "acquire_parse",
                        "error",
                        f"定向论文检索或解析失败：{str(exc)[:300]}",
                        loop_status="error",
                    )
                    update_autopilot_task(
                        run_id,
                        status="blocked",
                        blocked_reason="Targeted evidence expansion failed.",
                    )
                    return {"run_id": run_id, "status": state["status"], "research_loop": state}
                persist_loop_stage(
                    record,
                    "acquire_parse",
                    "limited",
                    "补充检索失败；按策略保留证据缺口并继续实验规划。",
                    details={"message": str(exc)[:500]},
                    loop_status="running",
                )
    record = load_run_record(run_id) or record
    evidence_gate = (
        record.research_outcome.get("evidence_gate")
        if isinstance(record.research_outcome, dict)
        else {}
    )
    if (
        (not isinstance(evidence_gate, dict) or evidence_gate.get("status") != "passed")
        and not policy.get("continue_on_limited_evidence")
    ):
        state = persist_loop_stage(
            record,
            "ground",
            "awaiting_input",
            "证据门仍未通过。请补充论文，或显式确认在保留证据缺口的前提下继续。",
            details={"evidence_gate": evidence_gate},
            loop_status="awaiting_input",
        )
        update_autopilot_task(
            run_id,
            status="blocked",
            blocked_reason="Evidence gate did not pass and limited-evidence continuation was not approved.",
            result_ref={"status": state["status"], "current_stage": "ground"},
        )
        return {"run_id": run_id, "status": state["status"], "research_loop": state}

    if not policy.get("auto_plan"):
        state = persist_loop_stage(
            record,
            "plan",
            "awaiting_input",
            "自动实验规划已关闭；请由研究者完善可证伪指标与执行方案后继续。",
            loop_status="awaiting_input",
        )
        update_autopilot_task(
            run_id,
            status="blocked",
            blocked_reason="Experiment planning is in manual mode.",
        )
        return {"run_id": run_id, "status": state["status"], "research_loop": state}
    persist_loop_stage(
        record,
        "plan",
        "running",
        "正在把获胜假设、证据引用和可证伪阈值整理为结构化 ExperimentProtocol。",
        loop_status="running",
    )
    evaluation = dict(policy.get("evaluation") or {})
    protocol = build_experiment_protocol(
        winner,
        winner.get("evidence_packet") if isinstance(winner.get("evidence_packet"), dict) else {},
        policy,
        metric_path=evaluation.get("metric_path"),
        operator=evaluation.get("operator"),
        threshold=evaluation.get("threshold"),
    )
    record = load_run_record(run_id) or record
    record.hypotheses[winner_index]["experiment_protocol"] = protocol
    record.research_loop["experiment_protocol"] = protocol
    knowledge_base.save_project_artifact(
        project_id=run_id,
        run_id=run_id,
        artifact_type="experiment_plan",
        target_ref={
            "hypothesis_index": winner_index,
            "hypothesis_id": winner.get("hypothesis_id"),
        },
        title=str(protocol.get("title") or "Experiment protocol"),
        payload=protocol,
    )
    persist_loop_stage(
        record,
        "plan",
        "complete",
        "结构化实验协议已保存，并绑定到获胜假设及其证据快照。",
        details={"hypothesis_index": winner_index},
        loop_status="running",
    )

    compute = dict(policy.get("compute") or {})
    existing_execution = (
        dict(record.research_loop.get("execution") or {})
        if isinstance(record.research_loop.get("execution"), dict)
        else {}
    )
    has_execution_intent = bool(existing_execution.get("job_id"))
    has_durable_execution = bool(
        existing_execution.get("job_id") and existing_execution.get("result_id")
    )
    if has_execution_intent:
        if existing_execution.get("protocol_id") not in {None, protocol.get("protocol_id")}:
            raise ValueError("Durable execution protocol mismatch; refusing to attach a result to a new protocol.")
        if existing_execution.get("hypothesis_index") not in {None, winner_index}:
            raise ValueError("Durable execution hypothesis mismatch; refusing to reinterpret the job.")
    if not has_execution_intent and (
        not policy.get("auto_execute") or compute.get("kind") in {None, "", "none"}
    ):
        state = persist_loop_stage(
            record,
            "execute",
            "awaiting_input",
            "实验协议已就绪；请选择受限本地 Python 或已登记 SSH 计算目标。",
            loop_status="awaiting_input",
        )
        update_autopilot_task(
            run_id,
            status="blocked",
            blocked_reason="Experiment protocol is ready; a compute target is required.",
            result_ref={"status": state["status"], "current_stage": state.get("current_stage")},
        )
        return {"run_id": run_id, "status": state["status"], "research_loop": state}

    if not has_execution_intent and protocol.get("status") != "preregistered":
        state = persist_loop_stage(
            record,
            "execute",
            "awaiting_input",
            "自动执行前必须先填写 metric_path、operator 和 threshold，形成预注册判定规则。",
            details={"protocol_status": protocol.get("status")},
            loop_status="awaiting_input",
        )
        update_autopilot_task(
            run_id,
            status="blocked",
            blocked_reason="A preregistered metric threshold is required before compute execution.",
            result_ref={"status": state["status"], "protocol_id": protocol.get("protocol_id")},
        )
        return {"run_id": run_id, "status": state["status"], "research_loop": state}

    required_scope = execution_scope(compute)
    if not has_execution_intent and not exact_grant(
        policy,
        required_scope,
        compute_target=compute,
    ):
        record.research_loop["pending_approvals"] = [
            {
                "scope": required_scope,
                "stage": "execute",
                "reason": "Mission-scoped approval is required for this compute target.",
                "server_id": compute.get("server_id"),
            }
        ]
        state = persist_loop_stage(
            record,
            "execute",
            "awaiting_approval",
            f"计算任务已准备，但缺少限定授权：{required_scope}。",
            details={"required_scope": required_scope, "compute_kind": compute.get("kind")},
            loop_status="awaiting_approval",
        )
        update_autopilot_task(
            run_id,
            status="blocked",
            blocked_reason=f"Awaiting mission-scoped approval: {required_scope}",
            result_ref={"status": state["status"], "required_scope": required_scope},
        )
        return {"run_id": run_id, "status": state["status"], "research_loop": state}

    if not has_execution_intent:
        policy = consume_autopilot_grant(
            record,
            policy,
            str(required_scope),
            server_id=str(compute.get("server_id") or "") or None,
        )
        record = load_run_record(run_id) or record
        execution_job_id = autopilot_execution_job_id(record, protocol)
        record.research_loop["execution"] = {
            "job_id": execution_job_id,
            "executor": compute.get("kind"),
            "status": "prepared",
            "protocol_id": protocol.get("protocol_id"),
            "hypothesis_index": winner_index,
            "hypothesis_id": winner.get("hypothesis_id"),
            "boundary": "A persisted execution intent is not evidence that the command ran.",
        }
        persist_loop_stage(
            record,
            "execute",
            "running",
            f"已锁定执行意图，准备通过 {compute.get('kind')} 运行预注册实验。",
            details={"job_id": execution_job_id, "protocol_id": protocol.get("protocol_id")},
            loop_status="running",
        )
        existing_execution = dict(record.research_loop["execution"])
        has_execution_intent = True

    if has_durable_execution:
        job = knowledge_base.get_background_job(str(existing_execution["job_id"])) or {}
        stored_result = knowledge_base.get_tool_result(str(existing_execution["result_id"])) or {}
        result_payload = stored_result.get("content") if isinstance(stored_result.get("content"), dict) else {}
        result_ref = {key: value for key, value in stored_result.items() if key != "content"}
        if not job or not result_payload:
            raise ValueError("Durable experiment references are incomplete; refusing to repeat compute automatically.")
    else:
        execution_job_id = str(existing_execution["job_id"])
        existing_job = knowledge_base.get_background_job(execution_job_id)
        if existing_job and existing_job.get("result_ref", {}).get("tool_result", {}).get("result_id"):
            recovered_result_id = str(existing_job["result_ref"]["tool_result"]["result_id"])
            stored_result = knowledge_base.get_tool_result(recovered_result_id) or {}
            result_payload = (
                stored_result.get("content")
                if isinstance(stored_result.get("content"), dict)
                else {}
            )
            result_ref = {key: value for key, value in stored_result.items() if key != "content"}
            job = existing_job
            if not result_payload:
                raise ValueError("The durable job references a missing result; refusing to repeat compute.")
        elif existing_job and existing_job.get("status") != "queued":
            state = persist_loop_stage(
                record,
                "execute",
                "awaiting_human",
                (
                    "执行意图已经离开 queued 状态，但没有可核验的结果引用。"
                    "为避免重复运行本地或远程命令，系统已停止自动重试。"
                ),
                details={
                    "job_id": execution_job_id,
                    "job_status": existing_job.get("status"),
                    "recovery": "Inspect the registered server/job artifacts, then attach or rerun explicitly.",
                },
                loop_status="awaiting_human",
            )
            update_autopilot_task(
                run_id,
                status="blocked",
                blocked_reason="Execution outcome is uncertain; automatic replay is disabled.",
                result_ref={"status": state["status"], "job_id": execution_job_id},
            )
            return {"run_id": run_id, "status": state["status"], "research_loop": state}
        else:
            record = load_run_record(run_id) or record
            record.research_loop["execution"]["status"] = "running"
            persist_loop_stage(
                record,
                "execute",
                "running",
                f"正在通过 {compute.get('kind')} 执行预注册实验。",
                details={"job_id": execution_job_id},
                loop_status="running",
            )
            job, result_payload, result_ref = await execute_autopilot_compute(
                record,
                hypothesis_index=winner_index,
                policy=policy,
                protocol=protocol,
                job_id=execution_job_id,
            )
        record = load_run_record(run_id) or record
        record.research_loop["execution"] = {
            "job_id": job.get("job_id"),
            "executor": compute.get("kind"),
            "status": result_payload.get("status"),
            "returncode": result_payload.get("returncode"),
            "result_id": result_ref.get("result_id"),
            "artifacts": result_payload.get("artifacts") or {},
            "protocol_id": protocol.get("protocol_id"),
            "hypothesis_index": winner_index,
            "hypothesis_id": winner.get("hypothesis_id"),
            "boundary": "Execution completion is not a scientific verdict.",
        }
        persist_loop_stage(
            record,
            "execute",
            "complete" if result_payload.get("status") == "complete" else "error",
            f"计算任务结束，returncode={result_payload.get('returncode')}。",
            loop_status="running",
        )

    try:
        if result_payload.get("status") != "complete":
            raise AutopilotValidationError(
                f"Execution ended with status={result_payload.get('status')}; no scientific verdict was inferred."
            )
        evaluation_result = evaluate_experiment_result(protocol, result_payload.get("result_json") or {})
    except AutopilotValidationError as exc:
        evaluation_result = {
            "protocol_id": protocol.get("protocol_id"),
            "verdict": "inconclusive",
            "relationship": "insufficient",
            "rationale": str(exc),
            "confidence": 0.0,
            "scientific_boundary": protocol.get("scientific_boundary"),
        }
    record = load_run_record(run_id) or record
    record.research_loop["interpretation"] = evaluation_result
    verdict = str(evaluation_result.get("verdict") or "inconclusive")
    existing_evidence_id = str(record.research_loop.get("interpretation_evidence_id") or "")
    can_auto_interpret = (
        bool(existing_evidence_id)
        or (
            bool(policy.get("auto_interpret"))
            and verdict in {"support", "contradict"}
            and exact_grant(policy, "experiment.feedback")
        )
    )
    if not can_auto_interpret:
        pending = [] if verdict == "inconclusive" else [
            {
                "scope": "experiment.feedback",
                "stage": "review",
                "reason": "Adopt the preregistered metric comparison as scientific evidence.",
            }
        ]
        record.research_loop["pending_approvals"] = pending
        state = persist_loop_stage(
            record,
            "review",
            "awaiting_human",
            str(evaluation_result.get("rationale") or "实验结果需要研究者解释。"),
            details={"proposed_verdict": verdict, "job_id": job.get("job_id")},
            loop_status="awaiting_human",
        )
        update_autopilot_task(
            run_id,
            status="blocked",
            blocked_reason="Experiment result requires human scientific interpretation.",
            result_ref={"status": state["status"], "job_id": job.get("job_id")},
        )
        return {"run_id": run_id, "status": state["status"], "research_loop": state}

    feedback_request = ExperimentFeedbackRequest(
        job_id=str(job["job_id"]),
        hypothesis_index=winner_index,
        verdict=verdict,
        rationale=str(evaluation_result.get("rationale") or "Pre-registered metric threshold evaluated."),
        rerank=False,
        approval=ToolWorkflowApproval(
            confirmed=True,
            scope="experiment.feedback",
            reason="mission-scoped autopilot grant with pre-registered metric threshold",
        ),
    )
    if existing_evidence_id:
        packet = record.hypotheses[winner_index].get("evidence_packet") or {}
        evidence_item = next(
            (
                dict(item)
                for item in (packet.get("items") or [])
                if isinstance(item, dict) and item.get("evidence_id") == existing_evidence_id
            ),
            {"evidence_id": existing_evidence_id},
        )
    else:
        policy = consume_autopilot_grant(record, policy, "experiment.feedback")
        record = load_run_record(run_id) or record
        evidence_item = apply_experiment_feedback_to_record(
            record,
            feedback_request,
            job,
            source_channel="policy_evaluated_experiment",
            relationship_confidence=float(evaluation_result.get("confidence") or 0.9),
            persist_loop_marker=True,
        )
    feedback = FeedbackItem(
        target_type="experiment",
        target_ref={
            "hypothesis_index": winner_index,
            "job_id": job.get("job_id"),
            "evidence_id": evidence_item.get("evidence_id"),
        },
        feedback_type="accept" if verdict == "support" else "reject",
        text=f"Pre-registered experiment verdict={verdict}. {feedback_request.rationale}",
    )
    feedback_id = f"feedback_autopilot_{hashlib.sha256(str(job['job_id']).encode('utf-8')).hexdigest()[:20]}"
    knowledge_base.store_feedback_item(
        feedback_id=feedback_id,
        run_id=run_id,
        target_type=feedback.target_type,
        target_ref=feedback.target_ref,
        feedback_type=feedback.feedback_type,
        text=feedback.text,
        source="research_autopilot",
    )
    record = load_run_record(run_id) or record
    record.research_loop["feedback_id"] = feedback_id
    persist_loop_stage(
        record,
        "review",
        "complete",
        f"预注册指标产生 {verdict} 结论，并已写回结构化实验证据。",
        details={"evidence_id": evidence_item.get("evidence_id")},
        loop_status="running",
    )

    if policy.get("auto_rerank"):
        starting_hypotheses = [
            str(hypothesis.get("text") or "").strip()
            for hypothesis in record.hypotheses
            if isinstance(hypothesis, dict) and str(hypothesis.get("text") or "").strip()
        ]
        existing_child = find_autopilot_rerank_child(run_id, str(job["job_id"]))
        if existing_child:
            rerank_run: Dict[str, Any] = {"run_id": existing_child.run_id, "recovered": True}
        else:
            rerank_run = await continue_run(
                run_id,
                ContinueRunRequest(
                    demo_mode=record.request.demo_mode,
                    literature_review=record.request.literature_review,
                    initial_hypotheses=min(8, max(1, len(starting_hypotheses))),
                    iterations=0,
                    starting_hypotheses=starting_hypotheses[:8],
                    user_feedback=[feedback],
                    refinement_mode="revise_hypotheses",
                    memory_scope=record.request.memory_scope,
                    library_id=record.request.library_id,
                    auto_discover_papers=False,
                    auto_ingest_papers=False,
                ),
            )
        record = load_run_record(run_id) or record
        record.research_loop["rerank_run_id"] = rerank_run.get("run_id")
        state = persist_loop_stage(
            record,
            "rerank",
            "running",
            "实验反馈已进入 continuation run；系统会在完成前核验实验级证据的假设 lineage。",
            details={"rerank_run_id": rerank_run.get("run_id")},
            loop_status="reranking",
        )
        update_autopilot_task(
            run_id,
            status="running",
            result_ref={"status": state["status"], "rerank_run_id": rerank_run.get("run_id")},
        )
        return {"run_id": run_id, "status": state["status"], "rerank_run": rerank_run}

    state = persist_loop_stage(
        record,
        "outcome",
        "complete",
        "实验解释、证据快照和 ResearchOutcome 已更新。",
        loop_status="complete",
    )
    update_autopilot_task(run_id, status="done", result_ref={"status": "complete"})
    return {"run_id": run_id, "status": state["status"], "research_loop": state}


def finalize_parent_autopilot_rerank(record: RunRecord) -> None:
    parent_run_id = record.request.parent_run_id
    if not parent_run_id:
        return
    parent = load_run_record(parent_run_id)
    if not parent or parent.research_loop.get("rerank_run_id") != record.run_id:
        return
    if record.status == "complete":
        expected_evidence_id = str(parent.research_loop.get("interpretation_evidence_id") or "")
        inherited_matches = [
            item
            for hypothesis in record.hypotheses
            if isinstance(hypothesis, dict)
            for item in ((hypothesis.get("evidence_packet") or {}).get("items") or [])
            if isinstance(item, dict) and item.get("evidence_id") == expected_evidence_id
        ]
        lineage_verified = bool(
            expected_evidence_id
            and any(item.get("lineage_status") == "exact" for item in inherited_matches)
        )
        parent.research_loop["rerank_outcome"] = {
            "run_id": record.run_id,
            "winner_id": record.research_outcome.get("winner_id"),
            "winner_index": record.research_outcome.get("winner_index"),
            "evidence_snapshot_id": record.research_outcome.get("evidence_snapshot_id"),
            "status": record.research_outcome.get("status"),
            "experimental_lineage_verified": lineage_verified,
            "expected_evidence_id": expected_evidence_id,
        }
        if not lineage_verified:
            state = persist_loop_stage(
                parent,
                "rerank",
                "awaiting_human",
                (
                    "Continuation Review/Elo 已完成，但获胜实验的证据 lineage 未能精确映射到修订后的假设。"
                    "系统不会把相似文本自动当作同一科学命题。"
                ),
                details={
                    "rerank_run_id": record.run_id,
                    "expected_evidence_id": expected_evidence_id,
                    "matching_items": len(inherited_matches),
                },
                loop_status="awaiting_human",
            )
            update_autopilot_task(
                parent_run_id,
                status="blocked",
                blocked_reason="Rerank completed, but experimental evidence lineage requires review.",
                result_ref={"status": state["status"], "rerank_run_id": record.run_id},
            )
            return
        parent.research_loop = update_loop_stage(
            parent.research_loop,
            "rerank",
            "complete",
            summary="Continuation Review/Elo completed with exact experimental-evidence lineage.",
            details={"rerank_run_id": record.run_id},
        )
        persist_loop_stage(
            parent,
            "outcome",
            "complete",
            "闭环完成：论文证据、预注册实验、结果解释与重新排名均已留下可追溯记录。",
            details={"rerank_run_id": record.run_id},
            loop_status="complete",
        )
        update_autopilot_task(
            parent_run_id,
            status="done",
            result_ref={"status": "complete", "rerank_run_id": record.run_id},
        )
    elif record.status == "error":
        persist_loop_stage(
            parent,
            "rerank",
            "error",
            record.error or "Continuation reranking failed.",
            details={"rerank_run_id": record.run_id},
            loop_status="error",
        )
        update_autopilot_task(
            parent_run_id,
            status="blocked",
            blocked_reason=record.error or "Continuation reranking failed.",
        )


async def execute_open_coscientist_run_work_item(item: Dict[str, Any]) -> Dict[str, Any]:
    run_id = str(item.get("run_id") or item.get("arguments", {}).get("run_id") or "").strip()
    if not run_id:
        raise ValueError("workflow.open_coscientist_run work item requires run_id")
    payload = knowledge_base.get_research_run(run_id)
    if not payload:
        raise ValueError(f"Run not found for work item: {run_id}")
    record = RunRecord(**payload)
    runs[run_id] = record
    task = run_demo(record) if record.request.demo_mode else run_real_evidence_first(record)
    await run_with_guard(record, task)
    if record.status != "complete":
        for research_task in knowledge_base.list_research_tasks(
            run_id=run_id,
            task_type="scheduled_workflow",
            limit=50,
        ):
            knowledge_base.update_research_task(
                str(research_task["task_id"]),
                status="blocked",
                blocked_reason=record.error or f"Run ended with status {record.status}",
                result_ref={"run_id": run_id, "status": record.status},
            )
        raise RuntimeError(record.error or f"Run ended with status {record.status}")
    finalize_parent_autopilot_rerank(record)
    if record.request.autopilot and normalize_policy(record.request.autopilot).get("mode") != "manual":
        enqueue_research_autopilot(record, record.request.autopilot)
    for research_task in knowledge_base.list_research_tasks(
        run_id=run_id,
        task_type="scheduled_workflow",
        limit=50,
    ):
        knowledge_base.update_research_task(
            str(research_task["task_id"]),
            status="done",
            result_ref={
                "run_id": run_id,
                "status": record.status,
                "winner_id": record.research_outcome.get("winner_id"),
            },
        )
    return {"run_id": run_id, "status": record.status}


def build_worker_runtime() -> ResearchWorkerRuntime:
    return ResearchWorkerRuntime(
        store=knowledge_base,
        handlers={
            "workflow.open_coscientist_run": execute_open_coscientist_run_work_item,
            AUTOPILOT_WORKFLOW: execute_research_autopilot_work_item,
        },
        schedule_handler=dispatch_due_research_schedules,
        owner=WORKER_OWNER,
        concurrency=WORKER_CONCURRENCY,
        lease_seconds=WORKER_LEASE_SECONDS,
        poll_seconds=WORKER_POLL_SECONDS,
        enabled=WORKER_AUTOSTART_ENABLED,
    )


@app.on_event("startup")
async def start_research_worker_runtime() -> None:
    global worker_runtime
    try:
        await asyncio.to_thread(_get_research_chat_llm_module)
    except Exception as exc:
        print(f"Research chat LLM module warmup failed: {exc}", file=sys.stderr)
    if worker_runtime is None:
        worker_runtime = build_worker_runtime()
    if WORKER_AUTOSTART_ENABLED:
        await worker_runtime.start()


@app.on_event("shutdown")
async def stop_research_worker_runtime() -> None:
    if worker_runtime is not None:
        await worker_runtime.stop()


def auth_success_payload(code: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **payload,
        "ok": True,
        "code": code,
        "http_status": 200,
    }


def auth_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "ok": False,
            "code": code,
            "message": message,
            "http_status": status_code,
        },
    )


def classify_register_error(message: str) -> tuple[int, str]:
    if "已存在" in message:
        return 409, "auth.register.account_exists"
    if "密码" in message:
        return 400, "auth.register.weak_password"
    if "邮箱" in message:
        return 400, "auth.register.invalid_email"
    return 400, "auth.register.invalid_request"


def classify_login_exception(exc: HTTPException) -> tuple[int, str, str]:
    detail = str(exc.detail)
    if exc.status_code == 403:
        return 403, "auth.login.account_disabled", detail
    if exc.status_code == 401:
        return 401, "auth.login.invalid_credentials", detail
    return exc.status_code, "auth.login.failed", detail


@app.post("/api/auth/register")
async def register_account(request: AuthRegisterRequest) -> Dict[str, Any]:
    try:
        user = create_account(
            request.email,
            request.password,
            display_name=request.display_name,
            role="researcher",
            recovery_question=request.recovery_question,
            recovery_answer=request.recovery_answer,
        )
    except ValueError as exc:
        message = str(exc)
        status_code, code = classify_register_error(message)
        raise auth_error(status_code, code, message) from exc
    try:
        session = authenticate(user["email"], request.password)
    except HTTPException as exc:
        status_code, code, message = classify_login_exception(exc)
        raise auth_error(status_code, code, message) from exc
    return auth_success_payload("auth.register.success", session)


@app.post("/api/auth/recovery/challenge")
async def recovery_challenge(request: AuthRecoveryChallengeRequest) -> Dict[str, Any]:
    try:
        challenge = get_recovery_challenge(request.email)
    except ValueError as exc:
        raise auth_error(400, "auth.recovery.invalid_email", str(exc)) from exc
    return {"ok": True, **challenge}


@app.post("/api/auth/recovery/reset")
async def recovery_reset_password(request: AuthRecoveryResetRequest) -> Dict[str, Any]:
    try:
        user = reset_password_with_recovery(request.email, request.answer, request.new_password)
        session = authenticate(user["email"], request.new_password)
    except ValueError as exc:
        message = str(exc)
        code = "auth.recovery.invalid_answer" if "答案" in message else "auth.recovery.unavailable"
        raise auth_error(400, code, message) from exc
    except HTTPException as exc:
        status_code, code, message = classify_login_exception(exc)
        raise auth_error(status_code, code, message) from exc
    return auth_success_payload("auth.recovery.reset_success", session)


@app.post("/api/auth/login")
async def login_account(request: AuthLoginRequest) -> Dict[str, Any]:
    try:
        session = authenticate(request.email, request.password)
    except ValueError as exc:
        message = str(exc)
        raise auth_error(400, "auth.login.invalid_email", message) from exc
    except HTTPException as exc:
        status_code, code, message = classify_login_exception(exc)
        raise auth_error(status_code, code, message) from exc
    return auth_success_payload("auth.login.success", session)


@app.get("/api/auth/me")
async def current_account(user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    return {"user": user}


@app.post("/api/auth/logout")
async def logout_account(user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    return {"ok": True, "user_id": user["id"]}


@app.get("/api/auth/roles")
async def auth_roles() -> Dict[str, Any]:
    return {"roles": list(role_rows())}


def remote_workspace_http_error(exc: RemoteWorkspaceError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "remote_workspace_failed", "message": str(exc)})


async def run_remote_workspace_call(
    fn: Callable[..., Dict[str, Any]],
    *args: Any,
    timeout_seconds: float = 25,
    **kwargs: Any,
) -> Dict[str, Any]:
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *args, **kwargs), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={"code": "remote_workspace_timeout", "message": "远程服务器连接超时，请切换服务器或稍后重试。"},
        ) from exc


@app.get("/api/remote-workspaces/status")
async def get_remote_workspace_status() -> Dict[str, Any]:
    return remote_workspace_status()


@app.get("/api/remote-workspaces/ssh-config-hosts")
async def get_remote_workspace_ssh_config_hosts() -> Dict[str, Any]:
    try:
        return {"mode": "unrestricted", "hosts": parse_ssh_config()}
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc


@app.get("/api/remote-workspaces/profiles")
async def get_remote_workspace_profiles() -> Dict[str, Any]:
    try:
        return {"mode": "unrestricted", "profiles": list_remote_workspace_profiles(REMOTE_WORKSPACE_STORE_PATH)}
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc


@app.post("/api/remote-workspaces/profiles")
async def save_remote_workspace_profile_endpoint(request: RemoteWorkspaceProfileRequest) -> Dict[str, Any]:
    try:
        profile = save_remote_workspace_profile(REMOTE_WORKSPACE_STORE_PATH, request.model_dump())
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc
    return {"mode": "unrestricted", "profile": profile}


@app.post("/api/remote-workspaces/profiles/import-ssh-config")
async def import_remote_workspace_profile_endpoint(request: RemoteWorkspaceImportRequest) -> Dict[str, Any]:
    try:
        profile = import_ssh_config_profile(
            REMOTE_WORKSPACE_STORE_PATH,
            request.alias,
            password=request.password,
            default_remote_path_value=request.default_remote_path,
        )
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc
    return {"mode": "unrestricted", "profile": profile}


@app.delete("/api/remote-workspaces/profiles/{profile_id}")
async def delete_remote_workspace_profile_endpoint(profile_id: str) -> Dict[str, Any]:
    try:
        return delete_remote_workspace_profile(REMOTE_WORKSPACE_STORE_PATH, profile_id)
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc


@app.get("/api/remote-workspaces/profiles/{profile_id}/ls")
async def list_remote_workspace_directory_endpoint(profile_id: str, path: Optional[str] = None) -> Dict[str, Any]:
    try:
        return await run_remote_workspace_call(list_remote_directory, REMOTE_WORKSPACE_STORE_PATH, profile_id, path)
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "remote_directory_list_failed", "message": str(exc)}) from exc


@app.get("/api/projects/{project_id}/remote-root")
async def get_project_remote_root_endpoint(project_id: str) -> Dict[str, Any]:
    try:
        root = get_project_remote_root(REMOTE_WORKSPACE_STORE_PATH, project_id)
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc
    return {"mode": "unrestricted", "remote_root": root}


@app.post("/api/projects/{project_id}/remote-root")
async def set_project_remote_root_endpoint(project_id: str, request: ProjectRemoteRootRequest) -> Dict[str, Any]:
    try:
        root = set_project_remote_root(
            REMOTE_WORKSPACE_STORE_PATH,
            project_id,
            request.profile_id,
            request.remote_path,
            request.label,
        )
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc
    return {"mode": "unrestricted", "remote_root": root}


@app.get("/api/remote-workspaces/profiles/{profile_id}/tmux")
async def list_remote_workspace_tmux_endpoint(profile_id: str, path: Optional[str] = None) -> Dict[str, Any]:
    try:
        return await run_remote_workspace_call(list_tmux_sessions, REMOTE_WORKSPACE_STORE_PATH, profile_id, path)
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "remote_tmux_list_failed", "message": str(exc)}) from exc


@app.post("/api/remote-workspaces/profiles/{profile_id}/tmux")
async def create_remote_workspace_tmux_endpoint(profile_id: str, request: RemoteTmuxCreateRequest) -> Dict[str, Any]:
    try:
        session = await run_remote_workspace_call(create_tmux_session, REMOTE_WORKSPACE_STORE_PATH, profile_id, request.name, request.workdir)
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc
    return {"mode": "unrestricted", "session": session}


@app.post("/api/remote-workspaces/profiles/{profile_id}/tmux/{session_name}/kill")
async def kill_remote_workspace_tmux_endpoint(profile_id: str, session_name: str) -> Dict[str, Any]:
    try:
        return {
            "mode": "unrestricted",
            "session": await run_remote_workspace_call(kill_tmux_session, REMOTE_WORKSPACE_STORE_PATH, profile_id, session_name),
        }
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc


@app.post("/api/remote-workspaces/profiles/{profile_id}/tmux/{session_name}/rename")
async def rename_remote_workspace_tmux_endpoint(profile_id: str, session_name: str, request: RemoteTmuxRenameRequest) -> Dict[str, Any]:
    try:
        return {
            "mode": "unrestricted",
            "session": await run_remote_workspace_call(
                rename_tmux_session,
                REMOTE_WORKSPACE_STORE_PATH,
                profile_id,
                session_name,
                request.new_name,
            ),
        }
    except RemoteWorkspaceError as exc:
        raise remote_workspace_http_error(exc) from exc


@app.get("/api/web-terminal/status")
async def get_web_terminal_status() -> Dict[str, Any]:
    return web_terminal_status()


@app.get("/api/web-terminal/sessions")
async def get_web_terminal_sessions() -> Dict[str, Any]:
    return {
        "mode": "unrestricted",
        "sessions": list_web_terminal_sessions(),
    }


@app.post("/api/web-terminal/sessions")
async def create_web_terminal_endpoint(request: WebTerminalSessionCreateRequest) -> Dict[str, Any]:
    try:
        session = create_web_terminal_session(
            profile_id=request.profile,
            cwd=request.cwd,
            default_root=ROOT,
            cols=request.cols,
            rows=request.rows,
            ssh_target=request.ssh_target,
            ssh_remote_cwd=request.ssh_remote_cwd,
            ssh_tmux_session=request.ssh_tmux_session,
        )
    except WebTerminalError as exc:
        raise HTTPException(status_code=400, detail={"code": "web_terminal_create_failed", "message": str(exc)}) from exc
    return {
        "mode": "unrestricted",
        "session": session.public_dict(),
        "websocket_path": f"/api/web-terminal/sessions/{session.session_id}/ws",
    }


@app.delete("/api/web-terminal/sessions/{session_id}")
async def close_web_terminal_endpoint(session_id: str) -> Dict[str, Any]:
    close_web_terminal_session(session_id)
    return {"ok": True, "session_id": session_id}


@app.websocket("/api/web-terminal/sessions/{session_id}/ws")
async def web_terminal_socket(websocket: WebSocket, session_id: str) -> None:
    try:
        session = get_web_terminal_session(session_id)
    except WebTerminalError:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    loop = asyncio.get_running_loop()
    output_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
    stop_event = threading.Event()

    def reader() -> None:
        while not stop_event.is_set() and session.process.isalive():
            try:
                data = session.process.read(4096)
            except Exception as exc:
                loop.call_soon_threadsafe(output_queue.put_nowait, {"type": "error", "message": str(exc)})
                break
            if data:
                loop.call_soon_threadsafe(output_queue.put_nowait, {"type": "output", "data": data})
            else:
                time.sleep(0.02)
        loop.call_soon_threadsafe(output_queue.put_nowait, {"type": "exit"})

    reader_thread = threading.Thread(target=reader, name=f"web-terminal-{session_id}", daemon=True)
    reader_thread.start()

    async def sender() -> None:
        while True:
            payload = await output_queue.get()
            await websocket.send_json(payload)
            if payload.get("type") == "exit":
                break

    sender_task = asyncio.create_task(sender())
    try:
        await websocket.send_json({"type": "ready", "session": session.public_dict()})
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"type": "input", "data": raw}
            message_type = payload.get("type")
            if message_type == "input":
                session.process.write(str(payload.get("data") or ""))
            elif message_type == "resize":
                rows = int(payload.get("rows") or 30)
                cols = int(payload.get("cols") or 100)
                session.process.resize(max(8, min(rows, 120)), max(20, min(cols, 400)))
            elif message_type == "close":
                break
    except WebSocketDisconnect:
        pass
    finally:
        stop_event.set()
        sender_task.cancel()
        close_web_terminal_session(session_id)
        with contextlib.suppress(asyncio.CancelledError, RuntimeError):
            await sender_task


@app.get("/api/literature-service/status")
async def literature_service_status(user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    return {"runtime": literature_mcp_runtime_status(), "actor": user}


@app.post("/api/literature-service/start")
async def literature_service_start(user: Dict[str, Any] = Depends(require_user)) -> Dict[str, Any]:
    runtime = await asyncio.to_thread(start_literature_mcp_service)
    mcp_status = await asyncio.to_thread(probe_mcp_server)
    return {"runtime": runtime, "literature_mcp": public_mcp_status(mcp_status), "actor": user}


@app.get("/api/admin/users")
async def admin_list_users(admin: Dict[str, Any] = Depends(require_permission("users:manage"))) -> Dict[str, Any]:
    return {"users": list_accounts(), "actor": admin}


@app.post("/api/admin/users")
async def admin_create_user(
    request: AdminAccountCreateRequest,
    admin: Dict[str, Any] = Depends(require_permission("users:manage")),
) -> Dict[str, Any]:
    try:
        user = create_account(
            request.email,
            request.password,
            display_name=request.display_name,
            role=request.role,
        )
        secret_path = record_local_account_secret(
            user,
            request.password,
            source="admin_create_user",
            actor_email=admin.get("email", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user, "actor": admin, "local_secret_path": str(secret_path)}


@app.put("/api/admin/users/{account_id}/status")
async def admin_update_user_status(
    account_id: str,
    request: AdminAccountStatusRequest,
    admin: Dict[str, Any] = Depends(require_permission("users:manage")),
) -> Dict[str, Any]:
    try:
        user = set_account_status(account_id, request.status)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user, "actor": admin}


@app.put("/api/admin/users/{account_id}/password")
async def admin_reset_user_password(
    account_id: str,
    request: AdminAccountPasswordRequest,
    admin: Dict[str, Any] = Depends(require_permission("users:manage")),
) -> Dict[str, Any]:
    try:
        user = reset_account_password(account_id, request.password)
        secret_path = record_local_account_secret(
            user,
            request.password,
            source="admin_reset_password",
            actor_email=admin.get("email", ""),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user, "actor": admin, "local_secret_path": str(secret_path)}


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return await build_health_payload(debug=False)


@app.get("/api/health/debug")
async def health_debug() -> Dict[str, Any]:
    return await build_health_payload(debug=True)


@app.get("/api/agents/registry")
async def get_agent_registry(disabled_phases: Optional[str] = None) -> Dict[str, Any]:
    from open_coscientist.agents.registry import get_agent_registry_payload

    disabled_phase_list = [
        phase.strip()
        for phase in str(disabled_phases or "").split(",")
        if phase.strip()
    ]
    return get_agent_registry_payload(public=True, disabled_phases=disabled_phase_list)


@app.get("/api/tools/registry")
async def get_tool_registry(
    phase: Optional[str] = None,
    toolset: Optional[str] = None,
) -> Dict[str, Any]:
    registry = research_tool_registry()
    tools = registry.list_tools(phase=phase, toolset=toolset)
    virtual_register = _virtual_tool_register_spec()
    if _virtual_tool_matches_filters(virtual_register, phase=phase, toolset=toolset):
        tools.append(virtual_register)
    tools.extend(_project_tool_registry_tools(phase=phase, toolset=toolset))
    return {
        "tools": tools,
        "count": len(tools),
        "phase": phase,
        "toolset": toolset,
    }


@app.get("/api/tools/toolsets")
async def get_toolsets() -> Dict[str, Any]:
    registry = research_tool_registry()
    toolsets = registry.list_toolsets()
    toolsets.append(
        {
            "toolset": "tool_management",
            "tools": ["tool.register_draft"],
            "risk_levels": ["write"],
            "phases": ["operator_diagnostics", "supervisor"],
        }
    )
    project_tools = _project_tool_registry_tools()
    if project_tools:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for tool in project_tools:
            grouped.setdefault(str(tool.get("toolset") or "project_custom"), []).append(tool)
        for toolset_name, tools in sorted(grouped.items()):
            toolsets.append(
                {
                    "toolset": toolset_name,
                    "tools": sorted(str(tool.get("name")) for tool in tools if tool.get("name")),
                    "risk_levels": sorted({str(tool.get("risk_level") or "read") for tool in tools}),
                    "phases": sorted({str(phase) for tool in tools for phase in (tool.get("phases") or [])}),
                }
            )
    return {"toolsets": toolsets, "count": len(toolsets)}


@app.get("/api/tools/policies")
async def get_tool_policies() -> Dict[str, Any]:
    policies = list_phase_tool_policies()
    return {"policies": policies, "count": len(policies)}


@app.get("/api/tools/command-permissions")
async def get_command_permissions() -> Dict[str, Any]:
    policy = get_command_permission_policy(KB_ROOT)
    return {
        "policy": policy,
        "terminal": terminal_command_status(),
        "ssh": ssh_training_status(),
    }


@app.put("/api/tools/command-permissions")
async def update_command_permissions(
    request: CommandPermissionUpdateRequest,
    actor: Dict[str, Any] = Depends(require_permission("runtime:write")),
) -> Dict[str, Any]:
    try:
        policy = set_command_permission_policy(KB_ROOT, request.mode, actor=actor.get("email"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "invalid_command_permission_mode", "message": str(exc)})
    return {
        "policy": policy,
        "terminal": terminal_command_status(),
        "ssh": ssh_training_status(),
        "actor": actor,
    }


@app.post("/api/tools/execute")
async def execute_research_tool(request: ToolExecuteRequest) -> Dict[str, Any]:
    registry = research_tool_registry()
    spec = registry.get(request.tool_name)
    if not spec:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "tool_not_found",
                "message": "没有找到这个科研工具。请先通过工具注册表确认名称。",
            },
        )

    phase = canonical_phase(request.phase)
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={
                key: value
                for key, value in authorization.items()
                if key != "allowed"
            },
        )

    description = spec.describe()
    availability = description["availability"]
    if not availability.get("available"):
        raise HTTPException(
            status_code=424,
            detail={
                "code": "tool_unavailable",
                "message": "这个工具当前不可用，请先查看 availability 诊断。",
                "availability": availability,
            },
        )

    if spec.risk_level != "read":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "tool_requires_dedicated_workflow",
                "message": "当前通用执行入口只允许 read-risk 工具；写入、网络、后台或沙箱工具需要专用工作流和审批。",
                "risk_level": spec.risk_level,
            },
        )

    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    args = request.arguments or {}
    guardrail = evaluate_tool_execution_guardrail(
        run_id=request.run_id,
        tool_name=request.tool_name,
        phase=phase,
        arguments=args,
    )
    if not guardrail["allowed"]:
        raise HTTPException(
            status_code=409,
            detail={
                key: value
                for key, value in guardrail.items()
                if key != "allowed"
            },
        )

    query_for_retrieval = ""
    limit_value = 0
    if request.tool_name == "knowledge_base.rag_search":
        query = str(args.get("query") or args.get("q") or "").strip()
        if not query:
            raise HTTPException(status_code=422, detail="Query must not be empty")
        limit_value = bounded_int(args.get("limit"), 8, 1, 50)
        query_for_retrieval = query
        results = knowledge_base.rag_search(
            query,
            limit=limit_value,
            paper_id=args.get("paper_id"),
            library_id=args.get("library_id"),
            parse_item_key=args.get("parse_item_key"),
            support_level=args.get("support_level"),
        )
    elif request.tool_name == "knowledge_base.support_for_hypothesis":
        hypothesis = args.get("hypothesis")
        if not isinstance(hypothesis, dict):
            raise HTTPException(status_code=422, detail="Hypothesis argument must be an object")
        limit_value = bounded_int(args.get("limit"), 6, 1, 20)
        query_for_retrieval = " ".join(
            str(hypothesis.get(key, ""))
            for key in ("text", "hypothesis", "technical_hypothesis", "explanation", "experiment")
        ).strip()
        results = knowledge_base.support_for_hypothesis(
            hypothesis,
            limit=limit_value,
        )
    else:
        raise HTTPException(
            status_code=501,
            detail={
                "code": "tool_executor_not_implemented",
                "message": "这个工具已经注册，但尚未接入受控执行器。",
            },
        )

    result_ref: Optional[Dict[str, Any]] = None
    if request.run_id:
        result_ref = knowledge_base.store_tool_result(
            run_id=request.run_id,
            tool_name=request.tool_name,
            phase=phase,
            content=results,
            result_kind="evidence_results",
            summary=f"{request.tool_name} returned {len(results)} evidence result(s).",
        )
        knowledge_base.record_research_tool_call(
            run_id=request.run_id,
            tool_name=request.tool_name,
            phase=phase,
            status="complete",
            arguments=args,
            result_summary=f"{request.tool_name} returned {len(results)} result(s).",
            metadata={
                "toolset": spec.toolset,
                "risk_level": spec.risk_level,
                "availability": availability,
                "result_count": len(results),
                "result_preview": results[:3],
                "result_ref": result_ref,
            },
        )
        knowledge_base.record_evidence_retrieval(
            run_id=request.run_id,
            tool_name=request.tool_name,
            query=query_for_retrieval,
            limit_value=limit_value,
            results=results,
            hypothesis_id=request.hypothesis_id,
            hypothesis_index=request.hypothesis_index,
        )

    return {
        "tool_name": request.tool_name,
        "phase": phase,
        "toolset": spec.toolset,
        "risk_level": spec.risk_level,
        "run_id": request.run_id,
        "results": results,
        "result_count": len(results),
        "availability": availability,
        "policy": authorization.get("policy"),
        "guardrail": guardrail,
        "result_ref": result_ref,
    }


@app.post("/api/tools/workflows/pdf-parse")
async def execute_pdf_parse_tool_workflow(request: PdfParseToolWorkflowRequest) -> Dict[str, Any]:
    registry = research_tool_registry()
    spec = registry.get("pdf.parse_to_knowledge_base")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})

    phase = canonical_phase(request.phase)
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )

    availability = spec.describe()["availability"]
    if not availability.get("available"):
        raise HTTPException(
            status_code=424,
            detail={
                "code": "tool_unavailable",
                "message": "PDF 解析工具当前不可用，请先安装后端依赖并查看 availability。",
                "availability": availability,
            },
        )

    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="pdf.parse_to_knowledge_base",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    arguments = {
        "pdf_path": request.pdf_path,
        "fetch_metadata": request.fetch_metadata,
        "ingest_to_knowledge_base": request.ingest_to_knowledge_base,
        "library_id": request.library_id or DEFAULT_LIBRARY_ID,
    }
    if request.run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=request.run_id,
            tool_name="pdf.parse_to_knowledge_base",
            phase=phase,
            arguments=arguments,
        )
        if repeated >= 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repeated_identical_tool_workflow",
                    "message": "同一 run 已执行过相同 PDF 解析 workflow，guardrail 阻止重复写入。",
                    "repeat_count": repeated,
                },
            )

    try:
        knowledge_base.resolve_library_id(request.library_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        )

    parse_run_id = f"parse_{uuid.uuid4().hex[:12]}"
    try:
        resolved_pdf = await asyncio.to_thread(resolve_pdf_input, request.pdf_path)
        payload = await parse_pdf_and_record(
            parse_run_id=parse_run_id,
            pdf_path=resolved_pdf,
            input_kind="local_path",
            input_path=request.pdf_path,
            fetch_metadata=request.fetch_metadata,
            ingest_to_knowledge_base=request.ingest_to_knowledge_base,
            library_id=request.library_id,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "pdf_not_found",
                "message": "没有找到这个 PDF 文件，请确认路径在当前机器上可访问。",
            },
        )
    except (requests.RequestException, ValueError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "pdf_download_failed",
                "message": "PDF 链接暂时无法读取，请确认链接可直接访问 PDF，或改用本机 PDF 路径。",
            },
        )
    except Exception:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "pdf_parse_failed",
                "message": "PDF 暂时无法解析，请确认文件未加密、未损坏，并且后端已安装 PyMuPDF。",
            },
        )

    result_ref: Optional[Dict[str, Any]] = None
    if request.run_id:
        result_ref = knowledge_base.store_tool_result(
            run_id=request.run_id,
            tool_name="pdf.parse_to_knowledge_base",
            phase=phase,
            content=payload,
            result_kind="pdf_parse_payload",
            summary=f"PDF parsed into knowledge base parse_run_id={payload.get('parse_run_id')}.",
        )
        knowledge_base.record_research_tool_call(
            run_id=request.run_id,
            tool_name="pdf.parse_to_knowledge_base",
            phase=phase,
            status="complete",
            arguments=arguments,
            result_summary=f"PDF parse workflow produced parse_run_id={payload.get('parse_run_id')}.",
            metadata={
                "toolset": spec.toolset,
                "risk_level": spec.risk_level,
                "availability": availability,
                "approval": approval,
                "parse_run_id": payload.get("parse_run_id"),
                "paper_id": payload.get("paper_id"),
                "result_ref": result_ref,
            },
        )

    return {
        "tool_name": "pdf.parse_to_knowledge_base",
        "phase": phase,
        "toolset": spec.toolset,
        "risk_level": spec.risk_level,
        "run_id": request.run_id,
        "approval": approval,
        "availability": availability,
        "policy": authorization.get("policy"),
        "result_ref": result_ref,
        "parse_result": payload,
    }


async def run_pdf_parse_background_job(
    job_id: str,
    request: PdfParseToolWorkflowRequest,
) -> None:
    knowledge_base.update_background_job(job_id, status="running")
    try:
        payload = await execute_pdf_parse_tool_workflow(request)
        knowledge_base.update_background_job(
            job_id,
            status="complete",
            result_ref={
                "tool_result": payload.get("result_ref"),
                "parse_run_id": payload.get("parse_result", {}).get("parse_run_id"),
                "paper_id": payload.get("parse_result", {}).get("paper_id"),
            },
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        knowledge_base.update_background_job(
            job_id,
            status="error",
            error_message=json.dumps(detail, ensure_ascii=False),
        )
    except Exception as exc:
        knowledge_base.update_background_job(
            job_id,
            status="error",
            error_message=str(exc),
        )


@app.post("/api/tools/workflows/pdf-parse/background")
async def enqueue_pdf_parse_tool_workflow(
    request: PdfParseToolWorkflowRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    phase = canonical_phase(request.phase)
    require_tool_workflow_approval(
        request.approval,
        expected_scope="pdf.parse_to_knowledge_base",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    arguments = {
        "pdf_path": request.pdf_path,
        "fetch_metadata": request.fetch_metadata,
        "ingest_to_knowledge_base": request.ingest_to_knowledge_base,
        "library_id": request.library_id or DEFAULT_LIBRARY_ID,
        "approval_scope": request.approval.scope,
    }
    job = knowledge_base.create_background_job(
        job_id=job_id,
        run_id=request.run_id,
        workflow_name="pdf.parse_to_knowledge_base",
        phase=phase,
        arguments=arguments,
    )
    background_tasks.add_task(run_pdf_parse_background_job, job_id, request)
    return {"job": job}


@app.post("/api/tools/workflows/mcp-call")
async def execute_mcp_tool_workflow(request: McpToolWorkflowRequest) -> Dict[str, Any]:
    phase = canonical_phase(request.phase)
    registry = research_tool_registry()
    spec = registry.get("mcp.literature_review")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})

    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )

    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="mcp.literature_review",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    tool_registry = build_policy_limited_tool_registry()
    allowed_tool_ids = tool_registry.get_tools_for_workflow(request.workflow_name)
    allowed_mcp_names = set(tool_registry.get_mcp_tool_names(allowed_tool_ids))
    tool_id = request.tool_id
    mcp_tool_name = request.mcp_tool_name
    if tool_id:
        if tool_id not in allowed_tool_ids:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "mcp_tool_not_allowed_by_workflow_policy",
                    "message": "这个 MCP 工具没有被当前 workflow policy 授权。",
                    "allowed_tools": allowed_tool_ids,
                },
            )
        tool_config = tool_registry.get_tool(tool_id)
        mcp_tool_name = tool_config.mcp_tool_name if tool_config else None
    if not mcp_tool_name:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "mcp_tool_required",
                "message": "必须提供 tool_id 或 mcp_tool_name。",
            },
        )
    if mcp_tool_name not in allowed_mcp_names:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "mcp_tool_not_allowed_by_workflow_policy",
                "message": "这个 MCP tool name 没有被当前 workflow policy 授权。",
                "allowed_mcp_tools": sorted(allowed_mcp_names),
            },
        )

    arguments = request.arguments or {}
    if request.run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=request.run_id,
            tool_name=f"mcp.{mcp_tool_name}",
            phase=phase,
            arguments=arguments,
        )
        if repeated >= 2:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repeated_identical_mcp_tool_call",
                    "message": "同一 run 已重复执行相同 MCP 工具调用，guardrail 阻止继续执行。",
                    "repeat_count": repeated,
                },
            )

    try:
        client = await get_policy_limited_mcp_client(tool_registry)
        result = await client.call_tool(mcp_tool_name, **arguments)
    except Exception as exc:
        if request.run_id:
            knowledge_base.record_research_tool_call(
                run_id=request.run_id,
                tool_name=f"mcp.{mcp_tool_name}",
                phase=phase,
                status="error",
                arguments=arguments,
                result_summary=f"MCP tool failed: {exc}",
                metadata={
                    "workflow_name": request.workflow_name,
                    "tool_id": tool_id,
                    "mcp_tool_name": mcp_tool_name,
                    "approval": approval,
                    "error": str(exc),
                },
            )
        raise HTTPException(
            status_code=424,
            detail={
                "code": "mcp_tool_call_failed",
                "message": "MCP 工具调用失败，请检查 MCP 服务状态和工具参数。",
            },
        )

    result_ref: Optional[Dict[str, Any]] = None
    if request.run_id:
        result_ref = knowledge_base.store_tool_result(
            run_id=request.run_id,
            tool_name=f"mcp.{mcp_tool_name}",
            phase=phase,
            content=result,
            result_kind="mcp_tool_result",
            summary=f"MCP tool {mcp_tool_name} completed under workflow {request.workflow_name}.",
        )
        knowledge_base.record_research_tool_call(
            run_id=request.run_id,
            tool_name=f"mcp.{mcp_tool_name}",
            phase=phase,
            status="complete",
            arguments=arguments,
            result_summary=f"MCP tool {mcp_tool_name} returned {len(str(result))} characters.",
            metadata={
                "workflow_name": request.workflow_name,
                "tool_id": tool_id,
                "mcp_tool_name": mcp_tool_name,
                "approval": approval,
                "result_ref": result_ref,
                "result_preview": str(result)[:700],
            },
        )
        query = str(arguments.get("query") or arguments.get("url") or arguments.get("doi") or "")
        knowledge_base.record_evidence_retrieval(
            run_id=request.run_id,
            tool_name=f"mcp.{mcp_tool_name}",
            query=query,
            limit_value=bounded_int(arguments.get("max_papers") or arguments.get("max_results"), 0, 0, 100),
            results=[{"result_ref": result_ref, "preview": str(result)[:700]}],
        )

    return {
        "tool_name": "mcp.literature_review",
        "mcp_tool_name": mcp_tool_name,
        "tool_id": tool_id,
        "workflow_name": request.workflow_name,
        "phase": phase,
        "run_id": request.run_id,
        "approval": approval,
        "policy": authorization.get("policy"),
        "result_ref": result_ref,
        "result_preview": str(result)[:700],
        "result_size": len(str(result).encode("utf-8")),
    }


@app.post("/api/tools/workflows/evidence-literature-verification")
async def evidence_literature_verification_workflow(
    request: EvidenceVerificationWorkflowRequest,
) -> Dict[str, Any]:
    return await execute_evidence_literature_verification_workflow(request)


@app.post("/api/tools/workflows/web-search")
async def execute_web_search_workflow(request: WebSearchWorkflowRequest) -> Dict[str, Any]:
    registry = research_tool_registry()
    spec = registry.get("web.search_public")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})

    phase = canonical_phase(request.phase)
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )

    availability = spec.describe()["availability"]
    if not availability.get("available"):
        raise HTTPException(status_code=424, detail={"code": "tool_unavailable", "availability": availability})

    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="web.search_public",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    arguments = {
        "query": request.query,
        "limit": request.limit,
        "domains": request.domains,
        "recency_days": request.recency_days,
    }
    if request.run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=request.run_id,
            tool_name="web.search_public",
            phase=phase,
            arguments=arguments,
        )
        if repeated >= 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repeated_identical_web_search",
                    "message": "同一 run 已执行过相同 public web search，guardrail 阻止重复检索。",
                    "repeat_count": repeated,
                },
            )

    try:
        search_result = await asyncio.to_thread(
            search_public_web,
            request.query,
            artifact_root=KB_ROOT / "web_search",
            limit=request.limit,
            domains=request.domains,
            recency_days=request.recency_days,
        )
    except WebSearchError as exc:
        raise HTTPException(status_code=422, detail={"code": "web_search_guardrail_failed", "message": str(exc)})
    except requests.RequestException:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "web_search_failed",
                "message": "公开搜索暂时失败；请检查网络或改用 MCP 文献检索 / 已知 URL 抓取。",
            },
        )

    payload = search_result.payload
    result_ref = knowledge_base.store_tool_result(
        run_id=request.run_id,
        tool_name="web.search_public",
        phase=phase,
        content=payload,
        result_kind="web_search_results",
        summary=f"Public web search returned {payload.get('result_count', 0)} result(s).",
    )
    if request.run_id:
        knowledge_base.record_research_tool_call(
            run_id=request.run_id,
            tool_name="web.search_public",
            phase=phase,
            status="complete",
            arguments=arguments,
            result_summary=f"Public web search returned {payload.get('result_count', 0)} result(s).",
            metadata={
                "toolset": spec.toolset,
                "risk_level": spec.risk_level,
                "availability": availability,
                "approval": approval,
                "result_ref": result_ref,
                "provider": payload.get("provider"),
                "results_path": payload.get("results_path"),
                "metadata_path": payload.get("metadata_path"),
            },
        )
        knowledge_base.record_evidence_retrieval(
            run_id=request.run_id,
            tool_name="web.search_public",
            query=request.query,
            limit_value=request.limit,
            results=[
                {
                    "result_ref": result_ref,
                    "rank": item.get("rank"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "source": item.get("source"),
                }
                for item in payload.get("results", [])
            ],
        )

    return {
        "tool_name": "web.search_public",
        "phase": phase,
        "toolset": spec.toolset,
        "risk_level": spec.risk_level,
        "run_id": request.run_id,
        "approval": approval,
        "availability": availability,
        "policy": authorization.get("policy"),
        "result_ref": result_ref,
        "web_search": payload,
    }


@app.post("/api/tools/workflows/web-extract")
async def execute_web_extract_workflow(request: WebExtractWorkflowRequest) -> Dict[str, Any]:
    registry = research_tool_registry()
    spec = registry.get("browser.web_extract")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})

    phase = canonical_phase(request.phase)
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )

    availability = spec.describe()["availability"]
    if not availability.get("available"):
        raise HTTPException(status_code=424, detail={"code": "tool_unavailable", "availability": availability})

    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="browser.web_extract",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    arguments = {
        "url": request.url,
        "max_bytes": request.max_bytes,
        "max_text_chars": request.max_text_chars,
        "ingest_to_knowledge_base": request.ingest_to_knowledge_base,
        "library_id": request.library_id or DEFAULT_LIBRARY_ID,
    }
    if request.run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=request.run_id,
            tool_name="browser.web_extract",
            phase=phase,
            arguments=arguments,
        )
        if repeated >= 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repeated_identical_web_extract",
                    "message": "同一 run 已执行过相同网页证据抓取 workflow，guardrail 阻止重复抓取。",
                    "repeat_count": repeated,
                },
            )

    try:
        web_result = await asyncio.to_thread(
            extract_web_evidence,
            request.url,
            artifact_root=KB_ROOT / "web_evidence",
            timeout_seconds=20,
            max_bytes=request.max_bytes,
            max_text_chars=request.max_text_chars,
        )
    except WebEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "web_extract_guardrail_failed",
                "message": str(exc),
            },
        )
    except requests.RequestException:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "web_extract_failed",
                "message": "网页证据暂时无法抓取，请确认 URL 可公开访问并返回文本/HTML 内容。",
            },
        )

    payload = web_result.payload
    public_payload = web_result.public_payload()
    paper_id: Optional[str] = None
    if request.ingest_to_knowledge_base and len(payload.get("extracted_text", "")) >= 20:
        paper = knowledge_base.ingest(
            title=payload.get("title") or payload.get("final_url") or request.url,
            content=payload["extracted_text"],
            url=payload.get("final_url") or request.url,
            abstract=payload.get("text_preview", "")[:2000],
            source="web_evidence",
            source_reliability=payload.get("source_reliability", "best_effort_public_html"),
            metadata={
                "artifact_id": payload.get("artifact_id"),
                "content_hash": payload.get("content_hash"),
                "snapshot_path": payload.get("snapshot_path"),
                "metadata_path": payload.get("metadata_path"),
                "link_count": payload.get("link_count"),
                "pdf_links": payload.get("pdf_links", []),
                "supplementary_links": payload.get("supplementary_links", []),
                "library_id": request.library_id or DEFAULT_LIBRARY_ID,
            },
            library_id=request.library_id,
        )
        paper_id = paper.paper_id
        payload["knowledge_base_paper_id"] = paper_id
        public_payload["knowledge_base_paper_id"] = paper_id

    result_ref: Optional[Dict[str, Any]] = None
    if request.run_id:
        result_ref = knowledge_base.store_tool_result(
            run_id=request.run_id,
            tool_name="browser.web_extract",
            phase=phase,
            content=payload,
            result_kind="web_evidence_extract",
            summary=f"Web evidence extracted from {payload.get('final_url') or request.url}.",
        )
        knowledge_base.record_research_tool_call(
            run_id=request.run_id,
            tool_name="browser.web_extract",
            phase=phase,
            status="complete",
            arguments=arguments,
            result_summary=f"Web evidence extracted title={payload.get('title') or 'untitled'}.",
            metadata={
                "toolset": spec.toolset,
                "risk_level": spec.risk_level,
                "availability": availability,
                "approval": approval,
                "result_ref": result_ref,
                "content_hash": payload.get("content_hash"),
                "snapshot_path": payload.get("snapshot_path"),
                "knowledge_base_paper_id": paper_id,
            },
        )
        knowledge_base.record_evidence_retrieval(
            run_id=request.run_id,
            tool_name="browser.web_extract",
            query=request.url,
            limit_value=1,
            results=[
                {
                    "result_ref": result_ref,
                    "paper_id": paper_id,
                    "title": payload.get("title"),
                    "final_url": payload.get("final_url"),
                    "source_reliability": payload.get("source_reliability"),
                    "content_hash": payload.get("content_hash"),
                }
            ],
        )

    return {
        "tool_name": "browser.web_extract",
        "phase": phase,
        "toolset": spec.toolset,
        "risk_level": spec.risk_level,
        "run_id": request.run_id,
        "approval": approval,
        "availability": availability,
        "policy": authorization.get("policy"),
        "result_ref": result_ref,
        "web_result": public_payload,
    }


async def run_web_extract_background_job(
    job_id: str,
    request: WebExtractWorkflowRequest,
) -> None:
    knowledge_base.update_background_job(job_id, status="running")
    try:
        payload = await execute_web_extract_workflow(request)
        knowledge_base.update_background_job(
            job_id,
            status="complete",
            result_ref={
                "tool_result": payload.get("result_ref"),
                "content_hash": payload.get("web_result", {}).get("content_hash"),
                "knowledge_base_paper_id": payload.get("web_result", {}).get("knowledge_base_paper_id"),
            },
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        knowledge_base.update_background_job(
            job_id,
            status="error",
            error_message=json.dumps(detail, ensure_ascii=False),
        )
    except Exception as exc:
        knowledge_base.update_background_job(
            job_id,
            status="error",
            error_message=str(exc),
        )


@app.post("/api/tools/workflows/web-extract/background")
async def enqueue_web_extract_workflow(
    request: WebExtractWorkflowRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    phase = canonical_phase(request.phase)
    require_tool_workflow_approval(
        request.approval,
        expected_scope="browser.web_extract",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job = knowledge_base.create_background_job(
        job_id=job_id,
        run_id=request.run_id,
        workflow_name="browser.web_extract",
        phase=phase,
        arguments={
            "url": request.url,
            "max_bytes": request.max_bytes,
            "max_text_chars": request.max_text_chars,
            "ingest_to_knowledge_base": request.ingest_to_knowledge_base,
            "approval_scope": request.approval.scope,
        },
    )
    background_tasks.add_task(run_web_extract_background_job, job_id, request)
    return {"job": job}


@app.get("/api/research-chat/capabilities")
async def list_research_chat_capabilities() -> Dict[str, Any]:
    capabilities = _chat_capabilities()
    return {"capabilities": capabilities, "count": len(capabilities)}


@app.get("/api/research-chat/sessions")
async def list_research_chat_sessions(run_id: Optional[str] = None, limit: int = 30) -> Dict[str, Any]:
    sessions = knowledge_base.list_research_chat_sessions(run_id=run_id, limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/api/research-chat/sessions/{session_id}")
async def get_research_chat_session(session_id: str) -> Dict[str, Any]:
    session = knowledge_base.get_research_chat_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={"code": "research_chat_session_not_found", "message": "没有找到这个对话记录。"},
        )
    return session


async def _research_chat_turn_impl(
    request: ResearchChatTurnRequest,
    *,
    progress: Optional[ResearchChatProgressCallback] = None,
) -> Dict[str, Any]:
    session_id = request.session_id or f"chat_{uuid.uuid4().hex[:12]}"
    await _emit_research_chat_progress(
        progress,
        "session",
        "已创建或恢复项目 AI 对话会话。",
        sessionId=session_id,
    )
    _ensure_chat_session(session_id, request)
    _record_chat_message(
        session_id,
        "user",
        request.message,
        {"text": request.message, "context": _context_dict(request.context)},
    )
    await _emit_research_chat_progress(
        progress,
        "routing",
        "正在用模型 planner 和 tool schema 判断请求是否需要确认卡、工具动作或只读 RAG 回答。",
    )
    routed = await _plan_research_chat_route(request=request, session_id=session_id, progress=progress)
    intent = routed["intent"]
    inputs = routed["extractedInputs"]
    await _emit_research_chat_progress(
        progress,
        "routed",
        f"路由完成：{intent}。",
        intent=intent,
        missingInputs=list(routed.get("missingInputs") or []),
    )

    if routed.get("plannerStatus") in {"model_missing", "model_disabled", "planner_error"}:
        result = {
            "intent": intent,
            "title": routed.get("title") or "模型规划器不可用",
            "summary": routed.get("summary") or routed.get("userFacingReason") or "模型 planner 暂时不可用。",
            "status": routed.get("plannerStatus"),
            "verdict": "limited",
            "modelName": routed.get("modelName") or _research_chat_model_name(request.context),
            "plannerStatus": routed.get("plannerStatus"),
            "plannerConfidence": routed.get("plannerConfidence", 0.0),
            "routingSource": routed.get("routingSource", "fallback_error"),
            "capabilityId": routed.get("capabilityId"),
            "nextActions": ["检查模型 API 配置", "重试同一问题", "把请求拆成更明确的一步"],
            "groundingBoundary": "model_without_local_evidence",
        }
        return _chat_turn_response(
            session_id=session_id,
            assistant_message={
                "kind": "result_summary",
                "text": result["summary"],
                "result": result,
                "suggestions": _chat_capabilities(),
            },
            state="needs_input" if result["status"] in {"model_missing", "model_disabled"} else "error",
        )

    if routed["missingInputs"]:
        if intent == "clarify":
            result = await _research_chat_llm_result(
                message=request.message,
                context=request.context,
                routed=routed,
                progress=progress,
            )
            return _chat_turn_response(
                session_id=session_id,
                assistant_message={
                    "kind": "result_summary",
                    "text": result["summary"],
                    "result": result,
                    "suggestions": _chat_capabilities(),
                },
                state="complete" if result.get("status") not in {"model_missing", "model_disabled"} else "needs_input",
            )
        prompt_by_intent = {
            "parse_pdf_to_knowledge_base": "请上传 PDF，或输入当前后端能访问的 PDF 路径。",
            "extract_web_evidence": "请提供要保存为证据的公开网页 URL。",
            "search_knowledge_evidence": "请告诉我要检索的机制、术语或假设。",
            "check_hypothesis_grounding": "请粘贴要检查的假设文本。",
            "verify_evidence_with_literature": "请粘贴要做外部文献反证检查的假设文本。",
            "start_research_run": "请用一句明确 research goal 描述这次研究目标，例如：研究目标：为某机制生成可证伪假设。",
            "run_terminal_command": "请提供要执行的本地 PowerShell/bash/terminal 命令。",
            "run_ssh_training_command": "请提供服务器 ID（例如 c201-5080）和要执行的远程命令。",
            "snapshot_local_file": "请提供要读取快照的本地文件路径，并确认它位于项目允许的证据根目录内。",
            "register_project_tool": "请提供工具 ID 和用途描述；如果已有 input schema，也可以一并给出。",
            "search_public_web": "请提供要执行公开 Web Search 的 query。",
            "clarify": "你想解析 PDF、抓取网页、搜索知识库，还是检查假设支撑？",
        }
        return _chat_turn_response(
            session_id=session_id,
            assistant_message={
                "kind": "clarification",
                "text": prompt_by_intent.get(intent, "请补充任务需要的输入。"),
                "routed_intent": routed,
                "suggestions": _chat_capabilities(),
            },
            state="needs_input",
        )

    if intent == "summarize_project_artifacts":
        result = _project_artifacts_summary_result(request.context, inputs)
        return await _chat_turn_llm_response(
            session_id=session_id,
            request=request,
            routed=routed,
            structured_context=result,
            knowledge_results=[item for item in result.get("items", []) if isinstance(item, dict)],
            progress=progress,
        )

    if intent in {"ask_project_ai", "discover_capabilities"}:
        structured = _capability_map_result() if intent == "discover_capabilities" else None
        return await _chat_turn_llm_response(
            session_id=session_id,
            request=request,
            routed=routed,
            structured_context=structured,
            progress=progress,
        )

    if intent == "start_research_run":
        research_goal = str(inputs["research_goal"]).strip()
        starting_hypotheses = [
            str(item).strip()
            for item in (inputs.get("starting_hypotheses") if isinstance(inputs.get("starting_hypotheses"), list) else [])
            if str(item).strip()
        ][:20]
        constraints = [
            str(item).strip()
            for item in (inputs.get("constraints") if isinstance(inputs.get("constraints"), list) else [])
            if str(item).strip()
        ][:40]
        attributes = [
            str(item).strip()
            for item in (inputs.get("attributes") if isinstance(inputs.get("attributes"), list) else [])
            if str(item).strip()
        ][:20]
        preferences = str(inputs.get("preferences") or "").strip() or None
        parent_run_id = request.context.run_id if _contains_any(request.message, ["继续", "基于当前", "基于上次", "continue", "revise"]) else None
        normalized_min_references = min(request.context.min_references, request.context.max_references)
        normalized_max_references = max(request.context.min_references, request.context.max_references)
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        return await _proposal_or_auto_response(
            session_id=session_id,
            action_id=action_id,
            intent=intent,
            title="启动 Live model research workflow",
            summary="我可以用这个 research goal 启动真实模型研究流程，生成、评审、排序并演化候选假设。若启用 literature-grounded workflow，会先使用本地知识库和 MCP 文献源做证据准备；执行前需要确认，因为会消耗模型/文献服务资源。",
            input_summary=research_goal[:240],
            operation_summary=[
                "检查模型、本地知识库和文献服务",
                "执行 safety gate",
                "按研究主题自动检索论文并写入当前资料库",
                "启动多阶段研究 workflow",
                f"纳入 {len(starting_hypotheses)} 条用户候选假设" if starting_hypotheses else "由模型生成候选假设",
                "生成 review、Elo ranking 和 timeline",
            ],
            risk_summary="将调用真实模型和文献 MCP；一键模式会把可解析 PDF 自动写入当前资料库。没有文献证据的输出会标记为 limited/ungrounded。",
            expected_result_summary=["research run", "ingested papers", "hypotheses", "reviews", "tournament matchups", "agent trace"],
            approval_scope="research.start_live_run",
            execution_target="workflow.start_run",
            request_preview={
                "research_goal": research_goal,
                "model_name": request.context.model_name,
                "demo_mode": bool(request.context.demo_mode),
                "literature_review": bool(request.context.literature_review),
                "initial_hypotheses": request.context.initial_hypotheses,
                "iterations": request.context.iterations,
                "min_references": normalized_min_references,
                "max_references": normalized_max_references,
                "preferences": preferences,
                "attributes": attributes,
                "constraints": constraints,
                "starting_hypotheses": starting_hypotheses,
                "starting_hypotheses_count": len(starting_hypotheses),
                "parent_run_id": parent_run_id,
                "refinement_mode": "continue_from_run" if parent_run_id else "new_run",
                "memory_scope": "library",
                "library_id": request.context.library_id,
                "auto_discover_papers": True,
                "auto_ingest_papers": True,
                "paper_discovery_limit": min(max(normalized_max_references, 6), 12),
                "paper_ingest_limit": min(max(normalized_min_references, 4), 8),
            },
        )

    if intent == "explain_current_run":
        result = _run_summary_result(request.context)
        return await _chat_turn_llm_response(
            session_id=session_id,
            request=request,
            routed=routed,
            structured_context=result,
            progress=progress,
        )

    if intent in {"critique_generated_hypothesis", "apply_expert_feedback"}:
        result = _record_hypothesis_feedback_result(request.context, {**inputs, "intent": intent})
        return _chat_turn_response(
            session_id=session_id,
            assistant_message={"kind": "result_summary", "text": result["summary"], "result": result},
            state="complete" if result.get("status") == "complete" else "needs_input",
        )

    if intent == "inspect_hypothesis":
        result = _inspect_hypothesis_result(request.context, inputs)
        return await _chat_turn_llm_response(
            session_id=session_id,
            request=request,
            routed=routed,
            structured_context=result,
            progress=progress,
        )

    if intent == "explain_ranking":
        result = _ranking_explanation_result(request.context, inputs)
        return await _chat_turn_llm_response(
            session_id=session_id,
            request=request,
            routed=routed,
            structured_context=result,
            progress=progress,
        )

    if intent == "design_experiment":
        result = _experiment_design_result(request.context, inputs)
        return await _chat_turn_llm_response(
            session_id=session_id,
            request=request,
            routed=routed,
            structured_context=result,
            progress=progress,
        )

    if intent == "draft_report":
        result = _report_draft_result(request.context)
        return await _chat_turn_llm_response(
            session_id=session_id,
            request=request,
            routed=routed,
            structured_context=result,
            progress=progress,
        )

    if intent == "search_session_history":
        query = str(inputs.get("query") or request.message).strip()
        result = _session_search_result(request.context, query)
        return await _chat_turn_llm_response(
            session_id=session_id,
            request=request,
            routed=routed,
            structured_context=result,
            progress=progress,
        )

    if intent == "snapshot_local_file":
        source_path = str(inputs["source_path"]).strip()
        start_line = bounded_int(inputs.get("start_line"), 1, 1, 1_000_000)
        line_count = bounded_int(inputs.get("line_count"), 200, 1, 2000)
        max_bytes = bounded_int(inputs.get("max_bytes"), 1_000_000, 1024, 5_000_000)
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        return await _proposal_or_auto_response(
            session_id=session_id,
            action_id=action_id,
            intent=intent,
            title="读取本地文件快照",
            summary="我可以通过受控 file.source_snapshot workflow 读取这段本地文件，生成分页、hash 和审计记录。文件必须位于配置的 source evidence root 内。",
            input_summary=_path_summary(source_path),
            operation_summary=["校验路径边界", "按行范围读取文本", "计算内容 hash", "保存 source evidence 快照和 tool result"],
            risk_summary="这是只读文件快照；仍会限制路径根目录、读取行数和最大字节数，并写入审计记录。不会读取凭据目录或越过 source evidence root。",
            expected_result_summary=["source file snapshot", "line range", "content sha256", "tool result provenance"],
            approval_scope="file.source_snapshot",
            execution_target="workflow.file_snapshot",
            request_preview={
                "source_path": source_path,
                "phase": "evidence_audit",
                "run_id": request.context.run_id,
                "start_line": start_line,
                "line_count": line_count,
                "max_bytes": max_bytes,
            },
        )

    if intent == "register_project_tool":
        tool_name = str(inputs["tool_name"]).strip()
        description = str(inputs["description"]).strip()
        toolset = str(inputs.get("toolset") or "project_custom").strip()
        phases = [str(item).strip() for item in inputs.get("phases", []) if str(item).strip()] if isinstance(inputs.get("phases"), list) else ["evidence_audit"]
        risk_level = str(inputs.get("risk_level") or "read").strip()
        input_schema = inputs.get("input_schema") if isinstance(inputs.get("input_schema"), dict) else {}
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        return await _proposal_or_auto_response(
            session_id=session_id,
            action_id=action_id,
            intent=intent,
            title="注册项目工具草案",
            summary="我可以把这个工具注册为项目级 schema 草案，供后续 planner 和人工实现参考。此操作不会安装执行器，也不会让模型写入或运行任意工具代码。",
            input_summary=f"{tool_name}: {description[:180]}",
            operation_summary=["规范化工具 ID", "校验 input schema 和 phase", "保存 schema-only 草案", "写入 tool result 审计记录并出现在工具注册表"],
            risk_summary="只保存工具元数据和输入 schema；执行器保持不可用，真正执行能力必须另行实现、审查和授权。",
            expected_result_summary=["project tool draft", "validated schema", "registry entry", "audit result"],
            approval_scope="tool.register_draft",
            execution_target="workflow.tool_register_draft",
            request_preview={
                "tool_name": tool_name,
                "user_title": str(inputs.get("user_title") or "").strip() or None,
                "description": description,
                "toolset": toolset,
                "phases": phases,
                "risk_level": risk_level,
                "input_schema": input_schema,
                "execution_boundary": str(inputs.get("execution_boundary") or "schema_registered_only"),
                "run_id": request.context.run_id,
            },
        )

    if intent == "run_terminal_command":
        command = str(inputs["command"]).strip()
        workdir = inputs.get("workdir")
        command_risk = classify_command_risk(command)
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        return await _proposal_or_auto_response(
            session_id=session_id,
            action_id=action_id,
            intent=intent,
            title="执行本地终端命令",
            summary="我可以通过受控 terminal workflow 执行这条本机命令，并把 stdout、stderr、manifest 和 guardrail 结果写入审计记录。",
            input_summary=redact_sensitive_text(command)[:240],
            operation_summary=["检查 command permission mode", "运行危险命令 denylist 和 cwd guardrail", "提交后台命令任务", "保存 stdout/stderr artifact 和 tool result"],
            risk_summary=f"命令风险等级：{command_risk.get('risk_level', 'unknown')}；仍会保留超时、敏感信息脱敏、危险命令拦截和审计记录。",
            expected_result_summary=["background job", "terminal stdout/stderr", "manifest artifact", "tool result provenance"],
            approval_scope="terminal.command",
            execution_target="workflow.terminal_command",
            request_preview={
                "command": command,
                "workdir": workdir,
                "phase": "operator_diagnostics",
                "run_id": request.context.run_id,
                "timeout_seconds": 120,
                "command_risk": command_risk,
            },
        )

    if intent == "run_ssh_training_command":
        server_id = str(inputs["server_id"]).strip()
        command = str(inputs["command"]).strip()
        workdir = inputs.get("workdir")
        command_risk = classify_command_risk(command)
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        return await _proposal_or_auto_response(
            session_id=session_id,
            action_id=action_id,
            intent=intent,
            title=f"在 {server_id} 执行 SSH 命令",
            summary="我可以通过受管 SSH workflow 在已配置服务器上执行这条远程命令，并保存远程 stdout、stderr、manifest 和 tool result provenance。",
            input_summary=f"{server_id}: {redact_sensitive_text(command)[:220]}",
            operation_summary=["校验服务器白名单", "运行远程命令 guardrail", "提交 SSH 后台任务", "保存远程 stdout/stderr artifact 和 tool result"],
            risk_summary=f"仅使用已配置 host alias；命令风险等级：{command_risk.get('risk_level', 'unknown')}；仍会拦截 sudo、凭据文件访问、关机/格式化等危险操作。",
            expected_result_summary=["background job", "remote stdout/stderr", "manifest artifact", "tool result provenance"],
            approval_scope="ssh.training_command",
            execution_target="workflow.ssh_training_command",
            request_preview={
                "server_id": server_id,
                "command": command,
                "workdir": workdir,
                "phase": "experiment_execution",
                "run_id": request.context.run_id,
                "timeout_seconds": 3600,
                "command_risk": command_risk,
            },
        )

    if intent == "parse_pdf_to_knowledge_base":
        pdf_path = str(inputs["pdf_path"])
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        return await _proposal_or_auto_response(
            session_id=session_id,
            action_id=action_id,
            intent=intent,
            title="解析 PDF 并写入知识库",
            summary="我可以解析这篇 PDF，抽取全文、metadata、语义片段和实验线索，并写入本地知识库。",
            input_summary=_path_summary(pdf_path),
            operation_summary=["读取 PDF", "抽取全文与 metadata", "生成语义 chunks", "写入知识库和证据记录"],
            risk_summary="将读取本机或远程 PDF，并写入本地知识库与 solve/ 产物目录。",
            expected_result_summary=["parse run", "knowledge paper", "evidence chunks", "可检索证据"],
            approval_scope="pdf.parse_to_knowledge_base",
            execution_target="workflow.pdf_parse",
            request_preview={
                "pdf_path": pdf_path,
                "phase": "paper_reading",
                "run_id": request.context.run_id,
                "fetch_metadata": True,
                "ingest_to_knowledge_base": True,
            },
        )

    if intent == "extract_web_evidence":
        url = str(inputs["url"])
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        return await _proposal_or_auto_response(
            session_id=session_id,
            action_id=action_id,
            intent=intent,
            title="抓取网页证据",
            summary="我可以抓取这个公开网页的文本、PDF 链接和 supplementary 链接，并按 best-effort evidence 写入知识库。",
            input_summary=_url_summary(url),
            operation_summary=["校验公开 URL", "抽取网页正文", "发现 PDF/supplementary 链接", "保存快照并可选入库"],
            risk_summary="将访问公开 HTTP(S) 页面并把可抽取文本写入本地证据库。",
            expected_result_summary=["web evidence snapshot", "knowledge paper", "tool result", "source reliability"],
            approval_scope="browser.web_extract",
            execution_target="workflow.web_extract",
            request_preview={
                "url": url,
                "phase": "literature_review",
                "run_id": request.context.run_id,
                "max_bytes": 1_000_000,
                "max_text_chars": 80_000,
                "ingest_to_knowledge_base": True,
            },
        )

    if intent == "extract_web_evidence_batch":
        urls = [str(url).strip() for url in inputs.get("urls", []) if str(url).strip()][:3]
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        return await _proposal_or_auto_response(
            session_id=session_id,
            action_id=action_id,
            intent=intent,
            title="抓取网页正文并整理",
            summary="我可以打开前几个高相关公开网页，抽取正文 preview，写入知识库，并基于网页内容给出聚合回答。",
            input_summary="；".join(_url_summary(url) for url in urls)[:240],
            operation_summary=["校验公开 URL", "抓取网页正文", "抽取文本 preview 并入库", "基于网页正文聚合回答"],
            risk_summary="将访问多个公开 HTTP(S) 页面；抓取结果是 best-effort public HTML，不等同于权威全文审查。",
            expected_result_summary=["web evidence snapshots", "knowledge papers", "aggregated answer", "source URLs"],
            approval_scope="browser.web_extract",
            execution_target="workflow.web_extract_batch",
            request_preview={
                "urls": urls,
                "query": inputs.get("query") or "",
                "phase": "literature_review",
                "run_id": request.context.run_id,
                "max_bytes": 1_000_000,
                "max_text_chars": 60_000,
                "ingest_to_knowledge_base": True,
                "model_name": request.context.model_name,
            },
        )

    if intent == "search_public_web":
        query = str(inputs["query"]).strip()
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        domains = inputs.get("domains") if isinstance(inputs.get("domains"), list) else []
        return await _proposal_or_auto_response(
            session_id=session_id,
            action_id=action_id,
            intent=intent,
            title="执行通用 Web Search",
            summary="我可以对公开 Web 做 best-effort 搜索，返回 source URL、snippet、retrieval metadata 和 result ref。搜索摘要只作为线索，不能当作全文证据。",
            input_summary=query[:240],
            operation_summary=["校验搜索 query", "调用 public web search provider", "保存搜索结果和 metadata", "返回可继续抓取/解析的 URL 线索"],
            risk_summary="将访问公开搜索引擎；结果是 snippets-only evidence boundary，后续全文支撑仍需通过网页抓取、PDF 解析、MCP 或知识库入库。",
            expected_result_summary=["search result list", "source URLs", "snippets", "tool result provenance"],
            approval_scope="web.search_public",
            execution_target="workflow.web_search",
            request_preview={
                "query": query,
                "phase": "literature_review",
                "run_id": request.context.run_id,
                "limit": 10,
                "domains": domains,
                "model_name": request.context.model_name,
            },
        )

    if intent == "search_knowledge_evidence":
        query = str(inputs["query"]).strip()
        results = paper_parse_store.rag_search(
            query,
            limit=8,
            paper_id=request.context.paper_id,
            library_id=request.context.library_id,
        )
        summary = _rag_result_summary(query, results)
        structured = {
            "intent": intent,
            "query": query,
            **summary,
            "groundingBoundary": "knowledge_base",
        }
        return await _chat_turn_llm_response(
            session_id=session_id,
            request=request,
            routed=routed,
            structured_context=structured,
            knowledge_results=_dedupe_knowledge_results(results + _project_chat_knowledge_fallback(limit=2), limit=8),
            progress=progress,
        )

    if intent == "verify_evidence_with_literature":
        hypothesis_text = str(inputs["hypothesis_text"]).strip()
        action_id = f"action_{uuid.uuid4().hex[:12]}"
        query = evidence_verifier.build_counter_evidence_query(hypothesis_text)
        return await _proposal_or_auto_response(
            session_id=session_id,
            action_id=action_id,
            intent=intent,
            title="外部文献反证检查",
            summary="我会先用本地知识库核验该假设，再经授权调用文献 MCP 检索 PubMed、arXiv 和 Google Scholar 的潜在反证、负面结果和复现失败线索。",
            input_summary=hypothesis_text[:240],
            operation_summary=["本地知识库核验", "构造反证检索 query", "检索 PubMed、arXiv 和 Google Scholar", "合并外部候选证据并写入核验报告"],
            risk_summary="将调用外部 MCP 文献服务，并把工具结果摘要和核验报告写入本地 provenance。",
            expected_result_summary=["本地核验报告", "外部文献反证候选", "tool result provenance", "下一步实验/证据缺口"],
            approval_scope="mcp.literature_review",
            execution_target="workflow.evidence_literature_verification",
            request_preview={
                "hypothesis_text": hypothesis_text,
                "query": query,
                "run_id": request.context.run_id,
                "paper_id": request.context.paper_id,
                "library_id": request.context.library_id,
                "max_papers": 5,
            },
        )

    if intent == "check_hypothesis_grounding":
        hypothesis_text = str(inputs["hypothesis_text"]).strip()
        report = _build_evidence_verification_report(
            hypothesis_text=hypothesis_text,
            context=request.context,
            store_report=True,
        )
        structured = {
            "intent": intent,
            **report,
        }
        local_evidence = [
            item
            for item in (report.get("supportingEvidence") or []) + (report.get("possibleCounterEvidence") or [])
            if isinstance(item, dict)
        ]
        return await _chat_turn_llm_response(
            session_id=session_id,
            request=request,
            routed=routed,
            structured_context=structured,
            knowledge_results=_dedupe_knowledge_results(local_evidence + _project_chat_knowledge_fallback(limit=2), limit=8),
            progress=progress,
        )

    return _chat_turn_response(
        session_id=session_id,
        assistant_message={
            "kind": "unsupported",
            "text": "我还不能可靠执行这个请求。你可以问项目能做什么、启动研究流程、解释当前 run、检查假设、解释 Elo 排名、解析 PDF/网页证据、执行本地命令、连接 SSH 服务器或搜索历史记录。",
            "suggestions": _chat_capabilities(),
        },
        state="idle",
    )


@app.post("/api/research-chat/turn")
async def research_chat_turn(request: ResearchChatTurnRequest) -> Dict[str, Any]:
    return await _research_chat_turn_impl(request)


@app.post("/api/research-chat/turn/stream")
async def research_chat_turn_stream(request: ResearchChatTurnRequest) -> StreamingResponse:
    session_id = request.session_id or f"chat_{uuid.uuid4().hex[:12]}"
    request_with_session = _research_chat_request_with_session(request, session_id)

    async def event_stream():
        queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()
        started_at = time.perf_counter()

        async def progress(event: Dict[str, Any]) -> None:
            event.setdefault("elapsedMs", round((time.perf_counter() - started_at) * 1000))
            await queue.put({"event": "progress", "data": event})
            await asyncio.sleep(0)

        async def run_turn() -> None:
            try:
                response = await _research_chat_turn_impl(request_with_session, progress=progress)
                await queue.put({"event": "final", "data": response})
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
                await queue.put(
                    {
                        "event": "error",
                        "data": {
                            "message": detail.get("message") or "研究聊天请求失败。",
                            "code": detail.get("code") or "research_chat_stream_failed",
                            "httpStatus": exc.status_code,
                        },
                    }
                )
            except Exception as exc:
                print(f"Research chat stream failed: {exc}", file=sys.stderr)
                await queue.put(
                    {
                        "event": "error",
                        "data": {
                            "message": "研究聊天流式请求失败，请稍后重试。",
                            "code": "research_chat_stream_failed",
                        },
                    }
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_turn())
        yield _research_chat_sse_event(
            "session",
            {
                "session_id": session_id,
                "message": "已打开流式项目 AI 通道。",
            },
        )

        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.2)
            except asyncio.TimeoutError:
                if task.done():
                    break
                yield _research_chat_sse_event(
                    "progress",
                    {
                        "phase": "waiting",
                        "message": "仍在等待模型或检索返回；页面会在结果可用后自动补全。",
                        "elapsedMs": round((time.perf_counter() - started_at) * 1000),
                    },
                )
                continue
            if item is None:
                break
            yield _research_chat_sse_event(item["event"], item["data"])

        if not task.done():
            task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/research-chat/actions/{action_id}/confirm")
async def confirm_research_chat_action(
    action_id: str,
    request: ResearchChatConfirmRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    record = research_chat_action_proposals.get(action_id) or knowledge_base.get_research_chat_action(action_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "chat_action_not_found", "message": "没有找到这张确认卡片。"})

    proposal = record["proposal"]
    expected_scope = proposal.get("approvalScope")
    if not request.approval.confirmed or request.approval.scope != expected_scope:
        raise HTTPException(
            status_code=428,
            detail={
                "code": "tool_workflow_approval_required",
                "message": "这个任务需要先在确认卡片中明确授权。",
                "expected_scope": expected_scope,
            },
        )

    record["status"] = "running"
    record["updated_at"] = time.time()
    try:
        knowledge_base.upsert_research_chat_action(
            action_id=action_id,
            session_id=record["session_id"],
            status="running",
            proposal=proposal,
        )
    except Exception as exc:
        print(f"Research chat action running persistence failed for {action_id}: {exc}", file=sys.stderr)
    preview = proposal.get("requestPreview", {})

    try:
        if proposal.get("executionTarget") == "workflow.start_run":
            normalized_min_references = min(
                bounded_int(preview.get("min_references"), 2, 0, 12),
                bounded_int(preview.get("max_references"), 6, 0, 12),
            )
            normalized_max_references = max(
                bounded_int(preview.get("min_references"), 2, 0, 12),
                bounded_int(preview.get("max_references"), 6, 0, 12),
            )
            payload = await create_run(
                RunRequest(
                    research_goal=str(preview["research_goal"]),
                    model_name=str(preview.get("model_name") or "deepseek/deepseek-v4-pro"),
                    demo_mode=bool(preview.get("demo_mode", False)),
                    literature_review=bool(preview.get("literature_review", True)),
                    initial_hypotheses=bounded_int(preview.get("initial_hypotheses"), 3, 1, 8),
                    iterations=bounded_int(preview.get("iterations"), 0, 0, 3),
                    min_references=normalized_min_references,
                    max_references=normalized_max_references,
                    preferences=str(preview.get("preferences") or "") or None,
                    attributes=[
                        str(item).strip()
                        for item in (preview.get("attributes") if isinstance(preview.get("attributes"), list) else [])
                        if str(item).strip()
                    ],
                    constraints=[
                        str(item).strip()
                        for item in (preview.get("constraints") if isinstance(preview.get("constraints"), list) else [])
                        if str(item).strip()
                    ],
                    starting_hypotheses=[
                        str(item).strip()
                        for item in (
                            preview.get("starting_hypotheses")
                            if isinstance(preview.get("starting_hypotheses"), list)
                            else []
                        )
                        if str(item).strip()
                    ],
                    parent_run_id=str(preview.get("parent_run_id") or "") or None,
                    refinement_mode=str(preview.get("refinement_mode") or "new_run"),
                    memory_scope=str(preview.get("memory_scope") or "library"),
                    library_id=str(preview.get("library_id") or "") or None,
                    auto_discover_papers=bool(preview.get("auto_discover_papers", True)),
                    auto_ingest_papers=bool(preview.get("auto_ingest_papers", True)),
                    paper_discovery_limit=bounded_int(preview.get("paper_discovery_limit"), 8, 1, 20),
                    paper_ingest_limit=bounded_int(preview.get("paper_ingest_limit"), 4, 0, 12),
                )
            )
            run_id = payload["run_id"]
            result_summary = {
                "intent": proposal.get("intent"),
                "title": "研究流程已启动",
                "summary": "已创建一键研究运行。系统会先自动检索论文并把可解析 PDF 写入资料库，再生成带证据回填的 hypotheses、reviews 和 tournament ranking。",
                "runId": run_id,
                "researchGoal": preview.get("research_goal"),
                "status": "queued",
                "modeBoundary": (
                    "Demo simulation：只验证 UI/schema。"
                    if preview.get("demo_mode")
                    else "Literature-grounded workflow：需要 MCP/PDF/fulltext 证据；证据不足时必须标记 limited 或 ungrounded。"
                    if preview.get("literature_review")
                    else "Live model workflow：真实模型输出，但未启用文献审查的结论不能伪装成文献支撑。"
                ),
                "nextActions": ["等待运行完成", "查看 timeline", "解释 Elo 排名", "检查最高假设证据"],
                "groundingBoundary": "live_model_workflow",
            }
        elif proposal.get("executionTarget") == "workflow.pdf_parse":
            payload = await execute_pdf_parse_tool_workflow(
                PdfParseToolWorkflowRequest(
                    pdf_path=str(preview["pdf_path"]),
                    phase=str(preview.get("phase") or "paper_reading"),
                    run_id=preview.get("run_id"),
                    fetch_metadata=bool(preview.get("fetch_metadata", True)),
                    ingest_to_knowledge_base=bool(preview.get("ingest_to_knowledge_base", True)),
                    approval=request.approval,
                )
            )
            parse_result = payload.get("parse_result", {})
            result_summary = {
                "intent": proposal.get("intent"),
                "title": parse_result.get("title") or "PDF 解析完成",
                "summary": (
                    f"已生成 {parse_result.get('chunks_count', 0)} 个知识库片段，"
                    f"{parse_result.get('experimental_chunks_count', 0)} 个实验线索。"
                ),
                "status": parse_result.get("status"),
                "pageCount": parse_result.get("page_count"),
                "chunksCount": parse_result.get("chunks_count"),
                "experimentalChunksCount": parse_result.get("experimental_chunks_count"),
                "knowledgeBaseIngested": parse_result.get("knowledge_base_ingested"),
                "ragSearchReady": parse_result.get("rag_search_ready"),
                "sourceReliability": parse_result.get("source_reliability"),
                "resultRef": payload.get("result_ref"),
                "parseRunId": parse_result.get("parse_run_id"),
                "paperId": parse_result.get("paper_id"),
                "artifactSummary": {
                    "solveDir": parse_result.get("solve_dir"),
                    "bibtexReady": bool(parse_result.get("bibtex_path")),
                    "mediaCount": len(parse_result.get("media_assets") or []),
                },
                "nextActions": ["检索这篇论文的证据", "检查候选假设支撑", "继续解析相关 PDF"],
                "groundingBoundary": "parsed_fulltext",
            }
        elif proposal.get("executionTarget") == "workflow.web_extract":
            payload = await execute_web_extract_workflow(
                WebExtractWorkflowRequest(
                    url=str(preview["url"]),
                    phase=str(preview.get("phase") or "literature_review"),
                    run_id=preview.get("run_id"),
                    max_bytes=bounded_int(preview.get("max_bytes"), 1_000_000, 4096, 3_000_000),
                    max_text_chars=bounded_int(preview.get("max_text_chars"), 80_000, 1000, 200_000),
                    ingest_to_knowledge_base=bool(preview.get("ingest_to_knowledge_base", True)),
                    approval=request.approval,
                )
            )
            web_result = payload.get("web_result", {})
            result_summary = {
                "intent": proposal.get("intent"),
                "title": web_result.get("title") or "网页证据已保存",
                "summary": "网页文本已按 best-effort public HTML 证据处理。",
                "finalUrl": web_result.get("final_url"),
                "sourceReliability": web_result.get("source_reliability"),
                "knowledgeBasePaperId": web_result.get("knowledge_base_paper_id"),
                "pdfLinkCount": len(web_result.get("pdf_links") or []),
                "supplementaryLinkCount": len(web_result.get("supplementary_links") or []),
                "resultRef": payload.get("result_ref"),
                "nextActions": ["解析发现的 PDF", "搜索相关证据", "创建人工复核任务"],
                "groundingBoundary": "public_html_best_effort",
            }
        elif proposal.get("executionTarget") == "workflow.web_extract_batch":
            urls = [str(url).strip() for url in preview.get("urls", []) if str(url).strip()][:3]
            web_results: List[Dict[str, Any]] = []
            extract_errors: List[Dict[str, str]] = []
            for url in urls:
                try:
                    payload = await execute_web_extract_workflow(
                        WebExtractWorkflowRequest(
                            url=url,
                            phase=str(preview.get("phase") or "literature_review"),
                            run_id=preview.get("run_id"),
                            max_bytes=bounded_int(preview.get("max_bytes"), 1_000_000, 4096, 3_000_000),
                            max_text_chars=bounded_int(preview.get("max_text_chars"), 60_000, 1000, 200_000),
                            ingest_to_knowledge_base=bool(preview.get("ingest_to_knowledge_base", True)),
                            approval=request.approval,
                        )
                    )
                    web_results.append(payload.get("web_result", {}))
                except HTTPException as exc:
                    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
                    extract_errors.append({"url": url, "error": str(detail.get("message") or detail.get("code") or exc.detail)})
                except Exception as exc:
                    extract_errors.append({"url": url, "error": str(exc)})
            if not web_results:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "web_extract_batch_failed",
                        "message": "高相关网页均未能抓取正文，请换用可公开访问的 URL 或先打开单个网页检查。",
                    },
                )
            query = str(preview.get("query") or "")
            model_name = _web_search_synthesis_model_name(
                str(preview.get("model_name") or os.getenv("COSCIENTIST_RESEARCH_CHAT_MODEL") or "deepseek/deepseek-v4-pro")
            )
            synthesized_answer = await _synthesize_web_extract_answer(
                query=query,
                web_results=web_results,
                errors=extract_errors,
                model_name=model_name,
            )
            result_summary = {
                "intent": proposal.get("intent"),
                "title": "网页内容已抓取并整理",
                "summary": synthesized_answer or _fallback_web_extract_answer(query, web_results, extract_errors),
                "status": "complete",
                "resultCount": len(web_results),
                "failedCount": len(extract_errors),
                "modelName": model_name if synthesized_answer else None,
                "synthesisStatus": "model_synthesized" if synthesized_answer else "fallback_synthesized",
                "items": [
                    {
                        "type": "web_evidence_extract",
                        "title": item.get("title"),
                        "url": item.get("final_url") or item.get("requested_url"),
                        "evidence_summary": item.get("text_preview"),
                        "source_channel": "browser_web_extract",
                        "source_reliability": item.get("source_reliability") or "best_effort_public_html",
                        "paper_id": item.get("knowledge_base_paper_id"),
                    }
                    for item in web_results[:5]
                ],
                "errors": extract_errors,
                "nextActions": ["继续抓取官方文档", "解析发现的 PDF", "用知识库核验候选假设"],
                "groundingBoundary": "public_html_best_effort",
            }
        elif proposal.get("executionTarget") == "workflow.web_search":
            payload = await execute_web_search_workflow(
                WebSearchWorkflowRequest(
                    query=str(preview["query"]),
                    phase=str(preview.get("phase") or "literature_review"),
                    run_id=preview.get("run_id"),
                    limit=bounded_int(preview.get("limit"), 10, 1, 20),
                    domains=list(preview.get("domains") or [])[:8],
                    recency_days=preview.get("recency_days"),
                    approval=request.approval,
                )
            )
            web_search = payload.get("web_search", {})
            result_count = int(web_search.get("result_count") or len(web_search.get("results") or []))
            query = str(web_search.get("query") or preview.get("query") or "")
            model_name = _web_search_synthesis_model_name(
                str(preview.get("model_name") or os.getenv("COSCIENTIST_RESEARCH_CHAT_MODEL") or "deepseek/deepseek-v4-pro")
            )
            synthesized_answer = await _synthesize_web_search_answer(
                query=query,
                web_search=web_search,
                model_name=model_name,
            )
            result_summary = {
                "intent": proposal.get("intent"),
                "title": "公开 Web Search 已整理",
                "summary": synthesized_answer
                or f"公开 Web Search 返回 {result_count} 条结果；这些是 snippet 线索，后续全文支撑仍需抓取网页、解析 PDF 或调用文献 MCP。",
                "query": query,
                "status": "complete",
                "resultCount": result_count,
                "modelName": model_name if synthesized_answer else None,
                "synthesisStatus": "model_synthesized" if synthesized_answer else "tool_summary_only",
                "items": [
                    {
                        "type": "web_search_result",
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "evidence_summary": item.get("snippet"),
                        "source_channel": "web_search_public",
                        "source_reliability": "snippet_only",
                    }
                    for item in (web_search.get("results") or [])[:5]
                ],
                "resultRef": payload.get("result_ref"),
                "nextActions": ["抓取高相关网页作为证据", "解析搜索结果中的 PDF", "继续搜索更精确 query", "用知识库核验候选假设"],
                "groundingBoundary": "public_web_search",
            }
        elif proposal.get("executionTarget") == "workflow.file_snapshot":
            payload = await execute_file_snapshot_workflow(
                FileSnapshotWorkflowRequest(
                    source_path=str(preview["source_path"]),
                    phase=str(preview.get("phase") or "evidence_audit"),
                    run_id=preview.get("run_id"),
                    start_line=bounded_int(preview.get("start_line"), 1, 1, 1_000_000),
                    line_count=bounded_int(preview.get("line_count"), 200, 1, 2000),
                    max_bytes=bounded_int(preview.get("max_bytes"), 1_000_000, 1024, 5_000_000),
                    approval=request.approval,
                )
            )
            file_result = payload.get("file_result", {})
            result_summary = {
                "intent": proposal.get("intent"),
                "title": "本地文件快照已保存",
                "summary": "已按行范围读取本地文件片段，并保存 content hash、快照元数据和 tool result provenance。",
                "status": "complete",
                "toolName": payload.get("tool_name"),
                "relativePath": file_result.get("relative_path"),
                "lineStart": file_result.get("start_line"),
                "lineCount": file_result.get("line_count"),
                "contentSha256": file_result.get("content_sha256"),
                "sourceReliability": file_result.get("source_reliability"),
                "resultRef": payload.get("result_ref"),
                "nextActions": ["基于文件片段继续问答", "把关键片段用于证据核验", "继续读取相邻行范围"],
                "groundingBoundary": "local_file_snapshot",
            }
        elif proposal.get("executionTarget") == "workflow.tool_register_draft":
            payload = await execute_project_tool_registration_workflow(
                ProjectToolRegistrationRequest(
                    tool_name=str(preview["tool_name"]),
                    user_title=preview.get("user_title"),
                    description=str(preview["description"]),
                    toolset=str(preview.get("toolset") or "project_custom"),
                    phases=list(preview.get("phases") or ["evidence_audit"]),
                    risk_level=str(preview.get("risk_level") or "read"),
                    input_schema=preview.get("input_schema") if isinstance(preview.get("input_schema"), dict) else {},
                    execution_boundary=str(preview.get("execution_boundary") or "schema_registered_only"),
                    run_id=preview.get("run_id"),
                    approval=request.approval,
                )
            )
            draft = payload.get("draft", {})
            result_summary = {
                "intent": proposal.get("intent"),
                "title": "项目工具草案已注册",
                "summary": f"已注册 {draft.get('name')} 的 schema-only 工具草案；它会出现在工具注册表中，但执行器仍不可用，不能直接运行代码。",
                "status": "complete",
                "toolName": payload.get("tool_name"),
                "registeredToolName": draft.get("name"),
                "toolset": draft.get("toolset"),
                "phases": draft.get("phases"),
                "riskLevel": draft.get("risk_level"),
                "executionStatus": draft.get("execution_status"),
                "resultRef": payload.get("result_ref"),
                "nextActions": ["在工具注册表查看草案", "人工实现并审查执行器", "为该工具补充测试和权限策略"],
                "groundingBoundary": "tool_registry_draft",
            }
        elif proposal.get("executionTarget") == "workflow.terminal_command":
            payload = await enqueue_terminal_command_background_job(
                TerminalCommandWorkflowRequest(
                    command=str(preview["command"]),
                    workdir=preview.get("workdir"),
                    phase=str(preview.get("phase") or "operator_diagnostics"),
                    run_id=preview.get("run_id"),
                    timeout_seconds=bounded_int(preview.get("timeout_seconds"), 120, 1, 3600),
                    approval=request.approval,
                ),
                background_tasks,
                actor={"source": "research_chat", "permissions": ["runtime:write"]},
            )
            job = payload.get("job", {})
            result_summary = {
                "intent": proposal.get("intent"),
                "title": "本地命令已提交",
                "summary": "本地 terminal 命令已进入后台任务队列；stdout、stderr、manifest 和 guardrail 结果会写入审计记录。",
                "status": job.get("status"),
                "jobId": job.get("job_id"),
                "toolName": payload.get("tool_name"),
                "commandRisk": payload.get("command_risk"),
                "guardrail": payload.get("guardrail"),
                "permissionPolicy": {
                    key: value
                    for key, value in (payload.get("permission_policy") or {}).items()
                    if key != "modes"
                },
                "resultRef": {"job_id": job.get("job_id")} if job.get("job_id") else {},
                "nextActions": ["查看后台任务状态", "打开 stdout/stderr artifact", "基于输出继续下一步诊断"],
                "groundingBoundary": "local_terminal_audit",
            }
        elif proposal.get("executionTarget") == "workflow.ssh_training_command":
            payload = await enqueue_ssh_training_background_job(
                SshTrainingJobRequest(
                    server_id=str(preview["server_id"]),
                    command=str(preview["command"]),
                    workdir=preview.get("workdir"),
                    phase=str(preview.get("phase") or "experiment_execution"),
                    run_id=preview.get("run_id"),
                    timeout_seconds=bounded_int(preview.get("timeout_seconds"), 3600, 1, 86400),
                    approval=request.approval,
                ),
                background_tasks,
            )
            job = payload.get("job", {})
            result_summary = {
                "intent": proposal.get("intent"),
                "title": "SSH 命令已提交",
                "summary": "远程 SSH 命令已进入后台任务队列；远程 stdout、stderr、manifest 和 guardrail 结果会写入审计记录。",
                "status": job.get("status"),
                "jobId": job.get("job_id"),
                "serverId": preview.get("server_id"),
                "toolName": payload.get("tool_name"),
                "commandRisk": payload.get("command_risk"),
                "guardrail": payload.get("guardrail"),
                "permissionPolicy": {
                    key: value
                    for key, value in (payload.get("permission_policy") or {}).items()
                    if key != "modes"
                },
                "resultRef": {"job_id": job.get("job_id")} if job.get("job_id") else {},
                "nextActions": ["查看后台任务状态", "打开远程 stdout/stderr artifact", "根据输出继续训练或部署诊断"],
                "groundingBoundary": "remote_ssh_audit",
            }
        elif proposal.get("executionTarget") == "workflow.evidence_literature_verification":
            payload = await execute_evidence_literature_verification_workflow(
                EvidenceVerificationWorkflowRequest(
                    hypothesis_text=str(preview["hypothesis_text"]),
                    run_id=preview.get("run_id"),
                    paper_id=preview.get("paper_id"),
                    library_id=preview.get("library_id"),
                    max_papers=bounded_int(preview.get("max_papers"), 5, 1, 10),
                    approval=request.approval,
                )
            )
            report = payload.get("verification_report", {})
            result_summary = {
                "intent": proposal.get("intent"),
                **report,
                "resultRef": payload.get("result_ref") or report.get("resultRef"),
                "mcpResultRef": payload.get("mcp_result_ref"),
                "groundingBoundary": report.get("groundingBoundary") or "literature_mcp_audit",
            }
        else:
            raise HTTPException(
                status_code=422,
                detail={"code": "unsupported_chat_action", "message": "这张确认卡片暂不支持执行。"},
            )
    except HTTPException as exc:
        record["status"] = "error"
        record["updated_at"] = time.time()
        record["error_summary"] = _safe_chat_error(exc)
        try:
            knowledge_base.upsert_research_chat_action(
                action_id=action_id,
                session_id=record["session_id"],
                status="error",
                proposal=proposal,
                error_summary=record["error_summary"],
            )
        except Exception as persist_exc:
            print(f"Research chat action error persistence failed for {action_id}: {persist_exc}", file=sys.stderr)
        assistant_message = {
            "kind": "error",
            "text": record["error_summary"],
            "result": {"intent": proposal.get("intent"), "title": proposal.get("title"), "summary": record["error_summary"]},
        }
        _record_chat_message(record["session_id"], "assistant", record["error_summary"], assistant_message)
        return {
            "session_id": record["session_id"],
            "assistant_message": assistant_message,
            "state": "error",
        }

    record["status"] = "complete"
    record["result_ref"] = result_summary.get("resultRef")
    record["updated_at"] = time.time()
    action_result_ref = result_summary.get("resultRef")
    if not action_result_ref and result_summary.get("runId"):
        action_result_ref = {"run_id": result_summary.get("runId")}
    try:
        knowledge_base.upsert_research_chat_action(
            action_id=action_id,
            session_id=record["session_id"],
            status="complete",
            proposal=proposal,
            result_ref=action_result_ref if isinstance(action_result_ref, dict) else {},
        )
    except Exception as exc:
        print(f"Research chat action complete persistence failed for {action_id}: {exc}", file=sys.stderr)
    assistant_message = {
        "kind": "result_summary",
        "text": result_summary["summary"],
        "result": result_summary,
    }
    _record_chat_message(record["session_id"], "assistant", result_summary["summary"], assistant_message)
    return {
        "session_id": record["session_id"],
        "assistant_message": assistant_message,
        "state": "complete",
    }


@app.post("/api/research-chat/actions/{action_id}/cancel")
async def cancel_research_chat_action(action_id: str) -> Dict[str, Any]:
    record = research_chat_action_proposals.get(action_id) or knowledge_base.get_research_chat_action(action_id)
    if not record:
        raise HTTPException(status_code=404, detail={"code": "chat_action_not_found", "message": "没有找到这张确认卡片。"})
    record["status"] = "cancelled"
    record["updated_at"] = time.time()
    proposal = record.get("proposal", {})
    try:
        knowledge_base.upsert_research_chat_action(
            action_id=action_id,
            session_id=record["session_id"],
            status="cancelled",
            proposal=proposal,
        )
    except Exception as exc:
        print(f"Research chat action cancel persistence failed for {action_id}: {exc}", file=sys.stderr)
    assistant_message = {
        "kind": "status",
        "text": "已取消，未执行任何写入型工具。",
    }
    _record_chat_message(record["session_id"], "assistant", assistant_message["text"], assistant_message)
    return {
        "session_id": record["session_id"],
        "assistant_message": assistant_message,
        "state": "idle",
    }


@app.post("/api/tools/workflows/browser-screenshot")
async def execute_browser_screenshot_workflow(request: BrowserScreenshotWorkflowRequest) -> Dict[str, Any]:
    registry = research_tool_registry()
    spec = registry.get("browser.capture_screenshot")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})

    phase = canonical_phase(request.phase)
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )

    availability = spec.describe()["availability"]
    if not availability.get("available"):
        raise HTTPException(status_code=424, detail={"code": "tool_unavailable", "availability": availability})
    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="browser.capture_screenshot",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    arguments = {
        "url": request.url,
        "viewport_width": request.viewport_width,
        "viewport_height": request.viewport_height,
        "full_page": request.full_page,
        "timeout_ms": request.timeout_ms,
    }
    if request.run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=request.run_id,
            tool_name="browser.capture_screenshot",
            phase=phase,
            arguments=arguments,
        )
        if repeated >= 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repeated_identical_browser_screenshot",
                    "message": "同一 run 已执行过相同浏览器截图 workflow，guardrail 阻止重复抓取。",
                    "repeat_count": repeated,
                },
            )

    try:
        browser_result = await asyncio.to_thread(
            capture_browser_screenshot,
            request.url,
            artifact_root=KB_ROOT / "browser_evidence",
            viewport_width=request.viewport_width,
            viewport_height=request.viewport_height,
            full_page=request.full_page,
            timeout_ms=request.timeout_ms,
        )
    except BrowserCaptureError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "browser_screenshot_failed",
                "message": str(exc),
            },
        )
    except Exception:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "browser_screenshot_failed",
                "message": "浏览器截图暂时失败，请确认 Playwright 浏览器已安装且 URL 可公开访问。",
            },
        )

    payload = browser_result.payload
    public_payload = browser_result.public_payload()
    result_ref: Optional[Dict[str, Any]] = None
    if request.run_id:
        result_ref = knowledge_base.store_tool_result(
            run_id=request.run_id,
            tool_name="browser.capture_screenshot",
            phase=phase,
            content=payload,
            result_kind="browser_screenshot",
            summary=f"Browser screenshot captured for {payload.get('final_url') or request.url}.",
        )
        knowledge_base.record_research_tool_call(
            run_id=request.run_id,
            tool_name="browser.capture_screenshot",
            phase=phase,
            status="complete",
            arguments=arguments,
            result_summary=f"Browser screenshot captured title={payload.get('title') or 'untitled'}.",
            metadata={
                "toolset": spec.toolset,
                "risk_level": spec.risk_level,
                "availability": availability,
                "approval": approval,
                "result_ref": result_ref,
                "screenshot_path": payload.get("screenshot_path"),
                "metadata_path": payload.get("metadata_path"),
            },
        )
        knowledge_base.record_evidence_retrieval(
            run_id=request.run_id,
            tool_name="browser.capture_screenshot",
            query=request.url,
            limit_value=1,
            results=[
                {
                    "result_ref": result_ref,
                    "title": payload.get("title"),
                    "final_url": payload.get("final_url"),
                    "screenshot_path": payload.get("screenshot_path"),
                    "source_reliability": payload.get("source_reliability"),
                }
            ],
        )

    return {
        "tool_name": "browser.capture_screenshot",
        "phase": phase,
        "toolset": spec.toolset,
        "risk_level": spec.risk_level,
        "run_id": request.run_id,
        "approval": approval,
        "availability": availability,
        "policy": authorization.get("policy"),
        "result_ref": result_ref,
        "browser_result": public_payload,
    }


@app.post("/api/tools/workflows/file-snapshot")
async def execute_file_snapshot_workflow(request: FileSnapshotWorkflowRequest) -> Dict[str, Any]:
    registry = research_tool_registry()
    spec = registry.get("file.source_snapshot")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})

    phase = canonical_phase(request.phase)
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )
    availability = spec.describe()["availability"]
    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="file.source_snapshot",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    arguments = {
        "source_path": request.source_path,
        "start_line": request.start_line,
        "line_count": request.line_count,
        "max_bytes": request.max_bytes,
    }
    if request.run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=request.run_id,
            tool_name="file.source_snapshot",
            phase=phase,
            arguments=arguments,
        )
        if repeated >= 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repeated_identical_file_snapshot",
                    "message": "同一 run 已执行过相同文件快照 workflow，guardrail 阻止重复读取。",
                    "repeat_count": repeated,
                },
            )

    try:
        snapshot = await asyncio.to_thread(
            snapshot_source_file,
            request.source_path,
            source_root=SOURCE_EVIDENCE_ROOT,
            artifact_root=KB_ROOT / "source_evidence",
            start_line=request.start_line,
            line_count=request.line_count,
            max_bytes=request.max_bytes,
        )
    except FileEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "file_snapshot_guardrail_failed",
                "message": str(exc),
            },
        )

    payload = snapshot.payload
    public_payload = snapshot.public_payload()
    result_ref = knowledge_base.store_tool_result(
        run_id=request.run_id,
        tool_name="file.source_snapshot",
        phase=phase,
        content=payload,
        result_kind="source_file_snapshot",
        summary=f"Source file snapshot captured for {payload.get('relative_path')}.",
    )
    if request.run_id:
        knowledge_base.record_research_tool_call(
            run_id=request.run_id,
            tool_name="file.source_snapshot",
            phase=phase,
            status="complete",
            arguments=arguments,
            result_summary=f"Source file snapshot captured relative_path={payload.get('relative_path')}.",
            metadata={
                "toolset": spec.toolset,
                "risk_level": spec.risk_level,
                "availability": availability,
                "approval": approval,
                "result_ref": result_ref,
                "content_sha256": payload.get("content_sha256"),
                "snapshot_path": payload.get("snapshot_path"),
            },
        )
        knowledge_base.record_evidence_retrieval(
            run_id=request.run_id,
            tool_name="file.source_snapshot",
            query=payload.get("relative_path") or request.source_path,
            limit_value=request.line_count,
            results=[
                {
                    "result_ref": result_ref,
                    "relative_path": payload.get("relative_path"),
                    "content_sha256": payload.get("content_sha256"),
                    "source_reliability": payload.get("source_reliability"),
                }
            ],
        )

    return {
        "tool_name": "file.source_snapshot",
        "phase": phase,
        "toolset": spec.toolset,
        "risk_level": spec.risk_level,
        "run_id": request.run_id,
        "approval": approval,
        "availability": availability,
        "policy": authorization.get("policy"),
        "result_ref": result_ref,
        "file_result": public_payload,
    }


@app.post("/api/tools/workflows/tool-register-draft")
async def execute_project_tool_registration_workflow(request: ProjectToolRegistrationRequest) -> Dict[str, Any]:
    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="tool.register_draft",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    registry = research_tool_registry()
    tool_name = _slug_project_tool_name(request.tool_name)
    if registry.get(tool_name):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "project_tool_name_conflicts_with_builtin",
                "message": f"{tool_name} 已是内置工具，不能作为项目草案覆盖。",
            },
        )
    drafts = _load_project_tool_drafts()
    if any(str(item.get("name") or "") == tool_name for item in drafts):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "project_tool_draft_exists",
                "message": f"{tool_name} 已注册为项目工具草案；请换一个 ID 或先人工审查已有草案。",
            },
        )

    phases = _normalize_project_tool_phases(request.phases)
    input_schema = _normalize_project_tool_input_schema(request.input_schema)
    toolset = _normalize_project_toolset(request.toolset)
    boundary = str(request.execution_boundary or "schema_registered_only").strip()[:1000]
    if boundary and re.search(r"(?:write\s+code|exec|subprocess|shell|powershell|bash|python\s+-c|任意代码|执行代码)", boundary, re.I):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "project_tool_boundary_requests_execution",
                "message": "工具草案的 execution_boundary 不能要求执行代码；请只描述 schema 和人工实现边界。",
            },
        )

    now = time.time()
    draft: Dict[str, Any] = {
        "name": tool_name,
        "user_title": request.user_title or tool_name,
        "description": request.description.strip(),
        "toolset": toolset,
        "phases": phases,
        "risk_level": request.risk_level,
        "input_schema": input_schema,
        "execution_boundary": boundary or "schema_registered_only",
        "path_policy": "source_evidence_root_only_for_file_inputs",
        "execution_status": "schema_registered_only",
        "registered_at": now,
        "registered_by": "research_chat_confirmation",
        "approval": approval,
    }
    result_ref = knowledge_base.store_tool_result(
        run_id=request.run_id,
        tool_name="tool.register_draft",
        phase="operator_diagnostics",
        content=draft,
        result_kind="project_tool_registration_draft",
        summary=f"Project tool draft registered: {tool_name}.",
    )
    draft["result_ref"] = result_ref
    drafts.append(draft)
    _save_project_tool_drafts(drafts)

    if request.run_id:
        knowledge_base.record_research_tool_call(
            run_id=request.run_id,
            tool_name="tool.register_draft",
            phase="operator_diagnostics",
            status="complete",
            arguments={
                "tool_name": tool_name,
                "toolset": toolset,
                "phases": phases,
                "risk_level": request.risk_level,
            },
            result_summary=f"Project tool draft registered: {tool_name}.",
            metadata={
                "approval": approval,
                "result_ref": result_ref,
                "execution_status": "schema_registered_only",
            },
        )

    return {
        "tool_name": "tool.register_draft",
        "run_id": request.run_id,
        "approval": approval,
        "result_ref": result_ref,
        "draft": draft,
        "registry_tool": _project_tool_draft_to_registry_tool(draft),
    }


@app.post("/api/tools/workflows/code-analysis")
async def execute_code_analysis_workflow(request: CodeAnalysisWorkflowRequest) -> Dict[str, Any]:
    registry = research_tool_registry()
    spec = registry.get("code.execute_analysis")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})

    phase = canonical_phase(request.phase)
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )

    availability = spec.describe()["availability"]
    if not availability.get("available"):
        raise HTTPException(status_code=424, detail={"code": "tool_unavailable", "availability": availability})

    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="code.execute_analysis",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    arguments = {
        "code": request.code,
        "timeout_seconds": request.timeout_seconds,
    }
    if request.run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=request.run_id,
            tool_name="code.execute_analysis",
            phase=phase,
            arguments=arguments,
        )
        if repeated >= 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repeated_identical_code_analysis",
                    "message": "同一 run 已执行过相同受限分析代码，guardrail 阻止重复执行。",
                    "repeat_count": repeated,
                },
            )

    result = await asyncio.to_thread(
        execute_restricted_python,
        request.code,
        timeout_seconds=request.timeout_seconds,
        root_dir=KB_ROOT / "analysis_jobs",
    )
    result_payload = result.to_dict()
    result_ref: Optional[Dict[str, Any]] = None
    if request.run_id:
        result_ref = knowledge_base.store_tool_result(
            run_id=request.run_id,
            tool_name="code.execute_analysis",
            phase=phase,
            content=result_payload,
            result_kind="restricted_python_analysis",
            summary=f"Restricted Python analysis finished with status={result.status}.",
        )
        knowledge_base.record_research_tool_call(
            run_id=request.run_id,
            tool_name="code.execute_analysis",
            phase=phase,
            status=result.status,
            arguments=arguments,
            result_summary=f"Restricted Python analysis status={result.status}, returncode={result.returncode}.",
            metadata={
                "toolset": spec.toolset,
                "risk_level": spec.risk_level,
                "availability": availability,
                "approval": approval,
                "result_ref": result_ref,
                "work_dir": result.work_dir,
                "guardrail": result.guardrail,
            },
        )

    return {
        "tool_name": "code.execute_analysis",
        "phase": phase,
        "toolset": spec.toolset,
        "risk_level": spec.risk_level,
        "run_id": request.run_id,
        "approval": approval,
        "availability": availability,
        "policy": authorization.get("policy"),
        "result_ref": result_ref,
        "analysis_result": result_payload,
    }


async def run_code_analysis_background_job(
    job_id: str,
    request: CodeAnalysisWorkflowRequest,
) -> None:
    knowledge_base.update_background_job(job_id, status="running")
    try:
        payload = await execute_code_analysis_workflow(request)
        knowledge_base.update_background_job(
            job_id,
            status=payload.get("analysis_result", {}).get("status", "complete"),
            result_ref={
                "tool_result": payload.get("result_ref"),
                "analysis_status": payload.get("analysis_result", {}).get("status"),
            },
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        knowledge_base.update_background_job(
            job_id,
            status="error",
            error_message=json.dumps(detail, ensure_ascii=False),
        )
    except Exception as exc:
        knowledge_base.update_background_job(
            job_id,
            status="error",
            error_message=str(exc),
        )


@app.post("/api/tools/workflows/code-analysis/background")
async def enqueue_code_analysis_workflow(
    request: CodeAnalysisWorkflowRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    phase = canonical_phase(request.phase)
    require_tool_workflow_approval(
        request.approval,
        expected_scope="code.execute_analysis",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job = knowledge_base.create_background_job(
        job_id=job_id,
        run_id=request.run_id,
        workflow_name="code.execute_analysis",
        phase=phase,
        arguments={
            "code": request.code,
            "timeout_seconds": request.timeout_seconds,
            "approval_scope": request.approval.scope,
        },
    )
    background_tasks.add_task(run_code_analysis_background_job, job_id, request)
    return {"job": job}


def attach_compute_execution_result(
    *,
    run_id: Optional[str],
    hypothesis_index: Optional[int],
    job_id: str,
    result_payload: Dict[str, Any],
    result_ref: Dict[str, Any],
    executor: str,
    manifest: Optional[Dict[str, Any]] = None,
) -> None:
    """Attach raw experiment provenance without interpreting scientific meaning."""
    if run_id is None or hypothesis_index is None:
        return
    record = load_run_record(run_id)
    if not record or hypothesis_index >= len(record.hypotheses):
        return
    hypothesis = record.hypotheses[hypothesis_index]
    experiment_runs = hypothesis.get("experiment_runs")
    experiment_runs = experiment_runs if isinstance(experiment_runs, list) else []
    experiment_runs.append(
        {
            "job_id": job_id,
            "executor": executor,
            "status": result_payload.get("status"),
            "returncode": result_payload.get("returncode"),
            "duration_seconds": result_payload.get("duration_seconds"),
            "result_ref": result_ref,
            "artifacts": result_payload.get("artifacts") or [],
            "manifest": manifest or {},
            "interpretation_status": "awaiting_human_interpretation",
            "boundary": (
                "Successful execution only proves the script ran. It does not support or contradict "
                "the hypothesis until an approved scientific interpretation is recorded."
            ),
        }
    )
    hypothesis["experiment_runs"] = experiment_runs[-20:]
    record.updated_at = time.time()
    add_event(
        record,
        "Experiment",
        "Experiment result awaiting interpretation",
        f"{executor} experiment {job_id} finished and is attached to hypothesis {hypothesis_index + 1}.",
        "complete",
    )
    persist_run_record(record)


def attach_experiment_execution_result(
    *,
    request: ExperimentBackgroundJobRequest,
    job_id: str,
    result_payload: Dict[str, Any],
    result_ref: Dict[str, Any],
) -> None:
    attach_compute_execution_result(
        run_id=request.run_id,
        hypothesis_index=request.hypothesis_index,
        job_id=job_id,
        result_payload=result_payload,
        result_ref=result_ref,
        executor="local_python",
        manifest={
            "script_path": request.script_path,
            "args": request.args,
            "timeout_seconds": request.timeout_seconds,
        },
    )


async def run_experiment_background_job(
    job_id: str,
    request: ExperimentBackgroundJobRequest,
) -> None:
    knowledge_base.update_background_job(job_id, status="running")
    phase = canonical_phase(request.phase)
    arguments = {
        "script_path": request.script_path,
        "args": request.args,
        "timeout_seconds": request.timeout_seconds,
        "hypothesis_index": request.hypothesis_index,
    }
    try:
        result = await asyncio.to_thread(
            run_python_experiment,
            request.script_path,
            experiment_root=EXPERIMENT_ROOT,
            artifact_root=EXPERIMENT_ARTIFACT_ROOT,
            args=request.args,
            timeout_seconds=request.timeout_seconds,
        )
        result_payload = result.to_dict()
        result_ref = knowledge_base.store_tool_result(
            run_id=request.run_id,
            tool_name="experiment.background_job",
            phase=phase,
            content=result_payload,
            result_kind="experiment_run",
            summary=f"Experiment background job finished with status={result.status}.",
        )
        if request.run_id:
            knowledge_base.record_research_tool_call(
                run_id=request.run_id,
                tool_name="experiment.background_job",
                phase=phase,
                status=result.status,
                arguments=arguments,
                result_summary=f"Experiment script returncode={result.returncode}, status={result.status}.",
                metadata={
                    "result_ref": result_ref,
                    "script_path": result.script_path,
                    "run_dir": result.run_dir,
                    "artifacts": result.artifacts,
                    "approval": request.approval.model_dump(),
                },
            )
        attach_experiment_execution_result(
            request=request,
            job_id=job_id,
            result_payload=result_payload,
            result_ref=result_ref,
        )
        knowledge_base.update_background_job(
            job_id,
            status=result.status,
            result_ref={
                "tool_result": result_ref,
                "experiment_status": result.status,
                "artifacts": result.artifacts,
            },
        )
    except Exception as exc:
        detail = {"code": "experiment_job_failed", "message": str(exc)}
        knowledge_base.update_background_job(
            job_id,
            status="error",
            error_message=json.dumps(detail, ensure_ascii=False),
        )


@app.post("/api/tools/workflows/experiment-job")
async def enqueue_experiment_background_job(
    request: ExperimentBackgroundJobRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    registry = research_tool_registry()
    spec = registry.get("experiment.background_job")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})

    phase = canonical_phase(request.phase)
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )

    availability = spec.describe()["availability"]
    if not availability.get("available"):
        raise HTTPException(status_code=424, detail={"code": "tool_unavailable", "availability": availability})
    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="experiment.background_job",
    )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    if request.run_id and request.hypothesis_index is not None:
        record = load_run_record(request.run_id)
        if not record or request.hypothesis_index >= len(record.hypotheses):
            raise HTTPException(status_code=404, detail="Hypothesis not found")
    try:
        guardrail = validate_experiment_script(request.script_path, experiment_root=EXPERIMENT_ROOT)
    except ExperimentRunnerError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "experiment_guardrail_failed",
                "message": str(exc),
            },
        )

    arguments = {
        "script_path": request.script_path,
        "args": request.args,
        "timeout_seconds": request.timeout_seconds,
        "hypothesis_index": request.hypothesis_index,
        "approval_scope": request.approval.scope,
    }
    if request.run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=request.run_id,
            tool_name="experiment.background_job",
            phase=phase,
            arguments={k: v for k, v in arguments.items() if k != "approval_scope"},
        )
        if repeated >= 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repeated_identical_experiment_job",
                    "message": "同一 run 已执行过相同实验脚本和参数，guardrail 阻止重复执行。",
                    "repeat_count": repeated,
                },
            )

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job = knowledge_base.create_background_job(
        job_id=job_id,
        run_id=request.run_id,
        workflow_name="experiment.background_job",
        phase=phase,
        arguments={
            **arguments,
            "resolved_script_path": guardrail["script_path"],
            "experiment_root": guardrail["experiment_root"],
        },
    )
    background_tasks.add_task(run_experiment_background_job, job_id, request)
    return {
        "job": job,
        "tool_name": "experiment.background_job",
        "phase": phase,
        "availability": availability,
        "policy": authorization.get("policy"),
        "approval": approval,
        "guardrail": guardrail,
    }


async def run_terminal_command_background_job(
    job_id: str,
    request: TerminalCommandWorkflowRequest,
    approval: Dict[str, Any],
    *,
    allow_any_workdir: bool,
) -> None:
    knowledge_base.update_background_job(job_id, status="running")
    phase = canonical_phase(request.phase)
    arguments = {
        "command": redact_sensitive_text(request.command),
        "workdir": request.workdir,
        "timeout_seconds": request.timeout_seconds,
    }
    if approval.get("permission_mode"):
        arguments["permission_mode"] = approval["permission_mode"]
    try:
        result = await asyncio.to_thread(
            run_terminal_command,
            command=request.command,
            workdir=request.workdir,
            artifact_root=TERMINAL_COMMAND_ARTIFACT_ROOT,
            timeout_seconds=request.timeout_seconds,
            default_root=ROOT,
            allow_any_workdir=allow_any_workdir,
            job_id=job_id,
        )
        result_payload = result.to_dict()
        result_ref = knowledge_base.store_tool_result(
            run_id=request.run_id,
            tool_name="terminal.command",
            phase=phase,
            content=result_payload,
            result_kind="terminal_command_run",
            summary=f"Terminal command finished with status={result.status}, returncode={result.returncode}.",
        )
        if request.run_id:
            knowledge_base.record_research_tool_call(
                run_id=request.run_id,
                tool_name="terminal.command",
                phase=phase,
                status=result.status,
                arguments=arguments,
                result_summary=f"Terminal command returncode={result.returncode}, status={result.status}.",
                metadata={
                    "result_ref": result_ref,
                    "run_dir": result.run_dir,
                    "artifacts": result.artifacts,
                    "guardrail": result.guardrail,
                    "approval": approval,
                },
            )
        knowledge_base.update_background_job(
            job_id,
            status=result.status,
            result_ref={
                "tool_result": result_ref,
                "terminal_status": result.status,
                "returncode": result.returncode,
                "artifacts": result.artifacts,
            },
        )
    except Exception as exc:
        detail = {"code": "terminal_command_failed", "message": str(exc)}
        if request.run_id:
            knowledge_base.record_research_tool_call(
                run_id=request.run_id,
                tool_name="terminal.command",
                phase=phase,
                status="error",
                arguments=arguments,
                result_summary=f"Terminal command workflow failed: {exc}",
                metadata={
                    "approval": approval,
                    "error": str(exc),
                },
            )
        knowledge_base.update_background_job(
            job_id,
            status="error",
            error_message=json.dumps(detail, ensure_ascii=False),
        )


@app.post("/api/tools/workflows/terminal-command")
async def enqueue_terminal_command_background_job(
    request: TerminalCommandWorkflowRequest,
    background_tasks: BackgroundTasks,
    actor: Dict[str, Any] = Depends(require_permission("runtime:write")),
) -> Dict[str, Any]:
    registry = research_tool_registry()
    spec = registry.get("terminal.command")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})

    phase = canonical_phase(request.phase)
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )

    availability = spec.describe()["availability"]
    shell_availability = terminal_command_status()
    if not availability.get("available") or not shell_availability.get("available"):
        raise HTTPException(
            status_code=424,
            detail={
                "code": "tool_unavailable",
                "availability": availability,
                "terminal": shell_availability,
            },
        )
    approval, permission_policy, command_risk = resolve_command_workflow_approval(
        request.approval,
        expected_scope="terminal.command",
        command=request.command,
    )
    allow_any_workdir = permission_policy.get("mode") == "full_access"
    guardrail = validate_terminal_command(
        request.command,
        workdir=request.workdir,
        default_root=ROOT,
        allow_any_workdir=allow_any_workdir,
    )
    arguments = {
        "command": redact_sensitive_text(request.command),
        "workdir": request.workdir,
        "timeout_seconds": request.timeout_seconds,
        "approval_scope": request.approval.scope,
        "permission_mode": permission_policy.get("mode"),
    }
    if not guardrail.get("allowed"):
        if request.run_id:
            knowledge_base.record_research_tool_call(
                run_id=request.run_id,
                tool_name="terminal.command",
                phase=phase,
                status="blocked",
                arguments={key: value for key, value in arguments.items() if key != "approval_scope"},
                result_summary=f"Terminal command blocked: {guardrail.get('message')}",
                metadata={
                    "guardrail": guardrail,
                    "approval": approval,
                    "permission_policy": permission_policy,
                },
            )
        raise HTTPException(
            status_code=422,
            detail={
                "code": guardrail.get("code", "terminal_command_guardrail_failed"),
                "message": guardrail.get("message", "Terminal command blocked by guardrail."),
                "guardrail": guardrail,
                "command_risk": command_risk,
                "permission_policy": {key: value for key, value in permission_policy.items() if key != "modes"},
            },
        )
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    if request.run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=request.run_id,
            tool_name="terminal.command",
            phase=phase,
            arguments={key: value for key, value in arguments.items() if key != "approval_scope"},
        )
        if repeated >= 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repeated_identical_terminal_command",
                    "message": "同一 run 已执行过相同本地终端命令，guardrail 阻止重复提交。",
                    "repeat_count": repeated,
                },
            )

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job = knowledge_base.create_background_job(
        job_id=job_id,
        run_id=request.run_id,
        workflow_name="terminal.command",
        phase=phase,
        arguments={
            **arguments,
            "guardrail": guardrail,
            "command_risk": command_risk,
            "artifact_root": str(TERMINAL_COMMAND_ARTIFACT_ROOT),
        },
    )
    background_tasks.add_task(
        run_terminal_command_background_job,
        job_id,
        request,
        approval,
        allow_any_workdir=allow_any_workdir,
    )
    return {
        "job": job,
        "tool_name": "terminal.command",
        "phase": phase,
        "availability": availability,
        "terminal": shell_availability,
        "policy": authorization.get("policy"),
        "approval": approval,
        "guardrail": guardrail,
        "command_risk": command_risk,
        "permission_policy": permission_policy,
        "actor": actor,
    }


@app.get("/api/tools/ssh/servers")
async def get_ssh_training_servers() -> Dict[str, Any]:
    servers = list_ssh_training_servers()
    return {
        "servers": servers,
        "count": len(servers),
        "availability": ssh_training_status(),
        "mcp_server_templates": build_ssh_mcp_server_templates(),
    }


async def run_ssh_training_background_job(
    job_id: str,
    request: SshTrainingJobRequest,
    approval: Optional[Dict[str, Any]] = None,
) -> None:
    knowledge_base.update_background_job(job_id, status="running")
    phase = canonical_phase(request.phase)
    arguments = {
        "server_id": request.server_id,
        "command": redact_sensitive_text(request.command),
        "workdir": request.workdir,
        "timeout_seconds": request.timeout_seconds,
    }
    if approval and approval.get("permission_mode"):
        arguments["permission_mode"] = approval["permission_mode"]
    try:
        result = await asyncio.to_thread(
            run_ssh_training_command,
            server_id=request.server_id,
            command=request.command,
            workdir=request.workdir,
            artifact_root=SSH_TRAINING_ARTIFACT_ROOT,
            timeout_seconds=request.timeout_seconds,
            job_id=job_id,
        )
        result_payload = result.to_dict()
        result_ref = knowledge_base.store_tool_result(
            run_id=request.run_id,
            tool_name="ssh.training_command",
            phase=phase,
            content=result_payload,
            result_kind="ssh_training_run",
            summary=(
                f"SSH training command on {result.server_id} finished "
                f"with status={result.status}, returncode={result.returncode}."
            ),
        )
        if request.run_id:
            knowledge_base.record_research_tool_call(
                run_id=request.run_id,
                tool_name="ssh.training_command",
                phase=phase,
                status=result.status,
                arguments=arguments,
                result_summary=(
                    f"SSH training command on {result.server_id} returncode={result.returncode}, "
                    f"status={result.status}."
                ),
                metadata={
                    "result_ref": result_ref,
                    "server_id": result.server_id,
                    "ssh_alias": result.ssh_alias,
                    "run_dir": result.run_dir,
                    "artifacts": result.artifacts,
                    "guardrail": result.guardrail,
                    "approval": approval or request.approval.model_dump(),
                },
            )
        knowledge_base.update_background_job(
            job_id,
            status=result.status,
            result_ref={
                "tool_result": result_ref,
                "ssh_status": result.status,
                "server_id": result.server_id,
                "returncode": result.returncode,
                "artifacts": result.artifacts,
            },
        )
    except Exception as exc:
        detail = {"code": "ssh_training_job_failed", "message": str(exc)}
        if request.run_id:
            knowledge_base.record_research_tool_call(
                run_id=request.run_id,
                tool_name="ssh.training_command",
                phase=phase,
                status="error",
                arguments=arguments,
                result_summary=f"SSH training workflow failed: {exc}",
                metadata={
                    "server_id": request.server_id,
                    "approval": approval or request.approval.model_dump(),
                    "error": str(exc),
                },
            )
        knowledge_base.update_background_job(
            job_id,
            status="error",
            error_message=json.dumps(detail, ensure_ascii=False),
        )


@app.post("/api/tools/workflows/ssh-training-job")
async def enqueue_ssh_training_background_job(
    request: SshTrainingJobRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    registry = research_tool_registry()
    spec = registry.get("ssh.training_command")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})

    phase = canonical_phase(request.phase)
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )

    availability = spec.describe()["availability"]
    if not availability.get("available"):
        raise HTTPException(status_code=424, detail={"code": "tool_unavailable", "availability": availability})
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        guardrail = validate_ssh_training_command(
            request.command,
            server_id=request.server_id,
            workdir=request.workdir,
        )
    except SshTrainingError as exc:
        guardrail = {"allowed": False, "code": "ssh_training_guardrail_failed", "message": str(exc)}
    permission_policy = get_command_permission_policy(KB_ROOT)
    command_risk = classify_command_risk(request.command)
    arguments = {
        "server_id": request.server_id,
        "command": redact_sensitive_text(request.command),
        "workdir": request.workdir,
        "timeout_seconds": request.timeout_seconds,
        "approval_scope": request.approval.scope,
        "permission_mode": permission_policy.get("mode"),
    }
    if not guardrail.get("allowed"):
        approval = require_tool_workflow_approval(
            request.approval,
            expected_scope="ssh.training_command",
        )
        if request.run_id:
            knowledge_base.record_research_tool_call(
                run_id=request.run_id,
                tool_name="ssh.training_command",
                phase=phase,
                status="blocked",
                arguments={key: value for key, value in arguments.items() if key != "approval_scope"},
                result_summary=f"SSH training command blocked: {guardrail.get('message')}",
                metadata={
                    "server_id": request.server_id,
                    "guardrail": guardrail,
                    "approval": approval,
                    "permission_policy": permission_policy,
                    "command_risk": command_risk,
                },
            )
        raise HTTPException(
            status_code=422,
            detail={
                "code": guardrail.get("code", "ssh_training_guardrail_failed"),
                "message": guardrail.get("message", "SSH training command blocked by guardrail."),
                "guardrail": guardrail,
                "command_risk": command_risk,
                "permission_policy": {key: value for key, value in permission_policy.items() if key != "modes"},
            },
        )
    approval, permission_policy, command_risk = resolve_command_workflow_approval(
        request.approval,
        expected_scope="ssh.training_command",
        command=request.command,
    )

    if request.run_id:
        repeated = knowledge_base.count_matching_tool_calls(
            run_id=request.run_id,
            tool_name="ssh.training_command",
            phase=phase,
            arguments={key: value for key, value in arguments.items() if key != "approval_scope"},
        )
        if repeated >= 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repeated_identical_ssh_training_job",
                    "message": "同一 run 已执行过相同 SSH 训练命令，guardrail 阻止重复提交。",
                    "repeat_count": repeated,
                },
            )

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job = knowledge_base.create_background_job(
        job_id=job_id,
        run_id=request.run_id,
        workflow_name="ssh.training_command",
        phase=phase,
        arguments={
            **arguments,
            "guardrail": guardrail,
            "command_risk": command_risk,
            "artifact_root": str(SSH_TRAINING_ARTIFACT_ROOT),
        },
    )
    background_tasks.add_task(run_ssh_training_background_job, job_id, request, approval)
    return {
        "job": job,
        "tool_name": "ssh.training_command",
        "phase": phase,
        "availability": availability,
        "policy": authorization.get("policy"),
        "approval": approval,
        "guardrail": guardrail,
        "command_risk": command_risk,
        "permission_policy": permission_policy,
    }


@app.get("/api/tools/background-jobs")
async def list_background_jobs(
    run_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    jobs = knowledge_base.list_background_jobs(run_id=run_id, limit=max(1, min(limit, 200)))
    return {"jobs": jobs, "count": len(jobs), "run_id": run_id}


@app.get("/api/tools/background-jobs/{job_id}")
async def get_background_job(job_id: str) -> Dict[str, Any]:
    job = knowledge_base.get_background_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "background_job_not_found",
                "message": "没有找到这个后台任务。",
            },
        )
    return job


def worker_status_counts() -> Dict[str, int]:
    statuses = ("queued", "leased", "running", "retrying", "blocked", "complete", "error", "cancelled")
    return {
        f"{status}_count": len(knowledge_base.list_work_items(status=status, limit=200))
        for status in statuses
    }


def summarize_worker_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "work_item_id": item.get("work_item_id"),
        "run_id": item.get("run_id"),
        "workflow_name": item.get("workflow_name"),
        "phase": item.get("phase"),
        "agent_role": item.get("agent_role"),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "lease_owner": item.get("lease_owner"),
        "lease_expires_at": item.get("lease_expires_at"),
        "attempt_count": item.get("attempt_count"),
        "max_attempts": item.get("max_attempts"),
        "updated_at": item.get("updated_at"),
    }


def worker_queue_snapshot(limit: int = 20) -> Dict[str, Any]:
    active_statuses = ("queued", "leased", "running", "retrying", "blocked")
    per_status_limit = max(1, min(limit, 50))
    active_items = [
        item
        for status in active_statuses
        for item in knowledge_base.list_work_items(status=status, limit=per_status_limit)
    ]
    active_items.sort(key=lambda item: (int(item.get("priority") or 3), -(float(item.get("updated_at") or 0))))
    counts = worker_status_counts()
    if counts.get("blocked_count", 0) > 0:
        health = "blocked"
    elif counts.get("retrying_count", 0) > 0:
        health = "retrying"
    elif counts.get("leased_count", 0) + counts.get("running_count", 0) > 0:
        health = "running"
    elif counts.get("queued_count", 0) > 0:
        health = "backlog"
    else:
        health = "idle"
    return {
        **counts,
        "queue_health": health,
        "active_work_items": [summarize_worker_item(item) for item in active_items[:limit]],
        "active_work_item_count": sum(counts.get(f"{status}_count", 0) for status in active_statuses),
        "boundary": (
            "Worker status exposes queue and lease metadata for runtime readiness. "
            "Work item arguments and result payloads are intentionally omitted from this summary."
        ),
    }


def worker_status_guidance(*, enabled: bool, queue_health: str, active_count: int) -> Dict[str, Any]:
    if not enabled and active_count > 0:
        return {
            "status": "worker_disabled",
            "summary": "Background worker is disabled; queued research tasks will remain waiting until a worker is enabled or an administrator runs a manual worker tick.",
            "next_actions": ["Enable the local worker", "Run an administrator worker tick", "Keep the run queued and check back later"],
        }
    if queue_health == "blocked":
        return {
            "status": "blocked",
            "summary": "At least one background task is blocked and needs administrative review before it can continue.",
            "next_actions": ["Open runtime readiness", "Review blocked task details", "Retry or cancel the affected task"],
        }
    if queue_health == "retrying":
        return {
            "status": "retrying",
            "summary": "Some background tasks are retrying after a recoverable failure or expired lease.",
            "next_actions": ["Wait for the next worker tick", "Review runtime readiness if retrying persists"],
        }
    if queue_health == "running":
        return {
            "status": "running",
            "summary": "Background research work is currently running.",
            "next_actions": ["Monitor run progress", "Open process and evidence details when results are available"],
        }
    if queue_health == "backlog":
        return {
            "status": "queued",
            "summary": "Background research work is queued and waiting for an available worker slot.",
            "next_actions": ["Wait for a worker slot", "Check runtime readiness if the queue does not move"],
        }
    return {
        "status": "idle",
        "summary": "No active background research work is waiting or running.",
        "next_actions": ["Start a research run"],
    }


@app.get("/api/worker/status")
async def get_worker_status() -> Dict[str, Any]:
    from open_coscientist.checkpointing import execution_memory_status

    runtime = worker_runtime or build_worker_runtime()
    runtime_status = runtime.status()
    queue_snapshot = worker_queue_snapshot()
    return {
        **runtime_status,
        "auto_start_enabled": WORKER_AUTOSTART_ENABLED,
        "execution_memory": execution_memory_status(),
        **queue_snapshot,
        "guidance": worker_status_guidance(
            enabled=bool(runtime_status.get("enabled")),
            queue_health=str(queue_snapshot.get("queue_health") or "idle"),
            active_count=int(queue_snapshot.get("active_work_item_count") or 0),
        ),
    }


@app.post("/api/worker/tick")
async def tick_worker_once() -> Dict[str, Any]:
    from open_coscientist.checkpointing import execution_memory_status

    global worker_runtime
    if worker_runtime is None:
        worker_runtime = build_worker_runtime()
    result = await worker_runtime.tick(force=True)
    queue_snapshot = worker_queue_snapshot()
    return {
        **result,
        "auto_start_enabled": WORKER_AUTOSTART_ENABLED,
        "execution_memory": execution_memory_status(),
        **queue_snapshot,
        "guidance": worker_status_guidance(
            enabled=bool(result.get("enabled")),
            queue_health=str(queue_snapshot.get("queue_health") or "idle"),
            active_count=int(queue_snapshot.get("active_work_item_count") or 0),
        ),
    }


@app.post("/api/research-tasks")
async def create_research_task(request: ResearchTaskCreateRequest) -> Dict[str, Any]:
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    phase = canonical_phase(request.phase) if request.phase else None
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task = knowledge_base.create_research_task(
        task_id=task_id,
        title=request.title,
        task_type=request.task_type,
        status=request.status,
        priority=request.priority,
        phase=phase,
        run_id=request.run_id,
        target_ref=request.target_ref,
        result_ref=request.result_ref,
        notes=request.notes,
        blocked_reason=request.blocked_reason,
        due_at=request.due_at,
    )
    return {"task": task}


@app.get("/api/research-tasks")
async def list_research_tasks(
    run_id: Optional[str] = None,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    tasks = knowledge_base.list_research_tasks(
        run_id=run_id,
        status=status,
        task_type=task_type,
        limit=max(1, min(limit, 300)),
    )
    return {"tasks": tasks, "count": len(tasks), "run_id": run_id}


@app.get("/api/research-tasks/{task_id}")
async def get_research_task(task_id: str) -> Dict[str, Any]:
    task = knowledge_base.get_research_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "research_task_not_found",
                "message": "没有找到这个科研任务。",
            },
        )
    return {"task": task}


@app.patch("/api/research-tasks/{task_id}")
async def update_research_task(task_id: str, request: ResearchTaskUpdateRequest) -> Dict[str, Any]:
    phase = canonical_phase(request.phase) if request.phase else None
    task = knowledge_base.update_research_task(
        task_id,
        title=request.title,
        task_type=request.task_type,
        status=request.status,
        priority=request.priority,
        phase=phase,
        target_ref=request.target_ref,
        result_ref=request.result_ref,
        notes=request.notes,
        blocked_reason=request.blocked_reason,
        due_at=request.due_at,
    )
    if not task:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "research_task_not_found",
                "message": "没有找到这个科研任务。",
            },
        )
    return {"task": task}


@app.get("/api/research-skills")
async def list_research_skill_templates(phase: Optional[str] = None) -> Dict[str, Any]:
    canonical = canonical_phase(phase) if phase else None
    skills = list_research_skills(canonical)
    return {"skills": skills, "count": len(skills), "phase": canonical}


@app.get("/api/research-skills/{skill_id}")
async def get_research_skill_template(skill_id: str) -> Dict[str, Any]:
    skill = get_research_skill(skill_id)
    if not skill:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "research_skill_not_found",
                "message": "没有找到这个科研方法 skill。",
            },
        )
    return {"skill": skill}


@app.post("/api/research-schedules")
async def create_research_schedule(request: ResearchScheduleCreateRequest) -> Dict[str, Any]:
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    phase = canonical_phase(request.phase) if request.phase else None
    next_run_at = request.next_run_at if request.next_run_at is not None else time.time() + request.interval_hours * 3600
    schedule_id = f"sched_{uuid.uuid4().hex[:12]}"
    arguments = dict(request.arguments)
    if request.auto_execute:
        approval = require_tool_workflow_approval(
            request.approval or ToolWorkflowApproval(),
            expected_scope="research_schedule.auto_execute",
        )
        arguments["_automation"] = {
            "enabled": True,
            "approval_scope": approval.get("scope"),
            "reason": approval.get("reason"),
        }
    schedule = knowledge_base.create_research_schedule(
        schedule_id=schedule_id,
        run_id=request.run_id,
        title=request.title,
        workflow_name=request.workflow_name,
        status=request.status,
        interval_hours=request.interval_hours,
        phase=phase,
        arguments=arguments,
        next_run_at=next_run_at,
    )
    return {"schedule": schedule}


@app.get("/api/research-schedules")
async def list_research_schedules(
    run_id: Optional[str] = None,
    status: Optional[str] = None,
    workflow_name: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    schedules = knowledge_base.list_research_schedules(
        run_id=run_id,
        status=status,
        workflow_name=workflow_name,
        limit=max(1, min(limit, 300)),
    )
    return {"schedules": schedules, "count": len(schedules), "run_id": run_id}


@app.get("/api/research-schedules/{schedule_id}")
async def get_research_schedule(schedule_id: str) -> Dict[str, Any]:
    schedule = knowledge_base.get_research_schedule(schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "research_schedule_not_found",
                "message": "没有找到这个科研计划。",
            },
        )
    return {"schedule": schedule}


@app.get("/api/session-search")
async def search_research_sessions(
    q: str = "",
    run_id: Optional[str] = None,
    types: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "search_query_too_short",
                "message": "Search query must contain at least 2 non-space characters.",
            },
        )
    result_types = [
        item.strip()
        for item in (types or "").split(",")
        if item.strip()
    ] or None
    results = knowledge_base.search_research_sessions(
        query,
        run_id=run_id,
        result_types=result_types,
        limit=max(1, min(limit, 100)),
    )
    return {
        "query": query,
        "run_id": run_id,
        "types": result_types,
        "count": len(results),
        "results": results,
    }


@app.patch("/api/research-schedules/{schedule_id}")
async def update_research_schedule(
    schedule_id: str,
    request: ResearchScheduleUpdateRequest,
) -> Dict[str, Any]:
    phase = canonical_phase(request.phase) if request.phase else None
    schedule = knowledge_base.update_research_schedule(
        schedule_id,
        title=request.title,
        workflow_name=request.workflow_name,
        status=request.status,
        interval_hours=request.interval_hours,
        phase=phase,
        arguments=request.arguments,
        last_run_at=request.last_run_at,
        next_run_at=request.next_run_at,
        result_ref=request.result_ref,
    )
    if not schedule:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "research_schedule_not_found",
                "message": "没有找到这个科研计划。",
            },
        )
    return {"schedule": schedule}


def scheduled_run_request(schedule: Dict[str, Any]) -> RunRequest:
    """Build a new run request from a schedule and its optional template run."""
    arguments = dict(schedule.get("arguments") or {})
    arguments.pop("_automation", None)
    nested = arguments.pop("run_request", None)
    overrides = dict(nested) if isinstance(nested, dict) else arguments

    template = load_run_record(str(schedule.get("run_id") or "")) if schedule.get("run_id") else None
    base = template.request.model_dump() if template else {}
    base.update(overrides)
    if template and "parent_run_id" not in overrides:
        base["parent_run_id"] = template.run_id
        base["refinement_mode"] = "continue_from_run"
    return RunRequest(**base)


async def dispatch_research_schedule(
    schedule: Dict[str, Any],
    *,
    approval: Dict[str, Any],
) -> Dict[str, Any]:
    """Materialize one due schedule as a task and, when supported, a queued run."""
    now = time.time()
    next_run_at = now + float(schedule["interval_hours"]) * 3600
    schedule_id = str(schedule["schedule_id"])

    if schedule["workflow_name"] == "workflow.open_coscientist_run":
        run_request = scheduled_run_request(schedule)
        run_result = await create_run(run_request)
        run_id = str(run_result["run_id"])
        task = knowledge_base.create_research_task(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            run_id=run_id,
            title=f"Scheduled: {schedule['title']}",
            task_type="scheduled_workflow",
            status="running",
            priority=2,
            phase=schedule.get("phase") or "workflow",
            target_ref={
                "schedule_id": schedule_id,
                "workflow_name": schedule["workflow_name"],
                "template_run_id": schedule.get("run_id"),
            },
            result_ref={
                "run_id": run_id,
                "work_item_id": run_result.get("work_item_id"),
                "status": "queued",
            },
            notes="Schedule created a new durable research run and queued it for the research worker.",
        )
        result_ref = {
            "task_id": task["task_id"],
            "run_id": run_id,
            "work_item_id": run_result.get("work_item_id"),
            "approval": approval,
        }
    else:
        task = knowledge_base.create_research_task(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            run_id=schedule.get("run_id"),
            title=f"Scheduled: {schedule['title']}",
            task_type="scheduled_workflow",
            status="ready",
            priority=2,
            phase=schedule.get("phase"),
            target_ref={
                "schedule_id": schedule_id,
                "workflow_name": schedule["workflow_name"],
                "arguments": schedule["arguments"],
            },
            result_ref={},
            notes="The scheduled workflow has no registered automatic executor and requires an approved runner.",
        )
        result_ref = {"task_id": task["task_id"], "approval": approval}

    updated_schedule = knowledge_base.update_research_schedule(
        schedule_id,
        last_run_at=now,
        next_run_at=next_run_at,
        result_ref=result_ref,
    )
    return {"schedule": updated_schedule, "task": task, "approval": approval}


async def dispatch_due_research_schedules() -> Dict[str, Any]:
    """Worker pre-tick hook for schedules explicitly approved for auto execution."""
    now = time.time()
    dispatched: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    for schedule in knowledge_base.claim_due_research_schedules(now=now, limit=100):
        automation = (schedule.get("arguments") or {}).get("_automation")
        assert isinstance(automation, dict) and automation.get("enabled")
        approval = {
            "confirmed": True,
            "scope": str(automation.get("approval_scope") or "research_schedule.auto_execute"),
            "reason": str(automation.get("reason") or "approved_schedule"),
        }
        try:
            result = await dispatch_research_schedule(schedule, approval=approval)
            dispatched.append(
                {
                    "schedule_id": schedule["schedule_id"],
                    "task_id": result["task"].get("task_id"),
                    "run_id": result["task"].get("run_id"),
                }
            )
        except Exception as exc:
            knowledge_base.update_research_schedule(
                str(schedule["schedule_id"]),
                last_run_at=now,
                next_run_at=now + float(schedule["interval_hours"]) * 3600,
                result_ref={"status": "error", "message": str(exc)[:500]},
            )
            failed.append({"schedule_id": schedule["schedule_id"], "message": str(exc)[:240]})
    return {"dispatched_count": len(dispatched), "failed_count": len(failed), "items": dispatched, "errors": failed}


@app.post("/api/research-schedules/{schedule_id}/tick")
async def tick_research_schedule(
    schedule_id: str,
    request: ResearchScheduleTickRequest,
) -> Dict[str, Any]:
    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="research_schedule.tick",
    )
    schedule = knowledge_base.get_research_schedule(schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "research_schedule_not_found",
                "message": "没有找到这个科研计划。",
            },
        )
    if schedule["status"] != "active":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "research_schedule_not_active",
                "message": "只有 active schedule 可以触发 tick。",
            },
        )
    now = time.time()
    if not request.force and schedule["next_run_at"] > now:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "research_schedule_not_due",
                "message": "这个 schedule 还没有到 next_run_at；如需人工触发必须显式 force。",
                "next_run_at": schedule["next_run_at"],
            },
        )
    return await dispatch_research_schedule(schedule, approval=approval)


@app.post("/api/research-delegations")
async def create_research_delegation(request: ResearchDelegationCreateRequest) -> Dict[str, Any]:
    if request.run_id and not load_run_record(request.run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    phase = canonical_phase(request.phase)
    delegation_id = f"deleg_{uuid.uuid4().hex[:12]}"
    delegation = knowledge_base.create_research_delegation(
        delegation_id=delegation_id,
        run_id=request.run_id,
        title=request.title,
        phase=phase,
        strategy=request.strategy,
        status=request.status,
        agents=[agent.model_dump() for agent in request.agents],
        target_ref=request.target_ref,
        result_ref=request.result_ref,
        summary=request.summary,
    )
    return {"delegation": delegation}


@app.get("/api/research-delegations")
async def list_research_delegations(
    run_id: Optional[str] = None,
    status: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    delegations = knowledge_base.list_research_delegations(
        run_id=run_id,
        status=status,
        strategy=strategy,
        limit=max(1, min(limit, 300)),
    )
    return {"delegations": delegations, "count": len(delegations), "run_id": run_id}


@app.get("/api/research-delegations/{delegation_id}")
async def get_research_delegation(delegation_id: str) -> Dict[str, Any]:
    delegation = knowledge_base.get_research_delegation(delegation_id)
    if not delegation:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "research_delegation_not_found",
                "message": "没有找到这个科研 delegation。",
            },
        )
    return {"delegation": delegation}


@app.patch("/api/research-delegations/{delegation_id}")
async def update_research_delegation(
    delegation_id: str,
    request: ResearchDelegationUpdateRequest,
) -> Dict[str, Any]:
    phase = canonical_phase(request.phase) if request.phase else None
    delegation = knowledge_base.update_research_delegation(
        delegation_id,
        title=request.title,
        phase=phase,
        strategy=request.strategy,
        status=request.status,
        agents=[agent.model_dump() for agent in request.agents] if request.agents is not None else None,
        target_ref=request.target_ref,
        result_ref=request.result_ref,
        summary=request.summary,
    )
    if not delegation:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "research_delegation_not_found",
                "message": "没有找到这个科研 delegation。",
            },
        )
    return {"delegation": delegation}


@app.post("/api/research-delegations/{delegation_id}/run")
async def run_research_delegation(
    delegation_id: str,
    request: ResearchDelegationRunRequest,
) -> Dict[str, Any]:
    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="research_delegation.run",
    )
    delegation = knowledge_base.get_research_delegation(delegation_id)
    if not delegation:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "research_delegation_not_found",
                "message": "没有找到这个科研 delegation。",
            },
        )
    run_id = delegation.get("run_id")
    run_record = load_run_record(run_id) if run_id else None
    if run_id and not run_record:
        raise HTTPException(status_code=404, detail="Run not found")
    if not has_model_provider_key(request.model_name):
        provider = provider_for_model(request.model_name)
        raise HTTPException(
            status_code=400,
            detail={
                "code": "missing_provider_key",
                "message": f"Delegation runner requires {', '.join(provider['env_vars'])} for {request.model_name}.",
                "repair_hint": provider["repair_hint"],
            },
        )

    agents = delegation.get("agents") or []
    knowledge_base.update_research_delegation(
        delegation_id,
        status="running",
        summary="Delegation runner is executing agent briefs.",
    )
    try:
        agent_outputs = await asyncio.gather(
            *[
                execute_delegation_agent(
                    delegation=delegation,
                    agent=agent,
                    run_record=run_record,
                    model_name=request.model_name,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                )
                for agent in agents
            ]
        )
    except Exception as exc:
        knowledge_base.update_research_delegation(
            delegation_id,
            status="blocked",
            summary=f"Delegation runner failed before all agent outputs completed: {exc}",
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "delegation_runner_failed",
                "message": "Delegation runner failed while executing one or more agent briefs.",
            },
        )

    summary = (
        f"Delegation completed with {len(agent_outputs)} agent outputs. "
        "Inspect research_tool_results for full per-agent reports and evidence refs."
    )
    result_payload = {
        "delegation_id": delegation_id,
        "run_id": run_id,
        "title": delegation.get("title"),
        "phase": delegation.get("phase"),
        "strategy": delegation.get("strategy"),
        "model_name": request.model_name,
        "approval": approval,
        "target_ref": delegation.get("target_ref", {}),
        "agent_outputs": agent_outputs,
        "summary": summary,
        "synthetic": False,
    }
    result_ref = knowledge_base.store_tool_result(
        run_id=run_id,
        tool_name="research.delegation_runner",
        phase=delegation.get("phase"),
        content=result_payload,
        result_kind="delegation_agent_outputs",
        summary=summary,
    )
    if run_id:
        knowledge_base.record_research_tool_call(
            run_id=run_id,
            tool_name="research.delegation_runner",
            phase=delegation.get("phase"),
            status="completed",
            arguments={
                "delegation_id": delegation_id,
                "model_name": request.model_name,
                "agent_count": len(agents),
            },
            result_summary=summary,
            metadata={
                "result_ref": result_ref,
                "approval": approval,
                "agent_roles": [agent.get("role") for agent in agents],
            },
        )
    updated = knowledge_base.update_research_delegation(
        delegation_id,
        status="completed",
        result_ref={"tool_result": result_ref},
        summary=summary,
    )
    return {
        "delegation": updated,
        "result_ref": result_ref,
        "agent_outputs": agent_outputs,
        "summary": summary,
    }


@app.get("/api/tools/phases/{phase}")
async def get_phase_tools(phase: str) -> Dict[str, Any]:
    canonical = canonical_phase(phase)
    payload = research_tool_registry().list_phase_tools(canonical)
    policy = next(
        (item for item in list_phase_tool_policies() if item["phase"] == canonical),
        None,
    )
    payload["policy"] = policy
    return payload


@app.post("/api/hypotheses/translate")
async def translate_hypothesis(request: TranslationRequest) -> Dict[str, str]:
    if not has_model_provider_key(request.model_name):
        provider = provider_for_model(request.model_name)
        raise HTTPException(
            status_code=400,
            detail={
                "code": "missing_provider_key",
                "message": f"Translation requires {', '.join(provider['env_vars'])} for {request.model_name}.",
            },
        )

    try:
        from open_coscientist.llm import call_llm

        prompt = (
            "Translate the following research hypothesis content into concise Simplified Chinese. "
            "Preserve scientific terms, uncertainty, and falsifiability language. "
            "Return only the Chinese translation, without Markdown headings.\n\n"
            f"Hypothesis:\n{request.text}\n\n"
            f"Explanation:\n{request.explanation or ''}\n\n"
            f"Experiment plan:\n{request.experiment or ''}"
        )
        translation = await call_llm(
            prompt=prompt,
            model_name=request.model_name,
            max_tokens=1200,
            temperature=0.2,
        )
        return {"translation": translation.strip()}
    except Exception:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "translation_failed",
                "message": "Chinese translation is temporarily unavailable.",
            },
        )


def _microsoft_translator_settings() -> Dict[str, str]:
    return {
        "key": os.getenv("MICROSOFT_TRANSLATOR_KEY") or os.getenv("AZURE_TRANSLATOR_KEY") or "",
        "region": os.getenv("MICROSOFT_TRANSLATOR_REGION") or os.getenv("AZURE_TRANSLATOR_REGION") or "",
        "endpoint": (
            os.getenv("MICROSOFT_TRANSLATOR_ENDPOINT")
            or os.getenv("AZURE_TRANSLATOR_ENDPOINT")
            or "https://api.cognitive.microsofttranslator.com"
        ).rstrip("/"),
    }


def _translate_with_microsoft(text: str, target_language: str) -> str:
    settings = _microsoft_translator_settings()
    if not settings["key"]:
        raise RuntimeError("missing_microsoft_translator_key")
    headers = {
        "Ocp-Apim-Subscription-Key": settings["key"],
        "Content-Type": "application/json",
        "X-ClientTraceId": str(uuid.uuid4()),
    }
    if settings["region"]:
        headers["Ocp-Apim-Subscription-Region"] = settings["region"]
    response = requests.post(
        f"{settings['endpoint']}/translate",
        params={"api-version": "3.0", "to": target_language or "zh-Hans"},
        headers=headers,
        json=[{"Text": text}],
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("empty_microsoft_translation")
    translations = payload[0].get("translations") if isinstance(payload[0], dict) else None
    if not translations:
        raise RuntimeError("empty_microsoft_translation")
    translated = translations[0].get("text") if isinstance(translations[0], dict) else ""
    if not translated:
        raise RuntimeError("empty_microsoft_translation")
    return str(translated).strip()


@app.post("/api/evidence/translate")
async def translate_evidence_text(request: TranslationRequest) -> Dict[str, str]:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail={"code": "empty_translation_text"})
    text = text[:6000]
    target_language = request.target_language or "zh-Hans"

    if request.provider in {"auto", "microsoft"}:
        try:
            translation = await asyncio.to_thread(_translate_with_microsoft, text, target_language)
            return {"translation": translation, "provider": "microsoft", "target_language": target_language}
        except Exception as exc:
            if request.provider == "microsoft":
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": "microsoft_translation_failed",
                        "message": "Microsoft Translator 暂时不可用，请检查 Azure Translator key、region 或网络。",
                    },
                ) from exc

    if not has_model_provider_key(request.model_name):
        provider = provider_for_model(request.model_name)
        raise HTTPException(
            status_code=400,
            detail={
                "code": "missing_provider_key",
                "message": (
                    "Evidence translation requires Microsoft Translator env vars "
                    f"or {', '.join(provider['env_vars'])} for {request.model_name}."
                ),
            },
        )

    try:
        from open_coscientist.llm import call_llm

        prompt = (
            "Translate the following evidence excerpt into concise Simplified Chinese. "
            "Preserve technical terms, symbols, numbers, uncertainty, negative-result language, and citations. "
            "Return only the Chinese translation; do not add analysis or new claims.\n\n"
            f"Evidence excerpt:\n{text}"
        )
        translation = await call_llm(
            prompt=prompt,
            model_name=request.model_name,
            max_tokens=1200,
            temperature=0.1,
        )
        return {"translation": translation.strip(), "provider": "model", "target_language": target_language}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "evidence_translation_failed",
                "message": "证据片段翻译暂时不可用。",
            },
        ) from exc


@app.get("/api/literature-libraries")
async def list_literature_libraries() -> Dict[str, Any]:
    libraries = knowledge_base.list_libraries()
    return {
        "libraries": libraries,
        "count": len(libraries),
        "default_library_id": DEFAULT_LIBRARY_ID,
    }


@app.post("/api/literature-libraries")
async def create_literature_library(request: LiteratureLibraryCreateRequest) -> Dict[str, Any]:
    try:
        library = knowledge_base.create_library(name=request.name, description=request.description)
    except ValueError as exc:
        raise HTTPException(
            status_code=409 if "already exists" in str(exc) else 422,
            detail={
                "code": "literature_library_create_failed",
                "message": "这个文献库名称暂时不能使用，请换一个更明确的名称。",
            },
        )
    return {"library": library}


@app.post("/api/literature-libraries/discover")
async def discover_literature_for_library(request: LiteratureDiscoveryRequest) -> Dict[str, Any]:
    try:
        library_id = knowledge_base.resolve_library_id(request.library_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        )

    mcp_status = await asyncio.to_thread(probe_mcp_server)
    if not mcp_status.get("available"):
        return {
            "query": request.query,
            "library_id": library_id,
            "status": "limited",
            "message": "文献 MCP 服务当前不可用；可以先上传 PDF、输入 PDF URL，或到运行准备页检查文献服务。",
            "mcp": public_mcp_status(mcp_status),
            "candidates": [],
        }

    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="mcp.literature_review",
    )
    phase = canonical_phase("literature_review")
    registry = research_tool_registry()
    spec = registry.get("mcp.literature_review")
    if not spec:
        raise HTTPException(status_code=404, detail={"code": "tool_not_found"})
    authorization = authorize_tool_for_phase(spec, phase)
    if not authorization["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={key: value for key, value in authorization.items() if key != "allowed"},
        )

    planner = await _plan_literature_discovery(
        query=request.query,
        preferred_source=request.preferred_source,
        max_results=request.max_results,
        planning_mode=request.planning_mode,
        model_name=request.model_name,
    )
    planned_tool_queries = [
        item
        for item in planner.get("tool_queries", [])
        if isinstance(item, dict) and str(item.get("tool_id") or "").strip()
    ]
    if not planned_tool_queries:
        planner = _rules_literature_discovery_plan(
            request.query,
            request.preferred_source,
            reason="检索计划为空，已回退到规则检索。",
        )
        planned_tool_queries = [
            item
            for item in planner.get("tool_queries", [])
            if isinstance(item, dict) and str(item.get("tool_id") or "").strip()
        ]

    tool_registry = build_policy_limited_tool_registry()
    tool_ids = [str(item["tool_id"]) for item in planned_tool_queries]
    allowed_tool_ids = set(tool_registry.get_tools_for_workflow("literature_review"))
    blocked_tool_ids = [tool_id for tool_id in tool_ids if tool_id not in allowed_tool_ids]
    if blocked_tool_ids:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "mcp_tool_not_allowed_by_workflow_policy",
                "message": "当前 workflow policy 没有授权这个文献搜索工具。",
                "blocked_tools": blocked_tool_ids,
            },
        )
    planned_calls: List[Dict[str, Any]] = []
    for call_index, item in enumerate(planned_tool_queries, start=1):
        tool_id = str(item.get("tool_id") or "")
        tool_config = tool_registry.get_tool(tool_id)
        planned_calls.append(
            {
                "call_id": f"{tool_id}:{call_index}",
                "tool_id": tool_id,
                "tool_config": tool_config,
                "query": str(item.get("query") or request.query).strip() or request.query,
                "rationale": str(item.get("rationale") or ""),
            }
        )
    missing_tool_ids = [str(item["tool_id"]) for item in planned_calls if not item.get("tool_config")]
    if missing_tool_ids:
        raise HTTPException(status_code=424, detail={"code": "mcp_tool_not_configured"})

    client = await get_policy_limited_mcp_client(tool_registry)
    source_statuses: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []
    seen_candidate_keys: set[str] = set()
    successful_tools: List[Dict[str, str]] = []

    def candidate_key(candidate: Dict[str, Any]) -> str:
        for key in ("doi", "arxiv_id", "source_id", "pdf_url", "url"):
            value = str(candidate.get(key) or "").strip().lower()
            if value:
                return f"{key}:{value}"
        return f"title:{str(candidate.get('title') or '').strip().lower()}"

    for planned_call in planned_calls:
        tool_id = str(planned_call["tool_id"])
        tool_config = planned_call["tool_config"]
        if not tool_config:
            continue
        planned_query = str(planned_call["query"])
        call_id = str(planned_call["call_id"])
        arguments = _discovery_tool_arguments(tool_id, planned_query, request.max_results, library_id)
        try:
            raw_result = await client.call_tool(tool_config.mcp_tool_name, **arguments)
        except Exception:
            if len(planned_calls) == 1:
                raise HTTPException(
                    status_code=424,
                    detail={
                        "code": "mcp_tool_call_failed",
                        "message": "文献 MCP 搜索暂时失败，请检查 MCP 服务状态或换一个检索词。",
                    },
                )
            source_statuses.append(
                {
                    "call_id": call_id,
                    "tool_id": tool_id,
                    "mcp_tool_name": tool_config.mcp_tool_name,
                    "display_name": tool_config.display_name,
                    "query": planned_query,
                    "rationale": str(planned_call.get("rationale") or ""),
                    "status": "failed",
                    "message": "该来源检索失败；已保留其他来源结果。",
                }
            )
            continue
        source_candidates = _literature_candidates_from_mcp_result(
            raw_result,
            tool_id=tool_id,
            max_results=request.max_results,
        )
        for candidate_index, candidate in enumerate(source_candidates, start=1):
            candidate["candidate_id"] = f"candidate_{tool_id}_{len(source_statuses) + 1}_{candidate_index}"
            candidate["discovery_query"] = planned_query
            candidate["discovery_call_id"] = call_id
            key = candidate_key(candidate)
            if key in seen_candidate_keys:
                continue
            seen_candidate_keys.add(key)
            candidates.append(candidate)
        successful_tools.append(
            {
                "call_id": call_id,
                "tool_id": tool_id,
                "mcp_tool_name": tool_config.mcp_tool_name,
                "display_name": tool_config.display_name,
                "query": planned_query,
                "rationale": str(planned_call.get("rationale") or ""),
            }
        )
        source_statuses.append(
            {
                "call_id": call_id,
                "tool_id": tool_id,
                "mcp_tool_name": tool_config.mcp_tool_name,
                "display_name": tool_config.display_name,
                "query": planned_query,
                "rationale": str(planned_call.get("rationale") or ""),
                "status": "ready" if source_candidates else "limited",
                "message": f"找到 {len(source_candidates)} 个候选。" if source_candidates else "该来源没有返回可展示候选。",
            }
        )
    pdf_discovery_results = (
        await _discover_pdf_links_for_candidates(
            client=client,
            tool_registry=tool_registry,
            candidates=candidates,
            source_statuses=source_statuses,
            max_pages=request.max_results if request.auto_discover_pdf_links else 0,
        )
        if candidates
        else []
    )
    auto_ingest_results = (
        await _auto_ingest_discovered_pdfs(
            candidates=candidates,
            library_id=library_id,
            limit=request.auto_ingest_limit,
        )
        if request.auto_ingest_pdfs and candidates
        else []
    )
    ingested_count = sum(1 for item in auto_ingest_results if item.get("status") == "ingested")
    return {
        "query": request.query,
        "library_id": library_id,
        "status": "ready" if candidates else "limited",
        "message": (
            (
                f"已通过 {len(successful_tools)} 组模型规划检索找到 {len(candidates)} 个去重候选。"
                + (f" 自动解析入库 {ingested_count} 篇 PDF。" if request.auto_ingest_pdfs else "")
            )
            if candidates
            else "文献搜索引擎已完成可用来源检索，但没有发现可直接展示的论文候选；建议换用更具体的检索词。"
        ),
        "mcp": public_mcp_status(mcp_status),
        "tool": successful_tools[0] if len(successful_tools) == 1 else None,
        "tools": successful_tools,
        "source_statuses": source_statuses,
        "planner": planner,
        "pdf_discovery": pdf_discovery_results,
        "auto_ingest": auto_ingest_results,
        "approval": approval,
        "candidates": candidates,
    }


@app.post("/api/literature-citations/bibtex")
async def fetch_literature_candidate_bibtex(request: LiteratureCitationRequest) -> Dict[str, Any]:
    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="citation.metadata",
    )
    doi = _doi_from_citation_request(request)
    if not doi:
        return {
            "status": "unavailable",
            "message": "当前候选没有 DOI，系统不会用题名或摘要自行生成 BibTeX；请打开论文页或机构访问入口下载官方引用文件。",
            "doi": None,
            "source": "not_available",
            "source_url": request.url or request.pdf_url,
            "approval": approval,
        }

    result = await asyncio.to_thread(_fetch_trusted_bibtex_for_doi, doi)
    if result.get("available"):
        return {
            "status": "ready",
            "message": f"已通过 {result['source_label']} 获取可信 BibTeX。",
            "doi": doi,
            "source": result["source"],
            "source_url": result["source_url"],
            "bibtex": result["bibtex"],
            "approval": approval,
        }
    return {
        "status": "unavailable",
        "message": "已尝试 DOI/Crossref/DataCite 规则化 BibTeX 获取，但该 DOI 暂未返回可复用 BibTeX；请到期刊页或机构访问入口下载官方引用文件。",
        "doi": doi,
        "source": "not_available",
        "source_url": request.url or f"https://doi.org/{urllib.parse.quote(doi, safe='/')}",
        "attempts_count": len(result.get("attempts", [])),
        "approval": approval,
    }


@app.post("/api/knowledge/papers")
async def ingest_knowledge_paper(request: PaperIngestRequest) -> Dict[str, Any]:
    validate_ingest_authors(request.authors)
    validate_ingest_metadata(request.metadata)
    reliability = request.source_reliability or reliability_for_source(request.source)
    try:
        paper = knowledge_base.ingest(
            title=request.title,
            content=request.content,
            authors=request.authors,
            year=request.year,
            doi=request.doi,
            url=request.url,
            abstract=request.abstract,
            source=request.source,
            source_reliability=reliability,
            metadata=request.metadata,
            library_id=request.library_id,
        )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        )
    experimental_chunks = [
        chunk
        for chunk in paper.chunks
        if chunk.experiment_data_summary
    ]
    return {
        "paper_id": paper.paper_id,
        "library_id": paper.library_id,
        "title": paper.title,
        "source_reliability": paper.source_reliability,
        "chunks_count": len(paper.chunks),
        "section_types": sorted({chunk.section_type for chunk in paper.chunks}),
        "experimental_chunks_count": len(experimental_chunks),
        "experimental_support_summaries": [
            {
                "chunk_id": chunk.chunk_id,
                "section_path": chunk.section_path,
                "summary": chunk.experiment_data_summary,
            }
            for chunk in experimental_chunks[:5]
        ],
    }


@app.post("/api/knowledge/pdf/parse")
async def parse_knowledge_pdf(request: PdfParseRequest) -> Dict[str, Any]:
    parse_run_id = f"parse_{uuid.uuid4().hex[:12]}"
    try:
        knowledge_base.resolve_library_id(request.library_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        )
    try:
        resolved_pdf = await asyncio.to_thread(resolve_pdf_input, request.pdf_path)
        return await parse_pdf_and_record(
            parse_run_id=parse_run_id,
            pdf_path=resolved_pdf,
            input_kind="local_path",
            input_path=request.pdf_path,
            fetch_metadata=request.fetch_metadata,
            ingest_to_knowledge_base=request.ingest_to_knowledge_base,
            library_id=request.library_id,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "pdf_not_found",
                "message": "没有找到这个 PDF 文件，请确认路径在当前机器上可访问。",
            },
        )
    except (requests.RequestException, ValueError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "pdf_download_failed",
                "message": "PDF 链接暂时无法读取，请确认链接可直接访问 PDF，或改用本机 PDF 路径。",
            },
        )
    except Exception:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "pdf_parse_failed",
                "message": "PDF 暂时无法解析，请确认文件未加密、未损坏，并且后端已安装 PyMuPDF。",
            },
        )

@app.post("/api/knowledge/pdf/upload-parse")
async def upload_parse_knowledge_pdf(
    file: UploadFile = File(...),
    fetch_metadata: bool = True,
    ingest_to_knowledge_base: bool = True,
    library_id: Optional[str] = None,
) -> Dict[str, Any]:
    parse_run_id = f"parse_{uuid.uuid4().hex[:12]}"
    filename = safe_upload_filename(file.filename or "paper.pdf")
    upload_dir = KB_ROOT / "uploads" / parse_run_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / filename
    try:
        knowledge_base.resolve_library_id(library_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        )
    try:
        content = await file.read()
        if not content.startswith(b"%PDF"):
            raise ValueError("Upload is not a PDF")
        target.write_bytes(content)
        return await parse_pdf_and_record(
            parse_run_id=parse_run_id,
            pdf_path=target,
            input_kind="upload",
            input_path=filename,
            fetch_metadata=fetch_metadata,
            ingest_to_knowledge_base=ingest_to_knowledge_base,
            library_id=library_id,
        )
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_pdf_upload",
                "message": "上传内容不是可解析的 PDF 文件。",
            },
        )
    except Exception:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "pdf_parse_failed",
                "message": "PDF 暂时无法解析，请确认文件未加密、未损坏，并且后端已安装 PyMuPDF。",
            },
        )


@app.get("/api/knowledge/parse-runs")
async def list_parse_runs(library_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        summaries = knowledge_base.list_parse_runs(library_id=library_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        )
    parse_runs = [
        knowledge_base.get_parse_run(summary["parse_run_id"]) or summary
        for summary in summaries
    ]
    return {"parse_runs": parse_runs, "count": len(parse_runs), "library_id": library_id}


@app.get("/api/knowledge/parse-runs/{parse_run_id}")
async def get_parse_run(parse_run_id: str) -> Dict[str, Any]:
    parse_run = knowledge_base.get_parse_run(parse_run_id)
    if not parse_run:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "parse_run_not_found",
                "message": "没有找到这次论文解析任务。",
            },
        )
    return parse_run


@app.get("/api/papers/{paper_id}/parse-status")
async def get_paper_parse_status(paper_id: str) -> Dict[str, Any]:
    parse_run = paper_parse_store.get_parse_status(paper_id)
    if not parse_run:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "paper_parse_status_not_found",
                "message": "没有找到这篇论文的解析证据状态。",
            },
        )
    return {
        "paper": {
            "paper_id": parse_run.get("paper_id"),
            "title": parse_run.get("title"),
            "pdf_path": parse_run.get("pdf_path"),
            "output_name": parse_run.get("input_path"),
        },
        "parse_run": parse_run,
        "parse_status_summary": parse_status_summary(parse_run, database_path=str(paper_parse_store.database_path)),
    }


@app.post("/api/papers/interpret")
async def interpret_single_paper(request: PaperInterpretRequest) -> Dict[str, Any]:
    if not has_model_provider_key(request.model_name):
        provider = provider_for_model(request.model_name)
        raise HTTPException(
            status_code=400,
            detail={
                "code": "missing_provider_key",
                "message": f"论文解读需要先配置 {', '.join(provider['env_vars'])}，否则不能生成可信中文译稿。",
            },
        )

    try:
        from open_coscientist.llm import call_llm

        async def translate(prompt: str) -> str:
            return await call_llm(
                prompt=prompt,
                model_name=request.model_name,
                max_tokens=3200,
                temperature=0.1,
            )

        result = await interpret_paper_pdf(
            Path(request.pdf_path),
            request.output_name,
            translate=translate,
            fetch_metadata=request.fetch_metadata,
        )
        parse_run_id = f"parse_{uuid.uuid4().hex[:12]}"
        markdown_text = Path(result.markdown_path).read_text(encoding="utf-8")
        extracted_text = Path(result.extracted_text_path).read_text(encoding="utf-8")
        paper = knowledge_base.ingest(
            title=result.title,
            content=f"# 中文结构化译稿\n\n{markdown_text}\n\n# 本地 PDF 抽取全文\n\n{extracted_text}",
            doi=result.doi,
            url=result.pdf_path,
            source="local_pdf_interpretation",
            source_reliability="parsed_fulltext",
            metadata={
                "parse_run_id": parse_run_id,
                "output_name": result.output_name,
                "markdown_path": result.markdown_path,
                "extracted_text_path": result.extracted_text_path,
                "official_metadata_path": result.official_metadata_path,
                "bibtex_path": result.bibtex_path,
                "media_dir": result.media_dir,
            },
        )
        payload = build_interpret_record_payload(
            parse_run_id=parse_run_id,
            result=result,
            paper_id=paper.paper_id,
            chunks=paper.chunks,
            output_name=result.output_name,
        )
        knowledge_base.record_parse_run(
            parse_run_id=parse_run_id,
            paper_id=paper.paper_id,
            title=result.title,
            status=payload["status"],
            input_kind="local_path",
            input_path=request.pdf_path,
            pdf_path=result.pdf_path,
            solve_dir=str(Path(result.markdown_path).parent),
            page_count=result.page_count,
            chunks_count=len(paper.chunks),
            experimental_chunks_count=payload["experimental_chunks_count"],
            knowledge_base_ingested=True,
            rag_search_ready=bool(paper.chunks),
            items=payload["items"],
            evidence=payload["evidence"],
        )
        parse_run = knowledge_base.get_parse_run(parse_run_id) or {"items": payload["items"], "chunks_count": len(paper.chunks), "rag_search_ready": bool(paper.chunks)}
        response = result_to_dict(result)
        response.update(
            {
                "paper_id": paper.paper_id,
                "parse_run_id": parse_run_id,
                "parse_items": parse_run.get("items", payload["items"]),
                "parse_status_summary": parse_status_summary(parse_run),
                "rag_indexed_chunks_count": len(paper.chunks),
                "database_path": str(knowledge_base.db_path),
            }
        )
        return response
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "pdf_not_found",
                "message": "没有找到这个 PDF 文件，请确认路径在当前机器上可访问。",
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_paper_interpret_request",
                "message": str(exc),
            },
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "paper_interpret_failed",
                "message": "论文解读暂时未能完成，请检查 PDF、模型配置和网络元数据服务后重试。",
            },
        )


@app.get("/api/knowledge/papers")
async def list_knowledge_papers(library_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        documents = knowledge_base.list_documents(library_id=library_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        )
    return {
        "papers": [
            {
                "paper_id": paper.paper_id,
                "library_id": paper.library_id,
                "title": paper.title,
                "authors": paper.authors,
                "year": paper.year,
                "doi": paper.doi,
                "url": paper.url,
                "source": paper.source,
                "source_reliability": paper.source_reliability,
                "parse_run_id": paper.parse_run_id,
                "chunks_count": len(paper.chunks),
                "section_types": sorted({chunk.section_type for chunk in paper.chunks}),
                "experimental_chunks_count": sum(1 for chunk in paper.chunks if chunk.experiment_data_summary),
                "created_at": paper.created_at,
            }
            for paper in documents
        ],
        "count": len(documents),
        "library_id": library_id,
    }


@app.get("/api/knowledge/search")
async def search_knowledge(q: str, limit: int = 8, library_id: Optional[str] = None) -> Dict[str, Any]:
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty")
    try:
        results = knowledge_base.search_chunks(q, limit=max(1, min(limit, 20)), library_id=library_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        )
    return {
        "query": q,
        "library_id": library_id,
        "results": results,
        "ragflow": knowledge_base.ragflow_status(),
    }


@app.get("/api/knowledge/ragflow/status")
async def get_ragflow_knowledge_status() -> Dict[str, Any]:
    return knowledge_base.ragflow_status()


@app.post("/api/knowledge/ragflow/reindex")
async def reindex_ragflow_embeddings(request: RagflowReindexRequest) -> Dict[str, Any]:
    try:
        return knowledge_base.reindex_embeddings(library_id=request.library_id, paper_id=request.paper_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        )


@app.get("/api/knowledge/rag/search")
async def search_rag_evidence(
    q: str,
    limit: int = 8,
    paper_id: Optional[str] = None,
    library_id: Optional[str] = None,
    parse_item_key: Optional[str] = None,
    support_level: Optional[str] = None,
) -> Dict[str, Any]:
    if not q.strip():
        raise HTTPException(status_code=422, detail="Query must not be empty")
    try:
        results = paper_parse_store.rag_search(
            q,
            limit=max(1, min(limit, 50)),
            paper_id=paper_id,
            library_id=library_id,
            parse_item_key=parse_item_key,
            support_level=support_level,
        )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        )
    return {
        "query": q,
        "paper_id": paper_id,
        "library_id": library_id,
        "parse_item_key": parse_item_key,
        "support_level": support_level,
        "results": results,
        "ragflow": knowledge_base.ragflow_status(),
        "database_path": str(paper_parse_store.database_path),
    }


@app.get("/api/workbench/snapshot")
async def get_workbench_snapshot(
    run_id: Optional[str] = None,
    library_id: Optional[str] = None,
    paper_limit: int = 12,
    run_limit: int = 8,
) -> Dict[str, Any]:
    selected_run: Optional[RunRecord] = None
    if run_id:
        selected_run = load_run_record(run_id)
        if not selected_run:
            raise HTTPException(status_code=404, detail="Run not found")

    try:
        documents = knowledge_base.list_documents(library_id=library_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "literature_library_not_found",
                "message": "没有找到目标文献库，请先选择或创建文献库。",
            },
        ) from exc

    run_summaries = knowledge_base.list_research_runs(limit=max(1, min(run_limit, 50)))
    recent_runs: list[RunRecord] = []
    for summary in run_summaries:
        record = load_run_record(str(summary.get("run_id") or ""))
        if record:
            recent_runs.append(record)
            if selected_run is None and record.status in {"queued", "running", "complete"}:
                selected_run = record

    papers = [_public_paper_summary(document) for document in documents[: max(1, min(paper_limit, 100))]]
    evidence_count = 0
    if selected_run:
        evidence_count = sum(
            len(hypothesis.get("citation_map") or {})
            for hypothesis in selected_run.hypotheses
            if isinstance(hypothesis, dict)
        )
    if not selected_run:
        evidence_boundary = "no_run"
    elif selected_run.request.demo_mode:
        evidence_boundary = "synthetic_demo"
    elif selected_run.request.literature_review and evidence_count:
        evidence_boundary = "literature_grounded_with_provenance_review"
    elif selected_run.request.literature_review:
        evidence_boundary = "literature_requested_but_evidence_pending"
    else:
        evidence_boundary = "ungrounded_model_output"

    health_payload = await build_health_payload(debug=False)
    project = None
    artifacts: list[Dict[str, Any]] = []
    if selected_run:
        project = {
            "id": selected_run.run_id,
            "title": " ".join(selected_run.request.research_goal.split())[:96],
            "research_goal": selected_run.request.research_goal,
            "status": selected_run.status,
            "mode": "demo" if selected_run.request.demo_mode else "live",
        }
        artifacts = knowledge_base.list_project_artifacts(
            project_id=selected_run.run_id,
            run_id=selected_run.run_id,
            limit=50,
        )

    return {
        "schema_version": "workbench.snapshot.v1",
        "project": project,
        "current_run": _public_snapshot_value(run_record_payload(selected_run))
        if selected_run
        else None,
        "runs": [_public_run_summary(record) for record in recent_runs[: max(1, min(run_limit, 50))]],
        "papers": papers,
        "artifacts": [_public_snapshot_value(item) for item in artifacts],
        "capabilities": {
            "research_run": True,
            "literature_library": True,
            "pdf_ingest": True,
            "evidence_search": True,
            "project_artifacts": True,
            "run_events": True,
            "research_outcome": True,
            "synthetic_demo": True,
        },
        "evidence_boundary": evidence_boundary,
        "literature_mcp": health_payload.get("literature_mcp", {}),
        "ragflow_knowledge": health_payload.get("ragflow_knowledge", {}),
    }


@app.get("/api/projects/{project_id}/artifacts")
async def list_project_artifacts(
    project_id: str,
    run_id: Optional[str] = None,
    artifact_type: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    return {
        "project_id": project_id,
        "artifacts": [
            _public_snapshot_value(item)
            for item in knowledge_base.list_project_artifacts(
                project_id=project_id,
                run_id=run_id,
                artifact_type=artifact_type,
                limit=limit,
            )
        ],
    }


@app.post("/api/projects/{project_id}/artifacts")
async def save_project_artifact(project_id: str, request: ProjectArtifactRequest) -> Dict[str, Any]:
    record = load_run_record(request.run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    artifact = knowledge_base.save_project_artifact(
        project_id=project_id,
        run_id=request.run_id,
        artifact_type=request.artifact_type,
        target_ref=request.target_ref,
        title=request.title,
        payload=request.payload,
    )
    return {"artifact": _public_snapshot_value(artifact)}


@app.post("/api/projects/{project_id}/experiment-plans")
async def create_project_experiment_plan(
    project_id: str,
    request: ExperimentPlanRequest,
) -> Dict[str, Any]:
    record = load_run_record(request.run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    if request.hypothesis_index >= len(record.hypotheses):
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    hypothesis = record.hypotheses[request.hypothesis_index]
    if not isinstance(hypothesis, dict):
        raise HTTPException(status_code=422, detail="Hypothesis payload is invalid")

    context = ResearchChatContext(
        run_id=request.run_id,
        selected_hypothesis_index=request.hypothesis_index,
        demo_mode=record.request.demo_mode,
        literature_review=record.request.literature_review,
    )
    result = _experiment_design_result(
        context,
        {
            "hypothesis_index": request.hypothesis_index,
            "query": str(hypothesis.get("text") or hypothesis.get("hypothesis") or ""),
        },
    )
    artifact = knowledge_base.save_project_artifact(
        project_id=project_id,
        run_id=request.run_id,
        artifact_type="experiment_plan",
        target_ref={"hypothesis_index": request.hypothesis_index},
        title=str(result.get("title") or "可证伪实验设计草案"),
        payload=result,
    )
    return {
        "experiment_plan": _public_snapshot_value(result),
        "artifact": _public_snapshot_value(artifact),
        "grounding_boundary": "run_audit",
    }


@app.get("/api/runs/{run_id}/events")
async def stream_run_events(run_id: str) -> StreamingResponse:
    initial = load_run_record(run_id)
    if not initial:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_stream():
        started_at = time.monotonic()
        last_fingerprint: Optional[tuple[Any, ...]] = None
        while True:
            record = load_run_record(run_id)
            if not record:
                yield _research_chat_sse_event(
                    "error",
                    {"code": "run_not_found", "message": "研究运行已不存在。"},
                )
                break
            fingerprint = (
                record.updated_at,
                record.status,
                len(record.timeline),
                len(record.hypotheses),
                len(record.agent_trace),
            )
            if fingerprint != last_fingerprint:
                last_fingerprint = fingerprint
                yield _research_chat_sse_event(
                    "run",
                    {
                        "run_id": run_id,
                        "status": record.status,
                        "updated_at": record.updated_at,
                        "timeline_count": len(record.timeline),
                        "hypothesis_count": len(record.hypotheses),
                        "agent_trace_count": len(record.agent_trace),
                        "record": _public_snapshot_value(run_record_payload(record)),
                    },
                )
            if record.status in {"complete", "error"}:
                yield _research_chat_sse_event(
                    "done",
                    {"run_id": run_id, "status": record.status},
                )
                break
            if time.monotonic() - started_at > max(RUN_TIMEOUT_SECONDS, 30) + STALE_RUN_GRACE_SECONDS:
                yield _research_chat_sse_event(
                    "error",
                    {
                        "run_id": run_id,
                        "code": "run_events_timeout",
                        "message": "运行事件流超过等待窗口，请刷新运行详情。",
                    },
                )
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/runs/{run_id}/recovery")
async def get_run_recovery(run_id: str) -> Dict[str, Any]:
    record = load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    queue = knowledge_base.active_work_item_snapshot(
        run_id=run_id,
        workflow_name="workflow.open_coscientist_run",
        limit=10,
    )
    recovery = _run_recovery_summary(record)
    if record.status in {"queued", "running"}:
        recovery = {
            "category": "in_progress",
            "summary": "运行仍在后台队列中，页面会继续接收阶段事件。",
            "retryable": False,
            "next_actions": ["monitor_run_events", "inspect_worker"],
        }
    return {
        "run_id": run_id,
        "status": record.status,
        "recovery": recovery,
        "queue": queue,
        "checkpoint_count": len(knowledge_base.list_checkpoint_metadata(run_id=run_id, limit=20)),
        "evidence_boundary": (
            "synthetic_demo"
            if record.request.demo_mode
            else "literature_requested"
            if record.request.literature_review
            else "ungrounded_model_output"
        ),
    }


@app.get("/api/runs")
async def list_runs(limit: int = 50) -> Dict[str, Any]:
    persisted = [
        normalize_run_summary_payload(item)
        for item in knowledge_base.list_research_runs(limit=max(1, min(limit, 200)))
    ]
    hot_run_ids = {item["run_id"] for item in persisted}
    hot_runs = [
        normalize_run_summary_payload(
            {
                "run_id": record.run_id,
                "status": record.status,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "request": run_record_payload(record).get("request", {}),
                "metrics": record.metrics,
                "citation_provenance_qa": record.citation_provenance_qa,
                "error": record.error,
            }
        )
        for record in runs.values()
        if record.run_id not in hot_run_ids
    ]
    combined = sorted(
        [*persisted, *hot_runs],
        key=lambda item: float(item.get("updated_at") or 0),
        reverse=True,
    )
    return {"runs": combined[: max(1, min(limit, 200))], "count": len(combined)}


@app.get("/api/runs/{run_id}/evidence-links")
async def get_run_evidence_links(run_id: str) -> Dict[str, Any]:
    if not load_run_record(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    links = knowledge_base.get_hypothesis_evidence_links(run_id)
    return {"run_id": run_id, "evidence_links": links, "count": len(links)}


@app.get("/api/runs/{run_id}/outcome")
async def get_run_research_outcome(run_id: str) -> Dict[str, Any]:
    record = load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    outcome = record.research_outcome or build_research_outcome(record)
    return {
        "run_id": run_id,
        "status": record.status,
        "evidence_snapshot": _public_snapshot_value(record.evidence_snapshot),
        "research_outcome": _public_snapshot_value(outcome),
    }


@app.get("/api/runs/{run_id}/evidence-retrievals")
async def get_run_evidence_retrievals(run_id: str) -> Dict[str, Any]:
    if not load_run_record(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    retrievals = knowledge_base.get_evidence_retrievals(run_id)
    return {"run_id": run_id, "retrievals": retrievals, "count": len(retrievals)}


@app.get("/api/runs/{run_id}/tool-calls")
async def get_run_tool_calls(run_id: str) -> Dict[str, Any]:
    if not load_run_record(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    tool_calls = knowledge_base.get_research_tool_calls(run_id)
    return {"run_id": run_id, "tool_calls": tool_calls, "count": len(tool_calls)}


@app.get("/api/runs/{run_id}/tool-results")
async def get_run_tool_results(run_id: str, limit: int = 50) -> Dict[str, Any]:
    if not load_run_record(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    results = knowledge_base.list_tool_results(run_id, limit=max(1, min(limit, 200)))
    return {"run_id": run_id, "tool_results": results, "count": len(results)}


@app.get("/api/tools/results/{result_id}")
async def get_tool_result(result_id: str) -> Dict[str, Any]:
    result = knowledge_base.get_tool_result(result_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "tool_result_not_found",
                "message": "没有找到这个工具结果引用。",
            },
        )
    return result


@app.post("/api/runs")
async def create_run(request: RunRequest) -> Dict[str, str]:
    if request.autopilot:
        try:
            request.autopilot = validate_autopilot_policy_for_persistence(request.autopilot)
        except AutopilotValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_autopilot_policy", "message": str(exc)},
            ) from exc
    if request.max_references < request.min_references:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_reference_range",
                "message": "Maximum references must be greater than or equal to minimum references.",
            },
        )
    if not request.demo_mode and not has_model_provider_key(request.model_name):
        provider = provider_for_model(request.model_name)
        raise HTTPException(
            status_code=400,
            detail={
                "code": "missing_provider_key",
                "message": f"Live mode requires {', '.join(provider['env_vars'])} for {request.model_name}.",
                "repair_hint": provider["repair_hint"],
            },
        )
    if request.literature_review:
        mcp_status = await asyncio.to_thread(probe_mcp_server)
        if not mcp_status["available"]:
            raise HTTPException(
                status_code=424,
                detail={
                    "code": "literature_mcp_unavailable",
                    "message": f"Literature review requires an MCP server at {mcp_status['url']}.",
                    "repair_hint": mcp_status["repair_hint"],
                },
            )
    if request.library_id or request.auto_discover_papers:
        try:
            request.library_id = knowledge_base.resolve_library_id(request.library_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "literature_library_not_found",
                    "message": "没有找到目标资料库，无法启动一键证据优先研究。",
                },
            ) from exc

    safety_gate = evaluate_safety_gate(request.research_goal)
    if safety_gate["status"] == "blocked":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "safety_gate_blocked",
                "message": "Research goal failed the pre-run safety gate and was not sent to the generation workflow.",
            },
        )
    if request.parent_run_id and not knowledge_base.get_research_run(request.parent_run_id):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "invalid_refinement_parent_run",
                "message": "Continuation requested a parent run that does not exist.",
            },
        )

    run_id = uuid.uuid4().hex[:12]
    record = RunRecord(
        run_id=run_id,
        status="queued",
        created_at=time.time(),
        updated_at=time.time(),
        request=request,
        safety_gate=safety_gate,
    )
    runs[run_id] = record
    persist_run_record(record)
    for feedback in request.user_feedback:
        knowledge_base.store_feedback_item(
            feedback_id=feedback.feedback_id,
            run_id=run_id,
            target_type=feedback.target_type,
            target_ref=feedback.target_ref,
            feedback_type=feedback.feedback_type,
            text=feedback.text,
            source="run_request",
            created_at=feedback.created_at,
        )

    work_item = knowledge_base.enqueue_work_item(
        workflow_name="workflow.open_coscientist_run",
        run_id=run_id,
        phase="workflow",
        agent_role="supervisor",
        arguments={
            "run_id": run_id,
            "demo_mode": request.demo_mode,
            "literature_review": request.literature_review,
            "auto_discover_papers": request.auto_discover_papers,
            "auto_ingest_papers": request.auto_ingest_papers,
            "library_id": request.library_id,
        },
    )
    persist_run_checkpoint_metadata(
        record,
        status="queued",
        phase="queue",
        checkpoint_ref=work_item.get("work_item_id"),
    )
    return {"run_id": run_id, "work_item_id": work_item.get("work_item_id", "")}


@app.post("/api/runs/{run_id}/continue")
async def continue_run(run_id: str, request: ContinueRunRequest) -> Dict[str, str]:
    parent = load_run_record(run_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Run not found")

    parent_request = parent.request
    continued_request = RunRequest(
        research_goal=request.research_goal or parent_request.research_goal,
        model_name=request.model_name or parent_request.model_name,
        demo_mode=parent_request.demo_mode if request.demo_mode is None else request.demo_mode,
        literature_review=parent_request.literature_review
        if request.literature_review is None
        else request.literature_review,
        initial_hypotheses=request.initial_hypotheses or parent_request.initial_hypotheses,
        iterations=parent_request.iterations if request.iterations is None else request.iterations,
        min_references=parent_request.min_references if request.min_references is None else request.min_references,
        max_references=parent_request.max_references if request.max_references is None else request.max_references,
        preferences=request.preferences if request.preferences is not None else parent_request.preferences,
        attributes=[*parent_request.attributes, *request.attributes],
        constraints=[*parent_request.constraints, *request.constraints],
        starting_hypotheses=[*parent_request.starting_hypotheses, *request.starting_hypotheses],
        user_feedback=request.user_feedback,
        parent_run_id=run_id,
        refinement_mode=request.refinement_mode,
        memory_scope=request.memory_scope or parent_request.memory_scope,
        library_id=request.library_id if request.library_id is not None else parent_request.library_id,
        auto_discover_papers=parent_request.auto_discover_papers
        if request.auto_discover_papers is None
        else request.auto_discover_papers,
        auto_ingest_papers=parent_request.auto_ingest_papers
        if request.auto_ingest_papers is None
        else request.auto_ingest_papers,
        paper_discovery_limit=parent_request.paper_discovery_limit
        if request.paper_discovery_limit is None
        else request.paper_discovery_limit,
        paper_ingest_limit=parent_request.paper_ingest_limit
        if request.paper_ingest_limit is None
        else request.paper_ingest_limit,
    )
    response = await create_run(continued_request)
    response["parent_run_id"] = run_id
    return response


@app.post("/api/runs/{run_id}/autopilot")
async def start_research_autopilot(
    run_id: str,
    request: ResearchAutopilotRequest,
) -> Dict[str, Any]:
    record = load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    if record.status != "complete":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "autopilot_requires_completed_run",
                "message": "研究主流程完成后才能进入证据—实验—重排闭环。",
            },
        )
    if record.research_loop:
        loop_status = str(record.research_loop.get("status") or "ready")
        raise HTTPException(
            status_code=409,
            detail={
                "code": "autopilot_already_exists",
                "message": (
                    f"这个 run 已有状态为 {loop_status} 的研究闭环。"
                    "等待态请调用 resume，awaiting_human 请提交实验解释；完成态请创建 continuation run。"
                ),
            },
        )
    try:
        result = enqueue_research_autopilot(record, request.policy)
    except (ValueError, AutopilotValidationError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_autopilot_policy", "message": str(exc)},
        ) from exc
    return {
        "run_id": run_id,
        "research_loop": _public_snapshot_value(result["research_loop"]),
        "work_item": summarize_worker_item(result["work_item"]),
    }


@app.get("/api/runs/{run_id}/autopilot")
async def get_research_autopilot(run_id: str) -> Dict[str, Any]:
    record = load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run_id,
        "research_loop": _public_snapshot_value(record.research_loop),
        "work_items": [
            summarize_worker_item(item)
            for item in knowledge_base.list_work_items(
                run_id=run_id,
                workflow_name=AUTOPILOT_WORKFLOW,
                limit=10,
            )
        ],
    }


@app.post("/api/runs/{run_id}/autopilot/resume")
async def resume_research_autopilot(
    run_id: str,
    request: ResearchAutopilotResumeRequest,
) -> Dict[str, Any]:
    record = load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    status = str(record.research_loop.get("status") or "")
    if status == "awaiting_human":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "scientific_interpretation_required",
                "message": "实验已经执行；请通过 experiment-feedback 接口确认 support、contradict 或 inconclusive，避免重复运行实验。",
            },
        )
    if status not in {"awaiting_input", "awaiting_approval", "waiting_approval", "paused", "error"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "autopilot_not_resumable",
                "message": f"当前闭环状态 {status or 'absent'} 不需要恢复。",
            },
        )
    merged = dict(record.research_loop.get("policy") or {})
    requested_grants = [dict(grant) for grant in request.grants if isinstance(grant, dict)]
    replacement_keys = {
        (str(grant.get("scope") or ""), str(grant.get("server_id") or ""))
        for grant in requested_grants
    }
    retained_grants = [
        grant
        for grant in (merged.get("grants") or [])
        if (
            str(grant.get("scope") or ""),
            str(grant.get("server_id") or ""),
        ) not in replacement_keys
    ]
    merged["grants"] = [*retained_grants, *requested_grants]
    if request.compute is not None:
        merged["compute"] = request.compute
        merged["auto_execute"] = True
    if request.evaluation is not None:
        merged["evaluation"] = request.evaluation
    if request.continue_on_limited_evidence is not None:
        merged["continue_on_limited_evidence"] = request.continue_on_limited_evidence
    if request.auto_interpret is not None:
        merged["auto_interpret"] = request.auto_interpret
    if request.auto_rerank is not None:
        merged["auto_rerank"] = request.auto_rerank
    history = list(record.research_loop.get("approval_history") or [])
    for grant in requested_grants:
        history.append(
            {
                "scope": grant.get("scope"),
                "server_id": grant.get("server_id"),
                "status": "granted" if grant.get("confirmed") else "denied",
                "reason": str(grant.get("reason") or "")[:500],
                "resolved_at": time.time(),
                "source": "autopilot_resume",
            }
        )
    record.research_loop["approval_history"] = history[-100:]
    try:
        result = enqueue_research_autopilot(record, merged, resume=True)
    except (ValueError, AutopilotValidationError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_autopilot_resume", "message": str(exc)},
        ) from exc
    return {
        "run_id": run_id,
        "research_loop": _public_snapshot_value(result["research_loop"]),
        "work_item": summarize_worker_item(result["work_item"]),
    }


@app.post("/api/runs/{run_id}/autopilot/pause")
async def pause_research_autopilot(run_id: str) -> Dict[str, Any]:
    record = load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    loop_status = str(record.research_loop.get("status") or "")
    if loop_status not in {"queued", "running"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "autopilot_not_pausable",
                "message": f"当前闭环状态 {loop_status or 'absent'} 不处于可暂停的安全推进阶段。",
            },
        )
    active = knowledge_base.list_work_items(
        run_id=run_id,
        workflow_name=AUTOPILOT_WORKFLOW,
        limit=10,
    )
    running = [item for item in active if item.get("status") in {"leased", "running"}]
    if running:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "autopilot_compute_already_running",
                "message": "当前 worker 已进入执行阶段；暂停不会安全终止远程进程，请等待本次 job 结束后再决定是否继续。",
            },
        )
    for item in active:
        if item.get("status") in {"queued", "retrying", "blocked"}:
            knowledge_base.cancel_work_item(str(item["work_item_id"]), reason="Paused by researcher")
    record.research_loop["status"] = "paused"
    record.updated_at = time.time()
    persist_run_record(record)
    update_autopilot_task(run_id, status="blocked", blocked_reason="Paused by researcher")
    return {"run_id": run_id, "research_loop": _public_snapshot_value(record.research_loop)}


@app.post("/api/runs/{run_id}/experiment-feedback")
async def record_experiment_feedback(
    run_id: str,
    request: ExperimentFeedbackRequest,
) -> Dict[str, Any]:
    approval = require_tool_workflow_approval(
        request.approval,
        expected_scope="experiment.feedback",
    )
    record = load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    job = knowledge_base.get_background_job(request.job_id)
    if not job or job.get("run_id") != run_id:
        raise HTTPException(status_code=404, detail="Experiment job not found for this run")
    if job.get("status") not in {"complete", "error"}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "experiment_job_not_terminal",
                "message": "实验尚未结束，不能提前写入科学解释。",
            },
        )
    if job.get("status") == "error" and request.verdict != "inconclusive":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "failed_execution_cannot_support_claim",
                "message": "执行失败只能标记为 inconclusive，不能作为支持或反驳假设的科学证据。",
            },
        )

    evidence_item = apply_experiment_feedback_to_record(record, request, job)
    feedback_type = {
        "support": "accept",
        "contradict": "reject",
        "inconclusive": "critique",
    }[request.verdict]
    feedback = FeedbackItem(
        target_type="experiment",
        target_ref={
            "hypothesis_index": request.hypothesis_index,
            "job_id": request.job_id,
            "evidence_id": evidence_item["evidence_id"],
        },
        feedback_type=feedback_type,
        text=f"Experiment verdict={request.verdict}. {request.rationale}",
    )
    knowledge_base.store_feedback_item(
        feedback_id=None,
        run_id=run_id,
        target_type=feedback.target_type,
        target_ref=feedback.target_ref,
        feedback_type=feedback.feedback_type,
        text=feedback.text,
        source="experiment_feedback",
    )

    rerank_run: Optional[Dict[str, str]] = None
    rerank_error: Optional[Dict[str, Any]] = None
    if request.rerank:
        starting_hypotheses = [
            str(hypothesis.get("text") or "").strip()
            for hypothesis in record.hypotheses
            if isinstance(hypothesis, dict) and str(hypothesis.get("text") or "").strip()
        ]
        try:
            rerank_run = await continue_run(
                run_id,
                ContinueRunRequest(
                    demo_mode=record.request.demo_mode,
                    literature_review=record.request.literature_review,
                    initial_hypotheses=min(8, max(1, len(starting_hypotheses))),
                    iterations=0,
                    starting_hypotheses=starting_hypotheses[:8],
                    user_feedback=[feedback],
                    refinement_mode="revise_hypotheses",
                    memory_scope=record.request.memory_scope,
                    library_id=record.request.library_id,
                    auto_discover_papers=False,
                    auto_ingest_papers=False,
                ),
            )
        except HTTPException as exc:
            rerank_error = {
                "status_code": exc.status_code,
                "detail": exc.detail,
                "boundary": "Experiment feedback was saved; reranking can be retried after runtime repair.",
            }

    loop_execution = record.research_loop.get("execution") if isinstance(record.research_loop, dict) else {}
    if isinstance(loop_execution, dict) and loop_execution.get("job_id") == request.job_id:
        persist_loop_stage(
            record,
            "review",
            "complete",
            f"研究者已将实验结果标记为 {request.verdict}，证据包和 ResearchOutcome 已刷新。",
            details={"evidence_id": evidence_item.get("evidence_id"), "job_id": request.job_id},
            loop_status="running",
        )
        if rerank_run:
            record = load_run_record(run_id) or record
            record.research_loop["rerank_run_id"] = rerank_run.get("run_id")
            persist_loop_stage(
                record,
                "rerank",
                "running",
                "人工解释已进入 continuation Review/Elo。",
                details={"rerank_run_id": rerank_run.get("run_id")},
                loop_status="reranking",
            )
            update_autopilot_task(
                run_id,
                status="running",
                result_ref={"status": "reranking", "rerank_run_id": rerank_run.get("run_id")},
            )
        elif rerank_error:
            persist_loop_stage(
                record,
                "rerank",
                "error",
                "实验解释已保存，但重新排名启动失败，可在修复运行环境后恢复。",
                details={"rerank_error": rerank_error},
                loop_status="error",
            )
            update_autopilot_task(
                run_id,
                status="blocked",
                blocked_reason="Experiment feedback saved; reranking failed to start.",
            )
        else:
            state = persist_loop_stage(
                record,
                "outcome",
                "complete",
                "实验解释和证据结果已写回；本次闭环在不重新排名的情况下完成。",
                loop_status="complete",
            )
            update_autopilot_task(run_id, status="done", result_ref={"status": state["status"]})

    return {
        "run_id": run_id,
        "hypothesis_index": request.hypothesis_index,
        "approval": approval,
        "evidence_item": _public_snapshot_value(evidence_item),
        "research_outcome": _public_snapshot_value(record.research_outcome),
        "rerank_run": rerank_run,
        "rerank_error": rerank_error,
    }


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    record = load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    return _public_snapshot_value(run_record_payload(record))


@app.post("/api/runs/{run_id}/feedback")
async def record_run_feedback(run_id: str, feedback: FeedbackItem) -> Dict[str, Any]:
    if not load_run_record(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    item = knowledge_base.store_feedback_item(
        feedback_id=feedback.feedback_id,
        run_id=run_id,
        target_type=feedback.target_type,
        target_ref=feedback.target_ref,
        feedback_type=feedback.feedback_type,
        text=feedback.text,
        source="user",
        created_at=feedback.created_at,
    )
    return {"feedback": item}


@app.get("/api/runs/{run_id}/feedback")
async def list_run_feedback(run_id: str, limit: int = 50) -> Dict[str, Any]:
    if not load_run_record(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    feedback = knowledge_base.list_feedback_items(run_id=run_id, limit=max(1, min(limit, 200)))
    return {"feedback": feedback, "count": len(feedback), "run_id": run_id}


@app.get("/api/runs/{run_id}/memory")
async def get_run_memory(run_id: str) -> Dict[str, Any]:
    record = load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    memory = knowledge_base.build_memory_context(
        research_goal=record.request.research_goal,
        parent_run_id=record.request.parent_run_id or run_id,
        library_id=record.request.library_id,
        memory_scope=record.request.memory_scope,
    )
    include_current_run_feedback_in_memory(memory, run_id=run_id, parent_run_id=record.request.parent_run_id)
    return {"run_id": run_id, "summary": memory_context_user_summary(memory), "memory": memory}


@app.get("/api/runs/{run_id}/checkpoints")
async def list_run_checkpoints(run_id: str, limit: int = 20) -> Dict[str, Any]:
    if not load_run_record(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    checkpoints = knowledge_base.list_checkpoint_metadata(run_id=run_id, limit=max(1, min(limit, 200)))
    has_langgraph_summary = any(
        item.get("checkpoint_backend") == "langgraph_sqlite" for item in checkpoints
    )
    latest_checkpoint = checkpoints[0] if checkpoints else None
    checkpoint_summary = {
        "status": (
            "ready"
            if has_langgraph_summary
            else "metadata_only"
            if latest_checkpoint
            else "not_available"
        ),
        "checkpoint_count": len(checkpoints),
        "thread_id": run_id,
        "latest_checkpoint_id": latest_checkpoint.get("checkpoint_id") if latest_checkpoint else None,
        "latest_status": latest_checkpoint.get("status") if latest_checkpoint else None,
        "latest_phase": latest_checkpoint.get("phase") if latest_checkpoint else None,
        "checkpoint_backend": latest_checkpoint.get("checkpoint_backend") if latest_checkpoint else None,
        "has_langgraph_summary": has_langgraph_summary,
        "resume_boundary": (
            "LangGraph checkpoint summary is available; raw state channels remain hidden."
            if has_langgraph_summary
            else "Only execution metadata is available; full LangGraph state resume remains limited."
            if latest_checkpoint
            else "No checkpoint metadata is available for this run."
        ),
    }
    return {
        "run_id": run_id,
        "checkpoints": checkpoints,
        "count": len(checkpoints),
        "summary": checkpoint_summary,
        "boundary": (
            "Checkpoint metadata includes LangGraph checkpoint summaries when available; raw channel values are not exposed."
            if has_langgraph_summary
            else "Execution metadata index only; LangGraph state saver summary is not available for this run."
        ),
    }


@app.get("/api/runs/{run_id}/trace")
async def get_run_trace(run_id: str) -> Dict[str, Any]:
    record = load_run_record(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"agent_trace": record.agent_trace, "summary": agent_trace_user_summary(record.agent_trace)}
