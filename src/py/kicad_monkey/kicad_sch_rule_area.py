"""KiCad schematic top-level (rule_area ...) annotation.

KiCad emits this via ``SCH_IO_KICAD_SEXPR::saveRuleArea`` for
``SCH_RULE_AREA_T`` items in
``eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr.cpp:1373``. The wire
format is::

    (rule_area
        [(locked yes)]
        (exclude_from_sim no)
        (in_bom yes)
        (on_board yes)
        (dnp no)
        <shape>          ; polyline | rectangle | circle | arc | bezier
    )

``SCH_RULE_AREA`` inherits ``SCH_SHAPE`` so ``saveRuleArea`` calls
``saveShape(aRuleArea)`` to emit the inner geometry. The four bools
are always written via ``KICAD_FORMAT::FormatBool`` (explicit yes/no);
``locked`` is the only one elided when false.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .kicad_base import find_element

# Shape-type tokens dispatched by saveShape (sch_io_kicad_sexpr.cpp:1332).
_SHAPE_TOKENS = ('polyline', 'rectangle', 'circle', 'arc', 'bezier')


@dataclass
class SchRuleArea:
    """Top-level schematic rule-area annotation."""

    locked: bool = False
    exclude_from_sim: bool = False
    in_bom: bool = True
    on_board: bool = True
    dnp: bool = False
    # Inner shape stored as a parsed dataclass when we recognise the
    # token (polyline / rectangle), or as the raw sexp list for shape
    # types we don't have dedicated parsers for. Either form must
    # expose ``to_sexp()`` returning a list. For the raw fallback we
    # store the list directly.
    shape: Optional[object] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchRuleArea':
        from .kicad_sch_shapes import SchPolyline, SchRectangle

        def _bool(name: str, default: bool) -> bool:
            elem = find_element(sexp, name)
            if elem and len(elem) > 1:
                return elem[1] == 'yes'
            return default

        locked = _bool('locked', False)
        exclude_from_sim = _bool('exclude_from_sim', False)
        in_bom = _bool('in_bom', True)
        on_board = _bool('on_board', True)
        dnp = _bool('dnp', False)

        shape: Optional[object] = None
        for item in sexp[1:]:
            if not isinstance(item, list) or not item:
                continue
            tag = item[0]
            if tag == 'polyline':
                shape = SchPolyline.from_sexp(item)
                break
            if tag == 'rectangle':
                shape = SchRectangle.from_sexp(item)
                break
            if tag in _SHAPE_TOKENS:
                # Round-trip raw for shapes we don't have a dedicated
                # parser for yet (arc / circle / bezier).
                shape = item
                break

        return cls(
            locked=locked,
            exclude_from_sim=exclude_from_sim,
            in_bom=in_bom,
            on_board=on_board,
            dnp=dnp,
            shape=shape,
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        result: list = ['rule_area']
        if self.locked:
            result.append(['locked', 'yes'])
        # KiCad always emits these four via FormatBool.
        result.append(['exclude_from_sim', 'yes' if self.exclude_from_sim else 'no'])
        result.append(['in_bom', 'yes' if self.in_bom else 'no'])
        result.append(['on_board', 'yes' if self.on_board else 'no'])
        result.append(['dnp', 'yes' if self.dnp else 'no'])
        if self.shape is not None:
            if isinstance(self.shape, list):
                result.append(self.shape)
            else:
                to_sexp = getattr(self.shape, "to_sexp", None)
                if callable(to_sexp):
                    result.append(to_sexp())
        return result


__all__ = ['SchRuleArea']
