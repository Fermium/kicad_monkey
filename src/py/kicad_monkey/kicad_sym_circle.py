"""
Circle graphic element in a symbol.
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
class SymCircle:
    """Circle graphic element in a symbol.

    Defined by center point and radius.
    """
    center_x: float
    center_y: float
    radius: float
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SymCircle':
        """Parse from (circle (center X Y) (radius R) ...)."""
        center_elem = find_element(sexp, 'center')
        radius_val = get_value(sexp, 'radius', 0.0)

        center_x = float(center_elem[1]) if center_elem and len(center_elem) > 1 else 0.0
        center_y = float(center_elem[2]) if center_elem and len(center_elem) > 2 else 0.0
        radius = float(radius_val)

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid')) if get_value(sexp, 'uuid') else None

        return cls(
            center_x=center_x, center_y=center_y,
            radius=radius,
            stroke=stroke, fill=fill, uuid=uuid,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result: SexpList = ['circle']
        result.append(['center', self.center_x, self.center_y])
        result.append(['radius', self.radius])
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())
        if self.uuid:
            result.append(['uuid', self.uuid])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of the circle."""
        from .kicad_geometry import BoundingBox
        bbox = BoundingBox()
        bbox.expand((self.center_x - self.radius, self.center_y - self.radius))
        bbox.expand((self.center_x + self.radius, self.center_y + self.radius))
        return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> list[str]:
        """Render circle to SVG element."""
        from .kicad_geometry import SvgRenderContext
        if ctx is None:
            ctx = SvgRenderContext()

        fill = "none" if self.fill.type == SymFillType.NONE else ctx.fill
        stroke_width = self.stroke.width if self.stroke.width > 0 else 0.1

        return [f'<circle cx="{ctx.fmt(self.center_x)}" cy="{ctx.fmt(self.center_y)}" '
                f'r="{ctx.fmt(self.radius)}" fill="{fill}" stroke="{ctx.stroke}" '
                f'stroke-width="{stroke_width}"/>']


__all__ = ['SymCircle']
