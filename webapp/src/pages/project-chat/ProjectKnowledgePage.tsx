import { Copy, Loader2, Send } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { MarkdownText } from "../../components/content/MarkdownText";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { useWorkbench } from "../../features/runs/workbench-context";
import { sendResearchChatTurn } from "../../lib/api/researchChat";
import { classNames, formatBackendText } from "../../lib/formatters/workbench";
import { mapRunToWorkspaceView } from "../../lib/view-models/workbench";
import type { ResearchChatAssistantMessage } from "../../types/research-chat";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  assistant?: ResearchChatAssistantMessage;
};

const starterPrompts = [
  "这个项目现在能做什么？",
  "我想生成候选假设，应该从哪里开始？",
  "演示模式、实时模型和文献支撑有什么区别？",
  "Elo 锦标赛排名如何审计？",
];

function makeId(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function ProjectKnowledgePage() {
  const [searchParams] = useSearchParams();
  const { history } = useWorkbench();
  const scopedRunId = searchParams.get("run") || "";
  const scopedHypothesisIndex = Number(searchParams.get("hypothesis") ?? "");
  const scopedIntent = searchParams.get("intent") || "";
  const scopedRun = useMemo(() => history.find((record) => record.run_id === scopedRunId), [history, scopedRunId]);
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
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [scopedPromptApplied, setScopedPromptApplied] = useState(false);
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

  const appendAssistant = (assistant: ResearchChatAssistantMessage) => {
    setMessages((items) => [...items, { id: makeId("assistant"), role: "assistant", text: assistant.text, assistant }]);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = input.trim();
    if (!value || isAnswering) return;
    setInput("");
    setMessages((items) => [...items, { id: makeId("user"), role: "user", text: value }]);
    setIsAnswering(true);
    try {
      const response = await sendResearchChatTurn({
        session_id: sessionId,
        message: value,
        context: {
          page: "/project-chat",
          page_path: "/project-chat",
          mode: "project_help",
          language: "zh",
          run_id: scopedRun?.run_id,
          project_goal: scopedRun?.request.research_goal,
          selected_hypothesis_index: scopedHypothesis ? scopedHypothesisIndex : undefined,
          hypothesis_index: scopedHypothesis ? scopedHypothesisIndex : undefined,
          hypothesis_title: scopedHypothesis?.title,
          hypothesis_summary: scopedHypothesis?.summary,
        },
      });
      setSessionId(response.session_id);
      appendAssistant(response.assistant_message);
    } catch {
      appendAssistant({ kind: "error", text: "项目问答暂时不可用，请确认后端服务正在运行后再试。" });
    } finally {
      setIsAnswering(false);
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

      <section className="project-chat-layout">
        <section className="project-chat-surface" aria-label="项目问答消息流">
          <div className="project-chat-messages" aria-live="polite">
            {messages.map((message) => (
              <article key={message.id} className={classNames("project-chat-message", message.role, message.assistant?.kind === "error" && "error")}>
                {message.role === "assistant" ? <MarkdownText text={message.text} /> : <p>{message.text}</p>}
                {message.assistant?.result ? <ProjectChatResult assistant={message.assistant} /> : null}
                {message.assistant?.proposal ? (
                  <div className="status-banner warning">
                    这是需要确认的动作。请到“研究流程”工作台执行，以便结果同步到右侧结构化面板。
                  </div>
                ) : null}
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
              </article>
            ) : null}
          </div>

          <div className="starter-prompt-row" aria-label="常用问题">
            {starterPrompts.map((prompt) => (
              <button type="button" key={prompt} onClick={() => setInput(prompt)}>
                {prompt}
              </button>
            ))}
          </div>

          <form className="project-chat-composer" onSubmit={handleSubmit}>
            <label htmlFor="project-chat-input">询问项目功能、运行步骤、页面职责</label>
            <textarea
              id="project-chat-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              rows={2}
              placeholder="例如：我想启动文献支撑的假设生成，需要准备什么？"
              disabled={isAnswering}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="project-chat-composer-actions">
              <span>Enter 换行，Ctrl+Enter 发送。</span>
              <button className="button-primary" type="submit" disabled={!input.trim() || isAnswering} aria-busy={isAnswering} aria-label="发送项目问答">
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

function ProjectChatResult({ assistant }: { assistant: ResearchChatAssistantMessage }) {
  const result = assistant.result;
  if (!result) return null;
  const capabilityCount = result.capabilities?.length ?? Object.values(result.capabilityGroups ?? {}).flat().length;
  return (
    <div className="project-chat-result">
      {result.title ? <strong>{result.title}</strong> : null}
      {result.modeBoundary ? <p>{result.modeBoundary}</p> : null}
      {capabilityCount ? <p>当前项目帮助上下文包含 {capabilityCount} 项任务入口，写入型动作会先确认。</p> : null}
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
      {result.nextActions?.length ? (
        <div className="chat-next-actions">
          {result.nextActions.slice(0, 4).map((item) => (
            <span key={item}>{item}</span>
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
