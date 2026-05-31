"""
KiCad Footprint Circle Element

One class per file.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from .kicad_sexpr import QuotedString

if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext
    from .kicad_pcb_polygon_ops import PolygonSet
from .kicad_base import (
    FillType,
    FRONT_SILKSCREEN_LAYER,
    find_element,
    get_value,
    unquote_string,
)
from .kicad_primitives import Stroke


@dataclass
class FpCircle:
    """Footprint circle element."""
    center_x: float
    center_y: float
    end_x: float
    end_y: float
    layer: str = FRONT_SILKSCREEN_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    fill: FillType = FillType.NO
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'FpCircle':
        center = find_element(sexp, 'center')
        end = find_element(sexp, 'end')

        # Parse fill
        fill_val = get_value(sexp, 'fill', 'no')
        try:
            fill = FillType(fill_val) if isinstance(fill_val, str) else FillType.NO
        except ValueError:
            fill = FillType.NO

        return cls(
            center_x=float(center[1]) if center else 0.0,
            center_y=float(center[2]) if center else 0.0,
            end_x=float(end[1]) if end else 0.0,
            end_y=float(end[2]) if end else 0.0,
            layer=unquote_string(get_value(sexp, 'layer', FRONT_SILKSCREEN_LAYER)),
            stroke=Stroke.from_sexp(sexp),
            fill=fill,
            uuid=unquote_string(get_value(sexp, 'uuid')),
            _raw_sexp=sexp
        )

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this circle.."""
        from .kicad_geometry import BoundingBox

        width = self.stroke.width if self.stroke else 0.12
        hw = width / 2
        r = self.radius

        return BoundingBox(
            min_x=self.center_x - r - hw,
            min_y=self.center_y - r - hw,
            max_x=self.center_x + r + hw,
            max_y=self.center_y + r + hw
        )

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> List[str]:
        """Render this circle to SVG elements.."""
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        cx = self.center_x + ctx.offset_x
        cy = self.center_y + ctx.offset_y
        r = self.radius
        width = self.stroke.width if self.stroke else 0.12

        if self.is_filled:
            return [
                f'<circle cx="{ctx.fmt(cx)}" cy="{ctx.fmt(cy)}" r="{ctx.fmt(r)}" '
                f'style="fill:{ctx.fill}; fill-opacity:1.0; stroke:none;" />'
            ]
        else:
            return [
                f'<circle cx="{ctx.fmt(cx)}" cy="{ctx.fmt(cy)}" r="{ctx.fmt(r)}" '
                f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)};" />'
            ]

    def to_sexp(self) -> list:
        result = ['fp_circle',
                  ['center', self.center_x, self.center_y],
                  ['end', self.end_x, self.end_y],
                  self.stroke.to_sexp(),
                  ['fill', self.fill.value],
                  ['layer', QuotedString(self.layer)]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    @property
    def radius(self) -> float:
        """Calculate radius from center to end point."""
        dx = self.end_x - self.center_x
        dy = self.end_y - self.center_y
        return math.sqrt(dx * dx + dy * dy)

    @property
    def is_filled(self) -> bool:
        """Check if circle is filled."""
        return self.fill in (FillType.SOLID, FillType.YES)

    def _to_poly(self, error: float = 0.005) -> 'PolygonSet':
        """Convert circle to polygon."""
        from .kicad_pcb_polygon_ops import PolygonSet, circle_to_polygon, ring_to_polygon

        r = self.radius
        w = self.stroke.width
        center = (self.center_x, self.center_y)

        if self.is_filled:
            outer_radius = r + w / 2 if w > 0 else r
            contour = circle_to_polygon(center, outer_radius, error)
            return PolygonSet(outlines=[contour])
        else:
            if w <= 0:
                contour = circle_to_polygon(center, r, error)
                return PolygonSet(outlines=[contour])
            return ring_to_polygon(center, r, w, error)
