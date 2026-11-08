"""Khối nội dung đề (domain/exam_document.py) → file DOCX bằng python-docx.

Bố cục khớp bản xem trước A4 ở trang Xuất đề (frontend ExamExportPage.tsx): khổ A4, Times New Roman
12 pt, đầu đề hai cột, phương án chia cột bằng tab, chân trang "Trang x/y" + phiên bản.

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
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.domain.exam_document import (
    Block,
    Figure,
    Header,
    Heading,
    Item,
    Options,
    PageBreak,
    Paragraph,
    Run,
    Table,
    header_lines,
)
from app.rag.generation.latex import normalize_latex
from app.services.figure_png import svg_to_png

FONT = "Times New Roman"
FIGURE_WIDTH_CM = 8
# Khổ A4 và lề khớp bản xem trước (794×1123 px, lề ngang 56 px ≈ 1,5 cm, lề trên 60 px ≈ 1,6 cm).
PAGE_W_CM, PAGE_H_CM = 21.0, 29.7
MARGIN_X_CM, MARGIN_TOP_CM, MARGIN_BOTTOM_CM = 1.5, 1.6, 2.0
TEXT_W_CM = PAGE_W_CM - 2 * MARGIN_X_CM
GAP = Pt(6)  # khoảng cách giữa các câu (pb-2 của bản xem trước)
SMALL = Pt(11.5)  # chữ đầu đề, đáp án và bảng đáp án (15 px của bản xem trước)
HEAD_LEFT = 0.4  # cột trái đầu đề (tên trường) chiếm 2/5, cột phải 3/5, như bản xem trước
# Tab dừng của style Footer mặc định (khổ Letter: giữa 3,25", phải 6,5") phải xoá để tab phải về sát lề A4.
FOOTER_STYLE_TABS = (Cm(8.255), Cm(16.51))
MATH_RE = re.compile(r"\$\$(.+?)\$\$|\$([^$]+?)\$", re.DOTALL)

log = logging.getLogger(__name__)

Equations = dict[str, object]  # LaTeX → phần tử m:oMath; thiếu khoá = giữ dạng chữ


def split_math(text: str) -> list[tuple[str, bool]]:
    """Chuỗi → các đoạn (chữ, False) / (LaTeX không kèm dấu $, True), giữ thứ tự."""
    text = _clean(text)  # BUG-004: exams stored before the fix still export clean formulas
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
            case Options(options):
                texts += list(options)
            case Header(info):
                texts += header_lines(info)
            case Table(rows):
                texts += [cell for row in rows for cell in row]
    return texts


def _clean(text: str) -> str:
    """Mọi chữ ghi vào DOCX đi qua đây: ký tự điều khiển XML không hợp lệ (dán từ Word, NUL...) làm python-docx báo lỗi."""
    return normalize_latex(text)


def _add_text(paragraph, text: str, bold: bool, equations: Equations, italic: bool = False) -> None:
    for part, is_math in split_math(text):
        if is_math and part in equations:
            paragraph._p.append(copy.deepcopy(equations[part]))
            continue
        run = paragraph.add_run(f"${part}$" if is_math else part)
        run.bold = bold
        if italic:
            run.italic = True


def _add_runs(paragraph, runs: tuple[Run, ...], equations: Equations) -> None:
    for r in runs:
        _add_text(paragraph, r.text, r.bold, equations, r.italic)


def _add_figure(doc, figure: Figure) -> None:
    """Hình khối nhúng dạng PNG ở giữa trang; không đổi được ảnh (kể cả thiếu libcairo) thì giữ mô tả chữ, đề vẫn xuất được."""
    try:
        png = svg_to_png(figure.svg)
    except Exception as e:  # noqa: BLE001 – FigureError hay OSError của Cairo: đều chỉ làm mất hình, không làm mất đề
        log.warning("Không nhúng được hình, giữ mô tả chữ: %s", e)
        if figure.caption:
            doc.add_paragraph(_clean(figure.caption))
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(io.BytesIO(png), width=Cm(FIGURE_WIDTH_CM))


# ----- chi tiết định dạng Word (OOXML) -----

# Phần tử con đứng sau w:pBdr trong w:pPr / sau w:bdr trong w:rPr theo schema; chèn sai thứ tự Word báo file hỏng.
_PBDR_AFTER = (
    "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct", "w:topLinePunct",
    "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind",
    "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment",
    "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
)  # fmt: skip
_BDR_AFTER = (
    "w:shd", "w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang", "w:eastAsianLayout", "w:specVanish",
    "w:oMath",
)  # fmt: skip


def _border(tag: str, color: str, size: int, space: int):
    el = OxmlElement(tag)
    for k, v in (("w:val", "single"), ("w:sz", str(size)), ("w:space", str(space)), ("w:color", color)):
        el.set(qn(k), v)
    return el


def _paragraph_border(paragraph, side: str, color: str = "999999", size: int = 12, space: int = 8) -> None:
    """Kẻ một cạnh của đoạn: vạch trái của lời giải, gạch dưới tên trường, vạch trên chân trang."""
    ppr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bdr.append(_border(f"w:{side}", color, size, space))
    ppr.insert_element_before(bdr, *_PBDR_AFTER)


def _boxed(run) -> None:
    """Khung quanh chữ, như nhãn "Bản giáo viên" ở đầu đề."""
    rpr = run._r.get_or_add_rPr()
    rpr.insert_element_before(_border("w:bdr", "111111", 6, 2), *_BDR_AFTER)


def _field(paragraph, instr: str, placeholder: str) -> None:
    """Trường Word tính lại khi dàn trang (PAGE, NUMPAGES): số trang hiện tại / tổng số trang."""
    for kind in ("begin", "instr", "separate", "text", "end"):
        run = paragraph.add_run(placeholder if kind == "text" else None)
        if kind == "instr":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = f" {instr} "
        elif kind != "text":
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            continue
        run._r.append(el)


def _style(paragraph, size=None, italic: bool = False, center: bool = False) -> None:
    for run in paragraph.runs:
        if size is not None:
            run.font.size = size
        if italic:
            run.italic = True
    if center:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _add_header(doc, block: Header, equations: Equations) -> None:
    """Đầu đề hai cột không kẻ khung như bản xem trước; "(Đề thi có NN trang)" là trường NUMPAGES."""
    school, title, subject, duration, *code = header_lines(block.info)
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    left, right = table.rows[0].cells
    left.width, right.width = Cm(TEXT_W_CM * HEAD_LEFT), Cm(TEXT_W_CM * (1 - HEAD_LEFT))

    p = left.paragraphs[0]
    _add_text(p, school if block.info.school_name.strip() else "TRƯỜNG ……………………", True, equations)
    _style(p, SMALL, center=True)
    rule = left.add_paragraph()  # gạch ngắn dưới tên trường
    rule.paragraph_format.left_indent = rule.paragraph_format.right_indent = Cm(TEXT_W_CM * HEAD_LEFT / 2 - 1.3)
    rule.paragraph_format.space_after = Pt(4)
    rule.add_run().font.size = Pt(2)
    _paragraph_border(rule, "bottom", "111111", 6, 1)
    p = left.add_paragraph()
    p.add_run("(Đề thi có ")
    _field(p, 'NUMPAGES \\# "00"', "01")
    p.add_run(" trang)")
    _style(p, SMALL, italic=True, center=True)

    lines = [(title, True, False), (subject, True, False), (duration, False, True)] + [(c, True, False) for c in code]
    for i, (text, bold, italic) in enumerate(lines):
        p = right.paragraphs[0] if i == 0 else right.add_paragraph()
        _add_text(p, text, bold, equations, italic)
        _style(p, SMALL, center=True)
        if i == 3:  # mã đề
            p.paragraph_format.space_before = Pt(3)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(TEXT_W_CM), WD_TAB_ALIGNMENT.RIGHT)
    p.add_run("Họ, tên thí sinh: ………………………………… Số báo danh: …………")
    if block.teacher:
        p.add_run("\t")
        label = p.add_run(" Bản giáo viên ")
        label.bold = True
        _boxed(label)


def _add_footer(doc, label: str) -> None:
    """Chân trang: "Trang x/y" bên trái, phiên bản (học sinh/giáo viên) bên phải, vạch kẻ trên."""
    p = doc.sections[0].footer.paragraphs[0]
    for pos in FOOTER_STYLE_TABS:
        p.paragraph_format.tab_stops.add_tab_stop(pos, WD_TAB_ALIGNMENT.CLEAR)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(TEXT_W_CM), WD_TAB_ALIGNMENT.RIGHT)
    p.add_run("Trang ")
    _field(p, "PAGE", "1")
    p.add_run("/")
    _field(p, "NUMPAGES", "1")
    p.add_run("\t" + label)
    _paragraph_border(p, "top", "CCCCCC", 6, 4)
    for run in p.runs:
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


def _add_options(doc, block: Options, equations: Equations) -> None:
    """Phương án chia cột bằng tab dừng: 4 cột một dòng, 2 cột hai dòng, 1 cột bốn dòng; "A." in đậm."""
    step = TEXT_W_CM / block.cols
    for start in range(0, len(block.texts), block.cols):
        p = doc.add_paragraph()
        for k in range(1, block.cols):
            p.paragraph_format.tab_stops.add_tab_stop(Cm(step * k))
        for j, text in enumerate(block.texts[start : start + block.cols]):
            if j:
                p.add_run("\t")
            p.add_run(f"{'ABCD'[start + j]}. ").bold = True
            _add_text(p, text, False, equations)


def _page_setup(doc) -> None:
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(PAGE_W_CM), Cm(PAGE_H_CM)
    section.left_margin = section.right_margin = Cm(MARGIN_X_CM)
    section.top_margin, section.bottom_margin = Cm(MARGIN_TOP_CM), Cm(MARGIN_BOTTOM_CM)
    section.footer_distance = Cm(0.8)
    style = doc.styles["Normal"]
    style.font.name = FONT
    style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    style.font.size = Pt(12)
    fmt = style.paragraph_format
    fmt.space_before, fmt.space_after, fmt.line_spacing = Pt(0), Pt(0), 1.15


def to_docx(blocks: list[Block]) -> bytes:
    formulas = [part for text in _texts(blocks) for part, is_math in split_math(text) if is_math]
    equations = _equations(list(dict.fromkeys(formulas)))
    doc = Document()
    _page_setup(doc)
    for block in blocks:
        match block:
            case Header():
                _add_header(doc, block, equations)
                _add_footer(doc, block.label)
            case Heading(level, text):
                p = doc.add_paragraph()
                p.add_run(_clean(text)).bold = True
                p.paragraph_format.space_before = GAP
                _style(p, center=level == 1)
            case Paragraph(runs, center, gap, aside):
                p = doc.add_paragraph()
                _add_runs(p, runs, equations)
                if center:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if gap:  # mở đầu câu / phần / bảng đáp án: không đứng một mình cuối trang
                    p.paragraph_format.space_before = GAP
                    p.paragraph_format.keep_with_next = True
                if aside:
                    p.paragraph_format.left_indent = Cm(0.4)
                    _paragraph_border(p, "left")
                    _style(p, SMALL)
            case Item(runs):
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.25)
                _add_runs(p, runs, equations)
            case Options():
                _add_options(doc, block, equations)
            case Table(rows, center, header, widths):
                table = doc.add_table(rows=len(rows), cols=len(rows[0]))
                table.style = "Table Grid"
                if widths:
                    table.autofit = False
                for r, row in enumerate(rows):
                    for c, text in enumerate(row):
                        cell = table.cell(r, c)
                        if widths:
                            cell.width = Cm(widths[c])
                        p = cell.paragraphs[0]
                        _add_text(p, text, header and r == 0, equations)
                        if header:  # bảng đáp án / ma trận: chữ 15 px như bản xem trước
                            _style(p, SMALL)
                        if center:
                            _style(p, SMALL, center=True)
                            # bảng đáp án ngắn: không tách sang hai trang
                            p.paragraph_format.keep_with_next = r < len(rows) - 1
                doc.add_paragraph()
            case Figure():
                _add_figure(doc, block)
            case PageBreak():
                doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
