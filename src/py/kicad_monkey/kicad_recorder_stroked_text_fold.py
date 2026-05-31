"""
Comparator-side stroked-text fold.

When KiCad renders text via the stroke font (the default schematic font),
each glyph is plotted as a sequence of filled-polygon strokes. In a
``kicad.plotter_recorder.v1`` dump these surface as runs of consecutive
``PlotPoly`` ops with ``fill="FILLED_SHAPE"`` and high point counts
(typically >=5 — one segment expanded to a thickened quad/hex). On a
fixture like ``complex_hierarchy.1`` the ~33 logical text items balloon into
800+ glyph PlotPoly ops, swamping the raw ``coverage_ratio`` produced by
:func:`compute_recorder_drift`.

This module provides a structural fold that collapses each such run
into a single synthetic ``StrokedTextRun`` op so the comparator's
denominator reflects the *semantic* gap (one logical text per kicad_monkey
``Text`` op) rather than the rendering-mode mismatch.

The fold is intentionally pure-data and conservative:

* It only collapses runs of ``PlotPoly`` whose payload ``fill`` is
  ``"FILLED_SHAPE"`` and whose ``points`` list has length
  ``>= STROKED_TEXT_FOLD_MIN_POINTS``.
* A run must contain at least ``STROKED_TEXT_FOLD_MIN_RUN`` consecutive
  matching ops to be folded; shorter "runs" pass through unchanged.
* No coordinate/colour/state ops are touched; non-glyph PlotPolys
  (wires, hier-label triangles, etc.) are preserved.

The synthetic op uses raw kind string ``"StrokedTextRun"`` so it
survives :class:`KiCadPlotterOp` round-trip via the unknown-kind
forward-compat path. Its payload carries::

    {"folded_op_count": <int>, "synthetic": True}
"""

from __future__ import annotations

from typing import Iterable

from .kicad_plotter_ir import (
    KiCadPlotterDocument,
    KiCadPlotterOp,
    KiCadPlotterRecord,
    _coerce_kind,
)


# =============================================================================
# Constants
# =============================================================================


STROKED_TEXT_FOLD_KIND: str = "StrokedTextRun"
"""Synthetic op kind emitted for each folded glyph-stroke cluster."""

STROKED_TEXT_FOLD_MIN_POINTS: int = 5
"""Minimum points-per-PlotPoly to qualify as a glyph-stroke polygon."""

STROKED_TEXT_FOLD_MIN_RUN: int = 2
"""Minimum number of consecutive glyph polygons required to fold."""


# =============================================================================
# Predicate
# =============================================================================


def _kind_str(op: KiCadPlotterOp) -> str:
    kind = op.kind
    return str(getattr(kind, "value", kind))


def is_stroked_text_glyph(
    op: KiCadPlotterOp,
    *,
    min_points: int = STROKED_TEXT_FOLD_MIN_POINTS,
) -> bool:
    """
    Return ``True`` when ``op`` looks like one stroked-text glyph
    polygon: a ``PlotPoly`` with ``fill="FILLED_SHAPE"`` and at least
    ``min_points`` points.
    """
    if _kind_str(op) != "PlotPoly":
        return False
    payload = op.payload or {}
    if payload.get("fill") != "FILLED_SHAPE":
        return False
    points = payload.get("points") or []
    return len(points) >= min_points


# =============================================================================
# Op-list fold
# =============================================================================


def fold_stroked_text_runs(
    ops: Iterable[KiCadPlotterOp],
    *,
    min_points: int = STROKED_TEXT_FOLD_MIN_POINTS,
    min_run_size: int = STROKED_TEXT_FOLD_MIN_RUN,
) -> tuple[list[KiCadPlotterOp], int, int]:
    """
    Collapse runs of consecutive glyph-stroke ``PlotPoly`` ops into
    synthetic ``StrokedTextRun`` ops.

    Returns a tuple ``(folded_ops, runs_folded, ops_absorbed)`` where:

    * ``folded_ops`` is a new list with each qualifying run replaced by
      one synthetic op carrying ``payload={"folded_op_count": N,
      "synthetic": True}``;
    * ``runs_folded`` is the number of runs collapsed;
    * ``ops_absorbed`` is the total number of original PlotPoly ops
      consumed by those runs (so the caller can compute a delta vs the
      raw op count).

    Runs shorter than ``min_run_size`` pass through verbatim. The
    function never mutates the input list or its ops.
    """
    op_list = list(ops)
    n = len(op_list)
    out: list[KiCadPlotterOp] = []
    runs_folded = 0
    ops_absorbed = 0

    i = 0
    while i < n:
        if is_stroked_text_glyph(op_list[i], min_points=min_points):
            run_start = i
            while i < n and is_stroked_text_glyph(
                op_list[i], min_points=min_points
            ):
                i += 1
            run_len = i - run_start
            if run_len >= min_run_size:
                out.append(
                    KiCadPlotterOp(
                        kind=_coerce_kind(STROKED_TEXT_FOLD_KIND),
                        payload={
                            "folded_op_count": run_len,
                            "synthetic": True,
                        },
                    )
                )
                runs_folded += 1
                ops_absorbed += run_len
            else:
                out.extend(op_list[run_start:i])
        else:
            out.append(op_list[i])
            i += 1

    return out, runs_folded, ops_absorbed


# =============================================================================
# Document-level fold
# =============================================================================


def fold_recorder_document(
    doc: KiCadPlotterDocument,
    *,
    min_points: int = STROKED_TEXT_FOLD_MIN_POINTS,
    min_run_size: int = STROKED_TEXT_FOLD_MIN_RUN,
) -> tuple[KiCadPlotterDocument, int, int]:
    """
    Apply :func:`fold_stroked_text_runs` to every record's operations
    list and return ``(new_doc, total_runs_folded, total_ops_absorbed)``.

    Runs are detected per-record (no cross-record fusion) so the fold
    never crosses logical document boundaries.
    """
    new_records: list[KiCadPlotterRecord] = []
    total_runs = 0
    total_absorbed = 0

    for record in doc.records:
        folded_ops, runs, absorbed = fold_stroked_text_runs(
            record.operations,
            min_points=min_points,
            min_run_size=min_run_size,
        )
        total_runs += runs
        total_absorbed += absorbed
        new_records.append(
            KiCadPlotterRecord(
                uuid=record.uuid,
                kind=record.kind,
                object_id=record.object_id,
                bounds=record.bounds,
                operations=folded_ops,
                extras=dict(record.extras) if record.extras else {},
            )
        )

    new_doc = KiCadPlotterDocument(
        records=new_records,
        source_path=doc.source_path,
        source_kind=doc.source_kind,
        document_id=doc.document_id,
        canvas=dict(doc.canvas) if doc.canvas else None,
        coordinate_space=(
            dict(doc.coordinate_space) if doc.coordinate_space else None
        ),
    )
    return new_doc, total_runs, total_absorbed


__all__ = [
    "STROKED_TEXT_FOLD_KIND",
    "STROKED_TEXT_FOLD_MIN_POINTS",
    "STROKED_TEXT_FOLD_MIN_RUN",
    "fold_recorder_document",
    "fold_stroked_text_runs",
    "is_stroked_text_glyph",
]
