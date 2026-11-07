"""Ảnh/PDF ma trận → markdown bằng marker (xem docs/marker.md), hoặc → JSON bằng Gemini (D-016).

Marker chạy ~2 phút mỗi ảnh nên chỉ gọi trong job nền (services/matrix_jobs.py). Unit test
dùng converter giả, không bao giờ chạy marker thật.
"""

import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from dotenv import dotenv_values

from app.core.config import settings
from app.domain.matrix_reader import read_matrix
from app.services.matrix_schema import MATRIX_SCHEMA, PROMPT


class ConversionError(Exception):
    """Marker không chuyển được file; thông báo hiển thị cho giáo viên."""


class MatrixConverter(Protocol):
    def convert(self, source: Path) -> str: ...


class MarkerConverter:
    """Chạy `marker_single` với marker_config.json (bắt buộc html_tables_in_markdown)."""

    def __init__(
        self,
        config_path: str | Path,
        env_file: str | Path | None = ".env",
        timeout: float = 600,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> None:
        self.config_path = str(config_path)
        self.env_file = env_file
        self.timeout = timeout
        self._run = run  # test truyền runner giả

    def _env(self) -> dict[str, str]:
        # GOOGLE_API_KEY, SURYA_INFERENCE_BACKEND, LLAMA_CPP_BINARY nằm trong .env.
        extra = dotenv_values(self.env_file) if self.env_file and Path(self.env_file).exists() else {}
        return os.environ | {k: v for k, v in extra.items() if v is not None}

    def convert(self, source: Path) -> str:
        with tempfile.TemporaryDirectory(prefix="marker_") as out:
            cmd = [
                "marker_single", str(source),
                "--config_json", self.config_path,
                "--output_dir", out,
            ]  # fmt: skip
            try:
                result = self._run(
                    cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=self.timeout, env=self._env(),
                )  # fmt: skip
            except subprocess.TimeoutExpired as exc:
                raise ConversionError("Marker chạy quá thời gian cho phép") from exc
            except FileNotFoundError as exc:
                raise ConversionError("Máy chủ chưa cài marker (uv sync --extra ocr)") from exc
            if result.returncode != 0:
                raise ConversionError(f"Marker lỗi: {(result.stderr or '')[-500:].strip()}")
            outputs = sorted(Path(out).rglob("*.md"))
            if not outputs:
                raise ConversionError("Marker không sinh file markdown nào")
            return outputs[0].read_text(encoding="utf-8")


_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}

def _problems(text: str) -> list[str]:
    """Lỗi cấu trúc/tổng của kết quả; chủ đề chưa có mã là việc của GV nên không tính (gọi lại cũng không hơn)."""
    return [i.message for i in read_matrix(text).issues if "chưa có mã chủ đề" not in i.message]


class GeminiMatrixConverter:
    """Gửi ảnh/PDF ma trận cho Gemini, nhận JSON theo MATRIX_SCHEMA (D-016) để matrix_extract đọc. Không cần torch."""

    def __init__(self, model: str, client=None, timeout_seconds: float = 120, retry_model: str | None = None) -> None:
        if client is None:
            from google import genai

            client = genai.Client(http_options={"timeout": int(timeout_seconds * 1000)})
        self.client, self.model = client, model
        # Lần đọc lại dùng model mạnh hơn: bản lite hay lệch cột ở bảng nhiều phần/mức (vd Phần III chỉ có Hiểu, VD).
        self.retry_model = retry_model or model
        self.usage: list[dict] = []

    def _ask(self, source: Path, mime: str, prompt: str, model: str | None = None) -> str:
        from google.genai import errors, types

        try:
            response = self.client.models.generate_content(
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


def get_matrix_converter() -> MatrixConverter:
    """Dependency cho FastAPI; test override bằng converter giả. MATRIX_CONVERTER=marker|gemini."""
    if settings.matrix_converter == "gemini":
        return GeminiMatrixConverter(settings.matrix_gemini_model, retry_model=settings.matrix_gemini_retry_model)
    return MarkerConverter(settings.marker_config_path, timeout=settings.marker_timeout_seconds)
