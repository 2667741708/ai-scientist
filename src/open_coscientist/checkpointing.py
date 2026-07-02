from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple


RUNTIME_ONLY_STATE_KEYS = frozenset({"progress_callback", "tool_registry"})
RECOVERABLE_WORK_ITEM_STATUSES = frozenset({"queued", "leased", "running", "retrying", "blocked"})


def langgraph_thread_config(
    run_id: str,
    *,
    recursion_limit: int | None = 100,
    checkpoint_ns: str | None = None,
) -> Dict[str, Any]:
    normalized_run_id = str(run_id).strip()
    if not normalized_run_id:
        raise ValueError("run_id is required to build a stable LangGraph thread config")

    configurable: Dict[str, Any] = {"thread_id": normalized_run_id}
    if checkpoint_ns is not None:
        configurable["checkpoint_ns"] = str(checkpoint_ns)

    config: Dict[str, Any] = {"configurable": configurable}
    if recursion_limit is not None:
        config["recursion_limit"] = recursion_limit
    return config


def langgraph_resume_config(
    run_id: str,
    *,
    checkpoint_id: str | None = None,
    recursion_limit: int | None = 100,
    checkpoint_ns: str | None = None,
) -> Dict[str, Any]:
    config = langgraph_thread_config(
        run_id,
        recursion_limit=recursion_limit,
        checkpoint_ns=checkpoint_ns,
    )
    normalized_checkpoint_id = str(checkpoint_id).strip() if checkpoint_id is not None else ""
    if normalized_checkpoint_id:
        config["configurable"]["checkpoint_id"] = normalized_checkpoint_id
    return config


def module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def execution_memory_status() -> Dict[str, Any]:
    sqlite_available = module_available("langgraph.checkpoint.sqlite")
    return {
        "status": "ready" if sqlite_available else "limited",
        "thread_id_required": True,
        "thread_id_source": "run_id",
        "checkpoint_backend": "langgraph_sqlite" if sqlite_available else "sqlite_metadata",
        "checkpointer_package": "langgraph-checkpoint-sqlite",
        "langgraph_checkpoint_sqlite_available": sqlite_available,
        "resume_config_fields": ["thread_id", "checkpoint_id", "checkpoint_ns"],
        "resume_supported": sqlite_available,
        "resume_mode": "langgraph_thread_resume" if sqlite_available else "metadata_only_retry",
        "runtime_only_state_keys": sorted(RUNTIME_ONLY_STATE_KEYS),
        "resume_boundary": (
            "Stable thread_id=run_id can be used with LangGraph SQLite checkpoint summaries."
            if sqlite_available
            else "Only queue/checkpoint metadata is available; full LangGraph state resume remains limited."
        ),
        "boundary": (
            "LangGraph SQLite checkpoint saver is available."
            if sqlite_available
            else "Execution memory is metadata-only until langgraph-checkpoint-sqlite is installed."
        ),
    }


def execution_recovery_policy(
    execution_memory: Mapping[str, Any] | None,
    *,
    work_item_status: str | None = None,
) -> Dict[str, Any]:
    memory = dict(execution_memory or {})
    status = str(memory.get("status") or "not_available")
    checkpoint_available = bool(memory.get("checkpoint_available"))
    resume_supported = bool(memory.get("resume_supported"))
    normalized_work_status = str(work_item_status or "").strip() or None
    work_item_recoverable = normalized_work_status in RECOVERABLE_WORK_ITEM_STATUSES

    if resume_supported:
        recovery_mode = "resume_from_checkpoint"
        next_action = "Resume the LangGraph thread using thread_id and checkpoint identity."
        can_resume = True
        should_retry = False
    elif checkpoint_available:
        recovery_mode = "metadata_guided_retry"
        next_action = "Retry the durable work item with checkpoint metadata as audit guidance."
        can_resume = False
        should_retry = work_item_recoverable
    elif work_item_recoverable:
        recovery_mode = "queue_retry_without_checkpoint"
        next_action = "Continue through the durable queue; no checkpoint state is available."
        can_resume = False
        should_retry = True
    else:
        recovery_mode = "not_recoverable"
        next_action = "Start a new run or inspect the failed execution before retrying."
        can_resume = False
        should_retry = False

    return {
        "status": status,
        "recovery_mode": recovery_mode,
        "checkpoint_available": checkpoint_available,
        "resume_supported": resume_supported,
        "can_resume": can_resume,
        "should_retry": should_retry,
        "work_item_status": normalized_work_status,
        "work_item_recoverable": work_item_recoverable,
        "resume_config_fields": list(memory.get("resume_config_fields") or ["thread_id"]),
        "next_action": next_action,
        "boundary": (
            "Recovery policy summarizes execution memory and queue state only; raw checkpoint "
            "channel values and worker internals remain hidden."
        ),
    }


def build_checkpoint_metadata_record(
    *,
    run_id: str,
    phase: str | None = None,
    status: str = "saved",
    checkpoint_id: str | None = None,
    checkpoint_ns: str | None = None,
    checkpoint_backend: str | None = None,
    checkpoint_ref: str | None = None,
    thread_id: str | None = None,
    state_summary: Mapping[str, Any] | None = None,
    checkpoint_tuple_summary: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_run_id = str(run_id).strip()
    if not normalized_run_id:
        raise ValueError("run_id is required to build checkpoint metadata")
    normalized_thread_id = str(thread_id).strip() if thread_id is not None else normalized_run_id
    if not normalized_thread_id:
        normalized_thread_id = normalized_run_id
    if normalized_thread_id != normalized_run_id:
        raise ValueError("checkpoint metadata requires thread_id to match run_id")

    tuple_summary = dict(checkpoint_tuple_summary or {})
    normalized_checkpoint_id = _first_nonempty_text(
        checkpoint_id,
        tuple_summary.get("checkpoint_id"),
    )
    normalized_checkpoint_ns = _first_nonempty_text(
        checkpoint_ns,
        tuple_summary.get("checkpoint_ns"),
    )
    normalized_backend = _first_nonempty_text(
        checkpoint_backend,
        "langgraph_sqlite" if tuple_summary else "sqlite_metadata",
    )
    resume_config = langgraph_resume_config(
        normalized_run_id,
        checkpoint_id=normalized_checkpoint_id,
        checkpoint_ns=normalized_checkpoint_ns or None,
    )
    return {
        "run_id": normalized_run_id,
        "thread_id": normalized_thread_id,
        "thread_id_matches_run_id": True,
        "phase": _first_nonempty_text(phase),
        "status": _first_nonempty_text(status) or "saved",
        "checkpoint_id": normalized_checkpoint_id,
        "checkpoint_ns": normalized_checkpoint_ns or "",
        "checkpoint_backend": normalized_backend,
        "checkpoint_ref": checkpoint_ref,
        "resume_config": resume_config,
        "checkpoint_tuple": {
            "parent_checkpoint_id": tuple_summary.get("parent_checkpoint_id"),
            "checkpoint_ts": tuple_summary.get("checkpoint_ts"),
            "channel_keys": list(tuple_summary.get("channel_keys") or []),
            "pending_writes_count": int(tuple_summary.get("pending_writes_count") or 0),
        },
        "state_summary": summarize_workflow_state_for_checkpoint_metadata(state_summary or {}),
        "visibility_boundary": (
            "Checkpoint metadata records run/thread/checkpoint identity, phase, status, resume config, "
            "and state keys/counts only; raw workflow channel values, prompts, feedback text, "
            "hypothesis text, and provider payloads must stay out of persisted metadata summaries."
        ),
    }


def summarize_workflow_state_for_checkpoint_metadata(state: Mapping[str, Any]) -> Dict[str, Any]:
    state_keys = sorted(str(key) for key in state.keys())
    omitted_runtime_keys = sorted(str(key) for key in state.keys() if key in RUNTIME_ONLY_STATE_KEYS)
    return {
        "state_key_count": len(state_keys),
        "state_keys": state_keys,
        "omitted_runtime_only_keys": omitted_runtime_keys,
        "hypothesis_count": _collection_length(state.get("hypotheses")),
        "message_count": _collection_length(state.get("messages")),
        "tournament_matchup_count": _collection_length(state.get("tournament_matchups")),
        "evolution_detail_count": _collection_length(state.get("evolution_details")),
        "current_iteration": state.get("current_iteration"),
        "has_memory_context": bool(state.get("memory_context")),
        "has_starting_hypotheses": bool(state.get("starting_hypotheses")),
        "boundary": (
            "Workflow state metadata stores keys and counts only. Raw values are intentionally omitted."
        ),
    }


def sanitize_workflow_state_for_checkpoint(state: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    sanitized: Dict[str, Any] = {}
    omitted: Dict[str, str] = {}
    for key, value in state.items():
        if key in RUNTIME_ONLY_STATE_KEYS:
            omitted[key] = "runtime_only"
            continue
        if callable(value):
            omitted[key] = "callable"
            continue
        sanitized[str(key)] = value
    metadata = {
        "omitted_keys": omitted,
        "boundary": "Sanitized checkpoint state excludes runtime-only callbacks and registries.",
    }
    return sanitized, metadata


def checkpoint_state_serializability(state: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        serializer = JsonPlusSerializer()
        serializer.dumps_typed(dict(state))
    except Exception as exc:
        return {
            "serializable": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    return {"serializable": True, "error_type": None, "error": None}


def summarize_langgraph_checkpoint_tuple(checkpoint_tuple: Any) -> Dict[str, Any]:
    config = getattr(checkpoint_tuple, "config", {}) or {}
    checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
    metadata = getattr(checkpoint_tuple, "metadata", {}) or {}
    parent_config = getattr(checkpoint_tuple, "parent_config", {}) or {}
    pending_writes = getattr(checkpoint_tuple, "pending_writes", []) or []

    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    parent_configurable = (
        parent_config.get("configurable", {}) if isinstance(parent_config, dict) else {}
    )
    channel_values = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
    channel_versions = checkpoint.get("channel_versions", {}) if isinstance(checkpoint, dict) else {}

    return {
        "thread_id": configurable.get("thread_id"),
        "checkpoint_id": configurable.get("checkpoint_id") or checkpoint.get("id"),
        "checkpoint_ns": configurable.get("checkpoint_ns", ""),
        "parent_checkpoint_id": parent_configurable.get("checkpoint_id"),
        "checkpoint_ts": checkpoint.get("ts") if isinstance(checkpoint, dict) else None,
        "metadata": {
            "source": metadata.get("source") if isinstance(metadata, dict) else None,
            "step": metadata.get("step") if isinstance(metadata, dict) else None,
        },
        "channel_keys": sorted(str(key) for key in channel_values.keys())
        if isinstance(channel_values, dict)
        else [],
        "channel_version_keys": sorted(str(key) for key in channel_versions.keys())
        if isinstance(channel_versions, dict)
        else [],
        "pending_writes_count": len(pending_writes),
        "boundary": "LangGraph checkpoint summary only; raw channel values are not exposed.",
    }


@asynccontextmanager
async def open_sqlite_checkpointer(db_path: str | Path):
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "langgraph-checkpoint-sqlite is required for durable LangGraph checkpoints"
        ) from exc

    resolved = Path(db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(resolved)) as saver:
        await saver.setup()
        yield saver


def _first_nonempty_text(*values: Any) -> str:
    for value in values:
        text = str(value).strip() if value is not None else ""
        if text:
            return text
    return ""


def _collection_length(value: Any) -> int:
    if value is None or isinstance(value, (str, bytes)):
        return 0
    try:
        return len(value)
    except TypeError:
        return 1
