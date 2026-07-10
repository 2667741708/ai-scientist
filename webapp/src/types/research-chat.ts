import type { RagEvidenceResult, ToolWorkflowApproval } from "./workbench";

export type ResearchChatIntent =
  | "ask_project_ai"
  | "discover_capabilities"
  | "summarize_project_artifacts"
  | "start_research_run"
  | "explain_current_run"
  | "inspect_hypothesis"
  | "explain_ranking"
  | "parse_pdf_to_knowledge_base"
  | "extract_web_evidence"
  | "extract_web_evidence_batch"
  | "search_public_web"
  | "search_knowledge_evidence"
  | "check_hypothesis_grounding"
  | "verify_evidence_with_literature"
  | "run_terminal_command"
  | "run_ssh_training_command"
  | "snapshot_local_file"
  | "register_project_tool"
  | "design_experiment"
  | "draft_report"
  | "search_session_history"
  | "clarify"
  | "unsupported";

export type ResearchChatState =
  | "idle"
  | "routing"
  | "needs_input"
  | "awaiting_confirmation"
  | "executing"
  | "complete"
  | "error";

export type ResearchChatCapability = {
  id: string;
  userTitle: string;
  userSummary: string;
  intent: ResearchChatIntent;
  taskArea:
    | "project_help"
    | "research_run"
    | "evidence"
    | "knowledge_search"
    | "hypothesis_audit"
    | "ranking_audit"
    | "experiment"
    | "report"
    | "history"
    | "runtime_tools"
    | "tool_management";
  executionMode: "read_only" | "approval_required" | "unsupported";
  approvalScope?: string;
  requiredInputs: Array<{
    key: string;
    label: string;
    type: "text" | "url" | "pdf_path" | "file" | "hypothesis_text" | "run_ref" | "command";
    required: boolean;
  }>;
  expectedOutputs: string[];
  groundingBoundary:
    | "project_capability_registry"
    | "live_model_workflow"
    | "parsed_fulltext"
    | "public_html_best_effort"
    | "knowledge_base"
    | "run_audit"
    | "tournament_audit"
    | "literature_mcp_audit"
    | "session_search"
    | "public_web_search"
    | "local_terminal_audit"
    | "remote_ssh_audit"
    | "local_file_snapshot"
    | "tool_registry_draft";
  availability?: {
    available: boolean;
    status: "ready" | "limited" | "unavailable" | string;
    summary: string;
  };
};

export type ResearchChatActionProposal = {
  actionId: string;
  intent: ResearchChatIntent;
  title: string;
  summary: string;
  inputSummary: string;
  operationSummary: string[];
  riskSummary: string;
  expectedResultSummary: string[];
  approvalRequired: boolean;
  approvalScope?:
    | "research.start_live_run"
    | "pdf.parse_to_knowledge_base"
    | "browser.web_extract"
    | "mcp.literature_review"
    | "web.search_public"
    | "terminal.command"
    | "ssh.training_command"
    | "file.source_snapshot"
    | "tool.register_draft";
  executionTarget:
    | "workflow.start_run"
    | "workflow.pdf_parse"
    | "workflow.web_extract"
    | "workflow.web_search"
    | "workflow.file_snapshot"
    | "workflow.tool_register_draft"
    | "workflow.terminal_command"
    | "workflow.ssh_training_command"
    | "workflow.evidence_literature_verification"
    | "query.capability_map"
    | "query.run_summary"
    | "query.hypothesis_inspection"
    | "query.ranking_explanation"
    | "query.session_search"
    | "navigation.workspace_panel"
    | "query.rag_search"
    | "query.hypothesis_grounding";
  requestPreview: Record<string, unknown>;
};

export type EvidenceVerificationItem = Partial<RagEvidenceResult> & {
  type?: string;
  status?: string;
  snippet?: string;
  target_ref?: Record<string, unknown>;
  evidence_id?: string | null;
  result_id?: string | null;
  source_channel?: "knowledge_base" | "run_link" | "external_mcp" | string;
  evidence_summary?: string;
  support_signal?: number;
  possible_counter_evidence?: boolean;
};

export type EvidenceClaimCheck = {
  claim: string;
  status: "supported" | "partially_supported" | "missing" | "ungrounded";
  matchedTerms?: string[];
  coverage?: number;
  evidenceCount?: number;
};

export type ResearchChatResult = {
  intent?: ResearchChatIntent;
  title?: string;
  summary?: string;
  verdict?: "grounded" | "supported" | "limited" | "contradicted" | "ungrounded";
  support_level?: string;
  confidence?: number;
  modelName?: string;
  plannerStatus?: "complete" | "model_missing" | "model_disabled" | "planner_error" | "legacy_disabled" | string;
  plannerConfidence?: number;
  capabilityId?: string | null;
  routingSource?: "llm_planner" | "safety_guard" | "fallback_error" | string;
  structuredContext?: Record<string, unknown> | null;
  query?: string;
  runId?: string;
  researchGoal?: string;
  hypothesisCount?: number;
  tournamentCount?: number;
  hypothesisIndex?: number;
  score?: number;
  eloRating?: number;
  plainExplanation?: string;
  experimentPlan?: string;
  reviewSummary?: string;
  modeBoundary?: string;
  timeline?: Array<Record<string, unknown>>;
  rankedHypotheses?: Array<{ index: number; title: string; eloRating?: number | string | null }>;
  tournamentMatchups?: Array<{
    matchupIndex: number;
    winner?: string | number | null;
    loser?: string | number | null;
    confidence?: number | string | null;
    beforeElo?: Record<string, unknown>;
    afterElo?: Record<string, unknown>;
    eloDelta?: Record<string, unknown>;
    reasoning?: string | null;
    comparisonMode?: string | null;
  }>;
  capabilityGroups?: Record<string, ResearchChatCapability[]>;
  capabilities?: ResearchChatCapability[];
  sections?: string[];
  artifactCounts?: Record<string, number | string | null>;
  hypothesisPreview?: string;
  hypotheses?: Array<{
    index: number;
    title: string;
    text?: string;
    plainExplanation?: string;
    experimentPlan?: string;
    score?: number | string | null;
    eloRating?: number | string | null;
    reviewSummary?: string;
    groundingStatus?: string | null;
  }>;
  experiments?: Array<{
    index: number;
    hypothesisIndex?: number;
    title: string;
    experimentPlan?: string;
    falsificationTests?: string[];
    source_channel?: string;
  }>;
  reports?: Array<{
    title: string;
    summary?: string;
    sections?: string[];
    source_channel?: string;
  }>;
  papers?: EvidenceVerificationItem[];
  items?: EvidenceVerificationItem[];
  supportingEvidence?: EvidenceVerificationItem[];
  possibleCounterEvidence?: EvidenceVerificationItem[];
  claimChecks?: EvidenceClaimCheck[];
  missingEvidence?: string[];
  falsificationTests?: string[];
  externalCheck?: {
    status?: "not_requested" | "running" | "complete" | "failed" | string;
    summary?: string;
    query?: string;
    mcpTool?: string;
    mcpToolName?: string;
    sources?: string[];
    sourceStatuses?: Array<{
      toolId?: string;
      mcpToolName?: string;
      status?: string;
      summary?: string;
      errorCode?: string | null;
      resultSize?: number;
      resultRef?: Record<string, unknown> | null;
    }>;
    resultPreview?: string;
    resultSize?: number;
    resultRef?: Record<string, unknown> | null;
    errorCode?: string | null;
  };
  sourceReliabilitySummary?: {
    parsedFulltextCount?: number;
    experimentalEvidenceCount?: number;
    externalMcpEvidenceCount?: number;
    totalEvidenceCount?: number;
    runEvidenceLinksCount?: number;
    runEvidenceRetrievalsCount?: number;
  };
  evidenceSourceExplanation?: string;
  rankingCaveat?: string;
  nextActions?: string[];
  groundingBoundary?: string;
  status?: string;
  knowledgeHitCount?: number;
  resultCount?: number;
  jobId?: string;
  toolName?: string;
  serverId?: string;
  commandRisk?: Record<string, unknown> | null;
  guardrail?: Record<string, unknown> | null;
  permissionPolicy?: Record<string, unknown> | null;
  pageCount?: number;
  chunksCount?: number;
  experimentalChunksCount?: number;
  knowledgeBaseIngested?: boolean;
  ragSearchReady?: boolean;
  sourceReliability?: string;
  parseRunId?: string;
  paperId?: string;
  finalUrl?: string;
  knowledgeBasePaperId?: string;
  pdfLinkCount?: number;
  supplementaryLinkCount?: number;
  artifactSummary?: {
    solveDir?: string;
    bibtexReady?: boolean;
    mediaCount?: number;
  };
  resultRef?: Record<string, unknown> | null;
  mcpResultRef?: Record<string, unknown> | null;
};

export type ResearchChatAssistantMessage = {
  kind: "clarification" | "action_proposal" | "result_summary" | "unsupported" | "error" | "status";
  text: string;
  proposal?: ResearchChatActionProposal;
  result?: ResearchChatResult;
  suggestions?: ResearchChatCapability[];
};

export type ResearchChatTurnResponse = {
  session_id: string;
  assistant_message: ResearchChatAssistantMessage;
  state: ResearchChatState;
};

export type ResearchChatProgressEvent = {
  phase: string;
  message: string;
  createdAt?: number;
  elapsedMs?: number;
  intent?: ResearchChatIntent | string;
  missingInputs?: string[];
  knowledgeHitCount?: number;
  modelName?: string;
  plannerStatus?: string;
  plannerConfidence?: number;
  capabilityId?: string | null;
  routingSource?: string;
  scoped?: boolean;
  sessionId?: string;
  delta?: string;
};

export type ResearchChatStreamEvent =
  | { event: "session"; data: { session_id: string; message?: string } }
  | { event: "progress"; data: ResearchChatProgressEvent }
  | { event: "final"; data: ResearchChatTurnResponse }
  | { event: "error"; data: { message: string; code?: string; httpStatus?: number } };

export type ResearchChatTurnRequest = {
  session_id?: string;
  message: string;
  context?: {
    page?: string;
    page_path?: string;
    mode?: "workspace" | "project_help" | "evidence";
    run_id?: string | null;
    project_goal?: string | null;
    paper_id?: string | null;
    library_id?: string | null;
    selected_hypothesis_id?: string | null;
    selected_hypothesis_index?: number | null;
    hypothesis_index?: number | null;
    hypothesis_title?: string | null;
    hypothesis_summary?: string | null;
    selected_source_ref?: string | null;
    model_name?: string;
    literature_review?: boolean;
    demo_mode?: boolean;
    initial_hypotheses?: number;
    iterations?: number;
    min_references?: number;
    max_references?: number;
    language?: "zh" | "en";
  };
};

export type ResearchChatConfirmRequest = {
  approval: ToolWorkflowApproval;
};

export type ResearchChatCapabilitiesResponse = {
  capabilities: ResearchChatCapability[];
  count: number;
};

export type ResearchChatSessionSummary = {
  session_id: string;
  mode: "workspace" | "project_help" | "evidence" | string;
  run_id?: string | null;
  title: string;
  context: Record<string, unknown>;
  created_at: number;
  updated_at: number;
};

export type ResearchChatSessionsResponse = {
  sessions: ResearchChatSessionSummary[];
  count: number;
};

export type ResearchChatSessionResponse = ResearchChatSessionSummary & {
  messages: Array<{
    message_id: string;
    role: "user" | "assistant" | string;
    text: string;
    message: Record<string, unknown>;
    created_at: number;
  }>;
  actions: Array<{
    action_id: string;
    status: string;
    intent: ResearchChatIntent | string;
    approval_scope?: string | null;
    execution_target: string;
    proposal: ResearchChatActionProposal;
    result_ref: Record<string, unknown>;
    error_summary?: string | null;
    created_at: number;
    updated_at: number;
  }>;
};
