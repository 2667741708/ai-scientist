from __future__ import annotations

import tempfile
from pathlib import Path

import fitz

from pdf_parser import parse_pdf_to_solve


def create_sample_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Adaptive knowledge parsing for research hypotheses", fontsize=16)
    page.insert_text(
        (72, 120),
        "Abstract\nThis paper evaluates semantic PDF parsing for hypothesis support.",
        fontsize=11,
    )
    page.insert_text(
        (72, 190),
        "1 Introduction\nThe parser should preserve paper sections.",
        fontsize=11,
    )
    page.insert_text(
        (72, 260),
        "2 Experiments\nWe benchmarked 120 papers and achieved accuracy 0.91 against baseline accuracy 0.82.",
        fontsize=11,
    )
    page.draw_rect(fitz.Rect(72, 350, 360, 460), color=(0, 0, 0), width=1)
    page.insert_text((80, 475), "Figure 1. Parsing workflow overview.", fontsize=10)
    doc.set_metadata({"title": "Adaptive knowledge parsing"})
    doc.save(str(path))
    doc.close()


def test_parse_pdf_to_solve_outputs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "paper.pdf"
        create_sample_pdf(pdf)
        result = parse_pdf_to_solve(pdf, fetch_metadata=False)

        solve_dir = Path(result.solve_dir)
        assert solve_dir.name == "solve"
        assert Path(result.extracted_text_path).exists()
        assert Path(result.metadata_json_path).exists()
        assert Path(result.metadata_text_path).exists()
        assert Path(result.chunks_json_path).exists()
        assert result.page_count == 1
        assert result.title == "Adaptive knowledge parsing"
        assert result.media_assets
        assert Path(result.media_assets[0].path).exists()
        assert result.media_assets[0].asset_id
        assert result.media_assets[0].width > 0
        assert result.media_assets[0].height > 0
        assert result.media_assets[0].file_size_bytes > 0
        assert result.media_assets[0].risk_level in {"ok", "review", "high"}
        assert isinstance(result.media_assets[0].risk_flags, list)
        assert (solve_dir / "media_region_audit.json").exists()
        assert "accuracy 0.91" in Path(result.extracted_text_path).read_text(encoding="utf-8")


if __name__ == "__main__":
    test_parse_pdf_to_solve_outputs()
    print("pdf_parser tests passed")
