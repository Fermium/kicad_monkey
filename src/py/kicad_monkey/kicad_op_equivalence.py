"""
Tolerance-aware op-by-op equivalence diff between a recorder document
and a kicad_monkey document.

After the stroked-text fold has aligned the two sides' op counts (see
:mod:`kicad_recorder_stroked_text_fold`), this module performs a
per-position structural diff that surfaces the **first divergent op** plus
aggregate kind/coord-mismatch counts. It is the natural escalation from
:func:`compute_recorder_drift`: the drift report tells you whether the
denominator is reasonable; the equivalence report tells you whether
the right ops land at the right places.

What the diff does
------------------

1. Optionally apply the stroked-text fold to the recorder side.
2. Merge recorder fill+outline primitive pairs into one declarative
   filled/stroked primitive.
3. Optionally fold recorder ``PenTo`` draw runs into declarative geometry.
4. Drop pure-state ops (``SetColor`` / ``SetCurrentLineWidth`` /
   ``SetDash`` / ``SetViewport`` / ``SetPageSettings`` / ``StartPlot`` /
   ``EndPlot`` / ``StartBlock`` / ``EndBlock`` / leftover ``PenTo``) on
   the recorder side; kicad_monkey's declarative IR does not emit them.
4. Pair the remaining geometric ops by **document order**.
5. For each pair compare:

   * ``kind`` (with a small equivalence map: a synthetic
     ``StrokedTextRun`` matches a real ``Text``).
   * Coord-bearing payload fields (extracted per op kind), comparing
     two equal-length sequences with ``max-abs-delta`` and emitting a
     ``coord_mismatch`` when the delta exceeds ``tolerance_nm``.

5. Report aggregate counts plus a structured
   :class:`KiCadOpDivergence` for the first divergence (or ``None``
   when both streams are equivalent within tolerance).

Order strategies
----------------

Two pairing strategies are supported via ``match_strategy``:

* ``"positional"`` (default) — strict pairing by document
  index. KiCad's plot pipeline visits the sheet items first then the
  border (drawing sheet) last, while :func:`schematic_to_ir` emits the
  drawing-sheet record first; under positional pairing a real-fixture
  diff trips at op 0 (kind_mismatch). That **is** the diagnostic.

* ``"by_kind"`` — group both sides by canonical
  :attr:`KiCadPlotterOp.kind` (with ``StrokedTextRun`` ↔ ``Text``
  equivalence collapsed) and pair positionally **within each kind
  bucket**. ``kind_mismatches`` is always 0 in this mode by
  construction; cross-kind reordering (e.g. drawing-sheet ordering)
  no longer trips at op 0. Per-kind population imbalances surface as
  ``monkey_short`` / ``monkey_long`` (the kind owning the leftover is
  named in ``first_divergence.details``). This is the natural
  escalation when investigating real-fixture diffs after the
  positional report has confirmed the populations are sane.

* ``"windowed_by_kind"`` — group by kind as in ``by_kind`` but
  pair via **greedy minimum-coord-delta matching** within each
  bucket, optionally restricted to a positional window of
  ``match_window`` slots (``0`` = unbounded, the full bucket).
  Tolerates intra-kind reordering: e.g. two ``Text`` ops at swapped
  positions still pair within tolerance when window allows. Only
  pairs whose ``max-abs-delta`` is within ``tolerance_nm`` are
  consumed; everything else surfaces as ``monkey_short`` /
  ``monkey_long`` carrying the first leftover op in document order.
  ``coord_length_mismatch`` and ``coord_delta_exceeded`` counters
  stay at 0 in this strategy — diagnostics shift to "did the op find
  a partner at all?". Use this when the v2 by_kind report shows
  per-kind population imbalances that you suspect are actually
  intra-kind reorderings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
import json
from typing import Any, Iterable

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


KICAD_OP_EQUIVALENCE_SCHEMA = "kicad.op_equivalence.v1"


# Valid ``match_strategy`` values for :func:`compute_op_equivalence`.
MATCH_STRATEGY_POSITIONAL = "positional"
MATCH_STRATEGY_BY_KIND = "by_kind"
MATCH_STRATEGY_WINDOWED_BY_KIND = "windowed_by_kind"
_VALID_MATCH_STRATEGIES = frozenset(
    {
        MATCH_STRATEGY_POSITIONAL,
        MATCH_STRATEGY_BY_KIND,
        MATCH_STRATEGY_WINDOWED_BY_KIND,
    }
)


# ``match_window`` sentinel meaning "no positional cap inside the kind
# bucket" (the full bucket is searched for the best partner). Only
# meaningful for ``MATCH_STRATEGY_WINDOWED_BY_KIND``.
MATCH_WINDOW_UNBOUNDED = 0


# =============================================================================
# Configuration tables
# =============================================================================


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


# Synthetic / stylistic kinds that are semantically equivalent for this
# diff — e.g. the recorder's stroked-text fold emits ``StrokedTextRun``
# while kicad_monkey emits ``Text``. Both are "logical text item".
_KIND_EQUIVALENT: dict[str, str] = {
    STROKED_TEXT_FOLD_KIND: "Text",
    "ThickSegment": "PlotPoly",
}


# Per-kind coord-extractor. Each entry is a tuple of payload keys whose
# values must all be ``int`` / ``float`` / convertible to ``float``.
# Keys missing on either side are treated as ``0``. ``points`` is
# expanded inline (flattened) so PlotPoly comparison checks every
# vertex.
_COORD_FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "PenTo": ("x", "y"),
    "Circle": ("cx", "cy", "diameter_nm"),
    "ArcThreePoint": ("start_x", "start_y", "mid_x", "mid_y", "end_x", "end_y"),
    "ArcCenterAngle": ("cx", "cy", "radius_nm"),
    "BezierCurve": (
        "start_x",
        "start_y",
        "ctrl1_x",
        "ctrl1_y",
        "ctrl2_x",
        "ctrl2_y",
        "end_x",
        "end_y",
    ),
    "Rect": ("x1", "y1", "x2", "y2"),
    "Text": ("x", "y", "size_x_nm", "size_y_nm"),
    "PlotImage": ("x", "y", "width_nm", "height_nm"),
    "ThickSegment": ("start_x", "start_y", "end_x", "end_y", "width_nm"),
    "ThickArc": ("cx", "cy", "radius_nm", "start_angle_deg", "sweep_deg"),
    "FlashPadCircle": ("x", "y", "diameter_nm"),
    "FlashPadOval": ("x", "y", "size_x_nm", "size_y_nm", "orient_deg"),
    "FlashPadRect": ("x", "y", "size_x_nm", "size_y_nm", "orient_deg"),
    "FlashPadRoundRect": (
        "x",
        "y",
        "size_x_nm",
        "size_y_nm",
        "corner_radius_nm",
        "orient_deg",
    ),
    "FlashPadTrapez": ("x", "y", "size_x_nm", "size_y_nm", "orient_deg"),
    "FlashRegularPolygon": ("x", "y", "diameter_nm", "corner_count", "orient_deg"),
}


_TEXT_INTERLINE_FACTOR = 1.68
# KiCad's recorder reports Text anchors after the C++ font stack resolves
# glyph boxes. The declarative IR keeps the schematic anchor. Treat small
# same-style anchor shifts as semantic text equivalence while still requiring
# exact text/style/size parity.
_TEXT_ANCHOR_SEMANTIC_TOLERANCE_NM = 130_000
_DNP_MARKER_COLOR = "#DC090DD9"
_DNP_MARKER_SEMANTIC_TOLERANCE_NM = 200_000
_GLOBAL_LABEL_BOX_COLOR = "#840000FF"
_GLOBAL_LABEL_BOX_SEMANTIC_TOLERANCE_NM = 350_000


# =============================================================================
# Predicates and helpers
# =============================================================================


def _kind_str(op: KiCadPlotterOp) -> str:
    kind = op.kind
    return str(getattr(kind, "value", kind))


def _equivalent_kind(kind: str) -> str:
    return _KIND_EQUIVALENT.get(kind, kind)


def _is_state_op(op: KiCadPlotterOp) -> bool:
    return _kind_str(op) in _RECORDER_STATE_KINDS


def _filter_geometric(ops: Iterable[KiCadPlotterOp]) -> list[KiCadPlotterOp]:
    return [op for op in ops if not _is_state_op(op)]


def _rotate_xy(x: float, y: float, angle_deg: float) -> tuple[float, float]:
    a = float(angle_deg) % 360.0
    if a == 0.0:
        return x, y
    if a == 90.0:
        return -y, x
    if a == 180.0:
        return -x, -y
    if a == 270.0:
        return y, -x
    rad = math.radians(a)
    c, s = math.cos(rad), math.sin(rad)
    return x * c - y * s, x * s + y * c


def _multiline_text_line_positions(payload: dict[str, Any], line_count: int) -> list[tuple[int, int]]:
    x = int(round(float(payload.get("x", 0) or 0)))
    y = int(round(float(payload.get("y", 0) or 0)))
    size_y_nm = int(round(float(payload.get("size_y_nm", 0) or 0)))
    line_step = int(round(size_y_nm * _TEXT_INTERLINE_FACTOR))
    orient_deg = float(payload.get("orient_deg", 0.0) or 0.0)
    v_align = str(payload.get("v_align", "GR_TEXT_V_ALIGN_BOTTOM") or "")

    pos_y = y
    if line_count > 1:
        if v_align == "GR_TEXT_V_ALIGN_CENTER":
            pos_y -= (line_count - 1) * line_step // 2
        elif v_align == "GR_TEXT_V_ALIGN_BOTTOM":
            pos_y -= (line_count - 1) * line_step

    rel_x, rel_y = _rotate_xy(0, pos_y - y, orient_deg)
    step_x, step_y = _rotate_xy(0, line_step, orient_deg)
    pos_x = int(round(x + rel_x))
    pos_y = int(round(y + rel_y))
    step_x_i = int(round(step_x))
    step_y_i = int(round(step_y))

    out: list[tuple[int, int]] = []
    for _idx in range(line_count):
        out.append((pos_x, pos_y))
        pos_x += step_x_i
        pos_y += step_y_i
    return out


def _split_multiline_text_ops(ops: Iterable[KiCadPlotterOp]) -> list[KiCadPlotterOp]:
    out: list[KiCadPlotterOp] = []
    for op in ops:
        if _kind_str(op) != "Text":
            out.append(op)
            continue
        payload = op.payload or {}
        text = str(payload.get("text", ""))
        if "\n" not in text:
            out.append(op)
            continue
        lines = text.split("\n")
        positions = _multiline_text_line_positions(payload, len(lines))
        for line, (x, y) in zip(lines, positions):
            if line == "":
                continue
            line_payload = dict(payload)
            line_payload["x"] = x
            line_payload["y"] = y
            line_payload["text"] = line
            line_payload["multiline"] = False
            out.append(KiCadPlotterOp(kind=op.kind, payload=line_payload))
    return out


def _is_opaque_hex_color(value: Any) -> bool:
    if value in (None, ""):
        return True
    text = str(value).upper()
    if not text.startswith("#"):
        return True
    if len(text) == 7:
        return True
    if len(text) == 9:
        return text[-2:] == "FF"
    return False


def _is_idempotent_overdraw_op(op: KiCadPlotterOp) -> bool:
    kind = _kind_str(op)
    if kind in {"PlotImage", STROKED_TEXT_FOLD_KIND}:
        return False
    payload = op.payload or {}
    if not any(key in payload for key in ("color", "stroke_color", "fill_color")):
        return False
    for key in ("color", "stroke_color", "fill_color"):
        if not _is_opaque_hex_color(payload.get(key)):
            return False
    return True


def _idempotent_duplicate_key(op: KiCadPlotterOp) -> str | None:
    if not _is_idempotent_overdraw_op(op):
        return None
    payload = dict(op.payload or {})
    for key in ("color", "stroke_color", "fill_color"):
        if key in payload:
            payload[key] = _normalise_style_value(key, payload.get(key))
    if _kind_str(op) != "Text":
        payload["line_style"] = _normalise_style_value(
            "line_style",
            payload.get("line_style", "SOLID"),
        )
    return json.dumps(
        {"kind": _kind_str(op), **payload},
        sort_keys=True,
        separators=(",", ":"),
    )


def _drop_idempotent_duplicate_ops(
    ops: Iterable[KiCadPlotterOp],
) -> list[KiCadPlotterOp]:
    out: list[KiCadPlotterOp] = []
    seen: set[str] = set()
    for op in ops:
        key = _idempotent_duplicate_key(op)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        out.append(op)
    return out


def _payload_xy(payload: dict[str, Any]) -> tuple[int, int]:
    return (
        int(round(float(payload.get("x", 0) or 0))),
        int(round(float(payload.get("y", 0) or 0))),
    )


def _line_width(payload: dict[str, Any]) -> int:
    try:
        return int(round(float(payload.get("width_nm", 0) or 0)))
    except (TypeError, ValueError):
        return 0


def _axis_aligned_rect(points: list[tuple[int, int]]) -> tuple[int, int, int, int] | None:
    if len(points) != 5 or points[0] != points[-1]:
        return None
    corners = set(points[:-1])
    xs = sorted({x for x, _y in corners})
    ys = sorted({y for _x, y in corners})
    if len(xs) != 2 or len(ys) != 2 or len(corners) != 4:
        return None
    if corners != {(xs[0], ys[0]), (xs[1], ys[0]), (xs[1], ys[1]), (xs[0], ys[1])}:
        return None
    return xs[0], ys[0], xs[1], ys[1]


def _fill_value(op: KiCadPlotterOp) -> str:
    return str((op.payload or {}).get("fill", "") or "")


def _is_no_fill(op: KiCadPlotterOp) -> bool:
    return _fill_value(op) in {"", "NO_FILL"}


def _primitive_key(op: KiCadPlotterOp) -> tuple[Any, ...] | None:
    kind = _kind_str(op)
    payload = op.payload or {}
    if kind == "Rect":
        x1 = int(round(float(payload.get("x1", 0) or 0)))
        y1 = int(round(float(payload.get("y1", 0) or 0)))
        x2 = int(round(float(payload.get("x2", 0) or 0)))
        y2 = int(round(float(payload.get("y2", 0) or 0)))
        return kind, min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    if kind == "Circle":
        return (
            kind,
            int(round(float(payload.get("cx", 0) or 0))),
            int(round(float(payload.get("cy", 0) or 0))),
            int(round(float(payload.get("diameter_nm", 0) or 0))),
        )
    return None


def _merge_fill_outline_primitives(
    ops: Iterable[KiCadPlotterOp],
) -> list[KiCadPlotterOp]:
    """Merge normalized fill+outline primitive pairs.

    KiCad often emits the fill pass first and the matching outline later, with
    pins/text interleaved between them. For logical IR parity we compare the
    filled primitive with the effective outline width attached and drop the
    later outline partner.
    """
    items = list(ops)
    out: list[KiCadPlotterOp] = []
    skipped: set[int] = set()
    for index, op in enumerate(items):
        if index in skipped:
            continue
        key = _primitive_key(op)
        if key is not None and not _is_no_fill(op):
            partner_index: int | None = None
            for lookahead in range(index + 1, len(items)):
                if lookahead in skipped:
                    continue
                candidate = items[lookahead]
                if _primitive_key(candidate) == key and _is_no_fill(candidate):
                    partner_index = lookahead
                    break
            if partner_index is not None:
                outline = items[partner_index]
                payload = dict(op.payload or {})
                outline_width = int((outline.payload or {}).get("width_nm", 0) or 0)
                if outline_width:
                    payload["width_nm"] = outline_width
                out.append(KiCadPlotterOp(kind=op.kind, payload=payload))
                skipped.add(partner_index)
                continue

        # Fast path for adjacent pairs where the outline comes first.
        op = items[index]
        if index + 1 >= len(items):
            out.append(op)
            continue
        nxt = items[index + 1]
        if _primitive_key(op) == _primitive_key(nxt) and _primitive_key(op) is not None:
            op_no_fill = _is_no_fill(op)
            nxt_no_fill = _is_no_fill(nxt)
            if op_no_fill != nxt_no_fill:
                filled = nxt if op_no_fill else op
                outline = op if op_no_fill else nxt
                payload = dict(filled.payload or {})
                outline_width = int((outline.payload or {}).get("width_nm", 0) or 0)
                if outline_width:
                    payload["width_nm"] = outline_width
                out.append(KiCadPlotterOp(kind=filled.kind, payload=payload))
                skipped.add(index + 1)
                continue
        out.append(op)
    return out


def _fold_pen_to_runs(ops: Iterable[KiCadPlotterOp]) -> list[KiCadPlotterOp]:
    """Collapse recorder ``PenTo`` line runs into declarative polylines."""
    out: list[KiCadPlotterOp] = []
    points: list[tuple[int, int]] = []
    current_width_nm = 0

    def flush() -> None:
        nonlocal points
        if len(points) >= 2:
            rect = _axis_aligned_rect(points)
            if rect is not None:
                out.append(
                    KiCadPlotterOp.rect(
                        x1=rect[0],
                        y1=rect[1],
                        x2=rect[2],
                        y2=rect[3],
                        fill="NO_FILL",
                        width_nm=current_width_nm,
                    )
                )
            else:
                out.append(
                    KiCadPlotterOp.plot_poly(
                        points=points,
                        fill="NO_FILL",
                        width_nm=current_width_nm,
                    )
                )
        points = []

    for op in ops:
        kind = _kind_str(op)
        payload = op.payload or {}
        if kind == "SetCurrentLineWidth":
            flush()
            current_width_nm = _line_width(payload)
            out.append(op)
            continue
        if kind != "PenTo":
            flush()
            out.append(op)
            continue

        action = str(payload.get("action", "") or "").upper()
        if action not in {"U", "D", "Z"}:
            flush()
            out.append(op)
            continue
        if action == "Z":
            flush()
            continue

        point = _payload_xy(payload)
        if action == "U":
            flush()
            points = [point]
            continue
        if not points:
            points = [point]
        elif points[-1] != point:
            points.append(point)

    flush()
    return out


def _apply_recorder_style_state(ops: Iterable[KiCadPlotterOp]) -> list[KiCadPlotterOp]:
    """
    Attach recorder plotter state to following geometric ops.

    RECORDER_PLOTTER is faithful to KiCad's stateful PLOTTER API:
    color, dash style, and current line width are emitted as state calls.
    The monkey IR is declarative, so equivalence compares a normalized
    recorder stream where each primitive carries the effective style payload.
    """
    out: list[KiCadPlotterOp] = []
    current_color: str | None = None
    current_line_style: str | None = None

    for op in ops:
        kind = _kind_str(op)
        payload = op.payload or {}
        if kind == "SetColor":
            color = payload.get("color")
            current_color = str(color).upper() if color else None
            out.append(op)
            continue
        if kind == "SetDash":
            style = payload.get("line_style")
            current_line_style = str(style) if style else None
            out.append(op)
            continue

        if kind in _RECORDER_STATE_KINDS:
            out.append(op)
            continue

        new_payload = dict(payload)
        if current_color and kind != "Text":
            new_payload.setdefault("stroke_color", current_color)
            if not _is_no_fill(op):
                new_payload.setdefault("fill_color", current_color)
        if current_line_style and kind != "Text":
            new_payload.setdefault("line_style", current_line_style)
        out.append(KiCadPlotterOp(kind=op.kind, payload=new_payload))

    return out


def _flatten_ops(doc: KiCadPlotterDocument) -> list[KiCadPlotterOp]:
    flat: list[KiCadPlotterOp] = []
    for record in doc.records:
        flat.extend(record.operations)
    return flat


def _extract_coords(op: KiCadPlotterOp) -> list[float]:
    """
    Return the coord-bearing payload values for ``op`` as a flat list of
    ``float`` (the diff is tolerance-aware in nm; floats are fine since
    we compare absolute deltas).

    For ``PlotPoly`` the points list is flattened ``[x0,y0,x1,y1,...]``
    so vertex-by-vertex deltas land in a single sequence. Unfilled
    two-point ``PlotPoly`` ops are canonicalized as thick segments by
    sorting endpoints and appending ``width_nm``; this lets declarative
    line IR compare against recorder ``ThickSegment`` calls.
    Synthetic ``StrokedTextRun`` and unknown kinds return ``[]``.
    """
    kind = _kind_str(op)
    payload = op.payload or {}

    if kind == "PlotPoly":
        points = payload.get("points", []) or []
        normalised_points = points
        is_unfilled_segment = len(points) == 2 and _is_no_fill(op)
        if is_unfilled_segment:
            normalised_points = sorted(points, key=lambda pt: (pt[0], pt[1]))
        flat: list[float] = []
        for pt in normalised_points:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                try:
                    flat.append(float(pt[0]))
                    flat.append(float(pt[1]))
                except (TypeError, ValueError):
                    continue
        if is_unfilled_segment:
            flat.append(float(_line_width(payload)))
        return flat

    if kind == "ThickSegment":
        try:
            start = (
                float(payload.get("start_x", 0) or 0),
                float(payload.get("start_y", 0) or 0),
            )
            end = (
                float(payload.get("end_x", 0) or 0),
                float(payload.get("end_y", 0) or 0),
            )
        except (TypeError, ValueError):
            return [0.0, 0.0, 0.0, 0.0, 0.0]
        points = sorted([start, end], key=lambda pt: (pt[0], pt[1]))
        return [points[0][0], points[0][1], points[1][0], points[1][1], float(_line_width(payload))]

    if kind == "Rect":
        try:
            x1 = float(payload.get("x1", 0) or 0)
            y1 = float(payload.get("y1", 0) or 0)
            x2 = float(payload.get("x2", 0) or 0)
            y2 = float(payload.get("y2", 0) or 0)
        except (TypeError, ValueError):
            return [0.0, 0.0, 0.0, 0.0]
        return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]

    fields = _COORD_FIELDS_BY_KIND.get(kind)
    if not fields:
        return []

    out: list[float] = []
    for key in fields:
        val = payload.get(key, 0)
        try:
            out.append(float(val))
        except (TypeError, ValueError):
            out.append(0.0)
    return out


def _max_coord_delta(a: list[float], b: list[float]) -> float | None:
    """
    Return ``max(|a[i] - b[i]|)`` over all i, or ``None`` if the
    sequences have different lengths (structural mismatch).
    """
    if len(a) != len(b):
        return None
    if not a:
        return 0.0
    return max(abs(x - y) for x, y in zip(a, b))


def _text_anchor_semantically_equivalent(
    rec: KiCadPlotterOp,
    mk: KiCadPlotterOp,
    *,
    tolerance_nm: float,
    delta: float,
) -> bool:
    if _equivalent_kind(_kind_str(rec)) != "Text":
        return False
    if _equivalent_kind(_kind_str(mk)) != "Text":
        return False
    if delta <= tolerance_nm:
        return True
    if delta > _TEXT_ANCHOR_SEMANTIC_TOLERANCE_NM:
        return False
    if _style_mismatches(rec, mk):
        return False

    rec_payload = rec.payload or {}
    mk_payload = mk.payload or {}
    for key in ("size_x_nm", "size_y_nm"):
        try:
            rec_value = float(rec_payload.get(key, 0) or 0)
            mk_value = float(mk_payload.get(key, 0) or 0)
        except (TypeError, ValueError):
            return False
        if abs(rec_value - mk_value) > tolerance_nm:
            return False

    for key in ("x", "y"):
        try:
            rec_value = float(rec_payload.get(key, 0) or 0)
            mk_value = float(mk_payload.get(key, 0) or 0)
        except (TypeError, ValueError):
            return False
        if abs(rec_value - mk_value) > _TEXT_ANCHOR_SEMANTIC_TOLERANCE_NM:
            return False

    return True


def _segment_endpoints(
    op: KiCadPlotterOp,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    kind = _kind_str(op)
    payload = op.payload or {}
    if kind == "ThickSegment":
        try:
            return (
                (
                    float(payload.get("start_x", 0) or 0),
                    float(payload.get("start_y", 0) or 0),
                ),
                (
                    float(payload.get("end_x", 0) or 0),
                    float(payload.get("end_y", 0) or 0),
                ),
            )
        except (TypeError, ValueError):
            return None
    if kind == "PlotPoly" and _is_no_fill(op):
        points = payload.get("points", []) or []
        if len(points) == 2:
            try:
                return (
                    (float(points[0][0]), float(points[0][1])),
                    (float(points[1][0]), float(points[1][1])),
                )
            except (TypeError, ValueError, IndexError):
                return None
    return None


def _segment_center(
    endpoints: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float]:
    return (
        (endpoints[0][0] + endpoints[1][0]) / 2.0,
        (endpoints[0][1] + endpoints[1][1]) / 2.0,
    )


def _segment_orientation_sign(
    endpoints: tuple[tuple[float, float], tuple[float, float]],
) -> int:
    dx = endpoints[1][0] - endpoints[0][0]
    dy = endpoints[1][1] - endpoints[0][1]
    product = dx * dy
    if product > 0:
        return 1
    if product < 0:
        return -1
    return 0


def _is_dnp_marker_segment(op: KiCadPlotterOp) -> bool:
    payload = op.payload or {}
    color = str(payload.get("stroke_color") or payload.get("color") or "").upper()
    return color == _DNP_MARKER_COLOR and _segment_endpoints(op) is not None


def _dnp_marker_semantically_equivalent(
    rec: KiCadPlotterOp,
    mk: KiCadPlotterOp,
    *,
    tolerance_nm: float,
    delta: float,
) -> bool:
    if delta <= tolerance_nm:
        return True
    if delta > _DNP_MARKER_SEMANTIC_TOLERANCE_NM:
        return False
    if not (_is_dnp_marker_segment(rec) and _is_dnp_marker_segment(mk)):
        return False
    if _style_mismatches(rec, mk):
        return False

    rec_endpoints = _segment_endpoints(rec)
    mk_endpoints = _segment_endpoints(mk)
    if rec_endpoints is None or mk_endpoints is None:
        return False
    if _segment_orientation_sign(rec_endpoints) != _segment_orientation_sign(mk_endpoints):
        return False

    rec_center = _segment_center(rec_endpoints)
    mk_center = _segment_center(mk_endpoints)
    return (
        abs(rec_center[0] - mk_center[0]) <= tolerance_nm
        and abs(rec_center[1] - mk_center[1]) <= tolerance_nm
    )


def _plot_poly_points(op: KiCadPlotterOp) -> list[list[float]] | None:
    payload = op.payload or {}
    if _kind_str(op) != "PlotPoly" or not _is_no_fill(op):
        return None
    points = payload.get("points", []) or []
    out: list[list[float]] = []
    try:
        for point in points:
            out.append([float(point[0]), float(point[1])])
    except (TypeError, ValueError, IndexError):
        return None
    return out


def _sign_with_tolerance(value: float, tolerance_nm: float) -> int:
    if value > tolerance_nm:
        return 1
    if value < -tolerance_nm:
        return -1
    return 0


def _is_global_label_box_op(op: KiCadPlotterOp) -> bool:
    payload = op.payload or {}
    if str(payload.get("stroke_color") or "").upper() != _GLOBAL_LABEL_BOX_COLOR:
        return False
    points = _plot_poly_points(op)
    if points is None or len(points) != 7:
        return False
    return points[0] == points[-1]


def _global_label_box_semantically_equivalent(
    rec: KiCadPlotterOp,
    mk: KiCadPlotterOp,
    *,
    tolerance_nm: float,
    delta: float,
) -> bool:
    if delta <= tolerance_nm:
        return True
    if delta > _GLOBAL_LABEL_BOX_SEMANTIC_TOLERANCE_NM:
        return False
    if not (_is_global_label_box_op(rec) and _is_global_label_box_op(mk)):
        return False
    if _style_mismatches(rec, mk):
        return False

    rec_points = _plot_poly_points(rec)
    mk_points = _plot_poly_points(mk)
    if rec_points is None or mk_points is None or len(rec_points) != len(mk_points):
        return False

    rec_anchor = rec_points[0]
    mk_anchor = mk_points[0]
    if (
        abs(rec_anchor[0] - mk_anchor[0]) > tolerance_nm
        or abs(rec_anchor[1] - mk_anchor[1]) > tolerance_nm
    ):
        return False

    for rec_point, mk_point in zip(rec_points[1:-1], mk_points[1:-1]):
        rec_dx = rec_point[0] - rec_anchor[0]
        rec_dy = rec_point[1] - rec_anchor[1]
        mk_dx = mk_point[0] - mk_anchor[0]
        mk_dy = mk_point[1] - mk_anchor[1]
        if _sign_with_tolerance(rec_dx, tolerance_nm) != _sign_with_tolerance(
            mk_dx, tolerance_nm
        ):
            return False
        if _sign_with_tolerance(rec_dy, tolerance_nm) != _sign_with_tolerance(
            mk_dy, tolerance_nm
        ):
            return False
    return True


def _semantically_equivalent(
    rec: KiCadPlotterOp,
    mk: KiCadPlotterOp,
    *,
    tolerance_nm: float,
    delta: float,
) -> bool:
    return (
        _text_anchor_semantically_equivalent(
            rec,
            mk,
            tolerance_nm=tolerance_nm,
            delta=delta,
        )
        or _dnp_marker_semantically_equivalent(
            rec,
            mk,
            tolerance_nm=tolerance_nm,
            delta=delta,
        )
        or _global_label_box_semantically_equivalent(
            rec,
            mk,
            tolerance_nm=tolerance_nm,
            delta=delta,
        )
    )


def _normalise_style_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in {"stroke_color", "fill_color", "color"}:
        return str(value).upper()
    if key == "line_style":
        text = str(value)
        return "SOLID" if text == "DEFAULT" else text
    if key == "fill":
        text = str(value)
        return None if text in {"", "NO_FILL"} else text
    if key in {"width_nm", "pen_width_nm"}:
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return 0
    if key == "orient_deg":
        try:
            return round(float(value) % 360.0, 6)
        except (TypeError, ValueError):
            return 0.0
    return value


def _style_payload(op: KiCadPlotterOp) -> dict[str, Any]:
    kind = _kind_str(op)
    payload = op.payload or {}
    if kind == "Text":
        keys = (
            "text",
            "color",
            "orient_deg",
            "h_align",
            "v_align",
            "pen_width_nm",
            "italic",
            "bold",
            "font_face",
        )
    elif kind == "PlotImage":
        keys = ("stroke_color", "line_style")
    else:
        keys = ("fill", "width_nm", "stroke_color", "fill_color", "line_style")
    out: dict[str, Any] = {}
    for key in keys:
        if key in payload:
            out[key] = _normalise_style_value(key, payload.get(key))
    if kind != "Text" and "line_style" not in out:
        out["line_style"] = "SOLID"
    return out


def _style_mismatches(rec: KiCadPlotterOp, mk: KiCadPlotterOp) -> dict[str, tuple[Any, Any]]:
    rec_style = _style_payload(rec)
    mk_style = _style_payload(mk)
    keys = sorted(set(rec_style) | set(mk_style))
    return {
        key: (rec_style.get(key), mk_style.get(key))
        for key in keys
        if rec_style.get(key) != mk_style.get(key)
    }


@dataclass
class _MatchAccumulator:
    """Mutable scratch state for either matching strategy."""

    matched: int = 0
    kind_mismatches: int = 0
    coord_length_mismatches: int = 0
    coord_delta_exceeded: int = 0
    style_mismatches: int = 0
    monkey_short: int = 0
    monkey_long: int = 0
    first: KiCadOpDivergence | None = None
    max_delta: float = 0.0


def _compare_pair(
    *,
    rec: KiCadPlotterOp,
    mk: KiCadPlotterOp,
    position: int,
    tolerance_nm: float,
    acc: "_MatchAccumulator",
    kind_for_details: str,
    compare_styles: bool,
    details_suffix: str = "",
) -> None:
    """Apply coord-length + tolerance checks to a same-kind pair.

    Updates ``acc`` in place. Caller is responsible for the kind check.
    """
    rec_coords = _extract_coords(rec)
    mk_coords = _extract_coords(mk)
    if len(rec_coords) != len(mk_coords):
        acc.coord_length_mismatches += 1
        if acc.first is None:
            acc.first = KiCadOpDivergence(
                position=position,
                kind="coord_length_mismatch",
                recorder_op=rec,
                monkey_op=mk,
                details=(
                    f"coord lengths differ: recorder={len(rec_coords)} "
                    f"monkey={len(mk_coords)} (kind={kind_for_details})"
                    f"{details_suffix}"
                ),
            )
        return

    delta = _max_coord_delta(rec_coords, mk_coords)
    if delta is None:
        acc.coord_length_mismatches += 1
        return
    if delta > acc.max_delta:
        acc.max_delta = delta
    if delta > tolerance_nm and not _semantically_equivalent(
        rec,
        mk,
        tolerance_nm=tolerance_nm,
        delta=delta,
    ):
        acc.coord_delta_exceeded += 1
        if acc.first is None:
            acc.first = KiCadOpDivergence(
                position=position,
                kind="coord_delta_exceeded",
                recorder_op=rec,
                monkey_op=mk,
                max_coord_delta_nm=delta,
                details=(
                    f"max coord delta {delta} > tolerance {tolerance_nm} "
                    f"(kind={kind_for_details})"
                    f"{details_suffix}"
                ),
            )
        return
    if compare_styles:
        style_diff = _style_mismatches(rec, mk)
        if style_diff:
            acc.style_mismatches += 1
            if acc.first is None:
                acc.first = KiCadOpDivergence(
                    position=position,
                    kind="style_mismatch",
                    recorder_op=rec,
                    monkey_op=mk,
                    details=(
                        f"style payload differs (kind={kind_for_details}): "
                        f"{style_diff}{details_suffix}"
                    ),
                )
            return
    acc.matched += 1


def _match_positional(
    rec_ops: list[KiCadPlotterOp],
    mk_ops: list[KiCadPlotterOp],
    *,
    tolerance_nm: float,
    compare_styles: bool,
) -> _MatchAccumulator:
    """Strict per-position matching."""
    acc = _MatchAccumulator()
    pair_count = min(len(rec_ops), len(mk_ops))
    for i in range(pair_count):
        rec = rec_ops[i]
        mk = mk_ops[i]
        rec_kind = _kind_str(rec)
        mk_kind = _kind_str(mk)

        if _equivalent_kind(rec_kind) != _equivalent_kind(mk_kind):
            acc.kind_mismatches += 1
            if acc.first is None:
                acc.first = KiCadOpDivergence(
                    position=i,
                    kind="kind_mismatch",
                    recorder_op=rec,
                    monkey_op=mk,
                    details=(
                        f"recorder kind {rec_kind!r} != monkey kind {mk_kind!r}"
                    ),
                )
            continue

        _compare_pair(
            rec=rec,
            mk=mk,
            position=i,
            tolerance_nm=tolerance_nm,
            acc=acc,
            kind_for_details=rec_kind,
            compare_styles=compare_styles,
        )

    # Length divergences
    acc.monkey_short = max(0, len(rec_ops) - len(mk_ops))
    acc.monkey_long = max(0, len(mk_ops) - len(rec_ops))
    if acc.first is None and acc.monkey_short > 0:
        acc.first = KiCadOpDivergence(
            position=pair_count,
            kind="monkey_short",
            recorder_op=rec_ops[pair_count] if pair_count < len(rec_ops) else None,
            monkey_op=None,
            details=(
                f"monkey ran out at position {pair_count}; recorder has "
                f"{acc.monkey_short} more op(s)"
            ),
        )
    elif acc.first is None and acc.monkey_long > 0:
        acc.first = KiCadOpDivergence(
            position=pair_count,
            kind="monkey_long",
            recorder_op=None,
            monkey_op=mk_ops[pair_count] if pair_count < len(mk_ops) else None,
            details=(
                f"recorder ran out at position {pair_count}; monkey has "
                f"{acc.monkey_long} more op(s)"
            ),
        )
    return acc


def _match_by_kind(
    rec_ops: list[KiCadPlotterOp],
    mk_ops: list[KiCadPlotterOp],
    *,
    tolerance_nm: float,
    compare_styles: bool,
) -> _MatchAccumulator:
    """Per-kind-bucket matching.

    Group both sides by ``_equivalent_kind(_kind_str(op))`` preserving
    document order within each bucket; pair positionally inside each
    bucket. ``kind_mismatches`` is always 0; per-kind population
    imbalances accumulate into ``monkey_short`` / ``monkey_long``. The
    first failing bucket (in recorder-side first-appearance order, then
    monkey-only kinds in monkey-side order) populates
    ``first_divergence`` with the kind named in ``details``.
    """
    acc = _MatchAccumulator()

    rec_by_kind: dict[str, list[tuple[int, KiCadPlotterOp]]] = {}
    mk_by_kind: dict[str, list[tuple[int, KiCadPlotterOp]]] = {}
    for i, op in enumerate(rec_ops):
        rec_by_kind.setdefault(_equivalent_kind(_kind_str(op)), []).append((i, op))
    for i, op in enumerate(mk_ops):
        mk_by_kind.setdefault(_equivalent_kind(_kind_str(op)), []).append((i, op))

    # Deterministic kind order: recorder-first-appearance, then any
    # monkey-only kinds in monkey first-appearance order.
    seen_kinds: list[str] = []
    for op in rec_ops:
        k = _equivalent_kind(_kind_str(op))
        if k not in seen_kinds:
            seen_kinds.append(k)
    for op in mk_ops:
        k = _equivalent_kind(_kind_str(op))
        if k not in seen_kinds:
            seen_kinds.append(k)

    for kind in seen_kinds:
        rec_list = rec_by_kind.get(kind, [])
        mk_list = mk_by_kind.get(kind, [])
        n = min(len(rec_list), len(mk_list))
        for i in range(n):
            ri, rec = rec_list[i]
            _, mk = mk_list[i]
            _compare_pair(
                rec=rec,
                mk=mk,
                position=ri,
                tolerance_nm=tolerance_nm,
                acc=acc,
                kind_for_details=kind,
                compare_styles=compare_styles,
                details_suffix=", by_kind",
            )

        # Per-kind leftovers → length divergences.
        if len(rec_list) > n:
            extra = len(rec_list) - n
            acc.monkey_short += extra
            if acc.first is None:
                ri, leftover = rec_list[n]
                acc.first = KiCadOpDivergence(
                    position=ri,
                    kind="monkey_short",
                    recorder_op=leftover,
                    monkey_op=None,
                    details=(
                        f"by_kind: kind {kind!r} has {extra} extra recorder op(s) "
                        f"with no monkey partner"
                    ),
                )
        if len(mk_list) > n:
            extra = len(mk_list) - n
            acc.monkey_long += extra
            if acc.first is None:
                mi, leftover = mk_list[n]
                acc.first = KiCadOpDivergence(
                    position=mi,
                    kind="monkey_long",
                    recorder_op=None,
                    monkey_op=leftover,
                    details=(
                        f"by_kind: kind {kind!r} has {extra} extra monkey op(s) "
                        f"with no recorder partner"
                    ),
                )
    return acc


def _match_windowed_by_kind(
    rec_ops: list[KiCadPlotterOp],
    mk_ops: list[KiCadPlotterOp],
    *,
    tolerance_nm: float,
    match_window: int,
    compare_styles: bool,
) -> _MatchAccumulator:
    """Greedy minimum-coord-delta matching within each kind bucket.

    Group both sides by ``_equivalent_kind(_kind_str(op))`` preserving
    document order within each bucket. Inside each bucket build the set
    of candidate (rec_local_idx, mk_local_idx) pairs whose coord
    sequences have equal length AND (when ``match_window > 0``) whose
    bucket-local index displacement is ``<= match_window``. Sort
    candidates by ``max-abs-delta`` ascending and greedily assign the
    lowest-delta pairs first, skipping any candidate whose recorder or
    monkey side has already been matched. Stop the in-tolerance pass
    when the next candidate's delta exceeds ``tolerance_nm``.

    Unmatched recorder ops in each bucket flow into ``monkey_short``;
    unmatched monkey ops flow into ``monkey_long``. The first such
    leftover (in document order, kind iteration order matching
    ``_match_by_kind``) populates ``first_divergence``.

    ``max_observed_coord_delta_nm`` tracks the largest observed delta
    across all *evaluated* candidate pairs (not just consumed ones), so
    a fixture that has many close-but-out-of-tolerance candidates
    surfaces a useful worst-case number even when nothing got paired.

    ``coord_length_mismatch`` and ``coord_delta_exceeded`` counters are
    not used in this strategy — coord-length mismatches simply fail to
    pair (the candidate is excluded from consideration), and
    over-tolerance deltas leave both ops as leftover. The diagnostic
    shift is intentional: v3 answers "did the op find a partner?"
    rather than v2's "did the positional partner agree?".
    """
    acc = _MatchAccumulator()

    rec_by_kind: dict[str, list[tuple[int, KiCadPlotterOp]]] = {}
    mk_by_kind: dict[str, list[tuple[int, KiCadPlotterOp]]] = {}
    for i, op in enumerate(rec_ops):
        rec_by_kind.setdefault(_equivalent_kind(_kind_str(op)), []).append((i, op))
    for i, op in enumerate(mk_ops):
        mk_by_kind.setdefault(_equivalent_kind(_kind_str(op)), []).append((i, op))

    seen_kinds: list[str] = []
    for op in rec_ops:
        k = _equivalent_kind(_kind_str(op))
        if k not in seen_kinds:
            seen_kinds.append(k)
    for op in mk_ops:
        k = _equivalent_kind(_kind_str(op))
        if k not in seen_kinds:
            seen_kinds.append(k)

    for kind in seen_kinds:
        rec_list = rec_by_kind.get(kind, [])
        mk_list = mk_by_kind.get(kind, [])

        # Build candidate (delta, rec_local, mk_local) tuples.
        candidates: list[tuple[int, int, float, int, int]] = []
        for ri in range(len(rec_list)):
            _, rop = rec_list[ri]
            rcoords = _extract_coords(rop)
            for mi in range(len(mk_list)):
                if match_window > 0 and abs(ri - mi) > match_window:
                    continue
                _, mop = mk_list[mi]
                mcoords = _extract_coords(mop)
                if len(rcoords) != len(mcoords):
                    continue
                d = _max_coord_delta(rcoords, mcoords)
                if d is None:
                    continue
                if d > acc.max_delta:
                    acc.max_delta = d
                accepted = (
                    d <= tolerance_nm
                    or _semantically_equivalent(
                        rop,
                        mop,
                        tolerance_nm=tolerance_nm,
                        delta=d,
                    )
                )
                style_penalty = (
                    1
                    if compare_styles and _style_mismatches(rop, mop)
                    else 0
                )
                candidates.append((0 if accepted else 1, style_penalty, d, ri, mi))

        # Greedy in-tolerance assignment.
        candidates.sort(key=lambda t: (t[0], t[1], t[2]))
        matched_rec_local: set[int] = set()
        matched_mk_local: set[int] = set()
        for rejected, _style_penalty, delta, ri, mi in candidates:
            if rejected:
                # All remaining candidates exceed tolerance — stop.
                break
            if ri in matched_rec_local or mi in matched_mk_local:
                continue
            global_pos, rop = rec_list[ri]
            _, mop = mk_list[mi]
            _compare_pair(
                rec=rop,
                mk=mop,
                position=global_pos,
                tolerance_nm=tolerance_nm,
                acc=acc,
                kind_for_details=kind,
                compare_styles=compare_styles,
                details_suffix=f", windowed_by_kind(window={match_window})",
            )
            matched_rec_local.add(ri)
            matched_mk_local.add(mi)

        # Per-kind leftovers (recorder side first, then monkey side).
        if len(matched_rec_local) < len(rec_list):
            extra = len(rec_list) - len(matched_rec_local)
            acc.monkey_short += extra
            if acc.first is None:
                for ri in range(len(rec_list)):
                    if ri not in matched_rec_local:
                        global_pos, leftover = rec_list[ri]
                        acc.first = KiCadOpDivergence(
                            position=global_pos,
                            kind="monkey_short",
                            recorder_op=leftover,
                            monkey_op=None,
                            details=(
                                f"windowed_by_kind: kind {kind!r} has {extra} extra "
                                f"recorder op(s) with no monkey partner within "
                                f"tolerance/window (window={match_window})"
                            ),
                        )
                        break
        if len(matched_mk_local) < len(mk_list):
            extra = len(mk_list) - len(matched_mk_local)
            acc.monkey_long += extra
            if acc.first is None:
                for mi in range(len(mk_list)):
                    if mi not in matched_mk_local:
                        global_pos, leftover = mk_list[mi]
                        acc.first = KiCadOpDivergence(
                            position=global_pos,
                            kind="monkey_long",
                            recorder_op=None,
                            monkey_op=leftover,
                            details=(
                                f"windowed_by_kind: kind {kind!r} has {extra} extra "
                                f"monkey op(s) with no recorder partner within "
                                f"tolerance/window (window={match_window})"
                            ),
                        )
                        break
    return acc


# =============================================================================
# Divergence record
# =============================================================================


@dataclass(frozen=True)
class KiCadOpDivergence:
    """
    Structured description of one paired-op divergence.

    ``kind`` values:

    * ``"kind_mismatch"`` — paired ops have different (non-equivalent)
      :attr:`KiCadPlotterOp.kind` values.
    * ``"coord_length_mismatch"`` — kinds match but the coord
      sequences have different lengths (e.g. ``PlotPoly`` with a
      different vertex count).
    * ``"coord_delta_exceeded"`` — kinds and lengths match but
      ``max-abs-delta`` exceeded ``tolerance_nm``.
    * ``"monkey_short"`` — kicad_monkey ran out of ops first.
    * ``"monkey_long"`` — recorder ran out of ops first.
    """

    position: int
    kind: str
    recorder_op: KiCadPlotterOp | None = None
    monkey_op: KiCadPlotterOp | None = None
    max_coord_delta_nm: float | None = None
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "position": self.position,
            "kind": self.kind,
            "details": self.details,
        }
        if self.recorder_op is not None:
            out["recorder_op"] = self.recorder_op.to_dict()
        else:
            out["recorder_op"] = None
        if self.monkey_op is not None:
            out["monkey_op"] = self.monkey_op.to_dict()
        else:
            out["monkey_op"] = None
        out["max_coord_delta_nm"] = (
            float(self.max_coord_delta_nm)
            if self.max_coord_delta_nm is not None
            else None
        )
        return out


# =============================================================================
# Aggregate report
# =============================================================================


@dataclass(frozen=True)
class OpEquivalenceReport:
    """
    Aggregate output of :func:`compute_op_equivalence`.

    ``equivalent`` is ``True`` iff every paired position passes the
    kind + coord-length + tolerance checks AND both sides have the same
    number of geometric ops. Use :attr:`first_divergence` for the
    structural detail of the first failing position.
    """

    schema: str = KICAD_OP_EQUIVALENCE_SCHEMA
    tolerance_nm: float = 0.0
    fold_stroked_text: bool = True
    fold_pen_to_runs: bool = False
    ignore_stroked_text_runs: bool = False
    match_strategy: str = MATCH_STRATEGY_POSITIONAL
    match_window: int = MATCH_WINDOW_UNBOUNDED
    compare_styles: bool = True

    # Stream sizes (post-fold, post-state-filter for recorder)
    recorder_total: int = 0
    monkey_total: int = 0

    # Per-position outcomes (over min(recorder_total, monkey_total))
    matched_pairs: int = 0
    kind_mismatches: int = 0
    coord_length_mismatches: int = 0
    coord_delta_exceeded: int = 0
    style_mismatches: int = 0

    # Length divergences
    monkey_short: int = 0  # recorder has more ops than monkey
    monkey_long: int = 0  # monkey has more ops than recorder

    # First divergence (None when streams are equivalent)
    first_divergence: KiCadOpDivergence | None = None

    # Fold provenance
    stroked_text_runs_folded: int = 0
    stroked_text_ops_absorbed: int = 0

    # Worst observed delta across all positionally-paired matches
    max_observed_coord_delta_nm: float = 0.0

    @property
    def equivalent(self) -> bool:
        return (
            self.first_divergence is None
            and self.monkey_short == 0
            and self.monkey_long == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "tolerance_nm": self.tolerance_nm,
            "fold_stroked_text": self.fold_stroked_text,
            "fold_pen_to_runs": self.fold_pen_to_runs,
            "ignore_stroked_text_runs": self.ignore_stroked_text_runs,
            "match_strategy": self.match_strategy,
            "match_window": self.match_window,
            "compare_styles": self.compare_styles,
            "equivalent": self.equivalent,
            "stream_sizes": {
                "recorder_total": self.recorder_total,
                "monkey_total": self.monkey_total,
            },
            "pair_outcomes": {
                "matched": self.matched_pairs,
                "kind_mismatches": self.kind_mismatches,
                "coord_length_mismatches": self.coord_length_mismatches,
                "coord_delta_exceeded": self.coord_delta_exceeded,
                "style_mismatches": self.style_mismatches,
            },
            "length_divergence": {
                "monkey_short": self.monkey_short,
                "monkey_long": self.monkey_long,
            },
            "first_divergence": (
                self.first_divergence.to_dict()
                if self.first_divergence is not None
                else None
            ),
            "stroked_text_fold": {
                "runs_folded": self.stroked_text_runs_folded,
                "ops_absorbed": self.stroked_text_ops_absorbed,
            },
            "max_observed_coord_delta_nm": self.max_observed_coord_delta_nm,
        }


# =============================================================================
# Main entry point
# =============================================================================


def compute_op_equivalence(
    recorder_doc: KiCadPlotterDocument,
    monkey_doc: KiCadPlotterDocument,
    *,
    tolerance_nm: float = 0.0,
    fold_stroked_text: bool = True,
    fold_pen_to_runs: bool = False,
    ignore_stroked_text_runs: bool = False,
    stroked_text_min_points: int = STROKED_TEXT_FOLD_MIN_POINTS,
    stroked_text_min_run_size: int = STROKED_TEXT_FOLD_MIN_RUN,
    match_strategy: str = MATCH_STRATEGY_POSITIONAL,
    match_window: int = MATCH_WINDOW_UNBOUNDED,
    compare_styles: bool = True,
) -> OpEquivalenceReport:
    """
    Compute a tolerance-aware ordered op-by-op equivalence diff.

    Parameters
    ----------
    recorder_doc :
        Document loaded via :func:`load_recorder_file` (or any
        ``kicad.plotter_recorder.v1`` source).
    monkey_doc :
        Document produced by :func:`schematic_to_ir` /
        :func:`lib_symbol_to_ir` / similar parser->IR boundary.
    tolerance_nm :
        Maximum allowed ``max-abs-delta`` per paired op (nm). Defaults
        to ``0.0`` (exact match required).
    fold_stroked_text :
        When ``True`` (default), apply the stroked-text fold to the recorder
        side before pairing. Disable for raw-pairing diagnostics.
    fold_pen_to_runs :
        When ``True``, collapse recorder ``PenTo`` draw runs into
        declarative ``PlotPoly`` / ``Rect`` ops before state filtering.
        This is useful for focused vocabulary-reduction analysis, but
        stays opt-in because the frozen recorder fixtures still include
        drawing-sheet linework without one-to-one declarative partners.
    ignore_stroked_text_runs :
        Drop synthetic ``StrokedTextRun`` ops after folding and before
        matching. Enable this for recorder dumps that keep high-level
        ``Text`` calls and also contain stroke-font glyph polygons.
    stroked_text_min_points / stroked_text_min_run_size :
        Forwarded to :func:`fold_stroked_text_runs` when fold is
        enabled.
    match_strategy :
        ``"positional"`` (default) for strict per-index pairing,
        ``"by_kind"`` for per-kind-bucket positional pairing, or
        ``"windowed_by_kind"`` for greedy minimum-coord-delta pairing
        within each bucket (intra-kind reordering tolerant). See
        module docstring for when to use each.
    match_window :
        Only meaningful for ``"windowed_by_kind"``. Maximum
        bucket-local positional displacement allowed when pairing.
        ``0`` (default) means unbounded — the full bucket is searched
        for the best partner. Positive values cap the search to
        ``|rec_local_idx - mk_local_idx| <= match_window``. Ignored
        for the other strategies.
    """
    if match_strategy not in _VALID_MATCH_STRATEGIES:
        raise ValueError(
            f"match_strategy must be one of "
            f"{sorted(_VALID_MATCH_STRATEGIES)}, got {match_strategy!r}"
        )
    if match_window < 0:
        raise ValueError(
            f"match_window must be >= 0 (0 = unbounded), got {match_window!r}"
        )

    rec_ops_raw = _flatten_ops(recorder_doc)
    mk_ops_raw = _flatten_ops(monkey_doc)

    if fold_stroked_text:
        rec_after_fold, runs_folded, ops_absorbed = fold_stroked_text_runs(
            rec_ops_raw,
            min_points=stroked_text_min_points,
            min_run_size=stroked_text_min_run_size,
        )
    else:
        rec_after_fold = rec_ops_raw
        runs_folded = 0
        ops_absorbed = 0

    if fold_pen_to_runs:
        rec_after_fold = _fold_pen_to_runs(rec_after_fold)
    rec_after_fold = _apply_recorder_style_state(rec_after_fold)
    rec_ops = _filter_geometric(rec_after_fold)
    rec_ops = _merge_fill_outline_primitives(rec_ops)
    if ignore_stroked_text_runs:
        rec_ops = [
            op
            for op in rec_ops
            if _kind_str(op) != STROKED_TEXT_FOLD_KIND
        ]
    rec_ops = _split_multiline_text_ops(rec_ops)
    rec_ops = _drop_idempotent_duplicate_ops(rec_ops)
    mk_ops = _split_multiline_text_ops(
        _merge_fill_outline_primitives(_filter_geometric(mk_ops_raw))
    )
    mk_ops = _drop_idempotent_duplicate_ops(mk_ops)

    if match_strategy == MATCH_STRATEGY_WINDOWED_BY_KIND:
        acc = _match_windowed_by_kind(
            rec_ops,
            mk_ops,
            tolerance_nm=float(tolerance_nm),
            match_window=match_window,
            compare_styles=compare_styles,
        )
    elif match_strategy == MATCH_STRATEGY_BY_KIND:
        acc = _match_by_kind(
            rec_ops,
            mk_ops,
            tolerance_nm=float(tolerance_nm),
            compare_styles=compare_styles,
        )
    else:
        acc = _match_positional(
            rec_ops,
            mk_ops,
            tolerance_nm=float(tolerance_nm),
            compare_styles=compare_styles,
        )

    return OpEquivalenceReport(
        schema=KICAD_OP_EQUIVALENCE_SCHEMA,
        tolerance_nm=float(tolerance_nm),
        fold_stroked_text=fold_stroked_text,
        fold_pen_to_runs=fold_pen_to_runs,
        ignore_stroked_text_runs=ignore_stroked_text_runs,
        match_strategy=match_strategy,
        match_window=match_window,
        compare_styles=compare_styles,
        recorder_total=len(rec_ops),
        monkey_total=len(mk_ops),
        matched_pairs=acc.matched,
        kind_mismatches=acc.kind_mismatches,
        coord_length_mismatches=acc.coord_length_mismatches,
        coord_delta_exceeded=acc.coord_delta_exceeded,
        style_mismatches=acc.style_mismatches,
        monkey_short=acc.monkey_short,
        monkey_long=acc.monkey_long,
        first_divergence=acc.first,
        stroked_text_runs_folded=runs_folded,
        stroked_text_ops_absorbed=ops_absorbed,
        max_observed_coord_delta_nm=acc.max_delta,
    )


__all__ = [
    "KICAD_OP_EQUIVALENCE_SCHEMA",
    "MATCH_STRATEGY_BY_KIND",
    "MATCH_STRATEGY_POSITIONAL",
    "MATCH_STRATEGY_WINDOWED_BY_KIND",
    "MATCH_WINDOW_UNBOUNDED",
    "KiCadOpDivergence",
    "OpEquivalenceReport",
    "compute_op_equivalence",
]
