import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FileText,
  Loader2,
  MessageSquareText,
  Play,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Trophy,
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { MarkdownText } from "../../components/content/MarkdownText";
import { fetchBackgroundJob, fetchRun, fetchToolResult } from "../../lib/api/workbench";
import {
  cancelResearchChatAction,
  confirmResearchChatAction,
  fetchResearchChatCapabilities,
  sendResearchChatTurn,
} from "../../lib/api/researchChat";
import { classNames, formatBackendText, formatRunState, formatStageLabel, getTimelineDetail } from "../../lib/formatters/workbench";
import type { BackgroundJob, DetailTab, RunRecord, TimelineEvent, ToolResultResponse } from "../../types/workbench";
import type {
  ResearchChatActionProposal,
  ResearchChatAssistantMessage,
  ResearchChatCapability,
  ResearchChatResult,
  ResearchChatState,
} from "../../types/research-chat";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  assistant?: ResearchChatAssistantMessage;
};

type ResearchCommandCenterProps = {
  record: RunRecord | null;
  selectedIndex: number;
  modelName: string;
  literatureReview: boolean;
  demoMode: boolean;
  initialHypotheses: number;
  iterations: number;
  minReferences: number;
  maxReferences: number;
  isBusy: boolean;
  onOpenRun: (record: RunRecord) => void;
  onSelectHypothesis: (index: number) => void;
  onSetDetailTab: (tab: "overview" | "agents" | "hypotheses" | "evidence" | "tournament" | "metrics") => void;
  expertComposer: ReactNode;
};

const starterPrompts = [
  "这个项目现在能做什么？",
  "研究目标：为 VLA 模型设计可证伪的多模态任务泛化假设",
  "执行本地命令：git status --short",
  "在 c201-5080 执行命令：hostname",
  "联网搜索：open-coscientist github",
  "检验这个假设是否正确：VLA token 序列可以通过层级动作语法稳定转换为机器臂可执行动作",
  "解释当前 Elo 锦标赛排名，展示 winner/loser 和 before/after Elo",
  "检查第 1 个假设的证据边界",
  "帮我解析 D:\\papers\\paper.pdf 并加入知识库",
];

function makeId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function promptForCapability(capability: Pick<ResearchChatCapability, "intent" | "userSummary">) {
  switch (capability.intent) {
    case "discover_capabilities":
      return starterPrompts[0];
    case "start_research_run":
      return starterPrompts[1];
    case "run_terminal_command":
      return starterPrompts[2];
    case "run_ssh_training_command":
      return starterPrompts[3];
    case "search_public_web":
      return starterPrompts[4];
    case "verify_evidence_with_literature":
      return starterPrompts[5];
    case "explain_ranking":
      return starterPrompts[6];
    case "inspect_hypothesis":
      return starterPrompts[7];
    case "parse_pdf_to_knowledge_base":
      return starterPrompts[8];
    case "extract_web_evidence":
      return "把这个网页保存为证据：https://example.org/article";
    case "search_knowledge_evidence":
      return "搜索知识库证据：";
    case "design_experiment":
      return "为第 1 个假设生成可证伪实验设计";
    case "draft_report":
      return "把当前研究结果整理成报告草稿结构";
    default:
      return capability.userSummary;
  }
}

function isResearchChatCapability(item: unknown): item is ResearchChatCapability {
  return Boolean(item && typeof item === "object" && "intent" in item && typeof (item as { intent?: unknown }).intent === "string");
}

const workflowProgressSteps = [
  { key: "supervisor", label: "规划", matches: ["supervisor", "planning"] },
  { key: "literature", label: "文献", matches: ["literature", "mcp", "evidence"] },
  { key: "generation", label: "生成", matches: ["generation", "generate", "generator", "hypothesis"] },
  { key: "review", label: "评审", matches: ["review", "reviewer", "reflection", "critique"] },
  { key: "tournament", label: "排序", matches: ["tournament", "rank", "ranker", "elo"] },
  { key: "evolution", label: "收敛", matches: ["meta review", "evolve", "evolution", "proximity", "metrics"] },
  { key: "complete", label: "完成", matches: ["complete", "final"] },
];

function normalizedTimelineText(event: TimelineEvent) {
  return `${event.stage} ${event.event} ${event.details}`.toLowerCase();
}

function findProgressStepIndex(event: TimelineEvent | undefined) {
  if (!event) return -1;
  const text = normalizedTimelineText(event);
  return workflowProgressSteps.findIndex((step) => step.matches.some((match) => text.includes(match)));
}

function latestTimelineEvent(record: RunRecord): TimelineEvent | undefined {
  return record.timeline[record.timeline.length - 1];
}

function extractProgressPercent(record: RunRecord, activeIndex: number) {
  const latest = latestTimelineEvent(record);
  const progressMatch = latest?.details?.match(/Progress\s+([0-9]+(?:\.[0-9]+)?)%/i);
  const backendProgress = progressMatch ? Number(progressMatch[1]) : null;
  const stepEstimate =
    record.status === "complete"
      ? 100
      : record.status === "queued"
        ? 4
        : Math.round((Math.max(activeIndex, 0) / Math.max(workflowProgressSteps.length - 1, 1)) * 100);
  const merged = Math.max(Number.isFinite(backendProgress ?? NaN) ? Number(backendProgress) : 0, stepEstimate);
  if (record.status === "complete") return 100;
  if (record.status === "error") return Math.max(merged, 8);
  return Math.min(Math.max(merged, 4), 96);
}

function getCurrentRunProgress(record: RunRecord) {
  const latest = latestTimelineEvent(record);
  const activeEvent =
    [...record.timeline].reverse().find((event) => event.status === "active") ?? latest;
  const explicitCompleted = record.timeline
    .filter((event) => event.status === "complete" || /complete|completed|finalized/i.test(`${event.stage} ${event.event}`))
    .map((event) => findProgressStepIndex(event))
    .filter((index) => index >= 0);
  const maxCompletedIndex = explicitCompleted.length ? Math.max(...explicitCompleted) : -1;
  const eventIndex = findProgressStepIndex(activeEvent);
  const activeIndex =
    record.status === "complete"
      ? workflowProgressSteps.length - 1
      : record.status === "queued"
        ? 0
        : Math.max(eventIndex, Math.min(maxCompletedIndex + 1, workflowProgressSteps.length - 1), 0);
  const percent = extractProgressPercent(record, activeIndex);
  const phaseLabel =
    record.status === "queued"
      ? "等待进入执行队列"
      : record.status === "complete"
        ? "研究运行已完成"
        : record.status === "error"
          ? "运行停止，需要检查"
          : activeEvent
            ? formatStageLabel(activeEvent.stage)
            : "正在启动";
  const eventLabel = activeEvent ? formatBackendText(activeEvent.event) : "等待第一个过程事件";
  const detail = activeEvent ? getTimelineDetail(activeEvent) : "后端创建运行后会写入 timeline。";
  return { activeIndex, percent, phaseLabel, eventLabel, detail, latestTime: activeEvent?.time ?? "" };
}

function inferResultActionTab(action: string): DetailTab | null {
  const normalized = action.toLowerCase();
  if (normalized.includes("timeline") || normalized.includes("过程") || normalized.includes("trace")) return "agents";
  if (normalized.includes("elo") || normalized.includes("排名") || normalized.includes("排序")) return "tournament";
  if (normalized.includes("证据") || normalized.includes("evidence")) return "evidence";
  if (normalized.includes("假设") || normalized.includes("hypothesis")) return "hypotheses";
  return null;
}

export function ResearchCommandCenter({
  record,
  selectedIndex,
  modelName,
  literatureReview,
  demoMode,
  initialHypotheses,
  iterations,
  minReferences,
  maxReferences,
  isBusy,
  onOpenRun,
  onSelectHypothesis,
  onSetDetailTab,
  expertComposer,
}: ResearchCommandCenterProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [input, setInput] = useState("");
  const [state, setState] = useState<ResearchChatState>("idle");
  const [activeLibraryId, setActiveLibraryId] = useState<string | null>(() => window.localStorage.getItem("coscientist.activeLibraryId"));
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "你可以像使用 ChatGPT 一样描述研究目标、询问功能、审计 Elo 排名、检查假设证据，或请求解析 PDF/网页证据。写入型和外部工具动作会先给确认卡。",
      assistant: {
        kind: "status",
        text: "你可以像使用 ChatGPT 一样描述研究目标、询问功能、审计 Elo 排名、检查假设证据，或请求解析 PDF/网页证据。写入型和外部工具动作会先给确认卡。",
      },
    },
  ]);
  const [capabilities, setCapabilities] = useState<ResearchChatCapability[]>([]);
  const [executingActionId, setExecutingActionId] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    void fetchResearchChatCapabilities()
      .then((response) => setCapabilities(response.capabilities))
      .catch(() => setCapabilities([]));
  }, []);

  useEffect(() => {
    const refreshActiveLibrary = () => setActiveLibraryId(window.localStorage.getItem("coscientist.activeLibraryId"));
    window.addEventListener("storage", refreshActiveLibrary);
    window.addEventListener("focus", refreshActiveLibrary);
    refreshActiveLibrary();
    return () => {
      window.removeEventListener("storage", refreshActiveLibrary);
      window.removeEventListener("focus", refreshActiveLibrary);
    };
  }, []);

  useEffect(() => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, state]);

  const context = useMemo(
    () => ({
      page: location.pathname,
      page_path: location.pathname,
      mode: "workspace" as const,
      run_id: record?.run_id ?? null,
      library_id: activeLibraryId,
      selected_hypothesis_index: selectedIndex,
      model_name: modelName,
      literature_review: literatureReview,
      demo_mode: demoMode,
      initial_hypotheses: initialHypotheses,
      iterations,
      min_references: minReferences,
      max_references: maxReferences,
      language: "zh" as const,
    }),
    [
      demoMode,
      initialHypotheses,
      iterations,
      literatureReview,
      location.pathname,
      maxReferences,
      minReferences,
      modelName,
      record?.run_id,
      selectedIndex,
      activeLibraryId,
    ],
  );

  const appendAssistant = (assistant: ResearchChatAssistantMessage) => {
    setMessages((items) => [...items, { id: makeId("assistant"), role: "assistant", text: assistant.text, assistant }]);
    if (assistant.result?.intent === "explain_ranking") onSetDetailTab("tournament");
    if (assistant.result?.intent === "inspect_hypothesis") {
      onSetDetailTab("hypotheses");
      if (typeof assistant.result.hypothesisIndex === "number") onSelectHypothesis(assistant.result.hypothesisIndex);
    }
    if (assistant.result?.intent === "search_knowledge_evidence" || assistant.result?.intent === "check_hypothesis_grounding") {
      onSetDetailTab("evidence");
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = input.trim();
    if (!message || state === "routing" || state === "executing") return;
    setInput("");
    setMessages((items) => [...items, { id: makeId("user"), role: "user", text: message }]);
    setState("routing");
    try {
      const response = await sendResearchChatTurn({ session_id: sessionId, message, context });
      setSessionId(response.session_id);
      appendAssistant(response.assistant_message);
      setState(response.state);
    } catch {
      appendAssistant({ kind: "error", text: "研究助手暂时不可用，请确认后端服务正在运行后再试。" });
      setState("error");
    }
  };

  const handleConfirm = async (proposal: ResearchChatActionProposal) => {
    if (!proposal.approvalScope) return;
    setExecutingActionId(proposal.actionId);
    setState("executing");
    try {
      const response = await confirmResearchChatAction(proposal.actionId, {
        approval: {
          confirmed: true,
          scope: proposal.approvalScope,
          reason: "User confirmed chat-first research workbench action.",
        },
      });
      setSessionId(response.session_id);
      appendAssistant(response.assistant_message);
      setState(response.state);
      const runId = response.assistant_message.result?.runId;
      if (runId) {
        navigate(`/workspace/${encodeURIComponent(runId)}`);
        if (proposal.executionTarget === "workflow.start_run") onSetDetailTab("agents");
        try {
          const run = await fetchRun(runId);
          onOpenRun(run);
        } catch {
          // The route-level query will keep polling; avoid turning a launched run into a visible error.
        }
      }
    } catch {
      appendAssistant({ kind: "error", text: "任务未能执行。请检查输入、模型 key、文献服务或运行准备状态后重试。" });
      setState("error");
    } finally {
      setExecutingActionId(null);
    }
  };

  const handleCancel = async (proposal: ResearchChatActionProposal) => {
    setExecutingActionId(proposal.actionId);
    try {
      const response = await cancelResearchChatAction(proposal.actionId);
      appendAssistant(response.assistant_message);
      setState(response.state);
    } catch {
      appendAssistant({ kind: "status", text: "已取消当前确认卡片。" });
      setState("idle");
    } finally {
      setExecutingActionId(null);
    }
  };

  const busy = state === "routing" || state === "executing";

  return (
    <section className="research-command-center" aria-label="对话式研究工作台">
      <div className="command-center-header">
        <div className="section-title">
          <MessageSquareText size={18} />
          <h2>对话式研究工作台</h2>
        </div>
        <p>用研究目标驱动假设生成；结果、证据和排序依据在右侧结构化面板审查。</p>
        <div className="command-status-row" aria-label="当前研究状态">
          <span className={classNames("status-chip", record?.status === "complete" && "ok", record?.status === "error" && "error")}>
            {record ? formatRunState(record.status) : "未启动"}
          </span>
          <span>{record ? `${record.hypotheses.length} 条假设` : "先输入研究目标"}</span>
          <span>{record?.tournament_matchups.length ?? 0} 场 Elo 比较</span>
        </div>
        {record ? (
          <ActiveRunProgress
            record={record}
            onOpenTimeline={() => onSetDetailTab("agents")}
            onOpenRanking={() => onSetDetailTab("tournament")}
          />
        ) : null}
      </div>

      <div className="command-chat-messages" ref={messagesRef} aria-live="polite">
        {messages.map((message) => (
          <CommandChatBubble
            key={message.id}
            message={message}
            record={record}
            executingActionId={executingActionId}
            onConfirm={handleConfirm}
            onCancel={handleCancel}
            onSetDetailTab={onSetDetailTab}
          />
        ))}
        {state === "routing" ? (
          <article className="chat-bubble assistant" role="status" aria-busy="true">
            <Loader2 size={16} className="spin" />
            <p>正在理解你的研究任务...</p>
          </article>
        ) : null}
      </div>

      <CapabilitySuggestions
        capabilities={capabilities}
        onPick={(value) => {
          setInput(value);
          inputRef.current?.focus();
        }}
      />

      <form className="research-chat-composer command-composer" onSubmit={handleSubmit}>
        <label htmlFor="command-center-input">输入研究目标、功能问题或审计请求</label>
        <textarea
          ref={inputRef}
          id="command-center-input"
          value={input}
          rows={4}
          maxLength={4000}
          placeholder="例如：研究目标：为某机制生成可证伪假设，并使用已入库文献作为证据"
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <div className="research-chat-composer-actions">
          <span>{state === "awaiting_confirmation" ? "请先处理确认卡片，或继续补充上下文。" : "Enter 发送，Shift+Enter 换行。"}</span>
          <button className={classNames("button-primary", busy && "is-loading")} type="submit" disabled={!input.trim() || busy || isBusy} aria-busy={busy}>
            {busy ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
            {busy ? "处理中" : "发送"}
          </button>
        </div>
      </form>

      <details className="command-expert-disclosure">
        <summary>专家设置与表单启动</summary>
        {expertComposer}
      </details>
    </section>
  );
}

function CapabilitySuggestions({ capabilities, onPick }: { capabilities: ResearchChatCapability[]; onPick: (value: string) => void }) {
  const preferredOrder = [
    "discover_capabilities",
    "start_research_run",
    "run_terminal_command",
    "run_ssh_training_command",
    "search_public_web",
    "verify_evidence_with_literature",
    "search_knowledge_evidence",
    "explain_ranking",
    "inspect_hypothesis",
    "parse_pdf_to_knowledge_base",
  ];
  const fallback = starterPrompts.map((prompt) => ({ userTitle: prompt, userSummary: prompt }));
  const items = capabilities.length
    ? [...capabilities]
        .sort((a, b) => {
          const aIndex = preferredOrder.indexOf(a.intent);
          const bIndex = preferredOrder.indexOf(b.intent);
          return (aIndex === -1 ? preferredOrder.length : aIndex) - (bIndex === -1 ? preferredOrder.length : bIndex);
        })
        .slice(0, 5)
    : fallback;
  return (
    <div className="research-chat-suggestions command-suggestions" aria-label="常用研究任务">
      {items.map((item) => (
        <button
          type="button"
          key={item.userTitle}
          onClick={() => onPick(isResearchChatCapability(item) ? promptForCapability(item) : item.userSummary)}
        >
          <Sparkles size={14} />
          <span>{item.userTitle}</span>
        </button>
      ))}
    </div>
  );
}

function CommandChatBubble({
  message,
  record,
  executingActionId,
  onConfirm,
  onCancel,
  onSetDetailTab,
}: {
  message: ChatMessage;
  record: RunRecord | null;
  executingActionId: string | null;
  onConfirm: (proposal: ResearchChatActionProposal) => void;
  onCancel: (proposal: ResearchChatActionProposal) => void;
  onSetDetailTab: (tab: DetailTab) => void;
}) {
  if (message.role === "user") {
    return (
      <article className="chat-bubble user">
        <p>{message.text}</p>
      </article>
    );
  }
  const assistant = message.assistant;
  return (
    <article className={classNames("chat-bubble assistant", assistant?.kind === "error" && "error")}>
      {assistant?.kind === "error" ? <AlertTriangle size={16} /> : <Sparkles size={16} />}
      <div className="chat-bubble-content">
        <MarkdownText text={message.text} />
        {assistant?.proposal ? (
          <ActionProposalCard
            proposal={assistant.proposal}
            busy={executingActionId === assistant.proposal.actionId}
            onConfirm={onConfirm}
            onCancel={onCancel}
          />
        ) : null}
        {assistant?.result ? <CommandResultCard result={assistant.result} record={record} onSetDetailTab={onSetDetailTab} /> : null}
        {assistant?.suggestions?.length ? (
          <div className="chat-inline-options">
            {assistant.suggestions.slice(0, 5).map((item) => (
              <span key={item.id}>{item.userTitle}</span>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function ActiveRunProgress({
  record,
  onOpenTimeline,
  onOpenRanking,
  compact = false,
}: {
  record: RunRecord;
  onOpenTimeline: () => void;
  onOpenRanking: () => void;
  compact?: boolean;
}) {
  const progress = getCurrentRunProgress(record);
  const busy = record.status === "queued" || record.status === "running";
  return (
    <section className={classNames("active-run-progress", compact && "compact")} aria-live="polite" aria-busy={busy}>
      <header>
        <Activity size={16} />
        <div>
          <strong>{compact ? "当前进度" : "当前运行进度"}</strong>
          <span>{progress.phaseLabel}</span>
        </div>
        <em className={classNames("run-progress-state", record.status)}>{formatRunState(record.status)}</em>
      </header>
      <div className="run-progress-meter" aria-label={`研究运行进度约 ${Math.round(progress.percent)}%`}>
        <span style={{ width: `${progress.percent}%` }} />
      </div>
      <div className="run-progress-copy">
        <strong>{progress.eventLabel}</strong>
        <span>{progress.detail || (progress.latestTime ? `最近更新 ${progress.latestTime}` : "正在等待下一条过程记录。")}</span>
      </div>
      <ol className="run-progress-steps" aria-label="研究流程阶段">
        {workflowProgressSteps.map((step, index) => {
          const state =
            record.status === "complete" || index < progress.activeIndex
              ? "complete"
              : record.status === "error" && index === progress.activeIndex
                ? "error"
                : index === progress.activeIndex
                  ? "active"
                  : "pending";
          return (
            <li className={state} key={step.key}>
              <span>{index + 1}</span>
              <strong>{step.label}</strong>
            </li>
          );
        })}
      </ol>
      <div className="run-progress-actions">
        <button type="button" className="button-secondary" onClick={onOpenTimeline}>
          查看过程记录
        </button>
        <button type="button" className="button-secondary" onClick={onOpenRanking}>
          查看 Elo 排序
        </button>
      </div>
    </section>
  );
}

function proposalPreviewFacts(proposal: ResearchChatActionProposal) {
  if (proposal.executionTarget !== "workflow.start_run") return [];
  const preview = proposal.requestPreview ?? {};
  const facts: string[] = [];
  const startingCount = Number(preview.starting_hypotheses_count ?? 0);
  const constraintCount = Array.isArray(preview.constraints) ? preview.constraints.length : 0;
  if (startingCount > 0) facts.push(`${startingCount} 条用户候选假设`);
  if (constraintCount > 0) facts.push(`${constraintCount} 条约束`);
  if (preview.parent_run_id) facts.push("基于历史运行继续");
  if (preview.memory_scope) facts.push(`上下文范围：${formatBackendText(String(preview.memory_scope))}`);
  return facts;
}

function ActionProposalCard({
  proposal,
  busy,
  onConfirm,
  onCancel,
}: {
  proposal: ResearchChatActionProposal;
  busy: boolean;
  onConfirm: (proposal: ResearchChatActionProposal) => void;
  onCancel: (proposal: ResearchChatActionProposal) => void;
}) {
  const previewFacts = proposalPreviewFacts(proposal);
  return (
    <section className="chat-proposal-card" aria-busy={busy}>
      <header>
        {proposal.executionTarget === "workflow.start_run" ? <Play size={16} /> : <ShieldCheck size={16} />}
        <div>
          <strong>{proposal.title}</strong>
          <span>{proposal.inputSummary}</span>
        </div>
      </header>
      <dl>
        <div>
          <dt>将执行</dt>
          <dd>{proposal.operationSummary.join("、")}</dd>
        </div>
        <div>
          <dt>边界</dt>
          <dd>{proposal.riskSummary}</dd>
        </div>
        <div>
          <dt>结果</dt>
          <dd>{proposal.expectedResultSummary.join("、")}</dd>
        </div>
      </dl>
      {previewFacts.length ? (
        <div className="status-badge-row" aria-label="运行输入摘要">
          {previewFacts.map((fact) => (
            <span className="status-chip" key={fact}>
              {fact}
            </span>
          ))}
        </div>
      ) : null}
      <div className="chat-proposal-actions">
        <button className={classNames("button-primary", busy && "is-loading")} type="button" disabled={busy} aria-busy={busy} onClick={() => onConfirm(proposal)}>
          {busy ? <Loader2 size={16} className="spin" /> : <CheckCircle2 size={16} />}
          {busy ? "执行中" : "确认执行"}
        </button>
        <button className="button-secondary" type="button" disabled={busy} onClick={() => onCancel(proposal)}>
          取消
        </button>
      </div>
      <details className="expert-summary">
        <summary>查看执行边界</summary>
        <dl>
          <div>
            <dt>授权范围</dt>
            <dd>{proposal.approvalScope}</dd>
          </div>
          <div>
            <dt>执行目标</dt>
            <dd>{proposal.executionTarget}</dd>
          </div>
        </dl>
      </details>
    </section>
  );
}

function CommandResultCard({
  result,
  record,
  onSetDetailTab,
}: {
  result: ResearchChatResult;
  record: RunRecord | null;
  onSetDetailTab: (tab: DetailTab) => void;
}) {
  const Icon = result.intent === "explain_ranking" ? Trophy : result.intent === "explain_current_run" ? Clock3 : result.intent === "discover_capabilities" ? Sparkles : FileText;
  const liveRecord = result.runId && record?.run_id === result.runId ? record : null;
  return (
    <section className="chat-result-card command-result-card">
      <header>
        <Icon size={16} />
        <div>
          <strong>{result.title || "任务完成"}</strong>
          {result.groundingBoundary ? <span>{formatBackendText(result.groundingBoundary)}</span> : null}
        </div>
      </header>
      <MetricStrip result={result} />
      {result.jobId ? <CommandExecutionPreview result={result} /> : null}
      {liveRecord && result.intent === "start_research_run" ? (
        <ActiveRunProgress
          record={liveRecord}
          compact
          onOpenTimeline={() => onSetDetailTab("agents")}
          onOpenRanking={() => onSetDetailTab("tournament")}
        />
      ) : null}
      {result.modeBoundary ? <div className="status-banner warning">{result.modeBoundary}</div> : null}
      {result.capabilityGroups ? <CapabilityMap groups={result.capabilityGroups} /> : null}
      {result.timeline?.length ? <TimelinePreview items={result.timeline} /> : null}
      {result.tournamentMatchups?.length ? <TournamentPreview matchups={result.tournamentMatchups} ranked={result.rankedHypotheses} /> : null}
      {result.sections?.length ? (
        <div className="chat-audit-block">
          <h3>结构</h3>
          {result.sections.map((section) => (
            <p key={section}>{section}</p>
          ))}
        </div>
      ) : null}
      {result.hypothesisPreview ? (
        <div className="chat-audit-block">
          <h3>假设摘要</h3>
          <MarkdownText text={result.hypothesisPreview} compact />
        </div>
      ) : null}
      {result.hypotheses?.length ? <HypothesisBriefList hypotheses={result.hypotheses} /> : null}
      {result.experimentPlan ? (
        <div className="chat-audit-block">
          <h3>实验计划</h3>
          <MarkdownText text={result.experimentPlan} compact />
        </div>
      ) : null}
      {result.items?.length ? <EvidencePreview result={result} /> : null}
      {result.externalCheck?.status && result.externalCheck.status !== "not_requested" ? <ExternalLiteratureStatus result={result} /> : null}
      {result.nextActions?.length ? (
        <div className="chat-next-actions">
          {result.nextActions.map((item) => {
            const tab = inferResultActionTab(item);
            return tab ? (
              <button key={item} type="button" onClick={() => onSetDetailTab(tab)}>
                {item}
              </button>
            ) : (
              <span key={item}>{item}</span>
            );
          })}
        </div>
      ) : null}
      <details className="expert-summary">
        <summary>查看审计摘要</summary>
        <dl>
          {result.runId ? (
            <div>
              <dt>研究运行</dt>
              <dd>{result.runId}</dd>
            </div>
          ) : null}
          {result.researchGoal ? (
            <div>
              <dt>研究目标</dt>
              <dd>{result.researchGoal}</dd>
            </div>
          ) : null}
          {result.reviewSummary ? (
            <div>
              <dt>评审摘要</dt>
              <dd>{result.reviewSummary}</dd>
            </div>
          ) : null}
          {result.plainExplanation ? (
            <div>
              <dt>通俗解释</dt>
              <dd>{result.plainExplanation}</dd>
            </div>
          ) : null}
        </dl>
      </details>
    </section>
  );
}

function CommandExecutionPreview({ result }: { result: ResearchChatResult }) {
  const [job, setJob] = useState<BackgroundJob | null>(null);
  const [toolResult, setToolResult] = useState<ToolResultResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!result.jobId) return;
    let cancelled = false;
    let timer: number | undefined;
    let attempts = 0;

    const poll = async () => {
      attempts += 1;
      try {
        const latestJob = await fetchBackgroundJob(result.jobId as string);
        if (cancelled) return;
        setJob(latestJob);
        const toolResultId = readToolResultId(latestJob);
        if (toolResultId) {
          const loaded = await fetchToolResult(toolResultId);
          if (!cancelled) setToolResult(loaded);
        }
        if ((latestJob.status === "queued" || latestJob.status === "running") && attempts < 40) {
          timer = window.setTimeout(poll, 500);
        }
      } catch {
        if (!cancelled) setError("后台任务结果暂时不可读取。");
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [result.jobId]);

  const content = toolResult?.content ?? {};
  const stdout = typeof content.stdout === "string" ? content.stdout.trim() : "";
  const stderr = typeof content.stderr === "string" ? content.stderr.trim() : "";
  const returncode = typeof content.returncode === "number" ? content.returncode : undefined;
  const status = job?.status || result.status || "queued";

  return (
    <div className="chat-audit-block command-output-preview">
      <h3>命令结果</h3>
      <p>
        {result.serverId ? `${result.serverId} · ` : ""}
        {result.jobId} · {formatBackendText(status)}
        {returncode !== undefined ? ` · returncode ${returncode}` : ""}
      </p>
      {stdout ? (
        <pre aria-label="命令 stdout">{stdout.slice(0, 4000)}</pre>
      ) : status === "queued" || status === "running" ? (
        <p>正在等待 stdout/stderr 写入审计结果...</p>
      ) : null}
      {stderr ? <pre aria-label="命令 stderr">{stderr.slice(0, 2000)}</pre> : null}
      {error ? <p>{error}</p> : null}
    </div>
  );
}

function readToolResultId(job: BackgroundJob) {
  const toolResult = job.result_ref?.tool_result;
  if (toolResult && typeof toolResult === "object" && "result_id" in toolResult) {
    const value = (toolResult as { result_id?: unknown }).result_id;
    return typeof value === "string" ? value : "";
  }
  return "";
}

function ExternalLiteratureStatus({ result }: { result: ResearchChatResult }) {
  const externalCheck = result.externalCheck;
  if (!externalCheck) return null;
  return (
    <div className={classNames("chat-verification-status", externalCheck.status === "complete" ? "ok" : externalCheck.status === "failed" ? "error" : "warning")}>
      <ShieldCheck size={14} />
      <div>
        <span>{externalCheck.summary || formatBackendText(externalCheck.status || "external_check")}</span>
        {externalCheck.sourceStatuses?.length ? (
          <div className="chat-source-status-row">
            {externalCheck.sourceStatuses.map((source) => (
              <small key={source.toolId || source.mcpToolName}>
                {formatBackendText(source.toolId || source.mcpToolName || "source")} · {formatBackendText(source.status || "unknown")}
              </small>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function CapabilityMap({ groups }: { groups: Record<string, ResearchChatCapability[]> }) {
  return (
    <div className="capability-map-grid">
      {Object.entries(groups).map(([area, items]) => (
        <article key={area}>
          <strong>{formatBackendText(area)}</strong>
          {items.slice(0, 4).map((item) => (
            <p key={item.id}>
              <span>{item.userTitle}</span>
              <small>{item.executionMode === "approval_required" ? "需确认" : "只读"}</small>
            </p>
          ))}
        </article>
      ))}
    </div>
  );
}

function TimelinePreview({ items }: { items: Array<Record<string, unknown>> }) {
  return (
    <div className="timeline-preview-list">
      {items.map((item, index) => (
        <article key={`${String(item.stage ?? "stage")}-${index}`}>
          <Clock3 size={14} />
          <div>
            <strong>{String(item.event ?? item.stage ?? "阶段")}</strong>
            <p>{String(item.details ?? item.status ?? "")}</p>
          </div>
        </article>
      ))}
    </div>
  );
}

function TournamentPreview({
  matchups,
  ranked,
}: {
  matchups: NonNullable<ResearchChatResult["tournamentMatchups"]>;
  ranked?: ResearchChatResult["rankedHypotheses"];
}) {
  return (
    <div className="tournament-preview">
      {ranked?.length ? (
        <div className="ranking-preview-list">
          {ranked.slice(0, 4).map((item) => (
            <span key={`${item.index}-${item.title}`}>
              #{item.index + 1} {item.eloRating ?? "Elo pending"}
            </span>
          ))}
        </div>
      ) : null}
      {matchups.slice(0, 4).map((matchup) => (
        <article key={matchup.matchupIndex}>
          <header>
            <strong>Match {matchup.matchupIndex}</strong>
            <span>{matchup.confidence !== undefined && matchup.confidence !== null ? `confidence ${matchup.confidence}` : "confidence n/a"}</span>
          </header>
          <p>
            winner {String(matchup.winner ?? "n/a")} / loser {String(matchup.loser ?? "n/a")}
          </p>
          {matchup.reasoning ? <p>{matchup.reasoning}</p> : null}
          <details className="expert-summary">
            <summary>before/after Elo</summary>
            <pre>{JSON.stringify({ before: matchup.beforeElo, after: matchup.afterElo, delta: matchup.eloDelta }, null, 2)}</pre>
          </details>
        </article>
      ))}
    </div>
  );
}

function HypothesisBriefList({ hypotheses }: { hypotheses: NonNullable<ResearchChatResult["hypotheses"]> }) {
  return (
    <div className="hypothesis-brief-list">
      {hypotheses.map((hypothesis) => (
        <article key={`${hypothesis.index}-${hypothesis.title}`}>
          <header>
            <strong>
              #{hypothesis.index + 1} {hypothesis.title}
            </strong>
            {hypothesis.eloRating !== undefined || hypothesis.score !== undefined ? (
              <span>{hypothesis.eloRating !== undefined ? `Elo ${hypothesis.eloRating}` : `score ${hypothesis.score}`}</span>
            ) : null}
          </header>
          {hypothesis.text ? <MarkdownText text={hypothesis.text} compact /> : null}
          {hypothesis.plainExplanation ? <p>{hypothesis.plainExplanation}</p> : null}
          {hypothesis.experimentPlan ? <p>验证：{hypothesis.experimentPlan}</p> : null}
          {hypothesis.reviewSummary ? <p>评审：{hypothesis.reviewSummary}</p> : null}
        </article>
      ))}
    </div>
  );
}

function EvidencePreview({ result }: { result: ResearchChatResult }) {
  return (
    <div className="chat-evidence-list">
      {(result.items ?? []).slice(0, 4).map((item, index) => (
        <article key={`${item.chunk_id || item.evidence_id || item.result_id || item.paper_id || "item"}-${index}`}>
          <div>
            <Search size={14} />
            <strong>{item.title || item.paper_id || item.type || "候选证据"}</strong>
          </div>
          <p>{String(item.text_preview || item.evidence_summary || item.snippet || "该结果只有摘要引用，需进入详情复核。").slice(0, 260)}</p>
          <footer>
            {item.source_channel ? <span>{formatBackendText(item.source_channel)}</span> : null}
            {item.support_level ? <span>{formatBackendText(item.support_level)}</span> : null}
            {item.status ? <span>{formatBackendText(String(item.status))}</span> : null}
          </footer>
        </article>
      ))}
    </div>
  );
}

function MetricStrip({ result }: { result: ResearchChatResult }) {
  const metrics = [
    result.runId ? { label: "运行", value: "已创建" } : null,
    result.hypothesisCount !== undefined ? { label: "假设", value: String(result.hypothesisCount) } : null,
    result.tournamentCount !== undefined ? { label: "Elo 比较", value: String(result.tournamentCount) } : null,
    result.hypothesisIndex !== undefined ? { label: "序号", value: `#${result.hypothesisIndex + 1}` } : null,
    result.eloRating !== undefined ? { label: "Elo", value: String(result.eloRating) } : null,
    result.score !== undefined ? { label: "评分", value: String(result.score) } : null,
    result.confidence !== undefined ? { label: "置信度", value: `${Math.round(result.confidence * 100)}%` } : null,
    result.status ? { label: "状态", value: formatBackendText(result.status) } : null,
    result.verdict ? { label: "结论", value: formatBackendText(result.verdict) } : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>;
  if (!metrics.length) return null;
  return (
    <div className="chat-metric-strip">
      {metrics.slice(0, 5).map((metric) => (
        <span key={metric.label}>
          <strong>{metric.value}</strong>
          {metric.label}
        </span>
      ))}
    </div>
  );
}
