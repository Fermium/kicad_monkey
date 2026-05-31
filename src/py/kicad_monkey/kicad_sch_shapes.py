"""KiCad schematic top-level graphic shapes (polyline / rectangle / arc / circle / bezier).

KiCad emits these via ``SCH_IO_KICAD_SEXPR::saveShape`` for ``SCH_SHAPE``
items in ``eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr.cpp:1332``,
which dispatches to ``formatPoly`` / ``formatRect`` / ``formatArc`` /
``formatCircle`` / ``formatBezier`` in
``eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr_common.cpp``.

The schematic-level wire format is the same as the lib-symbol form
emitted by ``sch_io_kicad_sexpr_lib_cache.cpp``, except:

* ``aIsPrivate`` is always ``false`` at sch-level (no ``private`` token).
* ``aInvertY`` is ``false`` at sch-level (Y axis is not flipped).
* ``aLocked`` may be ``true`` (sch-level shapes can be locked).
* ``uuid`` is wrapped via ``OUTPUTFORMATTER::Quotew``, so we emit it as
  a ``QuotedString``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, find_all_elements, get_value, unquote_string
from .kicad_primitives import Stroke
from .kicad_sym_rectangle import SymFill


@dataclass
class SchPolyline:
    """Top-level (notes-layer) polyline drawn on a schematic sheet."""

    points: List[Tuple[float, float]] = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    uuid: str = ""
    locked: bool = False
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchPolyline':
        pts_elem = find_element(sexp, 'pts')
        points: List[Tuple[float, float]] = []
        if pts_elem:
            for xy in find_all_elements(pts_elem, 'xy'):
                if len(xy) >= 3:
                    points.append((float(xy[1]), float(xy[2])))

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid', ''))
        locked_elem = find_element(sexp, 'locked')
        locked = bool(locked_elem and len(locked_elem) > 1 and locked_elem[1] == 'yes')

        return cls(points=points, stroke=stroke, fill=fill,
                   uuid=uuid, locked=locked, _raw_sexp=sexp)

    def to_sexp(self) -> list:
        result: list = ['polyline']
        result.append(['pts'] + [['xy', p[0], p[1]] for p in self.points])
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        if self.locked:
            result.append(['locked', 'yes'])
        return result


@dataclass
class SchRectangle:
    """Top-level rectangle drawn on a schematic sheet."""

    start_x: float = 0.0
    start_y: float = 0.0
    end_x: float = 0.0
    end_y: float = 0.0
    # ``formatRect`` emits ``(radius N)`` only when the corner radius is
    # > 0, so we elide on emit when the value is 0/None.
    radius: Optional[float] = None
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    uuid: str = ""
    locked: bool = False
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchRectangle':
        start_elem = find_element(sexp, 'start')
        end_elem = find_element(sexp, 'end')

        start_x = float(start_elem[1]) if start_elem and len(start_elem) > 1 else 0.0
        start_y = float(start_elem[2]) if start_elem and len(start_elem) > 2 else 0.0
        end_x = float(end_elem[1]) if end_elem and len(end_elem) > 1 else 0.0
        end_y = float(end_elem[2]) if end_elem and len(end_elem) > 2 else 0.0

        radius_elem = find_element(sexp, 'radius')
        radius: Optional[float] = None
        if radius_elem and len(radius_elem) > 1:
            radius = float(radius_elem[1])

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid', ''))
        locked_elem = find_element(sexp, 'locked')
        locked = bool(locked_elem and len(locked_elem) > 1 and locked_elem[1] == 'yes')

        return cls(
            start_x=start_x, start_y=start_y,
            end_x=end_x, end_y=end_y,
            radius=radius,
            stroke=stroke, fill=fill,
            uuid=uuid, locked=locked,
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        result: list = ['rectangle']
        result.append(['start', self.start_x, self.start_y])
        result.append(['end', self.end_x, self.end_y])
        if self.radius is not None and self.radius > 0:
            result.append(['radius', self.radius])
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        if self.locked:
            result.append(['locked', 'yes'])
        return result


@dataclass
class SchArc:
    """Top-level arc drawn on a schematic sheet.

    Per ``formatArc`` (sch_io_kicad_sexpr_common.cpp:228), the wire form
    is ``(arc (start X Y) (mid X Y) (end X Y) <stroke> <fill>
    [(uuid "...")] [(locked yes)])``. ``private`` is never emitted at
    schematic level.
    """

    start_x: float = 0.0
    start_y: float = 0.0
    mid_x: float = 0.0
    mid_y: float = 0.0
    end_x: float = 0.0
    end_y: float = 0.0
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    uuid: str = ""
    locked: bool = False
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchArc':
        start = find_element(sexp, 'start')
        mid = find_element(sexp, 'mid')
        end = find_element(sexp, 'end')

        sx = float(start[1]) if start and len(start) > 1 else 0.0
        sy = float(start[2]) if start and len(start) > 2 else 0.0
        mx = float(mid[1]) if mid and len(mid) > 1 else 0.0
        my = float(mid[2]) if mid and len(mid) > 2 else 0.0
        ex = float(end[1]) if end and len(end) > 1 else 0.0
        ey = float(end[2]) if end and len(end) > 2 else 0.0

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid', ''))
        locked_elem = find_element(sexp, 'locked')
        locked = bool(locked_elem and len(locked_elem) > 1 and locked_elem[1] == 'yes')

        return cls(
            start_x=sx, start_y=sy,
            mid_x=mx, mid_y=my,
            end_x=ex, end_y=ey,
            stroke=stroke, fill=fill,
            uuid=uuid, locked=locked,
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        result: list = ['arc']
        result.append(['start', self.start_x, self.start_y])
        result.append(['mid', self.mid_x, self.mid_y])
        result.append(['end', self.end_x, self.end_y])
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        if self.locked:
            result.append(['locked', 'yes'])
        return result


@dataclass
class SchCircle:
    """Top-level circle drawn on a schematic sheet.

    Per ``formatCircle`` (sch_io_kicad_sexpr_common.cpp:251), the wire
    form is ``(circle (center X Y) (radius R) <stroke> <fill>
    [(uuid "...")] [(locked yes)])``.
    """

    center_x: float = 0.0
    center_y: float = 0.0
    radius: float = 0.0
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    uuid: str = ""
    locked: bool = False
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchCircle':
        center = find_element(sexp, 'center')
        cx = float(center[1]) if center and len(center) > 1 else 0.0
        cy = float(center[2]) if center and len(center) > 2 else 0.0

        radius_elem = find_element(sexp, 'radius')
        radius = float(radius_elem[1]) if radius_elem and len(radius_elem) > 1 else 0.0

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid', ''))
        locked_elem = find_element(sexp, 'locked')
        locked = bool(locked_elem and len(locked_elem) > 1 and locked_elem[1] == 'yes')

        return cls(
            center_x=cx, center_y=cy,
            radius=radius,
            stroke=stroke, fill=fill,
            uuid=uuid, locked=locked,
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        result: list = ['circle']
        result.append(['center', self.center_x, self.center_y])
        result.append(['radius', self.radius])
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        if self.locked:
            result.append(['locked', 'yes'])
        return result


@dataclass
class SchBezier:
    """Top-level cubic Bezier drawn on a schematic sheet.

    Per ``formatBezier`` (sch_io_kicad_sexpr_common.cpp:297), the wire
    form is ``(bezier (pts (xy start) (xy c1) (xy c2) (xy end))
    <stroke> <fill> [(uuid "...")] [(locked yes)])`` — exactly four
    control points in start/c1/c2/end order.
    """

    points: List[Tuple[float, float]] = field(default_factory=list)
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    uuid: str = ""
    locked: bool = False
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchBezier':
        pts_elem = find_element(sexp, 'pts')
        points: List[Tuple[float, float]] = []
        if pts_elem:
            for xy in find_all_elements(pts_elem, 'xy'):
                if len(xy) >= 3:
                    points.append((float(xy[1]), float(xy[2])))

        stroke = Stroke.from_sexp(sexp)
        fill = SymFill.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid', ''))
        locked_elem = find_element(sexp, 'locked')
        locked = bool(locked_elem and len(locked_elem) > 1 and locked_elem[1] == 'yes')

        return cls(points=points, stroke=stroke, fill=fill,
                   uuid=uuid, locked=locked, _raw_sexp=sexp)

    def to_sexp(self) -> list:
        result: list = ['bezier']
        result.append(['pts'] + [['xy', p[0], p[1]] for p in self.points])
        result.append(self.stroke.to_sexp())
        result.append(self.fill.to_sexp())
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        if self.locked:
            result.append(['locked', 'yes'])
        return result


__all__ = ['SchPolyline', 'SchRectangle', 'SchArc', 'SchCircle', 'SchBezier']
