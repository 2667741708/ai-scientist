import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Loader2,
  MessageSquareText,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { MarkdownText } from "../../components/content/MarkdownText";
import {
  cancelResearchChatAction,
  confirmResearchChatAction,
  fetchResearchChatCapabilities,
  sendResearchChatTurn,
} from "../../lib/api/researchChat";
import { classNames, formatBackendText } from "../../lib/formatters/workbench";
import { useWorkbench } from "../runs/workbench-context";
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

const starterPrompts = [
  "帮我解析 D:\\papers\\paper.pdf 并加入知识库",
  "把这个网页保存为证据：https://example.org/article",
  "找一下关于耐药机制的 fulltext 证据",
  "检验这个假设是否正确，并查 PubMed、arXiv 和 Google Scholar：",
  "这个假设有没有足够证据支撑：",
  "执行本地命令：git status --short",
  "在 c201-5080 执行命令：hostname",
  "联网搜索：open-coscientist github",
];

function makeId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function promptForCapability(capability: Pick<ResearchChatCapability, "intent" | "userSummary">) {
  switch (capability.intent) {
    case "parse_pdf_to_knowledge_base":
      return starterPrompts[0];
    case "extract_web_evidence":
      return starterPrompts[1];
    case "search_knowledge_evidence":
      return starterPrompts[2];
    case "check_hypothesis_grounding":
      return starterPrompts[4];
    case "verify_evidence_with_literature":
      return starterPrompts[3];
    case "run_terminal_command":
      return starterPrompts[5];
    case "run_ssh_training_command":
      return starterPrompts[6];
    case "search_public_web":
      return starterPrompts[7];
    default:
      return capability.userSummary;
  }
}

function isResearchChatCapability(item: unknown): item is ResearchChatCapability {
  return Boolean(item && typeof item === "object" && "intent" in item && typeof (item as { intent?: unknown }).intent === "string");
}

function getFocusableElements(container: HTMLElement) {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute("disabled") && element.tabIndex !== -1);
}

export function ResearchChatLauncher() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="research-chat-launcher" type="button" onClick={() => setOpen(true)} aria-label="打开研究助手">
        <MessageSquareText size={18} />
        <span>研究助手</span>
      </button>
      {open ? <ResearchChatDrawer onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function ResearchChatDrawer({ onClose }: { onClose: () => void }) {
  const location = useLocation();
  const { currentRunId } = useWorkbench();
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [input, setInput] = useState("");
  const [state, setState] = useState<ResearchChatState>("idle");
  const [activeLibraryId, setActiveLibraryId] = useState<string | null>(() => window.localStorage.getItem("coscientist.activeLibraryId"));
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: makeId("assistant"),
      role: "assistant",
      text: "我可以帮你了解项目功能、解析 PDF、抓取网页证据、搜索知识库，或检查假设/Elo 排名。写入型任务会先给你确认卡片。",
      assistant: { kind: "status", text: "我可以帮你了解项目功能、解析 PDF、抓取网页证据、搜索知识库，或检查假设/Elo 排名。写入型任务会先给你确认卡片。" },
    },
  ]);
  const [capabilities, setCapabilities] = useState<ResearchChatCapability[]>([]);
  const [executingActionId, setExecutingActionId] = useState<string | null>(null);
  const drawerRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    closeRef.current?.focus();
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
      mode: "evidence" as const,
      run_id: currentRunId,
      library_id: activeLibraryId,
      language: "zh" as const,
    }),
    [activeLibraryId, currentRunId, location.pathname],
  );

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      onClose();
      return;
    }
    if (event.key !== "Tab" || !drawerRef.current) return;
    const focusable = getFocusableElements(drawerRef.current);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const appendAssistant = (assistant: ResearchChatAssistantMessage) => {
    setMessages((items) => [
      ...items,
      {
        id: makeId("assistant"),
        role: "assistant",
        text: assistant.text,
        assistant,
      },
    ]);
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
      appendAssistant({
        kind: "error",
        text: "证据助手暂时不可用，请确认后端服务正在运行后再试。",
      });
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
          reason: "User confirmed Evidence Copilot action.",
        },
      });
      appendAssistant(response.assistant_message);
      setState(response.state);
    } catch {
      appendAssistant({
        kind: "error",
        text: "任务未能执行。请检查输入和运行准备状态后重试。",
      });
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

  const isBusy = state === "routing" || state === "executing";

  return (
    <div className="drawer-backdrop research-chat-backdrop" role="presentation" onClick={onClose}>
      <aside
        ref={drawerRef}
        className="reference-drawer research-chat-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="research-chat-title"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="drawer-header research-chat-header">
          <div>
            <span>文献与证据任务</span>
            <h2 id="research-chat-title">研究助手</h2>
            <p>可询问项目能力，也可发起证据任务；写入型动作先确认。</p>
          </div>
          <button className="drawer-close" type="button" aria-label="关闭研究证据助手" onClick={onClose} ref={closeRef}>
            <X size={18} />
          </button>
        </div>

        <div className="research-chat-body">
          <div className="research-chat-messages" ref={messagesRef} aria-live="polite">
            {messages.map((message) => (
              <ChatBubble
                key={message.id}
                message={message}
                executingActionId={executingActionId}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
              />
            ))}
            {state === "routing" ? (
              <article className="chat-bubble assistant" role="status" aria-busy="true">
                <Loader2 size={16} className="spin" />
                <p>正在理解你的证据任务...</p>
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

          <form className="research-chat-composer" onSubmit={handleSubmit}>
            <label htmlFor="research-chat-input">输入研究任务或项目问题</label>
            <textarea
              ref={inputRef}
              id="research-chat-input"
              value={input}
              rows={3}
              maxLength={4000}
              placeholder="例如：这个项目能做什么？或 帮我解析 D:\\papers\\paper.pdf 并加入知识库"
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="research-chat-composer-actions">
              <span>{state === "awaiting_confirmation" ? "请先处理确认卡片，或继续补充上下文。" : "Enter 换行，Ctrl+Enter 发送。"}</span>
              <button className={classNames("button-primary", isBusy && "is-loading")} type="submit" disabled={!input.trim() || isBusy} aria-busy={isBusy}>
                {isBusy ? "处理中" : "发送"}
              </button>
            </div>
          </form>
        </div>
      </aside>
    </div>
  );
}

function CapabilitySuggestions({
  capabilities,
  onPick,
}: {
  capabilities: ResearchChatCapability[];
  onPick: (value: string) => void;
}) {
  const fallback = [
    { userTitle: "解析 PDF", userSummary: starterPrompts[0] },
    { userTitle: "抓取网页证据", userSummary: starterPrompts[1] },
    { userTitle: "搜索知识库", userSummary: starterPrompts[2] },
  ];
  const preferredOrder = [
    "parse_pdf_to_knowledge_base",
    "run_terminal_command",
    "run_ssh_training_command",
    "search_public_web",
    "verify_evidence_with_literature",
    "search_knowledge_evidence",
    "check_hypothesis_grounding",
  ];
  const items = capabilities.length
    ? [...capabilities]
        .sort((a, b) => {
          const aIndex = preferredOrder.indexOf(a.intent);
          const bIndex = preferredOrder.indexOf(b.intent);
          return (aIndex === -1 ? preferredOrder.length : aIndex) - (bIndex === -1 ? preferredOrder.length : bIndex);
        })
        .slice(0, 4)
    : fallback;
  return (
    <div className="research-chat-suggestions" aria-label="常用证据任务">
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

function ChatBubble({
  message,
  executingActionId,
  onConfirm,
  onCancel,
}: {
  message: ChatMessage;
  executingActionId: string | null;
  onConfirm: (proposal: ResearchChatActionProposal) => void;
  onCancel: (proposal: ResearchChatActionProposal) => void;
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
        {assistant?.result ? <ResultSummaryCard result={assistant.result} /> : null}
        {assistant?.suggestions?.length ? (
          <div className="chat-inline-options">
            {assistant.suggestions.slice(0, 4).map((item) => (
              <span key={item.id}>{item.userTitle}</span>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
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
  return (
    <section className="chat-proposal-card" aria-busy={busy}>
      <header>
        <ShieldCheck size={16} />
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
          <dt>风险</dt>
          <dd>{proposal.riskSummary}</dd>
        </div>
        <div>
          <dt>结果</dt>
          <dd>{proposal.expectedResultSummary.join("、")}</dd>
        </div>
      </dl>
      <div className="chat-proposal-actions">
        <button className={classNames("button-primary", busy && "is-loading")} type="button" disabled={busy} aria-busy={busy} onClick={() => onConfirm(proposal)}>
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

function ResultSummaryCard({ result }: { result: ResearchChatResult }) {
  const verdictTone =
    result.verdict === "grounded" || result.verdict === "supported"
      ? "ok"
      : result.verdict === "ungrounded" || result.verdict === "contradicted"
        ? "error"
        : "warning";
  const evidenceItems = result.items ?? [];
  return (
    <section className="chat-result-card">
      <header>
        {result.verdict === "grounded" || result.verdict === "supported" || result.ragSearchReady || result.knowledgeBaseIngested ? (
          <CheckCircle2 size={16} />
        ) : result.verdict ? (
          <AlertTriangle size={16} />
        ) : (
          <FileText size={16} />
        )}
        <div>
          <strong>{result.title || "任务完成"}</strong>
          {result.groundingBoundary ? <span>{formatBackendText(result.groundingBoundary)}</span> : null}
        </div>
      </header>
      {result.verdict ? <div className={classNames("status-pill", verdictTone)}>{formatBackendText(result.verdict)}</div> : null}
      <MetricStrip result={result} />
      {evidenceItems.length ? (
        <div className="chat-evidence-list">
          {evidenceItems.slice(0, 3).map((item, index) => (
            <article key={`${item.chunk_id || item.evidence_id || item.result_id || item.paper_id || "evidence"}-${index}`}>
              <div>
                <Search size={14} />
                <strong>{item.title || item.paper_id || "候选证据"}</strong>
              </div>
              <p>{(item.text_preview || item.evidence_summary || "该证据只有摘要引用，需进入详情复核。").slice(0, 280)}</p>
              <footer>
                {item.source_channel ? <span>{formatBackendText(item.source_channel)}</span> : null}
                {item.support_level ? <span>{formatBackendText(item.support_level)}</span> : null}
                {item.source_reliability ? <span>{formatBackendText(item.source_reliability)}</span> : null}
                {item.possible_counter_evidence ? <span>潜在反证</span> : null}
              </footer>
            </article>
          ))}
        </div>
      ) : null}
      {result.hypotheses?.length ? (
        <div className="hypothesis-brief-list">
          {result.hypotheses.map((hypothesis) => (
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
            </article>
          ))}
        </div>
      ) : null}
      {result.externalCheck?.status && result.externalCheck.status !== "not_requested" ? (
        <div className={classNames("chat-verification-status", result.externalCheck.status === "complete" ? "ok" : result.externalCheck.status === "failed" ? "error" : "warning")}>
          <ShieldCheck size={14} />
          <div>
            <span>{result.externalCheck.summary || formatBackendText(result.externalCheck.status)}</span>
            {result.externalCheck.sourceStatuses?.length ? (
              <div className="chat-source-status-row">
                {result.externalCheck.sourceStatuses.map((source) => (
                  <small key={source.toolId || source.mcpToolName}>
                    {formatBackendText(source.toolId || source.mcpToolName || "source")} · {formatBackendText(source.status || "unknown")}
                  </small>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
      {result.nextActions?.length ? (
        <div className="chat-next-actions">
          {result.nextActions.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      ) : null}
      <details className="expert-summary">
        <summary>查看审计引用</summary>
        <dl>
          {result.parseRunId ? (
            <div>
              <dt>解析任务</dt>
              <dd>{result.parseRunId}</dd>
            </div>
          ) : null}
          {result.paperId || result.knowledgeBasePaperId ? (
            <div>
              <dt>知识库论文</dt>
              <dd>{result.paperId || result.knowledgeBasePaperId}</dd>
            </div>
          ) : null}
          {result.artifactSummary?.solveDir ? (
            <div>
              <dt>产物目录</dt>
              <dd>{result.artifactSummary.solveDir}</dd>
            </div>
          ) : null}
          {result.finalUrl ? (
            <div>
              <dt>最终 URL</dt>
              <dd>{result.finalUrl}</dd>
            </div>
          ) : null}
          {result.confidence !== undefined ? (
            <div>
              <dt>核验置信度</dt>
              <dd>{Math.round(result.confidence * 100)}%</dd>
            </div>
          ) : null}
          {result.support_level ? (
            <div>
              <dt>支撑级别</dt>
              <dd>{formatBackendText(result.support_level)}</dd>
            </div>
          ) : null}
          {result.externalCheck?.query ? (
            <div>
              <dt>外部检索</dt>
              <dd>{result.externalCheck.query}</dd>
            </div>
          ) : null}
        </dl>
        {result.claimChecks?.length ? (
          <div className="chat-audit-block">
            <h3>Claim 核验</h3>
            {result.claimChecks.slice(0, 4).map((claim, index) => (
              <p key={`${claim.status}-${index}`}>
                <strong>{formatBackendText(claim.status)}</strong>
                {claim.claim}
              </p>
            ))}
          </div>
        ) : null}
        {result.missingEvidence?.length ? (
          <div className="chat-audit-block">
            <h3>证据缺口</h3>
            {result.missingEvidence.slice(0, 5).map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
        ) : null}
        {result.possibleCounterEvidence?.length ? (
          <div className="chat-audit-block">
            <h3>潜在反证</h3>
            {result.possibleCounterEvidence.slice(0, 3).map((item, index) => (
              <p key={`${item.chunk_id || item.result_id || "counter"}-${index}`}>{item.text_preview || item.evidence_summary}</p>
            ))}
          </div>
        ) : null}
        {result.falsificationTests?.length ? (
          <div className="chat-audit-block">
            <h3>可证伪检查</h3>
            {result.falsificationTests.slice(0, 4).map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
        ) : null}
      </details>
    </section>
  );
}

function MetricStrip({ result }: { result: ResearchChatResult }) {
  const metrics = [
    result.pageCount !== undefined ? { label: "页数", value: String(result.pageCount) } : null,
    result.chunksCount !== undefined ? { label: "片段", value: String(result.chunksCount) } : null,
    result.experimentalChunksCount !== undefined ? { label: "实验线索", value: String(result.experimentalChunksCount) } : null,
    result.pdfLinkCount !== undefined ? { label: "PDF 链接", value: String(result.pdfLinkCount) } : null,
    result.supplementaryLinkCount !== undefined ? { label: "补充材料", value: String(result.supplementaryLinkCount) } : null,
    result.sourceReliability ? { label: "来源", value: formatBackendText(result.sourceReliability) } : null,
    result.confidence !== undefined ? { label: "置信度", value: `${Math.round(result.confidence * 100)}%` } : null,
    result.sourceReliabilitySummary?.totalEvidenceCount !== undefined
      ? { label: "证据", value: String(result.sourceReliabilitySummary.totalEvidenceCount) }
      : null,
    result.sourceReliabilitySummary?.parsedFulltextCount !== undefined
      ? { label: "全文", value: String(result.sourceReliabilitySummary.parsedFulltextCount) }
      : null,
    result.sourceReliabilitySummary?.experimentalEvidenceCount !== undefined
      ? { label: "实验", value: String(result.sourceReliabilitySummary.experimentalEvidenceCount) }
      : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>;
  if (!metrics.length) return null;
  return (
    <div className="chat-metric-strip">
      {metrics.map((metric) => (
        <span key={metric.label}>
          <strong>{metric.value}</strong>
          {metric.label}
        </span>
      ))}
    </div>
  );
}
