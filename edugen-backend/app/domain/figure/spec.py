"""Spec hình do LLM trả (`figure_spec`) → `Spec` bất biến đã kiểm; sai thì FigureError, không đoán."""

import math
from dataclasses import dataclass
from typing import Any

from app.domain.figure.solids import BUILDERS

FEET = ("A", "center")
MIN_DIM, MAX_DIM = 1e-3, 1e4  # đủ cho mọi số đo trong SGK; ngoài khoảng này hình tính ra inf/NaN
MAX_RATIO = 10  # cạnh dài nhất / ngắn nhất; lệch hơn thì hình dẹt đến mức nhãn không đặt được


class FigureError(ValueError):
    """Spec hình không dùng được (hoặc không đổi được sang ảnh)."""


@dataclass(frozen=True)
class Spec:
    solid: str
    a: float
    b: float
    h: float
    foot: str | None


def _dim(raw: dict, key: str) -> float:
    value = raw.get(key)
    ok = isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
    if not ok or not MIN_DIM <= value <= MAX_DIM:
        raise FigureError(f"Kích thước '{key}' của hình phải là số trong khoảng [{MIN_DIM:g}, {MAX_DIM:g}]")
    return float(value)


def parse_spec(raw: Any) -> Spec:
    if not isinstance(raw, dict):
        raise FigureError("figure_spec phải là một object")
    solid = raw.get("solid")
    if solid not in BUILDERS:
        raise FigureError(f"Chưa vẽ được hình {str(solid)[:40]!r}, chỉ có {', '.join(sorted(BUILDERS))}")
    a, b, h = (_dim(raw, k) for k in "abh")
    if max(a, b, h) / min(a, b, h) > MAX_RATIO:
        raise FigureError(f"Các cạnh lệch nhau quá {MAX_RATIO} lần, hình sẽ méo")
    foot = raw.get("foot")
    if BUILDERS[solid].takes_foot:
        foot = foot or "center"
        if foot not in FEET:
            raise FigureError(f"Chân đường cao phải là một trong {', '.join(FEET)}")
    elif foot is not None:
        raise FigureError("Chỉ hình chóp mới có chân đường cao")
    return Spec(solid, a, b, h, foot)
