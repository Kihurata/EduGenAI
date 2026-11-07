"""Tóm tắt: feature test hợp đồng RAG → Backend nhìn từ phía Backend (T-028, D-008): dùng bộ sinh câu giả + file 22 câu mẫu để ghép một đề 12/4/6, mọi câu đúng định dạng và tra được nguồn bằng bộ tra đoạn giả; file mẫu sinh lại từ đề chính thức không lệch."""

import pytest

from app.rag.checking.validate import validate
from app.rag.chunking.exam import chunk_exam
from app.rag.contract import to_contract
from app.rag.fake import FakeChunkLookup, FakeGenerator
from app.rag.vocab import LEVELS, TOPICS
from tests.rag.support import CONTRACT, EXAM_2025, load

QUESTIONS = CONTRACT / "toan-22-questions.json"
CHUNKS = CONTRACT / "toan-22-chunks.json"
SHAPE = {"multiple_choice": 12, "true_false": 4, "short_answer": 6}


def _cells():
    return [{"subject": "toan", "topic": "dai_so_giai_tich/ung_dung_dao_ham", "level": "Hiểu", "type": t, "count": n}
            for t, n in SHAPE.items()]


def test_the_backend_builds_a_22_question_exam_from_the_fake():
    generate = FakeGenerator.from_file(QUESTIONS)

    exam = [q for c in _cells() for q in generate(c)[0]]

    assert [q["type"] for q in exam] == ["multiple_choice"] * 12 + ["true_false"] * 4 + ["short_answer"] * 6


def test_every_fake_question_passes_the_rag_validator():
    generate = FakeGenerator.from_file(QUESTIONS)

    for c in _cells():
        for q in generate(c)[0]:
            assert validate(q, None) == [], q["stem"][:40]


def test_every_fake_question_takes_the_cells_level_and_a_known_topic():
    generate = FakeGenerator.from_file(QUESTIONS)

    for c in _cells():
        assert all(q["level"] == "Hiểu" and q["level"] in LEVELS and q["topic"] in TOPICS for q in generate(c)[0])


def test_every_citation_of_the_exam_resolves_with_the_fake_lookup():
    generate, lookup = FakeGenerator.from_file(QUESTIONS), FakeChunkLookup.from_file(CHUNKS)
    ids = [i for c in _cells() for q in generate(c)[0] for i in q["source_chunk_ids"]]

    found, missing = lookup(ids)

    assert missing == [] and len(found) == 22


def test_a_23rd_question_is_never_invented():
    generate = FakeGenerator.from_file(QUESTIONS)

    valid, rejected = generate(_cells()[0] | {"count": 13})

    assert len(valid) == 12 and rejected == []


def test_the_fixture_shipped_to_the_backend_is_rebuilt_from_the_official_exam():
    levels = load(CONTRACT / "levels-toan-tn-2025-0101.json")
    rebuilt = to_contract(load(EXAM_2025), levels)
    cited = {i for q in rebuilt for i in q["source_chunk_ids"]}

    assert load(QUESTIONS) == rebuilt
    assert load(CHUNKS) == [c.to_dict() for c in chunk_exam(EXAM_2025) if c.id in cited]


@pytest.mark.parametrize("field", ["type", "stem", "level", "topic", "source_chunk_ids", "explanation"])
def test_every_fixture_question_has_the_contract_field(field):
    assert all(field in q for q in load(QUESTIONS))
