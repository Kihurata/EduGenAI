"""Câu hỏi đã chuẩn hóa → đề theo form edugen-lab/data/de_01.md (markdown và DOCX).

Đầu ra mong muốn:
- Đầu đề: tên trường, tên kỳ thi (tên ma trận), môn – lớp, thời gian GV nhập.
- Phần I → II → III, số câu đánh lại từ 1 mỗi phần; phần không có câu thì bỏ.
- Bản HS chỉ có đề; bản GV thêm Bảng đáp án, Lời giải tóm tắt và Ma trận đề (một hàng mỗi ô, hàng tổng).
- DOCX có cùng nội dung với markdown.
"""

import io
from pathlib import Path

from docx import Document

from app.domain.cell import Cell
from app.domain.exam_document import ExamInfo, build_blocks, to_markdown
from app.domain.question import split_questions
from app.models.enums import ExportVariant, Level, QuestionType
from app.services.docx_export import to_docx
from app.services.rag_mock import SampleRag

SAMPLES = Path(__file__).parents[1] / "fixtures" / "rag" / "ket_qua_mau.json"
MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer
B, H, VD = Level.biet, Level.hieu, Level.van_dung
INFO = ExamInfo("THPT Nguyễn Du", "KTGK - HK1 - 10", "Toán", 10, 90)


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
    assert "Môn: Toán – Lớp 10" in md
    assert "Thời gian làm bài: 90 phút (không kể thời gian phát đề)" in md


def test_parts_in_order_with_numbering_restarting_each_part():
    md = student_md()
    p1 = md.index("## PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn")
    p2 = md.index("## PHẦN II. Câu trắc nghiệm đúng sai")
    p3 = md.index("## PHẦN III. Câu trắc nghiệm trả lời ngắn")
    assert p1 < p2 < p3
    assert "Thí sinh trả lời từ câu 1 đến câu 2. Mỗi câu thí sinh chỉ chọn một phương án." in md
    assert md[p1:p2].count("**Câu ") == 2 and "**Câu 2.**" in md[p1:p2]
    assert md[p2:p3].count("**Câu 1.**") == 1
    assert md[p3:].count("**Câu 1.**") == 1
    assert md.rstrip().endswith("HẾT")


def test_options_and_statements_follow_the_form():
    md = student_md()
    assert "**Câu 1.** Cho hình bình hành $ABCD$" in md
    assert "bằng:\n- A. 8\n- B. 7,5\n- C. 6\n- D. 10\n" in md
    assert "\n- a) $\\overrightarrow{XY} = \\overrightarrow{ZG}$.\n- b) " in md


def test_student_copy_has_no_answers():
    md = student_md()
    assert "Bảng đáp án" not in md and "Lời giải" not in md and "7,07" not in md


def test_teacher_copy_adds_answer_tables_and_solutions():
    md = teacher_md()
    assert md.startswith(student_md().rstrip())
    assert "# ĐÁP ÁN VÀ LỜI GIẢI" in md
    assert "| Phần I | 1 | 2 |\n|---|---|---|\n| Đáp án | B | " in md
    assert "| Phần II | a | b | c | d |\n|---|---|---|---|---|\n| Câu 1 | S | Đ | S | S |" in md
    assert "| Phần III | 1 |\n|---|---|\n| Đáp số | 7,07 |" in md
    assert "## Lời giải tóm tắt" in md
    assert "- **Câu 1 (B).** Theo công thức" in md
    assert "- **Câu 1.** a) Sai: $\\overrightarrow{XY}=(4,0)$" in md
    assert "- **Câu 1 (7,07).** Áp dụng định lý cosin" in md


def test_empty_parts_are_skipped():
    md = to_markdown(build_blocks(INFO, questions((MC, B, 2)), ExportVariant.teacher))
    assert "PHẦN II" not in md and "PHẦN III" not in md
    assert "| Phần II" not in md and "### Phần III" not in md


def docx_text(variant: ExportVariant) -> tuple[list[str], int]:
    doc = Document(io.BytesIO(to_docx(build_blocks(INFO, QUESTIONS, variant))))
    return [p.text for p in doc.paragraphs], len(doc.tables)


def test_docx_student_copy():
    paragraphs, tables = docx_text(ExportVariant.student)
    assert paragraphs[0] == "THPT NGUYỄN DU"
    assert "KTGK - HK1 - 10" in paragraphs
    assert any(p.startswith("Câu 1. Cho hình bình hành") for p in paragraphs)
    assert "A. 8" in paragraphs
    assert tables == 0


def test_docx_teacher_copy_has_three_answer_tables():
    paragraphs, tables = docx_text(ExportVariant.teacher)
    assert "ĐÁP ÁN VÀ LỜI GIẢI" in paragraphs
    assert tables == 3


CELLS = (
    Cell(1, "toan", 10, "Vectơ", "Tích vô hướng", MC, B, 12),
    Cell(2, "toan", 10, "Vectơ", None, TF, H, 4, (B, B, H, H)),
    Cell(3, "toan", 10, "Hệ thức lượng", None, SA, VD, 6),
)


def test_teacher_copy_ends_with_matrix_table():
    md = to_markdown(build_blocks(INFO, QUESTIONS, ExportVariant.teacher, CELLS))
    assert md.rstrip().endswith(
        "## Ma trận đề\n\n"
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
    assert len(docx.tables) == 1
    cell = docx.tables[0].cell(0, 0)
    assert cell.text == ""
    assert cell._tc.xpath(".//m:oMath")


def test_two_markdown_tables_in_stem_both_exported():
    q = questions((MC, B, 1))[0]
    q["stem"] = "A\n| a |\n|---|\n| 1 |\nB\n| c |\n|---|\n| 3 |"
    docx = Document(io.BytesIO(to_docx(build_blocks(INFO, [q], ExportVariant.student))))
    assert len(docx.tables) == 2


def test_stem_starting_with_table_keeps_question_label():
    q = questions((MC, B, 1))[0]
    q["stem"] = "| a |\n|---|\n| 1 |"
    md = to_markdown(build_blocks(INFO, [q], ExportVariant.student))
    assert md.index("**Câu 1.**") < md.index("| a |")
