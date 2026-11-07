"""SVG của hình khối (domain/figure.py) → PNG để nhúng vào DOCX; Word và Pandoc không đọc SVG ổn định."""

import math
import xml.etree.ElementTree as ET

from app.domain.figure import FigureError

DEFAULT_SCALE = 3  # ~288 dpi khi hình rộng 3 inch: in ra giấy không vỡ nét
MAX_SCALE = 10


def svg_to_png(svg: str, scale: float = DEFAULT_SCALE) -> bytes:
    """Trả byte PNG rộng bằng chiều rộng SVG × scale; SVG hỏng hoặc scale sai thì FigureError."""
    if not (isinstance(scale, int | float) and math.isfinite(scale) and 0 < scale <= MAX_SCALE):
        raise FigureError(f"scale phải trong khoảng (0, {MAX_SCALE}]")
    try:
        if not ET.fromstring(svg).tag.endswith("}svg"):
            raise FigureError("Không phải SVG")
        import cairosvg  # import muộn: thiếu thư viện Cairo của máy chỉ làm hỏng việc đổi ảnh, không làm hỏng cả app

        return cairosvg.svg2png(bytestring=svg.encode("utf-8"), scale=scale, unsafe=False)  # không theo file/URL ngoài
    except FigureError:
        raise
    except Exception as exc:  # ParseError, OSError (thiếu libcairo), lỗi của cairosvg: đều là "không đổi được"
        raise FigureError(f"Không đổi được SVG sang PNG: {exc}") from exc
