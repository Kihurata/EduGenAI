"""BE nạp đề vào RAG ngay trong process: file JSON đề → chunk_file → embed → Qdrant.

Không nạp bge-m3, không mở Qdrant trên đĩa: dùng Qdrant ":memory:" và embedder giả.
File PDF/DOCX tải lên thì RAG chưa đọc được nên báo lỗi rõ.
"""

import json
import threading
from types import SimpleNamespace

import pytest
from qdrant_client import QdrantClient

from app.models.enums import IngestStatus
from app.rag.dto import GenerationResult
from app.rag.generation.llm import LLMError as RagLLMError
from app.rag.storage.qdrant import COLLECTION, index_chunks
from app.services import rag_client
from app.services.rag_client import LocalRag
from app.services.rag_ingest import poll_ingest, start_ingest
from tests.rag.fakes import FakeEmbedder
from tests.rag.support import cell, theory

DAO_HAM_OLD = "dai_so_giai_tich/dao_ham"
EXAM = {
    "id": "x", "exam": "Đề trường năm 2026", "subject": "toan", "ma_de": "ab12", "official": True,
    "questions": [
        {"part": "I", "cau": 1, "topic": "dai_so_giai_tich/dao_ham", "stem": "Tính $f'(x)$ của $x^2$.",
         "options": {"A": "$x$", "B": "$2x$", "C": "$x^2$", "D": "$2$"}, "answer": "B"},
        {"part": "III", "cau": 1, "topic": "", "stem": "Tính $1+1$.", "answer": "2"},
    ],
}  # fmt: skip
META = {"source": "exam_bank", "subject": "toan", "grade": 10, "title": "Đề trường"}
FILENAME = "exam_bank-1234.json"


def memory_rag():
    client = QdrantClient(":memory:")
    rag = LocalRag(
        lambda cell: GenerationResult([], []),
        index=lambda chunks: index_chunks(client, chunks, FakeEmbedder()),
    )
    return rag, client


def points(client):
    return [p.payload for p in client.scroll(COLLECTION, limit=100)[0]]


def test_exam_json_is_chunked_embedded_and_indexed():
    rag, client = memory_rag()
    result = start_ingest(rag, json.dumps(EXAM).encode(), FILENAME, META, "đề trong ngân hàng")
    assert result.status is IngestStatus.sent
    assert rag.ingest_status(result.job_id) == ("done", None)
    payloads = points(client)
    assert len(payloads) == 2
    assert {p["kind"] for p in payloads} == {"exam_item"}
    assert {p["source"] for p in payloads} == {FILENAME}  # nguồn nhận ra được là đề ngân hàng
    assert {p["grade"] for p in payloads} == {10}  # lớp lấy từ meta, không mặc định 12


def test_ingesting_the_same_exam_twice_does_not_duplicate_chunks():
    rag, client = memory_rag()
    for _ in range(2):
        rag.ingest(json.dumps(EXAM).encode(), FILENAME, META)
    assert len(points(client)) == 2


def test_poll_reports_done_after_ingest():
    rag, _ = memory_rag()
    job = rag.ingest(json.dumps(EXAM).encode(), FILENAME, META)
    result = poll_ingest(rag, IngestStatus.sent, job, "đề")
    assert result.status is IngestStatus.ingested


def test_unknown_job_is_failed_with_a_reason():
    rag, _ = memory_rag()
    status, error = rag.ingest_status("job-la")
    assert status == "failed"
    assert "khởi động lại" in error


@pytest.mark.parametrize("filename", ["de.pdf", "de.docx"])
def test_pdf_and_docx_are_clearly_unsupported(filename):
    rag, client = memory_rag()
    result = start_ingest(rag, b"PK", filename, META, "đề mẫu")
    assert result.status is IngestStatus.failed
    assert "PDF/DOCX" in result.error
    assert not client.collection_exists(COLLECTION)


def test_broken_json_fails_in_vietnamese():
    rag, _ = memory_rag()
    result = start_ingest(rag, b"{khong phai json", FILENAME, META, "đề")
    assert result.status is IngestStatus.failed
    assert "JSON" in result.error


def test_index_error_becomes_a_failed_ingest():
    def boom(chunks):
        raise RuntimeError("hết bộ nhớ")

    rag = LocalRag(lambda cell: GenerationResult([], []), index=boom)
    result = start_ingest(rag, json.dumps(EXAM).encode(), FILENAME, META, "đề")
    assert result.status is IngestStatus.failed
    assert "hết bộ nhớ" in result.error


def test_rag_that_cannot_start_reports_the_reason_on_ingest(monkeypatch):
    def no_index():
        raise RuntimeError("chưa cài bge-m3")

    monkeypatch.setattr(rag_client, "_build_rag", no_index)
    rag_client.local_rag.cache_clear()
    try:
        result = start_ingest(rag_client.local_rag(), json.dumps(EXAM).encode(), FILENAME, META, "đề")
    finally:
        rag_client.local_rag.cache_clear()
    assert result.status is IngestStatus.failed
    assert "chưa cài bge-m3" in result.error


# ----- đồng bộ truy cập Qdrant/embedder -----


WAIT = 5  # mọi chờ đều có hạn: hồi quy thì test fail chứ không treo


class GatedEmbedder(FakeEmbedder):
    """Lần embed được `gate()` đánh dấu sẽ dừng bên trong embed cho tới khi `release`."""

    def __init__(self):
        self.in_embed, self.release = threading.Event(), threading.Event()
        self.blocking = False
        self.active = 0
        self.overlaps = 0

    def gate(self):
        self.blocking = True

    def embed(self, texts):
        self.active += 1
        self.overlaps += self.active > 1
        try:
            if self.blocking:
                self.blocking = False
                self.in_embed.set()
                assert self.release.wait(WAIT)
            return super().embed(texts)
        finally:
            self.active -= 1


class GatedLLM:
    """LLM giả đứng chờ trong complete() cho tới khi `release`, rồi báo lỗi để generate dừng."""

    def __init__(self):
        self.in_llm, self.release = threading.Event(), threading.Event()

    def complete(self, system, prompt, **kwargs):
        self.in_llm.set()
        assert self.release.wait(WAIT)
        raise RagLLMError("dừng ở đây")


def real_wired(embedder, llm):
    """generate_for_cell + retrieve thật trên Qdrant :memory: và embedder giả, qua wire_rag."""
    client = QdrantClient(":memory:")
    index_chunks(client, [theory(1)], FakeEmbedder())  # retrieve cần có đoạn SGK thì mới tới LLM
    generate, index, _ = rag_client.wire_rag(client, embedder, llm)
    rag = LocalRag(generate, index)
    rag.ingest(json.dumps(EXAM).encode(), FILENAME, META)  # có collection thì generate mới chạy tới retrieve
    return rag


def run_in_thread(fn):
    done = threading.Event()
    errors = []

    def target():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        done.set()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, done, errors


def test_retrieve_waits_while_ingest_is_inside_embed():
    embedder, llm = GatedEmbedder(), GatedLLM()
    rag = real_wired(embedder, llm)
    embedder.gate()
    ingest, ingest_done, ingest_errors = run_in_thread(lambda: rag.ingest(json.dumps(EXAM).encode(), FILENAME, META))
    assert embedder.in_embed.wait(WAIT), ingest_errors  # nạp đang nằm trong embed
    _, retrieve_done, errors = run_in_thread(lambda: rag._generate(cell("multiple_choice", topic=DAO_HAM_OLD)))
    assert not retrieve_done.wait(0.3)  # retrieve (embed + query Qdrant) phải chờ
    embedder.release.set()
    assert ingest_done.wait(WAIT), ingest_errors
    assert llm.in_llm.wait(WAIT), errors  # nạp xong thì retrieve mới chạy tiếp, tới LLM
    llm.release.set()
    assert retrieve_done.wait(WAIT), errors
    ingest.join(WAIT)
    assert embedder.overlaps == 0
    assert [type(e) for e in errors] == [RagLLMError]


def test_slow_llm_call_does_not_hold_the_lock():
    llm = GatedLLM()
    rag = real_wired(GatedEmbedder(), llm)
    _, generate_done, errors = run_in_thread(lambda: rag._generate(cell("multiple_choice", topic=DAO_HAM_OLD)))
    assert llm.in_llm.wait(WAIT), errors  # retrieve đã xong, đang đợi LLM
    _, ingest_done, ingest_errors = run_in_thread(lambda: rag.ingest(json.dumps(EXAM).encode(), FILENAME, META))
    finished_during_llm = ingest_done.wait(WAIT) and not ingest_errors  # nạp xong trong lúc LLM còn chạy
    llm.release.set()
    assert generate_done.wait(WAIT), errors
    assert finished_during_llm
    assert [type(e) for e in errors] == [RagLLMError]


def test_locked_proxy_passes_non_callable_attributes_through():
    target = SimpleNamespace(dim=1024, name="x")
    proxy = rag_client._Locked(target, threading.RLock())
    assert (proxy.dim, proxy.name) == (1024, "x")


# ----- nạp lại đề ít câu hơn -----


def test_reingesting_a_shorter_exam_removes_stale_chunks():
    client = QdrantClient(":memory:")
    reindex = rag_client.make_index(client, FakeEmbedder())
    rag = LocalRag(lambda cell: GenerationResult([], []), index=reindex)
    rag.ingest(json.dumps(EXAM).encode(), FILENAME, META)
    shorter = EXAM | {"questions": EXAM["questions"][:1]}
    rag.ingest(json.dumps(shorter).encode(), FILENAME, META)
    assert len(points(client)) == 1
    other = EXAM | {"questions": EXAM["questions"][:1]}
    rag.ingest(json.dumps(other).encode(), "exam_bank-khac.json", META)
    assert len(points(client)) == 2  # đề khác không bị xóa


def test_school_upload_chunks_carry_the_school_id():
    rag, client = memory_rag()
    rag.ingest(json.dumps(EXAM).encode(), FILENAME, META | {"school_id": "s1"})
    assert {p["school_id"] for p in points(client)} == {"s1"}


def test_teacher_upload_chunks_carry_the_teacher_id():
    rag, client = memory_rag()
    rag.ingest(json.dumps(EXAM).encode(), FILENAME, META | {"school_id": "s1", "teacher_id": "u1"})
    assert {(p["school_id"], p["teacher_id"]) for p in points(client)} == {("s1", "u1")}


def test_upload_without_school_stays_shared():
    rag, client = memory_rag()
    rag.ingest(json.dumps(EXAM).encode(), FILENAME, META)
    assert all("school_id" not in p for p in points(client))


def test_uploaded_exam_takes_subject_official_and_kind_from_meta_not_from_its_json():
    """T-050: the JSON of a teacher upload is LLM- or teacher-written; the record decides these fields."""
    rag, client = memory_rag()
    meta = {"source": "sample_exam", "subject": "ly", "grade": 12, "title": "Thi thử", "school_id": "s-1",
            "official": False, "exam_kind": "tot_nghiep"}
    start_ingest(rag, json.dumps(EXAM).encode(), "sample-1.json", meta, "đề mẫu")  # EXAM says toan, official
    payloads = points(client)
    assert {(p["subject"], p["official"], p["exam_kind"], p["school_id"]) for p in payloads} == {
        ("ly", False, "tot_nghiep", "s-1")}


def test_TC_027_school_upload_without_ma_de_is_ingested():
    """T-055: bộ kiểm tra bản nháp không đòi mã đề, nên nạp cũng không được đòi (trước đây KeyError('ma_de'))."""
    rag, client = memory_rag()
    exam = {k: v for k, v in EXAM.items() if k != "ma_de"} | {"exam": "Đề kiểm tra giữa kì 2 Vật lí 12 trường X"}
    meta = {"source": "sample_exam", "subject": "ly", "grade": 12, "title": "GK2", "school_id": "s-1",
            "official": False, "exam_kind": "tot_nghiep"}
    result = start_ingest(rag, json.dumps(exam).encode(), "sample-2.json", meta, "đề mẫu")
    assert result.error is None and rag.ingest_status(result.job_id) == ("done", None)
    assert len(points(client)) == 2
