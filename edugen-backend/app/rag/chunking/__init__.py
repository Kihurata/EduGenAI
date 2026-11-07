"""Tóm tắt: bước cắt đoạn: chọn bộ cắt theo loại tài liệu (doc_type: đề thi .json hoặc SGK pages.md) và trả về danh sách Chunk.

Add a new source format here (one new module + one entry in CHUNKERS); `ingest` does not change.
"""

from pathlib import Path

from app.rag.chunking.exam import chunk_exam
from app.rag.chunking.theory import chunk_theory, read_pages_md
from app.rag.dto import Chunk


def _chunk_sgk(path, count_tokens=None, grade=12, subject="toan"):
    # Parser output layout: data/parsed/<book>/<parser>/pages.md, so the book name is two levels up.
    return chunk_theory(read_pages_md(path), source=f"{path.parent.parent.name}.pdf", subject=subject, grade=grade,
                        count_tokens=count_tokens)


def _chunk_exam(path, count_tokens=None, grade=12, subject="toan"):  # the exam JSON carries its own subject
    return chunk_exam(path)


CHUNKERS = {"sgk": _chunk_sgk, "exam": _chunk_exam}  # doc_type in data/sources.yaml (T-035) -> chunker


def chunk_source(doc_type, path, count_tokens=None, grade=12, subject="toan") -> list[Chunk]:
    """grade, subject: the manifest's; an SGK puts them in each chunk's payload and heading path ("Toán 11 > ...",
    "Hoá học 12 > ..."), T-056 and T-064."""
    if doc_type not in CHUNKERS:
        raise ValueError(f"unknown doc_type {doc_type!r}; use one of {sorted(CHUNKERS)}")
    return CHUNKERS[doc_type](Path(path), count_tokens, grade=grade, subject=subject)


def chunk_file(path, count_tokens=None) -> list[Chunk]:
    """A file without a manifest entry: its doc_type is read from the name."""
    path = Path(path)
    if path.suffix == ".json":
        return chunk_source("exam", path)
    if path.name == "pages.md":
        return chunk_source("sgk", path, count_tokens)
    # Raw PDFs go through the parser first (T-011); ingest reads its pages.md.
    raise ValueError(f"cannot ingest {path.name}: expected an exam .json or a parsed pages.md")
