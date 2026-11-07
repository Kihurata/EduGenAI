"""Bộ chuyển ma trận bằng Gemini trích JSON (D-016, T-054). Không gọi Gemini thật trong test.

Đầu ra mong muốn:
- Gửi file (PNG/JPG/PDF, đúng mime) kèm prompt, nhiệt độ 0, response_schema; trả JSON để matrix_extract đọc.
- Ghi usage để tính chi phí (mỗi lần gọi một dòng).
- Kết quả lệch cấu trúc/tổng thì gọi thêm đúng một lần kèm chỗ lệch; chỉ lệch chủ đề chưa có mã thì không gọi lại.
- Lỗi API, mạng/quá giờ, trả về không phải JSON ma trận, loại file lạ → ConversionError tiếng Việt.
- MATRIX_CONVERTER chọn bộ chuyển: marker hoặc gemini (mặc định); giá trị khác bị từ chối khi khởi động.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import errors
from pydantic import ValidationError

from app.core.config import Settings
from app.services import matrix_converter
from app.services.matrix_converter import ConversionError, GeminiMatrixConverter, MarkerConverter
from app.services.matrix_schema import MATRIX_SCHEMA

FIXTURES = Path(__file__).parents[1] / "fixtures" / "matrix_extract"
GOOD = (FIXTURES / "giua_ki_toan12.json").read_text(encoding="utf-8")
BO = (FIXTURES / "bo_2025_toan.json").read_text(encoding="utf-8")
BAD = json.dumps(
    {**json.loads(GOOD), "rows": [{**r, "multiple_choice": {"biet": 9, "hieu": 9, "van_dung": 0}} for r in json.loads(GOOD)["rows"][:1]]}
)  # 18 câu Phần I


class FakeModels:
    def __init__(self, texts=(GOOD,), raises=None):
        self.texts, self.raises, self.calls = list(texts), raises, []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        text = self.texts[min(len(self.calls), len(self.texts)) - 1]
        usage = SimpleNamespace(prompt_token_count=3000, candidates_token_count=1500, thoughts_token_count=None)
        return SimpleNamespace(text=text, usage_metadata=usage)


def gemini(tmp_path, name="ma_tran.png", texts=(GOOD,), raises=None):
    models = FakeModels(texts, raises)
    source = tmp_path / name
    source.write_bytes(b"PNG anh")
    return GeminiMatrixConverter("gemini-test", client=SimpleNamespace(models=models)), models, source


def test_sends_the_file_with_the_schema_and_returns_the_json(tmp_path):
    conv, models, source = gemini(tmp_path)
    assert conv.convert(source) == GOOD
    [call] = models.calls
    assert call["model"] == "gemini-test"
    assert call["config"]["temperature"] == 0 and call["config"]["response_schema"] == MATRIX_SCHEMA
    assert call["config"]["response_mime_type"] == "application/json"
    part, prompt = call["contents"]
    assert (part.inline_data.mime_type, part.inline_data.data) == ("image/png", b"PNG anh")
    assert "true_false_items" in prompt
    assert conv.usage == [{"input_tokens": 3000, "output_tokens": 1500, "thinking_tokens": 0}]


def test_pdf_uses_its_mime_type(tmp_path):
    conv, models, source = gemini(tmp_path, name="ma_tran.PDF")
    conv.convert(source)
    assert models.calls[0]["contents"][0].inline_data.mime_type == "application/pdf"


def test_a_mismatch_is_retried_once_with_the_problem_in_the_prompt(tmp_path):
    conv, models, source = gemini(tmp_path, texts=(BAD, GOOD))
    assert conv.convert(source) == GOOD
    assert len(models.calls) == 2 and len(conv.usage) == 2
    assert "Phần I cần đủ 12 câu" in models.calls[1]["contents"][1]


def test_a_retry_that_is_no_better_keeps_the_first_answer(tmp_path):
    conv, models, source = gemini(tmp_path, texts=(BAD, BAD))
    assert conv.convert(source) == BAD
    assert len(models.calls) == 2


def test_topics_without_a_code_do_not_trigger_a_retry(tmp_path):
    conv, models, source = gemini(tmp_path, texts=(BO,))
    assert conv.convert(source) == BO
    assert len(models.calls) == 1


@pytest.mark.parametrize(
    ("fake", "message"),
    [
        ({"raises": errors.APIError(503, {"error": {"message": "quá tải"}})}, "Gemini không đọc được ma trận"),
        ({"raises": TimeoutError()}, "Gemini không phản hồi: TimeoutError"),
        ({"texts": ("Xin lỗi, tôi không thấy bảng nào.",)}, "không trả về ma trận"),
        ({"texts": (None,)}, "không trả về ma trận"),
        ({"texts": ('{"rows": []}',)}, "không trả về ma trận"),
    ],
)
def test_failures_become_conversion_errors(tmp_path, fake, message):
    conv, _, source = gemini(tmp_path, **fake)
    with pytest.raises(ConversionError, match=message):
        conv.convert(source)


def test_unknown_file_type_is_rejected_before_calling_gemini(tmp_path):
    conv, models, source = gemini(tmp_path, name="ma_tran.gif")
    with pytest.raises(ConversionError, match="loại file"):
        conv.convert(source)
    assert models.calls == []


def test_setting_picks_the_converter(monkeypatch, session_factory):
    monkeypatch.setattr(matrix_converter.settings, "matrix_converter", "marker")
    assert isinstance(matrix_converter.get_matrix_converter(session_factory), MarkerConverter)
    monkeypatch.setattr(matrix_converter.settings, "matrix_converter", "gemini")
    monkeypatch.setattr(matrix_converter.settings, "matrix_cache_enabled", False)
    monkeypatch.setattr(matrix_converter, "GeminiMatrixConverter", lambda model, retry_model: ("gemini", model, retry_model))
    s = matrix_converter.settings
    assert matrix_converter.get_matrix_converter(session_factory) == ("gemini", s.matrix_gemini_model, s.matrix_gemini_retry_model)


def test_unknown_converter_name_fails_at_startup():
    with pytest.raises(ValidationError):
        Settings(matrix_converter="tesseract")


def test_the_retry_uses_the_stronger_model_when_one_is_set(tmp_path):
    """flash-lite đọc lệch bảng phức tạp; lần đọc lại dùng model mạnh hơn (vẫn tối đa 2 lần gọi)."""
    models = FakeModels((BAD, GOOD), None)
    conv = GeminiMatrixConverter("lite", client=SimpleNamespace(models=models), retry_model="strong")
    source = tmp_path / "ma_tran.png"
    source.write_bytes(b"png")
    assert conv.convert(source) == GOOD
    assert [c["model"] for c in models.calls] == ["lite", "strong"]
