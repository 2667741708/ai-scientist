import { useEffect, useMemo } from "react";
import { useWorkbench } from "./workbench-context";
import { useRunByIdQuery } from "./queries";

export function useProjectRouteRun(projectId?: string) {
  const { currentRun, history, openHistoryRun } = useWorkbench();
  const routedRunQuery = useRunByIdQuery(projectId ?? null);
  const routeRun = useMemo(
    () => (projectId ? history.find((item) => item.run_id === projectId) ?? routedRunQuery.data ?? null : null),
    [history, projectId, routedRunQuery.data],
  );

  useEffect(() => {
    if (!routeRun) return;
    if (currentRun?.run_id === routeRun.run_id) return;
    openHistoryRun(routeRun);
  }, [currentRun?.run_id, openHistoryRun, routeRun]);

  return routeRun ?? currentRun;
}
