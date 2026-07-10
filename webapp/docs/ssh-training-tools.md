# SSH Training Tools

`open-coscientist/webapp` exposes remote training as an approval-backed workflow, not as a generic shell.

## Registered Hosts

The backend registers three workspace SSH aliases:

| server_id | SSH alias | Hardware |
| --- | --- | --- |
| `c201-4090` | `c201-4090` | 1 x RTX 4090 |
| `c201-5080` | `c201-5080` | 2 x RTX 5080 |
| `d437` | `d437` | 1 x TITAN RTX |

Credentials are not stored in project files. SSH uses the local `~/.ssh/config`.

## API

```text
GET /api/tools/ssh/servers
POST /api/tools/workflows/ssh-training-job
GET /api/tools/background-jobs/{job_id}
GET /api/tools/results/{result_id}
```

`POST /api/tools/workflows/ssh-training-job` requires:

```json
{
  "server_id": "c201-5080",
  "command": "python train.py --config configs/run.yaml",
  "phase": "experiment_execution",
  "timeout_seconds": 3600,
  "approval": {
    "confirmed": true,
    "scope": "ssh.training_command",
    "reason": "run approved training job"
  }
}
```

The workflow records a background job, writes stdout/stderr/manifest artifacts under the knowledge-base directory, and stores a redacted tool result.

## MCP Templates

`src/open_coscientist/config/tools.yaml` includes disabled stdio MCP templates:

```text
ssh_c201_4090
ssh_c201_5080
ssh_d437
```

They assume the remote host exposes a command named `coscientist-ssh-mcp`. Keep them disabled until that controlled MCP service exists on the target host.
