"""TC-011 (nghiệm thu F-06, chạy với RAG giả lập nên ở mức integration): xuất đề Toán ra Word kèm đáp án.

Đề vào: đề tốt nghiệp THPT 2025 mã 0101 (đề chính thức, `fixtures/exams/toan-tn-2025-0101.json`). Ma trận
`fixtures/matrices/tn_2025_0101.md` có một ô mỗi câu theo thứ tự Câu (mức độ theo ma trận nhóm tự xếp, vault
`toan-matrix/derived-tn-2025-0101.yaml`); RAG giả trả ô thứ n đúng câu thứ n của đề.

Đầu ra mong muốn (đọc lại bản GV bằng python-docx):
- 22 câu theo Phần I → II → III; Phần I có phương án A–D, Phần II có ý a)–d).
- Bảng đáp án trùng đáp án chính thức của Bộ cho mã 0101 (`fixtures/exams/dap-an-toan-tn-2025.json`).
- Bảng ma trận: một hàng mỗi ô, tổng theo phần 12 / 4 / 6, hàng tổng 22.
"""

import copy
import io
import json

import pytest
from docx import Document

from app.domain.question import LEVEL_TO_RAG, TRUE_FALSE_MARKS, TYPE_TO_RAG
from app.models.enums import QuestionType
from tests.api.conftest import FIXTURES, FakeConverter, FakeIngestRag
from tests.api.test_exam_build import numbers_by_part
from tests.api.test_exams import BASE, approved_exam

EXAM = json.loads((FIXTURES / "exams" / "toan-tn-2025-0101.json").read_text(encoding="utf-8"))
KEY = json.loads((FIXTURES / "exams" / "dap-an-toan-tn-2025.json").read_text(encoding="utf-8"))["ma_de"]["0101"]
MATRIX_MD = FIXTURES / "matrices" / "tn_2025_0101.md"
TYPE_OF_PART = {"I": QuestionType.multiple_choice, "II": QuestionType.true_false, "III": QuestionType.short_answer}


def to_rag(q: dict) -> dict:
    """Câu của đề chính thức → câu RAG trả về (đề không kèm lời giải nên ghi nguồn đáp án)."""
    type_ = TYPE_OF_PART[q["part"]]
    raw = {"dang": TYPE_TO_RAG[type_], "de_bai": q["stem"], "loi_giai": f"Theo đáp án chính thức, {EXAM['exam']}."}
    if type_ is QuestionType.multiple_choice:
        raw |= {"phuong_an": [q["options"][k] for k in "ABCD"], "dap_an": q["answer"]}
    elif type_ is QuestionType.true_false:
        raw["y_dung_sai"] = [{"noi_dung": s["text"], "dung": s["answer"]} for s in q["statements"]]
        raw["dap_an"] = "".join(TRUE_FALSE_MARKS[s["answer"]] for s in q["statements"])
    else:
        raw["dap_an"] = q["answer"]
        # BUG-003 approval gate: the answer comes from the Bộ's key, so it counts as checked (not a SymPy expr).
        raw["kiem_tra"] = {"expr": "official answer key", "verified": True}
    return raw


class OfficialExamRag(FakeIngestRag):
    """Ô thứ n của ma trận (sort_order, từ 1) nhận lại câu thứ n của đề chính thức."""

    def __init__(self) -> None:
        super().__init__([])
        self.by_cell = [to_rag(q) for q in EXAM["questions"]]

    def generate(self, cell):
        raw = copy.deepcopy(self.by_cell[cell.id - 1])
        raw["muc_do"] = LEVEL_TO_RAG[cell.level]
        return [raw], []


@pytest.fixture
def rag() -> OfficialExamRag:
    return OfficialExamRag()


@pytest.fixture
def converter() -> FakeConverter:
    fake = FakeConverter()
    fake.markdown = MATRIX_MD.read_text(encoding="utf-8")
    return fake


def labels_by_question(paragraphs: list[str]) -> dict[str, list[str]]:
    """Nhãn các dòng phương án/ý sau mỗi "Câu n." của phần đề, khóa "I.1", "II.3"…"""
    out: dict[str, list[str]] = {}
    part, current = None, None
    for text in paragraphs:
        if text.startswith("PHẦN "):
            part = text.removeprefix("PHẦN ").split(".")[0]
        elif text.startswith("Câu ") and part:
            current = out.setdefault(f"{part}.{text.removeprefix('Câu ').split('.')[0]}", [])
        elif current is not None:
            # Phương án ngắn chung một dòng, cách nhau bằng tab ("A. 1\tB. 2\t…").
            current += [cell[0] for cell in text.split("\t") if cell[1:2] in (".", ")")]
    return out


def test_TC_011_export_toan_exam_docx(client, teacher_headers):
    exam = approved_exam(client, teacher_headers)
    student = client.get(f"{BASE}/{exam['id']}/export", params={"variant": "student"}, headers=teacher_headers)
    assert student.status_code == 200, student.text
    paragraphs = [p.text for p in Document(io.BytesIO(student.content)).paragraphs]
    paragraphs = paragraphs[: paragraphs.index("------ HẾT ------")]
    resp = client.get(f"{BASE}/{exam['id']}/export", params={"variant": "teacher"}, headers=teacher_headers)
    assert resp.status_code == 200, resp.text
    doc = Document(io.BytesIO(resp.content))

    # 22 câu theo thứ tự phần, Phần I có A–D, Phần II có a)–d).
    assert numbers_by_part(paragraphs) == {"I": list(range(1, 13)), "II": list(range(1, 5)), "III": list(range(1, 7))}
    labels = labels_by_question(paragraphs)
    assert [labels[f"I.{n}"] for n in range(1, 13)] == [list("ABCD")] * 12
    assert [labels[f"II.{n}"] for n in range(1, 5)] == [list("abcd")] * 4
    assert [labels[f"III.{n}"] for n in range(1, 7)] == [[]] * 6

    # Bảng đáp án = đáp án chính thức của Bộ, mã 0101.
    _, part_one, part_two, part_three, matrix = ([[c.text for c in r.cells] for r in t.rows] for t in doc.tables)
    assert part_one[1][1:] == KEY["I"]
    # Đúng – Sai: một hàng mỗi ý a–d, một cột mỗi câu (như bản xem trước) → xoay lại theo câu.
    by_question = [list(col) for col in zip(*(row[1:] for row in part_two[1:]))]
    assert [[mark == TRUE_FALSE_MARKS[True] for mark in q] for q in by_question] == KEY["II"]
    assert part_three[1][1:] == KEY["III"]

    # Bảng ma trận: một hàng mỗi ô, tổng 12 / 4 / 6.
    header, *rows, total = matrix
    assert (header[0], header[-1]) == ("Phần", "Số câu")
    assert len(rows) == 22
    assert {p: sum(int(r[-1]) for r in rows if r[0] == p) for p in ("I", "II", "III")} == {"I": 12, "II": 4, "III": 6}
    assert (total[0], total[-1]) == ("Tổng", "22")
