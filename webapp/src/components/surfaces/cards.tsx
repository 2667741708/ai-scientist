import { ArrowRight, BookOpenText, FileText, FlaskConical, Sparkles } from "lucide-react";
import { useRef } from "react";
import { Link } from "react-router-dom";
import { classNames } from "../../lib/formatters/workbench";
import { useListEntranceMotion } from "../../lib/motion/useAnimeEntrance";
import { useAnimatedNumber } from "../../lib/motion/useAnimatedNumber";
import type { OutputViewModel, ProjectViewModel, SummaryItem } from "../../types/workbench";

export function SummaryList({ items, empty }: { items: SummaryItem[]; empty: string }) {
  const summaryListRef = useRef<HTMLDivElement | null>(null);
  useListEntranceMotion(summaryListRef, items.map((item) => `${item.label}:${item.value}`).join("|"));

  if (items.length === 0) {
    return <div className="inline-empty">{empty}</div>;
  }
  return (
    <div className="summary-list" ref={summaryListRef}>
      {items.map((item, index) => (
        <article className={classNames("summary-row", item.tone)} key={`${item.label}-${index}`}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </article>
      ))}
    </div>
  );
}

export function ProjectCard({ project }: { project: ProjectViewModel }) {
  const animatedHypothesisCount = useAnimatedNumber(project.hypothesisCount);
  const animatedEvidenceCount = useAnimatedNumber(project.evidenceCount);

  return (
    <article className="surface-card project-card">
      <div className="card-meta-row">
        <span>{project.stageLabel}</span>
      </div>
      <div className="card-copy">
        <h3>{project.title}</h3>
        <p>{project.researchGoal}</p>
      </div>
      <div className="card-stats">
        <span>{animatedHypothesisCount} 个候选假设</span>
        <span>{animatedEvidenceCount} 个证据来源</span>
      </div>
      <div className="card-footer">
        <span>{project.nextStep}</span>
        <div className="card-links">
          <Link to={project.route}>项目详情</Link>
          <Link to={project.workspaceRoute}>
            进入工作区
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </article>
  );
}

export function OutputCard({ output }: { output: OutputViewModel }) {
  const Icon =
    output.kind === "experiment"
      ? FlaskConical
      : output.kind === "report"
        ? FileText
        : Sparkles;
  const kindLabel =
    output.kind === "experiment"
      ? "实验"
      : output.kind === "report"
        ? "报告"
        : "发现";

  return (
    <Link to={output.route} className="surface-card output-card">
      <div className="card-meta-row">
        <Icon size={16} />
        <span>{kindLabel}</span>
      </div>
      <div className="card-copy">
        <h3>{output.title}</h3>
        <p>{output.summary}</p>
      </div>
    </Link>
  );
}

export function ReferenceCard({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <article className="surface-card reference-card">
      <div className="card-meta-row">
        <BookOpenText size={16} />
        <span>参考文献</span>
      </div>
      <div className="card-copy">
        <h3>{label}</h3>
        <p>{value}</p>
      </div>
    </article>
  );
}
