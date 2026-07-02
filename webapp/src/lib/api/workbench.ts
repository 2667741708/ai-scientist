import type {
  AgentRegistryResponse,
  BackgroundJob,
  BackgroundJobsResponse,
  BrowserScreenshotRequest,
  BrowserScreenshotResponse,
  CodeAnalysisRequest,
  CodeAnalysisResponse,
  CommandPermissionMode,
  CommandPermissionResponse,
  ContinueRunRequest,
  ExperimentBackgroundJobRequest,
  FeedbackItem,
  FileSnapshotRequest,
  FileSnapshotResponse,
  Health,
  KnowledgePapersResponse,
  LiteratureCitationRequest,
  LiteratureCitationResponse,
  LiteratureDiscoveryRequest,
  LiteratureDiscoveryResponse,
  LiteratureLibrariesResponse,
  LiteratureLibraryCreateRequest,
  LiteratureServiceStartResponse,
  PaperIngestRequest,
  PaperIngestResponse,
  PaperInterpretRequest,
  PaperInterpretResponse,
  PaperParseStatusResponse,
  PaperParseRun,
  PaperParseRunsResponse,
  RagSearchResponse,
  PdfParseRequest,
  PdfParseResponse,
  ResearchDelegationCreateRequest,
  ResearchDelegationsResponse,
  ResearchScheduleCreateRequest,
  ResearchSchedulesResponse,
  ResearchScheduleTickResponse,
  ResearchSkillsResponse,
  ResearchTasksResponse,
  RunRecord,
  RunRequest,
  SessionSearchResponse,
  SessionSearchResultType,
  SshTrainingJobRequest,
  SshTrainingJobResponse,
  SshTrainingServersResponse,
  TerminalCommandJobRequest,
  TerminalCommandJobResponse,
  ToolResultResponse,
  TranslationRequest,
  TranslationResponse,
  WebExtractRequest,
  WebExtractResponse,
  WebSearchRequest,
  WebSearchResponse,
  WorkerStatus,
} from "../../types/workbench";
import { parseApiError } from "../formatters/workbench";
import { authHeaders } from "./auth";
import { getApiBase } from "./client";

export async function fetchHealth() {
  const response = await fetch(`${getApiBase()}/api/health`);
  if (!response.ok) throw new Error(`health_failed_${response.status}`);
  return (await response.json()) as Health;
}

export async function fetchAgentRegistry() {
  const response = await fetch(`${getApiBase()}/api/agents/registry`);
  if (!response.ok) throw new Error(`agent_registry_failed_${response.status}`);
  return (await response.json()) as AgentRegistryResponse;
}

export async function startLiteratureService() {
  const response = await fetch(`${getApiBase()}/api/literature-service/start`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(parseApiError(body));
  }
  return (await response.json()) as LiteratureServiceStartResponse;
}

export async function createRun(request: RunRequest) {
  const response = await fetch(`${getApiBase()}/api/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(parseApiError(body));
  }
  return (await response.json()) as { run_id: string; work_item_id?: string };
}

export async function continueRun(runId: string, request: ContinueRunRequest) {
  return postJson<{ run_id: string; work_item_id?: string; parent_run_id: string }>(
    `/api/runs/${encodeURIComponent(runId)}/continue`,
    request,
  );
}

export async function fetchRun(runId: string) {
  const response = await fetch(`${getApiBase()}/api/runs/${runId}`);
  if (!response.ok) throw new Error(`run_fetch_failed_${response.status}`);
  return (await response.json()) as RunRecord;
}

export async function postRunFeedback(runId: string, feedback: FeedbackItem) {
  return postJson<{ feedback: FeedbackItem }>(`/api/runs/${encodeURIComponent(runId)}/feedback`, feedback);
}

export async function listRunFeedback(runId: string, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  const response = await fetch(`${getApiBase()}/api/runs/${encodeURIComponent(runId)}/feedback?${params.toString()}`);
  if (!response.ok) throw new Error(`run_feedback_failed_${response.status}`);
  return (await response.json()) as { feedback: FeedbackItem[]; count: number; run_id: string };
}

export async function fetchRunMemory(runId: string) {
  const response = await fetch(`${getApiBase()}/api/runs/${encodeURIComponent(runId)}/memory`);
  if (!response.ok) throw new Error(`run_memory_failed_${response.status}`);
  return (await response.json()) as { run_id: string; memory: Record<string, unknown> };
}

export async function fetchWorkerStatus() {
  const response = await fetch(`${getApiBase()}/api/worker/status`);
  if (!response.ok) throw new Error(`worker_status_failed_${response.status}`);
  return (await response.json()) as WorkerStatus;
}

export async function tickWorker() {
  return postJson<WorkerStatus>("/api/worker/tick", {});
}

function coerceRunSummaryToRecord(summary: Partial<RunRecord> & { run_id: string }): RunRecord {
  return {
    run_id: summary.run_id,
    status: summary.status ?? "error",
    request: summary.request ?? {
      research_goal: "历史研究记录",
      model_name: "unknown",
      demo_mode: false,
      literature_review: false,
      initial_hypotheses: 0,
      iterations: 0,
      min_references: 0,
      max_references: 0,
    },
    timeline: summary.timeline ?? [],
    hypotheses: summary.hypotheses ?? [],
    research_plan: summary.research_plan ?? {},
    agent_trace: summary.agent_trace ?? [],
    tournament_matchups: summary.tournament_matchups ?? [],
    metrics: summary.metrics ?? {},
    safety_gate: summary.safety_gate ?? {},
    citation_provenance_qa: summary.citation_provenance_qa ?? {},
    expert_feedback: summary.expert_feedback ?? {},
    error: summary.error,
  };
}

export async function fetchRunHistory(limit = 8) {
  const response = await fetch(`${getApiBase()}/api/runs?limit=${limit}`);
  if (!response.ok) throw new Error(`runs_fetch_failed_${response.status}`);
  const payload = (await response.json()) as { runs?: Array<Partial<RunRecord> & { run_id: string }> };
  const summaries = (payload.runs ?? []).slice(0, limit).filter((item) => item.run_id);
  const detailed = await Promise.allSettled(summaries.map((item) => fetchRun(item.run_id)));
  return detailed.map((item, index) => (
    item.status === "fulfilled" ? item.value : coerceRunSummaryToRecord(summaries[index])
  ));
}

export async function translateHypothesis(request: TranslationRequest) {
  const response = await fetch(`${getApiBase()}/api/hypotheses/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(parseApiError(body));
  }
  return (await response.json()) as TranslationResponse;
}

export async function ingestKnowledgePaper(request: PaperIngestRequest) {
  const response = await fetch(`${getApiBase()}/api/knowledge/papers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...request, source: request.source ?? "user_upload" }),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(parseApiError(body));
  }
  return (await response.json()) as PaperIngestResponse;
}

export async function parseKnowledgePdf(request: PdfParseRequest) {
  const response = await fetch(`${getApiBase()}/api/knowledge/pdf/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...request,
      fetch_metadata: request.fetch_metadata ?? true,
      ingest_to_knowledge_base: request.ingest_to_knowledge_base ?? true,
    }),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(parseApiError(body));
  }
  return (await response.json()) as PdfParseResponse;
}

export async function uploadParseKnowledgePdf(file: File, libraryId?: string) {
  const body = new FormData();
  body.append("file", file);
  body.append("fetch_metadata", "true");
  body.append("ingest_to_knowledge_base", "true");
  const params = new URLSearchParams();
  if (libraryId) params.set("library_id", libraryId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${getApiBase()}/api/knowledge/pdf/upload-parse${suffix}`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(parseApiError(errorBody));
  }
  return (await response.json()) as PdfParseResponse;
}

export async function listKnowledgePapers({ library_id }: { library_id?: string } = {}) {
  const params = new URLSearchParams();
  if (library_id) params.set("library_id", library_id);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${getApiBase()}/api/knowledge/papers${suffix}`);
  if (!response.ok) throw new Error(`knowledge_papers_failed_${response.status}`);
  return (await response.json()) as KnowledgePapersResponse;
}

export async function listPaperParseRuns({ library_id }: { library_id?: string } = {}) {
  const params = new URLSearchParams();
  if (library_id) params.set("library_id", library_id);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${getApiBase()}/api/knowledge/parse-runs${suffix}`);
  if (!response.ok) throw new Error(`parse_runs_failed_${response.status}`);
  return (await response.json()) as PaperParseRunsResponse;
}

export async function fetchPaperParseRun(parseRunId: string) {
  const response = await fetch(`${getApiBase()}/api/knowledge/parse-runs/${parseRunId}`);
  if (!response.ok) throw new Error(`parse_run_failed_${response.status}`);
  return (await response.json()) as PaperParseRun;
}

export async function fetchPaperParseStatus(paperId: string) {
  const response = await fetch(`${getApiBase()}/api/papers/${encodeURIComponent(paperId)}/parse-status`);
  if (!response.ok) throw new Error(`paper_parse_status_failed_${response.status}`);
  return (await response.json()) as PaperParseStatusResponse;
}

export async function searchRagEvidence({
  q,
  paper_id,
  library_id,
  parse_item_key,
  support_level,
  limit = 8,
}: {
  q: string;
  paper_id?: string;
  library_id?: string;
  parse_item_key?: string;
  support_level?: string;
  limit?: number;
}) {
  const params = new URLSearchParams({ q, limit: String(limit) });
  if (paper_id) params.set("paper_id", paper_id);
  if (library_id) params.set("library_id", library_id);
  if (parse_item_key) params.set("parse_item_key", parse_item_key);
  if (support_level) params.set("support_level", support_level);
  const response = await fetch(`${getApiBase()}/api/knowledge/rag/search?${params.toString()}`);
  if (!response.ok) throw new Error(`rag_search_failed_${response.status}`);
  return (await response.json()) as RagSearchResponse;
}

export async function listLiteratureLibraries() {
  const response = await fetch(`${getApiBase()}/api/literature-libraries`);
  if (!response.ok) throw new Error(`literature_libraries_failed_${response.status}`);
  return (await response.json()) as LiteratureLibrariesResponse;
}

export async function createLiteratureLibrary(request: LiteratureLibraryCreateRequest) {
  return postJson<{ library: LiteratureLibrariesResponse["libraries"][number] }>("/api/literature-libraries", request);
}

export async function discoverLiteraturePapers(request: LiteratureDiscoveryRequest) {
  return postJson<LiteratureDiscoveryResponse>("/api/literature-libraries/discover", request);
}

export async function fetchLiteratureCitationBibtex(request: LiteratureCitationRequest) {
  return postJson<LiteratureCitationResponse>("/api/literature-citations/bibtex", request);
}

async function postJson<TResponse>(path: string, payload: unknown, method: "POST" | "PUT" = "POST") {
  const response = await fetch(`${getApiBase()}${path}`, {
    method,
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(parseApiError(body));
  }
  return (await response.json()) as TResponse;
}

export async function searchResearchSessions({
  q,
  run_id,
  types,
  limit = 20,
}: {
  q: string;
  run_id?: string;
  types?: SessionSearchResultType[];
  limit?: number;
}) {
  const params = new URLSearchParams({ q, limit: String(limit) });
  if (run_id) params.set("run_id", run_id);
  if (types?.length) params.set("types", types.join(","));
  const response = await fetch(`${getApiBase()}/api/session-search?${params.toString()}`);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(parseApiError(body));
  }
  return (await response.json()) as SessionSearchResponse;
}

export async function listResearchTasks({
  run_id,
  status,
  task_type,
  limit = 50,
}: {
  run_id?: string;
  status?: string;
  task_type?: string;
  limit?: number;
} = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (run_id) params.set("run_id", run_id);
  if (status) params.set("status", status);
  if (task_type) params.set("task_type", task_type);
  const response = await fetch(`${getApiBase()}/api/research-tasks?${params.toString()}`);
  if (!response.ok) throw new Error(`research_tasks_failed_${response.status}`);
  return (await response.json()) as ResearchTasksResponse;
}

export async function listResearchSkills({ phase }: { phase?: string } = {}) {
  const params = new URLSearchParams();
  if (phase) params.set("phase", phase);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${getApiBase()}/api/research-skills${suffix}`);
  if (!response.ok) throw new Error(`research_skills_failed_${response.status}`);
  return (await response.json()) as ResearchSkillsResponse;
}

export async function listResearchSchedules({
  run_id,
  status,
  workflow_name,
  limit = 20,
}: {
  run_id?: string;
  status?: string;
  workflow_name?: string;
  limit?: number;
} = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (run_id) params.set("run_id", run_id);
  if (status) params.set("status", status);
  if (workflow_name) params.set("workflow_name", workflow_name);
  const response = await fetch(`${getApiBase()}/api/research-schedules?${params.toString()}`);
  if (!response.ok) throw new Error(`research_schedules_failed_${response.status}`);
  return (await response.json()) as ResearchSchedulesResponse;
}

export async function createResearchSchedule(request: ResearchScheduleCreateRequest) {
  return postJson<{ schedule: ResearchSchedulesResponse["schedules"][number] }>("/api/research-schedules", request);
}

export async function tickResearchSchedule(scheduleId: string, request: { approval: { confirmed: boolean; scope: string; reason?: string }; force?: boolean }) {
  return postJson<ResearchScheduleTickResponse>(`/api/research-schedules/${encodeURIComponent(scheduleId)}/tick`, request);
}

export async function listResearchDelegations({
  run_id,
  status,
  strategy,
  limit = 20,
}: {
  run_id?: string;
  status?: string;
  strategy?: string;
  limit?: number;
} = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (run_id) params.set("run_id", run_id);
  if (status) params.set("status", status);
  if (strategy) params.set("strategy", strategy);
  const response = await fetch(`${getApiBase()}/api/research-delegations?${params.toString()}`);
  if (!response.ok) throw new Error(`research_delegations_failed_${response.status}`);
  return (await response.json()) as ResearchDelegationsResponse;
}

export async function createResearchDelegation(request: ResearchDelegationCreateRequest) {
  return postJson<{ delegation: ResearchDelegationsResponse["delegations"][number] }>("/api/research-delegations", request);
}

export async function listBackgroundJobs({
  run_id,
  limit = 20,
}: {
  run_id?: string;
  limit?: number;
} = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (run_id) params.set("run_id", run_id);
  const response = await fetch(`${getApiBase()}/api/tools/background-jobs?${params.toString()}`);
  if (!response.ok) throw new Error(`background_jobs_failed_${response.status}`);
  return (await response.json()) as BackgroundJobsResponse;
}

export async function fetchBackgroundJob(jobId: string) {
  const response = await fetch(`${getApiBase()}/api/tools/background-jobs/${encodeURIComponent(jobId)}`);
  if (!response.ok) throw new Error(`background_job_failed_${response.status}`);
  return (await response.json()) as BackgroundJob;
}

export async function fetchToolResult(resultId: string) {
  const response = await fetch(`${getApiBase()}/api/tools/results/${encodeURIComponent(resultId)}`);
  if (!response.ok) throw new Error(`tool_result_failed_${response.status}`);
  return (await response.json()) as ToolResultResponse;
}

export async function getCommandPermissions() {
  const response = await fetch(`${getApiBase()}/api/tools/command-permissions`);
  if (!response.ok) throw new Error(`command_permissions_failed_${response.status}`);
  return (await response.json()) as CommandPermissionResponse;
}

export async function updateCommandPermissions(mode: CommandPermissionMode) {
  return postJson<CommandPermissionResponse>("/api/tools/command-permissions", { mode }, "PUT");
}

export async function executeFileSnapshotWorkflow(request: FileSnapshotRequest) {
  return postJson<FileSnapshotResponse>("/api/tools/workflows/file-snapshot", request);
}

export async function executeWebExtractWorkflow(request: WebExtractRequest) {
  return postJson<WebExtractResponse>("/api/tools/workflows/web-extract", {
    ...request,
    ingest_to_knowledge_base: request.ingest_to_knowledge_base ?? true,
  });
}

export async function executeWebSearchWorkflow(request: WebSearchRequest) {
  return postJson<WebSearchResponse>("/api/tools/workflows/web-search", request);
}

export async function enqueueWebExtractWorkflow(request: WebExtractRequest) {
  return postJson<{ job: BackgroundJob }>("/api/tools/workflows/web-extract/background", {
    ...request,
    ingest_to_knowledge_base: request.ingest_to_knowledge_base ?? true,
  });
}

export async function executeBrowserScreenshotWorkflow(request: BrowserScreenshotRequest) {
  return postJson<BrowserScreenshotResponse>("/api/tools/workflows/browser-screenshot", request);
}

export async function executeCodeAnalysisWorkflow(request: CodeAnalysisRequest) {
  return postJson<CodeAnalysisResponse>("/api/tools/workflows/code-analysis", request);
}

export async function enqueueExperimentBackgroundJob(request: ExperimentBackgroundJobRequest) {
  return postJson<{ job: BackgroundJob }>("/api/tools/workflows/experiment-job", request);
}

export async function enqueueTerminalCommandJob(request: TerminalCommandJobRequest) {
  return postJson<TerminalCommandJobResponse>("/api/tools/workflows/terminal-command", request);
}

export async function listSshTrainingServers() {
  const response = await fetch(`${getApiBase()}/api/tools/ssh/servers`);
  if (!response.ok) throw new Error(`ssh_training_servers_failed_${response.status}`);
  return (await response.json()) as SshTrainingServersResponse;
}

export async function enqueueSshTrainingJob(request: SshTrainingJobRequest) {
  return postJson<SshTrainingJobResponse>("/api/tools/workflows/ssh-training-job", request);
}

export async function interpretPaper(request: PaperInterpretRequest) {
  const response = await fetch(`${getApiBase()}/api/papers/interpret`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...request,
      model_name: request.model_name ?? "deepseek/deepseek-v4-pro",
      fetch_metadata: request.fetch_metadata ?? true,
    }),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(parseApiError(body));
  }
  return (await response.json()) as PaperInterpretResponse;
}
