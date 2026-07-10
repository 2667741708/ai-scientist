import { FileText, MessageSquareText } from "lucide-react";
import { Link } from "react-router-dom";
import { MarkdownText } from "../../components/content/MarkdownText";
import { EmptyState } from "../../components/feedback/states";
import { mapRunToWorkspaceView } from "../../lib/view-models/workbench";
import type { RunRecord } from "../../types/workbench";

function buildFormattedDraft(record: RunRecord, selectedIndex: number, selectedHypothesis: ReturnType<typeof mapRunToWorkspaceView>["hypotheses"][number] | undefined) {
  if (!selectedHypothesis) return "暂无可整理的候选假设。";
  const evidenceBoundary = record.request.demo_mode
    ? "Demo simulation，仅用于 UI/流程/schema 检查，不能作为真实科学证据。"
    : record.request.literature_review
      ? "Literature-grounded workflow；仍需逐条核对 citation/source metadata、support level 和 parsed fulltext。"
      : "Live model workflow without literature review；必须标注为 limited / ungrounded proposal。";
  return [
    `## 候选假设 #${selectedIndex + 1}`,
    "",
    `**标题：** ${selectedHypothesis.title}`,
    "",
    "### 技术假设",
    selectedHypothesis.raw.text || selectedHypothesis.summary,
    "",
    "### 通俗解释",
    selectedHypothesis.raw.explanation || selectedHypothesis.summary,
    "",
    "### 证据边界",
    evidenceBoundary,
    "",
    "### 证据诊断",
    ...selectedHypothesis.evidenceDiagnostics.map((item) => `- **${item.label}：** ${item.value}`),
    "",
    "### 可证伪实验设计",
    selectedHypothesis.raw.experiment || selectedHypothesis.experimentPlan,
    "",
    "### 下一步",
    "- 优先补齐 marked warning/error 的证据来源。",
    "- 在实验页明确可观测变量、对照组、失败条件和最小验证路径。",
    "- 报告定稿前再次打开 Elo 排序依据，确认该假设确实优于其他候选。",
  ].join("\n");
}

export function ReportsPanel({
  record,
  selectedIndex = 0,
}: {
  record: RunRecord | null;
  selectedIndex?: number;
}) {
  if (!record) {
    return (
      <EmptyState
        title="先完成假设生成"
        description="完成研究工作区中的假设生成后，报告草稿会在这里组织。"
      />
    );
  }
  const workspace = mapRunToWorkspaceView(record);
  const selectedHypothesis = workspace.hypotheses[selectedIndex] ?? workspace.hypotheses[0];
  const formattedDraft = buildFormattedDraft(record, selectedIndex, selectedHypothesis);

  return (
    <section className="task-surface">
      <header className="task-header">
        <div>
          <span>报告</span>
          <h2>研究草稿</h2>
          <p>把候选假设、实验计划和局限性整理成可审查输出。</p>
        </div>
        <Link className="button-primary" to={`/project-chat?run=${record.run_id}&hypothesis=${selectedIndex}&intent=draft_report`}>
          <MessageSquareText size={16} />
          调用项目 AI 排版草稿
        </Link>
      </header>
      <div className="report-draft">
        <div className="section-kicker">
          <FileText size={14} />
          本地结构化草稿
        </div>
        <MarkdownText text={formattedDraft} />
      </div>
    </section>
  );
}
