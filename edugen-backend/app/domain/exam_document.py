"""Câu hỏi đã chuẩn hóa → nội dung đề theo form edugen-lab/data/de_01.md.

Đề dựng thành danh sách khối (tiêu đề, đoạn, dòng phương án, bảng) rồi mới in ra markdown
hoặc DOCX (services/docx_export.py), nên hai định dạng luôn cùng nội dung. Số "Câu n" đánh
lại từ 1 trong mỗi phần; LaTeX $...$ giữ nguyên.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.cell import Cell
from app.domain.exam_structure import PART_OF_TYPE, TYPE_OF_PART
from app.domain.matrix_reader import TYPE_LABELS
from app.domain.question import OPTION_LETTERS, TRUE_FALSE_MARKS, Question, stem_blocks
from app.models.enums import ExportVariant, QuestionType

MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer

PART_TITLES = {
    MC: "Câu trắc nghiệm nhiều phương án lựa chọn",
    TF: "Câu trắc nghiệm đúng sai",
    SA: "Câu trắc nghiệm trả lời ngắn",
}
PART_GUIDES = {
    MC: "Mỗi câu thí sinh chỉ chọn một phương án.",
    TF: "Trong mỗi ý a), b), c), d) ở mỗi câu, thí sinh chọn đúng hoặc sai.",
    SA: "",
}
STATEMENT_LETTERS = "abcd"


@dataclass(frozen=True)
class ExamInfo:
    school_name: str  # schools.name
    title: str  # tên kỳ thi = "Tên ma trận"
    subject_name: str
    grade: int
    duration_minutes: int  # GV nhập


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool = False


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class Paragraph:
    runs: tuple[Run, ...]
    center: bool = False


@dataclass(frozen=True)
class Item:
    """Dòng phương án/ý ("- A. …") hoặc dòng lời giải."""

    runs: tuple[Run, ...]


@dataclass(frozen=True)
class Table:
    rows: tuple[tuple[str, ...], ...]  # hàng đầu là header


@dataclass(frozen=True)
class PageBreak:
    pass


Block = Heading | Paragraph | Item | Table | PageBreak


def _p(text: str, bold: bool = False, center: bool = False) -> Paragraph:
    return Paragraph((Run(text, bold),), center)


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _by_part(questions: list[Question]) -> dict[QuestionType, list[Question]]:
    """Gom câu theo phần, giữ thứ tự trong phần; bỏ phần không có câu."""
    parts = {t: [q for q in questions if q["type"] == t.value] for t in TYPE_OF_PART.values()}
    return {t: qs for t, qs in parts.items() if qs}


def _stem(n: int, q: Question) -> list[Block]:
    """Nhãn "Câu n." + đề bài; bảng trong đề thành Table, hàng thiếu ô được bù ô trống."""
    segs = stem_blocks(q) or [{"text": ""}]
    if "table" in segs[0]:  # đề mở đầu bằng bảng: nhãn "Câu n." đứng một dòng riêng
        segs.insert(0, {"text": ""})
    blocks: list[Block] = [Paragraph((Run(f"Câu {n}.", bold=True), Run(" " + segs[0]["text"])))]
    for seg in segs[1:]:
        if "table" in seg:
            width = max(map(len, seg["table"]))
            blocks.append(Table(tuple(tuple(r) + ("",) * (width - len(r)) for r in seg["table"])))
        else:
            blocks.append(Paragraph((Run(seg["text"]),)))
    return blocks


def _questions(parts: dict[QuestionType, list[Question]]) -> list[Block]:
    blocks: list[Block] = []
    for type_, qs in parts.items():
        guide = f"Thí sinh trả lời từ câu 1 đến câu {len(qs)}. {PART_GUIDES[type_]}".strip()
        blocks += [Heading(2, f"PHẦN {PART_OF_TYPE[type_]}. {PART_TITLES[type_]}"), _p(guide)]
        for n, q in enumerate(qs, start=1):
            blocks += _stem(n, q)
            if type_ is MC:
                blocks += [Item((Run(f"{k}. {o}"),)) for k, o in zip(OPTION_LETTERS, q["options"])]
            if type_ is TF:
                blocks += [
                    Item((Run(f"{k}) {s['text']}"),))
                    for k, s in zip(STATEMENT_LETTERS, q["statements"])
                ]
    return blocks


def _answer_tables(parts: dict[QuestionType, list[Question]]) -> list[Block]:
    blocks: list[Block] = []
    for type_, qs in parts.items():
        part = f"Phần {PART_OF_TYPE[type_]}"
        if type_ is TF:
            rows = [(part, *STATEMENT_LETTERS)] + [
                (f"Câu {n}", *(TRUE_FALSE_MARKS[s["correct"]] for s in q["statements"]))
                for n, q in enumerate(qs, start=1)
            ]
        else:
            label = "Đáp án" if type_ is MC else "Đáp số"
            rows = [(part, *map(str, range(1, len(qs) + 1))), (label, *(q["answer"] for q in qs))]
        blocks.append(Table(tuple(rows)))
    return blocks


def _true_false_solution(q: Question) -> str:
    if not all(s["explanation"].strip() for s in q["statements"]):
        return q["solution"]
    return " ".join(
        f"{k}) {'Đúng' if s['correct'] else 'Sai'}: {s['explanation']}"
        for k, s in zip(STATEMENT_LETTERS, q["statements"])
    )


def _solutions(parts: dict[QuestionType, list[Question]]) -> list[Block]:
    blocks: list[Block] = [Heading(2, "Lời giải tóm tắt")]
    for type_, qs in parts.items():
        blocks.append(Heading(3, f"Phần {PART_OF_TYPE[type_]}"))
        for n, q in enumerate(qs, start=1):
            label = f"Câu {n}." if type_ is TF else f"Câu {n} ({q['answer']})."
            text = _true_false_solution(q) if type_ is TF else q["solution"]
            blocks.append(Item((Run(label, bold=True), Run(" " + _one_line(text)))))
    return blocks


MATRIX_HEADER = ("Phần", "Chủ đề", "Đơn vị kiến thức", "Dạng câu", "Mức độ", "Số câu")


def _matrix_table(cells: Sequence[Cell]) -> list[Block]:
    """Một hàng mỗi ô theo thứ tự ma trận; Đúng – Sai ghi mức độ từng ý a–d; hàng cuối là tổng số câu."""
    rows = [MATRIX_HEADER]
    for c in cells:
        level = ", ".join(lv.value for lv in c.statement_levels) if c.statement_levels else c.level.value
        rows.append((PART_OF_TYPE[c.type], c.topic, c.unit_label, TYPE_LABELS[c.type], level, str(c.count)))
    rows.append(("Tổng", "", "", "", "", str(sum(c.count for c in cells))))
    return [Heading(2, "Ma trận đề"), Table(tuple(rows))]


def build_blocks(
    info: ExamInfo, questions: list[Question], variant: ExportVariant, cells: Sequence[Cell] = ()
) -> list[Block]:
    """Bản HS: chỉ đề. Bản GV: đề + bảng đáp án + lời giải tóm tắt + ma trận đề (khi có `cells`)."""
    parts = _by_part(questions)
    blocks: list[Block] = [
        _p(info.school_name.upper(), bold=True, center=True),
        Heading(1, info.title),
        _p(f"Môn: {info.subject_name} – Lớp {info.grade}", center=True),
        _p(f"Thời gian làm bài: {info.duration_minutes} phút (không kể thời gian phát đề)", center=True),
        *_questions(parts),
        _p("HẾT", center=True),
    ]
    if variant is ExportVariant.teacher:
        blocks += [
            PageBreak(),
            Heading(1, "ĐÁP ÁN VÀ LỜI GIẢI"),
            Heading(2, "Bảng đáp án"),
            *_answer_tables(parts),
            *_solutions(parts),
        ]
        if cells:
            blocks += _matrix_table(cells)
    return blocks


# ----- Markdown -----


def _runs_md(runs: tuple[Run, ...]) -> str:
    return "".join(f"**{r.text}**" if r.bold else r.text for r in runs)


def to_markdown(blocks: list[Block]) -> str:
    out: list[str] = []
    for block in blocks:
        match block:
            case Heading(level, text):
                out.append(f"{'#' * level} {text}\n")
            case Paragraph(runs):
                out.append(_runs_md(runs) + "\n")
            case Item(runs):
                # Dòng phương án dính ngay dưới đề bài/dòng trước, như form đề mẫu.
                out[-1] = out[-1].rstrip("\n")
                out.append(f"- {_runs_md(runs)}\n")
            case Table(rows):
                lines = ["| " + " | ".join(r) + " |" for r in rows]
                lines.insert(1, "|" + "---|" * len(rows[0]))
                out.append("\n".join(lines) + "\n")
            case PageBreak():
                out.append("---\n")
    return "\n".join(out)
