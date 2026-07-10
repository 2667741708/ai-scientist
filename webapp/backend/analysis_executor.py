from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


FORBIDDEN_NAMES = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "globals",
    "locals",
    "open",
    "input",
    "help",
    "breakpoint",
    "getattr",
    "setattr",
    "delattr",
    "vars",
    "dir",
    "os",
    "sys",
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "pathlib",
    "shutil",
    "ctypes",
}

FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.ClassDef,
    ast.AsyncFunctionDef,
    ast.With,
    ast.AsyncWith,
    ast.Try,
)

RUNNER = r"""
import json
import math
import statistics
import traceback

SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}

namespace = {
    "__builtins__": SAFE_BUILTINS,
    "math": math,
    "statistics": statistics,
    "json": json,
    "result": None,
}

try:
    code = open("analysis_user_code.py", "r", encoding="utf-8").read()
    exec(compile(code, "analysis_user_code.py", "exec"), namespace, namespace)
    if namespace.get("result") is not None:
        print("__RESULT_JSON__" + json.dumps(namespace["result"], ensure_ascii=False, default=str))
except Exception:
    traceback.print_exc()
    raise
"""


@dataclass
class AnalysisExecutionResult:
    status: str
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float
    work_dir: str
    result_json: Any = None
    guardrail: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "work_dir": self.work_dir,
            "result_json": self.result_json,
            "guardrail": self.guardrail or {},
        }


def validate_restricted_python(code: str) -> Dict[str, Any]:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return {
            "allowed": False,
            "code": "syntax_error",
            "message": str(exc),
        }

    violations: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            violations.append(
                {
                    "code": "forbidden_syntax",
                    "node": type(node).__name__,
                    "line": getattr(node, "lineno", None),
                }
            )
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            violations.append(
                {
                    "code": "forbidden_name",
                    "name": node.id,
                    "line": getattr(node, "lineno", None),
                }
            )
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            violations.append(
                {
                    "code": "forbidden_dunder_attribute",
                    "name": node.attr,
                    "line": getattr(node, "lineno", None),
                }
            )
    if violations:
        return {
            "allowed": False,
            "code": "restricted_python_guardrail_failed",
            "message": "Code uses syntax or names outside the restricted analysis profile.",
            "violations": violations[:20],
        }
    return {
        "allowed": True,
        "code": "restricted_python_guardrail_passed",
        "message": "Code passed the restricted analysis AST guard.",
    }


def execute_restricted_python(
    code: str,
    *,
    timeout_seconds: int,
    root_dir: Path,
) -> AnalysisExecutionResult:
    guardrail = validate_restricted_python(code)
    if not guardrail["allowed"]:
        return AnalysisExecutionResult(
            status="blocked",
            stdout="",
            stderr=guardrail["message"],
            returncode=126,
            duration_seconds=0.0,
            work_dir="",
            guardrail=guardrail,
        )

    root_dir.mkdir(parents=True, exist_ok=True)
    work_dir = root_dir / f"analysis_{uuid.uuid4().hex[:12]}"
    work_dir.mkdir(parents=True, exist_ok=False)
    (work_dir / "analysis_user_code.py").write_text(code, encoding="utf-8")
    (work_dir / "analysis_runner.py").write_text(textwrap.dedent(RUNNER), encoding="utf-8")

    started = time.time()
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "analysis_runner.py"],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={},
        )
    except subprocess.TimeoutExpired as exc:
        duration = round(time.time() - started, 4)
        return AnalysisExecutionResult(
            status="error",
            stdout=exc.stdout or "",
            stderr=f"Analysis exceeded {timeout_seconds} seconds.",
            returncode=124,
            duration_seconds=duration,
            work_dir=str(work_dir),
            guardrail=guardrail,
        )
    duration = round(time.time() - started, 4)
    stdout = completed.stdout
    result_json = None
    lines = []
    for line in stdout.splitlines():
        if line.startswith("__RESULT_JSON__"):
            try:
                result_json = line.removeprefix("__RESULT_JSON__")
            except AttributeError:
                result_json = line[len("__RESULT_JSON__") :]
        else:
            lines.append(line)
    visible_stdout = "\n".join(lines)
    if isinstance(result_json, str):
        import json

        try:
            result_json = json.loads(result_json)
        except Exception:
            pass
    return AnalysisExecutionResult(
        status="complete" if completed.returncode == 0 else "error",
        stdout=visible_stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
        duration_seconds=duration,
        work_dir=str(work_dir),
        result_json=result_json,
        guardrail=guardrail,
    )
