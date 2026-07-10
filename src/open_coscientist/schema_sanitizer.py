from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional


UNSUPPORTED_SCHEMA_KEYS = {
    "$comment",
    "$id",
    "$schema",
    "deprecated",
    "examples",
    "readOnly",
    "writeOnly",
}

PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "dashscope": "qwen",
    "deepseek": "deepseek",
    "gemini": "gemini",
    "google": "gemini",
    "openai": "openai",
    "qwen": "qwen",
}


def provider_family(model_name: str) -> str:
    normalized = model_name.lower()
    for marker, family in PROVIDER_ALIASES.items():
        if normalized.startswith(f"{marker}/") or marker in normalized:
            return family
    return "generic"


def sanitize_response_schema(
    json_schema: Optional[Dict[str, Any]],
    *,
    model_name: str = "",
) -> Optional[Dict[str, Any]]:
    if json_schema is None:
        return None

    family = provider_family(model_name)
    schema = copy.deepcopy(json_schema)
    if "schema" in schema:
        sanitized_body = sanitize_json_schema(schema["schema"], provider_family=family)
        wrapper: Dict[str, Any] = {
            "name": _sanitize_schema_name(str(schema.get("name") or "structured_response")),
            "schema": sanitized_body,
        }
        if "description" in schema:
            wrapper["description"] = str(schema["description"])[:1024]
        if family == "openai" and "strict" in schema:
            wrapper["strict"] = bool(schema["strict"])
        return wrapper

    return sanitize_json_schema(schema, provider_family=family)


def sanitize_tools_for_model(
    tools: Optional[List[Dict[str, Any]]],
    *,
    model_name: str = "",
) -> Optional[List[Dict[str, Any]]]:
    if tools is None:
        return None
    family = provider_family(model_name)
    sanitized_tools: List[Dict[str, Any]] = []
    for tool in tools:
        cloned = copy.deepcopy(tool)
        if cloned.get("type") == "function" and isinstance(cloned.get("function"), dict):
            function = cloned["function"]
            function["name"] = _sanitize_schema_name(str(function.get("name") or "tool"))
            if "description" in function:
                function["description"] = str(function["description"])[:1024]
            if isinstance(function.get("parameters"), dict):
                function["parameters"] = sanitize_json_schema(function["parameters"], provider_family=family)
        sanitized_tools.append(cloned)
    return sanitized_tools


def sanitize_json_schema(schema: Dict[str, Any], *, provider_family: str = "generic") -> Dict[str, Any]:
    sanitized = _sanitize_schema_node(schema, provider_family=provider_family)
    if sanitized.get("type") == "object":
        sanitized.setdefault("properties", {})
    return sanitized


def _sanitize_schema_node(value: Any, *, provider_family: str) -> Any:
    if isinstance(value, list):
        return [_sanitize_schema_node(item, provider_family=provider_family) for item in value]
    if not isinstance(value, dict):
        return value

    node: Dict[str, Any] = {}
    for key, raw in value.items():
        if key in UNSUPPORTED_SCHEMA_KEYS:
            continue
        if key in {"default", "title", "format"}:
            continue
        if key == "const":
            node["enum"] = [raw]
            continue
        if key in {"anyOf", "oneOf"}:
            nullable = _collapse_nullable_union(raw, provider_family=provider_family)
            if nullable is not None:
                node.update(nullable)
                continue
        node[key] = _sanitize_schema_node(raw, provider_family=provider_family)

    if isinstance(node.get("type"), list):
        types = [item for item in node["type"] if item != "null"]
        if len(types) == 1:
            node["type"] = types[0]
        elif types:
            node["type"] = types
        else:
            node["type"] = "string"

    if node.get("type") == "object":
        properties = node.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        node["properties"] = {
            str(name): _sanitize_schema_node(prop, provider_family=provider_family)
            for name, prop in properties.items()
            if isinstance(prop, dict)
        }
        required = node.get("required")
        if isinstance(required, list):
            node["required"] = [name for name in required if name in node["properties"]]
        elif "required" in node:
            node.pop("required", None)
        if provider_family in {"openai", "anthropic", "deepseek", "qwen", "gemini"}:
            node.setdefault("additionalProperties", False)

    if node.get("type") == "array" and not isinstance(node.get("items"), dict):
        node["items"] = {"type": "string"}

    return node


def _collapse_nullable_union(raw: Any, *, provider_family: str) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) != 2:
        return None
    non_null = [item for item in raw if not (isinstance(item, dict) and item.get("type") == "null")]
    if len(non_null) != 1 or not isinstance(non_null[0], dict):
        return None
    sanitized = _sanitize_schema_node(non_null[0], provider_family=provider_family)
    if provider_family in {"generic", "openai"}:
        sanitized["nullable"] = True
    return sanitized


def _sanitize_schema_name(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
    if not sanitized:
        return "schema"
    if sanitized[0].isdigit():
        sanitized = f"schema_{sanitized}"
    return sanitized[:64]
