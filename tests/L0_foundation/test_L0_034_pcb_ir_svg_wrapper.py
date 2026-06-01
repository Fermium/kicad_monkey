"""
Test L0_034: render_pcb_ir_to_svg viewBox / translation behavior.
"""

from __future__ import annotations

import math
import re

from kicad_monkey import KiCadSvgRenderOptions, render_pcb_ir_to_svg
from kicad_monkey.kicad_pcb import KiCadPcb


_PCB_FIXTURE = """(kicad_pcb
\t(version 20240108)
\t(generator "pcbnew")
\t(layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
\t(gr_line (start 10 10) (end 50 10) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 50 10) (end 50 30) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 50 30) (end 10 30) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 10 30) (end 10 10) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
)
"""


_VIEWBOX_RE = re.compile(r'viewBox="([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)"')
_CIRCLE_R_RE = re.compile(r'<circle\b[^>]*\br="([-\d.]+)"')
_POLYGON_POINTS_RE = re.compile(r'<polygon\b[^>]*\bpoints="([^"]+)"')
_TRANSFORM_RE = re.compile(
    r'transform="translate\(([-\d.]+)\s+([-\d.]+)\)\s+rotate\(([-\d.]+)\)"'
)


def _extract_viewbox(svg: str) -> tuple[float, float, float, float]:
    match = _VIEWBOX_RE.search(svg)
    assert match is not None, f"viewBox not found in:\n{svg[:400]}"
    return (
        float(match.group(1)),
        float(match.group(2)),
        float(match.group(3)),
        float(match.group(4)),
    )


def _circle_radii(svg: str) -> list[float]:
    return [float(match.group(1)) for match in _CIRCLE_R_RE.finditer(svg)]


def _first_transformed_polygon_bbox(svg: str) -> tuple[float, float, float, float]:
    transform_match = _TRANSFORM_RE.search(svg)
    assert transform_match is not None, f"transform not found in:\n{svg[:400]}"
    tx, ty, angle = (float(part) for part in transform_match.groups())
    points_match = _POLYGON_POINTS_RE.search(svg)
    assert points_match is not None, f"polygon not found in:\n{svg[:400]}"

    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    transformed: list[tuple[float, float]] = []
    for pair in points_match.group(1).split():
        x, y = (float(part) for part in pair.split(","))
        transformed.append((tx + x * cos_a - y * sin_a, ty + x * sin_a + y * cos_a))

    xs = [x for x, _y in transformed]
    ys = [y for _x, y in transformed]
    return (min(xs), min(ys), max(xs), max(ys))


def test_render_pcb_ir_to_svg_viewbox_uses_centerline_bounds():
    pcb = KiCadPcb.from_string(_PCB_FIXTURE)

    ir_svg = render_pcb_ir_to_svg(pcb)
    ir_vb = _extract_viewbox(ir_svg)

    assert ir_vb[0] == 0.0 and ir_vb[1] == 0.0
    assert ir_vb[2] == 40.0
    assert ir_vb[3] == 20.0


def test_render_pcb_ir_to_svg_translates_content_into_viewbox():
    """Bbox-based offset should land content inside 0..W/0..H user units."""

    pcb = KiCadPcb.from_string(_PCB_FIXTURE)
    svg = render_pcb_ir_to_svg(pcb)
    width, height = _extract_viewbox(svg)[2:]

    # Pull every numeric coordinate from polyline "points" attrs (the
    # current IR renderer emits gr_line as <polyline points="x,y x,y">)
    # and verify they fall within the bbox-derived viewBox (with a small
    # slack for half-stroke spill at the edges).
    point_lists = re.findall(r'points="([^"]+)"', svg)
    assert point_lists, "expected at least one polyline points attribute"
    coords: list[float] = []
    for points_attr in point_lists:
        for pair in points_attr.split():
            x_str, y_str = pair.split(",")
            coords.append(float(x_str))
            coords.append(float(y_str))
    assert coords, "expected at least one drawn coordinate"

    slack = 0.5  # mm
    for v in coords:
        assert -slack <= v <= max(width, height) + slack, (
            f"coord {v} outside viewBox 0..{width} / 0..{height}"
        )


def test_render_pcb_ir_to_svg_empty_board_returns_empty_svg():
    pcb = KiCadPcb.from_string(
        """(kicad_pcb
\t(version 20240108)
\t(generator "pcbnew")
\t(layers (0 "F.Cu" signal))
)
"""
    )
    svg = render_pcb_ir_to_svg(pcb)
    assert 'viewBox="0 0 0 0"' in svg


def test_npth_mask_layer_renders_expanded_aperture_and_hole():
    pcb = KiCadPcb.from_string(
        """(kicad_pcb
\t(version 20240108)
\t(generator "pcbnew")
\t(layers (0 "F.Cu" signal) (36 "F.Mask" user) (44 "Edge.Cuts" user))
\t(setup (pad_to_mask_clearance 0.1016))
\t(footprint "Test:NPTH"
\t\t(layer "F.Cu")
\t\t(at 0 0 0)
\t\t(pad "" np_thru_hole circle
\t\t\t(at 10 10)
\t\t\t(size 2.5 2.5)
\t\t\t(drill 2.5)
\t\t\t(layers "*.Cu" "*.Mask")
\t\t)
\t)
)
"""
    )

    mask_svg = render_pcb_ir_to_svg(pcb, layers=["F.Mask"])
    silk_svg = render_pcb_ir_to_svg(pcb, layers=["Edge.Cuts"])

    mask_radii = sorted(round(radius, 4) for radius in _circle_radii(mask_svg))
    silk_radii = sorted(round(radius, 4) for radius in _circle_radii(silk_svg))

    assert mask_radii == [1.25, 1.3516]
    assert silk_radii == [1.25]


def test_embedded_footprint_pad_angle_is_relative_to_placement():
    pcb = KiCadPcb.from_string(
        """(kicad_pcb
\t(version 20240108)
\t(generator "pcbnew")
\t(layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))
\t(gr_line (start 0 0) (end 30 0) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 30 0) (end 30 30) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 30 30) (end 0 30) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 0 30) (end 0 0) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(footprint "Test:RotatedPad"
\t\t(layer "F.Cu")
\t\t(at 15 15 90)
\t\t(pad "1" smd rect
\t\t\t(at 0 0 90)
\t\t\t(size 4 2)
\t\t\t(layers "F.Cu" "F.Mask" "F.Paste")
\t\t)
\t)
)
"""
    )

    svg = render_pcb_ir_to_svg(pcb, layers=["F.Cu"])
    min_x, min_y, max_x, max_y = _first_transformed_polygon_bbox(svg)
    width = round(max_x - min_x, 4)
    height = round(max_y - min_y, 4)

    assert width == 2.0
    assert height == 4.0


def test_kicad_pcb_to_svg_uses_ir_renderer():
    pcb = KiCadPcb.from_string(_PCB_FIXTURE)

    assert pcb.to_svg() == render_pcb_ir_to_svg(pcb)


def test_render_pcb_ir_to_svg_default_profile_keeps_review_metadata():
    pcb = KiCadPcb.from_string(_PCB_FIXTURE)

    svg = render_pcb_ir_to_svg(pcb)

    assert 'data-ref="gr_line"' in svg


def test_render_pcb_ir_to_svg_kicad_cli_profile_suppresses_metadata():
    pcb = KiCadPcb.from_string(_PCB_FIXTURE)

    svg = render_pcb_ir_to_svg(pcb, profile="kicad_cli")

    assert 'data-ref="' not in svg
    assert 'data-uuid="' not in svg
    assert 'id="' not in svg
    assert "<polyline" in svg


def test_render_pcb_ir_to_svg_kicad_cli_options_suppress_metadata():
    pcb = KiCadPcb.from_string(_PCB_FIXTURE)
    options = KiCadSvgRenderOptions(profile="kicad_cli")

    svg = render_pcb_ir_to_svg(pcb, options=options)

    assert 'data-ref="' not in svg
    assert 'data-uuid="' not in svg
    assert 'id="' not in svg


def test_kicad_pcb_to_svg_forwards_profile_to_ir_renderer():
    pcb = KiCadPcb.from_string(_PCB_FIXTURE)

    assert pcb.to_svg(profile="kicad_cli") == render_pcb_ir_to_svg(
        pcb,
        profile="kicad_cli",
    )


# ---------------------------------------------------------------------------
# Phase B: layer filtering (record-level)
# ---------------------------------------------------------------------------


_LAYER_FILTER_FIXTURE = """(kicad_pcb
\t(version 20240108)
\t(generator "pcbnew")
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(31 "B.Cu" signal)
\t\t(37 "F.SilkS" user)
\t\t(44 "Edge.Cuts" user)
\t)
\t(gr_line (start 0 0) (end 30 0) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 30 0) (end 30 20) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 30 20) (end 0 20) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 0 20) (end 0 0) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
\t(gr_line (start 5 5) (end 25 5) (stroke (width 0.1) (type solid)) (layer "F.SilkS"))
\t(gr_text "TOP"
\t\t(at 15 15 0)
\t\t(layer "F.SilkS")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(segment (start 5 10) (end 25 10) (width 0.25) (layer "F.Cu") (net 0))
)
"""


def test_render_pcb_ir_to_svg_layer_filter_drops_other_layers():
    """Filtering to F.SilkS keeps F.SilkS records and drops Edge.Cuts/F.Cu."""

    from kicad_monkey import pcb_to_ir
    from kicad_monkey.kicad_pcb_ir_svg import _filter_records_by_layer

    pcb = KiCadPcb.from_string(_LAYER_FILTER_FIXTURE)
    doc = pcb_to_ir(pcb)

    all_kinds = sorted({record.kind for record in doc.records})
    assert "gr_line" in all_kinds
    assert "gr_text" in all_kinds
    assert "segment" in all_kinds

    filtered = _filter_records_by_layer(doc.records, ["F.SilkS"])
    kinds = [record.kind for record in filtered]

    # F.SilkS has 1 gr_line and 1 gr_text. The 4 Edge.Cuts lines and the
    # F.Cu segment should be dropped.
    assert kinds.count("gr_line") == 1
    assert kinds.count("gr_text") == 1
    assert "segment" not in kinds


def test_render_pcb_ir_to_svg_layer_filter_none_keeps_all():
    from kicad_monkey import pcb_to_ir
    from kicad_monkey.kicad_pcb_ir_svg import _filter_records_by_layer

    pcb = KiCadPcb.from_string(_LAYER_FILTER_FIXTURE)
    doc = pcb_to_ir(pcb)

    assert len(_filter_records_by_layer(doc.records, None)) == len(doc.records)


def test_render_pcb_ir_to_svg_layer_filter_via_keeps_for_any_layer_in_span():
    """Through-hole vias span multiple layers; selecting any one keeps the via."""

    from kicad_monkey import pcb_to_ir
    from kicad_monkey.kicad_pcb_ir_svg import _filter_records_by_layer

    pcb = KiCadPcb.from_string(
        """(kicad_pcb
\t(version 20240108)
\t(generator "pcbnew")
\t(layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
\t(via (at 10 10) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 0))
\t(gr_line (start 0 0) (end 20 0) (stroke (width 0.15) (type solid)) (layer "Edge.Cuts"))
)
"""
    )
    doc = pcb_to_ir(pcb)

    # F.Cu selection keeps the via (which spans F.Cu+B.Cu) and drops Edge.Cuts gr_line.
    via_only = _filter_records_by_layer(doc.records, ["F.Cu"])
    via_kinds = [record.kind for record in via_only]
    assert "via" in via_kinds
    assert "gr_line" not in via_kinds

    # B.Cu selection keeps the via too.
    via_only_back = _filter_records_by_layer(doc.records, ["B.Cu"])
    assert any(record.kind == "via" for record in via_only_back)

    # Edge.Cuts selection keeps the gr_line and drops the via.
    edge_only = _filter_records_by_layer(doc.records, ["Edge.Cuts"])
    edge_kinds = [record.kind for record in edge_only]
    assert "gr_line" in edge_kinds
    assert "via" not in edge_kinds


def test_render_pcb_ir_to_svg_layer_filter_emits_filtered_svg():
    """End-to-end: rendering with a layer filter produces a shorter SVG."""

    pcb = KiCadPcb.from_string(_LAYER_FILTER_FIXTURE)
    full_svg = render_pcb_ir_to_svg(pcb)
    silks_svg = render_pcb_ir_to_svg(pcb, layers=["F.SilkS"])

    # ViewBox stays the same because all-layer bounding box is independent
    # of the requested render layers.
    assert _extract_viewbox(full_svg) == _extract_viewbox(silks_svg)

    # Counting `data-ref="gr_line"` should drop from 5 (4 Edge.Cuts + 1
    # F.SilkS) to 1 once we filter to F.SilkS.
    assert full_svg.count('data-ref="gr_line"') == 5
    assert silks_svg.count('data-ref="gr_line"') == 1
