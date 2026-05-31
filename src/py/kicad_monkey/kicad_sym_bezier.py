"""
Bezier curve graphic element in a symbol.
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
class SymBezier:
    """Bezier curve graphic element in a symbol.

    KiCad beziers are defined by a list of control points.
    Typically 4 points for a cubic bezier.
    """
    points: List[Tuple[float, float]] = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SymBezier':
        """Parse from (bezier (pts (xy X Y) ...) ...)."""
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
        result: SexpList = ['bezier']
        pts = ['pts'] + [['xy', p[0], p[1]] for p in self.points]
        result.append(pts)
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())
        if self.uuid:
            result.append(['uuid', self.uuid])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of the bezier (approximation using control points)."""
        from .kicad_geometry import BoundingBox
        bbox = BoundingBox()
        for x, y in self.points:
            bbox.expand((x, y))
        return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> list[str]:
        """Render bezier to SVG path element."""
        from .kicad_geometry import SvgRenderContext
        if ctx is None:
            ctx = SvgRenderContext()

        if len(self.points) < 2:
            return []

        fill = "none" if self.fill.type == SymFillType.NONE else ctx.fill
        stroke_width = self.stroke.width if self.stroke.width > 0 else 0.1

        # Build SVG path
        p0 = self.points[0]
        d = f"M {ctx.fmt(p0[0])} {ctx.fmt(p0[1])}"

        if len(self.points) == 4:
            # Cubic bezier
            p1, p2, p3 = self.points[1], self.points[2], self.points[3]
            d += f" C {ctx.fmt(p1[0])} {ctx.fmt(p1[1])}, "
            d += f"{ctx.fmt(p2[0])} {ctx.fmt(p2[1])}, "
            d += f"{ctx.fmt(p3[0])} {ctx.fmt(p3[1])}"
        elif len(self.points) == 3:
            # Quadratic bezier
            p1, p2 = self.points[1], self.points[2]
            d += f" Q {ctx.fmt(p1[0])} {ctx.fmt(p1[1])}, "
            d += f"{ctx.fmt(p2[0])} {ctx.fmt(p2[1])}"
        else:
            # Fallback to line segments
            for px, py in self.points[1:]:
                d += f" L {ctx.fmt(px)} {ctx.fmt(py)}"

        return [f'<path d="{d}" fill="{fill}" stroke="{ctx.stroke}" '
                f'stroke-width="{stroke_width}"/>']


__all__ = ['SymBezier']
