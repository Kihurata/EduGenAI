"""Mã đề khi xuất DOCX: cùng đề đã duyệt, mỗi mã đề một thứ tự câu và phương án.

Đầu ra mong muốn:
- Có `code`: mã in trên đề, tên file có mã; cùng mã xuất lại ra cùng nội dung; mã khác ra thứ tự khác.
- Không `code`: bản gốc như trước, không có dòng "Mã đề".
- Mã sai → 422; đề chưa duyệt → 409 (kể cả khi có mã).
- `export-variants`: nhiều mã trong một zip, mỗi mã một DOCX; tối đa 10 mã.
- Ngân hàng đề: GV tải được đề theo mã như đề của mình.
"""

import io
import re
import zipfile

from docx import Document

from tests.api.test_exams import BASE, approved_exam, generated_exam

BANK = "/api/v1/bank"


def doc_of(data: bytes) -> Document:
    return Document(io.BytesIO(data))


def lines(data: bytes) -> list[str]:
    return [p.text for p in doc_of(data).paragraphs]


def export(client, headers, exam_id, variant="student", **params):
    return client.get(f"{BASE}/{exam_id}/export", params={"variant": variant, **params}, headers=headers)


def stems(data: bytes) -> list[str]:
    return [t for t in lines(data) if t.startswith("Câu ")]


def test_code_is_printed_and_in_filename(client, teacher_headers):
    exam = approved_exam(client, teacher_headers)
    resp = export(client, teacher_headers, exam["id"], code="101")
    assert resp.status_code == 200
    assert "M%C3%A3%20%C4%91%E1%BB%81%20101.docx" in resp.headers["content-disposition"]  # "Mã đề 101"
    assert "Mã đề: 101" in lines(resp.content)


def test_no_code_is_the_original_without_code_line(client, teacher_headers):
    exam = approved_exam(client, teacher_headers)
    plain = export(client, teacher_headers, exam["id"])
    assert not any(t.startswith("Mã đề") for t in lines(plain.content))
    assert "Mã đề" not in plain.headers["content-disposition"]


def test_same_code_same_content_other_code_other_order(client, teacher_headers):
    exam = approved_exam(client, teacher_headers)
    a = export(client, teacher_headers, exam["id"], code="101").content
    again = export(client, teacher_headers, exam["id"], code="101").content
    b = export(client, teacher_headers, exam["id"], code="102").content
    plain = export(client, teacher_headers, exam["id"]).content
    assert lines(a) == lines(again)
    assert lines(a) != lines(b)
    assert lines(a) != lines(plain)  # có xáo so với bản gốc
    assert len(stems(a)) == len(stems(b)) == len(stems(plain)) == 22


def test_teacher_variant_has_its_own_answer_tables(client, teacher_headers):
    """Bản GV theo mã đề vẫn đủ bảng đáp án + ma trận; đúng-sai từng phương án được unit test kiểm."""
    exam = approved_exam(client, teacher_headers)
    plain = doc_of(export(client, teacher_headers, exam["id"], "teacher").content)
    coded = doc_of(export(client, teacher_headers, exam["id"], "teacher", code="101").content)
    assert len(coded.tables) == len(plain.tables) == 4  # 3 bảng đáp án + ma trận đề
    answers = [c.text for c in coded.tables[0].rows[1].cells][1:]  # hàng "Đáp án" Phần I
    assert len(answers) == 12 and set(answers) <= set("ABCD")


def test_invalid_code_is_rejected(client, teacher_headers):
    exam = approved_exam(client, teacher_headers)
    for code in ("", "1 2", "../x", "123456789", "mã"):
        resp = export(client, teacher_headers, exam["id"], code=code)
        assert resp.status_code == 422, code


def test_unapproved_exam_cannot_export_even_with_code(client, teacher_headers):
    exam = generated_exam(client, teacher_headers)
    resp = export(client, teacher_headers, exam["id"], code="101")
    assert (resp.status_code, resp.json()["detail"]) == (409, "Đề chưa được duyệt, chưa xuất được")


def test_export_variants_zip_one_docx_per_code(client, teacher_headers):
    exam = approved_exam(client, teacher_headers)
    resp = client.get(
        f"{BASE}/{exam['id']}/export-variants",
        params={"variant": "teacher", "codes": "101, 102,101,103"},
        headers=teacher_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        names = z.namelist()
        assert names == [f"KTGK - HK1 - 10 - GV - Mã đề {c}.docx" for c in ("101", "102", "103")]  # bỏ mã trùng
        for code, name in zip(("101", "102", "103"), names):
            assert f"Mã đề: {code}" in lines(z.read(name))


def test_export_variants_validates_codes(client, teacher_headers):
    exam = approved_exam(client, teacher_headers)
    url = f"{BASE}/{exam['id']}/export-variants"
    bad = client.get(url, params={"variant": "student", "codes": "101,x y"}, headers=teacher_headers)
    assert bad.status_code == 422
    empty = client.get(url, params={"variant": "student", "codes": " , "}, headers=teacher_headers)
    assert empty.status_code == 422
    many = ",".join(str(100 + i) for i in range(11))
    over = client.get(url, params={"variant": "student", "codes": many}, headers=teacher_headers)
    assert (over.status_code, over.json()["detail"]) == (422, "Tối đa 10 mã đề mỗi lần xuất")


def test_colleague_downloads_bank_exam_by_code(client, teacher_headers, colleague_headers, admin_headers):
    exam = approved_exam(client, teacher_headers)
    entry = client.post(BANK, json={"exam_id": exam["id"]}, headers=admin_headers).json()
    client.patch(f"{BANK}/{entry['id']}", json={"is_visible": True}, headers=admin_headers)
    one = client.get(f"{BANK}/{entry['id']}/export", params={"variant": "student", "code": "201"}, headers=colleague_headers)
    assert one.status_code == 200 and "Mã đề: 201" in lines(one.content)
    many = client.get(
        f"{BANK}/{entry['id']}/export-variants", params={"variant": "student", "codes": "201,202"}, headers=colleague_headers
    )
    assert many.status_code == 200 and len(zipfile.ZipFile(io.BytesIO(many.content)).namelist()) == 2


def test_preview_matches_the_exported_file(client, teacher_headers):
    exam = approved_exam(client, teacher_headers)
    resp = client.get(f"{BASE}/{exam['id']}/variant", params={"code": "101"}, headers=teacher_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "101" and len(body["questions"]) == 22
    by_part = {p: [q["content"]["stem"] for q in body["questions"] if q["part"] == p] for p in ("I", "II", "III")}

    def plain(text: str) -> str:  # công thức $…$ thành equation trong DOCX nên không còn trong đoạn văn
        return " ".join(re.sub(r"\$[^$]*\$", "", text).split())

    exported = [plain(t.split(". ", 1)[1]) for t in stems(export(client, teacher_headers, exam["id"], code="101").content)]
    assert exported == [plain(s) for s in by_part["I"] + by_part["II"] + by_part["III"]]
    other = client.get(f"{BASE}/{exam['id']}/variant", params={"code": "102"}, headers=teacher_headers).json()
    assert other["questions"] != body["questions"]


def test_preview_rejects_bad_code_and_hides_other_schools(client, teacher_headers, outsider_headers):
    exam = approved_exam(client, teacher_headers)
    url = f"{BASE}/{exam['id']}/variant"
    assert client.get(url, params={"code": "a b"}, headers=teacher_headers).status_code == 422
    assert client.get(url, params={"code": "101"}, headers=outsider_headers).status_code == 404
