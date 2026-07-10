import { BookOpen, FlaskConical, MessageSquareText } from "lucide-react";
import { useEffect } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { EmptyState } from "../../components/feedback/states";
import { SummaryList } from "../../components/surfaces/cards";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { copy } from "../../lib/formatters/workbench";
import { mapRunToWorkspaceView } from "../../lib/view-models/workbench";
import { ExperimentsPanel } from "../../features/experiments/ExperimentsPanel";
import { HypothesisWorkspace } from "../../features/hypotheses/HypothesisWorkspace";
import { ReportsPanel } from "../../features/reports/ReportsPanel";
import { useWorkbench } from "../../features/runs/workbench-context";
import { useProjectRouteRun } from "../../features/runs/useProjectRouteRun";
import { useWorkbenchSnapshotQuery } from "../../features/runs/queries";

function ProjectSectionNav({ projectId }: { projectId: string }) {
  return (
    <div className="detail-nav">
      <Link to={`/projects/${projectId}`}>概览</Link>
      <Link to={`/projects/${projectId}/papers`}>论文</Link>
      <Link to={`/projects/${projectId}/hypotheses`}>假设</Link>
      <Link to={`/projects/${projectId}/experiments`}>实验</Link>
      <Link to={`/projects/${projectId}/reports`}>报告</Link>
    </div>
  );
}

export function ProjectDetailPage() {
  const params = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const {
    projects,
    selectedIndex,
    setSelectedIndex,
    error,
  } = useWorkbench();
  const record = useProjectRouteRun(params.projectId);
  const snapshotQuery = useWorkbenchSnapshotQuery(params.projectId ?? null);

  useEffect(() => {
    if (!record) return;
    const hypothesisParam = Number(searchParams.get("hypothesis"));
    if (!Number.isInteger(hypothesisParam)) return;
    if (hypothesisParam < 0 || hypothesisParam >= record.hypotheses.length) return;
    if (hypothesisParam !== selectedIndex) setSelectedIndex(hypothesisParam);
  }, [record, searchParams, selectedIndex, setSelectedIndex]);

  if (!params.projectId || !record) {
    const fallbackProject = projects[0];
    return (
      <EmptyState
        title="找不到研究项目"
        description="当前路由对应的项目尚未在本地历史中建立。你可以回到项目列表，或继续最近一次可用研究。"
        actions={
          <>
            {fallbackProject ? (
              <Link className="button-primary" to={fallbackProject.route}>
                打开最近研究
              </Link>
            ) : (
              <Link className="button-primary" to="/workspace">
                进入工作区
              </Link>
            )}
            <Link className="button-secondary" to="/projects">
              返回项目列表
            </Link>
          </>
        }
      />
    );
  }

  const workspace = mapRunToWorkspaceView(record);
  const project = workspace.project;
  const isPapers = location.pathname.endsWith("/papers");
  const isHypotheses = location.pathname.endsWith("/hypotheses");
  const isExperiments = location.pathname.endsWith("/experiments");
  const isReports = location.pathname.endsWith("/reports");
  const isHistoricalDemo = record.request.demo_mode;
  const selectedHypothesis = workspace.hypotheses[selectedIndex] ?? workspace.hypotheses[0];

  return (
    <div className="page-stack">
      <PageHeader
        kicker="研究项目"
        title={project.title}
        description={project.researchGoal}
        actions={
          <Link className={isHistoricalDemo ? "button-secondary" : "button-primary"} to={project.workspaceRoute}>
            {isHistoricalDemo ? "查看只读工作区" : "进入工作区"}
          </Link>
        }
      />

      <ProjectSectionNav projectId={project.id} />

      {isPapers ? (
        <section className="task-surface">
          <header className="task-header">
            <div>
              <span>文献</span>
              <h2>先确认研究依据</h2>
              <p>
                {project.evidenceCount > 0
                  ? "当前结果已经带有可检查的证据字段。"
                  : record.request.literature_review
                    ? "已经请求文献 grounding，但当前还没有形成可引用来源。"
                    : "当前缺少文献证据；如需继续当前研究，应在实时文献支撑路径下重新运行。"}
              </p>
            </div>
          </header>
          {snapshotQuery.data?.papers.length ? (
            <div className="card-grid">
              {snapshotQuery.data.papers.map((paper) => (
                <article className="surface-card" key={paper.paper_id}>
                  <span className="section-kicker">{paper.source_reliability}</span>
                  <h3>{paper.title}</h3>
                  <p>{paper.authors.slice(0, 3).join("、") || "作者信息待补充"}{paper.year ? ` · ${paper.year}` : ""}</p>
                  <p className="muted-note">
                    {paper.chunks_count} 个全文片段 · {paper.experimental_chunks_count} 个实验片段
                  </p>
                </article>
              ))}
            </div>
          ) : snapshotQuery.isLoading ? (
            <div className="inline-empty">正在读取项目资料库…</div>
          ) : (
            <SummaryList
              items={workspace.hypotheses.flatMap((hypothesis) => hypothesis.citations).slice(0, 12)}
              empty={copy.library.empty}
            />
          )}
        </section>
      ) : null}

      {isHypotheses ? (
        <HypothesisWorkspace
          record={record}
          error={error}
          isHistoricalDemo={isHistoricalDemo}
          selectedIndex={selectedIndex}
          setSelectedIndex={setSelectedIndex}
        />
      ) : null}

      {isExperiments ? <ExperimentsPanel record={record} selectedIndex={selectedIndex} /> : null}
      {isReports ? <ReportsPanel record={record} selectedIndex={selectedIndex} /> : null}

      {!isPapers && !isHypotheses && !isExperiments && !isReports ? (
        <div className="project-overview-stack">
          <section className="project-hypothesis-board">
            <div className="section-heading">
              <h2>候选假设</h2>
              <p>选择一条假设后，右侧会显示摘要、证据边界和下一步实验/AI 分析入口。</p>
            </div>
            {workspace.hypotheses.length > 0 && selectedHypothesis ? (
              <div className="project-hypothesis-grid">
                <div className="project-hypothesis-list" role="listbox" aria-label="项目候选假设">
                  {workspace.hypotheses.map((hypothesis, index) => (
                    <button
                      className={selectedIndex === index ? "selected" : undefined}
                      type="button"
                      role="option"
                      aria-selected={selectedIndex === index}
                      onClick={() => setSelectedIndex(index)}
                      key={hypothesis.id}
                    >
                      <span>#{index + 1}</span>
                      <strong>{hypothesis.title}</strong>
                      <small>{hypothesis.summary}</small>
                    </button>
                  ))}
                </div>
                <article className="project-hypothesis-reader">
                  <div>
                    <span className="status-chip ok">当前选择 #{selectedIndex + 1}</span>
                    <h3>{selectedHypothesis.title}</h3>
                    <p>{selectedHypothesis.summary}</p>
                  </div>
                  <SummaryList
                    items={[
                      { label: "Elo / 排名", value: selectedHypothesis.rankLabel },
                      { label: "评分", value: selectedHypothesis.scoreLabel },
                      { label: "参考范围", value: selectedHypothesis.referenceRangeLabel },
                    ]}
                    empty={copy.details.summaryEmpty}
                  />
                  <div className="project-hypothesis-actions">
                    <Link className="button-secondary" to={project.hypothesesRoute}>
                      <BookOpen size={16} />
                      打开详细阅读
                    </Link>
                    <Link className="button-secondary" to={`/project-chat?run=${record.run_id}&hypothesis=${selectedIndex}`}>
                      <MessageSquareText size={16} />
                      与项目 AI 分析
                    </Link>
                    <Link className="button-primary" to={project.experimentsRoute}>
                      <FlaskConical size={16} />
                      进入实验设计
                    </Link>
                  </div>
                </article>
              </div>
            ) : (
              <EmptyState
                title="还没有候选假设"
                description="项目运行完成后会在这里展示多条可比较、可打开阅读的假设。"
                actions={<Link className="button-primary" to={project.workspaceRoute}>进入工作区生成</Link>}
              />
            )}
          </section>

        </div>
      ) : null}
    </div>
  );
}
