import {
  BarChart3,
  BookOpenText,
  Brain,
  ChevronDown,
  ChevronRight,
  Database,
  FlaskConical,
  Folder,
  Lightbulb,
  MessageSquareText,
  Plus,
  Search,
  Settings2,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../../features/auth/auth-context";
import { useWorkbench } from "../../features/runs/workbench-context";
import { classNames } from "../../lib/formatters/workbench";
import type { ProjectViewModel } from "../../types/workbench";

const topActions = [
  { to: "/home", label: "新建项目", icon: Plus, active: ["/home"] },
  { to: "/project-chat", label: "项目 AI", icon: MessageSquareText, active: ["/project-chat"] },
  { to: "/workflows", label: "任务队列", icon: Brain, active: ["/workflows", "/workspace"] },
  { to: "/data", label: "资料库", icon: Database, active: ["/data", "/library"] },
];

const expertItems = [
  { to: "/tools", label: "研究工具", icon: Wrench, active: ["/tools"] },
  { to: "/outputs", label: "研究产出", icon: BarChart3, active: ["/outputs"] },
  { to: "/admin", label: "运行准备", icon: Settings2, active: ["/admin", "/settings"], adminOnly: true },
];

function isRouteActive(locationPath: string, searchRunId: string | null, item: { to: string; active?: string[] }) {
  if (item.active) {
    return item.active.some((path) => locationPath === path || locationPath.startsWith(`${path}/`));
  }
  return locationPath === item.to || locationPath.startsWith(`${item.to}/`) || searchRunId === item.to;
}

function isProjectActive(project: ProjectViewModel, pathname: string, searchRunId: string | null) {
  return (
    searchRunId === project.id ||
    pathname === project.route ||
    pathname.startsWith(`${project.route}/`) ||
    pathname === project.workspaceRoute ||
    pathname.startsWith(`${project.workspaceRoute}/`)
  );
}

function projectWorkspaces(project: ProjectViewModel) {
  return [
    { to: project.papersRoute, label: "论文", count: project.evidenceCount, icon: BookOpenText },
    { to: project.hypothesesRoute, label: "假设", count: project.hypothesisCount, icon: Lightbulb },
    { to: project.experimentsRoute, label: "实验", count: project.outputCount > 0 ? 1 : 0, icon: FlaskConical },
    { to: project.reportsRoute, label: "报告", count: project.outputCount > 0 ? 1 : 0, icon: BarChart3 },
    { to: `/project-chat?run=${project.id}`, label: "项目 AI", count: null, icon: MessageSquareText },
  ];
}

function ProjectTreeNode({
  project,
  active,
  expanded,
  onToggle,
}: {
  project: ProjectViewModel;
  active: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const location = useLocation();
  const searchRunId = new URLSearchParams(location.search).get("run");

  return (
    <article className={classNames("project-tree-node", active && "active")}>
      <div className="project-node-main">
        <button className="project-toggle-button" type="button" onClick={onToggle} aria-label={expanded ? "收起项目" : "展开项目"}>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <Link className="project-node-link" to={project.route}>
          <Folder size={16} />
          <span>{project.title}</span>
          <small>{project.lastActivity}</small>
        </Link>
      </div>
      {expanded ? (
        <div className="project-node-children" role="group" aria-label={`${project.title} 子工作区`}>
          {projectWorkspaces(project).map((workspace) => {
            const Icon = workspace.icon;
            const selected =
              location.pathname === workspace.to ||
              location.pathname.startsWith(`${workspace.to}/`) ||
              (workspace.to.startsWith("/project-chat") && searchRunId === project.id);
            return (
              <Link className={classNames("project-child-link", selected && "active")} to={workspace.to} key={workspace.label}>
                <Icon size={15} />
                <span>{workspace.label}</span>
                {typeof workspace.count === "number" ? <em>{workspace.count}</em> : null}
              </Link>
            );
          })}
        </div>
      ) : null}
    </article>
  );
}

export function PrimaryNav() {
  const location = useLocation();
  const { user } = useAuth();
  const { projects } = useWorkbench();
  const searchRunId = new URLSearchParams(location.search).get("run");
  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>({});
  const visibleExpertItems = user?.role === "admin" ? expertItems : expertItems.filter((item) => !item.adminOnly);
  const activeProject = projects.find((project) => isProjectActive(project, location.pathname, searchRunId));
  const pinnedProject = activeProject ?? projects.find((project) => project.status === "queued" || project.status === "running") ?? projects[0];
  const listedProjects = useMemo(() => {
    return projects.filter((project) => project.id !== pinnedProject?.id).slice(0, 8);
  }, [pinnedProject, projects]);

  useEffect(() => {
    if (!pinnedProject) return;
    setExpandedProjects((existing) => ({ ...existing, [pinnedProject.id]: existing[pinnedProject.id] ?? true }));
  }, [pinnedProject]);

  const toggleProject = (projectId: string) => {
    setExpandedProjects((existing) => ({ ...existing, [projectId]: !existing[projectId] }));
  };

  return (
    <nav aria-label="研究项目导航" className="primary-nav project-sidebar-nav">
      <section className="nav-section">
        <div className="nav-action-grid">
          {topActions.map((item) => {
            const Icon = item.icon;
            const active = isRouteActive(location.pathname, searchRunId, item);
            return (
              <Link className={classNames("nav-action", active && "active")} to={item.to} key={item.to}>
                <Icon size={16} />
                <span>{item.label}</span>
              </Link>
            );
          })}
          <Link className="nav-action muted" to="/project-chat">
            <Search size={16} />
            <span>搜索</span>
          </Link>
        </div>
      </section>

      <section className="nav-section">
        <div className="nav-section-heading">
          <span>置顶</span>
          {pinnedProject ? <Link to={pinnedProject.route}>打开</Link> : null}
        </div>
        {pinnedProject ? (
          <ProjectTreeNode
            project={pinnedProject}
            active={isProjectActive(pinnedProject, location.pathname, searchRunId)}
            expanded={expandedProjects[pinnedProject.id] ?? true}
            onToggle={() => toggleProject(pinnedProject.id)}
          />
        ) : (
          <div className="nav-empty-state">
            <Folder size={16} />
            <span>还没有研究项目</span>
            <Link to="/home">创建第一个项目</Link>
          </div>
        )}
      </section>

      <section className="nav-section">
        <div className="nav-section-heading">
          <span>项目</span>
          <Link to="/projects">全部</Link>
        </div>
        <div className="project-tree-list">
          {listedProjects.length > 0 ? (
            listedProjects.map((project) => (
              <ProjectTreeNode
                key={project.id}
                project={project}
                active={isProjectActive(project, location.pathname, searchRunId)}
                expanded={expandedProjects[project.id] ?? false}
                onToggle={() => toggleProject(project.id)}
              />
            ))
          ) : (
            <div className="nav-empty-state">
              <Folder size={16} />
              <span>运行一次研究后会出现在这里。</span>
            </div>
          )}
        </div>
      </section>

      <section className="nav-section">
        <div className="nav-section-heading">
          <span>专家与运行</span>
        </div>
        <div className="nav-utility-list">
          {visibleExpertItems.map((item) => {
            const Icon = item.icon;
            const active = isRouteActive(location.pathname, searchRunId, item);
            return (
              <Link className={classNames("nav-item", active && "active")} to={item.to} key={item.to}>
                <Icon size={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </section>
    </nav>
  );
}
