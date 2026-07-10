from __future__ import annotations

import tempfile
from pathlib import Path

from analysis_executor import execute_restricted_python, validate_restricted_python


def test_restricted_python_executes_small_analysis_and_captures_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = execute_restricted_python(
            """
values = [1, 2, 3, 4]
print("analysis ready")
result = {
    "mean": statistics.mean(values),
    "spread": max(values) - min(values),
}
""",
            timeout_seconds=5,
            root_dir=Path(tmp),
        )

    assert result.status == "complete"
    assert result.returncode == 0
    assert result.stdout == "analysis ready"
    assert result.result_json == {"mean": 2.5, "spread": 3}
    assert result.guardrail and result.guardrail["allowed"] is True


def test_restricted_python_blocks_imports_and_filesystem_access() -> None:
    import_guard = validate_restricted_python("import os\nresult = os.listdir('.')\n")
    assert import_guard["allowed"] is False
    assert any(item["node"] == "Import" for item in import_guard["violations"])

    with tempfile.TemporaryDirectory() as tmp:
        result = execute_restricted_python(
            "open('leak.txt', 'w').write('x')\n",
            timeout_seconds=5,
            root_dir=Path(tmp),
        )

    assert result.status == "blocked"
    assert result.returncode == 126
    assert result.guardrail and result.guardrail["code"] == "restricted_python_guardrail_failed"

