from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def load_studio(tmp: str):
    os.environ["COSCIENTIST_KNOWLEDGE_BASE_DIR"] = str(Path(tmp) / "kb")
    sys.modules.pop("app", None)
    return importlib.import_module("app")


def persist_test_run(studio, run_id: str) -> None:
    record = studio.RunRecord(
        run_id=run_id,
        status="complete",
        created_at=1.0,
        updated_at=1.0,
        request=studio.RunRequest(research_goal="Validate SSH training workflow provenance"),
    )
    studio.persist_run_record(record)


class FakeSshTrainingResult:
    status = "complete"
    server_id = "c201-5080"
    ssh_alias = "c201-5080"
    command = "python train.py --smoke"
    workdir = None
    run_dir = "fake-run-dir"
    stdout = "training complete"
    stderr = ""
    returncode = 0
    duration_seconds = 0.01
    artifacts = {"stdout": "stdout.txt", "stderr": "stderr.txt", "manifest": "manifest.json"}
    guardrail = {"allowed": True, "server_id": "c201-5080"}

    def to_dict(self):
        return {
            "status": self.status,
            "server_id": self.server_id,
            "ssh_alias": self.ssh_alias,
            "command": self.command,
            "workdir": self.workdir,
            "run_dir": self.run_dir,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "artifacts": self.artifacts,
            "guardrail": self.guardrail,
        }


def test_ssh_training_registry_and_workflow_persist_result() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        persist_test_run(studio, "run_ssh_training")
        studio.ssh_training_status = lambda: {
            "available": True,
            "mode": "test_ready",
            "reason": "test ssh ready",
            "checked_at": 1.0,
            "metadata": {"servers": ["c201-4090", "c201-5080", "d437"]},
        }
        studio.run_ssh_training_command = lambda **kwargs: FakeSshTrainingResult()
        client = TestClient(studio.app)

        servers = client.get("/api/tools/ssh/servers")
        assert servers.status_code == 200
        assert {item["server_id"] for item in servers.json()["servers"]} == {"c201-4090", "c201-5080", "d437"}
        assert "ssh_c201_5080" in servers.json()["mcp_server_templates"]

        registry = client.get("/api/tools/registry", params={"toolset": "ssh_training"})
        assert registry.status_code == 200
        assert registry.json()["tools"][0]["name"] == "ssh.training_command"

        no_approval = client.post(
            "/api/tools/workflows/ssh-training-job",
            json={
                "server_id": "c201-5080",
                "command": "python train.py --smoke",
                "run_id": "run_ssh_training",
            },
        )
        assert no_approval.status_code == 428

        approved = client.post(
            "/api/tools/workflows/ssh-training-job",
            json={
                "server_id": "c201-5080",
                "command": "python train.py --smoke",
                "run_id": "run_ssh_training",
                "timeout_seconds": 60,
                "approval": {
                    "confirmed": True,
                    "scope": "ssh.training_command",
                    "reason": "test remote training",
                },
            },
        )
        assert approved.status_code == 200, approved.text
        job_id = approved.json()["job"]["job_id"]
        job = client.get(f"/api/tools/background-jobs/{job_id}")
        assert job.status_code == 200
        assert job.json()["status"] == "complete"
        assert job.json()["result_ref"]["server_id"] == "c201-5080"

        tool_calls = client.get("/api/runs/run_ssh_training/tool-calls")
        assert tool_calls.status_code == 200
        assert tool_calls.json()["count"] == 1
        assert tool_calls.json()["tool_calls"][0]["tool_name"] == "ssh.training_command"

        result_ref = job.json()["result_ref"]["tool_result"]
        loaded_result = client.get(f"/api/tools/results/{result_ref['result_id']}")
        assert loaded_result.status_code == 200
        assert loaded_result.json()["content"]["stdout"] == "training complete"

        repeated = client.post(
            "/api/tools/workflows/ssh-training-job",
            json={
                "server_id": "c201-5080",
                "command": "python train.py --smoke",
                "run_id": "run_ssh_training",
                "timeout_seconds": 60,
                "approval": {
                    "confirmed": True,
                    "scope": "ssh.training_command",
                },
            },
        )
        assert repeated.status_code == 409
        assert repeated.json()["detail"]["code"] == "repeated_identical_ssh_training_job"


def test_ssh_training_guardrail_blocks_sudo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        studio = load_studio(tmp)
        persist_test_run(studio, "run_ssh_blocked")
        studio.ssh_training_status = lambda: {
            "available": True,
            "mode": "test_ready",
            "reason": "test ssh ready",
            "checked_at": 1.0,
        }
        client = TestClient(studio.app)

        blocked = client.post(
            "/api/tools/workflows/ssh-training-job",
            json={
                "server_id": "d437",
                "command": "sudo nvidia-smi",
                "run_id": "run_ssh_blocked",
                "approval": {
                    "confirmed": True,
                    "scope": "ssh.training_command",
                    "reason": "test blocked",
                },
            },
        )
        assert blocked.status_code == 422
        assert blocked.json()["detail"]["code"] == "blocked_remote_command"
        tool_calls = client.get("/api/runs/run_ssh_blocked/tool-calls")
        assert tool_calls.status_code == 200
        assert tool_calls.json()["tool_calls"][0]["status"] == "blocked"


if __name__ == "__main__":
    test_ssh_training_registry_and_workflow_persist_result()
    test_ssh_training_guardrail_blocks_sudo()
    print("SSH training workflow API tests passed")
