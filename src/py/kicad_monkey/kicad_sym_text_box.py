"""
Text box element in a symbol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_value, get_at, unquote_string
from .kicad_primitives import Effects, Stroke
from .kicad_sym_rectangle import SymFill, SymFillType


if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext


@dataclass
class SymTextBox:
    """Text box element in a symbol.

    A rectangular text container with optional border and fill.
    """
    text: str
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    size_x: float = 10.0
    size_y: float = 5.0
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    effects: Optional[Effects] = None
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SymTextBox':
        """Parse from (text_box "content" (at X Y A) (size W H) ...)."""
        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        x, y, angle = get_at(sexp)

        size_elem = find_element(sexp, 'size')
        size_x = float(size_elem[1]) if size_elem and len(size_elem) > 1 else 10.0
        size_y = float(size_elem[2]) if size_elem and len(size_elem) > 2 else 5.0

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)

        effects_elem = find_element(sexp, 'effects')
        effects = Effects.from_sexp(sexp) if effects_elem else None

        uuid = unquote_string(get_value(sexp, 'uuid')) if get_value(sexp, 'uuid') else None

        return cls(
            text=text,
            at_x=x, at_y=y, at_angle=angle,
            size_x=size_x, size_y=size_y,
            stroke=stroke, fill=fill,
            effects=effects, uuid=uuid,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = ['text_box', QuotedString(self.text)]

        # KiCad's reader requires the angle slot even when zero (drift inventory #1).
        result.append(['at', self.at_x, self.at_y, self.at_angle])

        result.append(['size', self.size_x, self.size_y])
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())

        if self.effects:
            result.append(self.effects.to_sexp())

        if self.uuid:
            result.append(['uuid', self.uuid])

        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of the text box."""
        from .kicad_geometry import BoundingBox
        bbox = BoundingBox()
        # Text box position is top-left corner
        bbox.expand((self.at_x, self.at_y))
        bbox.expand((self.at_x + self.size_x, self.at_y + self.size_y))
        return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> list[str]:
        """Render text box to SVG elements."""
        from .kicad_geometry import SvgRenderContext
        if ctx is None:
            ctx = SvgRenderContext()

        fill = "none" if self.fill.type == SymFillType.NONE else ctx.fill
        stroke_width = self.stroke.width if self.stroke.width > 0 else 0.1

        lines = []

        # Draw box
        lines.append(f'<rect x="{ctx.fmt(self.at_x)}" y="{ctx.fmt(self.at_y)}" '
                    f'width="{ctx.fmt(self.size_x)}" height="{ctx.fmt(self.size_y)}" '
                    f'fill="{fill}" stroke="{ctx.stroke}" stroke-width="{stroke_width}"/>')

        # Draw text (centered in box)
        font_size = 1.27
        if self.effects and self.effects.font:
            font_size = self.effects.font.size_y

        text_x = self.at_x + self.size_x / 2
        text_y = self.at_y + self.size_y / 2
        lines.append(f'<text x="{ctx.fmt(text_x)}" y="{ctx.fmt(text_y)}" '
                    f'font-size="{ctx.fmt(font_size)}" text-anchor="middle" '
                    f'dominant-baseline="middle">{self.text}</text>')

        return lines


__all__ = ['SymTextBox']
