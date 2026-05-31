"""
Symbol pin definition.

Pins are the connection points on symbols. They have electrical types
(input, output, etc.) and graphic styles (line, inverted, clock, etc.).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from .kicad_sexpr import QuotedString, SexpList
from .kicad_base import find_element, find_all_elements, get_value, get_at, has_flag, unquote_string
from .kicad_primitives import Effects
from .kicad_sch_enums import PinElectricalType, PinGraphicStyle


if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext


@dataclass
class PinAlternate:
    """Alternate function for a pin.

    Pins can have alternate functions that change the electrical type
    and graphic style when a specific alternate is selected.
    """
    name: str
    electrical_type: PinElectricalType
    graphic_style: PinGraphicStyle

    @classmethod
    def from_sexp(cls, sexp: list) -> 'PinAlternate':
        """Parse from (alternate "name" electrical_type graphic_style)."""
        name = unquote_string(sexp[1]) if len(sexp) > 1 else ""
        elec_type = PinElectricalType(sexp[2]) if len(sexp) > 2 else PinElectricalType.UNSPECIFIED
        gfx_style = PinGraphicStyle(sexp[3]) if len(sexp) > 3 else PinGraphicStyle.LINE
        return cls(name=name, electrical_type=elec_type, graphic_style=gfx_style)

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        return ['alternate', QuotedString(self.name),
                self.electrical_type.value, self.graphic_style.value]


@dataclass
class SymPin:
    """Symbol pin definition.

    Pins have:
    - Electrical type: defines ERC behavior (input, output, bidirectional, etc.)
    - Graphic style: visual appearance (line, inverted, clock, etc.)
    - Position and orientation
    - Name and number with optional effects
    - Optional alternate functions
    """
    electrical_type: PinElectricalType
    graphic_style: PinGraphicStyle
    at_x: float
    at_y: float
    at_angle: float = 0.0  # 0, 90, 180, 270
    length: float = 2.54

    name: str = ""
    name_effects: Optional[Effects] = None
    number: str = ""
    number_effects: Optional[Effects] = None

    hide: bool = False
    alternates: List[PinAlternate] = field(default_factory=list)

    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SymPin':
        """Parse from (pin electrical_type graphic_style (at X Y A) ...)."""
        # (pin input line (at 0 0 0) (length 2.54) (name "IN" ...) (number "1" ...))
        elec_type = PinElectricalType(sexp[1])
        gfx_style = PinGraphicStyle(sexp[2])

        x, y, angle = get_at(sexp)
        length = float(get_value(sexp, 'length', 2.54))
        # KiCad 10 emits (hide yes); KiCad 9 used a bare `hide` flag.
        hide = has_flag(sexp, 'hide') or get_value(sexp, 'hide') == 'yes'
        uuid_val = get_value(sexp, 'uuid')
        uuid = unquote_string(uuid_val) if uuid_val else None

        # Pin name
        name_elem = find_element(sexp, 'name')
        name = unquote_string(name_elem[1]) if name_elem and len(name_elem) > 1 else ""
        name_effects = None
        if name_elem:
            effects_elem = find_element(name_elem, 'effects')
            if effects_elem:
                name_effects = Effects.from_sexp(name_elem)

        # Pin number
        number_elem = find_element(sexp, 'number')
        number = unquote_string(number_elem[1]) if number_elem and len(number_elem) > 1 else ""
        number_effects = None
        if number_elem:
            effects_elem = find_element(number_elem, 'effects')
            if effects_elem:
                number_effects = Effects.from_sexp(number_elem)

        # Alternate functions
        alternates = []
        for alt_elem in find_all_elements(sexp, 'alternate'):
            alternates.append(PinAlternate.from_sexp(alt_elem))

        return cls(
            electrical_type=elec_type,
            graphic_style=gfx_style,
            at_x=x, at_y=y, at_angle=angle,
            length=length,
            name=name,
            name_effects=name_effects,
            number=number,
            number_effects=number_effects,
            hide=hide,
            alternates=alternates,
            uuid=uuid,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result: SexpList = ['pin', self.electrical_type.value, self.graphic_style.value]

        result.append(['at', self.at_x, self.at_y, self.at_angle])
        result.append(['length', self.length])

        # KiCad 10 emits (hide yes) at pin level (saveSymbolDrawItem in
        # eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr_lib_cache.cpp).
        if self.hide:
            result.append(['hide', 'yes'])

        # Name with effects
        name_elem = ['name', QuotedString(self.name)]
        if self.name_effects:
            name_elem.append(self.name_effects.to_sexp())
        result.append(name_elem)

        # Number with effects
        number_elem = ['number', QuotedString(self.number)]
        if self.number_effects:
            number_elem.append(self.number_effects.to_sexp())
        result.append(number_elem)

        # Alternates
        for alt in self.alternates:
            result.append(alt.to_sexp())

        if self.uuid:
            result.append(['uuid', self.uuid])

        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box including pin length.

        The pin wire extends from the external connection point (at_x, at_y)
        toward the symbol body. The body connection point (pin root) is at
        (at_x, at_y) + length * direction_vector.

        In KiCad symbol coordinates (Y-up):
        - angle 0° = pointing RIGHT, body to the right
        - angle 90° = pointing UP, body above
        - angle 180° = pointing LEFT, body to the left
        - angle 270° = pointing DOWN, body below
        """
        from .kicad_geometry import BoundingBox

        # Pin extends from external point (at_x, at_y) toward body
        # Direction vector: (cos(angle), sin(angle)) in Y-up coordinate system
        rad = math.radians(self.at_angle)
        body_x = self.at_x + self.length * math.cos(rad)
        body_y = self.at_y + self.length * math.sin(rad)  # Y-up coords, no inversion

        bbox = BoundingBox()
        bbox.expand((self.at_x, self.at_y))  # External connection point
        bbox.expand((body_x, body_y))  # Body connection point (pin root)
        return bbox

    @property
    def end_point(self) -> tuple[float, float]:
        """Get the body connection point (pin root) of the pin.

        This is the end of the pin wire that connects to the symbol body,
        calculated from the external point (at_x, at_y) extending toward
        the body by the pin length.
        """
        rad = math.radians(self.at_angle)
        body_x = self.at_x + self.length * math.cos(rad)
        body_y = self.at_y + self.length * math.sin(rad)  # Y-up coords
        return (body_x, body_y)

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> list[str]:
        """Render pin to SVG elements."""
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if self.hide:
            return []

        # Calculate pin body connection point (pin root)
        # Pin extends from external (at_x, at_y) toward body
        rad = math.radians(self.at_angle)
        end_x = self.at_x + self.length * math.cos(rad)
        end_y = self.at_y + self.length * math.sin(rad)  # Y-up coords

        lines = []

        # Pin line
        lines.append(f'<line x1="{ctx.fmt(self.at_x)}" y1="{ctx.fmt(self.at_y)}" '
                    f'x2="{ctx.fmt(end_x)}" y2="{ctx.fmt(end_y)}" '
                    f'stroke="{ctx.stroke}" stroke-width="0.15"/>')

        # Draw pin graphic style indicator
        if self.graphic_style == PinGraphicStyle.INVERTED:
            # Draw inversion bubble at end
            bubble_r = 0.3
            lines.append(f'<circle cx="{ctx.fmt(end_x)}" cy="{ctx.fmt(end_y)}" '
                        f'r="{ctx.fmt(bubble_r)}" fill="none" stroke="{ctx.stroke}" '
                        f'stroke-width="0.1"/>')
        elif self.graphic_style == PinGraphicStyle.CLOCK:
            # Draw clock indicator (small triangle)
            pass  # TODO: Implement clock indicator

        # Pin number text (near symbol body - at_x, at_y)
        if self.number:
            font_size = 0.8
            if self.number_effects and self.number_effects.font:
                font_size = self.number_effects.font.size_y
            # Position number perpendicular to pin
            num_offset = 0.5
            num_x = self.at_x + num_offset * math.sin(rad)
            num_y = self.at_y + num_offset * math.cos(rad)
            lines.append(f'<text x="{ctx.fmt(num_x)}" y="{ctx.fmt(num_y)}" '
                        f'font-size="{ctx.fmt(font_size)}" text-anchor="middle" '
                        f'dominant-baseline="middle">{self.number}</text>')

        # Pin name text (near end of pin)
        if self.name and self.name != "~":
            font_size = 0.8
            if self.name_effects and self.name_effects.font:
                font_size = self.name_effects.font.size_y
            # Position name along pin direction past end
            name_offset = 0.5
            name_x = end_x + name_offset * math.cos(rad)
            name_y = end_y - name_offset * math.sin(rad)
            lines.append(f'<text x="{ctx.fmt(name_x)}" y="{ctx.fmt(name_y)}" '
                        f'font-size="{ctx.fmt(font_size)}" text-anchor="start" '
                        f'dominant-baseline="middle">{self.name}</text>')

        return lines


__all__ = ['PinAlternate', 'SymPin']
