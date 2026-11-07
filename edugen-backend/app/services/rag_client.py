"""RAG thật chạy trong cùng process với BE (`app.rag`), hiện thực QuestionGenerator của domain.

Không còn RAG service HTTP: BE gọi thẳng `app.rag.pipeline.make_generator()` (Qdrant cục bộ
`qdrant_data/`, bộ nhúng theo `make_embedder()` (Gemini mặc định, bge-m3 nếu EMBEDDER=bge-m3), LLM theo `make_llm()`). Module này nối hai hợp đồng:

- Ô BE (`app/domain/cell.py`, chủ đề là tên chương tiếng Việt) → ô RAG D-008
  (`app/rag/dto.py`, chủ đề là mã `mạch/chủ_đề`).
- Câu RAG D-008 (khóa tiếng Anh) → câu dạng BE (`app/domain/question.py`, khóa tiếng Việt
  không dấu) để BE kiểm lại cấu trúc như trước; ngược lại khi GV sửa câu thì gửi RAG kiểm.

Qdrant cục bộ khóa thư mục index, nên mỗi process chỉ dựng RAG một lần (`local_rag`).
Dựng không được (chưa có index, thiếu GEMINI_API_KEY hoặc chưa cài bge-m3, index dựng bằng bộ nhúng khác, chưa có LLM) thì mỗi ô báo lỗi kèm lý do,
không làm kẹt job sinh đề. Sửa xong (vd. chép index vào) thì khởi động lại BE.
"""

import dataclasses
import logging
import tempfile
import threading
import uuid
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.errors import LLMError
from app.domain.cell import Cell
from app.domain.question import (
    LEVEL_FROM_RAG,
    LEVEL_TO_RAG,
    OPTION_LETTERS,
    TRUE_FALSE_MARKS,
    TYPE_FROM_RAG,
    TYPE_TO_RAG,
    Question,
)
from app.domain.topics import find_topic, topic_grade, topic_list_name
from app.models.enums import Level, QuestionType
from app.rag.checking.validate import validate as rag_validate
from app.rag.chunking import chunk_file
from app.rag.dto import Chunk, GenerationResult
from app.rag.generation.llm import LLMError as RagLLMError
from app.rag.pipeline import make_generator

if TYPE_CHECKING:
    from app.services.rag_mock import SampleRag

log = logging.getLogger("edugen.rag")

STATEMENT_LABELS = "abcd"
INGEST_UNSUPPORTED = (
    "RAG chưa đọc được file PDF/DOCX tải lên (chưa tách được từng câu hỏi); "
    "hiện chỉ nạp được đề trong ngân hàng và đề dạng JSON (python -m app.rag.ingest)"
)
LOST_JOB = "BE đã khởi động lại trước khi báo kết quả nạp; hãy nạp lại"

RagGenerate = Callable[[dict[str, Any]], GenerationResult]
RagIndex = Callable[[list[Chunk]], None]
RagDelete = Callable[[str, str | None], None]


# ----- ô BE → ô RAG -----


def to_rag_cell(cell: Cell) -> dict[str, Any]:
    """Tên chương trên ma trận → mã chủ đề RAG; không có mã thì ô đó lỗi (không đoán)."""
    topic = find_topic(cell.topic, grade=cell.grade, subject=cell.subject)
    if topic is None:
        raise LLMError(f"Chủ đề '{cell.topic}' chưa có mã trong {topic_list_name(cell.subject)}, RAG không tìm được")
    rag_cell: dict[str, Any] = {
        "subject": cell.subject,
        # lớp của chương, không phải của ma trận: đề lớp 12 hỏi cả chương lớp 11 và lý thuyết
        # RAG chỉ lọc theo lớp (không theo chủ đề), nên lớp 12 sẽ kéo về SGK 12 không liên quan
        "grade": topic_grade(topic, cell.grade),
        "topic": f"{topic.strand}/{topic.code}",
        "type": cell.type.value,
        "level": cell.level.value,
        "count": cell.count,
    }
    if cell.statement_levels is not None:
        rag_cell["statement_levels"] = [lv.value for lv in cell.statement_levels]
    if cell.content_unit:  # đơn vị kiến thức chỉ để prompt sinh câu đúng phần, không lọc truy xuất
        rag_cell["content_unit"] = cell.content_unit
    if cell.statement_units is not None:
        rag_cell["statement_units"] = list(cell.statement_units)
    if cell.school_id:
        rag_cell["school_id"] = cell.school_id
    if cell.teacher_id:
        rag_cell["teacher_id"] = cell.teacher_id
    if cell.exam_kind:
        rag_cell["exam_kind"] = cell.exam_kind
    if cell.previous_stems:
        rag_cell["previous_stems"] = list(cell.previous_stems)
    return rag_cell


# ----- câu RAG (D-008) ↔ câu dạng BE -----


def _enum_value(enum_cls: type, value: Any) -> Any:
    try:
        return enum_cls(value)
    except ValueError:
        return None


def from_rag_question(q: Any) -> Any:
    """Câu RAG → dạng BE cho parse_question; giá trị lạ giữ nguyên để parse_question báo lỗi."""
    if not isinstance(q, dict):
        return q
    type_ = _enum_value(QuestionType, q.get("type"))
    level = _enum_value(Level, q.get("level"))
    raw: dict[str, Any] = {
        "dang": TYPE_TO_RAG.get(type_, q.get("type")),
        "muc_do": LEVEL_TO_RAG.get(level, q.get("level")),
        "de_bai": q.get("stem"),
        "dap_an": q.get("answer"),
        "loi_giai": q.get("explanation"),
        "trich_dan": list(q.get("source_chunk_ids") or []),
        "kiem_tra": q.get("sympy"),
    }
    options = q.get("options")
    if options is not None:
        raw["phuong_an"] = [options.get(k) for k in OPTION_LETTERS] if isinstance(options, dict) else options
    statements = q.get("statements")
    if isinstance(statements, list) and all(isinstance(s, dict) for s in statements):
        raw["y_dung_sai"] = [{"noi_dung": s.get("text"), "dung": s.get("answer"), "giai_thich": ""} for s in statements]
        raw["dap_an"] = "".join(TRUE_FALSE_MARKS.get(s.get("answer"), "?") for s in statements)
    elif statements is not None:
        raw["y_dung_sai"] = statements
    for rag_key, be_key in (("figure", "hinh"), ("table", "bang")):
        if q.get(rag_key):
            raw[be_key] = q[rag_key]
    return raw


def _chunk_id(citation: Any) -> Any:
    if isinstance(citation, dict):
        return citation.get("id") or citation.get("chunk_id")
    return citation


def to_rag_question(raw: dict[str, Any]) -> dict[str, Any]:
    """Câu dạng BE (GV vừa sửa, qua domain.to_rag) → câu RAG D-008 để RAG kiểm."""
    type_ = TYPE_FROM_RAG.get(raw.get("dang"))
    level = LEVEL_FROM_RAG.get(raw.get("muc_do"))
    q: dict[str, Any] = {
        "type": type_.value if type_ else raw.get("dang"),
        "level": level.value if level else raw.get("muc_do"),
        "stem": raw.get("de_bai"),
        "explanation": raw.get("loi_giai"),
        "source_chunk_ids": [_chunk_id(c) for c in raw.get("trich_dan") or []],
    }
    options = raw.get("phuong_an")
    if isinstance(options, list):
        q["options"] = dict(zip(OPTION_LETTERS, options, strict=False))
    items = raw.get("y_dung_sai")
    if isinstance(items, list):
        q["statements"] = [
            {"label": label, "text": i.get("noi_dung"), "answer": i.get("dung")} if isinstance(i, dict) else i
            for label, i in zip(STATEMENT_LABELS, items, strict=False)
        ]  # fmt: skip
    else:
        q["answer"] = raw.get("dap_an")
    return q


# ----- adapter -----


class LocalRag:
    """QuestionGenerator + Ingester của BE, gọi RAG trong cùng process.

    `index` ghi đoạn vào Qdrant bằng đúng client + bộ nhúng của đường sinh câu (Qdrant cục bộ chỉ
    cho một client mỗi process). Nạp chạy đồng bộ: caller đã là job nền (BackgroundTasks) nên
    `ingest` về là xong; job_id chỉ để `ingest_status` trả "done" cho đến khi BE khởi động lại.
    """

    def __init__(self, generate: RagGenerate, index: RagIndex | None = None, delete: RagDelete | None = None) -> None:
        self._generate = generate
        self._index = index
        self._delete = delete
        self._done: set[str] = set()

    def delete(self, school_id: str, source: str | None = None) -> None:
        """T-046: xoá đoạn của trường (hoặc một đề mẫu của trường) khỏi Qdrant; đoạn dùng chung không bao giờ bị xoá."""
        if self._delete is None:
            raise LLMError("RAG chưa sẵn sàng để xoá dữ liệu")
        try:
            self._delete(school_id, source)
        except Exception as exc:
            log.exception("xoá dữ liệu RAG của trường %s lỗi", school_id)
            raise LLMError(f"RAG lỗi khi xoá dữ liệu khỏi chỉ mục: {exc}") from exc

    def generate(self, cell: Cell) -> tuple[list[Question], list[Question]]:
        rag_cell = to_rag_cell(cell)
        try:
            result = self._generate(rag_cell)
        except RagLLMError as exc:
            raise LLMError(f"RAG lỗi khi sinh câu: {exc}") from exc
        valid = [from_rag_question(q) for q in result.valid]
        rejected = [{"question": from_rag_question(r["question"]), "errors": r["errors"]} for r in result.rejected]
        return valid, rejected

    def validate(self, question: Question, cell: Cell | None) -> list[str]:
        """Câu GV sửa: chỉ kiểm định dạng + có trích dẫn (retrieved_ids None = GV sửa);
        không đòi biểu thức SymPy vì GV không viết được."""
        return rag_validate(to_rag_question(question), None)

    def ingest(self, data: bytes, filename: str, meta: dict[str, Any]) -> str:
        """Đề JSON (đúng định dạng app.rag.chunking.exam) → cắt, nhúng, ghi Qdrant."""
        if Path(filename).suffix.lower() != ".json":
            raise LLMError(INGEST_UNSUPPORTED)
        if self._index is None:
            raise LLMError("RAG chưa sẵn sàng để nạp đề")
        chunks = self._chunk(data, filename, meta)
        try:
            self._index(chunks)
        except Exception as exc:
            log.exception("nạp %s vào RAG lỗi", filename)
            raise LLMError(f"RAG lỗi khi ghi đề vào chỉ mục: {exc}") from exc
        job_id = f"local-{uuid.uuid4()}"
        self._done.add(job_id)
        return job_id

    def ingest_status(self, job_id: str) -> tuple[str, str | None]:
        if job_id in self._done:
            return "done", None
        return "failed", LOST_JOB

    @staticmethod
    def _chunk(data: bytes, filename: str, meta: dict[str, Any]) -> list[Chunk]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / Path(filename).name  # chunk_exam lấy tên file làm nguồn + id đoạn
            path.write_bytes(data)
            try:
                chunks = chunk_file(path)
            except (ValueError, KeyError, TypeError, AttributeError) as exc:  # JSON hỏng/thiếu khóa
                raise LLMError(f"File JSON đề không đúng định dạng RAG đọc được: {exc!r}") from exc
        return [dataclasses.replace(c, **_meta_overrides(meta)) for c in chunks]


def _meta_overrides(meta: dict[str, Any]) -> dict[str, Any]:
    """Trường của đoạn lấy từ meta BE gửi kèm file."""
    overrides: dict[str, Any] = {}
    if isinstance(meta.get("grade"), int):  # chunk_exam mặc định lớp 12; đề ngân hàng có lớp riêng
        overrides["grade"] = meta["grade"]
    if meta.get("school_id"):  # RBAC: đề trường tải lên chỉ trường đó truy xuất được
        overrides["school_id"] = meta["school_id"]
    if meta.get("teacher_id"):  # đề mẫu GV tự tải: chỉ GV đó truy xuất được
        overrides["teacher_id"] = meta["teacher_id"]
    # T-050: JSON của đề GV tải lên do LLM hoặc GV viết; bản ghi quyết định môn, official, loại đề.
    if meta.get("subject"):
        overrides["subject"] = meta["subject"]
    if isinstance(meta.get("official"), bool):
        overrides["official"] = meta["official"]
    if meta.get("exam_kind"):
        overrides["exam_kind"] = meta["exam_kind"]
    return overrides


def make_index(client: Any, embedder: Any) -> RagIndex:
    """Ghi đoạn vào Qdrant; nạp lại một file thì xóa đoạn cũ của file đó trước (đề bớt câu không còn đoạn thừa)."""
    from qdrant_client import models

    from app.rag.storage.qdrant import COLLECTION, index_chunks

    def index(chunks: list[Chunk]) -> None:
        sources = sorted({c.source for c in chunks})
        if sources and client.collection_exists(COLLECTION):
            client.delete(
                COLLECTION,
                points_selector=models.FilterSelector(filter=models.Filter(must=[
                    models.FieldCondition(key="source", match=models.MatchAny(any=sources))
                ])),
            )  # fmt: skip
        index_chunks(client, chunks, embedder)

    return index


def _build_rag() -> tuple[RagGenerate, RagIndex, RagDelete]:
    """Bản thật: Qdrant cục bộ + make_embedder() (Gemini mặc định, D-011) + make_llm(). Nặng (nạp model), chỉ gọi một lần.

    Client và embedder dùng chung cho sinh câu và nạp đề (Qdrant cục bộ khóa thư mục index).
    Thiếu LLM chỉ làm sinh câu lỗi, nạp đề không cần LLM nên vẫn chạy.
    """
    from app.rag.embedding import make_embedder
    from app.rag.storage.qdrant import check_index, default_client

    client, embedder = default_client(), make_embedder()
    check_index(client, embedder)  # an index built for the other embedder would retrieve nonsense silently
    return wire_rag(client, embedder)


class _Locked:
    """Proxy: mỗi lời gọi method của client/embedder giữ khóa chung (RLock nên lồng nhau được)."""

    def __init__(self, target: Any, lock: Any) -> None:
        self._target, self._lock = target, lock

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        def call(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                return attr(*args, **kwargs)

        return call


def wire_rag(client: Any, embedder: Any, llm: Any = None) -> tuple[RagGenerate, RagIndex, RagDelete]:
    """Nối sinh câu và nạp đề trên cùng client + embedder.

    Qdrant cục bộ và bộ nhúng không an toàn khi hai luồng dùng cùng lúc (sinh câu và job nạp nền),
    nên mọi truy cập embed/Qdrant đi qua proxy có khóa; cả một lần nạp giữ khóa liền (xóa đoạn cũ
    + embed + ghi). Khóa chỉ che generate + nạp đề của BE trong process này.
    Lời gọi LLM nằm ngoài proxy nên không giữ khóa. Thiếu LLM chỉ làm sinh câu lỗi.
    """
    from app.rag.storage.qdrant import COLLECTION, INDEX, delete_school_points

    lock = threading.RLock()
    locked_client, locked_embedder = _Locked(client, lock), _Locked(embedder, lock)
    reindex = make_index(locked_client, locked_embedder)

    def index(chunks: list[Chunk]) -> None:
        with lock:
            reindex(chunks)

    def delete(school_id: str, source: str | None = None) -> None:
        with lock:
            delete_school_points(client, school_id, source)

    try:
        make = make_generator(locked_client, locked_embedder, llm)
    except Exception as exc:  # noqa: BLE001 – thiếu LLM: sinh câu báo lỗi từng ô
        reason = f"RAG chưa sinh câu được: {exc}. Sửa xong thì khởi động lại BE."
        log.error(reason)

        def make(_cell: dict[str, Any]) -> GenerationResult:
            raise LLMError(reason)

    def generate(cell: dict[str, Any]) -> GenerationResult:
        if not locked_client.collection_exists(COLLECTION):  # chưa nạp gì: ô báo lỗi, nạp xong thì sinh được ngay
            raise LLMError(f"RAG chưa có index '{COLLECTION}' trong {INDEX}: nạp đề vào ngân hàng hoặc chép qdrant_data/")
        return make(cell)

    return generate, index, delete


@lru_cache(maxsize=1)
def local_rag() -> LocalRag:
    try:
        generate, index, delete = _build_rag()
    except Exception as exc:  # noqa: BLE001 – thiếu bộ nhúng/index: báo ở từng ô và khi nạp, không làm kẹt job
        reason = f"RAG chưa chạy được: {exc}. Sửa xong thì khởi động lại BE."
        log.error(reason)

        def generate(_cell: dict[str, Any]) -> GenerationResult:
            raise LLMError(reason)

        def index(_chunks: list[Chunk]) -> None:
            raise LLMError(reason)

        def delete(_school_id: str, _source: str | None = None) -> None:
            raise LLMError(reason)

    return LocalRag(generate, index, delete)


_BUILD_LOCK = threading.Lock()  # job nền chạy song song: không mở Qdrant hai lần


def get_rag_client() -> "LocalRag | SampleRag":
    """Dependency cho FastAPI; RAG_MOCK_SAMPLES chỉ dùng cho test và dev_server."""
    if settings.rag_mock_samples:
        from app.services.rag_mock import SampleRag

        return SampleRag.from_file(settings.rag_mock_samples)
    with _BUILD_LOCK:
        return local_rag()


def warm_up() -> None:
    """Dựng RAG sớm (gọi từ luồng nền lúc startup); lỗi chỉ cảnh báo, request vẫn tự báo lỗi như cũ."""
    try:
        get_rag_client()
    except Exception as exc:  # noqa: BLE001 – không để warm-up làm sập app
        log.warning("Warm-up RAG thất bại: %s", exc)
