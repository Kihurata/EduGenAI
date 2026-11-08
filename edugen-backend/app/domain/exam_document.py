"""Câu hỏi đã chuẩn hóa → nội dung đề, cùng bố cục với bản xem trước A4 ở trang Xuất đề.

Đề dựng thành danh sách khối (đầu đề, đoạn, phương án, bảng) rồi mới in ra markdown hoặc DOCX
(services/docx_export.py), nên hai định dạng luôn cùng nội dung. Bố cục khớp
frontend/src/features/teacher/ExamExportPage.tsx: đầu đề hai cột, phương án chia 4/2/1 cột theo độ
dài, bản GV có đáp án + lời giải ngay dưới từng câu và bảng đáp án sau "HẾT". Số "Câu n" đánh lại
từ 1 trong mỗi phần; LaTeX $...$ giữ nguyên.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.domain.cell import Cell
from app.domain.exam_structure import PART_OF_TYPE, TRUE_FALSE_POINTS, TYPE_OF_PART, get_structure
from app.domain.matrix_reader import TYPE_LABELS
from app.domain.question import OPTION_LETTERS, TRUE_FALSE_MARKS, Question, stem_blocks
from app.models.enums import ExportVariant, QuestionType

MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer

# Khớp PART_HEAD của frontend (features/teacher/lib.tsx).
PART_TITLES = {
    MC: "Câu trắc nghiệm nhiều phương án lựa chọn",
    TF: "Câu trắc nghiệm đúng sai",
    SA: "Câu trắc nghiệm trả lời ngắn",
}
PART_GUIDES = {
    MC: "Mỗi câu hỏi thí sinh chỉ chọn một phương án.",
    TF: "Trong mỗi ý a), b), c), d) ở mỗi câu, thí sinh chọn đúng hoặc sai.",
    SA: "Thí sinh ghi đáp số vào phiếu trả lời.",
}
STATEMENT_LETTERS = "abcd"
VARIANT_LABELS = {ExportVariant.student: "Bản học sinh", ExportVariant.teacher: "Bản giáo viên"}


@dataclass(frozen=True)
class ExamInfo:
    school_name: str  # schools.name
    title: str  # tên kỳ thi = "Tên ma trận"
    subject_name: str
    grade: int
    duration_minutes: int  # GV nhập
    code: str | None = None  # mã đề; None = bản gốc, không in mã
    subject_code: str = ""  # mã môn, để lấy thang điểm cho bảng đáp án; trống = không ghi điểm


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class Header:
    """Đầu đề hai cột (trường | kỳ thi, môn, thời gian, mã đề) + dòng họ tên; `label` in ở chân trang."""

    info: ExamInfo
    label: str  # "Bản học sinh" / "Bản giáo viên"
    teacher: bool = False


@dataclass(frozen=True)
class Heading:
    """Tiêu đề in đậm (DOCX không dùng style Heading của Word để giữ đúng phông đề thi)."""

    level: int
    text: str


@dataclass(frozen=True)
class Paragraph:
    runs: tuple[Run, ...]
    center: bool = False
    gap: bool = False  # cách đoạn trên một khoảng, như mở đầu một câu / một phần
    aside: bool = False  # thụt lề, kẻ vạch trái: đáp án và lời giải dưới câu (bản GV)


@dataclass(frozen=True)
class Item:
    """Dòng ý đúng/sai ("a) …")."""

    runs: tuple[Run, ...]


@dataclass(frozen=True)
class Options:
    """Bốn phương án A–D chia `cols` cột (4, 2 hoặc 1) theo độ dài, như bản xem trước."""

    texts: tuple[str, ...]
    cols: int


@dataclass(frozen=True)
class Table:
    rows: tuple[tuple[str, ...], ...]  # hàng đầu là header
    center: bool = False  # căn giữa, chữ nhỏ: bảng đáp án
    header: bool = False  # hàng đầu in đậm (bảng đáp án, ma trận đề)
    widths: tuple[float, ...] = ()  # bề rộng cột (cm); trống = chia đều


@dataclass(frozen=True)
class Figure:
    """Hình khối của câu (SVG từ domain/figure.py); caption là mô tả chữ, dùng khi không nhúng được ảnh."""

    svg: str
    caption: str = ""


@dataclass(frozen=True)
class PageBreak:
    pass


Block = Header | Heading | Paragraph | Item | Options | Table | Figure | PageBreak


def _p(text: str, bold: bool = False, center: bool = False, gap: bool = False) -> Paragraph:
    return Paragraph((Run(text, bold),), center, gap)


MATH_SPLIT = re.compile(r"(\$\$[\s\S]+?\$\$|\$[^$]+?\$)")


def solution_steps(text: str) -> list[str]:
    """Lời giải → các bước: theo xuống dòng, không có thì theo câu (không cắt trong $...$). Khớp solutionSteps ở FE."""
    by_line = [s.strip() for s in re.split(r"\n+", text) if s.strip()]
    if len(by_line) > 1:
        return by_line
    steps: list[str] = []
    buf = ""
    for i, part in enumerate(MATH_SPLIT.split(text)):
        if i % 2:
            buf += part
            continue
        for k, seg in enumerate(re.split(r"(?<=\.)\s+", part)):
            if k > 0:
                if buf.strip():
                    steps.append(buf.strip())
                buf = ""
            buf += seg
    if buf.strip():
        steps.append(buf.strip())
    return steps


def _glyphs(o: str) -> int:
    return len(re.sub(r"[${}^_\s]", "", re.sub(r"\\[a-zA-Z]+", "x", o)))


def option_columns(options: Sequence[str]) -> int:
    """Số cột phương án theo phương án dài nhất (lệnh LaTeX tính một ký tự). Khớp optionColumns(…, wide) ở FE."""
    longest = max(map(_glyphs, options), default=0)
    if longest <= 12:
        return 4
    return 2 if longest <= 30 else 1


def math_option(o: str) -> str:
    """Phương án có LaTeX mà thiếu $...$ (vd "(\\infty; 2)") thì bọc lại thành công thức. Khớp mathOption ở FE."""
    return f"${o}$" if "$" not in o and re.search(r"\\[a-zA-Z]+", o) else o


def _by_part(questions: list[Question]) -> dict[QuestionType, list[Question]]:
    """Gom câu theo phần, giữ thứ tự trong phần; bỏ phần không có câu."""
    parts = {t: [q for q in questions if q["type"] == t.value] for t in TYPE_OF_PART.values()}
    return {t: qs for t, qs in parts.items() if qs}


def _stem(n: int, q: Question) -> list[Block]:
    """Nhãn "Câu n." + đề bài; bảng trong đề thành Table, hàng thiếu ô được bù ô trống."""
    segs = stem_blocks(q) or [{"text": ""}]
    if "table" in segs[0]:  # đề mở đầu bằng bảng: nhãn "Câu n." đứng một dòng riêng
        segs.insert(0, {"text": ""})
    blocks: list[Block] = [Paragraph((Run(f"Câu {n}.", bold=True), Run(" " + segs[0]["text"])), gap=True)]
    for seg in segs[1:]:
        if "table" in seg:
            width = max(map(len, seg["table"]))
            blocks.append(Table(tuple(tuple(r) + ("",) * (width - len(r)) for r in seg["table"])))
        else:
            blocks.append(Paragraph((Run(seg["text"]),)))
    if q.get("figure_svg"):
        blocks.append(Figure(q["figure_svg"], q.get("figure") or ""))
    return blocks


def _answer(type_: QuestionType, q: Question) -> list[Block]:
    """Bản GV: đáp án in đậm rồi lời giải từng bước, ngay dưới câu (như bản xem trước)."""
    if type_ is TF:
        key = "; ".join(f"{k}) {'Đúng' if s['correct'] else 'Sai'}" for k, s in zip(STATEMENT_LETTERS, q["statements"]))
    else:
        key = str(q["answer"])
    label = "Đáp số" if type_ is SA else "Đáp án"
    blocks: list[Block] = [Paragraph((Run(f"{label}: {key}", bold=True),), aside=True)]
    blocks += [
        Paragraph((Run(f"{n}. {step}"),), aside=True)
        for n, step in enumerate(solution_steps(q.get("solution") or ""), start=1)
    ]
    if type_ is TF:
        blocks += [
            Paragraph((Run(f"{k})", bold=True), Run(" " + s["explanation"])), aside=True)
            for k, s in zip(STATEMENT_LETTERS, q["statements"])
            if (s.get("explanation") or "").strip()
        ]
    return blocks


def _questions(parts: dict[QuestionType, list[Question]], teacher: bool) -> list[Block]:
    blocks: list[Block] = []
    for type_, qs in parts.items():
        guide = f"Thí sinh trả lời từ câu 1 đến câu {len(qs)}. {PART_GUIDES[type_]}"
        head = Run(f"PHẦN {PART_OF_TYPE[type_]}. {PART_TITLES[type_]}.", bold=True)
        blocks.append(Paragraph((head, Run(" " + guide, italic=True)), gap=True))
        for n, q in enumerate(qs, start=1):
            blocks += _stem(n, q)
            if type_ is MC:
                options = tuple(math_option(o) for o in q["options"])
                blocks.append(Options(options, option_columns(options)))
            if type_ is TF:
                blocks += [
                    Item((Run(f"{k})", bold=True), Run(" " + s["text"])))
                    for k, s in zip(STATEMENT_LETTERS, q["statements"])
                ]
            if teacher:
                blocks += _answer(type_, q)
    return blocks


def _points(d: Decimal) -> str:
    return format(d.normalize(), "f").replace(".", ",")


def _point_notes(subject_code: str) -> dict[QuestionType, str]:
    """Câu ghi điểm cạnh bảng đáp án, theo thang điểm của môn; môn lạ thì không ghi."""
    try:
        points = get_structure(subject_code).points
    except ValueError:
        return {}
    tf = " · ".join(f"{n} ý: {_points(p)} đ" for n, p in enumerate(TRUE_FALSE_POINTS) if n)
    return {
        MC: f"Mỗi câu trả lời đúng được {_points(points[MC])} điểm.",
        TF: f"Đúng {tf}.",
        SA: f"Mỗi câu trả lời đúng được {_points(points[SA])} điểm.",
    }


def _answer_tables(parts: dict[QuestionType, list[Question]], subject_code: str) -> list[Block]:
    """Bảng đáp án ngang mỗi phần: hàng "Câu 1..n", rồi hàng đáp án (Đúng – Sai: một hàng mỗi ý a–d)."""
    notes = _point_notes(subject_code)
    blocks: list[Block] = [_p("ĐÁP ÁN", bold=True, center=True, gap=True)]
    for type_, qs in parts.items():
        head = ("Câu", *map(str, range(1, len(qs) + 1)))
        if type_ is TF:
            rows = [
                (f"Ý {k})", *(TRUE_FALSE_MARKS[q["statements"][i]["correct"]] for q in qs))
                for i, k in enumerate(STATEMENT_LETTERS)
            ]
        else:
            rows = [("Đáp án" if type_ is MC else "Đáp số", *(str(q["answer"]) for q in qs))]
        note = notes.get(type_)
        runs = (Run(f"Phần {PART_OF_TYPE[type_]}.", bold=True), *([Run(" " + note)] if note else []))
        blocks += [Paragraph(runs, gap=True), Table((head, *rows), center=True, header=True)]
    return blocks


MATRIX_HEADER = ("Phần", "Chủ đề", "Đơn vị kiến thức", "Dạng câu", "Mức độ", "Số câu")
MATRIX_WIDTHS = (1.6, 4.4, 4.8, 3.2, 2.3, 1.7)  # cm, tổng = bề rộng chữ của trang A4 (18 cm)


def _matrix_table(cells: Sequence[Cell]) -> list[Block]:
    """Một hàng mỗi ô theo thứ tự ma trận; Đúng – Sai ghi mức độ từng ý a–d; hàng cuối là tổng số câu."""
    rows = [MATRIX_HEADER]
    for c in cells:
        level = ", ".join(lv.value for lv in c.statement_levels) if c.statement_levels else c.level.value
        rows.append((PART_OF_TYPE[c.type], c.topic, c.unit_label, TYPE_LABELS[c.type], level, str(c.count)))
    rows.append(("Tổng", "", "", "", "", str(sum(c.count for c in cells))))
    return [_p("MA TRẬN ĐỀ", bold=True, center=True, gap=True), Table(tuple(rows), header=True, widths=MATRIX_WIDTHS)]


def build_blocks(
    info: ExamInfo, questions: list[Question], variant: ExportVariant, cells: Sequence[Cell] = ()
) -> list[Block]:
    """Bản HS: chỉ đề. Bản GV: đáp án + lời giải dưới từng câu, bảng đáp án và ma trận đề (khi có `cells`)."""
    teacher = variant is ExportVariant.teacher
    parts = _by_part(questions)
    blocks: list[Block] = [
        Header(info, VARIANT_LABELS[variant], teacher),
        *_questions(parts, teacher),
        _p("------ HẾT ------", bold=True, center=True, gap=True),
    ]
    if teacher:
        blocks += _answer_tables(parts, info.subject_code)
        if cells:
            blocks += _matrix_table(cells)
    return blocks


# ----- Markdown -----


def _runs_md(runs: tuple[Run, ...]) -> str:
    def fmt(r: Run) -> str:
        if r.bold:
            return f"**{r.text}**"
        if not (r.italic and r.text.strip()):
            return r.text
        lead = r.text[: len(r.text) - len(r.text.lstrip())]
        return f"{lead}*{r.text.strip()}*"

    return "".join(fmt(r) for r in runs)


def header_lines(info: ExamInfo) -> list[str]:
    """Các dòng đầu đề, theo thứ tự in: trường, kỳ thi, môn – lớp, thời gian, mã đề."""
    return [
        info.school_name.upper(),
        info.title.upper(),
        f"MÔN: {info.subject_name.upper()} – LỚP {info.grade}",
        f"Thời gian làm bài: {info.duration_minutes} phút, không kể thời gian phát đề",
        *([f"Mã đề: {info.code}"] if info.code else []),
    ]


def to_markdown(blocks: list[Block]) -> str:
    out: list[str] = []
    for block in blocks:
        match block:
            case Header(info, _, teacher):
                school, title, subject, duration, *code = header_lines(info)
                out += [f"**{school}**\n", f"# {title}\n", f"**{subject}**\n", f"*{duration}*\n"]
                out += [f"**{c}**\n" for c in code]
                out.append("Họ, tên thí sinh: ………………………… Số báo danh: …………" + (" **[Bản giáo viên]**" if teacher else "") + "\n")
            case Heading(level, text):
                out.append(f"{'#' * level} {text}\n")
            case Paragraph(runs):
                out.append(_runs_md(runs) + "\n")
            case Item(runs):
                # Dòng ý dính ngay dưới đề bài/dòng trước, như form đề mẫu.
                out[-1] = out[-1].rstrip("\n")
                out.append(f"- {_runs_md(runs)}\n")
            case Options(texts):
                out[-1] = out[-1].rstrip("\n")
                out.append("\n".join(f"- {k}. {t}" for k, t in zip(OPTION_LETTERS, texts)) + "\n")
            case Table(rows):
                lines = ["| " + " | ".join(r) + " |" for r in rows]
                lines.insert(1, "|" + "---|" * len(rows[0]))
                out.append("\n".join(lines) + "\n")
            case Figure(_, caption) if caption:  # markdown không nhúng ảnh; chỉ giữ mô tả chữ
                out.append(f"*Hình: {caption}*\n")
            case PageBreak():
                out.append("---\n")
    return "\n".join(out)
