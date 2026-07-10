from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


class ExperimentRunnerError(ValueError):
    pass


@dataclass
class ExperimentRunResult:
    status: str
    script_path: str
    run_dir: str
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float
    result_json: Optional[Dict[str, Any]]
    artifacts: Dict[str, str]
    guardrail: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "script_path": self.script_path,
            "run_dir": self.run_dir,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "result_json": self.result_json,
            "artifacts": self.artifacts,
            "guardrail": self.guardrail,
        }


def validate_experiment_script(script_path: str, *, experiment_root: Path) -> Dict[str, Any]:
    root = experiment_root.resolve()
    candidate = Path(script_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ExperimentRunnerError("Experiment script must stay inside the configured experiment root.") from exc
    if not resolved.exists() or not resolved.is_file():
        raise ExperimentRunnerError("Experiment script does not exist inside the configured experiment root.")
    if resolved.suffix.lower() != ".py":
        raise ExperimentRunnerError("Only Python experiment scripts are supported by this restricted runner.")
    return {
        "allowed": True,
        "experiment_root": str(root),
        "script_path": str(resolved),
    }


def run_python_experiment(
    script_path: str,
    *,
    experiment_root: Path,
    artifact_root: Path,
    args: Optional[List[str]] = None,
    timeout_seconds: int = 300,
) -> ExperimentRunResult:
    guardrail = validate_experiment_script(script_path, experiment_root=experiment_root)
    safe_args = [str(item) for item in (args or [])][:50]
    for item in safe_args:
        if "\x00" in item:
            raise ExperimentRunnerError("Experiment arguments cannot contain NUL bytes.")

    artifact_root.mkdir(parents=True, exist_ok=True)
    run_dir = artifact_root / f"experiment_{uuid.uuid4().hex[:12]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    result_path = run_dir / "result.json"
    manifest_path = run_dir / "manifest.json"

    command = [sys.executable, guardrail["script_path"], *safe_args]
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
        )
        stdout = completed.stdout
        stderr = completed.stderr
        returncode = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = f"Experiment exceeded {timeout_seconds} seconds."
        returncode = 124

    duration = round(time.time() - started, 4)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    result_json = _extract_result_json(stdout, result_path)
    status = "complete" if returncode == 0 else "error"
    manifest = {
        "status": status,
        "command": _redacted_command(command),
        "script_path": guardrail["script_path"],
        "args": safe_args,
        "returncode": returncode,
        "duration_seconds": duration,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "result_path": str(result_path) if result_json is not None else None,
        "guardrail": guardrail,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return ExperimentRunResult(
        status=status,
        script_path=guardrail["script_path"],
        run_dir=str(run_dir),
        stdout=_visible_text(_strip_result_json_lines(stdout)),
        stderr=_visible_text(stderr),
        returncode=returncode,
        duration_seconds=duration,
        result_json=result_json,
        artifacts={
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "manifest": str(manifest_path),
            **({"result_json": str(result_path)} if result_json is not None else {}),
        },
        guardrail=guardrail,
    )


def _extract_result_json(stdout: str, result_path: Path) -> Optional[Dict[str, Any]]:
    for line in stdout.splitlines():
        if line.startswith("__RESULT_JSON__"):
            payload = line[len("__RESULT_JSON__") :]
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                result_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                return parsed
    return None


def _visible_text(value: str, limit: int = 20_000) -> str:
    compact = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", value or "")
    return compact[:limit]


def _strip_result_json_lines(stdout: str) -> str:
    return "\n".join(
        line for line in stdout.splitlines()
        if not line.startswith("__RESULT_JSON__")
    ) + ("\n" if stdout.endswith("\n") else "")


def _redacted_command(command: List[str]) -> List[str]:
    return [Path(command[0]).name, *command[1:]]
