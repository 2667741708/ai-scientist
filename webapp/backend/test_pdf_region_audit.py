from __future__ import annotations

import tempfile
from pathlib import Path

import fitz

from pdf_region_audit import audit_pdf_region


def _audit(
    *,
    caption_text: str = "Figure 1. Parsing workflow.",
    clip: fitz.Rect | None = None,
    blocks: list[tuple] | None = None,
    width: int = 320,
    height: int = 320,
    file_bytes: int = 20_000,
) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        image_path = Path(tmp) / "asset.png"
        image_path.write_bytes(b"0" * file_bytes)
        page_rect = fitz.Rect(0, 0, 600, 800)
        caption_rect = fitz.Rect(80, 520, 480, 550)
        clip_rect = clip or fitz.Rect(70, 260, 500, 560)
        return audit_pdf_region(
            caption_text=caption_text,
            clip_rect=clip_rect,
            page_rect=page_rect,
            blocks=blocks
            or [
                (80, 320, 420, 450, "chart body", 0, 0),
                (80, 520, 480, 550, caption_text, 0, 0),
            ],
            image_path=image_path,
            pixel_width=width,
            pixel_height=height,
            caption_block_rect=caption_rect,
            drawing_rects=[fitz.Rect(80, 300, 420, 450)],
        )


def _codes(result: dict) -> set[str]:
    return {flag["code"] for flag in result["risk_flags"]}


def test_multiple_caption_numbers_is_high_risk() -> None:
    result = _audit(caption_text="Figure 1. Main result. Figure 2. Neighbor result.")
    assert "multiple_caption_numbers" in _codes(result)
    assert result["risk_level"] == "high"


def test_adjacent_caption_title_is_high_risk() -> None:
    result = _audit(
        blocks=[
            (80, 320, 420, 450, "chart body", 0, 0),
            (80, 520, 480, 550, "Figure 1. Parsing workflow.", 0, 0),
            (80, 575, 480, 600, "Table 1. Nearby metrics.", 0, 0),
        ]
    )
    assert "adjacent_caption_title" in _codes(result)
    assert result["risk_level"] == "high"


def test_abnormal_crop_height_requires_review() -> None:
    result = _audit(clip=fitz.Rect(70, 500, 500, 540))
    assert "abnormal_crop_height" in _codes(result)
    assert result["risk_level"] == "review"


def test_tiny_png_requires_review() -> None:
    result = _audit(width=120, height=120, file_bytes=1024)
    assert "tiny_png_file" in _codes(result)
    assert result["risk_level"] == "review"


def test_incomplete_pdf_block_coverage_requires_review() -> None:
    result = _audit(clip=fitz.Rect(0, 260, 500, 560), blocks=[(80, 520, 480, 550, "Figure 1. Caption only.", 0, 0)])
    assert "incomplete_pdf_block_coverage" in _codes(result)
    assert result["risk_level"] == "review"


def test_cross_column_region_requires_review() -> None:
    result = _audit(clip=fitz.Rect(80, 260, 540, 560))
    assert "cross_column_or_formula_region" in _codes(result)
    assert result["risk_level"] == "review"


if __name__ == "__main__":
    test_multiple_caption_numbers_is_high_risk()
    test_adjacent_caption_title_is_high_risk()
    test_abnormal_crop_height_requires_review()
    test_tiny_png_requires_review()
    test_incomplete_pdf_block_coverage_requires_review()
    test_cross_column_region_requires_review()
    print("pdf_region_audit tests passed")
