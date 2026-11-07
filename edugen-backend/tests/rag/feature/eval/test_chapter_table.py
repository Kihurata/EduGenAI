"""Tóm tắt: test khoá bảng chương (D-021, T-068): mọi tên chương trong CHAPTER_BY_TOPIC có đoạn lý thuyết Toán đúng lớp trong chỉ mục Qdrant cục bộ (qdrant_data/, không bao giờ là cluster); bỏ qua nếu chưa có chỉ mục cục bộ."""

from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

from app.domain.topics import _TOPIC_GRADES
from app.rag.storage.qdrant import COLLECTION
from app.rag.vocab import CHAPTER_BY_TOPIC

LOCAL = Path(__file__).parents[4] / "qdrant_data"


@pytest.mark.skipif(not LOCAL.exists(), reason="no local index; ingest SGK with QDRANT_URL empty")
def test_every_chapter_in_the_table_exists_in_the_local_index_for_its_grade():
    client = QdrantClient(path=str(LOCAL))
    for topic, chapter in CHAPTER_BY_TOPIC.items():
        grade = _TOPIC_GRADES[topic.split("/")[1]]
        flt = models.Filter(must=[models.FieldCondition(key=k, match=models.MatchValue(value=v))
                                  for k, v in {"subject": "toan", "kind": "theory", "grade": grade, "chapter": chapter}.items()])
        assert client.count(COLLECTION, count_filter=flt).count > 0, (topic, grade, chapter)
