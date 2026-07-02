export type RunStatus = "queued" | "running" | "complete" | "error";
export type EventStatus = "queued" | "active" | "complete" | "error";
export type DetailTab =
  | "overview"
  | "agents"
  | "hypotheses"
  | "evidence"
  | "tournament"
  | "metrics";
export type Language = "en" | "zh";

export type TimelineEvent = {
  time: string;
  stage: string;
  event: string;
  details: string;
  status: EventStatus;
};

export type Hypothesis = {
  text: string;
  explanation?: string;
  literature_grounding?: string;
  experiment?: string;
  score?: number;
  elo_rating?: number;
  generation_method?: string;
  win_count?: number;
  loss_count?: number;
  citation_map?: Record<string, unknown>;
  grounding_status?: "ungrounded" | "citation_mismatch" | "limited_fulltext" | "provenance_checked" | "knowledge_base_supported";
  citation_support_levels?: Record<string, string>;
  citation_source_reliability?: Record<string, string>;
  knowledge_base_support?: KnowledgeSupportItem[];
  experimental_support_summaries?: KnowledgeSupportItem[];
};

export type AgentTrace = {
  event_id?: string;
  parent_event_id?: string | null;
  agent: string;
  role: string;
  phase?: string;
  status?: EventStatus;
  output: string;
  tool_calls?: Record<string, unknown>[];
  token_usage?: Record<string, unknown>;
  synthetic?: boolean;
  confidence: number;
};

export type AgentSpec = {
  agent_id: string;
  phase: string;
  role: string;
  input_contract: Record<string, unknown>;
  output_contract: Record<string, unknown>;
  prompt_template: string;
  tool_policy: Record<string, unknown>;
  failure_policy: Record<string, unknown>;
  observability_fields: string[];
  configurable: boolean;
  degradation_when_disabled: string;
};

export type AgentRegistryResponse = {
  agents: AgentSpec[];
  count: number;
  phases: string[];
  registry_version: string;
  boundary: string;
};

export type ProviderStatus = {
  configured: boolean;
  usable: boolean;
  mode: string;
  reason: string;
  checked_at: number;
  repair_hint?: string;
  verified?: boolean;
};

export type LiteratureMcpStatus = {
  url?: string;
  available: boolean;
  mode: string;
  reason: string;
  repair_hint?: string;
  checked_at: number;
};

export type LiteratureServiceRuntime = {
  service: string;
  host: string;
  port: number;
  url: string;
  root?: string;
  server_file_exists: boolean;
  running: boolean;
  managed_process_running: boolean;
  startable: boolean;
  started?: boolean;
  pid?: number | null;
  stdout_log?: string;
  stderr_log?: string;
  message?: string;
  checked_at: number;
};

export type LiteratureServiceStartResponse = {
  runtime: LiteratureServiceRuntime;
  literature_mcp: LiteratureMcpStatus;
};

export type FeedbackItem = {
  feedback_id?: string;
  target_type: "run" | "hypothesis" | "ranking" | "evidence" | "experiment";
  target_ref: Record<string, unknown>;
  feedback_type: "accept" | "reject" | "edit" | "prefer" | "critique" | "constraint";
  text: string;
  created_at?: number;
};

export type RunRequest = {
  research_goal: string;
  model_name: string;
  demo_mode: boolean;
  literature_review: boolean;
  initial_hypotheses: number;
  iterations: number;
  min_references?: number;
  max_references?: number;
  preferences?: string | null;
  attributes?: string[];
  constraints?: string[];
  starting_hypotheses?: string[];
  user_feedback?: FeedbackItem[];
  parent_run_id?: string | null;
  refinement_mode?: "new_run" | "continue_from_run" | "revise_hypotheses";
  memory_scope?: "current_run" | "project" | "library" | "global";
  library_id?: string | null;
};

export type ContinueRunRequest = {
  research_goal?: string | null;
  model_name?: string | null;
  demo_mode?: boolean | null;
  literature_review?: boolean | null;
  initial_hypotheses?: number | null;
  iterations?: number | null;
  min_references?: number | null;
  max_references?: number | null;
  preferences?: string | null;
  attributes?: string[];
  constraints?: string[];
  starting_hypotheses?: string[];
  user_feedback?: FeedbackItem[];
  refinement_mode?: "new_run" | "continue_from_run" | "revise_hypotheses";
  memory_scope?: "current_run" | "project" | "library" | "global" | null;
  library_id?: string | null;
};

export type RunRecord = {
  run_id: string;
  status: RunStatus;
  request: RunRequest;
  timeline: TimelineEvent[];
  hypotheses: Hypothesis[];
  research_plan: Record<string, unknown>;
  agent_trace: AgentTrace[];
  tournament_matchups: Record<string, unknown>[];
  metrics: Record<string, unknown>;
  safety_gate?: Record<string, unknown>;
  citation_provenance_qa?: Record<string, unknown>;
  expert_feedback?: Record<string, unknown>;
  error?: string;
};

export type CheckpointMetadata = {
  checkpoint_id: string;
  run_id: string;
  thread_id: string;
  phase?: string | null;
  status: string;
  checkpoint_backend: string;
  checkpoint_ref?: string | null;
  state_summary: Record<string, unknown>;
  created_at: number;
  updated_at: number;
};

export type RunCheckpointsResponse = {
  run_id: string;
  checkpoints: CheckpointMetadata[];
  count: number;
  boundary: string;
};

export type ExecutionMemoryStatus = {
  status: "limited" | "ready";
  thread_id_required: boolean;
  thread_id_source: "run_id";
  checkpoint_backend: "sqlite_metadata" | "langgraph_sqlite";
  langgraph_checkpoint_sqlite_available: boolean;
  runtime_only_state_keys: string[];
  boundary: string;
};

export type Health = {
  status: string;
  api_endpoint?: string;
  run_timeout_seconds?: number;
  startup?: {
    powershell_utf8_command: string;
    working_directory: string;
  };
  literature_mcp?: LiteratureMcpStatus;
  has_gemini_key: boolean;
  has_openai_key: boolean;
  has_anthropic_key: boolean;
  has_deepseek_key: boolean;
  has_dashscope_key: boolean;
  has_mimo_key?: boolean;
  has_local_agent_key: boolean;
  local_agent_provider?: string;
  providers?: Record<string, ProviderStatus>;
};

export type AccountRole = "researcher" | "admin";
export type AccountStatus = "active" | "disabled";

export type AccountUser = {
  id: string;
  email: string;
  display_name: string;
  role: AccountRole;
  permissions: string[];
  status: AccountStatus;
  login_count: number;
  recovery_configured?: boolean;
  last_login_at?: number | null;
  created_at: number;
  updated_at: number;
};

export type AuthSession = {
  access_token: string;
  token_type: "bearer";
  user: AccountUser;
  ok?: boolean;
  code?: string;
  http_status?: number;
};

export type AuthUsersResponse = {
  users: AccountUser[];
  actor?: AccountUser;
};

export type SummaryItem = {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warning" | "error";
};

export type TournamentItemViewModel = {
  id: string;
  label: string;
  participantsLabel: string;
  winnerLabel: string;
  loserLabel: string;
  confidenceLabel: string;
  comparisonModeLabel: string;
  winnerEloLabel: string;
  loserEloLabel: string;
  reasoning: string;
  priorityLabel: string;
  tone?: "neutral" | "ok" | "warning" | "error";
};

export type KnowledgeSupportItem = {
  paper_id?: string;
  title?: string;
  chunk_id?: string;
  section_type?: string;
  section_path?: string[];
  chunk_title?: string;
  support_level?: string;
  experiment_data_summary?: string;
  text_preview?: string;
  source_reliability?: string;
};

export type StatusBadgeItem = {
  label: string;
  tone: "neutral" | "ok" | "warning" | "error";
};

export type TemplateOption = {
  title: Record<Language, string>;
  goal: Record<Language, string>;
  focus: Record<Language, string>;
};

export type ProjectViewModel = {
  id: string;
  title: string;
  researchGoal: string;
  status: RunStatus | "draft";
  modeLabel: string;
  groundingLabel: string;
  stageLabel: string;
  nextStep: string;
  hypothesisCount: number;
  evidenceCount: number;
  lastActivity: string;
  route: string;
  papersRoute: string;
  hypothesesRoute: string;
  experimentsRoute: string;
  reportsRoute: string;
  workspaceRoute: string;
  outputCount: number;
  run?: RunRecord;
};

export type HypothesisCardViewModel = {
  id: string;
  title: string;
  summary: string;
  scoreLabel: string;
  rankLabel: string;
  grounding: string;
  experimentPlan: string;
  citations: SummaryItem[];
  citationPdfCandidates: CitationPdfCandidate[];
  evidenceBadges: StatusBadgeItem[];
  governanceBadges: StatusBadgeItem[];
  citationSupportItems: SummaryItem[];
  knowledgeSupportItems: SummaryItem[];
  experimentSupportItems: SummaryItem[];
  referenceRangeLabel: string;
  raw: Hypothesis;
};

export type CitationPdfCandidate = {
  key: string;
  title: string;
  pdfPath: string;
  supportLabel: string;
};

export type TranslationRequest = {
  model_name: string;
  text: string;
  explanation?: string;
  experiment?: string;
};

export type TranslationResponse = {
  translation: string;
};

export type PaperIngestRequest = {
  title: string;
  content: string;
  authors?: string[];
  year?: number;
  doi?: string;
  url?: string;
  abstract?: string;
  source?: string;
  library_id?: string;
};

export type PaperIngestResponse = {
  paper_id: string;
  library_id: string;
  title: string;
  source_reliability: string;
  chunks_count: number;
  section_types: string[];
  experimental_chunks_count: number;
  experimental_support_summaries: Array<{
    chunk_id: string;
    section_path: string[];
    summary: string;
  }>;
};

export type PaperParseItemStatus = "pending" | "running" | "success" | "warning" | "error";
export type PdfRegionRiskLevel = "ok" | "review" | "high";

export type PdfRegionRiskFlag = {
  code:
    | "multiple_caption_numbers"
    | "adjacent_caption_title"
    | "abnormal_crop_height"
    | "tiny_png_file"
    | "incomplete_pdf_block_coverage"
    | "cross_column_or_formula_region";
  severity: PdfRegionRiskLevel;
  message: string;
  evidence: Record<string, unknown>;
};

export type PaperParseEvidence = {
  evidence_id: string;
  parse_run_id: string;
  paper_id?: string | null;
  item_key: string;
  evidence_type: "file" | "metadata" | "chunk" | "media" | "database" | "rag";
  label: string;
  file_path?: string | null;
  chunk_id?: string | null;
  section_path: string[];
  text_preview?: string | null;
  media_preview?: string | null;
  metadata: Record<string, unknown>;
  created_at: number;
};

export type PaperParseItem = {
  item_key: string;
  label: string;
  status: PaperParseItemStatus;
  evidence_type: "file" | "metadata" | "chunk" | "media" | "database" | "rag";
  evidence_summary: string;
  evidence_id?: string | null;
  completed_at?: number | null;
  error_message?: string | null;
  evidence?: PaperParseEvidence | null;
};

export type PaperParseRun = {
  parse_run_id: string;
  paper_id?: string | null;
  library_id?: string | null;
  title: string;
  status: PaperParseItemStatus;
  input_kind: "upload" | "local_path";
  input_path: string;
  pdf_path?: string | null;
  solve_dir?: string | null;
  page_count?: number | null;
  chunks_count: number;
  experimental_chunks_count: number;
  knowledge_base_ingested: boolean;
  rag_search_ready: boolean;
  created_at?: number;
  updated_at?: number;
  items: PaperParseItem[];
  evidence?: PaperParseEvidence[];
};

export type PaperParseRunsResponse = {
  parse_runs: PaperParseRun[];
  count: number;
};

export type PaperParseStatusResponse = {
  paper: {
    paper_id?: string | null;
    title?: string | null;
    pdf_path?: string | null;
    output_name?: string | null;
  };
  parse_run: PaperParseRun;
  parse_status_summary: {
    total_items: number;
    completed_items: number;
    warning_items: number;
    failed_items: Array<{
      item_key?: string | null;
      label?: string | null;
      error_message?: string | null;
    }>;
    completion_rate: number;
    rag_indexed_chunks_count: number;
    database_path: string;
  };
};

export type RagEvidenceResult = {
  chunk_id: string;
  paper_id: string;
  library_id?: string | null;
  parse_run_id?: string | null;
  parse_item_key?: string | null;
  title: string;
  section_path: string[];
  section_type: string;
  text_preview: string;
  evidence_summary?: string | null;
  support_level: string;
  source_reliability: string;
  evidence_path?: string | null;
  evidence_id?: string | null;
  score: number;
};

export type RagSearchResponse = {
  query: string;
  paper_id?: string | null;
  library_id?: string | null;
  parse_item_key?: string | null;
  support_level?: string | null;
  results: RagEvidenceResult[];
  database_path: string;
};

export type PdfParseRequest = {
  pdf_path: string;
  fetch_metadata?: boolean;
  ingest_to_knowledge_base?: boolean;
  library_id?: string;
};

export type PdfMediaAsset = {
  asset_id?: string;
  kind: string;
  page: number;
  rect: number[];
  path: string;
  caption_preview: string;
  width?: number;
  height?: number;
  file_size_bytes?: number;
  confidence?: number;
  risk_level?: PdfRegionRiskLevel;
  risk_flags?: PdfRegionRiskFlag[];
  review_required?: boolean;
};

export type PdfParseResponse = {
  parse_run_id: string;
  paper_id?: string | null;
  library_id?: string | null;
  title: string;
  doi?: string | null;
  page_count: number;
  solve_dir: string;
  extracted_text_path: string;
  metadata_json_path: string;
  metadata_text_path: string;
  chunks_json_path: string;
  bibtex_path?: string | null;
  media_assets: PdfMediaAsset[];
  chunks_count: number;
  experimental_chunks_count: number;
  knowledge_base_ingested: boolean;
  rag_search_ready: boolean;
  status: PaperParseItemStatus;
  items: PaperParseItem[];
  source_reliability: string;
  experimental_support_summaries: Array<{
    chunk_id: string;
    section_path: string[];
    summary: string;
    evidence_id?: string | null;
  }>;
};

export type KnowledgePaper = {
  paper_id: string;
  library_id?: string | null;
  title: string;
  authors: string[];
  year?: number | null;
  doi?: string | null;
  url?: string | null;
  source: string;
  source_reliability: string;
  parse_run_id?: string | null;
  chunks_count: number;
  section_types: string[];
  experimental_chunks_count: number;
  created_at: number;
};

export type KnowledgePapersResponse = {
  papers: KnowledgePaper[];
  count: number;
  library_id?: string | null;
};

export type LiteratureLibrary = {
  library_id: string;
  name: string;
  description?: string | null;
  created_at: number;
  updated_at: number;
  paper_count: number;
  parse_run_count: number;
  chunk_count: number;
  is_default: boolean;
};

export type LiteratureLibrariesResponse = {
  libraries: LiteratureLibrary[];
  count: number;
  default_library_id: string;
};

export type LiteratureLibraryCreateRequest = {
  name: string;
  description?: string;
};

export type LiteratureDiscoveryCandidate = {
  candidate_id: string;
  title: string;
  authors?: string;
  year?: string;
  source: string;
  source_id?: string;
  doi?: string | null;
  arxiv_id?: string | null;
  abstract?: string;
  url?: string | null;
  pdf_url?: string | null;
  download_method: string;
  can_parse_pdf: boolean;
  status: "ready_to_parse" | "landing_page_only" | "metadata_only";
  tool_id: string;
};

export type LiteratureDiscoveryRequest = {
  query: string;
  library_id?: string;
  preferred_source?: "auto" | "all" | "arxiv" | "pubmed" | "scholar";
  max_results?: number;
  approval: ToolWorkflowApproval;
};

export type LiteratureDiscoveryResponse = {
  query: string;
  library_id: string;
  status: "ready" | "limited";
  message: string;
  mcp: LiteratureMcpStatus;
  tool?: {
    tool_id: string;
    mcp_tool_name: string;
    display_name: string;
  };
  tools?: Array<{
    tool_id: string;
    mcp_tool_name: string;
    display_name: string;
  }>;
  source_statuses?: Array<{
    tool_id: string;
    mcp_tool_name: string;
    display_name: string;
    status: "ready" | "limited" | "failed" | string;
    message: string;
  }>;
  candidates: LiteratureDiscoveryCandidate[];
};

export type LiteratureCitationRequest = {
  title: string;
  source?: string;
  source_id?: string;
  doi?: string | null;
  arxiv_id?: string | null;
  url?: string | null;
  pdf_url?: string | null;
  approval: ToolWorkflowApproval;
};

export type LiteratureCitationResponse = {
  status: "ready" | "unavailable";
  message: string;
  doi?: string | null;
  source: string;
  source_url?: string | null;
  bibtex?: string;
};

export type PaperInterpretRequest = {
  pdf_path: string;
  output_name: string;
  model_name?: string;
  fetch_metadata?: boolean;
};

export type PaperInterpretResponse = {
  pdf_path: string;
  output_name: string;
  paper_id?: string | null;
  parse_run_id?: string | null;
  title: string;
  doi?: string | null;
  page_count: number;
  markdown_path: string;
  extracted_text_path: string;
  bibtex_path?: string | null;
  official_metadata_path: string;
  published_plain_text_path?: string | null;
  media_dir: string;
  media_assets: PdfMediaAsset[];
  image_links_checked: number;
  missing_image_links: string[];
  bibtex_source: string;
  plain_text_source_note: string;
  parse_status_summary?: PaperParseStatusResponse["parse_status_summary"];
  parse_items?: PaperParseItem[];
  rag_indexed_chunks_count?: number;
  database_path?: string;
};

export type OutputViewModel = {
  id: string;
  title: string;
  summary: string;
  kind: "finding" | "report" | "experiment";
  route: string;
};

export type WorkspaceViewModel = {
  project: ProjectViewModel;
  hypotheses: HypothesisCardViewModel[];
  outputs: OutputViewModel[];
  planItems: SummaryItem[];
  metricItems: SummaryItem[];
  tournamentItems: TournamentItemViewModel[];
};

export type ToolWorkflowApproval = {
  confirmed: boolean;
  scope: string;
  reason?: string | null;
  granted_by?: string;
  permission_mode?: CommandPermissionMode;
  command_risk?: Record<string, unknown>;
};

export type CommandPermissionMode = "request_approval" | "approve_safe" | "full_access";

export type CommandPermissionModeSpec = {
  mode: CommandPermissionMode;
  label: string;
  description: string;
  approval_policy: string;
};

export type CommandPermissionPolicy = CommandPermissionModeSpec & {
  source: string;
  modes: CommandPermissionModeSpec[];
  checked_at: number;
};

export type CommandPermissionResponse = {
  policy: CommandPermissionPolicy;
  terminal: Record<string, unknown>;
  ssh: Record<string, unknown>;
  actor?: AccountUser;
};

export type ToolWorkflowBaseResponse = {
  tool_name: string;
  phase: string;
  toolset: string;
  risk_level: string;
  run_id?: string | null;
  approval: ToolWorkflowApproval;
  availability?: Record<string, unknown>;
  policy?: Record<string, unknown>;
  result_ref?: Record<string, unknown> | null;
};

export type FileSnapshotRequest = {
  source_path: string;
  phase?: string;
  run_id?: string;
  start_line?: number;
  line_count?: number;
  max_bytes?: number;
  approval: ToolWorkflowApproval;
};

export type FileSnapshotResult = {
  artifact_id: string;
  relative_path: string;
  mime_type: string;
  content_sha256: string;
  size_bytes: number;
  modified_at: number;
  captured_at: number;
  start_line: number;
  line_count: number;
  total_lines: number;
  snapshot_path: string;
  metadata_path: string;
  artifact_dir: string;
  source_reliability: string;
  text_preview?: string;
  guardrail?: Record<string, unknown>;
};

export type FileSnapshotResponse = ToolWorkflowBaseResponse & {
  file_result: FileSnapshotResult;
};

export type WebExtractRequest = {
  url: string;
  phase?: string;
  run_id?: string;
  max_bytes?: number;
  max_text_chars?: number;
  ingest_to_knowledge_base?: boolean;
  approval: ToolWorkflowApproval;
};

export type WebExtractResult = {
  artifact_id: string;
  requested_url: string;
  final_url: string;
  host: string;
  status_code: number;
  content_type: string;
  content_hash: string;
  fetched_at: number;
  title: string;
  text_char_count: number;
  captured_text_char_count: number;
  response_truncated: boolean;
  text_truncated: boolean;
  snapshot_path: string;
  metadata_path: string;
  artifact_dir: string;
  link_count: number;
  pdf_links: Array<Record<string, string>>;
  supplementary_links: Array<Record<string, string>>;
  source_reliability: string;
  text_preview?: string;
  knowledge_base_paper_id?: string | null;
  guardrail?: Record<string, unknown>;
};

export type WebExtractResponse = ToolWorkflowBaseResponse & {
  web_result: WebExtractResult;
};

export type WebSearchRequest = {
  query: string;
  phase?: string;
  run_id?: string;
  limit?: number;
  domains?: string[];
  recency_days?: number;
  approval: ToolWorkflowApproval;
};

export type WebSearchResultItem = {
  rank: number;
  title: string;
  url: string;
  display_url: string;
  snippet: string;
  source: string;
};

export type WebSearchResult = {
  artifact_id: string;
  provider: string;
  query: string;
  effective_query: string;
  domains: string[];
  recency_days?: number | null;
  limit: number;
  search_url: string;
  status_code: number;
  fetched_at: number;
  result_count: number;
  results_path: string;
  metadata_path: string;
  source_reliability: string;
  boundary: string;
  results: WebSearchResultItem[];
};

export type WebSearchResponse = ToolWorkflowBaseResponse & {
  web_search: WebSearchResult;
};

export type BrowserScreenshotRequest = {
  url: string;
  phase?: string;
  run_id?: string;
  viewport_width?: number;
  viewport_height?: number;
  full_page?: boolean;
  timeout_ms?: number;
  approval: ToolWorkflowApproval;
};

export type BrowserScreenshotResult = {
  artifact_id: string;
  requested_url: string;
  final_url: string;
  title: string;
  status_code?: number | null;
  viewport: { width: number; height: number };
  full_page: boolean;
  duration_seconds: number;
  screenshot_path: string;
  metadata_path: string;
  artifact_dir: string;
  console_count: number;
  source_reliability: string;
  guardrail?: Record<string, unknown>;
};

export type BrowserScreenshotResponse = ToolWorkflowBaseResponse & {
  browser_result: BrowserScreenshotResult;
};

export type CodeAnalysisRequest = {
  code: string;
  phase?: string;
  run_id?: string;
  timeout_seconds?: number;
  approval: ToolWorkflowApproval;
};

export type CodeAnalysisResponse = ToolWorkflowBaseResponse & {
  analysis_result: {
    status: string;
    stdout: string;
    stderr: string;
    returncode: number;
    duration_seconds: number;
    work_dir: string;
    result_json?: unknown;
    guardrail?: Record<string, unknown>;
  };
};

export type ExperimentBackgroundJobRequest = {
  script_path: string;
  args?: string[];
  phase?: string;
  run_id?: string;
  timeout_seconds?: number;
  approval: ToolWorkflowApproval;
};

export type SshTrainingServer = {
  server_id: string;
  display_name: string;
  ssh_alias: string;
  user: string;
  host: string;
  port: number;
  gpu_summary: string;
  python_version: string;
  node_version: string;
  aliases: string[];
  notes: string;
  source: string;
  credential_boundary: string;
};

export type SshTrainingServersResponse = {
  servers: SshTrainingServer[];
  count: number;
  availability: Record<string, unknown>;
  mcp_server_templates: Record<string, Record<string, unknown>>;
};

export type SshTrainingJobRequest = {
  server_id: string;
  command: string;
  workdir?: string | null;
  phase?: string;
  run_id?: string;
  timeout_seconds?: number;
  approval: ToolWorkflowApproval;
};

export type SshTrainingJobResponse = {
  job: BackgroundJob;
  tool_name: string;
  phase: string;
  availability: Record<string, unknown>;
  policy?: Record<string, unknown>;
  approval: ToolWorkflowApproval;
  guardrail: Record<string, unknown>;
  command_risk?: Record<string, unknown>;
  permission_policy?: CommandPermissionPolicy;
};

export type TerminalCommandJobRequest = {
  command: string;
  workdir?: string | null;
  phase?: string;
  run_id?: string;
  timeout_seconds?: number;
  approval: ToolWorkflowApproval;
};

export type TerminalCommandJobResponse = {
  job: BackgroundJob;
  tool_name: string;
  phase: string;
  availability: Record<string, unknown>;
  terminal: Record<string, unknown>;
  policy?: Record<string, unknown>;
  approval: ToolWorkflowApproval;
  guardrail: Record<string, unknown>;
  command_risk: Record<string, unknown>;
  permission_policy: CommandPermissionPolicy;
};

export type BackgroundJob = {
  job_id: string;
  run_id?: string | null;
  workflow_name: string;
  phase?: string | null;
  status: "queued" | "running" | "complete" | "error" | string;
  arguments: Record<string, unknown>;
  result_ref: Record<string, unknown>;
  error_message?: string | null;
  created_at: number;
  updated_at: number;
};

export type BackgroundJobsResponse = {
  jobs: BackgroundJob[];
  count: number;
  run_id?: string | null;
};

export type WorkItem = {
  work_item_id: string;
  idempotency_key?: string | null;
  run_id?: string | null;
  workflow_name: string;
  phase?: string | null;
  agent_role?: string | null;
  status: "queued" | "leased" | "running" | "retrying" | "blocked" | "complete" | "error" | "cancelled" | string;
  priority: number;
  lease_owner?: string | null;
  lease_expires_at?: number | null;
  attempt_count: number;
  max_attempts: number;
  arguments: Record<string, unknown>;
  result_ref: Record<string, unknown>;
  error_message?: string | null;
  created_at: number;
  updated_at: number;
};

export type WorkerStatus = {
  enabled: boolean;
  auto_start_enabled?: boolean;
  execution_memory?: ExecutionMemoryStatus;
  owner: string;
  concurrency: number;
  lease_seconds: number;
  poll_seconds: number;
  running_count: number;
  queued_count?: number;
  leased_count?: number;
  retrying_count?: number;
  blocked_count?: number;
  complete_count?: number;
  error_count?: number;
  cancelled_count?: number;
  recovered_count?: number;
  last_tick_at?: number | null;
  last_error?: string | null;
};

export type ToolResultResponse = {
  result_id: string;
  run_id?: string | null;
  tool_name: string;
  phase?: string | null;
  result_kind: string;
  summary: string;
  content_size: number;
  created_at: number;
  content?: Record<string, unknown>;
};

export type ResearchTaskStatus = "backlog" | "ready" | "running" | "blocked" | "done" | "archived";

export type ResearchTask = {
  task_id: string;
  run_id?: string | null;
  title: string;
  task_type: string;
  status: ResearchTaskStatus;
  priority: number;
  phase?: string | null;
  target_ref: Record<string, unknown>;
  result_ref: Record<string, unknown>;
  notes: string;
  blocked_reason?: string | null;
  due_at?: number | null;
  created_at: number;
  updated_at: number;
};

export type ResearchTasksResponse = {
  tasks: ResearchTask[];
  count: number;
  run_id?: string | null;
};

export type ResearchSkill = {
  skill_id: string;
  title: string;
  purpose: string;
  phases: string[];
  checklist: string[];
  expected_outputs: string[];
};

export type ResearchSkillsResponse = {
  skills: ResearchSkill[];
  count: number;
  phase?: string | null;
};

export type ResearchScheduleStatus = "active" | "paused" | "archived";

export type ResearchSchedule = {
  schedule_id: string;
  run_id?: string | null;
  title: string;
  workflow_name: string;
  status: ResearchScheduleStatus;
  interval_hours: number;
  phase?: string | null;
  arguments: Record<string, unknown>;
  last_run_at?: number | null;
  next_run_at: number;
  result_ref: Record<string, unknown>;
  created_at: number;
  updated_at: number;
};

export type ResearchSchedulesResponse = {
  schedules: ResearchSchedule[];
  count: number;
  run_id?: string | null;
};

export type ResearchScheduleCreateRequest = {
  title: string;
  workflow_name: string;
  status?: ResearchScheduleStatus;
  interval_hours?: number;
  phase?: string;
  run_id?: string;
  arguments?: Record<string, unknown>;
  next_run_at?: number;
};

export type ResearchScheduleTickResponse = {
  schedule: ResearchSchedule;
  task: ResearchTask;
  approval: ToolWorkflowApproval;
};

export type ResearchDelegationStatus = "planned" | "running" | "completed" | "blocked" | "archived";

export type DelegationAgentBrief = {
  role: string;
  brief: string;
  skill_ids: string[];
  target_ref: Record<string, unknown>;
};

export type ResearchDelegation = {
  delegation_id: string;
  run_id?: string | null;
  title: string;
  phase: string;
  strategy: string;
  status: ResearchDelegationStatus;
  agents: DelegationAgentBrief[];
  target_ref: Record<string, unknown>;
  result_ref: Record<string, unknown>;
  summary: string;
  created_at: number;
  updated_at: number;
};

export type ResearchDelegationsResponse = {
  delegations: ResearchDelegation[];
  count: number;
  run_id?: string | null;
};

export type ResearchDelegationCreateRequest = {
  title: string;
  phase?: string;
  strategy?: string;
  status?: ResearchDelegationStatus;
  run_id?: string;
  agents: DelegationAgentBrief[];
  target_ref?: Record<string, unknown>;
  result_ref?: Record<string, unknown>;
  summary?: string;
};

export type SessionSearchResultType =
  | "run"
  | "hypothesis"
  | "tool_result"
  | "task"
  | "background_job"
  | "schedule"
  | "delegation";

export type SessionSearchResult = {
  type: SessionSearchResultType;
  id: string;
  run_id?: string | null;
  title: string;
  status?: string | null;
  snippet: string;
  updated_at: number;
  target_ref: Record<string, unknown>;
};

export type SessionSearchResponse = {
  query: string;
  run_id?: string | null;
  types?: SessionSearchResultType[] | null;
  count: number;
  results: SessionSearchResult[];
};

export type AppCopy = {
  productKicker: string;
  railSubtitle: string;
  runState: Record<RunStatus | "idle", string>;
  home: {
    title: string;
    description: string;
    activeTasks: string;
    recentResearch: string;
    recentOutputs: string;
    startNew: string;
    emptyProjects: string;
  };
  projects: {
    title: string;
    description: string;
    empty: string;
    continueLabel: string;
  };
  library: {
    title: string;
    description: string;
    papers: string;
    references: string;
    empty: string;
  };
  workspace: {
    title: string;
    description: string;
    taskTitle: string;
    taskDescription: string;
    runButtonIdle: string;
    runButtonRepeat: string;
    runButtonBusy: string;
    auditOpen: string;
    auditClose: string;
    outputsEmpty: string;
  };
  outputs: {
    title: string;
    description: string;
    empty: string;
  };
  settings: {
    title: string;
    description: string;
    expertSettings: string;
    refresh: string;
    clearRun: string;
    currentMode: string;
    localWorkflow: string;
    liveWorkflow: string;
    literatureWorkflow: string;
    currentProvider: string;
    runReadiness: string;
    blockedReason: string;
    nextAction: string;
  };
  workflow: {
    localMode: string;
    liveMode: string;
    readyDetail: string;
    runBlocked: string;
    requestFailed: string;
    pollFailed: string;
    runFailed: string;
    stageNeedsAttention: string;
    stageNeedsAttentionDesc: string;
  };
  details: {
    noGrounding: string;
    noExperiment: string;
    noPlan: string;
    noHypothesis: string;
    selectCompleted: string;
    summaryEmpty: string;
    sourceUnknown: string;
    planSummary: string;
    literatureGrounding: string;
    citationMap: string;
    experiment: string;
    tournamentEmpty: string;
    metricsEmpty: string;
    agentsEmpty: string;
    hypothesesCount: string;
    averageScore: string;
    tournamentRounds: string;
    groundedSources: string;
    matchLabel: (index: number) => string;
    confidence: (value: number) => string;
  };
};
