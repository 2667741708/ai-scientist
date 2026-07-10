"""
Source artifact tools for paper and code provenance.

These tools download and unpack public arXiv source bundles and GitHub source
archives into a controlled MCP cache. They return manifests and safe local paths
so later workflow steps can inspect LaTeX, BibTeX, code, configs, and README
files without relying only on PDF text extraction.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 OpenCoscientistSourceMCP/0.1"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
SOURCE_TIMEOUT = httpx.Timeout(120.0, connect=20.0)
DEFAULT_MAX_DOWNLOAD_BYTES = 200_000_000
DEFAULT_MAX_EXTRACTED_BYTES = 500_000_000
MAX_MANIFEST_FILES = 400
TEXT_EXTENSIONS = {
    ".tex",
    ".bib",
    ".bbl",
    ".sty",
    ".cls",
    ".md",
    ".rst",
    ".txt",
    ".py",
    ".ipynb",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".sh",
    ".ps1",
    ".r",
    ".m",
    ".jl",
    ".cpp",
    ".cc",
    ".c",
    ".h",
    ".hpp",
}
LATEX_EXTENSIONS = {".tex", ".bib", ".bbl", ".sty", ".cls"}
CODE_EXTENSIONS = {
    ".py",
    ".ipynb",
    ".r",
    ".m",
    ".jl",
    ".cpp",
    ".cc",
    ".c",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
}


def _source_cache_root() -> Path:
    root = os.getenv("COSCIENTIST_SOURCE_CACHE_DIR") or os.getenv(
        "COSCIENTIST_LIT_REVIEW_DIR",
        "./cache/literature_sources",
    )
    return Path(root).expanduser().resolve()


def _safe_slug(value: str, fallback: str = "artifact") -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return slug[:160] or fallback


def _is_within(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _ensure_cache_path(path: str | Path) -> Path:
    root = _source_cache_root()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not _is_within(root, resolved):
        raise ValueError(f"path is outside the source cache root: {resolved}")
    return resolved


def _extract_arxiv_id(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("missing arXiv id or URL")

    parsed = urlparse(value)
    if parsed.netloc.endswith("arxiv.org"):
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"abs", "pdf", "e-print", "src"}:
            arxiv_id = "/".join(parts[1:])
        else:
            arxiv_id = parts[-1] if parts else value
    else:
        arxiv_id = value

    arxiv_id = arxiv_id.split("?")[0].removesuffix(".pdf").strip("/")
    match = re.search(r"([a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5}(?:v\d+)?)", arxiv_id, re.IGNORECASE)
    if match:
        return match.group(1)
    raise ValueError(f"could not parse arXiv id from: {value}")


async def _download_to_file(
    url: str,
    destination: Path,
    max_bytes: int,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request_headers = {**DEFAULT_HEADERS, **(headers or {})}
    total = 0
    content_type = ""

    async with httpx.AsyncClient(
        timeout=SOURCE_TIMEOUT,
        headers=request_headers,
        follow_redirects=True,
    ) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            with open(destination, "wb") as handle:
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"download exceeded max_bytes={max_bytes}")
                    handle.write(chunk)

    return {"url": url, "path": str(destination), "bytes": total, "content_type": content_type}


def _safe_extract_tar(
    archive_path: Path,
    extract_dir: Path,
    max_extracted_bytes: int,
) -> Dict[str, Any]:
    extracted = 0
    skipped: List[str] = []
    files = 0
    with tarfile.open(archive_path, mode="r:*") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                skipped.append(member.name)
                continue
            target = extract_dir / member.name
            if not _is_within(extract_dir, target):
                skipped.append(member.name)
                continue
            if member.isfile():
                extracted += int(member.size or 0)
                if extracted > max_extracted_bytes:
                    raise ValueError(f"extracted files exceeded max_extracted_bytes={max_extracted_bytes}")
                files += 1
            archive.extract(member, extract_dir)
    return {"format": "tar", "files_extracted": files, "bytes_extracted": extracted, "skipped": skipped[:50]}


def _safe_extract_zip(
    archive_path: Path,
    extract_dir: Path,
    max_extracted_bytes: int,
) -> Dict[str, Any]:
    extracted = 0
    skipped: List[str] = []
    files = 0
    with zipfile.ZipFile(archive_path) as archive:
        for item in archive.infolist():
            target = extract_dir / item.filename
            if not _is_within(extract_dir, target):
                skipped.append(item.filename)
                continue
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            extracted += int(item.file_size or 0)
            if extracted > max_extracted_bytes:
                raise ValueError(f"extracted files exceeded max_extracted_bytes={max_extracted_bytes}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, open(target, "wb") as dest:
                shutil.copyfileobj(source, dest)
            files += 1
    return {"format": "zip", "files_extracted": files, "bytes_extracted": extracted, "skipped": skipped[:50]}


def _safe_extract_gzip_single_file(
    archive_path: Path,
    extract_dir: Path,
    max_extracted_bytes: int,
) -> Dict[str, Any]:
    target = extract_dir / "source.tex"
    extracted = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(archive_path, "rb") as source, open(target, "wb") as dest:
        while True:
            chunk = source.read(1024 * 256)
            if not chunk:
                break
            extracted += len(chunk)
            if extracted > max_extracted_bytes:
                raise ValueError(f"extracted file exceeded max_extracted_bytes={max_extracted_bytes}")
            dest.write(chunk)
    return {"format": "gzip-single-file", "files_extracted": 1, "bytes_extracted": extracted, "skipped": []}


def _extract_archive(
    archive_path: Path,
    extract_dir: Path,
    max_extracted_bytes: int,
) -> Dict[str, Any]:
    extract_dir.mkdir(parents=True, exist_ok=True)

    if zipfile.is_zipfile(archive_path):
        return _safe_extract_zip(archive_path, extract_dir, max_extracted_bytes)

    try:
        return _safe_extract_tar(archive_path, extract_dir, max_extracted_bytes)
    except tarfile.TarError:
        pass

    try:
        return _safe_extract_gzip_single_file(archive_path, extract_dir, max_extracted_bytes)
    except OSError as exc:
        raise ValueError(f"unsupported source archive format: {archive_path}") from exc


def _file_priority(path: Path) -> Tuple[int, int, str]:
    suffix = path.suffix.lower()
    if suffix in LATEX_EXTENSIONS:
        rank = 0
    elif path.name.lower() in {"readme.md", "readme.txt", "requirements.txt", "environment.yml", "pyproject.toml"}:
        rank = 1
    elif suffix in CODE_EXTENSIONS:
        rank = 2
    elif suffix in TEXT_EXTENSIONS:
        rank = 3
    else:
        rank = 9
    return (rank, len(path.parts), str(path).lower())


def _build_manifest(root: Path, max_files: int = MAX_MANIFEST_FILES) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    total_files = 0
    total_bytes = 0
    extension_counts: Dict[str, int] = {}

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        total_files += 1
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        total_bytes += size
        suffix = path.suffix.lower() or "<none>"
        extension_counts[suffix] = extension_counts.get(suffix, 0) + 1
        files.append(
            {
                "path": rel,
                "size": size,
                "extension": suffix,
                "is_text_candidate": suffix in TEXT_EXTENSIONS or path.name.lower().startswith("readme"),
            }
        )

    files.sort(key=lambda item: _file_priority(Path(item["path"])))
    important_files = files[:max_files]
    return {
        "root": str(root),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "extension_counts": dict(sorted(extension_counts.items())),
        "important_files": important_files,
        "manifest_truncated": len(files) > max_files,
    }


def _read_text_file(path: Path, max_chars: int) -> Dict[str, Any]:
    with open(path, "rb") as handle:
        data = handle.read(max_chars * 4)
    text = data.decode("utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars]
    return {
        "path": str(path),
        "content": text,
        "chars": len(text),
        "bytes_read": len(data),
        "truncated": len(data) >= max_chars * 4 or len(text) >= max_chars,
    }


async def download_arxiv_source(
    arxiv_id_or_url: str,
    extract: bool = True,
    overwrite: bool = False,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
) -> Dict[str, Any]:
    """Download and optionally extract an arXiv LaTeX/source bundle."""
    try:
        arxiv_id = _extract_arxiv_id(arxiv_id_or_url)
    except ValueError as exc:
        return {"error": str(exc), "input": arxiv_id_or_url}

    cache_dir = _source_cache_root() / "arxiv" / _safe_slug(arxiv_id.replace("/", "_"))
    archive_path = cache_dir / "source_package"
    extract_dir = cache_dir / "extracted"
    if overwrite and cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if archive_path.exists() and extract_dir.exists() and not overwrite:
        return {
            "source": "arxiv",
            "arxiv_id": arxiv_id,
            "cached": True,
            "archive_path": str(archive_path),
            "extract_dir": str(extract_dir),
            "manifest": _build_manifest(extract_dir),
        }

    quoted_id = quote(arxiv_id, safe="/.")
    urls = [
        f"https://arxiv.org/e-print/{quoted_id}",
        f"https://arxiv.org/src/{quoted_id}",
    ]
    download_info: Optional[Dict[str, Any]] = None
    errors: List[str] = []
    for url in urls:
        try:
            download_info = await _download_to_file(url, archive_path, int(max_bytes or DEFAULT_MAX_DOWNLOAD_BYTES))
            break
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    if download_info is None:
        return {"source": "arxiv", "arxiv_id": arxiv_id, "error": "download failed", "errors": errors}

    result: Dict[str, Any] = {
        "source": "arxiv",
        "arxiv_id": arxiv_id,
        "cached": False,
        "source_url": download_info["url"],
        "archive_path": str(archive_path),
        "download_bytes": download_info["bytes"],
        "content_type": download_info.get("content_type", ""),
    }

    if extract:
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        try:
            extraction = _extract_archive(
                archive_path,
                extract_dir,
                max_extracted_bytes=DEFAULT_MAX_EXTRACTED_BYTES,
            )
            result.update(
                {
                    "extract_dir": str(extract_dir),
                    "extraction": extraction,
                    "manifest": _build_manifest(extract_dir),
                }
            )
        except Exception as exc:
            result.update({"extract_error": f"{type(exc).__name__}: {exc}"})

    return result


def _parse_github_repository(value: str) -> Tuple[str, str, Optional[str]]:
    parsed = urlparse((value or "").strip())
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise ValueError(f"not a github.com repository URL: {value}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"could not parse owner/repo from GitHub URL: {value}")
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    ref = None
    if len(parts) >= 4 and parts[2] == "tree":
        ref = "/".join(parts[3:])
    return owner, repo, ref


async def _github_repo_metadata(owner: str, repo: str) -> Dict[str, Any]:
    headers = {**DEFAULT_HEADERS, "Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/repos/{owner}/{repo}"
    async with httpx.AsyncClient(timeout=SOURCE_TIMEOUT, headers=headers, follow_redirects=True) as client:
        response = await client.get(url)
    if response.status_code == 401 and "Authorization" in headers:
        logger.warning("GitHub token was rejected for %s/%s; retrying metadata anonymously", owner, repo)
        retry_headers = {k: v for k, v in headers.items() if k != "Authorization"}
        async with httpx.AsyncClient(
            timeout=SOURCE_TIMEOUT,
            headers=retry_headers,
            follow_redirects=True,
        ) as anonymous_client:
            response = await anonymous_client.get(url)
    response.raise_for_status()
    data = response.json()
    return {
        "api_url": url,
        "html_url": data.get("html_url"),
        "default_branch": data.get("default_branch") or "main",
        "description": data.get("description"),
        "license": (data.get("license") or {}).get("spdx_id"),
        "stars": data.get("stargazers_count"),
    }


async def download_github_repository(
    repository_url: str,
    ref: Optional[str] = None,
    extract: bool = True,
    overwrite: bool = False,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
) -> Dict[str, Any]:
    """Download and optionally extract a public GitHub repository archive."""
    try:
        owner, repo, url_ref = _parse_github_repository(repository_url)
    except ValueError as exc:
        return {"error": str(exc), "input": repository_url}

    metadata: Dict[str, Any] = {}
    if not ref:
        ref = url_ref
    if not ref:
        try:
            metadata = await _github_repo_metadata(owner, repo)
            ref = metadata.get("default_branch") or "main"
        except Exception as exc:
            metadata = {"metadata_error": f"{type(exc).__name__}: {exc}"}
            ref = None

    candidate_refs = [ref] if ref else ["master", "main"]
    candidate_refs = [candidate for candidate in dict.fromkeys(candidate_refs) if candidate]
    cache_ref = candidate_refs[0]
    cache_id = _safe_slug(f"{owner}_{repo}_{cache_ref.replace('/', '_')}")
    cache_dir = _source_cache_root() / "github" / cache_id
    archive_path = cache_dir / "repository.zip"
    extract_dir = cache_dir / "extracted"
    if overwrite and cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if archive_path.exists() and extract_dir.exists() and not overwrite:
        return {
            "source": "github",
            "cached": True,
            "owner": owner,
            "repo": repo,
            "ref": cache_ref,
            **metadata,
            "archive_path": str(archive_path),
            "extract_dir": str(extract_dir),
            "manifest": _build_manifest(extract_dir),
        }

    archive_urls = []
    for candidate_ref in candidate_refs:
        quoted_ref = quote(candidate_ref, safe="/._-")
        archive_urls.extend(
            [
                (candidate_ref, f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{quoted_ref}"),
                (candidate_ref, f"https://codeload.github.com/{owner}/{repo}/zip/refs/tags/{quoted_ref}"),
                (candidate_ref, f"https://codeload.github.com/{owner}/{repo}/zip/{quoted_ref}"),
            ]
        )
    download_info: Optional[Dict[str, Any]] = None
    downloaded_ref: Optional[str] = None
    errors: List[str] = []
    for candidate_ref, url in archive_urls:
        try:
            download_info = await _download_to_file(url, archive_path, int(max_bytes or DEFAULT_MAX_DOWNLOAD_BYTES))
            downloaded_ref = candidate_ref
            break
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    if download_info is None:
        return {
            "source": "github",
            "owner": owner,
            "repo": repo,
            "ref": cache_ref,
            "candidate_refs": candidate_refs,
            **metadata,
            "error": "download failed",
            "errors": errors,
        }

    result: Dict[str, Any] = {
        "source": "github",
        "cached": False,
        "owner": owner,
        "repo": repo,
        "ref": downloaded_ref or cache_ref,
        "candidate_refs": candidate_refs,
        **metadata,
        "archive_url": download_info["url"],
        "archive_path": str(archive_path),
        "download_bytes": download_info["bytes"],
        "content_type": download_info.get("content_type", ""),
    }

    if extract:
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        try:
            extraction = _safe_extract_zip(
                archive_path,
                extract_dir,
                max_extracted_bytes=DEFAULT_MAX_EXTRACTED_BYTES,
            )
            result.update(
                {
                    "extract_dir": str(extract_dir),
                    "extraction": extraction,
                    "manifest": _build_manifest(extract_dir),
                }
            )
        except Exception as exc:
            result.update({"extract_error": f"{type(exc).__name__}: {exc}"})

    return result


async def find_github_repository_links(url: str, max_links: int = 10) -> Dict[str, Any]:
    """Find public GitHub repository links on an HTML page."""
    if not url:
        return {"repositories": [], "error": "missing url"}
    try:
        async with httpx.AsyncClient(
            timeout=SOURCE_TIMEOUT,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {"repositories": [], "url": url, "error": str(exc), "status_code": exc.response.status_code}
    except httpx.HTTPError as exc:
        return {"repositories": [], "url": url, "error": f"{type(exc).__name__}: {exc}"}

    soup = BeautifulSoup(response.text, "lxml")
    links: List[str] = []
    for anchor in soup.find_all("a", href=True):
        links.append(urljoin(str(response.url), anchor["href"]))
    links.extend(re.findall(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", response.text))

    repositories = []
    seen = set()
    blocked_names = {"features", "topics", "collections", "events", "marketplace", "pricing", "login"}
    for link in links:
        parsed = urlparse(link)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            continue
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2 or parts[0].lower() in blocked_names:
            continue
        owner, repo = parts[0], parts[1].removesuffix(".git")
        repo_url = f"https://github.com/{owner}/{repo}"
        if repo_url in seen:
            continue
        seen.add(repo_url)
        repositories.append({"owner": owner, "repo": repo, "url": repo_url})
        if len(repositories) >= max(1, int(max_links or 10)):
            break
    return {"repositories": repositories, "url": str(response.url)}


async def read_downloaded_source_file(
    download_dir: str,
    relative_path: str,
    max_chars: int = 120_000,
) -> Dict[str, Any]:
    """Read a text-like file from the controlled source cache."""
    try:
        base = _ensure_cache_path(download_dir)
        target = (base / relative_path).resolve()
        if not _is_within(base, target):
            return {"content": "", "error": "relative_path escapes download_dir", "path": str(target)}
        if not target.is_file():
            return {"content": "", "error": "file not found", "path": str(target)}
        if target.suffix.lower() not in TEXT_EXTENSIONS and not target.name.lower().startswith("readme"):
            return {
                "content": "",
                "error": f"refusing non-text source file extension: {target.suffix}",
                "path": str(target),
            }
        return _read_text_file(target, max(1, int(max_chars or 120_000)))
    except Exception as exc:
        return {"content": "", "error": f"{type(exc).__name__}: {exc}"}


def serialize_tool_result(result: Any) -> str:
    """Utility for manual debugging and tests."""
    return json.dumps(result, ensure_ascii=False, indent=2)
