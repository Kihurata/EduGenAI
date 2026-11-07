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

from app.domain.question import Question

log = logging.getLogger(__name__)

SOLIDS = ("box", "prism", "pyramid")
FEET = ("A", "center")
MAX_RATIO = 10  # cạnh dài nhất / ngắn nhất; lệch hơn thì hình dẹt đến mức nhãn không đặt được
DEPTH_SCALE, DEPTH_ANGLE = 0.5, math.radians(45)
VIEW = np.array([DEPTH_SCALE * math.cos(DEPTH_ANGLE), DEPTH_SCALE * math.sin(DEPTH_ANGLE), -1.0])  # từ vật về phía mắt

SIZE = 220  # cạnh dài của hình, px
MARGIN = 2
FONT_SIZE = 14
CHAR_WIDTH = 8
LABEL_OFFSET = 11  # tâm nhãn cách đỉnh ít nhất ngần này px
LABEL_GAP = 1
STROKE, DASH = 1.5, "5 4"


class FigureError(ValueError):
    """Spec hình không dùng được (hoặc không đổi được sang ảnh)."""


@dataclass(frozen=True)
class Edge:
    a: str
    b: str
    hidden: bool


@dataclass(frozen=True)
class Label:
    name: str
    x: float  # tâm hộp nhãn
    y: float


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    points: dict[str, tuple[float, float]]  # px, gốc ở góc trên trái, y hướng xuống
    edges: tuple[Edge, ...]
    labels: tuple[Label, ...]


def project(point) -> tuple[float, float]:
    x, y, z = point
    return x + DEPTH_SCALE * z * math.cos(DEPTH_ANGLE), y + DEPTH_SCALE * z * math.sin(DEPTH_ANGLE)


def label_box(label: Label) -> tuple[float, float, float, float]:
    half_w, half_h = (CHAR_WIDTH * len(label.name) + 2) / 2, FONT_SIZE / 2
    return label.x - half_w, label.y - half_h, label.x + half_w, label.y + half_h


# ----- kiểm spec -----


def _dim(spec: dict, key: str) -> float:
    value = spec.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
        raise FigureError(f"Kích thước '{key}' của hình phải là số dương")
    return float(value)


def _parse(spec: Any) -> tuple[str, float, float, float, str | None]:
    if not isinstance(spec, dict):
        raise FigureError("figure_spec phải là một object")
    solid = spec.get("solid")
    if solid not in SOLIDS:
        raise FigureError(f"Chưa vẽ được hình {solid!r}, chỉ có {', '.join(SOLIDS)}")
    a, b, h = (_dim(spec, k) for k in "abh")
    if max(a, b, h) / min(a, b, h) > MAX_RATIO:
        raise FigureError(f"Các cạnh lệch nhau quá {MAX_RATIO} lần, hình sẽ méo")
    foot = spec.get("foot")
    if solid == "pyramid":
        foot = foot or "center"
        if foot not in FEET:
            raise FigureError(f"Chân đường cao phải là một trong {', '.join(FEET)}")
    elif foot is not None:
        raise FigureError("Chỉ hình chóp mới có chân đường cao")
    return solid, a, b, h, foot


# ----- tọa độ và mặt của từng khối -----

Faces = list[tuple[str, ...]]


def _build(solid: str, a: float, b: float, h: float, foot: str | None) -> tuple[dict[str, np.ndarray], Faces]:
    if solid == "prism":  # đáy tam giác vuông tại A: AB theo x, AC theo chiều sâu
        base = {"A": (0, 0, 0), "B": (a, 0, 0), "C": (0, 0, b)}
    else:
        base = {"A": (0, 0, 0), "B": (a, 0, 0), "C": (a, 0, b), "D": (0, 0, b)}
    names = list(base)
    ring = list(zip(names, names[1:] + names[:1]))
    if solid == "pyramid":
        base["S"] = (0, h, 0) if foot == "A" else (a / 2, h, b / 2)
        faces = [tuple(names), *(("S", u, v) for u, v in ring)]
    else:
        base |= {f"{k}'": (x, h, z) for k, (x, _, z) in list(base.items())}
        faces = [tuple(names), tuple(f"{k}'" for k in names), *((u, v, f"{v}'", f"{u}'") for u, v in ring)]
    return {k: np.array(v, float) for k, v in base.items()}, faces


def _edges(points: dict[str, np.ndarray], faces: Faces) -> tuple[Edge, ...]:
    centroid = np.mean(list(points.values()), axis=0)
    visible = []
    for face in faces:
        p = [points[k] for k in face]
        normal = np.cross(p[1] - p[0], p[2] - p[1])
        if normal @ (np.mean(p, axis=0) - centroid) < 0:
            normal = -normal  # hướng ra ngoài khối
        visible.append(normal @ VIEW > 1e-9)
    sides: dict[frozenset[str], list[bool]] = {}
    for face, seen in zip(faces, visible):
        for u, v in zip(face, face[1:] + face[:1]):
            sides.setdefault(frozenset((u, v)), []).append(seen)
    order = {frozenset((u, v)): (u, v) for face in faces for u, v in zip(face, face[1:] + face[:1])}
    return tuple(Edge(*order[key], hidden=not any(seen)) for key, seen in sides.items())


# ----- bố cục -----


def _overlaps(box, others) -> bool:
    x0, y0, x1, y1 = box
    return any(x0 < ox1 + LABEL_GAP and ox0 - LABEL_GAP < x1 and y0 < oy1 + LABEL_GAP and oy0 - LABEL_GAP < y1
               for ox0, oy0, ox1, oy1 in others)  # fmt: skip


def _covers(box, point) -> bool:
    return box[0] - LABEL_GAP < point[0] < box[2] + LABEL_GAP and box[1] - LABEL_GAP < point[1] < box[3] + LABEL_GAP


def _spot(name: str, vertex: np.ndarray, away: np.ndarray, taken: list) -> Label:
    """Chỗ đầu tiên không chồng nhãn nào: thử hướng "ra ngoài" rồi xoay dần, ở từng khoảng cách xa dần."""
    for step in range(40):
        for turn in (0, 30, -30, 60, -60, 90, -90, 120, -120, 150, -150, 180):
            t = math.radians(turn)
            direction = np.array([away[0] * math.cos(t) - away[1] * math.sin(t), away[0] * math.sin(t) + away[1] * math.cos(t)])
            x, y = vertex + direction * (LABEL_OFFSET + 5 * step)
            label = Label(name, float(x), float(y))
            if not _overlaps(label_box(label), taken) and not _covers(label_box(label), vertex):
                return label
    raise FigureError(f"Không đặt được nhãn {name}")


def _place_labels(points: dict[str, np.ndarray]) -> list[Label]:
    """Nhãn nằm ngoài đỉnh, theo hướng từ tâm hình ra; chồng nhau thì xoay hướng rồi đẩy xa dần."""
    center = np.mean(list(points.values()), axis=0)
    placed: list[Label] = []
    for name, vertex in points.items():
        away = vertex - center
        away = away / np.linalg.norm(away) if np.linalg.norm(away) > 1e-9 else np.array([0.0, -1.0])
        placed.append(_spot(name, vertex, away, [label_box(p) for p in placed]))
    return placed


def layout(spec: Any) -> Layout:
    solid, a, b, h, foot = _parse(spec)
    points, faces = _build(solid, a, b, h, foot)
    edges = _edges(points, faces)
    flat = {k: np.array(project(p)) for k, p in points.items()}
    xs, ys = zip(*flat.values())
    scale = SIZE / max(max(xs) - min(xs), max(ys) - min(ys))
    px = {k: np.array([(x - min(xs)) * scale, (max(ys) - y) * scale]) for k, (x, y) in flat.items()}
    labels = _place_labels(px)
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
