"""Hình khối cho câu hình học (F-17): tham số LLM → tọa độ → SVG kiểu SGK, chỉ dùng numpy và chuỗi.

LLM không viết tọa độ mà chỉ chọn hình và độ dài (`figure_spec`):
    {"solid": "box" | "prism" | "pyramid", "a": số dương, "b": số dương, "h": số dương, "foot": "A" | "center" | null}
Tên đỉnh cố định theo quy ước nên không đến từ LLM: hộp ABCD.A'B'C'D', lăng trụ ABC.A'B'C', chóp S.ABCD.
Trục: a theo x, h theo y (lên), b theo chiều sâu z; đáy ABCD nằm ngang, A ở trước-trái, B trước-phải, C sau-phải, D sau-trái.

Chiếu xiên kiểu SGK: mặt trước giữ nguyên, chiều sâu lệch 45° và co ½. Một mặt thấy được khi pháp tuyến hướng ra ngoài
có tích vô hướng dương với hướng nhìn; cạnh khuất là cạnh mà cả hai mặt kề đều khuất (chỉ đúng với khối lồi).
Cùng tham số cho cùng một chuỗi SVG. Spec sai báo FigureError, không đoán.
"""

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.domain.figure.labels import FONT_SIZE, Label, label_box, place_labels
from app.domain.figure.solids import BUILDERS, SOLIDS, Solid
from app.domain.figure.spec import FEET, MAX_RATIO, FigureError, Spec, parse_spec
from app.domain.figure.view import VIEW, Edge, classify_edges, project
from app.domain.question import Question

log = logging.getLogger(__name__)

SIZE = 220  # cạnh dài của hình, px
MARGIN = 2
STROKE, DASH = 1.5, "5 4"


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    points: dict[str, tuple[float, float]]  # px, gốc ở góc trên trái, y hướng xuống
    edges: tuple[Edge, ...]
    labels: tuple[Label, ...]


# ----- bố cục -----


def layout(spec: Any) -> Layout:
    parsed = parse_spec(spec)
    solid = BUILDERS[parsed.solid].build(parsed.a, parsed.b, parsed.h, parsed.foot)
    points, edges = solid.points, classify_edges(solid)
    flat = {k: np.array(project(p)) for k, p in points.items()}
    xs, ys = zip(*flat.values())
    scale = SIZE / max(max(xs) - min(xs), max(ys) - min(ys))
    px = {k: np.array([(x - min(xs)) * scale, (max(ys) - y) * scale]) for k, (x, y) in flat.items()}
    labels = place_labels(px)
    boxes = [label_box(label) for label in labels]
    left = min(min(p[0] for p in px.values()), *(bx[0] for bx in boxes)) - MARGIN
    top = min(min(p[1] for p in px.values()), *(bx[1] for bx in boxes)) - MARGIN
    right = max(max(p[0] for p in px.values()), *(bx[2] for bx in boxes)) + MARGIN
    bottom = max(max(p[1] for p in px.values()), *(bx[3] for bx in boxes)) + MARGIN
    return Layout(
        width=math.ceil(right - left),
        height=math.ceil(bottom - top),
        points={k: (round(float(p[0] - left), 2), round(float(p[1] - top), 2)) for k, p in px.items()},
        edges=edges,
        labels=tuple(Label(l.name, round(l.x - left, 2), round(l.y - top, 2)) for l in labels),
    )


# ----- SVG -----


def _n(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def render_svg(spec: Any) -> str:
    fig = layout(spec)
    w, h = fig.width, fig.height
    lines = []
    for e in fig.edges:
        (x1, y1), (x2, y2) = fig.points[e.a], fig.points[e.b]
        dash = f' stroke-dasharray="{DASH}"' if e.hidden else ""
        lines.append(f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}"{dash}/>')
    texts = [f'<text x="{_n(l.x)}" y="{_n(l.y + FONT_SIZE * 0.35)}">{l.name}</text>' for l in fig.labels]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<rect width="{w}" height="{h}" fill="#fff"/>'
        f'<g stroke="#000" stroke-width="{STROKE}" stroke-linecap="round">{"".join(lines)}</g>'
        f'<g font-family="serif" font-size="{FONT_SIZE}" text-anchor="middle" fill="#000">{"".join(texts)}</g>'
        "</svg>"
    )


# ----- gắn vào câu hỏi -----


def with_figure(question: Question) -> Question:
    """Bản sao của câu có `figure_svg` vẽ từ `figure_spec`; spec hỏng thì bỏ cả hai, giữ mô tả chữ `figure`.

    `figure_svg` luôn tính lại từ spec (không tin giá trị cũ hay do máy khách gửi), nên không có spec thì cũng không có SVG.
    """
    out = {k: v for k, v in question.items() if k not in ("figure_spec", "figure_svg")}
    spec = question.get("figure_spec")
    if not spec:
        return out
    try:
        return out | {"figure_spec": spec, "figure_svg": render_svg(spec)}
    except FigureError as exc:
        log.warning("Bỏ hình của câu: %s", exc)
        return out
