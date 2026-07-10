import { Info, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { DisclosurePanel } from "../../components/overlays/DisclosurePanel";
import { LoadingState, StatusBanner } from "../../components/feedback/states";
import { SummaryList } from "../../components/surfaces/cards";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { modelGroups } from "../../lib/constants/models";
import {
  copy,
  classNames,
  formatModeValue,
  getBlockedRunReason,
  getModelInfo,
  getRunReadinessLabel,
  getRunRecoveryAction,
  getSelectedProviderStatus,
} from "../../lib/formatters/workbench";
import { useWorkbench } from "../../features/runs/workbench-context";

export function SettingsPage() {
  const [showExpertSettings, setShowExpertSettings] = useState(false);
  const {
    health,
    healthLoading,
    modelName,
    setModelName,
    thinkingMode,
    setThinkingMode,
    initialHypotheses,
    setInitialHypotheses,
    iterations,
    setIterations,
    minReferences,
    setMinReferences,
    maxReferences,
    setMaxReferences,
    refreshHealth,
    runBlocked,
  } = useWorkbench();
  const model = getModelInfo(modelName);
  const selectedProvider = getSelectedProviderStatus(health, modelName);
  const literatureReady = Boolean(health?.literature_mcp?.available);
  const readinessLabel = getRunReadinessLabel(health, selectedProvider);
  const blockedReason = getBlockedRunReason(health, selectedProvider);
  const nextAction = getRunRecoveryAction(health, selectedProvider);
  const providerMode = selectedProvider ? formatModeValue(selectedProvider.mode) : "待检查";
  const referenceRangeMin = Math.min(minReferences, maxReferences);
  const referenceRangeMax = Math.max(minReferences, maxReferences);

  return (
    <div className="page-stack">
      <PageHeader
        kicker="运行准备"
        title={copy.settings.title}
        actions={
          <div className="page-header-actions">
            <button className="button-secondary" type="button" onClick={() => void refreshHealth()}>
              <RefreshCw size={16} />
              {copy.settings.refresh}
            </button>
            <Link className="button-primary" to="/workspace">
              返回工作区
            </Link>
            <button className="info-trigger" type="button" aria-label={copy.settings.description} data-tooltip={copy.settings.description}>
              <Info size={16} />
            </button>
          </div>
        }
      />

      {healthLoading ? (
        <LoadingState title="正在检查运行条件" description="正在确认当前模型通道与文献服务的可用性。" />
      ) : null}

      <div className="overview-grid settings-grid">
        <section className="surface-card overview-panel">
          <div className="section-heading">
            <h2>当前运行状态</h2>
          </div>
          <SummaryList
            items={[
              { label: copy.settings.currentMode, value: copy.workflow.liveMode, tone: "ok" },
              { label: copy.settings.currentProvider, value: `${model.label} · ${providerMode}`, tone: selectedProvider?.usable ? "ok" : "warning" },
              { label: copy.settings.liveWorkflow, value: selectedProvider?.usable ? "已满足实时模型调用条件。" : "当前模型通道不可用于研究运行。", tone: selectedProvider?.usable ? "ok" : "warning" },
              { label: copy.settings.literatureWorkflow, value: literatureReady ? "文献服务可为假设附加来源证据。" : "文献服务当前不可用。", tone: literatureReady ? "ok" : "warning" },
              { label: copy.settings.runReadiness, value: readinessLabel, tone: runBlocked ? "warning" : "ok" },
            ]}
            empty="检查完成后会显示当前运行状态。"
          />
        </section>

        <section className="surface-card overview-panel">
          <div className="section-heading">
            <h2>{runBlocked ? copy.settings.blockedReason : copy.settings.nextAction}</h2>
          </div>
          <StatusBanner tone={runBlocked ? "warning" : "ok"}>
            {runBlocked ? blockedReason : "当前条件已满足，可以直接返回工作区启动新的文献支撑研究。"}
          </StatusBanner>
          <SummaryList
            items={[{ label: copy.settings.nextAction, value: nextAction, tone: runBlocked ? "warning" : "ok" }]}
            empty="这里会显示恢复或继续的下一步动作。"
          />
        </section>
      </div>

      <DisclosurePanel
        open={showExpertSettings}
        onToggle={() => setShowExpertSettings((value) => !value)}
        label={copy.settings.expertSettings}
        meta={`${model.label} · ${thinkingMode ? "推理模式" : "标准模式"} · ${referenceRangeMin}-${referenceRangeMax} 条参考文献`}
      >
        <section className="surface-card overview-panel">
          <div className="expert-body">
            <label className="field-label" htmlFor="settings-model-name">
              基座模型协议
            </label>
            <select
              id="settings-model-name"
              value={modelName}
              onChange={(event) => setModelName(event.target.value)}
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
              这里选择 LiteLLM / OpenAI-compatible 模型协议；MiMo 使用独立 MIMO_API_KEY 和 MiMo API base，不复用 OpenAI 通道。
            </p>

            <div className="toggle-row">
              <div>
                <strong>推理模式</strong>
                <span>用于跨领域理论迁移、反证分析和实验设计；当前实现会切换到 DeepSeek Reasoner，关闭后回到 DeepSeek V4 Pro。</span>
              </div>
              <button
                className={classNames("switch", thinkingMode && "enabled", thinkingMode && "is-checked")}
                type="button"
                role="switch"
                aria-checked={thinkingMode}
                onClick={() => setThinkingMode(!thinkingMode)}
              >
                <span />
              </button>
            </div>

            <SliderField
              label="初始假设数量"
              value={initialHypotheses}
              min={1}
              max={8}
              onChange={setInitialHypotheses}
            />
            <SliderField
              label="演化迭代次数"
              value={iterations}
              min={0}
              max={3}
              onChange={setIterations}
            />
            <SliderField
              label="每条假设最小参考文献数"
              value={minReferences}
              min={0}
              max={12}
              onChange={setMinReferences}
            />
            <SliderField
              label="每条假设最大参考文献数"
              value={maxReferences}
              min={0}
              max={12}
              onChange={setMaxReferences}
            />
            <p className="control-hint">
              最小值和最大值使用固定刻度；提交研究时会自动归一化为 {referenceRangeMin}-{referenceRangeMax} 条参考文献范围。
            </p>
          </div>
        </section>
      </DisclosurePanel>
    </div>
  );
}

function SliderField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
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
      />
    </label>
  );
}
