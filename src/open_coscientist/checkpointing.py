from __future__ import annotations

import importlib.util
from typing import Any, Dict, Mapping, Tuple


RUNTIME_ONLY_STATE_KEYS = frozenset({"progress_callback", "tool_registry"})


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
        "langgraph_checkpoint_sqlite_available": sqlite_available,
        "runtime_only_state_keys": sorted(RUNTIME_ONLY_STATE_KEYS),
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
