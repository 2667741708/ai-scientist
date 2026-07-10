# Research Autopilot

Research Autopilot connects the existing literature, knowledge-base, hypothesis, experiment,
feedback, and ranking capabilities into one durable run ledger. Lattice is the primary human
control surface; the worker remains the execution boundary.

## Loop

Each completed research run can create one controller with these ordered stages:

1. `discover` — discover candidate literature.
2. `acquire_parse` — acquire permitted PDFs and parse them into the project library.
3. `ground` — rebuild claim-level evidence packets and the evidence gate.
4. `generate_rank` — bind the controller to the winning hypothesis from Review/Elo.
5. `plan` — save an `ExperimentProtocol` containing the hypothesis, evidence references,
   procedure, metric path, comparison operator, threshold, and compute contract hash.
6. `execute` — run a restricted local Python script or an approved registered SSH target.
7. `review` — compare only the preregistered metric and either pause for a researcher or write an
   approved structured experiment-evidence item.
8. `rerank` — create a continuation run and feed the experiment decision back into Review/Elo.
9. `outcome` — publish the updated `ResearchOutcome` and its source references.

The controller state is stored in `RunRecord.research_loop`. Work is enqueued as
`workflow.research_autopilot`, so process restarts do not erase the checkpoint.

## Autonomy and approvals

Modes describe defaults, not blanket permission:

- `manual` disables automatic stages.
- `guarded` automates evidence and planning, then pauses before compute and interpretation.
- `autonomous_compute` may execute and interpret only when every side effect has an exact,
  unexpired, unused mission grant.

Relevant exact scopes are:

- `mcp.literature_review`
- `experiment.background_job`
- `ssh.training_command` (also bound to one `server_id`)
- `experiment.feedback`

Grants have bounded `max_uses` counters. A grant is consumed and audited immediately before its
side effect. Wildcards are rejected. SSH commands containing inline passwords, tokens, or API keys
are rejected before persistence; secrets must be configured on the registered server.

## Experiment result contract

Local and remote experiment commands must emit exactly one line containing a JSON object:

```text
__RESULT_JSON__{"metrics":{"primary":0.84}}
```

The controller reads only the preregistered numeric `metric_path`. A satisfied threshold is a
screening signal, not proof of causality or scientific truth. Missing metrics, failed commands,
decision-boundary values, and ambiguous result markers become `inconclusive`.

Before compute begins, the controller persists a deterministic execution intent. If the worker
later sees a running or terminal job without a durable result reference, it stops at
`awaiting_human` rather than replaying the local or SSH command.

## API

Create the controller after the base run is complete:

```http
POST /api/runs/{run_id}/autopilot
```

Read its public, redacted state:

```http
GET /api/runs/{run_id}/autopilot
```

Resume a checkpoint with a compute target, evaluation rule, and exact grants:

```http
POST /api/runs/{run_id}/autopilot/resume
```

Pause only while the controller is queued or advancing at a safe checkpoint:

```http
POST /api/runs/{run_id}/autopilot/pause
```

When `review` is `awaiting_human`, use the existing experiment feedback endpoint:

```http
POST /api/runs/{run_id}/experiment-feedback
```

The same run cannot be started twice. Waiting states must be resumed, and a completed loop should
be extended with a continuation run. This avoids reusing an old idempotency key or silently
replaying an experiment.

## Scientific lineage boundary

Experiment evidence is inherited as support only when the continuation hypothesis text maps
exactly to its parent claim. Text-similar but revised claims receive the experiment as
`inherited_experiment_context` with relationship `insufficient`. If the rerank child cannot prove
exact experiment-evidence lineage, the parent controller stops for researcher review instead of
claiming the closed loop succeeded.

## Main implementation files

- `webapp/backend/research_autopilot.py` — pure policy, state, protocol, grant, and metric logic.
- `webapp/backend/app.py` — durable worker orchestration and API integration.
- `webapp/src/lattice/LatticeResearchApp.jsx` — stage timeline, checkpoints, compute authorization,
  and researcher interpretation controls.
- `webapp/backend/test_research_autopilot.py` — pure state/policy tests.
- `webapp/backend/test_research_autopilot_api.py` — API, resume, execution, and replay-safety tests.
