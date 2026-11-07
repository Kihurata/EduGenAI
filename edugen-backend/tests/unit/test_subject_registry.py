"""Tóm tắt: registry môn học (D-020, T-064, TC-032). Mỗi môn đăng ký phải đủ dữ liệu cho cả luồng (tên trên ma trận,
cấu trúc đề, chủ đề kèm lớp và cụm truy vấn RAG, prompt sinh câu, đề mục SGK), nên thêm môn chỉ cần thêm dữ liệu và test
này chỉ ra còn thiếu gì. Môn chưa đăng ký bị từ chối rõ ràng thay vì lặng lẽ dùng của Toán.
"""

import pytest

from app.core.subjects import SUBJECTS, get_subject
from app.domain.exam_structure import get_structure
from app.domain.matrix_reader import SUBJECT_CODES
from app.domain.topics import find_topic, topic_grade, topic_list_name, topics_for
from app.rag.chunking.markdown import heading_path
from app.rag.generation.generate import SYSTEM_PROMPT, system_prompt
from app.rag.vocab import TOPIC_QUERIES
from app.seed import SUBJECTS as SEEDED

CODES = sorted(SUBJECTS)


def test_TC_032_registry_holds_the_subjects_the_app_runs_today():
    assert CODES == ["hoa", "ly", "toan"]


@pytest.mark.parametrize("code", CODES)
def test_TC_032_every_registered_subject_has_data_for_the_whole_flow(code):
    s = get_subject(code)
    assert SUBJECT_CODES[s.name.lower()] == code  # dòng "Môn:" của ma trận
    assert SEEDED[code] == s.name  # bảng subjects
    assert get_structure(code).question_counts  # kiểm tổng ma trận, chấm điểm
    topics = topics_for(code)
    assert topics, "chưa có danh sách chủ đề"
    assert all(topic_grade(t, 0) in (10, 11, 12) for t in topics), "chủ đề thiếu lớp"
    assert all(TOPIC_QUERIES.get(f"{t.strand}/{t.code}") for t in topics), "chủ đề thiếu cụm truy vấn RAG"
    assert f"môn {s.label}" in system_prompt(code)
    assert heading_path(code, 12, ("Chương I",)) == f"{s.label} 12 > Chương I"
    assert topic_list_name(code) == s.topic_list


def test_TC_032_toan_prompt_is_unchanged():
    assert system_prompt("toan") == SYSTEM_PROMPT


def test_TC_032_unknown_subject_is_rejected_not_given_the_toan_prompt():
    with pytest.raises(ValueError, match="sinh"):
        get_subject("sinh")
    with pytest.raises(ValueError, match="sinh"):
        system_prompt("sinh")


@pytest.mark.parametrize("label, subject, code", [
    ("Toán 11 Chương I Hàm số lượng giác và phương trình lượng giác", "toan", "luong_giac"),
    ("Hóa học 12 Chương 1 Ester – Lipid", "hoa", "ester_lipid"),
    ("Vật lí 12 Chương I Vật lí nhiệt", "ly", "vat_li_nhiet"),
])
def test_TC_032_chapter_prefix_with_any_subject_name_is_ignored(label, subject, code):
    assert find_topic(label, grade=12, subject=subject).code == code


def test_TC_032_toan_short_labels_stay_toan_only():
    assert find_topic("Thống kê", grade=12, subject="toan").code == "thong_ke_phan_tan"
    assert find_topic("Thống kê", grade=12, subject="hoa") is None
