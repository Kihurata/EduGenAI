"""Bố cục hình: khối (đã kiểm spec) → điểm px, cạnh thấy/khuất, nhãn, kích thước khung chứa vừa đủ mọi thứ."""

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.domain.figure.labels import Label, label_box, place_labels
from app.domain.figure.solids import BUILDERS
from app.domain.figure.spec import parse_spec
from app.domain.figure.view import Edge, classify_edges, project

SIZE = 220  # cạnh dài của hình, px
MARGIN = 2


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    points: dict[str, tuple[float, float]]  # px, gốc ở góc trên trái, y hướng xuống
    edges: tuple[Edge, ...]
    labels: tuple[Label, ...]


def _fit(flat: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Phóng cạnh dài của hình lên SIZE px và lật y (SVG y hướng xuống)."""
    xs, ys = zip(*flat.values())
    scale = SIZE / max(max(xs) - min(xs), max(ys) - min(ys))
    return {k: np.array([(x - min(xs)) * scale, (max(ys) - y) * scale]) for k, (x, y) in flat.items()}


def _frame(points: dict[str, np.ndarray], labels: list[Label]) -> tuple[float, float, float, float]:
    """Khung (trái, trên, phải, dưới) ôm mọi điểm và hộp nhãn, cộng lề."""
    boxes = [label_box(label) for label in labels]
    xs = [p[0] for p in points.values()] + [v for b in boxes for v in (b[0], b[2])]
    ys = [p[1] for p in points.values()] + [v for b in boxes for v in (b[1], b[3])]
    return min(xs) - MARGIN, min(ys) - MARGIN, max(xs) + MARGIN, max(ys) + MARGIN


def layout(raw_spec: Any) -> Layout:
    spec = parse_spec(raw_spec)
    solid = BUILDERS[spec.solid].build(spec.a, spec.b, spec.h, spec.foot)
    px = _fit({k: np.array(project(p)) for k, p in solid.points.items()})
    labels = place_labels(px)
    left, top, right, bottom = _frame(px, labels)
    return Layout(
        width=math.ceil(right - left),
        height=math.ceil(bottom - top),
        points={k: (round(float(p[0] - left), 2), round(float(p[1] - top), 2)) for k, p in px.items()},
        edges=classify_edges(solid),
        labels=tuple(Label(lb.name, round(lb.x - left, 2), round(lb.y - top, 2)) for lb in labels),
    )
