"""Ma trận đã đọc → JSON chuẩn của team (schema Toán matrices.md) + ô gửi RAG (D-008).

- Chủ đề trên ma trận đổi sang mã trong Toán topic list; không khớp → issue, không đoán.
- Mức độ ghi mã biet/hieu/vandung; Phần II đếm theo ý, 4 ý của một câu chung `question`.
- Đề Toán cần 12 / 16 / 6 lệnh hỏi.
"""

from pathlib import Path

import pytest

from app.domain.matrix_json import build_matrix_json
from app.domain.matrix_reader import ParsedCell, ParsedMatrix, read_matrix
from app.domain.topics import TOPICS, find_topic
from app.models.enums import Level, QuestionType

FIXTURE = Path(__file__).parents[1] / "fixtures" / "matrices" / "ktgk_hk1_toan10.md"
MC, TF, SA = QuestionType.multiple_choice, QuestionType.true_false, QuestionType.short_answer
B, H, VD = Level.biet, Level.hieu, Level.van_dung
DAO_HAM = "Ứng dụng đạo hàm để khảo sát và vẽ đồ thị hàm số"
TICH_PHAN = "Nguyên hàm và tích phân"


def fixture_json():
    return build_matrix_json(read_matrix(FIXTURE.read_text(encoding="utf-8")))


def toan12(mc_count: int = 12) -> ParsedMatrix:
    """Ma trận tốt nghiệp hợp lệ: 12 MC, 4 câu Đ/S (16 ý), 6 trả lời ngắn."""
    return ParsedMatrix(
        subject="toan",
        grade=12,
        name="Đề thi thử TN THPT",
        cells=[
            ParsedCell(MC, DAO_HAM, None, B, mc_count),
            ParsedCell(TF, DAO_HAM, None, H, 3, (B, B, H, H)),
            ParsedCell(TF, TICH_PHAN, None, VD, 1, (B, H, H, VD)),
            ParsedCell(SA, TICH_PHAN, None, VD, 6),
        ],
    )


def test_topic_matches_vietnamese_name_ignoring_case_and_punctuation():
    assert find_topic("ỨNG DỤNG ĐẠO HÀM ĐỂ KHẢO SÁT VÀ VẼ ĐỒ THỊ HÀM SỐ.").code == "ung_dung_dao_ham"
    assert find_topic("  Nguyên hàm   và tích phân ").strand == "dai_so_giai_tich"
    assert find_topic("Mệnh đề và tập hợp").code == "menh_de_tap_hop"
    assert find_topic("Lý thuyết đồ thị") is None  # chương thuộc sách Chuyên đề, chưa có mã (D-022)


def test_fixture_header_and_totals():
    m = fixture_json().matrix
    assert (m["subject"], m["grade"], m["name"]) == ("toan", 10, "KTGK - HK1 - 10")
    assert m["exam_kind"] == "dinh_ky_7991"
    assert m["count_unit"] == "item"
    assert m["constraints"]["total_items"] == {"I": 12, "II": 16, "III": 6}
    assert m["constraints"]["level_totals"] == {
        "I": {"biet": 8, "hieu": 4, "vandung": 0},
        "II": {"biet": 8, "hieu": 8, "vandung": 0},
        "III": {"biet": 0, "hieu": 2, "vandung": 4},
    }


def test_fixture_maps_known_topics_and_has_no_issues():
    result = fixture_json()
    cell = result.matrix["cells"][3]
    assert cell["source_topic"] == "Bất phương trình và hệ bất phương trình bậc nhất hai ẩn"
    assert (cell["strand"], cell["topic"]) == ("dai_so_giai_tich", "he_bat_phuong_trinh_bac_nhat_hai_an")
    assert result.matrix["cells"][0]["topic"] == "menh_de_tap_hop"  # chương lớp 10 đã có mã
    assert [i.location for i in result.issues] == []
    assert result.ready_for_rag


def test_part_two_counts_statements_grouped_by_question():
    cells = [c for c in build_matrix_json(toan12()).matrix["cells"] if c["part"] == "II"]
    assert [(c["question"], c["level"], c["count"]) for c in cells] == [
        (1, "biet", 2), (1, "hieu", 2),
        (2, "biet", 2), (2, "hieu", 2),
        (3, "biet", 2), (3, "hieu", 2),
        (4, "biet", 1), (4, "hieu", 2), (4, "vandung", 1),
    ]  # fmt: skip
    assert all(c["type"] == "true_false" and "question" in c for c in cells)


def test_valid_matrix_gives_rag_cells_in_contract_shape():
    result = build_matrix_json(toan12())
    assert result.issues == []
    assert result.ready_for_rag
    assert result.matrix["exam_kind"] == "tot_nghiep"
    assert result.rag_cells[0] == {
        "subject": "toan", "topic": "ung_dung_dao_ham", "level": "Biết",
        "type": "multiple_choice", "count": 12,
    }  # fmt: skip
    assert result.rag_cells[1] == {
        "subject": "toan", "topic": "ung_dung_dao_ham", "level": "Hiểu", "type": "true_false",
        "count": 3, "statement_levels": ["Biết", "Biết", "Hiểu", "Hiểu"],
    }  # fmt: skip


def test_matrix_topic_resolution_uses_parsed_grade():
    parsed = ParsedMatrix(
        subject="toan", grade=10, name="Đề thi thử",
        cells=[ParsedCell(MC, TOPICS["ham_so_bac_hai"].name, None, B, 12)],
    )
    result = build_matrix_json(parsed)
    assert result.rag_cells[0]["topic"] == "ham_so_bac_hai"


def test_wrong_part_size_is_rejected():
    result = build_matrix_json(toan12(mc_count=11))
    assert [i.message for i in result.issues] == ["Phần I cần đủ 12 lệnh hỏi, hiện có 11: sửa số lệnh hỏi ở các ô của phần này"]
    assert not result.ready_for_rag


def test_part_two_cells_carry_codes_and_source_text_of_their_level():
    q1 = [c for c in fixture_json().matrix["cells"] if c.get("question") == 1]
    assert [(c["level"], c["competency_codes"]) for c in q1] == [("biet", ["GQ1.4"]), ("hieu", ["GQ2.1"])]
    assert "2a, 2b" in q1[0]["source_text"]
    assert "2c, 2d" in q1[1]["source_text"]


def test_plain_cells_keep_source_text():
    assert fixture_json().matrix["cells"][0]["source_text"] == "02 (TD1.2)"


def test_score_totals_per_part_and_level():
    c = fixture_json().matrix["constraints"]
    assert c["score_totals"] == {
        "I": {"biet": 2.0, "hieu": 1.0, "vandung": 0.0},
        "II": {"biet": 2.0, "hieu": 2.0, "vandung": 0.0},
        "III": {"biet": 0.0, "hieu": 1.0, "vandung": 2.0},
    }
    assert c["total_score"] == 10.0


GOLDEN = FIXTURE.with_suffix(".expected.json")


def test_real_matrix_matches_hand_checked_golden_file():
    """JSON kỳ vọng đã đối chiếu tay với ảnh ktgk_hk1_toan10.png; đổi parser mà lệch là lỗi."""
    import json

    result = fixture_json()
    got = {
        "ready_for_rag": result.ready_for_rag,
        "issues": [i.message for i in result.issues],
        "matrix": result.matrix,
        "rag_cells": result.rag_cells,
    }
    assert got == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_matrix_without_subject_is_not_treated_as_toan():
    parsed = toan12()
    parsed.subject = None
    with pytest.raises(ValueError, match="chưa có môn"):
        build_matrix_json(parsed)
