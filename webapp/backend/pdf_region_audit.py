from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

import fitz


RiskLevel = Literal["ok", "review", "high"]

CAPTION_NUMBER_PATTERN = re.compile(r"\b(?:fig(?:ure)?\.?|table|algorithm)\s*\d+[a-z]?\b", re.I)
FORMULA_HINT_PATTERN = re.compile(r"(∑|∫|√|≈|≤|≥|=|\\frac|\\sum|\\int|\$[^$]+\$)")

MIN_PNG_BYTES = 12 * 1024
MIN_PNG_DIMENSION = 160
MIN_CLIP_PAGE_HEIGHT_RATIO = 0.08
MAX_CLIP_PAGE_HEIGHT_RATIO = 0.65
ADJACENT_CAPTION_DISTANCE = 72


@dataclass
class PdfRegionRiskFlag:
    code: str
    severity: RiskLevel
    message: str
    evidence: dict[str, Any]


def _rect_from_block(block: Any) -> Optional[fitz.Rect]:
    try:
        return fitz.Rect(float(block[0]), float(block[1]), float(block[2]), float(block[3]))
    except (TypeError, ValueError, IndexError):
        return None


def _text_from_block(block: Any) -> str:
    try:
        return str(block[4] or "")
    except (TypeError, IndexError):
        return ""


def _rects_overlap(a: fitz.Rect, b: fitz.Rect) -> bool:
    return not (a.x1 < b.x0 or a.x0 > b.x1 or a.y1 < b.y0 or a.y0 > b.y1)


def _unique_caption_numbers(text: str) -> set[str]:
    return {match.group(0).lower().replace("figure", "fig").strip() for match in CAPTION_NUMBER_PATTERN.finditer(text)}


def _has_nearby_other_caption(
    *,
    blocks: Iterable[Any],
    caption_block_rect: fitz.Rect,
    clip_rect: fitz.Rect,
    caption_text: str,
) -> Optional[dict[str, Any]]:
    normalized_caption = re.sub(r"\s+", " ", caption_text).strip()
    for block in blocks:
        block_text = re.sub(r"\s+", " ", _text_from_block(block)).strip()
        if not block_text or not CAPTION_NUMBER_PATTERN.search(block_text):
            continue
        block_rect = _rect_from_block(block)
        if not block_rect:
            continue
        if block_rect == caption_block_rect or block_text == normalized_caption:
            continue
        vertical_gap = min(abs(block_rect.y0 - clip_rect.y1), abs(clip_rect.y0 - block_rect.y1))
        if vertical_gap <= ADJACENT_CAPTION_DISTANCE or _rects_overlap(block_rect, clip_rect):
            return {
                "caption": block_text[:180],
                "vertical_gap": round(vertical_gap, 2),
                "block_rect": [round(block_rect.x0, 2), round(block_rect.y0, 2), round(block_rect.x1, 2), round(block_rect.y1, 2)],
            }
    return None


def _has_drawing_or_non_caption_content(
    *,
    clip_rect: fitz.Rect,
    blocks: Iterable[Any],
    caption_block_rect: fitz.Rect,
    drawing_rects: Iterable[fitz.Rect],
) -> bool:
    for rect in drawing_rects:
        if _rects_overlap(rect, clip_rect):
            return True
    for block in blocks:
        block_rect = _rect_from_block(block)
        if not block_rect or block_rect == caption_block_rect:
            continue
        text = _text_from_block(block)
        if CAPTION_NUMBER_PATTERN.search(text):
            continue
        if _rects_overlap(block_rect, clip_rect):
            return True
    return False


def _risk_level(flags: list[PdfRegionRiskFlag]) -> RiskLevel:
    if any(flag.severity == "high" for flag in flags):
        return "high"
    if flags:
        return "review"
    return "ok"


def _confidence(flags: list[PdfRegionRiskFlag]) -> float:
    score = 1.0
    for flag in flags:
        score -= 0.24 if flag.severity == "high" else 0.12
    return round(max(0.05, min(1.0, score)), 2)


def audit_pdf_region(
    *,
    caption_text: str,
    clip_rect: fitz.Rect,
    page_rect: fitz.Rect,
    blocks: Iterable[Any],
    image_path: Path,
    pixel_width: int,
    pixel_height: int,
    caption_block_rect: fitz.Rect,
    drawing_rects: Optional[Iterable[fitz.Rect]] = None,
) -> dict[str, Any]:
    flags: list[PdfRegionRiskFlag] = []
    drawing_rects = list(drawing_rects or [])
    blocks = list(blocks)

    caption_numbers = _unique_caption_numbers(caption_text)
    if len(caption_numbers) > 1:
        flags.append(
            PdfRegionRiskFlag(
                code="multiple_caption_numbers",
                severity="high",
                message="裁剪区域内识别到多个 caption 编号，可能混入相邻图表。",
                evidence={"caption_numbers": sorted(caption_numbers), "caption_preview": caption_text[:240]},
            )
        )

    nearby_caption = _has_nearby_other_caption(
        blocks=blocks,
        caption_block_rect=caption_block_rect,
        clip_rect=clip_rect,
        caption_text=caption_text,
    )
    if nearby_caption:
        flags.append(
            PdfRegionRiskFlag(
                code="adjacent_caption_title",
                severity="high",
                message="裁剪区域附近存在另一个 Figure/Table/Algorithm 标题。",
                evidence=nearby_caption,
            )
        )

    height_ratio = clip_rect.height / max(page_rect.height, 1)
    if height_ratio < MIN_CLIP_PAGE_HEIGHT_RATIO or height_ratio > MAX_CLIP_PAGE_HEIGHT_RATIO:
        flags.append(
            PdfRegionRiskFlag(
                code="abnormal_crop_height",
                severity="review",
                message="裁剪区域高度相对页面异常，可能漏掉图体或包含过多上下文。",
                evidence={"height_ratio": round(height_ratio, 4), "clip_height": round(clip_rect.height, 2), "page_height": round(page_rect.height, 2)},
            )
        )

    file_size = image_path.stat().st_size if image_path.exists() else 0
    if file_size < MIN_PNG_BYTES or pixel_width < MIN_PNG_DIMENSION or pixel_height < MIN_PNG_DIMENSION:
        flags.append(
            PdfRegionRiskFlag(
                code="tiny_png_file",
                severity="review",
                message="PNG 文件过小或截图尺寸过小，可能不是完整图体。",
                evidence={"file_size_bytes": file_size, "width": pixel_width, "height": pixel_height},
            )
        )

    touches_boundary = (
        clip_rect.x0 <= page_rect.x0 + 2
        or clip_rect.y0 <= page_rect.y0 + 2
        or clip_rect.x1 >= page_rect.x1 - 2
        or clip_rect.y1 >= page_rect.y1 - 2
    )
    has_content = _has_drawing_or_non_caption_content(
        clip_rect=clip_rect,
        blocks=blocks,
        caption_block_rect=caption_block_rect,
        drawing_rects=drawing_rects,
    )
    if touches_boundary or not has_content:
        flags.append(
            PdfRegionRiskFlag(
                code="incomplete_pdf_block_coverage",
                severity="review",
                message="PDF block 或页面边界提示裁剪区域可能没有覆盖完整图体。",
                evidence={"touches_page_boundary": touches_boundary, "has_non_caption_content_or_drawing": has_content},
            )
        )

    spans_columns = clip_rect.x0 < page_rect.width * 0.35 and clip_rect.x1 > page_rect.width * 0.65
    formula_like = bool(FORMULA_HINT_PATTERN.search(caption_text))
    if spans_columns or formula_like:
        flags.append(
            PdfRegionRiskFlag(
                code="cross_column_or_formula_region",
                severity="review",
                message="区域疑似跨栏，或包含公式/图注/图体混杂内容。",
                evidence={"spans_columns": spans_columns, "formula_like_caption": formula_like},
            )
        )

    risk_level = _risk_level(flags)
    return {
        "risk_level": risk_level,
        "risk_flags": [asdict(flag) for flag in flags],
        "review_required": risk_level != "ok",
        "confidence": _confidence(flags),
        "file_size_bytes": file_size,
        "width": pixel_width,
        "height": pixel_height,
    }


def summarize_media_region_quality(media_assets: Iterable[Any]) -> dict[str, int]:
    total = 0
    review = 0
    high = 0
    ok = 0
    for asset in media_assets:
        total += 1
        risk_level = asset.get("risk_level") if isinstance(asset, dict) else getattr(asset, "risk_level", "ok")
        if risk_level == "high":
            high += 1
        elif risk_level == "review":
            review += 1
        else:
            ok += 1
    return {"total": total, "ok": ok, "review": review, "high": high}
