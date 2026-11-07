"""Tóm tắt: truy xuất lý thuyết và bài tập SGK ưu tiên đúng chương của chủ đề, thiếu thì bù theo lớp (D-021, T-068): ô có chương trong bảng thì lượt 1 lọc thêm chapter; thiếu k đoạn thì bù lượt chỉ lọc lớp, đoạn lượt 1 đứng trước, không trùng; mã không có trong bảng thì chỉ lọc lớp; ô Vận dụng: bài tập SGK cũng ưu tiên chương; bảng chương chỉ chứa mã chủ đề hợp lệ."""

from app.rag.storage.retrieve import retrieve
from app.rag.vocab import CHAPTER_BY_TOPIC, TOPICS
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import DAO_HAM, XAC_SUAT, cell, memory_client, theory

CH = CHAPTER_BY_TOPIC[DAO_HAM]
OTHER = "Chương II. Vectơ và hệ trục toạ độ trong không gian"


def _theory(i, chapter, kind="theory"):
    return theory(i, chapter=chapter, kind=kind)


def _ids(client, k=3, topic=DAO_HAM, **extra):
    return [c.id for c in retrieve(client, FakeEmbedder(), cell(topic=topic, **extra), k=k).theory]


def test_chunks_of_the_topic_chapter_are_taken_over_other_chapters():
    c = memory_client([_theory(i, CH) for i in range(3)] + [_theory(10 + i, OTHER) for i in range(5)])

    assert sorted(_ids(c)) == ["t0", "t1", "t2"]


def test_too_few_chunks_in_the_chapter_are_topped_up_by_grade_with_chapter_first():
    c = memory_client([_theory(1, CH)] + [_theory(10 + i, OTHER) for i in range(4)])

    ids = _ids(c)

    assert ids[0] == "t1" and len(ids) == 3 and len(set(ids)) == 3


def test_topic_without_a_chapter_is_filtered_by_grade_only():
    c = memory_client([_theory(i, CH) for i in range(2)] + [_theory(10 + i, OTHER) for i in range(2)])

    assert len(_ids(c, k=4, topic="dai_so_giai_tich/he_phuong_trinh_bac_nhat_ba_an")) == 4


def test_vandung_exercises_prefer_the_chapter_too():
    c = memory_client([_theory(1, CH), _theory(2, CH, "exercise"), _theory(3, OTHER, "exercise"), _theory(4, OTHER, "exercise")])

    got = retrieve(c, FakeEmbedder(), cell(topic=DAO_HAM, level="Vận dụng"), k=1).theory

    assert [x.id for x in got[:2]] == ["t1", "t2"] and len(got) == 3  # theory k=1, then 2 exercises: the in-chapter one first


def test_every_chapter_table_key_is_a_known_topic():
    assert set(CHAPTER_BY_TOPIC) <= TOPICS and XAC_SUAT in CHAPTER_BY_TOPIC
