"""Gửi tài liệu cho RAG học (đề mẫu, đề trong ngân hàng) và theo dõi trạng thái ingest.

pending → sent (RAG nhận, trả job_id) → ingested | failed. Trạng thái sent được hỏi lại RAG
mỗi khi admin xem bản ghi.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.errors import LLMError
from app.models.enums import IngestStatus

RAG_STATUS = {"done": IngestStatus.ingested, "failed": IngestStatus.failed}


class Ingester(Protocol):
    def ingest(self, data: bytes, filename: str, meta: dict[str, Any]) -> str: ...

    def ingest_status(self, job_id: str) -> tuple[str, str | None]: ...


class RagDeleter(Protocol):
    def delete(self, school_id: str, source: str | None = None) -> None: ...  # T-046


@dataclass(frozen=True)
class IngestResult:
    status: IngestStatus
    job_id: str | None = None
    error: str | None = None


def start_ingest(
    rag: Ingester, data: bytes, filename: str, meta: dict[str, Any], what: str
) -> IngestResult:
    """Gửi file; RAG lỗi → failed kèm thông báo cho admin."""
    try:
        return IngestResult(IngestStatus.sent, job_id=rag.ingest(data, filename, meta))
    except LLMError as exc:
        return IngestResult(IngestStatus.failed, error=f"Không gửi được {what} cho RAG: {exc}")


def poll_ingest(
    rag: Ingester, status: IngestStatus, job_id: str | None, what: str
) -> IngestResult | None:
    """Hỏi RAG khi đang sent; None = giữ nguyên (chưa gửi, đã xong, hoặc RAG lỗi tạm thời)."""
    if status is not IngestStatus.sent or not job_id:
        return None
    try:
        rag_status, error = rag.ingest_status(job_id)
    except LLMError:
        return None
    new_status = RAG_STATUS.get(rag_status, IngestStatus.sent)
    if new_status is IngestStatus.failed:
        return IngestResult(new_status, job_id, f"RAG không học được {what}: {error or 'không rõ lỗi'}")
    return IngestResult(new_status, job_id)
