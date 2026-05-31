"""
L0 unit tests for ``kicad_monkey.kicad_recorder_stroked_text_fold``.

Phase F-6.10 — covers the comparator-side stroked-text fold that
collapses runs of ``FILLED_SHAPE`` ``PlotPoly`` ops into synthetic
``StrokedTextRun`` ops so :func:`compute_recorder_drift` measures the
semantic gap rather than the rendering-mode mismatch between KiCad's
stroke-font glyph polygons and kicad_monkey's declarative ``Text`` ops.
"""

from __future__ import annotations

import pytest

from kicad_monkey import (
    STROKED_TEXT_FOLD_KIND,
    STROKED_TEXT_FOLD_MIN_POINTS,
    STROKED_TEXT_FOLD_MIN_RUN,
    compute_recorder_drift,
    fold_recorder_document,
    fold_stroked_text_runs,
    is_stroked_text_glyph,
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


def _glyph_poly(n_points: int = 5, fill: str = "FILLED_SHAPE") -> KiCadPlotterOp:
    return KiCadPlotterOp(
        kind=KiCadPlotterOpKind("PlotPoly"),
        payload={
            "fill": fill,
            "points": [[i, i] for i in range(n_points)],
        },
    )


def _wire(n_points: int = 2) -> KiCadPlotterOp:
    return KiCadPlotterOp(
        kind=KiCadPlotterOpKind("PlotPoly"),
        payload={
            "fill": "NO_FILL",
            "points": [[i, i] for i in range(n_points)],
        },
    )


def _op(kind: str, **payload) -> KiCadPlotterOp:
    return KiCadPlotterOp(kind=KiCadPlotterOpKind(kind), payload=dict(payload))


def _record(kind: str, ops: list[KiCadPlotterOp]) -> KiCadPlotterRecord:
    return KiCadPlotterRecord(uuid="", kind=kind, object_id="", operations=list(ops))


def _doc(records: list[KiCadPlotterRecord]) -> KiCadPlotterDocument:
    return KiCadPlotterDocument(records=records)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_fold_kind_is_stable_string():
    assert STROKED_TEXT_FOLD_KIND == "StrokedTextRun"


def test_fold_min_points_default_is_five():
    assert STROKED_TEXT_FOLD_MIN_POINTS == 5


def test_fold_min_run_default_is_two():
    assert STROKED_TEXT_FOLD_MIN_RUN == 2


# ---------------------------------------------------------------------------
# is_stroked_text_glyph predicate
# ---------------------------------------------------------------------------


def test_predicate_accepts_filled_polygon_with_five_points():
    assert is_stroked_text_glyph(_glyph_poly(n_points=5))


def test_predicate_accepts_filled_polygon_with_more_points():
    assert is_stroked_text_glyph(_glyph_poly(n_points=20))


def test_predicate_rejects_filled_polygon_below_min_points():
    assert not is_stroked_text_glyph(_glyph_poly(n_points=4))


def test_predicate_rejects_no_fill_polyline():
    assert not is_stroked_text_glyph(_wire(n_points=10))


def test_predicate_rejects_filled_with_bg_bodycolor():
    op = KiCadPlotterOp(
        kind=KiCadPlotterOpKind("PlotPoly"),
        payload={
            "fill": "FILLED_WITH_BG_BODYCOLOR",
            "points": [[i, i] for i in range(8)],
        },
    )
    assert not is_stroked_text_glyph(op)


def test_predicate_rejects_non_plot_poly_ops():
    assert not is_stroked_text_glyph(_op("Circle"))
    assert not is_stroked_text_glyph(_op("Rect"))
    assert not is_stroked_text_glyph(_op("Text"))
    assert not is_stroked_text_glyph(_op("StartPlot"))


def test_predicate_handles_missing_payload_keys():
    op = KiCadPlotterOp(kind=KiCadPlotterOpKind("PlotPoly"), payload={})
    assert not is_stroked_text_glyph(op)


def test_predicate_custom_min_points_threshold():
    op = _glyph_poly(n_points=3)
    assert not is_stroked_text_glyph(op, min_points=5)
    assert is_stroked_text_glyph(op, min_points=3)


# ---------------------------------------------------------------------------
# fold_stroked_text_runs — basic shape
# ---------------------------------------------------------------------------


def test_fold_collapses_two_consecutive_glyph_polygons():
    ops = [_glyph_poly(), _glyph_poly()]
    folded, runs, absorbed = fold_stroked_text_runs(ops)
    assert runs == 1
    assert absorbed == 2
    assert len(folded) == 1
    syn = folded[0]
    assert syn.kind == STROKED_TEXT_FOLD_KIND or (
        hasattr(syn.kind, "value") and syn.kind.value == STROKED_TEXT_FOLD_KIND
    )
    assert syn.payload == {"folded_op_count": 2, "synthetic": True}


def test_fold_emits_one_synthetic_op_per_run():
    # two separated runs → two synthetic ops
    ops = [
        _glyph_poly(), _glyph_poly(), _glyph_poly(),
        _op("SetColor", color="#000000"),
        _glyph_poly(), _glyph_poly(),
    ]
    folded, runs, absorbed = fold_stroked_text_runs(ops)
    assert runs == 2
    assert absorbed == 5
    # synthetic + SetColor + synthetic
    assert len(folded) == 3
    assert folded[0].payload["folded_op_count"] == 3
    assert folded[2].payload["folded_op_count"] == 2


def test_fold_preserves_singleton_glyph_polygon_below_min_run():
    # one glyph poly between non-glyphs → not folded (run < min_run_size)
    ops = [_op("Circle"), _glyph_poly(), _op("Rect")]
    folded, runs, absorbed = fold_stroked_text_runs(ops)
    assert runs == 0
    assert absorbed == 0
    assert len(folded) == 3
    assert folded[1].payload["fill"] == "FILLED_SHAPE"


def test_fold_respects_custom_min_run_size():
    ops = [_glyph_poly(), _glyph_poly(), _glyph_poly()]
    folded, runs, absorbed = fold_stroked_text_runs(ops, min_run_size=3)
    assert runs == 1
    assert absorbed == 3
    assert len(folded) == 1
    # below threshold: run of 2 stays unfolded
    folded2, runs2, _ = fold_stroked_text_runs(
        [_glyph_poly(), _glyph_poly()], min_run_size=3
    )
    assert runs2 == 0
    assert len(folded2) == 2


def test_fold_preserves_wires_unchanged():
    ops = [_wire(), _wire(), _wire()]
    folded, runs, absorbed = fold_stroked_text_runs(ops)
    assert runs == 0
    assert absorbed == 0
    assert folded == ops


def test_fold_preserves_state_ops_between_runs():
    ops = [
        _glyph_poly(), _glyph_poly(),
        _op("SetCurrentLineWidth", width_nm=10000),
        _op("SetColor", color="#FF0000"),
        _glyph_poly(), _glyph_poly(), _glyph_poly(),
    ]
    folded, runs, _ = fold_stroked_text_runs(ops)
    assert runs == 2
    # synthetic + SetCurrentLineWidth + SetColor + synthetic
    assert len(folded) == 4
    kinds = [
        f.kind.value if hasattr(f.kind, "value") else str(f.kind)
        for f in folded
    ]
    assert kinds == [
        STROKED_TEXT_FOLD_KIND,
        "SetCurrentLineWidth",
        "SetColor",
        STROKED_TEXT_FOLD_KIND,
    ]


def test_fold_does_not_fuse_runs_separated_by_non_glyph():
    # NO_FILL polyline (wire) breaks the run
    ops = [_glyph_poly(), _glyph_poly(), _wire(), _glyph_poly(), _glyph_poly()]
    folded, runs, absorbed = fold_stroked_text_runs(ops)
    assert runs == 2
    assert absorbed == 4
    assert len(folded) == 3  # synth + wire + synth


def test_fold_empty_input_returns_empty():
    folded, runs, absorbed = fold_stroked_text_runs([])
    assert folded == []
    assert runs == 0
    assert absorbed == 0


def test_fold_does_not_mutate_input_list():
    ops = [_glyph_poly(), _glyph_poly()]
    snapshot = list(ops)
    fold_stroked_text_runs(ops)
    assert ops == snapshot


def test_fold_custom_min_points_threshold():
    # 3-point filled polys would normally be ignored; allow them via custom threshold
    triangle = KiCadPlotterOp(
        kind=KiCadPlotterOpKind("PlotPoly"),
        payload={"fill": "FILLED_SHAPE", "points": [[0, 0], [1, 0], [0, 1]]},
    )
    ops = [triangle, triangle]
    # default: not folded
    folded, runs, _ = fold_stroked_text_runs(ops)
    assert runs == 0
    assert len(folded) == 2
    # threshold=3: folded
    folded2, runs2, _ = fold_stroked_text_runs(ops, min_points=3)
    assert runs2 == 1
    assert len(folded2) == 1


# ---------------------------------------------------------------------------
# fold_recorder_document — record-level wrapper
# ---------------------------------------------------------------------------


def test_fold_document_collapses_per_record():
    rec1 = _record("a", [_glyph_poly(), _glyph_poly()])
    rec2 = _record("b", [_op("Circle"), _glyph_poly(), _glyph_poly(), _glyph_poly()])
    doc = _doc([rec1, rec2])
    new_doc, runs, absorbed = fold_recorder_document(doc)
    assert runs == 2
    assert absorbed == 5
    assert len(new_doc.records) == 2
    assert len(new_doc.records[0].operations) == 1
    assert len(new_doc.records[1].operations) == 2


def test_fold_document_does_not_fuse_across_records():
    # last op of rec1 + first op of rec2 would form a run of 2 if fused
    rec1 = _record("a", [_op("Circle"), _glyph_poly()])
    rec2 = _record("b", [_glyph_poly(), _op("Rect")])
    doc = _doc([rec1, rec2])
    new_doc, runs, absorbed = fold_recorder_document(doc)
    assert runs == 0
    assert absorbed == 0
    assert len(new_doc.records[0].operations) == 2
    assert len(new_doc.records[1].operations) == 2


def test_fold_document_preserves_canvas_and_metadata():
    doc = KiCadPlotterDocument(
        records=[_record("a", [_glyph_poly(), _glyph_poly()])],
        source_path="x.kicad_sch",
        source_kind="SCH",
        document_id="x",
        canvas={"width_nm": 297000000, "height_nm": 210000000, "page_type": "A4"},
        coordinate_space={"unit": "nm", "y_axis": "down"},
    )
    new_doc, _, _ = fold_recorder_document(doc)
    assert new_doc.source_path == "x.kicad_sch"
    assert new_doc.source_kind == "SCH"
    assert new_doc.document_id == "x"
    assert new_doc.canvas == doc.canvas
    assert new_doc.canvas is not doc.canvas  # defensive copy
    assert new_doc.coordinate_space == doc.coordinate_space


def test_fold_document_preserves_record_uuid_kind_object_id():
    rec = KiCadPlotterRecord(
        uuid="abc-123",
        kind="symbol_instance",
        object_id="R1",
        operations=[_glyph_poly(), _glyph_poly()],
    )
    new_doc, _, _ = fold_recorder_document(_doc([rec]))
    assert new_doc.records[0].uuid == "abc-123"
    assert new_doc.records[0].kind == "symbol_instance"
    assert new_doc.records[0].object_id == "R1"


# ---------------------------------------------------------------------------
# Integration with compute_recorder_drift
# ---------------------------------------------------------------------------


def test_drift_default_applies_fold():
    rec = _doc([_record("d", [_glyph_poly(), _glyph_poly(), _glyph_poly()])])
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    # 3 PlotPoly → 1 StrokedTextRun
    assert rep.recorder_total_ops == 1
    assert rep.recorder_total_ops_pre_fold == 3
    assert rep.stroked_text_runs_folded == 1
    assert rep.stroked_text_ops_absorbed == 3
    assert rep.recorder_hist == {STROKED_TEXT_FOLD_KIND: 1}


def test_drift_fold_disabled_keeps_raw_histogram():
    rec = _doc([_record("d", [_glyph_poly(), _glyph_poly(), _glyph_poly()])])
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk, fold_stroked_text=False)
    assert rep.recorder_total_ops == 3
    assert rep.recorder_total_ops_pre_fold == 3
    assert rep.stroked_text_runs_folded == 0
    assert rep.stroked_text_ops_absorbed == 0
    assert rep.recorder_hist == {"PlotPoly": 3}


def test_drift_synthetic_op_counts_as_geometric():
    # StrokedTextRun must NOT be treated as a state op
    rec = _doc([_record("d", [_glyph_poly(), _glyph_poly()])])
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    assert rep.recorder_geometric_ops == 1


def test_drift_coverage_ratio_improves_with_fold():
    # 4 glyph polys → 1 synthetic; monkey emits 1 Text op → coverage 100%
    rec = _doc([_record("d", [_glyph_poly()] * 4)])
    mk = _doc([_record("text", [_op("Text", text="hello")])])
    rep_raw = compute_recorder_drift(rec, mk, fold_stroked_text=False)
    rep_fold = compute_recorder_drift(rec, mk, fold_stroked_text=True)
    assert rep_raw.coverage_ratio == pytest.approx(0.25)
    assert rep_fold.coverage_ratio == 1.0


def test_drift_fold_provenance_in_to_dict():
    rec = _doc([_record("d", [_glyph_poly(), _glyph_poly()])])
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    out = rep.to_dict()
    assert "stroked_text_fold" in out
    assert out["stroked_text_fold"] == {"runs_folded": 1, "ops_absorbed": 2}
    assert out["op_counts"]["recorder_total_pre_fold"] == 2
    assert out["op_counts"]["recorder_total"] == 1


def test_drift_custom_thresholds_threaded_through():
    # 3-point triangles, 2 of them — default would not fold; threshold 3 should
    triangle = KiCadPlotterOp(
        kind=KiCadPlotterOpKind("PlotPoly"),
        payload={"fill": "FILLED_SHAPE", "points": [[0, 0], [1, 0], [0, 1]]},
    )
    rec = _doc([_record("d", [triangle, triangle])])
    mk = _doc([])
    rep_default = compute_recorder_drift(rec, mk)
    assert rep_default.stroked_text_runs_folded == 0
    rep_custom = compute_recorder_drift(
        rec, mk, stroked_text_min_points=3
    )
    assert rep_custom.stroked_text_runs_folded == 1
