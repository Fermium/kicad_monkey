"""KiCad schematic top-level (text_box ...) annotation.

KiCad emits this via ``SCH_IO_KICAD_SEXPR::saveTextBox`` for
``SCH_TEXTBOX_T`` items in
``eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr.cpp:1508``. The wire
format is::

    (text_box "string"
        (exclude_from_sim yes/no)
        (at X Y angle) (size W H) (margins L T R B)
        (stroke ...)
        (fill ...)
        (effects ...)
        (uuid "...")
        [(locked yes)]
    )

This is the schematic-level form; the lib-symbol equivalent is
``SymTextBox`` and lacks ``exclude_from_sim`` / ``margins`` / ``locked``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Tuple

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_at, get_value, parse_maybe_absent_bool, unquote_string
from .kicad_primitives import Effects, Stroke
from .kicad_sym_rectangle import SymFill

if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox


@dataclass
class SchTextBox:
    """Top-level rectangular text box on a schematic sheet."""

    text: str = ""
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    size_x: float = 0.0
    size_y: float = 0.0
    # ``margins`` is None when the source omitted ``(margins ...)``; KiCad's
    # parser at sch_io_kicad_sexpr_parser.cpp:5021 then falls back to
    # ``SCH_TEXTBOX::GetLegacyTextMargin()`` (stroke/2 + size_y*0.75), so
    # we must elide the field on emit to round-trip through that fallback.
    margins: Optional[Tuple[float, float, float, float]] = None
    exclude_from_sim: bool = False
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    effects: Optional[Effects] = None
    uuid: str = ""
    locked: bool = False

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchTextBox':
        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        exclude_from_sim = parse_maybe_absent_bool(sexp, 'exclude_from_sim') or False

        x, y, angle = get_at(sexp)

        size_elem = find_element(sexp, 'size')
        size_x = float(size_elem[1]) if size_elem and len(size_elem) > 1 else 0.0
        size_y = float(size_elem[2]) if size_elem and len(size_elem) > 2 else 0.0

        margins_elem = find_element(sexp, 'margins')
        margins: Optional[Tuple[float, float, float, float]] = None
        if margins_elem and len(margins_elem) >= 5:
            margins = (
                float(margins_elem[1]),
                float(margins_elem[2]),
                float(margins_elem[3]),
                float(margins_elem[4]),
            )

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)

        effects_elem = find_element(sexp, 'effects')
        effects = Effects.from_sexp(sexp) if effects_elem else None

        uuid = unquote_string(get_value(sexp, 'uuid', ''))
        locked = parse_maybe_absent_bool(sexp, 'locked') or False

        return cls(
            text=text,
            at_x=x, at_y=y, at_angle=angle,
            size_x=size_x, size_y=size_y,
            margins=margins,
            exclude_from_sim=exclude_from_sim,
            stroke=stroke, fill=fill,
            effects=effects,
            uuid=uuid,
            locked=locked,
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        result: list = ['text_box', QuotedString(self.text)]

        # saveTextBox writes exclude_from_sim unconditionally via FormatBool.
        result.append(['exclude_from_sim', 'yes' if self.exclude_from_sim else 'no'])

        result.append(['at', self.at_x, self.at_y, self.at_angle])
        result.append(['size', self.size_x, self.size_y])
        if self.margins is not None:
            result.append(['margins', self.margins[0], self.margins[1],
                           self.margins[2], self.margins[3]])

        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())

        if self.effects:
            result.append(self.effects.to_sexp())

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        if self.locked:
            result.append(['locked', 'yes'])

        return result

    def get_bounds(self) -> 'BoundingBox':
        from .kicad_geometry import BoundingBox
        bbox = BoundingBox()
        bbox.expand((self.at_x, self.at_y))
        bbox.expand((self.at_x + self.size_x, self.at_y + self.size_y))
        return bbox


__all__ = ['SchTextBox']
