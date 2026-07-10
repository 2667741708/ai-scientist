from __future__ import annotations

import base64
import html
import json
import os
import re
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


class WebSearchError(ValueError):
    pass


@dataclass
class WebSearchResult:
    payload: Dict[str, Any]


class _BingResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._depth = 0
        self._current: Optional[Dict[str, str]] = None
        self._capture: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        class_name = attr_map.get("class", "")
        if tag.lower() == "li" and "b_algo" in class_name.split():
            self._current = {"title": "", "url": "", "snippet": ""}
            self._depth = 1
            return
        if not self._current:
            return
        self._depth += 1
        if tag.lower() == "a" and not self._current.get("url"):
            href = attr_map.get("href", "").strip()
            if href:
                self._current["url"] = _decode_bing_url(href)
                self._capture = "title"
        elif tag.lower() == "p":
            self._capture = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if not self._current:
            return
        if tag.lower() in {"a", "p"}:
            self._capture = None
        if self._depth > 0:
            self._depth -= 1
        if tag.lower() == "li" or self._depth <= 0:
            self._finish_current()

    def handle_data(self, data: str) -> None:
        if not self._current or not self._capture:
            return
        self._current[self._capture] = f"{self._current.get(self._capture, '')} {data}"

    def _finish_current(self) -> None:
        if not self._current:
            return
        title = _collapse_whitespace(self._current.get("title", ""))
        url = self._current.get("url", "").strip()
        snippet = _collapse_whitespace(self._current.get("snippet", ""))
        if title and _is_public_result_url(url):
            self.results.append({"title": title, "url": url, "snippet": snippet})
        self._current = None
        self._capture = None
        self._depth = 0


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _is_public_result_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password


def _decode_bing_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "bing.com" not in (parsed.hostname or ""):
        return url
    query = urllib.parse.parse_qs(parsed.query)
    encoded = (query.get("u") or [""])[0]
    if not encoded:
        return url
    if encoded.startswith("a1"):
        encoded = encoded[2:]
    padding = "=" * (-len(encoded) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{encoded}{padding}").decode("utf-8", errors="replace")
    except Exception:
        return url
    return decoded if _is_public_result_url(decoded) else url


def _validated_query(query: str) -> str:
    text = _collapse_whitespace(query)
    if len(text) < 2:
        raise WebSearchError("Search query must contain at least two visible characters.")
    if len(text) > 600:
        raise WebSearchError("Search query is too long.")
    return text


def _validated_domains(domains: Optional[List[str]]) -> List[str]:
    values: List[str] = []
    for item in domains or []:
        domain = item.strip().lower().lstrip(".")
        if not domain:
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,250}[a-z0-9]", domain):
            raise WebSearchError("Search domain filters must be plain host names.")
        values.append(domain)
    return values[:8]


def _provider_name() -> str:
    return (os.getenv("COSCIENTIST_WEB_SEARCH_PROVIDER") or "bing_html").strip().lower()


def web_search_status() -> Dict[str, Any]:
    provider = _provider_name()
    if provider not in {"bing_html"}:
        return {
            "available": False,
            "mode": "unsupported_provider",
            "reason": f"Unsupported public web search provider: {provider}.",
            "checked_at": time.time(),
            "metadata": {"supported_providers": ["bing_html"]},
        }
    return {
        "available": True,
        "mode": "best_effort_public_search",
        "reason": "Best-effort Bing HTML public search workflow is configured.",
        "checked_at": time.time(),
        "metadata": {"provider": provider},
    }


def search_public_web(
    query: str,
    *,
    artifact_root: Path,
    limit: int = 10,
    domains: Optional[List[str]] = None,
    recency_days: Optional[int] = None,
    timeout_seconds: int = 15,
) -> WebSearchResult:
    provider = _provider_name()
    if provider != "bing_html":
        raise WebSearchError(f"Unsupported public web search provider: {provider}.")
    clean_query = _validated_query(query)
    clean_domains = _validated_domains(domains)
    bounded_limit = max(1, min(int(limit or 10), 20))
    search_query = clean_query
    if clean_domains:
        site_clause = " OR ".join(f"site:{domain}" for domain in clean_domains)
        search_query = f"{clean_query} ({site_clause})"

    params = {"q": search_query, "count": str(bounded_limit), "setlang": "en-US"}
    search_url = f"https://www.bing.com/search?{urllib.parse.urlencode(params)}"
    response = requests.get(
        "https://www.bing.com/search",
        params=params,
        timeout=timeout_seconds,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Mozilla/5.0 Open-Coscientist-WebSearchBot/0.1",
        },
    )
    response.raise_for_status()

    parser = _BingResultParser()
    parser.feed(response.text)
    results: List[Dict[str, Any]] = []
    seen_urls = set()
    for item in parser.results:
        url = item["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        parsed = urllib.parse.urlparse(url)
        results.append(
            {
                "rank": len(results) + 1,
                "title": item["title"][:300],
                "url": url,
                "display_url": parsed.hostname or url,
                "snippet": item.get("snippet", "")[:1000],
                "source": provider,
            }
        )
        if len(results) >= bounded_limit:
            break

    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_id = f"web_search_{uuid.uuid4().hex[:12]}"
    artifact_dir = artifact_root / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    results_path = artifact_dir / "results.json"
    metadata_path = artifact_dir / "metadata.json"
    fetched_at = time.time()
    metadata = {
        "artifact_id": artifact_id,
        "provider": provider,
        "query": clean_query,
        "effective_query": search_query,
        "domains": clean_domains,
        "recency_days": recency_days,
        "limit": bounded_limit,
        "search_url": search_url,
        "status_code": response.status_code,
        "fetched_at": fetched_at,
        "result_count": len(results),
        "results_path": str(results_path),
        "metadata_path": str(metadata_path),
        "source_reliability": "best_effort_public_search_snippet",
        "boundary": "snippets_only_not_fulltext_evidence",
    }
    payload = {**metadata, "results": results}
    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return WebSearchResult(payload=payload)
