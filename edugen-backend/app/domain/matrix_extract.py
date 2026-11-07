"""Tóm tắt: đọc ma trận từ JSON do Gemini trích (D-016, T-054), thay parser bảng HTML cho đường Gemini.

Gemini chỉ chép số; việc ghép ý Đúng–Sai thành câu, chọn chủ đề, kiểm 12/4/6 làm ở đây bằng code.
Lỗi nào cũng thành MatrixIssue để giáo viên sửa ở bước xem lại, không ném lỗi.
"""

import json
import re
import unicodedata
from collections import Counter

from app.domain.exam_structure import STATEMENTS_PER_TRUE_FALSE, get_structure
from app.domain.matrix_reader import (
    MC,
    SA,
    STATEMENTS,
    SUBJECT_CODES,
    TF,
    VALID_GRADES,
    MatrixIssue,
    ParsedCell,
    ParsedMatrix,
)
from app.domain.topics import TOPICS, find_topic, topic_grade
from app.models.enums import LEVEL_ORDER, Level

_LEVELS = {"biet": Level.biet, "hieu": Level.hieu, "van_dung": Level.van_dung}
_PART_LABEL = {MC: "Phần I", TF: "Phần II", SA: "Phần III"}
_TYPE_NAME = {MC: "nhiều lựa chọn", TF: "đúng-sai", SA: "trả lời ngắn"}
_COUNT_KEYS = ("multiple_choice", "true_false_statements", "short_answer")
# Hàng tổng/tỉ lệ của bảng mà Gemini hay chép thành rows; "Tổng và hiệu…" vẫn là nội dung.
_SUMMARY_RE = re.compile(r"^(tổng|tổng cộng|(tổng số|tổng điểm|tỉ lệ|tỷ lệ|số câu|số điểm)\b.*|điểm)$")
_LETTER_RE = re.compile(r"([a-d])\W*$")


def _norm(text) -> str:
    return " ".join(unicodedata.normalize("NFC", str(text or "")).casefold().split())


def _int(value) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _counts(raw) -> list[tuple[Level, int]]:
    raw = raw if isinstance(raw, dict) else {}
    return [(level, _int(raw.get(key))) for key, level in _LEVELS.items()]


def _is_content(row: dict) -> bool:
    """Hàng đơn vị kiến thức có số: bỏ hàng tổng/tỉ lệ và hàng tiêu đề chương không có số nào."""
    if _SUMMARY_RE.match(_norm(row.get("unit_name")).rstrip(" :%")):
        return False
    return any(n for key in _COUNT_KEYS for _, n in _counts(row.get(key))) or bool(row.get("true_false_items"))


def _subject_code(name: str) -> str | None:
    """'Toán', 'Môn TOÁN 12', 'Toán học - Lớp 12' → 'toan'."""
    key = _norm(name)
    key = re.sub(r"^môn\s*:?\s*", "", key)
    key = re.sub(r"\s*[-–:]?\s*(lớp\s*)?\d+\s*$", "", key).strip()
    return SUBJECT_CODES.get(key)


def _grade(value) -> int | None:
    grade = _int(value)
    return grade if grade in VALID_GRADES else None


def _item(item) -> tuple[int, str, Level] | None:
    """Một ý Đúng–Sai Gemini liệt kê → (số câu, chữ ý a–d, mức); None nếu không đọc được."""
    if not isinstance(item, dict):
        return None
    cau, y = str(item.get("cau") or ""), str(item.get("y") or "")
    number = re.search(r"\d+", cau) or re.search(r"\d+", y)
    letter = _LETTER_RE.search(_norm(y)) or _LETTER_RE.search(_norm(cau))
    level = _LEVELS.get(_norm(item.get("level")).replace(" ", "_"))
    if not (number and letter and level):
        return None
    return int(number.group()), letter.group(1), level


def _row_topic(row: dict, subject: str | None, grade: int | None, parsed: ParsedMatrix) -> str:
    """Tên chủ đề của hàng (để RAG tra mã); không có mã thì ghi issue và giữ tên gốc."""
    unit = str(row.get("unit_name") or "").strip()
    topic = TOPICS.get(str(row.get("topic_code") or "").strip())
    if topic is not None and subject not in (None, topic.subject):
        topic = None  # Gemini gán mã của môn khác
    topic = topic or find_topic(unit, grade=_grade(row.get("grade")) or grade, subject=subject)
    if topic is None:
        parsed.issues.append(MatrixIssue(
            "Dòng này chưa có mã chủ đề: sửa tên nội dung cho khớp một chủ đề có sẵn trong hệ thống, "
            "hoặc bỏ dòng nếu chưa có SGK cho chủ đề này", unit
        ))  # fmt: skip
        return unit
    return topic.name


def _true_false_cell(members: list[tuple[int, Level]], levels: tuple[Level, ...], rows: list[dict],
                     topics: list[str]) -> ParsedCell:  # fmt: skip
    """Một câu Đúng–Sai từ các ý (chỉ số hàng, mức) theo thứ tự a → d; chủ đề nhiều ý nhất, hòa thì hàng đầu.

    Ý nào cũng giữ nội dung (hàng) của nó trong statement_units; content_unit chỉ có khi cả 4 ý cùng một hàng.
    """
    by_row = Counter(i for i, _ in members)
    topic = Counter(topics[i] for i, _ in members).most_common(1)[0][0]
    unit = rows[next(iter(by_row))]["unit_name"] if len(by_row) == 1 else None
    note = None
    if len(by_row) > 1:
        note = "Ghép từ: " + ", ".join(f"{rows[i]['unit_name']} ({n} ý)" for i, n in by_row.items())
    units = tuple(rows[i]["unit_name"] for i, _ in members)
    return ParsedCell(TF, topic, unit, max(levels, key=LEVEL_ORDER.index), 1, levels, (), note, statement_units=units)


def _coded_questions(rows, topics, parsed) -> list[ParsedCell]:
    """Ghép ý theo mã câu (C1a, C1b…), có thể rải nhiều hàng."""
    groups: dict[int, list] = {}
    for i, row in enumerate(rows):
        for number, letter, level in map(_item, row.get("true_false_items") or []):
            groups.setdefault(number, []).append((i, letter, level))
    cells = []
    for number, items in sorted(groups.items()):
        letters = Counter(y for _, y, _ in items)
        if sorted(letters) != list(STATEMENTS) or max(letters.values()) > 1:
            written = ", ".join(f"{y}×{n}" if n > 1 else y for y, n in sorted(letters.items()))
            parsed.issues.append(MatrixIssue(
                f"Câu Đúng – Sai {number}: cần đủ 4 ý a–d, mỗi ý đúng một lần (đang có: {written})", f"Câu {number}"
            ))  # fmt: skip
            continue
        by_letter = {y: (i, level) for i, y, level in items}
        levels = tuple(by_letter[y][1] for y in STATEMENTS)
        cells.append(_true_false_cell([by_letter[y] for y in STATEMENTS], levels, rows, topics))
    return cells


def _sequential_questions(rows, topics, parsed) -> list[ParsedCell]:
    """Không có mã câu: xếp ý theo thứ tự hàng rồi mức, cứ 4 ý một câu, mức tăng dần trong câu."""
    statements = [(i, level) for i, row in enumerate(rows)
                  for level, n in _counts(row.get("true_false_statements")) for _ in range(n)]  # fmt: skip
    if len(statements) % STATEMENTS_PER_TRUE_FALSE:
        parsed.issues.append(MatrixIssue(
            f"Số ý Đúng – Sai là {len(statements)}, không chia hết cho {STATEMENTS_PER_TRUE_FALSE}: không ghép được thành câu"
        ))  # fmt: skip
        return []
    cells = []
    for start in range(0, len(statements), STATEMENTS_PER_TRUE_FALSE):
        chunk = sorted(statements[start : start + STATEMENTS_PER_TRUE_FALSE], key=lambda s: LEVEL_ORDER.index(s[1]))
        cells.append(_true_false_cell(chunk, tuple(level for _, level in chunk), rows, topics))
    return cells


def _true_false_cells(rows, topics, parsed) -> list[ParsedCell]:
    items = [_item(item) for row in rows for item in row.get("true_false_items") or []]
    if items and all(items):
        from_items = Counter(level for _, _, level in items)
        from_counts = Counter()
        for row in rows:
            from_counts.update(dict(_counts(row.get("true_false_statements"))))
        from_counts = +from_counts  # bỏ mức có 0 ý
        if from_items == from_counts:
            return _coded_questions(rows, topics, parsed)
        parsed.issues.append(MatrixIssue(
            "Danh sách ý Đúng – Sai không khớp số ý theo mức trên ma trận; đã ghép theo số lượng, hãy kiểm tra lại"
        ))  # fmt: skip
    return _sequential_questions(rows, topics, parsed)


def _check_structure(parsed: ParsedMatrix) -> None:
    """Giữ cấu trúc 12/4/6 (D-016): lệch thì báo rõ, không sinh đề sai cấu trúc."""
    if parsed.subject is None:
        return
    have = Counter()
    for cell in parsed.cells:
        have[cell.type] += cell.count
    for qtype, need in get_structure(parsed.subject).question_counts.items():
        if have[qtype] != need:
            parsed.issues.append(MatrixIssue(
                f"{_PART_LABEL[qtype]} cần đủ {need} câu {_TYPE_NAME[qtype]}, hiện có {have[qtype]}: "
                f"{'thêm' if have[qtype] < need else 'bớt'} {abs(need - have[qtype])} câu ở các ô của phần này "
                "(cấu trúc bắt buộc 12 nhiều lựa chọn / 4 đúng-sai / 6 trả lời ngắn, chưa hỗ trợ câu tự luận)"
            ))  # fmt: skip


_LEVEL_LABELS = {Level.biet: "Biết", Level.hieu: "Hiểu", Level.van_dung: "VD"}


def _levels_text(counts: dict[Level, int]) -> str:
    return ", ".join(f"{_LEVEL_LABELS[lv]} {counts[lv]}" for lv in LEVEL_ORDER)


def _check_row_totals(rows: list[dict], parsed: ParsedMatrix) -> None:
    """Cột Tổng của hàng (lệnh hỏi theo mức, Đ/S đếm theo ý) phải bằng tổng các phần đọc được ở hàng đó.

    Gemini hay đọc lệch cột (chép số của cột Tổng vào một phần, bỏ sót một mã ý); lệch thì báo đúng hàng.
    """
    for row in rows:
        declared = dict(_counts(row.get("row_totals")))
        if not any(declared.values()):
            continue  # bảng không có cột Tổng, hoặc Gemini không chép
        read = Counter()
        for key in _COUNT_KEYS:
            read.update(dict(_counts(row.get(key))))
        read = {lv: read[lv] for lv in LEVEL_ORDER}
        if read != declared:
            parsed.issues.append(MatrixIssue(
                f"Hàng '{row['unit_name']}': cột Tổng ghi {_levels_text(declared)} nhưng các phần đọc được "
                f"{_levels_text(read)}; hãy kiểm tra lại các ô của hàng này", row["unit_name"],
            ))  # fmt: skip


_HOURS_RE = re.compile(r"\s*\(\s*\d+\s*tiết\s*\)\s*$", re.IGNORECASE)


def _clean_row(row: dict) -> dict:
    """Bỏ số tiết cuối tên nội dung: 'Tính đơn điệu… (6 tiết)' → 'Tính đơn điệu…'."""
    name = " ".join(str(row["unit_name"]).split())
    return row | {"unit_name": _HOURS_RE.sub("", name) or name}


def parse_extracted_matrix(text: str) -> ParsedMatrix:
    parsed = ParsedMatrix(declared_required=False)
    try:
        data = json.loads(text)
        rows = [_clean_row(r) for r in data["rows"] if isinstance(r, dict) and r.get("unit_name") and _is_content(r)]
    except (ValueError, KeyError, TypeError):
        parsed.issues.append(MatrixIssue("Không đọc được kết quả Gemini: không phải JSON"))
        return parsed

    subject_name = str(data.get("subject") or "").strip()
    parsed.subject = _subject_code(subject_name)
    if parsed.subject is None:
        parsed.issues.append(MatrixIssue(f"Môn '{subject_name}' chưa được hỗ trợ"))
    parsed.name = data.get("name") or None
    grades = [g for g in (_grade(r.get("grade")) for r in rows) if g]
    parsed.grade = max(grades, default=None)  # đề thi lấy lớp lớn nhất; lớp từng hàng chỉ gợi ý chọn chủ đề

    topics = [_row_topic(r, parsed.subject, parsed.grade, parsed) for r in rows]
    if parsed.grade is None:  # file không ghi lớp: lấy lớp lớn nhất của các chương đã có mã (SGK KNTT)
        known = {t.name: t for t in TOPICS.values() if t.subject == parsed.subject}
        chapter_grades = [topic_grade(known[name], 0) for name in topics if name in known]
        parsed.grade = max((g for g in chapter_grades if g in VALID_GRADES), default=None)
    if parsed.grade is None:
        parsed.issues.append(MatrixIssue(
            "Không xác định được lớp của ma trận: ghi lớp (10, 11 hoặc 12) ở từng dòng nội dung rồi tải lại"
        ))  # fmt: skip
    cells: dict = {MC: [], SA: []}
    for qtype, key in ((MC, "multiple_choice"), (SA, "short_answer")):
        for row, topic in zip(rows, topics, strict=True):
            for level, n in _counts(row.get(key)):
                if n:
                    cells[qtype].append(ParsedCell(qtype, topic, row["unit_name"], level, n, None, ()))
    parsed.cells = cells[MC] + _true_false_cells(rows, topics, parsed) + cells[SA]
    _check_row_totals(rows, parsed)
    _check_structure(parsed)
    return parsed
