from __future__ import annotations

import copy
import hashlib
import json
import math
import operator
import re
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


AUTONOMY_MODES: Tuple[str, ...] = ("manual", "guarded", "autonomous_compute")
LOOP_STAGES: Tuple[str, ...] = (
    "discover",
    "acquire_parse",
    "ground",
    "generate_rank",
    "plan",
    "execute",
    "review",
    "rerank",
    "outcome",
)
LOOP_STAGE_LABELS = {
    "discover": "Discover literature",
    "acquire_parse": "Acquire and parse papers",
    "ground": "Ground claims in evidence",
    "generate_rank": "Generate and rank hypotheses",
    "plan": "Preregister experiment",
    "execute": "Execute experiment",
    "review": "Review evidence and results",
    "rerank": "Rerank hypotheses",
    "outcome": "Publish research outcome",
}

POLICY_SCHEMA_VERSION = 1
LOOP_SCHEMA_VERSION = 1
PROTOCOL_SCHEMA_VERSION = 1
MAX_CYCLES = 12
MAX_GRANTS = 24
MAX_GRANT_USES = 100
RESULT_JSON_MARKER = "__RESULT_JSON__"

_AUTO_FIELDS = (
    "auto_evidence",
    "auto_plan",
    "auto_execute",
    "auto_interpret",
    "auto_rerank",
)
_STAGE_STATUSES = {
    "pending",
    "ready",
    "running",
    "blocked",
    "limited",
    "awaiting_input",
    "awaiting_approval",
    "awaiting_human",
    "complete",
    "skipped",
    "error",
    "cancelled",
}
_OPERATORS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}
_SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")

SCIENTIFIC_BOUNDARY = (
    "Execution success only shows that the preregistered procedure ran and produced the named "
    "metric. The metric comparison is a deterministic screening signal, not proof of causality or "
    "scientific truth. Source quality, confounding, statistical power, failed runs, and contradictory "
    "evidence remain subject to expert review."
)


class AutopilotValidationError(ValueError):
    """Raised when persisted autopilot data cannot be evaluated safely."""


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "on"}:
            return True
        if normalized in {"false", "no", "0", "off"}:
            return False
    return default


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _finite_number(value: Any, *, field: str, allow_none: bool = False) -> Optional[float]:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AutopilotValidationError(f"{field} must be a finite numeric value.")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise AutopilotValidationError(f"{field} must be a finite numeric value.")
    return parsed


def _normalize_compute(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {"kind": "none"}
    if isinstance(raw, str):
        value = raw.strip()
        if not value or value == "none":
            return {"kind": "none"}
        if value in {"local", "local_python"}:
            return {"kind": "local_python"}
        return {"kind": "ssh", "server_id": value[:80]}
    if not isinstance(raw, Mapping):
        return {"kind": "none"}

    raw_kind = str(raw.get("kind") or raw.get("type") or "none").strip().lower()
    kind_aliases = {
        "local": "local_python",
        "python": "local_python",
        "remote": "ssh",
        "server": "ssh",
    }
    kind = kind_aliases.get(raw_kind, raw_kind)
    if kind not in {"none", "local_python", "ssh"}:
        kind = "none"
    if kind == "none":
        return {"kind": "none"}

    normalized: Dict[str, Any] = {"kind": kind}
    workdir = raw.get("workdir")
    if isinstance(workdir, str) and workdir.strip():
        normalized["workdir"] = workdir.strip()[:600]
    if kind == "ssh":
        server_id = raw.get("server_id") or raw.get("id") or raw.get("target")
        if not isinstance(server_id, str) or not server_id.strip():
            return {"kind": "none"}
        normalized["server_id"] = server_id.strip()[:80]
        command = raw.get("command")
        if isinstance(command, str) and command.strip():
            normalized["command"] = command.strip()[:20_000]
    else:
        script_path = raw.get("script_path")
        if isinstance(script_path, str) and script_path.strip():
            normalized["script_path"] = script_path.strip()[:1200]
        args = raw.get("args")
        if isinstance(args, Sequence) and not isinstance(args, (str, bytes, bytearray)):
            normalized["args"] = [str(item)[:1000] for item in list(args)[:50]]
    normalized["timeout_seconds"] = _bounded_int(
        raw.get("timeout_seconds"),
        3600 if kind == "ssh" else 300,
        1,
        86_400 if kind == "ssh" else 3_600,
    )
    return normalized


def _normalize_evaluation(raw: Any) -> Dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}
    metric_path = str(source.get("metric_path") or "metrics.primary").strip()
    metric_path = metric_path[:240] or "metrics.primary"
    comparison = str(source.get("operator") or ">=").strip()
    if comparison not in _OPERATORS:
        comparison = ">="
    threshold: Optional[float]
    try:
        threshold = _finite_number(source.get("threshold"), field="evaluation.threshold", allow_none=True)
    except AutopilotValidationError:
        threshold = None
    normalized: Dict[str, Any] = {
        "metric_path": metric_path,
        "operator": comparison,
        "threshold": threshold,
    }
    margin = source.get("inconclusive_margin")
    if margin is not None:
        try:
            normalized["inconclusive_margin"] = abs(
                _finite_number(margin, field="evaluation.inconclusive_margin") or 0.0
            )
        except AutopilotValidationError:
            pass
    return normalized


def _normalize_grants(raw: Any, *, default_max_uses: int) -> List[Dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return []
    normalized: List[Dict[str, Any]] = []
    seen: set[Tuple[str, Optional[str]]] = set()
    for item in list(raw)[:MAX_GRANTS]:
        if isinstance(item, str):
            source: Mapping[str, Any] = {"scope": item, "confirmed": True}
        elif isinstance(item, Mapping):
            source = item
        else:
            continue
        scope = str(source.get("scope") or "").strip()
        if not _SCOPE_RE.fullmatch(scope) or scope == "*":
            continue
        server_id_value = source.get("server_id")
        server_id = (
            server_id_value.strip()[:80]
            if isinstance(server_id_value, str) and server_id_value.strip()
            else None
        )
        key = (scope, server_id)
        if key in seen:
            continue
        seen.add(key)
        max_uses = _bounded_int(
            source.get("max_uses"),
            default_max_uses,
            1,
            MAX_GRANT_USES,
        )
        used = _bounded_int(source.get("used"), 0, 0, max_uses)
        grant: Dict[str, Any] = {
            "confirmed": _as_bool(source.get("confirmed"), False),
            "scope": scope,
            "reason": str(source.get("reason") or "")[:500],
            "max_uses": max_uses,
            "used": used,
        }
        if server_id:
            grant["server_id"] = server_id
        expires_at = source.get("expires_at")
        if isinstance(expires_at, (int, float)) and not isinstance(expires_at, bool):
            if math.isfinite(float(expires_at)):
                grant["expires_at"] = float(expires_at)
        normalized.append(grant)
    return normalized


def normalize_policy(raw: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Normalize a persisted, bounded per-run autonomy policy.

    The policy only describes what the loop may attempt. Risky actions still need an exact,
    unexpired, unused grant for the endpoint scope and (for SSH) the selected server.
    """

    source: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    mode = str(source.get("mode") or "guarded").strip().lower()
    if mode not in AUTONOMY_MODES:
        mode = "guarded"
    defaults = {
        "manual": {
            "max_cycles": 1,
            "auto_evidence": False,
            "auto_plan": False,
            "auto_execute": False,
            "auto_interpret": False,
            "auto_rerank": False,
        },
        "guarded": {
            "max_cycles": 3,
            "auto_evidence": True,
            "auto_plan": True,
            "auto_execute": False,
            "auto_interpret": False,
            "auto_rerank": False,
        },
        "autonomous_compute": {
            "max_cycles": 5,
            "auto_evidence": True,
            "auto_plan": True,
            "auto_execute": True,
            "auto_interpret": True,
            "auto_rerank": True,
        },
    }[mode]
    max_cycles = _bounded_int(source.get("max_cycles"), defaults["max_cycles"], 1, MAX_CYCLES)
    policy: Dict[str, Any] = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "mode": mode,
        "max_cycles": max_cycles,
    }
    for field in _AUTO_FIELDS:
        policy[field] = _as_bool(source.get(field), bool(defaults[field]))
    if mode == "manual":
        for field in _AUTO_FIELDS:
            policy[field] = False
    policy["compute"] = _normalize_compute(source.get("compute", source.get("compute_target")))
    policy["evaluation"] = _normalize_evaluation(source.get("evaluation"))
    policy["continue_on_limited_evidence"] = _as_bool(
        source.get("continue_on_limited_evidence"),
        False,
    )
    policy["grants"] = _normalize_grants(source.get("grants"), default_max_uses=max_cycles)
    return policy


normalize_autonomy_policy = normalize_policy


def execution_scope(compute: Optional[Mapping[str, Any]] = None) -> Optional[str]:
    """Return the existing workflow approval scope required by a compute target."""

    normalized = _normalize_compute(compute)
    if normalized["kind"] == "local_python":
        return "experiment.background_job"
    if normalized["kind"] == "ssh":
        return "ssh.training_command"
    return None


required_execution_scope = execution_scope


def exact_grant(
    policy_or_grants: Any,
    scope: str,
    server_id: Optional[str] = None,
    *,
    compute_target: Optional[Mapping[str, Any]] = None,
    now: Optional[float] = None,
) -> bool:
    """Check an exact approval scope; wildcards and cross-server SSH grants never match."""

    if not isinstance(scope, str) or not _SCOPE_RE.fullmatch(scope) or scope == "*":
        return False
    if isinstance(policy_or_grants, Mapping):
        policy = normalize_policy(policy_or_grants)
        grants = policy["grants"]
        compute = _normalize_compute(compute_target) if compute_target is not None else policy["compute"]
        if server_id is None and scope == "ssh.training_command" and compute.get("kind") == "ssh":
            server_id = compute.get("server_id")
    else:
        policy = normalize_policy({"grants": policy_or_grants})
        grants = policy["grants"]
    for grant in grants:
        if not grant["confirmed"] or grant["scope"] != scope:
            continue
        grant_server = grant.get("server_id")
        if server_id is not None and grant_server != server_id:
            continue
        if server_id is None and grant_server is not None:
            continue
        if grant["used"] >= grant["max_uses"]:
            continue
        expires_at = grant.get("expires_at")
        if expires_at is not None and (time.time() if now is None else now) >= expires_at:
            continue
        return True
    return False


has_exact_approval_grant = exact_grant


def consume_exact_grant(
    policy: Mapping[str, Any],
    scope: str,
    server_id: Optional[str] = None,
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Return a new policy with one use consumed from the matching bounded grant."""

    normalized = normalize_policy(policy)
    if not exact_grant(normalized, scope, server_id, now=now):
        raise AutopilotValidationError(f"No exact, active approval grant for scope {scope!r}.")
    target_server = server_id
    if (
        target_server is None
        and scope == "ssh.training_command"
        and normalized["compute"].get("kind") == "ssh"
    ):
        target_server = normalized["compute"].get("server_id")
    for grant in normalized["grants"]:
        if grant["scope"] == scope and grant.get("server_id") == target_server:
            grant["used"] += 1
            break
    return normalized


def _fresh_stages() -> List[Dict[str, Any]]:
    return [
        {
            "id": stage,
            "label": LOOP_STAGE_LABELS[stage],
            "order": index,
            "status": "ready" if index == 0 else "pending",
            "attempts": 0,
            "message": "",
        }
        for index, stage in enumerate(LOOP_STAGES)
    ]


def build_loop_state(
    policy: Optional[Mapping[str, Any]] = None,
    run_id: Optional[str] = None,
    existing: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build or repair a durable, user-visible research-loop state."""

    if isinstance(policy, str) and isinstance(run_id, Mapping):
        policy, run_id = run_id, policy
    source = existing if isinstance(existing, Mapping) else {}
    effective_policy = normalize_policy(policy or source.get("policy"))
    stages = _fresh_stages()
    persisted_stages = source.get("stages")
    if isinstance(persisted_stages, Sequence):
        by_id = {
            str(item.get("id")): item
            for item in persisted_stages
            if isinstance(item, Mapping) and item.get("id") in LOOP_STAGES
        }
        for stage in stages:
            persisted = by_id.get(stage["id"])
            if not persisted:
                continue
            status = str(persisted.get("status") or "pending")
            stage["status"] = status if status in _STAGE_STATUSES else "pending"
            stage["attempts"] = _bounded_int(persisted.get("attempts"), 0, 0, 10_000)
            stage["message"] = str(persisted.get("message") or "")[:2000]
            for key in ("started_at", "completed_at", "updated_at", "artifacts", "summary", "details"):
                if key in persisted:
                    stage[key] = copy.deepcopy(persisted[key])

    current_stage = str(source.get("current_stage") or "discover")
    if current_stage not in LOOP_STAGES:
        current_stage = "discover"
    status = str(source.get("status") or "ready")
    if status not in {
        "ready",
        "queued",
        "running",
        "waiting_approval",
        "awaiting_approval",
        "awaiting_input",
        "awaiting_human",
        "reranking",
        "paused",
        "complete",
        "error",
        "cancelled",
    }:
        status = "ready"
    cycle = _bounded_int(source.get("cycle"), 1, 1, effective_policy["max_cycles"])
    state: Dict[str, Any] = {
        "schema_version": LOOP_SCHEMA_VERSION,
        "run_id": run_id or source.get("run_id"),
        "status": status,
        "current_stage": current_stage,
        "cycle": cycle,
        "max_cycles": effective_policy["max_cycles"],
        "policy": effective_policy,
        "pending_approvals": [],
        "approval_history": copy.deepcopy(source.get("approval_history") or []),
        "stages": stages,
    }
    for key in (
        "selected_hypothesis_index",
        "selected_hypothesis_id",
        "experiment_protocol",
        "evidence_expansion",
        "execution",
        "interpretation",
        "interpretation_evidence_id",
        "feedback_id",
        "rerank_run_id",
        "rerank_outcome",
        "resume_count",
        "boundary",
    ):
        if key in source:
            state[key] = copy.deepcopy(source[key])
    pending = source.get("pending_approvals")
    if isinstance(pending, Sequence):
        for item in pending:
            if not isinstance(item, Mapping):
                continue
            scope = str(item.get("scope") or "")
            stage = str(item.get("stage") or current_stage)
            if _SCOPE_RE.fullmatch(scope) and stage in LOOP_STAGES:
                state["pending_approvals"].append(copy.deepcopy(dict(item)))
    return state


def _stage_record(state: Dict[str, Any], stage: str) -> Dict[str, Any]:
    for record in state["stages"]:
        if record["id"] == stage:
            return record
    raise AutopilotValidationError(f"Unknown research-loop stage: {stage!r}.")


def update_loop_stage(
    state: Mapping[str, Any],
    stage: str,
    status: str,
    *,
    message: Optional[str] = None,
    summary: Optional[str] = None,
    details: Optional[Mapping[str, Any]] = None,
    artifacts: Optional[Sequence[Mapping[str, Any]]] = None,
    at: Optional[float] = None,
) -> Dict[str, Any]:
    """Purely update one loop stage and derive the public top-level status."""

    if stage not in LOOP_STAGES:
        raise AutopilotValidationError(f"Unknown research-loop stage: {stage!r}.")
    if status not in _STAGE_STATUSES:
        raise AutopilotValidationError(f"Unknown research-loop stage status: {status!r}.")
    updated = build_loop_state(existing=state)
    record = _stage_record(updated, stage)
    previous = record["status"]
    record["status"] = status
    if status == "running" and previous != "running":
        record["attempts"] += 1
        if at is not None:
            record["started_at"] = at
    if status in {"complete", "skipped"} and at is not None:
        record["completed_at"] = at
    if at is not None:
        record["updated_at"] = at
    resolved_message = message if message is not None else summary
    if resolved_message is not None:
        record["message"] = resolved_message[:2000]
        record["summary"] = resolved_message[:2000]
    if details is not None:
        record["details"] = copy.deepcopy(dict(details))
    if artifacts is not None:
        record["artifacts"] = copy.deepcopy(list(artifacts))

    if status == "blocked":
        updated["status"] = "waiting_approval"
        updated["current_stage"] = stage
    elif status in {"awaiting_input", "awaiting_approval", "awaiting_human"}:
        updated["status"] = status
        updated["current_stage"] = stage
    elif status == "cancelled":
        updated["status"] = "cancelled"
        updated["current_stage"] = stage
    elif status == "error":
        updated["status"] = "error"
        updated["current_stage"] = stage
    elif stage == "outcome" and status == "complete":
        updated["status"] = "complete"
        updated["current_stage"] = "outcome"
    elif status in {"running", "ready", "limited"}:
        updated["status"] = "running" if status == "running" else "ready"
        updated["current_stage"] = stage
    return updated


def advance_loop_state(
    state: Mapping[str, Any],
    *,
    message: Optional[str] = None,
    at: Optional[float] = None,
) -> Dict[str, Any]:
    """Complete the current stage and start the next ordered stage."""

    normalized = build_loop_state(existing=state)
    current = normalized["current_stage"]
    current_index = LOOP_STAGES.index(current)
    normalized = update_loop_stage(normalized, current, "complete", message=message, at=at)
    if current_index == len(LOOP_STAGES) - 1:
        return normalized
    return update_loop_stage(normalized, LOOP_STAGES[current_index + 1], "running", at=at)


def begin_next_cycle(
    state: Mapping[str, Any],
    *,
    at: Optional[float] = None,
) -> Dict[str, Any]:
    """Start another evidence-to-rerank cycle without repeating paper acquisition."""

    updated = build_loop_state(existing=state)
    if updated["cycle"] >= updated["max_cycles"]:
        raise AutopilotValidationError("The run has reached its maximum number of autonomy cycles.")
    if updated["current_stage"] not in {"rerank", "outcome"}:
        raise AutopilotValidationError("A new cycle can only begin after rerank or outcome review.")
    updated["cycle"] += 1
    for stage in LOOP_STAGES[2:]:
        record = _stage_record(updated, stage)
        record["status"] = "pending"
        record["message"] = ""
    return update_loop_stage(updated, "ground", "running", at=at)


def request_loop_approval(
    state: Mapping[str, Any],
    *,
    scope: str,
    reason: str,
    stage: Optional[str] = None,
    server_id: Optional[str] = None,
    at: Optional[float] = None,
) -> Dict[str, Any]:
    if not _SCOPE_RE.fullmatch(scope) or scope == "*":
        raise AutopilotValidationError("Approval scope must be a concrete exact scope.")
    updated = build_loop_state(existing=state)
    target_stage = stage or updated["current_stage"]
    if target_stage not in LOOP_STAGES:
        raise AutopilotValidationError(f"Unknown research-loop stage: {target_stage!r}.")
    approval = {
        "scope": scope,
        "stage": target_stage,
        "reason": reason[:1000],
        "status": "pending",
    }
    if server_id:
        approval["server_id"] = server_id[:80]
    if at is not None:
        approval["requested_at"] = at
    key = (scope, approval.get("server_id"))
    if not any(
        (item.get("scope"), item.get("server_id")) == key
        for item in updated["pending_approvals"]
    ):
        updated["pending_approvals"].append(approval)
    return update_loop_stage(updated, target_stage, "blocked", message=reason, at=at)


def resolve_loop_approval(
    state: Mapping[str, Any],
    *,
    scope: str,
    granted: bool,
    server_id: Optional[str] = None,
    reason: str = "",
    at: Optional[float] = None,
) -> Dict[str, Any]:
    updated = build_loop_state(existing=state)
    match: Optional[Dict[str, Any]] = None
    remaining: List[Dict[str, Any]] = []
    for item in updated["pending_approvals"]:
        if match is None and item.get("scope") == scope and item.get("server_id") == server_id:
            match = item
        else:
            remaining.append(item)
    if match is None:
        raise AutopilotValidationError(f"No pending approval matches exact scope {scope!r}.")
    match = copy.deepcopy(match)
    match["status"] = "granted" if granted else "denied"
    match["resolution_reason"] = reason[:1000]
    if at is not None:
        match["resolved_at"] = at
    updated["pending_approvals"] = remaining
    updated["approval_history"].append(match)
    stage = str(match["stage"])
    if granted:
        return update_loop_stage(updated, stage, "ready", message=reason, at=at)
    return update_loop_stage(updated, stage, "error", message=reason or "Approval denied.", at=at)


def _hypothesis_text(hypothesis: Any) -> str:
    if isinstance(hypothesis, str):
        return hypothesis.strip()
    if isinstance(hypothesis, Mapping):
        for key in ("text", "hypothesis", "statement", "title"):
            value = hypothesis.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _evidence_source_refs(evidence_packet: Any) -> List[Dict[str, Any]]:
    if isinstance(evidence_packet, Mapping):
        raw_items = evidence_packet.get("items") or evidence_packet.get("evidence") or []
    else:
        raw_items = evidence_packet
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes, bytearray)):
        return []
    refs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    fields = (
        "evidence_id",
        "paper_id",
        "chunk_id",
        "parse_run_id",
        "retrieval_id",
        "result_id",
        "title",
        "doi",
        "arxiv_id",
        "url",
        "source_channel",
        "source_reliability",
        "relationship",
    )
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        ref = {key: copy.deepcopy(item[key]) for key in fields if item.get(key) is not None}
        identity = str(
            ref.get("evidence_id")
            or ref.get("chunk_id")
            or ref.get("paper_id")
            or ref.get("result_id")
            or ref.get("url")
            or ""
        )
        if not identity or identity in seen:
            continue
        seen.add(identity)
        ref["reference_id"] = identity
        refs.append(ref)
    return refs[:50]


def build_experiment_protocol(
    hypothesis: Any,
    evidence_packet: Any,
    policy: Optional[Mapping[str, Any]] = None,
    *,
    metric_path: Optional[str] = None,
    operator_name: Optional[str] = None,
    operator: Optional[str] = None,
    threshold: Any = None,
) -> Dict[str, Any]:
    """Create a deterministic preregistered protocol tied to auditable evidence sources."""

    text = _hypothesis_text(hypothesis)
    if not text:
        raise AutopilotValidationError("An experiment protocol requires hypothesis text.")
    normalized_policy = normalize_policy(policy)
    evaluation = copy.deepcopy(normalized_policy["evaluation"])
    if metric_path is not None:
        evaluation["metric_path"] = str(metric_path).strip()
    comparison_override = operator_name if operator_name is not None else operator
    if comparison_override is not None:
        evaluation["operator"] = str(comparison_override).strip()
    if threshold is not None:
        evaluation["threshold"] = threshold
    if not evaluation.get("metric_path"):
        raise AutopilotValidationError("A preregistered metric_path is required.")
    if evaluation.get("operator") not in _OPERATORS:
        raise AutopilotValidationError("Unsupported preregistered metric operator.")
    evaluation["threshold"] = _finite_number(
        evaluation.get("threshold"),
        field="evaluation.threshold",
        allow_none=True,
    )
    if "inconclusive_margin" in evaluation:
        evaluation["inconclusive_margin"] = abs(
            _finite_number(
                evaluation["inconclusive_margin"],
                field="evaluation.inconclusive_margin",
            )
            or 0.0
        )
    source_refs = _evidence_source_refs(evidence_packet)
    hypothesis_id = None
    plan: Any = None
    if isinstance(hypothesis, Mapping):
        hypothesis_id = hypothesis.get("hypothesis_id") or hypothesis.get("id")
        plan = (
            hypothesis.get("experiment_protocol")
            or hypothesis.get("experiment_plan")
            or hypothesis.get("experiment")
            or hypothesis.get("test_plan")
        )
    snapshot_id = evidence_packet.get("snapshot_id") if isinstance(evidence_packet, Mapping) else None
    compute_spec = copy.deepcopy(normalized_policy["compute"])
    command = compute_spec.pop("command", None)
    if isinstance(command, str) and command:
        compute_spec["command_sha256"] = hashlib.sha256(command.encode("utf-8")).hexdigest()
        compute_spec["command_configured"] = True
    digest_payload = {
        "hypothesis": text,
        "evaluation": evaluation,
        "source_refs": source_refs,
        "snapshot_id": snapshot_id,
        "procedure": plan,
        "compute": compute_spec,
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:20]
    preregistered = evaluation.get("threshold") is not None
    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "protocol_id": f"protocol_{digest}",
        "status": "preregistered" if preregistered else "draft_needs_metric",
        "title": "Preregistered experiment protocol" if preregistered else "Experiment protocol draft",
        "hypothesis": {
            "id": str(hypothesis_id) if hypothesis_id is not None else None,
            "text": text,
        },
        "objective": f"Test the preregistered metric for: {text}",
        "procedure": copy.deepcopy(plan) if plan is not None else {},
        "evidence_snapshot_id": snapshot_id,
        "source_refs": source_refs,
        "evaluation": evaluation,
        "compute": compute_spec,
        "required_approval_scope": execution_scope(normalized_policy["compute"]),
        "scientific_boundary": SCIENTIFIC_BOUNDARY,
    }


def _path_parts(path: str) -> List[Any]:
    if path.startswith("/"):
        return [part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:]]
    parts: List[Any] = []
    for name, index in re.findall(r"(?:^|\.)([^.\[\]]+)|\[([0-9]+)\]", path):
        parts.append(name if name else int(index))
    if not parts or ".".join(str(part) for part in parts) == "":
        raise AutopilotValidationError("Metric path is empty or invalid.")
    return parts


def _nested_value(payload: Any, path: str) -> Any:
    current = payload
    for part in _path_parts(path):
        if isinstance(part, int):
            if not isinstance(current, Sequence) or isinstance(current, (str, bytes, bytearray)):
                raise AutopilotValidationError(f"Metric path {path!r} does not exist in the result JSON.")
            if part >= len(current):
                raise AutopilotValidationError(f"Metric path {path!r} does not exist in the result JSON.")
            current = current[part]
        else:
            if not isinstance(current, Mapping) or part not in current:
                raise AutopilotValidationError(f"Metric path {path!r} does not exist in the result JSON.")
            current = current[part]
    return current


def evaluate_experiment_result(
    protocol: Mapping[str, Any],
    result_json: Mapping[str, Any],
) -> Dict[str, Any]:
    """Evaluate only the preregistered numeric metric, without inventing interpretation."""

    if not isinstance(protocol, Mapping) or protocol.get("status") != "preregistered":
        raise AutopilotValidationError("Only a preregistered experiment protocol can be evaluated.")
    evaluation = protocol.get("evaluation")
    if not isinstance(evaluation, Mapping):
        raise AutopilotValidationError("The protocol has no preregistered evaluation rule.")
    if not isinstance(result_json, Mapping):
        raise AutopilotValidationError("Experiment result JSON must be an object.")
    metric_path = str(evaluation.get("metric_path") or "")
    comparison = str(evaluation.get("operator") or "")
    if comparison not in _OPERATORS:
        raise AutopilotValidationError("Unsupported preregistered metric operator.")
    threshold = _finite_number(evaluation.get("threshold"), field="evaluation.threshold")
    raw_value = _nested_value(result_json, metric_path)
    value = _finite_number(raw_value, field=f"result.{metric_path}")
    assert threshold is not None and value is not None
    passes = _OPERATORS[comparison](value, threshold)
    margin = _finite_number(
        evaluation.get("inconclusive_margin", 0.0),
        field="evaluation.inconclusive_margin",
    )
    assert margin is not None
    on_boundary = abs(value - threshold) <= margin and not passes
    if comparison in {">", "<"} and value == threshold:
        on_boundary = True
    if passes:
        verdict = "support"
        rationale = (
            f"Preregistered metric {metric_path}={value:g} satisfied "
            f"{comparison} {threshold:g}."
        )
    elif on_boundary:
        verdict = "inconclusive"
        rationale = (
            f"Preregistered metric {metric_path}={value:g} was at the decision boundary "
            f"for {comparison} {threshold:g}."
        )
    else:
        verdict = "contradict"
        rationale = (
            f"Preregistered metric {metric_path}={value:g} did not satisfy "
            f"{comparison} {threshold:g}."
        )
    return {
        "protocol_id": protocol.get("protocol_id"),
        "verdict": verdict,
        "relationship": "insufficient" if verdict == "inconclusive" else verdict,
        "metric_path": metric_path,
        "metric_value": value,
        "operator": comparison,
        "threshold": threshold,
        "rationale": rationale,
        "confidence": 0.95 if verdict in {"support", "contradict"} else 0.5,
        "scientific_boundary": protocol.get("scientific_boundary") or SCIENTIFIC_BOUNDARY,
    }


def parse_result_json_marker(stdout: str) -> Dict[str, Any]:
    """Parse the single structured result marker emitted by a local or remote command."""

    if not isinstance(stdout, str):
        raise AutopilotValidationError("Remote stdout must be text.")
    payloads = []
    for line in stdout.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(RESULT_JSON_MARKER):
            payloads.append(stripped[len(RESULT_JSON_MARKER) :].strip())
    if not payloads:
        raise AutopilotValidationError(f"Remote stdout is missing {RESULT_JSON_MARKER}.")
    if len(payloads) != 1:
        raise AutopilotValidationError("Remote stdout contains multiple ambiguous result markers.")
    try:
        parsed = json.loads(payloads[0])
    except json.JSONDecodeError as exc:
        raise AutopilotValidationError("Remote result marker does not contain valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise AutopilotValidationError("Remote result marker JSON must be an object.")
    return parsed


parse_remote_result_json = parse_result_json_marker
