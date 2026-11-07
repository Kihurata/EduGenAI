"""Tóm tắt: test nghiệm thu TC-002 (F-03): sinh 3 câu trắc nghiệm mức Biết cho một chủ đề Toán bằng Claude thật trên chỉ mục qdrant_data/; mọi câu qua validator và trích dẫn đoạn đã truy xuất. Không có ANTHROPIC_API_KEY thì dùng Claude Code (`claude -p`)."""

import pytest
from qdrant_client import models

from app.rag.embedding import make_embedder
from app.rag.generation.llm import make_llm
from app.rag.pipeline import generate_for_cell
from app.rag.storage.qdrant import COLLECTION, open_client

# SGK Toán 12 KNTT tập 1 covers ứng dụng đạo hàm (Chương I).
CELL = {"subject": "toan", "topic": "dai_so_giai_tich/ung_dung_dao_ham", "level": "Biết", "type": "multiple_choice",
        "count": 3}


@pytest.mark.acceptance
def test_TC_002_generate_cited_questions_for_cell():
    llm = make_llm()
    client = open_client()
    theory = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="theory"))])
    if not client.collection_exists(COLLECTION) or client.count(COLLECTION, count_filter=theory).count == 0:
        client.close()
        pytest.skip("no SGK theory chunks in qdrant_data/ yet (needs T-022 parse + T-003)")

    valid, rejected = generate_for_cell(client, make_embedder(), CELL, llm)
    client.close()

    assert rejected == []
    assert len(valid) == 3
    assert all(q["level"] == "Biết" and q["source_chunk_ids"] for q in valid)
