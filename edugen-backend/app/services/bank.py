"""Ngân hàng đề: gửi đề vừa nạp cho RAG học (job nền) và cập nhật trạng thái ingest.

Câu của đề đã duyệt vốn có cấu trúc trong DB nên gửi RAG dạng JSON đề (định dạng
`app.rag.chunking.exam` đang cắt), không đi vòng qua DOCX rồi tách lại.
"""

import json
import logging
import uuid

from sqlalchemy.orm import sessionmaker

from app.domain.exam_structure import PART_OF_TYPE
from app.domain.topics import find_topic
from app.models import Exam, ExamBankEntry
from app.models.enums import IngestStatus, QuestionType
from app.services.rag_ingest import Ingester, poll_ingest, start_ingest
from app.services.storage import LocalStorage

WHAT = "đề trong ngân hàng"
log = logging.getLogger("edugen.bank")


def _rag_question(question, part: str, number: int) -> dict:
    content = question.content
    topic = find_topic(question.matrix_cell.topic, grade=question.matrix_cell.matrix.grade)
    q: dict = {
        "part": part, "cau": number, "topic": f"{topic.strand}/{topic.code}" if topic else "",
        "stem": content["stem"],
    }  # fmt: skip
    for key in ("figure", "table"):
        if content.get(key):
            q[key] = content[key]
    kind = QuestionType(content["type"])
    if kind is QuestionType.multiple_choice:
        q["options"] = dict(zip("ABCD", content["options"], strict=True))
    if kind is QuestionType.true_false:
        q["statements"] = [
            {"label": label, "text": s["text"], "answer": s["correct"]}
            for label, s in zip("abcd", content["statements"], strict=True)
        ]  # fmt: skip
    else:
        q["answer"] = content["answer"]
    return q


def exam_to_rag_json(exam: Exam) -> bytes:
    """Đề đã duyệt → JSON đề của app.rag (số câu đánh lại theo phần, như khi xuất DOCX)."""
    counters: dict[str, int] = {}
    questions = []
    for question in exam.questions:
        part = PART_OF_TYPE[QuestionType(question.content["type"])]
        counters[part] = counters.get(part, 0) + 1
        questions.append(_rag_question(question, part, counters[part]))
    year = exam.created_at.year
    return json.dumps({
        "id": str(exam.id), "exam": f"{exam.title} (năm {year})", "subject": exam.matrix.subject.code,
        "ma_de": str(exam.id)[:8], "official": True, "questions": questions,
    }, ensure_ascii=False).encode()  # fmt: skip


def send_exam_to_rag(
    session_factory: sessionmaker, entry_id: uuid.UUID, rag: Ingester, storage: LocalStorage
) -> None:
    """Job nền: mọi lỗi đều kết thúc ở failed kèm lý do, không để bản ghi kẹt pending."""
    try:
        with session_factory() as session:
            entry = session.get(ExamBankEntry, entry_id)
            if entry is None:  # admin gỡ đề trước khi job chạy
                return
            exam = entry.exam
            meta = {
                "source": "exam_bank", "subject": exam.matrix.subject.code,
                "grade": exam.matrix.grade, "title": exam.title, "exam_id": str(exam.id),
                "school_id": str(entry.school_id),  # RBAC: đề ngân hàng chỉ trường mình truy xuất được (T-024)
            }  # fmt: skip
            result = start_ingest(rag, exam_to_rag_json(exam), f"exam_bank-{exam.id}.json", meta, WHAT)
            entry.rag_status, entry.rag_job_id, entry.error_message = result.status, result.job_id, result.error
            session.commit()
    except Exception:
        log.exception("gửi đề trong ngân hàng cho RAG lỗi")
        _mark_failed(
            session_factory, entry_id,
            f"Lỗi hệ thống khi gửi {WHAT} cho RAG, vui lòng thử lại hoặc báo quản trị viên.",
        )  # fmt: skip


def _mark_failed(session_factory: sessionmaker, entry_id: uuid.UUID, message: str) -> None:
    """Phiên mới vì phiên cũ có thể đã hỏng (commit lỗi)."""
    try:
        with session_factory() as session:
            entry = session.get(ExamBankEntry, entry_id)
            if entry is not None:
                entry.rag_status, entry.error_message = IngestStatus.failed, message
                session.commit()
    except Exception:
        log.exception("không ghi được trạng thái failed cho đề %s", entry_id)


def refresh_status(entry: ExamBankEntry, rag: Ingester) -> None:
    result = poll_ingest(rag, entry.rag_status, entry.rag_job_id, WHAT)
    if result:
        entry.rag_status, entry.error_message = result.status, result.error
