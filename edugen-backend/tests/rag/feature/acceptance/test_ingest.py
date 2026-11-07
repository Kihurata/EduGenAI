"""Tóm tắt: test nghiệm thu TC-001 (F-01): nạp một bài SGK Toán 12 và đề 2025 mã 0101 bằng bge-m3 thật, rồi tìm được đoạn theo bài học và câu đề theo phần; chạy lại không trùng. SGK lấy từ pages.md do bộ đọc PDF tạo ra (mặc định bản chép tay data/parsed/.../manual/pages.md; đổi bằng biến SGK_PAGES_MD)."""

import os
from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

from app.rag.embedding.bge_m3 import BgeM3Embedder
from app.rag.ingest import ingest
from app.rag.storage.qdrant import COLLECTION
from tests.rag.support import BACKEND, EXAM_2025

SGK_PAGES_MD = Path(os.environ.get("SGK_PAGES_MD", BACKEND / "data" / "parsed"
                                    / "sgk-toan-12-kntt-tap-1" / "manual" / "pages.md"))


def _match(**fields):
    return models.Filter(must=[models.FieldCondition(key=k, match=models.MatchValue(value=v)) for k, v in fields.items()])


@pytest.mark.acceptance
@pytest.mark.skipif(not SGK_PAGES_MD.exists(), reason="no parsed SGK pages.md (data/ is gitignored)")
def test_TC_001_ingest_toan_lesson_searchable():
    client = QdrantClient(":memory:")
    embedder = BgeM3Embedder()

    ingest([SGK_PAGES_MD, EXAM_2025], client, embedder)

    theory = client.scroll(COLLECTION, scroll_filter=_match(kind="theory"), limit=1000)[0]
    lesson = theory[0].payload["lesson"]
    hits = client.query_points(
        COLLECTION, query=embedder.embed([lesson])[0].dense, using="dense",
        query_filter=_match(kind="theory", lesson=lesson), limit=10,
    ).points
    assert hits and all(h.payload["lesson"] == lesson for h in hits)
    assert all(h.payload["page"] and h.payload["heading_path"] for h in hits)

    part2 = client.scroll(COLLECTION, scroll_filter=_match(kind="exam_item", part="II"), limit=100)[0]
    assert len(part2) == 4

    count = client.count(COLLECTION).count
    ingest([SGK_PAGES_MD, EXAM_2025], client, embedder)
    assert client.count(COLLECTION).count == count
