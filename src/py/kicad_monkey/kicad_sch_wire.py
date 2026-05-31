"""
KiCad Schematic Wire, Bus, and Bus Entry Elements

Wire connectivity elements in schematic documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .kicad_sexpr import QuotedString, SexpList
from .kicad_base import find_element, find_all_elements, get_value, unquote_string
from .kicad_primitives import Stroke


@dataclass
class SchWire:
    """Wire connecting two points in a schematic.

    S-expression format:
        (wire
            (pts
                (xy X1 Y1)
                (xy X2 Y2)
            )
            (stroke (width 0) (type default))
            (uuid "...")
        )
    """
    points: List[Tuple[float, float]] = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    uuid: str = ""

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchWire':
        """Parse from (wire (pts ...) (stroke ...) (uuid "..."))."""
        # Parse points
        points = []
        pts_elem = find_element(sexp, 'pts')
        if pts_elem:
            for xy in find_all_elements(pts_elem, 'xy'):
                if len(xy) >= 3:
                    points.append((float(xy[1]), float(xy[2])))

        stroke = Stroke.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        return cls(points=points, stroke=stroke, uuid=uuid, _raw_sexp=sexp)

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        pts: SexpList = ['pts']
        for x, y in self.points:
            pts.append(['xy', x, y])

        result = ['wire', pts, self.stroke.to_sexp()]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    @property
    def start(self) -> Tuple[float, float]:
        """Get start point of wire."""
        return self.points[0] if self.points else (0.0, 0.0)

    @property
    def end(self) -> Tuple[float, float]:
        """Get end point of wire."""
        return self.points[-1] if self.points else (0.0, 0.0)


@dataclass
class SchBus:
    """Bus connecting two points in a schematic.

    Similar to wire but carries multiple signals (bus).

    S-expression format:
        (bus
            (pts
                (xy X1 Y1)
                (xy X2 Y2)
            )
            (stroke (width 0) (type default))
            (uuid "...")
        )
    """
    points: List[Tuple[float, float]] = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    uuid: str = ""

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchBus':
        """Parse from (bus (pts ...) (stroke ...) (uuid "..."))."""
        points = []
        pts_elem = find_element(sexp, 'pts')
        if pts_elem:
            for xy in find_all_elements(pts_elem, 'xy'):
                if len(xy) >= 3:
                    points.append((float(xy[1]), float(xy[2])))

        stroke = Stroke.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        return cls(points=points, stroke=stroke, uuid=uuid, _raw_sexp=sexp)

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        pts: SexpList = ['pts']
        for x, y in self.points:
            pts.append(['xy', x, y])

        result = ['bus', pts, self.stroke.to_sexp()]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result


@dataclass
class SchBusEntry:
    """Bus entry connecting a wire to a bus.

    S-expression format:
        (bus_entry
            (at X Y)
            (size W H)
            (stroke (width 0) (type default))
            (uuid "...")
        )
    """
    at_x: float = 0.0
    at_y: float = 0.0
    size_x: float = 2.54
    size_y: float = 2.54
    stroke: Stroke = field(default_factory=Stroke)
    uuid: str = ""

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchBusEntry':
        """Parse from (bus_entry (at X Y) (size W H) ...)."""
        # Position
        at_elem = find_element(sexp, 'at')
        at_x = float(at_elem[1]) if at_elem and len(at_elem) > 1 else 0.0
        at_y = float(at_elem[2]) if at_elem and len(at_elem) > 2 else 0.0

        # Size
        size_elem = find_element(sexp, 'size')
        size_x = float(size_elem[1]) if size_elem and len(size_elem) > 1 else 2.54
        size_y = float(size_elem[2]) if size_elem and len(size_elem) > 2 else 2.54

        stroke = Stroke.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        return cls(
            at_x=at_x, at_y=at_y,
            size_x=size_x, size_y=size_y,
            stroke=stroke, uuid=uuid,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = [
            'bus_entry',
            ['at', self.at_x, self.at_y],
            ['size', self.size_x, self.size_y],
            self.stroke.to_sexp()
        ]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result


@dataclass
class SchBusAlias:
    """Bus alias definition.

    Defines a named group of signals for a bus.

    S-expression format:
        (bus_alias "AliasName"
            (members "signal1" "signal2" ...)
        )
    """
    name: str = ""
    members: List[str] = field(default_factory=list)

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchBusAlias':
        """Parse from (bus_alias "name" (members ...))."""
        name = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        members = []
        members_elem = find_element(sexp, 'members')
        if members_elem:
            for member in members_elem[1:]:
                members.append(unquote_string(member))

        return cls(name=name, members=members, _raw_sexp=sexp)

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = ['bus_alias', QuotedString(self.name)]
        if self.members:
            members_elem = ['members']
            for member in self.members:
                members_elem.append(QuotedString(member))
            result.append(members_elem)
        return result
