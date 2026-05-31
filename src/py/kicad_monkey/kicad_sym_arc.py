"""
Arc graphic element in a symbol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .kicad_base import find_element, get_value, unquote_string
from .kicad_primitives import Stroke
from .kicad_sym_rectangle import SymFill, SymFillType
from .kicad_sexpr import SexpList


if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext


@dataclass
class SymArc:
    """Arc graphic element in a symbol.

    KiCad arcs are defined by start, mid, and end points.
    The mid point defines the arc's curvature direction.
    """
    start_x: float
    start_y: float
    mid_x: float
    mid_y: float
    end_x: float
    end_y: float
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SymArc':
        """Parse from (arc (start X Y) (mid X Y) (end X Y) ...)."""
        start_elem = find_element(sexp, 'start')
        mid_elem = find_element(sexp, 'mid')
        end_elem = find_element(sexp, 'end')

        start_x = float(start_elem[1]) if start_elem and len(start_elem) > 1 else 0.0
        start_y = float(start_elem[2]) if start_elem and len(start_elem) > 2 else 0.0
        mid_x = float(mid_elem[1]) if mid_elem and len(mid_elem) > 1 else 0.0
        mid_y = float(mid_elem[2]) if mid_elem and len(mid_elem) > 2 else 0.0
        end_x = float(end_elem[1]) if end_elem and len(end_elem) > 1 else 0.0
        end_y = float(end_elem[2]) if end_elem and len(end_elem) > 2 else 0.0

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid')) if get_value(sexp, 'uuid') else None

        return cls(
            start_x=start_x, start_y=start_y,
            mid_x=mid_x, mid_y=mid_y,
            end_x=end_x, end_y=end_y,
            stroke=stroke, fill=fill, uuid=uuid,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result: SexpList = ['arc']
        result.append(['start', self.start_x, self.start_y])
        result.append(['mid', self.mid_x, self.mid_y])
        result.append(['end', self.end_x, self.end_y])
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())
        if self.uuid:
            result.append(['uuid', self.uuid])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of the arc."""
        from .kicad_geometry import BoundingBox
        bbox = BoundingBox()
        bbox.expand((self.start_x, self.start_y))
        bbox.expand((self.mid_x, self.mid_y))
        bbox.expand((self.end_x, self.end_y))
        return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> list[str]:
        """Render arc to SVG path element."""
        from .kicad_geometry import SvgRenderContext
        if ctx is None:
            ctx = SvgRenderContext()

        # Calculate arc parameters from three points
        # This is a simplified version - full implementation would calculate center/radius
        fill = "none" if self.fill.type == SymFillType.NONE else ctx.fill
        stroke_width = self.stroke.width if self.stroke.width > 0 else 0.1

        # Use quadratic bezier as approximation through mid point
        d = (f"M {ctx.fmt(self.start_x)} {ctx.fmt(self.start_y)} "
             f"Q {ctx.fmt(self.mid_x)} {ctx.fmt(self.mid_y)} "
             f"{ctx.fmt(self.end_x)} {ctx.fmt(self.end_y)}")

        return [f'<path d="{d}" fill="{fill}" stroke="{ctx.stroke}" '
                f'stroke-width="{stroke_width}"/>']


__all__ = ['SymArc']
