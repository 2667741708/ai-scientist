from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

try:
    from backend.web_evidence import WebEvidenceError, validate_public_http_url
except ModuleNotFoundError:
    from web_evidence import WebEvidenceError, validate_public_http_url


class BrowserCaptureError(ValueError):
    pass


@dataclass
class BrowserCaptureResult:
    payload: Dict[str, Any]

    def public_payload(self) -> Dict[str, Any]:
        payload = dict(self.payload)
        payload.pop("console_messages", None)
        return payload


def capture_browser_screenshot(
    url: str,
    *,
    artifact_root: Path,
    viewport_width: int = 1365,
    viewport_height: int = 768,
    full_page: bool = True,
    timeout_ms: int = 30_000,
) -> BrowserCaptureResult:
    guardrail = validate_public_http_url(url)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserCaptureError("Playwright is not installed in the backend environment.") from exc

    artifact_id = f"browser_{uuid.uuid4().hex[:12]}"
    artifact_dir = artifact_root / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    screenshot_path = artifact_dir / "screenshot.png"
    metadata_path = artifact_dir / "metadata.json"
    console_messages: List[Dict[str, Any]] = []
    started = time.time()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": viewport_width, "height": viewport_height},
                ignore_https_errors=True,
            )
            page = context.new_page()
            page.on(
                "console",
                lambda msg: console_messages.append(
                    {"type": msg.type, "text": msg.text[:1000]}
                ),
            )
            response = page.goto(guardrail["normalized_url"], wait_until="networkidle", timeout=timeout_ms)
            title = page.title()
            final_url = page.url
            page.screenshot(path=str(screenshot_path), full_page=full_page)
            status_code = response.status if response else None
            context.close()
            browser.close()
    except WebEvidenceError:
        raise
    except Exception as exc:
        raise BrowserCaptureError(str(exc)) from exc

    duration = round(time.time() - started, 4)
    metadata = {
        "artifact_id": artifact_id,
        "requested_url": guardrail["normalized_url"],
        "final_url": final_url,
        "title": title,
        "status_code": status_code,
        "host": guardrail["host"],
        "resolved_addresses": guardrail["resolved_addresses"],
        "viewport": {"width": viewport_width, "height": viewport_height},
        "full_page": full_page,
        "duration_seconds": duration,
        "screenshot_path": str(screenshot_path),
        "metadata_path": str(metadata_path),
        "artifact_dir": str(artifact_dir),
        "console_count": len(console_messages),
        "console_messages": console_messages[:50],
        "source_reliability": "browser_snapshot",
        "guardrail": guardrail,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return BrowserCaptureResult(payload=metadata)
