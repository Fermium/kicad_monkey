"""
Polygon conversion utilities matching KiCad's convert_basic_shapes_to_polygon.cpp

This module provides functions to convert basic shapes to polygon representations,
matching KiCad's internal algorithms for accurate rendering.

KiCad Source Reference:
    Version: 9.0.0-rc3-4364-g5f555f4d63
    Commit: 5f555f4d63b970e410d567d1f79e05e8ce41b9d8
    Date: 2025-11-27
    Source: https://gitlab.com/kicad/code/kicad
    Key files referenced:
    - libs/kimath/src/convert_basic_shapes_to_polygon.cpp - Core conversion functions
    - libs/kimath/include/convert_basic_shapes_to_polygon.h - Function signatures
    - common/eda_shape.cpp - EDA_SHAPE::TransformShapeToPolygon
    - pcbnew/pcb_track.cpp - Track/Arc/Via polygon conversion
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# Type aliases for clarity
Point = Tuple[float, float]
Contour = List[Point]


# =============================================================================
# Constants
# =============================================================================

# Default arc approximation error in mm
DEFAULT_ERROR_MM = 0.005

# Minimum segments for circle approximation (KiCad: MIN_SEGCOUNT_FOR_CIRCLE = 8)
MIN_SEGCOUNT_FOR_CIRCLE = 8


# =============================================================================
# PolygonSet - Container for polygons with holes
# =============================================================================

@dataclass(slots=True)
class PolygonSet:
    """
    Set of polygons with optional holes.

    Matches KiCad's SHAPE_POLY_SET concept - a collection of closed contours
    where the first contour is the outline and subsequent contours are holes.
    """
    outlines: List[Contour] = field(default_factory=list)
    holes: List[Contour] = field(default_factory=list)

    def to_svg_path(self, precision: int = 6) -> str:
        """Convert to SVG path data string with fill-rule='evenodd'."""
        parts = []

        # Outlines (counter-clockwise for SVG)
        for outline in self.outlines:
            parts.append(self._contour_to_path(outline, precision))

        # Holes (clockwise for SVG with evenodd)
        for hole in self.holes:
            parts.append(self._contour_to_path(hole, precision))

        return ' '.join(parts)

    @staticmethod
    def _contour_to_path(points: Contour, precision: int) -> str:
        """Convert a contour to SVG path commands."""
        if not points:
            return ''

        def fmt(v: float) -> str:
            if v == int(v):
                return str(int(v))
            return f"{v:.{precision}f}".rstrip('0').rstrip('.')

        d = f"M {fmt(points[0][0])},{fmt(points[0][1])}"
        for p in points[1:]:
            d += f" L {fmt(p[0])},{fmt(p[1])}"
        d += " Z"
        return d

    def is_empty(self) -> bool:
        """Check if polygon set is empty."""
        return len(self.outlines) == 0

    def append_outline(self, contour: Contour) -> None:
        """Add an outline contour."""
        self.outlines.append(contour)

    def append_hole(self, contour: Contour) -> None:
        """Add a hole contour."""
        self.holes.append(contour)

    def translate(self, dx: float, dy: float) -> 'PolygonSet':
        """
        Return a new PolygonSet with all coordinates translated by (dx, dy).

        Args:
            dx: X offset to add to all coordinates
            dy: Y offset to add to all coordinates

        Returns:
            New PolygonSet with translated coordinates
        """
        def translate_contour(contour: Contour) -> Contour:
            return [(x + dx, y + dy) for x, y in contour]

        return PolygonSet(
            outlines=[translate_contour(c) for c in self.outlines],
            holes=[translate_contour(c) for c in self.holes]
        )


# =============================================================================
# Utility Functions
# =============================================================================

def get_arc_segment_count(radius: float, error: float, arc_angle_deg: float = 360.0) -> int:
    """
    Calculate number of segments needed to approximate an arc.

    Exact clone of KiCad's GetArcToSegmentCount() from:
    libs/kimath/src/geometry/geometry_utils.cpp

    Algorithm:
        1. Calculate relative error: rel_error = error / radius
        2. Calculate arc increment in degrees: 180/PI * acos(1 - rel_error) * 2
        3. Cap arc increment at 45 degrees (360/8) for minimum 8 segments per circle
        4. Round arc_angle / arc_increment to nearest integer
        5. Return at least 2 segments

    Args:
        radius: Arc radius in mm
        error: Maximum allowed error in mm (KiCad default: 0.005mm)
        arc_angle_deg: Arc angle in degrees (360 for full circle)

    Returns:
        Number of segments needed
    """
    # KiCad clamps to minimum of 1 to avoid division by zero
    radius = max(1e-6, abs(radius))  # Use small float for mm units
    error = max(1e-6, abs(error))

    # Error relative to the radius value
    rel_error = error / radius

    # Clamp cos argument to valid range [-1, 1]
    cos_arg = 1.0 - rel_error
    cos_arg = max(-1.0, min(1.0, cos_arg))

    # Minimal arc increment in degrees
    # Formula: 180/PI * acos(1 - rel_error) * 2
    arc_increment = (180.0 / math.pi) * math.acos(cos_arg) * 2.0

    # Ensure a minimal arc increment (360.0/8 = 45 degrees)
    # This guarantees at least 8 segments for a full circle
    arc_increment = min(360.0 / MIN_SEGCOUNT_FOR_CIRCLE, arc_increment)

    # Avoid division by zero
    if arc_increment <= 0:
        return MIN_SEGCOUNT_FOR_CIRCLE

    # KiROUND - round to nearest integer
    seg_count = round(abs(arc_angle_deg) / arc_increment)

    # Return at least 2 segments
    return max(2, seg_count)


def rotate_point(point: Point, center: Point, angle_deg: float) -> Point:
    """Rotate a point around a center by angle (degrees, clockwise like KiCad)."""
    angle_rad = math.radians(-angle_deg)  # Negative for clockwise
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    dx = point[0] - center[0]
    dy = point[1] - center[1]

    new_x = center[0] + dx * cos_a - dy * sin_a
    new_y = center[1] + dx * sin_a + dy * cos_a

    return (new_x, new_y)


def distance(p1: Point, p2: Point) -> float:
    """Calculate distance between two points."""
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)


def normalize_vector(v: Point) -> Point:
    """Normalize a vector to unit length."""
    length = math.sqrt(v[0]**2 + v[1]**2)
    if length < 1e-10:
        return (0.0, 0.0)
    return (v[0] / length, v[1] / length)


def perpendicular(v: Point) -> Point:
    """Get perpendicular vector (90 degrees counter-clockwise)."""
    return (-v[1], v[0])


# =============================================================================
# Shape to Polygon Conversion Functions
# =============================================================================

def circle_to_polygon(
    center: Point,
    radius: float,
    error: float = DEFAULT_ERROR_MM,
    min_segments: int = MIN_SEGCOUNT_FOR_CIRCLE
) -> Contour:
    """
    Convert a circle to a polygon.

    Matches KiCad's TransformCircleToPolygon().

    Args:
        center: Circle center (x, y) in mm
        radius: Circle radius in mm
        error: Maximum approximation error in mm
        min_segments: Minimum number of segments

    Returns:
        List of (x, y) points forming a closed polygon
    """
    if radius <= 0:
        return []

    num_segs = get_arc_segment_count(radius, error, 360.0)
    num_segs = max(min_segments, num_segs)

    # Round up to multiple of 8 for proper 45-degree alignment
    num_segs = ((num_segs + 7) // 8) * 8

    points = []
    delta = 2.0 * math.pi / num_segs

    # Start at delta/2 offset like KiCad
    for i in range(num_segs):
        angle = delta / 2 + i * delta
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        points.append((x, y))

    return points


def oval_to_polygon(
    start: Point,
    end: Point,
    width: float,
    error: float = DEFAULT_ERROR_MM,
    min_segments: int = MIN_SEGCOUNT_FOR_CIRCLE
) -> Contour:
    """
    Convert an oval (capsule/stadium) shape to a polygon.

    This creates a track-like shape with semicircular ends.
    Matches KiCad's TransformOvalToPolygon().

    Args:
        start: Start point (x, y) in mm
        end: End point (x, y) in mm
        width: Total width of the oval in mm
        error: Maximum approximation error in mm
        min_segments: Minimum segments for semicircles

    Returns:
        List of (x, y) points forming a closed polygon
    """
    if width <= 0:
        return []

    radius = width / 2.0
    num_segs = get_arc_segment_count(radius, error, 360.0)
    num_segs = max(min_segments, num_segs)
    num_segs = ((num_segs + 7) // 8) * 8

    # Half segments for each semicircle
    half_segs = num_segs // 2
    delta = math.pi / half_segs

    # Calculate direction vector
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    seg_len = math.sqrt(dx * dx + dy * dy)

    if seg_len < 1e-10:
        # Zero-length segment becomes a circle
        return circle_to_polygon(start, radius, error, min_segments)

    # Unit direction vector
    ux = dx / seg_len
    uy = dy / seg_len

    # Perpendicular vector
    px = -uy
    py = ux

    points = []

    # Right semicircle (around end point)
    # Start at the "top" relative to direction
    for i in range(half_segs + 1):
        angle = -math.pi / 2 + i * delta
        # Point relative to direction
        rx = math.cos(angle)
        ry = math.sin(angle)
        # Transform to world coordinates
        x = end[0] + radius * (rx * ux + ry * px)
        y = end[1] + radius * (rx * uy + ry * py)
        points.append((x, y))

    # Left semicircle (around start point)
    for i in range(half_segs + 1):
        angle = math.pi / 2 + i * delta
        rx = math.cos(angle)
        ry = math.sin(angle)
        x = start[0] + radius * (rx * ux + ry * px)
        y = start[1] + radius * (rx * uy + ry * py)
        points.append((x, y))

    return points


def arc_to_polygon(
    start: Point,
    mid: Point,
    end: Point,
    width: float,
    error: float = DEFAULT_ERROR_MM
) -> Contour:
    """
    Convert an arc with width to a polygon.

    Matches KiCad's TransformArcToPolygon().

    Args:
        start: Arc start point
        mid: Arc midpoint
        end: Arc end point
        width: Arc stroke width in mm
        error: Maximum approximation error in mm

    Returns:
        List of (x, y) points forming a closed polygon
    """
    # Calculate arc center and radius from three points
    center, radius = _calc_arc_center(start, mid, end)

    if center is None or radius <= 0:
        # Degenerate arc - treat as line
        return oval_to_polygon(start, end, width, error)

    # Calculate start and end angles
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    mid_angle = math.atan2(mid[1] - center[1], mid[0] - center[0])
    end_angle = math.atan2(end[1] - center[1], end[0] - center[0])

    # Determine arc direction (clockwise or counter-clockwise)
    # by checking if mid is on the shorter path from start to end
    arc_angle = _normalize_angle(end_angle - start_angle)
    mid_offset = _normalize_angle(mid_angle - start_angle)

    if arc_angle >= 0:
        # Counter-clockwise
        if mid_offset < 0 or mid_offset > arc_angle:
            arc_angle = arc_angle - 2 * math.pi
    else:
        # Clockwise
        if mid_offset > 0 or mid_offset < arc_angle:
            arc_angle = arc_angle + 2 * math.pi

    half_width = width / 2.0
    outer_radius = radius + half_width
    inner_radius = radius - half_width

    arc_len_deg = abs(math.degrees(arc_angle))
    num_segs = get_arc_segment_count(outer_radius, error, arc_len_deg)
    num_segs = max(8, num_segs)

    delta = arc_angle / num_segs

    points = []

    # Outer arc
    for i in range(num_segs + 1):
        angle = start_angle + i * delta
        x = center[0] + outer_radius * math.cos(angle)
        y = center[1] + outer_radius * math.sin(angle)
        points.append((x, y))

    # End cap (semicircle)
    end_cap_center = (
        center[0] + radius * math.cos(end_angle),
        center[1] + radius * math.sin(end_angle)
    )
    cap_segs = max(4, num_segs // 4)
    cap_delta = math.pi / cap_segs
    cap_start = end_angle + (math.pi / 2 if arc_angle >= 0 else -math.pi / 2)

    for i in range(1, cap_segs):
        if arc_angle >= 0:
            angle = cap_start - i * cap_delta
        else:
            angle = cap_start + i * cap_delta
        x = end_cap_center[0] + half_width * math.cos(angle)
        y = end_cap_center[1] + half_width * math.sin(angle)
        points.append((x, y))

    # Inner arc (reverse direction)
    if inner_radius > 0:
        for i in range(num_segs + 1):
            angle = start_angle + arc_angle - i * delta
            x = center[0] + inner_radius * math.cos(angle)
            y = center[1] + inner_radius * math.sin(angle)
            points.append((x, y))
    else:
        # Inner radius is zero or negative - just add center point
        points.append(center)

    # Start cap (semicircle)
    start_cap_center = (
        center[0] + radius * math.cos(start_angle),
        center[1] + radius * math.sin(start_angle)
    )
    cap_start = start_angle + (-math.pi / 2 if arc_angle >= 0 else math.pi / 2)

    for i in range(1, cap_segs):
        if arc_angle >= 0:
            angle = cap_start - i * cap_delta
        else:
            angle = cap_start + i * cap_delta
        x = start_cap_center[0] + half_width * math.cos(angle)
        y = start_cap_center[1] + half_width * math.sin(angle)
        points.append((x, y))

    # Normalize winding direction to CCW for consistent rendering with nonzero fill-rule
    # Compute signed area using shoelace formula
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += (x2 - x1) * (y2 + y1)

    # If area is negative, polygon is CW - reverse to make CCW
    if area < 0:
        points = list(reversed(points))

    return points


def ring_to_polygon(
    center: Point,
    radius: float,
    width: float,
    error: float = DEFAULT_ERROR_MM
) -> PolygonSet:
    """
    Convert a ring (unfilled circle with stroke) to polygons.

    Matches KiCad's TransformRingToPolygon().

    Args:
        center: Ring center
        radius: Ring center radius
        width: Ring stroke width
        error: Maximum approximation error

    Returns:
        PolygonSet with outer circle and inner hole
    """
    inner_radius = radius - width / 2.0
    outer_radius = radius + width / 2.0

    if inner_radius <= 0:
        # Solid circle
        outer = circle_to_polygon(center, outer_radius, error)
        return PolygonSet(outlines=[outer])

    outer = circle_to_polygon(center, outer_radius, error)
    inner = circle_to_polygon(center, inner_radius, error)

    # Reverse inner circle to give it opposite winding direction
    # This is needed for nonzero fill-rule to create a hole
    inner_reversed = list(reversed(inner))

    return PolygonSet(outlines=[outer], holes=[inner_reversed])


def rect_to_polygon(
    start: Point,
    end: Point,
    width: float = 0.0,
    corner_radius: float = 0.0,
    error: float = DEFAULT_ERROR_MM
) -> Contour:
    """
    Convert a rectangle to a polygon.

    Args:
        start: One corner of rectangle
        end: Opposite corner of rectangle
        width: Stroke width (0 for filled rectangle uses corners directly)
        corner_radius: Radius for rounded corners (0 for sharp corners)
        error: Maximum approximation error for rounded corners

    Returns:
        List of (x, y) points forming a closed polygon
    """
    x1, y1 = min(start[0], end[0]), min(start[1], end[1])
    x2, y2 = max(start[0], end[0]), max(start[1], end[1])

    if corner_radius <= 0:
        # Simple rectangle
        if width <= 0:
            return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        else:
            # Expand by half width
            hw = width / 2.0
            return [(x1 - hw, y1 - hw), (x2 + hw, y1 - hw),
                    (x2 + hw, y2 + hw), (x1 - hw, y2 + hw)]

    # Rounded rectangle
    r = min(corner_radius, (x2 - x1) / 2, (y2 - y1) / 2)

    # Calculate number of segments for corner arcs
    num_segs = get_arc_segment_count(r, error, 90.0)
    num_segs = max(2, num_segs)

    points = []

    # Top-right corner
    cx, cy = x2 - r, y1 + r
    for i in range(num_segs + 1):
        angle = -math.pi / 2 + i * (math.pi / 2) / num_segs
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    # Bottom-right corner
    cx, cy = x2 - r, y2 - r
    for i in range(num_segs + 1):
        angle = 0 + i * (math.pi / 2) / num_segs
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    # Bottom-left corner
    cx, cy = x1 + r, y2 - r
    for i in range(num_segs + 1):
        angle = math.pi / 2 + i * (math.pi / 2) / num_segs
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    # Top-left corner
    cx, cy = x1 + r, y1 + r
    for i in range(num_segs + 1):
        angle = math.pi + i * (math.pi / 2) / num_segs
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    return points


def bezier_to_polyline(
    p0: Point, p1: Point, p2: Point, p3: Point,
    error: float = DEFAULT_ERROR_MM
) -> List[Point]:
    """
    Convert a cubic bezier curve to a polyline.

    Uses recursive subdivision until segments are within error tolerance.

    Args:
        p0, p1, p2, p3: Control points
        error: Maximum deviation from true curve

    Returns:
        List of points approximating the bezier curve
    """
    points = [p0]
    _subdivide_bezier(p0, p1, p2, p3, error * error, points)
    points.append(p3)
    return points


def _subdivide_bezier(
    p0: Point, p1: Point, p2: Point, p3: Point,
    error_sq: float,
    points: List[Point]
) -> None:
    """Recursively subdivide bezier curve."""
    # Check if curve is flat enough
    # Use distance from control points to line p0-p3
    dx = p3[0] - p0[0]
    dy = p3[1] - p0[1]
    len_sq = dx * dx + dy * dy

    if len_sq < 1e-10:
        return

    # Distance from p1 to line
    d1 = abs((p1[0] - p0[0]) * dy - (p1[1] - p0[1]) * dx)
    d2 = abs((p2[0] - p0[0]) * dy - (p2[1] - p0[1]) * dx)

    max_d_sq = max(d1 * d1, d2 * d2) / len_sq

    if max_d_sq <= error_sq:
        return

    # Subdivide
    m01 = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    m12 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    m23 = ((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)

    m012 = ((m01[0] + m12[0]) / 2, (m01[1] + m12[1]) / 2)
    m123 = ((m12[0] + m23[0]) / 2, (m12[1] + m23[1]) / 2)

    mid = ((m012[0] + m123[0]) / 2, (m012[1] + m123[1]) / 2)

    _subdivide_bezier(p0, m01, m012, mid, error_sq, points)
    points.append(mid)
    _subdivide_bezier(mid, m123, m23, p3, error_sq, points)


def bezier_to_polygon(
    p0: Point, p1: Point, p2: Point, p3: Point,
    width: float,
    error: float = DEFAULT_ERROR_MM
) -> Contour:
    """
    Convert a bezier curve with width to a polygon.

    First converts bezier to polyline, then creates capsules for each segment.

    Args:
        p0, p1, p2, p3: Control points
        width: Stroke width
        error: Maximum approximation error

    Returns:
        Combined polygon outline
    """
    polyline = bezier_to_polyline(p0, p1, p2, p3, error)

    if len(polyline) < 2:
        return []

    # For simplicity, just create ovals for each segment and union them
    # A more sophisticated approach would use offsetting
    all_points = []

    for i in range(len(polyline) - 1):
        oval = oval_to_polygon(polyline[i], polyline[i + 1], width, error)
        all_points.extend(oval)

    # Note: This is a simplification. For proper rendering, we should
    # use polygon boolean union. For now, return first segment only
    # as the full solution requires pyclipper or similar.
    if len(polyline) >= 2:
        return oval_to_polygon(polyline[0], polyline[-1], width, error)

    return all_points


# =============================================================================
# Helper Functions
# =============================================================================

def _calc_arc_center(
    start: Point, mid: Point, end: Point
) -> Tuple[Optional[Point], float]:
    """
    Calculate arc center and radius from three points.

    Returns:
        Tuple of (center, radius) or (None, 0) if points are collinear
    """
    # Use perpendicular bisector method
    ax, ay = start
    bx, by = mid
    cx, cy = end

    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))

    if abs(d) < 1e-10:
        return None, 0.0

    ux = ((ax * ax + ay * ay) * (by - cy) +
          (bx * bx + by * by) * (cy - ay) +
          (cx * cx + cy * cy) * (ay - by)) / d

    uy = ((ax * ax + ay * ay) * (cx - bx) +
          (bx * bx + by * by) * (ax - cx) +
          (cx * cx + cy * cy) * (bx - ax)) / d

    radius = math.sqrt((ax - ux) ** 2 + (ay - uy) ** 2)

    return (ux, uy), radius


def _normalize_angle(angle: float) -> float:
    """Normalize angle to [-pi, pi] range."""
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle
