"""Tóm tắt: Backend xoá dữ liệu Qdrant khi xoá trường hoặc đề mẫu (T-046, ví dụ 4): gọi xoá của RAG đúng một lần với đúng school_id (và source của đề mẫu), xoá Qdrant trước, RAG lỗi thì bản ghi trong DB còn nguyên để xoá lại; LocalRag nối xoá vào cùng client Qdrant."""

import uuid

import pytest

from app.core.errors import LLMError
from app.models import SampleExam, School, Subject, User
from app.rag.dto import GenerationResult
from app.rag.storage.qdrant import COLLECTION
from app.services import rag_client
from app.services.rag_client import LocalRag
from app.services.sample_exams import delete_sample_exam
from app.services.schools import delete_school
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import exam_item, memory_client


class FakeRag:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def delete(self, school_id, source=None):
        self.calls.append((school_id, source))
        if self.error:
            raise self.error


def _school_with_sample(db):
    school = School(code="nd", name="THPT Nguyễn Du")
    subject = Subject(code="toan", name="Toán học")
    db.add_all([school, subject])
    db.flush()
    teacher = User(school_id=school.id, email="gv@nd.vn", password_hash="x", full_name="GV")
    db.add(teacher)
    db.flush()
    sample = SampleExam(
        school_id=school.id, uploaded_by=teacher.id, subject_id=subject.id, grade=12, title="Đề 1",
        original_filename="de.json", mime_type="application/json", size_bytes=1, storage_key="s/1",
        checksum_sha256="0" * 64,
    )  # fmt: skip
    db.add(sample)
    db.commit()
    return school, sample


def test_deleting_a_sample_exam_deletes_its_points_once(db):
    school, sample = _school_with_sample(db)
    rag = FakeRag()

    delete_sample_exam(db, sample, rag)

    assert rag.calls == [(str(school.id), f"sample-{sample.id}.json")]
    assert db.get(SampleExam, sample.id) is None


def test_deleting_a_school_deletes_its_points_once(db):
    school, sample = _school_with_sample(db)
    school_id, sample_id = school.id, sample.id
    rag = FakeRag()

    delete_school(db, school, rag)

    assert rag.calls == [(str(school_id), None)]
    db.expire_all()
    assert db.get(School, school_id) is None and db.get(SampleExam, sample_id) is None  # DB cascade


def test_rag_failure_keeps_the_db_rows(db):
    school, sample = _school_with_sample(db)

    with pytest.raises(LLMError):
        delete_school(db, school, FakeRag(LLMError("qdrant down")))

    db.expire_all()
    assert db.get(School, school.id) is not None and db.get(SampleExam, sample.id) is not None


def test_local_rag_without_a_deleter_raises():
    with pytest.raises(LLMError):
        LocalRag(lambda cell: GenerationResult([], [])).delete("school-a")


def test_wired_delete_removes_the_schools_points_from_qdrant():
    from dataclasses import replace

    a = str(uuid.uuid4())
    client = memory_client([exam_item(1), replace(exam_item(2), school_id=a)])
    generate, index, delete = rag_client.wire_rag(client, FakeEmbedder())

    LocalRag(generate, index, delete).delete(a)

    assert client.count(COLLECTION).count == 1


def test_rag_that_cannot_start_reports_the_reason_on_delete(monkeypatch):
    def no_index():
        raise RuntimeError("chưa có QDRANT_URL")

    monkeypatch.setattr(rag_client, "_build_rag", no_index)
    rag_client.local_rag.cache_clear()
    try:
        with pytest.raises(LLMError, match="chưa có QDRANT_URL"):
            rag_client.local_rag().delete("school-a")
    finally:
        rag_client.local_rag.cache_clear()


def test_mock_rag_delete_is_a_no_op():
    from app.services.rag_mock import SampleRag

    assert SampleRag([]).delete("school-a", "sample-1.json") is None
