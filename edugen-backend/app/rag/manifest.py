"""Tóm tắt: danh mục nguồn data/sources.yaml (T-035, bước 1 của D-009): đọc và kiểm tra từng nguồn (id, doc_type, file, subject, grade, official, confidence; đề thi thêm exam_kind, year), rồi nạp: cắt theo doc_type, gắn source_id, official, grade của danh mục, nhúng và ghi Qdrant. Đường dẫn file tính từ thư mục của danh mục. Chạy: python -m app.rag.ingest --sources data/sources.yaml"""

import dataclasses
from pathlib import Path

import yaml

from app.rag.chunking import CHUNKERS, chunk_source
from app.rag.embedding import Embedder
from app.rag.storage.qdrant import index_chunks

MANIFEST = Path(__file__).parents[2] / "data" / "sources.yaml"
REQUIRED = ("id", "doc_type", "file", "subject", "grade", "official", "confidence")
EXAM_REQUIRED = ("exam_kind", "year")
EXAM_KINDS = ("tot_nghiep", "dinh_ky_7991")  # D-017: exam format only; official vs reference lives in `official`


def load_sources(path=MANIFEST) -> list[dict]:
    """Every entry is checked before anything is ingested, so a typo can't leave a half-built index."""
    sources = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["sources"]
    seen = set()
    for s in sources:
        name = s.get("id", "?")
        missing = [k for k in REQUIRED + (EXAM_REQUIRED if s.get("doc_type") == "exam" else ()) if s.get(k) is None]
        if missing:
            raise ValueError(f"{name}: missing {', '.join(missing)} in {path}")
        if s["doc_type"] not in CHUNKERS:
            raise ValueError(f"{name}: unknown doc_type {s['doc_type']!r}; use one of {sorted(CHUNKERS)}")
        if s["doc_type"] == "exam" and s["exam_kind"] not in EXAM_KINDS:
            raise ValueError(f"{name}: unknown exam_kind {s['exam_kind']!r}; use one of {', '.join(EXAM_KINDS)}")
        if name in seen:
            raise ValueError(f"duplicate source id {name} in {path}")
        seen.add(name)
    return sources


def ingest_sources(path, client, embedder: Embedder, count_tokens=None):
    path = Path(path)
    for s in load_sources(path):
        chunks = [dataclasses.replace(c, source_id=s["id"], official=s["official"], grade=s["grade"],
                                      exam_kind=s.get("exam_kind"))
                  for c in chunk_source(s["doc_type"], path.parent / s["file"], count_tokens, grade=s["grade"])]
        index_chunks(client, chunks, embedder)
        print(f"{s['id']}: {len(chunks)} chunks")
