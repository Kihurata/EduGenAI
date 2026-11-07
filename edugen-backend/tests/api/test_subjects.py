"""Tóm tắt: API môn học cho frontend (D-020, T-064, TC-032): danh sách môn kèm cấu trúc đề từng môn để trang kiểm ma trận
và trang đề mẫu không ghi cứng Toán 12/4/6; đề trả về môn và lớp để bản xem trước ghi đúng "Môn: … – Lớp …"."""

from tests.api.test_exams import generated_exam

BASE = "/api/v1/subjects"


def test_TC_032_subjects_list_their_exam_structure(client, teacher_headers):
    resp = client.get(BASE, headers=teacher_headers)
    assert resp.status_code == 200, resp.text
    by_code = {s["code"]: s for s in resp.json()}
    assert sorted(by_code) == ["hoa", "ly", "toan"]
    toan, ly = by_code["toan"], by_code["ly"]
    assert (toan["name"], toan["label"]) == ("Toán học", "Toán")
    assert toan["question_counts"] == {"multiple_choice": 12, "true_false": 4, "short_answer": 6}
    assert toan["points"] == {"multiple_choice": 0.25, "true_false": 1.0, "short_answer": 0.5}
    assert toan["duration_minutes"] == 90
    assert ly["question_counts"]["multiple_choice"] == 18 and ly["duration_minutes"] == 50


def test_subjects_need_login(client):
    assert client.get(BASE).status_code == 401


def test_TC_032_exam_carries_subject_and_grade_of_its_matrix(client, teacher_headers):
    exam = generated_exam(client, teacher_headers)
    assert (exam["subject"], exam["grade"]) == ("toan", 12)
