"""
2-D coordinate transforms for :class:`KiCadPlotterOp` payloads.

A ``LibSymbol`` body is converted to ops in the symbol's local frame via
:func:`lib_symbol_to_ir`, and those ops then need to be re-anchored at each
placement by translating, rotating, and mirroring the coordinates inside
their payloads.

This module is **purely structural**: it walks each op kind, applies a
:class:`KiCadPlotterTransform2D` to every coordinate field in the
payload, and returns a new op. It does not interpret semantics
(stroke width, fill, text content, etc.) and does not change op kind.

Transform order (matches KiCad's ``SCH_SYMBOL`` placement convention):

    1. rotate by ``rotation_deg`` (around 0,0 — symbol-local origin)
    2. mirror around the X axis (``mirror_x`` flips Y sign)
    3. mirror around the Y axis (``mirror_y`` flips X sign)
    4. translate by ``(offset_x_nm, offset_y_nm)``

For 90 / 180 / 270 deg multiples the rotation uses exact integer
arithmetic; for arbitrary angles ``math.cos``/``math.sin`` are used and
results are rounded to the nearest int.

Pure state ops (``SetColor``, ``SetCurrentLineWidth``, ``SetDash``,
``SetViewport``, ``SetPageSettings``, ``StartPlot``, ``EndPlot``,
``StartBlock``, ``EndBlock``) are returned unchanged — they have no
coordinates.

``orient_deg`` fields on ``Text`` / ``FlashPad*`` ops are summed with
``rotation_deg``. Mirror flag effects on those fields match KiCad's
convention: a mirror inverts the sign of ``orient_deg``.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

from .kicad_plotter_ir import KiCadPlotterOp, KiCadPlotterOpKind


# =============================================================================
# Transform dataclass
# =============================================================================


@dataclass(frozen=True)
class KiCadPlotterTransform2D:
    """
    Affine 2-D transform applied to a :class:`KiCadPlotterOp` payload.

    All numeric fields are in KiCad internal units (nm) for offsets and
    decimal degrees for the rotation. ``mirror_x`` mirrors around the X
    axis (Y sign flips); ``mirror_y`` mirrors around the Y axis (X sign
    flips).

    Default values give the identity transform.
    """

    offset_x_nm: int = 0
    offset_y_nm: int = 0
    rotation_deg: float = 0.0
    mirror_x: bool = False
    mirror_y: bool = False

    @classmethod
    def identity(cls) -> "KiCadPlotterTransform2D":
        return cls()

    @classmethod
    def translation(cls, dx_nm: int, dy_nm: int) -> "KiCadPlotterTransform2D":
        return cls(offset_x_nm=int(dx_nm), offset_y_nm=int(dy_nm))


# =============================================================================
# Coordinate transforms
# =============================================================================


_PURE_STATE_OP_KINDS: frozenset[str] = frozenset(
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
    }
)


def transform_point(
    x: float, y: float, transform: KiCadPlotterTransform2D
) -> tuple[int, int]:
    """
    Apply ``transform`` to a single point and return ``(int_x, int_y)``.

    Steps: rotate → mirror_x → mirror_y → translate.
    Float results are rounded to the nearest integer (banker's rounding
    via Python's built-in ``round``).
    """
    rx, ry = _rotate(float(x), float(y), transform.rotation_deg)
    if transform.mirror_x:
        ry = -ry
    if transform.mirror_y:
        rx = -rx
    rx += transform.offset_x_nm
    ry += transform.offset_y_nm
    return int(round(rx)), int(round(ry))


def transform_orient(orient_deg: float, transform: KiCadPlotterTransform2D) -> float:
    """
    Apply ``transform`` to a text/flash orient angle. Mirror flags
    invert the angle sign (matching KiCad's convention).
    """
    angle = float(orient_deg) + float(transform.rotation_deg)
    if transform.mirror_x:
        angle = -angle
    if transform.mirror_y:
        angle = -angle
    return angle


def _rotate(x: float, y: float, angle_deg: float) -> tuple[float, float]:
    """
    Rotate ``(x, y)`` by ``angle_deg`` around the origin. Uses exact
    integer arithmetic for 90/180/270/0 deg multiples (modulo 360);
    otherwise falls back to ``math.cos``/``math.sin``.
    """
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


# =============================================================================
# Per-kind dispatch
# =============================================================================


def _xform_xy(payload: dict[str, Any], transform: KiCadPlotterTransform2D, *,
              x_key: str, y_key: str) -> None:
    nx, ny = transform_point(payload[x_key], payload[y_key], transform)
    payload[x_key] = nx
    payload[y_key] = ny


def apply_transform_to_op(
    op: KiCadPlotterOp, transform: KiCadPlotterTransform2D
) -> KiCadPlotterOp:
    """
    Return a new :class:`KiCadPlotterOp` with ``transform`` applied to
    every coordinate field in its payload. Op kind, fill, stroke width,
    colour, etc. are preserved unchanged.

    Pure state ops (no coordinates) are returned unchanged (a fresh
    deep-copy, so callers can mutate the result safely).
    """
    kind_str = str(getattr(op.kind, "value", op.kind))

    payload = copy.deepcopy(op.payload)

    if kind_str in _PURE_STATE_OP_KINDS:
        return KiCadPlotterOp(kind=op.kind, payload=payload)

    if kind_str == KiCadPlotterOpKind.PEN_TO.value:
        _xform_xy(payload, transform, x_key="x", y_key="y")

    elif kind_str == KiCadPlotterOpKind.CIRCLE.value:
        _xform_xy(payload, transform, x_key="cx", y_key="cy")

    elif kind_str == KiCadPlotterOpKind.ARC_THREE_POINT.value:
        _xform_xy(payload, transform, x_key="start_x", y_key="start_y")
        _xform_xy(payload, transform, x_key="mid_x", y_key="mid_y")
        _xform_xy(payload, transform, x_key="end_x", y_key="end_y")

    elif kind_str == KiCadPlotterOpKind.ARC_CENTER_ANGLE.value:
        _xform_xy(payload, transform, x_key="cx", y_key="cy")
        payload["start_angle_deg"] = transform_orient(
            payload["start_angle_deg"], transform
        )
        # sweep_deg sign flips under a single mirror; double mirror cancels.
        if transform.mirror_x ^ transform.mirror_y:
            payload["sweep_deg"] = -float(payload["sweep_deg"])

    elif kind_str == KiCadPlotterOpKind.BEZIER_CURVE.value:
        for x_key, y_key in (
            ("start_x", "start_y"),
            ("ctrl1_x", "ctrl1_y"),
            ("ctrl2_x", "ctrl2_y"),
            ("end_x", "end_y"),
        ):
            _xform_xy(payload, transform, x_key=x_key, y_key=y_key)

    elif kind_str == KiCadPlotterOpKind.RECT.value:
        # Rect's two corners are points; transform both. Caller may
        # later renormalise (x1 ≤ x2, y1 ≤ y2) if downstream code
        # requires it — we preserve identity of the named corners.
        _xform_xy(payload, transform, x_key="x1", y_key="y1")
        _xform_xy(payload, transform, x_key="x2", y_key="y2")

    elif kind_str == KiCadPlotterOpKind.PLOT_POLY.value:
        new_points = []
        for pt in payload.get("points", []):
            nx, ny = transform_point(pt[0], pt[1], transform)
            new_points.append([nx, ny])
        payload["points"] = new_points

    elif kind_str == KiCadPlotterOpKind.TEXT.value:
        _xform_xy(payload, transform, x_key="x", y_key="y")
        payload["orient_deg"] = transform_orient(payload["orient_deg"], transform)

    elif kind_str == KiCadPlotterOpKind.PLOT_IMAGE.value:
        _xform_xy(payload, transform, x_key="x", y_key="y")

    elif kind_str == KiCadPlotterOpKind.THICK_SEGMENT.value:
        _xform_xy(payload, transform, x_key="start_x", y_key="start_y")
        _xform_xy(payload, transform, x_key="end_x", y_key="end_y")

    elif kind_str == KiCadPlotterOpKind.THICK_ARC.value:
        _xform_xy(payload, transform, x_key="cx", y_key="cy")
        payload["start_angle_deg"] = transform_orient(
            payload["start_angle_deg"], transform
        )
        if transform.mirror_x ^ transform.mirror_y:
            payload["sweep_deg"] = -float(payload["sweep_deg"])

    elif kind_str in (
        KiCadPlotterOpKind.FLASH_PAD_CIRCLE.value,
    ):
        _xform_xy(payload, transform, x_key="x", y_key="y")

    elif kind_str in (
        KiCadPlotterOpKind.FLASH_PAD_OVAL.value,
        KiCadPlotterOpKind.FLASH_PAD_RECT.value,
        KiCadPlotterOpKind.FLASH_PAD_ROUNDRECT.value,
        KiCadPlotterOpKind.FLASH_REG_POLYGON.value,
    ):
        _xform_xy(payload, transform, x_key="x", y_key="y")
        payload["orient_deg"] = transform_orient(payload["orient_deg"], transform)

    elif kind_str == KiCadPlotterOpKind.FLASH_PAD_CUSTOM.value:
        _xform_xy(payload, transform, x_key="x", y_key="y")
        payload["orient_deg"] = transform_orient(payload["orient_deg"], transform)
        new_polygons = []
        for ring in payload.get("polygons", []):
            new_ring = []
            for pt in ring:
                nx, ny = transform_point(pt[0], pt[1], transform)
                new_ring.append([nx, ny])
            new_polygons.append(new_ring)
        payload["polygons"] = new_polygons

    elif kind_str == KiCadPlotterOpKind.FLASH_PAD_TRAPEZ.value:
        _xform_xy(payload, transform, x_key="x", y_key="y")
        payload["orient_deg"] = transform_orient(payload["orient_deg"], transform)
        new_corners = []
        for c in payload.get("corners", []):
            nx, ny = transform_point(c[0], c[1], transform)
            new_corners.append([nx, ny])
        payload["corners"] = new_corners

    # Unknown op kinds (forward-compat raw strings): pass through
    # unchanged. We can't safely guess which keys are coordinates.

    return KiCadPlotterOp(kind=op.kind, payload=payload)


def apply_transform_to_ops(
    ops: list[KiCadPlotterOp], transform: KiCadPlotterTransform2D
) -> list[KiCadPlotterOp]:
    """Apply ``transform`` to every op in ``ops``; return a new list."""
    return [apply_transform_to_op(op, transform) for op in ops]


__all__ = [
    "KiCadPlotterTransform2D",
    "apply_transform_to_op",
    "apply_transform_to_ops",
    "transform_orient",
    "transform_point",
]
