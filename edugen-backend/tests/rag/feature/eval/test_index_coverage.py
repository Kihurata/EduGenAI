"""Tóm tắt: test TC-017 kiểm tra chỉ mục thật ở qdrant_data/ có đủ cả hai tập SGK Toán 12: mỗi bài trong mục lục có đoạn lý thuyết, không đoạn nào hỏng công thức (\\frac bị mất dấu \\) hay thiếu trang/tiêu đề. In thêm tỉ lệ lệnh hỏi trong các ma trận đề có nguồn SGK trong chỉ mục (chủ đề lớp 10–11 chưa có sách)."""

import json
import re
from collections import Counter

import pytest
import yaml

from app.rag.storage.qdrant import COLLECTION, open_client
from tests.rag.support import FIXTURES

OUTLINE = FIXTURES / "rag-retrieval" / "sgk-toan-12-outline.json"
MATRICES = FIXTURES / "toan-matrix"

# "\f" eaten as a form feed leaves "rac{"; a lost backslash leaves a bare "frac{"; other control characters are parser debris.
BROKEN = re.compile(r"(?<![A-Za-z\\])rac\{|(?<![A-Za-z\\])frac\{|[\x00-\x08\x0b\x0c\x0e-\x1f]")


@pytest.mark.eval
def test_TC_017_index_covers_every_sgk_lesson():
    client = open_client()
    if not client.collection_exists(COLLECTION):
        client.close()
        pytest.skip("no qdrant_data/ index yet")
    points = client.scroll(COLLECTION, limit=10_000, with_payload=True, with_vectors=False)[0]
    client.close()
    outline = json.loads(OUTLINE.read_text(encoding="utf-8"))["books"]
    sgk = [p.payload for p in points if p.payload["source"] in outline]

    theory = Counter((p["source"], p["lesson"]) for p in sgk if p["kind"] == "theory")
    missing = [(book, lesson) for book, chapters in outline.items()
               for ch in chapters for lesson in ch["lessons"] if not theory[(book, lesson)]]
    assert missing == []

    assert [(p["source"], p["page"], m.group()) for p in sgk if (m := BROKEN.search(p["text"]))] == []
    assert [p["id"] for p in sgk if not (p["page"] and p["heading_path"] and p["chapter"])] == []

    covered = {ch["topic"] for chapters in outline.values() for ch in chapters}
    for f in sorted(MATRICES.glob("*.yaml")):
        cells = yaml.safe_load(f.read_text(encoding="utf-8"))["matrix"]["cells"]
        have = sum(c["count"] for c in cells if c.get("topic") in covered)
        print(f"TC-017 {f.stem}: {have}/{sum(c['count'] for c in cells)} items have an SGK source in the index")
