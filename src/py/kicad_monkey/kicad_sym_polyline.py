"""
Polyline graphic element in a symbol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple

from .kicad_base import find_element, find_all_elements, get_value, unquote_string
from .kicad_primitives import Stroke
from .kicad_sym_rectangle import SymFill, SymFillType
from .kicad_sexpr import SexpList


if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext


@dataclass
class SymPolyline:
    """Polyline graphic element in a symbol.

    A series of connected line segments defined by a list of points.
    Can be filled to create a polygon.
    """
    points: List[Tuple[float, float]] = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SymPolyline':
        """Parse from (polyline (pts (xy X Y) (xy X Y) ...) ...)."""
        pts_elem = find_element(sexp, 'pts')
        points = []
        if pts_elem:
            for xy in find_all_elements(pts_elem, 'xy'):
                if len(xy) >= 3:
                    points.append((float(xy[1]), float(xy[2])))

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid')) if get_value(sexp, 'uuid') else None

        return cls(
            points=points,
            stroke=stroke, fill=fill, uuid=uuid,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result: SexpList = ['polyline']
        pts = ['pts'] + [['xy', p[0], p[1]] for p in self.points]
        result.append(pts)
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())
        if self.uuid:
            result.append(['uuid', self.uuid])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of the polyline."""
        from .kicad_geometry import BoundingBox
        bbox = BoundingBox()
        for x, y in self.points:
            bbox.expand((x, y))
        return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> list[str]:
        """Render polyline to SVG element."""
        from .kicad_geometry import SvgRenderContext
        if ctx is None:
            ctx = SvgRenderContext()

        if not self.points:
            return []

        fill = "none" if self.fill.type == SymFillType.NONE else ctx.fill
        stroke_width = self.stroke.width if self.stroke.width > 0 else 0.1

        # Build SVG polyline points string
        points_str = " ".join(f"{ctx.fmt(x)},{ctx.fmt(y)}" for x, y in self.points)

        if self.fill.type != SymFillType.NONE and len(self.points) >= 3:
            # Use polygon for filled shapes
            return [f'<polygon points="{points_str}" fill="{fill}" '
                    f'stroke="{ctx.stroke}" stroke-width="{stroke_width}"/>']
        else:
            return [f'<polyline points="{points_str}" fill="none" '
                    f'stroke="{ctx.stroke}" stroke-width="{stroke_width}"/>']


__all__ = ['SymPolyline']
