import { FolderOpen, Import, Plus, RefreshCw, Server, TerminalSquare, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getApiBase } from "../../lib/api/client";
import { getSafeErrorMessage } from "../../lib/formatters/workbench";
import type { WebTerminalPreset } from "./WebTerminalPanel";

type RemoteProfile = {
  profile_id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  auth_type: "ssh_config" | "password" | "private_key" | "agent";
  ssh_config_alias?: string | null;
  ssh_target: string;
  private_key_path?: string | null;
  has_password: boolean;
  default_remote_path: string;
};

type SshConfigHost = {
  name: string;
  host: string;
  username: string;
  port: number;
  identity_file?: string;
  default_remote_path: string;
};

type RemoteEntry = {
  name: string;
  path: string;
  kind: "directory" | "file" | "symlink";
  is_directory: boolean;
  size: number;
  modified_time: number;
  permissions: string;
};

type ProjectRemoteRoot = {
  project_id: string;
  profile_id: string;
  profile: RemoteProfile;
  remote_path: string;
  label: string;
  updated_at: number;
};

type TmuxSession = {
  name: string;
  windows: number;
  created_at?: number | null;
  attached: boolean;
  current_path: string;
};

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    try {
      const payload = JSON.parse(text);
      const message = payload?.detail?.message || payload?.message;
      if (typeof message === "string" && message.trim()) {
        throw new Error(message.trim());
      }
    } catch (exc) {
      if (exc instanceof Error && exc.message && !exc.message.startsWith("Unexpected")) {
        throw exc;
      }
    }
    throw new Error(text || `request_failed_${response.status}`);
  }
  return (await response.json()) as T;
}

function parentPath(path: string) {
  if (!path || path === "/") return "/";
  const parts = path.split("/").filter(Boolean);
  parts.pop();
  return parts.length ? `/${parts.join("/")}` : "/";
}

function formatSessionTime(value?: number | null) {
  if (!value) return "";
  return new Date(value * 1000).toLocaleString();
}

export function RemoteWorkspacePanel({
  projectId,
  onTerminalPreset,
}: {
  projectId: string;
  onTerminalPreset: (preset: Omit<WebTerminalPreset, "revision">) => void;
}) {
  const [profiles, setProfiles] = useState<RemoteProfile[]>([]);
  const [sshHosts, setSshHosts] = useState<SshConfigHost[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [currentPath, setCurrentPath] = useState("/");
  const [entries, setEntries] = useState<RemoteEntry[]>([]);
  const [remoteRoot, setRemoteRoot] = useState<ProjectRemoteRoot | null>(null);
  const [tmuxSessions, setTmuxSessions] = useState<TmuxSession[]>([]);
  const [loadingDir, setLoadingDir] = useState(false);
  const [loadingTmux, setLoadingTmux] = useState(false);
  const [error, setError] = useState("");
  const [selectedAlias, setSelectedAlias] = useState("");
  const [aliasPassword, setAliasPassword] = useState("");
  const [newTmuxName, setNewTmuxName] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [manualProfile, setManualProfile] = useState({
    name: "",
    host: "",
    port: "22",
    username: "",
    auth_type: "agent" as RemoteProfile["auth_type"],
    password: "",
    private_key_path: "",
    ssh_config_alias: "",
    default_remote_path: "",
  });
  const directoryRequestRef = useRef(0);
  const tmuxRequestRef = useRef(0);
  const profilesRef = useRef<RemoteProfile[]>([]);

  useEffect(() => {
    profilesRef.current = profiles;
  }, [profiles]);

  const selectedProfile = useMemo(
    () => profiles.find((item) => item.profile_id === selectedProfileId) ?? null,
    [profiles, selectedProfileId],
  );
  const tmuxPath = remoteRoot?.remote_path || currentPath || selectedProfile?.default_remote_path || "/";

  const refreshProfiles = useCallback(async () => {
    const payload = await apiJson<{ profiles: RemoteProfile[] }>("/api/remote-workspaces/profiles");
    setProfiles(payload.profiles);
    setSelectedProfileId((current) => current || payload.profiles[0]?.profile_id || "");
    return payload.profiles;
  }, []);

  const loadDirectory = useCallback(async (profileId: string, path: string) => {
    if (!profileId) return;
    const requestId = directoryRequestRef.current + 1;
    directoryRequestRef.current = requestId;
    setLoadingDir(true);
    setError("");
    setEntries([]);
    try {
      const payload = await apiJson<{ path: string; entries: RemoteEntry[] }>(
        `/api/remote-workspaces/profiles/${encodeURIComponent(profileId)}/ls?path=${encodeURIComponent(path)}`,
      );
      if (requestId !== directoryRequestRef.current) return;
      setCurrentPath(payload.path);
      setEntries(payload.entries);
    } catch (exc) {
      if (requestId !== directoryRequestRef.current) return;
      setEntries([]);
      const profileName = profilesRef.current.find((item) => item.profile_id === profileId)?.name || profileId;
      setError(`${profileName} · ${path}：${getSafeErrorMessage(exc, "无法读取远程目录。")}`);
    } finally {
      if (requestId === directoryRequestRef.current) {
        setLoadingDir(false);
      }
    }
  }, []);

  const refreshTmux = useCallback(
    async (profileId: string, path: string) => {
      if (!profileId) return;
      const requestId = tmuxRequestRef.current + 1;
      tmuxRequestRef.current = requestId;
      setLoadingTmux(true);
      try {
        const payload = await apiJson<{ sessions: TmuxSession[] }>(
          `/api/remote-workspaces/profiles/${encodeURIComponent(profileId)}/tmux?path=${encodeURIComponent(path)}`,
        );
        if (requestId !== tmuxRequestRef.current) return;
        setTmuxSessions(payload.sessions);
      } catch (exc) {
        if (requestId !== tmuxRequestRef.current) return;
        const profileName = profilesRef.current.find((item) => item.profile_id === profileId)?.name || profileId;
        setTmuxSessions([]);
        setError(`${profileName} · ${path}：${getSafeErrorMessage(exc, "无法读取 tmux 会话。")}`);
      } finally {
        if (requestId === tmuxRequestRef.current) {
          setLoadingTmux(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    let disposed = false;
    void Promise.all([
      refreshProfiles(),
      apiJson<{ hosts: SshConfigHost[] }>("/api/remote-workspaces/ssh-config-hosts"),
      apiJson<{ remote_root: ProjectRemoteRoot | null }>(`/api/projects/${encodeURIComponent(projectId)}/remote-root`),
    ])
      .then(([nextProfiles, hostPayload, rootPayload]) => {
        if (disposed) return;
        setSshHosts(hostPayload.hosts);
        setSelectedAlias(hostPayload.hosts[0]?.name || "");
        setRemoteRoot(rootPayload.remote_root);
        const profileId = rootPayload.remote_root?.profile_id || nextProfiles[0]?.profile_id || "";
        setSelectedProfileId(profileId);
        const startPath = rootPayload.remote_root?.remote_path || nextProfiles.find((item) => item.profile_id === profileId)?.default_remote_path || "/";
        setCurrentPath(startPath);
        if (profileId) {
          void loadDirectory(profileId, startPath);
          if (rootPayload.remote_root) {
            void refreshTmux(profileId, startPath);
          } else {
            setTmuxSessions([]);
          }
        }
      })
      .catch((exc) => {
        if (!disposed) setError(getSafeErrorMessage(exc, "远程工作区初始化失败。"));
      });
    return () => {
      disposed = true;
    };
  }, [loadDirectory, projectId, refreshProfiles, refreshTmux]);

  useEffect(() => {
    if (!selectedProfile) return;
    const nextPath =
      remoteRoot?.profile_id === selectedProfile.profile_id
        ? remoteRoot.remote_path
        : selectedProfile.default_remote_path || "/";
    setCurrentPath(nextPath);
    setTmuxSessions([]);
    void loadDirectory(selectedProfile.profile_id, nextPath);
    if (remoteRoot?.profile_id === selectedProfile.profile_id) {
      void refreshTmux(selectedProfile.profile_id, nextPath);
    }
  }, [selectedProfile?.profile_id]);

  const importAlias = useCallback(async () => {
    if (!selectedAlias) return;
    setError("");
    try {
      const payload = await apiJson<{ profile: RemoteProfile }>("/api/remote-workspaces/profiles/import-ssh-config", {
        method: "POST",
        body: JSON.stringify({ alias: selectedAlias, password: aliasPassword || null }),
      });
      await refreshProfiles();
      setSelectedProfileId(payload.profile.profile_id);
      setAliasPassword("");
    } catch (exc) {
      setError(getSafeErrorMessage(exc, "导入 SSH config 失败。"));
    }
  }, [aliasPassword, refreshProfiles, selectedAlias]);

  const saveManualProfile = useCallback(async () => {
    setError("");
    try {
      const payload = await apiJson<{ profile: RemoteProfile }>("/api/remote-workspaces/profiles", {
        method: "POST",
        body: JSON.stringify({
          ...manualProfile,
          port: Number(manualProfile.port || 22),
          password: manualProfile.password || null,
          private_key_path: manualProfile.private_key_path || null,
          ssh_config_alias: manualProfile.ssh_config_alias || null,
          default_remote_path: manualProfile.default_remote_path || null,
        }),
      });
      await refreshProfiles();
      setSelectedProfileId(payload.profile.profile_id);
      setManualOpen(false);
    } catch (exc) {
      setError(getSafeErrorMessage(exc, "保存服务器失败。"));
    }
  }, [manualProfile, refreshProfiles]);

  const setAsRoot = useCallback(async () => {
    if (!selectedProfile) return;
    setError("");
    try {
      const payload = await apiJson<{ remote_root: ProjectRemoteRoot }>(`/api/projects/${encodeURIComponent(projectId)}/remote-root`, {
        method: "POST",
        body: JSON.stringify({
          profile_id: selectedProfile.profile_id,
          remote_path: currentPath,
          label: currentPath.split("/").filter(Boolean).pop() || currentPath,
        }),
      });
      setRemoteRoot(payload.remote_root);
      onTerminalPreset({ sshTarget: selectedProfile.ssh_target, remoteCwd: currentPath });
      void refreshTmux(selectedProfile.profile_id, currentPath);
    } catch (exc) {
      setError(getSafeErrorMessage(exc, "设置实验根目录失败。"));
    }
  }, [currentPath, onTerminalPreset, projectId, refreshTmux, selectedProfile]);

  const fillTerminal = useCallback(
    (sessionName?: string) => {
      if (!selectedProfile) return;
      onTerminalPreset({
        sshTarget: selectedProfile.ssh_target,
        remoteCwd: tmuxPath,
        tmuxSession: sessionName,
      });
    },
    [onTerminalPreset, selectedProfile, tmuxPath],
  );

  const createTmux = useCallback(async () => {
    if (!selectedProfile || !newTmuxName.trim()) return;
    setError("");
    try {
      await apiJson(`/api/remote-workspaces/profiles/${encodeURIComponent(selectedProfile.profile_id)}/tmux`, {
        method: "POST",
        body: JSON.stringify({ name: newTmuxName.trim(), workdir: tmuxPath }),
      });
      const createdName = newTmuxName.trim().replace(/[^A-Za-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "");
      setNewTmuxName("");
      await refreshTmux(selectedProfile.profile_id, tmuxPath);
      fillTerminal(createdName);
    } catch (exc) {
      setError(getSafeErrorMessage(exc, "创建 tmux 会话失败。"));
    }
  }, [fillTerminal, newTmuxName, refreshTmux, selectedProfile, tmuxPath]);

  const killTmux = useCallback(
    async (sessionName: string) => {
      if (!selectedProfile) return;
      setError("");
      try {
        await apiJson(`/api/remote-workspaces/profiles/${encodeURIComponent(selectedProfile.profile_id)}/tmux/${encodeURIComponent(sessionName)}/kill`, {
          method: "POST",
        });
        await refreshTmux(selectedProfile.profile_id, tmuxPath);
      } catch (exc) {
        setError(getSafeErrorMessage(exc, "删除 tmux 会话失败。"));
      }
    },
    [refreshTmux, selectedProfile, tmuxPath],
  );

  return (
    <section className="remote-workspace-panel" aria-label="远程实验工作区">
      <header className="remote-workspace-header">
        <div>
          <span>远程工作区</span>
          <h2>选择服务器目录并运行实验</h2>
          <p>保存 SSH 连接，浏览服务器文件夹，绑定实验根目录，再进入 tmux 运行长期任务。</p>
        </div>
        <button className="button-secondary" type="button" onClick={() => selectedProfile && loadDirectory(selectedProfile.profile_id, currentPath)} disabled={!selectedProfile || loadingDir}>
          <RefreshCw size={15} />
          刷新
        </button>
      </header>

      <div className="remote-workspace-grid">
        <div className="remote-workspace-column">
          <div className="remote-workspace-column-title">
            <Server size={16} />
            服务器
          </div>
          <label className="field-stack">
            <span>已保存连接</span>
            <select value={selectedProfileId} onChange={(event) => setSelectedProfileId(event.target.value)}>
              {profiles.length === 0 ? <option value="">未保存服务器</option> : null}
              {profiles.map((profile) => (
                <option key={profile.profile_id} value={profile.profile_id}>
                  {profile.name} · {profile.ssh_target}
                </option>
              ))}
            </select>
          </label>

          <div className="remote-import-row">
            <select value={selectedAlias} onChange={(event) => setSelectedAlias(event.target.value)}>
              {sshHosts.length === 0 ? <option value="">未发现 ~/.ssh/config</option> : null}
              {sshHosts.map((host) => (
                <option key={host.name} value={host.name}>
                  {host.name} · {host.username}@{host.host}
                </option>
              ))}
            </select>
            <button className="button-secondary" type="button" onClick={importAlias} disabled={!selectedAlias}>
              <Import size={15} />
              导入
            </button>
          </div>
          <input
            className="remote-password-input"
            value={aliasPassword}
            onChange={(event) => setAliasPassword(event.target.value)}
            placeholder="密码或私钥 passphrase，可留空"
            type="password"
          />

          <button className="button-secondary remote-wide-button" type="button" onClick={() => setManualOpen((value) => !value)}>
            <Plus size={15} />
            手动保存服务器
          </button>

          {manualOpen ? (
            <div className="remote-manual-form">
              <input value={manualProfile.name} onChange={(event) => setManualProfile({ ...manualProfile, name: event.target.value })} placeholder="名称" />
              <input value={manualProfile.host} onChange={(event) => setManualProfile({ ...manualProfile, host: event.target.value })} placeholder="Host/IP" />
              <div className="remote-two">
                <input value={manualProfile.username} onChange={(event) => setManualProfile({ ...manualProfile, username: event.target.value })} placeholder="用户" />
                <input value={manualProfile.port} onChange={(event) => setManualProfile({ ...manualProfile, port: event.target.value })} placeholder="端口" />
              </div>
              <select value={manualProfile.auth_type} onChange={(event) => setManualProfile({ ...manualProfile, auth_type: event.target.value as RemoteProfile["auth_type"] })}>
                <option value="agent">默认密钥/agent</option>
                <option value="password">密码</option>
                <option value="private_key">私钥路径</option>
                <option value="ssh_config">SSH config alias</option>
              </select>
              {manualProfile.auth_type === "password" ? (
                <input value={manualProfile.password} onChange={(event) => setManualProfile({ ...manualProfile, password: event.target.value })} placeholder="密码" type="password" />
              ) : null}
              {manualProfile.auth_type === "private_key" ? (
                <input value={manualProfile.private_key_path} onChange={(event) => setManualProfile({ ...manualProfile, private_key_path: event.target.value })} placeholder="私钥路径" />
              ) : null}
              {manualProfile.auth_type === "ssh_config" ? (
                <input value={manualProfile.ssh_config_alias} onChange={(event) => setManualProfile({ ...manualProfile, ssh_config_alias: event.target.value })} placeholder="SSH config alias" />
              ) : null}
              <input value={manualProfile.default_remote_path} onChange={(event) => setManualProfile({ ...manualProfile, default_remote_path: event.target.value })} placeholder="默认目录，例如 /home/user" />
              <button className="button-secondary" type="button" onClick={saveManualProfile}>
                保存
              </button>
            </div>
          ) : null}
        </div>

        <div className="remote-workspace-column remote-browser-column">
          <div className="remote-workspace-column-title">
            <FolderOpen size={16} />
            目录
          </div>
          <div className="remote-path-bar">
            <button className="icon-button" type="button" onClick={() => selectedProfile && loadDirectory(selectedProfile.profile_id, parentPath(currentPath))} disabled={!selectedProfile || currentPath === "/"}>
              ..
            </button>
            <span title={currentPath}>{currentPath}</span>
          </div>
          <div className="remote-directory-list" aria-busy={loadingDir}>
            {loadingDir ? <div className="remote-empty">正在读取目录...</div> : null}
            {!loadingDir && entries.length === 0 ? <div className="remote-empty">选择服务器后读取目录。</div> : null}
            {entries.map((entry) => (
              <button
                className={`remote-entry ${entry.is_directory ? "directory" : "file"}`}
                key={entry.path}
                type="button"
                onClick={() => entry.is_directory && selectedProfile && loadDirectory(selectedProfile.profile_id, entry.path)}
                disabled={!entry.is_directory}
                title={entry.path}
              >
                <span>{entry.is_directory ? "目录" : entry.kind === "symlink" ? "链接" : "文件"}</span>
                <strong>{entry.name}</strong>
                <small>{entry.permissions}</small>
              </button>
            ))}
          </div>
          <div className="remote-browser-actions">
            <button className="button-secondary" type="button" onClick={setAsRoot} disabled={!selectedProfile}>
              设为实验根目录
            </button>
            <button className="button-secondary" type="button" onClick={() => fillTerminal()} disabled={!selectedProfile}>
              <TerminalSquare size={15} />
              填入终端
            </button>
          </div>
        </div>

        <div className="remote-workspace-column">
          <div className="remote-workspace-column-title">
            <TerminalSquare size={16} />
            tmux
          </div>
          <div className="remote-root-card">
            <span>当前根目录</span>
            <strong>{remoteRoot ? remoteRoot.remote_path : "尚未绑定"}</strong>
          </div>
          <div className="remote-import-row">
            <input value={newTmuxName} onChange={(event) => setNewTmuxName(event.target.value)} placeholder="新会话名，如 exp1" />
            <button className="button-secondary" type="button" onClick={createTmux} disabled={!selectedProfile || !newTmuxName.trim()}>
              新建
            </button>
          </div>
          <button className="button-secondary remote-wide-button" type="button" onClick={() => selectedProfile && refreshTmux(selectedProfile.profile_id, tmuxPath)} disabled={!selectedProfile || loadingTmux}>
            <RefreshCw size={15} />
            {loadingTmux ? "读取中" : "刷新会话"}
          </button>
          <div className="remote-tmux-list">
            {tmuxSessions.length === 0 ? <div className="remote-empty">暂无属于该目录的 tmux 会话。</div> : null}
            {tmuxSessions.map((session) => (
              <div className="remote-tmux-row" key={session.name}>
                <button type="button" onClick={() => fillTerminal(session.name)} title={session.current_path}>
                  <strong>{session.name}</strong>
                  <span>{session.attached ? "已连接" : "后台"} · {session.windows} 窗口</span>
                  <small>{formatSessionTime(session.created_at)}</small>
                </button>
                <button className="icon-button danger" type="button" onClick={() => killTmux(session.name)} title="删除 tmux 会话">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {error ? <div className="status-banner warning">{error}</div> : null}
    </section>
  );
}
