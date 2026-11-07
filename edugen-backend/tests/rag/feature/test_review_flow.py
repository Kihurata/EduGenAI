"""Tóm tắt: feature test luồng duyệt đề phía RAG (F-05, T-019 / T-029): câu vừa sinh → màn hình duyệt tra được nguồn trích dẫn; giáo viên sửa câu → kiểm tra lại không cần truy xuất (validate(q, None)) kèm SymPy; sửa sai thì có lý do, nguồn lạ hiện là thiếu chứ không lỗi."""

import copy

from app.rag.checking import check
from app.rag.pipeline import make_generator
from app.rag.storage.lookup import make_chunk_lookup
from tests.rag.fakes import FakeEmbedder, FakeLLM
from tests.rag.support import LLM_OUTPUT, cell, exam_item, memory_client, reply, theory

TOPIC = "dai_so_giai_tich/dao_ham"


def _generated(qtype):
    client = memory_client([theory(1), theory(2), exam_item(1, TOPIC, "I"), exam_item(2, TOPIC, "III")])
    valid, _ = make_generator(client, FakeEmbedder(), FakeLLM([reply(LLM_OUTPUT[qtype])]))(cell(qtype, topic=TOPIC))
    return client, valid[0]


def test_the_review_screen_shows_where_a_generated_question_comes_from():
    client, q = _generated("short_answer")

    found, missing = make_chunk_lookup(client)(q["source_chunk_ids"])

    assert missing == []
    assert [(found[i]["heading_path"], found[i]["page"]) for i in q["source_chunk_ids"]] == [
        ("Bài 1 > Mục 1", 1), ("Bài 1 > Mục 2", 2)]


def test_an_unchanged_question_passes_the_recheck():
    _, q = _generated("true_false")

    assert check(q, None) == []


def test_a_teacher_fixing_the_wording_passes():
    _, q = _generated("multiple_choice")
    edited = copy.deepcopy(q) | {"stem": "Đạo hàm của hàm số $y = x^2$ bằng"}

    assert check(edited, None) == []


def test_a_teacher_breaking_the_format_gets_the_reasons():
    _, q = _generated("multiple_choice")
    edited = copy.deepcopy(q)
    del edited["options"]["D"]
    edited["answer"] = "D"

    # One reason: the answer letter is still A–D; the missing option is what the options rule reports.
    assert check(edited, None) == ["multiple_choice needs exactly options A, B, C, D"]


def test_a_teacher_changing_a_short_answer_is_rechecked_with_sympy():
    _, q = _generated("short_answer")
    edited = copy.deepcopy(q) | {"answer": "3"}

    assert check(edited, None) == ["answer 3 but SymPy gives 2 for 'diff(x**2, x).subs(x, 1)'"]


def test_a_teacher_fixing_both_answer_and_expression_passes():
    _, q = _generated("short_answer")
    edited = copy.deepcopy(q) | {"answer": "3", "sympy": {"expr": "diff(x**3, x).subs(x, 1)"}}

    assert check(edited, None) == []
    assert edited["sympy"]["verified"] is True


def test_a_teacher_removing_every_source_is_told_to_keep_one():
    _, q = _generated("true_false")

    assert check(copy.deepcopy(q) | {"source_chunk_ids": []}, None) == ["no source_chunk_ids"]


def test_a_source_the_index_does_not_know_shows_as_missing_not_an_error():
    client, q = _generated("multiple_choice")
    edited = copy.deepcopy(q) | {"source_chunk_ids": ["t1", "from-another-book"]}

    assert check(edited, None) == []  # no retrieval run to compare against
    assert make_chunk_lookup(client)(edited["source_chunk_ids"])[1] == ["from-another-book"]


def test_rechecking_does_not_change_an_unedited_question():
    _, q = _generated("short_answer")
    before = copy.deepcopy(q)

    check(q, None)

    assert q == before
