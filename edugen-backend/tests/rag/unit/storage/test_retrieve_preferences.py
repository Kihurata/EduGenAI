"""Tóm tắt: truy xuất câu đề mẫu theo dạng câu và ưu tiên (T-034): lọc theo type thay vì part; mức độ (level) và loại đề (exam_kind: tot_nghiep | dinh_ky_7991, D-017) chỉ là ưu tiên: thiếu thì bù cho đủ k, bỏ level trước rồi mới bỏ exam_kind; cùng một lượt thì câu official đứng trước; không trả trùng."""

from dataclasses import replace

import pytest

from app.rag.storage.retrieve import retrieve
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import DAO_HAM, cell, exam_item, memory_client


def _item(i, level=None, exam_kind=None, official=True, **over):
    return replace(exam_item(i, DAO_HAM, "I"), level=level, exam_kind=exam_kind, official=official, **over)


def _items(client, k=3, **cell_extra):
    return retrieve(client, FakeEmbedder(), cell(topic=DAO_HAM, **cell_extra), k=k).exam_items


def test_exam_items_are_filtered_on_type_not_part():
    c = memory_client([_item(1, type="short_answer"), _item(2)])

    assert [e.id for e in _items(c, qtype="short_answer")] == ["e1"]
    assert [e.id for e in _items(c, qtype="multiple_choice")] == ["e2"]


@pytest.mark.parametrize("level", ["Biết", "Hiểu"])
def test_items_of_the_cell_level_come_first(level):
    c = memory_client([_item(i, "Biết", "tot_nghiep") for i in range(3)] + [_item(10 + i, "Hiểu", "tot_nghiep") for i in range(3)])

    assert {e.level for e in _items(c, level=level)} == {level}


def test_too_few_items_of_the_level_are_topped_up_to_k():
    c = memory_client([_item(1, "Hiểu", "tot_nghiep")] + [_item(10 + i, "Biết", "tot_nghiep") for i in range(4)])

    items = _items(c, level="Hiểu")

    assert len(items) == 3 and items[0].id == "e1"
    assert len({e.id for e in items}) == 3  # no duplicates across the passes


def test_level_is_dropped_before_exam_kind():
    same_level_other_kind = _item(1, "Hiểu", "dinh_ky_7991", official=False)
    other_level_same_kind = _item(2, "Biết", "tot_nghiep")
    other_level_other_kind = _item(3, "Biết", "dinh_ky_7991", official=False)
    c = memory_client([same_level_other_kind, other_level_same_kind, other_level_other_kind])

    items = _items(c, k=2, level="Hiểu", exam_kind="tot_nghiep")

    assert items[0].id == "e2" and len(items) == 2


def test_periodic_cell_gets_periodic_items_before_official_graduation_items():
    """D-017: a grade 10-11 dinh_ky_7991 cell takes the school periodic exams first."""
    c = memory_client([_item(1, "Biết", "tot_nghiep"), _item(2, "Biết", "dinh_ky_7991", official=False)])

    assert _items(c, k=1, level="Biết", exam_kind="dinh_ky_7991", grade=10)[0].id == "e2"


@pytest.mark.parametrize("official_first_in_index", [True, False])
def test_official_items_come_before_unofficial_ones_of_the_same_pass(official_first_in_index):
    """D-017: official replaces PREFERRED_EXAM_KIND = official; order must not depend on index order or score."""
    official = _item(1, "Biết", "tot_nghiep")
    mock = _item(2, "Biết", "tot_nghiep", official=False)
    c = memory_client([official, mock] if official_first_in_index else [mock, official])

    assert [e.id for e in _items(c, k=2, level="Biết", exam_kind="tot_nghiep")] == ["e1", "e2"]


def test_cell_without_exam_kind_still_puts_official_items_first():
    c = memory_client([_item(1, "Biết", "dinh_ky_7991", official=False), _item(2, "Biết", "tot_nghiep")])

    assert [e.id for e in _items(c, k=2, level="Biết")] == ["e2", "e1"]


def test_items_without_level_or_kind_still_fill_the_cell():
    c = memory_client([_item(i) for i in range(3)])

    assert len(_items(c, level="Vận dụng")) == 3


@pytest.mark.parametrize("pool, expected", [("official", {"e1"}), ("unofficial", {"e2", "e3"}), ("all", {"e1", "e2", "e3"}), (None, {"e1", "e2", "e3"})])
def test_example_pool_picks_which_exam_items_are_examples(pool, expected):
    c = memory_client([_item(1, official=True), _item(2, official=False), _item(3, official=False)])

    extra = {"example_pool": pool} if pool else {}
    assert {e.id for e in _items(c, **extra)} == expected


def test_unknown_example_pool_fails_loudly():
    with pytest.raises(ValueError, match="example_pool"):
        _items(memory_client([_item(1)]), example_pool="offical")
