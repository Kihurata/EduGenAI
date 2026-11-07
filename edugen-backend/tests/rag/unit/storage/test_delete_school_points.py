"""Tóm tắt: xoá dữ liệu Qdrant theo trường (T-046): xoá trường thì mất mọi đoạn có school_id của trường đó, đoạn dùng chung (SGK, đề chính thức) và đoạn trường khác giữ nguyên; school_id rỗng thì báo lỗi, không xoá gì; xoá một đề mẫu chỉ xoá đoạn của đề đó (source)."""

from dataclasses import replace

import pytest
from qdrant_client import models

from app.rag.storage.qdrant import COLLECTION, delete_school_points
from tests.rag.support import exam_item, memory_client, theory

A, B = "school-a", "school-b"


def _owned(chunk, school_id, source=None):
    return replace(chunk, school_id=school_id, source=source or chunk.source)


def _ids(client):
    points, _ = client.scroll(COLLECTION, limit=100)
    return {p.payload["id"] for p in points}


def _mixed_client():
    return memory_client([
        theory(1), exam_item(2),  # shared
        _owned(exam_item(3), A, "sample-a1.json"), _owned(exam_item(4), A, "sample-a2.json"),
        _owned(exam_item(5), B, "sample-b1.json"),
    ])  # fmt: skip


def test_deleting_a_school_removes_only_its_chunks():
    c = _mixed_client()

    delete_school_points(c, A)

    assert _ids(c) == {"t1", "e2", "e5"}


@pytest.mark.parametrize("school_id", [None, "", "  "])
def test_an_empty_school_id_raises_and_deletes_nothing(school_id):
    c = _mixed_client()

    with pytest.raises(ValueError):
        delete_school_points(c, school_id)

    assert len(_ids(c)) == 5


def test_deleting_one_sample_exam_keeps_the_schools_other_exam():
    c = _mixed_client()

    delete_school_points(c, A, source="sample-a1.json")

    assert _ids(c) == {"t1", "e2", "e4", "e5"}
    left = c.count(COLLECTION, count_filter=models.Filter(must=[
        models.FieldCondition(key="source", match=models.MatchValue(value="sample-a2.json"))])).count  # fmt: skip
    assert left == 1


def test_a_source_of_another_school_is_not_deleted():
    c = _mixed_client()

    delete_school_points(c, A, source="sample-b1.json")

    assert len(_ids(c)) == 5


def test_no_collection_is_a_no_op():
    delete_school_points(memory_client(), A)
