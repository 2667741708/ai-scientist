import type {
  CitationPdfCandidate,
  Hypothesis,
  HypothesisCardViewModel,
  OutputViewModel,
  ProjectViewModel,
  RunRecord,
  StatusBadgeItem,
  SummaryItem,
  WorkspaceViewModel,
} from "../../types/workbench";
import {
  copy,
  formatBackendText,
  formatRunState,
  formatScore,
  formatSummaryValue,
  getCitationItems,
  getExperimentPlanDisplay,
  getHypothesisDisplay,
  getMetricItems,
  getPhaseLabel,
  getPlanItems,
  getProjectTitle,
  getRunModeLabel,
  getTournamentItems,
  getVisibleProductRuns,
} from "../formatters/workbench";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function countEvidence(run: RunRecord) {
  return run.hypotheses.reduce(
    (total, hypothesis) => total
      + Object.keys(hypothesis.citation_map ?? {}).length
      + (hypothesis.evidence_packet?.item_count ?? 0),
    0,
  );
}

function getGroundingLabel(run: RunRecord) {
  if (run.request.demo_mode) return "历史合成记录";
  if (!run.request.literature_review) return "实时模型提案";
  return countEvidence(run) > 0 ? "已附带文献证据" : "等待文献证据";
}

function getRunErrorRecovery(run: RunRecord) {
  const error = run.error ?? "";
  if (/parse LLM response as JSON|JSON/i.test(error)) {
    return "运行失败：模型结构化输出未通过解析。请进入工作区重试，优先减少候选数或切换到更稳定的非思考模型。";
  }
  if (/certificate|ssl|connect/i.test(error)) {
    return "运行失败：模型或文献服务连接异常。请检查运行准备后重试。";
  }
  if (/timeout|exceeded|stale/i.test(error)) {
    return "运行失败：后台运行超过超时窗口。请进入工作区重新启动。";
  }
  return "运行失败：没有生成可审查假设。请进入工作区调整模型、证据设置或研究目标后重试。";
}

function getNextStep(run: RunRecord) {
  if (run.request.demo_mode) return "这是历史合成记录，仅供回看，不再作为当前研究主线继续运行。";
  if (run.status === "error") return getRunErrorRecovery(run);
  if (run.status === "queued" || run.status === "running") return "等待当前运行完成，然后进入假设比较与实验设计。";
  if (run.hypotheses.length === 0) return "重新生成候选假设，补齐第一轮候选池。";
  if (run.request.literature_review && countEvidence(run) === 0) return "检查文献证据是否完整，再决定是否重新运行。";
  return "检查候选假设与参考文献，然后进入实验设计。";
}

function getRecordStatusValue(record: Record<string, unknown> | undefined, keys: string[]) {
  if (!record) return "";
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string") return value;
    if (typeof value === "boolean") return value ? "passed" : "failed";
  }
  return "";
}

function getSafetyBadge(run: RunRecord): StatusBadgeItem {
  const status = getRecordStatusValue(run.safety_gate, ["status", "result", "decision"]);
  if (/block|fail|reject/i.test(status)) return { label: "安全门未通过", tone: "error" };
  if (/review|warn|needs/i.test(status)) return { label: "需安全复核", tone: "warning" };
  if (/pass|allow|ok/i.test(status) || run.safety_gate) return { label: "安全门通过", tone: "ok" };
  return { label: "等待安全检查", tone: "warning" };
}

function getExpertFeedbackBadge(run: RunRecord): StatusBadgeItem {
  const status = getRecordStatusValue(run.expert_feedback, ["status", "state", "decision"]);
  if (/approved|accepted|complete/i.test(status)) return { label: "专家反馈已记录", tone: "ok" };
  if (/rejected|blocked/i.test(status)) return { label: "专家反馈需处理", tone: "error" };
  if (/await|pending|review|requested/i.test(status) || run.expert_feedback) {
    return { label: "等待专家反馈", tone: "warning" };
  }
  return { label: "可提交专家审查", tone: "neutral" };
}

function getGroundingBadge(status: string | undefined): StatusBadgeItem {
  if (status === "provenance_checked") return { label: "引用已核验", tone: "ok" };
  if (status === "knowledge_base_supported") return { label: "知识库支撑", tone: "ok" };
  if (status === "limited_fulltext") return { label: "全文不足", tone: "warning" };
  if (status === "citation_mismatch") return { label: "引用不一致", tone: "error" };
  if (status === "ungrounded") return { label: "缺少文献支撑", tone: "warning" };
  return { label: "证据待核验", tone: "neutral" };
}

function getCitationQaBadge(run: RunRecord): StatusBadgeItem {
  const status = getRecordStatusValue(run.citation_provenance_qa, ["status", "result", "decision"]);
  if (/mismatch|fail|invalid/i.test(status)) return { label: "引用不一致", tone: "error" };
  if (/limited|partial|insufficient/i.test(status)) return { label: "全文不足", tone: "warning" };
  if (/checked|pass|ok/i.test(status) || run.citation_provenance_qa) return { label: "证据已核验", tone: "ok" };
  return { label: "证据待核验", tone: "neutral" };
}

function formatSupportLevel(level: string) {
  const labels: Record<string, { label: string; tone: SummaryItem["tone"] }> = {
    fulltext: { label: "全文支撑", tone: "ok" },
    abstract: { label: "摘要支撑", tone: "warning" },
    metadata: { label: "元数据支撑", tone: "warning" },
    "source-code": { label: "源码支撑", tone: "ok" },
    source_code: { label: "源码支撑", tone: "ok" },
    missing: { label: "支撑不足", tone: "error" },
    mismatch: { label: "引用不一致", tone: "error" },
  };
  return labels[level] ?? { label: level.replaceAll("_", " "), tone: "neutral" as const };
}

function getCitationSupportItems(supportLevels: Record<string, string> | undefined): SummaryItem[] {
  if (!supportLevels) return [];
  return Object.entries(supportLevels).slice(0, 8).map(([source, level]) => {
    const support = formatSupportLevel(level);
    return {
      label: formatBackendText(source),
      value: support.label,
      tone: support.tone,
    };
  });
}

function getRecordSummaryText(record: Record<string, unknown> | undefined) {
  if (!record) return "";
  for (const key of ["summary", "reason", "message", "details", "explanation"]) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return formatBackendText(value);
  }
  return "";
}

function getCitationMapStatus(value: unknown) {
  if (!isRecord(value)) return "";
  for (const key of ["support_level", "status", "grounding_status", "source_reliability", "provenance_status"]) {
    const item = value[key];
    if (typeof item === "string" && item.trim()) return item.trim();
  }
  return "";
}

function getEvidenceDiagnostics(run: RunRecord, hypothesis: Hypothesis): SummaryItem[] {
  const items: SummaryItem[] = [];
  const groundingStatus = hypothesis.grounding_status ?? "";
  if (groundingStatus === "citation_mismatch") {
    items.push({
      label: "引用不一致",
      value: "当前假设被后端标记为 citation_mismatch；优先检查支撑级别为 mismatch/missing 的来源和 claim 对应关系。",
      tone: "error",
    });
  }
  if (groundingStatus === "limited_fulltext") {
    items.push({
      label: "全文不足",
      value: "当前证据主要来自摘要、元数据或不可访问全文；不能把模型生成内容写成已被 fulltext 支撑的结论。",
      tone: "warning",
    });
  }
  if (groundingStatus === "ungrounded") {
    items.push({
      label: "缺少文献支撑",
      value: "没有可追溯 citation_map 或知识库片段；应先补充 PDF/网页/外部文献证据。",
      tone: "warning",
    });
  }

  for (const [source, level] of Object.entries(hypothesis.citation_support_levels ?? {})) {
    const normalized = String(level).toLowerCase();
    if (/mismatch|missing|contradict|invalid/.test(normalized)) {
      items.push({
        label: formatBackendText(source),
        value: `来源支撑级别为 ${formatSupportLevel(level).label}，需要核对该 citation 是否真的支持假设中的具体 claim。`,
        tone: "error",
      });
    } else if (/abstract|metadata|limited|partial|weak|public|landing/.test(normalized)) {
      items.push({
        label: formatBackendText(source),
        value: `仅达到 ${formatSupportLevel(level).label}；进入实验或报告前建议解析 PDF fulltext 或补充可引用来源。`,
        tone: "warning",
      });
    }
  }

  for (const [source, value] of Object.entries(hypothesis.citation_map ?? {})) {
    const status = getCitationMapStatus(value);
    if (!status) continue;
    if (/mismatch|missing|contradict|invalid/.test(status)) {
      items.push({
        label: formatBackendText(source),
        value: `citation_map 标记为 ${formatBackendText(status)}，这里就是引用不一致的直接入口。`,
        tone: "error",
      });
    } else if (/abstract|metadata|limited|partial|weak|html|landing/.test(status)) {
      items.push({
        label: formatBackendText(source),
        value: `citation_map 只有 ${formatBackendText(status)} 级别证据，属于全文不足或弱支撑。`,
        tone: "warning",
      });
    }
  }

  const qaBadge = getCitationQaBadge(run);
  const qaSummary = getRecordSummaryText(run.citation_provenance_qa);
  if (qaBadge.tone === "error" || qaBadge.tone === "warning") {
    items.push({
      label: qaBadge.label,
      value: qaSummary || "运行级引用核验没有完全通过；请逐条检查引用来源、support level 和知识库命中片段。",
      tone: qaBadge.tone,
    });
  }

  if (items.length === 0 && Object.keys(hypothesis.citation_map ?? {}).length === 0) {
    items.push({
      label: "没有证据入口",
      value: "当前假设没有 citation_map。应先解析 PDF、抓取网页或运行文献支撑 workflow。",
      tone: "warning",
    });
  }

  if (items.length === 0) {
    items.push({
      label: "未发现显式证据异常",
      value: "当前数据没有标记 citation mismatch 或 limited fulltext；仍建议在报告前打开参考文献逐条核验。",
      tone: "ok",
    });
  }
  return items.slice(0, 10);
}

function getKnowledgeSupportItems(support: Hypothesis["knowledge_base_support"] | undefined): SummaryItem[] {
  return (support ?? []).slice(0, 6).map((item, index) => ({
    label: item.title || item.chunk_title || `知识库片段 ${index + 1}`,
    value: [
      item.section_path?.join(" / "),
      item.support_level === "experimental_data" ? "实验数据支撑" : "全文片段支撑",
      item.source_reliability ? formatSummaryValue(item.source_reliability) : "",
    ].filter(Boolean).join(" · "),
    tone: item.support_level === "experimental_data" ? "ok" : "neutral",
  }));
}

function getExperimentSupportItems(support: Hypothesis["experimental_support_summaries"] | undefined): SummaryItem[] {
  return (support ?? []).slice(0, 6).map((item, index) => ({
    label: item.title || item.chunk_title || `实验数据 ${index + 1}`,
    value: item.experiment_data_summary || item.text_preview || "已定位实验数据片段",
    tone: "ok",
  }));
}

function getRunGovernanceItems(run: RunRecord): SummaryItem[] {
  const safety = getSafetyBadge(run);
  const citationQa = getCitationQaBadge(run);
  const expertFeedback = getExpertFeedbackBadge(run);
  const evidenceGateStatus = run.research_outcome?.evidence_gate?.status;
  const evidenceGate: SummaryItem = evidenceGateStatus === "passed"
    ? { label: "闭环证据门", value: "排名前证据检查已通过", tone: "ok" }
    : evidenceGateStatus
      ? { label: "闭环证据门", value: "证据仍有限，冠军需要人工复核", tone: "warning" }
      : { label: "闭环证据门", value: "等待生成 ResearchOutcome", tone: "neutral" };
  return [
    { label: "安全门", value: safety.label, tone: safety.tone },
    { label: "证据核验", value: citationQa.label, tone: citationQa.tone },
    { label: "专家反馈", value: expertFeedback.label, tone: expertFeedback.tone },
    evidenceGate,
  ];
}

export function mapRunToProjectView(run: RunRecord): ProjectViewModel {
  const projectId = run.run_id;
  return {
    id: projectId,
    title: getProjectTitle(run.request.research_goal),
    researchGoal: run.request.research_goal,
    status: run.status,
    modeLabel: getRunModeLabel(run),
    groundingLabel: getGroundingLabel(run),
    stageLabel: getPhaseLabel(run),
    nextStep: getNextStep(run),
    hypothesisCount: run.hypotheses.length,
    evidenceCount: countEvidence(run),
    lastActivity: formatRunState(run.status),
    route: `/projects/${projectId}`,
    papersRoute: `/projects/${projectId}/papers`,
    hypothesesRoute: `/projects/${projectId}/hypotheses`,
    experimentsRoute: `/projects/${projectId}/experiments`,
    reportsRoute: `/projects/${projectId}/reports`,
    workspaceRoute: `/workspace/${projectId}`,
    outputCount: run.hypotheses.length > 0 ? 3 : 0,
    run,
  };
}

export function mapRunsToProjects(runs: RunRecord[]) {
  return getVisibleProductRuns(runs).map(mapRunToProjectView);
}

export function mapRunToHypothesisViews(run: RunRecord): HypothesisCardViewModel[] {
  const minReferences = run.request.min_references ?? 2;
  const maxReferences = run.request.max_references ?? 6;
  return run.hypotheses.map((hypothesis, index) => {
    const display = getHypothesisDisplay(hypothesis, index);
    return {
      id: `${run.run_id}-hypothesis-${index}`,
      title: display.title,
      summary: display.summary,
      scoreLabel: formatScore(hypothesis.score),
      rankLabel: hypothesis.elo_rating ? String(hypothesis.elo_rating) : "暂无",
      grounding: hypothesis.literature_grounding
        ? formatBackendText(hypothesis.literature_grounding)
        : copy.details.noGrounding,
      experimentPlan: getExperimentPlanDisplay(hypothesis),
      citations: getCitationItems(hypothesis.citation_map, maxReferences),
      citationPdfCandidates: getCitationPdfCandidates(hypothesis.citation_map),
      evidenceBadges: [
        getGroundingBadge(hypothesis.grounding_status),
        getCitationQaBadge(run),
      ],
      governanceBadges: [
        getSafetyBadge(run),
        getExpertFeedbackBadge(run),
      ],
      citationSupportItems: getCitationSupportItems(hypothesis.citation_support_levels),
      knowledgeSupportItems: getKnowledgeSupportItems(hypothesis.knowledge_base_support),
      experimentSupportItems: getExperimentSupportItems(hypothesis.experimental_support_summaries),
      evidenceDiagnostics: getEvidenceDiagnostics(run, hypothesis),
      referenceRangeLabel: `${minReferences}-${maxReferences} 条参考文献目标`,
      raw: hypothesis,
    };
  });
}

function getCitationPdfCandidates(citationMap: Record<string, unknown> | undefined): CitationPdfCandidate[] {
  if (!citationMap) return [];
  return Object.entries(citationMap).flatMap(([key, value]) => {
    if (!isRecord(value)) return [];
    const title = formatBackendText(String(value.title ?? value.name ?? key));
    const supportLabel = formatBackendText(String(value.source_reliability ?? value.source ?? value.type ?? "来源"));
    const candidates = [
      value.pdf_path,
      value.pdf_url,
      value.fulltext_pdf,
      value.url,
      ...(Array.isArray(value.pdf_links) ? value.pdf_links : []),
    ]
      .map((item) => String(item ?? "").trim())
      .filter((item) => item && (item.toLowerCase().endsWith(".pdf") || item.toLowerCase().includes(".pdf?")));
    return candidates.slice(0, 2).map((pdfPath, index) => ({
      key: `${key}-${index}`,
      title,
      pdfPath,
      supportLabel,
    }));
  }).slice(0, 8);
}

export function mapRunToOutputs(run: RunRecord): OutputViewModel[] {
  if (run.hypotheses.length === 0) return [];
  const topHypothesis = mapRunToHypothesisViews(run)[0];
  return [
    {
      id: `${run.run_id}-finding`,
      title: "研究发现",
      summary: topHypothesis.summary,
      kind: "finding",
      route: `/outputs?project=${run.run_id}`,
    },
    {
      id: `${run.run_id}-experiment`,
      title: "实验计划",
      summary: topHypothesis.experimentPlan,
      kind: "experiment",
      route: `/projects/${run.run_id}/experiments`,
    },
    {
      id: `${run.run_id}-report`,
      title: "报告草稿",
      summary: run.request.demo_mode
        ? "这是历史合成记录生成的草稿，仅供回看，不作为当前研究结论。"
        : "把候选假设、实验计划和局限性整理为可审查草稿。",
      kind: "report",
      route: `/projects/${run.run_id}/reports`,
    },
  ];
}

export function mapRunToWorkspaceView(run: RunRecord): WorkspaceViewModel {
  return {
    project: mapRunToProjectView(run),
    hypotheses: mapRunToHypothesisViews(run),
    outputs: mapRunToOutputs(run),
    planItems: getPlanItems(run.research_plan),
    metricItems: [...getMetricItems(run), ...getRunGovernanceItems(run)],
    tournamentItems: getTournamentItems(run.tournament_matchups),
  };
}
