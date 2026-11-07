"""Nhãn đỉnh: nằm ngoài đỉnh theo hướng từ tâm hình ra; chồng nhau thì xoay hướng rồi đẩy xa dần."""

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from app.domain.figure.spec import FigureError

FONT_SIZE = 14
CHAR_WIDTH = 8
LABEL_OFFSET = 11  # tâm nhãn cách đỉnh ít nhất ngần này px
LABEL_GAP = 1
TURNS = (0, 30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180)  # độ xoay thử, gần hướng "ra ngoài" trước
MAX_STEPS = 40  # mỗi bước đẩy nhãn xa thêm 5 px

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Label:
    name: str
    x: float  # tâm hộp nhãn
    y: float


def label_box(label: Label) -> Box:
    half_w, half_h = (CHAR_WIDTH * len(label.name) + 2) / 2, FONT_SIZE / 2
    return label.x - half_w, label.y - half_h, label.x + half_w, label.y + half_h


def overlaps(box: Box, others: Iterable[Box]) -> bool:
    """Hộp chồng (hoặc sát quá LABEL_GAP) một hộp nào đó."""
    x0, y0, x1, y1 = box
    return any(x0 < ox1 + LABEL_GAP and ox0 - LABEL_GAP < x1 and y0 < oy1 + LABEL_GAP and oy0 - LABEL_GAP < y1
               for ox0, oy0, ox1, oy1 in others)  # fmt: skip


def covers(box: Box, point) -> bool:
    return box[0] - LABEL_GAP < point[0] < box[2] + LABEL_GAP and box[1] - LABEL_GAP < point[1] < box[3] + LABEL_GAP


def _rotate(v: np.ndarray, degrees: int) -> np.ndarray:
    t = math.radians(degrees)
    return np.array([v[0] * math.cos(t) - v[1] * math.sin(t), v[0] * math.sin(t) + v[1] * math.cos(t)])


def _find_spot(name: str, vertex: np.ndarray, away: np.ndarray, taken: list[Box]) -> Label:
    """Chỗ đầu tiên không chồng nhãn nào và không che đỉnh: thử hướng "ra ngoài" rồi xoay dần, xa dần."""
    for step in range(MAX_STEPS):
        for turn in TURNS:
            x, y = vertex + _rotate(away, turn) * (LABEL_OFFSET + 5 * step)
            label = Label(name, float(x), float(y))
            box = label_box(label)
            if not overlaps(box, taken) and not covers(box, vertex):
                return label
    raise FigureError(f"Không đặt được nhãn {name}")


def place_labels(points: dict[str, np.ndarray]) -> list[Label]:
    """Một nhãn cho mỗi đỉnh (tọa độ px), theo thứ tự đỉnh, không nhãn nào chồng nhau."""
    center = np.mean(list(points.values()), axis=0)
    placed: list[Label] = []
    for name, vertex in points.items():
        away = vertex - center
        away = away / np.linalg.norm(away) if np.linalg.norm(away) > 1e-9 else np.array([0.0, -1.0])
        placed.append(_find_spot(name, vertex, away, [label_box(p) for p in placed]))
    return placed
