"""
KiCad Footprint Polygon Element

One class per file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, TYPE_CHECKING

from .kicad_sexpr import QuotedString

if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext
    from .kicad_pcb_polygon_ops import PolygonSet
from .kicad_base import (
    FillType,
    FRONT_SILKSCREEN_LAYER,
    find_element,
    find_all_elements,
    get_value,
    unquote_string,
)
from .kicad_primitives import Stroke


@dataclass
class FpPoly:
    """Footprint polygon element."""
    points: List[Tuple[float, float]] = field(default_factory=list)
    layer: str = FRONT_SILKSCREEN_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    fill: FillType = FillType.NO
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'FpPoly':
        pts_elem = find_element(sexp, 'pts')
        points = []
        if pts_elem:
            for xy in find_all_elements(pts_elem, 'xy'):
                if len(xy) >= 3:
                    points.append((float(xy[1]), float(xy[2])))

        fill_val = get_value(sexp, 'fill', 'no')
        # Handle both "fill yes" and "fill solid" formats
        if fill_val == 'yes':
            fill = FillType.YES
        elif fill_val == 'solid':
            fill = FillType.SOLID
        else:
            fill = FillType.NO

        return cls(
            points=points,
            layer=unquote_string(get_value(sexp, 'layer', FRONT_SILKSCREEN_LAYER)),
            stroke=Stroke.from_sexp(sexp),
            fill=fill,
            uuid=unquote_string(get_value(sexp, 'uuid')),
            _raw_sexp=sexp
        )

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this polygon.."""
        from .kicad_geometry import BoundingBox

        width = self.stroke.width if self.stroke else 0.12
        hw = width / 2

        bbox = BoundingBox()
        for x, y in self.points:
            bbox.expand((x - hw, y - hw))
            bbox.expand((x + hw, y + hw))

        return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> List[str]:
        """Render this polygon to SVG elements.."""
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        if not self.points:
            return []

        width = self.stroke.width if self.stroke else 0.12

        # Build path
        first_pt = self.points[0]
        path_d = f"M {ctx.fmt(first_pt[0] + ctx.offset_x)},{ctx.fmt(first_pt[1] + ctx.offset_y)}\n"
        for x, y in self.points[1:]:
            path_d += f"{ctx.fmt(x + ctx.offset_x)},{ctx.fmt(y + ctx.offset_y)}\n"
        path_d += "Z"

        if self.is_filled:
            return [
                f'<path d="{path_d}" '
                f'style="fill:{ctx.fill}; fill-opacity:1.0; stroke:none; fill-rule:evenodd;" />'
            ]
        else:
            return [
                f'<path d="{path_d}" '
                f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
                f'stroke-linecap:round; stroke-linejoin:round;" />'
            ]

    def to_sexp(self) -> list:
        pts = ['pts'] + [['xy', p[0], p[1]] for p in self.points]
        result = ['fp_poly', pts,
                  self.stroke.to_sexp(),
                  ['fill', self.fill.value],
                  ['layer', QuotedString(self.layer)]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    @property
    def is_filled(self) -> bool:
        """Check if polygon is filled."""
        return self.fill in (FillType.SOLID, FillType.YES)

    def _to_poly(self, error: float = 0.005) -> 'PolygonSet':
        """Convert fp_poly to a PolygonSet."""
        from .kicad_pcb_polygon_ops import PolygonSet

        if not self.points:
            return PolygonSet()

        if self.is_filled:
            # Filled polygon - use points directly
            return PolygonSet(outlines=[list(self.points)])
        else:
            # Unfilled polygon - stroke outline only
            # For now, just return the outline
            return PolygonSet(outlines=[list(self.points)])
