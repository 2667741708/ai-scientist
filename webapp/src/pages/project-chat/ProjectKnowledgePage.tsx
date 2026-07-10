import { CheckCircle2, Copy, Languages, Loader2, Send, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { MarkdownText } from "../../components/content/MarkdownText";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { useWorkbench } from "../../features/runs/workbench-context";
import { getCommandPermissions, translateEvidenceText, updateCommandPermissions } from "../../lib/api/workbench";
import { cancelResearchChatAction, confirmResearchChatAction, sendResearchChatTurn, streamResearchChatTurn } from "../../lib/api/researchChat";
import { classNames, formatBackendText } from "../../lib/formatters/workbench";
import { mapRunToWorkspaceView } from "../../lib/view-models/workbench";
import type { ResearchChatActionProposal, ResearchChatAssistantMessage, ResearchChatProgressEvent, ResearchChatResult, ResearchChatTurnRequest } from "../../types/research-chat";
import type { CommandPermissionMode, CommandPermissionPolicy } from "../../types/workbench";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  assistant?: ResearchChatAssistantMessage;
  progress?: ResearchChatProgressEvent[];
};

type ProjectToolAction = {
  id: string;
  label: string;
  description: string;
  prompt: string;
  userMessage: string;
  expectedApprovalScope: NonNullable<ResearchChatActionProposal["approvalScope"]>;
  autoConfirm: boolean;
};

type EvidenceTranslationState = {
  status: "loading" | "complete" | "error";
  text?: string;
  provider?: string;
  error?: string;
};

const starterPrompts = [
  "这个项目现在能做什么？",
  "我想生成候选假设，应该从哪里开始？",
  "演示模式、实时模型和文献支撑有什么区别？",
  "Elo 锦标赛排名如何审计？",
];

const projectAiPolicyModes: Array<{
  mode: CommandPermissionMode;
  label: string;
  description: string;
}> = [
  {
    mode: "request_approval",
    label: "请求审批",
    description: "每个写入、外部访问或命令动作都显示确认卡。",
  },
  {
    mode: "approve_safe",
    label: "替我审批",
    description: "自动执行安全的 schema 化动作，高风险动作仍需确认。",
  },
  {
    mode: "full_access",
    label: "完全访问",
    description: "确认卡会按后端 guardrail 自动执行，危险命令仍会被拦截。",
  },
];

function makeId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function summarizeLatestResult(result?: ResearchChatResult) {
  if (!result) return [];
  return [
    result.intent ? `最近意图: ${formatBackendText(result.intent)}` : "",
    result.title ? `最近结果: ${result.title}` : "",
    result.status ? `最近状态: ${formatBackendText(result.status)}` : "",
    result.verdict ? `证据判断: ${formatBackendText(result.verdict)}` : "",
    result.groundingBoundary ? `证据边界: ${formatBackendText(result.groundingBoundary)}` : "",
    result.query ? `最近检索词: ${result.query}` : "",
    typeof result.knowledgeHitCount === "number" ? `知识库命中: ${result.knowledgeHitCount}` : "",
    result.items?.length ? `证据片段数: ${result.items.length}` : "",
    result.nextActions?.length ? `建议动作: ${result.nextActions.slice(0, 4).join("；")}` : "",
  ].filter(Boolean);
}

function compactToolQuery(value?: string | null) {
  const firstLine = (value || "")
    .split("\n")
    .map((line) => line.trim())
    .find(Boolean) || "";
  return firstLine
    .replace(/^联网搜索[:：]\s*/i, "")
    .replace(/^web\s*search[:：]\s*/i, "")
    .trim()
    .slice(0, 240);
}

function isGenericCurrentProjectQuestion(text?: string | null) {
  const value = text || "";
  return /(当前这个项目|当前项目|这个项目|指定项目|project)/i.test(value) && /(能做什么|可以实现什么|有什么|有哪些|产出|论文|假设|实验|报告|artifact|inventory|papers|hypotheses|experiments|reports)/i.test(value);
}

function looksLikeConcreteHypothesisRequest(text?: string | null, result?: ResearchChatResult) {
  if (result?.hypothesisPreview) return true;
  const value = text || "";
  if (isGenericCurrentProjectQuestion(value)) return false;
  return /(候选假设\s*#?\d+|假设\s*#?\d+|这个假设|该假设|hypothesis\s*#?\d+|Action Dependency Graph|Gradient-based|self-attention)/i.test(value);
}

function extractPdfReference(text: string) {
  const match = text.match(/([A-Za-z]:\\[^\n\r"<>|]+?\.pdf|https?:\/\/[^\s"'<>]+?\.pdf)(?=$|\s|[，。；,;])/i);
  return match?.[1]?.trim() || "";
}

function inferProjectToolActions(assistant: ResearchChatAssistantMessage, lastUserMessage?: string) {
  const result = assistant.result;
  const resultItems = (result?.items ?? []) as Array<Record<string, unknown>>;
  const webResultUrls = resultItems
    .map((item) => (typeof item.url === "string" ? item.url : ""))
    .filter(Boolean)
    .slice(0, 3);
  if (result?.intent === "search_public_web" && webResultUrls.length) {
    const query = compactToolQuery(result.query || lastUserMessage || assistant.text);
    return [
      {
        id: "browser.web_extract.batch",
        label: "允许抓取网页并整理",
        description: "打开搜索结果中的高相关公开网页，抽取正文 preview，并基于网页内容聚合回答。",
        prompt: [
          "抓取高相关网页作为证据并整理回答：",
          ...webResultUrls,
          query ? `原始问题：${query}` : "",
        ]
          .filter(Boolean)
          .join("\n"),
        userMessage: `允许抓取 ${webResultUrls.length} 个网页并整理回答`,
        expectedApprovalScope: "browser.web_extract" as const,
        autoConfirm: true,
      },
    ];
  }
  if (
    result?.intent &&
    [
      "parse_pdf_to_knowledge_base",
      "extract_web_evidence",
      "extract_web_evidence_batch",
      "verify_evidence_with_literature",
      "run_terminal_command",
      "run_ssh_training_command",
    ].includes(result.intent)
  ) {
    return [];
  }
  const combinedText = [
    assistant.text,
    result?.summary,
    result?.title,
    result?.modeBoundary,
    ...(result?.nextActions ?? []),
  ]
    .filter(Boolean)
    .join("\n");
  const query = compactToolQuery(result?.query || lastUserMessage || result?.title || assistant.text);
  const actions: ProjectToolAction[] = [];

  if (query && /(web search|websearch|联网搜索|通用 web|公开 web|外部网络|公开搜索|网络搜索)/i.test(combinedText)) {
    actions.push({
      id: "web.search_public",
      label: "允许并执行 Web Search",
      description: "用当前问题发起公开 Web Search，返回 URL、snippet 和 provenance；搜索摘要只是线索。",
      prompt: `联网搜索：${query}`,
      userMessage: `允许 Web Search：${query}`,
      expectedApprovalScope: "web.search_public",
      autoConfirm: true,
    });
  }

  const pdfReference = extractPdfReference(`${lastUserMessage || ""}\n${combinedText}`);
  if (pdfReference && /(pdf|全文|入库|解析)/i.test(combinedText)) {
    actions.push({
      id: "pdf.parse_to_knowledge_base",
      label: "允许解析 PDF",
      description: "读取这个 PDF，抽取全文、metadata 和 chunks，并写入本地知识库。",
      prompt: `解析 PDF 并写入知识库：${pdfReference}`,
      userMessage: `允许解析 PDF：${pdfReference}`,
      expectedApprovalScope: "pdf.parse_to_knowledge_base",
      autoConfirm: true,
    });
  }

  if (
    query &&
    /(外部文献|mcp|pubmed|arxiv|google scholar|反证|负面结果|failed replication)/i.test(combinedText) &&
    looksLikeConcreteHypothesisRequest(lastUserMessage || query, result)
  ) {
    actions.push({
      id: "mcp.literature_review",
      label: "允许外部文献反证检查",
      description: "授权调用文献 MCP 检索潜在反证、负面结果和复现失败线索。",
      prompt: `用外部文献反证检查这个假设：${query}`,
      userMessage: `允许外部文献反证检查：${query}`,
      expectedApprovalScope: "mcp.literature_review",
      autoConfirm: true,
    });
  }

  return actions;
}

export function ProjectKnowledgePage() {
  const [searchParams] = useSearchParams();
  const { history } = useWorkbench();
  const scopedRunId = searchParams.get("run") || "";
  const scopedHypothesisIndex = Number(searchParams.get("hypothesis") ?? "");
  const scopedIntent = searchParams.get("intent") || "";
  const scopedRun = useMemo(() => history.find((record) => record.run_id === scopedRunId), [history, scopedRunId]);
  const activeRunId = scopedRunId || scopedRun?.run_id || "";
  const scopedWorkspace = useMemo(() => (scopedRun ? mapRunToWorkspaceView(scopedRun) : null), [scopedRun]);
  const scopedHypothesis = Number.isFinite(scopedHypothesisIndex)
    ? scopedWorkspace?.hypotheses[scopedHypothesisIndex]
    : undefined;
  const scopedPrompt = scopedHypothesis
    ? scopedIntent === "draft_report"
      ? `请围绕当前项目中的候选假设 #${scopedHypothesisIndex + 1}「${scopedHypothesis.title}」整理一份排版清晰的 Markdown 报告草稿。请结合项目 research skills：evidence-grounding-rubric、citation-provenance-qa、falsifiability-review。报告至少包含：研究目标、候选假设原文、中文解释、证据边界、引用不一致或全文不足说明、可证伪实验设计、失败条件、下一步任务。`
      : `围绕当前项目中的候选假设 #${scopedHypothesisIndex + 1}「${scopedHypothesis.title}」，请帮我做具体实验和分析：列出可观测变量、对照组、失败条件、最小验证路径，以及还缺哪些证据。`
    : "";
  const [input, setInput] = useState("");
  const [isAnswering, setIsAnswering] = useState(false);
  const [executingActionId, setExecutingActionId] = useState<string | null>(null);
  const [preparingToolActionId, setPreparingToolActionId] = useState<string | null>(null);
  const [progressSteps, setProgressSteps] = useState<ResearchChatProgressEvent[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [scopedPromptApplied, setScopedPromptApplied] = useState(false);
  const [actionPolicy, setActionPolicy] = useState<CommandPermissionPolicy | null>(null);
  const [actionPolicyStatus, setActionPolicyStatus] = useState<"loading" | "ready" | "saving" | "error">("loading");
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "你可以直接问这个项目能做什么、如何开始运行、哪个页面负责什么，以及哪些能力只是演示、实时模型或文献支撑。",
      assistant: {
        kind: "status",
        text: "你可以直接问这个项目能做什么、如何开始运行、哪个页面负责什么，以及哪些能力只是演示、实时模型或文献支撑。",
      },
    },
  ]);

  useEffect(() => {
    setScopedPromptApplied(false);
  }, [scopedRunId, scopedHypothesisIndex, scopedIntent]);

  useEffect(() => {
    if (!scopedPrompt || scopedPromptApplied) return;
    setInput(scopedPrompt);
    setScopedPromptApplied(true);
  }, [scopedPrompt, scopedPromptApplied]);

  useEffect(() => {
    let cancelled = false;
    setActionPolicyStatus("loading");
    getCommandPermissions()
      .then((response) => {
        if (cancelled) return;
        setActionPolicy(response.policy);
        setActionPolicyStatus("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setActionPolicyStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const appendAssistant = (assistant: ResearchChatAssistantMessage, progress?: ResearchChatProgressEvent[]) => {
    setMessages((items) => [...items, { id: makeId("assistant"), role: "assistant", text: assistant.text, assistant, progress }]);
  };

  const handleActionPolicyChange = async (mode: CommandPermissionMode) => {
    if (actionPolicyStatus === "saving" || actionPolicy?.mode === mode) return;
    setActionPolicyStatus("saving");
    try {
      const response = await updateCommandPermissions(mode);
      setActionPolicy(response.policy);
      setActionPolicyStatus("ready");
    } catch (error) {
      setActionPolicyStatus("error");
      appendAssistant({
        kind: "error",
        text: error instanceof Error ? error.message : "项目 AI 执行策略更新失败。请检查当前账号权限或后端服务状态。",
      });
    }
  };

  const isBusy = isAnswering || Boolean(executingActionId) || Boolean(preparingToolActionId);

  const latestAssistantResult = useMemo(() => {
    return [...messages].reverse().find((message) => message.role === "assistant" && message.assistant?.result)?.assistant?.result;
  }, [messages]);

  const lastUserMessage = useMemo(() => {
    return [...messages].reverse().find((message) => message.role === "user")?.text;
  }, [messages]);

  const contextLines = useMemo(() => {
    return [
      "当前页面: /project-chat",
      scopedRun ? `当前项目目标: ${scopedRun.request.research_goal}` : activeRunId ? `当前绑定运行: ${activeRunId}，等待加载本地摘要` : "当前没有绑定具体运行",
      scopedRun ? `当前运行: ${scopedRun.run_id}，状态 ${scopedRun.status}` : activeRunId ? `当前运行: ${activeRunId}` : "",
      scopedRun ? `当前运行产物: ${scopedRun.hypotheses.length} 条假设，${scopedRun.tournament_matchups.length} 场 Elo/排序比较` : "",
      scopedHypothesis ? `当前假设: #${scopedHypothesisIndex + 1} ${scopedHypothesis.title}` : "",
      scopedHypothesis?.summary ? `当前假设摘要: ${scopedHypothesis.summary}` : "",
      lastUserMessage ? `上一轮用户问题: ${lastUserMessage}` : "",
      ...summarizeLatestResult(latestAssistantResult),
    ].filter(Boolean);
  }, [activeRunId, lastUserMessage, latestAssistantResult, scopedHypothesis, scopedHypothesisIndex, scopedRun]);

  const stagePrompt = (value: string) => {
    setInput(value);
    window.setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(value.length, value.length);
    }, 0);
  };

  const withConversationContext = (question: string) => {
    return `${question}

请基于下面的当前对话上下文回答，不要只给通用说明；如果下一步需要解析 PDF、联网搜索或调用外部文献服务，请先返回确认卡或明确说明需要我确认。

${contextLines.map((line) => `- ${line}`).join("\n")}`;
  };

  const buildStarterPrompt = (prompt: string) => {
    if (prompt.includes("生成候选假设")) {
      return withConversationContext("我想基于当前项目和最近对话生成候选假设。请告诉我现在最应该补充哪些证据、研究目标还缺哪些约束，以及下一步应启动哪种 workflow。");
    }
    if (prompt.includes("演示模式")) {
      return withConversationContext("请结合当前项目状态解释演示模式、实时模型和文献支撑 workflow 的区别，并告诉我当前上下文更适合哪一种。");
    }
    if (prompt.includes("Elo")) {
      return withConversationContext("请基于当前运行的真实 tournament/Elo 上下文解释排名如何审计，包括 winner/loser、confidence、before/after Elo 和证据边界。");
    }
    return withConversationContext("请基于当前项目、最近对话和已有知识库结果，说明这个项目现在能做什么、不能做什么，以及最自然的下一步。");
  };

  const buildNextActionPrompt = (action: string) => {
    const normalized = action.toLowerCase();
    if (action.includes("抓取高相关网页") || action.includes("抓取网页")) {
      const urls = ((latestAssistantResult?.items ?? []) as Array<Record<string, unknown>>)
        .map((item) => (typeof item.url === "string" ? item.url : ""))
        .filter(Boolean)
        .slice(0, 3);
      if (urls.length) {
        return [
          "抓取高相关网页作为证据并整理回答：",
          ...urls,
          latestAssistantResult?.query || lastUserMessage ? `原始问题：${latestAssistantResult?.query || lastUserMessage}` : "",
        ]
          .filter(Boolean)
          .join("\n");
      }
    }
    if (action.includes("解析") || normalized.includes("pdf")) {
      return withConversationContext(`我想执行建议动作「${action}」。请基于当前证据缺口指出需要解析哪些 PDF/论文、还缺哪些路径或 URL；如果信息足够，请生成解析 PDF 并入库的确认卡。`);
    }
    if (action.includes("检索词") || action.includes("搜索词") || normalized.includes("query")) {
      return withConversationContext(`我想执行建议动作「${action}」。请基于当前未命中的问题生成 3-5 个更具体检索词，说明每个检索词针对的机制/证据缺口，并推荐一个继续检索 SQL 知识库。`);
    }
    if (action.includes("文献服务") || action.includes("MCP") || normalized.includes("literature")) {
      return withConversationContext(`我想执行建议动作「${action}」。请检查或解释当前文献服务/MCP/外部检索能力状态，告诉我哪些能力 ready、limited 或 unavailable，以及如何恢复。`);
    }
    if (action.includes("Web Search") || action.includes("联网") || normalized.includes("web")) {
      const query = compactToolQuery(latestAssistantResult?.query || lastUserMessage || action);
      return `联网搜索：${query || action}`;
    }
    return withConversationContext(`请基于当前对话上下文继续执行建议动作「${action}」，并说明它会使用哪些知识库片段、run/audit 数据或外部工具。`);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = input.trim();
    if (!value || isBusy) return;
    setInput("");
    setMessages((items) => [...items, { id: makeId("user"), role: "user", text: value }]);
    setProgressSteps([{ phase: "submitted", message: "已发送问题，准备进入项目 AI 路由。" }]);
    setStreamingText("");
    setIsAnswering(true);
    const request: ResearchChatTurnRequest = {
      session_id: sessionId,
      message: value,
      context: {
        page: "/project-chat",
        page_path: "/project-chat",
        mode: "project_help",
        language: "zh",
        run_id: activeRunId || undefined,
        project_goal: scopedRun?.request.research_goal,
        selected_hypothesis_index: scopedHypothesis ? scopedHypothesisIndex : undefined,
        hypothesis_index: scopedHypothesis ? scopedHypothesisIndex : undefined,
        hypothesis_title: scopedHypothesis?.title,
        hypothesis_summary: scopedHypothesis?.summary,
      },
    };
    const streamedProgress: ResearchChatProgressEvent[] = [];
    let streamedAnswer = "";
    let sawStreamEvent = false;
    const handleProgress = (step: ResearchChatProgressEvent) => {
      sawStreamEvent = true;
      if (step.phase === "answer_delta" && step.delta) {
        streamedAnswer += step.delta;
        setStreamingText(streamedAnswer);
        return;
      }
      streamedProgress.push(step);
      setProgressSteps((items) => [...items.filter((item) => item.phase !== step.phase), step].slice(-8));
    };
    try {
      let response;
      try {
        response = await streamResearchChatTurn(request, {
          onSession: (nextSessionId) => {
            sawStreamEvent = true;
            setSessionId(nextSessionId);
          },
          onProgress: handleProgress,
        });
      } catch (streamError) {
        if (sawStreamEvent) throw streamError;
        handleProgress({ phase: "stream_fallback", message: "当前后端流式接口不可用，已回退到同步问答。" });
        response = await sendResearchChatTurn(request);
      }
      setSessionId(response.session_id);
      appendAssistant(response.assistant_message, streamedProgress);
    } catch {
      appendAssistant({ kind: "error", text: "项目问答暂时不可用，请确认后端服务正在运行后再试。" });
    } finally {
      setIsAnswering(false);
      setProgressSteps([]);
      setStreamingText("");
    }
  };

  const handleConfirm = async (proposal: ResearchChatActionProposal) => {
    if (!proposal.approvalScope) return;
    setExecutingActionId(proposal.actionId);
    try {
      const response = await confirmResearchChatAction(proposal.actionId, {
        approval: {
          confirmed: true,
          scope: proposal.approvalScope,
          reason: "User confirmed Project AI action.",
        },
      });
      setSessionId(response.session_id);
      appendAssistant(response.assistant_message);
    } catch {
      appendAssistant({ kind: "error", text: "任务未能执行。请检查输入、后端服务和运行准备状态后重试。" });
    } finally {
      setExecutingActionId(null);
    }
  };

  const handleCancel = async (proposal: ResearchChatActionProposal) => {
    setExecutingActionId(proposal.actionId);
    try {
      const response = await cancelResearchChatAction(proposal.actionId);
      setSessionId(response.session_id);
      appendAssistant(response.assistant_message);
    } catch {
      appendAssistant({ kind: "status", text: "已取消当前确认卡片。" });
    } finally {
      setExecutingActionId(null);
    }
  };

  const handleToolAction = async (action: ProjectToolAction) => {
    if (isBusy) return;
    setPreparingToolActionId(action.id);
    setProgressSteps([{ phase: "tool_authorization", message: `已选择「${action.label}」，正在生成工具确认卡。` }]);
    setMessages((items) => [...items, { id: makeId("user"), role: "user", text: action.userMessage }]);
    try {
      const response = await sendResearchChatTurn({
        session_id: sessionId,
        message: action.prompt,
        context: {
          page: "/project-chat",
          page_path: "/project-chat",
          mode: "project_help",
          language: "zh",
          run_id: activeRunId || undefined,
          project_goal: scopedRun?.request.research_goal,
          selected_hypothesis_index: scopedHypothesis ? scopedHypothesisIndex : undefined,
          hypothesis_index: scopedHypothesis ? scopedHypothesisIndex : undefined,
          hypothesis_title: scopedHypothesis?.title,
          hypothesis_summary: scopedHypothesis?.summary,
        },
      });
      setSessionId(response.session_id);
      appendAssistant(response.assistant_message);

      const proposal = response.assistant_message.proposal;
      if (action.autoConfirm && proposal?.approvalScope === action.expectedApprovalScope) {
        setExecutingActionId(proposal.actionId);
        const confirmed = await confirmResearchChatAction(proposal.actionId, {
          approval: {
            confirmed: true,
            scope: proposal.approvalScope,
            reason: `User clicked adaptive Project AI tool authorization: ${action.label}.`,
          },
        });
        setSessionId(confirmed.session_id);
        appendAssistant(confirmed.assistant_message);
      }
    } catch {
      appendAssistant({ kind: "error", text: "工具授权未能完成。请检查后端服务、工具可用性或改用手动确认卡。" });
    } finally {
      setPreparingToolActionId(null);
      setExecutingActionId(null);
      setProgressSteps([]);
    }
  };

  return (
    <div className="page-stack project-knowledge-page">
      <PageHeader
        kicker="Open Co-Scientist"
        title={scopedHypothesis ? "项目 AI 假设分析" : "问项目如何使用"}
        description={
          scopedHypothesis
            ? `当前聚焦：#${scopedHypothesisIndex + 1} ${scopedHypothesis.title}。可以继续追问实验、反证、证据缺口和分析路径。`
            : "研究员可以直接询问项目功能、运行步骤、页面职责和能力边界。普通问答会先检索 SQL 知识库，再结合模型生成回答。"
        }
      />
      <ProjectAiPolicyBar
        policy={actionPolicy}
        status={actionPolicyStatus}
        onChange={handleActionPolicyChange}
      />

      <section className="project-chat-layout">
        <section className="project-chat-surface" aria-label="项目问答消息流">
          <div className="project-chat-messages" aria-live="polite">
            {messages.map((message) => (
              <article key={message.id} className={classNames("project-chat-message", message.role, message.assistant?.kind === "error" && "error")}>
                {message.role === "assistant" ? <MarkdownText text={message.text} /> : <p>{message.text}</p>}
                {message.assistant?.result ? (
                  <ProjectChatResult
                    assistant={message.assistant}
                    lastUserMessage={lastUserMessage}
                    onNextAction={(action) => stagePrompt(buildNextActionPrompt(action))}
                    onToolAction={handleToolAction}
                    preparingToolActionId={preparingToolActionId}
                    busy={isBusy}
                  />
                ) : null}
                {message.assistant?.proposal ? (
                  <ProjectActionProposalCard
                    proposal={message.assistant.proposal}
                    busy={executingActionId === message.assistant.proposal.actionId}
                    onConfirm={handleConfirm}
                    onCancel={handleCancel}
                  />
                ) : null}
                {message.progress?.length ? <ProjectChatProgress steps={message.progress} compact /> : null}
                {message.role === "assistant" ? (
                  <div className="project-chat-meta">
                    <span className={classNames("status-chip", message.assistant?.kind !== "error" && "ok", message.assistant?.kind === "error" && "error")}>
                      {message.assistant?.kind === "error" ? "能力受限" : "已查询项目知识"}
                    </span>
                    <button className="icon-copy-button" type="button" aria-label="复制回答">
                      <Copy size={14} />
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
            {isAnswering ? (
              <article className="project-chat-message assistant" role="status" aria-busy="true">
                <Loader2 size={16} className="spin" />
                <p>正在检索 SQL 知识库并调用模型...</p>
                {streamingText ? (
                  <div className="project-chat-streaming-answer">
                    <MarkdownText text={streamingText} />
                  </div>
                ) : null}
                <ProjectChatProgress steps={progressSteps} />
              </article>
            ) : null}
          </div>

          <div className="starter-prompt-row" aria-label="常用问题">
            {starterPrompts.map((prompt) => (
              <button type="button" key={prompt} onClick={() => stagePrompt(buildStarterPrompt(prompt))}>
                {prompt}
              </button>
            ))}
          </div>

          <form className="project-chat-composer" onSubmit={handleSubmit}>
            <label htmlFor="project-chat-input">询问项目功能、运行步骤、页面职责</label>
            <textarea
              ref={inputRef}
              id="project-chat-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              rows={2}
              placeholder="例如：我想启动文献支撑的假设生成，需要准备什么？"
              disabled={isBusy}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="project-chat-composer-actions">
              <span>Enter 换行，Ctrl+Enter 发送。</span>
              <button className="button-primary" type="submit" disabled={!input.trim() || isBusy} aria-busy={isBusy} aria-label="发送项目问答">
                {isAnswering ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
                发送
              </button>
            </div>
          </form>
        </section>
      </section>
    </div>
  );
}

function ProjectAiPolicyBar({
  policy,
  status,
  onChange,
}: {
  policy: CommandPermissionPolicy | null;
  status: "loading" | "ready" | "saving" | "error";
  onChange: (mode: CommandPermissionMode) => void;
}) {
  const activeMode = policy?.mode ?? "request_approval";
  return (
    <section className="project-ai-policy-bar" aria-label="项目 AI 执行策略">
      <div className="project-ai-policy-copy">
        <ShieldCheck size={16} />
        <div>
          <strong>项目 AI 执行策略</strong>
          <span>
            {status === "loading"
              ? "正在读取权限策略"
              : status === "saving"
                ? "正在保存策略"
                : status === "error"
                  ? "策略读取或保存失败"
                  : `当前：${policy?.label ?? "请求审批"}`}
          </span>
        </div>
      </div>
      <div className="project-ai-policy-modes" role="group" aria-label="切换项目 AI 执行策略">
        {projectAiPolicyModes.map((item) => (
          <button
            key={item.mode}
            type="button"
            className={classNames("button-secondary", activeMode === item.mode && "is-selected")}
            disabled={status === "loading" || status === "saving"}
            aria-pressed={activeMode === item.mode}
            title={item.description}
            onClick={() => onChange(item.mode)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {policy?.source ? <span className="project-ai-policy-source">{policy.source}</span> : null}
    </section>
  );
}

function ProjectChatResult({
  assistant,
  lastUserMessage,
  onNextAction,
  onToolAction,
  preparingToolActionId,
  busy,
}: {
  assistant: ResearchChatAssistantMessage;
  lastUserMessage?: string;
  onNextAction: (action: string) => void;
  onToolAction: (action: ProjectToolAction) => void;
  preparingToolActionId: string | null;
  busy: boolean;
}) {
  const result = assistant.result;
  const [evidenceTranslations, setEvidenceTranslations] = useState<Record<string, EvidenceTranslationState>>({});
  const handleTranslateEvidence = async (key: string, text: string) => {
    const source = text.trim();
    if (!source) return;
    setEvidenceTranslations((items) => ({ ...items, [key]: { status: "loading" } }));
    try {
      const translated = await translateEvidenceText({
        model_name: "deepseek/deepseek-chat",
        text: source.slice(0, 5000),
        target_language: "zh-Hans",
        provider: "auto",
      });
      setEvidenceTranslations((items) => ({
        ...items,
        [key]: {
          status: "complete",
          text: translated.translation,
          provider: translated.provider,
        },
      }));
    } catch (error) {
      setEvidenceTranslations((items) => ({
        ...items,
        [key]: {
          status: "error",
          error: error instanceof Error ? error.message : "翻译暂时不可用。",
        },
      }));
    }
  };
  if (!result) return null;
  const capabilityCount = result.capabilities?.length ?? Object.values(result.capabilityGroups ?? {}).flat().length;
  const toolActions = inferProjectToolActions(assistant, lastUserMessage);
  return (
    <div className="project-chat-result">
      {result.title ? <strong>{result.title}</strong> : null}
      {result.modeBoundary ? <p>{result.modeBoundary}</p> : null}
      {capabilityCount ? <p>当前项目帮助上下文包含 {capabilityCount} 项任务入口，写入型动作会按执行策略处理。</p> : null}
      {toolActions.length ? (
        <div className="project-tool-actions" aria-label="可授权工具动作">
          {toolActions.map((action) => {
            const actionBusy = preparingToolActionId === action.id;
            return (
              <button
                className={classNames("button-primary", actionBusy && "is-loading")}
                type="button"
                key={action.id}
                disabled={busy}
                aria-busy={actionBusy}
                title={action.description}
                onClick={() => onToolAction(action)}
              >
                {actionBusy ? <Loader2 size={16} className="spin" /> : <ShieldCheck size={16} />}
                {actionBusy ? "准备授权中" : action.label}
              </button>
            );
          })}
        </div>
      ) : null}
      {result.hypotheses?.length ? (
        <div className="hypothesis-brief-list">
          {result.hypotheses.map((hypothesis) => (
            <article key={`${hypothesis.index}-${hypothesis.title}`}>
              <header>
                <strong>#{hypothesis.index + 1} {hypothesis.title}</strong>
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
      {result.experiments?.length ? (
        <div className="project-evidence-list" aria-label="实验计划草案">
          {result.experiments.slice(0, 4).map((experiment) => (
            <article key={`${experiment.index}-${experiment.title}`}>
              <strong>
                实验 #{experiment.hypothesisIndex !== undefined ? experiment.hypothesisIndex + 1 : experiment.index + 1} {experiment.title}
              </strong>
              {experiment.experimentPlan ? <MarkdownText text={experiment.experimentPlan} compact /> : null}
              {experiment.falsificationTests?.length ? <p>失败条件：{experiment.falsificationTests.slice(0, 3).join("；")}</p> : null}
            </article>
          ))}
        </div>
      ) : null}
      {result.reports?.length ? (
        <div className="project-evidence-list" aria-label="报告草稿结构">
          {result.reports.slice(0, 2).map((report) => (
            <article key={report.title}>
              <strong>{report.title}</strong>
              {report.summary ? <p>{report.summary}</p> : null}
              {report.sections?.length ? <p>章节：{report.sections.slice(0, 6).join("；")}</p> : null}
            </article>
          ))}
        </div>
      ) : null}
      {result.items?.length ? (
        <div className="project-evidence-list" aria-label="搜索和证据线索">
          {result.items.slice(0, 5).map((item, index) => {
            const record = item as Record<string, unknown>;
            const title = String(record.title || record.chunk_title || `线索 ${index + 1}`);
            const url = typeof record.url === "string" ? record.url : "";
            const summary = String(record.evidence_summary || record.snippet || record.text_preview || "");
            const translationKey = `${title}-${index}`;
            const translation = evidenceTranslations[translationKey];
            return (
              <article key={translationKey}>
                <strong>{title}</strong>
                {url ? (
                  <a href={url} target="_blank" rel="noreferrer">
                    {url}
                  </a>
                ) : null}
                {summary ? <p>{summary}</p> : null}
                {summary ? (
                  <div className="evidence-translation-row">
                    <button
                      type="button"
                      className="evidence-translate-button"
                      disabled={translation?.status === "loading"}
                      onClick={() => handleTranslateEvidence(translationKey, summary)}
                    >
                      {translation?.status === "loading" ? <Loader2 size={14} className="spin" /> : <Languages size={14} />}
                      {translation?.status === "complete" ? "重新翻译" : "翻译为中文"}
                    </button>
                    {translation?.provider ? <span>来源：{translation.provider === "microsoft" ? "Microsoft Translator" : "模型翻译"}</span> : null}
                  </div>
                ) : null}
                {translation?.status === "complete" && translation.text ? (
                  <p className="evidence-translation">{translation.text}</p>
                ) : null}
                {translation?.status === "error" ? <p className="evidence-translation error">{translation.error}</p> : null}
              </article>
            );
          })}
        </div>
      ) : null}
      {result.evidenceSourceExplanation || result.rankingCaveat ? (
        <div className="project-evidence-list" aria-label="证据来源与排序边界">
          {result.evidenceSourceExplanation ? (
            <article>
              <strong>当前证据如何获得</strong>
              <p>{result.evidenceSourceExplanation}</p>
            </article>
          ) : null}
          {result.rankingCaveat ? (
            <article>
              <strong>为什么有反证仍可能是 winner</strong>
              <p>{result.rankingCaveat}</p>
            </article>
          ) : null}
        </div>
      ) : null}
      {result.nextActions?.length ? (
        <div className="chat-next-actions">
          {result.nextActions.slice(0, 4).map((item) => (
            <button type="button" key={item} onClick={() => onNextAction(item)}>
              {item}
            </button>
          ))}
        </div>
      ) : null}
      <div className="project-chat-meta">
        {result.groundingBoundary ? (
          <span className="source-chip">
            {formatBackendText(result.groundingBoundary)}
          </span>
        ) : null}
        {result.runId ? (
          <span className="source-chip">
            相关运行
          </span>
        ) : null}
      </div>
    </div>
  );
}

function ProjectChatProgress({
  steps,
  compact = false,
}: {
  steps: ResearchChatProgressEvent[];
  compact?: boolean;
}) {
  if (!steps.length) return null;
  const visibleSteps = compact ? steps.slice(-5) : steps;
  return (
    <div className={classNames("project-chat-progress", compact && "compact")}>
      <header>
        <CheckCircle2 size={14} />
        <strong>可审计过程</strong>
        <span>展示路由、检索和模型调用阶段；不展示模型隐式推理。</span>
      </header>
      <ol>
        {visibleSteps.map((step, index) => (
          <li key={`${step.phase}-${index}`}>
            <span>{formatBackendText(step.phase)}</span>
            <p>{step.message}</p>
            <small>
              {typeof step.knowledgeHitCount === "number" ? `命中 ${step.knowledgeHitCount} 条` : ""}
              {step.modelName ? `${typeof step.knowledgeHitCount === "number" ? " · " : ""}${step.modelName}` : ""}
              {typeof step.elapsedMs === "number" ? `${step.knowledgeHitCount !== undefined || step.modelName ? " · " : ""}${Math.max(0, Math.round(step.elapsedMs / 1000))}s` : ""}
            </small>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ProjectActionProposalCard({
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
        <button
          className={classNames("button-primary", busy && "is-loading")}
          type="button"
          disabled={busy || !proposal.approvalScope}
          aria-busy={busy}
          onClick={() => onConfirm(proposal)}
        >
          {busy ? "执行中" : "允许执行"}
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
            <dd>{proposal.approvalScope || "需要明确授权范围"}</dd>
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
