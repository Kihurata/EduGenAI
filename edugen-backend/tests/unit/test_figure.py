"""Hình khối cho câu hình học: tham số LLM → tọa độ → SVG kiểu SGK (T-012, F-17).

Đầu ra mong muốn:
- Điểm (x, y, z) chiếu xiên: mặt trước giữ nguyên, chiều sâu lệch 45° và co ½.
- Hình hộp: 12 cạnh, đúng 3 nét đứt (AD, CD, DD'); chóp S.ABCD đáy chữ nhật: 8 cạnh, nét khuất AD, CD, SD;
  lăng trụ đứng tam giác: 9 cạnh, nét khuất AC, BC, CC'.
- SVG có đúng một nhãn cho mỗi đỉnh, đúng tên (A, B, A', S…); mọi nét và nhãn nằm trong khung; hai nhãn không chồng nhau.
- Cùng tham số cho ra cùng một chuỗi SVG, và SVG không chứa chữ nào do LLM viết.
- Tham số sai (không nhận ra hình, thiếu cạnh, âm, NaN, tỉ lệ quá lệch…) báo FigureError, không đoán.
- with_figure gắn `figure_svg` vào câu; spec hỏng thì bỏ spec, giữ mô tả chữ `figure`, câu vẫn dùng được.
"""

import math
import xml.etree.ElementTree as ET

import pytest

from app.domain.figure import FigureError, label_box, layout, project, render_svg, with_figure

BOX = {"solid": "box", "a": 3, "b": 4, "h": 5}
PYRAMID = {"solid": "pyramid", "a": 3, "b": 4, "h": 5, "foot": "center"}
PRISM = {"solid": "prism", "a": 3, "b": 3, "h": 5}
SPECS = {"box": BOX, "pyramid": PYRAMID, "prism": PRISM}
NAMES = {
    "box": {"A", "B", "C", "D", "A'", "B'", "C'", "D'"},
    "pyramid": {"S", "A", "B", "C", "D"},
    "prism": {"A", "B", "C", "A'", "B'", "C'"},
}


def hidden(spec: dict) -> set[frozenset[str]]:
    return {frozenset((e.a, e.b)) for e in layout(spec).edges if e.hidden}


def pairs(*edges: str) -> set[frozenset[str]]:
    return {frozenset(e.split("-")) for e in edges}


def svg_root(spec: dict) -> ET.Element:
    return ET.fromstring(render_svg(spec))


def lines(spec: dict) -> list[ET.Element]:
    return [el for el in svg_root(spec).iter() if el.tag.endswith("line")]


def texts(spec: dict) -> list[str]:
    return [el.text for el in svg_root(spec).iter() if el.tag.endswith("text")]


def test_oblique_projection_keeps_front_face_and_slants_depth():
    assert project((1, 2, 0)) == pytest.approx((1, 2))
    shift = 3 * 0.5 * math.cos(math.radians(45))
    assert project((1, 2, 3)) == pytest.approx((1 + shift, 2 + shift))


@pytest.mark.parametrize(("name", "edges"), [("box", 12), ("pyramid", 8), ("prism", 9)])
def test_each_solid_has_all_its_edges_and_vertices(name, edges):
    figure = layout(SPECS[name])
    assert len(figure.edges) == edges
    assert {label.name for label in figure.labels} == NAMES[name]
    assert {v for e in figure.edges for v in (e.a, e.b)} == NAMES[name]


def test_box_hides_the_back_left_bottom_corner_edges():
    assert hidden(BOX) == pairs("A-D", "C-D", "D-D'")


def test_pyramid_hides_the_base_back_and_left_edges():
    assert hidden(PYRAMID) == pairs("A-D", "C-D", "S-D")


def test_long_low_pyramid_shows_its_back_face_so_only_one_edge_hides():
    # h > a/2 hides the left face, h < 0.177·b shows the back face: only AD has two hidden faces left
    assert hidden({"solid": "pyramid", "a": 3, "b": 10, "h": 1.6, "foot": "center"}) == pairs("A-D")


def test_very_flat_pyramid_hides_no_edge_because_every_slanted_face_faces_the_viewer():
    assert hidden({"solid": "pyramid", "a": 3, "b": 4, "h": 0.5, "foot": "center"}) == set()


def test_pyramid_over_vertex_a_hides_the_base_and_left_edges():
    assert hidden({**PYRAMID, "foot": "A"}) == pairs("A-D", "C-D", "S-D")


def test_prism_hides_the_edges_of_its_back_corner():
    assert hidden(PRISM) == pairs("A-C", "B-C", "C-C'")


@pytest.mark.parametrize("name", SPECS)
def test_svg_has_one_solid_or_dashed_line_per_edge(name):
    dashed = [el for el in lines(SPECS[name]) if el.get("stroke-dasharray")]
    assert len(dashed) == len(hidden(SPECS[name]))
    assert len(lines(SPECS[name])) == len(layout(SPECS[name]).edges)


def test_box_svg_has_three_dashed_and_nine_solid_lines():
    dashed = [el for el in lines(BOX) if el.get("stroke-dasharray")]
    assert (len(dashed), len(lines(BOX)) - len(dashed)) == (3, 9)


@pytest.mark.parametrize("name", SPECS)
def test_svg_has_one_text_label_per_vertex_with_the_exact_name(name):
    assert sorted(texts(SPECS[name])) == sorted(NAMES[name])


@pytest.mark.parametrize("name", SPECS)
def test_svg_is_well_formed_with_a_viewbox(name):
    root = svg_root(SPECS[name])
    assert root.tag.endswith("svg")
    width, height = float(root.get("width")), float(root.get("height"))
    assert root.get("viewBox") == f"0 0 {width:g} {height:g}"


DIMS = [(3, 4, 5), (1, 1, 1), (1, 10, 1), (10, 1, 10), (2.5, 3.5, 0.5), (100, 100, 100), (0.01, 0.02, 0.01)]


def solids():
    for name, base in SPECS.items():
        for a, b, h in DIMS:
            yield pytest.param({**base, "a": a, "b": b, "h": h}, id=f"{name}-{a}x{b}x{h}")


@pytest.mark.parametrize("spec", list(solids()))
def test_every_line_and_label_is_inside_the_frame(spec):
    figure = layout(spec)
    for x, y in figure.points.values():
        assert 0 <= x <= figure.width and 0 <= y <= figure.height
    for label in figure.labels:
        x0, y0, x1, y1 = label_box(label)
        assert 0 <= x0 and x1 <= figure.width and 0 <= y0 and y1 <= figure.height


@pytest.mark.parametrize("spec", list(solids()))
def test_no_two_labels_overlap(spec):
    boxes = [(label.name, label_box(label)) for label in layout(spec).labels]
    for i, (n1, (ax0, ay0, ax1, ay1)) in enumerate(boxes):
        for n2, (bx0, by0, bx1, by1) in boxes[i + 1 :]:
            assert ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0, f"{n1} overlaps {n2}"


def test_label_sits_outside_its_vertex():
    figure = layout(BOX)
    for label in figure.labels:
        x0, y0, x1, y1 = label_box(label)
        vx, vy = figure.points[label.name]
        assert not (x0 < vx < x1 and y0 < vy < y1)


def test_same_spec_gives_the_same_svg_every_time():
    assert render_svg(PYRAMID) == render_svg(dict(PYRAMID))
    assert render_svg(BOX) != render_svg({**BOX, "h": 2})


def test_ints_and_floats_are_both_accepted():
    assert render_svg({**BOX, "a": 3.0}) == render_svg(BOX)


def test_nothing_written_by_the_llm_reaches_the_svg():
    spec = {**BOX, "names": "<script>alert(1)</script>", "title": "<img src=x>"}
    svg = render_svg(spec)
    assert "script" not in svg and "<img" not in svg and "alert" not in svg


def test_extra_keys_are_ignored():
    assert render_svg({**BOX, "unused": 1}) == render_svg(BOX)


@pytest.mark.parametrize("foot", [None, "center"])
def test_pyramid_foot_defaults_to_center(foot):
    spec = {k: v for k, v in PYRAMID.items() if k != "foot"}
    assert render_svg({**spec, "foot": foot}) == render_svg(PYRAMID)


def test_pyramid_foot_a_differs_from_center():
    assert render_svg({**PYRAMID, "foot": "A"}) != render_svg(PYRAMID)


BAD_SPECS = [
    pytest.param(None, id="none"),
    pytest.param("hinh chop", id="string"),
    pytest.param([], id="list"),
    pytest.param({}, id="empty"),
    pytest.param({**BOX, "solid": "sphere"}, id="unknown-solid"),
    pytest.param({**BOX, "solid": None}, id="solid-null"),
    pytest.param({**BOX, "solid": "BOX"}, id="solid-case"),
    pytest.param({"solid": "box", "a": 3, "b": 4}, id="missing-h"),
    pytest.param({**BOX, "a": 0}, id="zero"),
    pytest.param({**BOX, "a": -3}, id="negative"),
    pytest.param({**BOX, "a": float("nan")}, id="nan"),
    pytest.param({**BOX, "a": float("inf")}, id="inf"),
    pytest.param({**BOX, "a": "3"}, id="numeric-string"),
    pytest.param({**BOX, "a": True}, id="bool"),
    pytest.param({**BOX, "a": None}, id="dim-null"),
    pytest.param({**BOX, "a": 1, "b": 11, "h": 1}, id="ratio-too-skewed"),
    pytest.param({**BOX, "a": 1e-9, "b": 1, "h": 1}, id="tiny-vs-others"),
    pytest.param({**PYRAMID, "foot": "B"}, id="bad-foot"),
    pytest.param({**BOX, "foot": "A"}, id="foot-on-box"),
]


@pytest.mark.parametrize("spec", BAD_SPECS)
def test_bad_spec_raises_figure_error(spec):
    with pytest.raises(FigureError):
        render_svg(spec)
    with pytest.raises(FigureError):
        layout(spec)


QUESTION = {"type": "multiple_choice", "stem": "Cho hình chóp $S.ABCD$", "figure": "Chóp S.ABCD, đáy chữ nhật"}


def test_with_figure_adds_the_svg_and_keeps_the_text_description():
    q = with_figure(QUESTION | {"figure_spec": PYRAMID})
    assert q["figure_svg"] == render_svg(PYRAMID)
    assert q["figure_spec"] == PYRAMID
    assert q["figure"] == QUESTION["figure"]


def test_with_figure_does_not_change_the_question_it_was_given():
    original = QUESTION | {"figure_spec": PYRAMID}
    with_figure(original)
    assert "figure_svg" not in original


def test_question_without_a_spec_stays_as_it_is():
    assert with_figure(QUESTION) == QUESTION


@pytest.mark.parametrize("empty", [None, {}])
def test_empty_spec_is_the_same_as_no_spec(empty):
    assert with_figure(QUESTION | {"figure_spec": empty}) == QUESTION


def test_a_stale_svg_is_dropped_when_the_spec_is_gone():
    assert with_figure(QUESTION | {"figure_svg": "<svg/>"}) == QUESTION


def test_bad_spec_is_dropped_and_the_text_description_is_kept():
    q = with_figure(QUESTION | {"figure_spec": {**PYRAMID, "a": -1}, "figure_svg": "<svg/>"})
    assert q == QUESTION


def test_spec_that_is_not_a_dict_is_dropped_too():
    assert with_figure(QUESTION | {"figure_spec": "hinh chop"}) == QUESTION


def test_a_changed_spec_replaces_the_old_svg():
    old = with_figure(QUESTION | {"figure_spec": PYRAMID})
    new = with_figure(old | {"figure_spec": {**PYRAMID, "h": 2}})
    assert new["figure_svg"] == render_svg({**PYRAMID, "h": 2}) != old["figure_svg"]


def test_overlap_check_keeps_a_gap_between_labels():
    from app.domain.figure.labels import covers, overlaps

    assert overlaps((0, 0, 10, 10), [(5, 5, 15, 15)])
    assert overlaps((0, 0, 10, 10), [(10.5, 0, 20, 10)])  # chạm sát: thiếu khe hở
    assert not overlaps((0, 0, 10, 10), [(12, 0, 20, 10)])
    assert not overlaps((0, 0, 10, 10), [])
    assert covers((0, 0, 10, 10), (5, 5)) and covers((0, 0, 10, 10), (10.5, 5))
    assert not covers((0, 0, 10, 10), (12, 5))
