import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createRun, fetchRun, fetchRunHistory, fetchWorkbenchSnapshot } from "../../lib/api/workbench";
import { queryKeys } from "../../lib/constants/queryKeys";
import { listLocalRunHistory, saveLocalRunHistory, upsertRunHistory } from "../../lib/storage/runHistory";
import type { RunRecord, RunRequest } from "../../types/workbench";

export function useRunHistoryQuery() {
  return useQuery({
    queryKey: queryKeys.runs.history,
    queryFn: async () => {
      try {
        const history = await fetchRunHistory(8);
        saveLocalRunHistory(history);
        return history;
      } catch {
        return listLocalRunHistory();
      }
    },
    staleTime: 3000,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const records = query.state.data as RunRecord[] | undefined;
      if (!records?.length) return false;
      return records.some((record) => record.status === "queued" || record.status === "running") ? 1500 : false;
    },
  });
}

export function useRunByIdQuery(runId: string | null) {
  return useQuery({
    queryKey: runId ? queryKeys.runs.byId(runId) : [...queryKeys.runs.current, "idle"],
    queryFn: () => fetchRun(runId!),
    enabled: Boolean(runId),
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const record = query.state.data as RunRecord | undefined;
      if (!record) return 900;
      return record.status === "queued" || record.status === "running" ? 900 : false;
    },
  });
}

export function useWorkbenchSnapshotQuery(runId: string | null) {
  return useQuery({
    queryKey: ["workbench", "snapshot", runId ?? "idle"],
    queryFn: () => fetchWorkbenchSnapshot({ run_id: runId! }),
    enabled: Boolean(runId),
    staleTime: 5000,
    refetchOnWindowFocus: false,
  });
}

export function useCreateRunMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: RunRequest) => createRun(request),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.runs.current });
      queryClient.invalidateQueries({ queryKey: queryKeys.runs.byId(data.run_id) });
    },
  });
}

export function updateHistoryCache(queryClient: ReturnType<typeof useQueryClient>, record: RunRecord) {
  const next = upsertRunHistory(record);
  queryClient.setQueryData(queryKeys.runs.history, next);
}

export function selectHistoryRun(queryClient: ReturnType<typeof useQueryClient>, record: RunRecord) {
  updateHistoryCache(queryClient, record);
  queryClient.setQueryData(queryKeys.runs.current, record);
  queryClient.setQueryData(queryKeys.runs.byId(record.run_id), record);
}

export function clearHistoryCache(queryClient: ReturnType<typeof useQueryClient>) {
  saveLocalRunHistory([]);
  queryClient.setQueryData(queryKeys.runs.history, []);
}
