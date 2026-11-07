"""Tóm tắt: bản nháp đề GV tải lên (T-050), theo schema của app.rag.chunking.exam. `validate_exam_draft` liệt kê lỗi
theo từng câu ("II-2") để GV sửa trên màn hình duyệt; `normalize_draft` ghi đè các trường do hệ thống quyết định
(môn, official = false) để bản nháp do LLM hay GV viết không đổi được chúng.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.domain.topics import topic_grade, topics_for

PARTS = ("I", "II", "III")
LEVELS = ("Biết", "Hiểu", "Vận dụng")
OPTIONS = ("A", "B", "C", "D")
STATEMENT_LABELS = ("a", "b", "c", "d")
EXAM_KINDS = ("tot_nghiep", "dinh_ky_7991")  # D-017: định dạng đề, cùng bộ với app.rag.manifest (test TC-028 giữ khớp)
_OLD_EXAM_KINDS = {"thi_thu": "tot_nghiep", "dinh_ky": "dinh_ky_7991"}  # bộ cũ của T-050
_NUMBER = re.compile(r"-?\d+(,\d+)?")  # đáp án Phần III trên phiếu: số, dấu trừ, dấu phẩy thập phân


@dataclass(frozen=True)
class DraftIssue:
    message: str
    question: str | None = None  # "<phần>-<câu>", None = lỗi của cả đề

    def as_dict(self) -> dict[str, Any]:
        return {"message": self.message, "question": self.question}


def migrate_exam_kind(kind: str | None, grade: int) -> str | None:
    """D-017 mục 5: đổi loại đề cũ sang bộ mới; `khac` theo lớp (12 → tot_nghiep, 10–11 → dinh_ky_7991)."""
    if not kind:
        return None
    if kind == "khac":
        return "tot_nghiep" if grade == 12 else "dinh_ky_7991"
    return _OLD_EXAM_KINDS.get(kind, kind)


def normalize_draft(draft: dict[str, Any], subject: str, grade: int) -> dict[str, Any]:
    """Bản sao bản nháp với môn và official do hệ thống gắn; lớp mặc định là lớp khi tải lên."""
    return {**draft, "subject": subject, "official": False, "grade": draft.get("grade") or grade}


def _blank(value: Any) -> bool:
    return not isinstance(value, str) or not value.strip()


def validate_exam_draft(draft: dict[str, Any], subject: str) -> list[DraftIssue]:
    issues: list[DraftIssue] = []
    if _blank(draft.get("exam")):
        issues.append(DraftIssue("Thiếu tên đề"))
    grade = draft.get("grade")
    if not isinstance(grade, int) or not 10 <= grade <= 12:
        issues.append(DraftIssue(f"Lớp {grade} không hợp lệ, chỉ nhận lớp 10–12"))
        grade = 12
    if draft.get("exam_kind") not in (None, "", *EXAM_KINDS):
        issues.append(DraftIssue(f"loại đề '{draft['exam_kind']}' không có trong danh sách {', '.join(EXAM_KINDS)}"))
    questions = draft.get("questions")
    if not isinstance(questions, list) or not questions:
        return [*issues, DraftIssue("Đề chưa có câu nào")]

    topics = {f"{t.strand}/{t.code}": t for t in topics_for(subject)}
    seen: set[str] = set()
    for q in questions:
        where = f"{q.get('part')}-{q.get('cau')}"
        issues += [DraftIssue(m, where) for m in _question_issues(q, topics, grade)]
        if where in seen:
            issues.append(DraftIssue("Số câu bị trùng trong cùng một phần", where))
        seen.add(where)
    return issues


def _question_issues(q: dict[str, Any], topics: dict, grade: int) -> list[str]:
    part = q.get("part")
    if part not in PARTS:
        return [f"Phần '{part}' không hợp lệ, chỉ nhận I, II, III"]
    out = []
    if not isinstance(q.get("cau"), int):
        out.append("Số câu phải là số nguyên")
    if _blank(q.get("stem")):
        out.append("Thiếu đề bài")
    topic = topics.get(q.get("topic"))
    if topic is None:
        out.append("Chưa chọn chủ đề, hoặc chủ đề không thuộc môn của đề")
    elif topic_grade(topic, grade) > grade:
        out.append(f"Chương '{topic.name}' là chủ đề lớp {topic_grade(topic, grade)}, không dùng cho đề lớp {grade}")
    if q.get("level") not in (None, "", *LEVELS):
        out.append(f"mức độ '{q['level']}' không hợp lệ (Biết / Hiểu / Vận dụng)")
    if part == "I":
        out += _multiple_choice_issues(q)
    elif part == "II":
        out += _true_false_issues(q)
    elif not isinstance(q.get("answer"), str) or not _NUMBER.fullmatch(q["answer"].strip()):
        out.append("Đáp án trả lời ngắn phải là một con số (dấu phẩy thập phân, ví dụ -1,5)")
    return out


def _multiple_choice_issues(q: dict[str, Any]) -> list[str]:
    options = q.get("options")
    out = []
    if not isinstance(options, dict) or tuple(sorted(options)) != OPTIONS or any(_blank(v) for v in options.values()):
        out.append("Câu trắc nghiệm cần đủ 4 phương án A–D")
    if q.get("answer") not in OPTIONS:
        out.append("Thiếu đáp án hoặc đáp án không phải A, B, C, D")
    return out


def _true_false_issues(q: dict[str, Any]) -> list[str]:
    statements = q.get("statements")
    out = []
    if not isinstance(statements, list) or [s.get("label") for s in statements] != list(STATEMENT_LABELS):
        out.append("Câu đúng/sai cần đủ 4 ý a, b, c, d")
    elif any(_blank(s.get("text")) or not isinstance(s.get("answer"), bool) for s in statements):
        out.append("Mỗi ý cần nội dung và đáp án Đúng/Sai")
    levels = q.get("statement_levels")
    if levels is not None and (not isinstance(levels, list) or len(levels) != 4 or any(lv not in LEVELS for lv in levels)):
        out.append("Cần mức độ cho đủ 4 ý, mỗi ý Biết / Hiểu / Vận dụng")
    return out
