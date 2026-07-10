from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    os.environ["COSCIENTIST_AUTH_ROOT"] = str(Path(tmp) / "auth")
    os.environ["COSCIENTIST_AUTH_DB_PATH"] = str(Path(tmp) / "auth" / "accounts.sqlite3")
    os.environ.pop("COSCIENTIST_COMMAND_PERMISSION_MODE", None)
    sys.modules.pop("app", None)
    sys.modules.pop("auth_store", None)
    return importlib.import_module("app")


def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={
            "email": "haomingwang@stumail.ysu.edu.cn",
            "password": "ResearchAdmin123!",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_terminal_command_permission_modes_and_guardrail() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        studio = load_studio(tmp)
        client = TestClient(studio.app)
        headers = admin_headers(client)

        permissions = client.get("/api/tools/command-permissions")
        assert permissions.status_code == 200
        assert permissions.json()["policy"]["mode"] == "request_approval"

        no_approval = client.post(
            "/api/tools/workflows/terminal-command",
            headers=headers,
            json={
                "command": "echo terminal_ok",
                "timeout_seconds": 10,
            },
        )
        assert no_approval.status_code == 428
        assert no_approval.json()["detail"]["expected_scope"] == "terminal.command"

        os.environ["COSCIENTIST_COMMAND_PERMISSION_MODE"] = "approve_safe"
        auto_approved = client.post(
            "/api/tools/workflows/terminal-command",
            headers=headers,
            json={
                "command": "echo terminal_ok",
                "timeout_seconds": 10,
            },
        )
        assert auto_approved.status_code == 200, auto_approved.text
        payload = auto_approved.json()
        assert payload["approval"]["granted_by"] == "command_permission_mode"
        assert payload["command_risk"]["risk_level"] == "safe"

        job_id = payload["job"]["job_id"]
        job = client.get(f"/api/tools/background-jobs/{job_id}")
        assert job.status_code == 200
        assert job.json()["status"] == "complete"
        result_id = job.json()["result_ref"]["tool_result"]["result_id"]
        result = client.get(f"/api/tools/results/{result_id}")
        assert result.status_code == 200
        assert "terminal_ok" in result.json()["content"]["stdout"]

        os.environ["COSCIENTIST_COMMAND_PERMISSION_MODE"] = "full_access"
        blocked = client.post(
            "/api/tools/workflows/terminal-command",
            headers=headers,
            json={
                "command": "sudo whoami",
                "timeout_seconds": 10,
            },
        )
        assert blocked.status_code == 422
        assert blocked.json()["detail"]["command_risk"]["risk_level"] == "blocked"
        os.environ.pop("COSCIENTIST_COMMAND_PERMISSION_MODE", None)


if __name__ == "__main__":
    test_terminal_command_permission_modes_and_guardrail()
    print("command permission workflow API tests passed")
