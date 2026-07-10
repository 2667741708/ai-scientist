"""
Academic search tools for non-biomedical literature sources.

The bundled PubMed implementation is excellent for biomedical papers but misses
most AI/ML literature. These tools add public arXiv search, best-effort public
Google Scholar HTML search, and lightweight content retrieval for open pages and
PDFs.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pdfminer.high_level import extract_text

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 OpenCoscientistLiteratureMCP/0.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
HTTP_TIMEOUT = httpx.Timeout(60.0, connect=15.0)
MAX_SEARCH_RESULTS = 20
MAX_CONTENT_CHARS = 200_000


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _source_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("||".join(parts).encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _safe_year(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    match = re.search(r"(19|20)\d{2}", value)
    return int(match.group(0)) if match else None


def _arxiv_pdf_url(arxiv_id: str) -> str:
    clean_id = arxiv_id.split("v")[0] if re.search(r"v\d+$", arxiv_id) else arxiv_id
    return f"https://arxiv.org/pdf/{clean_id}.pdf"


def _normalize_pdf_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("arxiv.org") and parsed.path.startswith("/abs/"):
        arxiv_id = parsed.path.removeprefix("/abs/")
        return _arxiv_pdf_url(arxiv_id)
    return url


async def search_arxiv(
    query: str,
    max_results: int = 10,
    starting_year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Search arXiv's public Atom API.

    Args:
        query: Natural language or keyword query.
        max_results: Maximum results to return.
        starting_year: Optional lower bound for publication year.

    Returns:
        {"results": [...]} with metadata and direct PDF URLs.
    """
    max_results = max(1, min(int(max_results or 10), MAX_SEARCH_RESULTS))
    params = {
        "search_query": f"all:{query}",
        "start": "0",
        "max_results": str(max_results),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    logger.info(
        "Searching arXiv query=%r max_results=%s starting_year=%s",
        query,
        max_results,
        starting_year,
    )

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=DEFAULT_HEADERS) as client:
            response = await client.get("https://export.arxiv.org/api/query", params=params)
            if response.status_code == 429:
                logger.warning("arXiv Atom API returned 429; falling back to arxiv.org HTML search")
                return await _search_arxiv_html(query, max_results, starting_year)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("arXiv Atom API failed; falling back to HTML search: %s", exc)
        return await _search_arxiv_html(query, max_results, starting_year)

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(response.text)
    results: List[Dict[str, Any]] = []

    for entry in root.findall("atom:entry", ns):
        entry_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        arxiv_id = entry_id.rstrip("/").split("/")[-1]
        published = entry.findtext("atom:published", default="", namespaces=ns)
        year = _safe_year(published)
        if starting_year and year and year < starting_year:
            continue

        pdf_url = ""
        html_url = entry_id
        for link in entry.findall("atom:link", ns):
            href = link.attrib.get("href", "")
            title = link.attrib.get("title", "")
            rel = link.attrib.get("rel", "")
            link_type = link.attrib.get("type", "")
            if title == "pdf" or link_type == "application/pdf":
                pdf_url = href
            elif rel == "alternate" and href:
                html_url = href
        if not pdf_url and arxiv_id:
            pdf_url = _arxiv_pdf_url(arxiv_id)

        authors = [
            _clean_text(author.findtext("atom:name", default="", namespaces=ns))
            for author in entry.findall("atom:author", ns)
        ]
        categories = [cat.attrib.get("term", "") for cat in entry.findall("atom:category", ns)]
        primary_category = (
            entry.find("arxiv:primary_category", ns).attrib.get("term", "")
            if entry.find("arxiv:primary_category", ns) is not None
            else (categories[0] if categories else "")
        )

        results.append(
            {
                "title": _clean_text(entry.findtext("atom:title", default="", namespaces=ns)),
                "url": html_url,
                "authors": [author for author in authors if author],
                "year": year,
                "abstract": _clean_text(entry.findtext("atom:summary", default="", namespaces=ns)),
                "arxiv_id": arxiv_id,
                "source_id": arxiv_id,
                "source": "arxiv",
                "primary_category": primary_category,
                "venue": primary_category,
                "pdf_url": pdf_url,
                "pdf_links": [pdf_url] if pdf_url else [],
                "source_url": f"https://arxiv.org/e-print/{arxiv_id}" if arxiv_id else "",
                "has_fulltext": bool(pdf_url),
                "published": published,
                "categories": categories,
            }
        )

    return {"results": results}


async def _search_arxiv_html(
    query: str,
    max_results: int,
    starting_year: Optional[int] = None,
) -> Dict[str, Any]:
    """Fallback parser for arxiv.org public HTML search results."""
    params = {
        "query": query,
        "searchtype": "all",
        "abstracts": "show",
        "order": "-announced_date_first",
        "size": "25",
    }
    try:
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        ) as client:
            response = await client.get("https://arxiv.org/search/", params=params)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        warning = f"arXiv HTML fallback failed: {type(exc).__name__}: {exc}"
        logger.warning(warning)
        return {"results": [], "warning": warning, "fallback": "arxiv_html"}

    soup = BeautifulSoup(response.text, "lxml")
    results: List[Dict[str, Any]] = []
    for item in soup.select("li.arxiv-result"):
        title = _clean_text(item.select_one("p.title").get_text(" ", strip=True)) if item.select_one("p.title") else ""
        authors = [
            _clean_text(a.get_text(" ", strip=True))
            for a in item.select("p.authors a")
        ]
        abstract = _clean_text(item.select_one("span.abstract-full").get_text(" ", strip=True)) if item.select_one("span.abstract-full") else ""
        date_text = _clean_text(item.select_one("p.is-size-7").get_text(" ", strip=True)) if item.select_one("p.is-size-7") else ""
        year = _safe_year(date_text)
        if starting_year and year and year < starting_year:
            continue
        arxiv_id = ""
        html_url = ""
        pdf_url = ""
        for anchor in item.select("p.list-title a, div.is-marginless a"):
            href = anchor.get("href", "")
            text = anchor.get_text(" ", strip=True).lower()
            if "/abs/" in href:
                html_url = href
                arxiv_id = href.rstrip("/").split("/")[-1]
            if "/pdf/" in href or "pdf" in text:
                pdf_url = _normalize_pdf_url(href)
        if arxiv_id and not pdf_url:
            pdf_url = _arxiv_pdf_url(arxiv_id)
        if title:
            results.append(
                {
                    "title": title,
                    "url": html_url or f"https://arxiv.org/abs/{arxiv_id}",
                    "authors": authors,
                    "year": year,
                    "abstract": abstract,
                    "arxiv_id": arxiv_id or _source_id("arxiv", title),
                    "source_id": arxiv_id or _source_id("arxiv", title),
                    "source": "arxiv",
                    "primary_category": "",
                    "venue": "arXiv",
                    "pdf_url": pdf_url,
                    "pdf_links": [pdf_url] if pdf_url else [],
                    "source_url": f"https://arxiv.org/e-print/{arxiv_id}" if arxiv_id else "",
                    "has_fulltext": bool(pdf_url),
                    "published": date_text,
                    "categories": [],
                }
            )
        if len(results) >= max_results:
            break
    return {"results": results, "fallback": "arxiv_html"}


def _parse_scholar_authors(meta_text: str) -> List[str]:
    if not meta_text:
        return []
    first_segment = meta_text.split(" - ")[0]
    first_segment = re.sub(r"\.\.\.$", "", first_segment).strip()
    return [_clean_text(part) for part in re.split(r",| and ", first_segment) if _clean_text(part)]


async def search_google_scholar(
    query: str,
    max_results: int = 10,
    starting_year: Optional[int] = None,
    page: int = 0,
) -> Dict[str, Any]:
    """
    Search public Google Scholar HTML pages on a best-effort basis.

    This does not bypass CAPTCHA, paywalls, login walls, or rate limits. If
    Google Scholar blocks automated access, the response includes a warning and
    empty results. For production-scale use, configure a licensed Scholar proxy
    such as SerpAPI outside this repository.
    """
    max_results = max(1, min(int(max_results or 10), MAX_SEARCH_RESULTS))
    start = max(0, int(page or 0)) * 10
    params = {
        "q": query,
        "hl": "en",
        "start": str(start),
    }
    if starting_year:
        params["as_ylo"] = str(starting_year)

    logger.info(
        "Searching Google Scholar query=%r max_results=%s starting_year=%s page=%s",
        query,
        max_results,
        starting_year,
        page,
    )

    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
    ) as client:
        response = await client.get("https://scholar.google.com/scholar", params=params)

    body = response.text
    lower_body = body.lower()
    if response.status_code >= 400 or "unusual traffic" in lower_body or "/sorry/" in str(response.url):
        warning = (
            f"Google Scholar blocked public HTML access: status={response.status_code}, "
            f"url={response.url}"
        )
        logger.warning(warning)
        return {"results": [], "warning": warning, "blocked": True}

    soup = BeautifulSoup(body, "lxml")
    results: List[Dict[str, Any]] = []

    for item in soup.select("div.gs_r.gs_or.gs_scl"):
        title_node = item.select_one("h3.gs_rt")
        if not title_node:
            continue

        link_node = title_node.find("a")
        title = _clean_text(title_node.get_text(" ", strip=True))
        title = re.sub(r"^\[[^\]]+\]\s*", "", title)
        url = link_node.get("href", "") if link_node else ""
        meta_text = _clean_text(item.select_one("div.gs_a").get_text(" ", strip=True)) if item.select_one("div.gs_a") else ""
        snippet = _clean_text(item.select_one("div.gs_rs").get_text(" ", strip=True)) if item.select_one("div.gs_rs") else ""
        year = _safe_year(meta_text)
        if starting_year and year and year < starting_year:
            continue

        citations = 0
        for anchor in item.select("div.gs_fl a"):
            text = anchor.get_text(" ", strip=True)
            match = re.search(r"Cited by\s+(\d+)", text)
            if match:
                citations = int(match.group(1))
                break

        pdf_links = []
        for pdf_anchor in item.select(".gs_or_ggsm a"):
            href = pdf_anchor.get("href")
            if href:
                pdf_links.append(urljoin("https://scholar.google.com", href))

        venue = ""
        meta_parts = [part.strip() for part in meta_text.split(" - ") if part.strip()]
        if len(meta_parts) >= 2:
            venue = meta_parts[1]

        if title:
            pdf_url = pdf_links[0] if pdf_links else None
            results.append(
                {
                    "title": title,
                    "url": url,
                    "authors": _parse_scholar_authors(meta_text),
                    "year": year,
                    "abstract": snippet,
                    "source_id": _source_id("scholar", title, url),
                    "source": "google_scholar",
                    "venue": venue,
                    "citations": citations,
                    "pdf_url": pdf_url,
                    "pdf_links": pdf_links,
                    "has_fulltext": bool(pdf_url),
                    "metadata": meta_text,
                }
            )
        if len(results) >= max_results:
            break

    return {"results": results, "blocked": False}


async def find_pdf_links(url: str, max_links: int = 5) -> Dict[str, Any]:
    """Find public PDF links on a landing page."""
    if not url:
        return {"pdf_links": []}
    normalized = _normalize_pdf_url(url)
    if normalized.lower().split("?")[0].endswith(".pdf"):
        return {"pdf_links": [normalized]}

    links: List[str] = []
    try:
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "pdf_links": [],
            "url": url,
            "error": str(exc),
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        return {"pdf_links": [], "url": url, "error": f"{type(exc).__name__}: {exc}"}

    soup = BeautifulSoup(response.text, "lxml")
    for meta in soup.select("meta[name='citation_pdf_url'], meta[name='dc.identifier']"):
        content = meta.get("content", "")
        if content and ".pdf" in content.lower():
            links.append(urljoin(str(response.url), content))

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        text = anchor.get_text(" ", strip=True).lower()
        absolute = urljoin(str(response.url), href)
        lower_href = absolute.lower()
        if lower_href.split("?")[0].endswith(".pdf") or "pdf" in text:
            links.append(absolute)

    deduped = list(dict.fromkeys(_normalize_pdf_url(link) for link in links))
    return {"pdf_links": deduped[: max(1, int(max_links or 5))]}


async def read_pdf(
    url: str,
    max_pages: int = 16,
    max_chars: int = MAX_CONTENT_CHARS,
) -> Dict[str, Any]:
    """Download a public PDF and extract text with pdfminer.six."""
    if not url:
        return {"content": "", "url": url, "error": "missing url"}

    pdf_url = _normalize_pdf_url(url)
    try:
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        ) as client:
            response = await client.get(pdf_url)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "content": "",
            "url": pdf_url,
            "error": str(exc),
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        return {"content": "", "url": pdf_url, "error": f"{type(exc).__name__}: {exc}"}

    content_type = response.headers.get("content-type", "")
    if "pdf" not in content_type.lower() and not pdf_url.lower().split("?")[0].endswith(".pdf"):
        return {
            "content": "",
            "url": pdf_url,
            "error": f"URL did not return a PDF content type: {content_type}",
        }

    def _extract() -> str:
        return extract_text(io.BytesIO(response.content), maxpages=max(1, int(max_pages or 16)))

    try:
        text = await asyncio.to_thread(_extract)
    except Exception as exc:
        return {"content": "", "url": pdf_url, "content_type": content_type, "error": str(exc)}
    text = text[: max(1, int(max_chars or MAX_CONTENT_CHARS))]
    return {"content": text, "url": pdf_url, "content_type": content_type}


async def read_url(url: str, max_chars: int = MAX_CONTENT_CHARS) -> Dict[str, Any]:
    """Fetch a public URL and return readable text content."""
    if not url:
        return {"content": "", "url": url, "error": "missing url"}

    normalized = _normalize_pdf_url(url)
    if normalized.lower().split("?")[0].endswith(".pdf"):
        return await read_pdf(normalized, max_chars=max_chars)

    try:
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        ) as client:
            response = await client.get(normalized)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "content": "",
            "url": normalized,
            "error": str(exc),
            "status_code": exc.response.status_code,
        }
    except httpx.HTTPError as exc:
        return {"content": "", "url": normalized, "error": f"{type(exc).__name__}: {exc}"}

    content_type = response.headers.get("content-type", "")
    if "pdf" in content_type.lower():
        return await read_pdf(str(response.url), max_chars=max_chars)

    soup = BeautifulSoup(response.text, "lxml")
    for node in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        node.decompose()

    title = _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    abstract_parts = [
        meta.get("content", "")
        for meta in soup.select(
            "meta[name='description'], meta[name='citation_abstract'], meta[property='og:description']"
        )
        if meta.get("content")
    ]
    container = soup.find("article") or soup.find("main") or soup.body or soup
    body_text = _clean_text(container.get_text("\n", strip=True))
    pieces = [part for part in [title, *abstract_parts, body_text] if part]
    content = "\n\n".join(pieces)
    return {
        "content": content[: max(1, int(max_chars or MAX_CONTENT_CHARS))],
        "url": str(response.url),
        "content_type": content_type,
    }


async def generate_queries_hypotheses(
    research_goal: str,
    query_format: str = "natural_language",
    seed: int = 0,
) -> Dict[str, Any]:
    """
    Generate deterministic literature search queries for hypothesis generation.

    The main LLM can still generate queries when this tool is absent, but having a
    local MCP query generator keeps multi-source literature retrieval available
    even before a model call succeeds.
    """
    goal = _clean_text(research_goal)
    quoted_terms = re.findall(r"\b[A-Z][A-Z0-9-]{2,}\b", goal)
    keywords = [
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", goal)
        if token.lower()
        not in {
            "with",
            "from",
            "that",
            "this",
            "into",
            "using",
            "covering",
            "develop",
            "novel",
            "testable",
            "hypotheses",
        }
    ]
    compact = " ".join(dict.fromkeys(keywords[:10]))
    queries = [goal]
    if quoted_terms:
        queries.append(" ".join(dict.fromkeys(quoted_terms + keywords[:8])))
    if compact:
        queries.append(compact)

    # The literature node caps to three queries, but keep this function tidy.
    return {"queries": list(dict.fromkeys(q for q in queries if q))[:3], "format": query_format, "seed": seed}


def serialize_tool_result(result: Any) -> str:
    """Utility for manual debugging and tests."""
    return json.dumps(result, ensure_ascii=False, indent=2)
