"""Chiếu xiên kiểu SGK và xét cạnh thấy / khuất.

Mặt trước giữ nguyên, chiều sâu lệch 45° và co ½. Một mặt thấy được khi pháp tuyến hướng ra ngoài có tích vô hướng
dương với hướng nhìn; cạnh khuất là cạnh mà cả hai mặt kề đều khuất (chỉ đúng với khối lồi và kín).
"""

import math
from dataclasses import dataclass

import numpy as np

from app.domain.figure.solids import Solid
from app.domain.figure.spec import FigureError

DEPTH_SCALE, DEPTH_ANGLE = 0.5, math.radians(45)
VIEW = np.array([DEPTH_SCALE * math.cos(DEPTH_ANGLE), DEPTH_SCALE * math.sin(DEPTH_ANGLE), -1.0])  # từ vật về phía mắt


@dataclass(frozen=True)
class Edge:
    a: str
    b: str
    hidden: bool


def project(point) -> tuple[float, float]:
    x, y, z = point
    return x + DEPTH_SCALE * z * math.cos(DEPTH_ANGLE), y + DEPTH_SCALE * z * math.sin(DEPTH_ANGLE)


def _is_visible(face: tuple[str, ...], solid: Solid, centroid: np.ndarray, view: np.ndarray) -> bool:
    p = [solid.points[k] for k in face]
    normal = np.cross(p[1] - p[0], p[2] - p[1])
    if normal @ (np.mean(p, axis=0) - centroid) < 0:
        normal = -normal  # hướng ra ngoài khối
    return bool(normal @ view > 1e-9)


def classify_edges(solid: Solid, view: np.ndarray = VIEW) -> tuple[Edge, ...]:
    """Mọi cạnh của khối kèm cờ khuất; mặt hở (cạnh không thuộc đúng hai mặt) thì FigureError, không vẽ sai nét."""
    centroid = np.mean(list(solid.points.values()), axis=0)
    seen: dict[frozenset[str], list[bool]] = {}
    direction: dict[frozenset[str], tuple[str, str]] = {}
    for face in solid.faces:
        visible = _is_visible(face, solid, centroid, view)
        for u, v in zip(face, face[1:] + face[:1]):
            seen.setdefault(frozenset((u, v)), []).append(visible)
            direction.setdefault(frozenset((u, v)), (u, v))
    if any(len(v) != 2 for v in seen.values()):
        raise FigureError("Khối không kín: có cạnh không thuộc đúng hai mặt")
    return tuple(Edge(*direction[key], hidden=not any(v)) for key, v in seen.items())
