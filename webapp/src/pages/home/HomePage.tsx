import { ArrowRight, BookOpenCheck, Database, FileText, FlaskConical, Loader2, MessageSquareText, Search, Sparkles, Wrench } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { EmptyState } from "../../components/feedback/states";
import { ProjectCard } from "../../components/surfaces/cards";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { useAuth } from "../../features/auth/auth-context";
import { GuidedResearchBrief } from "../../features/research-brief/GuidedResearchBrief";
import { useWorkbench } from "../../features/runs/workbench-context";
import { classNames, copy, getVisibleProductRuns } from "../../lib/formatters/workbench";
import type { ProjectViewModel } from "../../types/workbench";

const workflowItems = [
  { title: "文献综述", description: "先确认研究依据和证据覆盖。", route: "/data", icon: BookOpenCheck },
  { title: "候选假设生成", description: "输入研究目标，比较候选方向。", route: "/workspace", icon: Sparkles },
  { title: "实验设计", description: "把入选假设转成可证伪实验。", route: "/workspace", icon: FlaskConical },
  { title: "报告草稿", description: "汇总发现、局限性和引用覆盖。", route: "/outputs", icon: FileText },
];

function uniqueBy<T>(items: T[], getKey: (item: T) => string) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = getKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function HomePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { projects, history, health, isBusy, selectedProviderUsable, startRun, error } = useWorkbench();
  const [projectGoal, setProjectGoal] = useState("");
  const [creatingProject, setCreatingProject] = useState(false);
  const canViewAdmin = user?.role === "admin";
  const visibleHistory = getVisibleProductRuns(history);
  const recentProjects = uniqueBy(
    projects,
    (project: ProjectViewModel) => `${project.title}:${project.researchGoal}:${project.status}`,
  ).slice(0, 3);
  const activeProject = recentProjects.find((project) => project.status === "queued" || project.status === "running") ?? recentProjects[0];
  const literatureReady = Boolean(health?.literature_mcp?.available);
  const projectGoalReady = projectGoal.trim().length >= 8;
  const projectCreationBlocked = creatingProject || isBusy || !projectGoalReady || !health || !selectedProviderUsable || !literatureReady;
  const projectCreationHint = !projectGoalReady
    ? "输入一个具体研究主题，例如机制、现象、数据集或最小验证目标。"
    : !health || !selectedProviderUsable
      ? "实时模型通道暂不可用，请先到运行准备检查模型。"
      : !literatureReady
        ? "文献支撑服务暂不可用，请先恢复文献服务。"
        : isBusy
          ? "已有研究任务正在运行，请等待完成后再创建新项目。"
          : "将创建项目并生成候选假设、评审和排序结果。";

  const handleCreateProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (projectCreationBlocked) return;
    setCreatingProject(true);
    try {
      const runId = await startRun(projectGoal);
      if (runId) {
        navigate(`/projects/${runId}/hypotheses`);
      }
    } finally {
      setCreatingProject(false);
    }
  };
  const priorityCopy = useMemo(() => {
    if (activeProject) {
      const isFailed = activeProject.status === "error";
      return {
        title: activeProject.nextStep || "继续推进当前研究",
        body: `${activeProject.title} · ${activeProject.stageLabel || "研究进行中"}。建议先检查证据准备，再进入工作区继续生成、评审或整理产出。`,
        primaryLabel: isFailed
          ? "进入工作区重试"
          : activeProject.nextStep?.includes("证据") || activeProject.nextStep?.includes("文献")
            ? "去管理资料"
            : "继续研究",
        primaryRoute: activeProject.nextStep?.includes("证据") || activeProject.nextStep?.includes("文献") ? "/data" : activeProject.workspaceRoute,
      };
    }
    return {
      title: "先定义一个研究目标",
      body: "输入明确研究目标后，系统会把资料准备、候选假设、评审排序、实验设计和报告草稿串成一条可推进的研究路径。",
      primaryLabel: "创建第一个研究",
      primaryRoute: "/workspace",
    };
  }, [activeProject]);

  return (
    <div className="page-stack home-redesign">
      <PageHeader
        kicker={copy.productKicker}
        title="研究项目"
        description="围绕一个具体主题创建项目，生成候选假设，再选择其中一条进入阅读、实验分析和项目 AI 对话。"
        actions={
          <div className="page-header-actions">
            <Link className="button-secondary" to="/project-chat">
              <MessageSquareText size={16} />
              项目问答
            </Link>
            <Link className="button-primary" to="/workspace">
              新建研究
              <ArrowRight size={16} />
            </Link>
          </div>
        }
      />

      <section className="home-dashboard-grid">
        <div className="home-main-stack">
          <GuidedResearchBrief
            disabled={creatingProject || isBusy || !health || !selectedProviderUsable || !literatureReady}
            onSubmit={async (goal) => {
              setCreatingProject(true);
              try {
                const runId = await startRun(goal);
                if (runId) navigate(`/projects/${runId}/hypotheses`);
              } finally {
                setCreatingProject(false);
              }
            }}
          />
          <section className="project-create-panel">
            <div className="section-heading">
              <h2>创建一个研究项目</h2>
              <p>项目会以研究主题为中心组织论文、候选假设、实验设计和报告草稿。</p>
            </div>
            <form className="project-create-form" onSubmit={handleCreateProject}>
              <label htmlFor="project-goal-input">研究主题或目标</label>
              <textarea
                id="project-goal-input"
                value={projectGoal}
                onChange={(event) => setProjectGoal(event.target.value)}
                rows={4}
                placeholder="例如：探索 VLA 将 token 序列转换为机器人臂动作的机制，并生成可证伪、可实验验证的候选假设"
                disabled={creatingProject || isBusy}
              />
              <div className="project-create-footer">
                <span className={classNames("project-create-hint", projectCreationBlocked && projectGoalReady && "warning")}>{projectCreationHint}</span>
                <button className="button-primary" type="submit" disabled={projectCreationBlocked} aria-busy={creatingProject}>
                  {creatingProject ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />}
                  {creatingProject ? "正在创建项目" : "创建项目并生成假设"}
                </button>
              </div>
              {error ? <div className="control-feedback warning">{error}</div> : null}
            </form>
          </section>

          <section className="task-priority-panel">
            <div className="section-heading">
              <h2>当前优先任务</h2>
              <p>系统把最近项目、证据准备和运行状态折叠成一个可执行下一步。</p>
            </div>
            <div className="priority-copy">
              <span className="status-chip warning">下一步</span>
              <h3>{priorityCopy.title}</h3>
              <p>{priorityCopy.body}</p>
            </div>
            <div className="priority-actions">
              <Link className="button-primary" to={priorityCopy.primaryRoute}>
                {priorityCopy.primaryLabel}
              </Link>
              <Link className="button-secondary" to="/data">
                检查证据
              </Link>
            </div>
          </section>

          <section className="section-stack">
            <div className="section-heading">
              <h2>继续工作</h2>
              <p>只显示和下一步相关的研究对象，不做项目卡片墙。</p>
            </div>
            {recentProjects.length > 0 ? (
              <div className="card-grid">
                {recentProjects.map((project) => (
                  <ProjectCard key={project.id} project={project} />
                ))}
              </div>
            ) : (
              <EmptyState
                title="还没有可继续的研究"
                description={copy.home.emptyProjects}
                actions={
                  <Link className="button-primary" to="/workspace">
                    创建研究
                  </Link>
                }
              />
            )}
          </section>

          <section className="workflow-lane">
            <div className="section-heading">
              <h2>研究路径</h2>
              <p>从资料准备到报告产出，每一步都对应一个可执行页面。</p>
            </div>
            <div className="workflow-lane-grid">
              {workflowItems.map((item, index) => {
                const Icon = item.icon;
                return (
                  <Link className="workflow-lane-step" to={item.route} key={item.title}>
                    <span>{index + 1}</span>
                    <Icon size={16} />
                    <strong>{item.title}</strong>
                    <small>{item.description}</small>
                  </Link>
                );
              })}
            </div>
          </section>
        </div>

        <aside className="readiness-rail" aria-label="数据准备状态">
          <div className="section-heading">
            <h2>研究准备状态</h2>
            <p>状态是行动建议，不是静态指标。</p>
          </div>
          <article className="readiness-row">
            <span>文献服务</span>
            <strong className={literatureReady ? "ok-text" : "warning-text"}>
              {literatureReady ? "可用" : "需要检查"}
            </strong>
          </article>
          <article className="readiness-row">
            <span>研究记录</span>
            <strong>{visibleHistory.length}</strong>
          </article>
          <article className="readiness-row">
            <span>最近项目</span>
            <strong>{recentProjects.length}</strong>
          </article>
          <article className="readiness-row">
            <span>项目问答</span>
            <strong>可用</strong>
          </article>
          <div className="readiness-actions">
            <Link className="button-secondary" to="/data">
              <Database size={16} />
              管理资料
            </Link>
            <Link className="button-secondary" to="/project-chat">
              <Search size={16} />
              问项目
            </Link>
            {canViewAdmin ? (
              <Link className="button-secondary" to="/admin">
                <Wrench size={16} />
                运行准备
              </Link>
            ) : (
              <span className="muted-note" role="status">
                运行准备由管理员维护；可先补充本地论文证据。
              </span>
            )}
          </div>
        </aside>
      </section>
    </div>
  );
}
