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

    def ask(c, stems, feedback=()):
        questions = generate(c, theory, exam_items, llm, system=system, format_examples=format_examples,
                             previous_stems=stems, feedback=feedback)
        valid, rejected = _checked(questions, retrieved_ids)
        valid, repeats = _drop_repeats(valid, stems)
        return valid, rejected + repeats

    valid, rejected = ask(cell, tuple(previous_stems))
    if rejected and (missing := cell.get("count", 1) - len(valid)) > 0:
        # T-038, widened to every rejection: the missing ones are asked for again once (no loop), with the reasons
        # they failed and the stems kept so far, so the replacements neither repeat the mistakes nor the questions.
        kept = (*previous_stems, *(q.get("stem") or "" for q in valid))
        more_valid, more_rejected = ask(cell | {"count": missing}, kept, feedback=_reasons(rejected))
        valid, rejected = valid + more_valid, rejected + more_rejected
    return GenerationResult(valid, rejected)


def _reasons(rejected):
    """Why the questions were rejected, once each; a toxic one's words are not sent back to the LLM."""
    reasons = ("offensive or unsuitable wording" if e.startswith("toxic_content") else e
               for r in rejected for e in r["errors"])
    return tuple(dict.fromkeys(reasons))


REPEAT = "repeats a question already in the exam"
_LONG_STEM = 30  # shorter stems ("Tính $f'(1)$.") differ by one character, so only identical ones are repeats
_MATH = re.compile(r"\$[^$]*\$")


def _drop_repeats(valid, previous_stems):
    """BUG-005: cells are generated one by one, so a question may repeat one already in the exam or in this reply."""
    seen = [_stem_key(s) for s in previous_stems]
    kept, repeats = [], []
    for q in valid:
        key = _stem_key(q.get("stem") or "")
        if any(_same_question(key, s) for s in seen):
            repeats.append({"question": q, "errors": [REPEAT]})
        else:
            kept.append(q)
            seen.append(key)
    return kept, repeats


def _stem_key(stem):
    """(plain stem, its formulas): spacing or $ changes still read as the same stem."""
    return _plain(stem), tuple(_plain(m) for m in _MATH.findall(stem))


def _same_question(a, b):
    """Identical, or near-identical wording on the same formulas. Templated stems such as "Tiệm cận ngang của
    $y=\\frac{3x-2}{x+1}$" and "Tiệm cận đứng của $y=\\frac{3-x}{x+2}$" are 90% alike yet ask different things."""
    (stem, maths), (other, other_maths) = a, b
    if stem == other:
        return True
    return (maths == other_maths and min(len(stem), len(other)) >= _LONG_STEM
            and SequenceMatcher(None, stem, other).ratio() >= 0.9)


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
