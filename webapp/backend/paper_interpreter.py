from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

import fitz
import requests

try:
    from backend.pdf_parser import DOI_PATTERN
except ModuleNotFoundError:
    from pdf_parser import DOI_PATTERN


TranslateFn = Callable[[str], Awaitable[str]]

MEDIA_PATTERN = re.compile(
    r"\b(fig(?:ure)?\.?|table|algorithm|alg\.?|pseudocode|流程图|框架图)\s*[\w.\-]*",
    re.I,
)
SECTION_HEADING_PATTERN = re.compile(
    r"^\s*((?:\d+(?:\.\d+)*|[IVX]+)\.?\s+)?"
    r"(abstract|introduction|related work|background|preliminaries|method|methods|methodology|"
    r"optimization|theory|experiments?|experimental setup|results?|discussion|conclusion|"
    r"limitations?|acknowledg(?:e)?ments?|appendix|references)\b.*$",
    re.I,
)


@dataclass
class InterpretMediaAsset:
    kind: str
    page: int
    path: str
    markdown_path: str
    caption_preview: str


@dataclass
class PaperInterpretResult:
    pdf_path: str
    output_name: str
    title: str
    doi: Optional[str]
    page_count: int
    markdown_path: str
    extracted_text_path: str
    bibtex_path: Optional[str]
    official_metadata_path: str
    published_plain_text_path: Optional[str]
    media_dir: str
    media_assets: List[InterpretMediaAsset] = field(default_factory=list)
    image_links_checked: int = 0
    missing_image_links: List[str] = field(default_factory=list)
    bibtex_source: str = "not_available"
    plain_text_source_note: str = ""


def _safe_output_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value.strip())
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._")
    if not cleaned:
        raise ValueError("Output name must not be empty")
    return cleaned[:120]


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_doi_from_pdf(text: str, metadata: Dict[str, Any]) -> Optional[str]:
    candidates = [
        metadata.get("doi"),
        metadata.get("subject"),
        metadata.get("keywords"),
        metadata.get("title"),
        text[:6000],
    ]
    for candidate in candidates:
        match = DOI_PATTERN.search(str(candidate or ""))
        if match:
            return match.group(0).rstrip(".,);]").lower()
    return None


def _crossref_by_doi(doi: Optional[str]) -> Dict[str, Any]:
    if not doi:
        return {}
    try:
        response = requests.get(f"https://api.crossref.org/works/{doi}", timeout=20)
        if response.ok:
            return response.json().get("message", {})
    except (requests.RequestException, ValueError):
        return {}
    return {}


def _crossref_by_title(title: str) -> Dict[str, Any]:
    if not title.strip():
        return {}
    try:
        response = requests.get(
            "https://api.crossref.org/works",
            params={"query.title": title, "rows": 1},
            timeout=20,
        )
        if not response.ok:
            return {}
        items = response.json().get("message", {}).get("items", [])
        if not items:
            return {}
        candidate = items[0]
        candidate_title = _clean_text((candidate.get("title") or [""])[0]).lower()
        normalized_title = _clean_text(title).lower()
        if candidate_title and (candidate_title == normalized_title or normalized_title in candidate_title):
            return candidate
    except (requests.RequestException, ValueError):
        return {}
    return {}


def _format_author(author: Dict[str, Any]) -> str:
    given = author.get("given", "")
    family = author.get("family", "")
    name = _clean_text(f"{given} {family}")
    return name or _clean_text(author.get("name", ""))


def _year_from_crossref(metadata: Dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "issued"):
        parts = metadata.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            return str(parts[0][0])
    return ""


def _official_metadata_text(title: str, doi: Optional[str], metadata: Dict[str, Any], pdf_path: Path) -> str:
    authors = ", ".join(_format_author(author) for author in metadata.get("author", []) if isinstance(author, dict))
    container = "; ".join(metadata.get("container-title", []) or [])
    pages = metadata.get("page", "")
    volume = metadata.get("volume", "")
    issue = metadata.get("issue", "")
    abstract = re.sub(r"<[^>]+>", "", metadata.get("abstract", "") or "").strip()
    keywords = ", ".join(metadata.get("subject", []) or [])
    lines = [
        f"DOI: {doi or metadata.get('DOI', '') or ''}",
        f"Title: {_clean_text((metadata.get('title') or [title])[0] if metadata else title)}",
        f"Authors: {authors}",
        f"Journal/Conference: {container}",
        f"Year: {_year_from_crossref(metadata)}",
        f"Volume: {volume}",
        f"Issue: {issue}",
        f"Pages: {pages}",
        f"Publisher: {metadata.get('publisher', '')}",
        f"URL: {metadata.get('URL', '')}",
        f"Keywords: {keywords}",
        f"Abstract: {abstract}",
        f"Local PDF: {pdf_path}",
    ]
    return "\n".join(lines) + "\n"


def _normalize_bibtex(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"pages\s*=\s*[{\"](\d+)\s*-\s*(\d+)[}\"]", r"pages = {\1--\2}", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip() + "\n"


def _fetch_bibtex(doi: Optional[str], metadata: Dict[str, Any], output_path: Path) -> tuple[Optional[Path], str]:
    if doi:
        try:
            response = requests.get(
                f"https://doi.org/{doi}",
                headers={"Accept": "application/x-bibtex"},
                timeout=20,
            )
            if response.ok and response.text.strip():
                output_path.write_text(_normalize_bibtex(response.text), encoding="utf-8")
                return output_path, "doi_content_negotiation"
        except requests.RequestException:
            pass
    if metadata.get("DOI"):
        try:
            response = requests.get(
                f"https://api.crossref.org/works/{metadata['DOI']}/transform/application/x-bibtex",
                timeout=20,
            )
            if response.ok and response.text.strip():
                output_path.write_text(_normalize_bibtex(response.text), encoding="utf-8")
                return output_path, "crossref_transform"
        except requests.RequestException:
            pass
    return None, "not_available"


def _caption_kind(text: str) -> str:
    lowered = text.lower()
    if "algorithm" in lowered or "pseudocode" in lowered or "alg." in lowered:
        return "algorithm"
    if "table" in lowered:
        return "table"
    return "figure"


def _clip_caption(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    page_rect = page.rect
    y0 = max(0, rect.y0 - page_rect.height * 0.38)
    y1 = min(page_rect.height, rect.y1 + 24)
    if y1 - y0 < 100:
        y0 = max(0, rect.y0 - 180)
    return fitz.Rect(max(0, rect.x0 - 28), y0, min(page_rect.width, rect.x1 + 28), y1)


def _extract_media(doc: fitz.Document, media_dir: Path) -> list[InterpretMediaAsset]:
    media_dir.mkdir(parents=True, exist_ok=True)
    assets: list[InterpretMediaAsset] = []
    seen: set[tuple[int, int, int, int, int]] = set()
    for page_index, page in enumerate(doc):
        for block in page.get_text("blocks"):
            x0, y0, x1, y1, text, *_ = block
            if not MEDIA_PATTERN.search(text or ""):
                continue
            clip = _clip_caption(page, fitz.Rect(x0, y0, x1, y1))
            key = (page_index, round(clip.x0), round(clip.y0), round(clip.x1), round(clip.y1))
            if key in seen:
                continue
            seen.add(key)
            kind = _caption_kind(text)
            filename = f"{kind}_{len(assets) + 1:02d}_p{page_index + 1}.png"
            path = media_dir / filename
            pix = page.get_pixmap(matrix=fitz.Matrix(220 / 72, 220 / 72), clip=clip, alpha=False)
            pix.save(str(path))
            assets.append(
                InterpretMediaAsset(
                    kind=kind,
                    page=page_index + 1,
                    path=str(path),
                    markdown_path=f"media/{filename}",
                    caption_preview=_clean_text(text)[:300],
                )
            )
    return assets


def _split_sections_by_page(page_texts: list[tuple[int, str]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current = {"title": "Document", "page_start": 1, "text": []}
    for page_number, text in page_texts:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if SECTION_HEADING_PATTERN.match(line) and len(line) <= 120:
                if "\n".join(current["text"]).strip():
                    sections.append(current)
                current = {"title": line, "page_start": page_number, "text": []}
            current["text"].append(raw_line)
    if "\n".join(current["text"]).strip():
        sections.append(current)
    return sections


def _chunk_for_translation(text: str, limit: int = 9000) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in paragraphs:
        if current and current_len + len(paragraph) > limit:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(paragraph)
        current_len += len(paragraph)
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text[:limit]]


async def _translate_section(title: str, text: str, translate: TranslateFn) -> str:
    translated_parts: list[str] = []
    for chunk in _chunk_for_translation(text):
        prompt = (
            "你是科研论文翻译助手。请将以下论文段落翻译为中文结构化译稿。\n"
            "必须保留公式、变量名、算法名、数据集名、评价指标、方法名、定理名和参考文献编号的英文/数学原文。\n"
            "不要改写公式含义，不要补充原文没有的科学结论。保留列表、编号和段落层次。\n\n"
            f"章节标题：{title}\n\n原文：\n{chunk}"
        )
        translated_parts.append((await translate(prompt)).strip())
    return "\n\n".join(translated_parts)


def _insert_media_for_section(
    markdown: str,
    section_page_start: int,
    section_page_end: int,
    assets: list[InterpretMediaAsset],
) -> str:
    matching = [
        asset
        for asset in assets
        if section_page_start <= asset.page <= section_page_end
    ]
    if not matching:
        return markdown
    media_md = "\n\n".join(
        f"![{asset.kind} p{asset.page}]({asset.markdown_path})\n\n> {asset.caption_preview}"
        for asset in matching
    )
    return f"{markdown}\n\n{media_md}"


def _validate_markdown_images(markdown_path: Path) -> tuple[int, list[str]]:
    text = markdown_path.read_text(encoding="utf-8")
    links = re.findall(r"!\[[^\]]*]\(([^)]+)\)", text)
    missing = [link for link in links if not (markdown_path.parent / link).exists()]
    return len(links), missing


async def interpret_paper_pdf(
    pdf_path: Path,
    output_name: str,
    *,
    translate: TranslateFn,
    fetch_metadata: bool = True,
) -> PaperInterpretResult:
    resolved = pdf_path.expanduser().resolve()
    if not resolved.exists() or resolved.suffix.lower() != ".pdf":
        raise FileNotFoundError("PDF file was not found")
    safe_name = _safe_output_name(output_name)
    output_dir = resolved.parent
    media_dir = output_dir / "media"
    markdown_path = output_dir / f"{safe_name}_中文译稿.md"
    extracted_text_path = output_dir / f"{safe_name}.extracted.txt"
    bibtex_output_path = output_dir / f"{safe_name}.bib"
    official_metadata_path = output_dir / f"{safe_name}_official_metadata_plain_text.txt"
    published_plain_text_path = output_dir / f"{safe_name}_published_plain_text.txt"

    with fitz.open(str(resolved)) as doc:
        pdf_metadata = dict(doc.metadata or {})
        page_texts = [(index + 1, page.get_text("text")) for index, page in enumerate(doc)]
        full_text = "\n\n".join(f"===== Page {page} =====\n{text}" for page, text in page_texts)
        title = _clean_text(pdf_metadata.get("title")) or resolved.stem
        media_assets = _extract_media(doc, media_dir)
        page_count = doc.page_count

    extracted_text_path.write_text(full_text + "\n", encoding="utf-8")
    doi = _extract_doi_from_pdf(full_text, pdf_metadata)
    crossref = _crossref_by_doi(doi) if fetch_metadata else {}
    if not crossref and fetch_metadata:
        crossref = _crossref_by_title(title)
        doi = doi or str(crossref.get("DOI") or "").lower() or None
    if crossref.get("title"):
        title = _clean_text(crossref["title"][0])

    official_metadata_path.write_text(
        _official_metadata_text(title, doi, crossref, resolved),
        encoding="utf-8",
    )
    bibtex_path, bibtex_source = _fetch_bibtex(doi, crossref, bibtex_output_path) if fetch_metadata else (None, "disabled")

    published_plain_text_written: Optional[Path] = None
    abstract = re.sub(r"<[^>]+>", "", crossref.get("abstract", "") or "").strip()
    if abstract:
        published_plain_text_path.write_text(
            f"Official abstract from Crossref metadata.\n\nTitle: {title}\nDOI: {doi or ''}\n\n{abstract}\n",
            encoding="utf-8",
        )
        published_plain_text_written = published_plain_text_path

    sections = _split_sections_by_page(page_texts)
    markdown_parts = [
        f"# {title}",
        "",
        "## 文献来源边界",
        f"- 本地 PDF：`{resolved}`",
        f"- DOI：{doi or '未识别'}",
        f"- BibTeX 来源：{bibtex_source}",
        "- 开放 plain text："
        + ("Crossref official abstract" if published_plain_text_written else "未发现合法开放全文 plain text；使用本地 PDF 抽取全文作为翻译来源。"),
        "",
    ]
    for index, section in enumerate(sections):
        section_title = _clean_text(section["title"]) or "Document"
        section_text = "\n".join(section["text"]).strip()
        translated = await _translate_section(section_title, section_text, translate)
        section_page_start = int(section["page_start"])
        next_page_start = (
            int(sections[index + 1]["page_start"])
            if index + 1 < len(sections)
            else page_count + 1
        )
        section_page_end = max(section_page_start, next_page_start - 1)
        markdown_parts.append(f"## {section_title}")
        markdown_parts.append(
            _insert_media_for_section(
                translated,
                section_page_start,
                section_page_end,
                media_assets,
            )
        )
        markdown_parts.append("")

    markdown_parts.extend(
        [
            "## 生成报告",
            f"- Markdown：`{markdown_path.name}`",
            f"- 抽取全文：`{extracted_text_path.name}`",
            f"- 官方元数据：`{official_metadata_path.name}`",
            f"- BibTeX：`{bibtex_path.name if bibtex_path else '未生成'}`",
            f"- 媒介截图数量：{len(media_assets)}",
        ]
    )
    markdown_path.write_text("\n".join(markdown_parts).strip() + "\n", encoding="utf-8")
    link_count, missing_links = _validate_markdown_images(markdown_path)
    markdown_parts.append(f"- Markdown 图片链接校验：{link_count} 个链接，缺失 {len(missing_links)} 个")
    if missing_links:
        markdown_parts.append(f"- 缺失图片链接：{', '.join(missing_links)}")
    markdown_path.write_text("\n".join(markdown_parts).strip() + "\n", encoding="utf-8")

    return PaperInterpretResult(
        pdf_path=str(resolved),
        output_name=safe_name,
        title=title,
        doi=doi,
        page_count=page_count,
        markdown_path=str(markdown_path),
        extracted_text_path=str(extracted_text_path),
        bibtex_path=str(bibtex_path) if bibtex_path else None,
        official_metadata_path=str(official_metadata_path),
        published_plain_text_path=str(published_plain_text_written) if published_plain_text_written else None,
        media_dir=str(media_dir),
        media_assets=media_assets,
        image_links_checked=link_count,
        missing_image_links=missing_links,
        bibtex_source=bibtex_source,
        plain_text_source_note=(
            "Crossref official abstract saved as published plain text."
            if published_plain_text_written
            else "No legal open full-text plain text was found; local PDF extracted text was saved and used."
        ),
    )


def result_to_dict(result: PaperInterpretResult) -> Dict[str, Any]:
    data = asdict(result)
    data["created_at"] = time.time()
    return data
