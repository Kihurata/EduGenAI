"""Hình khối cho câu hình học (F-17): tham số LLM → tọa độ → SVG kiểu SGK, chỉ dùng numpy và chuỗi.

LLM không viết tọa độ mà chỉ chọn hình và độ dài (`figure_spec`):
    {"solid": "box" | "prism" | "pyramid", "a": số dương, "b": số dương, "h": số dương, "foot": "A" | "center" | null}
Mỗi file một việc: spec.py (kiểm spec), solids.py (bảng đăng ký khối), view.py (chiếu xiên, cạnh khuất), labels.py (nhãn),
layout.py (bố cục), svg.py (viết SVG), attach.py (gắn vào câu hỏi). Thêm khối mới chỉ cần thêm vào solids.BUILDERS.
"""

from app.domain.figure.attach import with_figure
from app.domain.figure.labels import Label, label_box
from app.domain.figure.layout import Layout, layout
from app.domain.figure.solids import SOLIDS
from app.domain.figure.spec import FigureError, Spec, parse_spec
from app.domain.figure.svg import render_svg
from app.domain.figure.view import Edge, project

__all__ = [
    "SOLIDS", "Edge", "FigureError", "Label", "Layout", "Spec",
    "label_box", "layout", "parse_spec", "project", "render_svg", "with_figure",
]  # fmt: skip
