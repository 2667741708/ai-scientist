from __future__ import annotations

import hashlib
import json
import mimetypes
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


class FileEvidenceError(ValueError):
    pass


@dataclass
class FileEvidenceResult:
    payload: Dict[str, Any]

    def public_payload(self) -> Dict[str, Any]:
        payload = dict(self.payload)
        payload.pop("text", None)
        return payload


def snapshot_source_file(
    source_path: str,
    *,
    source_root: Path,
    artifact_root: Path,
    start_line: int = 1,
    line_count: int = 200,
    max_bytes: int = 1_000_000,
) -> FileEvidenceResult:
    guardrail = validate_source_file(source_path, source_root=source_root, max_bytes=max_bytes)
    resolved = Path(guardrail["source_path"])
    raw = resolved.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    start = max(1, start_line)
    count = max(1, min(line_count, 2000))
    selected = lines[start - 1 : start - 1 + count]
    numbered = "\n".join(f"{index}: {line}" for index, line in enumerate(selected, start=start))

    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_id = f"file_{uuid.uuid4().hex[:12]}"
    artifact_dir = artifact_root / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    snapshot_path = artifact_dir / "snapshot.txt"
    metadata_path = artifact_dir / "metadata.json"
    snapshot_path.write_text(numbered, encoding="utf-8")
    stat = resolved.stat()
    metadata = {
        "artifact_id": artifact_id,
        "source_path": str(resolved),
        "source_root": guardrail["source_root"],
        "relative_path": guardrail["relative_path"],
        "mime_type": mimetypes.guess_type(str(resolved))[0] or "text/plain",
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": stat.st_size,
        "modified_at": stat.st_mtime,
        "captured_at": time.time(),
        "start_line": start,
        "line_count": len(selected),
        "total_lines": len(lines),
        "snapshot_path": str(snapshot_path),
        "metadata_path": str(metadata_path),
        "artifact_dir": str(artifact_dir),
        "source_reliability": "local_source_snapshot",
        "guardrail": guardrail,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return FileEvidenceResult(payload={**metadata, "text": numbered, "text_preview": numbered[:2000]})


def validate_source_file(source_path: str, *, source_root: Path, max_bytes: int = 1_000_000) -> Dict[str, Any]:
    root = source_root.resolve()
    candidate = Path(source_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise FileEvidenceError("Source file must stay inside the configured source evidence root.") from exc
    if not resolved.exists() or not resolved.is_file():
        raise FileEvidenceError("Source file does not exist inside the configured source evidence root.")
    size = resolved.stat().st_size
    if size > max_bytes:
        raise FileEvidenceError("Source file is larger than the configured snapshot byte limit.")
    sample = resolved.read_bytes()[:4096]
    if b"\x00" in sample:
        raise FileEvidenceError("Binary files are not supported by source snapshot evidence.")
    return {
        "allowed": True,
        "source_root": str(root),
        "source_path": str(resolved),
        "relative_path": str(relative).replace("\\", "/"),
        "max_bytes": max_bytes,
    }
