import { modelGroups, workflowPhaseCount } from "../constants/models";
import type {
  AppCopy,
  Health,
  Hypothesis,
  ProviderStatus,
  RunRecord,
  RunStatus,
  SummaryItem,
  TimelineEvent,
  TournamentItemViewModel,
} from "../../types/workbench";

const internalFieldPattern =
  /(api|endpoint|url|path|command|key|token|secret|traceback|raw|run_id|request_id|provider|repair|error)/i;
const internalTextPattern =
  /(api[-_\s]?key|GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|token|secret|endpoint|run_id|request_id|repair_hint|provider)/i;

export const copy: AppCopy = {
  productKicker: "AI 科研工作台",
  railSubtitle: "研究工作台",
  runState: {
    idle: "就绪",
    queued: "排队中",
    running: "运行中",
    complete: "已完成",
    error: "错误",
  },
  home: {
    title: "研究主页",
    description: "从最近研究、活跃任务和最近产出继续推进，而不是从一张运行面板重新开始。",
    activeTasks: "活跃任务",
    recentResearch: "最近研究",
    recentOutputs: "最近产出",
    startNew: "开始新研究",
    emptyProjects: "还没有研究记录。先在工作区定义研究目标并生成第一轮候选假设。",
  },
  projects: {
    title: "研究项目",
    description: "按研究目标组织项目、阶段、候选假设和下一步，而不是暴露底层执行结构。",
    empty: "还没有可浏览的项目。先在工作区启动一次研究。",
    continueLabel: "继续研究",
  },
  library: {
    title: "资料库",
    description: "把已有运行中的论文线索、引用来源和证据槽位整理成只读知识面。",
    papers: "论文与线索",
    references: "引用来源",
    empty: "当前还没有可浏览的文献或引用元数据。",
  },
  workspace: {
    title: "研究工作区",
    description: "围绕当前研究目标生成假设、检查证据、设计实验和整理报告。",
    taskTitle: "当前任务：形成可检验假设",
    taskDescription: "输入研究目标后，系统会生成候选假设、评审依据、排序信号和下一步实验方向。",
    runButtonIdle: "生成候选假设",
    runButtonRepeat: "重新生成候选假设",
    runButtonBusy: "正在形成假设",
    auditOpen: "查看过程与证据",
    auditClose: "收起过程与证据",
    outputsEmpty: "生成候选假设后，这里会出现可选择的研究方向、实验入口和审计详情。",
  },
  outputs: {
    title: "研究产出",
    description: "把发现、实验建议和报告草稿汇总成可回看对象，而不是埋在页面尾部。",
    empty: "完成一次研究运行后，这里会聚合发现、实验计划和报告草稿。",
  },
  settings: {
    title: "运行准备",
    description: "确认当前是否满足实时研究运行条件，并通过专家设置调整模型与生成参数。",
    expertSettings: "专家设置",
    refresh: "重新检查",
    clearRun: "清空结果",
    currentMode: "当前运行模式",
    localWorkflow: "历史合成记录",
    liveWorkflow: "实时模型流程",
    literatureWorkflow: "文献支撑",
    currentProvider: "当前模型通道",
    runReadiness: "运行准备状态",
    blockedReason: "阻塞原因",
    nextAction: "建议下一步",
  },
  workflow: {
    localMode: "历史合成记录",
    liveMode: "实时模型与文献支撑",
    readyDetail: "可以开始研究运行",
    runBlocked: "当前研究暂未满足运行条件。请调整运行模式，或关闭当前不可用能力。",
    requestFailed: "研究运行未能启动，请在工作台准备完成后重试。",
    pollFailed: "暂时无法刷新最新运行进展。",
    runFailed: "研究运行在产出完整结果前停止，已保留可检查的中间结果。",
    stageNeedsAttention: "该阶段需要检查。",
    stageNeedsAttentionDesc: "可用的中间结果已保留在页面中。",
  },
  details: {
    noGrounding: "暂无文献支撑。",
    noExperiment: "暂无实验计划。",
    noPlan: "运行研究流程后可查看研究计划。",
    noHypothesis: "尚未选择假设",
    selectCompleted: "选择一个已完成结果以查看解释。",
    summaryEmpty: "暂无摘要信息。",
    sourceUnknown: "未命名来源",
    planSummary: "研究计划摘要",
    literatureGrounding: "文献支撑",
    citationMap: "证据来源",
    experiment: "实验",
    tournamentEmpty: "运行结束后会显示成对比较、胜负、置信度和 Elo 变化。",
    metricsEmpty: "运行结束后会显示质量信号。",
    agentsEmpty: "运行结束后会显示过程记录。",
    hypothesesCount: "候选假设",
    averageScore: "平均评分",
    tournamentRounds: "成对比较",
    groundedSources: "证据来源",
    matchLabel: (index: number) => `比较 ${index}`,
    confidence: (value: number) => `${Math.round(value * 100)}% 置信度`,
  },
};

export function classNames(...items: Array<string | false | null | undefined>) {
  return items.filter(Boolean).join(" ");
}

export function getModelInfo(modelName: string) {
  for (const group of modelGroups) {
    const model = group.models.find((item) => item.value === modelName);
    if (model) return { provider: group.provider, label: model.label };
  }
  return { provider: "自定义", label: modelName };
}

export function getProviderIdForModel(modelName: string) {
  if (modelName.startsWith("openai/mimo-") || modelName.startsWith("mimo/") || modelName.startsWith("xiaomi/")) return "mimo";
  if (modelName.startsWith("gemini/")) return "gemini";
  if (modelName.startsWith("dashscope/")) return "qwen_dashscope";
  if (modelName.startsWith("deepseek/")) return "deepseek";
  if (modelName.startsWith("claude")) return "anthropic";
  return "openai";
}

export function getSelectedProviderStatus(health: Health | null, modelName: string) {
  return health?.providers?.[getProviderIdForModel(modelName)];
}

export function isVisibleProductRun(run: RunRecord) {
  return !run.request.demo_mode;
}

export function getVisibleProductRuns(runs: RunRecord[]) {
  return runs.filter(isVisibleProductRun);
}

export function getRunModeLabel(run: RunRecord) {
  return run.request.demo_mode ? "历史合成记录" : copy.workflow.liveMode;
}

export function getBlockedRunReason(health: Health | null, provider: ProviderStatus | undefined) {
  if (!health) return "工作台正在检查运行条件，暂时不能启动研究。";
  if (!provider?.usable) return "当前选中的模型通道不可用，研究运行已暂停。";
  if (!health.literature_mcp?.available) return "文献服务当前不可用，研究运行已暂停。";
  return "";
}

export function getRunReadinessLabel(health: Health | null, provider: ProviderStatus | undefined) {
  return getBlockedRunReason(health, provider) ? "暂不可运行" : "可立即启动研究";
}

export function getRunRecoveryAction(health: Health | null, provider: ProviderStatus | undefined) {
  if (!health) return "等待检查完成后重新刷新。";
  if (!provider?.usable) return "在专家设置中切换到当前可用的实时模型。";
  if (!health.literature_mcp?.available) return "先恢复文献服务，再返回工作区启动研究。";
  return "返回工作区，开始新的文献支撑研究。";
}

export function parseApiError(body: string) {
  try {
    const parsed = JSON.parse(body) as {
      detail?: string | { message?: string; repair_hint?: string; code?: string };
    };
    if (typeof parsed.detail === "string" || parsed.detail?.message) {
      return "request_failed";
    }
  } catch {
    // Keep backend payloads out of the user-facing UI.
  }
  return "request_failed";
}

export function getSafeErrorMessage(error: unknown, fallback: string) {
  if (!(error instanceof Error) || !error.message.trim()) return fallback;
  const message = error.message.trim();
  const unsafe =
    message === "request_failed" ||
    /^[a-z0-9_]+_failed(_\d+)?$/i.test(message) ||
    /https?:\/\/|\/api\/|endpoint|traceback|stack|provider|token|secret|api[-_\s]?key|run_id|request_id|[\[\]{}\\]/i.test(message) ||
    containsInternalRuntimeText(message) ||
    message.length > 140;
  if (unsafe) return fallback;
  return /[\u4e00-\u9fff]/.test(message) ? message : fallback;
}

export function formatRunState(status: RunStatus | undefined) {
  if (!status) return copy.runState.idle;
  return copy.runState[status];
}

export function formatStageLabel(stage: string) {
  const normalized = stage.replace(/\s+(Start|Complete)$/i, "");
  const stageLabels: Record<string, string> = {
    Supervisor: "监督规划",
    "Literature Scout": "文献侦察",
    "Literature Review": "文献综述",
    Generation: "假设生成",
    Reflection: "反思校验",
    Tournament: "成对排序",
    "Meta Review": "元评审",
    Generator: "假设生成器",
    Reviewer: "评审节点",
    Ranker: "排序节点",
    Literature: "文献检索",
    Generate: "假设生成",
    Review: "科学评审",
    Rank: "成对排序",
    Evolve: "演化改写",
    Proximity: "相似性检查",
    Metrics: "指标汇总",
    Complete: "完成",
    Error: "错误",
  };
  return stageLabels[stage] ?? stageLabels[normalized] ?? normalized;
}

export function formatModeValue(value: unknown) {
  const raw = String(value ?? "");
  const modeLabels: Record<string, string> = {
    ok: "正常",
    missing: "缺失",
    reachable: "可达",
    configured_not_called: "已配置，未调用",
    demo_synthetic: "演示模拟",
    local: "本地",
    live: "实时",
    queued: "排队中",
    running: "运行中",
    complete: "已完成",
    error: "错误",
  };
  return modeLabels[raw] ?? raw.replaceAll("_", " ");
}

export function containsInternalRuntimeText(value: string) {
  return internalTextPattern.test(value);
}

export function formatBackendText(text: string) {
  const textLabels: Record<string, string> = {
    "Local agent key accepted": "本地模拟通道已确认",
    "Codex simulation provider initialized": "本地模拟流程已初始化",
    "Evidence scaffold built": "证据骨架已建立",
    "Synthetic citation slots prepared for MCP/PubMed replacement": "已准备证据挂接位置",
    "Hypotheses generated": "假设已生成",
    "Peer review completed": "同行评审已完成",
    "Scientific soundness, novelty, relevance, testability, clarity, and impact scored":
      "已完成科学性、新颖性、相关性、可检验性、清晰度与影响力评分",
    "Tournament updated": "成对排序已更新",
    "Pairwise preference ranking produced Elo scores": "成对偏好排序已生成 Elo 分数",
    "Diversity checked": "多样性已检查",
    "Candidate population checked for near-duplicate collapse": "已检查候选集合是否出现近重复收缩",
    "Run finalized": "运行已完成",
    "Local multi-agent simulation results prepared for inspection": "本地多角色模拟结果已可检查",
    "Live open-coscientist workflow started": "实时科研工作流已启动",
    "Run failed": "运行失败",
    "Research planner": "研究规划器",
    "Evidence mapper": "证据映射器",
    "Hypothesis proposer": "假设提出器",
    "Rubric critic": "评分规约评审",
    "Tournament judge": "成对排序裁判",
    "Diversity guard": "多样性守卫",
    "I decomposed the goal into three work packages: claim grounding, candidate diversity, and falsification-first evaluation.":
      "我将目标拆解为三个工作包：论断证据锚定、候选假设多样性、以及可证伪性优先的评估。",
    "No external corpus was queried in local simulation mode. I created a synthetic evidence map so the UI can show where real MCP/PubMed citations would attach.":
      "本地模拟模式不会查询外部语料；这里展示证据字段在结果中的挂接位置。",
    "I scored each candidate on scientific soundness, novelty, relevance, testability, clarity, and impact, then attached concise critique summaries.":
      "我已按科学合理性、新颖性、相关性、可检验性、清晰度和影响力为每个候选假设评分，并附上简明评审摘要。",
    "I preferred the retrieval-audited protocol because it has the clearest measurement path and the lowest risk of ungrounded claims.":
      "我更偏好带检索审计的方案，因为它的测量路径最清晰，且无依据论断风险最低。",
    "The candidates cover three distinct intervention points, so no duplicate collapse was detected in this simulated run.":
      "候选假设覆盖三个不同干预点，因此本次模拟运行未检测到重复收缩。",
    "Demo mode uses synthetic grounding. Run with model credentials and literature review enabled to resolve real sources.":
      "当前为本地演示模拟，只展示证据字段位置；启用文献综述后会替换为真实来源。",
    "Demo mode shows the output structure without querying PubMed or MCP tools.":
      "当前为本地演示模拟，只展示输出结构，不代表真实文献检索结果。",
    "No real literature is consulted in demo mode.": "当前演示模拟未查询真实文献。",
    local_agent_simulation: "本地模拟证据槽",
    parsed_fulltext: "已解析全文",
    parsed_full_text: "已解析全文",
    fulltext: "全文支撑",
    full_text: "全文支撑",
    abstract: "摘要支撑",
    metadata: "元数据支撑",
    local_pdf: "本地 PDF",
    uploaded_pdf: "上传 PDF",
    web_extract: "公开网页证据",
    browser_web_extract: "公开网页证据",
    source_snapshot: "文件证据快照",
    file_source_snapshot: "文件证据快照",
    experimental_data: "实验数据支撑",
    knowledge_base_supported: "知识库支撑",
    limited_fulltext: "全文不足",
    ungrounded: "缺少文献支撑",
    introduction: "引言",
    methods: "方法",
    method: "方法",
    experiments: "实验",
    experiment: "实验",
    results: "结果",
    discussion: "讨论",
    conclusion: "结论",
    references: "参考文献",
    tables: "表格",
    table: "表格",
    figures: "图",
    figure: "图",
    "Supervisor evidence checkpoint": "监督规划证据检查点",
    "Reviewer falsification critique": "评审可证伪性意见",
    "Generator diversity proposal": "生成器多样性提案",
    "Proximity deduplication signal": "相似性去重信号",
    "Use a fake API-key path to inspect the product workflow before connecting a live model.":
      "当前使用本地模拟路径，用于检查产品流程和交互状态。",
    "Define the scientific claim type and measurable failure modes.": "定义科学论断类型和可测量失败条件。",
    "Generate diverse candidate mechanisms instead of variants of one idea.":
      "生成多样化候选机制，而不是同一想法的变体。",
    "Review each hypothesis with a rubric and rank via pairwise tournament.":
      "按评审规约审查每条假设，并通过成对比较排序。",
    "Expose citations, critique, and metrics in the UI for human inspection.":
      "把证据、评审意见和质量信号整理为可审查结果。",
    "Disable simulation mode after setting GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY.":
      "如需真实模型运行，请在专家设置中切换运行模式。",
    "Compare the protocol against a baseline generator on a curated benchmark. Measure claim support precision, contradiction rate, reviewer preference, and reproducibility of proposed experiments.":
      "与基线生成器对照，测量论断证据精确率、矛盾率、评审偏好和实验设计可复现性。",
    "Run ablations with and without proximity penalties. Track hypothesis diversity, expert novelty ratings, and downstream experiment pass rate.":
      "对相似性惩罚做消融，追踪假设多样性、专家新颖性评分和后续实验通过率。",
    "Have independent reviewers score whether each plan contains clear reject criteria, measurable metrics, and an executable minimum experiment.":
      "由独立评审检查每个计划是否包含清晰拒绝条件、可测指标和可执行的最小实验。",
  };
  const exact = textLabels[text];
  if (exact) return exact;
  const candidates = text.match(/^(\d+) initial candidates drafted$/);
  if (candidates) return `已起草 ${candidates[1]} 个初始候选假设`;
  const returned = text.match(/^(\d+) hypotheses returned$/);
  if (returned) return `已返回 ${returned[1]} 个假设`;
  if (/^Environment variable .+$/.test(text)) return "实时运行所需凭据尚未就绪。";
  if (containsInternalRuntimeText(text)) {
    return "内部运行配置已隐藏，可在专家设置中调整运行模式。";
  }
  if (text.startsWith("Built-in local agent simulation")) {
    return "内置本地模拟流程已启用。";
  }
  if (text.startsWith("TCP ") && text.includes("is accepting connections")) {
    return text.replace("is accepting connections", "正在接受连接");
  }
  return text
    .replace(/\bAI\/MCP\b/g, "AI/文献服务")
    .replace(/\bMCP\b/g, "外部文献服务")
    .replace(/\blive model\b/gi, "实时模型")
    .replace(/\bliterature-grounded workflow\b/gi, "文献支撑研究路径")
    .replace(/\bresearch goal\b/gi, "研究目标");
}

function isInternalField(key: string) {
  return internalFieldPattern.test(key);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function formatPlanLabel(key: string) {
  const labels: Record<string, string> = {
    research_goal: "研究目标",
    goal: "研究目标",
    plan: "计划",
    research_plan: "研究计划",
    constraints: "约束",
    priorities: "优先级",
    strategy: "策略",
    methodology: "方法",
    workflow: "研究任务流程",
    hypotheses: "假设",
    literature_review: "文献综述",
    validation: "验证",
    experiment: "实验",
    experiments: "实验",
    metrics: "评价指标",
    assumptions: "关键假设",
    risks: "风险",
    next_steps: "后续步骤",
    next_step: "建议下一步",
    recommended_next_step: "建议下一步",
    supervisor_plan: "研究计划",
    summary: "摘要",
    objective: "目标",
  };
  return labels[key] ?? key.replaceAll("_", " ");
}

export function formatSummaryValue(value: unknown, depth = 0): string {
  if (value === null || value === undefined || value === "") return "暂无";
  if (typeof value === "string") return formatBackendText(value);
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) {
    const items = value
      .slice(0, 4)
      .map((item) => formatSummaryValue(item, depth + 1))
      .filter((item) => item && item !== "暂无");
    return items.length > 0 ? items.join("；") : "暂无";
  }
  if (isRecord(value)) {
    if (depth > 1) return "已整理为结构化条目";
    const entries = Object.entries(value)
      .filter(([key]) => !isInternalField(key))
      .slice(0, 4);
    if (entries.length === 0) return "已记录";
    return entries
      .map(([key, item]) => `${formatPlanLabel(key)}：${formatSummaryValue(item, depth + 1)}`)
      .join("；");
  }
  return String(value);
}

export function getPlanItems(plan: Record<string, unknown> | null | undefined): SummaryItem[] {
  if (!plan || Object.keys(plan).length === 0) return [];
  return Object.entries(plan)
    .filter(([key]) => !isInternalField(key))
    .slice(0, 8)
    .map(([key, value]) => ({
      label: formatPlanLabel(key),
      value: formatSummaryValue(value),
    }));
}

export function getCitationItems(citationMap: Record<string, unknown> | undefined, limit = 8): SummaryItem[] {
  if (!citationMap) return [];
  return Object.entries(citationMap)
    .slice(0, limit)
    .map(([key, value]) => {
      if (!isRecord(value)) {
        return { label: formatBackendText(key), value: formatSummaryValue(value) };
      }
      const title = formatBackendText(String(value.title ?? value.name ?? key));
      const authors = Array.isArray(value.authors)
        ? value.authors.slice(0, 2).map(String).join(", ")
        : "";
      const year = value.year ? String(value.year) : "";
      const type = value.type ? formatSummaryValue(value.type) : copy.details.sourceUnknown;
      const meta = [authors, year, type].filter(Boolean).join(" · ");
      return { label: title, value: meta || copy.details.sourceUnknown };
    });
}

function readString(value: unknown, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function readNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return null;
}

function readNumberMap(value: unknown): Record<string, number> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, item]) => [key, readNumber(item)] as const)
      .filter((entry): entry is readonly [string, number] => entry[1] !== null),
  );
}

function formatEloDelta(delta: number | null) {
  if (delta === null) return "";
  return delta > 0 ? `+${delta}` : String(delta);
}

function formatEloTransition(before: number | null, after: number | null, delta: number | null) {
  if (before === null || after === null) return "Elo 未记录";
  const formattedDelta = formatEloDelta(delta ?? after - before);
  return `${before} -> ${after}${formattedDelta ? ` (${formattedDelta})` : ""}`;
}

function getMapValue(map: Record<string, number>, key: string) {
  return key ? map[key] ?? null : null;
}

function sideLabel(side: string) {
  if (side === "a") return "A";
  if (side === "b") return "B";
  return side || "未标注";
}

export function getTournamentItems(matchups: Record<string, unknown>[] | undefined): TournamentItemViewModel[] {
  return (matchups ?? []).slice(0, 12).map((matchup, index) => {
    const winner = readString(matchup.winner).toLowerCase();
    const loser = readString(matchup.loser).toLowerCase();
    const winnerId = readString(matchup.winner_id);
    const loserId = readString(matchup.loser_id);
    const hypothesisAId = readString(matchup.hypothesis_a_id);
    const hypothesisBId = readString(matchup.hypothesis_b_id);
    const winnerSide = winner === "a" || winner === "b" ? winner : "";
    const loserSide = loser === "a" || loser === "b" ? loser : winnerSide === "a" ? "b" : winnerSide === "b" ? "a" : "";
    const resolvedWinnerId =
      winnerId || (winnerSide === "a" ? hypothesisAId : winnerSide === "b" ? hypothesisBId : "");
    const resolvedLoserId =
      loserId || (loserSide === "a" ? hypothesisAId : loserSide === "b" ? hypothesisBId : "");
    const beforeMap = readNumberMap(matchup.before_elo);
    const afterMap = readNumberMap(matchup.after_elo);
    const deltaMap = readNumberMap(matchup.elo_delta);
    const winnerBefore =
      getMapValue(beforeMap, resolvedWinnerId) ?? readNumber(matchup.winner_elo_before);
    const winnerAfter =
      getMapValue(afterMap, resolvedWinnerId) ?? readNumber(matchup.winner_elo_after);
    const winnerDelta =
      getMapValue(deltaMap, resolvedWinnerId) ?? readNumber(matchup.winner_elo_delta);
    const loserBefore =
      getMapValue(beforeMap, resolvedLoserId) ?? readNumber(matchup.loser_elo_before);
    const loserAfter =
      getMapValue(afterMap, resolvedLoserId) ?? readNumber(matchup.loser_elo_after);
    const loserDelta =
      getMapValue(deltaMap, resolvedLoserId) ?? readNumber(matchup.loser_elo_delta);
    const confidence = readString(matchup.confidence_level) || readString(matchup.confidence, "Unknown");
    const confidenceScore = readNumber(matchup.confidence_score);
    const confidenceLabel =
      confidenceScore !== null
        ? `${formatBackendText(confidence)} · ${Math.round(confidenceScore * 100)}%`
        : formatBackendText(confidence);
    const comparisonMode = readString(matchup.comparison_mode, "single_turn");
    const priority = isRecord(matchup.pairing_priority) ? matchup.pairing_priority : {};
    const priorityLabel = [
      readNumber(priority.proximity) !== null ? `相似度优先 ${readNumber(priority.proximity)}` : "",
      readNumber(priority.newer_hypotheses) !== null ? `新假设 ${readNumber(priority.newer_hypotheses)}` : "",
      readNumber(priority.top_ranked) !== null ? `高排序 ${readNumber(priority.top_ranked)}` : "",
    ].filter(Boolean).join(" · ");
    const reason =
      matchup.reasoning ??
      matchup.reason ??
      matchup.rationale ??
      matchup.explanation ??
      matchup.feedback ??
      copy.workflow.stageNeedsAttentionDesc;
    return {
      id: readString(matchup.matchup_id, `matchup-${index + 1}`),
      label: copy.details.matchLabel(readNumber(matchup.round) ?? index + 1),
      participantsLabel: [
        hypothesisAId ? `A ${hypothesisAId}` : "A",
        hypothesisBId ? `B ${hypothesisBId}` : "B",
      ].join(" vs "),
      winnerLabel: `${sideLabel(winnerSide)} ${resolvedWinnerId || "胜者"}`,
      loserLabel: `${sideLabel(loserSide)} ${resolvedLoserId || "落败方"}`,
      confidenceLabel,
      comparisonModeLabel:
        comparisonMode === "debate"
          ? `多轮科学辩论 · ${readNumber(matchup.debate_turns_requested) ?? 3} 轮`
          : "单轮成对比较",
      winnerEloLabel: formatEloTransition(winnerBefore, winnerAfter, winnerDelta),
      loserEloLabel: formatEloTransition(loserBefore, loserAfter, loserDelta),
      reasoning: formatSummaryValue(reason),
      priorityLabel: priorityLabel || "按 tournament 调度",
      tone: confidence.toLowerCase() === "low" ? "warning" : "neutral",
    };
  });
}

export function getMetricItems(record: RunRecord | null): SummaryItem[] {
  if (!record) return [];
  const scores = record.hypotheses
    .map((hypothesis) => hypothesis.score)
    .filter((score): score is number => typeof score === "number");
  const sourceCount = record.hypotheses.reduce(
    (total, hypothesis) => total + Object.keys(hypothesis.citation_map ?? {}).length,
    0,
  );
  const averageScore =
    scores.length > 0
      ? (scores.reduce((total, score) => total + score, 0) / scores.length).toFixed(2)
      : "暂无";
  return [
    { label: copy.details.hypothesesCount, value: String(record.hypotheses.length) },
    { label: copy.details.averageScore, value: averageScore },
    { label: copy.details.tournamentRounds, value: String(record.tournament_matchups.length) },
    { label: copy.details.groundedSources, value: String(sourceCount) },
  ];
}

export function getTimelineDetail(event: TimelineEvent) {
  if (event.status === "error") return copy.workflow.stageNeedsAttentionDesc;
  if (/^Progress\s+/i.test(event.details)) return "";
  return formatBackendText(event.details)
    .replace("Live open-coscientist workflow", "实时科研工作流")
    .replace("open-coscientist workflow", "科研工作流");
}

export function getProjectTitle(goal: string) {
  const normalized = goal.replace(/[。.!?？]/g, "").trim();
  if (normalized.includes("长上下文")) return "长上下文事实一致性研究";
  if (normalized.includes("阿尔茨海默")) return "阿尔茨海默病早筛假设研究";
  if (normalized.includes("多智能体") || normalized.includes("科研工作流")) return "科研智能体方法学研究";
  return normalized.length > 22 ? `${normalized.slice(0, 22)}...` : normalized || "新研究项目";
}

export function getHypothesisDisplay(hypothesis: Hypothesis, index: number) {
  const method = hypothesis.generation_method ?? "";
  if (method.includes("evolved")) {
    return {
      title: "证据审计式生成协议",
      summary: "要求每个论断经过证据、反例和实验设计检查后才进入候选池。",
    };
  }
  if (method.includes("generated")) {
    return {
      title: "多样性演化搜索",
      summary: "保留多个机制方向，并用相似性惩罚避免候选假设收缩为重复变体。",
    };
  }
  if (method.includes("review")) {
    return {
      title: "可证伪优先实验门控",
      summary: "先定义能推翻假设的观测条件，再决定是否进入昂贵验证。",
    };
  }
  return {
    title: getGeneratedHypothesisTitle(hypothesis, index),
    summary: getGeneratedHypothesisSummary(hypothesis),
  };
}

function getGeneratedHypothesisTitle(hypothesis: Hypothesis, index: number) {
  const text = cleanHypothesisText(hypothesis.text);
  const lower = text.toLowerCase();
  if (lower.includes("action dependency graph")) return "Action Dependency Graph inference framework";
  if (lower.includes("gradient-based error attribution tracker")) return "Gradient-based error attribution tracker";
  if (lower.includes("action-token self-attention")) return "Action-token self-attention comparative pipeline";
  const bold = hypothesis.text.match(/\*\*([^*]{8,100})\*\*/);
  if (bold?.[1]) return toCompactTitle(cleanHypothesisText(bold[1]));
  const quoted = text.match(/'([^']{8,90})'/);
  if (quoted?.[1]) return toCompactTitle(quoted[1]);
  const developed = text.match(/\bdevelop\s+(?:an?|the)?\s*(.{16,130}?)(?:\s+to enable|\s+that\b|\s+which\b|\s+for\b|[.;])/i);
  if (developed?.[1]) return toCompactTitle(developed[1]);
  const firstSentence = text.split(/[.!?]/)[0]?.trim();
  return firstSentence ? toCompactTitle(firstSentence) : `候选假设 ${index + 1}`;
}

function getGeneratedHypothesisSummary(hypothesis: Hypothesis) {
  const source = cleanHypothesisText(hypothesis.explanation || hypothesis.text);
  const firstSentence = source.split(/[.!?]/)[0]?.trim();
  return truncateDisplayText(firstSentence || source, 220);
}

function cleanHypothesisText(value: string) {
  return value
    .replace(/\*\*/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function toCompactTitle(value: string) {
  return truncateDisplayText(value.replace(/^['"]|['"]$/g, "").trim(), 96);
}

function truncateDisplayText(value: string, limit: number) {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 3).trim()}...`;
}

export function getExperimentPlanDisplay(hypothesis: Hypothesis | undefined) {
  if (!hypothesis) return copy.details.noExperiment;
  const method = hypothesis.generation_method ?? "";
  if (method.includes("evolved")) {
    return "与基线生成器对照，测量论断证据精确率、矛盾率、评审偏好和实验设计可复现性。";
  }
  if (method.includes("generated")) {
    return "在同一研究目标下维护多组机制候选，比较多样性、胜率、重复率和最终假设质量。";
  }
  if (method.includes("review")) {
    return "先定义失败观测，再用最小可执行实验排除不可证伪或代价过高的候选。";
  }
  return hypothesis.experiment ? formatBackendText(hypothesis.experiment) : copy.details.noExperiment;
}

export function getCompletedStageCount(record: RunRecord | null) {
  if (!record) return 0;
  const stages = new Set<string>();
  record.timeline.forEach((event) => {
    if (event.status === "complete") stages.add(event.stage);
  });
  return stages.size;
}

export function getActiveStage(record: RunRecord | null) {
  if (!record?.timeline.length) return undefined;
  for (let index = record.timeline.length - 1; index >= 0; index -= 1) {
    if (record.timeline[index].status === "active") return record.timeline[index].stage;
  }
  return undefined;
}

export function getPhaseLabel(record: RunRecord | null) {
  if (record?.status === "error") return "运行失败";
  if (record?.status === "queued") return "等待启动";
  const activeStage = getActiveStage(record);
  if (activeStage) return formatStageLabel(activeStage);
  if (record?.status === "running") return "运行中";
  const completed = getCompletedStageCount(record);
  if (completed > 0) return `${completed}/${workflowPhaseCount} 已完成`;
  return copy.workflow.readyDetail;
}

export function formatScore(score?: number) {
  if (typeof score !== "number") return "暂无";
  if (score <= 1) return String(Math.round(score * 100));
  return String(Math.round(score));
}

export function getSelectedProviderUsable(provider?: ProviderStatus) {
  return Boolean(provider?.usable);
}
