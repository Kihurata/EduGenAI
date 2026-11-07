"""Đề mẫu (T-050): job nền đọc file gốc thành bản nháp JSON chờ GV duyệt; GV sửa bản nháp (kiểm tra lại mỗi lần lưu);
GV xác nhận thì gửi RAG học và theo dõi trạng thái ingest. Môn, official và school_id lấy từ bản ghi, không từ bản nháp.
"""

import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.domain.exam_draft import normalize_draft, validate_exam_draft
from app.models import SampleExam
from app.models.enums import IngestStatus, UserRole
from app.services.draft_extractor import DraftExtractor, ExtractionError
from app.services.rag_ingest import Ingester, RagDeleter, poll_ingest, start_ingest
from app.services.storage import LocalStorage

WHAT = "đề mẫu"
log = logging.getLogger("edugen.sample_exams")


def extract_draft(
    session_factory: sessionmaker, sample_id: uuid.UUID, extractor: DraftExtractor, storage: LocalStorage
) -> None:
    with session_factory() as session:
        try:
            sample = session.get(SampleExam, sample_id)
            if sample is None:
                return
            draft = extractor.extract(
                storage.read(sample.storage_key), sample.original_filename, sample.subject.code, sample.grade
            )
            set_draft(sample, draft)
            sample.status, sample.error_message = IngestStatus.needs_review, None
            session.commit()
        except ExtractionError as exc:
            session.rollback()
            _mark_failed(session_factory, sample_id, f"Không đọc được {WHAT}: {exc}")
        except Exception:
            session.rollback()
            log.exception("đọc đề mẫu lỗi")
            _mark_failed(
                session_factory, sample_id,
                f"Lỗi hệ thống khi đọc {WHAT}, vui lòng thử lại hoặc báo quản trị viên.",
            )  # fmt: skip


def set_draft(sample: SampleExam, draft: dict[str, Any]) -> None:
    """Lưu bản nháp (đã gắn môn/official) và lỗi kiểm tra; lớp của đề theo bản nháp."""
    draft = normalize_draft(draft, sample.subject.code, sample.grade)
    sample.draft = draft
    sample.draft_issues = [i.as_dict() for i in validate_exam_draft(draft, sample.subject.code)]
    if isinstance(draft.get("grade"), int) and 10 <= draft["grade"] <= 12:
        sample.grade = draft["grade"]


def confirm(sample: SampleExam, rag: Ingester) -> None:
    """Gửi bản nháp đã sạch lỗi cho RAG; cùng tên file mỗi lần nên nạp lại thay các đoạn cũ."""
    meta = {
        "source": "sample_exam", "subject": sample.subject.code, "grade": sample.grade, "title": sample.title,
        "school_id": str(sample.school_id), "official": False, "exam_kind": sample.draft.get("exam_kind") or None,
    }  # fmt: skip
    if sample.uploader.role is UserRole.teacher:  # đề GV tự tải: chỉ GV đó truy xuất; đề admin tải cả trường dùng
        meta["teacher_id"] = str(sample.uploaded_by)
    data = json.dumps(sample.draft, ensure_ascii=False).encode("utf-8")
    result = start_ingest(rag, data, f"sample-{sample.id}.json", meta, WHAT)
    sample.status, sample.rag_job_id, sample.error_message = result.status, result.job_id, result.error


def _mark_failed(session_factory: sessionmaker, sample_id: uuid.UUID, message: str) -> None:
    try:
        with session_factory() as session:
            sample = session.get(SampleExam, sample_id)
            if sample is not None:
                sample.status, sample.error_message = IngestStatus.failed, message
                session.commit()
    except Exception:
        log.exception("không ghi được trạng thái failed cho đề mẫu %s", sample_id)


def refresh_status(sample: SampleExam, rag: Ingester) -> None:
    result = poll_ingest(rag, sample.status, sample.rag_job_id, WHAT)
    if result:
        sample.status, sample.error_message = result.status, result.error


def delete_sample_exam(db: Session, sample: SampleExam, rag: RagDeleter) -> None:
    """T-046: Qdrant first, then the row; if RAG fails the row stays so the delete can be retried."""
    rag.delete(str(sample.school_id), f"sample-{sample.id}.json")  # same name as confirm()'s ingest
    db.delete(sample)
    db.commit()
