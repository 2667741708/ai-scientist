from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping, Optional


HYPOTHESIS_ORIGIN_LABELS = {
    "user_seeded": "user seeded",
    "model_generated": "model generated",
    "evolved": "evolved",
    "tool_generated": "tool grounded",
    "tool_grounded": "tool grounded",
}


def hypothesis_surface_summary(
    hypothesis: Any,
    *,
    index: Optional[int] = None,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    source = _as_mapping(hypothesis)
    origin = _canonical_origin(
        _first_value(source, ("origin", "source_origin", "hypothesis_origin"))
        or _infer_origin(source)
    )
    rank = _first_value(source, ("rank", "ranking", "position"))
    elo_rating = _first_value(source, ("elo_rating", "elo", "rating"))
    support_level = _first_value(source, ("support_level", "evidence_support_level", "grounding_status"))
    title = _first_text(source, ("title", "name"))
    technical_text = _first_text(source, ("technical_hypothesis", "hypothesis", "text"))
    plain_summary = _first_text(source, ("plain_explanation", "explanation", "summary", "rationale"))
    if not title:
        title = _title_from_text(plain_summary or technical_text or f"Hypothesis {index + 1 if index is not None else ''}")
    if not plain_summary:
        plain_summary = _compact_text(technical_text, max_length=220)

    summary = {
        "index": index,
        "title": title,
        "plain_summary": _compact_text(plain_summary, max_length=280),
        "origin": origin,
        "origin_label": HYPOTHESIS_ORIGIN_LABELS.get(origin, origin.replace("_", " ")),
        "rank": _safe_int(rank),
        "elo_rating": _safe_number(elo_rating),
        "support_level": str(support_level or "unknown"),
        "status": _hypothesis_status(source, support_level),
        "next_actions": _hypothesis_next_actions(source, support_level),
        "visibility_boundary": (
            "Hypothesis surface summaries expose scan-friendly title, summary, origin, ranking, "
            "support level, and next actions; full technical text, reviews, tournament payloads, "
            "and lineage refs require explicit detail disclosure."
        ),
    }
    if include_internal_refs:
        summary["internal_refs"] = {
            "hypothesis_id": _first_value(source, ("id", "hypothesis_id")),
            "origin_evidence": _first_value(source, ("origin_evidence", "generation_method")),
            "evolution_history_count": _list_length(_first_value(source, ("evolution_history", "lineage"))),
            "citation_count": _citation_count(source),
        }
        summary["technical_text"] = _compact_text(technical_text, max_length=1400)
    return summary


def hypothesis_surface_collection(
    hypotheses: Iterable[Any],
    *,
    include_internal_refs: bool = False,
) -> Dict[str, Any]:
    items = [
        hypothesis_surface_summary(
            hypothesis,
            index=index,
            include_internal_refs=include_internal_refs,
        )
        for index, hypothesis in enumerate(hypotheses or [])
    ]
    origin_counts: Dict[str, int] = {}
    support_counts: Dict[str, int] = {}
    for item in items:
        origin = str(item.get("origin") or "unknown")
        support = str(item.get("support_level") or "unknown")
        origin_counts[origin] = origin_counts.get(origin, 0) + 1
        support_counts[support] = support_counts.get(support, 0) + 1
    return {
        "hypothesis_count": len(items),
        "origin_counts": origin_counts,
        "support_level_counts": support_counts,
        "items": items,
        "visibility_boundary": (
            "Collection summary is safe for default hypothesis lists; raw reviews, citations, "
            "and tournament matchups remain behind per-hypothesis detail views."
        ),
    }


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    data = getattr(value, "model_dump", None)
    if callable(data):
        dumped = data()
        if isinstance(dumped, Mapping):
            return dumped
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}


def _first_value(source: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and value != "":
            return value
    return None


def _first_text(source: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    value = _first_value(source, keys)
    return str(value or "").strip()


def _canonical_origin(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized == "tool_grounded":
        return "tool_generated"
    if normalized in HYPOTHESIS_ORIGIN_LABELS:
        return normalized
    return "model_generated"


def _infer_origin(source: Mapping[str, Any]) -> str:
    method = str(_first_value(source, ("generation_method", "method", "source")) or "").lower()
    if any(marker in method for marker in ("user", "seed")):
        return "user_seeded"
    if any(marker in method for marker in ("evolve", "mutation", "refine", "revised")):
        return "evolved"
    if any(marker in method for marker in ("tool", "evidence", "literature", "ground")):
        return "tool_generated"
    if _list_length(_first_value(source, ("evolution_history", "lineage"))) > 0:
        return "evolved"
    return "model_generated"


def _hypothesis_status(source: Mapping[str, Any], support_level: Any) -> str:
    if _first_value(source, ("error", "error_message")):
        return "error"
    support = str(support_level or "").lower()
    if support in {"contradicted", "unsupported"}:
        return "needs_review"
    if support in {"limited", "ungrounded", "unknown", ""}:
        return "limited"
    return "ready"


def _hypothesis_next_actions(source: Mapping[str, Any], support_level: Any) -> list[str]:
    actions = ["inspect_evidence", "design_experiment", "add_feedback"]
    support = str(support_level or "").lower()
    if support in {"limited", "ungrounded", "unknown", ""}:
        actions.insert(1, "verify_evidence")
    if _list_length(_first_value(source, ("reviews", "review_feedback", "review"))) > 0:
        actions.append("inspect_review")
    return actions


def _title_from_text(value: str) -> str:
    compact = _compact_text(value, max_length=96)
    if not compact:
        return "Untitled hypothesis"
    sentence = re.split(r"(?<=[.!?])\s+", compact, maxsplit=1)[0].strip()
    return sentence or compact


def _compact_text(value: Any, *, max_length: int = 280) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 3].rstrip()}..."


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _list_length(value: Any) -> int:
    if isinstance(value, (list, tuple, set)):
        return len(value)
    if isinstance(value, Mapping):
        return len(value)
    return 1 if value else 0


def _citation_count(source: Mapping[str, Any]) -> int:
    citations = _first_value(source, ("citation_map", "citations", "evidence_links"))
    return _list_length(citations)
