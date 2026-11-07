"""Câu hỏi RAG trả về (`cau_hoi`, khóa tiếng Việt không dấu) → câu hỏi của BE.

RAG đã tự lọc câu, nhưng BE vẫn kiểm lại cấu trúc theo dạng câu trước khi lưu: câu sai
cấu trúc không dựng được đề nên tính là câu bị loại. Câu hợp lệ được chuẩn hóa:

    {
      "type": "multiple_choice" | "true_false" | "short_answer",
      "level": "Biết" | "Hiểu" | "Vận dụng",
      "stem": "...",                                     # đề bài, LaTeX $...$
      "options": ["...", "...", "...", "..."],           # chỉ multiple_choice, A → D
      "statements": [{"text", "correct", "explanation"}] # chỉ true_false, ý a → d
      "answer": "B" | "SĐSS" | "7,07",
      "solution": "...",
      "citations": [...],                                # trich_dan, giữ nguyên
      "check": {...} | null,                             # kiem_tra (SymPy), giữ nguyên
      "figure": "...",                                   # hinh, chỉ khi câu cần hình (mô tả bằng chữ)
      "table": [["...", ...], ...],                      # bang, chỉ khi câu cần bảng số liệu
      "figure_spec": {"solid", "a", "b", "h", "foot"},   # hinh_ve, tham số hình khối để BE vẽ (domain/figure.py)
    }
Thêm `figure_svg` (BE vẽ từ figure_spec, domain/figure.py:with_figure) không có khóa RAG nên không đi ngược về RAG.
"""

import re
from typing import Any

from app.domain.cell import Cell
from app.domain.exam_structure import STATEMENTS_PER_TRUE_FALSE
from app.models.enums import Level, QuestionType

Question = dict[str, Any]

MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer

TYPE_FROM_RAG = {"nhieu_lua_chon": MC, "dung_sai": TF, "tra_loi_ngan": SA}
TYPE_TO_RAG = {t: k for k, t in TYPE_FROM_RAG.items()}
LEVEL_FROM_RAG = {"Biet": Level.biet, "Hieu": Level.hieu, "Van_dung": Level.van_dung}
LEVEL_TO_RAG = {lv: k for k, lv in LEVEL_FROM_RAG.items()}

OPTION_LETTERS = "ABCD"
TRUE_FALSE_MARKS = {True: "Đ", False: "S"}
SHORT_ANSWER_MAX_CHARS = 4  # phiếu trả lời ngắn có 4 ô (kể cả dấu "-" và ",")
EXTRA_KEYS = (("hinh", "figure"), ("bang", "table"), ("hinh_ve", "figure_spec"))  # tùy chọn, giữ nguyên khi có


_SEPARATOR_CELL = re.compile(r":?-+:?")
Segment = dict[str, Any]  # {"text": str} | {"table": list[list[str]]}


def _math_end(t: str, i: int) -> int:
    """Vị trí ngay sau công thức $...$ / $$...$$ bắt đầu tại `i` (hết dòng nếu không đóng)."""
    delim = "$$" if t.startswith("$$", i) else "$"
    end = t.find(delim, i + len(delim))
    return len(t) if end < 0 else end + len(delim)


def _cells(line: str) -> list[str]:
    """Tách một dòng bảng markdown theo `|`; `\\|` là dấu `|` thường, `|` trong $...$ / $$...$$ được giữ."""
    t = line.strip()
    cells: list[str] = []
    buf, i = "", 0
    while i < len(t):
        ch = t[i]
        if ch == "\\" and t[i + 1 : i + 2] == "|":
            buf, i = buf + "|", i + 2
        elif ch == "$":
            end = _math_end(t, i)
            buf, i = buf + t[i:end], end
        elif ch == "|":
            cells.append(buf.strip())
            buf, i = "", i + 1
        else:
            buf, i = buf + ch, i + 1
    cells.append(buf.strip())
    if t.startswith("|"):
        cells = cells[1:]
    if t.endswith("|") and not t.endswith("\\|") and cells:
        cells = cells[:-1]
    return cells


def _is_separator(line: str) -> bool:
    return "|" in line and all(_SEPARATOR_CELL.fullmatch(c) for c in _cells(line)) and bool(_cells(line))


def stem_blocks(q: Question) -> list[Segment]:
    """Đề bài → các khối theo thứ tự: {"text": ...} hoặc {"table": hàng} (bảng chuẩn, hàng đầu là header).

    Bảng markdown trong đề (dòng `| x | … |` + dòng `|---|`; dấu `|` đầu/cuối tùy chọn) thành khối
    bảng tại đúng chỗ, không bỏ bảng nào. Có trường `table` thì trường đó là bảng chuẩn: bảng markdown
    bị bỏ khỏi đề và bảng của trường đứng ngay sau phần chữ. Dòng có `|` mà không có dòng phân cách
    ngay sau là chữ thường.
    """
    lines = q["stem"].split("\n")
    segments: list[Segment] = []
    text: list[str] = []

    def flush() -> None:
        if (joined := "\n".join(text).strip()):
            segments.append({"text": joined})
        text.clear()

    i = 0
    while i < len(lines):
        if "|" in lines[i] and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            flush()
            rows = [_cells(lines[i])]
            i += 2
            while i < len(lines) and "|" in lines[i]:
                rows.append(_cells(lines[i]))
                i += 1
            segments.append({"table": rows})
        else:
            text.append(lines[i])
            i += 1
    flush()
    field = q.get("table")
    if isinstance(field, list) and field:
        rows = [[str(c) for c in r] for r in field if isinstance(r, list)]
        segments = [s for s in segments if "text" in s]
        if len(segments) > 1:  # chữ rời nhau do bảng bị bỏ → nối lại một khối
            segments = [{"text": "\n".join(s["text"] for s in segments)}]
        return [*segments, {"table": rows}]
    return segments


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_multiple_choice(raw: dict[str, Any], errors: list[str]) -> None:
    options = raw.get("phuong_an")
    if not (isinstance(options, list) and len(options) == 4 and all(map(_text, options))):
        errors.append("Câu nhiều lựa chọn cần đúng 4 phương án không rỗng")
    if raw.get("dap_an") not in tuple(OPTION_LETTERS):
        errors.append("Đáp án phải là A, B, C hoặc D")


def _check_true_false(raw: dict[str, Any], errors: list[str]) -> None:
    items = raw.get("y_dung_sai")
    ok = (
        isinstance(items, list)
        and len(items) == STATEMENTS_PER_TRUE_FALSE
        and all(isinstance(i, dict) and _text(i.get("noi_dung")) and isinstance(i.get("dung"), bool) for i in items)
    )  # fmt: skip
    if not ok:
        errors.append("Câu đúng sai cần đúng 4 ý, mỗi ý có nội dung và đúng/sai")
    answer = raw.get("dap_an")
    if not (isinstance(answer, str) and len(answer) == 4 and set(answer) <= set("ĐS")):
        errors.append("Đáp án câu đúng sai phải gồm 4 ký tự Đ/S")
    elif ok and answer != "".join(TRUE_FALSE_MARKS[i["dung"]] for i in items):
        errors.append("Đáp án câu đúng sai không khớp với đúng/sai của từng ý")


def _check_short_answer(raw: dict[str, Any], errors: list[str]) -> None:
    answer = raw.get("dap_an")
    if not _text(answer):
        errors.append("Câu trả lời ngắn thiếu đáp án")
    elif len(answer.strip()) > SHORT_ANSWER_MAX_CHARS:
        errors.append(f"Đáp án trả lời ngắn tối đa {SHORT_ANSWER_MAX_CHARS} ký tự (đang là {answer!r})")


_CHECKS = {MC: _check_multiple_choice, TF: _check_true_false, SA: _check_short_answer}


def _normalize(raw: dict[str, Any], type_: QuestionType, level: Level) -> Question:
    question: Question = {"type": type_.value, "level": level.value, "stem": raw["de_bai"]}
    if type_ is MC:
        question["options"] = list(raw["phuong_an"])
    if type_ is TF:
        question["statements"] = [
            {"text": i["noi_dung"], "correct": i["dung"], "explanation": i.get("giai_thich") or ""}
            for i in raw["y_dung_sai"]
        ]
    question |= {
        "answer": raw["dap_an"].strip(),
        "solution": raw["loi_giai"],
        "citations": list(raw.get("trich_dan") or []),
        "check": raw.get("kiem_tra"),
    }
    for raw_key, key in EXTRA_KEYS:
        if raw.get(raw_key):
            question[key] = raw[raw_key]
    return question


def parse_question(raw: Any, cell: Cell | None) -> tuple[Question | None, list[str]]:
    """Kiểm cấu trúc câu RAG trả về; hợp lệ → (câu đã chuẩn hóa, []), ngược lại (None, lỗi)."""
    if not isinstance(raw, dict):
        return None, ["Câu hỏi không phải object JSON"]
    errors: list[str] = []
    type_ = TYPE_FROM_RAG.get(raw.get("dang"))
    level = LEVEL_FROM_RAG.get(raw.get("muc_do"))
    if type_ is None:
        errors.append(f"Không nhận ra dạng câu {raw.get('dang')!r}")
    if level is None:
        errors.append(f"Không nhận ra mức độ {raw.get('muc_do')!r}")
    if not _text(raw.get("de_bai")):
        errors.append("Thiếu đề bài")
    if not _text(raw.get("loi_giai")):
        errors.append("Thiếu lời giải")
    if type_ is not None:
        _CHECKS[type_](raw, errors)
    if cell is not None and type_ is not None and type_ is not cell.type:
        errors.append(f"Sai dạng câu: ô cần {TYPE_TO_RAG[cell.type]}, RAG trả {raw['dang']}")
    if cell is not None and level is not None and level is not cell.level:
        errors.append(f"Sai mức độ: ô cần {cell.level.value}, RAG trả {level.value}")
    if errors:
        return None, errors
    return _normalize(raw, type_, level), []


def to_rag(question: Question) -> dict[str, Any]:
    """Câu của BE (vd GV vừa sửa) → dạng RAG, để kiểm lại bằng parse_question và gửi /validate.

    Giá trị lạ được giữ nguyên để parse_question báo lỗi thay vì đoán.
    """
    type_, level = question.get("type"), question.get("level")
    raw: dict[str, Any] = {
        "dang": TYPE_TO_RAG.get(type_, type_) if isinstance(type_, str) else type_,
        "muc_do": LEVEL_TO_RAG.get(level, level) if isinstance(level, str) else level,
        "de_bai": question.get("stem"),
        "dap_an": question.get("answer"),
        "loi_giai": question.get("solution"),
        "trich_dan": question.get("citations") or [],
        "kiem_tra": question.get("check"),
    }
    if "options" in question:
        raw["phuong_an"] = question["options"]
    for raw_key, key in EXTRA_KEYS:
        if question.get(key):
            raw[raw_key] = question[key]
    statements = question.get("statements")
    if isinstance(statements, list):
        raw["y_dung_sai"] = [
            {"noi_dung": s.get("text"), "dung": s.get("correct"), "giai_thich": s.get("explanation")}
            if isinstance(s, dict) else s
            for s in statements
        ]  # fmt: skip
    elif statements is not None:
        raw["y_dung_sai"] = statements
    return raw


def split_questions(raws: list[Any], cell: Cell | None) -> tuple[list[Question], list[dict[str, Any]]]:
    """Tách câu hợp lệ (đã chuẩn hóa) và câu bị loại ({"question": gốc, "errors": [...]})."""
    valid, rejected = [], []
    for raw in raws:
        question, errors = parse_question(raw, cell)
        if question is None:
            rejected.append({"question": raw, "errors": errors})
        else:
            valid.append(question)
    return valid, rejected
