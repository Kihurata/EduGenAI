"""Tóm tắt: unit test bộ từ vựng chung của hợp đồng RAG (T-028): loại câu ↔ phần đề, mức độ Biết/Hiểu/Vận dụng theo thứ tự, 25 mã chủ đề mới "mạch/chủ đề", bảng đổi mã cũ → mới và chiều ngược lại (old_codes)."""

import pytest

from app.rag.vocab import LEVEL_FROM_CODE, LEVELS, OLD_TO_NEW, PART_BY_TYPE, TOPICS, TYPES, old_codes

STRANDS = {"dai_so_giai_tich", "hinh_hoc_do_luong", "thong_ke_xac_suat"}


# --- existing behaviour ----------------------------------------------------------------------------------------

def test_types_map_to_parts():
    assert set(TYPES) == set(PART_BY_TYPE)
    assert PART_BY_TYPE == {"multiple_choice": "I", "true_false": "II", "short_answer": "III"}


def test_level_codes_cover_levels():
    assert set(LEVEL_FROM_CODE.values()) == set(LEVELS)
    assert LEVEL_FROM_CODE["vandung"] == "Vận dụng"


def test_every_old_code_maps_to_a_topic():
    assert len(TOPICS) == 25
    assert len(OLD_TO_NEW) == 31
    assert set(OLD_TO_NEW.values()) <= TOPICS


def test_concrete_mappings_from_topic_list():
    assert OLD_TO_NEW["dai_so_giai_tich/tiem_can"] == "dai_so_giai_tich/ung_dung_dao_ham"
    assert OLD_TO_NEW["thong_ke_xac_suat/to_hop"] == "dai_so_giai_tich/to_hop"  # strand changes
    assert OLD_TO_NEW["hinh_hoc_do_luong/toa_do_vecto"] == "hinh_hoc_do_luong/vecto_khong_gian"


def test_old_codes_inverts_mapping():
    assert set(old_codes("dai_so_giai_tich/day_so_cap_so")) == {
        "dai_so_giai_tich/cap_so_cong", "dai_so_giai_tich/cap_so_nhan"}
    assert old_codes("hinh_hoc_do_luong/quan_he_song_song") == ["hinh_hoc_do_luong/quan_he_song_song"]
    # ham_so_thuc_te has two targets: retrieval finds it under both.
    assert "dai_so_giai_tich/ham_so_thuc_te" in old_codes("dai_so_giai_tich/ham_so_bac_hai")
    assert "dai_so_giai_tich/ham_so_thuc_te" in old_codes("dai_so_giai_tich/ung_dung_dao_ham")


# --- invariants ------------------------------------------------------------------------------------------------

def test_types_are_in_exam_part_order():
    assert [PART_BY_TYPE[t] for t in TYPES] == ["I", "II", "III"]


def test_parts_are_one_to_one_with_types():
    assert len(set(PART_BY_TYPE.values())) == len(PART_BY_TYPE)


def test_levels_go_from_recall_to_application():
    assert LEVELS == ("Biết", "Hiểu", "Vận dụng")


@pytest.mark.parametrize("code", sorted(TOPICS | set(OLD_TO_NEW)))
def test_every_code_is_strand_slash_topic(code):
    strand, _, topic = code.partition("/")

    assert strand in STRANDS and topic and topic == topic.lower() and " " not in code


@pytest.mark.parametrize("topic", sorted(TOPICS))
def test_old_codes_of_a_topic_all_map_back_to_it_or_are_its_second_target(topic):
    for old in old_codes(topic):
        assert old in OLD_TO_NEW
        assert OLD_TO_NEW[old] == topic or old == "dai_so_giai_tich/ham_so_thuc_te"


def test_every_old_code_is_found_from_its_new_topic():
    assert all(old in old_codes(new) for old, new in OLD_TO_NEW.items())


def test_old_codes_of_an_unknown_topic_is_empty():
    assert old_codes("khong/co") == []


def test_codes_that_kept_their_name_map_to_themselves():
    same = [old for old, new in OLD_TO_NEW.items() if old == new]

    assert "dai_so_giai_tich/ung_dung_dao_ham" in same and all(s in TOPICS for s in same)


def test_only_these_topics_have_no_old_exam_code():
    # No indexed exam item uses them yet, so retrieval for them finds theory only; a new one shows up here.
    # The six Toán 10-11 chapters were added for periodic (giữa kì) matrices, not for the graduation exams.
    assert {t for t in TOPICS if not old_codes(t)} == {
        "thong_ke_xac_suat/thong_ke_phan_tan",
        "dai_so_giai_tich/menh_de_tap_hop",
        "hinh_hoc_do_luong/he_thuc_luong_tam_giac",
        "hinh_hoc_do_luong/vecto_mat_phang",
        "thong_ke_xac_suat/thong_ke_khong_ghep_nhom",
        "hinh_hoc_do_luong/toa_do_mat_phang",
        "dai_so_giai_tich/gioi_han_ham_lien_tuc",
    }
