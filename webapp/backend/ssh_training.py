from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


class SshTrainingError(ValueError):
    pass


@dataclass(frozen=True)
class SshTrainingServer:
    server_id: str
    display_name: str
    ssh_alias: str
    user: str
    host: str
    port: int
    gpu_summary: str
    python_version: str
    node_version: str
    notes: str
    aliases: tuple[str, ...] = ()

    def public_dict(self) -> Dict[str, Any]:
        return {
            "server_id": self.server_id,
            "display_name": self.display_name,
            "ssh_alias": self.ssh_alias,
            "user": self.user,
            "host": self.host,
            "port": self.port,
            "gpu_summary": self.gpu_summary,
            "python_version": self.python_version,
            "node_version": self.node_version,
            "aliases": list(self.aliases),
            "notes": self.notes,
            "source": "workspace_ssh_config",
            "credential_boundary": "uses local ~/.ssh/config; no private keys or passwords are stored in project config",
        }


DEFAULT_SSH_TRAINING_SERVERS: Dict[str, SshTrainingServer] = {
    "c201-4090": SshTrainingServer(
        server_id="c201-4090",
        display_name="c201-4090",
        ssh_alias="c201-4090",
        user="a",
        host="10.20.22.77",
        port=22,
        gpu_summary="NVIDIA GeForce RTX 4090, 49140 MiB",
        python_version="3.13.7",
        node_version="22.12.0 via ~/.local/bin",
        aliases=("c201-4090-lan", "c201-4090-zt"),
        notes="Prefer Python 3.12/3.11 venv or conda for packages with Python 3.13 gaps.",
    ),
    "c201-5080": SshTrainingServer(
        server_id="c201-5080",
        display_name="c201-5080",
        ssh_alias="c201-5080",
        user="c201",
        host="10.20.22.105",
        port=22,
        gpu_summary="2 x NVIDIA GeForce RTX 5080, 16303 MiB each",
        python_version="3.12.3",
        node_version="22.12.0 via ~/.local/bin",
        aliases=("c201-5080-lan", "c201-5080-zt"),
        notes="Use PATH=\"$HOME/.local/bin:$PATH\" in non-interactive commands.",
    ),
    "d437": SshTrainingServer(
        server_id="d437",
        display_name="d437",
        ssh_alias="d437",
        user="d437",
        host="10.20.30.56",
        port=22,
        gpu_summary="NVIDIA TITAN RTX, 24576 MiB",
        python_version="3.12.3",
        node_version="22.12.0 via ~/.local/bin",
        aliases=("d437-zt",),
        notes="Use the ordinary d437/d437-zt user entry for this project, not container/jump aliases.",
    ),
}


SECRET_PATTERN = re.compile(
    r"(?i)("
    r"bearer\s+[A-Za-z0-9._\-]+"
    r"|sk-[A-Za-z0-9_\-]{8,}"
    r"|ghp_[A-Za-z0-9_]{8,}"
    r"|(?:token|api[_-]?key|password|secret)=['\"]?[^'\"\s;]+"
    r")"
)


BLOCKED_COMMAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(^|[;&|]\s*)sudo(\s|$)"), "sudo is not allowed in remote training workflows."),
    (re.compile(r"(^|[;&|]\s*)su(\s|$)"), "user switching is not allowed."),
    (re.compile(r"\b(passwd|visudo)\b"), "interactive account-management commands are blocked."),
    (re.compile(r"\b(shutdown|reboot|poweroff|halt)\b"), "power-management commands are blocked."),
    (re.compile(r"\b(mkfs|fdisk|parted)\b"), "disk partitioning/formatting commands are blocked."),
    (re.compile(r"\bdd\s+.*\bof="), "raw disk write commands are blocked."),
    (re.compile(r":\s*\(\)\s*\{"), "fork-bomb style shell functions are blocked."),
    (re.compile(r"\b(?:curl|wget)\b[^\n|;&]*\|\s*(?:bash|sh|python|python3)\b"), "download-and-execute pipelines are blocked."),
    (re.compile(r">\s*/etc/|>>\s*/etc/|\btee\s+/etc/"), "writes to /etc are blocked."),
    (re.compile(r"(^|[;&|]\s*)rm\s+-[A-Za-z]*r[A-Za-z]*f?[A-Za-z]*\s+(?:/|~|\$HOME)(?:\s|$)"), "recursive deletion of root/home is blocked."),
    (re.compile(r"\.ssh/(?:id_|authorized_keys|config)|~/.ssh|/\.ssh/"), "direct access to SSH credential files is blocked."),
)


@dataclass
class SshTrainingResult:
    status: str
    server_id: str
    ssh_alias: str
    command: str
    workdir: Optional[str]
    run_dir: str
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float
    artifacts: Dict[str, str]
    guardrail: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "server_id": self.server_id,
            "ssh_alias": self.ssh_alias,
            "command": redact_sensitive_text(self.command),
            "workdir": self.workdir,
            "run_dir": self.run_dir,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "artifacts": self.artifacts,
            "guardrail": self.guardrail,
        }


def redact_sensitive_text(value: str) -> str:
    return SECRET_PATTERN.sub("[REDACTED]", value or "")


def list_ssh_training_servers() -> List[Dict[str, Any]]:
    return [server.public_dict() for server in DEFAULT_SSH_TRAINING_SERVERS.values()]


def get_ssh_training_server(server_id: str) -> SshTrainingServer:
    normalized = (server_id or "").strip()
    if normalized in DEFAULT_SSH_TRAINING_SERVERS:
        return DEFAULT_SSH_TRAINING_SERVERS[normalized]
    for server in DEFAULT_SSH_TRAINING_SERVERS.values():
        if normalized in server.aliases:
            return server
    raise SshTrainingError("Unknown SSH training server. Use one of: c201-4090, c201-5080, d437.")


def ssh_training_status() -> Dict[str, Any]:
    ssh_path = shutil.which("ssh")
    return {
        "available": bool(ssh_path and DEFAULT_SSH_TRAINING_SERVERS),
        "mode": "configured_not_runtime_proven" if ssh_path else "missing_ssh_client",
        "reason": (
            f"OpenSSH client found at {ssh_path}; {len(DEFAULT_SSH_TRAINING_SERVERS)} training hosts are configured."
            if ssh_path
            else "OpenSSH client is not available on PATH."
        ),
        "checked_at": time.time(),
        "metadata": {
            "ssh_path": ssh_path,
            "servers": [server["server_id"] for server in list_ssh_training_servers()],
            "requires_approval_scope": "ssh.training_command",
        },
    }


def build_ssh_mcp_server_templates() -> Dict[str, Dict[str, Any]]:
    """Return disabled stdio MCP templates for SSH-hosted exec MCP services.

    These entries document how to attach a real MCP service exposed over SSH.
    They remain disabled by default because the remote command must exist on the
    target host and should be enabled explicitly by an operator.
    """
    templates: Dict[str, Dict[str, Any]] = {}
    for server in DEFAULT_SSH_TRAINING_SERVERS.values():
        safe_name = server.server_id.replace("-", "_")
        templates[f"ssh_{safe_name}"] = {
            "transport": "stdio",
            "command": "ssh",
            "args": [server.ssh_alias, "coscientist-ssh-mcp"],
            "enabled": False,
            "server_id": server.server_id,
            "source": "workspace_ssh_config",
            "description": "Disabled template for a remote SSH MCP service exposing controlled training tools.",
        }
    return templates


def validate_ssh_training_command(command: str, *, server_id: str, workdir: Optional[str] = None) -> Dict[str, Any]:
    text = (command or "").strip()
    if not text:
        return {"allowed": False, "code": "empty_command", "message": "Remote training command must not be empty."}
    if "\x00" in text:
        return {"allowed": False, "code": "nul_byte", "message": "Command cannot contain NUL bytes."}
    if len(text) > 20_000:
        return {"allowed": False, "code": "command_too_long", "message": "Command is too long for the SSH training workflow."}
    try:
        server = get_ssh_training_server(server_id)
    except SshTrainingError as exc:
        return {"allowed": False, "code": "unknown_server", "message": str(exc)}
    if workdir is not None and ("\x00" in workdir or "\n" in workdir or "\r" in workdir):
        return {"allowed": False, "code": "invalid_workdir", "message": "Remote workdir must be a single path string."}
    for pattern, reason in BLOCKED_COMMAND_PATTERNS:
        if pattern.search(text):
            return {
                "allowed": False,
                "code": "blocked_remote_command",
                "message": reason,
                "server_id": server.server_id,
                "matched": pattern.pattern,
            }
    return {
        "allowed": True,
        "server_id": server.server_id,
        "ssh_alias": server.ssh_alias,
        "risk_boundary": "remote_background_write",
    }


def run_ssh_training_command(
    *,
    server_id: str,
    command: str,
    artifact_root: Path,
    timeout_seconds: int,
    workdir: Optional[str] = None,
    job_id: Optional[str] = None,
) -> SshTrainingResult:
    guardrail = validate_ssh_training_command(command, server_id=server_id, workdir=workdir)
    server = get_ssh_training_server(server_id)
    artifact_root.mkdir(parents=True, exist_ok=True)
    run_dir = artifact_root / (job_id or f"ssh_training_{uuid.uuid4().hex[:12]}")
    run_dir.mkdir(parents=True, exist_ok=False)
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    manifest_path = run_dir / "manifest.json"

    if not guardrail.get("allowed"):
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(guardrail.get("message", "Blocked by guardrail."), encoding="utf-8")
        manifest = {
            "status": "blocked",
            "server_id": server.server_id,
            "ssh_alias": server.ssh_alias,
            "command": redact_sensitive_text(command),
            "workdir": workdir,
            "guardrail": guardrail,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return SshTrainingResult(
            status="blocked",
            server_id=server.server_id,
            ssh_alias=server.ssh_alias,
            command=command,
            workdir=workdir,
            run_dir=str(run_dir),
            stdout="",
            stderr=guardrail.get("message", "Blocked by guardrail."),
            returncode=126,
            duration_seconds=0.0,
            artifacts={"stdout": str(stdout_path), "stderr": str(stderr_path), "manifest": str(manifest_path)},
            guardrail=guardrail,
        )

    if not shutil.which("ssh"):
        raise SshTrainingError("OpenSSH client is not available on PATH.")

    setup = [
        'export PATH="$HOME/.local/bin:$PATH"',
        "export PYTHONUTF8=1",
        "export PYTHONIOENCODING=utf-8",
        "set -o pipefail",
    ]
    if workdir:
        setup.append(f"cd {shlex.quote(workdir)}")
    remote_script = "; ".join(setup + [command])
    ssh_command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        server.ssh_alias,
        "bash",
        "-lc",
        shlex.quote(remote_script),
    ]

    started = time.time()
    returncode = 0
    status = "complete"
    with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_fh, stderr_path.open(
        "w",
        encoding="utf-8",
        errors="replace",
    ) as stderr_fh:
        process = subprocess.Popen(
            ssh_command,
            stdin=subprocess.DEVNULL,
            stdout=stdout_fh,
            stderr=stderr_fh,
            text=True,
        )
        try:
            returncode = process.wait(timeout=timeout_seconds)
            status = "complete" if returncode == 0 else "error"
        except subprocess.TimeoutExpired:
            process.kill()
            returncode = 124
            status = "timeout"
            stderr_fh.write(f"\nSSH training command exceeded {timeout_seconds} seconds.\n")

    duration = round(time.time() - started, 4)
    stdout = _visible_file_text(stdout_path)
    stderr = _visible_file_text(stderr_path)
    manifest = {
        "status": status,
        "server_id": server.server_id,
        "ssh_alias": server.ssh_alias,
        "command": redact_sensitive_text(command),
        "workdir": workdir,
        "returncode": returncode,
        "duration_seconds": duration,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "guardrail": guardrail,
        "ssh_command_preview": _redacted_command_preview(ssh_command),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return SshTrainingResult(
        status=status,
        server_id=server.server_id,
        ssh_alias=server.ssh_alias,
        command=command,
        workdir=workdir,
        run_dir=str(run_dir),
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        duration_seconds=duration,
        artifacts={"stdout": str(stdout_path), "stderr": str(stderr_path), "manifest": str(manifest_path)},
        guardrail=guardrail,
    )


def _visible_file_text(path: Path, limit: int = 20_000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", text)
    text = redact_sensitive_text(text)
    if len(text) <= limit:
        return text
    head = limit // 3
    tail = limit - head
    omitted = len(text) - head - tail
    return f"{text[:head]}\n\n... [OUTPUT TRUNCATED: {omitted} chars omitted] ...\n\n{text[-tail:]}"


def _redacted_command_preview(command: List[str]) -> List[str]:
    preview = [Path(command[0]).name, *command[1:]]
    return [redact_sensitive_text(item) for item in preview]
