"""Tóm tắt: danh sách môn hệ thống chạy được, kèm cấu trúc đề từng môn (D-020, T-064). Frontend đọc từ đây thay vì ghi
cứng Toán và 12/4/6: trang kiểm ma trận so số câu theo đúng môn, trang đề mẫu lấy danh sách môn."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.core.subjects import SUBJECTS
from app.domain.exam_structure import get_structure
from app.models.enums import QuestionType

router = APIRouter(prefix="/subjects", tags=["subjects"])


class SubjectOut(BaseModel):
    code: str
    name: str  # tên chính thức, như dòng "Môn:" của ma trận
    label: str  # tên ngắn để hiển thị
    duration_minutes: int
    question_counts: dict[QuestionType, int]  # số câu từng dạng của đề chính thức
    points: dict[QuestionType, float]  # điểm tối đa một câu


@router.get("")
def list_subjects(user: CurrentUser) -> list[SubjectOut]:
    out = []
    for s in SUBJECTS.values():
        structure = get_structure(s.code)
        out.append(SubjectOut(
            code=s.code, name=s.name, label=s.label, duration_minutes=structure.duration_minutes,
            question_counts=structure.question_counts, points={t: float(p) for t, p in structure.points.items()},
        ))  # fmt: skip
    return out
