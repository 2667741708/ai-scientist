import {
  AlertTriangle,
  ArrowRight,
  BookMarked,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Database,
  FileDown,
  FileSearch,
  FlaskConical,
  Globe2,
  History,
  Languages,
  Loader2,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Terminal,
  UsersRound,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { SkeletonState } from "../../components/feedback/states";
import { PageHeader } from "../../components/surfaces/PageHeader";
import { useAuth } from "../../features/auth/auth-context";
import { useWorkbench } from "../../features/runs/workbench-context";
import {
  createResearchDelegation,
  createResearchSchedule,
  enqueueTerminalCommandJob,
  enqueueSshTrainingJob,
  executeFileSnapshotWorkflow,
  executeWebExtractWorkflow,
  getCommandPermissions,
  listBackgroundJobs,
  listKnowledgePapers,
  listPaperParseRuns,
  listResearchDelegations,
  listResearchSchedules,
  listResearchSkills,
  listResearchTasks,
  listSshTrainingServers,
  searchResearchSessions,
  tickResearchSchedule,
  updateCommandPermissions,
} from "../../lib/api/workbench";
import { classNames, formatBackendText, getSafeErrorMessage } from "../../lib/formatters/workbench";
import type {
  BackgroundJob,
  CommandPermissionMode,
  CommandPermissionPolicy,
  FileSnapshotResponse,
  ResearchDelegation,
  ResearchSchedule,
  ResearchSkill,
  ResearchTask,
  SessionSearchResult,
  SshTrainingJobResponse,
  SshTrainingServer,
  TerminalCommandJobResponse,
  WebExtractResponse,
} from "../../types/workbench";

const toolCategories = ["全部", "文献", "假设", "实验", "报告"];

const allTools = [
  {
    title: "论文解析",
    description: "把论文和来源线索整理进数据资产面。",
    category: "文献",
    icon: BookMarked,
    route: "/data",
    status: "需要数据",
  },
  {
    title: "引用检查",
    description: "检查候选假设是否具备足够引用来源。",
    category: "文献",
    icon: ClipboardCheck,
    route: "/data?view=references",
    status: "可检查",
  },
  {
    title: "候选假设中文翻译",
    description: "在工作区选中假设后，把技术表述翻译成中文说明。",
    category: "假设",
    icon: Languages,
    route: "/workspace",
    status: "工作区内使用",
  },
  {
    title: "证据抽屉",
    description: "点击单条假设后，按需查看参考文献和证据来源。",
    category: "假设",
    icon: Search,
    route: "/workspace",
    status: "按需展开",
  },
  {
    title: "实验模板",
    description: "把入选假设转成最小可证伪实验设计。",
    category: "实验",
    icon: FlaskConical,
    route: "/workspace",
    status: "后续步骤",
  },
  {
    title: "报告导出",
    description: "从研究产出中回看发现、实验计划和报告草稿。",
    category: "报告",
    icon: FileDown,
    route: "/outputs",
    status: "可回看",
  },
];

const searchTypeLabels: Record<string, string> = {
  run: "研究运行",
  hypothesis: "候选假设",
  tool_result: "工具证据",
  task: "科研任务",
  background_job: "后台任务",
};

const evidenceBackgroundWorkflows = new Set(["browser.web_extract", "pdf.parse_to_knowledge_base"]);

type ToolDrawerId =
  | "skills"
  | "command-permissions"
  | "terminal-command"
  | "ssh-training"
  | "schedules"
  | "delegations";

function formatTime(timestamp?: number | null) {
  if (!timestamp) return "暂无时间";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp * 1000));
}

function getErrorMessage(error: unknown, fallback: string) {
  return getSafeErrorMessage(error, fallback);
}

function statusTone(status?: string | null): "neutral" | "ok" | "warning" | "error" {
  if (!status) return "neutral";
  if (["complete", "done", "success", "active"].includes(status)) return "ok";
  if (["error", "failed", "blocked"].includes(status)) return "error";
  if (["running", "queued", "ready"].includes(status)) return "warning";
  return "neutral";
}

function formatStatusLabel(status?: string | null) {
  const labels: Record<string, string> = {
    active: "可用",
    blocked: "已阻塞",
    complete: "已完成",
    done: "已完成",
    error: "失败",
    failed: "失败",
    planned: "已计划",
    pending: "等待中",
    queued: "排队中",
    ready: "待处理",
    running: "进行中",
    success: "已完成",
  };
  return status ? labels[status] ?? "可回查" : "可回查";
}

function targetSummary(target: Record<string, unknown>) {
  return Object.entries(target)
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" · ");
}

function compactPathName(path: string) {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || "文件证据快照";
}

function webSourceTitle(title: string | null | undefined, url: string) {
  if (title?.trim()) return title.trim();
  try {
    return new URL(url).hostname || "公开网页证据";
  } catch {
    return "公开网页证据";
  }
}

function formatWorkflowName(value?: string | null) {
  if (!value) return "研究任务流程";
  const labels: Record<string, string> = {
    citation_provenance_qa: "引用证据复核",
    evidence_audit: "证据审计",
    periodic_research_review: "定期研究复核",
    "ssh.training_command": "远程训练任务",
    "terminal.command": "本地命令任务",
    "browser.web_extract": "网页证据抽取",
    "pdf.parse_to_knowledge_base": "PDF 解析入库",
    "引用证据复核": "引用证据复核",
  };
  if (labels[value]) return labels[value];
  return /^[a-z0-9_. -]+$/i.test(value) ? "研究任务流程" : value;
}

function isLikelySafeCommand(command: string) {
  const text = command.trim();
  if (!text) return false;
  if (/[>|]/.test(text)) return false;
  if (/\b(rm|del|Remove-Item|sudo|scp|rsync|curl|wget|Invoke-WebRequest|npm\s+install|pip\s+install|git\s+(?:pull|push|clone|reset|clean))\b/i.test(text)) {
    return false;
  }
  return /^(pwd|ls|dir|Get-ChildItem|hostname|whoami|date|echo|cat|type|Get-Content|head|tail|wc|rg|grep|git\s+(status|diff|log|show)|python\s+--version|node\s+-v|npm\s+-v|nvidia-smi|df|du|where|which|Get-Command|sha256sum|Get-FileHash|tar\s+-t|tar\s+-tzf|test\s+-[fde]|Test-Path)(\s|$)/i.test(text);
}

function needsManualCommandApproval(mode: CommandPermissionMode, command: string) {
  if (mode === "full_access") return false;
  if (mode === "approve_safe" && isLikelySafeCommand(command)) return false;
  return true;
}

function commandPermissionLabel(mode?: CommandPermissionMode) {
  const labels: Record<CommandPermissionMode, string> = {
    request_approval: "请求批准",
    approve_safe: "替我审批",
    full_access: "完全访问权限",
  };
  return mode ? labels[mode] : "请求批准";
}

function formatDelegationStrategy(value?: string | null) {
  if (value === "parallel_review") return "并行审查";
  return value && !/^[a-z0-9_. -]+$/i.test(value) ? value : "多角色审查";
}

function formatSshAvailability(availability: Record<string, unknown>) {
  const reason = typeof availability.reason === "string" ? availability.reason : "";
  const mode = typeof availability.mode === "string" ? formatBackendText(availability.mode) : "已配置";
  return reason ? `${mode}：${reason}` : mode;
}

export function ToolsPage() {
  const { user } = useAuth();
  const { health } = useWorkbench();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(toolCategories[0]);
  const [paperCount, setPaperCount] = useState(0);
  const [parseRunCount, setParseRunCount] = useState(0);
  const [tasks, setTasks] = useState<ResearchTask[]>([]);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [skills, setSkills] = useState<ResearchSkill[]>([]);
  const [schedules, setSchedules] = useState<ResearchSchedule[]>([]);
  const [delegations, setDelegations] = useState<ResearchDelegation[]>([]);
  const [sshServers, setSshServers] = useState<SshTrainingServer[]>([]);
  const [sshAvailability, setSshAvailability] = useState<Record<string, unknown> | null>(null);
  const [dataStatus, setDataStatus] = useState<"idle" | "loading" | "error">("idle");
  const [activeDrawer, setActiveDrawer] = useState<ToolDrawerId | null>(null);

  const [sessionQuery, setSessionQuery] = useState("");
  const [sessionStatus, setSessionStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [sessionResults, setSessionResults] = useState<SessionSearchResult[]>([]);
  const [sessionError, setSessionError] = useState("");

  const [filePath, setFilePath] = useState("README.md");
  const [fileStartLine, setFileStartLine] = useState(1);
  const [fileLineCount, setFileLineCount] = useState(80);
  const [fileReason, setFileReason] = useState("为当前科研假设保留源码或文档证据快照");
  const [fileApproved, setFileApproved] = useState(false);
  const [fileStatus, setFileStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [fileResult, setFileResult] = useState<FileSnapshotResponse | null>(null);
  const [fileError, setFileError] = useState("");

  const [webUrl, setWebUrl] = useState("");
  const [webReason, setWebReason] = useState("为当前科研假设采集公开网页证据并写入知识库");
  const [webApproved, setWebApproved] = useState(false);
  const [webIngest, setWebIngest] = useState(true);
  const [webStatus, setWebStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [webResult, setWebResult] = useState<WebExtractResponse | null>(null);
  const [webError, setWebError] = useState("");

  const [commandPermission, setCommandPermission] = useState<CommandPermissionPolicy | null>(null);
  const [permissionStatus, setPermissionStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [permissionError, setPermissionError] = useState("");

  const [terminalWorkdir, setTerminalWorkdir] = useState("");
  const [terminalCommand, setTerminalCommand] = useState("git status --short");
  const [terminalTimeout, setTerminalTimeout] = useState(120);
  const [terminalReason, setTerminalReason] = useState("本地诊断：检查项目工作树或运行环境状态");
  const [terminalApproved, setTerminalApproved] = useState(false);
  const [terminalStatus, setTerminalStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [terminalResult, setTerminalResult] = useState<TerminalCommandJobResponse | null>(null);
  const [terminalError, setTerminalError] = useState("");

  const [sshServerId, setSshServerId] = useState("c201-4090");
  const [sshWorkdir, setSshWorkdir] = useState("");
  const [sshCommand, setSshCommand] = useState("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader");
  const [sshTimeout, setSshTimeout] = useState(120);
  const [sshReason, setSshReason] = useState("演示远程训练节点可达性，只执行 GPU 状态检查");
  const [sshApproved, setSshApproved] = useState(false);
  const [sshStatus, setSshStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [sshResult, setSshResult] = useState<SshTrainingJobResponse | null>(null);
  const [sshError, setSshError] = useState("");

  const [scheduleTitle, setScheduleTitle] = useState("每周文献与证据复核");
  const [scheduleWorkflow, setScheduleWorkflow] = useState("引用证据复核");
  const [scheduleInterval, setScheduleInterval] = useState(168);
  const [scheduleStatus, setScheduleStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [scheduleError, setScheduleError] = useState("");
  const [tickStatusById, setTickStatusById] = useState<Record<string, "idle" | "loading" | "success" | "error">>({});

  const [delegationTitle, setDelegationTitle] = useState("文献支撑与反证并行审查");
  const [delegationStatus, setDelegationStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [delegationError, setDelegationError] = useState("");

  const literatureReady = Boolean(health?.literature_mcp?.available);
  const canViewAdmin = user?.role === "admin";
  const activeCategory = toolCategories.includes(category) ? category : "全部";
  const activeCommandPermissionMode = commandPermission?.mode ?? "request_approval";
  const terminalNeedsApproval = needsManualCommandApproval(activeCommandPermissionMode, terminalCommand);
  const sshNeedsApproval = needsManualCommandApproval(activeCommandPermissionMode, sshCommand);

  useEffect(() => {
    let cancelled = false;
    async function loadDataToolStatus() {
      setDataStatus("loading");
      try {
        const [
          papers,
          parseRuns,
          taskBoard,
          backgroundJobs,
          skillList,
          scheduleList,
          delegationList,
          sshList,
          permissionInfo,
        ] = await Promise.all([
          listKnowledgePapers(),
          listPaperParseRuns(),
          listResearchTasks({ limit: 6 }),
          listBackgroundJobs({ limit: 6 }),
          listResearchSkills(),
          listResearchSchedules({ limit: 6 }),
          listResearchDelegations({ limit: 6 }),
          listSshTrainingServers(),
          getCommandPermissions(),
        ]);
        if (!cancelled) {
          setPaperCount(papers.count);
          setParseRunCount(parseRuns.count);
          setTasks(taskBoard.tasks);
          setJobs(backgroundJobs.jobs.filter((job) => evidenceBackgroundWorkflows.has(job.workflow_name)));
          setSkills(skillList.skills);
          setSchedules(scheduleList.schedules);
          setDelegations(delegationList.delegations);
          setSshServers(sshList.servers);
          setSshAvailability(sshList.availability);
          setCommandPermission(permissionInfo.policy);
          if (sshList.servers.length > 0 && !sshList.servers.some((server) => server.server_id === sshServerId)) {
            setSshServerId(sshList.servers[0].server_id);
          }
          setDataStatus("idle");
        }
      } catch {
        if (!cancelled) {
          setPaperCount(0);
          setParseRunCount(0);
          setTasks([]);
          setJobs([]);
          setSkills([]);
          setSchedules([]);
          setDelegations([]);
          setSshServers([]);
          setSshAvailability(null);
          setCommandPermission(null);
          setDataStatus("error");
        }
      }
    }
    void loadDataToolStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredTools = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return allTools.filter((tool) => {
      const categoryMatch = activeCategory === "全部" || tool.category === activeCategory;
      const queryMatch =
        normalized.length === 0 ||
        `${tool.title} ${tool.description} ${tool.category}`.toLowerCase().includes(normalized);
      return categoryMatch && queryMatch;
    });
  }, [activeCategory, query]);

  const handleSessionSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (sessionQuery.trim().length < 2 || sessionStatus === "loading") return;
    setSessionStatus("loading");
    setSessionError("");
    try {
      const response = await searchResearchSessions({
        q: sessionQuery,
        types: ["run", "hypothesis", "tool_result", "task", "background_job"],
        limit: 12,
      });
      setSessionResults(response.results);
      setSessionStatus("success");
    } catch (error) {
      setSessionResults([]);
      setSessionError(getErrorMessage(error, "历史证据暂时不可检索。"));
      setSessionStatus("error");
    }
  };

  const handleFileSnapshot = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!filePath.trim() || !fileApproved || fileStatus === "loading") return;
    setFileStatus("loading");
    setFileError("");
    setFileResult(null);
    try {
      const response = await executeFileSnapshotWorkflow({
        source_path: filePath.trim(),
        phase: "evidence_audit",
        start_line: fileStartLine,
        line_count: fileLineCount,
        approval: {
          confirmed: true,
          scope: "file.source_snapshot",
          reason: fileReason.trim() || undefined,
        },
      });
      setFileResult(response);
      setFileStatus("success");
    } catch (error) {
      setFileError(getErrorMessage(error, "文件快照未能完成。"));
      setFileStatus("error");
    }
  };

  const handleWebExtract = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!webUrl.trim() || !webApproved || webStatus === "loading") return;
    setWebStatus("loading");
    setWebError("");
    setWebResult(null);
    try {
      const response = await executeWebExtractWorkflow({
        url: webUrl.trim(),
        phase: "literature_review",
        ingest_to_knowledge_base: webIngest,
        approval: {
          confirmed: true,
          scope: "browser.web_extract",
          reason: webReason.trim() || undefined,
        },
      });
      setWebResult(response);
      setWebStatus("success");
    } catch (error) {
      setWebError(getErrorMessage(error, "网页证据采集未能完成。"));
      setWebStatus("error");
    }
  };

  const handleCommandPermissionMode = async (mode: CommandPermissionMode) => {
    if (!canViewAdmin || permissionStatus === "loading" || mode === activeCommandPermissionMode) return;
    setPermissionStatus("loading");
    setPermissionError("");
    try {
      const response = await updateCommandPermissions(mode);
      setCommandPermission(response.policy);
      setPermissionStatus("success");
    } catch (error) {
      setPermissionError(getErrorMessage(error, "命令权限模式未能更新，请确认当前账号具备运行时管理权限。"));
      setPermissionStatus("error");
    }
  };

  const handleTerminalCommand = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canViewAdmin || !terminalCommand.trim() || (terminalNeedsApproval && !terminalApproved) || terminalStatus === "loading") return;
    setTerminalStatus("loading");
    setTerminalError("");
    setTerminalResult(null);
    try {
      const response = await enqueueTerminalCommandJob({
        command: terminalCommand.trim(),
        workdir: terminalWorkdir.trim() || null,
        phase: "operator_diagnostics",
        timeout_seconds: terminalTimeout,
        approval: {
          confirmed: terminalNeedsApproval ? terminalApproved : false,
          scope: "terminal.command",
          reason: terminalReason.trim() || undefined,
        },
      });
      setTerminalResult(response);
      setTerminalStatus("success");
    } catch (error) {
      setTerminalError(getErrorMessage(error, "本地命令任务未能提交，请检查权限模式、确认状态和命令范围。"));
      setTerminalStatus("error");
    }
  };

  const handleSshTraining = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!sshServerId || !sshCommand.trim() || (sshNeedsApproval && !sshApproved) || sshStatus === "loading") return;
    setSshStatus("loading");
    setSshError("");
    setSshResult(null);
    try {
      const response = await enqueueSshTrainingJob({
        server_id: sshServerId,
        command: sshCommand.trim(),
        workdir: sshWorkdir.trim() || null,
        phase: "experiment_execution",
        timeout_seconds: sshTimeout,
        approval: {
          confirmed: sshNeedsApproval ? sshApproved : false,
          scope: "ssh.training_command",
          reason: sshReason.trim() || undefined,
        },
      });
      setSshResult(response);
      setSshStatus("success");
    } catch (error) {
      setSshError(getErrorMessage(error, "远程训练任务未能提交，请检查服务器选择、确认状态和命令范围。"));
      setSshStatus("error");
    }
  };

  const handleCreateSchedule = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!scheduleTitle.trim() || !scheduleWorkflow.trim() || scheduleStatus === "loading") return;
    setScheduleStatus("loading");
    setScheduleError("");
    try {
      const response = await createResearchSchedule({
        title: scheduleTitle.trim(),
        workflow_name: scheduleWorkflow.trim(),
        phase: "evidence_audit",
        interval_hours: scheduleInterval,
        arguments: { source: "tools_page", workflow_goal: "periodic_research_review" },
      });
      setSchedules((items) => [response.schedule, ...items].slice(0, 6));
      setScheduleStatus("success");
    } catch (error) {
      setScheduleError(getErrorMessage(error, "科研计划未能创建。"));
      setScheduleStatus("error");
    }
  };

  const handleTickSchedule = async (schedule: ResearchSchedule) => {
    if (tickStatusById[schedule.schedule_id] === "loading") return;
    setTickStatusById((items) => ({ ...items, [schedule.schedule_id]: "loading" }));
    try {
      const response = await tickResearchSchedule(schedule.schedule_id, {
        force: true,
        approval: {
          confirmed: true,
          scope: "research_schedule.tick",
          reason: "研究者在工具页手动生成到期待办，不直接执行外部工具。",
        },
      });
      setSchedules((items) => items.map((item) => (item.schedule_id === schedule.schedule_id ? response.schedule : item)));
      setTasks((items) => [response.task, ...items].slice(0, 6));
      setTickStatusById((items) => ({ ...items, [schedule.schedule_id]: "success" }));
    } catch {
      setTickStatusById((items) => ({ ...items, [schedule.schedule_id]: "error" }));
    }
  };

  const handleCreateDelegation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!delegationTitle.trim() || delegationStatus === "loading") return;
    setDelegationStatus("loading");
    setDelegationError("");
    try {
      const response = await createResearchDelegation({
        title: delegationTitle.trim(),
        phase: "review_critique",
        strategy: "parallel_review",
        summary: "Created from the tools page as a planned multi-role research review. Run execution still requires approval.",
        agents: [
          {
            role: "Literature grounding reviewer",
            brief: "Check whether the target hypothesis has parsed fulltext, source reliability, support level, and citation provenance.",
            skill_ids: ["evidence-grounding-rubric", "citation-provenance-qa"],
            target_ref: { source: "tools_page" },
          },
          {
            role: "Falsifiability reviewer",
            brief: "Identify failure conditions, negative controls, and results that would weaken the hypothesis.",
            skill_ids: ["falsifiability-review", "experiment-design-checklist"],
            target_ref: { source: "tools_page" },
          },
        ],
      });
      setDelegations((items) => [response.delegation, ...items].slice(0, 6));
      setDelegationStatus("success");
    } catch (error) {
      setDelegationError(getErrorMessage(error, "多角色审查计划未能创建。"));
      setDelegationStatus("error");
    }
  };

  const drawerTitles: Record<ToolDrawerId, { kicker: string; title: string; description: string }> = {
    skills: {
      kicker: "方法模板",
      title: "模板",
      description: "查看当前工作台注册的方法模板和适用阶段。",
    },
    "command-permissions": {
      kicker: "运行边界",
      title: "权限",
      description: "控制本地终端和远程 SSH 命令是否需要人工确认。",
    },
    "terminal-command": {
      kicker: "管理员工具",
      title: "本地",
      description: "通过权限门控执行本机命令，并保留审批与结果记录。",
    },
    "ssh-training": {
      kicker: "实验执行",
      title: "远训",
      description: "把验证脚本或训练命令提交到白名单服务器，并保留审计记录。",
    },
    schedules: {
      kicker: "定期计划",
      title: "复核",
      description: "保存周期性研究复核计划；触发时只生成待办任务。",
    },
    delegations: {
      kicker: "多角色审查",
      title: "审查",
      description: "创建文献支撑、反证和可证伪性等并行审查计划。",
    },
  };
  const activeDrawerMeta = activeDrawer ? drawerTitles[activeDrawer] : null;

  return (
    <div className="page-stack">
      <PageHeader
        kicker="研究工具"
        title="证据工具"
        description="围绕论文、网页和项目文件做证据采集与回查，结果进入可审计的知识链。"
      />

      <section className="tool-console-shell" aria-label="研究动作控制台">
        <article className="tool-console-panel">
          <div>
            <span className="section-kicker">证据状态</span>
            <h2>先确认资料，再采集证据</h2>
            <p>这里保留与当前研究直接相关的资料、解析和任务状态；运行时诊断和远程执行已从普通工具页移出。</p>
          </div>
          <div className="tool-status-strip" aria-label="工具状态摘要">
            <span className={classNames("status-pill", literatureReady ? "ok" : "warning")}>
              文献服务 {literatureReady ? "可达" : "待检查"}
            </span>
            <span className="status-pill neutral">{paperCount} 篇资料</span>
            <span className="status-pill neutral">{parseRunCount} 次解析</span>
          </div>
          {dataStatus === "error" ? (
            <article className="status-banner warning" role="status">
              工具状态暂时不可读取。执行动作时后端仍会重新校验权限、范围和可用性。
            </article>
          ) : null}
          <div className="quick-actions" aria-label="常用研究动作">
            <a href="#tool-execution-console">
              <FileSearch size={14} />
              采集证据
            </a>
            <a href="#session-search-console">
              <History size={14} />
              历史回查
            </a>
            <Link to="/data">
              <Database size={14} />
              资料入库
            </Link>
            <Link to="/outputs">
              <FileDown size={14} />
              装配报告
            </Link>
          </div>
        </article>
        <OperationList title="活跃科研任务" icon={ClipboardCheck} items={tasks} empty="暂无任务板记录。" />
        <BackgroundJobList jobs={jobs} />
      </section>

      <section className="tool-workbench-panel" id="tool-execution-console">
        <div className="section-heading">
          <div>
            <span className="section-kicker">证据采集</span>
            <h2>回查、文件和网页证据</h2>
            <p>选择一个证据动作，确认采集范围，再把结果写入可回查的证据链或知识库。</p>
          </div>
          <div className="tool-status-strip" aria-label="工具状态摘要">
            <span className={classNames("status-pill", literatureReady ? "ok" : "warning")}>
              文献服务 {literatureReady ? "可达" : "待检查"}
            </span>
            <span className="status-pill neutral">任务 {tasks.length}</span>
            <span className="status-pill neutral">后台 {jobs.length}</span>
          </div>
        </div>

        <div className="tool-workbench-grid">
          <article className="tool-workflow-card" id="session-search-console">
            <WorkflowCardHeader
              icon={History}
              title="历史证据回查"
              description="检索已保存的运行、假设、工具结果、任务和后台作业。"
              status={sessionStatus}
            />
            <form className="tool-form-row" onSubmit={(event) => void handleSessionSearch(event)}>
              <label className="command-input" htmlFor="session-search-query">
                <Search size={16} />
                <input
                  id="session-search-query"
                  type="search"
                  value={sessionQuery}
                  onChange={(event) => setSessionQuery(event.target.value)}
                  placeholder="输入假设、实验指标、证据名称或任务关键词"
                  aria-invalid={sessionStatus === "error"}
                />
              </label>
              <button
                className={classNames("button-secondary", sessionStatus === "loading" && "is-loading")}
                type="submit"
                disabled={sessionQuery.trim().length < 2 || sessionStatus === "loading"}
                aria-busy={sessionStatus === "loading"}
              >
                {sessionStatus === "loading" ? "检索中" : "回查"}
              </button>
            </form>
            <WorkflowFeedback
              status={sessionStatus}
              error={sessionError}
              success={sessionResults.length ? `找到 ${sessionResults.length} 条可回查记录。` : "没有匹配记录，可换用更具体的术语。"}
            />
            {sessionStatus === "loading" ? <SkeletonState title="正在回查历史证据" rows={4} /> : null}
            {sessionResults.length > 0 ? <SessionResultList results={sessionResults} /> : null}
          </article>

          <article className="tool-workflow-card">
            <WorkflowCardHeader
              icon={FileSearch}
              title="本地文件证据快照"
              description="在源码或文档内截取指定行段，保存采集时间和片段摘要。"
              status={fileStatus}
            />
            <form className="tool-form-stack" onSubmit={(event) => void handleFileSnapshot(event)}>
              <label className="field-stack" htmlFor="file-snapshot-path">
                <span>文件路径</span>
                <input
                  id="file-snapshot-path"
                  type="text"
                  value={filePath}
                  onChange={(event) => setFilePath(event.target.value)}
                  placeholder="例如 README.md 或 src/open_coscientist/generator.py"
                  aria-invalid={fileStatus === "error"}
                />
              </label>
              <div className="tool-inline-fields">
                <label className="field-stack" htmlFor="file-start-line">
                  <span>起始行</span>
                  <input
                    id="file-start-line"
                    type="number"
                    min={1}
                    value={fileStartLine}
                    onChange={(event) => setFileStartLine(Number(event.target.value) || 1)}
                  />
                </label>
                <label className="field-stack" htmlFor="file-line-count">
                  <span>行数</span>
                  <input
                    id="file-line-count"
                    type="number"
                    min={1}
                    max={2000}
                    value={fileLineCount}
                    onChange={(event) => setFileLineCount(Number(event.target.value) || 1)}
                  />
                </label>
              </div>
              <label className="field-stack" htmlFor="file-approval-reason">
                <span>采集理由</span>
                <input
                  id="file-approval-reason"
                  type="text"
                  value={fileReason}
                  onChange={(event) => setFileReason(event.target.value)}
                />
              </label>
              <label className="tool-approval-row">
                <input
                  type="checkbox"
                  checked={fileApproved}
                  onChange={(event) => setFileApproved(event.target.checked)}
                />
                <span>确认只采集该路径片段，作为科研证据链的一部分。</span>
              </label>
              <button
                className={classNames("button-primary", fileStatus === "loading" && "is-loading")}
                type="submit"
                disabled={!filePath.trim() || !fileApproved || fileStatus === "loading"}
                aria-busy={fileStatus === "loading"}
              >
                {fileStatus === "loading" ? "正在生成快照" : "生成文件证据"}
              </button>
            </form>
            <WorkflowFeedback
              status={fileStatus}
              error={fileError}
              success={fileResult ? "已保存文件证据快照，可在下方摘要检查片段内容。" : "文件证据已保存。"}
            />
            {fileResult ? <FileSnapshotPreview result={fileResult} /> : null}
          </article>

          <article className="tool-workflow-card">
            <WorkflowCardHeader
              icon={Globe2}
              title="公开网页证据抽取"
              description="抓取公开文本或 HTML 页面，保留来源摘要并可选写入知识库。"
              status={webStatus}
            />
            <form className="tool-form-stack" onSubmit={(event) => void handleWebExtract(event)}>
              <label className="field-stack" htmlFor="web-extract-url">
                <span>公开网页 URL</span>
                <input
                  id="web-extract-url"
                  type="text"
                  value={webUrl}
                  onChange={(event) => setWebUrl(event.target.value)}
                  placeholder="https://..."
                  aria-invalid={webStatus === "error"}
                />
              </label>
              <label className="field-stack" htmlFor="web-approval-reason">
                <span>采集理由</span>
                <input
                  id="web-approval-reason"
                  type="text"
                  value={webReason}
                  onChange={(event) => setWebReason(event.target.value)}
                />
              </label>
              <label className="tool-approval-row">
                <input
                  type="checkbox"
                  checked={webIngest}
                  onChange={(event) => setWebIngest(event.target.checked)}
                />
                <span>抽取后写入知识库。</span>
              </label>
              <label className="tool-approval-row">
                <input
                  type="checkbox"
                  checked={webApproved}
                  onChange={(event) => setWebApproved(event.target.checked)}
                />
                <span>确认该 URL 为公开来源，并允许保存证据快照。</span>
              </label>
              <button
                className={classNames("button-primary", webStatus === "loading" && "is-loading")}
                type="submit"
                disabled={!webUrl.trim() || !webApproved || webStatus === "loading"}
                aria-busy={webStatus === "loading"}
              >
                {webStatus === "loading" ? "正在抽取证据" : "抽取网页证据"}
              </button>
            </form>
            <WorkflowFeedback
              status={webStatus}
              error={webError}
              success={webResult ? `已采集 ${webSourceTitle(webResult.web_result.title, webResult.web_result.final_url)}。` : "网页证据已保存。"}
            />
            {webResult ? <WebExtractPreview result={webResult} /> : null}
          </article>
        </div>
      </section>

      <section className="tool-workbench-panel" aria-label="按需研究工具">
        <div className="section-heading">
          <div>
            <span className="section-kicker">按需工具</span>
            <h2>运行、计划和审查工具</h2>
            <p>这些能力仍可在工具页调用，但默认压缩为单行；需要执行或查看明细时再打开右侧面板。</p>
          </div>
          <div className="tool-status-strip" aria-label="按需工具状态摘要">
            <span className="status-pill neutral">{skills.length} 个模板</span>
            <span className="status-pill neutral">{schedules.length} 个计划</span>
            <span className="status-pill neutral">{delegations.length} 个审查</span>
          </div>
        </div>
        <div className="tool-compact-list">
          <ToolActionRow
            icon={BookMarked}
            title="模板"
            description="查看证据支撑、可证伪性和实验设计等方法模板。"
            status={`${skills.length} 个模板`}
            onOpen={() => setActiveDrawer("skills")}
          />
          <ToolActionRow
            icon={ShieldCheck}
            title="权限"
            description="管理本地命令和远程任务的人工确认边界。"
            status={canViewAdmin ? commandPermissionLabel(activeCommandPermissionMode) : "只读"}
            onOpen={() => setActiveDrawer("command-permissions")}
          />
          <ToolActionRow
            icon={Terminal}
            title="本地"
            description="管理员诊断本机运行环境或项目工作树，结果写入审计。"
            status={canViewAdmin ? "可提交" : "仅管理员"}
            onOpen={() => setActiveDrawer("terminal-command")}
          />
          <ToolActionRow
            icon={FlaskConical}
            title="远训"
            description="提交白名单 SSH/GPU 训练节点任务，保留审批与输出记录。"
            status={sshServers.length > 0 ? `${sshServers.length} 台服务器` : "待检查"}
            onOpen={() => setActiveDrawer("ssh-training")}
          />
          <ToolActionRow
            icon={CalendarClock}
            title="复核"
            description="创建周期性复核，触发时只生成待办，不自动执行外部工具。"
            status={`${schedules.length} 个计划`}
            onOpen={() => setActiveDrawer("schedules")}
          />
          <ToolActionRow
            icon={UsersRound}
            title="审查"
            description="计划文献支撑、反证和可证伪性等并行审查角色。"
            status={`${delegations.length} 个计划`}
            onOpen={() => setActiveDrawer("delegations")}
          />
        </div>
      </section>

      <details className="tool-catalog-disclosure">
        <summary>
          <span>
            <SlidersHorizontal size={16} />
            浏览工具目录
          </span>
          <small>按需查找入口；默认优先使用上方控制台和执行队列。</small>
        </summary>
        <section className="command-center">
          <label className="command-input" htmlFor="tool-search">
            <Search size={18} />
            <input
              id="tool-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索工具、研究流程或数据动作"
            />
          </label>
          <div className="segmented-control" role="tablist" aria-label="工具分类">
            {toolCategories.map((item) => (
              <button
                className={classNames(activeCategory === item && "selected")}
                key={item}
                type="button"
                role="tab"
                aria-selected={activeCategory === item}
                onClick={() => setCategory(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </section>

        <div className="tool-grid">
          {filteredTools.map((tool) => {
            const Icon = tool.icon;
            const blockedByLiterature = tool.category === "文献" && !literatureReady;
            return (
              <Link className={classNames("tool-card", blockedByLiterature && "warning")} to={tool.route} key={tool.title}>
                <div className="tool-icon">
                  <Icon size={18} />
                </div>
                <div className="tool-copy">
                  <div className="card-meta-row">
                    <span>{tool.category}</span>
                    <span className={classNames("status-pill", blockedByLiterature ? "warning" : "ok")}>
                      {tool.title === "论文解析"
                        ? parseRunCount > 0
                          ? `${parseRunCount} 次解析 / ${paperCount} 篇入库`
                          : "等待首篇论文"
                        : blockedByLiterature
                          ? "需检查文献服务"
                          : tool.status}
                    </span>
                  </div>
                  <h2>{tool.title}</h2>
                  <p>{tool.description}</p>
                </div>
                <ArrowRight size={16} />
              </Link>
            );
          })}
        </div>
      </details>

      {activeDrawer && activeDrawerMeta ? (
        <div className="drawer-backdrop" onClick={() => setActiveDrawer(null)} role="presentation">
          <aside
            className="reference-drawer tool-action-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tool-action-drawer-title"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="drawer-header">
              <div>
                <span>{activeDrawerMeta.kicker}</span>
                <h2 id="tool-action-drawer-title">{activeDrawerMeta.title}</h2>
                <p>{activeDrawerMeta.description}</p>
              </div>
              <button className="drawer-close" type="button" onClick={() => setActiveDrawer(null)} aria-label="关闭工具面板">
                <X size={18} />
              </button>
            </header>

            <div className="tool-drawer-body">
              {activeDrawer === "skills" ? <ResearchSkillPanel skills={skills} /> : null}
              {activeDrawer === "command-permissions" ? (
                <CommandPermissionPanel
                  canViewAdmin={canViewAdmin}
                  commandPermission={commandPermission}
                  activeMode={activeCommandPermissionMode}
                  permissionStatus={permissionStatus}
                  permissionError={permissionError}
                  onChangeMode={(mode) => void handleCommandPermissionMode(mode)}
                />
              ) : null}
              {activeDrawer === "terminal-command" ? (
                <TerminalCommandPanel
                  canViewAdmin={canViewAdmin}
                  terminalWorkdir={terminalWorkdir}
                  terminalCommand={terminalCommand}
                  terminalTimeout={terminalTimeout}
                  terminalReason={terminalReason}
                  terminalApproved={terminalApproved}
                  terminalNeedsApproval={terminalNeedsApproval}
                  terminalStatus={terminalStatus}
                  terminalError={terminalError}
                  terminalResult={terminalResult}
                  onWorkdirChange={setTerminalWorkdir}
                  onCommandChange={setTerminalCommand}
                  onTimeoutChange={setTerminalTimeout}
                  onReasonChange={setTerminalReason}
                  onApprovedChange={setTerminalApproved}
                  onSubmit={(event) => void handleTerminalCommand(event)}
                />
              ) : null}
              {activeDrawer === "ssh-training" ? (
                <SshTrainingPanel
                  sshServers={sshServers}
                  selectedServerId={sshServerId}
                  sshAvailability={sshAvailability}
                  sshWorkdir={sshWorkdir}
                  sshCommand={sshCommand}
                  sshTimeout={sshTimeout}
                  sshReason={sshReason}
                  sshApproved={sshApproved}
                  sshNeedsApproval={sshNeedsApproval}
                  sshStatus={sshStatus}
                  sshError={sshError}
                  sshResult={sshResult}
                  activeCommandPermissionMode={activeCommandPermissionMode}
                  onServerChange={setSshServerId}
                  onWorkdirChange={setSshWorkdir}
                  onCommandChange={setSshCommand}
                  onTimeoutChange={setSshTimeout}
                  onReasonChange={setSshReason}
                  onApprovedChange={setSshApproved}
                  onSubmit={(event) => void handleSshTraining(event)}
                />
              ) : null}
              {activeDrawer === "schedules" ? (
                <SchedulePlanner
                  schedules={schedules}
                  title={scheduleTitle}
                  workflow={scheduleWorkflow}
                  interval={scheduleInterval}
                  status={scheduleStatus}
                  error={scheduleError}
                  tickStatusById={tickStatusById}
                  onTitleChange={setScheduleTitle}
                  onWorkflowChange={setScheduleWorkflow}
                  onIntervalChange={setScheduleInterval}
                  onSubmit={(event) => void handleCreateSchedule(event)}
                  onTick={(schedule) => void handleTickSchedule(schedule)}
                />
              ) : null}
              {activeDrawer === "delegations" ? (
                <DelegationPlanner
                  delegations={delegations}
                  title={delegationTitle}
                  status={delegationStatus}
                  error={delegationError}
                  onTitleChange={setDelegationTitle}
                  onSubmit={(event) => void handleCreateDelegation(event)}
                />
              ) : null}
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}

function WorkflowCardHeader({
  icon: Icon,
  title,
  description,
  status,
}: {
  icon: typeof Search;
  title: string;
  description: string;
  status: "idle" | "loading" | "success" | "error";
}) {
  return (
    <header className="workflow-tool-header">
      <div className="tool-icon">
        {status === "loading" ? <Loader2 size={18} className="spin" /> : <Icon size={18} />}
      </div>
      <div>
        <div className="card-meta-row">
          <span>研究任务流程</span>
          <span className={classNames("status-pill", statusTone(status))}>
            {status === "loading" ? "运行中" : status === "success" ? "已完成" : status === "error" ? "需处理" : "待执行"}
          </span>
        </div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
    </header>
  );
}

function WorkflowFeedback({
  status,
  error,
  success,
}: {
  status: "idle" | "loading" | "success" | "error";
  error: string;
  success: string;
}) {
  if (status === "idle" || status === "loading") return null;
  if (status === "error") return <article className="status-banner error" role="alert">{error}</article>;
  return <article className="status-banner ok" role="status">{success}</article>;
}

function ToolActionRow({
  icon: Icon,
  title,
  description,
  status,
  onOpen,
}: {
  icon: typeof Search;
  title: string;
  description: string;
  status: string;
  onOpen: () => void;
}) {
  return (
    <button className="tool-compact-row" type="button" onClick={onOpen}>
      <span className="tool-icon">
        <Icon size={18} />
      </span>
      <span className="tool-compact-copy">
        <strong>{title}</strong>
        <span>{description}</span>
      </span>
      <span className="status-pill neutral">{status}</span>
      <ArrowRight size={16} />
    </button>
  );
}

function SessionResultList({ results }: { results: SessionSearchResult[] }) {
  return (
    <div className="tool-result-list">
      {results.map((result) => (
        <article className="tool-result-card" key={`${result.type}-${result.id}`}>
          <header>
            <div>
              <span>{searchTypeLabels[result.type] ?? result.type}</span>
              <strong>{result.title}</strong>
            </div>
            <span className={classNames("status-pill", statusTone(result.status))}>{formatStatusLabel(result.status)}</span>
          </header>
          {result.snippet ? <p>{result.snippet}</p> : <p>该记录没有可展示摘要，可在详情中回到对应研究对象。</p>}
          <details className="expert-summary">
            <summary>查看定位信息</summary>
            <span>{targetSummary(result.target_ref) || result.id}</span>
          </details>
        </article>
      ))}
    </div>
  );
}

function ResearchSkillPanel({ skills }: { skills: ResearchSkill[] }) {
  return (
    <section className="reference-section">
      {skills.length === 0 ? <p className="drawer-note">暂无可用方法模板。</p> : null}
      <div className="tool-mini-list">
        {skills.map((skill) => (
          <div className="tool-mini-row" key={skill.skill_id}>
            <span className="status-pill ok">{skill.phases.length} 个适用阶段</span>
            <div>
              <strong>{skill.title}</strong>
              <p>{skill.purpose}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function CommandPermissionPanel({
  canViewAdmin,
  commandPermission,
  activeMode,
  permissionStatus,
  permissionError,
  onChangeMode,
}: {
  canViewAdmin: boolean;
  commandPermission: CommandPermissionPolicy | null;
  activeMode: CommandPermissionMode;
  permissionStatus: "idle" | "loading" | "success" | "error";
  permissionError: string;
  onChangeMode: (mode: CommandPermissionMode) => void;
}) {
  const fallbackModes = [
    {
      mode: "request_approval" as CommandPermissionMode,
      label: "请求批准",
      description: "每次命令都要求确认。",
      approval_policy: "always",
    },
    {
      mode: "approve_safe" as CommandPermissionMode,
      label: "替我审批",
      description: "安全命令自动批准。",
      approval_policy: "safe_commands_only",
    },
    {
      mode: "full_access" as CommandPermissionMode,
      label: "完全访问权限",
      description: "允许命令免确认执行。",
      approval_policy: "no_prompt_for_allowed_commands",
    },
  ];
  return (
    <section className="reference-section">
      <div className="remote-server-strip" aria-label="AI 命令权限模式">
        {(commandPermission?.modes ?? fallbackModes).map((mode) => (
          <button
            className={classNames("status-pill", mode.mode === activeMode ? "ok" : "neutral")}
            disabled={!canViewAdmin || permissionStatus === "loading"}
            key={mode.mode}
            onClick={() => onChangeMode(mode.mode)}
            title={mode.description}
            type="button"
          >
            {mode.label}
          </button>
        ))}
      </div>
      <p className="drawer-note">
        当前模式：{commandPermissionLabel(activeMode)}。危险命令仍会被后端 guardrail 拦截，所有执行都会写入工具结果和后台任务审计。
      </p>
      {!canViewAdmin ? <p className="drawer-note">只有管理员可以修改命令权限模式。</p> : null}
      <WorkflowFeedback
        status={permissionStatus}
        error={permissionError}
        success={`命令权限已切换为 ${commandPermissionLabel(activeMode)}。`}
      />
    </section>
  );
}

function TerminalCommandPanel({
  canViewAdmin,
  terminalWorkdir,
  terminalCommand,
  terminalTimeout,
  terminalReason,
  terminalApproved,
  terminalNeedsApproval,
  terminalStatus,
  terminalError,
  terminalResult,
  onWorkdirChange,
  onCommandChange,
  onTimeoutChange,
  onReasonChange,
  onApprovedChange,
  onSubmit,
}: {
  canViewAdmin: boolean;
  terminalWorkdir: string;
  terminalCommand: string;
  terminalTimeout: number;
  terminalReason: string;
  terminalApproved: boolean;
  terminalNeedsApproval: boolean;
  terminalStatus: "idle" | "loading" | "success" | "error";
  terminalError: string;
  terminalResult: TerminalCommandJobResponse | null;
  onWorkdirChange: (value: string) => void;
  onCommandChange: (value: string) => void;
  onTimeoutChange: (value: number) => void;
  onReasonChange: (value: string) => void;
  onApprovedChange: (value: boolean) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  if (!canViewAdmin) {
    return <p className="drawer-note">本地命令任务仅管理员可提交。普通研究员可以继续使用证据采集、网页抽取和远程训练入口。</p>;
  }
  return (
    <section className="reference-section">
      <form className="tool-form-stack" onSubmit={onSubmit}>
        <label className="field-stack" htmlFor="terminal-command-workdir">
          <span>本地工作目录</span>
          <input
            id="terminal-command-workdir"
            type="text"
            value={terminalWorkdir}
            onChange={(event) => onWorkdirChange(event.target.value)}
            placeholder="可留空，默认项目根目录；完全访问模式可使用其他目录"
            disabled={terminalStatus === "loading"}
          />
        </label>
        <label className="field-stack" htmlFor="terminal-command-text">
          <span>本地命令</span>
          <textarea
            id="terminal-command-text"
            value={terminalCommand}
            onChange={(event) => onCommandChange(event.target.value)}
            rows={4}
            placeholder="例如 git status --short"
            aria-invalid={terminalStatus === "error"}
            disabled={terminalStatus === "loading"}
          />
        </label>
        <div className="tool-inline-fields">
          <label className="field-stack" htmlFor="terminal-command-timeout">
            <span>超时秒数</span>
            <input
              id="terminal-command-timeout"
              type="number"
              min={1}
              max={3600}
              value={terminalTimeout}
              onChange={(event) => onTimeoutChange(Number(event.target.value) || 120)}
              disabled={terminalStatus === "loading"}
            />
          </label>
          <label className="field-stack" htmlFor="terminal-command-reason">
            <span>执行理由</span>
            <input
              id="terminal-command-reason"
              type="text"
              value={terminalReason}
              onChange={(event) => onReasonChange(event.target.value)}
              disabled={terminalStatus === "loading"}
            />
          </label>
        </div>
        <label className="tool-approval-row">
          <input
            type="checkbox"
            checked={terminalApproved}
            onChange={(event) => onApprovedChange(event.target.checked)}
            disabled={terminalStatus === "loading" || !terminalNeedsApproval}
          />
          <span>
            {terminalNeedsApproval
              ? "确认在本机执行该命令，并把结果写入审计记录。"
              : "当前权限模式允许该命令免确认提交，后端仍会记录审计结果。"}
          </span>
        </label>
        <button
          className={classNames("button-primary", terminalStatus === "loading" && "is-loading")}
          type="submit"
          disabled={!terminalCommand.trim() || (terminalNeedsApproval && !terminalApproved) || terminalStatus === "loading"}
          aria-busy={terminalStatus === "loading"}
        >
          {terminalStatus === "loading" ? "正在提交命令" : "提交本地命令"}
        </button>
      </form>
      <WorkflowFeedback
        status={terminalStatus}
        error={terminalError}
        success={terminalResult ? "本地命令已进入后台队列；执行结果会写入审计记录和工具结果。" : "本地命令已提交。"}
      />
      {terminalResult ? <CommandJobPreview result={terminalResult} title="本地命令任务" /> : null}
    </section>
  );
}

function FileSnapshotPreview({ result }: { result: FileSnapshotResponse }) {
  return (
    <article className="tool-result-card">
      <header>
        <div>
          <span>{formatBackendText(result.file_result.source_reliability)}</span>
          <strong>{compactPathName(result.file_result.relative_path)}</strong>
        </div>
        <span className="status-pill ok">{result.file_result.line_count} 行</span>
      </header>
      {result.file_result.text_preview ? <p>{result.file_result.text_preview}</p> : null}
      <details className="expert-summary">
        <summary>查看证据文件</summary>
        <dl className="tool-detail-list">
          <div>
            <dt>来源文件</dt>
            <dd>{result.file_result.relative_path}</dd>
          </div>
          <div>
            <dt>内容哈希</dt>
            <dd>{result.file_result.content_sha256}</dd>
          </div>
          <div>
            <dt>快照文件</dt>
            <dd>{result.file_result.snapshot_path}</dd>
          </div>
          <div>
            <dt>采集时间</dt>
            <dd>{formatTime(result.file_result.captured_at)}</dd>
          </div>
        </dl>
      </details>
    </article>
  );
}

function WebExtractPreview({ result }: { result: WebExtractResponse }) {
  return (
    <article className="tool-result-card">
      <header>
        <div>
          <span>{formatBackendText(result.web_result.source_reliability)}</span>
          <strong>{webSourceTitle(result.web_result.title, result.web_result.final_url)}</strong>
        </div>
        <span className="status-pill ok">{result.web_result.captured_text_char_count} 字符</span>
      </header>
      {result.web_result.text_preview ? <p>{result.web_result.text_preview}</p> : null}
      <footer className="tool-card-footer">
        <span>{result.web_result.pdf_links.length} 个 PDF 线索</span>
        <span>{result.web_result.supplementary_links.length} 个补充材料线索</span>
        {result.web_result.knowledge_base_paper_id ? <span>已入库</span> : <span>未入库</span>}
      </footer>
      <details className="expert-summary">
        <summary>查看证据文件</summary>
        <dl className="tool-detail-list">
          <div>
            <dt>最终 URL</dt>
            <dd>{result.web_result.final_url}</dd>
          </div>
          <div>
            <dt>内容哈希</dt>
            <dd>{result.web_result.content_hash}</dd>
          </div>
          <div>
            <dt>快照文件</dt>
            <dd>{result.web_result.snapshot_path}</dd>
          </div>
        </dl>
      </details>
    </article>
  );
}

function RemoteServerStrip({
  servers,
  selectedServerId,
}: {
  servers: SshTrainingServer[];
  selectedServerId: string;
}) {
  if (servers.length === 0) {
    return (
      <article className="status-banner warning" role="status">
        暂未读取到白名单训练服务器。请稍后刷新工具状态。
      </article>
    );
  }
  return (
    <div className="remote-server-strip" aria-label="白名单训练服务器">
      {servers.map((server) => (
        <span
          className={classNames("status-pill", server.server_id === selectedServerId ? "ok" : "neutral")}
          key={server.server_id}
          title={server.gpu_summary}
        >
          {server.display_name}
        </span>
      ))}
    </div>
  );
}

function SshTrainingPanel({
  sshServers,
  selectedServerId,
  sshAvailability,
  sshWorkdir,
  sshCommand,
  sshTimeout,
  sshReason,
  sshApproved,
  sshNeedsApproval,
  sshStatus,
  sshError,
  sshResult,
  activeCommandPermissionMode,
  onServerChange,
  onWorkdirChange,
  onCommandChange,
  onTimeoutChange,
  onReasonChange,
  onApprovedChange,
  onSubmit,
}: {
  sshServers: SshTrainingServer[];
  selectedServerId: string;
  sshAvailability: Record<string, unknown> | null;
  sshWorkdir: string;
  sshCommand: string;
  sshTimeout: number;
  sshReason: string;
  sshApproved: boolean;
  sshNeedsApproval: boolean;
  sshStatus: "idle" | "loading" | "success" | "error";
  sshError: string;
  sshResult: SshTrainingJobResponse | null;
  activeCommandPermissionMode: CommandPermissionMode;
  onServerChange: (value: string) => void;
  onWorkdirChange: (value: string) => void;
  onCommandChange: (value: string) => void;
  onTimeoutChange: (value: number) => void;
  onReasonChange: (value: string) => void;
  onApprovedChange: (value: boolean) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="reference-section">
      <RemoteServerStrip servers={sshServers} selectedServerId={selectedServerId} />
      <form className="tool-form-stack" onSubmit={onSubmit}>
        <label className="field-stack" htmlFor="ssh-training-server">
          <span>训练服务器</span>
          <select
            id="ssh-training-server"
            value={selectedServerId}
            onChange={(event) => onServerChange(event.target.value)}
            disabled={sshStatus === "loading" || sshServers.length === 0}
          >
            {sshServers.length === 0 ? <option value="">暂无可用服务器</option> : null}
            {sshServers.map((server) => (
              <option value={server.server_id} key={server.server_id}>
                {server.display_name} · {server.gpu_summary}
              </option>
            ))}
          </select>
        </label>
        <label className="field-stack" htmlFor="ssh-training-workdir">
          <span>远程工作目录</span>
          <input
            id="ssh-training-workdir"
            type="text"
            value={sshWorkdir}
            onChange={(event) => onWorkdirChange(event.target.value)}
            placeholder="可留空，或填写远端项目目录"
            disabled={sshStatus === "loading"}
          />
        </label>
        <label className="field-stack" htmlFor="ssh-training-command">
          <span>远程命令</span>
          <textarea
            id="ssh-training-command"
            value={sshCommand}
            onChange={(event) => onCommandChange(event.target.value)}
            rows={4}
            placeholder="例如 nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"
            aria-invalid={sshStatus === "error"}
            disabled={sshStatus === "loading"}
          />
        </label>
        <div className="tool-inline-fields">
          <label className="field-stack" htmlFor="ssh-training-timeout">
            <span>超时秒数</span>
            <input
              id="ssh-training-timeout"
              type="number"
              min={1}
              max={86400}
              value={sshTimeout}
              onChange={(event) => onTimeoutChange(Number(event.target.value) || 120)}
              disabled={sshStatus === "loading"}
            />
          </label>
          <label className="field-stack" htmlFor="ssh-approval-reason">
            <span>执行理由</span>
            <input
              id="ssh-approval-reason"
              type="text"
              value={sshReason}
              onChange={(event) => onReasonChange(event.target.value)}
              disabled={sshStatus === "loading"}
            />
          </label>
        </div>
        <label className="tool-approval-row">
          <input
            type="checkbox"
            checked={sshApproved}
            onChange={(event) => onApprovedChange(event.target.checked)}
            disabled={sshStatus === "loading" || !sshNeedsApproval}
          />
          <span>
            {sshNeedsApproval
              ? "确认只在所选白名单服务器执行该命令，并把结果写入本地审计记录。"
              : "当前权限模式允许该远程命令免确认提交，后端仍会执行 guardrail 和审计记录。"}
          </span>
        </label>
        <button
          className={classNames("button-primary", sshStatus === "loading" && "is-loading")}
          type="submit"
          disabled={!selectedServerId || !sshCommand.trim() || (sshNeedsApproval && !sshApproved) || sshStatus === "loading" || sshServers.length === 0}
          aria-busy={sshStatus === "loading"}
        >
          {sshStatus === "loading" ? "正在提交任务" : "提交远程任务"}
        </button>
      </form>
      <p className="tool-muted-copy">当前命令权限：{commandPermissionLabel(activeCommandPermissionMode)}。</p>
      <WorkflowFeedback
        status={sshStatus}
        error={sshError}
        success={sshResult ? "远程任务已进入后台队列；执行结果会写入审计记录和工具结果。" : "远程任务已提交。"}
      />
      {sshResult ? <SshTrainingPreview result={sshResult} /> : null}
      {sshAvailability ? (
        <details className="expert-summary">
          <summary>查看远程执行边界</summary>
          <span>{formatSshAvailability(sshAvailability)}</span>
        </details>
      ) : null}
    </section>
  );
}

function SshTrainingPreview({ result }: { result: SshTrainingJobResponse }) {
  const serverId = typeof result.job.arguments?.server_id === "string" ? result.job.arguments.server_id : "所选服务器";
  const timeoutSeconds = typeof result.job.arguments?.timeout_seconds === "number" ? result.job.arguments.timeout_seconds : null;
  return (
    <article className="tool-result-card">
      <header>
        <div>
          <span>后台训练任务</span>
          <strong>{serverId}</strong>
        </div>
        <span className={classNames("status-pill", statusTone(result.job.status))}>{formatStatusLabel(result.job.status)}</span>
      </header>
      <p>命令已通过审批边界提交。系统会保存标准输出、错误输出和执行清单，默认页面只展示任务摘要。</p>
      <footer className="tool-card-footer">
        <span>{formatWorkflowName(result.phase)}</span>
        {timeoutSeconds ? <span>{timeoutSeconds} 秒超时</span> : null}
        <span>本地审计记录</span>
      </footer>
      <details className="expert-summary">
        <summary>查看任务定位</summary>
        <dl className="tool-detail-list">
          <div>
            <dt>后台任务</dt>
            <dd>{result.job.job_id}</dd>
          </div>
          <div>
            <dt>执行阶段</dt>
            <dd>{formatWorkflowName(result.phase)}</dd>
          </div>
          <div>
            <dt>审批范围</dt>
            <dd>{result.approval.scope}</dd>
          </div>
        </dl>
      </details>
    </article>
  );
}

function CommandJobPreview({
  result,
  title,
}: {
  result: TerminalCommandJobResponse | SshTrainingJobResponse;
  title: string;
}) {
  const command = typeof result.job.arguments?.command === "string" ? result.job.arguments.command : "已提交命令";
  const timeoutSeconds = typeof result.job.arguments?.timeout_seconds === "number" ? result.job.arguments.timeout_seconds : null;
  const mode =
    result.permission_policy?.label ??
    (typeof result.job.arguments?.permission_mode === "string" ? commandPermissionLabel(result.job.arguments.permission_mode as CommandPermissionMode) : "权限门控");
  return (
    <article className="tool-result-card">
      <header>
        <div>
          <span>{title}</span>
          <strong>{mode}</strong>
        </div>
        <span className={classNames("status-pill", statusTone(result.job.status))}>{formatStatusLabel(result.job.status)}</span>
      </header>
      <p>{command}</p>
      <footer className="tool-card-footer">
        <span>{formatWorkflowName(result.phase)}</span>
        {timeoutSeconds ? <span>{timeoutSeconds} 秒超时</span> : null}
        <span>{result.approval.granted_by === "command_permission_mode" ? "自动批准" : "显式确认"}</span>
      </footer>
      <details className="expert-summary">
        <summary>查看任务定位</summary>
        <dl className="tool-detail-list">
          <div>
            <dt>后台任务</dt>
            <dd>{result.job.job_id}</dd>
          </div>
          <div>
            <dt>审批范围</dt>
            <dd>{result.approval.scope}</dd>
          </div>
          <div>
            <dt>风险等级</dt>
            <dd>{typeof result.command_risk?.risk_level === "string" ? result.command_risk.risk_level : "已分类"}</dd>
          </div>
        </dl>
      </details>
    </article>
  );
}

function SchedulePlanner({
  schedules,
  title,
  workflow,
  interval,
  status,
  error,
  tickStatusById,
  onTitleChange,
  onWorkflowChange,
  onIntervalChange,
  onSubmit,
  onTick,
}: {
  schedules: ResearchSchedule[];
  title: string;
  workflow: string;
  interval: number;
  status: "idle" | "loading" | "success" | "error";
  error: string;
  tickStatusById: Record<string, "idle" | "loading" | "success" | "error">;
  onTitleChange: (value: string) => void;
  onWorkflowChange: (value: string) => void;
  onIntervalChange: (value: number) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onTick: (schedule: ResearchSchedule) => void;
}) {
  return (
    <section className="reference-section">
      <form className="tool-form-stack" onSubmit={onSubmit}>
        <label className="field-stack" htmlFor="schedule-title">
          <span>计划名称</span>
          <input id="schedule-title" type="text" value={title} onChange={(event) => onTitleChange(event.target.value)} />
        </label>
        <div className="tool-inline-fields">
          <label className="field-stack" htmlFor="schedule-workflow">
            <span>研究任务流程</span>
            <input
              id="schedule-workflow"
              type="text"
              value={workflow}
              onChange={(event) => onWorkflowChange(event.target.value)}
            />
          </label>
          <label className="field-stack" htmlFor="schedule-interval">
            <span>间隔小时</span>
            <input
              id="schedule-interval"
              type="number"
              min={1}
              value={interval}
              onChange={(event) => onIntervalChange(Number(event.target.value) || 24)}
            />
          </label>
        </div>
        <button
          className={classNames("button-secondary", status === "loading" && "is-loading")}
          type="submit"
          disabled={!title.trim() || !workflow.trim() || status === "loading"}
          aria-busy={status === "loading"}
        >
          {status === "loading" ? "正在创建" : "创建计划"}
        </button>
      </form>
      <WorkflowFeedback
        status={status}
        error={error}
        success="计划已保存；触发时只生成待办任务，不直接执行外部工具。"
      />
      <div className="tool-mini-list">
        {schedules.length === 0 ? <p className="inline-empty">暂无定期计划。</p> : null}
        {schedules.slice(0, 6).map((schedule) => {
          const tickStatus = tickStatusById[schedule.schedule_id] ?? "idle";
          return (
            <div className="tool-mini-row" key={schedule.schedule_id}>
              <span className={classNames("status-pill", statusTone(schedule.status))}>{formatStatusLabel(schedule.status)}</span>
              <div>
                <strong>{schedule.title}</strong>
                <p>
                  {formatWorkflowName(schedule.workflow_name)} · 下次 {formatTime(schedule.next_run_at)}
                </p>
              </div>
              <button
                className={classNames("button-secondary", tickStatus === "loading" && "is-loading")}
                type="button"
                onClick={() => onTick(schedule)}
                disabled={tickStatus === "loading" || schedule.status !== "active"}
                aria-busy={tickStatus === "loading"}
              >
                {tickStatus === "loading" ? "生成中" : "生成待办"}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function DelegationPlanner({
  delegations,
  title,
  status,
  error,
  onTitleChange,
  onSubmit,
}: {
  delegations: ResearchDelegation[];
  title: string;
  status: "idle" | "loading" | "success" | "error";
  error: string;
  onTitleChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="reference-section">
      <form className="tool-form-stack" onSubmit={onSubmit}>
        <label className="field-stack" htmlFor="delegation-title">
          <span>审查标题</span>
          <input id="delegation-title" type="text" value={title} onChange={(event) => onTitleChange(event.target.value)} />
        </label>
        <button
          className={classNames("button-secondary", status === "loading" && "is-loading")}
          type="submit"
          disabled={!title.trim() || status === "loading"}
          aria-busy={status === "loading"}
        >
          {status === "loading" ? "正在创建" : "创建审查计划"}
        </button>
      </form>
      <WorkflowFeedback status={status} error={error} success="已创建多角色审查计划；真正运行仍需执行前确认和模型通道检查。" />
      <div className="tool-mini-list">
        {delegations.length === 0 ? <p className="inline-empty">暂无多角色审查计划。</p> : null}
        {delegations.slice(0, 6).map((delegation) => (
          <div className="tool-mini-row" key={delegation.delegation_id}>
            <span className={classNames("status-pill", statusTone(delegation.status))}>{formatStatusLabel(delegation.status)}</span>
            <div>
              <strong>{delegation.title}</strong>
              <p>
                {formatDelegationStrategy(delegation.strategy)} · {delegation.agents.length} 个审查角色
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function OperationList({
  title,
  icon: Icon,
  items,
  empty,
}: {
  title: string;
  icon: typeof ClipboardCheck;
  items: ResearchTask[];
  empty: string;
}) {
  return (
    <article className="tool-operations-card">
      <header>
        <div className="tool-icon">
          <Icon size={18} />
        </div>
        <div>
          <span className="section-kicker">任务队列</span>
          <h3>{title}</h3>
        </div>
      </header>
      {items.length === 0 ? <p className="inline-empty">{empty}</p> : null}
      <div className="tool-mini-list">
        {items.slice(0, 4).map((item) => (
          <div className="tool-mini-row" key={item.task_id}>
            <span className={classNames("status-pill", statusTone(item.status))}>{formatStatusLabel(item.status)}</span>
            <div>
              <strong>{formatBackendText(item.title)}</strong>
              <p>{formatWorkflowName(item.phase || item.task_type)}</p>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

function BackgroundJobList({ jobs }: { jobs: BackgroundJob[] }) {
  return (
    <article className="tool-operations-card">
      <header>
        <div className="tool-icon">
          <Clock3 size={18} />
        </div>
        <div>
          <span className="section-kicker">后台任务</span>
          <h3>后台证据任务</h3>
        </div>
      </header>
      {jobs.length === 0 ? <p className="inline-empty">暂无后台工具任务。</p> : null}
      <div className="tool-mini-list">
        {jobs.slice(0, 4).map((job) => (
          <div className="tool-mini-row" key={job.job_id}>
            <span className={classNames("status-pill", statusTone(job.status))}>{formatStatusLabel(job.status)}</span>
            <div>
              <strong>{formatWorkflowName(job.workflow_name)}</strong>
              <p>{job.error_message ? "任务需要检查，详情已保留在本地审计记录中。" : `${formatWorkflowName(job.phase)} · ${formatTime(job.updated_at)}`}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="tool-card-footer">
        <span>
          <Database size={14} /> 本地审计记录
        </span>
        <span>
          <ShieldCheck size={14} /> 执行前确认
        </span>
        {jobs.some((job) => job.status === "error") ? (
          <span>
            <AlertTriangle size={14} /> 有失败任务
          </span>
        ) : (
          <span>
            <CheckCircle2 size={14} /> 可审计
          </span>
        )}
      </div>
    </article>
  );
}
