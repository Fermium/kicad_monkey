"""
Pad geometry helpers for the legacy PCB SVG renderer.

These functions are intentionally geometry-only. Standalone footprint SVG
rendering goes through the plotter-IR pipeline via KiCadFootprint.to_svg().
"""

from __future__ import annotations

import math
from typing import List, Tuple

from .kicad_geometry import rotate_point


def fmt(v: float, precision: int = 4) -> str:
    """Format float for SVG output matching KiCad's format."""
    return f"{v:.{precision}f}"


def pad_on_layer(pad, layer: str) -> bool:
    """Check if pad is present on the specified layer."""
    if layer in pad.layers:
        return True
    if layer in ("F.Cu", "B.Cu") and "F&B.Cu" in pad.layers:
        return True
    if layer.endswith(".Cu") and "*.Cu" in pad.layers:
        return True
    if layer.endswith(".Mask") and "*.Mask" in pad.layers:
        return True
    if layer.endswith(".Paste") and "*.Paste" in pad.layers:
        return True
    return False


def pad_to_rect_polygon(pad, clearance: float = 0.0) -> List[Tuple[float, float]]:
    """Convert rectangular pad to polygon corners in KiCad plot order."""
    half_w = pad.size_x / 2 + clearance
    half_h = pad.size_y / 2 + clearance

    corners = [
        (-half_w, half_h),
        (-half_w, -half_h),
        (half_w, -half_h),
        (half_w, half_h),
    ]

    if pad.at_angle != 0:
        corners = [rotate_point(x, y, -pad.at_angle) for x, y in corners]

    return [(x + pad.at_x, y + pad.at_y) for x, y in corners]


def get_arc_to_segment_count(
    radius: float,
    error_max: float,
    arc_angle_deg: float = 360.0,
) -> int:
    """Calculate number of segments to approximate an arc."""
    min_segcount_for_circle = 8

    radius = max(0.001, radius)
    error_max = max(0.001, error_max)
    rel_error = min(error_max / radius, 1.0)
    arc_increment = 180 / math.pi * math.acos(1.0 - rel_error) * 2
    arc_increment = min(360.0 / min_segcount_for_circle, arc_increment)

    return max(round(abs(arc_angle_deg) / arc_increment), 2)


def pad_to_rect_with_rounded_corners(
    pad,
    corner_radius: float,
    error_mm: float = 0.002,
) -> List[Tuple[float, float]]:
    """
    Convert rectangular pad to polygon with rounded corners.

    Used when mask expansion rounds rectangular pad corners by the mask
    clearance amount.
    """
    if corner_radius < 0.001:
        return pad_to_rect_polygon(pad)

    half_w = pad.size_x / 2 + corner_radius
    half_h = pad.size_y / 2 + corner_radius
    r = corner_radius

    num_segs = max(16, get_arc_to_segment_count(r, error_mm, 360.0))
    ang_delta = 360.0 / num_segs
    end_angle = 90.0

    last_seg = end_angle
    while last_seg > ang_delta:
        last_seg -= ang_delta

    if abs(last_seg) < 0.001:
        ang_pos_start = ang_delta
    else:
        ang_pos_start = (ang_delta + last_seg) / 2

    corners = []
    corner_centers = [
        (-half_w + r, -half_h + r),
        (half_w - r, -half_h + r),
        (half_w - r, half_h - r),
        (-half_w + r, half_h - r),
    ]
    arc_start_angles = [180, 270, 0, 90]

    for corner_idx in range(4):
        cx, cy = corner_centers[corner_idx]
        arc_start = arc_start_angles[corner_idx]

        angle_rad = math.radians(arc_start)
        corners.append((cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad)))

        ang_pos = ang_pos_start
        while ang_pos < end_angle - 0.001:
            angle_rad = math.radians(arc_start + ang_pos)
            corners.append((cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad)))
            ang_pos += ang_delta

        angle_rad = math.radians(arc_start + end_angle)
        corners.append((cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad)))

    if pad.at_angle != 0:
        corners = [rotate_point(x, y, -pad.at_angle) for x, y in corners]

    return [(x + pad.at_x, y + pad.at_y) for x, y in corners]


def pad_to_roundrect_polygon(
    pad,
    error_mm: float = 0.005,
    clearance: float = 0.0,
) -> List[Tuple[float, float]]:
    """Convert roundrect pad to polygon with rounded corners."""
    expanded_size_x = pad.size_x + 2 * clearance
    expanded_size_y = pad.size_y + 2 * clearance
    half_w = expanded_size_x / 2
    half_h = expanded_size_y / 2

    rratio = getattr(pad, "roundrect_rratio", None)
    if rratio is None:
        rratio = 0.25
    r = min(pad.size_x, pad.size_y) * rratio + clearance

    chamfer_ratio = getattr(pad, "chamfer_ratio", None)
    chamfer_corners = getattr(pad, "chamfer_corners", None) or []
    if chamfer_corners and chamfer_ratio is not None and chamfer_ratio > 0 and r < 0.001:
        return pad_to_chamfered_rect_polygon(
            pad,
            chamfer_ratio=chamfer_ratio,
            chamfer_corners=chamfer_corners,
            clearance=clearance,
        )

    if r < 0.001:
        return pad_to_rect_polygon(pad, clearance)

    num_segs = max(16, get_arc_to_segment_count(r, error_mm, 360.0))
    ang_delta = 360.0 / num_segs
    end_angle = 90.0

    last_seg = end_angle
    while last_seg > ang_delta:
        last_seg -= ang_delta

    if abs(last_seg) < 0.001:
        ang_pos_start = ang_delta
    else:
        ang_pos_start = (ang_delta + last_seg) / 2

    corners = []
    corner_centers = [
        (-half_w + r, -half_h + r),
        (half_w - r, -half_h + r),
        (half_w - r, half_h - r),
        (-half_w + r, half_h - r),
    ]
    arc_start_angles = [180, 270, 0, 90]

    for corner_idx in range(4):
        cx, cy = corner_centers[corner_idx]
        arc_start = arc_start_angles[corner_idx]

        angle_rad = math.radians(arc_start)
        corners.append((cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad)))

        ang_pos = ang_pos_start
        while ang_pos < end_angle - 0.001:
            angle_rad = math.radians(arc_start + ang_pos)
            corners.append((cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad)))
            ang_pos += ang_delta

        angle_rad = math.radians(arc_start + end_angle)
        corners.append((cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad)))

    if pad.at_angle != 0:
        corners = [rotate_point(x, y, -pad.at_angle) for x, y in corners]

    return [(x + pad.at_x, y + pad.at_y) for x, y in corners]


def pad_to_chamfered_rect_polygon(
    pad,
    chamfer_ratio: float,
    chamfer_corners: List[str],
    clearance: float = 0.0,
) -> List[Tuple[float, float]]:
    """Convert a chamfered roundrect pad to polygon."""
    expanded_size_x = pad.size_x + 2 * clearance
    expanded_size_y = pad.size_y + 2 * clearance
    half_w = expanded_size_x / 2
    half_h = expanded_size_y / 2

    shorter_side = min(pad.size_x, pad.size_y)
    chamfer = max(0.0, chamfer_ratio * shorter_side)

    corners = [
        {"x": -half_w, "y": -half_h},
        {"x": half_w, "y": -half_h},
        {"x": half_w, "y": half_h},
        {"x": -half_w, "y": half_h},
    ]

    chamfer_set = set(chamfer_corners)
    corner_names = ["top_left", "top_right", "bottom_right", "bottom_left"]
    sign = [0, 1, -1, 0, 0, -1, 1, 0]

    chamfer_count = sum(1 for name in corner_names if name in chamfer_set)
    pos = 0
    for cc, name in enumerate(corner_names):
        if name not in chamfer_set:
            pos += 1
            continue

        if chamfer == 0:
            pos += 1
            continue

        corners.insert(pos + 1, dict(corners[pos]))
        corners[pos]["x"] += sign[(2 * cc) & 7] * chamfer
        corners[pos]["y"] += sign[(2 * cc - 2) & 7] * chamfer
        corners[pos + 1]["x"] += sign[(2 * cc + 1) & 7] * chamfer
        corners[pos + 1]["y"] += sign[(2 * cc - 1) & 7] * chamfer
        pos += 2

    if chamfer_count > 1 and 2 * chamfer >= shorter_side:
        dedup = []
        for pt in corners:
            if not dedup:
                dedup.append(pt)
                continue
            if abs(pt["x"] - dedup[-1]["x"]) > 1e-9 or abs(pt["y"] - dedup[-1]["y"]) > 1e-9:
                dedup.append(pt)
        if (
            len(dedup) > 1
            and abs(dedup[0]["x"] - dedup[-1]["x"]) < 1e-9
            and abs(dedup[0]["y"] - dedup[-1]["y"]) < 1e-9
        ):
            dedup.pop()
        corners = dedup

    points = [(pt["x"], pt["y"]) for pt in corners]

    if pad.at_angle != 0:
        points = [rotate_point(x, y, -pad.at_angle) for x, y in points]

    return [(x + pad.at_x, y + pad.at_y) for x, y in points]


def pad_to_oval_thick_segment(
    pad,
    clearance: float = 0.0,
) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    """Convert oval pad to thick segment parameters."""
    w = pad.size_x + 2 * clearance
    h = pad.size_y + 2 * clearance
    angle = pad.at_angle

    if w > h:
        w, h = h, w
        angle = angle + 90

    delta = h - w
    start = (0, -delta / 2)
    end = (0, delta / 2)

    if angle != 0:
        start = rotate_point(start[0], start[1], -angle)
        end = rotate_point(end[0], end[1], -angle)

    return (
        (start[0] + pad.at_x, start[1] + pad.at_y),
        (end[0] + pad.at_x, end[1] + pad.at_y),
        w,
    )


__all__ = [
    "fmt",
    "pad_on_layer",
    "pad_to_oval_thick_segment",
    "pad_to_rect_polygon",
    "pad_to_rect_with_rounded_corners",
    "pad_to_roundrect_polygon",
]
