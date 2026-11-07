"""Tóm tắt: unit test bộ đọc PDF thành Markdown (T-002): trang chữ ra đề mục #/##/###, trang scan gửi ảnh cho LLM đọc ảnh (giả) và giữ số trang; thêm biên: trang scan không có LLM thì báo lỗi nêu số trang, nhiều trang đánh số đúng, chỉ trang scan mới gọi LLM."""

import pymupdf
import pytest

from app.rag.parse import parse_pdf


def _text_page(doc):
    p = doc.new_page()
    p.insert_text((50, 60), "Chuong I. Ung dung dao ham", fontsize=22, fontname="hebo")
    p.insert_text((50, 100), "Bai 1. Tinh don dieu", fontsize=17, fontname="hebo")
    p.insert_text((50, 140), "1. Dinh nghia", fontsize=14, fontname="hebo")
    for i in range(8):
        p.insert_text((50, 170 + i * 16), f"Cho ham so y = f(x) xac dinh tren khoang K, dong {i}.", fontsize=11)


def _scanned_page(doc):
    # An image-only page: no extractable text, like a scanned SGK page.
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pix.set_rect(pix.irect, (200, 200, 200))
    p = doc.new_page()
    p.insert_image(pymupdf.Rect(50, 50, 250, 250), pixmap=pix)


def _pdf(tmp_path, *builders):
    doc = pymupdf.open()
    for build in builders:
        build(doc)
    path = tmp_path / "lesson.pdf"
    doc.save(path)
    return path


def test_text_page_becomes_markdown_with_heading_levels(tmp_path):
    pages = parse_pdf(_pdf(tmp_path, _text_page))

    assert [page for page, _ in pages] == [1]
    lines = pages[0][1].splitlines()
    assert "# Chuong I. Ung dung dao ham" in lines
    assert "## Bai 1. Tinh don dieu" in lines
    assert "### 1. Dinh nghia" in lines


def test_scanned_page_is_transcribed_by_vision_llm_with_page_number(tmp_path):
    seen = []

    def fake_vision(png):
        seen.append(png)
        return "## Bai 2. Cuc tri\n\n$$f'(x)=0$$"

    pages = parse_pdf(_pdf(tmp_path, _text_page, _scanned_page), transcribe=fake_vision)

    assert pages[1] == (2, "## Bai 2. Cuc tri\n\n$$f'(x)=0$$")
    assert len(seen) == 1 and seen[0].startswith(b"\x89PNG")


# --- edge cases ------------------------------------------------------------------------------------------------

def test_a_scanned_page_without_a_vision_llm_names_the_page(tmp_path):
    with pytest.raises(ValueError, match="page 2 "):
        parse_pdf(_pdf(tmp_path, _text_page, _scanned_page))


def test_pages_are_numbered_from_one_in_order(tmp_path):
    pages = parse_pdf(_pdf(tmp_path, _text_page, _scanned_page, _text_page, _scanned_page), transcribe=lambda png: "x")

    assert [n for n, _ in pages] == [1, 2, 3, 4]


def test_only_scanned_pages_go_to_the_vision_llm(tmp_path):
    seen = []

    parse_pdf(_pdf(tmp_path, _text_page, _text_page, _scanned_page), transcribe=lambda png: seen.append(png) or "x")

    assert len(seen) == 1


def test_text_pages_have_no_bold_markers_left_in_headings(tmp_path):
    [(_, md)] = parse_pdf(_pdf(tmp_path, _text_page))

    assert not [line for line in md.splitlines() if line.startswith("#") and "**" in line]


def test_markdown_is_stripped(tmp_path):
    [(_, md)] = parse_pdf(_pdf(tmp_path, _text_page))

    assert md == md.strip()


def test_a_missing_file_raises(tmp_path):
    with pytest.raises(RuntimeError):  # pymupdf.FileNotFoundError subclasses RuntimeError
        parse_pdf(tmp_path / "nope.pdf")
