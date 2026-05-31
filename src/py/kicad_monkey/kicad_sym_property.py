"""
Symbol property with ID ordinal support.

Properties in KiCad symbols have ordinal IDs that determine their type:
- 0: Reference (e.g., "U1")
- 1: Value (e.g., "LM358")
- 2: Footprint
- 3: Datasheet
- 4: Description
- 5+: User-defined properties
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from ._api_markers import public_api
from .kicad_defaults import KICAD_DEFAULT_TEXT_SIZE_MM
from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_value, get_at, has_flag, unquote_string
from .kicad_primitives import Effects
from .kicad_sch_enums import PropertyId

if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox


@dataclass
class SymProperty:
    """Symbol property definition.

    Properties have an ID ordinal that determines their type:
    - 0: Reference (e.g., "U1")
    - 1: Value (e.g., "LM358")
    - 2: Footprint
    - 3: Datasheet
    - 4: Description
    - 5+: User-defined properties

    See PropertyId class in kicad_sch_enums for constants.
    """
    key: str
    value: str
    id: int = 0  # Property ordinal (0=Reference, 1=Value, etc.)
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    effects: Optional[Effects] = None
    show_name: bool = False  # KiCad 9: show property name
    do_not_autoplace: bool = False  # KiCad 9: exclude from autoplace
    hide: bool = False  # KiCad 10: property-level (hide yes) sibling of effects

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    @public_api
    def from_sexp(cls, sexp: list) -> 'SymProperty':
        """Parse from (property "key" "value" (id N) (at X Y A) ...)."""
        key = unquote_string(sexp[1])
        value = unquote_string(sexp[2])

        # Property ID (ordinal)
        prop_id = get_value(sexp, 'id', 0)

        # Position
        x, y, angle = get_at(sexp)

        # Effects
        effects = Effects.from_sexp(sexp)
        # If no effects element found, effects will be default, not None
        effects_elem = find_element(sexp, 'effects')
        if not effects_elem:
            effects = None

        # Flags — KiCad has used three forms across versions:
        #   - bare token  `show_name`
        #   - empty list  `(show_name)`            (intermediate format)
        #   - sub-list    `(show_name yes/no)`    (KiCad 10 canonical,
        #                                          KICAD_FORMAT::FormatBool)
        # Treat (name) without a value as truthy — KiCad parses it as a
        # set flag.
        def _bool_flag(name: str) -> bool:
            if has_flag(sexp, name):
                return True
            elem = find_element(sexp, name)
            if elem is None:
                return False
            if len(elem) <= 1:
                return True  # `(name)` form — flag is set
            return elem[1] == 'yes'

        show_name = _bool_flag('show_name')
        do_not_autoplace = _bool_flag('do_not_autoplace')

        # KiCad 10 emits (hide yes) at property level (saveField in
        # sch_io_kicad_sexpr_lib_cache.cpp); KiCad 9 nested it inside
        # (effects ...). Accept either form.
        hide = (get_value(sexp, 'hide') == 'yes'
                or (effects is not None and effects.hide))

        return cls(
            key=key, value=value, id=int(prop_id),
            at_x=x, at_y=y, at_angle=angle,
            effects=effects,
            show_name=show_name,
            do_not_autoplace=do_not_autoplace,
            hide=hide,
            _raw_sexp=sexp
        )

    @public_api
    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = ['property', QuotedString(self.key), QuotedString(self.value)]

        result.append(['id', self.id])

        # KiCad's reader requires the angle slot even when zero (drift inventory #1).
        result.append(['at', self.at_x, self.at_y, self.at_angle])

        # KiCad 10 emits these via KICAD_FORMAT::FormatBool as
        # (show_name yes/no) / (do_not_autoplace yes/no) sub-lists
        # (saveField in eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr_lib_cache.cpp).
        # The bare-token form is rejected by KiCad 10's parser. Emit
        # only when True so kicad-cli round-trips cleanly without bloating
        # defaults (kicad-cli canonicalises to explicit yes/no on save).
        if self.show_name:
            result.append(['show_name', 'yes'])

        if self.do_not_autoplace:
            result.append(['do_not_autoplace', 'yes'])

        # KiCad 10 emits (hide yes) at property level, before (effects ...);
        # see saveField in eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr_lib_cache.cpp.
        if self.hide:
            result.append(['hide', 'yes'])

        if self.effects:
            # Effects.hide is the legacy nested form — suppress on emit so
            # we don't double-emit alongside the property-level (hide yes).
            if self.effects.hide:
                effects_emit = Effects(
                    font=self.effects.font,
                    justify=self.effects.justify,
                    hide=False,
                ).to_sexp()
            else:
                effects_emit = self.effects.to_sexp()
            result.append(effects_emit)

        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this property text."""
        from .kicad_geometry import BoundingBox
        # Estimate based on text length and font size
        font_size = KICAD_DEFAULT_TEXT_SIZE_MM
        if self.effects and self.effects.font:
            font_size = self.effects.font.size_y
        text_width = len(self.value or 'X') * font_size * 0.7
        half_w, half_h = text_width / 2, font_size / 2
        bbox = BoundingBox()
        bbox.expand((self.at_x - half_w, self.at_y - half_h))
        bbox.expand((self.at_x + half_w, self.at_y + half_h))
        return bbox

    @property
    def is_reference(self) -> bool:
        """Check if this is the Reference property."""
        return self.id == PropertyId.REFERENCE

    @property
    def is_value(self) -> bool:
        """Check if this is the Value property."""
        return self.id == PropertyId.VALUE

    @property
    def is_footprint(self) -> bool:
        """Check if this is the Footprint property."""
        return self.id == PropertyId.FOOTPRINT


__all__ = ['SymProperty']
