"""Tóm tắt: TC-030: chủ đề Toán lớp 10 và 11 truy xuất đúng bài SGK: mỗi dòng golden-retrieval-toan-10-11.json chạy qua retrieve chỉ với ô (không query, không lesson), hybrid k=5, recall@5 ≥ 80%; in kèm dense và số dòng bỏ qua vì bài chưa nạp. Bài mong đợi lấy từ mục lục SGK KNTT trong chỉ mục, theo cụm tìm kiếm của chủ đề, không lấy từ kết quả truy xuất. Chạy trên Qdrant cục bộ (qdrant_data/, không bao giờ là cluster), cần GEMINI_API_KEY."""

import json
import os
from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

from app.rag.embedding import make_embedder
from app.rag.evaluate import recall_at_k
from app.rag.storage.qdrant import COLLECTION
from tests.rag.support import RETRIEVAL

LOCAL_INDEX = Path(__file__).parents[4] / "qdrant_data"  # never the cluster, whatever QDRANT_URL says
GOLDEN = RETRIEVAL / "golden-retrieval-toan-10-11.json"
THEORY = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="theory"))])


@pytest.mark.eval
@pytest.mark.skipif(not LOCAL_INDEX.exists() or not os.environ.get("GEMINI_API_KEY"),
                    reason="needs the local qdrant_data/ with SGK 10-11 and GEMINI_API_KEY")
def test_TC_030_grade_10_11_cell_only_recall_at_5():
    client, golden = QdrantClient(path=str(LOCAL_INDEX)), json.loads(GOLDEN.read_text(encoding="utf-8"))
    lessons, offset = set(), None
    while True:
        points, offset = client.scroll(COLLECTION, scroll_filter=THEORY, with_payload=["lesson"], limit=1000, offset=offset)
        lessons |= {p.payload["lesson"] for p in points}
        if offset is None:
            break
    rows = [r for r in golden if any(e in lesson for e in r["expected_lessons"] for lesson in lessons)]
    assert rows, "no golden row's expected lesson is ingested"
    embedder = make_embedder()

    hybrid = recall_at_k(client, embedder, rows, k=5, mode="hybrid")
    dense = recall_at_k(client, embedder, rows, k=5, mode="dense")
    client.close()

    print(f"TC-030 cell-only recall@5 on {len(rows)} rows ({len(golden) - len(rows)} skipped, lesson not ingested): "
          f"hybrid={hybrid:.0%} dense={dense:.0%}")
    assert hybrid >= 0.8
