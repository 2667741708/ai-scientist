import { BrainCircuit, CheckCircle2, Loader2, Play, RefreshCw, Target } from "lucide-react";
import { useState } from "react";
import { modelGroups } from "../../lib/constants/models";
import { classNames, copy, formatRunState, getBlockedRunReason, getModelInfo, getPhaseLabel, getSelectedProviderStatus } from "../../lib/formatters/workbench";
import type { Health, RunRecord } from "../../types/workbench";

type RunComposerProps = {
  goal: string;
  setGoal: (value: string) => void;
  modelName: string;
  setModelName: (value: string) => void;
  thinkingMode: boolean;
  setThinkingMode: (enabled: boolean) => void;
  literatureReview: boolean;
  initialHypotheses: number;
  setInitialHypotheses: (value: number) => void;
  iterations: number;
  setIterations: (value: number) => void;
  minReferences: number;
  setMinReferences: (value: number) => void;
  maxReferences: number;
  setMaxReferences: (value: number) => void;
  isBusy: boolean;
  health: Health | null;
  runBlocked: boolean;
  record: RunRecord | null;
  runHistory: RunRecord[];
  onOpenRun: (record: RunRecord) => void;
  onRun: () => void;
  onClearRun: () => void;
  onRefresh: () => void;
  onStartLiteratureService: () => void;
  literatureServiceStarting: boolean;
  readOnlyHistoricalDemo?: boolean;
};

export function RunComposer(props: RunComposerProps) {
  const [showExpertSettings, setShowExpertSettings] = useState(false);
  const model = getModelInfo(props.modelName);
  const selectedProvider = getSelectedProviderStatus(props.health, props.modelName);
  const runState = formatRunState(props.record?.status);
  const hypothesisCount = props.record?.hypotheses.length ?? 0;
  const phaseLabel = getPhaseLabel(props.record);
  const goalReady = props.goal.trim().length >= 8;
  const goalTouched = props.goal.trim().length > 0;
  const goalValidationFailed = goalTouched && !goalReady;
  const literatureAvailable = Boolean(props.health?.literature_mcp?.available);
  const readinessMessage = !goalReady
    ? "请先输入具体研究目标，再启动候选假设生成。"
    : getBlockedRunReason(props.health, selectedProvider ?? undefined) || "当前工作台已可启动这次研究流程。";
  const visibleRunState = !goalReady && !props.record ? "待输入研究目标" : runState;

  const runButtonMeta = props.isBusy
    ? phaseLabel
    : !props.health
      ? "准备就绪后即可生成候选假设"
      : props.runBlocked
        ? readinessMessage
        : props.record?.status === "complete"
          ? `${hypothesisCount} 个候选假设已生成，先在右侧比较并审查证据`
          : `将生成 ${props.initialHypotheses} 个候选假设，并给出评审与排序`;
  const runSucceeded = props.record?.status === "complete";
  const runFailed = props.record?.status === "error";
  const readOnlyHistoricalDemo = Boolean(props.readOnlyHistoricalDemo);
  const referenceRangeMin = Math.min(props.minReferences, props.maxReferences);
  const referenceRangeMax = Math.max(props.minReferences, props.maxReferences);

  return (
    <section className="run-panel project-panel">
      <div className="panel-heading">
        <div className="section-title">
          <Target size={18} />
          <h2>{copy.workspace.taskTitle}</h2>
        </div>
        <p>{copy.workspace.taskDescription}</p>
      </div>

      <label className="field-label" htmlFor="research-goal">
        研究目标
      </label>
      <textarea
        id="research-goal"
        value={props.goal}
        onChange={(event) => props.setGoal(event.target.value)}
        placeholder="输入当前研究目标，例如：为 VLA 模型设计可证伪的多模态任务泛化假设。"
        readOnly={props.isBusy || readOnlyHistoricalDemo}
        aria-readonly={props.isBusy || readOnlyHistoricalDemo}
        aria-invalid={runFailed || goalValidationFailed}
        data-status={runFailed ? "error" : runSucceeded ? "success" : goalValidationFailed || props.runBlocked ? "warning" : undefined}
        rows={5}
      />
      <p className="control-hint">
        {visibleRunState} · {readOnlyHistoricalDemo ? "当前只读展示历史合成记录。" : runSucceeded ? "下一步是比较候选假设，打开参考文献，再进入实验设计。" : goalReady ? "下一步是生成候选假设并选择最值得验证的方向" : "先输入当前研究目标"}
      </p>

      {readOnlyHistoricalDemo ? (
        <div className="control-feedback warning" role="status">
          这是历史合成记录，只保留回看能力；新的研究运行必须使用实时模型和文献支撑。
        </div>
      ) : null}
      {props.runBlocked && (props.health || !goalReady) ? (
        <div className="control-feedback warning" role="status">
          <span>{readinessMessage}</span>
          {goalReady && !literatureAvailable ? (
            <div className="inline-action-row">
              <button
                className="button-secondary"
                type="button"
                onClick={props.onStartLiteratureService}
                disabled={props.literatureServiceStarting || props.isBusy}
                aria-busy={props.literatureServiceStarting}
              >
                {props.literatureServiceStarting ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                {props.literatureServiceStarting ? "正在启动文献服务" : "启动文献服务"}
              </button>
              <button className="button-ghost" type="button" onClick={props.onRefresh} disabled={props.literatureServiceStarting}>
                重新检查
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
      {runSucceeded ? (
        <div className="control-feedback success" role="status">
          已生成候选假设。先在右侧选择一条候选，打开参考文献检查证据，再进入实验设计。
        </div>
      ) : null}
      {runFailed ? <div className="control-feedback error" role="alert">这次生成没有完成，请调整任务后重试。</div> : null}

      {!readOnlyHistoricalDemo ? (
        <button
          className={classNames(
            "run-button",
            props.isBusy && "is-loading",
            runSucceeded && "is-success",
            props.runBlocked && "is-warning",
          )}
          type="button"
          disabled={props.isBusy || props.runBlocked}
          onClick={props.onRun}
          aria-busy={props.isBusy}
        >
          {props.isBusy ? <Loader2 className="spin" size={18} /> : runSucceeded ? <CheckCircle2 size={18} /> : <Play size={18} />}
          <span className="run-button-copy">
            <strong>
              {props.isBusy
                ? copy.workspace.runButtonBusy
                : props.record
                  ? copy.workspace.runButtonRepeat
                  : copy.workspace.runButtonIdle}
            </strong>
            <span>{runButtonMeta}</span>
          </span>
        </button>
      ) : null}

      {!readOnlyHistoricalDemo && props.runHistory.length > 0 ? (
        <div className="starter-section">
          <h3>继续最近研究</h3>
          <div className="starter-list">
            {props.runHistory.slice(0, 3).map((item) => (
              <button
                className="starter-item"
                type="button"
                key={item.run_id}
                onClick={() => props.onOpenRun(item)}
                disabled={props.isBusy}
              >
                <strong>{item.request.research_goal}</strong>
                <span>{item.hypotheses.length} 个候选假设</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="expert-settings">
        <button
          className="expert-summary"
          type="button"
          onClick={() => setShowExpertSettings((value) => !value)}
          aria-expanded={showExpertSettings}
        >
          {copy.settings.expertSettings}
        </button>
        {showExpertSettings ? (
          <div className="expert-body">
            <div className="settings-subsection">
              <BrainCircuit size={16} />
              <div>
                <strong>模型与推理</strong>
                <span>{model.label} · {props.thinkingMode ? "推理模式已开启" : "标准模式"}</span>
              </div>
            </div>
            <label className="field-label" htmlFor="model-name">
              模型
            </label>
            <select
              id="model-name"
              value={props.modelName}
              onChange={(event) => props.setModelName(event.target.value)}
              disabled={props.isBusy}
            >
              {modelGroups.map((group) => (
                <optgroup label={group.provider} key={group.provider}>
                  {group.models.map((modelOption) => (
                    <option value={modelOption.value} key={modelOption.value}>
                      {modelOption.label} ({modelOption.value})
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <p className="control-hint">
              {model.label} · {copy.workflow.liveMode}
            </p>

            <div className="toggle-row">
              <div>
                <strong>推理模式</strong>
                <span>用于跨领域迁移、机制推断和反证分析。当前实现会切换到 DeepSeek Reasoner；关闭后回到 DeepSeek V4 Pro 做更快的常规生成。</span>
              </div>
              <button
                className={classNames("switch", props.thinkingMode && "enabled", props.thinkingMode && "is-checked")}
                type="button"
                role="switch"
                aria-checked={props.thinkingMode}
                onClick={() => props.setThinkingMode(!props.thinkingMode)}
                disabled={props.isBusy}
              >
                <span />
              </button>
            </div>

            <div className="toggle-row">
              <div>
                <strong>文献支撑</strong>
                <span>{literatureAvailable ? "文献支撑服务已可达，本次研究会尝试检索并保留来源证据。" : "文献支撑服务未运行。点击上方“启动文献服务”后再生成，避免把模型常识当作论文证据。"}</span>
              </div>
              <button
                className={classNames("switch", props.literatureReview && "enabled", props.literatureReview && "is-checked")}
                type="button"
                role="switch"
                aria-checked={props.literatureReview}
                disabled
              >
                <span />
              </button>
            </div>

            <SliderField
              label="初始假设数量"
              value={props.initialHypotheses}
              min={1}
              max={8}
              onChange={props.setInitialHypotheses}
              disabled={props.isBusy}
            />
            <SliderField
              label="演化迭代次数"
              value={props.iterations}
              min={0}
              max={3}
              onChange={props.setIterations}
              disabled={props.isBusy}
            />
            <SliderField
              label="每条假设最小参考文献数"
              value={props.minReferences}
              min={0}
              max={12}
              onChange={props.setMinReferences}
              disabled={props.isBusy}
            />
            <SliderField
              label="每条假设最大参考文献数"
              value={props.maxReferences}
              min={0}
              max={12}
              onChange={props.setMaxReferences}
              disabled={props.isBusy}
            />
            <p className="control-hint">
              这两个值是独立设计参数。当前执行范围为 {referenceRangeMin}-{referenceRangeMax} 条，模型会在该范围内自适应检索和筛选来源。
            </p>

            <div className="expert-actions">
              <button type="button" onClick={props.onRefresh}>
                <RefreshCw size={16} />
                {copy.settings.refresh}
              </button>
              {!readOnlyHistoricalDemo ? <button type="button" onClick={props.onClearRun}>{copy.settings.clearRun}</button> : null}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function SliderField({
  label,
  value,
  min,
  max,
  onChange,
  disabled,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  disabled?: boolean;
}) {
  return (
    <label className="slider-row">
      <span>
        {label}
        <strong>{value}</strong>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        disabled={disabled}
      />
    </label>
  );
}
