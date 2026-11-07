"""Tóm tắt: test đánh giá TC-004: sinh câu cho bộ ô ma trận cố định bằng Claude thật và đòi ≥ 90% câu qua mọi validator; in lý do lỗi và số token để tính chi phí. TC-016: ≥ 90% câu trả lời ngắn có đáp số được SymPy xác nhận. Không có ANTHROPIC_API_KEY thì dùng Claude Code (`claude -p`)."""

import json

import pytest
from qdrant_client import models

from app.rag.embedding import make_embedder
from app.rag.generation.llm import make_llm
from app.rag.pipeline import generate_for_cell
from app.rag.storage.qdrant import COLLECTION, open_client
from tests.rag.support import RETRIEVAL

CELLS = RETRIEVAL / "matrix-cells-toan.json"


@pytest.mark.eval
def test_TC_004_generated_questions_pass_validators():
    llm = make_llm()
    client = open_client()
    theory = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="theory"))])
    if not client.collection_exists(COLLECTION) or client.count(COLLECTION, count_filter=theory).count == 0:
        client.close()
        pytest.skip("no SGK theory chunks in qdrant_data/ yet (needs T-022 parse + T-003)")
    embedder = make_embedder()

    passed = failed = 0
    for cell in json.loads(CELLS.read_text(encoding="utf-8")):
        valid, rejected = generate_for_cell(client, embedder, cell, llm)
        passed, failed = passed + len(valid), failed + len(rejected)
        for r in rejected:
            print(f"{cell['topic']} {cell['type']}: {r['errors']}")
    client.close()

    rate = passed / max(passed + failed, 1)
    print(f"TC-004 pass rate: {rate:.0%} ({passed}/{passed + failed}); usage: {getattr(llm, 'usage', None)}")
    assert rate >= 0.9


@pytest.mark.eval
def test_TC_016_generated_numeric_answers_match_sympy():
    llm = make_llm()
    client = open_client()
    theory = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="theory"))])
    if not client.collection_exists(COLLECTION) or client.count(COLLECTION, count_filter=theory).count == 0:
        client.close()
        pytest.skip("no SGK theory chunks in qdrant_data/ yet (needs T-022 parse + T-003)")
    embedder = make_embedder()

    questions, errors = [], []
    for cell in json.loads(CELLS.read_text(encoding="utf-8")):
        if cell["type"] != "short_answer":
            continue
        valid, rejected = generate_for_cell(client, embedder, cell, llm)
        questions += valid + [r["question"] for r in rejected]
        errors += [e for r in rejected for e in r["errors"]]
    client.close()

    verified = sum(1 for q in questions if q.get("sympy", {}).get("verified"))
    rate = verified / max(len(questions), 1)
    print(f"TC-016 SymPy-verified: {rate:.0%} ({verified}/{len(questions)}); "
          f"mismatches: {sum('SymPy gives' in e for e in errors)}, "
          f"unverifiable: {sum(e.startswith('sympy.expr unverifiable') for e in errors)}, "
          f"no expr: {errors.count('no sympy.expr')}; usage: {getattr(llm, 'usage', None)}")
    assert rate >= 0.9
