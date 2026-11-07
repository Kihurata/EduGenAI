import pytest

from app.domain.topics import find_topic
from app.rag.vocab import TOPICS as RAG_TOPICS


@pytest.mark.parametrize(
    ("label", "grade", "code"),
    [
        ("Chương I. Hàm số lượng giác và phương trình lượng giác", 11, "dai_so_giai_tich/luong_giac"),
        ("TOÁN 11 - CHƯƠNG II: Dãy số, cấp số cộng và cấp số nhân", 11, "dai_so_giai_tich/day_so_cap_so"),
        ("Chương VI – Hàm số và đồ thị", 10, "dai_so_giai_tich/ham_so_bac_hai"),
        ("Chương VIII Đại số tổ hợp", 10, "dai_so_giai_tich/to_hop"),
        ("Chương IX: Tính xác suất theo định nghĩa cổ điển", 10, "thong_ke_xac_suat/xac_suat_co_dien"),
        ("Chương VI. Hàm số mũ và hàm số lôgarit", 11, "dai_so_giai_tich/mu_logarit"),
        ("Chương IX Đạo hàm", 11, "dai_so_giai_tich/dao_ham"),
        ("Chương VI Hàm số và đồ thị", 10, "dai_so_giai_tich/ham_so_bac_hai"),
        ("Hàm số", 10, "dai_so_giai_tich/ham_so_bac_hai"),
        ("Thống kê", 11, "thong_ke_xac_suat/thong_ke_trung_tam"),
        ("Thống kê", 12, "thong_ke_xac_suat/thong_ke_phan_tan"),
    ],
)
def test_find_topic_accepts_kntt_aliases_and_grade(label, grade, code):
    assert find_topic(label, grade=grade).code == code.split("/", 1)[1]
    assert find_topic(label, grade=grade).strand == code.split("/", 1)[0]


def test_find_topic_remains_backwards_compatible():
    assert find_topic("Nguyên hàm và tích phân").code == "nguyen_ham_tich_phan"


def test_ambiguous_short_name_requires_grade():
    assert find_topic("Thống kê") is None


@pytest.mark.parametrize(
    ("label", "code"),
    [
        ("Hàm số mũ và hàm số lôgarit", "mu_logarit"),  # lớp 11, đề TN 2025 Câu 10
        ("Quan hệ vuông góc trong không gian", "quan_he_vuong_goc"),  # lớp 11, Câu 12
        ("Đạo hàm", "dao_ham"),  # lớp 11
        ("Đại số tổ hợp", "to_hop"),  # lớp 10
    ],
)
def test_grade_12_matrix_still_resolves_grade_10_and_11_chapters(label, code):
    # Đề TN THPT (ma trận lớp 12) hỏi cả chủ đề lớp 10-11 (D-009): lớp chỉ chặn chủ đề của lớp CAO hơn.
    assert find_topic(label, grade=12).code == code


def test_grade_11_matrix_resolves_grade_10_chapter_but_not_grade_12():
    assert find_topic("Đại số tổ hợp", grade=11).code == "to_hop"
    assert find_topic("Nguyên hàm và tích phân", grade=11) is None


def test_all_topic_codes_exist_in_rag_vocab():
    from app.domain.topics import TOPICS

    # Lý/Hóa codes (D-013) are checked against topic_queries.json in test_topics_subjects.py.
    assert {f"{topic.strand}/{topic.code}" for topic in TOPICS.values() if topic.subject == "toan"} <= RAG_TOPICS
