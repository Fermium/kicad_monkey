"""
Dashed/dotted stroke decomposition for IR emission.

Mirrors KiCad's ``STROKE_PARAMS::Stroke`` algorithm (``common/stroke_params.cpp``):
when a ``gr_line``/``gr_arc``/``fp_line``/``fp_arc`` carries a non-solid stroke
style, the PCB plotter decomposes the shape into individual sub-segments via
``ThickSegment`` calls — one per dash/dot. The SVG plotter then emits one
``<path>`` per segment (no CSS ``stroke-dasharray`` is used on the PCB plot
path).

This module replicates that decomposition in pure Python so that the IR-driven
SVG renderer can match kicad-cli's structural output exactly (one IR
``thick_segment`` op per dash → one SVG element per dash).

Length ratios (from KiCad ``RENDER_SETTINGS``, ISO 128-2 with correction=1.0):
  - dash_len = 11.0 * width
  - gap_len  = 4.0  * width
  - dot_len  = 0.2  * width

Arc dashes are further subdivided into 0.5-degree chord segments per kicad-cli.
Dot strokes on arcs (DOT alone, or the dot parts of DASH-DOT / DASH-DOT-DOT)
emit a single chord segment.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .kicad_base import StrokeType


# Ratios from RENDER_SETTINGS (correction = 1.0)
_DASH_RATIO = 11.0
_GAP_RATIO = 4.0
_DOT_RATIO = 0.2

# Arc subdivision step (matches kicad-cli's 0.5-degree increments)
_ARC_CHORD_STEP_RAD = math.radians(0.5)


def _stroke_pattern(
    style: "StrokeType",
    width_nm: int,
) -> tuple[list[float], int]:
    """Return (strokes_array, wrap_around) for a non-solid style."""
    from .kicad_base import StrokeType

    w = float(width_nm)
    dash = _DASH_RATIO * w
    gap = _GAP_RATIO * w
    dot = _DOT_RATIO * w

    if style == StrokeType.DASH:
        return [dash, gap], 2
    if style == StrokeType.DOT:
        return [dot, gap], 2
    if style == StrokeType.DASH_DOT:
        return [dash, gap, dot, gap], 4
    if style == StrokeType.DASH_DOT_DOT:
        return [dash, gap, dot, gap, dot, gap], 6
    raise ValueError(f"Solid styles do not need decomposition: {style!r}")


def is_decomposable_style(style: "StrokeType | None") -> bool:
    """True iff the style requires per-dash decomposition (i.e. non-solid)."""
    from .kicad_base import StrokeType

    if style is None:
        return False
    return style in (
        StrokeType.DASH,
        StrokeType.DOT,
        StrokeType.DASH_DOT,
        StrokeType.DASH_DOT_DOT,
    )


def decompose_segment(
    start_x_nm: int,
    start_y_nm: int,
    end_x_nm: int,
    end_y_nm: int,
    width_nm: int,
    style: "StrokeType",
) -> list[tuple[int, int, int, int]]:
    """Decompose a dashed line into sub-segments.

    Returns a list of (sx_nm, sy_nm, ex_nm, ey_nm) integer-nm tuples. The
    final sub-segment is clipped to the original line's end.
    """
    strokes, wrap = _stroke_pattern(style, width_nm)

    dx = float(end_x_nm - start_x_nm)
    dy = float(end_y_nm - start_y_nm)
    total = math.hypot(dx, dy)
    if total <= 0.0:
        return []

    ux = dx / total
    uy = dy / total

    out: list[tuple[int, int, int, int]] = []
    cur = 0.0
    i = 0
    while cur < total and i < 10000:
        seg_len = strokes[i % wrap]
        nxt = cur + seg_len
        if i % 2 == 0:
            end_along = min(nxt, total)
            if end_along > cur:
                ax = start_x_nm + ux * cur
                ay = start_y_nm + uy * cur
                bx = start_x_nm + ux * end_along
                by = start_y_nm + uy * end_along
                out.append(
                    (int(round(ax)), int(round(ay)), int(round(bx)), int(round(by)))
                )
        cur = nxt
        i += 1
    return out


def _arc_center_radius_from_three_points(
    sx: float, sy: float,
    mx: float, my: float,
    ex: float, ey: float,
) -> tuple[float, float, float] | None:
    """Return (cx, cy, radius) of the circle through three points.

    Returns None when the points are collinear (no finite circle).
    """
    # Perpendicular bisectors of (s, m) and (m, e) intersect at the center.
    # Solve the linear system from |P - C|^2 equality.
    ax = mx - sx
    ay = my - sy
    bx = ex - mx
    by = ey - my
    d = 2.0 * (ax * by - ay * bx)
    if abs(d) < 1e-9:
        return None

    # Standard circumscribed-circle formula.
    sx2 = sx * sx + sy * sy
    mx2 = mx * mx + my * my
    ex2 = ex * ex + ey * ey
    cx = (sx2 * (my - ey) + mx2 * (ey - sy) + ex2 * (sy - my)) / d
    cy = (sx2 * (ex - mx) + mx2 * (sx - ex) + ex2 * (mx - sx)) / d
    r = math.hypot(sx - cx, sy - cy)
    return cx, cy, r


def _normalize_arc_sweep(
    start_angle: float,
    mid_angle: float,
    end_angle: float,
) -> tuple[float, float]:
    """Return (start_angle, end_angle) such that start < end and the arc
    from start to end (CCW in math convention) passes through mid_angle.

    Mirrors the C++ KiCad logic: marches monotonically upward from start
    toward end. Direction is determined by which way (CCW or CW) the arc
    actually goes through the mid sample point.
    """
    two_pi = 2.0 * math.pi

    # Normalize all to [0, 2π)
    def n(a: float) -> float:
        return a % two_pi

    s = n(start_angle)
    m = n(mid_angle)
    e = n(end_angle)

    # CCW sweep from s to e passes through m iff:
    # (e - s) mod 2π contains (m - s) mod 2π.
    ccw_e = (e - s) % two_pi
    ccw_m = (m - s) % two_pi
    if ccw_e == 0.0:
        # Full circle
        return s, s + two_pi
    if 0.0 < ccw_m < ccw_e:
        # CCW: march from s upward to s + ccw_e
        return s, s + ccw_e

    # Otherwise the arc is CW from s to e. Equivalent CCW arc: from e upward to e + (2π - ccw_e).
    cw_sweep = two_pi - ccw_e
    return e, e + cw_sweep


def decompose_arc(
    start_x_nm: int, start_y_nm: int,
    mid_x_nm: int, mid_y_nm: int,
    end_x_nm: int, end_y_nm: int,
    width_nm: int,
    style: "StrokeType",
) -> list[tuple[int, int, int, int]]:
    """Decompose a dashed three-point arc into chord sub-segments.

    DASH segments (and the dash portions of DASH-DOT / DASH-DOT-DOT) are
    further subdivided into 0.5-degree chord steps to match kicad-cli's
    per-step ``ThickSegment`` emission. DOT segments emit a single chord.

    Returns a list of (sx_nm, sy_nm, ex_nm, ey_nm) integer-nm tuples.
    """
    from .kicad_base import StrokeType

    strokes, wrap = _stroke_pattern(style, width_nm)

    cr = _arc_center_radius_from_three_points(
        float(start_x_nm), float(start_y_nm),
        float(mid_x_nm), float(mid_y_nm),
        float(end_x_nm), float(end_y_nm),
    )
    if cr is None:
        # Collinear — fall back to segment decomposition (start → end).
        return decompose_segment(
            start_x_nm, start_y_nm, end_x_nm, end_y_nm, width_nm, style
        )

    cx, cy, r = cr
    if r <= 0.0:
        return []
    circumference = 2.0 * math.pi * r

    sa_raw = math.atan2(float(start_y_nm) - cy, float(start_x_nm) - cx)
    ma_raw = math.atan2(float(mid_y_nm) - cy, float(mid_x_nm) - cx)
    ea_raw = math.atan2(float(end_y_nm) - cy, float(end_x_nm) - cx)

    start_angle, arc_end_angle = _normalize_arc_sweep(sa_raw, ma_raw, ea_raw)

    out: list[tuple[int, int, int, int]] = []
    i = 0
    cur_angle = start_angle
    while cur_angle < arc_end_angle and i < 10000:
        seg_len = strokes[i % wrap]
        theta = 2.0 * math.pi * seg_len / circumference
        next_angle = min(cur_angle + theta, arc_end_angle)

        if i % 2 == 0:
            # Even index = drawn (dash or dot)
            subdivide = (style == StrokeType.DASH) or (
                style in (StrokeType.DASH_DOT, StrokeType.DASH_DOT_DOT)
                and (i % wrap) == 0
            )
            if subdivide:
                # Walk in 0.5-degree increments, emit chord per step.
                a_lo = cur_angle
                while a_lo < next_angle:
                    a_hi = min(a_lo + _ARC_CHORD_STEP_RAD, next_angle)
                    ax = cx + r * math.cos(a_lo)
                    ay = cy + r * math.sin(a_lo)
                    bx = cx + r * math.cos(a_hi)
                    by = cy + r * math.sin(a_hi)
                    out.append(
                        (
                            int(round(ax)),
                            int(round(ay)),
                            int(round(bx)),
                            int(round(by)),
                        )
                    )
                    a_lo = a_hi
            else:
                # Single chord across the dot interval.
                ax = cx + r * math.cos(cur_angle)
                ay = cy + r * math.sin(cur_angle)
                bx = cx + r * math.cos(next_angle)
                by = cy + r * math.sin(next_angle)
                out.append(
                    (
                        int(round(ax)),
                        int(round(ay)),
                        int(round(bx)),
                        int(round(by)),
                    )
                )

        cur_angle = next_angle
        i += 1

    return out


__all__ = [
    "decompose_arc",
    "decompose_segment",
    "is_decomposable_style",
]
