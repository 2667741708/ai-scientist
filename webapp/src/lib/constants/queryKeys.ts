export const queryKeys = {
  health: ["health"] as const,
  runs: {
    current: ["runs", "current"] as const,
    byId: (runId: string) => ["runs", "byId", runId] as const,
    history: ["runs", "history"] as const,
  },
  workspace: {
    project: (projectId: string) => ["workspace", "project", projectId] as const,
    outputs: (projectId: string) => ["workspace", "outputs", projectId] as const,
  },
};
