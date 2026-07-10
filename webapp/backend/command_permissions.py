from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Literal


CommandPermissionMode = Literal["request_approval", "approve_safe", "full_access"]

DEFAULT_COMMAND_PERMISSION_MODE: CommandPermissionMode = "request_approval"

COMMAND_PERMISSION_MODES: Dict[str, Dict[str, Any]] = {
    "request_approval": {
        "mode": "request_approval",
        "label": "请求批准",
        "description": "每次执行本地终端或远程 SSH 命令前都要求显式确认。",
        "approval_policy": "always",
    },
    "approve_safe": {
        "mode": "approve_safe",
        "label": "替我审批",
        "description": "只读/诊断命令自动批准；写入、网络、安装、远程同步等风险命令仍要求确认。",
        "approval_policy": "safe_commands_only",
    },
    "full_access": {
        "mode": "full_access",
        "label": "完全访问权限",
        "description": "允许命令工具免确认执行；仍保留硬性危险命令拦截、敏感信息脱敏和审计记录。",
        "approval_policy": "no_prompt_for_allowed_commands",
    },
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
    (re.compile(r"(^|[;&|]\s*)sudo(\s|$)", re.IGNORECASE), "sudo is not allowed in agent command workflows."),
    (re.compile(r"(^|[;&|]\s*)su(\s|$)", re.IGNORECASE), "user switching is not allowed."),
    (re.compile(r"\b(passwd|visudo)\b", re.IGNORECASE), "interactive account-management commands are blocked."),
    (re.compile(r"\b(shutdown|reboot|poweroff|halt)\b", re.IGNORECASE), "power-management commands are blocked."),
    (re.compile(r"\b(mkfs|fdisk|parted|diskpart|format)\b", re.IGNORECASE), "disk formatting/partitioning commands are blocked."),
    (re.compile(r"\bdd\s+.*\bof=", re.IGNORECASE), "raw disk write commands are blocked."),
    (re.compile(r":\s*\(\)\s*\{"), "fork-bomb style shell functions are blocked."),
    (
        re.compile(r"\b(?:curl|wget|Invoke-WebRequest|iwr)\b[^\n|;&]*\|\s*(?:bash|sh|python|python3|powershell|pwsh)\b", re.IGNORECASE),
        "download-and-execute pipelines are blocked.",
    ),
    (re.compile(r">\s*/etc/|>>\s*/etc/|\btee\s+/etc/", re.IGNORECASE), "writes to /etc are blocked."),
    (
        re.compile(r"(^|[;&|]\s*)rm\s+-[A-Za-z]*r[A-Za-z]*f?[A-Za-z]*\s+(?:/|~|\$HOME)(?:\s|$)", re.IGNORECASE),
        "recursive deletion of root/home is blocked.",
    ),
    (
        re.compile(r"\.ssh/(?:id_|authorized_keys|config)|~/.ssh|/\.ssh/|\\\.ssh\\", re.IGNORECASE),
        "direct access to SSH credential files is blocked.",
    ),
    (re.compile(r"\bSet-ExecutionPolicy\b", re.IGNORECASE), "changing PowerShell execution policy is blocked."),
    (re.compile(r"\breg\s+(?:delete|add|import)\b", re.IGNORECASE), "Windows registry mutation is blocked."),
)


REVIEW_COMMAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(^|[;&|]\s*)(rm|del|erase|rmdir|Remove-Item)\b", re.IGNORECASE), "deletes files or directories"),
    (re.compile(r"(^|[;&|]\s*)(mv|move|ren|rename|Move-Item|Rename-Item)\b", re.IGNORECASE), "moves or renames files"),
    (re.compile(r"(^|[;&|]\s*)(cp|copy|Copy-Item|scp|rsync)\b", re.IGNORECASE), "copies or transfers files"),
    (re.compile(r"\b(mkdir|New-Item|touch|Set-Content|Add-Content|Out-File)\b", re.IGNORECASE), "writes files or directories"),
    (re.compile(r"\b(git\s+(?:clone|pull|push|fetch|checkout|reset|clean|merge|rebase|commit))\b", re.IGNORECASE), "mutates git or network state"),
    (re.compile(r"\b(npm|pnpm|yarn|pip|conda|uv)\s+(?:install|add|update|remove|uninstall|sync)\b", re.IGNORECASE), "installs or removes packages"),
    (re.compile(r"\b(curl|wget|Invoke-WebRequest|iwr)\b", re.IGNORECASE), "accesses the network"),
    (re.compile(r"\b(tar\s+-x|Expand-Archive|unzip)\b", re.IGNORECASE), "extracts archives"),
    (re.compile(r"(^|[;&|]\s*)(python|python3|py|node|npm|npx|powershell|pwsh|bash|sh)\b", re.IGNORECASE), "runs an interpreter or package script"),
    (re.compile(r">|>>|\|\s*(?:tee|Set-Content|Out-File)\b", re.IGNORECASE), "writes through shell redirection or pipe"),
)


SAFE_COMMAND_PATTERN = re.compile(
    r"^\s*(?:"
    r"pwd|ls|dir|Get-ChildItem|gci|Get-Location|hostname|whoami|id|date|"
    r"echo|cat|type|Get-Content|gc|head|tail|wc|rg|grep|findstr|"
    r"git\s+(?:status|diff|log|show|rev-parse|remote)|"
    r"python\s+--version|python3\s+--version|py\s+--version|node\s+-v|npm\s+-v|npx\s+--version|"
    r"nvidia-smi|df|du|free|uname|where|which|Get-Command|sha256sum|Get-FileHash|"
    r"tar\s+-t|tar\s+-tzf|test\s+-[fde]|Test-Path"
    r")(?:\s|$)",
    re.IGNORECASE,
)


def redact_sensitive_text(value: str) -> str:
    return SECRET_PATTERN.sub("[REDACTED]", value or "")


def _normalize_mode(value: str | None) -> CommandPermissionMode:
    normalized = (value or "").strip().lower()
    if normalized in COMMAND_PERMISSION_MODES:
        return normalized  # type: ignore[return-value]
    return DEFAULT_COMMAND_PERMISSION_MODE


def command_permission_file(root: Path) -> Path:
    return root / "command_permission_policy.json"


def get_command_permission_policy(root: Path) -> Dict[str, Any]:
    configured = os.environ.get("COSCIENTIST_COMMAND_PERMISSION_MODE")
    if configured:
        mode = _normalize_mode(configured)
        source = "environment"
    else:
        path = command_permission_file(root)
        mode = DEFAULT_COMMAND_PERMISSION_MODE
        source = "default"
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                mode = _normalize_mode(str(payload.get("mode") or ""))
                source = str(payload.get("source") or "local_policy_file")
            except Exception:
                mode = DEFAULT_COMMAND_PERMISSION_MODE
                source = "invalid_policy_file_defaulted"
    return {
        **COMMAND_PERMISSION_MODES[mode],
        "source": source,
        "modes": list(COMMAND_PERMISSION_MODES.values()),
        "checked_at": time.time(),
    }


def set_command_permission_policy(root: Path, mode: str, *, actor: str | None = None) -> Dict[str, Any]:
    normalized = _normalize_mode(mode)
    if normalized != mode:
        raise ValueError("Unknown command permission mode.")
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": normalized,
        "source": "local_policy_file",
        "updated_at": time.time(),
        "updated_by": actor,
    }
    command_permission_file(root).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return get_command_permission_policy(root)


def classify_command_risk(command: str) -> Dict[str, Any]:
    text = (command or "").strip()
    if not text:
        return {"allowed": False, "risk_level": "blocked", "code": "empty_command", "message": "Command must not be empty."}
    if "\x00" in text:
        return {"allowed": False, "risk_level": "blocked", "code": "nul_byte", "message": "Command cannot contain NUL bytes."}
    if len(text) > 20_000:
        return {"allowed": False, "risk_level": "blocked", "code": "command_too_long", "message": "Command is too long."}
    for pattern, reason in BLOCKED_COMMAND_PATTERNS:
        if pattern.search(text):
            return {
                "allowed": False,
                "risk_level": "blocked",
                "code": "blocked_command",
                "message": reason,
                "matched": pattern.pattern,
            }
    review_matches = [
        {"reason": reason, "matched": pattern.pattern}
        for pattern, reason in REVIEW_COMMAND_PATTERNS
        if pattern.search(text)
    ]
    if review_matches:
        return {
            "allowed": True,
            "risk_level": "review",
            "code": "command_requires_review",
            "message": "Command may mutate files, access the network, install packages, or run arbitrary code.",
            "matches": review_matches[:6],
        }
    if SAFE_COMMAND_PATTERN.search(text):
        return {
            "allowed": True,
            "risk_level": "safe",
            "code": "safe_command",
            "message": "Command matches the safe diagnostic/read-only profile.",
        }
    return {
        "allowed": True,
        "risk_level": "review",
        "code": "unclassified_command_requires_review",
        "message": "Command is not recognized as a simple read-only diagnostic command.",
    }


def command_requires_approval(policy: Dict[str, Any], risk: Dict[str, Any]) -> bool:
    mode = _normalize_mode(str(policy.get("mode") or ""))
    if mode == "full_access":
        return False
    if mode == "approve_safe" and risk.get("risk_level") == "safe":
        return False
    return True
