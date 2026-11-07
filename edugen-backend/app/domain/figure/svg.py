"""Layout → chuỗi SVG. Chỉ có số và tên đỉnh cố định, không chữ nào do LLM viết, nên cùng spec cho cùng một chuỗi an toàn."""

from typing import Any

from app.domain.figure.labels import FONT_SIZE, Label
from app.domain.figure.layout import Layout, layout
from app.domain.figure.view import Edge

STROKE, DASH = 1.5, "5 4"


def _n(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _line(edge: Edge, fig: Layout) -> str:
    (x1, y1), (x2, y2) = fig.points[edge.a], fig.points[edge.b]
    dash = f' stroke-dasharray="{DASH}"' if edge.hidden else ""
    return f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}"{dash}/>'


def _text(label: Label) -> str:
    return f'<text x="{_n(label.x)}" y="{_n(label.y + FONT_SIZE * 0.35)}">{label.name}</text>'


def render_svg(raw_spec: Any) -> str:
    fig = layout(raw_spec)
    w, h = fig.width, fig.height
    lines, texts = "".join(_line(e, fig) for e in fig.edges), "".join(_text(lb) for lb in fig.labels)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<rect width="{w}" height="{h}" fill="#fff"/>'
        f'<g stroke="#000" stroke-width="{STROKE}" stroke-linecap="round">{lines}</g>'
        f'<g font-family="serif" font-size="{FONT_SIZE}" text-anchor="middle" fill="#000">{texts}</g>'
        "</svg>"
    )
