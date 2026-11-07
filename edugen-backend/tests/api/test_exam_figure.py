"""Hình khối trong đề (F-17), chạy qua API với RAG giả lập: RAG trả tham số hình → BE vẽ SVG → FE xem, DOCX nhúng PNG.

Đầu ra mong muốn:
- Câu RAG kèm `hinh_ve` hợp lệ: nội dung câu có `figure_spec` và `figure_svg`; API trả nguyên cho FE xem trước.
- `hinh_ve` hỏng: bỏ spec, câu vẫn nhận (giữ mô tả chữ `figure`), đề vẫn `generated`.
- GV sửa câu: SVG vẽ lại từ spec mới; SVG do máy khách gửi không được tin; bỏ spec thì bỏ SVG.
- Xuất DOCX (bản HS và bản GV): mỗi hình một ảnh PNG, bản GV không vẽ lại hình ở phần lời giải.
- Hình lỗi khi chuyển PNG không làm hỏng việc xuất đề.
"""

import copy
import io
import zipfile

import pytest
from docx import Document

from app.domain.figure import render_svg
from app.services import docx_export
from tests.api.conftest import FakeIngestRag
from tests.api.test_exams import BASE, approved_exam, generated_exam
from tests.api.test_review import edit, fetch, url

SPEC = {"solid": "pyramid", "a": 3, "b": 4, "h": 5, "foot": "center"}
BAD_SPEC = {"solid": "sphere", "a": 1, "b": 1, "h": 1, "foot": None}
TEXT = "Hình chóp $S.ABCD$ có đáy là hình chữ nhật"


class FigureRag(FakeIngestRag):
    """Ô 1 trả câu có hình chóp hợp lệ, ô 2 trả câu có hình hỏng, các ô còn lại không có hình."""

    def generate(self, cell):
        valid, rejected = super().generate(cell)
        valid = copy.deepcopy(valid)
        if cell.id == 1:
            valid[0] |= {"hinh_ve": SPEC, "hinh": TEXT}
        if cell.id == 2:
            valid[0] |= {"hinh_ve": BAD_SPEC, "hinh": "Hình cầu"}
        return valid, rejected


@pytest.fixture
def rag() -> FigureRag:
    import json

    from tests.api.conftest import SAMPLES

    return FigureRag(json.loads(SAMPLES.read_text(encoding="utf-8")))


def with_svg(exam: dict) -> list[dict]:
    return [q for q in exam["questions"] if "figure_svg" in q["content"]]


def drawn(client, headers) -> tuple[dict, dict]:
    exam = generated_exam(client, headers)
    [question] = with_svg(exam)
    return exam, question


def test_valid_spec_is_drawn_and_served_to_the_frontend(client, teacher_headers):
    exam, question = drawn(client, teacher_headers)
    content = question["content"]
    assert exam["status"] == "generated"
    assert content["figure_spec"] == SPEC
    assert content["figure_svg"] == render_svg(SPEC)
    assert content["figure"] == TEXT


def test_bad_spec_is_dropped_and_the_exam_is_still_complete(client, teacher_headers):
    exam = generated_exam(client, teacher_headers)
    [bad] = [q for q in exam["questions"] if q["content"].get("figure") == "Hình cầu"]
    assert "figure_spec" not in bad["content"] and "figure_svg" not in bad["content"]
    assert [r["status"] for r in exam["cell_runs"]] == ["complete"] * 18


def test_questions_without_a_figure_are_untouched(client, teacher_headers):
    exam = generated_exam(client, teacher_headers)
    plain = [q for q in exam["questions"] if "figure" not in q["content"]]
    assert plain
    assert all("figure_spec" not in q["content"] and "figure_svg" not in q["content"] for q in plain)


def test_editing_the_spec_redraws_the_svg(client, teacher_headers):
    exam, question = drawn(client, teacher_headers)
    new_spec = SPEC | {"h": 2, "foot": "A"}
    resp = edit(client, teacher_headers, exam, question, figure_spec=new_spec)
    assert resp.status_code == 200, resp.text
    assert resp.json()["content"]["figure_svg"] == render_svg(new_spec) != render_svg(SPEC)


def test_a_stale_or_forged_svg_from_the_client_is_never_kept(client, teacher_headers):
    exam, question = drawn(client, teacher_headers)
    forged = '<svg onload="alert(1)"/>'
    resp = edit(client, teacher_headers, exam, question, figure_spec=SPEC | {"a": 4}, figure_svg=forged)
    assert resp.json()["content"]["figure_svg"] == render_svg(SPEC | {"a": 4})
    assert "onload" not in str(fetch(client, teacher_headers, exam))


def test_removing_the_spec_removes_the_svg_and_keeps_the_text(client, teacher_headers):
    exam, question = drawn(client, teacher_headers)
    content = {k: v for k, v in question["content"].items() if k not in ("figure_spec", "figure_svg")}
    resp = client.put(url(exam, "questions", question["id"]), json=content, headers=teacher_headers)
    assert resp.status_code == 200, resp.text
    assert "figure_svg" not in resp.json()["content"] and resp.json()["content"]["figure"] == TEXT


def test_an_svg_without_any_spec_is_dropped_on_edit(client, teacher_headers):
    exam = generated_exam(client, teacher_headers)
    plain = next(q for q in exam["questions"] if "figure" not in q["content"])
    resp = edit(client, teacher_headers, exam, plain, figure_svg='<svg onload="alert(1)"/>')
    assert resp.status_code == 200 and "figure_svg" not in resp.json()["content"]


def test_a_bad_spec_in_an_edit_is_dropped_and_the_edit_still_saves(client, teacher_headers):
    exam, question = drawn(client, teacher_headers)
    resp = edit(client, teacher_headers, exam, question, figure_spec=BAD_SPEC)
    assert resp.status_code == 200
    content = resp.json()["content"]
    assert "figure_spec" not in content and "figure_svg" not in content and content["figure"] == TEXT


def png_files(response) -> list[str]:
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    return [n for n in names if n.startswith("word/media/") and n.endswith(".png")]


@pytest.mark.parametrize("variant", ["student", "teacher"])
def test_export_embeds_one_png_for_the_one_figure(client, teacher_headers, variant):
    exam = approved_exam(client, teacher_headers)
    resp = client.get(f"{BASE}/{exam['id']}/export", params={"variant": variant}, headers=teacher_headers)
    assert resp.status_code == 200, resp.text
    assert len(png_files(resp)) == 1
    assert len(Document(io.BytesIO(resp.content)).inline_shapes) == 1


def test_export_still_works_when_the_png_conversion_breaks(client, teacher_headers, monkeypatch):
    def broken(svg):
        raise OSError("no libcairo")

    monkeypatch.setattr(docx_export, "svg_to_png", broken)
    exam = approved_exam(client, teacher_headers)
    resp = client.get(f"{BASE}/{exam['id']}/export", params={"variant": "student"}, headers=teacher_headers)
    assert resp.status_code == 200 and png_files(resp) == []
    assert TEXT in [p.text for p in Document(io.BytesIO(resp.content)).paragraphs]


def test_regenerating_the_question_draws_the_figure_again(client, teacher_headers):
    exam, question = drawn(client, teacher_headers)
    resp = client.post(url(exam, "questions", question["id"], "regenerate"), headers=teacher_headers)
    assert resp.status_code == 202
    [again] = [q for q in fetch(client, teacher_headers, exam)["questions"] if q["id"] == question["id"]]
    assert again["content"]["figure_svg"] == render_svg(SPEC)
