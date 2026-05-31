"""
KiCad Schematic No Connect

No-connect markers for pins that are intentionally left unconnected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_value, unquote_string


@dataclass
class SchNoConnect:
    """No-connect marker at a pin location.

    Indicates that the pin is intentionally not connected.

    S-expression format:
        (no_connect
            (at X Y)
            (uuid "...")
        )
    """
    at_x: float = 0.0
    at_y: float = 0.0
    uuid: str = ""

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchNoConnect':
        """Parse from (no_connect (at X Y) (uuid "..."))."""
        # Position
        at_elem = find_element(sexp, 'at')
        at_x = float(at_elem[1]) if at_elem and len(at_elem) > 1 else 0.0
        at_y = float(at_elem[2]) if at_elem and len(at_elem) > 2 else 0.0

        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        return cls(at_x=at_x, at_y=at_y, uuid=uuid, _raw_sexp=sexp)

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = ['no_connect', ['at', self.at_x, self.at_y]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result
