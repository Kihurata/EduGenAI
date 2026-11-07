"""Công thức LaTeX trong đề → công thức Word (OMML) khi xuất DOCX (F-06).

Đầu ra mong muốn:
- `$...$` và `$$...$$` thành công thức Word sửa được (`m:oMath`), không còn dấu `$` trong chữ.
- Chữ quanh công thức giữ nguyên, kể cả in đậm; công thức trong bảng cũng đổi.
- LaTeX hỏng thì giữ nguyên dạng chữ `$...$`; Pandoc lỗi thì cả đề giữ dạng chữ, vẫn xuất được.
- Đề không có công thức thì không gọi Pandoc.
"""

import io

import pytest
from docx import Document
from docx.oxml.ns import qn

from app.domain.exam_document import Paragraph, Run, Table
from app.services import docx_export
from app.services.docx_export import split_math, to_docx

OMATH = qn("m:oMath")


def paragraphs(blocks) -> list:
    return Document(io.BytesIO(to_docx(blocks))).paragraphs


def maths(element) -> list:
    return list(element.iter(OMATH))


def test_split_math_keeps_text_and_formulas_in_order():
    assert split_math(r"Cho $x^2$ và $$\int_0^1 x\,dx$$.") == [
        ("Cho ", False), ("x^2", True), (" và ", False), (r"\int_0^1 x\,dx", True), (".", False),
    ]  # fmt: skip
    assert split_math("Không có công thức") == [("Không có công thức", False)]
    assert split_math("Giá 5$ thôi") == [("Giá 5$ thôi", False)]


def test_inline_formulas_become_word_equations():
    [p] = paragraphs([Paragraph((Run(r"Cho $x^2$ và $|\overrightarrow{AB}| = 5$."),))])
    assert len(maths(p._p)) == 2
    assert "$" not in p.text
    assert p.text == "Cho  và ."


def test_display_formula_is_inlined_as_one_equation():
    [p] = paragraphs([Paragraph((Run(r"Tính $$\int_0^1 x\,dx$$"),))])
    assert len(maths(p._p)) == 1
    assert not list(p._p.iter(qn("m:oMathPara")))


def test_bold_label_stays_bold_next_to_a_formula():
    [p] = paragraphs([Paragraph((Run("Câu 1.", bold=True), Run(r" Tính $\frac{1}{2}$")))])
    assert p.runs[0].text == "Câu 1."
    assert p.runs[0].bold
    assert len(maths(p._p)) == 1


def test_formula_in_answer_table_cell():
    doc = Document(io.BytesIO(to_docx([Table((("Phần III", "1"), ("Đáp số", r"$\sqrt{2}$")))])))
    cell = doc.tables[0].cell(1, 1)
    assert len(maths(cell._tc)) == 1
    assert cell.text == ""


def test_broken_latex_stays_as_text():
    [p] = paragraphs([Paragraph((Run(r"Sai $\frac{1$ nhưng $x$ đúng"),))])
    assert len(maths(p._p)) == 1
    assert p.text == r"Sai $\frac{1$ nhưng  đúng"


def test_formula_with_blank_line_does_not_shift_later_formulas():
    [p] = paragraphs([Paragraph((Run("$$a\n\nb$$ rồi $x^2$ rồi $\\sqrt{3}$"),))])
    assert len(maths(p._p)) == 3
    assert "".join(t.text for t in p._p.iter(qn("m:t"))) == "abx23"  # công thức không giữ khoảng trắng


def test_pandoc_paragraph_count_mismatch_keeps_text(monkeypatch):
    real = docx_export._pandoc_docx
    monkeypatch.setattr(docx_export, "_pandoc_docx", lambda md: real(md + "\n\nthêm một đoạn"))
    [p] = paragraphs([Paragraph((Run("Cho $x^2$"),))])
    assert p.text == "Cho $x^2$"


def test_no_formula_does_not_call_pandoc(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("không được gọi Pandoc")

    monkeypatch.setattr(docx_export, "_pandoc_docx", boom)
    [p] = paragraphs([Paragraph((Run("Chỉ có chữ"),))])
    assert p.text == "Chỉ có chữ"


def test_pandoc_failure_keeps_every_formula_as_text(monkeypatch):
    def broken(markdown: str) -> bytes:
        raise OSError("không chạy được pandoc")

    monkeypatch.setattr(docx_export, "_pandoc_docx", broken)
    [p] = paragraphs([Paragraph((Run(r"Cho $x^2$"),))])
    assert p.text == "Cho $x^2$"
    assert not maths(p._p)


@pytest.mark.parametrize("tex", [r"\overrightarrow{AB}\cdot\overrightarrow{AD}", r"\widehat{BAD}=60^{\circ}"])
def test_sample_formulas_convert(tex):
    [p] = paragraphs([Paragraph((Run(f"${tex}$"),))])
    assert len(maths(p._p)) == 1


def test_BUG_004_stored_questions_with_broken_latex_export_clean_formulas():
    """Exams already in the DB (e81f6617) were generated before the fix; the export normalises them too."""
    assert split_math(r"Với $1 \≤ x \≤ 120$ thì $x \tiff 2$.") == [
        ("Với ", False), (r"1 \le x \le 120", True), (" thì ", False), (r"x \iff 2", True), (".", False)]
