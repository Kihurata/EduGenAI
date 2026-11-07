"""Tóm tắt: test đánh giá T-007: bảng 2×2 recall@5 trên golden set Toán, cắt theo đề mục vs cắt cố định × tìm kiếm lai vs chỉ dense, chạy trên SGK đã đọc (pages.md) với bge-m3 thật. Chỉ tính các dòng có bài nằm trong sách được nạp. Kết quả trái với D-003 / D-004 thì báo Minh Quan. Chạy: SGK_PAGES_MD=a/pages.md:b/pages.md uv run pytest --suite F-03 -m eval -s -k chunking."""

import os
from pathlib import Path

import pytest

from app.rag.chunking.theory import read_pages_md
from app.rag.evaluate import compare_chunkers, format_table
from tests.rag.support import BACKEND, RETRIEVAL, load

DEFAULT = BACKEND / "data" / "parsed" / "sgk-toan-12-kntt-tap-1" / "manual" / "pages.md"
BOOKS = [Path(p) for p in os.environ.get("SGK_PAGES_MD", str(DEFAULT)).split(os.pathsep)]


@pytest.mark.eval
@pytest.mark.skipif(not all(b.exists() for b in BOOKS), reason="no parsed SGK pages.md (data/ is gitignored)")
def test_T007_heading_vs_fixed_chunking_x_hybrid_vs_dense():
    pytest.importorskip("FlagEmbedding", reason="bge-m3 not installed: uv sync --extra embed")
    from app.rag.embedding.bge_m3 import BgeM3Embedder

    pages = [page for book in BOOKS for page in read_pages_md(book)]
    lessons = " ".join(md for _, md in pages)
    golden = [r for r in load(RETRIEVAL / "golden-retrieval-toan.json")
              if any(e in lessons for e in r["expected_lessons"])]
    if not golden:
        pytest.skip("no golden row's expected lesson is in these books")

    result = compare_chunkers(pages, BOOKS[0].parent.parent.name + ".pdf", golden, BgeM3Embedder())

    print(f"\nT-007 recall@5 on {len(golden)} golden rows ({', '.join(b.parent.parent.name for b in BOOKS)}):")
    print(format_table(result))
    assert all(0 <= r <= 1 for r in result.values())
