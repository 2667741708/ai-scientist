import { Maximize2, Minimize2, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { HypothesisWorkspace } from "../../features/hypotheses/HypothesisWorkspace";
import { ResearchCommandCenter } from "../../features/research-chat/ResearchCommandCenter";
import { RunComposer } from "../../features/runs/RunComposer";
import { useProjectRouteRun } from "../../features/runs/useProjectRouteRun";
import { useWorkbench } from "../../features/runs/workbench-context";
import { classNames, copy, formatRunState, getVisibleProductRuns } from "../../lib/formatters/workbench";

type ComposerScale = "rail" | "compact" | "standard" | "focus";

const composerScaleOptions: Array<{
  value: ComposerScale;
  label: string;
  description: string;
  icon: typeof PanelLeftOpen;
}> = [
  { value: "rail", label: "收起", description: "只保留候选生成启动栏，把空间让给假设审查。", icon: PanelLeftClose },
  { value: "compact", label: "紧凑", description: "默认工作台宽度，适合边生成边审查。", icon: Minimize2 },
  { value: "standard", label: "标准", description: "显示完整对话工作台和建议任务。", icon: PanelLeftOpen },
  { value: "focus", label: "专注", description: "扩大候选生成面板，用于细写 research goal。", icon: Maximize2 },
];

export function WorkspacePage() {
  const params = useParams();
  const navigate = useNavigate();
  const [composerScale, setComposerScale] = useState<ComposerScale>(() => {
    const saved = window.localStorage.getItem("coscientist.workspaceComposerScale");
    return saved === "rail" || saved === "compact" || saved === "standard" || saved === "focus" ? saved : "compact";
  });
  const {
    goal,
    setGoal,
    modelName,
    setModelName,
    thinkingMode,
    setThinkingMode,
    demoMode,
    literatureReview,
    initialHypotheses,
    setInitialHypotheses,
    iterations,
    setIterations,
    minReferences,
    setMinReferences,
    maxReferences,
    setMaxReferences,
    isBusy,
    health,
    runBlocked,
    currentRun,
    history,
    openHistoryRun,
    startRun,
    clearCurrentRun,
    refreshHealth,
    startLiteratureService,
    literatureServiceStarting,
    error,
    selectedIndex,
    setSelectedIndex,
    activeDetailTab,
    setActiveDetailTab,
  } = useWorkbench();

  const routedRun = useProjectRouteRun(params.projectId);
  const activeRun = params.projectId ? routedRun : currentRun;
  const readOnlyHistoricalDemo = Boolean(activeRun?.request.demo_mode);
  const visibleHistory = getVisibleProductRuns(history);
  useEffect(() => {
    window.localStorage.setItem("coscientist.workspaceComposerScale", composerScale);
  }, [composerScale]);

  const handleExpertRun = async () => {
    const runId = await startRun();
    if (!runId) return;
    setActiveDetailTab("agents");
    navigate(`/workspace/${encodeURIComponent(runId)}`);
  };

  return (
    <div className="page-stack">
      <PageHeader
        kicker={copy.productKicker}
        title={copy.workspace.title}
        description={copy.workspace.description}
        actions={<WorkspaceScaleControl value={composerScale} onChange={setComposerScale} />}
      />
      <section className={classNames("studio-grid", `composer-${composerScale}`)}>
        {composerScale === "rail" ? (
          <HypothesisLaunchRail
            record={activeRun}
            isBusy={isBusy}
            onExpand={() => setComposerScale("compact")}
            onOpenProcess={() => setActiveDetailTab("agents")}
          />
        ) : (
          <ResearchCommandCenter
            record={activeRun}
            selectedIndex={selectedIndex}
            modelName={modelName}
            literatureReview={literatureReview}
            demoMode={demoMode}
            initialHypotheses={initialHypotheses}
            iterations={iterations}
            minReferences={minReferences}
            maxReferences={maxReferences}
            isBusy={isBusy}
            onOpenRun={openHistoryRun}
            onSelectHypothesis={setSelectedIndex}
            onSetDetailTab={setActiveDetailTab}
            expertComposer={
              <RunComposer
                goal={goal}
                setGoal={setGoal}
                modelName={modelName}
                setModelName={setModelName}
                thinkingMode={thinkingMode}
                setThinkingMode={setThinkingMode}
                literatureReview={literatureReview}
                initialHypotheses={initialHypotheses}
                setInitialHypotheses={setInitialHypotheses}
                iterations={iterations}
                setIterations={setIterations}
                minReferences={minReferences}
                setMinReferences={setMinReferences}
                maxReferences={maxReferences}
                setMaxReferences={setMaxReferences}
                isBusy={isBusy}
                health={health}
                runBlocked={runBlocked}
                record={activeRun}
                runHistory={visibleHistory}
                onOpenRun={openHistoryRun}
                onRun={() => void handleExpertRun()}
                onClearRun={clearCurrentRun}
                onRefresh={() => void refreshHealth()}
                onStartLiteratureService={() => void startLiteratureService()}
                literatureServiceStarting={literatureServiceStarting}
                readOnlyHistoricalDemo={readOnlyHistoricalDemo}
              />
            }
          />
        )}
        <HypothesisWorkspace
          record={activeRun}
          error={error}
          isHistoricalDemo={readOnlyHistoricalDemo}
          selectedIndex={selectedIndex}
          setSelectedIndex={setSelectedIndex}
        />
      </section>
    </div>
  );
}

function WorkspaceScaleControl({
  value,
  onChange,
}: {
  value: ComposerScale;
  onChange: (value: ComposerScale) => void;
}) {
  return (
    <div className="workspace-scale-control" role="group" aria-label="候选假设生成面板大小">
      <span className="scale-control-label">候选生成</span>
      {composerScaleOptions.map((item) => {
        const Icon = item.icon;
        return (
          <button
            className={classNames(value === item.value && "selected")}
            type="button"
            key={item.value}
            onClick={() => onChange(item.value)}
            aria-pressed={value === item.value}
            aria-label={`${item.label}候选假设生成面板`}
            data-tooltip={item.description}
          >
            <Icon size={15} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function HypothesisLaunchRail({
  record,
  isBusy,
  onExpand,
  onOpenProcess,
}: {
  record: ReturnType<typeof useWorkbench>["currentRun"] | null;
  isBusy: boolean;
  onExpand: () => void;
  onOpenProcess: () => void;
}) {
  const hypothesisCount = record?.hypotheses.length ?? 0;
  return (
    <aside className="hypothesis-launch-rail" aria-label="候选假设生成已收起">
      <button className="rail-expand-button" type="button" onClick={onExpand} aria-label="展开候选假设生成面板">
        <PanelLeftOpen size={18} />
      </button>
      <div className="rail-status-copy">
        <span>候选生成</span>
        <strong>{record ? formatRunState(record.status) : isBusy ? "运行中" : "待启动"}</strong>
        <small>{hypothesisCount} 条假设</small>
      </div>
      <button className="rail-process-button" type="button" onClick={onOpenProcess} disabled={!record}>
        过程
      </button>
    </aside>
  );
}
