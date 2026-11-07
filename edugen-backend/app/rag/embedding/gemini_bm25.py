"""Tóm tắt: bộ nhúng Gemini embedding + BM25 (T-048, D-011): vector dense 1024 chiều từ API gemini-embedding-001 (task_type khác nhau cho tài liệu và truy vấn), vector sparse BM25 tự tính theo âm tiết và cặp âm tiết; IDF do Qdrant tính (sparse_idf). Không cần torch hay tải model."""

import itertools
import re
import zlib
from collections import Counter

from app.rag.dto import Vector

MODEL = "gemini-embedding-001"
DIM = 1024  # same as bge-m3, so DENSE_DIM stays
BATCH = 100  # Gemini batch embedding limit per request
K1, B = 1.2, 0.75
# shortcut: fixed average document length (tokens incl. pairs) of the 391-chunk Toán index (T-047); recompute if the corpus changes a lot.
AVG_LEN = 464


def tokens(text):
    words = re.findall(r"\w+", text.lower())
    return words + [f"{a} {b}" for a, b in itertools.pairwise(words)]


def token_id(token):
    return zlib.crc32(token.encode("utf-8")) & 0x7FFFFFFF


def bm25_document(text):
    tf = Counter(token_id(t) for t in tokens(text))
    n = sum(tf.values())
    return {i: f * (K1 + 1) / (f + K1 * (1 - B + B * n / AVG_LEN)) for i, f in tf.items()}


def bm25_query(text):
    return {token_id(t): 1.0 for t in set(tokens(text))}


class GeminiBm25Embedder:
    sparse_idf = True  # BM25 weights need Qdrant's IDF modifier on the sparse vector

    def __init__(self, client=None, model=MODEL):
        if client is None:
            from google import genai
            client = genai.Client()  # reads GEMINI_API_KEY
        self.client, self.model = client, model

    def embed(self, texts):
        dense = self._dense(texts, "RETRIEVAL_DOCUMENT")
        return [Vector(dense=d, sparse=bm25_document(t)) for d, t in zip(dense, texts)]

    def embed_query(self, text):
        [dense] = self._dense([text], "RETRIEVAL_QUERY")
        return Vector(dense=dense, sparse=bm25_query(text))

    def _dense(self, texts, task_type):
        from google.genai import types

        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=DIM)
        out = []
        for i in range(0, len(texts), BATCH):
            batch = texts[i:i + BATCH]
            # One Content per text: a plain list of strings can come back as ONE merged vector (T-047).
            contents = [types.Content(parts=[types.Part(text=t)]) for t in batch]
            res = self.client.models.embed_content(model=self.model, contents=contents, config=config)
            if len(res.embeddings) != len(batch):
                raise ValueError(f"{self.model}: {len(res.embeddings)} vectors for {len(batch)} texts")
            out += [list(e.values) for e in res.embeddings]
        return out
