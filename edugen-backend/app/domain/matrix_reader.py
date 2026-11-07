"""Đọc ma trận đề từ markdown do marker sinh (docs/marker.md).

Marker chạy với html_tables_in_markdown nên bảng là HTML giữ rowspan/colspan: nhờ đó phân
biệt được ô gộp dọc (gán cho cả chủ đề) với ô thường. Mọi chỗ không đọc được hoặc lệch hàng
tổng đều thành MatrixIssue để giáo viên sửa ở bước xem lại; không ném lỗi, không đoán.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from app.domain.exam_structure import (
    FULL_SCORE,
    STATEMENTS_PER_TRUE_FALSE,
    get_structure,
)
from app.models.enums import LEVEL_ORDER, Level, QuestionType

MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer

SUBJECT_CODES = {
    "toán học": "toan", "toán": "toan",
    "vật lí": "ly", "vật lý": "ly", "lí": "ly", "lý": "ly",
    "hóa học": "hoa", "hoá học": "hoa", "hóa": "hoa", "hoá": "hoa",
}  # fmt: skip
VALID_GRADES = range(10, 13)
STATEMENTS = "abcd"

# Từ khóa nhận dạng cột dạng câu trong header (so chữ thường).
TYPE_KEYWORDS = [(MC, "nhiều lựa chọn"), (TF, "đúng"), (SA, "trả lời ngắn")]
TYPE_LABELS = {MC: "Nhiều lựa chọn", TF: "Đúng – Sai", SA: "Trả lời ngắn"}

Column = tuple[QuestionType, Level]

_COUNT_RE = re.compile(r"^(\d+)\s*(?:\((.*)\))?$")
_TF_RE = re.compile(r"^([\da-d,\s]+?)\s*(?:\((.*)\))?$")
_TF_ITEM_RE = re.compile(r"^(\d*)([a-d])$")


@dataclass(frozen=True)
class MatrixIssue:
    message: str
    location: str | None = None  # "Chủ đề › Đơn vị › Dạng / Mức" hoặc "Dạng / Mức"


@dataclass(frozen=True)
class ParsedCell:
    type: QuestionType
    topic: str
    content_unit: str | None  # None khi ô gộp trùm cả chủ đề
    level: Level  # Đúng–Sai: mức cao nhất của 4 ý
    count: int  # số CÂU
    statement_levels: tuple[Level, ...] | None = None  # chỉ Đúng–Sai, ý a → d
    competency_codes: tuple[str, ...] = ()  # Đúng–Sai: hợp mã của 4 ý
    # Chữ gốc trên ô để đối chiếu với ảnh; Đúng–Sai giữ theo từng ý a → d.
    source_text: str | None = None
    statement_codes: tuple[tuple[str, ...], ...] | None = None
    statement_texts: tuple[str, ...] | None = None
    # Chỉ Đúng–Sai: nội dung kiến thức của ý a → d (một câu có thể rải nhiều nội dung); None = không rõ.
    statement_units: tuple[str | None, ...] | None = None


@dataclass
class ParsedMatrix:
    subject: str | None = None  # mã môn, vd "toan"
    grade: int | None = None
    name: str | None = None
    cells: list[ParsedCell] = field(default_factory=list)
    # Hàng "Tổng số câu"/"Tổng số điểm" ghi trên ma trận; Đúng–Sai đếm theo ý.
    declared_counts: dict[Column, int] = field(default_factory=dict)
    declared_points: dict[Column, Decimal] = field(default_factory=dict)
    issues: list[MatrixIssue] = field(default_factory=list)
    declared_required: bool = True  # False khi nguồn (JSON Gemini) không có hàng tổng để đối chiếu


# ----- HTML → lưới ô -----


@dataclass(frozen=True)
class _Slot:
    text: str
    top: int
    left: int
    height: int


class _TableReader(HTMLParser):
    """Lấy bảng đầu tiên: danh sách hàng, mỗi hàng là (text, rowspan, colspan)."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[tuple[str, int, int]]] = []
        self.found = False
        self._done = False
        self._cell: list[str] | None = None
        self._spans = (1, 1)

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        attrs = dict(attrs)
        if tag == "table":
            self.found = True
        elif tag == "tr" and self.found:
            self.rows.append([])
        elif tag in ("td", "th") and self.rows:
            self._cell = []
            self._spans = (int(attrs.get("rowspan") or 1), int(attrs.get("colspan") or 1))
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self.rows[-1].append((" ".join("".join(self._cell).split()), *self._spans))
            self._cell = None
        elif tag == "table" and self.found:
            self._done = True

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _grid(rows: list[list[tuple[str, int, int]]]) -> list[list[_Slot | None]]:
    occupied: dict[tuple[int, int], _Slot] = {}
    for r, cells in enumerate(rows):
        c = 0
        for text, rowspan, colspan in cells:
            while (r, c) in occupied:
                c += 1
            slot = _Slot(text, r, c, min(rowspan, len(rows) - r))
            for dr in range(slot.height):
                for dc in range(colspan):
                    occupied[(r + dr, c + dc)] = slot
            c += colspan
    width = max((c for _, c in occupied), default=-1) + 1
    return [[occupied.get((r, c)) for c in range(width)] for r in range(len(rows))]


def _text(slot: _Slot | None) -> str:
    return slot.text if slot else ""


def _label(text: str) -> str:
    return text.strip().rstrip(".").strip()


def group_issues(issues: list[MatrixIssue]) -> list[MatrixIssue]:
    """Gộp lỗi cùng nội dung thành một dòng; các vị trí khác nhau nối bằng dấu phẩy, giữ thứ tự xuất hiện."""
    locations: dict[tuple[str, bool], list[str]] = {}  # lỗi chung (không vị trí) tách khỏi lỗi có vị trí
    for issue in issues:
        found = locations.setdefault((issue.message, bool(issue.location)), [])
        if issue.location and issue.location not in found:
            found.append(issue.location)
    return [MatrixIssue(message, ", ".join(found) or None) for (message, _), found in locations.items()]


# ----- Phần đầu -----


def _read_title(before_table: str, parsed: ParsedMatrix) -> None:
    plain = before_table.replace("*", "").replace("#", "")
    if m := re.search(r"Môn\s*:\s*(.+?)\s*[-–]\s*Lớp\s*:\s*(\d+)", plain):
        subject_name, grade = m.group(1).strip(), int(m.group(2))
        parsed.subject = SUBJECT_CODES.get(subject_name.lower())
        if parsed.subject is None:
            parsed.issues.append(MatrixIssue(f"Môn '{subject_name}' chưa được hỗ trợ"))
        if grade in VALID_GRADES:
            parsed.grade = grade
        else:
            parsed.issues.append(MatrixIssue(
                f"Lớp {grade} không hợp lệ, chỉ nhận lớp 10–12: sửa dòng 'Môn: … - Lớp: …' trên ma trận rồi ghi lại"
            ))  # fmt: skip
    else:
        parsed.issues.append(MatrixIssue("Không tìm thấy dòng 'Môn: … - Lớp: …'"))
    if m := re.search(r"Tên ma trận\s*:\s*(.+)", plain):
        parsed.name = m.group(1).strip()
    else:
        parsed.issues.append(MatrixIssue("Không tìm thấy dòng 'Tên ma trận: …'"))


# ----- Header bảng -----


@dataclass
class _Layout:
    data_start: int
    topic_col: int
    unit_col: int
    columns: dict[int, Column]  # cột giá trị → (dạng, mức)


def _read_layout(grid: list[list[_Slot | None]]) -> _Layout | None:
    levels = {lv.value.lower(): lv for lv in Level}
    level_row = next(
        (r for r, row in enumerate(grid) if sum(_text(s).lower() in levels for s in row) >= 3), None
    )
    if level_row is None:
        return None
    header = grid[: level_row + 1]

    def find_col(*keywords: str) -> int | None:
        for row in header:
            for c, slot in enumerate(row):
                if any(k in _text(slot).lower() for k in keywords):
                    return c
        return None

    topic_col, unit_col = find_col("chủ đề", "chương"), find_col("nội dung", "đơn vị")
    if topic_col is None or unit_col is None:
        return None

    columns = {}
    for c, slot in enumerate(grid[level_row]):
        level = levels.get(_text(slot).lower())
        qtype = next(
            (t for row in header[:level_row] for t, k in TYPE_KEYWORDS if k in _text(row[c]).lower()),
            None,
        )
        if level and qtype:
            columns[c] = (qtype, level)
    return _Layout(level_row + 1, topic_col, unit_col, columns)


# ----- Giá trị ô -----


def _column_label(column: Column) -> str:
    return f"{TYPE_LABELS[column[0]]} / {column[1].value}"


def _codes(raw: str | None) -> tuple[str, ...]:
    return tuple(c.strip() for c in re.split(r"[,;]", raw or "") if c.strip())


def _read_count(text: str) -> tuple[int, tuple[str, ...]] | None:
    if m := _COUNT_RE.match(text):
        return int(m.group(1)), _codes(m.group(2))
    return None


def _read_statements(text: str) -> tuple[set[int], str, tuple[str, ...]] | None:
    """'2a, 2b (GQ1.4)' → ({2}, 'ab', ('GQ1.4',)). Tập số câu để phát hiện ghi lệch."""
    m = _TF_RE.match(text)
    if not m:
        return None
    items = [_TF_ITEM_RE.match(i.strip()) for i in m.group(1).split(",") if i.strip()]
    if not items or not all(items):
        return None
    counts = {int(i.group(1) or 1) for i in items}
    return counts, "".join(i.group(2) for i in items), _codes(m.group(2))


# ----- Đọc bảng -----


@dataclass
class _TrueFalseGroup:
    topic: str
    unit: str | None
    location: str
    counts: set[int] = field(default_factory=set)
    letters: dict[str, list[Level]] = field(default_factory=lambda: defaultdict(list))
    codes: list[str] = field(default_factory=list)
    letter_codes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    letter_texts: dict[str, str] = field(default_factory=dict)


def _span_unit(grid, layout: _Layout, slot: _Slot) -> tuple[str, str | None] | None:
    """(chủ đề, đơn vị) của ô; None nếu ô gộp qua nhiều chủ đề."""
    rows = range(slot.top, slot.top + slot.height)
    topics = {grid[r][layout.topic_col] for r in rows}
    if len(topics) > 1:
        return None
    [topic_slot] = topics
    topic = _label(_text(topic_slot))
    if slot.height == 1:
        return topic, _label(_text(grid[slot.top][layout.unit_col]))
    if topic_slot and (topic_slot.top, topic_slot.height) == (slot.top, slot.height):
        return topic, None
    return topic, "; ".join(_label(_text(grid[r][layout.unit_col])) for r in rows)


def _read_totals(row, layout: _Layout, parsed: ParsedMatrix, kind: str) -> None:
    for c, column in layout.columns.items():
        raw = _text(row[c]).replace(",", ".")
        if not raw:
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation:
            parsed.issues.append(MatrixIssue(f"Không đọc được ô tổng '{raw}'", _column_label(column)))
            continue
        if kind == "count":
            parsed.declared_counts[column] = int(value)
        else:
            parsed.declared_points[column] = value


def _read_body(grid, layout: _Layout, parsed: ParsedMatrix) -> None:
    plain: list[tuple[tuple[int, int], ParsedCell]] = []
    tf_groups: dict[tuple[int, int], _TrueFalseGroup] = {}

    for r in range(layout.data_start, len(grid)):
        row = grid[r]
        row_text = " ".join(_text(s).lower() for s in row)
        if "tổng số câu" in row_text:
            _read_totals(row, layout, parsed, "count")
            continue
        if "tổng số điểm" in row_text:
            _read_totals(row, layout, parsed, "points")
            continue

        for c, column in layout.columns.items():
            slot = row[c]
            if not slot or slot.top != r or slot.left != c or not slot.text:
                continue
            qtype, level = column
            place = _span_unit(grid, layout, slot)
            if place is None:
                parsed.issues.append(
                    MatrixIssue(f"Ô '{slot.text}' gộp qua nhiều chủ đề", _column_label(column))
                )
                continue
            topic, unit = place
            location = f"{topic} › {unit or '(cả chủ đề)'} › {_column_label(column)}"

            if qtype is TF:
                read = _read_statements(slot.text)
                if read is None:
                    parsed.issues.append(MatrixIssue(
                        f"Không đọc được ô '{slot.text}': ô Đúng – Sai cần ghi ý, vd 'a, b' hoặc '2a, 2b'",
                        location,
                    ))  # fmt: skip
                    continue
                counts, letters, codes = read
                group = tf_groups.setdefault(
                    (slot.top, slot.height),
                    _TrueFalseGroup(topic, unit, f"{topic} › {unit or '(cả chủ đề)'} › Đúng – Sai"),
                )
                group.counts |= counts
                for letter in letters:
                    group.letters[letter].append(level)
                    group.letter_codes[letter] = codes
                    group.letter_texts[letter] = slot.text
                group.codes += [code for code in codes if code not in group.codes]
                continue

            read = _read_count(slot.text)
            if read is None:
                parsed.issues.append(MatrixIssue(f"Không đọc được ô '{slot.text}': ô cần ghi số câu, vd '2' hoặc '2 (GQ1.4)'", location))
                continue
            count, codes = read
            if count > 0:
                plain.append(((r, c), ParsedCell(qtype, topic, unit, level, count, None, codes, slot.text)))

    tf_cells = [cell for cell in (_true_false_cell(g, parsed) for _, g in sorted(tf_groups.items())) if cell]
    by_type = defaultdict(list)
    for _, cell in sorted(plain, key=lambda item: item[0]):
        by_type[cell.type].append(cell)
    parsed.cells = by_type[MC] + tf_cells + by_type[SA]


def _true_false_cell(group: _TrueFalseGroup, parsed: ParsedMatrix) -> ParsedCell | None:
    problems = []
    if len(group.counts) > 1:
        problems.append(f"các ý ghi số câu khác nhau ({', '.join(map(str, sorted(group.counts)))})")
    if sorted(group.letters) != list(STATEMENTS) or any(len(v) > 1 for v in group.letters.values()):
        written = ", ".join(f"{k}×{len(v)}" if len(v) > 1 else k for k, v in sorted(group.letters.items()))
        problems.append(f"cần đủ 4 ý a–d, mỗi ý đúng một lần (đang có: {written})")
    if problems:
        parsed.issues.append(MatrixIssue("Câu Đúng – Sai: " + "; ".join(problems), group.location))
        return None
    levels = tuple(group.letters[letter][0] for letter in STATEMENTS)
    return ParsedCell(
        TF, group.topic, group.unit, max(levels, key=LEVEL_ORDER.index), group.counts.pop(),
        levels, tuple(group.codes),
        statement_codes=tuple(group.letter_codes[letter] for letter in STATEMENTS),
        statement_texts=tuple(group.letter_texts[letter] for letter in STATEMENTS),
        statement_units=(group.unit,) * STATEMENTS_PER_TRUE_FALSE if group.unit else None,
    )  # fmt: skip


def parse_matrix_markdown(markdown: str) -> ParsedMatrix:
    """Đọc phần đầu và bảng; lỗi của từng ô nằm trong `issues`, không đối chiếu hàng tổng."""
    if markdown.lstrip().startswith("{"):  # JSON do Gemini trích (D-016); markdown của marker không bao giờ mở bằng {
        # import muộn: matrix_extract dùng lại các kiểu ở đây
        from app.domain.matrix_extract import parse_extracted_matrix

        return parse_extracted_matrix(markdown)
    parsed = ParsedMatrix()
    table_at = markdown.find("<table")
    _read_title(markdown if table_at < 0 else markdown[:table_at], parsed)
    if table_at < 0:
        parsed.issues.append(MatrixIssue(
            "Không tìm thấy bảng HTML; chạy marker với html_tables_in_markdown (xem docs/marker.md)"
        ))  # fmt: skip
        return parsed

    reader = _TableReader()
    reader.feed(markdown[table_at:])
    grid = _grid(reader.rows)
    layout = _read_layout(grid)
    if layout is None or not layout.columns:
        parsed.issues.append(MatrixIssue(
            "Không nhận ra header bảng: cần cột Chủ đề, Nội dung và hàng mức độ Biết/Hiểu/Vận dụng"
        ))  # fmt: skip
        return parsed
    _read_body(grid, layout, parsed)
    return parsed


# ----- Đối chiếu hàng tổng -----


def _tally(cells: list[ParsedCell]) -> dict[Column, int]:
    """Số câu theo cột; Đúng–Sai đếm theo ý như hàng tổng trên ma trận."""
    tally: dict[Column, int] = defaultdict(int)
    for cell in cells:
        if cell.statement_levels:
            for level in cell.statement_levels:
                tally[(cell.type, level)] += cell.count
        else:
            tally[(cell.type, cell.level)] += cell.count
    return tally


def check_totals(parsed: ParsedMatrix) -> list[MatrixIssue]:
    """So các ô với hàng 'Tổng số câu'/'Tổng số điểm' và kiểm tổng điểm bằng 10."""
    tally = _tally(parsed.cells)
    issues = [
        MatrixIssue(f"Không thấy hàng '{label}' trên ma trận nên không đối chiếu được các ô đã đọc")
        for label, declared in (("Tổng số câu", parsed.declared_counts), ("Tổng số điểm", parsed.declared_points))
        if parsed.declared_required and not declared
    ]
    issues += [
        MatrixIssue(f"Tổng số câu ghi {declared} nhưng cộng các ô được {tally[column]}: sửa số câu ở các ô của cột này cho đủ {declared}", _column_label(column))
        for column, declared in parsed.declared_counts.items()
        if declared != tally[column]
    ]
    if parsed.subject is None:
        return issues

    points = get_structure(parsed.subject).points
    unit_points = {MC: points[MC], TF: points[TF] / STATEMENTS_PER_TRUE_FALSE, SA: points[SA]}
    actual = {column: unit_points[column[0]] * n for column, n in tally.items()}
    issues += [
        MatrixIssue(
            f"Tổng số điểm ghi {declared.normalize():f} nhưng tính từ các ô được "
            f"{actual.get(column, Decimal(0)).normalize():f}",
            _column_label(column),
        )
        for column, declared in parsed.declared_points.items()
        if declared != actual.get(column, Decimal(0))
    ]
    total = sum(actual.values(), Decimal(0))
    if total != FULL_SCORE:
        issues.append(MatrixIssue(
            f"Tổng điểm của ma trận là {total.normalize():f}, phải bằng {FULL_SCORE.normalize():f}: "
            "sửa số câu theo cấu trúc 12 nhiều lựa chọn / 4 đúng-sai / 6 trả lời ngắn"
        ))  # fmt: skip
    return issues


def read_matrix(markdown: str) -> ParsedMatrix:
    """Đọc ma trận và đối chiếu hàng tổng. Không có issue → trạng thái parsed, ngược lại invalid."""
    parsed = parse_matrix_markdown(markdown)
    parsed.issues += check_totals(parsed)
    return parsed
