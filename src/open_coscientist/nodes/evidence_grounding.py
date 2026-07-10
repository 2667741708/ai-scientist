"""Attach hypothesis-specific evidence packets before review and ranking."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..models import Hypothesis
from ..state import WorkflowState

logger = logging.getLogger(__name__)

EvidenceResolver = Callable[
    [Dict[str, Any]],
    Awaitable[Dict[str, Any] | List[Dict[str, Any]]] | Dict[str, Any] | List[Dict[str, Any]],
]

_EVIDENCE_ITEM_FIELDS = (
    "evidence_id",
    "chunk_id",
    "paper_id",
    "parse_run_id",
    "library_id",
    "title",
    "chunk_title",
    "section_type",
    "section_path",
    "support_level",
    "source_reliability",
    "relationship",
    "score",
    "evidence_summary",
    "experiment_data_summary",
    "text_preview",
    "url",
    "evidence_path",
)


def _compact_text(value: Any, limit: int = 1200) -> str:
    return " ".join(str(value or "").split())[:limit]


def _public_evidence_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        field: item.get(field)
        for field in _EVIDENCE_ITEM_FIELDS
        if item.get(field) not in (None, "", [])
    }
    if "text_preview" in normalized:
        normalized["text_preview"] = _compact_text(normalized["text_preview"])
    if "evidence_summary" in normalized:
        normalized["evidence_summary"] = _compact_text(normalized["evidence_summary"], 600)
    normalized.setdefault("relationship", "relevant")
    return normalized


def _packet_snapshot_id(items: List[Dict[str, Any]]) -> str:
    refs = [
        {
            key: item.get(key)
            for key in (
                "evidence_id",
                "chunk_id",
                "paper_id",
                "parse_run_id",
                "support_level",
                "source_reliability",
                "text_preview",
            )
            if item.get(key) not in (None, "")
        }
        for item in items
    ]
    digest = hashlib.sha256(
        json.dumps(refs, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"evidence_{digest}"


def normalize_evidence_packet(
    result: Dict[str, Any] | List[Dict[str, Any]] | None,
    *,
    hypothesis: Hypothesis,
) -> Dict[str, Any]:
    payload = result if isinstance(result, dict) else {}
    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else result
    raw_items = raw_items if isinstance(raw_items, list) else []
    items = [_public_evidence_item(item) for item in raw_items if isinstance(item, dict)][:12]
    parsed_fulltext_count = sum(
        1 for item in items if item.get("source_reliability") == "parsed_fulltext"
    )
    experimental_data_count = sum(
        1 for item in items if item.get("support_level") == "experimental_data"
    )
    weak_count = sum(
        1
        for item in items
        if item.get("support_level") in {"metadata", "abstract", "unknown", None}
    )
    return {
        "status": str(payload.get("status") or ("ready" if items else "absent")),
        "query": str(payload.get("query") or hypothesis.text),
        "library_id": payload.get("library_id"),
        "snapshot_id": str(payload.get("snapshot_id") or _packet_snapshot_id(items)),
        "item_count": len(items),
        "parsed_fulltext_count": parsed_fulltext_count,
        "experimental_data_count": experimental_data_count,
        "weak_support_count": weak_count,
        "items": items,
        "boundary": (
            "Retrieved chunks are relevance candidates, not automatically supporting evidence. "
            "The reviewer and tournament judge must distinguish support, contradiction, and insufficiency."
        ),
    }


async def _resolve_one(
    resolver: EvidenceResolver,
    hypothesis: Hypothesis,
) -> Dict[str, Any]:
    try:
        result = resolver(hypothesis.to_dict())
        if inspect.isawaitable(result):
            result = await result
        return normalize_evidence_packet(result, hypothesis=hypothesis)
    except Exception as exc:  # pragma: no cover - defensive provider boundary
        logger.warning("Evidence resolver failed for hypothesis: %s", exc)
        return {
            "status": "error",
            "query": hypothesis.text,
            "snapshot_id": _packet_snapshot_id([]),
            "item_count": 0,
            "parsed_fulltext_count": 0,
            "experimental_data_count": 0,
            "weak_support_count": 0,
            "items": [],
            "error": _compact_text(exc, 400),
            "boundary": "Evidence retrieval failed; this hypothesis must not be treated as grounded.",
        }


async def evidence_grounding_node(
    state: WorkflowState,
    resolver: Optional[EvidenceResolver] = None,
) -> Dict[str, Any]:
    """Resolve and freeze evidence for every current hypothesis."""
    hypotheses = state["hypotheses"]
    if resolver is None:
        return {"hypotheses": hypotheses, "evidence_snapshot": {"status": "not_configured"}}

    if state.get("progress_callback"):
        await state["progress_callback"](
            "evidence_grounding_start",
            {
                "message": f"Retrieving evidence for {len(hypotheses)} hypotheses...",
                "progress": 48,
            },
        )

    packets = await asyncio.gather(*[_resolve_one(resolver, hypothesis) for hypothesis in hypotheses])
    for hypothesis, packet in zip(hypotheses, packets):
        hypothesis.evidence_packet = packet

    packet_ids = sorted(str(packet.get("snapshot_id") or "") for packet in packets)
    snapshot_digest = hashlib.sha256("|".join(packet_ids).encode("utf-8")).hexdigest()[:16]
    snapshot = {
        "snapshot_id": f"snapshot_{snapshot_digest}",
        "status": "ready" if any(packet.get("item_count") for packet in packets) else "limited",
        "hypothesis_count": len(hypotheses),
        "packet_count": len(packets),
        "evidence_item_count": sum(int(packet.get("item_count") or 0) for packet in packets),
        "parsed_fulltext_count": sum(
            int(packet.get("parsed_fulltext_count") or 0) for packet in packets
        ),
        "experimental_data_count": sum(
            int(packet.get("experimental_data_count") or 0) for packet in packets
        ),
        "packet_snapshot_ids": packet_ids,
        "boundary": "Snapshot fingerprints the exact hypothesis evidence packets used before review and Elo.",
    }

    if state.get("progress_callback"):
        await state["progress_callback"](
            "evidence_grounding_complete",
            {
                "message": f"Frozen {snapshot['evidence_item_count']} evidence links for review.",
                "progress": 52,
                "snapshot_id": snapshot["snapshot_id"],
            },
        )

    return {"hypotheses": hypotheses, "evidence_snapshot": snapshot}


def format_hypothesis_with_evidence(hypothesis: Hypothesis) -> str:
    """Format a bounded, provenance-aware hypothesis packet for model review."""
    packet = hypothesis.evidence_packet if isinstance(hypothesis.evidence_packet, dict) else {}
    items = packet.get("items") if isinstance(packet.get("items"), list) else []
    if not items:
        return (
            f"{hypothesis.text}\n\n"
            "Evidence packet: no hypothesis-specific knowledge chunks were retrieved. "
            "Treat evidence strength as insufficient and do not infer support from absence."
        )

    lines = []
    for index, item in enumerate(items[:6], start=1):
        if not isinstance(item, dict):
            continue
        title = _compact_text(item.get("title") or item.get("chunk_title") or "Untitled source", 180)
        preview = _compact_text(
            item.get("text_preview")
            or item.get("evidence_summary")
            or item.get("experiment_data_summary"),
            650,
        )
        lines.append(
            f"E{index}: title={title}; support_level={item.get('support_level') or 'unknown'}; "
            f"source_reliability={item.get('source_reliability') or 'unknown'}; "
            f"relationship={item.get('relationship') or 'relevant'}; excerpt={preview or 'unavailable'}"
        )
    return (
        f"{hypothesis.text}\n\n"
        f"Evidence packet {packet.get('snapshot_id') or 'unknown'} "
        f"({packet.get('item_count', len(lines))} retrieved items):\n"
        + "\n".join(lines)
        + "\nEvidence policy: retrieved relevance is not proof. Judge whether excerpts support, contradict, "
        "or are insufficient for the hypothesis; penalize weak or absent grounding."
    )
