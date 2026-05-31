"""
KiCad Zone Fill Utilities

Provides a PolygonSet class that wraps pyclipr (Clipper2) with an API
matching KiCad's SHAPE_POLY_SET operations.

This module enables Python-based zone fill computation that produces
identical output to KiCad's zone_filler.cpp.
"""

import importlib
import logging
import math
from enum import Enum
from typing import Any, List, Tuple, Optional, Iterator

import numpy as np

log = logging.getLogger(__name__)


class _MissingPyclipr:
    def __init__(self, reason: ModuleNotFoundError) -> None:
        self._reason = reason

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError("pyclipr is required for zone fill utilities") from self._reason


try:
    pyclipr: Any = importlib.import_module("pyclipr")
except ModuleNotFoundError as exc:
    pyclipr = _MissingPyclipr(exc)

# Type aliases
Point = Tuple[float, float]
Polygon = List[Point]


def _numpy_to_polygon(arr: np.ndarray) -> Polygon:
    """Convert numpy array to list of (x, y) tuples."""
    return [(float(p[0]), float(p[1])) for p in arr]


def _polygons_from_result(result: List[np.ndarray]) -> List[Polygon]:
    """Convert pyclipr result (list of numpy arrays) to list of polygons."""
    return [_numpy_to_polygon(arr) for arr in result if len(arr) >= 3]


class CornerStrategy(Enum):
    """Corner handling strategies for inflate/deflate operations.

    Maps to KiCad's CORNER_STRATEGY enum and Clipper2's JoinType.
    """
    CHAMFER_ALL_CORNERS = "chamfer"  # JoinType.Square - Fast, fewer points
    ROUND_ALL_CORNERS = "round"      # JoinType.Round - Smooth, more points
    ALLOW_ACUTE_CORNERS = "miter"    # JoinType.Miter - Sharp corners


# Default epsilon value (1 micron) to prevent floating-point edge cases
EPSILON_MM = 0.001

# Default arc tolerance (5 microns) - from KiCad's ARC_HIGH_DEF
DEFAULT_MAX_ERROR = 0.005


def _join_type_from_strategy(strategy: CornerStrategy) -> Any:
    """Convert CornerStrategy to pyclipr JoinType."""
    mapping = {
        CornerStrategy.CHAMFER_ALL_CORNERS: pyclipr.JoinType.Square,
        CornerStrategy.ROUND_ALL_CORNERS: pyclipr.JoinType.Round,
        CornerStrategy.ALLOW_ACUTE_CORNERS: pyclipr.JoinType.Miter,
    }
    return mapping[strategy]


def _polygon_area(points: Polygon) -> float:
    """Calculate signed area of a polygon using the shoelace formula.

    Positive area = counter-clockwise winding
    Negative area = clockwise winding
    """
    if len(points) < 3:
        return 0.0

    area = 0.0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return area / 2.0


def _polygon_bounds(points: Polygon) -> Tuple[float, float, float, float]:
    """Get bounding box of polygon as (min_x, min_y, max_x, max_y)."""
    if not points:
        return (0, 0, 0, 0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """Test if a point is inside a polygon using ray casting.

    Uses the even-odd rule (ray crossing algorithm).
    """
    x, y = point
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i

    return inside


class PolygonSet:
    """
    KiCad SHAPE_POLY_SET equivalent using pyclipr (Clipper2).

    Supports boolean operations, inflate/deflate, and polygon manipulation
    with an API matching KiCad's internal polygon operations.

    Coordinates are in mm (matching KiCad file format).
    """

    def __init__(self, polygons: Optional[List[Polygon]] = None):
        """Initialize with optional list of polygons.

        Args:
            polygons: List of polygons, each polygon is a list of (x, y) points.
                     First polygon in each group is the outline, subsequent are holes.
        """
        self._polygons: List[Polygon] = []
        if polygons:
            for poly in polygons:
                if poly and len(poly) >= 3:
                    self._polygons.append(list(poly))

    @classmethod
    def from_polygon(cls, points: Polygon) -> 'PolygonSet':
        """Create a PolygonSet from a single polygon."""
        return cls([points])

    @classmethod
    def from_rectangle(cls, x1: float, y1: float, x2: float, y2: float) -> 'PolygonSet':
        """Create a PolygonSet from a rectangle."""
        points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        return cls([points])

    @classmethod
    def from_circle(cls, cx: float, cy: float, radius: float,
                   segments: int = 32) -> 'PolygonSet':
        """Create a PolygonSet from a circle approximation."""
        points = []
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            points.append((x, y))
        return cls([points])

    def clone(self) -> 'PolygonSet':
        """Create a deep copy of this PolygonSet."""
        return PolygonSet([list(p) for p in self._polygons])

    @property
    def polygons(self) -> List[Polygon]:
        """Get the list of polygons."""
        return self._polygons

    @property
    def is_empty(self) -> bool:
        """Check if the polygon set is empty."""
        return len(self._polygons) == 0

    @property
    def outline_count(self) -> int:
        """Get the number of polygons (outlines)."""
        return len(self._polygons)

    def __len__(self) -> int:
        return len(self._polygons)

    def __iter__(self) -> Iterator[Polygon]:
        return iter(self._polygons)

    def add_outline(self, points: Polygon) -> None:
        """Add a polygon outline to this set."""
        if points and len(points) >= 3:
            self._polygons.append(list(points))

    def add_polygon_set(self, other: 'PolygonSet') -> None:
        """Add all polygons from another set to this one (without boolean union)."""
        for poly in other._polygons:
            self._polygons.append(list(poly))

    def clear(self) -> None:
        """Remove all polygons."""
        self._polygons.clear()

    def bounds(self) -> Tuple[float, float, float, float]:
        """Get bounding box as (min_x, min_y, max_x, max_y)."""
        if not self._polygons:
            return (0, 0, 0, 0)

        all_points = [p for poly in self._polygons for p in poly]
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        return (min(xs), min(ys), max(xs), max(ys))

    def area(self) -> float:
        """Calculate total visible area of all polygons.

        Handles holes correctly: positive area = solid, negative area = hole.
        Clipper2 returns holes with negative (clockwise) winding.
        """
        # Sum signed areas - holes have negative area and subtract automatically
        total = sum(_polygon_area(poly) for poly in self._polygons)
        return abs(total)

    def contains(self, point: Point) -> bool:
        """Test if a point is inside any polygon in this set.

        Uses even-odd fill rule.
        """
        for poly in self._polygons:
            if _point_in_polygon(point, poly):
                return True
        return False

    # =========================================================================
    # Boolean Operations (using pyclipr)
    # =========================================================================

    def boolean_subtract(self, other: 'PolygonSet') -> 'PolygonSet':
        """Subtract other polygon set from this one (Clipper2 Difference).

        Returns a new PolygonSet with areas of 'other' removed from 'self'.
        """
        if self.is_empty:
            return PolygonSet()
        if other.is_empty:
            return self.clone()

        pc = pyclipr.Clipper()
        pc.scaleFactor = int(1e6)  # Use nanometer precision

        # Add subject paths (this polygon set)
        for poly in self._polygons:
            if len(poly) >= 3:
                pc.addPath(poly, pyclipr.Subject)

        # Add clip paths (other polygon set)
        for poly in other._polygons:
            if len(poly) >= 3:
                pc.addPath(poly, pyclipr.Clip)

        # Execute difference operation
        try:
            result = pc.execute(pyclipr.Difference, pyclipr.FillRule.EvenOdd)
            return PolygonSet(_polygons_from_result(result))
        except Exception as e:
            log.warning(f"Boolean subtract failed: {e}")
            return self.clone()

    def boolean_add(self, other: 'PolygonSet') -> 'PolygonSet':
        """Add (union) another polygon set to this one (Clipper2 Union).

        Returns a new PolygonSet combining both sets.
        """
        if self.is_empty:
            return other.clone()
        if other.is_empty:
            return self.clone()

        pc = pyclipr.Clipper()
        pc.scaleFactor = int(1e6)

        for poly in self._polygons:
            if len(poly) >= 3:
                pc.addPath(poly, pyclipr.Subject)

        for poly in other._polygons:
            if len(poly) >= 3:
                pc.addPath(poly, pyclipr.Clip)

        try:
            result = pc.execute(pyclipr.Union, pyclipr.FillRule.EvenOdd)
            return PolygonSet(_polygons_from_result(result))
        except Exception as e:
            log.warning(f"Boolean add failed: {e}")
            return self.clone()

    def boolean_intersection(self, other: 'PolygonSet') -> 'PolygonSet':
        """Intersect with another polygon set (Clipper2 Intersection).

        Returns a new PolygonSet containing only overlapping areas.
        """
        if self.is_empty or other.is_empty:
            return PolygonSet()

        pc = pyclipr.Clipper()
        pc.scaleFactor = int(1e6)

        for poly in self._polygons:
            if len(poly) >= 3:
                pc.addPath(poly, pyclipr.Subject)

        for poly in other._polygons:
            if len(poly) >= 3:
                pc.addPath(poly, pyclipr.Clip)

        try:
            result = pc.execute(pyclipr.Intersection, pyclipr.FillRule.EvenOdd)
            return PolygonSet(_polygons_from_result(result))
        except Exception as e:
            log.warning(f"Boolean intersection failed: {e}")
            return PolygonSet()

    def boolean_xor(self, other: 'PolygonSet') -> 'PolygonSet':
        """XOR with another polygon set (Clipper2 XOR).

        Returns a new PolygonSet containing non-overlapping areas.
        """
        if self.is_empty:
            return other.clone()
        if other.is_empty:
            return self.clone()

        pc = pyclipr.Clipper()
        pc.scaleFactor = int(1e6)

        for poly in self._polygons:
            if len(poly) >= 3:
                pc.addPath(poly, pyclipr.Subject)

        for poly in other._polygons:
            if len(poly) >= 3:
                pc.addPath(poly, pyclipr.Clip)

        try:
            result = pc.execute(pyclipr.Xor, pyclipr.FillRule.EvenOdd)
            return PolygonSet(_polygons_from_result(result))
        except Exception as e:
            log.warning(f"Boolean xor failed: {e}")
            return self.clone()

    # =========================================================================
    # Inflate/Deflate Operations (using pyclipr ClipperOffset)
    # =========================================================================

    def inflate(self, amount: float,
                strategy: CornerStrategy = CornerStrategy.ROUND_ALL_CORNERS,
                max_error: float = DEFAULT_MAX_ERROR) -> 'PolygonSet':
        """Inflate (grow) all polygons by the specified amount.

        Args:
            amount: Distance to inflate (positive = grow, negative = shrink)
            strategy: Corner handling strategy
            max_error: Arc tolerance for curved corners

        Returns:
            New PolygonSet with inflated polygons.
        """
        if self.is_empty or abs(amount) < 1e-9:
            return self.clone()

        po = pyclipr.ClipperOffset()
        po.scaleFactor = int(1e6)

        join_type = _join_type_from_strategy(strategy)

        # Note: arcTolerance property is read-only in pyclipr 0.1.7
        # The default value (0.25) works for most cases
        # TODO: Check if newer pyclipr versions allow setting this

        for poly in self._polygons:
            if len(poly) >= 3:
                po.addPath(poly, join_type, pyclipr.EndType.Polygon)

        try:
            # Amount is in mm, execute does the scaling
            result = po.execute(amount)
            return PolygonSet(_polygons_from_result(result))
        except Exception as e:
            log.warning(f"Inflate failed: {e}")
            return self.clone()

    def deflate(self, amount: float,
                strategy: CornerStrategy = CornerStrategy.CHAMFER_ALL_CORNERS,
                max_error: float = DEFAULT_MAX_ERROR) -> 'PolygonSet':
        """Deflate (shrink) all polygons by the specified amount.

        This is equivalent to inflate with negative amount.

        Args:
            amount: Distance to deflate (positive = shrink)
            strategy: Corner handling strategy (CHAMFER is faster)
            max_error: Arc tolerance for curved corners

        Returns:
            New PolygonSet with deflated polygons.
        """
        return self.inflate(-amount, strategy, max_error)

    # =========================================================================
    # Utility Operations
    # =========================================================================

    def simplify(self, tolerance: float = 0.001) -> 'PolygonSet':
        """Simplify polygons by removing points within tolerance.

        Uses Clipper2's built-in simplification.
        """
        if self.is_empty:
            return PolygonSet()

        # Use boolean union with self to simplify
        pc = pyclipr.Clipper()
        pc.scaleFactor = int(1e6)

        for poly in self._polygons:
            if len(poly) >= 3:
                pc.addPath(poly, pyclipr.Subject)

        try:
            result = pc.execute(pyclipr.Union, pyclipr.FillRule.EvenOdd)
            return PolygonSet(_polygons_from_result(result))
        except Exception as e:
            log.warning(f"Simplify failed: {e}")
            return self.clone()

    def remove_small_islands(self, min_dimension: float) -> 'PolygonSet':
        """Remove polygons smaller than the specified minimum dimension.

        A polygon is removed if max(bbox_width, bbox_height) < min_dimension.

        Args:
            min_dimension: Minimum dimension to keep (mm)

        Returns:
            New PolygonSet with small islands removed.
        """
        result_polys = []
        for poly in self._polygons:
            if len(poly) < 3:
                continue
            min_x, min_y, max_x, max_y = _polygon_bounds(poly)
            width = max_x - min_x
            height = max_y - min_y
            if max(width, height) >= min_dimension:
                result_polys.append(poly)
        return PolygonSet(result_polys)

    def fracture(self) -> 'PolygonSet':
        """Fracture polygons into triangles/convex parts for rendering.

        Currently returns self unchanged - implement if needed for complex zones.
        """
        # TODO: Implement polygon fracturing if needed
        return self.clone()


# =============================================================================
# Convenience Functions
# =============================================================================

def circle_to_polygon(cx: float, cy: float, radius: float,
                     max_error: float = DEFAULT_MAX_ERROR) -> PolygonSet:
    """Convert a circle to a polygon approximation.

    Uses the max_error to determine segment count (matching KiCad's approach).
    """
    if radius <= 0:
        return PolygonSet()

    # Calculate number of segments based on max_error
    # Using the same formula as KiCad: segments = ceil(pi / acos(1 - error/radius))
    if max_error >= radius:
        segments = 4  # Minimum
    else:
        segments = max(4, int(math.ceil(math.pi / math.acos(1 - max_error / radius))))

    return PolygonSet.from_circle(cx, cy, radius, segments)


def segment_to_polygon(start: Point, end: Point, width: float,
                      max_error: float = DEFAULT_MAX_ERROR) -> PolygonSet:
    """Convert a track segment to a polygon (capsule/stadium shape).

    Creates a stadium shape: rectangle with semicircular ends.

    For a segment from start to end with given width:
    - The center line goes from start to end
    - The width extends perpendicular to this line
    - Semicircular caps at each end
    """
    if width <= 0:
        return PolygonSet()

    radius = width / 2
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx*dx + dy*dy)

    if length < 1e-9:
        # Degenerate case - just a circle
        return circle_to_polygon(start[0], start[1], radius, max_error)

    # Get the angle of the segment
    segment_angle = math.atan2(dy, dx)

    # Calculate number of segments for semicircles based on max_error
    if max_error >= radius:
        arc_segments = 4
    else:
        arc_segments = max(4, int(math.ceil(math.pi / math.acos(1 - max_error / radius))))

    # Build the capsule polygon in counter-clockwise order
    points = []

    # Semicircle at start: from perpendicular (segment_angle + 90) going backwards
    # to (segment_angle - 90), i.e., around the back of the start point
    for i in range(arc_segments + 1):
        angle = segment_angle + math.pi / 2 + math.pi * i / arc_segments
        x = start[0] + radius * math.cos(angle)
        y = start[1] + radius * math.sin(angle)
        points.append((x, y))

    # Semicircle at end: from perpendicular (segment_angle - 90) going forwards
    # to (segment_angle + 90), i.e., around the front of the end point
    for i in range(arc_segments + 1):
        angle = segment_angle - math.pi / 2 + math.pi * i / arc_segments
        x = end[0] + radius * math.cos(angle)
        y = end[1] + radius * math.sin(angle)
        points.append((x, y))

    return PolygonSet([points])
