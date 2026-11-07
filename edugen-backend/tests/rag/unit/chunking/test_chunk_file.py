"""Tóm tắt: unit test bước chọn bộ cắt theo loại file (chunk_file): .json là đề thi, pages.md là SGK (tên sách lấy từ thư mục cha của cha), loại khác báo lỗi nêu tên file."""

import pytest

from app.rag.chunking import chunk_file
from tests.rag.support import EXAM_2025, count_words, sgk_pages_md, words


def test_exam_json_goes_to_the_exam_chunker():
    chunks = chunk_file(EXAM_2025)

    assert len(chunks) == 22 and {c.kind for c in chunks} == {"exam_item"}


def test_pages_md_goes_to_the_theory_chunker_with_the_book_as_source(tmp_path):
    md = sgk_pages_md(tmp_path / "sgk-toan-12-kntt-tap-1" / "marker" / "pages.md",
                      [("Chương I", "Bài 1", [("1. A", words(150))])])

    [c] = chunk_file(md, count_tokens=count_words)

    assert (c.kind, c.source, c.page) == ("theory", "sgk-toan-12-kntt-tap-1.pdf", 1)


def test_count_tokens_is_passed_to_the_theory_chunker(tmp_path):
    md = sgk_pages_md(tmp_path / "book" / "p" / "pages.md", [("Chương I", "Bài 1", [("1. A", words(150))])])
    seen = []

    chunk_file(md, count_tokens=lambda t: seen.append(t) or count_words(t))

    assert seen


def test_accepts_a_string_path():
    assert len(chunk_file(str(EXAM_2025))) == 22


@pytest.mark.parametrize("name", ["notes.txt", "sgk.pdf", "de.docx", "PAGES.md", "pages.md.bak", "other.md"])
def test_other_files_are_refused_naming_the_file(tmp_path, name):
    path = tmp_path / name
    path.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match=name.replace(".", r"\.")):
        chunk_file(path)


def test_a_missing_exam_file_raises():
    with pytest.raises(FileNotFoundError):
        chunk_file("does-not-exist.json")
