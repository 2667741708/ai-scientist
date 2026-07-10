from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List

import requests


TEXTUAL_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/json",
    "application/ld+json",
}
BENCHMARK_PROXY_NETWORKS = (ipaddress.ip_network("198.18.0.0/15"),)


class WebEvidenceError(ValueError):
    pass


class _EvidenceHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.skip_depth = 0
        self.in_title = False
        self.title_parts: List[str] = []
        self.text_parts: List[str] = []
        self.links: List[Dict[str, str]] = []
        self._current_anchor: Dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "svg", "canvas"}:
            self.skip_depth += 1
            return
        if normalized == "title":
            self.in_title = True
        if normalized == "a":
            attr_map = {key.lower(): value or "" for key, value in attrs}
            href = attr_map.get("href", "").strip()
            if href:
                absolute = urllib.parse.urljoin(self.base_url, href)
                parsed = urllib.parse.urlparse(absolute)
                if parsed.scheme in {"http", "https"}:
                    self._current_anchor = {"url": absolute, "text": ""}
        if normalized in {"p", "div", "section", "article", "li", "br", "tr", "h1", "h2", "h3"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "svg", "canvas"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if normalized == "title":
            self.in_title = False
        if normalized == "a" and self._current_anchor:
            self._current_anchor["text"] = _collapse_whitespace(self._current_anchor.get("text", ""))
            self.links.append(self._current_anchor)
            self._current_anchor = None

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        self.text_parts.append(data)
        if self._current_anchor is not None:
            self._current_anchor["text"] += data


@dataclass
class WebEvidenceResult:
    payload: Dict[str, Any]

    def public_payload(self) -> Dict[str, Any]:
        return {key: value for key, value in self.payload.items() if key != "extracted_text"}


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _validate_public_http_url(url: str) -> Dict[str, Any]:
    normalized = url.strip()
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise WebEvidenceError("Only absolute http/https URLs can be extracted as web evidence.")
    if parsed.username or parsed.password:
        raise WebEvidenceError("Credential-bearing URLs are not allowed for evidence extraction.")

    try:
        hostname_ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        hostname_ip = None

    resolved: List[str] = []
    proxy_reserved: List[str] = []
    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise WebEvidenceError("URL host could not be resolved.") from exc

    for info in addr_infos:
        address = info[4][0]
        if address in resolved:
            continue
        resolved.append(address)
        ip = ipaddress.ip_address(address)
        if hostname_ip is None and any(ip in network for network in BENCHMARK_PROXY_NETWORKS):
            proxy_reserved.append(address)
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise WebEvidenceError("Private, loopback, link-local, multicast, and reserved IP targets are not allowed.")
    return {
        "normalized_url": normalized,
        "host": parsed.hostname,
        "resolved_addresses": resolved,
        "proxy_reserved_addresses": proxy_reserved,
    }


def validate_public_http_url(url: str) -> Dict[str, Any]:
    return _validate_public_http_url(url)


def _content_type_family(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def extract_web_evidence(
    url: str,
    *,
    artifact_root: Path,
    timeout_seconds: int = 20,
    max_bytes: int = 1_000_000,
    max_text_chars: int = 80_000,
) -> WebEvidenceResult:
    guardrail = _validate_public_http_url(url)
    headers = {
        "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.9,*/*;q=0.3",
        "User-Agent": "Open-Coscientist-ResearchEvidenceBot/0.1",
    }
    response = requests.get(guardrail["normalized_url"], timeout=timeout_seconds, headers=headers)
    response.raise_for_status()

    content = response.content[:max_bytes]
    truncated = len(response.content) > max_bytes
    content_hash = hashlib.sha256(content).hexdigest()
    content_type = response.headers.get("content-type", "")
    family = _content_type_family(content_type)
    if content.startswith(b"%PDF") or "pdf" in family:
        raise WebEvidenceError("PDF URLs must be parsed through pdf.parse_to_knowledge_base.")
    if family and family not in TEXTUAL_CONTENT_TYPES and not family.startswith("text/"):
        raise WebEvidenceError("URL did not return textual or HTML evidence.")

    text = content.decode(response.encoding or "utf-8", errors="replace")
    links: List[Dict[str, str]] = []
    title = ""
    if "html" in family or "<html" in text[:1000].lower():
        parser = _EvidenceHTMLParser(response.url)
        parser.feed(text)
        title = _collapse_whitespace(" ".join(parser.title_parts))
        text = _collapse_whitespace("\n".join(parser.text_parts))
        seen_urls = set()
        for link in parser.links:
            link_url = link["url"]
            if link_url in seen_urls:
                continue
            seen_urls.add(link_url)
            links.append(link)
    else:
        title = Path(urllib.parse.urlparse(response.url).path).name or response.url
        text = _collapse_whitespace(text)

    extracted_text = text[:max_text_chars]
    text_truncated = len(text) > max_text_chars
    pdf_links = [
        link for link in links
        if link["url"].lower().split("?", 1)[0].endswith(".pdf") or "pdf" in link.get("text", "").lower()
    ][:30]
    supplementary_links = [
        link for link in links
        if re.search(r"supplement|appendix|artifact|code|dataset|leaderboard|benchmark", link.get("text", ""), re.I)
        or re.search(r"supplement|appendix|artifact|code|dataset|leaderboard|benchmark", link["url"], re.I)
    ][:30]

    artifact_id = f"web_{uuid.uuid4().hex[:12]}"
    artifact_dir = artifact_root / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    snapshot_path = artifact_dir / "snapshot.txt"
    metadata_path = artifact_dir / "metadata.json"
    snapshot_path.write_text(extracted_text, encoding="utf-8")

    fetched_at = time.time()
    metadata = {
        "artifact_id": artifact_id,
        "requested_url": guardrail["normalized_url"],
        "final_url": response.url,
        "host": guardrail["host"],
        "resolved_addresses": guardrail["resolved_addresses"],
        "status_code": response.status_code,
        "content_type": content_type,
        "content_hash": content_hash,
        "fetched_at": fetched_at,
        "title": title,
        "text_char_count": len(text),
        "captured_text_char_count": len(extracted_text),
        "response_truncated": truncated,
        "text_truncated": text_truncated,
        "snapshot_path": str(snapshot_path),
        "metadata_path": str(metadata_path),
        "artifact_dir": str(artifact_dir),
        "link_count": len(links),
        "links": links[:80],
        "pdf_links": pdf_links,
        "supplementary_links": supplementary_links,
        "source_reliability": "best_effort_public_html",
        "guardrail": guardrail,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return WebEvidenceResult(
        payload={
            **metadata,
            "extracted_text": extracted_text,
            "text_preview": extracted_text[:2000],
        }
    )
