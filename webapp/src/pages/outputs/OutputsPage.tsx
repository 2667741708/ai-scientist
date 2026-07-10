import { Download, ExternalLink, FileText, FlaskConical, Info, Link2, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../../components/feedback/states";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { useWorkbench } from "../../features/runs/workbench-context";
import { classNames, copy, formatBackendText, getVisibleProductRuns } from "../../lib/formatters/workbench";
import { mapRunToHypothesisViews, mapRunToOutputs } from "../../lib/view-models/workbench";
import type { HypothesisCardViewModel, OutputViewModel, RunRecord } from "../../types/workbench";

type ReportWorkspaceItem = {
  output: OutputViewModel;
  run: RunRecord;
  hypotheses: HypothesisCardViewModel[];
};

function uniqueBy<T>(items: T[], getKey: (item: T) => string) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = getKey(item);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function outputKindLabel(kind: OutputViewModel["kind"]) {
  if (kind === "experiment") return "实验计划";
  if (kind === "report") return "报告草稿";
  return "发现";
}

function OutputKindIcon({ kind }: { kind: OutputViewModel["kind"] }) {
  const Icon = kind === "experiment" ? FlaskConical : kind === "report" ? FileText : Sparkles;
  return <Icon size={16} />;
}

function buildDraftText(item: ReportWorkspaceItem) {
  const topHypothesis = item.hypotheses[0];
  const evidenceBoundary = item.run.request.demo_mode
    ? "Demo simulation: 该草稿只能用于 UI、流程和 schema 检查，不能作为科学证据。"
    : item.run.request.literature_review
      ? "Literature-grounded workflow: 需要继续核对每条 citation/source metadata 的可访问性和 support level。"
      : "Live model workflow without literature review: 输出应标记为 limited / ungrounded，后续必须补证据。";

  return [
    `# ${item.output.title}`,
    "",
    `研究目标：${item.run.request.research_goal}`,
    "",
    `核心摘要：${item.output.summary}`,
    "",
    topHypothesis ? `入选假设：${topHypothesis.title}` : "入选假设：尚未选择。",
    topHypothesis ? `实验验证：${topHypothesis.experimentPlan}` : "实验验证：等待候选假设生成后补齐。",
    "",
    `证据边界：${evidenceBoundary}`,
    "",
    "局限性与下一步：",
    "- 核对证据是否来自 parsed fulltext、metadata 还是模型潜在知识。",
    "- 明确负面结果、替代解释和最小可行验证路径。",
    "- 导出前检查 Elo 排名和 review feedback 是否支持当前排序。",
  ].join("\n");
}

function getEvidenceStatus(item: ReportWorkspaceItem) {
  if (item.run.request.demo_mode) return { label: "Demo-only", tone: "warning" as const };
  if (item.run.request.literature_review) return { label: "需核对引用", tone: "ok" as const };
  return { label: "证据不足", tone: "warning" as const };
}

export function OutputsPage() {
  const { history } = useWorkbench();
  const visibleHistory = getVisibleProductRuns(history);
  const activeRun = visibleHistory.find((run) => run.status === "queued" || run.status === "running");
  const reportItems = useMemo(
    () =>
      uniqueBy(
        visibleHistory.flatMap((run) => {
          const hypotheses = mapRunToHypothesisViews(run);
          return mapRunToOutputs(run).map((output) => ({ output, run, hypotheses }));
        }),
        (item) => item.output.id,
      ),
    [visibleHistory],
  );
  const [selectedId, setSelectedId] = useState("");
  const selectedItem = reportItems.find((item) => item.output.id === selectedId) ?? reportItems[0];
  const [draftText, setDraftText] = useState("");
  const [copyStatus, setCopyStatus] = useState("");

  useEffect(() => {
    if (reportItems.length > 0 && !reportItems.some((item) => item.output.id === selectedId)) {
      setSelectedId(reportItems[0].output.id);
    }
  }, [reportItems, selectedId]);

  useEffect(() => {
    if (selectedItem) {
      setDraftText(buildDraftText(selectedItem));
      setCopyStatus("");
    }
  }, [selectedItem?.output.id]);

  const handleCopyDraft = async () => {
    if (!draftText.trim()) return;
    try {
      await navigator.clipboard.writeText(draftText);
      setCopyStatus("草稿已复制，可粘贴到报告或审查记录。");
    } catch {
      setCopyStatus("浏览器没有授予剪贴板权限；草稿仍可在编辑区手动选取。");
    }
  };

  if (reportItems.length === 0) {
    return (
      <div className="page-stack">
        <PageHeader
          kicker="研究产出"
          title={copy.outputs.title}
          actions={
            <button className="info-trigger" type="button" aria-label={copy.outputs.description} data-tooltip={copy.outputs.description}>
              <Info size={16} />
            </button>
          }
        />
        <EmptyState
          title={activeRun ? "研究仍在生成产出" : "还没有研究产出"}
          description={
            activeRun
              ? "当前研究还在运行中；发现、实验计划和报告草稿会在完成后自动聚合到这里。"
              : copy.outputs.empty
          }
          actions={
            activeRun ? (
              <Link className="button-primary" to={`/workspace/${activeRun.run_id}`}>
                返回当前工作区
              </Link>
            ) : (
              <Link className="button-primary" to="/workspace">
                去启动研究
              </Link>
            )
          }
        />
      </div>
    );
  }

  const evidenceStatus = selectedItem ? getEvidenceStatus(selectedItem) : null;
  const topHypothesis = selectedItem?.hypotheses[0];

  return (
    <div className="page-stack">
      <PageHeader
        kicker="研究产出"
        title="报告工作区"
        description="选择发现、实验计划或报告片段，装配成可审查草稿，并在导出前检查证据边界。"
        actions={
          <button className="info-trigger" type="button" aria-label={copy.outputs.description} data-tooltip={copy.outputs.description}>
            <Info size={16} />
          </button>
        }
      />

      <section className="report-workspace" aria-label="报告装配工作区">
        <aside className="report-selection-panel" aria-label="产出选择队列">
          <div className="section-heading compact">
            <div>
              <span className="section-kicker">装配队列</span>
              <h2>待处理产出</h2>
            </div>
            <span className="status-pill neutral">{reportItems.length}</span>
          </div>
          <div className="report-output-list" role="list">
            {reportItems.map((item) => (
              <button
                className={classNames("report-output-row", selectedItem?.output.id === item.output.id && "selected")}
                type="button"
                key={item.output.id}
                onClick={() => setSelectedId(item.output.id)}
                aria-pressed={selectedItem?.output.id === item.output.id}
              >
                <span className="report-output-icon">
                  <OutputKindIcon kind={item.output.kind} />
                </span>
                <span>
                  <strong>{item.output.title}</strong>
                  <small>
                    {outputKindLabel(item.output.kind)} · {formatBackendText(item.run.status)}
                  </small>
                </span>
              </button>
            ))}
          </div>
        </aside>

        <article className="report-editor-panel">
          <header className="report-editor-header">
            <div>
              <div className="card-meta-row">
                <span>{selectedItem ? outputKindLabel(selectedItem.output.kind) : "报告草稿"}</span>
                {evidenceStatus ? <span className={classNames("status-pill", evidenceStatus.tone)}>{evidenceStatus.label}</span> : null}
              </div>
              <h2>{selectedItem?.output.title}</h2>
              <p>{selectedItem?.run.request.research_goal}</p>
            </div>
            <div className="report-editor-actions">
              <button className="button-secondary" type="button" onClick={() => void handleCopyDraft()}>
                <Download size={14} />
                复制草稿
              </button>
              {selectedItem ? (
                <Link className="button-primary" to={selectedItem.output.route}>
                  打开来源
                  <ExternalLink size={14} />
                </Link>
              ) : null}
            </div>
          </header>

          <label className="field-stack report-draft-editor" htmlFor="report-draft-editor">
            <span>可编辑报告草稿</span>
            <textarea
              id="report-draft-editor"
              value={draftText}
              onChange={(event) => setDraftText(event.target.value)}
              rows={18}
              spellCheck={false}
            />
          </label>
          {copyStatus ? <p className="control-feedback" role="status">{copyStatus}</p> : null}
        </article>

        <aside className="report-evidence-panel" aria-label="导出前检查">
          <div className="section-heading compact">
            <div>
              <span className="section-kicker">导出检查</span>
              <h2>证据与限制</h2>
            </div>
          </div>
          <dl className="report-checklist">
            <div>
              <dt>候选假设</dt>
              <dd>{selectedItem?.run.hypotheses.length ?? 0}</dd>
            </div>
            <div>
              <dt>Elo 对局</dt>
              <dd>{selectedItem?.run.tournament_matchups.length ?? 0}</dd>
            </div>
            <div>
              <dt>过程记录</dt>
              <dd>{selectedItem?.run.agent_trace.length ?? 0}</dd>
            </div>
            <div>
              <dt>文献模式</dt>
              <dd>{selectedItem?.run.request.literature_review ? "已请求" : "未启用"}</dd>
            </div>
          </dl>

          <div className="report-side-section">
            <span className="section-kicker">当前入选</span>
            <strong>{topHypothesis?.title ?? "尚未选择假设"}</strong>
            <p>{topHypothesis?.summary ?? "完成一次研究运行后，这里会显示可审查的候选假设摘要。"}</p>
          </div>

          <div className="report-side-section">
            <span className="section-kicker">证据链接</span>
            <div className="report-link-list">
              <Link to="/data">
                <Link2 size={14} />
                检查资料库
              </Link>
              <Link to="/workspace">
                <Link2 size={14} />
                回到假设比较
              </Link>
              {selectedItem ? (
                <Link to={selectedItem.output.route}>
                  <Link2 size={14} />
                  查看来源结果
                </Link>
              ) : null}
            </div>
          </div>
        </aside>
      </section>
    </div>
  );
}
