import {
  BarChart3,
  BookOpenText,
  Database,
  FileText,
  FlaskConical,
  Folder,
  Lightbulb,
  MessageSquareText,
  PanelRightClose,
  PanelRightOpen,
  Search,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { HypothesisSidePanelContent } from "../../features/hypotheses/HypothesisWorkspace";
import { useProjectRouteRun } from "../../features/runs/useProjectRouteRun";
import { useWorkbench } from "../../features/runs/workbench-context";
import { classNames } from "../../lib/formatters/workbench";
import type { ProjectViewModel } from "../../types/workbench";

type SidePanelProps = {
  open: boolean;
  onClose: () => void;
  onToggle: () => void;
};

type PanelLink = {
  to: string;
  label: string;
  detail: string;
  icon: typeof Folder;
};

function isProjectRoute(project: ProjectViewModel, pathname: string, runId: string | null) {
  return (
    runId === project.id ||
    pathname === project.route ||
    pathname.startsWith(`${project.route}/`) ||
    pathname === project.workspaceRoute ||
    pathname.startsWith(`${project.workspaceRoute}/`)
  );
}

function routeLabel(pathname: string) {
  if (pathname.startsWith("/projects")) return "项目工作区";
  if (pathname.startsWith("/data") || pathname.startsWith("/library")) return "资料库";
  if (pathname.startsWith("/project-chat")) return "项目 AI";
  if (pathname.startsWith("/workflows") || pathname.startsWith("/workspace")) return "任务队列";
  if (pathname.startsWith("/tools")) return "研究工具";
  if (pathname.startsWith("/outputs")) return "研究产出";
  if (pathname.startsWith("/admin")) return "运行准备";
  return "研究主页";
}

function useActiveLibraryLabel() {
  const [libraryId, setLibraryId] = useState(() => window.localStorage.getItem("coscientist.activeLibraryId") || "默认文献库");

  useEffect(() => {
    const refresh = () => setLibraryId(window.localStorage.getItem("coscientist.activeLibraryId") || "默认文献库");
    window.addEventListener("storage", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener("storage", refresh);
      window.removeEventListener("focus", refresh);
    };
  }, []);

  return libraryId;
}

export function AppSidePanel({ open, onClose, onToggle }: SidePanelProps) {
  const location = useLocation();
  const { currentRun, currentRunId, projects, isBusy, error } = useWorkbench();
  const searchRunId = new URLSearchParams(location.search).get("run");
  const hypothesisRouteMatch = location.pathname.match(/^\/projects\/([^/]+)\/hypotheses$/);
  const hypothesisRouteRun = useProjectRouteRun(hypothesisRouteMatch?.[1]);
  const isHypothesisRoute = Boolean(hypothesisRouteMatch);
  const hypothesisPanelRecord = isHypothesisRoute ? hypothesisRouteRun : null;
  const activeLibraryLabel = useActiveLibraryLabel();
  const activeProject = useMemo(
    () => projects.find((project) => isProjectRoute(project, location.pathname, searchRunId)),
    [location.pathname, projects, searchRunId],
  );
  const project = activeProject ?? projects.find((item) => item.id === currentRunId) ?? projects[0] ?? null;
  const panelLinks = useMemo<PanelLink[]>(() => {
    if (!project) {
      return [
        { to: "/home", label: "创建项目", detail: "从研究主题开始", icon: Folder },
        { to: "/data", label: "补充论文", detail: "入库 PDF/fulltext", icon: BookOpenText },
        { to: "/project-chat", label: "询问项目 AI", detail: "基于知识库问答", icon: MessageSquareText },
      ];
    }
    return [
      { to: project.papersRoute, label: "论文", detail: `${project.evidenceCount} 条证据入口`, icon: BookOpenText },
      { to: project.hypothesesRoute, label: "假设", detail: `${project.hypothesisCount} 条候选假设`, icon: Lightbulb },
      { to: project.experimentsRoute, label: "实验", detail: "验证设计与运行", icon: FlaskConical },
      { to: project.reportsRoute, label: "报告", detail: "草稿与产出", icon: FileText },
      { to: `/project-chat?run=${project.id}`, label: "项目 AI", detail: "围绕当前项目追问", icon: MessageSquareText },
    ];
  }, [project]);

  return (
    <>
      <div className="side-panel-controls" role="toolbar" aria-label="工作区面板">
        <button
          className={classNames("side-panel-icon-button", open && "active")}
          type="button"
          onClick={onToggle}
          aria-label={open ? "隐藏右侧栏" : "显示右侧栏"}
          aria-expanded={open}
          data-tooltip="显示/隐藏右侧栏 Ctrl+Alt+B"
        >
          {open ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
        </button>
      </div>

      {open ? (
        <aside className="app-side-panel" aria-label="右侧工作面板">
          <header className="app-side-panel-header">
            <div>
              <span>工作区</span>
              <strong>{isHypothesisRoute ? "假设工具" : routeLabel(location.pathname)}</strong>
            </div>
            <button className="side-panel-icon-button" type="button" onClick={onClose} aria-label="收起右侧栏">
              <X size={18} />
            </button>
          </header>

          {isHypothesisRoute ? (
            <HypothesisSidePanelContent
              record={hypothesisPanelRecord}
              error={error}
              isHistoricalDemo={Boolean(hypothesisPanelRecord?.request.demo_mode)}
            />
          ) : (
            <>
          <section className="side-panel-section" aria-labelledby="side-panel-context-heading">
            <div className="side-panel-section-heading">
              <h2 id="side-panel-context-heading">当前上下文</h2>
            </div>
            <div className="side-panel-context">
              <Folder size={16} />
              <div>
                <strong>{project?.title ?? "暂无项目"}</strong>
                <span>{project?.researchGoal ?? "先创建或运行一个研究项目。"}</span>
              </div>
            </div>
            <dl className="side-panel-metrics">
              <div>
                <dt>运行</dt>
                <dd>{currentRun?.status ?? project?.status ?? "idle"}</dd>
              </div>
              <div>
                <dt>假设</dt>
                <dd>{currentRun?.hypotheses.length ?? project?.hypothesisCount ?? 0}</dd>
              </div>
              <div>
                <dt>状态</dt>
                <dd>{isBusy ? "运行中" : "可检查"}</dd>
              </div>
            </dl>
          </section>

          <section className="side-panel-section" aria-labelledby="side-panel-output-heading">
            <div className="side-panel-section-heading">
              <h2 id="side-panel-output-heading">输出</h2>
              {project ? <Link to={project.route}>打开项目</Link> : null}
            </div>
            <div className="side-panel-link-list">
              {panelLinks.map((item) => {
                const Icon = item.icon;
                return (
                  <Link className="side-panel-link" to={item.to} key={item.label}>
                    <Icon size={16} />
                    <span>
                      <strong>{item.label}</strong>
                      <small>{item.detail}</small>
                    </span>
                  </Link>
                );
              })}
            </div>
          </section>

          <section className="side-panel-section" aria-labelledby="side-panel-source-heading">
            <div className="side-panel-section-heading">
              <h2 id="side-panel-source-heading">来源</h2>
              <Link to="/data">管理</Link>
            </div>
            <div className="side-panel-source-row">
              <Database size={16} />
              <div>
                <strong>{activeLibraryLabel}</strong>
                <span>SQL 知识库、PDF 解析片段和网页证据会优先进入这里。</span>
              </div>
            </div>
          </section>

          <section className="side-panel-section" aria-labelledby="side-panel-shortcut-heading">
            <div className="side-panel-section-heading">
              <h2 id="side-panel-shortcut-heading">快捷入口</h2>
            </div>
            <div className="side-panel-quick-actions">
              <Link to="/project-chat">
                <Search size={15} />
                搜索与问答
              </Link>
              <Link to="/outputs">
                <BarChart3 size={15} />
                查看产出
              </Link>
            </div>
          </section>
            </>
          )}
        </aside>
      ) : null}
    </>
  );
}
