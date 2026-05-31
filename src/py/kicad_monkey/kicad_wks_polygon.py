"""
KiCad Worksheet Polygon Element.

S-expression format:
    (polygon (name "poly1:Poly") (pos X Y [corner]) (rotate A) (linewidth W)
        (pts (xy X Y) (xy X Y) ...)
        (pts (xy X Y) ...)  ; Additional pts sections define holes
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import math

from .kicad_sexpr import QuotedString, SexpList
from .kicad_base import find_element, find_all_elements, get_value, unquote_string
from .kicad_wks_primitives import WksPoint, WksCorner, WksRepeat, parse_option


_LINEWIDTH_UNSET = float('nan')


@dataclass
class WksPolygon:
    """Polygon element in a worksheet.

    Polygons can have multiple point sets - the first defines the outline,
    additional ones define holes within the polygon.
    """
    pos: WksPoint = field(default_factory=WksPoint)
    rotate: float = 0.0
    linewidth: float = field(default=_LINEWIDTH_UNSET)
    name: str = ""
    comment: str = ""
    option: str = ""
    repeat: WksRepeat = field(default_factory=WksRepeat)

    # List of point lists - first is outline, rest are holes
    point_sets: List[List[Tuple[float, float]]] = field(default_factory=list)

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'WksPolygon':
        """Parse from (polygon ...) element."""
        pos = cls._parse_pos(sexp)
        rotate = float(get_value(sexp, 'rotate', 0.0))
        lw_elem = find_element(sexp, 'linewidth')
        linewidth = float(lw_elem[1]) if lw_elem and len(lw_elem) > 1 else _LINEWIDTH_UNSET
        name = unquote_string(get_value(sexp, 'name', ''))
        comment = unquote_string(get_value(sexp, 'comment', ''))
        option = parse_option(sexp)
        repeat = WksRepeat.from_sexp(sexp)

        # Parse all pts sections
        point_sets = []
        for pts_elem in find_all_elements(sexp, 'pts'):
            points = []
            for xy_elem in find_all_elements(pts_elem, 'xy'):
                if len(xy_elem) >= 3:
                    x = float(xy_elem[1])
                    y = float(xy_elem[2])
                    points.append((x, y))
            if points:
                point_sets.append(points)

        return cls(
            pos=pos,
            rotate=rotate,
            linewidth=linewidth,
            name=name,
            comment=comment,
            option=option,
            repeat=repeat,
            point_sets=point_sets,
            _raw_sexp=sexp
        )

    @staticmethod
    def _parse_pos(sexp: list) -> WksPoint:
        """Parse position from (pos X Y [corner])."""
        elem = find_element(sexp, 'pos')
        if not elem:
            return WksPoint()

        x = float(elem[1]) if len(elem) > 1 else 0.0
        y = float(elem[2]) if len(elem) > 2 else 0.0

        corner = WksCorner.NONE
        if len(elem) > 3 and isinstance(elem[3], str):
            try:
                corner = WksCorner(elem[3])
            except ValueError:
                pass

        return WksPoint(x=x, y=y, corner=corner)

    def to_sexp(self) -> list:
        """Serialize to S-expression list per ds_data_model_io.cpp:357."""
        result: list = ['polygon']

        result.append(['name', QuotedString(self.name)])
        result.append(self.pos.to_sexp('pos'))

        if self.option:
            result.append(['option', self.option])

        result.extend(self.repeat.to_sexp_items())

        if self.rotate != 0.0:
            result.append(['rotate', self.rotate])

        if not math.isnan(self.linewidth) and self.linewidth != 0.0:
            result.append(['linewidth', self.linewidth])

        if self.comment:
            result.append(['comment', QuotedString(self.comment)])

        # Pts sections come last per format(DS_DATA_ITEM_POLYGONS*).
        for points in self.point_sets:
            pts: SexpList = ['pts']
            for x, y in points:
                pts.append(['xy', x, y])
            result.append(pts)

        return result
