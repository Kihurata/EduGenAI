"""SVG của hình khối → PNG để nhúng vào DOCX (Word và Pandoc không đọc SVG ổn định).

Đầu ra mong muốn:
- Trả về byte PNG thật (đúng chữ ký 8 byte), rộng đúng chiều rộng SVG × scale.
- scale lớn hơn cho ảnh to hơn (in ra giấy không vỡ nét); mặc định đủ nét để in.
- SVG hỏng, rỗng hoặc scale không hợp lệ báo FigureError, không để lỗi của thư viện lọt ra ngoài.
"""

import struct

import pytest

from app.domain.figure import FigureError, layout, render_svg
from app.services.figure_png import DEFAULT_SCALE, svg_to_png

SPEC = {"solid": "pyramid", "a": 3, "b": 4, "h": 5, "foot": "center"}
SIGNATURE = b"\x89PNG\r\n\x1a\n"


def size(png: bytes) -> tuple[int, int]:
    """Rộng và cao đọc từ khối IHDR của PNG."""
    return struct.unpack(">II", png[16:24])


def test_png_has_the_png_signature_and_the_svg_size_times_scale():
    png = svg_to_png(render_svg(SPEC), scale=2)
    assert png.startswith(SIGNATURE)
    figure = layout(SPEC)
    assert size(png) == (round(figure.width * 2), round(figure.height * 2))


def test_larger_scale_gives_a_larger_image():
    svg = render_svg(SPEC)
    small, large = size(svg_to_png(svg, scale=1)), size(svg_to_png(svg, scale=3))
    assert large[0] == 3 * small[0] and large[1] == 3 * small[1]


def test_default_scale_is_sharp_enough_to_print():
    assert DEFAULT_SCALE >= 3
    assert size(svg_to_png(render_svg(SPEC)))[0] == round(layout(SPEC).width * DEFAULT_SCALE)


def test_image_is_not_blank():
    png = svg_to_png(render_svg(SPEC))
    assert len(set(png)) > 20 and len(png) > 1000


@pytest.mark.parametrize("bad", ["", "   ", "không phải svg", "<svg", "<html></html>", "<svg><line></svg>"])
def test_broken_svg_raises_figure_error(bad):
    with pytest.raises(FigureError):
        svg_to_png(bad)


@pytest.mark.parametrize("scale", [0, -1, float("nan"), float("inf"), 100])
def test_bad_scale_raises_figure_error(scale):
    with pytest.raises(FigureError):
        svg_to_png(render_svg(SPEC), scale=scale)
