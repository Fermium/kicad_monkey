"""
Rectangle graphic element in a symbol.

Also contains SymFill class used by all symbol graphic elements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple

from .kicad_base import find_element, get_value, unquote_string
from .kicad_primitives import Stroke
from .kicad_sexpr import SexpList


if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext


class SymFillType(Enum):
    """Fill type for symbol graphics.

    Note: This differs from PCB FillType - symbol fills use 'background'
    instead of 'yes' for filled shapes.

    Schematic-level shapes / text_boxes accept the same (fill (type ...))
    syntax but with extra hatch variants per ``formatFill`` in
    ``eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr_common.cpp:33``.
    """
    NONE = "none"
    OUTLINE = "outline"
    BACKGROUND = "background"
    COLOR = "color"  # KiCad 9: explicit color fill
    HATCH = "hatch"
    REVERSE_HATCH = "reverse_hatch"
    CROSS_HATCH = "cross_hatch"


@dataclass
class SymFill:
    """Fill settings for symbol graphics."""
    type: SymFillType = SymFillType.NONE
    color: Optional[Tuple[int, int, int, float]] = None

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SymFill':
        """Parse fill from parent element containing (fill (type ...))."""
        fill_elem = find_element(sexp, 'fill')
        if not fill_elem:
            return cls()
        type_str = get_value(fill_elem, 'type', 'none')
        try:
            fill_type = SymFillType(type_str)
        except ValueError:
            fill_type = SymFillType.NONE

        # Parse color if present: (color R G B A)
        color = None
        color_elem = find_element(fill_elem, 'color')
        if color_elem and len(color_elem) >= 5:
            color = (int(color_elem[1]), int(color_elem[2]),
                     int(color_elem[3]), float(color_elem[4]))

        return cls(type=fill_type, color=color)

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result: SexpList = ['fill', ['type', self.type.value]]
        if self.color:
            result.append(['color', self.color[0], self.color[1],
                          self.color[2], self.color[3]])
        return result


@dataclass
class SymRectangle:
    """Rectangle graphic element in a symbol."""
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SymRectangle':
        """Parse from (rectangle (start X Y) (end X Y) (stroke ...) (fill ...))."""
        start_elem = find_element(sexp, 'start')
        end_elem = find_element(sexp, 'end')

        start_x = float(start_elem[1]) if start_elem and len(start_elem) > 1 else 0.0
        start_y = float(start_elem[2]) if start_elem and len(start_elem) > 2 else 0.0
        end_x = float(end_elem[1]) if end_elem and len(end_elem) > 1 else 0.0
        end_y = float(end_elem[2]) if end_elem and len(end_elem) > 2 else 0.0

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid')) if get_value(sexp, 'uuid') else None

        return cls(
            start_x=start_x, start_y=start_y,
            end_x=end_x, end_y=end_y,
            stroke=stroke, fill=fill, uuid=uuid,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result: SexpList = ['rectangle']
        result.append(['start', self.start_x, self.start_y])
        result.append(['end', self.end_x, self.end_y])
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())
        if self.uuid:
            result.append(['uuid', self.uuid])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of the rectangle."""
        from .kicad_geometry import BoundingBox
        bbox = BoundingBox()
        bbox.expand((self.start_x, self.start_y))
        bbox.expand((self.end_x, self.end_y))
        return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> list[str]:
        """Render rectangle to SVG elements."""
        from .kicad_geometry import SvgRenderContext
        if ctx is None:
            ctx = SvgRenderContext()

        x = min(self.start_x, self.end_x)
        y = min(self.start_y, self.end_y)
        w = abs(self.end_x - self.start_x)
        h = abs(self.end_y - self.start_y)

        fill = "none" if self.fill.type == SymFillType.NONE else ctx.fill
        stroke_width = self.stroke.width if self.stroke.width > 0 else 0.1

        return [f'<rect x="{ctx.fmt(x)}" y="{ctx.fmt(y)}" '
                f'width="{ctx.fmt(w)}" height="{ctx.fmt(h)}" '
                f'fill="{fill}" stroke="{ctx.stroke}" '
                f'stroke-width="{stroke_width}"/>']


__all__ = ['SymFillType', 'SymFill', 'SymRectangle']
