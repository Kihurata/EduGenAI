"""Tóm tắt: test trên SGK thật (T-024, T-032): cắt từng cuốn normalized/pages.md bằng tokenizer bge-m3 thì không mất và không lặp dòng nào (sau đề mục đầu tiên), công thức $$ không bị cắt, ID không trùng. Trước đây việc kiểm "không mất đoạn" chỉ chạy bằng script; giờ là test, bỏ qua khi máy không có dữ liệu SGK hoặc tokenizer."""

from collections import Counter

import pytest

from app.rag.chunking.markdown import HEADING, read_pages_md
from app.rag.chunking.theory import chunk_theory
from tests.rag.support import BACKEND

BOOKS = [BACKEND / "data" / "parsed" / name / "normalized" / "pages.md"
         for name in ("sgk-toan-12-kntt-tap-1", "sgk-toan-12-kntt-tap-2")]


def _source_lines(pages):
    """Every text line from the first heading on (text before it is dropped by design)."""
    lines, started = Counter(), False
    for _, md in pages:
        for line in md.splitlines():
            started = started or bool(HEADING.match(line))
            if started and line.strip() and not HEADING.match(line):
                lines[line] += 1
    return lines


def _chunk_lines(chunks):
    """Lines inside the chunks, without each chunk's heading-path line and the headings of merged sections."""
    return Counter(line for c in chunks for line in c.text.split("\n")[1:] if line.strip() and not HEADING.match(line))


@pytest.mark.eval
@pytest.mark.parametrize("book", BOOKS, ids=lambda p: p.parents[1].name)
def test_real_sgk_chunks_lose_and_repeat_no_line(book):
    if not book.exists():
        pytest.skip(f"no {book.relative_to(BACKEND)} (data/ is gitignored)")
    pytest.importorskip("tokenizers", reason="bge-m3 tokenizer not installed: uv sync")
    pages = read_pages_md(book)

    chunks = chunk_theory(pages, source=f"{book.parents[1].name}.pdf")

    assert _chunk_lines(chunks) == _source_lines(pages)
    assert all(c.text.count("$$") % 2 == 0 for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)
    print(f"\n{book.parents[1].name}: {len(chunks)} chunks "
          f"({sum(c.kind == 'exercise' for c in chunks)} exercise), pages {pages[0][0]}–{pages[-1][0]}")
