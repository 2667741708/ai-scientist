import type { RunRecord } from "../../types/workbench";

const RUN_HISTORY_KEY = "open-coscientist.run-history";

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function listLocalRunHistory() {
  if (!canUseStorage()) return [] as RunRecord[];
  try {
    const raw = window.localStorage.getItem(RUN_HISTORY_KEY);
    if (!raw) return [] as RunRecord[];
    const parsed = JSON.parse(raw) as RunRecord[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [] as RunRecord[];
  }
}

export function saveLocalRunHistory(history: RunRecord[]) {
  if (!canUseStorage()) return;
  window.localStorage.setItem(RUN_HISTORY_KEY, JSON.stringify(history.slice(0, 12)));
}

export function upsertRunHistory(record: RunRecord) {
  const history = listLocalRunHistory();
  const next = [record, ...history.filter((item) => item.run_id !== record.run_id)].slice(0, 12);
  saveLocalRunHistory(next);
  return next;
}
