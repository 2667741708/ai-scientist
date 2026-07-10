import { Link } from "react-router-dom";
import { EmptyState, StatusBanner } from "../../components/feedback/states";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { SummaryList } from "../../components/surfaces/cards";
import { copy, getVisibleProductRuns } from "../../lib/formatters/workbench";
import { useWorkbench } from "../../features/runs/workbench-context";

export function LibraryPage() {
  const { history } = useWorkbench();
  const visibleHistory = getVisibleProductRuns(history);
  const paperSummaries = visibleHistory.map((run) => ({
    label: run.request.research_goal,
    value: run.request.literature_review
      ? "已启用文献支撑研究"
      : "当前记录缺少文献证据，应重新回到实时文献支撑路径。",
  }));

  return (
    <div className="page-stack">
      <PageHeader
        kicker="资料库"
        title={copy.library.title}
      />
      <StatusBanner tone="warning">
        资料库旧入口已收敛到“资料库”路径；引用、解析记录和证据定位请在资料库页面按需展开查看。
      </StatusBanner>
      {paperSummaries.length > 0 ? (
        <section className="surface-card overview-panel">
          <SummaryList items={paperSummaries} empty={copy.library.empty} />
        </section>
      ) : (
        <EmptyState
          title="还没有资料库内容"
          description={copy.library.empty}
          actions={
            <>
              <Link className="button-primary" to="/data">
                进入资料库
              </Link>
              <Link className="button-secondary" to="/workspace">
                创建研究
              </Link>
            </>
          }
        />
      )}
    </div>
  );
}
