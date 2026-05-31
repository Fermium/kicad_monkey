"""
KiCad Footprint Line Element

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
class FpLine:
    """Footprint line element."""
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    layer: str = FRONT_SILKSCREEN_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'FpLine':
        start = find_element(sexp, 'start')
        end = find_element(sexp, 'end')

        return cls(
            start_x=float(start[1]) if start else 0.0,
            start_y=float(start[2]) if start else 0.0,
            end_x=float(end[1]) if end else 0.0,
            end_y=float(end[2]) if end else 0.0,
            layer=unquote_string(get_value(sexp, 'layer', FRONT_SILKSCREEN_LAYER)),
            stroke=Stroke.from_sexp(sexp),
            uuid=unquote_string(get_value(sexp, 'uuid')),
            _raw_sexp=sexp
        )

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this line. REQ-KICAD-071."""
        from .kicad_geometry import BoundingBox

        width = self.stroke.width if self.stroke else 0.12
        hw = width / 2

        return BoundingBox(
            min_x=min(self.start_x, self.end_x) - hw,
            min_y=min(self.start_y, self.end_y) - hw,
            max_x=max(self.start_x, self.end_x) + hw,
            max_y=max(self.start_y, self.end_y) + hw
        )

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> List[str]:
        """Render this line to SVG elements. REQ-KICAD-072."""
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        sx = self.start_x + ctx.offset_x
        sy = self.start_y + ctx.offset_y
        ex = self.end_x + ctx.offset_x
        ey = self.end_y + ctx.offset_y
        width = self.stroke.width if self.stroke else 0.12

        return [
            f'<path d="M{ctx.fmt(sx)} {ctx.fmt(sy)} L{ctx.fmt(ex)} {ctx.fmt(ey)}" '
            f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
            f'stroke-linecap:round; stroke-linejoin:round;" />'
        ]

    def to_sexp(self) -> list:
        result = ['fp_line',
                  ['start', self.start_x, self.start_y],
                  ['end', self.end_x, self.end_y],
                  self.stroke.to_sexp(),
                  ['layer', QuotedString(self.layer)]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    def _to_poly(self, error: float = 0.005) -> 'PolygonSet':
        """
        Convert line to polygon (capsule/stadium shape).

        The line is converted to an oval shape with semicircular ends.
        Uses local (footprint) coordinates.
        """
        from .kicad_pcb_polygon_ops import PolygonSet, oval_to_polygon

        width = self.stroke.width
        if width <= 0:
            # Zero-width line - no polygon
            return PolygonSet()

        start = (self.start_x, self.start_y)
        end = (self.end_x, self.end_y)

        contour = oval_to_polygon(start, end, width, error)
        return PolygonSet(outlines=[contour])
