import { Link } from "react-router-dom";
import { EmptyState } from "../../components/feedback/states";
import { ProjectCard } from "../../components/surfaces/cards";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { copy } from "../../lib/formatters/workbench";
import { useWorkbench } from "../../features/runs/workbench-context";

export function ProjectsPage() {
  const { projects } = useWorkbench();

  return (
    <div className="page-stack">
      <PageHeader
        kicker={copy.productKicker}
        title={copy.projects.title}
        actions={
          <Link className="button-secondary" to="/workspace">
            新建研究
          </Link>
        }
      />
      {projects.length > 0 ? (
        <div className="card-grid">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      ) : (
        <EmptyState title="还没有项目" description={copy.projects.empty} />
      )}
    </div>
  );
}
