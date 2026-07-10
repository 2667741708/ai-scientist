from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz
import requests

try:
    from backend.knowledge_base import PaperDocument, hierarchical_chunk_paper
    from backend.pdf_region_audit import audit_pdf_region
except ModuleNotFoundError:
    from knowledge_base import PaperDocument, hierarchical_chunk_paper
    from pdf_region_audit import audit_pdf_region


CAPTION_PATTERN = re.compile(r"\b(fig(?:ure)?\.?|table|algorithm)\s*\d+", re.I)
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)


@dataclass
class PdfMediaAsset:
    asset_id: str
    kind: str
    page: int
    rect: List[float]
    path: str
    caption_preview: str
    width: int
    height: int
    file_size_bytes: int
    confidence: float
    risk_level: str
    risk_flags: List[Dict[str, Any]] = field(default_factory=list)
    review_required: bool = False


@dataclass
class PdfParseResult:
    pdf_path: str
    solve_dir: str
    title: str
    page_count: int
    doi: Optional[str]
    metadata: Dict[str, Any]
    extracted_text_path: str
    metadata_json_path: str
    metadata_text_path: str
    chunks_json_path: str
    bibtex_path: Optional[str]
    media_assets: List[PdfMediaAsset] = field(default_factory=list)
    content: str = ""
    abstract: Optional[str] = None


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _safe_stem(path: Path) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", path.stem).strip("._") or "paper"


def _extract_doi(text: str, metadata: Dict[str, Any]) -> Optional[str]:
    candidates = [
        _clean(metadata.get("doi")),
        _clean(metadata.get("subject")),
        _clean(metadata.get("keywords")),
        text[:12000],
    ]
    for candidate in candidates:
        match = DOI_PATTERN.search(candidate)
        if match:
            return match.group(0).rstrip(".,);]").lower()
    return None


def _extract_abstract(text: str) -> Optional[str]:
    match = re.search(
        r"\babstract\b\s*(.+?)(?:\n\s*(?:1\s+)?(?:introduction|keywords?|index terms)\b)",
        text,
        flags=re.I | re.S,
    )
    if not match:
        return None
    abstract = re.sub(r"\s+", " ", match.group(1)).strip()
    return abstract[:20000] if len(abstract) >= 40 else None


def _fetch_bibtex(doi: Optional[str], solve_dir: Path) -> Optional[Path]:
    if not doi:
        return None
    try:
        response = requests.get(
            f"https://doi.org/{doi}",
            headers={"Accept": "application/x-bibtex"},
            timeout=20,
        )
        if response.ok and response.text.strip():
            path = solve_dir / "bibtex.bib"
            path.write_text(response.text.strip() + "\n", encoding="utf-8")
            return path
    except requests.RequestException:
        return None
    return None


def _fetch_crossref_metadata(doi: Optional[str]) -> Dict[str, Any]:
    if not doi:
        return {}
    try:
        response = requests.get(f"https://api.crossref.org/works/{doi}", timeout=20)
        if response.ok:
            return response.json().get("message", {})
    except (requests.RequestException, ValueError):
        return {}
    return {}


def _caption_kind(text: str) -> str:
    normalized = text.lower()
    if "algorithm" in normalized:
        return "algorithm"
    if "table" in normalized:
        return "table"
    return "figure"


def _clip_for_caption(page: fitz.Page, block_rect: fitz.Rect) -> fitz.Rect:
    page_rect = page.rect
    height = page_rect.height
    x0 = max(0, block_rect.x0 - 24)
    x1 = min(page_rect.width, block_rect.x1 + 24)
    y0 = max(0, block_rect.y0 - height * 0.36)
    y1 = min(page_rect.height, block_rect.y1 + 18)
    if y1 - y0 < 80:
        y0 = max(0, block_rect.y0 - 140)
    return fitz.Rect(x0, y0, x1, y1)


def _render_caption_assets(doc: fitz.Document, media_dir: Path, *, dpi: int = 220) -> List[PdfMediaAsset]:
    media_dir.mkdir(parents=True, exist_ok=True)
    assets: List[PdfMediaAsset] = []
    seen: set[tuple[int, int, int, int, int]] = set()
    for page_index, page in enumerate(doc):
        blocks = page.get_text("blocks")
        try:
            drawing_rects = [drawing["rect"] for drawing in page.get_drawings() if drawing.get("rect")]
        except Exception:
            drawing_rects = []
        for block in blocks:
            x0, y0, x1, y1, text, *_ = block
            if not CAPTION_PATTERN.search(text or ""):
                continue
            clip = _clip_for_caption(page, fitz.Rect(x0, y0, x1, y1))
            key = (page_index, round(clip.x0), round(clip.y0), round(clip.x1), round(clip.y1))
            if key in seen:
                continue
            seen.add(key)
            kind = _caption_kind(text)
            asset_id = f"{kind}_{len(assets) + 1:02d}_p{page_index + 1}"
            filename = f"{asset_id}.png"
            path = media_dir / filename
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=clip, alpha=False)
            pix.save(str(path))
            audit = audit_pdf_region(
                caption_text=text or "",
                clip_rect=clip,
                page_rect=page.rect,
                blocks=blocks,
                image_path=path,
                pixel_width=pix.width,
                pixel_height=pix.height,
                caption_block_rect=fitz.Rect(x0, y0, x1, y1),
                drawing_rects=drawing_rects,
            )
            assets.append(
                PdfMediaAsset(
                    asset_id=asset_id,
                    kind=kind,
                    page=page_index + 1,
                    rect=[round(clip.x0, 2), round(clip.y0, 2), round(clip.x1, 2), round(clip.y1, 2)],
                    path=str(path),
                    caption_preview=re.sub(r"\s+", " ", text).strip()[:300],
                    width=audit["width"],
                    height=audit["height"],
                    file_size_bytes=audit["file_size_bytes"],
                    confidence=audit["confidence"],
                    risk_level=audit["risk_level"],
                    risk_flags=audit["risk_flags"],
                    review_required=audit["review_required"],
                )
            )
    return assets


def parse_pdf_to_solve(pdf_path: Path, *, fetch_metadata: bool = True) -> PdfParseResult:
    resolved = pdf_path.expanduser().resolve()
    if not resolved.exists() or resolved.suffix.lower() != ".pdf":
        raise FileNotFoundError("PDF file was not found")
    solve_dir = resolved.parent / "solve"
    media_dir = solve_dir / "media"
    solve_dir.mkdir(parents=True, exist_ok=True)

    stem = _safe_stem(resolved)
    with fitz.open(str(resolved)) as doc:
        metadata = dict(doc.metadata or {})
        page_text_parts: list[str] = []
        for index, page in enumerate(doc, start=1):
            page_text_parts.append(f"\n\n===== Page {index} =====\n{page.get_text('text')}")
        content = "".join(page_text_parts).strip()
        doi = _extract_doi(content, metadata)
        title = _clean(metadata.get("title")) or resolved.stem
        abstract = _extract_abstract(content)
        media_assets = _render_caption_assets(doc, media_dir)
        page_count = doc.page_count

    crossref = _fetch_crossref_metadata(doi) if fetch_metadata else {}
    if crossref.get("title"):
        title = str(crossref["title"][0])

    metadata_payload = {
        "pdf_path": str(resolved),
        "parsed_at": time.time(),
        "page_count": page_count,
        "doi": doi,
        "pdf_metadata": metadata,
        "crossref": crossref,
        "media_assets": [asdict(asset) for asset in media_assets],
    }
    extracted_text_path = solve_dir / f"{stem}.extracted.txt"
    metadata_json_path = solve_dir / "metadata.json"
    metadata_text_path = solve_dir / "metadata.txt"
    chunks_json_path = solve_dir / "chunks.json"
    media_region_audit_path = solve_dir / "media_region_audit.json"
    extracted_text_path.write_text(content + "\n", encoding="utf-8")
    metadata_json_path.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    media_region_audit_path.write_text(
        json.dumps([asdict(asset) for asset in media_assets], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    metadata_text_path.write_text(
        "\n".join(
            [
                f"Title: {title}",
                f"DOI: {doi or ''}",
                f"Pages: {page_count}",
                f"Source PDF: {resolved}",
                f"Media assets: {len(media_assets)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    paper = PaperDocument(
        paper_id=f"pdf_preview_{stem}",
        title=title,
        doi=doi,
        url=str(resolved),
        abstract=abstract,
        source="local_pdf",
        source_reliability="parsed_fulltext",
        metadata=metadata_payload,
        content=content,
    )
    paper.chunks = hierarchical_chunk_paper(paper)
    chunks_json_path.write_text(
        json.dumps([asdict(chunk) for chunk in paper.chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    bibtex_path = _fetch_bibtex(doi, solve_dir) if fetch_metadata else None

    return PdfParseResult(
        pdf_path=str(resolved),
        solve_dir=str(solve_dir),
        title=title,
        page_count=page_count,
        doi=doi,
        metadata=metadata_payload,
        extracted_text_path=str(extracted_text_path),
        metadata_json_path=str(metadata_json_path),
        metadata_text_path=str(metadata_text_path),
        chunks_json_path=str(chunks_json_path),
        bibtex_path=str(bibtex_path) if bibtex_path else None,
        media_assets=media_assets,
        content=content,
        abstract=abstract,
    )
