"""KiCad schematic top-level (text ...) annotation.

KiCad emits this via ``SCH_IO_KICAD_SEXPR::saveText`` for ``SCH_TEXT_T``
items in ``eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr.cpp:1431``.
The wire format is::

    (text "string"
        (exclude_from_sim yes/no)
        (at X Y angle)
        (effects ...)
        (uuid "...")
        [(locked yes)]
    )

This is distinct from ``SymText`` (text *inside* a library symbol) — the
schematic-level form has ``exclude_from_sim`` and a ``locked`` flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_at, get_value, parse_maybe_absent_bool, unquote_string
from .kicad_primitives import Effects

if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox


@dataclass
class SchText:
    """Top-level text annotation on a schematic sheet."""

    text: str = ""
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    exclude_from_sim: bool = False
    effects: Optional[Effects] = None
    uuid: str = ""
    locked: bool = False

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchText':
        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        # KiCad 10 emits (exclude_from_sim yes/no) via FormatBool; treat
        # an absent flag as False to match SCH_IO_KICAD_SEXPR's default.
        exclude_from_sim = parse_maybe_absent_bool(sexp, 'exclude_from_sim') or False

        x, y, angle = get_at(sexp)

        effects_elem = find_element(sexp, 'effects')
        effects = Effects.from_sexp(sexp) if effects_elem else None

        uuid = unquote_string(get_value(sexp, 'uuid', ''))
        locked = parse_maybe_absent_bool(sexp, 'locked') or False

        return cls(
            text=text,
            at_x=x, at_y=y, at_angle=angle,
            exclude_from_sim=exclude_from_sim,
            effects=effects,
            uuid=uuid,
            locked=locked,
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        result: list = ['text', QuotedString(self.text)]

        # `(exclude_from_sim ...)` is unconditional in KiCad's saveText
        # (FormatBool always writes it); preserve that ordering so the
        # round-trip canonicalises to the same shape.
        result.append(['exclude_from_sim', 'yes' if self.exclude_from_sim else 'no'])

        result.append(['at', self.at_x, self.at_y, self.at_angle])

        if self.effects:
            result.append(self.effects.to_sexp())

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        if self.locked:
            result.append(['locked', 'yes'])

        return result

    def get_bounds(self) -> 'BoundingBox':
        from .kicad_geometry import BoundingBox
        font_size = 1.27
        if self.effects and self.effects.font:
            font_size = self.effects.font.size_y
        text_width = len(self.text or 'X') * font_size * 0.7
        half_w, half_h = text_width / 2, font_size / 2
        bbox = BoundingBox()
        bbox.expand((self.at_x - half_w, self.at_y - half_h))
        bbox.expand((self.at_x + half_w, self.at_y + half_h))
        return bbox


__all__ = ['SchText']
