"""Tóm tắt: TC-033 (D-021, T-068): mỗi ô Toán của ma trận derived-tn-2025-0101 có chủ đề trong bảng chương thì top 5 lý thuyết lấy đúng chương (chương ít hơn 5 đoạn thì lấy hết đoạn của chương rồi bù cùng lớp), đủ 5 đoạn, không ô nào rỗng. Chạy trên Qdrant cục bộ (qdrant_data/, không bao giờ là cluster), embedding thật bằng Gemini nên cần GEMINI_API_KEY."""

import os
from pathlib import Path

import pytest
import yaml
from qdrant_client import QdrantClient, models

from app.domain.topics import _TOPIC_GRADES
from app.rag.embedding import make_embedder
from app.rag.storage.qdrant import COLLECTION
from app.rag.storage.retrieve import retrieve
from app.rag.vocab import CHAPTER_BY_TOPIC, LEVEL_FROM_CODE
from tests.rag.support import FIXTURES

LOCAL_INDEX = Path(__file__).parents[4] / "qdrant_data"  # never the cluster, whatever QDRANT_URL says
K = 5
MATRIX = FIXTURES / "toan-matrix" / "derived-tn-2025-0101.yaml"


def _cells():
    seen = {}
    for c in yaml.safe_load(MATRIX.read_text(encoding="utf-8"))["matrix"]["cells"]:
        topic = f"{c['strand']}/{c['topic']}"
        if topic in CHAPTER_BY_TOPIC:
            seen[(topic, c["level"])] = {"subject": "toan", "grade": _TOPIC_GRADES[c["topic"]], "topic": topic,
                                         "type": c["type"], "level": LEVEL_FROM_CODE[c["level"]], "count": c["count"]}
    return list(seen.values())


@pytest.mark.eval
@pytest.mark.skipif(not LOCAL_INDEX.exists() or not os.environ.get("GEMINI_API_KEY"),
                    reason="needs the local qdrant_data/ with SGK 10-12 and GEMINI_API_KEY")
def test_TC_033_toan_cell_theory_from_topic_chapter():
    client, embedder, bad = QdrantClient(path=str(LOCAL_INDEX)), make_embedder(), []
    for cell in _cells():
        chapter = CHAPTER_BY_TOPIC[cell["topic"]]
        in_chapter = models.Filter(must=[models.FieldCondition(key=k, match=models.MatchValue(value=v)) for k, v in
                                         {"subject": "toan", "kind": "theory", "grade": cell["grade"], "chapter": chapter}.items()])
        theory = [c for c in retrieve(client, embedder, cell, k=K).theory if c.kind == "theory"]
        right = sum(c.chapter == chapter for c in theory)
        want = min(K, client.count(COLLECTION, count_filter=in_chapter).count)
        if len(theory) < K or right < want:
            bad.append((cell["topic"], cell["level"], f"{right}/{want} in chapter, {len(theory)} chunks"))
    assert not bad, bad
