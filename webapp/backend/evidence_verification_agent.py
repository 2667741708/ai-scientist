from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "using",
    "used",
    "use",
    "can",
    "could",
    "would",
    "should",
    "may",
    "might",
    "are",
    "was",
    "were",
    "been",
    "has",
    "have",
    "had",
    "its",
    "our",
    "their",
    "between",
    "through",
    "via",
    "通过",
    "可以",
    "能够",
    "可能",
    "以及",
    "并且",
    "或者",
    "如果",
    "因此",
    "这个",
    "这些",
    "假设",
    "研究",
}

NEGATIVE_MARKERS = (
    "contradict",
    "conflict",
    "inconsistent",
    "negative result",
    "no effect",
    "not associated",
    "failed",
    "failure",
    "does not",
    "did not",
    "lack of",
    "absence of",
    "replication failed",
    "反证",
    "相反",
    "不支持",
    "未发现",
    "没有发现",
    "无显著",
    "失败",
    "不能证明",
)


def _terms(text: str) -> List[str]:
    seen: set[str] = set()
    output: List[str] = []
    for token in re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", text.lower()):
        if token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        output.append(token)
    return output


def _first_text(value: Dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
        if item is not None and not isinstance(item, (dict, list)):
            return str(item)
    return ""


def _split_claims(hypothesis_text: str) -> List[str]:
    parts = [
        part.strip(" \t\r\n-")
        for part in re.split(r"[\n。；;.!?]+", hypothesis_text)
        if part.strip(" \t\r\n-")
    ]
    if not parts:
        return [hypothesis_text.strip()]
    return parts[:6]


def _evidence_key(item: Dict[str, Any]) -> str:
    for key in ("chunk_id", "evidence_id", "link_id", "result_id", "retrieval_id"):
        value = item.get(key)
        if value:
            return f"{key}:{value}"
    return f"text:{_first_text(item, ('title', 'text_preview', 'preview'))[:120]}"


class EvidenceVerificationAgent:
    """Deterministic evidence verifier for local RAG and approval-backed packets.

    The verifier does not claim scientific truth. It checks whether the current
    evidence corpus contains auditable support for the hypothesis and exposes
    gaps, weak source reliability, and possible counter-evidence markers.
    """

    def verify(
        self,
        *,
        hypothesis_text: str,
        local_results: List[Dict[str, Any]],
        run_evidence_links: Optional[List[Dict[str, Any]]] = None,
        run_evidence_retrievals: Optional[List[Dict[str, Any]]] = None,
        external_packets: Optional[List[Dict[str, Any]]] = None,
        run_id: Optional[str] = None,
        paper_id: Optional[str] = None,
        external_check: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        hypothesis = hypothesis_text.strip()
        evidence_items = self._normalize_evidence(
            local_results=local_results,
            run_evidence_links=run_evidence_links or [],
            external_packets=external_packets or [],
        )
        claim_checks = self._check_claims(hypothesis, evidence_items)
        supporting_items = [
            item
            for item in evidence_items
            if item.get("support_signal", 0) > 0 and not item.get("possible_counter_evidence")
        ]
        counter_items = [item for item in evidence_items if item.get("possible_counter_evidence")]
        parsed_fulltext_count = sum(
            1 for item in evidence_items if item.get("source_reliability") == "parsed_fulltext"
        )
        experimental_count = sum(
            1 for item in evidence_items if item.get("support_level") == "experimental_data"
        )
        external_count = sum(1 for item in evidence_items if item.get("source_channel") == "external_mcp")
        covered_claim_count = sum(1 for item in claim_checks if item["status"] in {"supported", "partially_supported"})
        verdict = self._verdict(
            evidence_count=len(evidence_items),
            parsed_fulltext_count=parsed_fulltext_count,
            experimental_count=experimental_count,
            covered_claim_count=covered_claim_count,
            claim_count=max(1, len(claim_checks)),
            counter_count=len(counter_items),
        )
        missing_evidence = self._missing_evidence(
            evidence_count=len(evidence_items),
            parsed_fulltext_count=parsed_fulltext_count,
            experimental_count=experimental_count,
            run_id=run_id,
            run_links_count=len(run_evidence_links or []),
            external_check=external_check,
        )
        confidence = self._confidence(
            verdict=verdict,
            evidence_count=len(evidence_items),
            parsed_fulltext_count=parsed_fulltext_count,
            experimental_count=experimental_count,
            covered_claim_count=covered_claim_count,
            claim_count=max(1, len(claim_checks)),
            counter_count=len(counter_items),
        )
        support_level = self._support_level(parsed_fulltext_count, experimental_count, len(evidence_items))
        summary = self._summary(verdict, parsed_fulltext_count, experimental_count, len(counter_items), external_check)
        return {
            "agent": "evidence_verification_agent",
            "phase": "evidence_audit",
            "title": "证据核验报告",
            "summary": summary,
            "verdict": verdict,
            "support_level": support_level,
            "confidence": confidence,
            "hypothesisPreview": hypothesis[:700],
            "runId": run_id,
            "paperId": paper_id,
            "items": evidence_items[:8],
            "supportingEvidence": supporting_items[:8],
            "possibleCounterEvidence": counter_items[:6],
            "claimChecks": claim_checks,
            "missingEvidence": missing_evidence,
            "falsificationTests": self._falsification_tests(hypothesis, missing_evidence),
            "sourceReliabilitySummary": {
                "parsedFulltextCount": parsed_fulltext_count,
                "experimentalEvidenceCount": experimental_count,
                "externalMcpEvidenceCount": external_count,
                "totalEvidenceCount": len(evidence_items),
                "runEvidenceLinksCount": len(run_evidence_links or []),
                "runEvidenceRetrievalsCount": len(run_evidence_retrievals or []),
            },
            "evidenceSourceExplanation": (
                "当前证据由本地 SQL RAG/parsed fulltext 检索片段、当前 run 的 hypothesis_evidence_links，"
                "以及经用户授权后的外部 MCP 文献候选合并而来；possible_counter_evidence 是从片段文本中检测到"
                "负面结果、失败、contradict 等标记，表示需要人工审计，不等同于最终科学反驳。"
            ),
            "rankingCaveat": (
                "Elo winner 来自 ranking/tournament 阶段的相对比较；evidence audit 是后置证据核验。"
                "如果 winner 后续出现潜在反证，应把它视为高优先级待核验假设，而不是已被证据支撑的结论。"
            ),
            "externalCheck": external_check or {
                "status": "not_requested",
                "summary": "尚未执行外部文献/MCP 反证检查。",
            },
            "nextActions": self._next_actions(verdict, missing_evidence, external_check),
            "groundingBoundary": "literature_mcp_audit" if external_check else "run_audit",
        }

    def build_counter_evidence_query(self, hypothesis_text: str) -> str:
        keywords = _terms(hypothesis_text)
        core = " ".join(keywords[:12]) or hypothesis_text[:240]
        return f"{core} contradictory negative result failed replication no effect"

    def classify_evidence_items(
        self,
        *,
        hypothesis_text: str,
        evidence_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Classify each retrieved item without claiming that lexical overlap proves truth."""
        hypothesis_terms = set(_terms(hypothesis_text))
        classified: List[Dict[str, Any]] = []
        for item in evidence_items:
            text = _first_text(
                item,
                ("text_preview", "preview", "evidence_summary", "experiment_data_summary", "summary"),
            )
            item_terms = set(_terms(f"{_first_text(item, ('title', 'chunk_title'))} {text}"))
            overlap = hypothesis_terms.intersection(item_terms)
            coverage = len(overlap) / max(1, len(hypothesis_terms))
            has_counter_marker = any(marker in text.lower() for marker in NEGATIVE_MARKERS)
            strong_source = (
                item.get("source_reliability") in {"parsed_fulltext", "experiment_run"}
                or item.get("support_level") == "experimental_data"
            )
            if not text.strip() or coverage < 0.08:
                relationship = "irrelevant"
                confidence = 0.7 if not text.strip() else 0.55
                rationale = "The chunk has insufficient lexical overlap with the hypothesis claim."
            elif has_counter_marker:
                relationship = "contradict"
                confidence = min(0.9, 0.55 + coverage)
                rationale = "The chunk overlaps the claim and contains a negative-result marker."
            elif strong_source and coverage >= 0.2:
                relationship = "support"
                confidence = min(0.9, 0.5 + coverage)
                rationale = "A strong-source chunk overlaps the hypothesis claim."
            else:
                relationship = "insufficient"
                confidence = min(0.75, 0.35 + coverage)
                rationale = "The chunk is relevant but too weak or incomplete to count as support."
            classified.append(
                {
                    **item,
                    "relationship": relationship,
                    "relationship_confidence": round(confidence, 2),
                    "relationship_rationale": rationale,
                    "matched_terms": sorted(overlap)[:12],
                    "claim_coverage": round(coverage, 3),
                    "possible_counter_evidence": has_counter_marker,
                }
            )
        return classified

    def external_packets_from_mcp_payload(
        self,
        *,
        payload: Dict[str, Any],
        query: str,
    ) -> List[Dict[str, Any]]:
        preview = str(payload.get("result_preview") or "").strip()
        if not preview:
            return []
        result_ref = payload.get("result_ref") if isinstance(payload.get("result_ref"), dict) else None
        return [
            {
                "result_id": result_ref.get("result_id") if result_ref else None,
                "title": f"MCP literature result: {payload.get('mcp_tool_name') or 'literature_review'}",
                "text_preview": preview[:900],
                "support_level": "external_literature_candidate",
                "source_reliability": "external_mcp_best_effort",
                "source_channel": "external_mcp",
                "evidence_path": result_ref.get("result_id") if result_ref else None,
                "query": query,
            }
        ]

    def _normalize_evidence(
        self,
        *,
        local_results: List[Dict[str, Any]],
        run_evidence_links: List[Dict[str, Any]],
        external_packets: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        normalized: List[Dict[str, Any]] = []
        for source_channel, items in (
            ("knowledge_base", local_results),
            ("run_link", run_evidence_links),
            ("external_mcp", external_packets),
        ):
            for item in items:
                key = _evidence_key(item)
                if key in seen:
                    continue
                seen.add(key)
                text = _first_text(item, ("text_preview", "preview", "evidence_summary", "experiment_data_summary", "summary"))
                title = _first_text(item, ("title", "chunk_title", "paper_id", "source"))
                possible_counter = any(marker in text.lower() for marker in NEGATIVE_MARKERS)
                support_signal = self._support_signal(item, text)
                normalized.append(
                    {
                        "evidence_id": item.get("evidence_id"),
                        "chunk_id": item.get("chunk_id"),
                        "paper_id": item.get("paper_id"),
                        "parse_run_id": item.get("parse_run_id"),
                        "title": title or "Evidence item",
                        "text_preview": text[:900],
                        "evidence_summary": _first_text(item, ("evidence_summary", "experiment_data_summary", "summary"))[:600],
                        "support_level": item.get("support_level") or "candidate",
                        "source_reliability": item.get("source_reliability") or "unknown",
                        "source_channel": item.get("source_channel") or source_channel,
                        "evidence_path": item.get("evidence_path"),
                        "score": item.get("score"),
                        "support_signal": support_signal,
                        "possible_counter_evidence": possible_counter,
                    }
                )
        return normalized

    def _support_signal(self, item: Dict[str, Any], text: str) -> int:
        signal = 0
        if item.get("source_reliability") == "parsed_fulltext":
            signal += 2
        if item.get("support_level") == "experimental_data":
            signal += 2
        if text.strip():
            signal += 1
        if item.get("source_channel") == "external_mcp" or item.get("source_reliability") == "external_mcp_best_effort":
            signal += 1
        return signal

    def _check_claims(self, hypothesis_text: str, evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        evidence_terms = {
            term
            for item in evidence_items
            for term in _terms(f"{item.get('title', '')} {item.get('text_preview', '')}")
        }
        checks: List[Dict[str, Any]] = []
        for claim in _split_claims(hypothesis_text):
            claim_terms = _terms(claim)
            overlap = [term for term in claim_terms if term in evidence_terms]
            ratio = len(overlap) / max(1, len(claim_terms))
            if not evidence_items:
                status = "ungrounded"
            elif ratio >= 0.45:
                status = "supported"
            elif ratio >= 0.2:
                status = "partially_supported"
            else:
                status = "missing"
            checks.append(
                {
                    "claim": claim[:500],
                    "status": status,
                    "matchedTerms": overlap[:12],
                    "coverage": round(ratio, 3),
                    "evidenceCount": len(evidence_items),
                }
            )
        return checks

    def _verdict(
        self,
        *,
        evidence_count: int,
        parsed_fulltext_count: int,
        experimental_count: int,
        covered_claim_count: int,
        claim_count: int,
        counter_count: int,
    ) -> str:
        if evidence_count == 0:
            return "ungrounded"
        if counter_count >= 2 and parsed_fulltext_count == 0:
            return "contradicted"
        coverage_ratio = covered_claim_count / max(1, claim_count)
        if parsed_fulltext_count >= 2 and experimental_count >= 1 and coverage_ratio >= 0.5:
            return "supported"
        if counter_count >= 1 and coverage_ratio < 0.4:
            return "contradicted"
        return "limited"

    def _confidence(
        self,
        *,
        verdict: str,
        evidence_count: int,
        parsed_fulltext_count: int,
        experimental_count: int,
        covered_claim_count: int,
        claim_count: int,
        counter_count: int,
    ) -> float:
        if evidence_count == 0:
            return 0.25
        coverage_ratio = covered_claim_count / max(1, claim_count)
        score = 0.22 + min(evidence_count, 6) * 0.05 + min(parsed_fulltext_count, 4) * 0.08
        score += min(experimental_count, 3) * 0.08 + coverage_ratio * 0.22
        if counter_count and verdict != "contradicted":
            score -= 0.12
        return round(max(0.1, min(score, 0.92)), 2)

    def _support_level(self, parsed_fulltext_count: int, experimental_count: int, evidence_count: int) -> str:
        if experimental_count:
            return "experimental_data"
        if parsed_fulltext_count:
            return "parsed_fulltext"
        if evidence_count:
            return "candidate_evidence"
        return "none"

    def _missing_evidence(
        self,
        *,
        evidence_count: int,
        parsed_fulltext_count: int,
        experimental_count: int,
        run_id: Optional[str],
        run_links_count: int,
        external_check: Optional[Dict[str, Any]],
    ) -> List[str]:
        missing: List[str] = []
        if evidence_count == 0:
            missing.append("当前知识库没有命中可审计证据片段。")
        if parsed_fulltext_count == 0:
            missing.append("缺少 parsed fulltext 级别证据；abstract、metadata 或候选片段不足以构成完整文献支撑。")
        if experimental_count == 0:
            missing.append("缺少实验数据、benchmark、dataset、metric 或可复现实验条件。")
        if run_id and run_links_count == 0:
            missing.append("当前 run 尚未形成 hypothesis_evidence_links，无法追溯到具体假设-证据链。")
        if not external_check:
            missing.append("尚未执行外部文献/MCP 反证检查。")
        elif external_check.get("status") != "complete":
            missing.append("外部文献/MCP 反证检查未完成或不可用。")
        return missing

    def _falsification_tests(self, hypothesis_text: str, missing_evidence: List[str]) -> List[str]:
        tests = [
            "把假设拆成机制、对象、干预、指标和实验条件，并为每个 claim 指定负面结果判据。",
            "优先寻找独立数据集或复现实验，检查同一效应是否在不同 cohort / benchmark 中保持。",
        ]
        if any("实验数据" in item for item in missing_evidence):
            tests.append("补充最小可行实验：定义 baseline、主要 metric、样本量/重复次数和失败阈值。")
        if any("反证" in item for item in missing_evidence):
            tests.append("执行外部文献反证检索，专门搜索 negative result、failed replication、no effect 等关键词。")
        if len(hypothesis_text) > 600:
            tests.append("假设文本较长，建议先拆成 2-4 条独立可证伪 claim 后逐条核验。")
        return tests

    def _summary(
        self,
        verdict: str,
        parsed_fulltext_count: int,
        experimental_count: int,
        counter_count: int,
        external_check: Optional[Dict[str, Any]],
    ) -> str:
        if verdict == "supported":
            return (
                f"当前核验找到 {parsed_fulltext_count} 条 parsed fulltext 和 "
                f"{experimental_count} 条实验线索支撑；仍需人工复核反证和实验可证伪性。"
            )
        if verdict == "contradicted":
            return "当前证据中存在潜在反证或负面结果标记，不能把该假设视为已支撑。"
        if verdict == "ungrounded":
            return "当前知识库没有找到可审计支撑，该假设只能标注为 ungrounded proposal。"
        if external_check and external_check.get("status") == "complete":
            return "外部文献/MCP 检查已接入，但 fulltext、实验或 claim 覆盖仍不足，结论保持 limited。"
        if counter_count:
            return "找到候选证据，但同时存在潜在反证标记，结论保持 limited。"
        return "找到候选证据，但 fulltext、实验数据或 claim 覆盖不足，结论保持 limited。"

    def _next_actions(
        self,
        verdict: str,
        missing_evidence: List[str],
        external_check: Optional[Dict[str, Any]],
    ) -> List[str]:
        actions = ["人工复核证据片段", "把假设拆成可证伪 claim"]
        if not external_check:
            actions.append("执行外部文献/MCP 反证检查")
        if any("parsed fulltext" in item for item in missing_evidence):
            actions.append("解析更多 fulltext PDF")
        if any("实验数据" in item for item in missing_evidence):
            actions.append("补充实验设计或 benchmark")
        if verdict == "contradicted":
            actions.append("优先检查反证来源和负面结果解释")
        return actions[:5]
