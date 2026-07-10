import { ArrowRight, BookOpenCheck, ClipboardList, FileText, FlaskConical, GitBranch, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState } from "../../components/feedback/states";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { useWorkbench } from "../../features/runs/workbench-context";
import { classNames, copy } from "../../lib/formatters/workbench";

const workflows = [
  {
    title: "文献综述",
    requiredInput: "论文、PDF、网页证据或已入库知识片段",
    blocker: "缺少可核验来源时会降级为 latent-knowledge based",
    lastResult: "证据来源、citation map 和 fulltext chunk",
    primaryAction: "整理证据",
    icon: BookOpenCheck,
    route: "/data",
    status: "需要数据",
    tone: "warning",
  },
  {
    title: "候选假设生成",
    requiredInput: "明确 research goal、机制、变量、验证约束",
    blocker: "目标过泛会降低可证伪性和排序质量",
    lastResult: "候选假设、plain explanation 和 validation plan",
    primaryAction: "启动生成",
    icon: Sparkles,
    route: "/workspace",
    status: "核心路径",
    tone: "ok",
  },
  {
    title: "假设比较",
    requiredInput: "至少两条候选假设和 review/ranking 结果",
    blocker: "缺少 tournament matchups 时只能做弱排序",
    lastResult: "winner/loser、Elo delta、review feedback",
    primaryAction: "比较候选",
    icon: GitBranch,
    route: "/workspace",
    status: "完成后进入",
    tone: "neutral",
  },
  {
    title: "实验设计",
    requiredInput: "选中的假设、替代解释、关键指标",
    blocker: "没有失败条件时不应进入执行",
    lastResult: "最小可行验证、对照、失败解释",
    primaryAction: "设计实验",
    icon: FlaskConical,
    route: "/workspace",
    status: "后续步骤",
    tone: "neutral",
  },
  {
    title: "报告草稿",
    requiredInput: "入选发现、实验计划、局限性和证据覆盖",
    blocker: "缺少证据链接时只能导出 limited 草稿",
    lastResult: "可审查报告区和导出入口",
    primaryAction: "装配报告",
    icon: FileText,
    route: "/outputs",
    status: "可回看",
    tone: "neutral",
  },
  {
    title: "审计检查",
    requiredInput: "timeline、agent trace、metrics 和 provenance",
    blocker: "未完成运行时只能查看 phase-level trace",
    lastResult: "过程记录、证据边界和质量信号",
    primaryAction: "检查过程",
    icon: ClipboardList,
    route: "/workspace",
    status: "按需展开",
    tone: "neutral",
  },
];

export function WorkflowsPage() {
  const { projects } = useWorkbench();
  const recentProjects = projects.slice(0, 3);
  const currentProject = recentProjects[0];

  return (
    <div className="page-stack">
      <PageHeader
        kicker={copy.productKicker}
        title="研究任务队列"
        actions={
          <Link className="button-primary" to="/workspace">
            新建研究
            <ArrowRight size={16} />
          </Link>
        }
      />

      <section className="workflow-queue-shell" aria-label="当前研究任务队列">
        <div className="workflow-queue-summary">
          <div>
            <span className="section-kicker">当前项目</span>
            <h2>{currentProject?.title ?? "等待研究目标"}</h2>
            <p>
              {currentProject?.researchGoal ??
                "先创建一个 research goal；队列会按证据准备、假设生成、评审排序、实验设计和报告装配推进。"}
            </p>
          </div>
          <div className="workflow-queue-metrics" aria-label="队列摘要">
            <span>
              <strong>{currentProject?.hypothesisCount ?? 0}</strong>
              候选假设
            </span>
            <span>
              <strong>{currentProject?.evidenceCount ?? 0}</strong>
              证据来源
            </span>
            <span>
              <strong>{currentProject?.outputCount ?? 0}</strong>
              可回看产出
            </span>
          </div>
        </div>

        <ol className="workflow-queue-list">
          {workflows.map((workflow, index) => {
          const Icon = workflow.icon;
          return (
            <li className="workflow-queue-row" key={workflow.title}>
              <div className="workflow-step-index">{index + 1}</div>
              <div className="workflow-queue-main">
                <div className="workflow-queue-title">
                  <Icon size={18} />
                  <h2>{workflow.title}</h2>
                  <span className={classNames("status-pill", workflow.tone)}>{workflow.status}</span>
                </div>
                <dl className="workflow-queue-fields">
                  <div>
                    <dt>需要输入</dt>
                    <dd>{workflow.requiredInput}</dd>
                  </div>
                  <div>
                    <dt>阻塞项</dt>
                    <dd>{workflow.blocker}</dd>
                  </div>
                  <div>
                    <dt>最近结果</dt>
                    <dd>{workflow.lastResult}</dd>
                  </div>
                </dl>
              </div>
              <Link className="button-secondary" to={workflow.route}>
                {workflow.primaryAction}
                <ArrowRight size={14} />
              </Link>
            </li>
          );
        })}
        </ol>
      </section>

      <section className="section-stack">
        <div className="section-heading">
          <h2>继续推进</h2>
        </div>
        {recentProjects.length > 0 ? (
          <div className="project-table" role="list" aria-label="最近研究项目">
            {recentProjects.map((project) => (
              <article className="project-table-row" key={project.id} role="listitem">
                <div>
                  <span>{project.stageLabel}</span>
                  <strong>{project.title}</strong>
                  <p>{project.nextStep}</p>
                </div>
                <div className="project-table-stats">
                  <span>{project.hypothesisCount} 假设</span>
                  <span>{project.evidenceCount} 证据</span>
                  <span>{project.lastActivity}</span>
                </div>
                <Link className="button-secondary" to={project.workspaceRoute}>
                  进入工作区
                  <ArrowRight size={14} />
                </Link>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="还没有可继续的研究"
            description="先创建一个研究目标，系统会把候选假设、文献证据和后续实验串成可推进的研究路径。"
            actions={
              <Link className="button-primary" to="/workspace">
                创建研究
              </Link>
            }
          />
        )}
      </section>
    </div>
  );
}
