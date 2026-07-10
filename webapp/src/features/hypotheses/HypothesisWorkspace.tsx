import { useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, BookmarkPlus, BookOpen, CheckCircle2, Copy, FileText, FlaskConical, Languages, Link2, ListChecks, MessageSquareText, Trophy } from "lucide-react";
import { Link } from "react-router-dom";
import { MarkdownText } from "../../components/content/MarkdownText";
import { SkeletonState } from "../../components/feedback/states";
import { saveProjectArtifact } from "../../lib/api/workbench";
import { SummaryList } from "../../components/surfaces/cards";
import { parseKnowledgePdf, translateHypothesis } from "../../lib/api/workbench";
import { copy, formatBackendText, formatRunState, formatStageLabel } from "../../lib/formatters/workbench";
import { mapRunToWorkspaceView } from "../../lib/view-models/workbench";
import type { DetailTab, HypothesisPanelTab, RunRecord, TournamentItemViewModel } from "../../types/workbench";
import { TimelinePanel } from "../runs/TimelinePanel";
import { useWorkbench } from "../runs/workbench-context";
import { classNames } from "../../lib/formatters/workbench";
import { useListEntranceMotion } from "../../lib/motion/useAnimeEntrance";
import { useAnimatedNumber } from "../../lib/motion/useAnimatedNumber";

export function HypothesisWorkspace({
  record,
  error,
  isHistoricalDemo,
  selectedIndex,
  setSelectedIndex,
}: {
  record: RunRecord | null;
  error: string | null;
  isHistoricalDemo: boolean;
  selectedIndex: number;
  setSelectedIndex: (index: number) => void;
}) {
  const hypothesisListRef = useRef<HTMLDivElement | null>(null);
  const workspace = useMemo(() => (record ? mapRunToWorkspaceView(record) : null), [record]);
  const hypothesisCount = workspace?.hypotheses.length ?? 0;
  const outputMeta = record
    ? `${formatRunState(record.status)} · ${copy.details.hypothesesCount}: ${hypothesisCount}`
    : "等待候选结果";
  const isGenerating = record?.status === "queued" || record?.status === "running";
  const hasHypotheses = hypothesisCount > 0;
  useListEntranceMotion(hypothesisListRef, `${record?.run_id ?? "empty"}-${hypothesisCount}`);

  return (
    <section className={classNames("output-workspace", !record && !error && "empty")}>
      <header className="output-header">
        <div className="section-title">
          <BarChart3 size={18} />
          <h2>候选假设与证据</h2>
        </div>
        <span>{outputMeta}</span>
      </header>

      {!record && !error ? (
        <div className="output-empty-line">
          先在左侧定义研究目标并生成候选假设；完成后这里会进入“比较假设、查看证据、设计实验、整理报告”的研究推进流。
        </div>
      ) : (
        <div className="output-body">
          {error ? <div className="control-feedback warning" role="status">{copy.workflow.runFailed}</div> : null}
          {isHistoricalDemo ? (
            <div className="status-banner warning" role="status">
              当前仅在只读模式下展示历史合成记录；它不会再进入研究主页、研究项目或研究产出的主产品路径。
            </div>
          ) : null}

          <ResearchFlowGuide
            record={record}
            hypothesisCount={hypothesisCount}
            selectedIndex={selectedIndex}
          />

          {record && hasHypotheses && workspace ? (
            <RankingDecisionSummary
              record={record}
              workspace={workspace}
              selectedIndex={selectedIndex}
              onSelectHypothesis={setSelectedIndex}
            />
          ) : null}

          <section className="inspector">
            <header className="subsection-header">
              <h3>候选假设</h3>
              <span>
                {hasHypotheses
                  ? "先比较三条候选，再打开选中假设的证据。"
                  : "运行完成后会出现可比较的候选方向。"}
              </span>
            </header>
            {hasHypotheses && workspace ? (
              <div className="hypothesis-list hypothesis-list-with-side-panel" ref={hypothesisListRef} role="listbox" aria-label="候选假设列表">
                {workspace.hypotheses.map((hypothesis, index) => (
                  <HypothesisCard
                    key={hypothesis.id}
                    hypothesis={hypothesis}
                    index={index}
                    selected={selectedIndex === index}
                    onSelect={() => setSelectedIndex(index)}
                  />
                ))}
              </div>
            ) : isGenerating ? (
              <SkeletonState title="正在生成候选假设" rows={3} />
            ) : (
              <div className="inline-empty">结果会在这里展示候选方向、评分、实验入口和证据摘要。</div>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

type WorkspaceView = ReturnType<typeof mapRunToWorkspaceView>;
type WorkspaceHypothesis = WorkspaceView["hypotheses"][number];

function mapPanelTabToDetailTab(tab: HypothesisPanelTab): DetailTab | null {
  if (tab === "translation" || tab === "ai" || tab === "report") return null;
  return tab;
}

function getHypothesisFullClipboardText(hypothesis: WorkspaceHypothesis) {
  return [
    `# ${hypothesis.title}`,
    "",
    "## 完整技术假设",
    hypothesis.raw.text || hypothesis.summary,
    "",
    "## 通俗解释",
    hypothesis.raw.explanation || hypothesis.summary || copy.details.noHypothesis,
    "",
    "## 实验计划",
    hypothesis.raw.experiment || hypothesis.experimentPlan || copy.details.noExperiment,
    "",
    "## 文献/证据边界",
    hypothesis.grounding || copy.details.noGrounding,
  ].join("\n");
}

type RankingRow = {
  sourceIndex: number;
  rank: number;
  hypothesis: WorkspaceHypothesis;
  hypothesisId: string;
  finalElo: number | null;
  finalEloLabel: string;
  wins: number;
  losses: number;
};

type MatchupBrief = {
  id: string;
  label: string;
  winnerLabel: string;
  loserLabel: string;
  confidenceLabel: string;
  winnerEloLabel: string;
  loserEloLabel: string;
  reasoning: string;
};

function RankingDecisionSummary({
  record,
  workspace,
  selectedIndex,
  onSelectHypothesis,
}: {
  record: RunRecord;
  workspace: WorkspaceView;
  selectedIndex: number;
  onSelectHypothesis: (index: number) => void;
}) {
  const hypothesisIdByIndex = getHypothesisIdByIndex(record, workspace.hypotheses);
  const hypothesisIndexById = new Map(
    [...hypothesisIdByIndex.entries()].map(([index, id]) => [id, index] as const),
  );
  const winLossById = getWinLossByHypothesisId(record);
  const rankingRows = workspace.hypotheses
    .map((hypothesis, sourceIndex) => {
      const hypothesisId = hypothesisIdByIndex.get(sourceIndex) ?? "";
      const matchupRecord = hypothesisId ? winLossById.get(hypothesisId) : undefined;
      const finalElo = readNumber(hypothesis.raw.elo_rating) ?? readNumber(hypothesis.rankLabel);
      return {
        sourceIndex,
        rank: 0,
        hypothesis,
        hypothesisId,
        finalElo,
        finalEloLabel: finalElo === null ? hypothesis.rankLabel : String(Math.round(finalElo)),
        wins: matchupRecord?.wins ?? hypothesis.raw.win_count ?? 0,
        losses: matchupRecord?.losses ?? hypothesis.raw.loss_count ?? 0,
      };
    })
    .sort((left, right) => {
      const rightElo = right.finalElo ?? Number.NEGATIVE_INFINITY;
      const leftElo = left.finalElo ?? Number.NEGATIVE_INFINITY;
      if (rightElo !== leftElo) return rightElo - leftElo;
      return right.wins - left.wins || left.losses - right.losses || left.sourceIndex - right.sourceIndex;
    })
    .map((row, index) => ({ ...row, rank: index + 1 }));
  const matchupBriefs = getMatchupBriefs(record, workspace.hypotheses, hypothesisIndexById);
  const topRow = rankingRows[0];
  const secondRow = rankingRows[1];
  const conclusion = buildRankingConclusion(rankingRows);

  if (!topRow) return null;

  return (
    <section className="ranking-decision-summary" aria-label="Elo 锦标赛排序摘要">
      <header className="ranking-summary-header">
        <div>
          <span className="ranking-kicker">
            <Trophy size={16} />
            Elo 锦标赛
          </span>
          <h3>当前推荐排序</h3>
          <p>{conclusion}</p>
        </div>
        <div className="ranking-summary-counts" aria-label="排序统计">
          <span>{rankingRows.length} 条假设</span>
          <strong>{record.tournament_matchups.length} 场比较</strong>
        </div>
      </header>

      <div className="ranking-table" role="list" aria-label="按 Final Elo 排序的候选假设">
        {rankingRows.map((row) => (
          <article
            className={classNames("ranking-row", selectedIndex === row.sourceIndex && "selected")}
            key={`${row.sourceIndex}-${row.hypothesis.id}`}
            role="listitem"
            onClick={() => onSelectHypothesis(row.sourceIndex)}
          >
            <span className="ranking-position">#{row.rank}</span>
            <span className="ranking-hypothesis-copy">
              <strong>H{row.sourceIndex + 1}: {row.hypothesis.title}</strong>
              <em>{row.hypothesis.summary}</em>
            </span>
            <span className="ranking-metric-strip">
              <span className="ranking-score-pill">
                <small>Final Elo</small>
                <strong>{row.finalEloLabel}</strong>
              </span>
              <span className="ranking-record-pill">
                <small>战绩</small>
                <strong>{row.wins}W-{row.losses}L</strong>
              </span>
            </span>
          </article>
        ))}
      </div>

      {matchupBriefs.length > 0 ? (
        <div className="matchup-brief-list" aria-label="关键 Elo 对局">
          <div className="matchup-brief-heading">
            <strong>对局依据</strong>
            <span>
              {topRow && secondRow
                ? `优先查看 ${getShortHypothesisLabel(topRow.sourceIndex)} 与 ${getShortHypothesisLabel(secondRow.sourceIndex)} 的胜负依据。`
                : "查看每场成对比较的胜负、置信度和 Elo 变化。"}
            </span>
          </div>
          {matchupBriefs.map((matchup) => (
            <article className="matchup-brief-card" key={matchup.id}>
              <header>
                <strong>{matchup.label}</strong>
                <span>{matchup.winnerLabel} 胜出</span>
              </header>
              <dl className="matchup-elo-grid">
                <div>
                  <dt>Winner</dt>
                  <dd>{matchup.winnerLabel}</dd>
                </div>
                <div>
                  <dt>Loser</dt>
                  <dd>{matchup.loserLabel}</dd>
                </div>
                <div>
                  <dt>Confidence</dt>
                  <dd>{matchup.confidenceLabel}</dd>
                </div>
                <div>
                  <dt>Winner Elo</dt>
                  <dd>{matchup.winnerEloLabel}</dd>
                </div>
                <div>
                  <dt>Loser Elo</dt>
                  <dd>{matchup.loserEloLabel}</dd>
                </div>
              </dl>
              <p>{matchup.reasoning}</p>
              <details className="matchup-full-reasoning">
                <summary>查看全部裁判理由</summary>
                <MarkdownText text={matchup.reasoning} compact />
              </details>
            </article>
          ))}
        </div>
      ) : (
        <div className="inline-empty">当前运行尚未记录 Elo 对局；只能按候选假设自身评分浏览。</div>
      )}
    </section>
  );
}

function buildRankingConclusion(rows: RankingRow[]) {
  const top = rows[0];
  const runnerUp = rows[1];
  if (!top) return "等待 Elo 锦标赛完成后，这里会展示当前最值得优先审查的假设。";
  const topLabel = getShortHypothesisLabel(top.sourceIndex);
  if (!runnerUp) return `${topLabel} 是当前唯一候选，请补充更多候选后再做成对比较。`;
  const runnerUpLabel = getShortHypothesisLabel(runnerUp.sourceIndex);
  if (top.wins > 0) {
    return `${topLabel} 当前排第一，因为它在 pairwise tournament 中取得 ${top.wins}W-${top.losses}L；${runnerUpLabel} 排第二，需要继续检查证据和可证伪实验。`;
  }
  return `${topLabel} 当前 Final Elo 最高；请继续查看对局依据，确认它是否真的优于 ${runnerUpLabel}。`;
}

function getShortHypothesisLabel(index: number) {
  return `H${index + 1}`;
}

function getHypothesisIdByIndex(record: RunRecord, hypotheses: WorkspaceHypothesis[]) {
  const result = new Map<number, string>();
  for (const matchup of record.tournament_matchups) {
    const aId = readString(matchup.hypothesis_a_id);
    const bId = readString(matchup.hypothesis_b_id);
    const aIndex = findHypothesisIndex(hypotheses, readString(matchup.hypothesis_a));
    const bIndex = findHypothesisIndex(hypotheses, readString(matchup.hypothesis_b));
    if (aId && aIndex !== null) result.set(aIndex, aId);
    if (bId && bIndex !== null) result.set(bIndex, bId);
  }
  return result;
}

function findHypothesisIndex(hypotheses: WorkspaceHypothesis[], matchupText: string) {
  if (!matchupText) return null;
  const normalizedMatchup = normalizeHypothesisText(matchupText);
  const stablePrefix = normalizedMatchup.slice(0, 96);
  for (const [index, hypothesis] of hypotheses.entries()) {
    const normalizedHypothesis = normalizeHypothesisText(hypothesis.raw.text);
    if (
      normalizedHypothesis === normalizedMatchup ||
      normalizedHypothesis.startsWith(stablePrefix) ||
      normalizedMatchup.startsWith(normalizedHypothesis.slice(0, 96))
    ) {
      return index;
    }
  }
  return null;
}

function normalizeHypothesisText(value: string) {
  return value.replace(/\s+/g, " ").replace(/\*\*/g, "").trim().toLowerCase();
}

function getWinLossByHypothesisId(record: RunRecord) {
  const result = new Map<string, { wins: number; losses: number }>();
  const ensure = (id: string) => {
    if (!result.has(id)) result.set(id, { wins: 0, losses: 0 });
    return result.get(id)!;
  };
  for (const matchup of record.tournament_matchups) {
    const resolved = resolveMatchupWinnerLoser(matchup);
    if (resolved.winnerId) ensure(resolved.winnerId).wins += 1;
    if (resolved.loserId) ensure(resolved.loserId).losses += 1;
  }
  return result;
}

function getMatchupBriefs(
  record: RunRecord,
  hypotheses: WorkspaceHypothesis[],
  hypothesisIndexById: Map<string, number>,
): MatchupBrief[] {
  return record.tournament_matchups.slice(0, 6).map((matchup, index) => {
    const resolved = resolveMatchupWinnerLoser(matchup);
    const winnerIndex = resolved.winnerId ? hypothesisIndexById.get(resolved.winnerId) : undefined;
    const loserIndex = resolved.loserId ? hypothesisIndexById.get(resolved.loserId) : undefined;
    const beforeMap = readNumberMap(matchup.before_elo);
    const afterMap = readNumberMap(matchup.after_elo);
    const deltaMap = readNumberMap(matchup.elo_delta);
    const winnerBefore = getMapNumber(beforeMap, resolved.winnerId) ?? readNumber(matchup.winner_elo_before);
    const winnerAfter = getMapNumber(afterMap, resolved.winnerId) ?? readNumber(matchup.winner_elo_after);
    const winnerDelta = getMapNumber(deltaMap, resolved.winnerId) ?? readNumber(matchup.winner_elo_delta);
    const loserBefore = getMapNumber(beforeMap, resolved.loserId) ?? readNumber(matchup.loser_elo_before);
    const loserAfter = getMapNumber(afterMap, resolved.loserId) ?? readNumber(matchup.loser_elo_after);
    const loserDelta = getMapNumber(deltaMap, resolved.loserId) ?? readNumber(matchup.loser_elo_delta);
    const confidenceLevel = readString(matchup.confidence_level) || readString(matchup.confidence, "Unknown");
    const confidenceScore = readNumber(matchup.confidence_score);
    const confidenceLabel =
      confidenceScore === null
        ? formatBackendText(confidenceLevel)
        : `${formatBackendText(confidenceLevel)}, score ${confidenceScore.toFixed(2)}`;
    return {
      id: readString(matchup.matchup_id, `matchup-${index + 1}`),
      label: `Match ${readNumber(matchup.round) ?? index + 1}`,
      winnerLabel: formatMatchupHypothesisLabel(winnerIndex, hypotheses),
      loserLabel: formatMatchupHypothesisLabel(loserIndex, hypotheses),
      confidenceLabel,
      winnerEloLabel: formatEloTransition(winnerBefore, winnerAfter, winnerDelta),
      loserEloLabel: formatEloTransition(loserBefore, loserAfter, loserDelta),
      reasoning: formatBackendText(
        readString(matchup.reasoning) ||
          readString(matchup.reason) ||
          readString(matchup.rationale) ||
          "已记录成对比较，但没有返回可展示的裁判理由。",
      ),
    };
  });
}

function resolveMatchupWinnerLoser(matchup: Record<string, unknown>) {
  const winner = readString(matchup.winner).toLowerCase();
  const loser = readString(matchup.loser).toLowerCase();
  const hypothesisAId = readString(matchup.hypothesis_a_id);
  const hypothesisBId = readString(matchup.hypothesis_b_id);
  const winnerId =
    readString(matchup.winner_id) ||
    (winner === "a" ? hypothesisAId : winner === "b" ? hypothesisBId : "");
  const loserId =
    readString(matchup.loser_id) ||
    (loser === "a" ? hypothesisAId : loser === "b" ? hypothesisBId : winner === "a" ? hypothesisBId : winner === "b" ? hypothesisAId : "");
  return { winnerId, loserId };
}

function formatMatchupHypothesisLabel(index: number | undefined, hypotheses: WorkspaceHypothesis[]) {
  if (index === undefined) return "未记录";
  const hypothesis = hypotheses[index];
  if (!hypothesis) return getShortHypothesisLabel(index);
  return getShortHypothesisLabel(index);
}

function readString(value: unknown, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function readNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function readNumberMap(value: unknown) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, item]) => [key, readNumber(item)] as const)
      .filter((entry): entry is readonly [string, number] => entry[1] !== null),
  );
}

function getMapNumber(map: Record<string, number>, key: string) {
  return key ? map[key] ?? null : null;
}

function formatEloTransition(before: number | null, after: number | null, delta: number | null) {
  if (before === null || after === null) return "Elo 未记录";
  const resolvedDelta = delta ?? after - before;
  const deltaLabel = resolvedDelta > 0 ? `+${resolvedDelta}` : String(resolvedDelta);
  return `${before} -> ${after} (${deltaLabel})`;
}

function ResearchFlowGuide({
  record,
  hypothesisCount,
  selectedIndex,
}: {
  record: RunRecord | null;
  hypothesisCount: number;
  selectedIndex: number;
}) {
  const isGenerating = record?.status === "queued" || record?.status === "running";
  const hasHypotheses = hypothesisCount > 0;
  const selectedLabel = hasHypotheses ? `#${Math.min(selectedIndex + 1, hypothesisCount)}` : "待选择";
  const steps = [
    {
      label: "生成候选",
      state: record ? "done" : "active",
    },
    {
      label: "比较假设",
      state: hasHypotheses ? "active" : isGenerating ? "pending" : "upcoming",
    },
    {
      label: "查看证据",
      state: hasHypotheses ? "available" : "upcoming",
    },
    {
      label: "实验设计",
      state: hasHypotheses ? "available" : "upcoming",
    },
    {
      label: "报告草稿",
      state: hasHypotheses ? "available" : "upcoming",
    },
  ];
  const title = hasHypotheses
    ? `下一步：审查 ${selectedLabel} 的证据，再决定是否进入实验`
    : isGenerating
      ? "当前步骤：等待候选假设生成完成"
      : "当前步骤：先生成候选假设";
  const description = hasHypotheses
    ? "页面不会默认展开全部细节；请选择一条候选假设，按需打开参考文献和过程证据。"
    : "生成完成后，系统会把结果组织成可比较的候选假设，而不是散落的运行日志。";

  return (
    <section className="research-flow-guide" aria-label="研究推进步骤">
      <ol className="research-flow-steps">
        {steps.map((step, index) => (
          <li className={step.state} key={step.label}>
            <span>{index + 1}</span>
            <strong>{step.label}</strong>
          </li>
        ))}
      </ol>
      <div className="research-flow-next">
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
    </section>
  );
}

function HypothesisCard({
  hypothesis,
  index,
  selected,
  onSelect,
}: {
  hypothesis: NonNullable<ReturnType<typeof mapRunToWorkspaceView>["hypotheses"][number]>;
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const scoreValue = Number(hypothesis.scoreLabel);
  const rankValue = Number(hypothesis.rankLabel);
  const animatedScore = useAnimatedNumber(Number.isFinite(scoreValue) ? scoreValue : 0);
  const animatedRank = useAnimatedNumber(Number.isFinite(rankValue) ? rankValue : 0);

  return (
    <article className={classNames("hypothesis-card", selected && "selected")} role="option" aria-selected={selected}>
      <button className="hypothesis-card-main" onClick={onSelect} type="button" aria-pressed={selected}>
        <span className="rank">#{index + 1}</span>
        <strong>{hypothesis.title}</strong>
        <em>{hypothesis.summary}</em>
        <span className="meta-line">
          <span>分数 {Number.isFinite(scoreValue) ? animatedScore : hypothesis.scoreLabel}</span>
          <span>排序 {Number.isFinite(rankValue) ? animatedRank : hypothesis.rankLabel}</span>
        </span>
        <StatusBadgeRow items={hypothesis.evidenceBadges} />
      </button>
    </article>
  );
}

export function HypothesisSidePanelContent({
  record,
  error,
  isHistoricalDemo,
}: {
  record: RunRecord | null;
  error: string | null;
  isHistoricalDemo: boolean;
}) {
  const {
    selectedIndex,
    activeHypothesisPanelTab,
    setActiveHypothesisPanelTab,
    setActiveDetailTab,
  } = useWorkbench();
  const [translations, setTranslations] = useState<Record<string, string>>({});
  const [translationLoadingId, setTranslationLoadingId] = useState<string | null>(null);
  const [translationErrorId, setTranslationErrorId] = useState<string | null>(null);
  const [copiedHypothesisId, setCopiedHypothesisId] = useState<string | null>(null);
  const [artifactSaving, setArtifactSaving] = useState(false);
  const [artifactSavedId, setArtifactSavedId] = useState<string | null>(null);
  const [evidenceSaving, setEvidenceSaving] = useState(false);
  const [evidenceSavedId, setEvidenceSavedId] = useState<string | null>(null);
  const workspace = useMemo(() => (record ? mapRunToWorkspaceView(record) : null), [record]);
  const selectedHypothesis = workspace?.hypotheses[selectedIndex] ?? workspace?.hypotheses[0];

  const openPanelTab = (tab: HypothesisPanelTab) => {
    setActiveHypothesisPanelTab(tab);
    const detailTab = mapPanelTabToDetailTab(tab);
    if (detailTab) setActiveDetailTab(detailTab);
  };

  const handleTranslate = async (target = selectedHypothesis) => {
    if (!record || !target || translationLoadingId) return;
    setTranslationLoadingId(target.id);
    setTranslationErrorId(null);
    try {
      const result = await translateHypothesis({
        model_name: record.request.model_name,
        text: target.raw.text,
        explanation: target.raw.explanation,
        experiment: target.raw.experiment,
      });
      setTranslations((existing) => ({
        ...existing,
        [target.id]: result.translation,
      }));
    } catch {
      setTranslationErrorId(target.id);
    } finally {
      setTranslationLoadingId(null);
    }
  };

  const handleCopyHypothesis = async (target = selectedHypothesis) => {
    if (!target) return;
    const text = getHypothesisFullClipboardText(target);
    if (!text.trim()) return;
    await navigator.clipboard.writeText(text);
    setCopiedHypothesisId(target.id);
    window.setTimeout(() => setCopiedHypothesisId((existing) => (existing === target.id ? null : existing)), 1600);
  };

  const handleSaveHypothesis = async () => {
    if (!record || !selectedHypothesis || artifactSaving) return;
    setArtifactSaving(true);
    try {
      const result = await saveProjectArtifact({
        project_id: record.run_id,
        run_id: record.run_id,
        artifact_type: "hypothesis",
        target_ref: {
          hypothesis_index: selectedIndex,
          hypothesis_id: selectedHypothesis.id,
        },
        title: selectedHypothesis.title,
        payload: {
          text: selectedHypothesis.raw.text,
          explanation: selectedHypothesis.raw.explanation,
          experiment: selectedHypothesis.raw.experiment,
          score: selectedHypothesis.raw.score,
          elo_rating: selectedHypothesis.raw.elo_rating,
          demo_mode: record.request.demo_mode,
        },
      });
      setArtifactSavedId(result.artifact.artifact_id);
    } catch {
      setArtifactSavedId(null);
    } finally {
      setArtifactSaving(false);
    }
  };

  const handleSaveEvidence = async () => {
    if (!record || !selectedHypothesis || evidenceSaving) return;
    setEvidenceSaving(true);
    try {
      const result = await saveProjectArtifact({
        project_id: record.run_id,
        run_id: record.run_id,
        artifact_type: "evidence_link",
        target_ref: {
          hypothesis_index: selectedIndex,
          hypothesis_id: selectedHypothesis.id,
        },
        title: `${selectedHypothesis.title} 的证据入口`,
        payload: {
          grounding: selectedHypothesis.grounding,
          reference_range: selectedHypothesis.referenceRangeLabel,
          citations: selectedHypothesis.citations,
          citation_support: selectedHypothesis.citationSupportItems,
          pdf_candidates: selectedHypothesis.citationPdfCandidates,
          demo_mode: record.request.demo_mode,
        },
      });
      setEvidenceSavedId(result.artifact.artifact_id);
    } catch {
      setEvidenceSavedId(null);
    } finally {
      setEvidenceSaving(false);
    }
  };

  if (!record || !workspace || !selectedHypothesis) {
    return (
      <section className="side-panel-section">
        <div className="inline-empty">选择一个已完成的研究项目后，这里会显示假设全文、参考文献和报告草稿。</div>
      </section>
    );
  }

  return (
    <SelectedHypothesisPanel
      record={record}
      error={error}
      isHistoricalDemo={isHistoricalDemo}
      workspace={workspace}
      hypothesis={selectedHypothesis}
      selectedIndex={selectedIndex}
      activePanelTab={activeHypothesisPanelTab}
      onSetPanelTab={openPanelTab}
      translation={translations[selectedHypothesis.id]}
      translationLoading={translationLoadingId === selectedHypothesis.id}
      translationError={translationErrorId === selectedHypothesis.id}
      copied={copiedHypothesisId === selectedHypothesis.id}
      onCopy={() => void handleCopyHypothesis()}
      onTranslate={() => void handleTranslate()}
      onSave={() => void handleSaveHypothesis()}
      artifactSaving={artifactSaving}
      artifactSaved={artifactSavedId !== null}
      onSaveEvidence={() => void handleSaveEvidence()}
      evidenceSaving={evidenceSaving}
      evidenceSaved={evidenceSavedId !== null}
    />
  );
}

function SelectedHypothesisPanel({
  record,
  error,
  isHistoricalDemo,
  workspace,
  hypothesis,
  selectedIndex,
  activePanelTab,
  onSetPanelTab,
  translation,
  translationLoading,
  translationError,
  copied,
  onCopy,
  onTranslate,
  onSave,
  artifactSaving,
  artifactSaved,
  onSaveEvidence,
  evidenceSaving,
  evidenceSaved,
}: {
  record: RunRecord | null;
  error: string | null;
  isHistoricalDemo: boolean;
  workspace: ReturnType<typeof mapRunToWorkspaceView> | null;
  hypothesis: ReturnType<typeof mapRunToWorkspaceView>["hypotheses"][number] | undefined;
  selectedIndex: number;
  activePanelTab: HypothesisPanelTab;
  onSetPanelTab: (tab: HypothesisPanelTab) => void;
  translation?: string;
  translationLoading: boolean;
  translationError: boolean;
  copied: boolean;
  onCopy: () => void;
  onTranslate: () => void;
  onSave: () => void;
  artifactSaving: boolean;
  artifactSaved: boolean;
  onSaveEvidence: () => void;
  evidenceSaving: boolean;
  evidenceSaved: boolean;
}) {
  if (!record || !hypothesis) return null;

  const citationCount = hypothesis.citations.length;
  const openTranslation = () => {
    onSetPanelTab("translation");
    void onTranslate();
  };

  return (
    <aside className="selected-hypothesis-panel" aria-live="polite">
      <div className="decision-kicker">
        <ListChecks size={16} />
        <span>当前选择</span>
      </div>
      <div className="decision-title">
        <strong>#{selectedIndex + 1} {hypothesis.title}</strong>
        <p>{hypothesis.summary}</p>
      </div>
      <div className="decision-checklist">
        <button className="decision-check active" type="button" onClick={() => onSetPanelTab("tournament")}>
          <CheckCircle2 size={16} />
          <span>先确认这条假设是否比其他候选更值得验证。</span>
        </button>
        <button className="decision-check" type="button" onClick={() => onSetPanelTab("evidence")}>
          <BookOpen size={16} />
          <span>{citationCount > 0 ? `已有 ${citationCount} 条证据入口，目标范围：${hypothesis.referenceRangeLabel}。` : `参考文献目标范围：${hypothesis.referenceRangeLabel}；没有来源时不要写成确定结论。`}</span>
        </button>
        <button className="decision-check" type="button" onClick={() => onSetPanelTab("evidence")}>
          <BookOpen size={16} />
          <span>{hypothesis.citationSupportItems.length > 0 ? "已标注每条来源的支撑级别，可在参考文献中逐条核验。" : "来源支撑级别尚不足，进入实验前需要补齐文献证据。"}</span>
        </button>
        <button className="decision-check" type="button" onClick={() => onSetPanelTab("metrics")}>
          <CheckCircle2 size={16} />
          <span>{hypothesis.governanceBadges.map((item) => item.label).join("；")}。</span>
        </button>
        <button className="decision-check" type="button" onClick={() => onSetPanelTab("hypotheses")}>
          <FlaskConical size={16} />
          <span>证据足够后再进入实验设计，检查可证伪条件和评估指标。</span>
        </button>
      </div>
      <div className="decision-actions hypothesis-panel-action-grid">
        <button className="button-secondary" type="button" onClick={() => onSetPanelTab("hypotheses")}>
          <FileText size={16} />
          展开全文
        </button>
        <button className="button-secondary" type="button" onClick={onCopy}>
          <Copy size={16} />
          {copied ? "已复制全文" : "复制全文"}
        </button>
        <button className="button-secondary" type="button" onClick={openTranslation} disabled={translationLoading}>
          <Languages size={16} />
          {translationLoading ? "正在翻译" : translation ? "刷新中文译文" : "翻译中文"}
        </button>
        <button className="button-secondary" type="button" onClick={() => onSetPanelTab("evidence")}>
          <BookOpen size={16} />
          查看参考文献
        </button>
        <button className="button-secondary" type="button" onClick={onSaveEvidence} disabled={evidenceSaving} aria-busy={evidenceSaving}>
          <Link2 size={16} />
          {evidenceSaving ? "正在保存证据" : evidenceSaved ? "证据已加入项目" : "加入证据链"}
        </button>
        <button className="button-secondary" type="button" onClick={onSave} disabled={artifactSaving} aria-busy={artifactSaving}>
          <BookmarkPlus size={16} />
          {artifactSaving ? "正在保存" : artifactSaved ? "已保存到项目" : "保存到项目"}
        </button>
        <button className="button-secondary" type="button" onClick={() => onSetPanelTab("ai")}>
          <MessageSquareText size={16} />
          与项目 AI 分析
        </button>
        <Link className="button-primary" to={`/projects/${record.run_id}/experiments`}>
          <FlaskConical size={16} />
          进入实验设计
        </Link>
        <button className="button-ghost" type="button" onClick={() => onSetPanelTab("report")}>
          <FileText size={16} />
          AI 整理报告草稿
        </button>
        <button className="button-ghost" type="button" onClick={() => onSetPanelTab("agents")}>
          <ListChecks size={16} />
          过程记录
        </button>
      </div>
      <HypothesisPanelTabs
        activeTab={activePanelTab}
        setActiveTab={onSetPanelTab}
        record={record}
        error={error}
        isHistoricalDemo={isHistoricalDemo}
        workspace={workspace}
        selectedIndex={selectedIndex}
        translation={translation}
        translationLoading={translationLoading}
        translationError={translationError}
        copied={copied}
        onCopy={onCopy}
        onTranslate={openTranslation}
      />
    </aside>
  );
}

function HypothesisPanelTabs({
  activeTab,
  setActiveTab,
  record,
  error,
  isHistoricalDemo,
  workspace,
  selectedIndex,
  translation,
  translationLoading,
  translationError,
  copied,
  onCopy,
  onTranslate,
}: {
  activeTab: HypothesisPanelTab;
  setActiveTab: (tab: HypothesisPanelTab) => void;
  record: RunRecord | null;
  error: string | null;
  isHistoricalDemo: boolean;
  workspace: ReturnType<typeof mapRunToWorkspaceView> | null;
  selectedIndex: number;
  translation?: string;
  translationLoading: boolean;
  translationError: boolean;
  copied: boolean;
  onCopy: () => void;
  onTranslate: () => void;
}) {
  const tabs: Array<{ id: HypothesisPanelTab; label: string }> = [
    { id: "overview", label: "计划" },
    { id: "hypotheses", label: "全文" },
    { id: "evidence", label: "参考" },
    { id: "translation", label: "翻译" },
    { id: "ai", label: "AI" },
    { id: "report", label: "报告" },
    { id: "agents", label: "过程" },
    { id: "tournament", label: "排序" },
    { id: "metrics", label: "质量" },
  ];
  const selectedHypothesis = workspace?.hypotheses[selectedIndex] ?? workspace?.hypotheses[0];

  return (
    <section className="details-panel hypothesis-side-tabs">
      <div className="tab-list hypothesis-side-tab-list" role="tablist" aria-label="假设右侧功能">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={classNames("tab-button", activeTab === tab.id && "active")}
            onClick={() => setActiveTab(tab.id)}
            role="tab"
            aria-selected={activeTab === tab.id}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="tab-content">
        {activeTab === "overview" ? (
          <div className="detail-copy">
            <h3>{copy.details.planSummary}</h3>
            <SummaryList items={workspace?.planItems ?? []} empty={record ? copy.details.summaryEmpty : copy.details.noPlan} />
          </div>
        ) : null}
        {activeTab === "agents" ? (
          <ProcessRecordPanel record={record} error={error} isHistoricalDemo={isHistoricalDemo} />
        ) : null}
        {activeTab === "hypotheses" ? (
          <HypothesisFullDetail
            hypothesis={selectedHypothesis}
            selectedIndex={selectedIndex}
            allHypotheses={workspace?.hypotheses ?? []}
            translation={translation}
            translationLoading={translationLoading}
            translationError={translationError}
            copied={copied}
            onCopy={onCopy}
            onTranslate={onTranslate}
          />
        ) : null}
        {activeTab === "evidence" ? (
          <ReferencePanelContent hypothesis={selectedHypothesis} />
        ) : null}
        {activeTab === "translation" ? (
          <TranslationTabPanel
            hypothesis={selectedHypothesis}
            translation={translation}
            translationLoading={translationLoading}
            translationError={translationError}
            onTranslate={onTranslate}
          />
        ) : null}
        {activeTab === "ai" ? (
          <AiAnalysisPanel record={record} hypothesis={selectedHypothesis} selectedIndex={selectedIndex} />
        ) : null}
        {activeTab === "report" ? (
          <ReportDraftPanel record={record} hypothesis={selectedHypothesis} selectedIndex={selectedIndex} />
        ) : null}
        {activeTab === "tournament" ? (
          <TournamentList items={workspace?.tournamentItems ?? []} empty={copy.details.tournamentEmpty} />
        ) : null}
        {activeTab === "metrics" ? (
          <SummaryList items={workspace?.metricItems ?? []} empty={copy.details.metricsEmpty} />
        ) : null}
      </div>
    </section>
  );
}

function ReferencePanelContent({ hypothesis }: { hypothesis: WorkspaceHypothesis | undefined }) {
  const [parsingPdfKey, setParsingPdfKey] = useState<string | null>(null);
  const [parsePdfMessage, setParsePdfMessage] = useState("");
  const [parsePdfStatus, setParsePdfStatus] = useState<"idle" | "success" | "error">("idle");

  if (!hypothesis) {
    return <div className="inline-empty">{copy.details.noGrounding}</div>;
  }

  const isDemoGrounding = /演示|模拟|历史合成|暂无真实文献|未查询真实文献/.test(hypothesis.grounding);

  const handleParsePdf = async (candidateKey: string, pdfPath: string) => {
    setParsingPdfKey(candidateKey);
    setParsePdfStatus("idle");
    setParsePdfMessage("");
    try {
      const result = await parseKnowledgePdf({
        pdf_path: pdfPath,
        fetch_metadata: true,
        ingest_to_knowledge_base: true,
      });
      setParsePdfStatus("success");
      setParsePdfMessage(`已解析并写入知识库：${result.title}；生成 ${result.chunks_count} 个层级片段和 ${result.media_assets.length} 个媒体线索。`);
    } catch {
      setParsePdfStatus("error");
      setParsePdfMessage("PDF 暂时无法解析。请确认链接可直接访问 PDF，或在资料管理页使用本机 PDF 路径解析。");
    } finally {
      setParsingPdfKey(null);
    }
  };

  return (
    <div className="reference-tab-panel">
      <section className="readable-block">
        <h4>{copy.details.literatureGrounding}</h4>
        <div className="status-badge-row">
          {[...hypothesis.evidenceBadges, ...hypothesis.governanceBadges].map((item) => (
            <span className={classNames("status-pill", item.tone)} key={`${item.label}-${item.tone}`}>
              {item.label}
            </span>
          ))}
        </div>
        <MarkdownText text={hypothesis.grounding || copy.details.noGrounding} compact />
      </section>

      <section className="readable-block">
        <h4>{copy.details.citationMap}</h4>
        <p className="reference-range">{hypothesis.referenceRangeLabel}</p>
        <SummaryList items={hypothesis.citations} empty="当前假设暂无可解析参考文献。" />
      </section>

      <section className="readable-block">
        <h4>PDF 解析</h4>
        {hypothesis.citationPdfCandidates.length > 0 ? (
          <div className="pdf-candidate-list">
            {hypothesis.citationPdfCandidates.map((candidate) => (
              <article className="pdf-candidate-row" key={candidate.key}>
                <div>
                  <strong>{candidate.title}</strong>
                  <span>{candidate.supportLabel}</span>
                </div>
                <button
                  className={classNames("button-secondary", parsingPdfKey === candidate.key && "is-loading")}
                  type="button"
                  disabled={Boolean(parsingPdfKey)}
                  aria-busy={parsingPdfKey === candidate.key}
                  onClick={() => void handleParsePdf(candidate.key, candidate.pdfPath)}
                >
                  {parsingPdfKey === candidate.key ? "正在解析" : "解析 PDF"}
                </button>
              </article>
            ))}
          </div>
        ) : (
          <p className="drawer-note">当前来源没有可直接解析的 PDF 路径或链接。</p>
        )}
        {parsePdfMessage ? (
          <p className={classNames("control-feedback", parsePdfStatus === "error" ? "error" : "success")} role={parsePdfStatus === "error" ? "alert" : "status"}>
            {parsePdfMessage}
          </p>
        ) : null}
      </section>

      <EvidenceDetailPanel hypothesis={hypothesis} />

      {isDemoGrounding ? (
        <p className="drawer-note">当前显示的是历史合成记录保留下来的证据占位；新的研究运行应在实时文献支撑路径下生成真实来源元数据。</p>
      ) : null}
    </div>
  );
}

function TranslationTabPanel({
  hypothesis,
  translation,
  translationLoading,
  translationError,
  onTranslate,
}: {
  hypothesis: WorkspaceHypothesis | undefined;
  translation?: string;
  translationLoading: boolean;
  translationError: boolean;
  onTranslate: () => void;
}) {
  if (!hypothesis) return <div className="inline-empty">{copy.details.selectCompleted}</div>;
  return (
    <div className="translation-tab-panel">
      <section className="readable-block">
        <header className="detail-section-header">
          <div>
            <span className="section-kicker">中文查看</span>
            <h3>{hypothesis.title}</h3>
          </div>
          <button className="button-secondary" type="button" onClick={onTranslate} disabled={translationLoading} aria-busy={translationLoading}>
            <Languages size={16} />
            {translationLoading ? "正在翻译" : translation ? "刷新译文" : "翻译中文"}
          </button>
        </header>
        {translation ? (
          <MarkdownText text={translation} />
        ) : (
          <p className="muted-note">点击“翻译中文”后，这里会显示模型整理后的中文译文；原始英文全文仍保留在“全文”tab。</p>
        )}
        {translationError ? <div className="control-feedback warning" role="status">暂时无法生成中文译文，请稍后重试。</div> : null}
      </section>
    </div>
  );
}

function AiAnalysisPanel({
  record,
  hypothesis,
  selectedIndex,
}: {
  record: RunRecord | null;
  hypothesis: WorkspaceHypothesis | undefined;
  selectedIndex: number;
}) {
  if (!record || !hypothesis) return <div className="inline-empty">请选择一条假设后再调用项目 AI。</div>;
  return (
    <div className="ai-tab-panel">
      <section className="readable-block">
        <h4>与项目 AI 分析</h4>
        <p className="muted-note">把当前假设、项目论文、证据边界和实验计划带入项目 AI，继续追问实验设计、反证检查或报告组织。</p>
        <div className="panel-link-stack">
          <Link className="button-primary" to={`/project-chat?run=${record.run_id}&hypothesis=${selectedIndex}`}>
            <MessageSquareText size={16} />
            打开项目 AI
          </Link>
          <Link className="button-secondary" to={`/project-chat?run=${record.run_id}&hypothesis=${selectedIndex}&intent=verify_hypothesis`}>
            核验证据与反例
          </Link>
          <Link className="button-secondary" to={`/project-chat?run=${record.run_id}&hypothesis=${selectedIndex}&intent=design_experiment`}>
            生成实验设计
          </Link>
          <Link className="button-secondary" to={`/project-chat?run=${record.run_id}&hypothesis=${selectedIndex}&intent=draft_report`}>
            整理报告草稿
          </Link>
        </div>
      </section>
      <section className="readable-block">
        <h4>建议追问</h4>
        <SummaryList
          items={[
            { label: "证据", value: "这条假设有哪些直接支撑、潜在反例和缺失证据？" },
            { label: "实验", value: "列出可观测变量、对照组、失败条件和最小验证路径。" },
            { label: "报告", value: "把该假设整理成报告草稿，并标明 evidence boundary。" },
          ]}
          empty=""
        />
      </section>
    </div>
  );
}

function ReportDraftPanel({
  record,
  hypothesis,
  selectedIndex,
}: {
  record: RunRecord | null;
  hypothesis: WorkspaceHypothesis | undefined;
  selectedIndex: number;
}) {
  if (!record || !hypothesis) return <div className="inline-empty">完成假设生成后，这里会整理报告草稿。</div>;
  const draft = buildHypothesisReportDraft(record, selectedIndex, hypothesis);
  return (
    <div className="report-side-panel">
      <section className="readable-block">
        <header className="detail-section-header">
          <div>
            <span className="section-kicker">本地结构化草稿</span>
            <h3>报告草稿</h3>
          </div>
          <Link className="button-secondary" to={`/project-chat?run=${record.run_id}&hypothesis=${selectedIndex}&intent=draft_report`}>
            <MessageSquareText size={16} />
            让项目 AI 继续整理
          </Link>
        </header>
        <MarkdownText text={draft} />
      </section>
    </div>
  );
}

function ProcessRecordPanel({
  record,
  error,
  isHistoricalDemo,
}: {
  record: RunRecord | null;
  error: string | null;
  isHistoricalDemo: boolean;
}) {
  return (
    <div className="process-tab-panel">
      <TimelinePanel record={record} error={error} isHistoricalDemo={isHistoricalDemo} />
      <section className="readable-block">
        <h4>Agent 过程记录</h4>
        <div className="agent-trace-list">
          {(record?.agent_trace ?? []).length === 0 ? (
            <p className="muted-note">{copy.details.agentsEmpty}</p>
          ) : (
            (record?.agent_trace ?? []).map((agent) => (
              <article className="agent-trace-card" key={`${agent.agent}-${agent.role}`}>
                <div>
                  <strong>{formatStageLabel(agent.agent)}</strong>
                  <span>{formatBackendText(agent.role)}</span>
                </div>
                <p>{formatBackendText(agent.output)}</p>
                <em>{copy.details.confidence(agent.confidence)}</em>
              </article>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function buildHypothesisReportDraft(record: RunRecord, selectedIndex: number, hypothesis: WorkspaceHypothesis) {
  const evidenceBoundary = record.request.demo_mode
    ? "Demo simulation，仅用于 UI、流程和 schema 检查，不能作为真实科学证据。"
    : record.request.literature_review
      ? "Literature-grounded workflow；仍需逐条核对 citation/source metadata、support level 和 parsed fulltext。"
      : "Live model workflow without literature review；必须标注为 limited / ungrounded proposal。";
  return [
    `## 候选假设 #${selectedIndex + 1}`,
    "",
    `**标题：** ${hypothesis.title}`,
    "",
    "### 技术假设",
    hypothesis.raw.text || hypothesis.summary,
    "",
    "### 通俗解释",
    hypothesis.raw.explanation || hypothesis.summary,
    "",
    "### 证据边界",
    evidenceBoundary,
    "",
    "### 证据诊断",
    ...hypothesis.evidenceDiagnostics.map((item) => `- **${item.label}：** ${item.value}`),
    "",
    "### 可证伪实验设计",
    hypothesis.raw.experiment || hypothesis.experimentPlan,
    "",
    "### 下一步",
    "- 优先补齐 warning/error 的证据来源。",
    "- 在实验页明确可观测变量、对照组、失败条件和最小验证路径。",
    "- 报告定稿前再次打开 Elo 排序依据，确认该假设是否真的优于其他候选。",
  ].join("\n");
}

function HypothesisFullDetail({
  hypothesis,
  selectedIndex,
  allHypotheses,
  translation,
  translationLoading,
  translationError,
  copied,
  onCopy,
  onTranslate,
}: {
  hypothesis: WorkspaceHypothesis | undefined;
  selectedIndex: number;
  allHypotheses: WorkspaceHypothesis[];
  translation?: string;
  translationLoading: boolean;
  translationError: boolean;
  copied: boolean;
  onCopy: () => void;
  onTranslate: () => void;
}) {
  if (!hypothesis) {
    return <div className="inline-empty">{copy.details.selectCompleted}</div>;
  }
  return (
    <div className="detail-copy hypothesis-full-detail">
      <header className="detail-section-header">
        <div>
          <span className="section-kicker">当前假设 #{selectedIndex + 1}</span>
          <h3>{hypothesis.title}</h3>
        </div>
        <div className="detail-header-actions">
          <button className="button-secondary" type="button" onClick={onCopy}>
            <Copy size={16} />
            {copied ? "已复制全文" : "复制全文"}
          </button>
          <button className="button-secondary" type="button" onClick={onTranslate} disabled={translationLoading} aria-busy={translationLoading}>
            <Languages size={16} />
            {translationLoading ? "正在翻译" : translation ? "刷新中文译文" : "翻译中文"}
          </button>
        </div>
      </header>

      <section className="readable-block">
        <h4>完整技术假设</h4>
        <MarkdownText text={hypothesis.raw.text || hypothesis.summary} />
      </section>

      <section className="readable-block">
        <h4>通俗解释</h4>
        <MarkdownText text={hypothesis.raw.explanation || hypothesis.summary || copy.details.noHypothesis} />
      </section>

      <section className="readable-block">
        <h4>{copy.details.experiment}</h4>
        <MarkdownText text={hypothesis.raw.experiment || hypothesis.experimentPlan || copy.details.noExperiment} />
      </section>

      <section className="readable-block">
        <h4>{copy.details.literatureGrounding}</h4>
        <MarkdownText text={hypothesis.grounding || copy.details.noGrounding} />
      </section>

      {translation ? (
        <section className="readable-block translation-panel">
          <h4>中文译文</h4>
          <MarkdownText text={translation} />
        </section>
      ) : null}
      {translationError ? <div className="control-feedback warning" role="status">暂时无法生成中文译文，请稍后重试。</div> : null}

      <details className="all-hypotheses-disclosure">
        <summary>查看全部候选假设内容</summary>
        <div className="all-hypotheses-list">
          {allHypotheses.map((item, index) => (
            <article className={classNames("all-hypothesis-card", index === selectedIndex && "selected")} key={item.id}>
              <header>
                <span>#{index + 1}</span>
                <strong>{item.title}</strong>
              </header>
              <MarkdownText text={item.raw.text || item.summary} compact />
            </article>
          ))}
        </div>
      </details>
    </div>
  );
}

function EvidenceDetailPanel({ hypothesis }: { hypothesis: WorkspaceHypothesis | undefined }) {
  if (!hypothesis) {
    return <div className="inline-empty">{copy.details.noGrounding}</div>;
  }
  return (
    <div className="detail-copy evidence-detail-panel">
      <section className="evidence-explainer-grid" aria-label="证据状态说明">
        <article>
          <strong>引用不一致</strong>
          <p>表示某条 citation、source claim 或 support level 与假设中的具体 claim 没有对上，常见来源是 mismatch/missing/invalid 标记。</p>
        </article>
        <article>
          <strong>全文不足</strong>
          <p>表示只有摘要、元数据、网页入口或弱支撑，缺少 parsed fulltext / 实验数据片段；此时只能写成 limited evidence。</p>
        </article>
      </section>

      <h3>证据诊断</h3>
      <SummaryList items={hypothesis.evidenceDiagnostics} empty="当前没有显式证据诊断。" />

      <h3>{copy.details.literatureGrounding}</h3>
      <MarkdownText text={hypothesis.grounding || copy.details.noGrounding} />

      <h4>{copy.details.citationMap}</h4>
      <SummaryList items={hypothesis.citations} empty={copy.details.noGrounding} />

      <h4>证据支撑级别</h4>
      <SummaryList items={hypothesis.citationSupportItems} empty="当前来源尚未标注全文、摘要或元数据支撑级别。" />

      <h4>知识库支撑</h4>
      <SummaryList items={hypothesis.knowledgeSupportItems} empty="当前假设尚未匹配到知识库论文片段。" />

      <h4>实验数据摘要</h4>
      <SummaryList items={hypothesis.experimentSupportItems} empty="当前假设尚未匹配到论文中的实验数据摘要。" />
    </div>
  );
}

function TournamentList({ items, empty }: { items: TournamentItemViewModel[]; empty: string }) {
  if (items.length === 0) return <div className="inline-empty">{empty}</div>;
  return (
    <div className="tournament-list" aria-label="成对排序依据">
      {items.map((item) => (
        <article className={classNames("tournament-match-card", item.tone)} key={item.id}>
          <header>
            <span>{item.label}</span>
            <strong>{item.winnerLabel} 胜出</strong>
            <em>{item.confidenceLabel}</em>
          </header>
          <dl className="tournament-match-grid">
            <div>
              <dt>参赛假设</dt>
              <dd>{item.participantsLabel}</dd>
            </div>
            <div>
              <dt>落败方</dt>
              <dd>{item.loserLabel}</dd>
            </div>
            <div>
              <dt>比较模式</dt>
              <dd>{item.comparisonModeLabel}</dd>
            </div>
            <div>
              <dt>调度依据</dt>
              <dd>{item.priorityLabel}</dd>
            </div>
            <div>
              <dt>胜者 Elo</dt>
              <dd>{item.winnerEloLabel}</dd>
            </div>
            <div>
              <dt>败者 Elo</dt>
              <dd>{item.loserEloLabel}</dd>
            </div>
          </dl>
          <p>{item.reasoning}</p>
        </article>
      ))}
    </div>
  );
}

function StatusBadgeRow({ items }: { items: ReturnType<typeof mapRunToWorkspaceView>["hypotheses"][number]["evidenceBadges"] }) {
  if (items.length === 0) return null;
  return (
    <span className="status-badge-row" aria-label="证据与治理状态">
      {items.map((item) => (
        <span className={classNames("status-pill", item.tone)} key={`${item.label}-${item.tone}`} title={explainStatusBadge(item.label)}>
          {item.label}
        </span>
      ))}
    </span>
  );
}

function explainStatusBadge(label: string) {
  if (label.includes("引用不一致")) return "某些 citation/source claim 与假设 claim 未对齐；打开证据诊断查看具体来源。";
  if (label.includes("全文不足")) return "当前证据没有达到 parsed fulltext 或实验数据支撑级别；报告中应标注 limited evidence。";
  if (label.includes("知识库")) return "已有本地知识库片段支撑，但仍建议检查片段内容和来源可靠性。";
  if (label.includes("核验")) return "运行级 citation provenance QA 已记录；打开证据面板查看详细诊断。";
  return label;
}
