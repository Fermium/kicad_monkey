"""
L0 unit tests for ``kicad_monkey.kicad_op_equivalence``.

Phase F-6.11 — covers the tolerance-aware op-by-op equivalence diff
that pairs a recorder document against a kicad_monkey document by
document order, with the F-6.10 stroked-text fold applied to the
recorder side and the recorder's pure-state ops dropped.

These tests construct synthetic two-side documents directly and verify
each branch of :func:`compute_op_equivalence` (kind, coord-length,
coord-delta, length divergences, fold integration, state-op filtering,
``equivalent`` and ``to_dict`` shape).
"""

from __future__ import annotations

import pytest

from kicad_monkey import (
    KICAD_OP_EQUIVALENCE_SCHEMA,
    MATCH_STRATEGY_BY_KIND,
    MATCH_STRATEGY_POSITIONAL,
    MATCH_STRATEGY_WINDOWED_BY_KIND,
    MATCH_WINDOW_UNBOUNDED,
    KiCadOpDivergence,
    OpEquivalenceReport,
    compute_op_equivalence,
)
from kicad_monkey.kicad_plotter_ir import (
    KiCadPlotterDocument,
    KiCadPlotterOp,
    KiCadPlotterOpKind,
    KiCadPlotterRecord,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _op(kind: str, **payload) -> KiCadPlotterOp:
    return KiCadPlotterOp(kind=KiCadPlotterOpKind(kind), payload=dict(payload))


def _record(kind: str, ops: list[KiCadPlotterOp]) -> KiCadPlotterRecord:
    return KiCadPlotterRecord(uuid="", kind=kind, object_id="", operations=list(ops))


def _doc(records: list[KiCadPlotterRecord]) -> KiCadPlotterDocument:
    return KiCadPlotterDocument(records=records)


def _glyph_poly(n_points: int = 5) -> KiCadPlotterOp:
    return _op(
        "PlotPoly",
        fill="FILLED_SHAPE",
        points=[[i, i] for i in range(n_points)],
    )


def _circle(cx=0, cy=0, d=100) -> KiCadPlotterOp:
    return _op("Circle", cx=cx, cy=cy, diameter_nm=d)


def _text(x=0, y=0, sx=1000, sy=1000) -> KiCadPlotterOp:
    return _op("Text", x=x, y=y, size_x_nm=sx, size_y_nm=sy)


def _rect(x1=0, y1=0, x2=10, y2=10) -> KiCadPlotterOp:
    return _op("Rect", x1=x1, y1=y1, x2=x2, y2=y2)


def _polyline(points, **payload) -> KiCadPlotterOp:
    return _op("PlotPoly", fill="NO_FILL", points=list(points), **payload)


def _wrap(*ops) -> KiCadPlotterDocument:
    return _doc([_record("Misc", list(ops))])


# ---------------------------------------------------------------------------
# Schema constant
# ---------------------------------------------------------------------------


def test_schema_constant_is_stable():
    assert KICAD_OP_EQUIVALENCE_SCHEMA == "kicad.op_equivalence.v1"


def test_default_report_uses_schema_constant():
    rep = OpEquivalenceReport()
    assert rep.schema == KICAD_OP_EQUIVALENCE_SCHEMA


# ---------------------------------------------------------------------------
# Equivalent streams
# ---------------------------------------------------------------------------


def test_identical_streams_are_equivalent():
    doc = _wrap(_circle(1, 2, 100), _rect(0, 0, 10, 10))
    rep = compute_op_equivalence(doc, doc)
    assert rep.equivalent is True
    assert rep.first_divergence is None
    assert rep.matched_pairs == 2
    assert rep.recorder_total == 2
    assert rep.monkey_total == 2
    assert rep.max_observed_coord_delta_nm == 0.0


def test_unfilled_two_point_plotpoly_direction_is_equivalent():
    rec = _wrap(_polyline([[10, 0], [0, 0]]))
    mk = _wrap(_polyline([[0, 0], [10, 0]]))
    rep = compute_op_equivalence(rec, mk)
    assert rep.equivalent is True
    assert rep.matched_pairs == 1


def test_recorder_style_state_matches_declarative_payload():
    rec = _wrap(
        _op("SetColor", color="#0A141EFF"),
        _op("SetDash", line_width_nm=254000, line_style="DASH_DOT"),
        _op(
            "PlotPoly",
            points=[[0, 0], [1000, 0]],
            fill="NO_FILL",
            width_nm=254000,
        ),
    )
    mk = _wrap(
        _op(
            "PlotPoly",
            points=[[0, 0], [1000, 0]],
            fill="NO_FILL",
            width_nm=254000,
            stroke_color="#0A141EFF",
            line_style="DASH_DOT",
        )
    )

    rep = compute_op_equivalence(rec, mk, compare_styles=True)

    assert rep.equivalent is True
    assert rep.matched_pairs == 1
    assert rep.style_mismatches == 0


def test_compare_styles_reports_style_mismatch():
    rec = _wrap(
        _op("SetColor", color="#0A141EFF"),
        _op("PlotPoly", points=[[0, 0], [1000, 0]], fill="NO_FILL", width_nm=10),
    )
    mk = _wrap(
        _op(
            "PlotPoly",
            points=[[0, 0], [1000, 0]],
            fill="NO_FILL",
            width_nm=10,
            stroke_color="#000000FF",
        )
    )

    rep = compute_op_equivalence(rec, mk, compare_styles=True)

    assert rep.equivalent is False
    assert rep.style_mismatches == 1
    assert rep.first_divergence is not None
    assert rep.first_divergence.kind == "style_mismatch"


def test_rect_corner_order_is_equivalent():
    rec = _wrap(_rect(10, 20, 0, 0))
    mk = _wrap(_rect(0, 0, 10, 20))
    rep = compute_op_equivalence(rec, mk)
    assert rep.equivalent is True
    assert rep.matched_pairs == 1


def test_empty_streams_are_equivalent():
    rep = compute_op_equivalence(_wrap(), _wrap())
    assert rep.equivalent is True
    assert rep.matched_pairs == 0
    assert rep.first_divergence is None


# ---------------------------------------------------------------------------
# Kind mismatch
# ---------------------------------------------------------------------------


def test_kind_mismatch_reports_first_divergence():
    rec = _wrap(_circle(0, 0, 100))
    mk = _wrap(_rect(0, 0, 100, 100))
    rep = compute_op_equivalence(rec, mk, fold_pen_to_runs=True)
    assert rep.equivalent is False
    assert rep.kind_mismatches == 1
    div = rep.first_divergence
    assert div is not None
    assert div.position == 0
    assert div.kind == "kind_mismatch"
    assert "Circle" in div.details and "Rect" in div.details


def test_kind_equivalence_strokedtextrun_matches_text():
    # 5-point filled poly counts as a glyph; two consecutive runs fold.
    rec = _wrap(_glyph_poly(), _glyph_poly())
    mk = _wrap(_text(x=0, y=0, sx=0, sy=0))
    rep = compute_op_equivalence(rec, mk, fold_pen_to_runs=True)
    # Fold collapses 2 glyphs -> 1 StrokedTextRun, then equiv to Text.
    assert rep.stroked_text_runs_folded == 1
    assert rep.stroked_text_ops_absorbed == 2
    assert rep.recorder_total == 1
    assert rep.monkey_total == 1
    # StrokedTextRun has no coord fields, so coord lengths are both 0.
    # Text has 4 coord fields (x, y, size_x, size_y).
    # Different lengths -> coord_length_mismatch (the v1 diff).
    assert rep.first_divergence is not None
    assert rep.first_divergence.kind == "coord_length_mismatch"


def test_ignore_stroked_text_runs_keeps_logical_text_match():
    rec = _wrap(_text(x=100, y=200), _glyph_poly(), _glyph_poly())
    mk = _wrap(_text(x=100, y=200))

    rep = compute_op_equivalence(rec, mk, ignore_stroked_text_runs=True)

    assert rep.ignore_stroked_text_runs is True
    assert rep.stroked_text_runs_folded == 1
    assert rep.recorder_total == 1
    assert rep.monkey_total == 1
    assert rep.matched_pairs == 1
    assert rep.equivalent is True


def test_multiline_text_splits_to_recorder_line_ops_by_default():
    rec = _wrap(
        _op(
            "Text",
            x=100,
            y=1_000,
            text="first",
            size_x_nm=1_000,
            size_y_nm=1_000,
            v_align="GR_TEXT_V_ALIGN_BOTTOM",
        ),
        _op(
            "Text",
            x=100,
            y=2_680,
            text="second",
            size_x_nm=1_000,
            size_y_nm=1_000,
            v_align="GR_TEXT_V_ALIGN_BOTTOM",
        ),
    )
    mk = _wrap(
        _op(
            "Text",
            x=100,
            y=2_680,
            text="first\nsecond",
            size_x_nm=1_000,
            size_y_nm=1_000,
            v_align="GR_TEXT_V_ALIGN_BOTTOM",
            multiline=True,
        )
    )

    rep = compute_op_equivalence(rec, mk)

    assert rep.equivalent is True
    assert rep.recorder_total == 2
    assert rep.monkey_total == 2
    assert rep.matched_pairs == 2


def test_multiline_text_split_keeps_line_text_strict():
    rec = _wrap(
        _op(
            "Text",
            x=100,
            y=1_000,
            text="first",
            size_x_nm=1_000,
            size_y_nm=1_000,
            v_align="GR_TEXT_V_ALIGN_BOTTOM",
        ),
        _op(
            "Text",
            x=100,
            y=2_680,
            text="changed",
            size_x_nm=1_000,
            size_y_nm=1_000,
            v_align="GR_TEXT_V_ALIGN_BOTTOM",
        ),
    )
    mk = _wrap(
        _op(
            "Text",
            x=100,
            y=2_680,
            text="first\nsecond",
            size_x_nm=1_000,
            size_y_nm=1_000,
            v_align="GR_TEXT_V_ALIGN_BOTTOM",
            multiline=True,
        )
    )

    rep = compute_op_equivalence(rec, mk)

    assert rep.equivalent is False
    assert rep.style_mismatches == 1
    assert rep.first_divergence is not None
    assert rep.first_divergence.kind == "style_mismatch"


# ---------------------------------------------------------------------------
# Coord-length mismatch
# ---------------------------------------------------------------------------


def test_coord_length_mismatch_polyline_vertex_count():
    rec = _wrap(_polyline([[0, 0], [1, 1], [2, 2]]))
    mk = _wrap(_polyline([[0, 0], [1, 1]]))
    rep = compute_op_equivalence(rec, mk)
    assert rep.coord_length_mismatches == 1
    div = rep.first_divergence
    assert div is not None
    assert div.kind == "coord_length_mismatch"
    assert div.position == 0


# ---------------------------------------------------------------------------
# Coord-delta within / outside tolerance
# ---------------------------------------------------------------------------


def test_coord_delta_within_tolerance_is_matched():
    rec = _wrap(_circle(0, 0, 100))
    mk = _wrap(_circle(0, 0, 105))
    rep = compute_op_equivalence(rec, mk, tolerance_nm=10.0)
    assert rep.equivalent is True
    assert rep.matched_pairs == 1
    assert rep.max_observed_coord_delta_nm == 5.0


def test_coord_delta_exceeds_tolerance_is_divergent():
    rec = _wrap(_circle(0, 0, 100))
    mk = _wrap(_circle(0, 0, 200))
    rep = compute_op_equivalence(rec, mk, tolerance_nm=10.0)
    assert rep.equivalent is False
    assert rep.coord_delta_exceeded == 1
    div = rep.first_divergence
    assert div is not None
    assert div.kind == "coord_delta_exceeded"
    assert div.max_coord_delta_nm == 100.0


def test_same_style_text_anchor_drift_is_semantic_equivalence_by_default():
    common = {
        "text": "TestPoint",
        "color": "#949391FF",
        "orient_deg": 0.0,
        "size_x_nm": 1_270_000,
        "size_y_nm": 1_270_000,
        "h_align": "GR_TEXT_H_ALIGN_CENTER",
        "v_align": "GR_TEXT_V_ALIGN_CENTER",
        "pen_width_nm": 152_400,
        "italic": False,
        "bold": False,
        "font_face": "Arial",
    }
    rec = _wrap(_op("Text", x=647_670_300, y=139_962_000, **common))
    mk = _wrap(_op("Text", x=647_770_358, y=139_962_000, **common))

    rep = compute_op_equivalence(
        rec,
        mk,
        tolerance_nm=10_000.0,
        match_strategy="windowed_by_kind",
        compare_styles=True,
    )

    assert rep.equivalent is True
    assert rep.matched_pairs == 1
    assert rep.max_observed_coord_delta_nm == 100_058.0


def test_text_anchor_semantic_equivalence_requires_exact_style():
    rec = _wrap(
        _op(
            "Text",
            x=308_610_000,
            y=258_724_400,
            text="1",
            color="#A90000FF",
            orient_deg=0.0,
            size_x_nm=1_270_000,
            size_y_nm=1_270_000,
            h_align="GR_TEXT_H_ALIGN_CENTER",
            v_align="GR_TEXT_V_ALIGN_BOTTOM",
            pen_width_nm=254_000,
            italic=False,
            bold=False,
            font_face="Arial",
        )
    )
    mk = _wrap(
        _op(
            "Text",
            x=308_610_000,
            y=258_826_000,
            text="1",
            color="#A90000FF",
            orient_deg=0.0,
            size_x_nm=1_270_000,
            size_y_nm=1_270_000,
            h_align="GR_TEXT_H_ALIGN_CENTER",
            v_align="GR_TEXT_V_ALIGN_BOTTOM",
            pen_width_nm=152_400,
            italic=False,
            bold=False,
            font_face="Arial",
        )
    )

    rep = compute_op_equivalence(
        rec,
        mk,
        tolerance_nm=10_000.0,
        match_strategy="windowed_by_kind",
        compare_styles=True,
    )

    assert rep.equivalent is False
    assert rep.matched_pairs == 0
    assert rep.monkey_short == 1
    assert rep.monkey_long == 1


def test_same_center_dnp_marker_bbox_drift_is_semantic_equivalence():
    rec = _wrap(
        _op(
            "ThickSegment",
            start_x=192_709_800,
            start_y=35_788_500,
            end_x=195_910_200,
            end_y=42_951_500,
            width_nm=457_200,
            stroke_color="#DC090DD9",
            line_style="SOLID",
        )
    )
    mk = _wrap(
        _op(
            "ThickSegment",
            start_x=192_801_240,
            start_y=35_971_480,
            end_x=195_818_760,
            end_y=42_768_520,
            width_nm=457_200,
            stroke_color="#DC090DD9",
        )
    )

    rep = compute_op_equivalence(
        rec,
        mk,
        tolerance_nm=10_000.0,
        match_strategy="windowed_by_kind",
        compare_styles=True,
    )

    assert rep.equivalent is True
    assert rep.matched_pairs == 1
    assert rep.max_observed_coord_delta_nm == 182_980.0


def test_dnp_marker_semantic_equivalence_requires_same_center():
    rec = _wrap(
        _op(
            "ThickSegment",
            start_x=0,
            start_y=0,
            end_x=1_000_000,
            end_y=1_000_000,
            width_nm=457_200,
            stroke_color="#DC090DD9",
        )
    )
    mk = _wrap(
        _op(
            "ThickSegment",
            start_x=40_000,
            start_y=0,
            end_x=1_040_000,
            end_y=1_000_000,
            width_nm=457_200,
            stroke_color="#DC090DD9",
        )
    )

    rep = compute_op_equivalence(
        rec,
        mk,
        tolerance_nm=10_000.0,
        match_strategy="windowed_by_kind",
        compare_styles=True,
    )

    assert rep.equivalent is False
    assert rep.matched_pairs == 0


def test_dnp_marker_semantic_equivalence_does_not_apply_to_wire_segments():
    rec = _wrap(
        _op(
            "ThickSegment",
            start_x=0,
            start_y=0,
            end_x=1_000_000,
            end_y=1_000_000,
            width_nm=457_200,
            stroke_color="#009600FF",
        )
    )
    mk = _wrap(
        _op(
            "ThickSegment",
            start_x=100_000,
            start_y=100_000,
            end_x=900_000,
            end_y=900_000,
            width_nm=457_200,
            stroke_color="#009600FF",
        )
    )

    rep = compute_op_equivalence(
        rec,
        mk,
        tolerance_nm=10_000.0,
        match_strategy="windowed_by_kind",
        compare_styles=True,
    )

    assert rep.equivalent is False
    assert rep.matched_pairs == 0


def test_global_label_box_far_edge_drift_is_semantic_equivalence():
    common = {
        "fill": "NO_FILL",
        "width_nm": 152_400,
        "stroke_color": "#840000FF",
        "line_style": "SOLID",
    }
    rec = _wrap(
        _op(
            "PlotPoly",
            points=[
                [100_000_000, 50_000_000],
                [99_238_000, 50_000_000],
                [97_968_000, 51_270_000],
                [99_238_000, 52_540_000],
                [100_000_000, 52_540_000],
                [100_000_000, 50_000_000],
                [100_000_000, 50_000_000],
            ],
            **common,
        )
    )
    mk = _wrap(
        _op(
            "PlotPoly",
            points=[
                [100_000_000, 50_000_000],
                [99_238_000, 50_000_000],
                [97_707_021, 51_270_000],
                [99_238_000, 52_540_000],
                [100_000_000, 52_540_000],
                [100_000_000, 50_000_000],
                [100_000_000, 50_000_000],
            ],
            **common,
        )
    )

    rep = compute_op_equivalence(
        rec,
        mk,
        tolerance_nm=10_000.0,
        match_strategy="windowed_by_kind",
        compare_styles=True,
    )

    assert rep.equivalent is True
    assert rep.matched_pairs == 1
    assert rep.max_observed_coord_delta_nm == 260_979.0


def test_global_label_box_semantic_equivalence_requires_same_anchor():
    common = {
        "fill": "NO_FILL",
        "width_nm": 152_400,
        "stroke_color": "#840000FF",
        "line_style": "SOLID",
    }
    points = [
        [100_000_000, 50_000_000],
        [99_238_000, 50_000_000],
        [97_968_000, 51_270_000],
        [99_238_000, 52_540_000],
        [100_000_000, 52_540_000],
        [100_000_000, 50_000_000],
        [100_000_000, 50_000_000],
    ]
    rec = _wrap(_op("PlotPoly", points=points, **common))
    mk = _wrap(
        _op(
            "PlotPoly",
            points=[
                [100_025_000, 50_000_000],
                [99_263_000, 50_000_000],
                [97_732_021, 51_270_000],
                [99_263_000, 52_540_000],
                [100_025_000, 52_540_000],
                [100_025_000, 50_000_000],
                [100_025_000, 50_000_000],
            ],
            **common,
        )
    )

    rep = compute_op_equivalence(
        rec,
        mk,
        tolerance_nm=10_000.0,
        match_strategy="windowed_by_kind",
        compare_styles=True,
    )

    assert rep.equivalent is False
    assert rep.matched_pairs == 0


def test_global_label_box_semantic_equivalence_requires_same_shape_direction():
    common = {
        "fill": "NO_FILL",
        "width_nm": 152_400,
        "stroke_color": "#840000FF",
        "line_style": "SOLID",
    }
    rec = _wrap(
        _op(
            "PlotPoly",
            points=[
                [100_000_000, 50_000_000],
                [99_238_000, 50_000_000],
                [97_968_000, 51_270_000],
                [99_238_000, 52_540_000],
                [100_000_000, 52_540_000],
                [100_000_000, 50_000_000],
                [100_000_000, 50_000_000],
            ],
            **common,
        )
    )
    mk = _wrap(
        _op(
            "PlotPoly",
            points=[
                [100_000_000, 50_000_000],
                [100_762_000, 50_000_000],
                [102_292_979, 51_270_000],
                [100_762_000, 52_540_000],
                [100_000_000, 52_540_000],
                [100_000_000, 50_000_000],
                [100_000_000, 50_000_000],
            ],
            **common,
        )
    )

    rep = compute_op_equivalence(
        rec,
        mk,
        tolerance_nm=10_000.0,
        match_strategy="windowed_by_kind",
        compare_styles=True,
    )

    assert rep.equivalent is False
    assert rep.matched_pairs == 0


def test_max_observed_delta_tracks_largest_in_pass():
    rec = _wrap(_circle(0, 0, 100), _circle(50, 0, 100))
    mk = _wrap(_circle(3, 0, 100), _circle(50, 0, 107))
    rep = compute_op_equivalence(rec, mk, tolerance_nm=10.0)
    assert rep.equivalent is True
    assert rep.max_observed_coord_delta_nm == 7.0


# ---------------------------------------------------------------------------
# Length divergences
# ---------------------------------------------------------------------------


def test_monkey_short_when_recorder_has_more_ops():
    rec = _wrap(_circle(), _circle(1, 1, 100))
    mk = _wrap(_circle())
    rep = compute_op_equivalence(rec, mk)
    assert rep.equivalent is False
    assert rep.monkey_short == 1
    assert rep.monkey_long == 0
    div = rep.first_divergence
    assert div is not None
    assert div.kind == "monkey_short"
    assert div.position == 1


def test_monkey_long_when_monkey_has_more_ops():
    rec = _wrap(_circle())
    mk = _wrap(_circle(), _circle(1, 1, 100))
    rep = compute_op_equivalence(rec, mk)
    assert rep.equivalent is False
    assert rep.monkey_short == 0
    assert rep.monkey_long == 1
    div = rep.first_divergence
    assert div is not None
    assert div.kind == "monkey_long"
    assert div.position == 1


# ---------------------------------------------------------------------------
# State-op filtering
# ---------------------------------------------------------------------------


def test_recorder_state_ops_are_filtered():
    rec = _wrap(
        _op("StartPlot"),
        _op("SetColor", r=0, g=0, b=0),
        _op("SetCurrentLineWidth", width_nm=100),
        _circle(0, 0, 100),
        _op("PenTo", x=0, y=0),
        _op("EndPlot"),
    )
    mk = _wrap(_circle(0, 0, 100))
    rep = compute_op_equivalence(rec, mk)
    assert rep.equivalent is True
    assert rep.recorder_total == 1
    assert rep.monkey_total == 1


def test_recorder_pen_to_runs_fold_to_declarative_polyline():
    rec = _wrap(
        _op("SetCurrentLineWidth", width_nm=152_400),
        _op("PenTo", x=0, y=0, action="U"),
        _op("PenTo", x=10, y=0, action="D"),
        _op("PenTo", x=10, y=10, action="D"),
        _op("PenTo", x=10, y=10, action="Z"),
    )
    mk = _wrap(_polyline([[0, 0], [10, 0], [10, 10]], width_nm=152_400))

    rep = compute_op_equivalence(rec, mk, fold_pen_to_runs=True)

    assert rep.equivalent is True
    assert rep.recorder_total == 1
    assert rep.monkey_total == 1
    assert rep.matched_pairs == 1


def test_recorder_thick_segment_matches_declarative_polyline():
    rec = _wrap(
        _op(
            "ThickSegment",
            start_x=10,
            start_y=0,
            end_x=0,
            end_y=0,
            width_nm=152_400,
        )
    )
    mk = _wrap(_polyline([[0, 0], [10, 0]], width_nm=152_400))

    rep = compute_op_equivalence(rec, mk, fold_pen_to_runs=True)

    assert rep.equivalent is True
    assert rep.recorder_total == 1
    assert rep.monkey_total == 1
    assert rep.matched_pairs == 1


def test_plot_image_dimensions_are_coordinates_not_stroke_style():
    rec = _wrap(_op("PlotImage", x=0, y=0, stroke_color="#840000FF"))
    mk = _wrap(
        _op(
            "PlotImage",
            x=0,
            y=0,
            width_nm=0,
            height_nm=0,
            stroke_color="#840000FF",
        )
    )

    rep = compute_op_equivalence(rec, mk, compare_styles=True)

    assert rep.equivalent is True
    assert rep.style_mismatches == 0
    assert rep.matched_pairs == 1


def test_recorder_fill_outline_rect_pair_merges_to_declarative_rect():
    rec = _wrap(
        _op(
            "Rect",
            x1=0,
            y1=0,
            x2=10,
            y2=20,
            fill="FILLED_WITH_BG_BODYCOLOR",
            width_nm=0,
        ),
        _op("Rect", x1=0, y1=0, x2=10, y2=20, fill="NO_FILL", width_nm=152_400),
    )
    mk = _wrap(
        _op(
            "Rect",
            x1=0,
            y1=0,
            x2=10,
            y2=20,
            fill="FILLED_WITH_BG_BODYCOLOR",
            width_nm=152_400,
        )
    )

    rep = compute_op_equivalence(rec, mk)

    assert rep.equivalent is True
    assert rep.recorder_total == 1
    assert rep.monkey_total == 1


# ---------------------------------------------------------------------------
# Fold integration
# ---------------------------------------------------------------------------


def test_fold_disabled_keeps_glyph_polys():
    rec = _wrap(_glyph_poly(), _glyph_poly())
    mk = _wrap(_text())
    rep = compute_op_equivalence(rec, mk, fold_stroked_text=False)
    assert rep.stroked_text_runs_folded == 0
    assert rep.stroked_text_ops_absorbed == 0
    # 2 PlotPoly vs 1 Text -> kind mismatch at position 0
    assert rep.first_divergence is not None
    assert rep.first_divergence.kind == "kind_mismatch"


def test_fold_enabled_collapses_glyph_runs():
    rec = _wrap(_glyph_poly(), _glyph_poly(), _glyph_poly())
    mk = _wrap(_text())
    rep = compute_op_equivalence(rec, mk, fold_stroked_text=True)
    assert rep.stroked_text_runs_folded == 1
    assert rep.stroked_text_ops_absorbed == 3
    assert rep.recorder_total == 1


def test_exact_opaque_duplicate_text_overdraw_is_semantic_equivalence():
    text = _op(
        "Text",
        x=353_060_000,
        y=258_064_000,
        text="R1",
        color="#006464FF",
        orient_deg=0.0,
        size_x_nm=1_828_800,
        size_y_nm=1_828_800,
        h_align="GR_TEXT_H_ALIGN_CENTER",
        v_align="GR_TEXT_V_ALIGN_CENTER",
        pen_width_nm=254_000,
        italic=False,
        bold=False,
        font_face="Arial",
    )

    rep = compute_op_equivalence(_wrap(text, text), _wrap(text))

    assert rep.equivalent is True
    assert rep.recorder_total == 1
    assert rep.monkey_short == 0


def test_opaque_duplicate_overdraw_normalizes_default_line_style():
    rec_a = _op(
        "Rect",
        x1=0,
        y1=0,
        x2=10,
        y2=10,
        fill="NO_FILL",
        width_nm=100,
        stroke_color="#840000FF",
    )
    rec_b = _op(
        "Rect",
        x1=0,
        y1=0,
        x2=10,
        y2=10,
        fill="NO_FILL",
        width_nm=100,
        stroke_color="#840000FF",
        line_style="SOLID",
    )
    mk = _op(
        "Rect",
        x1=0,
        y1=0,
        x2=10,
        y2=10,
        fill="NO_FILL",
        width_nm=100,
        stroke_color="#840000FF",
        line_style="DEFAULT",
    )

    rep = compute_op_equivalence(_wrap(rec_a, rec_b), _wrap(mk))

    assert rep.equivalent is True
    assert rep.recorder_total == 1
    assert rep.monkey_total == 1


def test_translucent_duplicate_overdraw_is_not_collapsed():
    text = _op(
        "Text",
        x=0,
        y=0,
        text="A",
        color="#00000080",
        size_x_nm=1_000,
        size_y_nm=1_000,
    )

    rep = compute_op_equivalence(_wrap(text, text), _wrap(text))

    assert rep.equivalent is False
    assert rep.recorder_total == 2
    assert rep.monkey_short == 1


# ---------------------------------------------------------------------------
# equivalent property semantics
# ---------------------------------------------------------------------------


def test_equivalent_property_requires_no_first_divergence_and_no_length_drift():
    # Length drift alone (no positional divergence) sets equivalent=False
    rec = _wrap(_circle(), _circle())
    mk = _wrap(_circle())
    rep = compute_op_equivalence(rec, mk)
    assert rep.equivalent is False
    assert rep.first_divergence is not None  # populated by length-divergence path


# ---------------------------------------------------------------------------
# to_dict shape
# ---------------------------------------------------------------------------


def test_report_to_dict_top_level_shape():
    rep = compute_op_equivalence(_wrap(_circle()), _wrap(_circle()))
    d = rep.to_dict()
    assert set(d.keys()) == {
        "schema",
        "tolerance_nm",
        "fold_stroked_text",
        "fold_pen_to_runs",
        "ignore_stroked_text_runs",
        "match_strategy",
        "match_window",
        "compare_styles",
        "equivalent",
        "stream_sizes",
        "pair_outcomes",
        "length_divergence",
        "first_divergence",
        "stroked_text_fold",
        "max_observed_coord_delta_nm",
    }
    assert d["schema"] == KICAD_OP_EQUIVALENCE_SCHEMA
    assert d["equivalent"] is True
    assert set(d["stream_sizes"].keys()) == {"recorder_total", "monkey_total"}
    assert set(d["pair_outcomes"].keys()) == {
        "matched",
        "kind_mismatches",
        "coord_length_mismatches",
        "coord_delta_exceeded",
        "style_mismatches",
    }
    assert set(d["length_divergence"].keys()) == {"monkey_short", "monkey_long"}
    assert set(d["stroked_text_fold"].keys()) == {"runs_folded", "ops_absorbed"}


def test_report_to_dict_first_divergence_serializes():
    rec = _wrap(_circle(0, 0, 100))
    mk = _wrap(_rect(0, 0, 100, 100))
    rep = compute_op_equivalence(rec, mk)
    d = rep.to_dict()
    assert d["first_divergence"] is not None
    fd = d["first_divergence"]
    assert set(fd.keys()) >= {
        "position",
        "kind",
        "details",
        "recorder_op",
        "monkey_op",
        "max_coord_delta_nm",
    }
    assert fd["kind"] == "kind_mismatch"
    assert fd["position"] == 0


# ---------------------------------------------------------------------------
# KiCadOpDivergence dataclass
# ---------------------------------------------------------------------------


def test_divergence_to_dict_with_no_ops():
    div = KiCadOpDivergence(position=3, kind="monkey_short", details="no more ops")
    d = div.to_dict()
    assert d["position"] == 3
    assert d["kind"] == "monkey_short"
    assert d["recorder_op"] is None
    assert d["monkey_op"] is None
    assert d["max_coord_delta_nm"] is None


def test_divergence_to_dict_with_ops_serializes_them():
    rec_op = _circle(0, 0, 100)
    mk_op = _rect(0, 0, 100, 100)
    div = KiCadOpDivergence(
        position=0,
        kind="kind_mismatch",
        recorder_op=rec_op,
        monkey_op=mk_op,
        details="x",
    )
    d = div.to_dict()
    assert isinstance(d["recorder_op"], dict)
    assert isinstance(d["monkey_op"], dict)


# ---------------------------------------------------------------------------
# match_strategy="by_kind" (F-6.11 v2)
# ---------------------------------------------------------------------------


def test_match_strategy_constants_are_stable():
    assert MATCH_STRATEGY_POSITIONAL == "positional"
    assert MATCH_STRATEGY_BY_KIND == "by_kind"


def test_default_match_strategy_is_positional():
    rep = compute_op_equivalence(_wrap(_circle()), _wrap(_circle()))
    assert rep.match_strategy == "positional"


def test_invalid_match_strategy_raises_value_error():
    with pytest.raises(ValueError, match="match_strategy"):
        compute_op_equivalence(_wrap(_circle()), _wrap(_circle()), match_strategy="bogus")


def test_by_kind_label_in_report():
    rep = compute_op_equivalence(
        _wrap(_circle()), _wrap(_circle()), match_strategy="by_kind"
    )
    assert rep.match_strategy == "by_kind"
    assert rep.to_dict()["match_strategy"] == "by_kind"


def test_by_kind_pairs_across_reordered_streams():
    # Recorder: Circle -> Rect; Monkey: Rect -> Circle. Positional sees
    # 2 kind_mismatches; by_kind sees 2 matched pairs (within each kind
    # bucket, n=1 pair).
    rec = _wrap(_circle(cx=0, cy=0), _rect(0, 0, 10, 10))
    mk = _wrap(_rect(0, 0, 10, 10), _circle(cx=0, cy=0))

    pos = compute_op_equivalence(rec, mk)
    assert pos.match_strategy == "positional"
    assert pos.kind_mismatches == 2
    assert pos.matched_pairs == 0
    assert pos.equivalent is False

    by_kind = compute_op_equivalence(rec, mk, match_strategy="by_kind")
    assert by_kind.match_strategy == "by_kind"
    assert by_kind.kind_mismatches == 0
    assert by_kind.matched_pairs == 2
    assert by_kind.equivalent is True
    assert by_kind.first_divergence is None


def test_by_kind_drawing_sheet_first_vs_last_caveat_resolved():
    # Models the canonical real-fixture caveat: KiCad emits the drawing
    # sheet last (Rect border + Texts), kicad_monkey emits it first.
    # Positional trips at op 0 (kind_mismatch). by_kind aligns matching
    # kinds across the reordering and reports zero divergences.
    border = _rect(0, 0, 297, 210)  # title-block border
    title_text = _text(x=10, y=10)
    body_circle = _circle(cx=50, cy=50)

    # Recorder: body first, then drawing sheet
    rec = _wrap(body_circle, border, title_text)
    # Monkey: drawing sheet first, then body
    mk = _wrap(border, title_text, body_circle)

    pos = compute_op_equivalence(rec, mk)
    assert pos.first_divergence is not None
    assert pos.first_divergence.position == 0
    assert pos.first_divergence.kind == "kind_mismatch"

    by_kind = compute_op_equivalence(rec, mk, match_strategy="by_kind")
    assert by_kind.equivalent is True
    assert by_kind.matched_pairs == 3
    assert by_kind.kind_mismatches == 0


def test_by_kind_per_kind_population_imbalance_to_monkey_short():
    # Recorder: 2 Circles, 1 Rect. Monkey: 1 Circle, 1 Rect.
    # by_kind: Circle bucket has 1 leftover recorder op (no monkey
    # partner) → monkey_short=1.
    rec = _wrap(_circle(cx=0, cy=0), _circle(cx=10, cy=10), _rect(0, 0, 1, 1))
    mk = _wrap(_circle(cx=0, cy=0), _rect(0, 0, 1, 1))

    rep = compute_op_equivalence(rec, mk, match_strategy="by_kind")
    assert rep.matched_pairs == 2
    assert rep.kind_mismatches == 0
    assert rep.monkey_short == 1
    assert rep.monkey_long == 0
    assert rep.first_divergence is not None
    assert rep.first_divergence.kind == "monkey_short"
    assert "Circle" in rep.first_divergence.details
    assert rep.equivalent is False


def test_by_kind_per_kind_population_imbalance_to_monkey_long():
    # Recorder: 1 Rect. Monkey: 1 Rect, 2 Circles.
    # by_kind: Circle bucket has 2 leftover monkey ops → monkey_long=2.
    rec = _wrap(_rect(0, 0, 1, 1))
    mk = _wrap(_rect(0, 0, 1, 1), _circle(cx=0, cy=0), _circle(cx=10, cy=10))

    rep = compute_op_equivalence(rec, mk, match_strategy="by_kind")
    assert rep.matched_pairs == 1
    assert rep.kind_mismatches == 0
    assert rep.monkey_short == 0
    assert rep.monkey_long == 2
    assert rep.first_divergence is not None
    assert rep.first_divergence.kind == "monkey_long"
    assert "Circle" in rep.first_divergence.details


def test_by_kind_propagates_coord_delta_within_bucket():
    # Two Circle ops on each side; second pair has a 5nm coord delta.
    rec = _wrap(_circle(cx=0, cy=0, d=100), _circle(cx=100, cy=100, d=100))
    mk = _wrap(_circle(cx=0, cy=0, d=100), _circle(cx=105, cy=100, d=100))

    rep_strict = compute_op_equivalence(rec, mk, match_strategy="by_kind")
    assert rep_strict.coord_delta_exceeded == 1
    assert rep_strict.first_divergence.kind == "coord_delta_exceeded"
    assert "by_kind" in rep_strict.first_divergence.details
    assert rep_strict.max_observed_coord_delta_nm == 5.0

    rep_tol = compute_op_equivalence(
        rec, mk, tolerance_nm=10.0, match_strategy="by_kind"
    )
    assert rep_tol.coord_delta_exceeded == 0
    assert rep_tol.equivalent is True
    assert rep_tol.max_observed_coord_delta_nm == 5.0


def test_by_kind_propagates_coord_length_mismatch_within_bucket():
    # Both sides have one PlotPoly each (so by_kind pairs them) but the
    # vertex count differs.
    rec = _wrap(_polyline([[0, 0], [10, 0], [10, 10]]))
    mk = _wrap(_polyline([[0, 0], [10, 10]]))

    rep = compute_op_equivalence(rec, mk, match_strategy="by_kind")
    assert rep.coord_length_mismatches == 1
    assert rep.first_divergence.kind == "coord_length_mismatch"
    assert "by_kind" in rep.first_divergence.details


def test_by_kind_first_divergence_orders_by_recorder_appearance():
    # Two kinds: Rect and Circle; Rect appears first in recorder so its
    # bucket is checked first. Both buckets have leftovers; first
    # divergence should be the Rect leftover.
    rec = _wrap(_rect(0, 0, 1, 1), _rect(2, 2, 3, 3), _circle(cx=0, cy=0), _circle(cx=10, cy=0))
    mk = _wrap(_rect(0, 0, 1, 1), _circle(cx=0, cy=0))

    rep = compute_op_equivalence(rec, mk, match_strategy="by_kind")
    assert rep.first_divergence is not None
    assert rep.first_divergence.kind == "monkey_short"
    assert "Rect" in rep.first_divergence.details


def test_by_kind_stroked_text_fold_equivalence_still_collapses():
    # StrokedTextRun ↔ Text equivalence still applies in by_kind mode
    # because _equivalent_kind is used to canonicalize bucket keys.
    rec = _wrap(_glyph_poly(5), _glyph_poly(5))  # folds to 1 StrokedTextRun
    mk = _wrap(_text())
    rep = compute_op_equivalence(rec, mk, match_strategy="by_kind")
    assert rep.stroked_text_runs_folded == 1
    assert rep.matched_pairs == 0  # synthetic StrokedTextRun has no coords
    # synthetic kind has empty coord vector → coord_length_mismatch (Text has 4)
    assert rep.coord_length_mismatches == 1


# ---------------------------------------------------------------------------
# match_strategy="windowed_by_kind" (F-6.11 v3)
# ---------------------------------------------------------------------------


def test_windowed_by_kind_constant_pinned():
    # Lazy-export wiring: name reachable from package surface.
    from kicad_monkey import (
        MATCH_STRATEGY_WINDOWED_BY_KIND as _STRAT,
        MATCH_WINDOW_UNBOUNDED as _UNB,
    )
    assert _STRAT == "windowed_by_kind"
    assert _UNB == 0
    assert MATCH_STRATEGY_WINDOWED_BY_KIND == "windowed_by_kind"
    assert MATCH_WINDOW_UNBOUNDED == 0


def test_windowed_by_kind_default_match_window_is_zero():
    # The default report carries match_window=0 (unbounded).
    rep = compute_op_equivalence(_wrap(_circle()), _wrap(_circle()))
    assert rep.match_window == 0


def test_windowed_by_kind_label_in_report():
    rep = compute_op_equivalence(
        _wrap(_circle()),
        _wrap(_circle()),
        match_strategy="windowed_by_kind",
    )
    assert rep.match_strategy == "windowed_by_kind"
    d = rep.to_dict()
    assert d["match_strategy"] == "windowed_by_kind"
    assert d["match_window"] == 0


def test_windowed_by_kind_match_window_in_report():
    rep = compute_op_equivalence(
        _wrap(_circle()),
        _wrap(_circle()),
        match_strategy="windowed_by_kind",
        match_window=3,
    )
    assert rep.match_window == 3
    assert rep.to_dict()["match_window"] == 3


def test_windowed_by_kind_negative_match_window_raises():
    with pytest.raises(ValueError, match="match_window"):
        compute_op_equivalence(
            _wrap(_circle()),
            _wrap(_circle()),
            match_strategy="windowed_by_kind",
            match_window=-1,
        )


def test_windowed_by_kind_swapped_intra_kind_pairs_match():
    # Two Text ops in swapped order within a single Text bucket.
    # by_kind would coord_delta_exceeded both pairs; windowed_by_kind
    # with default unbounded window picks the lowest-delta pairing first.
    a = _text(x=0, y=0)
    b = _text(x=100_000, y=200_000)
    rec = _wrap(a, b)
    mk = _wrap(_text(x=100_000, y=200_000), _text(x=0, y=0))
    rep = compute_op_equivalence(rec, mk, match_strategy="windowed_by_kind")
    assert rep.equivalent is True
    assert rep.matched_pairs == 2
    assert rep.monkey_short == 0
    assert rep.monkey_long == 0
    assert rep.first_divergence is None


def test_windowed_by_kind_window_caps_displacement():
    # Displacement of 2 within bucket; window=1 forbids the swap so it
    # cannot pair → both ops fall through to monkey_short / monkey_long.
    rec = _wrap(_text(x=0, y=0), _text(x=10, y=10), _text(x=999_000, y=999_000))
    mk = _wrap(_text(x=999_000, y=999_000), _text(x=10, y=10), _text(x=0, y=0))
    rep = compute_op_equivalence(
        rec, mk, match_strategy="windowed_by_kind", match_window=1
    )
    # Middle op (idx 1) still pairs (within window), but the corner pair
    # at (rec[0], mk[2]) and (rec[2], mk[0]) are window-forbidden.
    assert rep.matched_pairs == 1
    assert rep.monkey_short == 2
    assert rep.monkey_long == 2
    assert rep.first_divergence is not None


def test_windowed_by_kind_unbounded_handles_full_bucket_swap():
    # Same fixture as the windowed test but with default (unbounded)
    # window — full bucket sweep finds all three matches.
    rec = _wrap(_text(x=0, y=0), _text(x=10, y=10), _text(x=999_000, y=999_000))
    mk = _wrap(_text(x=999_000, y=999_000), _text(x=10, y=10), _text(x=0, y=0))
    rep = compute_op_equivalence(rec, mk, match_strategy="windowed_by_kind")
    assert rep.equivalent is True
    assert rep.matched_pairs == 3


def test_windowed_by_kind_population_imbalance_to_monkey_short():
    rec = _wrap(_circle(cx=0), _circle(cx=100), _circle(cx=200))
    mk = _wrap(_circle(cx=100), _circle(cx=0))
    rep = compute_op_equivalence(rec, mk, match_strategy="windowed_by_kind")
    assert rep.matched_pairs == 2
    assert rep.monkey_short == 1
    assert rep.monkey_long == 0
    assert rep.first_divergence is not None
    assert rep.first_divergence.kind == "monkey_short"
    assert "Circle" in rep.first_divergence.details
    assert "windowed_by_kind" in rep.first_divergence.details


def test_windowed_by_kind_population_imbalance_to_monkey_long():
    rec = _wrap(_circle(cx=0))
    mk = _wrap(_circle(cx=0), _circle(cx=100), _circle(cx=200))
    rep = compute_op_equivalence(rec, mk, match_strategy="windowed_by_kind")
    assert rep.matched_pairs == 1
    assert rep.monkey_long == 2
    assert rep.first_divergence is not None
    assert rep.first_divergence.kind == "monkey_long"
    assert "Circle" in rep.first_divergence.details


def test_windowed_by_kind_tolerance_drives_pair_acceptance():
    # Out-of-tolerance pair leaves both ops as leftover.
    rec = _wrap(_circle(cx=0))
    mk = _wrap(_circle(cx=100))
    rep_strict = compute_op_equivalence(rec, mk, match_strategy="windowed_by_kind")
    assert rep_strict.matched_pairs == 0
    assert rep_strict.monkey_short == 1
    assert rep_strict.monkey_long == 1
    # Loosen tolerance → pair consumed.
    rep_loose = compute_op_equivalence(
        rec, mk, tolerance_nm=200.0, match_strategy="windowed_by_kind"
    )
    assert rep_loose.matched_pairs == 1
    assert rep_loose.equivalent is True


def test_windowed_by_kind_reports_closest_style_mismatch_before_far_style_match():
    rec = _wrap(_op("Circle", cx=0, cy=0, diameter_nm=100, stroke_color="#FF0000FF"))
    mk = _wrap(
        _op("Circle", cx=0, cy=0, diameter_nm=100, stroke_color="#0000FFFF"),
        _op("Circle", cx=100, cy=0, diameter_nm=100, stroke_color="#FF0000FF"),
    )

    rep = compute_op_equivalence(
        rec,
        mk,
        match_strategy="windowed_by_kind",
        compare_styles=True,
    )

    assert rep.style_mismatches == 1
    assert rep.first_divergence is not None
    assert rep.first_divergence.kind == "style_mismatch"


def test_windowed_by_kind_max_observed_delta_tracks_all_candidates():
    # Even when a pair can't be matched (tolerance=0), the delta is
    # observed and surfaces in max_observed_coord_delta_nm.
    rec = _wrap(_circle(cx=0))
    mk = _wrap(_circle(cx=42))
    rep = compute_op_equivalence(rec, mk, match_strategy="windowed_by_kind")
    assert rep.max_observed_coord_delta_nm == 42.0
    assert rep.matched_pairs == 0


def test_windowed_by_kind_coord_length_mismatch_leaves_unmatched():
    # PlotPolys with different vertex counts in the same bucket: the
    # mismatched-length pair is excluded from candidates entirely (so
    # both surface as leftovers, not as coord_length_mismatches).
    rec = _wrap(_polyline([(0, 0), (10, 10)]))
    mk = _wrap(_polyline([(0, 0), (10, 10), (20, 20)]))
    rep = compute_op_equivalence(rec, mk, match_strategy="windowed_by_kind")
    assert rep.coord_length_mismatches == 0
    assert rep.matched_pairs == 0
    assert rep.monkey_short == 1
    assert rep.monkey_long == 1


def test_windowed_by_kind_multi_kind_buckets_independent():
    # Reordered Text bucket + correct Circle bucket: both should pair.
    rec = _wrap(_text(x=0), _text(x=100), _circle(cx=5))
    mk = _wrap(_circle(cx=5), _text(x=100), _text(x=0))
    rep = compute_op_equivalence(rec, mk, match_strategy="windowed_by_kind")
    assert rep.equivalent is True
    assert rep.matched_pairs == 3
    assert rep.kind_mismatches == 0


def test_windowed_by_kind_invalid_strategy_still_raises():
    # Sanity: validation order — bad strategy raises even if match_window valid.
    with pytest.raises(ValueError, match="match_strategy"):
        compute_op_equivalence(
            _wrap(_circle()),
            _wrap(_circle()),
            match_strategy="bogus",
            match_window=2,
        )
