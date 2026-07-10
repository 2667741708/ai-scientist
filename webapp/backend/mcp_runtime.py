from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parents[2]
WEBAPP_ROOT = ROOT / "webapp"
LOG_ROOT = WEBAPP_ROOT / ".codex" / "run-logs"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.getenv("COSCIENTIST_MCP_PORT", "8888"))
_last_started_process: Optional[subprocess.Popen] = None


def _is_port_open(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def literature_mcp_runtime_status() -> Dict[str, Any]:
    server_file = ROOT / "mcp_server" / "server.py"
    running = _is_port_open()
    process_running = _last_started_process is not None and _last_started_process.poll() is None
    return {
        "service": "literature_mcp",
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "url": f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/mcp",
        "root": str(ROOT),
        "server_file_exists": server_file.exists(),
        "running": running,
        "managed_process_running": process_running,
        "startable": server_file.exists(),
        "checked_at": time.time(),
    }


def start_literature_mcp_service() -> Dict[str, Any]:
    global _last_started_process

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    status = literature_mcp_runtime_status()
    if status["running"]:
        return {
            **status,
            "started": False,
            "message": "文献 MCP 服务已经在本机监听。",
        }
    if not status["startable"]:
        return {
            **status,
            "started": False,
            "message": "当前仓库缺少 mcp_server/server.py，无法启动文献 MCP 服务。",
        }

    stdout_path = LOG_ROOT / "literature-mcp.stdout.log"
    stderr_path = LOG_ROOT / "literature-mcp.stderr.log"
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "mcp_server.server:app",
        "--host",
        DEFAULT_HOST,
        "--port",
        str(DEFAULT_PORT),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        _last_started_process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            close_fds=os.name != "nt",
            creationflags=creationflags,
        )

    deadline = time.time() + 8
    while time.time() < deadline:
        if _is_port_open():
            return {
                **literature_mcp_runtime_status(),
                "started": True,
                "pid": _last_started_process.pid,
                "stdout_log": str(stdout_path),
                "stderr_log": str(stderr_path),
                "message": "文献 MCP 服务已启动。",
            }
        if _last_started_process.poll() is not None:
            break
        time.sleep(0.25)

    return {
        **literature_mcp_runtime_status(),
        "started": False,
        "pid": _last_started_process.pid if _last_started_process else None,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "message": "已尝试启动文献 MCP 服务，但端口尚未变为可用。请检查日志。",
    }
