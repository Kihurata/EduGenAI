"""Ảnh/PDF ma trận → JSON bằng Gemini (D-014, D-016).

Gọi Gemini mất vài chục giây mỗi file nên chỉ gọi trong job nền (services/matrix_jobs.py). Unit test
dùng converter giả, không bao giờ gọi Gemini thật.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Annotated, Protocol

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.session import get_session_factory
from app.domain.matrix_reader import read_matrix
from app.models.matrix import MatrixConversion
from app.services.matrix_schema import MATRIX_SCHEMA, PROMPT

log = logging.getLogger(__name__)


class ConversionError(Exception):
    """Không đọc được file ma trận; thông báo hiển thị cho giáo viên."""


class MatrixConverter(Protocol):
    def convert(self, source: Path) -> str: ...


_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}

def _problems(text: str) -> list[str]:
    """Lỗi cấu trúc/tổng của kết quả; chủ đề chưa có mã là việc của GV nên không tính (gọi lại cũng không hơn)."""
    return [i.message for i in read_matrix(text).issues if "chưa có mã chủ đề" not in i.message]


class GeminiMatrixConverter:
    """Gửi ảnh/PDF ma trận cho Gemini, nhận JSON theo MATRIX_SCHEMA (D-016) để matrix_extract đọc. Không cần torch."""

    def __init__(self, model: str, client=None, timeout_seconds: float = 120, retry_model: str | None = None) -> None:
        self._client, self._timeout_seconds, self.model = client, timeout_seconds, model
        # Lần đọc lại dùng model mạnh hơn: bản lite hay lệch cột ở bảng nhiều phần/mức (vd Phần III chỉ có Hiểu, VD).
        self.retry_model = retry_model or model
        self.usage: list[dict] = []

    @property
    def client(self):
        """Dựng lúc đọc file, không phải lúc khởi tạo: thiếu khoá thì job báo lỗi cho GV thay vì upload trả 500."""
        if self._client is None:
            from google import genai

            try:
                self._client = genai.Client(http_options={"timeout": int(self._timeout_seconds * 1000)})
            except ValueError as exc:
                raise ConversionError("Máy chủ chưa cấu hình GEMINI_API_KEY để Gemini đọc ma trận") from exc
        return self._client
    def _ask(self, source: Path, mime: str, prompt: str, model: str | None = None) -> str:
        from google.genai import errors, types

        client = self.client  # ConversionError nếu thiếu khoá, không bị gói thành lỗi mạng bên dưới
        try:
            response = client.models.generate_content(
                model=model or self.model,
                contents=[types.Part.from_bytes(data=source.read_bytes(), mime_type=mime), prompt],
                config={"temperature": 0, "max_output_tokens": 32768, "response_mime_type": "application/json",
                        "response_schema": MATRIX_SCHEMA},
            )  # fmt: skip
        except errors.APIError as exc:
            raise ConversionError(f"Gemini không đọc được ma trận: {exc}") from exc
        except Exception as exc:  # timeouts/network errors come from httpx; show one message
            raise ConversionError(f"Gemini không phản hồi: {type(exc).__name__}") from exc
        u = response.usage_metadata
        if u is not None:
            self.usage.append({"input_tokens": u.prompt_token_count, "output_tokens": u.candidates_token_count,
                               "thinking_tokens": u.thoughts_token_count or 0})  # fmt: skip
        try:
            if not json.loads(response.text or "")["rows"]:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise ConversionError("Gemini không trả về ma trận") from None
        return response.text

    def convert(self, source: Path) -> str:
        mime = _MIME.get(source.suffix.lower())
        if mime is None:
            raise ConversionError(f"Không đọc được loại file {source.suffix}")
        first = self._ask(source, mime, PROMPT)
        problems = _problems(first)
        if not problems:
            return first
        # D-016: lệch thì đọc lại đúng một lần kèm chỗ lệch; lần sau không hơn thì giữ lần đầu, GV sửa ở bước xem lại.
        hint = "\n".join(f"- {p}" for p in problems)
        prompt = f"{PROMPT}\nLần đọc trước bị lệch, hãy đọc lại thật kỹ từng cột:\n{hint}"
        try:
            retry = self._ask(source, mime, prompt, model=self.retry_model)
        except ConversionError:
            return first  # lần đầu đã đọc được: lỗi ở lần đọc lại không làm hỏng cả ma trận
        return retry if len(_problems(retry)) < len(problems) else first


def matrix_cache_key(model: str, retry_model: str | None) -> str:
    """Đổi prompt, schema hay model thì khoá đổi theo, cache cũ tự mất hiệu lực."""
    # Mã hoá có cấu trúc để ("ab","c") và ("a","bc") không trùng khoá
    raw = json.dumps(
        {"prompt": PROMPT, "schema": MATRIX_SCHEMA, "model": model, "retry_model": retry_model or model},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class CachedMatrixConverter:
    """Bọc một converter: file giống hệt từng byte (SHA-256) đã đọc sạch thì trả JSON đã lưu, khỏi gọi Gemini.

    Lỗi DB không được làm hỏng upload nên chỉ ghi cảnh báo rồi chạy như không có cache.
    """

    def __init__(self, inner: MatrixConverter, session_factory: sessionmaker, cache_key: str) -> None:
        self.inner, self.session_factory, self.cache_key = inner, session_factory, cache_key

    @property
    def usage(self) -> list[dict]:
        return self.inner.usage  # type: ignore[attr-defined]

    def _lookup(self, sha: str) -> str | None:
        try:
            with self.session_factory() as session:
                return session.scalar(
                    select(MatrixConversion.output).where(
                        MatrixConversion.source_sha256 == sha, MatrixConversion.cache_key == self.cache_key
                    )
                )
        except Exception:
            log.warning("Không tra được cache ma trận, gọi converter", exc_info=True)
            return None

    def _store(self, sha: str, output: str) -> None:
        try:
            with self.session_factory() as session:
                session.add(MatrixConversion(source_sha256=sha, cache_key=self.cache_key, output=output))
                try:
                    session.commit()
                except IntegrityError:  # upload song song đã lưu cùng file
                    session.rollback()
        except Exception:
            log.warning("Không lưu được cache ma trận", exc_info=True)

    def convert(self, source: Path) -> str:
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        cached = self._lookup(sha)
        if cached is not None:
            log.info("Ma trận cache hit %s", sha[:12])
            return cached
        output = self.inner.convert(source)
        if not _problems(output):
            self._store(sha, output)
        return output


def get_matrix_converter(factory: Annotated[sessionmaker, Depends(get_session_factory)]) -> MatrixConverter:
    """Dependency cho FastAPI; test override bằng converter giả."""
    converter = GeminiMatrixConverter(settings.matrix_gemini_model, retry_model=settings.matrix_gemini_retry_model)
    if settings.matrix_cache_enabled:
        key = matrix_cache_key(settings.matrix_gemini_model, settings.matrix_gemini_retry_model)
        return CachedMatrixConverter(converter, factory, key)
    return converter
