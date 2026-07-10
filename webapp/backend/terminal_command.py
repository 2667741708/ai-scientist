from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from backend.command_permissions import classify_command_risk, redact_sensitive_text
except ModuleNotFoundError:
    from command_permissions import classify_command_risk, redact_sensitive_text


class TerminalCommandError(ValueError):
    pass


@dataclass
class TerminalCommandResult:
    status: str
    command: str
    workdir: str
    shell: str
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
            "command": redact_sensitive_text(self.command),
            "workdir": self.workdir,
            "shell": self.shell,
            "run_dir": self.run_dir,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "artifacts": self.artifacts,
            "guardrail": self.guardrail,
        }


def terminal_command_status() -> Dict[str, Any]:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    bash = shutil.which("bash")
    if os.name == "nt":
        available = bool(powershell)
        shell = powershell
    else:
        available = bool(bash)
        shell = bash
    return {
        "available": available,
        "mode": "ready" if available else "missing_shell",
        "reason": (
            f"Local terminal command workflow can use {shell}."
            if available
            else "No supported shell was found on PATH."
        ),
        "checked_at": time.time(),
        "metadata": {
            "preferred_shell": shell,
            "python": sys.executable,
        },
    }


def resolve_terminal_workdir(workdir: Optional[str], *, default_root: Path, allow_any: bool) -> Path:
    if not workdir or not workdir.strip():
        return default_root.resolve()
    raw = Path(workdir.strip())
    resolved = (raw if raw.is_absolute() else default_root / raw).resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise TerminalCommandError("Terminal workdir must be an existing directory.")
    if not allow_any:
        root = default_root.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise TerminalCommandError("Terminal workdir must stay inside the project workspace unless full access is enabled.") from exc
    return resolved


def validate_terminal_command(command: str, *, workdir: Optional[str], default_root: Path, allow_any_workdir: bool) -> Dict[str, Any]:
    risk = classify_command_risk(command)
    if not risk.get("allowed"):
        return risk
    try:
        resolved = resolve_terminal_workdir(workdir, default_root=default_root, allow_any=allow_any_workdir)
    except TerminalCommandError as exc:
        return {
            "allowed": False,
            "risk_level": "blocked",
            "code": "invalid_workdir",
            "message": str(exc),
        }
    return {
        **risk,
        "workdir": str(resolved),
        "risk_boundary": "local_terminal_exec",
    }


def run_terminal_command(
    *,
    command: str,
    artifact_root: Path,
    timeout_seconds: int,
    default_root: Path,
    workdir: Optional[str] = None,
    allow_any_workdir: bool = False,
    job_id: Optional[str] = None,
) -> TerminalCommandResult:
    guardrail = validate_terminal_command(
        command,
        workdir=workdir,
        default_root=default_root,
        allow_any_workdir=allow_any_workdir,
    )
    resolved_workdir = guardrail.get("workdir") or str(default_root.resolve())
    artifact_root.mkdir(parents=True, exist_ok=True)
    run_dir = artifact_root / (job_id or f"terminal_{uuid.uuid4().hex[:12]}")
    run_dir.mkdir(parents=True, exist_ok=False)
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    manifest_path = run_dir / "manifest.json"

    if not guardrail.get("allowed"):
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(guardrail.get("message", "Blocked by guardrail."), encoding="utf-8")
        manifest = {
            "status": "blocked",
            "command": redact_sensitive_text(command),
            "workdir": resolved_workdir,
            "guardrail": guardrail,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return TerminalCommandResult(
            status="blocked",
            command=command,
            workdir=resolved_workdir,
            shell="blocked",
            run_dir=str(run_dir),
            stdout="",
            stderr=guardrail.get("message", "Blocked by guardrail."),
            returncode=126,
            duration_seconds=0.0,
            artifacts={"stdout": str(stdout_path), "stderr": str(stderr_path), "manifest": str(manifest_path)},
            guardrail=guardrail,
        )

    shell_name = "powershell" if os.name == "nt" else "bash"
    if os.name == "nt":
        shell = shutil.which("powershell") or shutil.which("pwsh")
        if not shell:
            raise TerminalCommandError("PowerShell is not available on PATH.")
        utf8_prefix = "$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false);"
        process_command = [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"{utf8_prefix} {command}",
        ]
    else:
        shell = shutil.which("bash")
        if not shell:
            raise TerminalCommandError("bash is not available on PATH.")
        process_command = [
            shell,
            "-lc",
            f"export LANG=C.UTF-8 LC_ALL=C.UTF-8; {command}",
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
            process_command,
            cwd=resolved_workdir,
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
            stderr_fh.write(f"\nTerminal command exceeded {timeout_seconds} seconds.\n")

    duration = round(time.time() - started, 4)
    stdout = _visible_file_text(stdout_path)
    stderr = _visible_file_text(stderr_path)
    manifest = {
        "status": status,
        "command": redact_sensitive_text(command),
        "workdir": resolved_workdir,
        "returncode": returncode,
        "duration_seconds": duration,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "guardrail": guardrail,
        "shell": shell_name,
        "command_preview": _redacted_command_preview(process_command),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return TerminalCommandResult(
        status=status,
        command=command,
        workdir=resolved_workdir,
        shell=shell_name,
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
    text = redact_sensitive_text(text)
    if len(text) <= limit:
        return text
    head = limit // 3
    tail = limit - head
    omitted = len(text) - head - tail
    return f"{text[:head]}\n\n... [OUTPUT TRUNCATED: {omitted} chars omitted] ...\n\n{text[-tail:]}"


def _redacted_command_preview(command: list[str]) -> list[str]:
    preview = [Path(command[0]).name, *command[1:]]
    return [redact_sensitive_text(shlex.quote(item) if " " in item else item) for item in preview]
