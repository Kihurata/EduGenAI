"""Tóm tắt: unit test bộ nhúng bge-m3 với mô hình giả (không tải torch): gọi mô hình đúng tham số, đổi kết quả thành Vector (dense list, sparse id số nguyên → trọng số), giữ thứ tự; bản giả FakeEmbedder dùng trong test có cùng hình dạng."""

import sys
import types

import numpy as np
import pytest

from app.rag.dto import Vector
from tests.rag.fakes import FakeEmbedder


class FakeModel:
    def __init__(self, name, use_fp16):
        self.name, self.use_fp16 = name, use_fp16
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        return {
            "dense_vecs": np.array([[float(i), 0.5] for i in range(len(texts))], dtype=np.float32),
            "lexical_weights": [{str(10 + i): np.float32(0.25 * (i + 1))} for i in range(len(texts))],
        }


@pytest.fixture
def embedder(monkeypatch):
    monkeypatch.setitem(sys.modules, "FlagEmbedding", types.SimpleNamespace(BGEM3FlagModel=FakeModel))
    from app.rag.embedding.bge_m3 import BgeM3Embedder

    return BgeM3Embedder()


def test_loads_bge_m3_in_full_precision(embedder):
    assert (embedder.model.name, embedder.model.use_fp16) == ("BAAI/bge-m3", False)


def test_asks_the_model_for_dense_and_sparse_vectors(embedder):
    embedder.embed(["a", "b"])

    assert embedder.model.calls == [(["a", "b"], {"return_dense": True, "return_sparse": True})]


def test_returns_one_vector_per_text_in_order(embedder):
    out = embedder.embed(["a", "b", "c"])

    assert [v.dense[0] for v in out] == [0.0, 1.0, 2.0]
    assert all(isinstance(v, Vector) for v in out)


def test_converts_numpy_values_to_plain_python_types(embedder):
    [v] = embedder.embed(["a"])

    assert v.dense == [0.0, 0.5] and all(type(x) is float for x in v.dense)
    assert v.sparse == {10: 0.25}
    assert all(type(k) is int and type(w) is float for k, w in v.sparse.items())


def test_empty_input_gives_no_vectors(embedder):
    assert embedder.embed([]) == []


def test_fake_embedder_has_the_same_shape():
    a, b, a2 = FakeEmbedder().embed(["a", "b", "a"])

    assert isinstance(a, Vector) and len(a.dense) == 1024 and a.sparse
    assert a == a2 and a != b  # deterministic, text-dependent


def test_a_query_is_embedded_like_a_document(embedder):
    assert embedder.embed_query("b") == embedder.embed(["b"])[0]


def test_bge_m3_sparse_weights_need_no_idf(embedder):
    assert getattr(embedder, "sparse_idf", False) is False
