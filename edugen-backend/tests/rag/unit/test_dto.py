"""Tóm tắt: unit test các DTO giữa các bước RAG: Chunk chuyển dict ↔ đối tượng không mất trường (D-003), Vector/Verification không sửa được, Retrieved/GenerationResult vẫn tách được như tuple."""

import dataclasses
import json

import pytest

from app.rag.dto import Chunk, GenerationResult, Retrieved, Vector, Verification

THEORY = {
    "id": "abc123", "kind": "theory", "text": "Toán 12 > Chương I > Bài 1 > 1. Định nghĩa\nHàm số đồng biến ...",
    "subject": "toan", "grade": 12, "chapter": "Chương I", "lesson": "Bài 1", "section": "1. Định nghĩa",
    "heading_path": "Toán 12 > Chương I > Bài 1 > 1. Định nghĩa", "source": "sgk-toan-12-kntt-tap1.pdf", "page": 5,
    "official": True,
}

EXAM_ITEM = {
    "id": "def456", "kind": "exam_item", "text": "Câu 1. ...", "subject": "toan", "grade": 12, "chapter": "",
    "lesson": "", "section": "", "heading_path": "", "source": "toan-tn-2025-0101.json", "page": None,
    "official": True, "year": 2025, "exam_code": "0101", "part": "II", "question_no": 1,
    "topic": "dai_so_giai_tich/ung_dung_dao_ham", "type": "true_false", "exam_kind": None, "level": None,
    "statement_levels": None,
}

EXAM_ONLY = ("year", "exam_code", "part", "question_no", "topic", "type", "exam_kind", "level", "statement_levels")


# --- Chunk (D-003) ---------------------------------------------------------------------------------------------

def test_theory_chunk_round_trips():
    assert Chunk.from_dict(THEORY).to_dict() == THEORY


def test_exam_item_chunk_round_trips():
    assert Chunk.from_dict(EXAM_ITEM).to_dict() == EXAM_ITEM


@pytest.mark.parametrize("kind", ["theory", "exercise"])
def test_non_exam_chunks_drop_the_exam_only_fields(kind):
    d = Chunk.from_dict(THEORY | {"kind": kind, "year": 2025, "part": "I"}).to_dict()

    assert not set(EXAM_ONLY) & set(d)


def test_from_dict_ignores_unknown_keys_and_defaults_missing_exam_fields():
    c = Chunk.from_dict(THEORY | {"score": 0.9, "vector": [1, 2]})

    assert not hasattr(c, "score")
    assert all(getattr(c, k) is None for k in EXAM_ONLY)


def test_from_dict_without_a_required_field_raises():
    with pytest.raises(TypeError):
        Chunk.from_dict({k: v for k, v in THEORY.items() if k != "text"})


def test_to_dict_is_json_serializable_and_keeps_vietnamese():
    text = json.dumps(Chunk.from_dict(EXAM_ITEM).to_dict(), ensure_ascii=False)

    assert json.loads(text) == EXAM_ITEM


def test_to_dict_returns_a_copy():
    c = Chunk.from_dict(THEORY)
    c.to_dict()["text"] = "changed"

    assert c.text == THEORY["text"]


# --- hand-off types --------------------------------------------------------------------------------------------

def test_vector_is_frozen():
    v = Vector(dense=[0.1], sparse={1: 0.5})

    with pytest.raises(dataclasses.FrozenInstanceError):
        v.dense = []


def test_verification_is_frozen_and_reason_defaults_to_none():
    v = Verification("verified", "1", "1")

    assert v.reason is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.status = "mismatch"


def test_retrieved_unpacks_like_a_tuple_and_names_its_parts():
    theory, exam_items = Retrieved(["t"], ["e"])

    assert (theory, exam_items) == (["t"], ["e"])
    assert Retrieved(["t"], ["e"]).exam_items == ["e"]


def test_generation_result_unpacks_like_the_v1_contract():
    valid, rejected = GenerationResult([{"stem": "q"}], [])

    assert valid == [{"stem": "q"}] and rejected == []
    assert GenerationResult([], [{"question": {}, "errors": ["x"]}]).rejected[0]["errors"] == ["x"]


def test_generation_result_equals_the_plain_tuple_the_backend_compares_with():
    assert GenerationResult([], []) == ([], [])
