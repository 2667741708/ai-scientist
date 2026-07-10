import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";
import { deepseekProModelName, deepseekReasonerModelName, defaultModelName, modelGroups } from "../../lib/constants/models";
import { getProviderIdForModel, getSelectedProviderStatus, copy } from "../../lib/formatters/workbench";
import { mapRunsToProjects } from "../../lib/view-models/workbench";
import type { DetailTab, Health, HypothesisPanelTab, RunRecord } from "../../types/workbench";
import { startLiteratureService as requestStartLiteratureService, subscribeToRunEvents } from "../../lib/api/workbench";
import { queryKeys } from "../../lib/constants/queryKeys";
import { useHealthQuery } from "../health/queries";
import {
  selectHistoryRun,
  updateHistoryCache,
  useCreateRunMutation,
  useRunByIdQuery,
  useRunHistoryQuery,
} from "./queries";

type WorkbenchContextValue = {
  goal: string;
  setGoal: (value: string) => void;
  modelName: string;
  setModelName: (value: string) => void;
  thinkingMode: boolean;
  setThinkingMode: (enabled: boolean) => void;
  demoMode: boolean;
  setDemoMode: (value: boolean) => void;
  literatureReview: boolean;
  setLiteratureReview: (value: boolean) => void;
  initialHypotheses: number;
  setInitialHypotheses: (value: number) => void;
  iterations: number;
  setIterations: (value: number) => void;
  minReferences: number;
  setMinReferences: (value: number) => void;
  maxReferences: number;
  setMaxReferences: (value: number) => void;
  selectedIndex: number;
  setSelectedIndex: (value: number) => void;
  activeDetailTab: DetailTab;
  setActiveDetailTab: (value: DetailTab) => void;
  activeHypothesisPanelTab: HypothesisPanelTab;
  setActiveHypothesisPanelTab: (value: HypothesisPanelTab) => void;
  currentRunId: string | null;
  currentRun: RunRecord | null;
  history: RunRecord[];
  projects: ReturnType<typeof mapRunsToProjects>;
  health: Health | null;
  healthLoading: boolean;
  isBusy: boolean;
  startRun: (goalOverride?: string) => Promise<string | null>;
  clearCurrentRun: () => void;
  openHistoryRun: (record: RunRecord) => void;
  refreshHealth: () => Promise<unknown>;
  startLiteratureService: () => Promise<void>;
  literatureServiceStarting: boolean;
  error: string | null;
  clearError: () => void;
  runBlocked: boolean;
  selectedProviderUsable: boolean;
};

const WorkbenchContext = createContext<WorkbenchContextValue | null>(null);

export function WorkbenchProvider({ children }: PropsWithChildren) {
  const [goal, setGoal] = useState("");
  const [modelName, setModelName] = useState(defaultModelName);
  const [demoMode, setDemoMode] = useState(false);
  const [literatureReview, setLiteratureReview] = useState(true);
  const [initialHypotheses, setInitialHypotheses] = useState(3);
  const [iterations, setIterations] = useState(0);
  const [minReferences, setMinReferencesState] = useState(2);
  const [maxReferences, setMaxReferencesState] = useState(6);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeDetailTab, setActiveDetailTab] = useState<DetailTab>("overview");
  const [activeHypothesisPanelTab, setActiveHypothesisPanelTab] = useState<HypothesisPanelTab>("overview");
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [literatureServiceStarting, setLiteratureServiceStarting] = useState(false);
  const queryClient = useQueryClient();

  const healthQuery = useHealthQuery();
  const historyQuery = useRunHistoryQuery();
  const runQuery = useRunByIdQuery(currentRunId);
  const createRunMutation = useCreateRunMutation();

  const currentRun = runQuery.data ?? null;
  const history = historyQuery.data ?? [];
  const projects = useMemo(() => mapRunsToProjects(history), [history]);
  const selectedProvider = getSelectedProviderStatus(healthQuery.data ?? null, modelName);
  const literatureAvailable = Boolean(healthQuery.data?.literature_mcp?.available);
  const selectedProviderUsable = Boolean(selectedProvider?.usable);
  const goalReady = goal.trim().length >= 8;
  const thinkingMode = modelName === deepseekReasonerModelName;
  const setThinkingMode = (enabled: boolean) => {
    setModelName(enabled ? deepseekReasonerModelName : deepseekProModelName);
  };
  const setMinReferences = (value: number) => {
    setMinReferencesState(Math.max(0, Math.min(value, 12)));
  };
  const setMaxReferences = (value: number) => {
    setMaxReferencesState(Math.max(0, Math.min(value, 12)));
  };
  const runBlocked =
    !goalReady ||
    !healthQuery.data ||
    !selectedProviderUsable ||
    !literatureAvailable;
  const isBusy = currentRun?.status === "queued" || currentRun?.status === "running";

  useEffect(() => {
    if (!currentRunId || !isBusy) return;
    return subscribeToRunEvents(
      currentRunId,
      () => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.runs.byId(currentRunId), exact: true });
        void queryClient.invalidateQueries({ queryKey: queryKeys.runs.history, exact: true });
      },
      () => undefined,
    );
  }, [currentRunId, isBusy, queryClient]);

  useEffect(() => {
    if (!healthQuery.data || selectedProviderUsable || modelName !== defaultModelName) return;
    const fallbackModel = modelGroups
      .flatMap((group) => group.models)
      .find((model) => healthQuery.data?.providers?.[getProviderIdForModel(model.value)]?.usable);
    if (fallbackModel) {
      setModelName(fallbackModel.value);
    }
  }, [healthQuery.data, modelName, selectedProviderUsable]);

  useEffect(() => {
    if (!currentRun) return;
    updateHistoryCache(queryClient, currentRun);
    if (currentRun.hypotheses.length > 0) {
      setSelectedIndex((existing) => Math.min(existing, currentRun.hypotheses.length - 1));
    }
    if (currentRun.status === "error") {
      setError(copy.workflow.runFailed);
    }
  }, [currentRun, queryClient]);

  const value = useMemo<WorkbenchContextValue>(
    () => ({
      goal,
      setGoal,
      modelName,
      setModelName,
      thinkingMode,
      setThinkingMode,
      demoMode,
      setDemoMode,
      literatureReview,
      setLiteratureReview,
      initialHypotheses,
      setInitialHypotheses,
      iterations,
      setIterations,
      minReferences,
      setMinReferences,
      maxReferences,
      setMaxReferences,
      selectedIndex,
      setSelectedIndex,
      activeDetailTab,
      setActiveDetailTab,
      activeHypothesisPanelTab,
      setActiveHypothesisPanelTab,
      currentRunId,
      currentRun,
      history,
      projects,
      health: healthQuery.data ?? null,
      healthLoading: healthQuery.isLoading,
      isBusy,
      startRun: async (goalOverride?: string) => {
        setError(null);
        setSelectedIndex(0);
        setActiveDetailTab("overview");
        setActiveHypothesisPanelTab("overview");
        const effectiveGoal = (goalOverride ?? goal).trim();
        if (goalOverride !== undefined) {
          setGoal(effectiveGoal);
        }
        const effectiveRunBlocked =
          effectiveGoal.length < 8 ||
          !healthQuery.data ||
          !selectedProviderUsable ||
          !literatureAvailable;
        if (effectiveRunBlocked) {
          setError(copy.workflow.runBlocked);
          return null;
        }
        try {
          const normalizedMinReferences = Math.min(minReferences, maxReferences);
          const normalizedMaxReferences = Math.max(minReferences, maxReferences);
          const activeLibraryId = window.localStorage.getItem("coscientist.activeLibraryId") || null;
          const data = await createRunMutation.mutateAsync({
            research_goal: effectiveGoal,
            model_name: modelName,
            demo_mode: false,
            literature_review: true,
            initial_hypotheses: initialHypotheses,
            iterations,
            min_references: normalizedMinReferences,
            max_references: normalizedMaxReferences,
            memory_scope: "library",
            library_id: activeLibraryId,
            auto_discover_papers: true,
            auto_ingest_papers: true,
            paper_discovery_limit: Math.min(Math.max(normalizedMaxReferences, 6), 12),
            paper_ingest_limit: Math.min(Math.max(normalizedMinReferences, 4), 8),
          });
          setCurrentRunId(data.run_id);
          return data.run_id;
        } catch {
          setError(copy.workflow.requestFailed);
          return null;
        }
      },
      clearCurrentRun: () => {
        setCurrentRunId(null);
        setSelectedIndex(0);
        setActiveDetailTab("overview");
        setActiveHypothesisPanelTab("overview");
        setError(null);
      },
      openHistoryRun: (record) => {
        setGoal(record.request.research_goal);
        setModelName(record.request.model_name);
        setDemoMode(false);
        setLiteratureReview(true);
        setInitialHypotheses(record.request.initial_hypotheses);
        setIterations(record.request.iterations);
        setMinReferencesState(record.request.min_references ?? 2);
        setMaxReferencesState(record.request.max_references ?? 6);
        setCurrentRunId(record.run_id);
        setSelectedIndex(0);
        setActiveDetailTab("overview");
        setActiveHypothesisPanelTab("overview");
        setError(null);
        selectHistoryRun(queryClient, record);
      },
      refreshHealth: () => healthQuery.refetch(),
      startLiteratureService: async () => {
        setError(null);
        setLiteratureServiceStarting(true);
        try {
          await requestStartLiteratureService();
          await healthQuery.refetch();
        } catch {
          setError("文献服务启动失败，请在运行准备中检查本地文献服务状态。");
        } finally {
          setLiteratureServiceStarting(false);
        }
      },
      literatureServiceStarting,
      error,
      clearError: () => setError(null),
      runBlocked,
      selectedProviderUsable,
    }),
    [
      activeDetailTab,
      activeHypothesisPanelTab,
      createRunMutation,
      currentRun,
      currentRunId,
      demoMode,
      error,
      goal,
      healthQuery,
      history,
      initialHypotheses,
      isBusy,
      iterations,
      literatureAvailable,
      literatureServiceStarting,
      literatureReview,
      maxReferences,
      minReferences,
      modelName,
      projects,
      queryClient,
      runBlocked,
      selectedIndex,
      selectedProviderUsable,
    ],
  );

  return <WorkbenchContext.Provider value={value}>{children}</WorkbenchContext.Provider>;
}

export function useWorkbench() {
  const context = useContext(WorkbenchContext);
  if (!context) throw new Error("useWorkbench must be used inside WorkbenchProvider");
  return context;
}
