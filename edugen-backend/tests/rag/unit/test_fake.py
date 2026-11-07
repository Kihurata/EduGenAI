"""Tóm tắt: unit test bộ sinh câu giả và bộ tra đoạn giả cho Backend (T-028, T-029): trả câu đúng dạng, ưu tiên đúng chủ đề, gắn mức độ/chủ đề của ô, không bịa thêm câu khi thiếu, không làm hỏng ngân hàng câu; bộ tra đoạn giả trả bản sao và có đủ đoạn mà file câu hỏi mẫu trích dẫn."""

import json

import pytest

from app.rag.fake import FakeChunkLookup, FakeGenerator
from tests.rag.support import CONTRACT, load


def _q(qtype, topic, stem):
    return {"type": qtype, "topic": topic, "level": "Biết", "stem": stem, "source_chunk_ids": ["th1"]}


QUESTIONS = [
    _q("multiple_choice", "tich_phan", "mc other topic"),
    _q("multiple_choice", "dao_ham", "mc same topic 1"),
    _q("true_false", "dao_ham", "tf"),
    _q("multiple_choice", "dao_ham", "mc same topic 2"),
]


def _cell(qtype="multiple_choice", count=2, topic="dao_ham"):
    return {"subject": "toan", "topic": topic, "level": "Hiểu", "type": qtype, "count": count}


# --- FakeGenerator ---------------------------------------------------------------------------------------------

def test_returns_count_questions_of_cell_type_preferring_cell_topic():
    valid, rejected = FakeGenerator(QUESTIONS)(_cell(count=2))

    assert [q["stem"] for q in valid] == ["mc same topic 1", "mc same topic 2"]
    assert rejected == []


def test_falls_back_to_other_topics_then_returns_fewer_without_padding():
    valid, _ = FakeGenerator(QUESTIONS)(_cell(count=5))

    assert [q["stem"] for q in valid] == ["mc same topic 1", "mc same topic 2", "mc other topic"]


def test_copies_take_level_and_topic_from_cell_and_leave_the_bank_untouched():
    generate = FakeGenerator(QUESTIONS)

    valid, _ = generate(_cell(count=3))

    assert all((q["level"], q["topic"]) == ("Hiểu", "dao_ham") for q in valid)
    assert QUESTIONS[0]["level"] == "Biết" and QUESTIONS[0]["topic"] == "tich_phan"
    assert generate.calls == [_cell(count=3)]


def test_from_file_loads_json_list(tmp_path):
    path = tmp_path / "bank.json"
    path.write_text(json.dumps(QUESTIONS, ensure_ascii=False), encoding="utf-8")

    valid, _ = FakeGenerator.from_file(path)(_cell("true_false", count=1))

    assert [q["stem"] for q in valid] == ["tf"]


def test_count_zero_gives_nothing():
    assert FakeGenerator(QUESTIONS)(_cell(count=0)) == ([], [])


def test_a_type_with_no_questions_gives_nothing():
    assert FakeGenerator(QUESTIONS)(_cell("short_answer", count=3)) == ([], [])


def test_an_empty_bank_gives_nothing():
    assert FakeGenerator([])(_cell()) == ([], [])


def test_editing_a_returned_question_does_not_change_later_calls():
    generate = FakeGenerator(QUESTIONS)

    first, _ = generate(_cell(count=1))
    first[0]["stem"] = "edited"
    first[0]["source_chunk_ids"].append("x")
    second, _ = generate(_cell(count=1))

    assert second[0]["stem"] == "mc same topic 1" and second[0]["source_chunk_ids"] == ["th1"]


def test_the_bank_list_passed_in_is_not_mutated():
    bank = list(QUESTIONS)
    generate = FakeGenerator(bank)
    bank.clear()

    assert generate(_cell(count=1))[0]


def test_every_call_is_recorded_in_order():
    generate = FakeGenerator(QUESTIONS)

    for n in (1, 2, 3):
        generate(_cell(count=n))

    assert [c["count"] for c in generate.calls] == [1, 2, 3]


@pytest.mark.parametrize("count", [1, 12, 50])
def test_contract_fixture_serves_a_whole_part(count):
    questions = load(CONTRACT / "toan-22-questions.json")

    valid, _ = FakeGenerator(questions)(_cell("multiple_choice", count=count, topic="none"))

    assert len(valid) == min(count, 12) and all(q["type"] == "multiple_choice" for q in valid)


# --- FakeChunkLookup -------------------------------------------------------------------------------------------

def test_fake_chunk_lookup_has_every_chunk_cited_by_the_contract_fixture():
    """T-029: the Backend's review screen can show the source of every contract question without Qdrant."""
    questions = load(CONTRACT / "toan-22-questions.json")
    ids = [i for q in questions for i in q["source_chunk_ids"]]

    found, missing = FakeChunkLookup.from_file(CONTRACT / "toan-22-chunks.json")(ids)

    assert missing == []
    assert all(found[i]["text"] and found[i]["heading_path"] for i in ids)


def test_fake_lookup_lists_unknown_ids_in_order():
    lookup = FakeChunkLookup([{"id": "a", "text": "x"}])

    assert lookup(["z", "a", "y"]) == ({"a": {"id": "a", "text": "x"}}, ["z", "y"])


def test_fake_lookup_returns_copies():
    chunks = [{"id": "a", "text": "x"}]
    lookup = FakeChunkLookup(chunks)

    lookup(["a"])[0]["a"]["text"] = "changed"

    assert lookup(["a"])[0]["a"]["text"] == "x"


def test_fake_lookup_with_no_ids():
    assert FakeChunkLookup([])([]) == ({}, [])
