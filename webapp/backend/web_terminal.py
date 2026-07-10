from __future__ import annotations

import os
import platform
import shlex
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


class WebTerminalError(ValueError):
    pass


@dataclass(frozen=True)
class TerminalProfile:
    id: str
    label: str
    command: str
    args: tuple[str, ...] = ()
    available: bool = True
    reason: str = ""
    platform: str = field(default_factory=lambda: platform.system().lower())

    def public_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "command": self.command,
            "args": list(self.args),
            "available": self.available,
            "reason": self.reason,
            "platform": self.platform,
        }


class BaseTerminalProcess:
    def read(self, size: int = 4096) -> str:
        raise NotImplementedError

    def write(self, data: str) -> None:
        raise NotImplementedError

    def resize(self, rows: int, cols: int) -> None:
        raise NotImplementedError

    def isalive(self) -> bool:
        raise NotImplementedError

    def terminate(self) -> None:
        raise NotImplementedError


class WindowsTerminalProcess(BaseTerminalProcess):
    def __init__(self, argv: List[str], *, cwd: Path, env: Dict[str, str], rows: int, cols: int):
        try:
            from winpty import PtyProcess
        except Exception as exc:  # pragma: no cover - platform/dependency specific
            raise WebTerminalError("pywinpty is required for web terminal support on Windows.") from exc
        self._process = PtyProcess.spawn(argv, cwd=str(cwd), env=env, dimensions=(rows, cols))

    def read(self, size: int = 4096) -> str:
        return self._process.read(size)

    def write(self, data: str) -> None:
        self._process.write(data)

    def resize(self, rows: int, cols: int) -> None:
        self._process.setwinsize(rows, cols)

    def isalive(self) -> bool:
        return bool(self._process.isalive())

    def terminate(self) -> None:
        try:
            self._process.terminate(force=True)
        except TypeError:
            self._process.terminate()


class UnixTerminalProcess(BaseTerminalProcess):
    def __init__(self, argv: List[str], *, cwd: Path, env: Dict[str, str], rows: int, cols: int):
        import fcntl
        import pty
        import struct
        import termios

        self._os = os
        self._fcntl = fcntl
        self._termios = termios
        self._struct = struct
        self._master_fd, slave_fd = pty.openpty()
        self._set_size(rows, cols)
        self._process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave_fd)

    def _set_size(self, rows: int, cols: int) -> None:
        packed = self._struct.pack("HHHH", rows, cols, 0, 0)
        self._fcntl.ioctl(self._master_fd, self._termios.TIOCSWINSZ, packed)

    def read(self, size: int = 4096) -> str:
        data = self._os.read(self._master_fd, size)
        return data.decode("utf-8", errors="replace")

    def write(self, data: str) -> None:
        self._os.write(self._master_fd, data.encode("utf-8", errors="replace"))

    def resize(self, rows: int, cols: int) -> None:
        self._set_size(rows, cols)
        try:
            self._process.send_signal(signal.SIGWINCH)
        except Exception:
            pass

    def isalive(self) -> bool:
        return self._process.poll() is None

    def terminate(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
        try:
            self._os.close(self._master_fd)
        except OSError:
            pass


@dataclass
class WebTerminalSession:
    session_id: str
    profile_id: str
    label: str
    command: str
    args: List[str]
    cwd: str
    created_at: float
    process: BaseTerminalProcess
    ssh_target: Optional[str] = None
    ssh_remote_cwd: Optional[str] = None
    ssh_tmux_session: Optional[str] = None

    def public_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "profile_id": self.profile_id,
            "label": self.label,
            "command": self.command,
            "args": self.args,
            "cwd": self.cwd,
            "created_at": self.created_at,
            "mode": "unrestricted",
            "ssh_target": self.ssh_target,
            "ssh_remote_cwd": self.ssh_remote_cwd,
            "ssh_tmux_session": self.ssh_tmux_session,
        }


_sessions: Dict[str, WebTerminalSession] = {}
_sessions_lock = threading.Lock()


def _existing_path(*candidates: str) -> Optional[str]:
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def terminal_profiles() -> List[TerminalProfile]:
    system = platform.system().lower()
    profiles: List[TerminalProfile] = []
    if system == "windows":
        git_bash = _existing_path(
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        )
        powershell = _which("powershell.exe") or _which("pwsh.exe")
        ssh = _which("ssh.exe") or _existing_path(r"C:\Windows\System32\OpenSSH\ssh.exe")
        profiles.extend(
            [
                TerminalProfile(
                    id="git-bash",
                    label="Git Bash",
                    command=git_bash or "bash.exe",
                    args=("--login", "-i"),
                    available=bool(git_bash),
                    reason="" if git_bash else "Git Bash was not found under Program Files.",
                ),
                TerminalProfile(
                    id="powershell",
                    label="PowerShell",
                    command=powershell or "powershell.exe",
                    args=("-NoLogo", "-NoExit"),
                    available=bool(powershell),
                    reason="" if powershell else "PowerShell was not found on PATH.",
                ),
                TerminalProfile(
                    id="cmd",
                    label="Command Prompt",
                    command=os.environ.get("COMSPEC", "cmd.exe"),
                    args=(),
                    available=bool(os.environ.get("COMSPEC") or _which("cmd.exe")),
                    reason="",
                ),
                TerminalProfile(
                    id="ssh",
                    label="OpenSSH",
                    command=ssh or "ssh.exe",
                    args=(),
                    available=bool(ssh),
                    reason="" if ssh else "OpenSSH client was not found on PATH.",
                ),
            ]
        )
    else:
        bash = _which("bash") or "/bin/bash"
        sh = _which("sh") or "/bin/sh"
        zsh = _which("zsh")
        ssh = _which("ssh")
        profiles.extend(
            [
                TerminalProfile(
                    id="bash",
                    label="Bash",
                    command=bash,
                    args=("-l",),
                    available=bool(Path(bash).exists() or _which("bash")),
                    reason="",
                    platform=system,
                ),
                TerminalProfile(
                    id="zsh",
                    label="Zsh",
                    command=zsh or "zsh",
                    args=("-l",),
                    available=bool(zsh),
                    reason="" if zsh else "zsh was not found on PATH.",
                    platform=system,
                ),
                TerminalProfile(
                    id="sh",
                    label="sh",
                    command=sh,
                    args=(),
                    available=bool(Path(sh).exists() or _which("sh")),
                    reason="",
                    platform=system,
                ),
                TerminalProfile(
                    id="ssh",
                    label="OpenSSH",
                    command=ssh or "ssh",
                    args=(),
                    available=bool(ssh),
                    reason="" if ssh else "OpenSSH client was not found on PATH.",
                    platform=system,
                ),
            ]
        )
    return profiles


def default_profile_id() -> str:
    profiles = terminal_profiles()
    preferred = ("git-bash", "bash", "powershell", "sh", "cmd")
    for profile_id in preferred:
        profile = next((item for item in profiles if item.id == profile_id and item.available), None)
        if profile:
            return profile.id
    available = next((item for item in profiles if item.available), None)
    return available.id if available else profiles[0].id


def web_terminal_status() -> Dict[str, Any]:
    profiles = [profile.public_dict() for profile in terminal_profiles()]
    return {
        "available": any(profile["available"] for profile in profiles),
        "mode": "unrestricted",
        "platform": platform.system().lower(),
        "default_profile": default_profile_id(),
        "profiles": profiles,
        "active_sessions": len(_sessions),
    }


def _resolve_cwd(cwd: Optional[str], *, default_root: Path) -> Path:
    if not cwd or not cwd.strip():
        return default_root.resolve()
    candidate = Path(cwd.strip())
    if not candidate.is_absolute():
        candidate = default_root / candidate
    resolved = candidate.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise WebTerminalError("Terminal cwd must be an existing directory.")
    return resolved


def create_web_terminal_session(
    *,
    profile_id: Optional[str],
    cwd: Optional[str],
    default_root: Path,
    cols: int = 100,
    rows: int = 30,
    ssh_target: Optional[str] = None,
    ssh_remote_cwd: Optional[str] = None,
    ssh_tmux_session: Optional[str] = None,
) -> WebTerminalSession:
    selected_id = profile_id or default_profile_id()
    profile = next((item for item in terminal_profiles() if item.id == selected_id), None)
    if not profile:
        raise WebTerminalError(f"Unknown terminal profile: {selected_id}.")
    if not profile.available:
        raise WebTerminalError(profile.reason or f"Terminal profile is not available: {profile.label}.")
    resolved_cwd = _resolve_cwd(cwd, default_root=default_root)
    safe_cols = min(max(int(cols or 100), 20), 400)
    safe_rows = min(max(int(rows or 30), 8), 120)
    args = list(profile.args)
    normalized_ssh_target: Optional[str] = None
    normalized_remote_cwd: Optional[str] = None
    normalized_tmux_session: Optional[str] = None
    if profile.id == "ssh":
        target = (ssh_target or "").strip()
        if not target:
            raise WebTerminalError("SSH target is required when using the OpenSSH profile.")
        if any(char in target for char in ("\x00", "\r", "\n")):
            raise WebTerminalError("SSH target must be a single host or alias.")
        normalized_ssh_target = target
        remote_cwd = (ssh_remote_cwd or "").strip()
        tmux_session = (ssh_tmux_session or "").strip()
        if remote_cwd and any(char in remote_cwd for char in ("\x00", "\r", "\n")):
            raise WebTerminalError("SSH remote cwd must be a single path.")
        if tmux_session and any(char in tmux_session for char in ("\x00", "\r", "\n")):
            raise WebTerminalError("tmux session must be a single name.")
        normalized_remote_cwd = remote_cwd or None
        normalized_tmux_session = tmux_session or None
        if normalized_tmux_session:
            quoted_session = shlex.quote(normalized_tmux_session)
            if normalized_remote_cwd:
                quoted_cwd = shlex.quote(normalized_remote_cwd)
                remote_command = (
                    f"tmux attach-session -t {quoted_session} "
                    f"|| tmux new-session -A -s {quoted_session} -c {quoted_cwd}"
                )
            else:
                remote_command = f"tmux attach-session -t {quoted_session} || tmux new-session -A -s {quoted_session}"
            args = ["-tt", target, remote_command]
        elif normalized_remote_cwd:
            quoted_cwd = shlex.quote(normalized_remote_cwd)
            remote_command = f"cd {quoted_cwd} && exec ${{SHELL:-bash}} -l"
            args = ["-tt", target, remote_command]
        else:
            args = [target]
    env = {
        **os.environ,
        "TERM": "xterm-256color",
        "FORCE_COLOR": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    argv = [profile.command, *args]
    if platform.system().lower() == "windows":
        process: BaseTerminalProcess = WindowsTerminalProcess(argv, cwd=resolved_cwd, env=env, rows=safe_rows, cols=safe_cols)
    else:
        process = UnixTerminalProcess(argv, cwd=resolved_cwd, env=env, rows=safe_rows, cols=safe_cols)
    session = WebTerminalSession(
        session_id=f"term_{uuid.uuid4().hex[:12]}",
        profile_id=profile.id,
        label=profile.label,
        command=profile.command,
        args=args,
        cwd=str(resolved_cwd),
        created_at=time.time(),
        process=process,
        ssh_target=normalized_ssh_target,
        ssh_remote_cwd=normalized_remote_cwd,
        ssh_tmux_session=normalized_tmux_session,
    )
    with _sessions_lock:
        _sessions[session.session_id] = session
    return session


def get_web_terminal_session(session_id: str) -> WebTerminalSession:
    with _sessions_lock:
        session = _sessions.get(session_id)
    if not session:
        raise WebTerminalError("Terminal session was not found.")
    return session


def close_web_terminal_session(session_id: str) -> None:
    with _sessions_lock:
        session = _sessions.pop(session_id, None)
    if session:
        session.process.terminate()


def list_web_terminal_sessions() -> List[Dict[str, Any]]:
    with _sessions_lock:
        sessions = list(_sessions.values())
    return [session.public_dict() for session in sessions]
