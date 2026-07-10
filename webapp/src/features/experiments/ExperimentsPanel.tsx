import { Link } from "react-router-dom";
import { EmptyState } from "../../components/feedback/states";
import { createExperimentPlan, getResearchAutopilot, startResearchAutopilot } from "../../lib/api/workbench";
import { copy, formatBackendText } from "../../lib/formatters/workbench";
import { mapRunToWorkspaceView } from "../../lib/view-models/workbench";
import type { ResearchLoopState, RunRecord } from "../../types/workbench";
import { useEffect, useState } from "react";
import { RemoteWorkspacePanel } from "./RemoteWorkspacePanel";
import { WebTerminalPanel, type WebTerminalPreset } from "./WebTerminalPanel";

export function ExperimentsPanel({
  record,
  selectedIndex = 0,
}: {
  record: RunRecord | null;
  selectedIndex?: number;
}) {
  const [terminalPreset, setTerminalPreset] = useState<WebTerminalPreset | null>(null);
  const [planState, setPlanState] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [planResult, setPlanResult] = useState<Record<string, unknown> | null>(null);
  const [loopState, setLoopState] = useState<ResearchLoopState | null>(record?.research_loop ?? null);
  const [loopBusy, setLoopBusy] = useState(false);
  const [loopError, setLoopError] = useState(false);

  useEffect(() => {
    setLoopState(record?.research_loop ?? null);
  }, [record?.research_loop]);
  useEffect(() => {
    if (!record || !["queued", "running", "reranking"].includes(loopState?.status ?? "")) return undefined;
    let cancelled = false;
    const refresh = async () => {
      try {
        const response = await getResearchAutopilot(record.run_id);
        if (!cancelled) setLoopState(response.research_loop);
      } catch {
        // Preserve the last durable snapshot and retry on the next interval.
      }
    };
    const timer = window.setInterval(() => void refresh(), 1200);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [record?.run_id, loopState?.status]);

  if (!record) {
    return (
      <EmptyState
        title="先选择一个候选假设"
        description="生成并选择候选假设后，这里会组织可证伪实验、失败条件和评估指标。"
      />
    );
  }
  const workspace = mapRunToWorkspaceView(record);
  const selectedHypothesis = workspace.hypotheses[selectedIndex] ?? workspace.hypotheses[0];
  const createPlan = async () => {
    if (!selectedHypothesis) return;
    setPlanState("loading");
    try {
      const response = await createExperimentPlan(record.run_id, record.run_id, selectedIndex);
      setPlanResult(response.experiment_plan);
      setPlanState("success");
    } catch {
      setPlanState("error");
    }
  };
  const startLoop = async () => {
    if (loopState) return;
    setLoopBusy(true);
    setLoopError(false);
    try {
      const response = await startResearchAutopilot(record.run_id, {
        mode: "guarded",
        auto_evidence: true,
        auto_plan: true,
        auto_execute: false,
        auto_interpret: false,
        auto_rerank: true,
        continue_on_limited_evidence: true,
        grants: [{
          confirmed: true,
          scope: "mcp.literature_review",
          reason: "Researcher started the guarded evidence expansion loop.",
          max_uses: 1,
        }],
      });
      setLoopState(response.research_loop);
    } catch {
      setLoopError(true);
    } finally {
      setLoopBusy(false);
    }
  };

  return (
    <div className="experiment-page-stack">
      <section className="task-surface">
        <header className="task-header">
          <div>
            <span>实验</span>
            <h2>{selectedHypothesis ? `验证：${selectedHypothesis.title}` : "先选择一个候选假设"}</h2>
            <p>{selectedHypothesis?.experimentPlan ?? "等待候选假设。"}</p>
          </div>
          <div className="task-actions">
            <button className="button-primary" type="button" onClick={() => void createPlan()} disabled={!selectedHypothesis || planState === "loading"} aria-busy={planState === "loading"}>
              {planState === "loading" ? "正在生成实验计划" : planState === "success" ? "已保存实验计划" : "生成可证伪实验"}
            </button>
            <button className="button-secondary" type="button" onClick={() => void startLoop()} disabled={!selectedHypothesis || loopBusy || Boolean(loopState)} aria-busy={loopBusy}>
              {loopBusy ? "正在创建闭环" : loopState?.status ? `闭环：${loopState.status}` : "创建自动研究闭环"}
            </button>
            <Link to={`/projects/${record.run_id}/hypotheses`}>查看假设</Link>
            <Link to={`/projects/${record.run_id}/reports`}>写入报告</Link>
          </div>
        </header>
        <div className="task-list">
          <article>
            <strong>可证伪条件</strong>
            <span>如果关键观测无法区分候选机制，则该假设不应进入昂贵验证。</span>
          </article>
          <article>
            <strong>评估输出</strong>
            <span>实验计划应产生可复查指标、负面结果解释和失败边界。</span>
          </article>
          <article>
            <strong>文献边界</strong>
            <span>{record.request.demo_mode ? "这是历史合成记录，只供回看，不再作为新的实验设计入口。" : "没有真实文献证据时，应把结果标注为模型生成提案。"}</span>
          </article>
        </div>
      </section>

      {planState === "error" ? <div className="control-feedback error" role="alert">实验计划生成失败，请稍后重试。</div> : null}
      {loopError ? <div className="control-feedback error" role="alert">闭环未能启动；已有任务请在 Lattice 中恢复，或稍后重试。</div> : null}
      {loopState ? <ResearchLoopResult state={loopState} /> : null}
      {planResult ? <ExperimentPlanResult plan={planResult} /> : null}

      <RemoteWorkspacePanel
        projectId={record.run_id}
        onTerminalPreset={(preset) => setTerminalPreset({ ...preset, revision: Date.now() })}
      />

      <WebTerminalPanel preset={terminalPreset} />
    </div>
  );
}

function ResearchLoopResult({ state }: { state: ResearchLoopState }) {
  const stages = state.stages ?? [];
  return (
    <section className="task-surface" aria-label="自动研究闭环状态">
      <header className="task-header">
        <div>
          <span>Research Autopilot</span>
          <h2>{state.status === "awaiting_approval" ? "等待限定授权" : state.status === "awaiting_human" ? "等待研究者判断" : "闭环任务已建立"}</h2>
          <p>安全的检索、解析、证据整理和实验计划可自动推进；远程计算、低置信结论与冲突证据会停下来等待你。</p>
        </div>
      </header>
      <div className="task-list">
        {stages.map((stage) => (
          <article key={stage.id}>
            <strong>{stage.id}</strong>
            <span>{stage.summary || stage.status}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function ExperimentPlanResult({ plan }: { plan: Record<string, unknown> }) {
  const listValue = (key: string) => {
    const value = plan[key];
    return Array.isArray(value) ? value.map((item) => formatBackendText(String(item))).filter(Boolean) : [];
  };
  const falsificationTests = listValue("falsificationTests");
  const missingEvidence = listValue("missingEvidence");
  return (
    <section className="task-surface">
      <header className="task-header">
        <div>
          <span>结构化实验计划</span>
          <h2>{formatBackendText(String(plan.title || "可证伪实验设计草案"))}</h2>
          <p>{formatBackendText(String(plan.summary || "实验设计已从当前 run 审计上下文生成。"))}</p>
        </div>
      </header>
      <div className="task-list">
        <article>
          <strong>实验计划</strong>
          <span>{formatBackendText(String(plan.experimentPlan || "定义变量、对照条件、指标和失败边界。"))}</span>
        </article>
        <article>
          <strong>证伪条件</strong>
          <span>{falsificationTests.join("；") || "尚未提取显式证伪条件。"}</span>
        </article>
        <article>
          <strong>待补证据</strong>
          <span>{missingEvidence.join("；") || "当前结果没有额外列出证据缺口。"}</span>
        </article>
      </div>
    </section>
  );
}
