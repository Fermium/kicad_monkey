"""
Cross-validation drift report between a canonical
``kicad.plotter_recorder.v1`` dump (loaded via
:func:`load_recorder_file`) and the kicad_monkey-produced
:class:`KiCadPlotterDocument` from ``schematic_to_ir`` (or any other
parser → IR boundary).

The report is an objective, frozen-snapshot baseline showing the gap
between the kicad_monkey toolchain and KiCad's own ground-truth plot ops.

The report is intentionally structural (op-kind histograms, canvas
dims, kind sets), NOT a per-coordinate equivalence proof. Two reasons:

1. The recorder vocabulary is stateful (SetColor / SetCurrentLineWidth
   / SetDash / PenTo / StartBlock / EndBlock / StartPlot / EndPlot /
   SetViewport / SetPageSettings) while the kicad_monkey IR is
   declarative — pen state is baked into each geometric op's payload.
   So a one-to-one op-count match would require the recorder to be
   "reduced" by folding state ops into following geometry.
2. Symbol-body composition into ``schematic_to_ir`` is represented
   structurally, so this report surfaces remaining semantic gaps.

Schema id of the emitted report: ``kicad.recorder_drift.v1``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .kicad_plotter_ir import KiCadPlotterDocument, KiCadPlotterOp
from .kicad_recorder_stroked_text_fold import (
    STROKED_TEXT_FOLD_KIND,
    STROKED_TEXT_FOLD_MIN_POINTS,
    STROKED_TEXT_FOLD_MIN_RUN,
    fold_stroked_text_runs,
)


# =============================================================================
# Schema constant
# =============================================================================


KICAD_RECORDER_DRIFT_SCHEMA = "kicad.recorder_drift.v1"


# =============================================================================
# Pure-state ops (recorder side)
# =============================================================================
#
# These ops appear in the recorder dump as PLOTTER state-machine calls
# but are NOT emitted by kicad_monkey's declarative IR (where colour /
# line-width / line-style / fill state lives inside each geometric op
# payload). They are tracked separately so a useful coverage ratio can
# be computed against geometric ops only.
#
# PenTo is here because it represents incremental pen movement / single-
# segment line draw; kicad_monkey collects equivalent geometry into
# ``PlotPoly`` ops (a future fold pass will collapse runs of PenTo into
# PlotPoly for a stronger equivalence check).


_RECORDER_STATE_KINDS: frozenset[str] = frozenset(
    {
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
    }
)


def _kind_str(op: KiCadPlotterOp) -> str:
    """Return ``op.kind`` as a plain string (handles enum + raw)."""
    kind = op.kind
    return str(getattr(kind, "value", kind))


def _histogram(ops: list[KiCadPlotterOp]) -> dict[str, int]:
    out: dict[str, int] = {}
    for op in ops:
        k = _kind_str(op)
        out[k] = out.get(k, 0) + 1
    return out


def _flatten_ops(doc: KiCadPlotterDocument) -> list[KiCadPlotterOp]:
    flat: list[KiCadPlotterOp] = []
    for record in doc.records:
        flat.extend(record.operations)
    return flat


def _canvas_int(canvas: Mapping[str, Any] | None, key: str) -> int | None:
    if not canvas:
        return None
    val = canvas.get(key)
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    return None


# =============================================================================
# Report dataclass
# =============================================================================


@dataclass(frozen=True)
class RecorderDriftReport:
    """
    Structured drift report between a recorder document and a
    kicad_monkey document.

    All histograms map op-kind name (string) → count.
    """

    schema: str = KICAD_RECORDER_DRIFT_SCHEMA

    # Op counts
    recorder_total_ops: int = 0
    monkey_total_ops: int = 0
    recorder_geometric_ops: int = 0
    """
    Recorder ops excluding pure state ops (SetColor/SetWidth/SetDash/
    PenTo/StartBlock/EndBlock/StartPlot/EndPlot/SetViewport/
    SetPageSettings). This is the meaningful denominator for kicad_monkey
    coverage since kicad_monkey's IR doesn't emit state ops.
    """

    coverage_ratio: float = 0.0
    """
    ``min(monkey_total_ops, recorder_geometric_ops) /
    recorder_geometric_ops`` (0.0 when recorder has no geometric ops).
    A coarse upper-bound coverage estimate; tighter equivalence comes from
    kind-by-kind coordinate diffs.
    """

    # Histograms
    recorder_hist: dict[str, int] = field(default_factory=dict)
    monkey_hist: dict[str, int] = field(default_factory=dict)
    op_kind_delta: dict[str, int] = field(default_factory=dict)
    """``recorder_hist[k] - monkey_hist[k]`` for every k in either set."""

    # Set differences
    recorder_only_kinds: list[str] = field(default_factory=list)
    monkey_only_kinds: list[str] = field(default_factory=list)

    # Canvas
    recorder_canvas: dict[str, Any] | None = None
    monkey_canvas: dict[str, Any] | None = None
    canvas_drift_nm: tuple[int, int] | None = None
    """
    ``(width_recorder - width_monkey, height_recorder - height_monkey)``
    when both canvases expose integer ``width_nm``/``height_nm``;
    otherwise ``None``.
    """

    # Record kind histograms
    recorder_record_hist: dict[str, int] = field(default_factory=dict)
    monkey_record_hist: dict[str, int] = field(default_factory=dict)

    # Stroked-text fold provenance
    recorder_total_ops_pre_fold: int = 0
    """
    Recorder op count before any fold pass. Equal to
    :attr:`recorder_total_ops` when the fold is disabled or no qualifying
    runs were detected.
    """

    stroked_text_runs_folded: int = 0
    """Number of glyph-stroke clusters collapsed into synthetic ops."""

    stroked_text_ops_absorbed: int = 0
    """Total raw ``PlotPoly`` ops consumed by the fold pass."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict of the report."""
        return {
            "schema": self.schema,
            "op_counts": {
                "recorder_total": self.recorder_total_ops,
                "recorder_total_pre_fold": self.recorder_total_ops_pre_fold,
                "recorder_geometric": self.recorder_geometric_ops,
                "monkey_total": self.monkey_total_ops,
                "coverage_ratio": self.coverage_ratio,
            },
            "op_hist": {
                "recorder": dict(self.recorder_hist),
                "monkey": dict(self.monkey_hist),
                "delta": dict(self.op_kind_delta),
                "recorder_only_kinds": list(self.recorder_only_kinds),
                "monkey_only_kinds": list(self.monkey_only_kinds),
            },
            "canvas": {
                "recorder": self.recorder_canvas,
                "monkey": self.monkey_canvas,
                "drift_nm": (
                    list(self.canvas_drift_nm)
                    if self.canvas_drift_nm is not None
                    else None
                ),
            },
            "record_hist": {
                "recorder": dict(self.recorder_record_hist),
                "monkey": dict(self.monkey_record_hist),
            },
            "stroked_text_fold": {
                "runs_folded": self.stroked_text_runs_folded,
                "ops_absorbed": self.stroked_text_ops_absorbed,
            },
        }


# =============================================================================
# Comparison
# =============================================================================


def compute_recorder_drift(
    recorder_doc: KiCadPlotterDocument,
    monkey_doc: KiCadPlotterDocument,
    *,
    fold_stroked_text: bool = True,
    stroked_text_min_points: int = STROKED_TEXT_FOLD_MIN_POINTS,
    stroked_text_min_run_size: int = STROKED_TEXT_FOLD_MIN_RUN,
) -> RecorderDriftReport:
    """
    Compute a :class:`RecorderDriftReport` comparing the canonical
    recorder document against the kicad_monkey-produced document.

    Both arguments are :class:`KiCadPlotterDocument` instances; the
    recorder side is typically obtained via
    :func:`load_recorder_file`, the kicad_monkey side via
    :func:`schematic_to_ir` (or any other parser → IR boundary).

    When ``fold_stroked_text=True`` (the default) consecutive
    ``FILLED_SHAPE`` ``PlotPoly`` runs in the recorder dump are collapsed
    into synthetic ``StrokedTextRun`` ops via
    :func:`fold_stroked_text_runs` *before* histogramming, so the
    coverage ratio reflects logical text items rather than per-glyph
    polygon counts. The fold is applied to the recorder side only —
    kicad_monkey's IR emits ``Text`` ops directly. Set
    ``fold_stroked_text=False`` to inspect the raw histogram.
    """
    rec_ops_raw = _flatten_ops(recorder_doc)
    mk_ops = _flatten_ops(monkey_doc)

    if fold_stroked_text:
        rec_ops, runs_folded, ops_absorbed = fold_stroked_text_runs(
            rec_ops_raw,
            min_points=stroked_text_min_points,
            min_run_size=stroked_text_min_run_size,
        )
    else:
        rec_ops = rec_ops_raw
        runs_folded = 0
        ops_absorbed = 0

    rec_hist = _histogram(rec_ops)
    mk_hist = _histogram(mk_ops)

    geometric_count = sum(
        n for k, n in rec_hist.items() if k not in _RECORDER_STATE_KINDS
    )

    coverage_ratio = 0.0
    if geometric_count > 0:
        coverage_ratio = min(len(mk_ops), geometric_count) / geometric_count

    all_kinds = sorted(set(rec_hist) | set(mk_hist))
    delta = {k: rec_hist.get(k, 0) - mk_hist.get(k, 0) for k in all_kinds}

    rec_only = sorted(set(rec_hist) - set(mk_hist))
    mk_only = sorted(set(mk_hist) - set(rec_hist))

    canvas_drift: tuple[int, int] | None = None
    rec_w = _canvas_int(recorder_doc.canvas, "width_nm")
    rec_h = _canvas_int(recorder_doc.canvas, "height_nm")
    mk_w = _canvas_int(monkey_doc.canvas, "width_nm")
    mk_h = _canvas_int(monkey_doc.canvas, "height_nm")
    if (
        rec_w is not None
        and rec_h is not None
        and mk_w is not None
        and mk_h is not None
    ):
        canvas_drift = (rec_w - mk_w, rec_h - mk_h)

    rec_record_hist: dict[str, int] = {}
    for r in recorder_doc.records:
        rec_record_hist[r.kind] = rec_record_hist.get(r.kind, 0) + 1
    mk_record_hist: dict[str, int] = {}
    for r in monkey_doc.records:
        mk_record_hist[r.kind] = mk_record_hist.get(r.kind, 0) + 1

    return RecorderDriftReport(
        schema=KICAD_RECORDER_DRIFT_SCHEMA,
        recorder_total_ops=len(rec_ops),
        monkey_total_ops=len(mk_ops),
        recorder_geometric_ops=geometric_count,
        coverage_ratio=coverage_ratio,
        recorder_hist=rec_hist,
        monkey_hist=mk_hist,
        op_kind_delta=delta,
        recorder_only_kinds=rec_only,
        monkey_only_kinds=mk_only,
        recorder_canvas=dict(recorder_doc.canvas) if recorder_doc.canvas else None,
        monkey_canvas=dict(monkey_doc.canvas) if monkey_doc.canvas else None,
        canvas_drift_nm=canvas_drift,
        recorder_record_hist=rec_record_hist,
        monkey_record_hist=mk_record_hist,
        recorder_total_ops_pre_fold=len(rec_ops_raw),
        stroked_text_runs_folded=runs_folded,
        stroked_text_ops_absorbed=ops_absorbed,
    )


__all__ = [
    "KICAD_RECORDER_DRIFT_SCHEMA",
    "STROKED_TEXT_FOLD_KIND",
    "STROKED_TEXT_FOLD_MIN_POINTS",
    "STROKED_TEXT_FOLD_MIN_RUN",
    "RecorderDriftReport",
    "compute_recorder_drift",
]
