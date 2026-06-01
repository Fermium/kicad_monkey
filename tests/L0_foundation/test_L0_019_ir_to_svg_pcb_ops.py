"""
Test L0_019: F-5 / F-7 PCB op dispatch in :mod:`kicad_monkey.kicad_ir_to_svg`.

Covers each PCB-side op kind that the F-7 footprint pipeline emits:

  * ``ThickSegment``        → ``<polyline>`` with stroke width
  * ``ThickArc``            → ``<path>`` (centre+angle → 3-point arc)
  * ``FlashPadCircle``      → filled ``<circle>``
  * ``FlashPadRect``        → rotated ``<polygon>`` (4 corners)
  * ``FlashPadOval``        → stadium polygon
  * ``FlashPadRoundRect``   → rounded-rect polygon
  * ``FlashPadTrapez``      → 4-corner ``<polygon>``
  * ``FlashPadCustom``      → one ``<polygon>`` per polygon ring
  * ``FlashRegularPolygon`` → regular n-gon ``<polygon>``

Each test exercises the dispatch path, asserts the emitted element
type, fill semantics, and that rotation produces the expected geometry
under KiCad's ``RotatePoint`` convention
``(x*cos+y*sin, -x*sin+y*cos)``.
"""

from __future__ import annotations

import math

import pytest

from kicad_monkey import (
    KiCadPlotterOp,
    KiCadPlotterDocument,
    KiCadPlotterRecord,
    KiCadSvgRenderContext,
    KiCadSvgRenderOptions,
    render_ir_to_svg,
    render_record,
    render_op,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx() -> KiCadSvgRenderContext:
    """A4-landscape default context (millimetre user units)."""
    return KiCadSvgRenderContext(
        sheet_width_nm=297_000_000,
        sheet_height_nm=210_000_000,
    )


def layer_ctx(*layers: str) -> KiCadSvgRenderContext:
    return KiCadSvgRenderContext(
        sheet_width_nm=297_000_000,
        sheet_height_nm=210_000_000,
        options=KiCadSvgRenderOptions(visible_layers=layers),
    )


def kicad_cli_ctx() -> KiCadSvgRenderContext:
    return KiCadSvgRenderContext(
        sheet_width_nm=297_000_000,
        sheet_height_nm=210_000_000,
        options=KiCadSvgRenderOptions(profile="kicad_cli"),
    )


def op_with_payload(op: KiCadPlotterOp, **payload) -> KiCadPlotterOp:
    return KiCadPlotterOp(kind=op.kind, payload={**op.payload, **payload})


# ---------------------------------------------------------------------------
# Text Render Cache
# ---------------------------------------------------------------------------


def test_render_op_text_prefers_render_cache_polygons(
    ctx: KiCadSvgRenderContext,
) -> None:
    op = KiCadPlotterOp.text(
        x=10_000_000,
        y=10_000_000,
        text="OK",
        size_x_nm=2_000_000,
        size_y_nm=2_000_000,
        render_cache_polygons=[
            [
                [10_000_000, 10_000_000],
                [12_000_000, 10_000_000],
                [12_000_000, 12_000_000],
                [10_000_000, 12_000_000],
            ]
        ],
    )

    svg = render_op(op, ctx=ctx)

    assert svg.startswith("<polygon")
    assert ">OK<" not in svg


def test_render_op_text_uses_typed_render_cache_holes(
    ctx: KiCadSvgRenderContext,
) -> None:
    op = KiCadPlotterOp.text(
        x=10_000_000,
        y=10_000_000,
        text="O",
        size_x_nm=2_000_000,
        size_y_nm=2_000_000,
        render_cache={
            "schema": "kicad.render_cache.v1",
            "unit": "nm",
            "coordinate_space": "board",
            "text": "O",
            "angle": 0.0,
            "polygons": [
                {
                    "contours": [
                        [
                            [10_000_000, 10_000_000],
                            [14_000_000, 10_000_000],
                            [14_000_000, 14_000_000],
                            [10_000_000, 14_000_000],
                        ],
                        [
                            [11_000_000, 11_000_000],
                            [13_000_000, 11_000_000],
                            [13_000_000, 13_000_000],
                            [11_000_000, 13_000_000],
                        ],
                    ]
                }
            ],
        },
    )

    svg = render_op(op, ctx=ctx)

    assert svg.startswith("<path")
    assert 'fill-rule="evenodd"' in svg
    assert "<polygon" not in svg
    assert ">O<" not in svg


# ---------------------------------------------------------------------------
# ThickSegment
# ---------------------------------------------------------------------------


def test_render_op_thick_segment(ctx: KiCadSvgRenderContext) -> None:
    op = KiCadPlotterOp.thick_segment(
        start_x=10_000_000, start_y=20_000_000,
        end_x=30_000_000, end_y=40_000_000,
        width_nm=200_000,
    )
    svg = render_op(op, ctx=ctx)
    assert svg.startswith("<polyline")
    assert 'fill="none"' in svg
    # Both endpoints converted to mm user units
    assert "10,20" in svg and "30,40" in svg
    assert 'stroke-width="0.2"' in svg


def test_render_op_thick_segment_default_width_falls_through(
    ctx: KiCadSvgRenderContext,
) -> None:
    """``width_nm = 0`` should pass ``None`` so ctx default applies."""
    op = KiCadPlotterOp.thick_segment(
        start_x=0, start_y=0, end_x=1_000_000, end_y=0, width_nm=0,
    )
    svg = render_op(op, ctx=ctx)
    # Renderer must still emit a polyline; explicit zero width is replaced
    # by ctx's current line width default.
    assert svg.startswith("<polyline")


# ---------------------------------------------------------------------------
# ThickArc — centre+angle is converted to a 3-point arc
# ---------------------------------------------------------------------------


def test_render_op_thick_arc_quarter_sweep(ctx: KiCadSvgRenderContext) -> None:
    """
    Centre at (10mm, 10mm), radius 5mm, sweep from 0° → 90°. Expect a
    ``<path>`` whose ``d`` contains an ``A`` (arc) command and the
    end-point is at (10mm, 15mm) — i.e. cy + r*sin(90°) in nm coords.
    """
    op = KiCadPlotterOp.thick_arc(
        cx=10_000_000.0, cy=10_000_000.0,
        start_angle_deg=0.0, sweep_deg=90.0,
        radius_nm=5_000_000.0,
        width_nm=200_000,
    )
    svg = render_op(op, ctx=ctx)
    assert svg.startswith("<path")
    assert " A " in svg
    assert 'stroke-width="0.2"' in svg
    assert 'fill="none"' in svg


# ---------------------------------------------------------------------------
# FlashPadCircle
# ---------------------------------------------------------------------------


def test_render_op_flash_pad_circle(ctx: KiCadSvgRenderContext) -> None:
    op = KiCadPlotterOp.flash_pad_circle(
        x=20_000_000, y=30_000_000, diameter_nm=4_000_000,
    )
    svg = render_op(op, ctx=ctx)
    assert svg.startswith("<circle")
    assert 'cx="20"' in svg and 'cy="30"' in svg
    assert 'r="2"' in svg
    # Pad is filled
    assert 'fill="#000000"' in svg
    assert 'stroke-width="0"' in svg


def test_render_ir_to_svg_filled_flash_pad_uses_stroke_none_bucket() -> None:
    """Filled pad area should not be inflated by the current plot stroke."""
    doc = KiCadPlotterDocument(
        source_kind="PCB",
        canvas={"width_nm": 5_000_000, "height_nm": 5_000_000},
        records=[
            KiCadPlotterRecord(
                uuid="pad",
                kind="footprint",
                object_id="pad",
                operations=[
                    KiCadPlotterOp.flash_pad_roundrect(
                        x=2_000_000,
                        y=2_000_000,
                        size_x_nm=820_000,
                        size_y_nm=220_000,
                        corner_radius_nm=40_000,
                        orient_deg=0.0,
                    )
                ],
                extras={"layer": "F.Cu"},
            ),
        ],
    )

    svg = render_ir_to_svg(
        doc,
        options=KiCadSvgRenderOptions(visible_layers=("F.Cu",)),
    )

    assert "fill:#000000; stroke:none" in svg
    assert "fill:#000000; stroke:#000000; stroke-width:0.1524" not in svg


# ---------------------------------------------------------------------------
# FlashPadRect — rotation correctness
# ---------------------------------------------------------------------------


def test_render_op_flash_pad_rect_axis_aligned(
    ctx: KiCadSvgRenderContext,
) -> None:
    op = KiCadPlotterOp.flash_pad_rect(
        x=10_000_000, y=10_000_000,
        size_x_nm=4_000_000, size_y_nm=2_000_000,
        orient_deg=0.0,
    )
    svg = render_op(op, ctx=ctx)
    assert svg.startswith("<polygon")
    # Corners at (8,9) (12,9) (12,11) (8,11)
    for expected in ("8,9", "12,9", "12,11", "8,11"):
        assert expected in svg, f"missing corner {expected} in {svg!r}"
    assert 'fill="#000000"' in svg
    assert 'stroke-width="0"' in svg


def test_render_op_flash_pad_rect_rotated_90deg(
    ctx: KiCadSvgRenderContext,
) -> None:
    """
    KiCad RotatePoint(theta=90°) maps (x, y) → (y, -x).
    Local corners ±(2mm, 1mm). After 90° rotation:
        (-2,-1) → (-1,  2)
        ( 2,-1) → (-1, -2)
        ( 2, 1) → ( 1, -2)
        (-2, 1) → ( 1,  2)
    Translated by (10mm, 10mm) → (9,12)(9,8)(11,8)(11,12).
    """
    op = KiCadPlotterOp.flash_pad_rect(
        x=10_000_000, y=10_000_000,
        size_x_nm=4_000_000, size_y_nm=2_000_000,
        orient_deg=90.0,
    )
    svg = render_op(op, ctx=ctx)
    for expected in ("9,12", "9,8", "11,8", "11,12"):
        assert expected in svg, f"missing rotated corner {expected} in {svg!r}"


# ---------------------------------------------------------------------------
# FlashPadOval
# ---------------------------------------------------------------------------


def test_render_op_flash_pad_oval_thick_segment(ctx: KiCadSvgRenderContext) -> None:
    op = KiCadPlotterOp.flash_pad_oval(
        x=15_000_000, y=15_000_000,
        size_x_nm=6_000_000, size_y_nm=2_000_000,
        orient_deg=0.0,
    )
    svg = render_op(op, ctx=ctx)
    assert svg.startswith("<polyline")
    assert 'fill="none"' in svg
    assert 'stroke="#000000"' in svg
    assert 'stroke-width="2"' in svg
    assert 'stroke-linecap="round"' in svg
    # PlotPad_Oval emits a thick segment whose centerline endpoints sit
    # at cx +/- (size_x - size_y) / 2 for a horizontal oval.
    assert "13,15" in svg
    assert "17,15" in svg


# ---------------------------------------------------------------------------
# FlashPadRoundRect
# ---------------------------------------------------------------------------


def test_render_op_flash_pad_roundrect_polygon(
    ctx: KiCadSvgRenderContext,
) -> None:
    op = KiCadPlotterOp.flash_pad_roundrect(
        x=10_000_000, y=10_000_000,
        size_x_nm=4_000_000, size_y_nm=2_000_000,
        corner_radius_nm=500_000,
        orient_deg=0.0,
    )
    svg = render_op(op, ctx=ctx)
    assert svg.startswith("<polygon")
    assert 'fill="#000000"' in svg
    assert 'stroke-width="0"' in svg


def test_render_op_flash_pad_roundrect_zero_radius_falls_back_to_rect(
    ctx: KiCadSvgRenderContext,
) -> None:
    op = KiCadPlotterOp.flash_pad_roundrect(
        x=10_000_000, y=10_000_000,
        size_x_nm=4_000_000, size_y_nm=2_000_000,
        corner_radius_nm=0,
        orient_deg=0.0,
    )
    svg = render_op(op, ctx=ctx)
    # 4 corners, no arc approximation
    for expected in ("8,9", "12,9", "12,11", "8,11"):
        assert expected in svg


def test_render_op_flash_pad_roundrect_kicad_cli_uses_fill_only_path() -> None:
    op = KiCadPlotterOp.flash_pad_roundrect(
        x=10_000_000,
        y=10_000_000,
        size_x_nm=4_000_000,
        size_y_nm=2_000_000,
        corner_radius_nm=500_000,
        orient_deg=0.0,
    )

    svg = render_op(op, ctx=kicad_cli_ctx())

    assert svg.startswith("<path")
    assert "<polygon" not in svg
    assert 'fill="#000000"' in svg
    assert 'stroke="none"' in svg
    assert "stroke-width" not in svg
    assert 'fill-rule="evenodd"' in svg


# ---------------------------------------------------------------------------
# FlashPadTrapez
# ---------------------------------------------------------------------------


def test_render_op_flash_pad_trapez_axis_aligned(
    ctx: KiCadSvgRenderContext,
) -> None:
    """Custom 4-corner shape, supplied in pad-local nm. Rotation = 0."""
    op = KiCadPlotterOp.flash_pad_trapez(
        x=10_000_000, y=10_000_000,
        corners=[
            (-2_000_000, -1_000_000),
            (2_000_000, -500_000),
            (2_000_000, 500_000),
            (-2_000_000, 1_000_000),
        ],
        orient_deg=0.0,
    )
    svg = render_op(op, ctx=ctx)
    assert svg.startswith("<polygon")
    assert "8,9" in svg
    assert "12,9.5" in svg
    assert "12,10.5" in svg
    assert "8,11" in svg
    assert 'stroke-width="0"' in svg


def test_render_op_flash_pad_trapez_empty_corners_emits_nothing(
    ctx: KiCadSvgRenderContext,
) -> None:
    """Trapez with no corners (forward-compat) returns empty."""
    # Build the op directly to bypass factory's 4-corner check.
    op = KiCadPlotterOp(
        kind="FlashPadTrapez",
        payload={"x": 0, "y": 0, "corners": [], "orient_deg": 0.0},
    )
    svg = render_op(op, ctx=ctx)
    assert svg == ""


# ---------------------------------------------------------------------------
# FlashPadCustom
# ---------------------------------------------------------------------------


def test_render_op_flash_pad_custom_multiring(
    ctx: KiCadSvgRenderContext,
) -> None:
    op = KiCadPlotterOp.flash_pad_custom(
        x=10_000_000, y=10_000_000,
        size_x_nm=4_000_000, size_y_nm=2_000_000,
        orient_deg=0.0,
        polygons=[
            [[-1_000_000, -1_000_000], [1_000_000, -1_000_000], [0, 1_000_000]],
            [[-500_000, -500_000], [500_000, -500_000], [0, 500_000]],
        ],
    )
    svg = render_op(op, ctx=ctx)
    # Two polygon elements (one per ring)
    assert svg.count("<polygon") == 2
    assert 'fill="#000000"' in svg
    assert svg.count('stroke-width="0"') == 2


def test_render_op_flash_pad_custom_empty_polygons(
    ctx: KiCadSvgRenderContext,
) -> None:
    op = KiCadPlotterOp.flash_pad_custom(
        x=0, y=0, size_x_nm=0, size_y_nm=0, orient_deg=0.0, polygons=[],
    )
    svg = render_op(op, ctx=ctx)
    assert svg == ""


def test_render_op_flash_pad_custom_kicad_cli_uses_paths() -> None:
    op = KiCadPlotterOp.flash_pad_custom(
        x=10_000_000,
        y=10_000_000,
        size_x_nm=4_000_000,
        size_y_nm=2_000_000,
        orient_deg=0.0,
        polygons=[
            [[-1_000_000, -1_000_000], [1_000_000, -1_000_000], [0, 1_000_000]],
            [[-500_000, -500_000], [500_000, -500_000], [0, 500_000]],
        ],
    )

    svg = render_op(op, ctx=kicad_cli_ctx())

    assert svg.count("<path") == 2
    assert "<polygon" not in svg
    assert svg.count('stroke="none"') == 2
    assert svg.count('fill-rule="evenodd"') == 2


# ---------------------------------------------------------------------------
# FlashRegularPolygon
# ---------------------------------------------------------------------------


def test_render_op_flash_reg_polygon_hexagon(
    ctx: KiCadSvgRenderContext,
) -> None:
    op = KiCadPlotterOp.flash_reg_polygon(
        x=10_000_000, y=10_000_000,
        diameter_nm=4_000_000, corner_count=6, orient_deg=0.0,
    )
    svg = render_op(op, ctx=ctx)
    assert svg.startswith("<polygon")
    # 6 vertices → 6 comma-separated pairs in points=
    points_attr_start = svg.index('points="') + len('points="')
    points_attr_end = svg.index('"', points_attr_start)
    pairs = svg[points_attr_start:points_attr_end].split(" ")
    assert len(pairs) == 6
    assert 'stroke-width="0"' in svg


# ---------------------------------------------------------------------------
# Geometry-helper sanity (rotation, stadium, regular polygon)
# ---------------------------------------------------------------------------


def test_rotate_local_point_90deg() -> None:
    from kicad_monkey.kicad_ir_to_svg import _rotate_local_point

    rx, ry = _rotate_local_point(1.0, 0.0, 90.0)
    assert math.isclose(rx, 0.0, abs_tol=1e-9)
    assert math.isclose(ry, -1.0, abs_tol=1e-9)


def test_stadium_local_corners_horizontal_long_axis() -> None:
    from kicad_monkey.kicad_ir_to_svg import _stadium_local_corners

    pts = _stadium_local_corners(6_000_000, 2_000_000)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    # Long axis = X. Extents ±3mm in X, ±1mm in Y.
    assert max(xs) == pytest.approx(3_000_000.0, rel=1e-6)
    assert min(xs) == pytest.approx(-3_000_000.0, rel=1e-6)
    assert max(ys) == pytest.approx(1_000_000.0, rel=1e-6)
    assert min(ys) == pytest.approx(-1_000_000.0, rel=1e-6)


def test_regular_polygon_local_count() -> None:
    from kicad_monkey.kicad_ir_to_svg import _regular_polygon_local

    pts = _regular_polygon_local(4_000_000, 5)
    assert len(pts) == 5
    # All vertices on circle of radius 2mm
    for x, y in pts:
        r = math.hypot(x, y)
        assert math.isclose(r, 2_000_000.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# PCB footprint placement records
# ---------------------------------------------------------------------------


def test_render_record_applies_pcb_footprint_placement_transform(
    ctx: KiCadSvgRenderContext,
) -> None:
    rec = KiCadPlotterRecord(
        uuid="fp1",
        kind="footprint",
        object_id="lib:R",
        operations=[
            KiCadPlotterOp.flash_pad_circle(
                x=1_000_000,
                y=2_000_000,
                diameter_nm=500_000,
            )
        ],
        extras={
            "placement": {
                "x_nm": 10_000_000,
                "y_nm": 20_000_000,
                "angle_deg": 90.0,
            }
        },
    )

    svg = render_record(rec, ctx=ctx)

    assert 'data-ref="footprint"' in svg
    assert 'transform="translate(10 20) rotate(-90)"' in svg
    assert '<circle cx="1" cy="2"' in svg


def test_render_record_kicad_cli_profile_suppresses_source_metadata() -> None:
    ctx = KiCadSvgRenderContext(
        sheet_width_nm=40_000_000,
        sheet_height_nm=30_000_000,
        options=KiCadSvgRenderOptions(profile="kicad_cli"),
    )
    rec = KiCadPlotterRecord(
        uuid="fp-cli",
        kind="footprint",
        object_id="lib:R",
        operations=[
            KiCadPlotterOp.flash_pad_circle(
                x=1_000_000,
                y=2_000_000,
                diameter_nm=500_000,
            )
        ],
        extras={
            "placement": {
                "x_nm": 10_000_000,
                "y_nm": 20_000_000,
                "angle_deg": 90.0,
            }
        },
    )

    svg = render_record(rec, ctx=ctx)

    assert 'transform="translate(10 20) rotate(-90)"' in svg
    assert 'id="fp-cli"' not in svg
    assert "data-uuid" not in svg
    assert "data-ref" not in svg
    assert '<circle cx="1" cy="2"' in svg


def test_render_record_keeps_footprint_local_coords_out_of_board_offset() -> None:
    """Placed footprint children stay footprint-local when the board view is offset."""

    ctx = KiCadSvgRenderContext(
        sheet_width_nm=40_000_000,
        sheet_height_nm=30_000_000,
        offset_x_nm=-100_000_000,
        offset_y_nm=-200_000_000,
    )
    rec = KiCadPlotterRecord(
        uuid="fp-offset",
        kind="footprint",
        object_id="lib:R",
        operations=[
            KiCadPlotterOp.flash_pad_circle(
                x=1_000_000,
                y=2_000_000,
                diameter_nm=500_000,
            )
        ],
        extras={
            "placement": {
                "x_nm": 110_000_000,
                "y_nm": 220_000_000,
                "angle_deg": 90.0,
            }
        },
    )

    svg = render_record(rec, ctx=ctx)

    assert 'transform="translate(10 20) rotate(-90)"' in svg
    assert '<circle cx="1" cy="2"' in svg
    assert 'cx="-99"' not in svg
    assert 'cy="-198"' not in svg


def test_render_record_filters_board_record_by_layer() -> None:
    rec = KiCadPlotterRecord(
        uuid="b-silk",
        kind="gr_line",
        object_id="line",
        operations=[
            KiCadPlotterOp.thick_segment(
                start_x=0,
                start_y=0,
                end_x=1_000_000,
                end_y=0,
                width_nm=100_000,
            )
        ],
        extras={"layer": "B.SilkS"},
    )

    assert render_record(rec, ctx=layer_ctx("F.SilkS")) == ""


def test_render_record_filters_pcb_footprint_ops_by_payload_layer() -> None:
    front = op_with_payload(
        KiCadPlotterOp.flash_pad_circle(
            x=1_000_000,
            y=0,
            diameter_nm=500_000,
        ),
        layer="F.SilkS",
    )
    back = op_with_payload(
        KiCadPlotterOp.flash_pad_circle(
            x=3_000_000,
            y=0,
            diameter_nm=500_000,
        ),
        layer="B.SilkS",
    )
    rec = KiCadPlotterRecord(
        uuid="fp",
        kind="footprint",
        object_id="lib:R",
        operations=[front, back],
        extras={"layer": "F.Cu"},
    )

    svg = render_record(rec, ctx=layer_ctx("F.SilkS"))

    assert '<circle cx="1"' in svg
    assert '<circle cx="3"' not in svg


def test_render_record_filters_pad_ops_by_wildcard_layers() -> None:
    copper_pad = op_with_payload(
        KiCadPlotterOp.flash_pad_circle(
            x=2_000_000,
            y=0,
            diameter_nm=500_000,
        ),
        layers=["*.Cu", "*.Mask"],
    )
    rec = KiCadPlotterRecord(
        uuid="fp",
        kind="footprint",
        object_id="lib:R",
        operations=[copper_pad],
        extras={"layer": "F.Cu"},
    )

    assert '<circle cx="2"' in render_record(rec, ctx=layer_ctx("F.Cu"))
    assert render_record(rec, ctx=layer_ctx("F.SilkS")) == ""


def test_render_record_filters_zone_fill_layers_per_op() -> None:
    front = KiCadPlotterOp.flash_pad_circle(
        x=1_000_000,
        y=0,
        diameter_nm=500_000,
    )
    back = KiCadPlotterOp.flash_pad_circle(
        x=3_000_000,
        y=0,
        diameter_nm=500_000,
    )
    rec = KiCadPlotterRecord(
        uuid="zone",
        kind="zone_fill",
        object_id="zone",
        operations=[front, back],
        extras={"layers": ["F.Cu", "B.Cu"], "fill_layers": ["F.Cu", "B.Cu"]},
    )

    svg = render_record(rec, ctx=layer_ctx("F.Cu"))

    assert '<circle cx="1"' in svg
    assert '<circle cx="3"' not in svg


def test_render_record_keeps_via_visible_on_spanned_inner_copper() -> None:
    rec = KiCadPlotterRecord(
        uuid="via",
        kind="via",
        object_id="via",
        operations=[
            KiCadPlotterOp.flash_pad_circle(
                x=2_000_000,
                y=0,
                diameter_nm=500_000,
            )
        ],
        extras={"layers": ["F.Cu", "B.Cu"]},
    )

    svg = render_record(rec, ctx=layer_ctx("In2.Cu"))

    assert '<circle cx="2"' in svg


def test_render_op_pad_drill_circle_white_on_copper() -> None:
    op = op_with_payload(
        KiCadPlotterOp.circle(cx=1_000_000, cy=0, diameter_nm=400_000),
        role="pad_drill",
    )

    svg = render_op(op, ctx=layer_ctx("F.Cu"))

    assert 'fill="#FFFFFF"' in svg
    assert 'stroke="#FFFFFF"' in svg
    assert 'stroke-width="0"' in svg


def test_render_op_pad_drill_circle_outline_on_non_copper_layer() -> None:
    op = op_with_payload(
        KiCadPlotterOp.circle(cx=1_000_000, cy=0, diameter_nm=400_000),
        role="pad_drill",
    )

    svg = render_op(op, ctx=layer_ctx("F.SilkS"))

    assert 'fill="none"' in svg
    assert 'stroke-width="0.1"' in svg


def test_render_op_pad_drill_slot_white_on_copper() -> None:
    op = op_with_payload(
        KiCadPlotterOp.thick_segment(
            start_x=1_000_000,
            start_y=0,
            end_x=2_000_000,
            end_y=0,
            width_nm=400_000,
        ),
        role="pad_drill",
    )

    svg = render_op(op, ctx=layer_ctx("F.Cu"))

    assert 'stroke="#FFFFFF"' in svg
    assert 'stroke-width="0.4"' in svg


def test_render_ir_to_svg_moves_drill_knockouts_after_later_copper() -> None:
    """Document rendering should leave drill knockouts above all copper."""
    via_aperture = op_with_payload(
        KiCadPlotterOp.flash_pad_circle(
            x=2_000_000,
            y=2_000_000,
            diameter_nm=1_000_000,
        ),
        role="via_aperture",
        layers=["F.Cu", "B.Cu"],
    )
    via_drill = op_with_payload(
        KiCadPlotterOp.circle(
            cx=2_000_000,
            cy=2_000_000,
            diameter_nm=400_000,
        ),
        role="via_drill",
        layers=["F.Cu", "B.Cu"],
    )
    covering_copper = KiCadPlotterOp.flash_pad_circle(
        x=2_000_000,
        y=2_000_000,
        diameter_nm=2_000_000,
    )
    doc = KiCadPlotterDocument(
        source_kind="PCB",
        canvas={"width_nm": 5_000_000, "height_nm": 5_000_000},
        records=[
            KiCadPlotterRecord(
                uuid="via",
                kind="via",
                object_id="via",
                operations=[via_aperture, via_drill],
                extras={"layers": ["F.Cu", "B.Cu"]},
            ),
            KiCadPlotterRecord(
                uuid="later-copper",
                kind="footprint",
                object_id="pad",
                operations=[covering_copper],
                extras={"layer": "F.Cu"},
            ),
        ],
    )

    svg = render_ir_to_svg(
        doc,
        options=KiCadSvgRenderOptions(visible_layers=("F.Cu",)),
    )

    assert 'data-ref="drill_overlay"' in svg
    assert svg.rfind('fill="#FFFFFF"') > svg.rfind('fill="#000000"')
