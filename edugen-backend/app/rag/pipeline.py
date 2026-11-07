"""Tóm tắt: luồng sinh câu cho một ô ma trận (T-010): truy xuất (storage) → sinh câu (generation) → kiểm tra (checking); trả về câu hợp lệ và câu bị loại kèm lý do. `make_generator` cho Backend một hàm `generate(cell)` dùng ngay (T-028) và là nơi duy nhất chọn bản thật của Qdrant, bộ nhúng (make_embedder) và LLM. Spike T-036: rag=False là nhánh A (không tài liệu, nguồn ghi tự do nên không kiểm tra trích dẫn); exclude_year, format_examples và previous_stems (đề bài đã có trong đề, chống lặp) dùng cho cả hai nhánh."""

import re
from difflib import SequenceMatcher

from app.rag.checking import check
from app.rag.dto import Cell, GenerationResult
from app.rag.embedding import Embedder
from app.rag.generation.generate import generate, shown_exam_items, system_prompt
from app.rag.generation.llm import LLM, LLMError
from app.rag.storage.qdrant import default_client
from app.rag.storage.retrieve import retrieve


def generate_for_cell(client, embedder: Embedder, cell: Cell, llm: LLM, rag=True, exclude_year=None,
                      format_examples=(), previous_stems=()) -> GenerationResult:
    """-> (valid questions, rejected [{"question", "errors"}])."""
    if rag:
        theory, exam_items = retrieve(client, embedder, cell, exclude_year=exclude_year)
        retrieved_ids = {c.id for c in theory + shown_exam_items(cell, exam_items)}
        if not retrieved_ids:  # nothing to cite: an LLM call would only come back as "no source_chunk_ids"
            raise LLMError(f"Không tìm thấy nội dung SGK hay câu đề mẫu cho chủ đề {cell['topic']} "
                           f"(môn {cell['subject']}); kiểm tra chỉ mục Qdrant đã nạp tài liệu chưa")
    else:
        theory, exam_items, retrieved_ids = [], [], None  # None: the free-form source isn't checked
    system = system_prompt(cell["subject"], rag)

    def ask(c):
        questions = generate(c, theory, exam_items, llm, system=system, format_examples=format_examples,
                             previous_stems=previous_stems)
        return _checked(questions, retrieved_ids)

    valid, rejected = ask(cell)
    if toxic := sum(any(e.startswith("toxic_content") for e in r["errors"]) for r in rejected):
        more_valid, more_rejected = ask(cell | {"count": toxic})  # T-038: asked for again once, no loop
        valid, rejected = valid + more_valid, rejected + more_rejected
    valid, repeats = _drop_repeats(valid, previous_stems)
    return GenerationResult(valid, rejected + repeats)


REPEAT = "repeats a question already in the exam"
_LONG_STEM = 30  # shorter stems ("Tính $f'(1)$.") differ by one character, so only identical ones are repeats


def _drop_repeats(valid, previous_stems):
    """BUG-005: cells are generated one by one, so a question may repeat one already in the exam or in this reply."""
    seen = [_plain(s) for s in previous_stems]
    kept, repeats = [], []
    for q in valid:
        stem = _plain(q.get("stem") or "")
        if any(stem == s or (min(len(stem), len(s)) >= _LONG_STEM and SequenceMatcher(None, stem, s).ratio() >= 0.9)
               for s in seen):
            repeats.append({"question": q, "errors": [REPEAT]})
        else:
            kept.append(q)
            seen.append(stem)
    return kept, repeats


def _plain(stem):
    """Lower case without spaces or $: options shuffled or spacing changed still reads as the same stem."""
    return re.sub(r"[\s$]", "", stem.lower())


def _checked(questions, retrieved_ids) -> GenerationResult:
    valid, rejected = [], []
    for q in questions:
        if errors := check(q, retrieved_ids):
            rejected.append({"question": q, "errors": errors})
        else:
            valid.append(q)
    return GenerationResult(valid, rejected)


def make_generator(client=None, embedder: Embedder | None = None, llm: LLM | None = None):
    """-> generate(cell) for the Backend; defaults: the local qdrant_data/ index, make_embedder() and make_llm()."""
    if client is None:
        client = default_client()
    if embedder is None:
        from app.rag.embedding import make_embedder
        from app.rag.storage.qdrant import check_index, warn_if_empty
        embedder = make_embedder()
        check_index(client, embedder)
        warn_if_empty(client)
    if llm is None:
        from app.rag.generation.llm import make_llm
        llm = make_llm()
    return lambda cell: generate_for_cell(client, embedder, cell, llm, previous_stems=cell.get("previous_stems", ()))
