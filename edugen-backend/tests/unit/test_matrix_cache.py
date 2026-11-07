"""Cache kết quả chuyển ma trận theo SHA-256 của file (chỉ file giống hệt từng byte, chỉ kết quả sạch).

Đầu ra mong muốn:
- Cùng file tải lại → trả JSON đã lưu, không gọi converter bên trong.
- File khác byte, hoặc cache_key khác (đổi prompt/schema/model) → miss.
- Kết quả còn lệch (`_problems` không rỗng) không được lưu; ConversionError đi thẳng ra ngoài, không lưu.
- Lỗi DB (tra hoặc lưu) không làm hỏng upload; ghi trùng do upload song song bị bỏ qua.
- get_matrix_converter chỉ bọc Gemini khi MATRIX_CACHE_ENABLED bật.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import MatrixConversion
from app.services import matrix_converter
from app.services.matrix_converter import (
    CachedMatrixConverter,
    ConversionError,
    matrix_cache_key,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "matrix_extract"
GOOD = (FIXTURES / "giua_ki_toan12.json").read_text(encoding="utf-8")
BAD = json.dumps(
    {
        **json.loads(GOOD),
        "rows": [{**r, "multiple_choice": {"biet": 9, "hieu": 9, "van_dung": 0}} for r in json.loads(GOOD)["rows"][:1]],
    }
)


class FakeConverter:
    def __init__(self, output=GOOD, raises=None):
        self.output, self.raises, self.calls = output, raises, 0
        self.usage = []

    def convert(self, source):
        self.calls += 1
        if self.raises:
            raise self.raises
        return self.output


def src(tmp_path, data=b"anh-1", name="mt.png"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def count(session_factory):
    with session_factory() as s:
        return s.scalar(select(func.count()).select_from(MatrixConversion))


def test_same_bytes_hit_cache(tmp_path, session_factory):
    inner = FakeConverter()
    conv = CachedMatrixConverter(inner, session_factory, "k")
    assert conv.convert(src(tmp_path)) == GOOD
    assert conv.convert(src(tmp_path, name="khac_ten.png")) == GOOD
    assert inner.calls == 1


def test_different_bytes_miss(tmp_path, session_factory):
    inner = FakeConverter()
    conv = CachedMatrixConverter(inner, session_factory, "k")
    conv.convert(src(tmp_path, b"a"))
    conv.convert(src(tmp_path, b"b"))
    assert inner.calls == 2


def test_different_cache_key_miss(tmp_path, session_factory):
    inner = FakeConverter()
    CachedMatrixConverter(inner, session_factory, "k1").convert(src(tmp_path))
    CachedMatrixConverter(inner, session_factory, "k2").convert(src(tmp_path))
    assert inner.calls == 2


def test_output_with_problems_is_not_stored(tmp_path, session_factory):
    inner = FakeConverter(BAD)
    conv = CachedMatrixConverter(inner, session_factory, "k")
    assert conv.convert(src(tmp_path)) == BAD
    conv.convert(src(tmp_path))
    assert inner.calls == 2
    assert count(session_factory) == 0


def test_conversion_error_propagates_and_nothing_stored(tmp_path, session_factory):
    conv = CachedMatrixConverter(FakeConverter(raises=ConversionError("hỏng")), session_factory, "k")
    with pytest.raises(ConversionError, match="hỏng"):
        conv.convert(src(tmp_path))
    assert count(session_factory) == 0


def test_broken_db_falls_back_to_inner(tmp_path):
    def broken():
        raise RuntimeError("db chết")

    inner = FakeConverter()
    assert CachedMatrixConverter(inner, broken, "k").convert(src(tmp_path)) == GOOD
    assert inner.calls == 1


def test_duplicate_insert_is_ignored(tmp_path, session_factory):
    inner = FakeConverter()
    conv = CachedMatrixConverter(inner, session_factory, "k")
    path = src(tmp_path)
    conv._lookup = lambda sha: None  # giả lập upload song song: lúc tra chưa có, lúc lưu đã có
    conv.convert(path)
    assert conv.convert(path) == GOOD  # lưu lần hai trùng khoá → IntegrityError bị nuốt
    assert inner.calls == 2
    assert count(session_factory) == 1


def test_cache_key_changes_with_models():
    assert matrix_cache_key("a", "b") == matrix_cache_key("a", "b")
    assert matrix_cache_key("a", "b") != matrix_cache_key("a", "c")
    assert len(matrix_cache_key("a", "b")) == 64


def test_cache_key_has_boundaries_and_default_retry():
    assert matrix_cache_key("ab", "c") != matrix_cache_key("a", "bc")
    assert matrix_cache_key("a", None) == matrix_cache_key("a", "a")


def test_factory_wraps_gemini_only_when_enabled(monkeypatch, session_factory):
    s = matrix_converter.settings
    monkeypatch.setattr(matrix_converter, "GeminiMatrixConverter", lambda model, retry_model: FakeConverter())
    monkeypatch.setattr(s, "matrix_cache_enabled", True)
    assert isinstance(matrix_converter.get_matrix_converter(session_factory), CachedMatrixConverter)
    monkeypatch.setattr(s, "matrix_cache_enabled", False)
    assert isinstance(matrix_converter.get_matrix_converter(session_factory), FakeConverter)
