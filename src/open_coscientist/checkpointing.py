from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple


RUNTIME_ONLY_STATE_KEYS = frozenset({"progress_callback", "tool_registry"})


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
