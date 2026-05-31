"""
L0 unit tests for ``kicad_monkey.kicad_recorder_drift``.

Phase F-6.2 — covers the cross-validation drift reporter that compares
a canonical ``kicad.plotter_recorder.v1`` document against a
kicad_monkey ``KiCadPlotterDocument`` (typically produced by
``schematic_to_ir``).
"""

from __future__ import annotations

import pytest

from kicad_monkey import (
    KICAD_RECORDER_DRIFT_SCHEMA,
    RecorderDriftReport,
    compute_recorder_drift,
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


def _doc(records: list[KiCadPlotterRecord], canvas: dict | None = None) -> KiCadPlotterDocument:
    return KiCadPlotterDocument(
        records=records,
        source_path=None,
        source_kind="SCH",
        document_id=None,
        canvas=canvas,
        coordinate_space={"unit": "nm", "y_axis": "down"},
    )


def _record(kind: str, ops: list[KiCadPlotterOp]) -> KiCadPlotterRecord:
    return KiCadPlotterRecord(
        uuid="",
        kind=kind,
        object_id="",
        operations=list(ops),
    )


# ---------------------------------------------------------------------------
# Schema constant
# ---------------------------------------------------------------------------


def test_drift_schema_constant_value():
    assert KICAD_RECORDER_DRIFT_SCHEMA == "kicad.recorder_drift.v1"


def test_drift_report_default_schema():
    rep = RecorderDriftReport()
    assert rep.schema == KICAD_RECORDER_DRIFT_SCHEMA


# ---------------------------------------------------------------------------
# Op counting + coverage
# ---------------------------------------------------------------------------


def test_compute_drift_counts_total_ops_recorder_side():
    rec = _doc([_record("recorder_dump", [_op("Circle", x=0, y=0, diameter_nm=1)] * 5)])
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    assert rep.recorder_total_ops == 5
    assert rep.monkey_total_ops == 0


def test_compute_drift_counts_total_ops_monkey_side():
    rec = _doc([])
    mk = _doc([_record("wire", [_op("PlotPoly", points=[])] * 3)])
    rep = compute_recorder_drift(rec, mk)
    assert rep.recorder_total_ops == 0
    assert rep.monkey_total_ops == 3


def test_compute_drift_geometric_excludes_state_kinds():
    # 4 state ops + 2 geometric ops → 2 geometric
    rec = _doc(
        [
            _record(
                "recorder_dump",
                [
                    _op("StartPlot"),
                    _op("SetColor", color="#FF0000"),
                    _op("SetCurrentLineWidth", width_nm=10000),
                    _op("Circle", x=0, y=0, diameter_nm=100),
                    _op("PlotPoly", points=[]),
                    _op("EndPlot"),
                ],
            )
        ]
    )
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    assert rep.recorder_total_ops == 6
    assert rep.recorder_geometric_ops == 2


@pytest.mark.parametrize(
    "state_kind",
    [
        "SetColor",
        "SetCurrentLineWidth",
        "SetDash",
        "SetViewport",
        "SetPageSettings",
        "StartPlot",
        "EndPlot",
        "StartBlock",
        "EndBlock",
        "PenTo",
    ],
)
def test_compute_drift_each_state_kind_excluded_from_geometric(state_kind):
    rec = _doc([_record("recorder_dump", [_op(state_kind)])])
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    assert rep.recorder_total_ops == 1
    assert rep.recorder_geometric_ops == 0


def test_compute_drift_coverage_ratio_zero_when_no_geometric():
    rec = _doc([_record("recorder_dump", [_op("StartPlot"), _op("EndPlot")])])
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    assert rep.coverage_ratio == 0.0


def test_compute_drift_coverage_ratio_full_match():
    rec = _doc([_record("recorder_dump", [_op("Circle"), _op("Rect"), _op("Text")])])
    mk = _doc(
        [
            _record(
                "wire", [_op("PlotPoly"), _op("PlotPoly"), _op("PlotPoly")]
            )
        ]
    )
    rep = compute_recorder_drift(rec, mk)
    # 3 monkey ops vs 3 geometric recorder ops → 100%
    assert rep.coverage_ratio == 1.0


def test_compute_drift_coverage_ratio_capped_at_one():
    rec = _doc([_record("recorder_dump", [_op("Circle")])])
    # monkey emits more ops than recorder geometric — coverage caps at 1.0
    mk = _doc([_record("x", [_op("PlotPoly"), _op("PlotPoly"), _op("PlotPoly")])])
    rep = compute_recorder_drift(rec, mk)
    assert rep.coverage_ratio == 1.0


def test_compute_drift_coverage_ratio_partial():
    rec = _doc(
        [
            _record(
                "recorder_dump",
                [_op("Circle"), _op("Rect"), _op("Text"), _op("PlotPoly")],
            )
        ]
    )
    mk = _doc([_record("x", [_op("PlotPoly")])])
    rep = compute_recorder_drift(rec, mk)
    assert rep.coverage_ratio == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------


def test_compute_drift_recorder_hist():
    rec = _doc(
        [
            _record(
                "recorder_dump",
                [_op("Circle"), _op("Circle"), _op("Rect"), _op("StartPlot")],
            )
        ]
    )
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    assert rep.recorder_hist == {"Circle": 2, "Rect": 1, "StartPlot": 1}


def test_compute_drift_monkey_hist():
    rec = _doc([])
    mk = _doc(
        [
            _record("wire", [_op("PlotPoly"), _op("PlotPoly")]),
            _record("junction", [_op("Circle")]),
        ]
    )
    rep = compute_recorder_drift(rec, mk)
    assert rep.monkey_hist == {"PlotPoly": 2, "Circle": 1}


def test_compute_drift_op_kind_delta():
    rec = _doc(
        [
            _record(
                "recorder_dump",
                [_op("Circle"), _op("Circle"), _op("Circle"), _op("Rect")],
            )
        ]
    )
    mk = _doc([_record("x", [_op("Circle"), _op("PlotPoly")])])
    rep = compute_recorder_drift(rec, mk)
    # delta = recorder - monkey
    assert rep.op_kind_delta == {"Circle": 2, "Rect": 1, "PlotPoly": -1}


def test_compute_drift_recorder_only_and_monkey_only_kinds():
    rec = _doc(
        [_record("recorder_dump", [_op("Circle"), _op("Rect"), _op("StartPlot")])]
    )
    mk = _doc([_record("x", [_op("Circle"), _op("PlotPoly")])])
    rep = compute_recorder_drift(rec, mk)
    # rec - mk: Rect, StartPlot ;  mk - rec: PlotPoly
    assert rep.recorder_only_kinds == ["Rect", "StartPlot"]
    assert rep.monkey_only_kinds == ["PlotPoly"]


# ---------------------------------------------------------------------------
# Canvas drift
# ---------------------------------------------------------------------------


def test_compute_drift_canvas_drift_basic():
    rec = _doc([], canvas={"width_nm": 297002200, "height_nm": 210007200})
    mk = _doc([], canvas={"width_nm": 297000000, "height_nm": 210000000})
    rep = compute_recorder_drift(rec, mk)
    assert rep.canvas_drift_nm == (2200, 7200)


def test_compute_drift_canvas_drift_none_when_recorder_canvas_missing():
    rec = _doc([], canvas=None)
    mk = _doc([], canvas={"width_nm": 297000000, "height_nm": 210000000})
    rep = compute_recorder_drift(rec, mk)
    assert rep.canvas_drift_nm is None
    assert rep.recorder_canvas is None
    assert rep.monkey_canvas == {"width_nm": 297000000, "height_nm": 210000000}


def test_compute_drift_canvas_drift_none_when_monkey_canvas_missing():
    rec = _doc([], canvas={"width_nm": 297000000, "height_nm": 210000000})
    mk = _doc([], canvas=None)
    rep = compute_recorder_drift(rec, mk)
    assert rep.canvas_drift_nm is None


def test_compute_drift_canvas_drift_none_when_dim_keys_missing():
    rec = _doc([], canvas={"page_type": "A4"})
    mk = _doc([], canvas={"width_nm": 297000000, "height_nm": 210000000})
    rep = compute_recorder_drift(rec, mk)
    assert rep.canvas_drift_nm is None


def test_compute_drift_canvas_drift_none_when_dims_non_int():
    rec = _doc([], canvas={"width_nm": "297mm", "height_nm": "210mm"})
    mk = _doc([], canvas={"width_nm": 297000000, "height_nm": 210000000})
    rep = compute_recorder_drift(rec, mk)
    assert rep.canvas_drift_nm is None


# ---------------------------------------------------------------------------
# Record histograms
# ---------------------------------------------------------------------------


def test_compute_drift_record_hist_recorder():
    rec = _doc(
        [
            _record("recorder_dump", []),
            _record("recorder_dump", []),
            _record("other", []),
        ]
    )
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    assert rep.recorder_record_hist == {"recorder_dump": 2, "other": 1}


def test_compute_drift_record_hist_monkey():
    rec = _doc([])
    mk = _doc(
        [
            _record("sheet_header", []),
            _record("wire", []),
            _record("wire", []),
            _record("symbol_instance", []),
        ]
    )
    rep = compute_recorder_drift(rec, mk)
    assert rep.monkey_record_hist == {
        "sheet_header": 1,
        "wire": 2,
        "symbol_instance": 1,
    }


# ---------------------------------------------------------------------------
# to_dict shape
# ---------------------------------------------------------------------------


def test_to_dict_round_trip_shape():
    rec = _doc(
        [_record("recorder_dump", [_op("Circle"), _op("StartPlot")])],
        canvas={"width_nm": 1000, "height_nm": 500},
    )
    mk = _doc(
        [_record("wire", [_op("PlotPoly")])],
        canvas={"width_nm": 1000, "height_nm": 500},
    )
    rep = compute_recorder_drift(rec, mk)
    out = rep.to_dict()

    assert out["schema"] == KICAD_RECORDER_DRIFT_SCHEMA
    assert set(out.keys()) == {
        "schema",
        "op_counts",
        "op_hist",
        "canvas",
        "record_hist",
        "stroked_text_fold",
    }
    assert set(out["op_counts"].keys()) == {
        "recorder_total",
        "recorder_total_pre_fold",
        "recorder_geometric",
        "monkey_total",
        "coverage_ratio",
    }
    assert set(out["op_hist"].keys()) == {
        "recorder",
        "monkey",
        "delta",
        "recorder_only_kinds",
        "monkey_only_kinds",
    }
    assert set(out["canvas"].keys()) == {"recorder", "monkey", "drift_nm"}
    assert out["canvas"]["drift_nm"] == [0, 0]


def test_to_dict_drift_nm_none_when_canvas_drift_missing():
    rec = _doc([], canvas=None)
    mk = _doc([], canvas=None)
    rep = compute_recorder_drift(rec, mk)
    out = rep.to_dict()
    assert out["canvas"]["drift_nm"] is None


def test_to_dict_op_hist_empty_when_no_ops():
    rec = _doc([])
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    out = rep.to_dict()
    assert out["op_hist"]["recorder"] == {}
    assert out["op_hist"]["monkey"] == {}
    assert out["op_hist"]["delta"] == {}
    assert out["op_hist"]["recorder_only_kinds"] == []
    assert out["op_hist"]["monkey_only_kinds"] == []


# ---------------------------------------------------------------------------
# Multi-record flattening
# ---------------------------------------------------------------------------


def test_compute_drift_flattens_ops_across_records():
    rec = _doc(
        [
            _record("a", [_op("Circle"), _op("Circle")]),
            _record("b", [_op("Circle"), _op("Rect")]),
        ]
    )
    mk = _doc([])
    rep = compute_recorder_drift(rec, mk)
    assert rep.recorder_total_ops == 4
    assert rep.recorder_hist == {"Circle": 3, "Rect": 1}
