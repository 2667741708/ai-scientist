import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { PlugZap, Square, TerminalSquare } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getApiBase } from "../../lib/api/client";
import { getSafeErrorMessage } from "../../lib/formatters/workbench";

type TerminalProfile = {
  id: string;
  label: string;
  command: string;
  args: string[];
  available: boolean;
  reason: string;
  platform: string;
};

type TerminalStatus = {
  available: boolean;
  mode: "unrestricted";
  platform: string;
  default_profile: string;
  profiles: TerminalProfile[];
  active_sessions: number;
};

type TerminalSessionResponse = {
  mode: "unrestricted";
  session: {
    session_id: string;
    profile_id: string;
    label: string;
    command: string;
    args: string[];
    cwd: string;
    created_at: number;
    mode: "unrestricted";
  };
  websocket_path: string;
};

export type WebTerminalPreset = {
  revision: number;
  sshTarget: string;
  remoteCwd?: string;
  tmuxSession?: string;
};

function websocketUrl(path: string) {
  const url = new URL(path, getApiBase());
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

async function fetchTerminalStatus() {
  const response = await fetch(`${getApiBase()}/api/web-terminal/status`);
  if (!response.ok) throw new Error(`web_terminal_status_failed_${response.status}`);
  return (await response.json()) as TerminalStatus;
}

async function createTerminalSession(request: {
  profile: string;
  cwd?: string | null;
  cols: number;
  rows: number;
  ssh_target?: string | null;
  ssh_remote_cwd?: string | null;
  ssh_tmux_session?: string | null;
}) {
  const response = await fetch(`${getApiBase()}/api/web-terminal/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `web_terminal_create_failed_${response.status}`);
  }
  return (await response.json()) as TerminalSessionResponse;
}

export function WebTerminalPanel({
  defaultCwd = "",
  preset,
}: {
  defaultCwd?: string;
  preset?: WebTerminalPreset | null;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const terminalRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const disposeDataRef = useRef<{ dispose: () => void } | null>(null);
  const [status, setStatus] = useState<TerminalStatus | null>(null);
  const [profile, setProfile] = useState("");
  const [cwd, setCwd] = useState(defaultCwd);
  const [sshTarget, setSshTarget] = useState("");
  const [sshRemoteCwd, setSshRemoteCwd] = useState("");
  const [sshTmuxSession, setSshTmuxSession] = useState("");
  const [sessionLabel, setSessionLabel] = useState("");
  const [terminalState, setTerminalState] = useState<"idle" | "connecting" | "open" | "closed" | "error">("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    let disposed = false;
    void fetchTerminalStatus()
      .then((next) => {
        if (disposed) return;
        setStatus(next);
        setProfile(next.default_profile);
      })
      .catch((exc) => {
        if (!disposed) setError(getSafeErrorMessage(exc, "Web terminal runtime is not available."));
      });
    return () => {
      disposed = true;
    };
  }, []);

  const selectedProfile = useMemo(
    () => status?.profiles.find((item) => item.id === profile) ?? null,
    [profile, status?.profiles],
  );

  useEffect(() => {
    if (!preset) return;
    setProfile("ssh");
    setSshTarget(preset.sshTarget);
    setSshRemoteCwd(preset.remoteCwd ?? "");
    setSshTmuxSession(preset.tmuxSession ?? "");
    const suffix = preset.tmuxSession ? `tmux:${preset.tmuxSession}` : preset.remoteCwd || preset.sshTarget;
    setSessionLabel(`已填入远程工作区 · ${suffix}`);
  }, [preset?.revision]);

  const fitTerminal = useCallback(() => {
    const terminal = terminalRef.current;
    const fit = fitRef.current;
    const socket = socketRef.current;
    if (!terminal || !fit) return;
    requestAnimationFrame(() => {
      fit.fit();
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "resize", cols: terminal.cols, rows: terminal.rows }));
      }
    });
  }, []);

  const cleanupTerminal = useCallback(() => {
    socketRef.current?.close();
    socketRef.current = null;
    disposeDataRef.current?.dispose();
    disposeDataRef.current = null;
    terminalRef.current?.dispose();
    terminalRef.current = null;
    fitRef.current = null;
  }, []);

  useEffect(() => {
    const onResize = () => fitTerminal();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [fitTerminal]);

  useEffect(() => () => cleanupTerminal(), [cleanupTerminal]);

  const startTerminal = useCallback(async () => {
    if (!hostRef.current || !selectedProfile) return;
    setError("");
    setTerminalState("connecting");
    cleanupTerminal();

    const terminal = new Terminal({
      cursorBlink: true,
      convertEol: true,
      fontFamily: "Cascadia Mono, Consolas, monospace",
      fontSize: 13,
      lineHeight: 1.18,
      scrollback: 8000,
      theme: {
        background: "#101418",
        foreground: "#edf1f5",
        cursor: "#ffffff",
        selectionBackground: "#37506b",
      },
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(hostRef.current);
    terminalRef.current = terminal;
    fitRef.current = fit;
    fit.fit();
    terminal.write("\r\n[opening unrestricted experiment terminal]\r\n");

    try {
      const created = await createTerminalSession({
        profile: selectedProfile.id,
        cwd: cwd.trim() || null,
        cols: terminal.cols,
        rows: terminal.rows,
        ssh_target: selectedProfile.id === "ssh" ? sshTarget.trim() : null,
        ssh_remote_cwd: selectedProfile.id === "ssh" ? sshRemoteCwd.trim() || null : null,
        ssh_tmux_session: selectedProfile.id === "ssh" ? sshTmuxSession.trim() || null : null,
      });
      setSessionLabel(`${created.session.label} · ${created.session.cwd}`);
      const socket = new WebSocket(websocketUrl(created.websocket_path));
      socketRef.current = socket;
      socket.onopen = () => {
        setTerminalState("open");
        fitTerminal();
      };
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(String(event.data));
          if (payload.type === "output") terminal.write(String(payload.data || ""));
          if (payload.type === "ready") terminal.write(`[connected: ${payload.session?.label ?? "terminal"}]\r\n`);
          if (payload.type === "error") terminal.write(`\r\n[terminal error: ${payload.message || "unknown"}]\r\n`);
          if (payload.type === "exit") {
            terminal.write("\r\n[terminal exited]\r\n");
            setTerminalState("closed");
          }
        } catch {
          terminal.write(String(event.data));
        }
      };
      socket.onerror = () => {
        setTerminalState("error");
        setError("Web terminal socket failed.");
      };
      socket.onclose = () => {
        setTerminalState((current) => (current === "open" || current === "connecting" ? "closed" : current));
      };
      disposeDataRef.current = terminal.onData((data) => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "input", data }));
        }
      });
    } catch (exc) {
      setTerminalState("error");
      setError(getSafeErrorMessage(exc, "Terminal session could not be created."));
      terminal.write(`\r\n[failed: ${getSafeErrorMessage(exc, "terminal create failed")}]\r\n`);
    }
  }, [cleanupTerminal, cwd, fitTerminal, selectedProfile, sshRemoteCwd, sshTarget, sshTmuxSession]);

  const stopTerminal = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: "close" }));
    }
    cleanupTerminal();
    setTerminalState("closed");
    setSessionLabel("");
  }, [cleanupTerminal]);

  const canStart = Boolean(selectedProfile?.available) && terminalState !== "connecting" && (selectedProfile?.id !== "ssh" || sshTarget.trim());

  return (
    <section className="experiment-terminal-panel" aria-label="实验终端">
      <header className="experiment-terminal-header">
        <div>
          <span>实验终端</span>
          <h2>像进入服务器本地一样执行命令</h2>
          <p>第一版使用 unrestricted mode：浏览器输入会直接进入后端机器上的真实 PTY 终端。</p>
        </div>
        <div className="experiment-terminal-actions">
          <button className="button-secondary" type="button" onClick={startTerminal} disabled={!canStart}>
            <TerminalSquare size={16} />
            {terminalState === "connecting" ? "连接中" : "打开终端"}
          </button>
          <button className="button-secondary" type="button" onClick={stopTerminal} disabled={terminalState !== "open"}>
            <Square size={15} />
            关闭
          </button>
        </div>
      </header>

      <div className="experiment-terminal-controls">
        <label className="field-stack">
          <span>终端类型</span>
          <select value={profile} onChange={(event) => setProfile(event.target.value)}>
            {(status?.profiles ?? []).map((item) => (
              <option key={item.id} value={item.id} disabled={!item.available}>
                {item.label}{item.available ? "" : " unavailable"}
              </option>
            ))}
          </select>
        </label>
        <label className="field-stack">
          <span>启动目录</span>
          <input value={cwd} onChange={(event) => setCwd(event.target.value)} placeholder="留空使用项目根目录，或输入任意已存在路径" />
        </label>
        {selectedProfile?.id === "ssh" ? (
          <>
            <label className="field-stack">
              <span>SSH 目标</span>
              <input value={sshTarget} onChange={(event) => setSshTarget(event.target.value)} placeholder="例如 c201-4090 或 user@10.20.22.77" />
            </label>
            <label className="field-stack">
              <span>远程目录</span>
              <input value={sshRemoteCwd} onChange={(event) => setSshRemoteCwd(event.target.value)} placeholder="例如 /home/user/project" />
            </label>
            <label className="field-stack">
              <span>tmux 会话</span>
              <input value={sshTmuxSession} onChange={(event) => setSshTmuxSession(event.target.value)} placeholder="留空进入普通远程 shell" />
            </label>
          </>
        ) : null}
      </div>

      <div className="experiment-terminal-status">
        <span className="status-chip warning">
          <PlugZap size={14} />
          unrestricted
        </span>
        <span>{selectedProfile ? `${selectedProfile.command} ${selectedProfile.args.join(" ")}` : "loading terminal profiles"}</span>
        {sessionLabel ? <span title={sessionLabel}>{sessionLabel}</span> : null}
      </div>
      {error ? <div className="status-banner warning">{error}</div> : null}
      <div className="experiment-terminal-host" ref={hostRef} />
    </section>
  );
}
