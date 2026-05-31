"""
KiCad Footprint Rectangle Element

REQ-KICAD-070: One class per file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

from .kicad_sexpr import QuotedString

if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext
    from .kicad_pcb_polygon_ops import PolygonSet
from .kicad_base import (
    FillType,
    FRONT_SILKSCREEN_LAYER,
    find_element,
    get_value,
    unquote_string,
)
from .kicad_primitives import Stroke


@dataclass
class FpRect:
    """Footprint rectangle element."""
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    layer: str = FRONT_SILKSCREEN_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    fill: FillType = FillType.NO
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'FpRect':
        start = find_element(sexp, 'start')
        end = find_element(sexp, 'end')

        # Parse fill
        fill_val = get_value(sexp, 'fill', 'no')
        try:
            fill = FillType(fill_val) if isinstance(fill_val, str) else FillType.NO
        except ValueError:
            fill = FillType.NO

        return cls(
            start_x=float(start[1]) if start else 0.0,
            start_y=float(start[2]) if start else 0.0,
            end_x=float(end[1]) if end else 0.0,
            end_y=float(end[2]) if end else 0.0,
            layer=unquote_string(get_value(sexp, 'layer', FRONT_SILKSCREEN_LAYER)),
            stroke=Stroke.from_sexp(sexp),
            fill=fill,
            uuid=unquote_string(get_value(sexp, 'uuid')),
            _raw_sexp=sexp
        )

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this rectangle. REQ-KICAD-071."""
        from .kicad_geometry import BoundingBox

        width = self.stroke.width if self.stroke else 0.12
        hw = width / 2

        return BoundingBox(
            min_x=min(self.start_x, self.end_x) - hw,
            min_y=min(self.start_y, self.end_y) - hw,
            max_x=max(self.start_x, self.end_x) + hw,
            max_y=max(self.start_y, self.end_y) + hw
        )

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> List[str]:
        """Render this rectangle to SVG elements. REQ-KICAD-072."""
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        width = self.stroke.width if self.stroke else 0.12

        # Rectangle corners
        x1 = min(self.start_x, self.end_x) + ctx.offset_x
        y1 = min(self.start_y, self.end_y) + ctx.offset_y
        x2 = max(self.start_x, self.end_x) + ctx.offset_x
        y2 = max(self.start_y, self.end_y) + ctx.offset_y

        # Build path
        path_d = (
            f"M {ctx.fmt(x1)},{ctx.fmt(y1)} "
            f"L {ctx.fmt(x2)},{ctx.fmt(y1)} "
            f"L {ctx.fmt(x2)},{ctx.fmt(y2)} "
            f"L {ctx.fmt(x1)},{ctx.fmt(y2)} Z"
        )

        if self.is_filled:
            return [
                f'<path d="{path_d}" '
                f'style="fill:{ctx.fill}; fill-opacity:1.0; stroke:none;" />'
            ]
        else:
            return [
                f'<path d="{path_d}" '
                f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
                f'stroke-linecap:round; stroke-linejoin:round;" />'
            ]

    def to_sexp(self) -> list:
        result = ['fp_rect',
                  ['start', self.start_x, self.start_y],
                  ['end', self.end_x, self.end_y],
                  self.stroke.to_sexp(),
                  ['fill', self.fill.value],
                  ['layer', QuotedString(self.layer)]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    @property
    def is_filled(self) -> bool:
        """Check if rectangle is filled."""
        return self.fill in (FillType.SOLID, FillType.YES)

    def _to_poly(self, error: float = 0.005) -> 'PolygonSet':
        """Convert rectangle to polygon."""
        from .kicad_pcb_polygon_ops import PolygonSet, rect_to_polygon

        w = self.stroke.width

        contour = rect_to_polygon(
            (self.start_x, self.start_y),
            (self.end_x, self.end_y),
            w, 0.0, error
        )
        return PolygonSet(outlines=[contour])
