"""Tóm tắt: cô lập giáo viên trong cùng trường khi truy xuất: đề mẫu GV tự tải (teacher_id) chỉ GV đó thấy; đoạn của trường không gắn GV (admin tải) và đoạn dùng chung thì mọi GV của trường đều thấy; ô không có teacher_id chỉ thấy đoạn của trường không gắn GV (đóng khi thiếu). Trường khác vẫn không thấy gì."""

from dataclasses import replace

import pytest

from app.rag.storage.retrieve import retrieve
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import DAO_HAM, exam_item, memory_client

MODES = ["hybrid", "dense"]
A, B = "school-a", "school-b"
T1, T2 = "teacher-1", "teacher-2"


def _client():
    return memory_client([
        replace(exam_item(1), school_id=A, teacher_id=T1),
        replace(exam_item(2), school_id=A, teacher_id=T2),
        replace(exam_item(3), school_id=A),  # uploaded by the school admin: the whole school sees it
        exam_item(4),  # shared: official exams
        replace(exam_item(5), school_id=B, teacher_id=T1),  # same teacher id string in another school
    ])


def _ids(cell_extra, mode="hybrid"):
    cell = {"subject": "toan", "topic": DAO_HAM, "type": "multiple_choice"} | cell_extra
    return {e.id for e in retrieve(_client(), FakeEmbedder(), cell, k=50, mode=mode).exam_items}


@pytest.mark.parametrize("mode", MODES)
def test_a_teacher_sees_own_uploads_school_uploads_and_shared_items(mode):
    assert _ids({"school_id": A, "teacher_id": T1}, mode) == {"e1", "e3", "e4"}
    assert _ids({"school_id": A, "teacher_id": T2}, mode) == {"e2", "e3", "e4"}


def test_cell_without_teacher_sees_no_teacher_uploads():
    assert _ids({"school_id": A}) == {"e3", "e4"}


def test_teacher_id_never_crosses_schools():
    assert _ids({"school_id": B, "teacher_id": T1}) == {"e4", "e5"}
    assert _ids({"teacher_id": T1}) == {"e4"}  # no school: shared only


def test_teacher_id_is_stored_and_omitted_when_empty():
    assert replace(exam_item(1), teacher_id=T1).to_dict()["teacher_id"] == T1
    assert "teacher_id" not in exam_item(1).to_dict()
