import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { ChevronDown, ChevronUp, ExternalLink, GripHorizontal, Plus, TerminalSquare, X } from "lucide-react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DesktopRuntimeStatus, DesktopTerminalSessionInfo } from "../../types/desktop";
import { classNames } from "../../lib/formatters/workbench";

type TerminalView = DesktopTerminalSessionInfo & {
  title: string;
  status: "running" | "exited";
  exitCode?: number;
};

type TerminalRuntime = {
  terminal: Terminal;
  fit: FitAddon;
  mounted: boolean;
};

const MIN_HEIGHT = 220;
const MAX_HEIGHT = 560;
const DEFAULT_HEIGHT = 320;

function hasDesktopBridge() {
  return typeof window !== "undefined" && Boolean(window.coscientist?.terminal);
}

function formatServiceState(status?: DesktopRuntimeStatus | null) {
  if (!status) return "desktop runtime";
  const api = status.services.api;
  const mcp = status.services.mcp;
  const web = status.services.web;
  return `API ${api?.state ?? "unknown"} · MCP ${mcp?.state ?? "unknown"} · Web ${web?.port ?? "-"} ${web?.state ?? "unknown"}`;
}

export function DesktopTerminalDock({
  onExpandedChange,
}: {
  onExpandedChange?: (expanded: boolean) => void;
}) {
  const bridgeAvailable = hasDesktopBridge();
  const [expanded, setExpanded] = useState(false);
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const [sessions, setSessions] = useState<TerminalView[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<DesktopRuntimeStatus | null>(null);
  const [workspaceRoot, setWorkspaceRoot] = useState("");
  const terminalRefs = useRef(new Map<string, TerminalRuntime>());
  const hostRefs = useRef(new Map<string, HTMLDivElement>());
  const pendingOutput = useRef(new Map<string, string[]>());

  const activeSession = useMemo(() => sessions.find((session) => session.id === activeId), [activeId, sessions]);

  useEffect(() => {
    onExpandedChange?.(expanded);
  }, [expanded, onExpandedChange]);

  useEffect(() => {
    if (!bridgeAvailable || !window.coscientist) return;

    let disposed = false;
    void window.coscientist.appInfo().then((info) => {
      if (!disposed) setWorkspaceRoot(info.workspaceRoot);
    });
    void window.coscientist.serviceStatus().then((status) => {
      if (!disposed) setRuntimeStatus(status);
    });
    const unsubscribeStatus = window.coscientist.onServiceStatus((status) => setRuntimeStatus(status));
    const unsubscribeData = window.coscientist.terminal.onData(({ id, data }) => {
      const runtime = terminalRefs.current.get(id);
      if (runtime) {
        runtime.terminal.write(data);
        return;
      }
      const buffered = pendingOutput.current.get(id) ?? [];
      buffered.push(data);
      pendingOutput.current.set(id, buffered);
    });
    const unsubscribeExit = window.coscientist.terminal.onExit(({ id, exitCode }) => {
      setSessions((current) => current.map((session) => (session.id === id ? { ...session, status: "exited", exitCode } : session)));
      const runtime = terminalRefs.current.get(id);
      runtime?.terminal.write(`\r\n[terminal exited with code ${exitCode}]\r\n`);
    });

    return () => {
      disposed = true;
      unsubscribeStatus();
      unsubscribeData();
      unsubscribeExit();
    };
  }, [bridgeAvailable]);

  const fitTerminal = useCallback((id: string) => {
    const runtime = terminalRefs.current.get(id);
    if (!runtime) return;
    requestAnimationFrame(() => {
      runtime.fit.fit();
      window.coscientist?.terminal.resize({ id, cols: runtime.terminal.cols, rows: runtime.terminal.rows });
    });
  }, []);

  const mountTerminal = useCallback((id: string, element: HTMLDivElement | null) => {
    if (!element) {
      hostRefs.current.delete(id);
      return;
    }
    hostRefs.current.set(id, element);
    const runtime = terminalRefs.current.get(id);
    if (!runtime || runtime.mounted) return;
    runtime.terminal.open(element);
    runtime.mounted = true;
    const buffered = pendingOutput.current.get(id);
    if (buffered) {
      for (const chunk of buffered) runtime.terminal.write(chunk);
      pendingOutput.current.delete(id);
    }
    fitTerminal(id);
    runtime.terminal.focus();
  }, [fitTerminal]);

  const createTerminal = useCallback(async () => {
    if (!window.coscientist) return;
    const term = new Terminal({
      cursorBlink: true,
      convertEol: true,
      fontFamily: "Cascadia Mono, Consolas, monospace",
      fontSize: 13,
      lineHeight: 1.18,
      scrollback: 4000,
      theme: {
        background: "#111315",
        foreground: "#e6e8eb",
        cursor: "#ffffff",
        selectionBackground: "#37506b",
      },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);

    const provisionalCols = activeId ? terminalRefs.current.get(activeId)?.terminal.cols : undefined;
    const provisionalRows = activeId ? terminalRefs.current.get(activeId)?.terminal.rows : undefined;
    const session = await window.coscientist.terminal.create({ cols: provisionalCols ?? 100, rows: provisionalRows ?? 24 });

    term.onData((data) => window.coscientist?.terminal.write({ id: session.id, data }));
    terminalRefs.current.set(session.id, { terminal: term, fit, mounted: false });
    setSessions((current) => [
      ...current,
      {
        ...session,
        title: `PowerShell ${current.length + 1}`,
        status: "running",
      },
    ]);
    setActiveId(session.id);
    setExpanded(true);
  }, [activeId]);

  const closeTerminal = useCallback((id: string) => {
    window.coscientist?.terminal.dispose({ id });
    const runtime = terminalRefs.current.get(id);
    runtime?.terminal.dispose();
    terminalRefs.current.delete(id);
    pendingOutput.current.delete(id);
    setSessions((current) => {
      const next = current.filter((session) => session.id !== id);
      if (activeId === id) {
        setActiveId(next.at(-1)?.id ?? null);
      }
      return next;
    });
  }, [activeId]);

  useEffect(() => {
    if (!expanded || sessions.length > 0 || !bridgeAvailable) return;
    void createTerminal();
  }, [bridgeAvailable, createTerminal, expanded, sessions.length]);

  useEffect(() => {
    if (!expanded || !activeId) return;
    fitTerminal(activeId);
  }, [activeId, expanded, fitTerminal, height]);

  useEffect(() => {
    const handleResize = () => {
      if (activeId) fitTerminal(activeId);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [activeId, fitTerminal]);

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const startY = event.clientY;
    const startHeight = height;
    const handleMove = (moveEvent: PointerEvent) => {
      const next = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, startHeight + startY - moveEvent.clientY));
      setHeight(next);
    };
    const handleUp = () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
      if (activeId) fitTerminal(activeId);
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
  };

  if (!bridgeAvailable) return null;

  return (
    <section
      className={classNames("desktop-terminal-dock", expanded ? "expanded" : "collapsed")}
      style={expanded ? { height } : undefined}
      aria-label="桌面终端"
    >
      {expanded ? (
        <div className="desktop-terminal-resize-handle" onPointerDown={startResize} aria-hidden="true">
          <GripHorizontal size={16} />
        </div>
      ) : null}
      <header className="desktop-terminal-header">
        <div className="desktop-terminal-tabs" role="tablist" aria-label="终端标签">
          {sessions.length === 0 ? (
            <button className="desktop-terminal-tab active" type="button" onClick={() => void createTerminal()}>
              <TerminalSquare size={15} />
              PowerShell
            </button>
          ) : (
            sessions.map((session) => (
              <button
                key={session.id}
                className={classNames("desktop-terminal-tab", session.id === activeId && "active", session.status === "exited" && "exited")}
                type="button"
                onClick={() => {
                  setActiveId(session.id);
                  setExpanded(true);
                }}
              >
                <TerminalSquare size={15} />
                <span>{session.title}</span>
                {session.status === "exited" ? <small>exit {session.exitCode}</small> : null}
              </button>
            ))
          )}
        </div>
        <div className="desktop-terminal-actions">
          <span title={workspaceRoot || undefined}>{formatServiceState(runtimeStatus)}</span>
          {runtimeStatus?.webUrl ? (
            <button className="icon-button" type="button" title="在系统浏览器打开工作台" onClick={() => void window.coscientist?.openExternal(runtimeStatus.webUrl)}>
              <ExternalLink size={15} />
            </button>
          ) : null}
          <button className="icon-button" type="button" title="新建 PowerShell" onClick={() => void createTerminal()}>
            <Plus size={15} />
          </button>
          <button className="icon-button" type="button" title={expanded ? "收起终端" : "展开终端"} onClick={() => setExpanded((value) => !value)}>
            {expanded ? <ChevronDown size={15} /> : <ChevronUp size={15} />}
          </button>
          {activeSession ? (
            <button className="icon-button" type="button" title="关闭当前终端" onClick={() => closeTerminal(activeSession.id)}>
              <X size={15} />
            </button>
          ) : null}
        </div>
      </header>
      {expanded ? (
        <>
          <div className="desktop-terminal-boundary">
            交互终端会以当前 Windows 用户权限执行真实本地命令；需要可审计确认的动作请继续使用 Tools/Chat 中的命令卡。
          </div>
          <div className="desktop-terminal-body">
            {sessions.map((session) => (
              <div
                key={session.id}
                ref={(element) => mountTerminal(session.id, element)}
                className={classNames("desktop-terminal-pane", session.id === activeId && "active")}
                aria-hidden={session.id !== activeId}
              />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
