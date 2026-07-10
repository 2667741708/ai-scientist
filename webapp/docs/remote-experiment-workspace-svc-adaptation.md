# SVC remote workspace adaptation for experiments

本文记录对 `SVC_sshfs_webview.zip` 的阅读结论，以及将其能力改造成 `open-coscientist/webapp` 实验页面能力的推荐路线。

## 结论

SVC 不应该作为 VSIX 插件直接嵌入当前项目。当前项目宿主是 FastAPI + React 浏览器应用，而 SVC 宿主是 VS Code Extension Host。应该移植的是 SVC 的产品能力和后端流程：

1. 保存或导入 SSH 连接配置。
2. 用可视化目录浏览器选择远程服务器上的实验根目录。
3. 将选中的远程目录绑定到当前研究项目/候选假设。
4. 从该目录打开 SSH 终端。
5. 用 tmux 新建、列出、进入、重命名和终止长期实验会话。
6. 将 SSHFS/FUSE 本地挂载作为可选增强，而不是第一版主路径。

## SVC 当前代码要点

SVC 的当前源码主要是 TypeScript VS Code 扩展，不是浏览器插件。关键模块如下：

- `src/configManager.ts`
  - `ServerConfig` 包含 `id/name/host/port/username/authType/password/privateKeyPath/remotePath`。
  - 服务器列表保存在 VS Code `globalState` 的 `svc.servers`。
- `src/sshConfigParser.ts`
  - 解析本机 `~/.ssh/config` 的 `Host/HostName/User/Port/IdentityFile`。
  - 跳过通配符 Host。
- `src/serverConfigUI.ts`
  - 支持粘贴 `ssh alias`、`user@host -p 22`，自动解析后逐项确认。
  - 支持从 `~/.ssh/config` 导入。
- `src/sftpClient.ts`
  - 使用 `ssh2-sftp-client` 建立 SFTP 连接池。
  - 支持目录列表、文件读写、stat、mkdir、delete、rename。
  - 连接池用 `pendingConnections` 合并并发连接，并用 `ping()` 检查连接是否失效。
- `src/remoteFolderBrowser.ts` + `media/folderBrowserView.html`
  - VS Code Webview 目录选择器。
  - 前端通过 `postMessage` 发送 `listDir/selectFolder/cancel`。
  - 后端通过 SFTP 返回目录和文件列表。
- `src/sshfsMounter.ts`
  - 使用系统 `sshfs` 将远程目录挂到 `/tmp/svc_mounts/<server>/<path>`。
  - 依赖 `sshfs` 和 `fusermount3`，更适合 Linux；Windows 需要额外 SSHFS-Win/WinFsp 路线。
- `src/tmuxManager.ts`
  - 通过 SSH 执行 tmux 命令。
  - 支持 `listSessions`、`listSessionsForPath`、`newSession`、`killSession`、`renameSession`。
  - 新建会话时设置 `mouse on` 和 `history-limit 100000`。
- `src/sshTerminal.ts`
  - VS Code Pseudoterminal 形式的 SSH 终端。
  - 支持打开普通 shell，也支持 attach 到指定 tmux session。

## 与当前项目的映射

当前项目已经有实验页内的 Web Terminal：

- `backend/web_terminal.py`
  - 已支持 Windows `pywinpty` 和 Linux/Ubuntu `pty`。
  - 已检测 Git Bash、PowerShell、cmd、OpenSSH、bash、zsh、sh。
  - `ssh` profile 当前只负责打开 `ssh <target>`。
- `backend/app.py`
  - 已暴露 `/api/web-terminal/status`
  - `/api/web-terminal/sessions`
  - `/api/web-terminal/sessions/{session_id}/ws`
- `src/features/experiments/WebTerminalPanel.tsx`
  - 已在实验页显示终端类型、启动目录、SSH 目标和 xterm 终端。

SVC 能力应扩展在这条线上，而不是另起一个 VS Code 插件运行时。

## 推荐第一版架构

### 后端

新增 `backend/remote_workspace.py`：

- SSH profile store
  - `GET /api/remote-workspaces/ssh-config-hosts`
  - `GET /api/remote-workspaces/profiles`
  - `POST /api/remote-workspaces/profiles`
  - `DELETE /api/remote-workspaces/profiles/{profile_id}`
- 远程目录浏览
  - `GET /api/remote-workspaces/profiles/{profile_id}/ls?path=/home/a/project`
  - 第一版建议使用 Python SSH/SFTP 库或系统 OpenSSH；目录树最好优先走非交互私钥/agent。
- 远程实验根目录
  - `POST /api/projects/{project_id}/remote-root`
  - 记录 `profile_id`、`remote_path`、`label`、`last_used_at`。
- tmux
  - `GET /api/remote-workspaces/profiles/{profile_id}/tmux?path=/home/a/project`
  - `POST /api/remote-workspaces/profiles/{profile_id}/tmux`
  - `POST /api/remote-workspaces/profiles/{profile_id}/tmux/{name}/attach`
  - `POST /api/remote-workspaces/profiles/{profile_id}/tmux/{name}/kill`

扩展 `backend/web_terminal.py`：

- `ssh_target` 之外新增 `ssh_remote_cwd`。
- 可选新增 `ssh_tmux_session`。
- OpenSSH profile 启动时支持：
  - 普通远程目录：`ssh -tt <target> 'cd <remote_cwd>; exec ${SHELL:-bash} -l'`
  - tmux：`ssh -tt <target> 'tmux attach-session -t <session>'`

### 前端

新增 `src/features/experiments/RemoteWorkspacePanel.tsx`：

- 左列：服务器 profile 列表和从 SSH config 导入入口。
- 中列：远程路径 breadcrumb + 文件夹列表。
- 右列：当前实验根目录、tmux 会话、打开终端。

默认首屏只显示：

1. 选择服务器。
2. 选择实验目录。
3. 打开/新建 tmux 会话。

不要默认展示 raw SSH config、私钥内容、完整环境变量、底层命令参数。这些放入详情或专家设置。

## 第一版边界

- 允许用户获得“像进入远程服务器本地一样”的终端权限。
- 目录浏览 API 需要非交互认证。只有密码但没有私钥/agent 时，终端可用，目录树可能需要用户先保存密码或后续实现交互式认证。
- SSHFS 不作为第一版必需能力：
  - Ubuntu 上可选启用 `sshfs`。
  - Windows 需要 WinFsp/SSHFS-Win，部署成本高。
  - 浏览器项目实际更需要“选路径 + 终端/tmux 持久运行”，不一定必须把远程目录映射成宿主机文件系统。

## 用户路径

```text
实验页
  -> 选择服务器
  -> 浏览远程文件夹
  -> 设为实验根目录
  -> 新建或进入 tmux 会话
  -> 在 Web Terminal 中运行实验
  -> 后续把输出/日志/产物绑定回项目
```

这个路径比当前单纯输入 `ssh target` 更适合科研实验，因为它把“服务器”和“实验根目录”变成项目上下文，而不是一次性的终端输入。
