from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path


WEBAPP_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = WEBAPP_ROOT / "backend"
PROJECT_ROOT = WEBAPP_ROOT.parents[0]
if str(WEBAPP_ROOT) not in sys.path:
    sys.path.insert(0, str(WEBAPP_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.knowledge_base import KnowledgeBaseStore  # noqa: E402
from backend.pdf_parser import parse_pdf_to_solve  # noqa: E402
from backend.pdf_region_audit import summarize_media_region_quality  # noqa: E402


def default_kb_root() -> Path:
    return Path(os.getenv("COSCIENTIST_KNOWLEDGE_BASE_DIR", str(WEBAPP_ROOT / ".knowledge_base")))


def write_audit_json(media_assets: list[dict], solve_dir: Path) -> Path:
    target = solve_dir / "media_region_audit.json"
    target.write_text(json.dumps(media_assets, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def audit_pdf_path(pdf_path: Path) -> tuple[list[dict], Path]:
    result = parse_pdf_to_solve(pdf_path, fetch_metadata=False)
    media_assets = [asdict(asset) for asset in result.media_assets]
    audit_path = write_audit_json(media_assets, Path(result.solve_dir))
    return media_assets, audit_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit PDF Figure/Table/Algorithm crop confidence without multimodal calls.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pdf-path", help="Backend-local PDF path to parse and audit.")
    group.add_argument("--parse-run-id", help="Existing parse run id in the SQLite knowledge base.")
    parser.add_argument("--write-db", action="store_true", help="Write audit metadata back to the parse run.")
    parser.add_argument("--knowledge-root", help="Override knowledge base root directory.")
    args = parser.parse_args()

    kb_root = Path(args.knowledge_root) if args.knowledge_root else default_kb_root()
    store = KnowledgeBaseStore(kb_root)

    if args.pdf_path:
        pdf_path = Path(args.pdf_path)
        media_assets, audit_path = audit_pdf_path(pdf_path)
        parse_run_id = None
    else:
        parse_run = store.get_parse_run(args.parse_run_id)
        if not parse_run:
            raise SystemExit(f"parse run not found: {args.parse_run_id}")
        if not parse_run.get("pdf_path"):
            raise SystemExit(f"parse run has no pdf_path: {args.parse_run_id}")
        media_assets, audit_path = audit_pdf_path(Path(str(parse_run["pdf_path"])))
        parse_run_id = str(args.parse_run_id)
        if args.write_db:
            store.update_media_region_audit(parse_run_id, media_assets)

    summary = summarize_media_region_quality(media_assets)
    output = {
        "parse_run_id": parse_run_id,
        "audit_path": str(audit_path),
        "summary": summary,
        "review_required": summary["review"] + summary["high"] > 0,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
