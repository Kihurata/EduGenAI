"""Gắn hình vào câu hỏi: `figure_spec` → `figure_svg`."""

import logging

from app.domain.figure.spec import FigureError
from app.domain.figure.svg import render_svg
from app.domain.question import Question

log = logging.getLogger(__name__)

DERIVED_KEYS = ("figure_spec", "figure_svg")


def with_figure(question: Question) -> Question:
    """Bản sao của câu có `figure_svg` vẽ từ `figure_spec`; spec hỏng thì bỏ cả hai, giữ mô tả chữ `figure`.

    `figure_svg` luôn tính lại từ spec (không tin giá trị cũ hay do máy khách gửi), nên không có spec thì cũng không có SVG.
    """
    out = {k: v for k, v in question.items() if k not in DERIVED_KEYS}
    spec = question.get("figure_spec")
    if not spec:
        return out
    try:
        return out | {"figure_spec": spec, "figure_svg": render_svg(spec)}
    except FigureError as exc:
        log.warning("Bỏ hình của câu: %s", exc)
        return out
