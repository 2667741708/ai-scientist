import type { LucideIcon } from "lucide-react";
import { Activity, Database, LockKeyhole, RefreshCw, ShieldCheck, SlidersHorizontal, Users } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { LoadingState, StatusBanner } from "../../components/feedback/states";
import { DisclosurePanel } from "../../components/overlays/DisclosurePanel";
import { SummaryList } from "../../components/surfaces/cards";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { useAuth } from "../../features/auth/auth-context";
import { useWorkbench } from "../../features/runs/workbench-context";
import { createAuthUser, listAuthUsers, resetAuthUserPassword, updateAuthUserStatus } from "../../lib/api/auth";
import { modelGroups } from "../../lib/constants/models";
import {
  classNames,
  copy,
  getBlockedRunReason,
  getModelInfo,
  getRunRecoveryAction,
  getSafeErrorMessage,
  getSelectedProviderStatus,
  getVisibleProductRuns,
} from "../../lib/formatters/workbench";
import type { AccountRole, AccountUser } from "../../types/workbench";

const roleRows = [
  { role: "研究员", scope: "工作流、工具、资料库、产出", status: "普通账号" },
  { role: "管理员", scope: "运行准备、用户、模型协议、服务审计", status: "受限入口" },
];

const serviceRows = [
  { name: "实时模型通道", owner: "模型调用", intent: "生成、评审和排序候选假设" },
  { name: "文献支撑通道", owner: "证据来源", intent: "补齐来源证据和引用线索" },
  { name: "数据资产面", owner: "资料管理", intent: "管理论文、引用、数据集和导入任务" },
  { name: "审计记录", owner: "质量审查", intent: "保留过程、证据和质量信号" },
];

export function AdminPage() {
  const [showExpertSettings, setShowExpertSettings] = useState(false);
  const { user: currentUser } = useAuth();
  const [accountUsers, setAccountUsers] = useState<AccountUser[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountNotice, setAccountNotice] = useState("");
  const [accountEmail, setAccountEmail] = useState("");
  const [accountDisplayName, setAccountDisplayName] = useState("");
  const [accountRole, setAccountRole] = useState<AccountRole>("researcher");
  const [accountPassword, setAccountPassword] = useState("Researcher123!");
  const [resetPassword, setResetPassword] = useState("Researcher123!");
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
    history,
  } = useWorkbench();
  const visibleHistory = getVisibleProductRuns(history);
  const model = getModelInfo(modelName);
  const selectedProvider = getSelectedProviderStatus(health, modelName);
  const liveModelReady = Boolean(selectedProvider?.usable);
  const literatureReady = Boolean(health?.literature_mcp?.available);
  const adminReady = Boolean(health && liveModelReady && literatureReady);
  const activeRuns = visibleHistory.filter((run) => run.status === "queued" || run.status === "running");
  const completedRuns = visibleHistory.filter((run) => run.status === "complete");
  const blockedReason = getBlockedRunReason(health, selectedProvider);
  const nextAction = getRunRecoveryAction(health, selectedProvider);
  const referenceRangeMin = Math.min(minReferences, maxReferences);
  const referenceRangeMax = Math.max(minReferences, maxReferences);

  async function refreshAccounts() {
    setAccountsLoading(true);
    setAccountNotice("");
    try {
      const response = await listAuthUsers();
      setAccountUsers(response.users);
    } catch (error) {
      setAccountNotice(getSafeErrorMessage(error, "账号列表加载失败。"));
    } finally {
      setAccountsLoading(false);
    }
  }

  useEffect(() => {
    void refreshAccounts();
  }, []);

  async function handleCreateAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAccountsLoading(true);
    setAccountNotice("");
    try {
      const response = await createAuthUser({
        email: accountEmail,
        password: accountPassword,
        display_name: accountDisplayName,
        role: accountRole,
      });
      setAccountEmail("");
      setAccountDisplayName("");
      setAccountNotice(response.local_secret_path ? `账号已创建，并已写入本地密码备忘：${response.local_secret_path}` : "账号已创建。");
      await refreshAccounts();
    } catch (error) {
      setAccountNotice(getSafeErrorMessage(error, "账号创建失败。"));
    } finally {
      setAccountsLoading(false);
    }
  }

  async function handleToggleAccount(row: AccountUser) {
    setAccountsLoading(true);
    setAccountNotice("");
    try {
      await updateAuthUserStatus(row.id, row.status === "active" ? "disabled" : "active");
      setAccountNotice(row.status === "active" ? "账号已停用。" : "账号已启用。");
      await refreshAccounts();
    } catch (error) {
      setAccountNotice(getSafeErrorMessage(error, "账号状态更新失败。"));
    } finally {
      setAccountsLoading(false);
    }
  }

  async function handleResetPassword(row: AccountUser) {
    setAccountsLoading(true);
    setAccountNotice("");
    try {
      const response = await resetAuthUserPassword(row.id, resetPassword);
      setAccountNotice(
        response.local_secret_path
          ? `已为 ${row.email} 重置临时密码，并已写入本地密码备忘：${response.local_secret_path}`
          : `已为 ${row.email} 重置临时密码。`,
      );
      await refreshAccounts();
    } catch (error) {
      setAccountNotice(getSafeErrorMessage(error, "密码重置失败。"));
    } finally {
      setAccountsLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        kicker="运行准备"
        title="运行控制面"
        actions={
          <div className="page-header-actions">
            <button className="button-secondary" type="button" onClick={() => void refreshHealth()}>
              <RefreshCw size={16} />
              重新检查
            </button>
            <Link className="button-primary" to="/workspace">
              进入工作区
            </Link>
          </div>
        }
      />

      {healthLoading ? (
        <LoadingState title="正在检查运行准备" description="正在确认实时模型、文献支撑和工作台状态。" />
      ) : null}

      <section className="admin-metric-grid">
        <AdminMetric icon={ShieldCheck} label="运行准备" value={adminReady ? "可运行" : "已阻塞"} tone={adminReady ? "ok" : "warning"} />
        <AdminMetric icon={Activity} label="活跃任务" value={String(activeRuns.length)} tone={activeRuns.length > 0 ? "warning" : "neutral"} />
        <AdminMetric icon={Database} label="研究记录" value={String(visibleHistory.length)} tone="neutral" />
        <AdminMetric icon={Users} label="角色策略" value="2 类角色" tone="ok" />
      </section>

      <section className="admin-grid">
        <article className="surface-card admin-panel">
          <div className="section-heading">
            <h2>{adminReady ? "当前可启动研究" : "当前运行已暂停"}</h2>
          </div>
          <StatusBanner tone={adminReady ? "ok" : "warning"}>
            {adminReady ? "实时模型和文献支撑均已满足，可以返回工作区启动研究。" : blockedReason || "工作台正在等待运行准备完成。"}
          </StatusBanner>
          <SummaryList
            items={[
              { label: "实时模型", value: liveModelReady ? "可用于研究" : "需要处理", tone: liveModelReady ? "ok" : "warning" },
              { label: "文献支撑", value: literatureReady ? "可附加来源证据" : "不可用，研究启动已阻塞", tone: literatureReady ? "ok" : "warning" },
              { label: "建议下一步", value: nextAction, tone: adminReady ? "ok" : "warning" },
            ]}
            empty="检查完成后显示运行准备状态。"
          />
        </article>

        <article className="surface-card admin-panel">
          <div className="section-heading">
            <h2>用户与角色</h2>
          </div>
          <div className="admin-table compact">
            {roleRows.map((row) => (
              <div className="admin-table-row" key={row.role}>
                <strong>{row.role}</strong>
                <span>{row.scope}</span>
                <span className="status-pill ok">{row.status}</span>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="admin-grid">
        <article className="surface-card admin-panel">
          <div className="section-heading">
            <h2>研究能力状态</h2>
          </div>
          <div className="admin-table">
            {serviceRows.map((row) => (
              <div className="admin-table-row" key={row.name}>
                <strong>{row.name}</strong>
                <span>{row.owner}</span>
                <span>{row.intent}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="surface-card admin-panel">
          <div className="section-heading">
            <h2>任务队列</h2>
          </div>
          <div className="admin-table">
            {(activeRuns.length > 0 ? activeRuns : completedRuns.slice(0, 3)).map((run) => (
              <div className="admin-table-row" key={run.run_id}>
                <strong>{run.request.research_goal}</strong>
                <span>{run.status === "complete" ? "已完成" : "运行中"}</span>
                <Link to={`/workspace/${run.run_id}`}>查看</Link>
              </div>
            ))}
            {visibleHistory.length === 0 ? <div className="inline-empty">还没有研究任务。</div> : null}
          </div>
        </article>
      </section>

      <section className="surface-card admin-panel account-management-panel">
        <div className="section-heading">
          <h2>账号管理</h2>
          <p className="control-hint">
            当前管理员：{currentUser?.display_name || currentUser?.email}。普通研究员只能访问研究工作流；管理员可以创建账号、停用账号和重置临时密码。
            数据库只保存加密哈希；管理员创建或重置时设置的密码会写入本地密码备忘，但不能查看用户自行设置过的原密码。
          </p>
        </div>

        <div className="account-safety-note" role="note">
          忘记密码处理：优先让研究员用登录页的密保问题自助重置；未设置密保时，由管理员在这里设置新的临时密码并通知本人。
        </div>

        <form className="account-admin-form" onSubmit={handleCreateAccount}>
          <label className="field-stack" htmlFor="account-email">
            <span>账号邮箱</span>
            <input
              id="account-email"
              type="email"
              value={accountEmail}
              placeholder="researcher@example.com"
              required
              onChange={(event) => setAccountEmail(event.target.value)}
            />
          </label>
          <label className="field-stack" htmlFor="account-display-name">
            <span>显示名称</span>
            <input
              id="account-display-name"
              type="text"
              value={accountDisplayName}
              placeholder="课题组成员姓名"
              onChange={(event) => setAccountDisplayName(event.target.value)}
            />
          </label>
          <label className="field-stack" htmlFor="account-role">
            <span>角色</span>
            <select id="account-role" value={accountRole} onChange={(event) => setAccountRole(event.target.value as AccountRole)}>
              <option value="researcher">研究员</option>
              <option value="admin">管理员</option>
            </select>
          </label>
          <label className="field-stack" htmlFor="account-password">
            <span>初始密码</span>
            <input
              id="account-password"
              type="password"
              minLength={8}
              value={accountPassword}
              onChange={(event) => setAccountPassword(event.target.value)}
            />
          </label>
          <button className="button-primary" type="submit" disabled={accountsLoading} aria-busy={accountsLoading}>
            创建账号
          </button>
        </form>

        <div className="account-reset-row">
          <label className="field-stack" htmlFor="reset-password">
            <span>密码重置使用的临时密码</span>
            <input
              id="reset-password"
              type="password"
              minLength={8}
              value={resetPassword}
              onChange={(event) => setResetPassword(event.target.value)}
            />
          </label>
          <button className="button-secondary" type="button" onClick={() => void refreshAccounts()} disabled={accountsLoading}>
            <RefreshCw size={16} />
            刷新账号
          </button>
        </div>

        {accountNotice ? (
          <StatusBanner tone={accountNotice.includes("失败") || accountNotice.includes("不正确") ? "error" : "ok"}>{accountNotice}</StatusBanner>
        ) : null}

        <div className="account-table" aria-busy={accountsLoading}>
          {accountUsers.map((row) => (
            <article className="account-table-row" key={row.id}>
              <div>
                <strong>{row.display_name || row.email}</strong>
                <span>{row.email}</span>
              </div>
              <span className={classNames("status-pill", row.role === "admin" ? "warning" : "neutral")}>
                {row.role === "admin" ? "管理员" : "研究员"}
              </span>
              <span className={classNames("status-pill", row.status === "active" ? "ok" : "warning")}>
                {row.status === "active" ? "启用" : "停用"}
              </span>
              <span className={classNames("status-pill", row.recovery_configured ? "ok" : "neutral")}>
                {row.recovery_configured ? "已设密保" : "无密保"}
              </span>
              <span>{formatAccountTime(row.last_login_at)}</span>
              <div className="account-row-actions">
                <button className="button-secondary" type="button" disabled={accountsLoading} onClick={() => void handleToggleAccount(row)}>
                  {row.status === "active" ? "停用" : "启用"}
                </button>
                <button className="button-ghost" type="button" disabled={accountsLoading} onClick={() => void handleResetPassword(row)}>
                  重置密码
                </button>
              </div>
            </article>
          ))}
          {accountUsers.length === 0 ? <div className="inline-empty">还没有账号记录。</div> : null}
        </div>
      </section>

      <DisclosurePanel
        open={showExpertSettings}
        onToggle={() => setShowExpertSettings((value) => !value)}
        label="专家设置"
        meta={`${model.label} · ${thinkingMode ? "推理模式" : "标准模式"} · ${referenceRangeMin}-${referenceRangeMax} 条参考文献`}
      >
        <section className="surface-card overview-panel">
          <div className="expert-body">
            <label className="field-label" htmlFor="admin-model-name">
              基座模型协议
            </label>
            <select
              id="admin-model-name"
              value={modelName}
              onChange={(event) => setModelName(event.target.value)}
            >
              {modelGroups.map((group) => (
                <optgroup label={group.provider} key={group.provider}>
                  {group.models.map((modelOption) => (
                    <option value={modelOption.value} key={modelOption.value}>
                      {modelOption.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <p className="control-hint">
              普通用户不会看到底层密钥；这里只保留运行策略、基座模型协议和参考文献范围。MiMo 走独立 OpenAI-compatible endpoint。
            </p>

            <div className="toggle-row">
              <div>
                <strong>推理模式</strong>
                <span>用于跨领域理论迁移、反证分析和实验设计；开启后使用推理模型，关闭后回到默认实时模型。</span>
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

            <SliderField label="初始假设数量" value={initialHypotheses} min={1} max={8} onChange={setInitialHypotheses} />
            <SliderField label="演化迭代次数" value={iterations} min={0} max={3} onChange={setIterations} />
            <SliderField label="每条假设最小参考文献数" value={minReferences} min={0} max={12} onChange={setMinReferences} />
            <SliderField label="每条假设最大参考文献数" value={maxReferences} min={0} max={12} onChange={setMaxReferences} />
            <p className="control-hint">
              最小值和最大值是独立设计参数。当前执行范围为 {referenceRangeMin}-{referenceRangeMax} 条，模型会在范围内自适应检索和筛选来源。
            </p>
          </div>
        </section>
      </DisclosurePanel>
    </div>
  );
}

function AdminMetric({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  tone: "ok" | "warning" | "neutral";
}) {
  return (
    <article className={classNames("admin-metric", tone)}>
      <Icon size={18} />
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function formatAccountTime(value?: number | null) {
  if (!value) return "尚未登录";
  return new Date(value * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
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
