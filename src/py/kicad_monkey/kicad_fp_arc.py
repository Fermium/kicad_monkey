"""
KiCad Footprint Arc Element

REQ-KICAD-070: One class per file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from .kicad_sexpr import QuotedString

if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext
    from .kicad_pcb_polygon_ops import PolygonSet
from .kicad_base import (
    FRONT_SILKSCREEN_LAYER,
    find_element,
    get_value,
    unquote_string,
)
from .kicad_primitives import Stroke


@dataclass
class FpArc:
    """Footprint arc element."""
    start_x: float
    start_y: float
    mid_x: float
    mid_y: float
    end_x: float
    end_y: float
    layer: str = FRONT_SILKSCREEN_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'FpArc':
        start = find_element(sexp, 'start')
        mid = find_element(sexp, 'mid')
        end = find_element(sexp, 'end')

        return cls(
            start_x=float(start[1]) if start else 0.0,
            start_y=float(start[2]) if start else 0.0,
            mid_x=float(mid[1]) if mid else 0.0,
            mid_y=float(mid[2]) if mid else 0.0,
            end_x=float(end[1]) if end else 0.0,
            end_y=float(end[2]) if end else 0.0,
            layer=unquote_string(get_value(sexp, 'layer', FRONT_SILKSCREEN_LAYER)),
            stroke=Stroke.from_sexp(sexp),
            uuid=unquote_string(get_value(sexp, 'uuid')),
            _raw_sexp=sexp
        )

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this arc. REQ-KICAD-071."""
        from .kicad_geometry import BoundingBox

        width = self.stroke.width if self.stroke else 0.12
        hw = width / 2

        # Conservative: use all three points
        bbox = BoundingBox()
        for x, y in [(self.start_x, self.start_y), (self.mid_x, self.mid_y), (self.end_x, self.end_y)]:
            bbox.expand((x - hw, y - hw))
            bbox.expand((x + hw, y + hw))

        return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> List[str]:
        """Render this arc to SVG elements. REQ-KICAD-072."""
        from .kicad_geometry import SvgRenderContext
        import math

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        width = self.stroke.width if self.stroke else 0.12

        # Calculate arc parameters from 3 points
        sx = self.start_x + ctx.offset_x
        sy = self.start_y + ctx.offset_y
        mx = self.mid_x + ctx.offset_x
        my = self.mid_y + ctx.offset_y
        ex = self.end_x + ctx.offset_x
        ey = self.end_y + ctx.offset_y

        # Calculate center and radius from 3 points
        # Using circumcircle formula
        d = 2 * (sx * (my - ey) + mx * (ey - sy) + ex * (sy - my))
        if abs(d) < 1e-10:
            # Points are collinear, draw line
            return [
                f'<path d="M{ctx.fmt(sx)} {ctx.fmt(sy)} L{ctx.fmt(ex)} {ctx.fmt(ey)}" '
                f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
                f'stroke-linecap:round; stroke-linejoin:round;" />'
            ]

        ux = ((sx*sx + sy*sy) * (my - ey) + (mx*mx + my*my) * (ey - sy) + (ex*ex + ey*ey) * (sy - my)) / d
        uy = ((sx*sx + sy*sy) * (ex - mx) + (mx*mx + my*my) * (sx - ex) + (ex*ex + ey*ey) * (mx - sx)) / d
        r = math.sqrt((sx - ux)**2 + (sy - uy)**2)

        # Determine arc direction (large-arc and sweep flags)
        # Cross product to determine direction
        cross = (mx - sx) * (ey - sy) - (my - sy) * (ex - sx)
        sweep = 1 if cross > 0 else 0

        # Calculate arc angles to determine large arc flag
        start_angle = math.atan2(sy - uy, sx - ux)
        end_angle = math.atan2(ey - uy, ex - ux)
        mid_angle = math.atan2(my - uy, mx - ux)

        # Normalize angles
        def normalize(a: float) -> float:
            while a < 0:
                a += 2 * math.pi
            while a >= 2 * math.pi:
                a -= 2 * math.pi
            return a

        start_angle = normalize(start_angle)
        end_angle = normalize(end_angle)
        mid_angle = normalize(mid_angle)

        # Check if mid is between start and end
        if sweep == 1:
            if start_angle < end_angle:
                mid_between = start_angle <= mid_angle <= end_angle
            else:
                mid_between = mid_angle >= start_angle or mid_angle <= end_angle
        else:
            if start_angle > end_angle:
                mid_between = end_angle <= mid_angle <= start_angle
            else:
                mid_between = mid_angle <= start_angle or mid_angle >= end_angle

        large_arc = 0 if mid_between else 1

        return [
            f'<path d="M{ctx.fmt(sx)} {ctx.fmt(sy)} '
            f'A{ctx.fmt(r)} {ctx.fmt(r)} 0 {large_arc} {sweep} {ctx.fmt(ex)} {ctx.fmt(ey)}" '
            f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
            f'stroke-linecap:round; stroke-linejoin:round;" />'
        ]

    def to_sexp(self) -> list:
        result = ['fp_arc',
                  ['start', self.start_x, self.start_y],
                  ['mid', self.mid_x, self.mid_y],
                  ['end', self.end_x, self.end_y],
                  self.stroke.to_sexp(),
                  ['layer', QuotedString(self.layer)]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    def _to_poly(self, error: float = 0.005) -> 'PolygonSet':
        """Convert arc to polygon with stroke width."""
        from .kicad_pcb_polygon_ops import PolygonSet, arc_to_polygon

        width = self.stroke.width
        if width <= 0:
            return PolygonSet()

        start = (self.start_x, self.start_y)
        mid = (self.mid_x, self.mid_y)
        end = (self.end_x, self.end_y)

        contour = arc_to_polygon(start, mid, end, width, error)
        return PolygonSet(outlines=[contour])
