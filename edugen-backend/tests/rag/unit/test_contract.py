"""Tóm tắt: unit test hợp đồng câu hỏi RAG → Backend (T-028): đề Toán 2025 mã 0101 đổi sang 22 câu đúng dạng hợp đồng (loại, mức độ, mã chủ đề mới, đoạn trích dẫn), file mẫu giao Backend không lệch code; thêm kiểm tra từng trường và dữ liệu mức độ."""

import pytest

from app.rag.checking.validate import validate
from app.rag.chunking.exam import chunk_exam
from app.rag.contract import to_contract
from app.rag.vocab import LEVELS, PART_BY_TYPE, TOPICS
from tests.rag.support import CONTRACT, EXAM_2025, load

LEVELS_FILE = CONTRACT / "levels-toan-tn-2025-0101.json"


def _questions():
    return to_contract(load(EXAM_2025), load(LEVELS_FILE))


# --- existing behaviour ----------------------------------------------------------------------------------------

def test_22_questions_in_part_order():
    qs = _questions()

    assert [q["part"] for q in qs] == ["I"] * 12 + ["II"] * 4 + ["III"] * 6
    assert all(PART_BY_TYPE[q["type"]] == q["part"] for q in qs)


def test_every_question_fits_the_contract():
    for q in _questions():
        assert validate(q, None) == [], q["cau"]
        assert q["level"] in LEVELS
        assert q["topic"] in TOPICS
        assert q["source_chunk_ids"]


def test_true_false_statements_have_levels_and_question_takes_the_highest():
    q1 = next(q for q in _questions() if q["type"] == "true_false")

    assert [s["level"] for s in q1["statements"]] == ["Biết", "Biết", "Biết", "Hiểu"]
    assert q1["level"] == "Hiểu"


def test_source_chunk_ids_are_the_exam_item_chunk_ids():
    ids = {(c.part, c.question_no): c.id for c in chunk_exam(EXAM_2025)}

    assert all(q["source_chunk_ids"] == [ids[(q["part"], q["cau"])]] for q in _questions())


def test_concrete_question():
    q = _questions()[0]

    assert (q["type"], q["answer"], q["level"], q["topic"]) == (
        "multiple_choice", "C", "Hiểu", "hinh_hoc_do_luong/vecto_khong_gian")
    assert q["explanation"] == "" and "figure" in q


def test_committed_contract_fixture_matches_code():
    assert load(CONTRACT / "toan-22-questions.json") == _questions()


# --- field by field --------------------------------------------------------------------------------------------

def test_every_true_false_question_takes_its_hardest_statement_level():
    for q in _questions():
        if q["type"] == "true_false":
            assert q["level"] == max((s["level"] for s in q["statements"]), key=LEVELS.index)


def test_true_false_questions_have_no_options_or_answer_key():
    for q in _questions():
        if q["type"] == "true_false":
            assert "options" not in q and "answer" not in q


def test_other_types_have_no_statements():
    assert all("statements" not in q for q in _questions() if q["type"] != "true_false")


def test_numbering_restarts_in_each_part():
    qs = _questions()

    for part, n in (("I", 12), ("II", 4), ("III", 6)):
        assert [q["cau"] for q in qs if q["part"] == part] == list(range(1, n + 1))


def test_the_contract_fixture_has_no_sympy_field():
    assert all("sympy" not in q for q in _questions())  # D-008: the Backend treats sympy as optional


def test_the_chunk_fixture_holds_exactly_the_cited_chunks():
    cited = {i for q in _questions() for i in q["source_chunk_ids"]}

    assert {c["id"] for c in load(CONTRACT / "toan-22-chunks.json")} == cited


def test_a_missing_level_entry_fails_loudly():
    levels = load(LEVELS_FILE)
    del levels["I"]["1"]

    with pytest.raises(KeyError):
        to_contract(load(EXAM_2025), levels)


def test_a_true_false_level_list_of_the_wrong_length_fails_loudly():
    levels = load(LEVELS_FILE)
    levels["II"]["1"] = ["Biết", "Hiểu"]

    with pytest.raises(ValueError):
        to_contract(load(EXAM_2025), levels)
