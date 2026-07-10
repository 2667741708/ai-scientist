from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
import shutil
import stat
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class RemoteWorkspaceError(ValueError):
    pass


STORE_VERSION = 1
_store_lock = threading.Lock()


def _paramiko():
    try:
        import paramiko
    except Exception as exc:  # pragma: no cover - dependency/runtime specific
        raise RemoteWorkspaceError("paramiko is required for remote workspace SSH/SFTP support.") from exc
    return paramiko


def remote_workspace_status() -> Dict[str, Any]:
    paramiko_available = True
    paramiko_error = ""
    try:
        _paramiko()
    except RemoteWorkspaceError as exc:
        paramiko_available = False
        paramiko_error = str(exc)
    return {
        "mode": "unrestricted",
        "ssh_sftp": {
            "available": paramiko_available,
            "reason": paramiko_error,
        },
        "sshfs": sshfs_status(),
    }


def _blank_store() -> Dict[str, Any]:
    return {
        "version": STORE_VERSION,
        "updated_at": time.time(),
        "profiles": [],
        "project_roots": {},
    }


def _load_store(store_path: Path) -> Dict[str, Any]:
    if not store_path.exists():
        return _blank_store()
    try:
        payload = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RemoteWorkspaceError(f"Remote workspace store could not be read: {exc}") from exc
    if not isinstance(payload, dict):
        return _blank_store()
    payload.setdefault("version", STORE_VERSION)
    payload.setdefault("profiles", [])
    payload.setdefault("project_roots", {})
    return payload


def _save_store(store_path: Path, payload: Dict[str, Any]) -> None:
    payload["version"] = STORE_VERSION
    payload["updated_at"] = time.time()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _public_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    username = str(profile.get("username") or "")
    host = str(profile.get("host") or "")
    alias = str(profile.get("ssh_config_alias") or "")
    ssh_target = alias or (f"{username}@{host}" if username and host else host)
    return {
        "profile_id": profile.get("profile_id"),
        "name": profile.get("name"),
        "host": host,
        "port": int(profile.get("port") or 22),
        "username": username,
        "auth_type": profile.get("auth_type") or "agent",
        "ssh_config_alias": alias or None,
        "ssh_target": ssh_target,
        "private_key_path": profile.get("private_key_path") or None,
        "has_password": bool(profile.get("password")),
        "has_passphrase": bool(profile.get("passphrase")),
        "default_remote_path": profile.get("default_remote_path") or default_remote_path(username),
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
    }


def list_profiles(store_path: Path) -> List[Dict[str, Any]]:
    with _store_lock:
        store = _load_store(store_path)
    profiles = [item for item in store.get("profiles", []) if isinstance(item, dict)]
    return [_public_profile(item) for item in profiles]


def _profile_id(value: Optional[str] = None) -> str:
    if value:
        normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._-")
        if normalized:
            return normalized[:80]
    return f"ssh_{uuid.uuid4().hex[:12]}"


def default_remote_path(username: str) -> str:
    if username == "root":
        return "/root"
    if username:
        return f"/home/{username}"
    return "/"


def normalize_remote_path(value: Optional[str]) -> str:
    raw = (value or "/").strip() or "/"
    if "\x00" in raw or "\r" in raw or "\n" in raw:
        raise RemoteWorkspaceError("Remote path must be a single path.")
    if not raw.startswith("/"):
        raw = "/" + raw
    normalized = posixpath.normpath(raw)
    return "/" if normalized == "." else normalized


def _normalize_profile(payload: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    existing = existing or {}
    alias = str(payload.get("ssh_config_alias") or existing.get("ssh_config_alias") or "").strip()
    host = str(payload.get("host") or existing.get("host") or "").strip()
    username = str(payload.get("username") or existing.get("username") or "").strip()
    name = str(payload.get("name") or existing.get("name") or alias or host or "").strip()
    if not name:
        raise RemoteWorkspaceError("Profile name is required.")
    if not host and not alias:
        raise RemoteWorkspaceError("Host or SSH config alias is required.")
    try:
        port = int(payload.get("port") or existing.get("port") or 22)
    except (TypeError, ValueError) as exc:
        raise RemoteWorkspaceError("SSH port must be a number.") from exc
    if port < 1 or port > 65535:
        raise RemoteWorkspaceError("SSH port must be between 1 and 65535.")
    auth_type = str(payload.get("auth_type") or existing.get("auth_type") or "").strip()
    private_key_path = str(payload.get("private_key_path") or existing.get("private_key_path") or "").strip()
    password = payload.get("password") if "password" in payload else existing.get("password")
    passphrase = payload.get("passphrase") if "passphrase" in payload else existing.get("passphrase")
    if not auth_type:
        if alias:
            auth_type = "ssh_config"
        elif private_key_path:
            auth_type = "private_key"
        elif password:
            auth_type = "password"
        else:
            auth_type = "agent"
    if auth_type not in {"ssh_config", "password", "private_key", "agent"}:
        raise RemoteWorkspaceError("Unsupported SSH auth type.")
    now = time.time()
    profile_id = str(payload.get("profile_id") or existing.get("profile_id") or _profile_id(alias or f"{username}_{host}_{port}"))
    return {
        "profile_id": _profile_id(profile_id),
        "name": name,
        "host": host or alias,
        "port": port,
        "username": username,
        "auth_type": auth_type,
        "password": password or None,
        "private_key_path": private_key_path or None,
        "passphrase": passphrase or None,
        "ssh_config_alias": alias or None,
        "default_remote_path": normalize_remote_path(payload.get("default_remote_path") or existing.get("default_remote_path") or default_remote_path(username)),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
    }


def save_profile(store_path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    with _store_lock:
        store = _load_store(store_path)
        profiles = [item for item in store.get("profiles", []) if isinstance(item, dict)]
        wanted_id = str(payload.get("profile_id") or "")
        existing_index = next((idx for idx, item in enumerate(profiles) if item.get("profile_id") == wanted_id), -1)
        existing = profiles[existing_index] if existing_index >= 0 else None
        profile = _normalize_profile(payload, existing)
        duplicate_index = next(
            (
                idx
                for idx, item in enumerate(profiles)
                if item.get("profile_id") != profile["profile_id"]
                and item.get("host") == profile["host"]
                and int(item.get("port") or 22) == profile["port"]
                and item.get("username") == profile["username"]
            ),
            -1,
        )
        if existing_index >= 0:
            profiles[existing_index] = profile
        elif duplicate_index >= 0:
            profile["profile_id"] = profiles[duplicate_index]["profile_id"]
            profile["created_at"] = profiles[duplicate_index].get("created_at") or profile["created_at"]
            profiles[duplicate_index] = profile
        else:
            profiles.append(profile)
        store["profiles"] = profiles
        _save_store(store_path, store)
    return _public_profile(profile)


def delete_profile(store_path: Path, profile_id: str) -> Dict[str, Any]:
    with _store_lock:
        store = _load_store(store_path)
        profiles = [item for item in store.get("profiles", []) if isinstance(item, dict)]
        next_profiles = [item for item in profiles if item.get("profile_id") != profile_id]
        if len(next_profiles) == len(profiles):
            raise RemoteWorkspaceError("SSH profile was not found.")
        store["profiles"] = next_profiles
        project_roots = store.get("project_roots", {})
        if isinstance(project_roots, dict):
            store["project_roots"] = {
                key: value
                for key, value in project_roots.items()
                if not (isinstance(value, dict) and value.get("profile_id") == profile_id)
            }
        _save_store(store_path, store)
    return {"ok": True, "profile_id": profile_id}


def _get_full_profile(store_path: Path, profile_id: str) -> Dict[str, Any]:
    with _store_lock:
        store = _load_store(store_path)
    for profile in store.get("profiles", []):
        if isinstance(profile, dict) and profile.get("profile_id") == profile_id:
            return profile
    raise RemoteWorkspaceError("SSH profile was not found.")


def parse_ssh_config(config_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = config_path or (Path.home() / ".ssh" / "config")
    if not path.exists():
        return []
    hosts: List[Dict[str, Any]] = []
    current_names: List[str] = []
    current: Dict[str, Any] = {}

    def flush() -> None:
        if not current_names:
            return
        for name in current_names:
            if "*" in name or "?" in name:
                continue
            item = {"name": name, **current}
            item["host"] = item.get("hostname") or name
            item["port"] = int(item.get("port") or 22)
            item["username"] = item.get("user") or os.getenv("USER") or os.getenv("USERNAME") or ""
            item["default_remote_path"] = default_remote_path(str(item.get("username") or ""))
            item["ssh_target"] = name
            hosts.append(item)

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue
        key, value = parts[0].lower(), parts[1].strip().strip('"')
        if key == "host":
            flush()
            current_names = value.split()
            current = {}
            continue
        if not current_names:
            continue
        if key == "hostname":
            current["hostname"] = value
        elif key == "user":
            current["user"] = value
        elif key == "port":
            try:
                current["port"] = int(value)
            except ValueError:
                pass
        elif key == "identityfile":
            expanded = os.path.expandvars(os.path.expanduser(value))
            current["identity_file"] = str(Path(expanded))
    flush()
    return hosts


def import_ssh_config_profile(store_path: Path, alias: str, *, password: Optional[str] = None, default_remote_path_value: Optional[str] = None) -> Dict[str, Any]:
    wanted = alias.strip()
    if not wanted:
        raise RemoteWorkspaceError("SSH config alias is required.")
    host = next((item for item in parse_ssh_config() if str(item.get("name") or "").lower() == wanted.lower()), None)
    if not host:
        raise RemoteWorkspaceError("SSH config host was not found.")
    return save_profile(
        store_path,
        {
            "profile_id": _profile_id(str(host.get("name") or wanted)),
            "name": host.get("name") or wanted,
            "host": host.get("host") or wanted,
            "port": host.get("port") or 22,
            "username": host.get("username") or "",
            "auth_type": "ssh_config" if host.get("name") else "agent",
            "password": password,
            "private_key_path": host.get("identity_file"),
            "ssh_config_alias": host.get("name") or wanted,
            "default_remote_path": default_remote_path_value or host.get("default_remote_path") or "/",
        },
    )


def _connect_ssh(profile: Dict[str, Any]):
    paramiko = _paramiko()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    password = profile.get("password") or None
    passphrase = profile.get("passphrase") or None
    kwargs: Dict[str, Any] = {
        "hostname": profile.get("host") or profile.get("ssh_config_alias"),
        "port": int(profile.get("port") or 22),
        "username": profile.get("username") or None,
        "timeout": 8,
        "banner_timeout": 8,
        "auth_timeout": 8,
        "allow_agent": True,
        "look_for_keys": True,
        "gss_auth": False,
        "gss_kex": False,
    }
    private_key_path = profile.get("private_key_path")
    if private_key_path:
        kwargs["key_filename"] = private_key_path
        if passphrase or password:
            kwargs["passphrase"] = passphrase or password
    elif password:
        kwargs["password"] = password
    client.connect(**kwargs)
    return client


def _join_remote_path(base: str, name: str) -> str:
    joined = posixpath.normpath(posixpath.join(base, name))
    return "/" if joined == "." else joined


def list_remote_directory(store_path: Path, profile_id: str, remote_path: Optional[str]) -> Dict[str, Any]:
    profile = _get_full_profile(store_path, profile_id)
    target_path = normalize_remote_path(remote_path or profile.get("default_remote_path") or "/")
    client = _connect_ssh(profile)
    try:
        sftp = client.open_sftp()
        try:
            entries = []
            for attr in sftp.listdir_attr(target_path):
                mode = int(attr.st_mode or 0)
                is_dir = stat.S_ISDIR(mode)
                is_link = stat.S_ISLNK(mode)
                kind = "directory" if is_dir else "symlink" if is_link else "file"
                entries.append(
                    {
                        "name": attr.filename,
                        "path": _join_remote_path(target_path, attr.filename),
                        "kind": kind,
                        "is_directory": is_dir,
                        "size": int(attr.st_size or 0),
                        "modified_time": int(attr.st_mtime or 0),
                        "permissions": stat.filemode(mode) if mode else "",
                    }
                )
            entries.sort(key=lambda item: (not item["is_directory"], str(item["name"]).lower()))
            return {"profile": _public_profile(profile), "path": target_path, "entries": entries, "mode": "unrestricted"}
        finally:
            sftp.close()
    finally:
        client.close()


def _exec_ssh(store_path: Path, profile_id: str, command: str, *, timeout: int = 20) -> Dict[str, Any]:
    profile = _get_full_profile(store_path, profile_id)
    client = _connect_ssh(profile)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        stdin.close()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return {"stdout": out, "stderr": err, "exit_code": code}
    finally:
        client.close()


def _safe_tmux_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    if not safe:
        raise RemoteWorkspaceError("tmux session name is required.")
    return safe[:80]


def list_tmux_sessions(store_path: Path, profile_id: str, remote_path: Optional[str] = None) -> Dict[str, Any]:
    command = "command -v tmux >/dev/null 2>&1 && tmux list-sessions -F '#{session_name}\\t#{session_windows}\\t#{session_created}\\t#{session_attached}\\t#{pane_current_path}' 2>/dev/null || true"
    result = _exec_ssh(store_path, profile_id, command, timeout=15)
    sessions = []
    for line in result["stdout"].splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        name = parts[0] if len(parts) > 0 else ""
        if not name:
            continue
        created_at = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        current_path = parts[4] if len(parts) > 4 else ""
        sessions.append(
            {
                "name": name,
                "windows": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
                "created_at": created_at,
                "attached": (parts[3] == "1") if len(parts) > 3 else False,
                "current_path": current_path,
            }
        )
    if remote_path:
        normalized = normalize_remote_path(remote_path).rstrip("/")
        sessions = [
            item
            for item in sessions
            if item.get("current_path", "").rstrip("/") == normalized
            or item.get("current_path", "").rstrip("/").startswith(normalized + "/")
        ]
    return {"sessions": sessions, "mode": "unrestricted", "stderr": result.get("stderr") or ""}


def create_tmux_session(store_path: Path, profile_id: str, name: str, remote_path: Optional[str] = None) -> Dict[str, Any]:
    safe_name = _safe_tmux_name(name)
    workdir = normalize_remote_path(remote_path or "/")
    quoted_name = shlex.quote(safe_name)
    quoted_workdir = shlex.quote(workdir)
    command = (
        "command -v tmux >/dev/null 2>&1 || { echo 'tmux is not installed' >&2; exit 127; }; "
        f"tmux has-session -t {quoted_name} 2>/dev/null || tmux new-session -d -s {quoted_name} -c {quoted_workdir}; "
        f"tmux set-option -t {quoted_name} mouse on; "
        f"tmux set-option -t {quoted_name} history-limit 100000"
    )
    result = _exec_ssh(store_path, profile_id, command, timeout=20)
    if result["exit_code"] != 0:
        raise RemoteWorkspaceError(result["stderr"] or "tmux session could not be created.")
    return {"ok": True, "name": safe_name, "workdir": workdir, "result": result}


def kill_tmux_session(store_path: Path, profile_id: str, name: str) -> Dict[str, Any]:
    safe_name = _safe_tmux_name(name)
    result = _exec_ssh(store_path, profile_id, f"tmux kill-session -t {shlex.quote(safe_name)}", timeout=15)
    if result["exit_code"] != 0:
        raise RemoteWorkspaceError(result["stderr"] or "tmux session could not be killed.")
    return {"ok": True, "name": safe_name}


def rename_tmux_session(store_path: Path, profile_id: str, old_name: str, new_name: str) -> Dict[str, Any]:
    safe_old = _safe_tmux_name(old_name)
    safe_new = _safe_tmux_name(new_name)
    result = _exec_ssh(
        store_path,
        profile_id,
        f"tmux rename-session -t {shlex.quote(safe_old)} {shlex.quote(safe_new)}",
        timeout=15,
    )
    if result["exit_code"] != 0:
        raise RemoteWorkspaceError(result["stderr"] or "tmux session could not be renamed.")
    return {"ok": True, "old_name": safe_old, "new_name": safe_new}


def set_project_remote_root(store_path: Path, project_id: str, profile_id: str, remote_path: str, label: Optional[str] = None) -> Dict[str, Any]:
    profile = _get_full_profile(store_path, profile_id)
    normalized = normalize_remote_path(remote_path)
    payload = {
        "project_id": project_id,
        "profile_id": profile_id,
        "profile": _public_profile(profile),
        "remote_path": normalized,
        "label": label or posixpath.basename(normalized.rstrip("/")) or normalized,
        "updated_at": time.time(),
        "mode": "unrestricted",
    }
    with _store_lock:
        store = _load_store(store_path)
        project_roots = store.get("project_roots")
        if not isinstance(project_roots, dict):
            project_roots = {}
        project_roots[project_id] = payload
        store["project_roots"] = project_roots
        _save_store(store_path, store)
    return payload


def get_project_remote_root(store_path: Path, project_id: str) -> Optional[Dict[str, Any]]:
    with _store_lock:
        store = _load_store(store_path)
    project_roots = store.get("project_roots")
    if not isinstance(project_roots, dict):
        return None
    item = project_roots.get(project_id)
    return item if isinstance(item, dict) else None


def sshfs_status() -> Dict[str, Any]:
    sshfs = shutil.which("sshfs") or shutil.which("sshfs.exe")
    fusermount = shutil.which("fusermount3") or shutil.which("fusermount")
    return {
        "available": bool(sshfs),
        "sshfs": sshfs,
        "fusermount": fusermount,
        "default_enabled": False,
        "reason": "" if sshfs else "sshfs is not installed or not on PATH; first version uses SFTP browsing plus SSH/tmux terminal.",
    }
