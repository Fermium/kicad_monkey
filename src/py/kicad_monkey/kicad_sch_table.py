"""KiCad schematic ``(table ...)`` and ``(table_cell ...)`` models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from .kicad_base import find_all_elements, find_element, get_at, get_value, parse_maybe_absent_bool, unquote_string
from .kicad_primitives import Effects, Stroke
from .kicad_sexpr import QuotedString
from .kicad_sym_rectangle import SymFill


@dataclass
class SchTableCell:
    """Schematic table cell; layout-compatible with ``SchTextBox``."""

    text: str = ""
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    size_x: float = 0.0
    size_y: float = 0.0
    margins: Optional[Tuple[float, float, float, float]] = None
    span: Tuple[int, int] = (1, 1)
    exclude_from_sim: bool = False
    stroke: Stroke = field(default_factory=Stroke)
    fill: SymFill = field(default_factory=SymFill)
    effects: Optional[Effects] = None
    uuid: str = ""

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> "SchTableCell":
        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""
        exclude_from_sim = parse_maybe_absent_bool(sexp, "exclude_from_sim") or False
        x, y, angle = get_at(sexp)

        size_elem = find_element(sexp, "size")
        size_x = float(size_elem[1]) if size_elem and len(size_elem) > 1 else 0.0
        size_y = float(size_elem[2]) if size_elem and len(size_elem) > 2 else 0.0

        margins_elem = find_element(sexp, "margins")
        margins: Optional[Tuple[float, float, float, float]] = None
        if margins_elem and len(margins_elem) >= 5:
            margins = (
                float(margins_elem[1]),
                float(margins_elem[2]),
                float(margins_elem[3]),
                float(margins_elem[4]),
            )

        span_elem = find_element(sexp, "span")
        span = (
            int(span_elem[1]) if span_elem and len(span_elem) > 1 else 1,
            int(span_elem[2]) if span_elem and len(span_elem) > 2 else 1,
        )
        effects_elem = find_element(sexp, "effects")

        return cls(
            text=text,
            at_x=x,
            at_y=y,
            at_angle=angle,
            size_x=size_x,
            size_y=size_y,
            margins=margins,
            span=span,
            exclude_from_sim=exclude_from_sim,
            stroke=Stroke.from_sexp(sexp),
            fill=SymFill.from_sexp(sexp),
            effects=Effects.from_sexp(sexp) if effects_elem else None,
            uuid=unquote_string(get_value(sexp, "uuid", "")),
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        if self._raw_sexp is not None:
            return self._raw_sexp
        result: list = ["table_cell", QuotedString(self.text)]
        result.append(["exclude_from_sim", "yes" if self.exclude_from_sim else "no"])
        result.append(["at", self.at_x, self.at_y, self.at_angle])
        result.append(["size", self.size_x, self.size_y])
        if self.margins is not None:
            result.append(["margins", *self.margins])
        result.append(["span", self.span[0], self.span[1]])
        result.append(self.fill.to_sexp())
        if self.effects is not None:
            result.append(self.effects.to_sexp())
        if self.uuid:
            result.append(["uuid", QuotedString(self.uuid)])
        return result


@dataclass
class SchTable:
    """Schematic table container."""

    cells: list[SchTableCell] = field(default_factory=list)
    uuid: str = ""

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> "SchTable":
        cells_elem = find_element(sexp, "cells")
        cells = (
            [SchTableCell.from_sexp(e) for e in find_all_elements(cells_elem, "table_cell")]
            if cells_elem
            else []
        )
        return cls(
            cells=cells,
            uuid=unquote_string(get_value(sexp, "uuid", "")),
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        if self._raw_sexp is not None:
            return self._raw_sexp
        return [
            "table",
            ["uuid", QuotedString(self.uuid)],
            ["cells", *[cell.to_sexp() for cell in self.cells]],
        ]


__all__ = ["SchTable", "SchTableCell"]
