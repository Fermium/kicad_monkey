"""
KiCad Worksheet Rectangle Element.

S-expression format:
    (rect (name "rect1:Rect") (comment "description")
        (start X Y [corner]) (end X Y [corner])
        (linewidth W) (repeat N) (incrx X) (incry Y))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import math

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_value, unquote_string
from .kicad_wks_primitives import WksPoint, WksCorner, WksRepeat, parse_option


_LINEWIDTH_UNSET = float('nan')


@dataclass
class WksRect:
    """Rectangle element in a worksheet.

    Rectangles are defined by start and end corner positions,
    with optional corner reference for each.
    """
    start: WksPoint = field(default_factory=WksPoint)
    end: WksPoint = field(default_factory=WksPoint)
    linewidth: float = field(default=_LINEWIDTH_UNSET)
    name: str = ""
    comment: str = ""
    option: str = ""
    repeat: WksRepeat = field(default_factory=WksRepeat)

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'WksRect':
        """Parse from (rect ...) element."""
        start = cls._parse_point(sexp, 'start')
        end = cls._parse_point(sexp, 'end')

        lw_elem = find_element(sexp, 'linewidth')
        linewidth = float(lw_elem[1]) if lw_elem and len(lw_elem) > 1 else _LINEWIDTH_UNSET
        name = unquote_string(get_value(sexp, 'name', ''))
        comment = unquote_string(get_value(sexp, 'comment', ''))
        option = parse_option(sexp)
        repeat = WksRepeat.from_sexp(sexp)

        return cls(
            start=start,
            end=end,
            linewidth=linewidth,
            name=name,
            comment=comment,
            option=option,
            repeat=repeat,
            _raw_sexp=sexp
        )

    @staticmethod
    def _parse_point(sexp: list, tag: str) -> WksPoint:
        """Parse a point from (tag X Y [corner])."""
        elem = find_element(sexp, tag)
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
        """Serialize to S-expression list per ds_data_model_io.cpp:332."""
        result: list = ['rect']

        result.append(['name', QuotedString(self.name)])
        result.append(self.start.to_sexp('start'))
        result.append(self.end.to_sexp('end'))

        if self.option:
            result.append(['option', self.option])

        if not math.isnan(self.linewidth):
            result.append(['linewidth', self.linewidth])

        result.extend(self.repeat.to_sexp_items())

        if self.comment:
            result.append(['comment', QuotedString(self.comment)])

        return result
