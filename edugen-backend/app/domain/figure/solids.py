"""Bảng đăng ký các khối hình (F-17): mỗi khối là một SolidBuilder; thêm khối mới = thêm một dòng vào BUILDERS.

Trục: a theo x, h theo y (lên), b theo chiều sâu z; đáy nằm ngang. Tên đỉnh cố định theo quy ước SGK.
Mỗi khối trả tọa độ các đỉnh và các mặt (danh sách tên đỉnh theo vòng); khối phải kín và lồi.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

Faces = tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Solid:
    points: dict[str, np.ndarray]
    faces: Faces


@dataclass(frozen=True)
class SolidBuilder:
    build: Callable[[float, float, float, str | None], Solid]  # (a, b, h, foot) → khối
    takes_foot: bool = False  # chỉ chóp có chân đường cao


def _solid(points: dict[str, tuple[float, float, float]], faces: Faces) -> Solid:
    return Solid({k: np.array(v, float) for k, v in points.items()}, faces)


def _ring(names: list[str]) -> list[tuple[str, str]]:
    return list(zip(names, names[1:] + names[:1]))


def _prism_over(base: dict[str, tuple[float, float, float]], h: float) -> Solid:
    """Lăng trụ đứng: đáy `base`, đáy trên cao h với tên có dấu '."""
    names = list(base)
    top = {f"{k}'": (x, h, z) for k, (x, _, z) in base.items()}
    sides = tuple((u, v, f"{v}'", f"{u}'") for u, v in _ring(names))
    return _solid(base | top, (tuple(names), tuple(f"{k}'" for k in names), *sides))


def _box(a: float, b: float, h: float, foot: str | None) -> Solid:
    return _prism_over({"A": (0, 0, 0), "B": (a, 0, 0), "C": (a, 0, b), "D": (0, 0, b)}, h)


def _prism(a: float, b: float, h: float, foot: str | None) -> Solid:
    """Đáy tam giác vuông tại A: AB theo x, AC theo chiều sâu."""
    return _prism_over({"A": (0, 0, 0), "B": (a, 0, 0), "C": (0, 0, b)}, h)


def _pyramid(a: float, b: float, h: float, foot: str | None) -> Solid:
    base = {"A": (0, 0, 0), "B": (a, 0, 0), "C": (a, 0, b), "D": (0, 0, b)}
    apex = (0, h, 0) if foot == "A" else (a / 2, h, b / 2)
    names = list(base)
    return _solid(base | {"S": apex}, (tuple(names), *(("S", u, v) for u, v in _ring(names))))


BUILDERS: dict[str, SolidBuilder] = {
    "box": SolidBuilder(_box),
    "prism": SolidBuilder(_prism),
    "pyramid": SolidBuilder(_pyramid, takes_foot=True),
}
SOLIDS = tuple(sorted(BUILDERS))  # tên hình có sẵn lúc nạp module; kiểm spec luôn tra BUILDERS nên hình đăng ký thêm vẫn dùng được
