from __future__ import annotations

import tempfile
from pathlib import Path

import fitz

from paper_interpreter import interpret_paper_pdf


def create_interpret_sample_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "A Test Paper for Translation", fontsize=16)
    page.insert_text((72, 120), "Abstract\nWe evaluate method X on CIFAR-10 with accuracy 0.91.", fontsize=11)
    page.insert_text((72, 190), "1 Introduction\nThe goal is to keep Equation y = kx unchanged.", fontsize=11)
    page.insert_text((72, 260), "2 Method\nAlgorithm 1 describes the training loop.", fontsize=11)
    page.draw_rect(fitz.Rect(72, 340, 360, 440), color=(0, 0, 0), width=1)
    page.insert_text((80, 455), "Figure 1. Framework overview.", fontsize=10)
    doc.set_metadata({"title": "A Test Paper for Translation"})
    doc.save(str(path))
    doc.close()


def create_cross_page_media_pdf(path: Path) -> None:
    doc = fitz.open()
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((72, 72), "A Cross Page Test Paper", fontsize=16)
    page1.insert_text((72, 140), "1 Introduction\nThis section starts on page one.", fontsize=11)
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((72, 90), "Continuation of the introduction section.", fontsize=11)
    page2.draw_rect(fitz.Rect(72, 240, 360, 340), color=(0, 0, 0), width=1)
    page2.insert_text((80, 355), "Figure 1. Cross-page framework.", fontsize=10)
    doc.set_metadata({"title": "A Cross Page Test Paper"})
    doc.save(str(path))
    doc.close()


async def fake_translate(prompt: str) -> str:
    return "中文译稿片段：保留 Equation y = kx、CIFAR-10、Algorithm 1。"


def test_interpret_paper_outputs() -> None:
    import asyncio

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "paper.pdf"
        create_interpret_sample_pdf(pdf)
        result = asyncio.run(
            interpret_paper_pdf(
                pdf,
                "paper_output",
                translate=fake_translate,
                fetch_metadata=False,
            )
        )
        assert Path(result.markdown_path).exists()
        assert Path(result.extracted_text_path).exists()
        assert Path(result.official_metadata_path).exists()
        assert Path(result.media_dir).exists()
        assert result.media_assets
        assert result.image_links_checked >= 1
        assert result.missing_image_links == []
        assert Path(result.markdown_path).name == "paper_output_中文译稿.md"


def test_cross_page_media_is_inserted_into_section() -> None:
    import asyncio

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "cross_page.pdf"
        create_cross_page_media_pdf(pdf)
        result = asyncio.run(
            interpret_paper_pdf(
                pdf,
                "cross_page_output",
                translate=fake_translate,
                fetch_metadata=False,
            )
        )
        markdown = Path(result.markdown_path).read_text(encoding="utf-8")
        assert result.media_assets
        assert result.image_links_checked >= 1
        assert "media/figure_01_p2.png" in markdown
        assert "Markdown 图片链接校验" in markdown


if __name__ == "__main__":
    test_interpret_paper_outputs()
    test_cross_page_media_is_inserted_into_section()
    print("paper_interpreter tests passed")
