"""Khối nội dung đề (domain/exam_document.py) → file DOCX bằng python-docx.

LaTeX `$...$` / `$$...$$` thành công thức Word (OMML): mọi công thức của đề gửi Pandoc một lần,
lấy `m:oMath` ra chèn vào đúng chỗ. Công thức Pandoc không đọc được, hoặc Pandoc lỗi, thì giữ
nguyên dạng chữ để đề vẫn xuất được. Hình khối (Figure) nhúng dạng PNG; không đổi được thì giữ mô tả chữ.
"""

import copy
import io
import logging
import re
import tempfile
import zipfile
from pathlib import Path

import pypandoc
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from app.domain.exam_document import (
    Block,
    Figure,
    Heading,
    Item,
    PageBreak,
    Paragraph,
    Run,
    Table,
)
from app.rag.generation.latex import normalize_latex
from app.services.figure_png import svg_to_png

FONT = "Times New Roman"
FIGURE_WIDTH_CM = 8
MATH_RE = re.compile(r"\$\$(.+?)\$\$|\$([^$]+?)\$", re.DOTALL)

log = logging.getLogger(__name__)

Equations = dict[str, object]  # LaTeX → phần tử m:oMath; thiếu khoá = giữ dạng chữ


def split_math(text: str) -> list[tuple[str, bool]]:
    """Chuỗi → các đoạn (chữ, False) / (LaTeX không kèm dấu $, True), giữ thứ tự."""
    text = normalize_latex(text)  # BUG-004: exams stored before the fix still export clean formulas
    parts: list[tuple[str, bool]] = []
    pos = 0
    for m in MATH_RE.finditer(text):
        if m.start() > pos:
            parts.append((text[pos : m.start()], False))
        parts.append(((m[1] or m[2]).strip(), True))
        pos = m.end()
    if pos < len(text):
        parts.append((text[pos:], False))
    return parts


def _pandoc_docx(markdown: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "math.docx"
        pypandoc.convert_text(markdown, "docx", format="markdown", outputfile=str(out), extra_args=["--quiet"])
        return out.read_bytes()


def _equations(formulas: list[str]) -> Equations:
    """Mỗi công thức một đoạn trong một lần gọi Pandoc; đoạn nào không có m:oMath thì bỏ qua.

    Khoảng trắng trong công thức gộp lại để dòng trống không tách đoạn; số đoạn trả về lệch
    số công thức thì không ghép (tránh chèn nhầm chỗ), cả đề giữ dạng chữ.
    """
    if not formulas:
        return {}
    try:
        data = _pandoc_docx("\n\n".join(f"${' '.join(f.split())}$" for f in formulas))
    except (OSError, RuntimeError) as e:
        log.warning("Pandoc lỗi, công thức giữ dạng chữ: %s", e)
        return {}
    body = parse_xml(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml")).find(qn("w:body"))
    paragraphs = list(body.iterchildren(qn("w:p")))
    if len(paragraphs) != len(formulas):
        log.warning("Pandoc trả %d đoạn cho %d công thức, giữ dạng chữ", len(paragraphs), len(formulas))
        return {}
    equations: Equations = {}
    for tex, p in zip(formulas, paragraphs):
        if (omath := next(p.iter(qn("m:oMath")), None)) is not None:
            equations[tex] = omath
    return equations


def _texts(blocks: list[Block]) -> list[str]:
    texts: list[str] = []
    for block in blocks:
        match block:
            case Paragraph(runs) | Item(runs):
                texts += [r.text for r in runs]
            case Table(rows):
                texts += [cell for row in rows for cell in row]
    return texts


def _add_text(paragraph, text: str, bold: bool, equations: Equations) -> None:
    for part, is_math in split_math(text):
        if not is_math:
            paragraph.add_run(part).bold = bold
        elif part in equations:
            paragraph._p.append(copy.deepcopy(equations[part]))
        else:
            paragraph.add_run(f"${part}$").bold = bold


def _add_runs(paragraph, runs: tuple[Run, ...], equations: Equations) -> None:
    for r in runs:
        _add_text(paragraph, r.text, r.bold, equations)


def _add_figure(doc, figure: Figure) -> None:
    """Hình khối nhúng dạng PNG ở giữa trang; không đổi được ảnh (kể cả thiếu libcairo) thì giữ mô tả chữ, đề vẫn xuất được."""
    try:
        png = svg_to_png(figure.svg)
    except Exception as e:  # noqa: BLE001 – FigureError hay OSError của Cairo: đều chỉ làm mất hình, không làm mất đề
        log.warning("Không nhúng được hình, giữ mô tả chữ: %s", e)
        if figure.caption:
            doc.add_paragraph(figure.caption)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(io.BytesIO(png), width=Cm(FIGURE_WIDTH_CM))


def to_docx(blocks: list[Block]) -> bytes:
    formulas = [part for text in _texts(blocks) for part, is_math in split_math(text) if is_math]
    equations = _equations(list(dict.fromkeys(formulas)))
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = FONT
    style.font.size = Pt(12)
    for block in blocks:
        match block:
            case Heading(level, text):
                h = doc.add_heading(text, level=level)
                if level == 1:
                    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            case Paragraph(runs, center):
                p = doc.add_paragraph()
                _add_runs(p, runs, equations)
                if center:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            case Item(runs):
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.75)
                _add_runs(p, runs, equations)
            case Table(rows):
                table = doc.add_table(rows=len(rows), cols=len(rows[0]))
                table.style = "Table Grid"
                for r, row in enumerate(rows):
                    for c, text in enumerate(row):
                        _add_text(table.cell(r, c).paragraphs[0], text, False, equations)
                doc.add_paragraph()
            case Figure():
                _add_figure(doc, block)
            case PageBreak():
                doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
