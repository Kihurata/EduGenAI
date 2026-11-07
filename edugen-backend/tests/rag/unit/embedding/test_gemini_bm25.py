"""Tóm tắt: unit test bộ nhúng Gemini embedding + BM25 (T-048, D-011) với client Gemini giả, không gọi API: mỗi đoạn gửi một Content riêng, đúng model, số chiều và task_type cho tài liệu / truy vấn, chia lô, báo lỗi khi API trả thiếu vector; trọng số BM25 (âm tiết + cặp âm tiết); make_embedder chọn bộ nhúng theo biến EMBEDDER."""

import sys
import types

import pytest

from app.rag.dto import Vector
from app.rag.embedding import make_embedder
from app.rag.embedding.gemini_bm25 import GeminiBm25Embedder, bm25_document, bm25_query, token_id, tokens


class FakeModels:
    def __init__(self, drop=0):
        self.calls, self.drop = [], drop

    def embed_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        n = len(contents) - self.drop
        return types.SimpleNamespace(embeddings=[types.SimpleNamespace(values=[float(i), 0.5]) for i in range(n)])


def embedder(drop=0):
    return GeminiBm25Embedder(client=types.SimpleNamespace(models=FakeModels(drop)))


def _texts(call):
    return [c.parts[0].text for c in call["contents"]]


# --- BM25 ---------------------------------------------------------------------------------------------------

def test_tokens_are_lowercase_syllables_plus_adjacent_pairs():
    assert tokens("Cực trị hàm số") == ["cực", "trị", "hàm", "số", "cực trị", "trị hàm", "hàm số"]


def test_a_repeated_term_weighs_more_and_every_weight_is_positive():
    doc = bm25_document("tiệm cận tiệm cận đứng")

    assert doc[token_id("tiệm")] > doc[token_id("đứng")] > 0


def test_query_weights_each_distinct_token_once_with_ids_shared_with_documents():
    q = bm25_query("tiệm cận tiệm cận")

    assert set(q.values()) == {1.0}
    assert set(q) == {token_id("tiệm"), token_id("cận"), token_id("tiệm cận"), token_id("cận tiệm")}
    assert set(q) <= set(bm25_document("tiệm cận tiệm cận đứng"))


# --- Gemini calls -------------------------------------------------------------------------------------------

def test_documents_go_one_content_each_with_the_document_task_type():
    e = embedder()

    out = e.embed(["a b", "c"])

    [call] = e.client.models.calls
    assert call["model"] == "gemini-embedding-001"
    assert _texts(call) == ["a b", "c"]  # a plain list of strings would come back as ONE vector (T-047)
    assert call["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert call["config"].output_dimensionality == 1024
    assert [v.dense for v in out] == [[0.0, 0.5], [1.0, 0.5]]
    assert out[0].sparse == bm25_document("a b")


def test_a_query_uses_the_query_task_type_and_query_weights():
    e = embedder()

    v = e.embed_query("cực trị")

    assert e.client.models.calls[0]["config"].task_type == "RETRIEVAL_QUERY"
    assert isinstance(v, Vector) and v.sparse == bm25_query("cực trị")


def test_large_inputs_are_sent_in_batches_of_at_most_100():
    e = embedder()

    out = e.embed([f"t{i}" for i in range(250)])

    assert [len(c["contents"]) for c in e.client.models.calls] == [100, 100, 50]
    assert len(out) == 250


def test_fewer_vectors_than_texts_fails_loudly():
    with pytest.raises(ValueError, match="1 vectors for 2 texts"):
        embedder(drop=1).embed(["a", "b"])


def test_empty_input_makes_no_call():
    e = embedder()

    assert e.embed([]) == [] and e.client.models.calls == []


def test_the_sparse_side_needs_idf_from_qdrant():
    assert embedder().sparse_idf is True


# --- choosing the embedder ------------------------------------------------------------------------------------

def test_gemini_is_the_default(monkeypatch):
    monkeypatch.delenv("EMBEDDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")  # genai.Client only stores it; no call is made

    assert isinstance(make_embedder(), GeminiBm25Embedder)


def test_bge_m3_can_still_be_chosen(monkeypatch):
    class FakeModel:
        def __init__(self, name, use_fp16):
            pass

    monkeypatch.setitem(sys.modules, "FlagEmbedding", types.SimpleNamespace(BGEM3FlagModel=FakeModel))
    monkeypatch.setenv("EMBEDDER", "bge-m3")
    from app.rag.embedding.bge_m3 import BgeM3Embedder

    assert isinstance(make_embedder(), BgeM3Embedder)


def test_an_unknown_embedder_name_fails_loudly(monkeypatch):
    monkeypatch.setenv("EMBEDDER", "bge3")

    with pytest.raises(ValueError, match="unknown EMBEDDER 'bge3'"):
        make_embedder()
