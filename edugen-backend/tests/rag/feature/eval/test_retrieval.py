"""Tóm tắt: test đánh giá TC-003 và TC-014: recall@5 của truy xuất trên golden set Toán phải ≥ 80% (chế độ lai), in kèm kết quả chỉ dense để so sánh. TC-014 bỏ câu hỏi, chỉ dùng ô ma trận như lúc sinh đề, và chỉ tính các dòng có bài đã nạp. Chạy trên chỉ mục thật (Qdrant Cloud nếu có QDRANT_URL, không thì qdrant_data/) sau khi đã nạp SGK."""

import json

import pytest
from qdrant_client import models

from app.rag.embedding import make_embedder
from app.rag.evaluate import recall_at_k
from app.rag.storage.qdrant import COLLECTION, open_client
from tests.rag.support import RETRIEVAL

GOLDEN = RETRIEVAL / "golden-retrieval-toan.json"


THEORY = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="theory"))])


def _open_index():
    client = open_client()
    if not client.collection_exists(COLLECTION) or client.count(COLLECTION, count_filter=THEORY).count == 0:
        client.close()
        pytest.skip("no SGK theory chunks in qdrant_data/ yet (needs SGK PDF + T-003)")
    return client


@pytest.mark.eval
def test_TC_003_retrieval_recall_at_5():
    client = _open_index()
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    embedder = make_embedder()

    hybrid = recall_at_k(client, embedder, golden, k=5, mode="hybrid")
    dense = recall_at_k(client, embedder, golden, k=5, mode="dense")
    client.close()

    print(f"TC-003 recall@5: hybrid={hybrid:.0%} dense={dense:.0%}")
    assert hybrid >= 0.8


def _indexed_lessons(client):
    lessons, offset = set(), None
    while True:
        points, offset = client.scroll(COLLECTION, scroll_filter=THEORY, with_payload=["lesson"], limit=1000, offset=offset)
        lessons |= {p.payload["lesson"] for p in points}
        if offset is None:
            return lessons


@pytest.mark.eval
def test_TC_014_cell_only_retrieval_recall_at_5():
    client = _open_index()
    lessons = _indexed_lessons(client)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    # Cell only, as exam generation calls it; rows whose lessons aren't ingested can't hit, so they don't count.
    rows = [{k: v for k, v in r.items() if k != "query"} for r in golden
            if any(e in lesson for e in r["expected_lessons"] for lesson in lessons)]
    if not rows:
        client.close()
        pytest.skip("no golden row's expected lesson is ingested yet")
    embedder = make_embedder()

    hybrid = recall_at_k(client, embedder, rows, k=5, mode="hybrid")
    dense = recall_at_k(client, embedder, rows, k=5, mode="dense")
    client.close()

    print(f"TC-014 cell-only recall@5 on {len(rows)} rows ({len(golden) - len(rows)} skipped, lesson not ingested): "
          f"hybrid={hybrid:.0%} dense={dense:.0%}")
    assert hybrid >= 0.8
