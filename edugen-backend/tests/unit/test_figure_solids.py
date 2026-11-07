"""Khối hình là bảng đăng ký (mở cho thêm hình mới, không sửa chỗ khác) và spec là giá trị bất biến (F-17).

Đầu ra mong muốn:
- `parse_spec` trả một `Spec` bất biến; chóp mặc định chân đường cao ở tâm, hình khác không có chân.
- SOLIDS lấy từ bảng đăng ký; mỗi hình đăng ký có đủ mặt kín (mỗi cạnh thuộc đúng hai mặt).
- Thêm một hình vào bảng đăng ký là vẽ được ngay, thông báo lỗi liệt kê cả hình mới; hình hở mặt báo FigureError.
- Hướng nhìn là tham số: nhìn từ phía đối diện thì cạnh khuất đổi chỗ.
"""

import dataclasses

import numpy as np
import pytest

from app.domain.figure import SOLIDS, FigureError, layout, render_svg
from app.domain.figure.solids import BUILDERS, Solid, SolidBuilder
from app.domain.figure.spec import Spec, parse_spec
from app.domain.figure.view import VIEW, classify_edges

BOX = {"solid": "box", "a": 3, "b": 4, "h": 5}


def test_parse_spec_returns_an_immutable_spec_with_float_sizes():
    spec = parse_spec(BOX)
    assert spec == Spec("box", 3.0, 4.0, 5.0, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.a = 1.0


def test_pyramid_foot_defaults_to_center_and_other_solids_have_none():
    assert parse_spec({**BOX, "solid": "pyramid"}).foot == "center"
    assert parse_spec(BOX).foot is None


def test_solids_come_from_the_registry():
    assert SOLIDS == tuple(sorted(BUILDERS))


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_every_registered_solid_is_closed(name):
    solid = BUILDERS[name].build(3.0, 4.0, 5.0, "center" if BUILDERS[name].takes_foot else None)
    count: dict[frozenset, int] = {}
    for face in solid.faces:
        for u, v in zip(face, face[1:] + face[:1]):
            count[frozenset((u, v))] = count.get(frozenset((u, v)), 0) + 1
    assert set(count.values()) == {2}
    assert {v for face in solid.faces for v in face} == set(solid.points)


def test_a_new_solid_is_drawn_after_registering_it_without_touching_any_other_module(monkeypatch):
    cube = SolidBuilder(build=lambda a, b, h, foot: BUILDERS["box"].build(a, a, a, None))
    monkeypatch.setitem(BUILDERS, "cube", cube)
    svg = render_svg({"solid": "cube", "a": 2, "b": 9, "h": 9})
    assert svg.count("<line") == 12
    with pytest.raises(FigureError, match="cube"):
        render_svg({"solid": "sphere", "a": 1, "b": 1, "h": 1})


def test_foot_is_accepted_only_by_solids_that_declare_it(monkeypatch):
    monkeypatch.setitem(BUILDERS, "tall", SolidBuilder(build=BUILDERS["pyramid"].build, takes_foot=True))
    assert parse_spec({**BOX, "solid": "tall", "foot": "A"}).foot == "A"
    with pytest.raises(FigureError):
        parse_spec({**BOX, "solid": "tall", "foot": "B"})
    with pytest.raises(FigureError):
        parse_spec({**BOX, "foot": "A"})


def test_an_open_surface_is_rejected_instead_of_drawn_with_wrong_dashes(monkeypatch):
    def open_box(a, b, h, foot):
        solid = BUILDERS["box"].build(a, b, h, None)
        return Solid(solid.points, solid.faces[:-1])  # thiếu một mặt

    monkeypatch.setitem(BUILDERS, "open", SolidBuilder(build=open_box))
    with pytest.raises(FigureError, match="kín"):
        layout({"solid": "open", "a": 1, "b": 1, "h": 1})


def hidden(solid: Solid, view) -> set[frozenset[str]]:
    return {frozenset((e.a, e.b)) for e in classify_edges(solid, view) if e.hidden}


def test_looking_from_the_opposite_side_hides_other_edges():
    solid = BUILDERS["box"].build(3.0, 4.0, 5.0, None)
    front, back = hidden(solid, VIEW), hidden(solid, -VIEW)
    assert len(front) == len(back) == 3 and front != back and not front & back


def test_view_is_a_numpy_vector_pointing_toward_the_viewer():
    assert isinstance(VIEW, np.ndarray) and VIEW[2] < 0
