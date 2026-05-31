"""
KiCad Schematic Junction

Junction (connection dot) elements in schematic documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_value, unquote_string


@dataclass
class SchJunction:
    """Junction (connection dot) at a wire intersection.

    S-expression format:
        (junction
            (at X Y)
            (diameter D)
            (color R G B A)
            (uuid "...")
        )
    """
    at_x: float = 0.0
    at_y: float = 0.0
    diameter: float = 0.0  # 0 = default size
    color: Optional[Tuple[int, int, int, float]] = None
    uuid: str = ""

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchJunction':
        """Parse from (junction (at X Y) (diameter D) (color R G B A) (uuid "..."))."""
        # Position
        at_elem = find_element(sexp, 'at')
        at_x = float(at_elem[1]) if at_elem and len(at_elem) > 1 else 0.0
        at_y = float(at_elem[2]) if at_elem and len(at_elem) > 2 else 0.0

        # Diameter
        diameter = float(get_value(sexp, 'diameter', 0.0))

        # Color
        color = None
        color_elem = find_element(sexp, 'color')
        if color_elem and len(color_elem) >= 5:
            color = (
                int(color_elem[1]),
                int(color_elem[2]),
                int(color_elem[3]),
                float(color_elem[4])
            )

        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        return cls(
            at_x=at_x, at_y=at_y,
            diameter=diameter, color=color,
            uuid=uuid, _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = ['junction', ['at', self.at_x, self.at_y]]
        result.append(['diameter', self.diameter])

        if self.color:
            result.append(['color', self.color[0], self.color[1], self.color[2], self.color[3]])
        else:
            result.append(['color', 0, 0, 0, 0])

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        return result
