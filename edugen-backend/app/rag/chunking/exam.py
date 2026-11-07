"""Tóm tắt: cắt file JSON đề thi chính thức thành đoạn (T-004): mỗi câu hỏi một Chunk kind=exam_item, có đề bài, hình/bảng, phương án hoặc ý a–d và đáp án, kèm năm, mã đề, phần, câu, chủ đề, dạng câu (type) và mức độ nếu nguồn có (T-034). Lớp lấy từ tham số grade, hoặc khoá "grade" trong file (mặc định 12, đề tốt nghiệp); đề định kỳ đặt "heading" để thay nhãn "Toán TN <năm> mã <mã đề>"; không có heading mà thiếu năm hoặc mã đề (đề trường, có thể không có ma_de) thì nhãn là tên đề (T-055)."""

import hashlib
import json
import re
from pathlib import Path

from app.rag.chunking.markdown import SUBJECT_NAMES
from app.rag.dto import Chunk

# Same as vocab.PART_BY_TYPE inverted; chunking may only import dto (test_architecture).
TYPE_BY_PART = {"I": "multiple_choice", "II": "true_false", "III": "short_answer"}


def chunk_exam(path, grade=None):
    path = Path(path)
    exam = json.loads(path.read_text(encoding="utf-8"))
    found = re.search(r"\d{4}", exam["exam"])
    year = int(found.group()) if found else None  # school exams often print no year
    grade = grade or exam.get("grade", 12)
    ma_de = exam.get("ma_de") or None  # đề kiểm tra của trường thường không có mã đề (T-055)
    heading = exam.get("heading") or _heading(exam, year, ma_de)
    chunks = []
    for q in exam["questions"]:
        label = f"{heading} > Phần {q['part']} > Câu {q['cau']}"
        chunks.append(Chunk(
            id=exam_item_id(path.name, q["part"], q["cau"]),
            kind="exam_item",
            text=_text(q),
            subject=exam["subject"],
            grade=grade,
            chapter="",
            lesson="",
            section="",
            heading_path=label,
            source=path.name,
            page=None,
            official=exam["official"],
            year=year,
            exam_code=ma_de,
            part=q["part"],
            question_no=q["cau"],
            topic=q["topic"],
            type=TYPE_BY_PART[q["part"]],
            level=q.get("level"),
            statement_levels=q.get("statement_levels"),
        ))
    return chunks


def _heading(exam, year, ma_de):
    """Đề tốt nghiệp: "Toán TN 2025 mã 0101"; thiếu năm hoặc mã đề thì lấy tên đề, không ghi "TN None"."""
    if year and ma_de:
        return f"{SUBJECT_NAMES[exam['subject']]} TN {year} mã {ma_de}"
    return exam["exam"]


def exam_item_id(source, part, cau):
    return hashlib.sha1(f"{source}|{part}|{cau}".encode()).hexdigest()[:16]


def _text(q):
    lines = [f"Câu {q['cau']}. {q['stem']}"]
    if "figure" in q:
        lines.append(f"Hình: {q['figure']}")
    if "table" in q:
        head, *rows = q["table"]
        lines += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        lines += ["| " + " | ".join(r) + " |" for r in rows]
    for letter, option in q.get("options", {}).items():
        lines.append(f"{letter}. {option}")
    for s in q.get("statements", []):
        lines.append(f"{s['label']}) {s['text']}")
    if "statements" in q:
        answer = ", ".join(f"{s['label']}) {'Đúng' if s['answer'] else 'Sai'}" for s in q["statements"])
    else:
        answer = q["answer"]
    lines.append(f"Đáp án: {answer}")
    return "\n".join(lines)
