"""Tóm tắt: unit test cô lập trường (RBAC) khi truy xuất: đề mẫu/tài liệu một trường nạp lên chỉ trường đó thấy, đoạn dùng chung (school_id None: SGK, đề chính thức) trường nào cũng thấy, ô không có school_id thì chỉ thấy đoạn dùng chung (đóng khi thiếu). Viết trước khi có tính năng: hiện phải FAIL."""

from dataclasses import replace

import pytest

from app.rag.storage.retrieve import retrieve
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import DAO_HAM, exam_item, memory_client, theory

MODES = ["hybrid", "dense"]
A, B = "school-a", "school-b"


def _owned(chunk, school_id):
    """Chunk uploaded by one school; school_id=None means shared (SGK, official national exams)."""
    return replace(chunk, school_id=school_id)


def _cell(school_id=None, **extra):
    cell = {"subject": "toan", "topic": DAO_HAM, "type": "multiple_choice"} | extra
    return cell if school_id is None else cell | {"school_id": school_id}


def _mixed_client():
    return memory_client([
        _owned(exam_item(1), A), _owned(exam_item(2), A),
        _owned(exam_item(3), B),
        _owned(exam_item(4), None),
        _owned(theory(1), A), _owned(theory(2), B), _owned(theory(3), None),
    ])


@pytest.mark.parametrize("mode", MODES)
def test_exam_items_of_another_school_are_never_returned(mode):
    _, exam_items = retrieve(_mixed_client(), FakeEmbedder(), _cell(A), k=50, mode=mode)

    assert {e.id for e in exam_items} == {"e1", "e2", "e4"}


@pytest.mark.parametrize("mode", MODES)
def test_theory_of_another_school_is_never_returned(mode):
    theory_chunks, _ = retrieve(_mixed_client(), FakeEmbedder(), _cell(B), k=50, mode=mode)

    assert {t.id for t in theory_chunks} == {"t2", "t3"}


def test_returned_chunks_carry_their_school_id():
    theory_chunks, exam_items = retrieve(_mixed_client(), FakeEmbedder(), _cell(A), k=50)

    assert {c.school_id for c in theory_chunks + exam_items} == {A, None}


def test_shared_chunks_are_visible_to_every_school():
    c = _mixed_client()

    for school in (A, B):
        theory_chunks, exam_items = retrieve(c, FakeEmbedder(), _cell(school), k=50)
        assert "t3" in {t.id for t in theory_chunks} and "e4" in {e.id for e in exam_items}


@pytest.mark.parametrize("mode", MODES)
def test_a_cell_without_school_sees_only_shared_chunks(mode):
    """Fail closed: a caller that forgets school_id must not see any school's private uploads."""
    theory_chunks, exam_items = retrieve(_mixed_client(), FakeEmbedder(), _cell(), k=50, mode=mode)

    assert [t.id for t in theory_chunks] == ["t3"] and [e.id for e in exam_items] == ["e4"]


def test_an_unknown_school_sees_only_shared_chunks():
    theory_chunks, exam_items = retrieve(_mixed_client(), FakeEmbedder(), _cell("school-zzz"), k=50)

    assert [t.id for t in theory_chunks] == ["t3"] and [e.id for e in exam_items] == ["e4"]


def test_school_filter_combines_with_exclude_year():
    c = memory_client([_owned(exam_item(1), A), _owned(replace(exam_item(2), year=2026), A),
                       _owned(replace(exam_item(3), year=2026), B)])

    _, exam_items = retrieve(c, FakeEmbedder(), _cell(A), k=50, exclude_year=2025)

    assert [e.id for e in exam_items] == ["e2"]


def test_school_id_survives_the_payload_round_trip():
    chunk = _owned(exam_item(1), A)

    assert type(chunk).from_dict(chunk.to_dict()).school_id == A


@pytest.mark.parametrize("mode", MODES)
def test_isolation_holds_on_a_large_mixed_index(mode):
    schools = (A, B, "school-c", None)
    chunks = [_owned(exam_item(i), schools[i % 4]) for i in range(400)]
    chunks += [_owned(theory(1000 + i), schools[i % 4]) for i in range(400)]

    theory_chunks, exam_items = retrieve(memory_client(chunks), FakeEmbedder(), _cell(B), k=150, mode=mode)

    assert len(exam_items) == 150 and len(theory_chunks) == 150
    assert {c.school_id for c in theory_chunks + exam_items} <= {B, None}
