"""Câu hỏi đã chuẩn hóa → đề cùng bố cục với bản xem trước A4 (markdown và DOCX).

Đầu ra mong muốn:
- Đầu đề: tên trường, tên kỳ thi (tên ma trận), môn – lớp, thời gian GV nhập; DOCX đặt thành bảng hai cột.
- Phần I → II → III, số câu đánh lại từ 1 mỗi phần; phần không có câu thì bỏ.
- Phương án A–D chia 4/2/1 cột theo độ dài, như bản xem trước.
- Bản HS chỉ có đề; bản GV thêm đáp án + lời giải dưới từng câu, bảng đáp án sau "HẾT" và Ma trận đề.
- DOCX có cùng nội dung với markdown, khổ A4.
"""

import io
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from app.domain.cell import Cell
from app.domain.exam_document import ExamInfo, Figure, Options, build_blocks, option_columns, to_markdown
from app.domain.figure import render_svg
from app.domain.question import split_questions
from app.models.enums import ExportVariant, Level, QuestionType
from app.services.docx_export import to_docx
from app.services.rag_mock import SampleRag

SAMPLES = Path(__file__).parents[1] / "fixtures" / "rag" / "ket_qua_mau.json"
MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer
B, H, VD = Level.biet, Level.hieu, Level.van_dung
INFO = ExamInfo("THPT Nguyễn Du", "KTGK - HK1 - 10", "Toán", 10, 90, subject_code="toan")


def questions(*specs: tuple[QuestionType, Level, int]) -> list[dict]:
    rag, out = SampleRag.from_file(SAMPLES), []
    for type_, level, count in specs:
        c = Cell(1, "toan", 10, "Vectơ", None, type_, level, count, (B, B, H, H) if type_ is TF else None)
        out += split_questions(rag.generate(c)[0], c)[0]
    return out


# Cố ý trộn thứ tự: đề phải sắp lại Phần I → II → III.
QUESTIONS = questions((SA, VD, 1), (MC, B, 1), (TF, H, 1), (MC, H, 1))


def student_md() -> str:
    return to_markdown(build_blocks(INFO, QUESTIONS, ExportVariant.student))


def teacher_md() -> str:
    return to_markdown(build_blocks(INFO, QUESTIONS, ExportVariant.teacher))


def test_header_has_school_exam_name_subject_and_duration():
    md = student_md()
    assert md.startswith("**THPT NGUYỄN DU**\n\n# KTGK - HK1 - 10\n\n")
    assert "**MÔN: TOÁN – LỚP 10**" in md
    assert "*Thời gian làm bài: 90 phút, không kể thời gian phát đề*" in md
    assert "Họ, tên thí sinh:" in md and "Bản giáo viên" not in md


def test_parts_in_order_with_numbering_restarting_each_part():
    md = student_md()
    p1 = md.index("**PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn.**")
    p2 = md.index("**PHẦN II. Câu trắc nghiệm đúng sai.**")
    p3 = md.index("**PHẦN III. Câu trắc nghiệm trả lời ngắn.**")
    assert p1 < p2 < p3
    assert "* *Thí sinh trả lời từ câu 1 đến câu 2. Mỗi câu hỏi thí sinh chỉ chọn một phương án.*" in md
    assert md[p1:p2].count("**Câu ") == 2 and "**Câu 2.**" in md[p1:p2]
    assert md[p2:p3].count("**Câu 1.**") == 1
    assert md[p3:].count("**Câu 1.**") == 1
    assert md.rstrip().endswith("**------ HẾT ------**")


def test_options_and_statements_follow_the_form():
    md = student_md()
    assert "**Câu 1.** Cho hình bình hành $ABCD$" in md
    assert "bằng:\n- A. 8\n- B. 7,5\n- C. 6\n- D. 10\n" in md
    assert "\n- **a)** $\\overrightarrow{XY} = \\overrightarrow{ZG}$.\n- **b)** " in md


def test_short_options_share_one_line_longer_ones_split_in_two_or_four_lines():
    assert option_columns(["8", "7,5", "6", "10"]) == 4
    assert option_columns([r"$(-\infty; 0)$", "$(0; 2)$", "x", "y"]) == 4  # lệnh LaTeX tính một ký tự
    assert option_columns(["Hàm số đồng biến trên khoảng", "b", "c", "d"]) == 2
    assert option_columns(["Hàm số nghịch biến trên các khoảng $(-\\infty; 1)$ và $(1; +\\infty)$", "b", "c", "d"]) == 1
    [first, *_] = [b for b in build_blocks(INFO, QUESTIONS, ExportVariant.student) if isinstance(b, Options)]
    assert first == Options(("8", "7,5", "6", "10"), 4)


def test_student_copy_has_no_answers():
    md = student_md()
    assert "ĐÁP ÁN" not in md and "Đáp án:" not in md and "7,07" not in md


def test_teacher_copy_puts_answer_and_steps_under_each_question():
    md = teacher_md()
    assert "Họ, tên thí sinh: ………………………… Số báo danh: ………… **[Bản giáo viên]**" in md
    q1 = md.index("**Câu 1.** Cho hình bình hành")
    assert md.index("- D. 10", q1) < md.index("**Đáp án: B**", q1) < md.index("1. Theo công thức", q1)
    assert "**Đáp án: a) Sai; b) Đúng; c) Sai; d) Sai**" in md
    assert "**a)** $\\overrightarrow{XY}=(4,0)$" in md  # giải thích từng ý đúng/sai
    assert "**Đáp số: 7,07**" in md
    assert md.index("**Đáp số: 7,07**") < md.index("**------ HẾT ------**")


def test_teacher_copy_adds_answer_tables_after_the_end_line():
    md = teacher_md()
    end = md.index("**------ HẾT ------**")
    assert md.index("**ĐÁP ÁN**") > end
    assert "**Phần I.** Mỗi câu trả lời đúng được 0,25 điểm.\n\n| Câu | 1 | 2 |\n|---|---|---|\n| Đáp án | B | D |" in md
    assert "**Phần II.** Đúng 1 ý: 0,1 đ · 2 ý: 0,25 đ · 3 ý: 0,5 đ · 4 ý: 1 đ." in md
    assert "| Câu | 1 |\n|---|---|\n| Ý a) | S |\n| Ý b) | Đ |\n| Ý c) | S |\n| Ý d) | S |" in md
    assert "**Phần III.** Mỗi câu trả lời đúng được 0,5 điểm.\n\n| Câu | 1 |\n|---|---|\n| Đáp số | 7,07 |" in md


def test_point_notes_follow_the_subject_and_are_left_out_for_an_unknown_subject():
    ly = ExamInfo("THPT Nguyễn Du", "KTGK", "Vật lí", 12, 50, subject_code="ly")
    assert "**Phần III.** Mỗi câu trả lời đúng được 0,25 điểm." in to_markdown(
        build_blocks(ly, QUESTIONS, ExportVariant.teacher)
    )
    unknown = ExamInfo("THPT Nguyễn Du", "KTGK", "Toán", 10, 90)
    md = to_markdown(build_blocks(unknown, QUESTIONS, ExportVariant.teacher))
    assert "**Phần I.**\n" in md and "Mỗi câu trả lời đúng" not in md and "Đúng 1 ý" not in md


def test_empty_parts_are_skipped():
    md = to_markdown(build_blocks(INFO, questions((MC, B, 2)), ExportVariant.teacher))
    assert "PHẦN II" not in md and "PHẦN III" not in md
    assert "**Phần II.**" not in md and "**Phần III.**" not in md


def docx_of(variant: ExportVariant) -> Document:
    return Document(io.BytesIO(to_docx(build_blocks(INFO, QUESTIONS, variant))))


def docx_text(variant: ExportVariant) -> tuple[list[str], list[str], int]:
    """(chữ đầu đề, các đoạn thân đề, số bảng không kể bảng đầu đề)."""
    doc = docx_of(variant)
    head = [p.text for cell in doc.tables[0].rows[0].cells for p in cell.paragraphs if p.text]
    return head, [p.text for p in doc.paragraphs], len(doc.tables) - 1


def test_docx_student_copy():
    head, paragraphs, tables = docx_text(ExportVariant.student)
    assert head[0] == "THPT NGUYỄN DU"
    assert head[2:] == ["KTGK - HK1 - 10", "MÔN: TOÁN – LỚP 10", "Thời gian làm bài: 90 phút, không kể thời gian phát đề"]
    assert any(p.startswith("Câu 1. Cho hình bình hành") for p in paragraphs)
    assert "A. 8\tB. 7,5\tC. 6\tD. 10" in paragraphs  # bốn phương án ngắn chung một dòng
    assert tables == 0


def test_docx_is_a4_times_12_with_page_numbers_in_the_footer():
    doc = docx_of(ExportVariant.student)
    section = doc.sections[0]
    assert (round(section.page_width.cm, 1), round(section.page_height.cm, 1)) == (21.0, 29.7)
    assert doc.styles["Normal"].font.name == "Times New Roman" and doc.styles["Normal"].font.size.pt == 12
    footer = section.footer.paragraphs[0]
    assert footer.text.endswith("\tBản học sinh")
    assert [i.text.strip() for i in footer._p.iter(qn("w:instrText"))] == ["PAGE", "NUMPAGES"]
    left = doc.tables[0].rows[0].cells[0]
    assert any("NUMPAGES" in (i.text or "") for i in left._tc.iter(qn("w:instrText")))  # "(Đề thi có NN trang)"


def test_docx_teacher_copy_has_three_answer_tables():
    _, paragraphs, tables = docx_text(ExportVariant.teacher)
    assert "ĐÁP ÁN" in paragraphs and "Đáp án: B" in paragraphs
    assert any(p.endswith("Bản giáo viên ") for p in paragraphs)
    assert tables == 3


CELLS = (
    Cell(1, "toan", 10, "Vectơ", "Tích vô hướng", MC, B, 12),
    Cell(2, "toan", 10, "Vectơ", None, TF, H, 4, (B, B, H, H)),
    Cell(3, "toan", 10, "Hệ thức lượng", None, SA, VD, 6),
)


def test_teacher_copy_ends_with_matrix_table():
    md = to_markdown(build_blocks(INFO, QUESTIONS, ExportVariant.teacher, CELLS))
    assert md.rstrip().endswith(
        "**MA TRẬN ĐỀ**\n\n"
        "| Phần | Chủ đề | Đơn vị kiến thức | Dạng câu | Mức độ | Số câu |\n"
        "|---|---|---|---|---|---|\n"
        "| I | Vectơ | Tích vô hướng | Nhiều lựa chọn | Biết | 12 |\n"
        "| II | Vectơ |  | Đúng – Sai | Biết, Biết, Hiểu, Hiểu | 4 |\n"
        "| III | Hệ thức lượng |  | Trả lời ngắn | Vận dụng | 6 |\n"
        "| Tổng |  |  |  |  | 22 |"
    )
    assert "Ma trận đề" not in to_markdown(build_blocks(INFO, QUESTIONS, ExportVariant.student, CELLS))


def test_question_table_becomes_real_table_block_in_place():
    from app.domain.exam_document import Table

    q = questions((MC, B, 1))[0]
    q["stem"] = "Cho bảng:\n| $x$ | 1 |\n|---|---|\n| $y$ | 2 |\nTìm $y$."
    blocks = build_blocks(INFO, [q], ExportVariant.student)
    i = next(i for i, b in enumerate(blocks) if isinstance(b, Table))
    assert blocks[i] == Table((("$x$", "1"), ("$y$", "2")))
    assert "Cho bảng:" in blocks[i - 1].runs[-1].text
    assert "Tìm $y$." in blocks[i + 1].runs[0].text
    md = to_markdown(blocks)
    assert md.index("Cho bảng:") < md.index("| $x$ | 1 |") < md.index("Tìm $y$.")
    docx = Document(io.BytesIO(to_docx(blocks)))
    assert len(docx.tables) == 2  # bảng đầu đề + bảng trong đề bài
    cell = docx.tables[1].cell(0, 0)
    assert cell.text == ""
    assert cell._tc.xpath(".//m:oMath")


def test_two_markdown_tables_in_stem_both_exported():
    q = questions((MC, B, 1))[0]
    q["stem"] = "A\n| a |\n|---|\n| 1 |\nB\n| c |\n|---|\n| 3 |"
    docx = Document(io.BytesIO(to_docx(build_blocks(INFO, [q], ExportVariant.student))))
    assert len(docx.tables) == 3  # bảng đầu đề + hai bảng trong đề bài


def test_stem_starting_with_table_keeps_question_label():
    q = questions((MC, B, 1))[0]
    q["stem"] = "| a |\n|---|\n| 1 |"
    md = to_markdown(build_blocks(INFO, [q], ExportVariant.student))
    assert md.index("**Câu 1.**") < md.index("| a |")


# ----- hình khối trong đề -----

SPEC = {"solid": "pyramid", "a": 3, "b": 4, "h": 5, "foot": "center"}
SVG = render_svg(SPEC)
CAPTION = "Hình chóp $S.ABCD$ có đáy là hình chữ nhật"


def with_figure_on_first_mc(**extra) -> list[dict]:
    qs = [dict(q) for q in QUESTIONS]
    first = next(q for q in qs if q["type"] == "multiple_choice")
    first.update({"figure_svg": SVG, "figure": CAPTION} | extra)
    return qs


def figures(blocks):
    return [b for b in blocks if isinstance(b, Figure)]


def test_question_with_a_figure_has_one_figure_block_after_its_stem_before_its_options():
    blocks = build_blocks(INFO, with_figure_on_first_mc(), ExportVariant.student)
    [figure] = figures(blocks)
    i = blocks.index(figure)
    assert blocks[i - 1].runs[0].text.startswith("Câu 1.")
    assert isinstance(blocks[i + 1], Options)
    assert figure.svg == SVG and figure.caption == CAPTION


def test_no_figure_block_without_an_svg():
    assert figures(build_blocks(INFO, QUESTIONS, ExportVariant.student)) == []


def test_text_figure_alone_adds_no_figure_block():
    qs = [dict(q, figure=CAPTION) for q in QUESTIONS]
    assert figures(build_blocks(INFO, qs, ExportVariant.student)) == []


def test_figure_comes_after_the_tables_of_the_stem():
    qs = with_figure_on_first_mc(stem="Cho bảng:\n| x | 1 |\n|---|---|\n| y | 2 |\n")
    blocks = build_blocks(INFO, qs, ExportVariant.student)
    [figure] = figures(blocks)
    assert type(blocks[blocks.index(figure) - 1]).__name__ == "Table"


def test_teacher_copy_draws_the_figure_once_not_again_in_the_solutions():
    blocks = build_blocks(INFO, with_figure_on_first_mc(), ExportVariant.teacher)
    assert len(figures(blocks)) == 1


def test_figure_without_caption_has_an_empty_caption():
    [figure] = figures(build_blocks(INFO, with_figure_on_first_mc(figure=None), ExportVariant.student))
    assert figure.caption == ""


def test_markdown_shows_the_caption_not_the_svg():
    md = to_markdown(build_blocks(INFO, with_figure_on_first_mc(), ExportVariant.student))
    assert f"*Hình: {CAPTION}*" in md
    assert "<svg" not in md


def test_markdown_shows_nothing_for_a_figure_without_caption():
    md = to_markdown(build_blocks(INFO, with_figure_on_first_mc(figure=None), ExportVariant.student))
    assert "Hình:" not in md and "<svg" not in md
