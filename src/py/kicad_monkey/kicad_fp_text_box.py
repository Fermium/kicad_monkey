"""
KiCad footprint text box element (fp_text_box).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .kicad_footprint import KiCadFootprint
    from .kicad_geometry import BoundingBox, SvgRenderContext, TextParams
    from .kicad_pcb_graphics import GrTextBox

from .kicad_base import (
    FRONT_SILKSCREEN_LAYER,
    find_element,
    get_value,
    parse_maybe_absent_bool,
    unquote_string,
)
from .kicad_primitives import Effects, RenderCache, Stroke
from .kicad_sexpr import QuotedString


@dataclass
class FpTextBox:
    """Footprint-local text box element."""

    text: str = ""
    start_x: float = 0.0
    start_y: float = 0.0
    end_x: float = 0.0
    end_y: float = 0.0
    margins: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    angle: float = 0.0
    polygon_points: Optional[list[Tuple[float, float]]] = None
    layer: str = FRONT_SILKSCREEN_LAYER
    locked: bool = False
    effects: Optional[Effects] = None
    stroke: Optional[Stroke] = None
    border: Optional[bool] = None
    knockout: Optional[bool] = None
    render_cache: Optional[RenderCache] = None
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> "FpTextBox":
        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        start = find_element(sexp, "start")
        end = find_element(sexp, "end")
        polygon_points = cls._parse_pts(sexp)
        start_x = float(start[1]) if start and len(start) > 1 else 0.0
        start_y = float(start[2]) if start and len(start) > 2 else 0.0
        end_x = float(end[1]) if end and len(end) > 1 else 0.0
        end_y = float(end[2]) if end and len(end) > 2 else 0.0
        if polygon_points and not (start and end):
            xs = [point[0] for point in polygon_points]
            ys = [point[1] for point in polygon_points]
            start_x = min(xs)
            start_y = min(ys)
            end_x = max(xs)
            end_y = max(ys)

        margins_elem = find_element(sexp, "margins")
        margins = (0.0, 0.0, 0.0, 0.0)
        if margins_elem and len(margins_elem) >= 5:
            margins = (
                float(margins_elem[1]),
                float(margins_elem[2]),
                float(margins_elem[3]),
                float(margins_elem[4]),
            )

        locked = parse_maybe_absent_bool(sexp, "locked")
        border = parse_maybe_absent_bool(sexp, "border")
        knockout = parse_maybe_absent_bool(sexp, "knockout")
        render_cache = RenderCache.from_sexp(sexp)

        return cls(
            text=text,
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            margins=margins,
            angle=float(get_value(sexp, "angle", 0.0)),
            polygon_points=polygon_points or None,
            layer=unquote_string(get_value(sexp, "layer", FRONT_SILKSCREEN_LAYER)),
            locked=bool(locked),
            effects=Effects.from_sexp(sexp) if find_element(sexp, "effects") else None,
            stroke=Stroke.from_sexp(sexp) if find_element(sexp, "stroke") else None,
            border=border,
            knockout=knockout,
            render_cache=render_cache,
            uuid=unquote_string(get_value(sexp, "uuid")),
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        result = [
            "fp_text_box",
            QuotedString(self.text),
        ]
        if self.locked:
            result.append(["locked", "yes"])
        if self.polygon_points:
            result.append(["pts"] + [["xy", x, y] for x, y in self.polygon_points])
        else:
            result.extend([
                ["start", self.start_x, self.start_y],
                ["end", self.end_x, self.end_y],
            ])
        result.append([
            "margins",
            self.margins[0],
            self.margins[1],
            self.margins[2],
            self.margins[3],
        ])
        if self.angle != 0.0:
            result.append(["angle", self.angle])
        result.append(["layer", QuotedString(self.layer)])
        if self.uuid:
            result.append(["uuid", QuotedString(self.uuid)])
        if self.effects:
            result.append(self.effects.to_sexp())
        if self.border is not None:
            result.append(["border", "yes" if self.border else "no"])
        if self.stroke:
            result.append(self.stroke.to_sexp())
        if self.knockout is not None:
            result.append(["knockout", "yes" if self.knockout else "no"])
        if self.render_cache:
            result.append(self.render_cache.to_sexp())
        return result

    @staticmethod
    def _parse_pts(sexp: list) -> list[Tuple[float, float]]:
        pts_elem = find_element(sexp, "pts")
        if not pts_elem:
            return []

        points: list[Tuple[float, float]] = []
        for point in pts_elem[1:]:
            if isinstance(point, list) and len(point) >= 3 and point[0] == "xy":
                points.append((float(point[1]), float(point[2])))
        return points

    @staticmethod
    def _rotate_point(x: float, y: float, angle: float) -> Tuple[float, float]:
        radians = math.radians(angle)
        cos_a = math.cos(radians)
        sin_a = math.sin(radians)
        return (x * cos_a + y * sin_a, y * cos_a - x * sin_a)

    def _as_board_text_box(self, footprint: 'Optional[KiCadFootprint]' = None) -> 'GrTextBox':
        from .kicad_pcb_graphics import GrTextBox

        fp_angle = float(getattr(footprint, "at_angle", 0.0) or 0.0)
        fp_x = float(getattr(footprint, "at_x", 0.0) or 0.0)
        fp_y = float(getattr(footprint, "at_y", 0.0) or 0.0)
        start_x, start_y = self._rotate_point(self.start_x, self.start_y, fp_angle)
        end_x, end_y = self._rotate_point(self.end_x, self.end_y, fp_angle)
        local_corners = self.polygon_points or [
            (self.start_x, self.start_y),
            (self.end_x, self.start_y),
            (self.end_x, self.end_y),
            (self.start_x, self.end_y),
        ]
        polygon_points = []
        for x, y in local_corners:
            point_x, point_y = self._rotate_point(x, y, fp_angle)
            polygon_points.append((point_x + fp_x, point_y + fp_y))

        return GrTextBox(
            text=self.text,
            start_x=start_x + fp_x,
            start_y=start_y + fp_y,
            end_x=end_x + fp_x,
            end_y=end_y + fp_y,
            margins=self.margins,
            angle=(self.angle + fp_angle) % 360.0,
            polygon_points=polygon_points if (self.polygon_points or fp_angle % 360.0) else None,
            layer=self.layer,
            locked=self.locked,
            effects=self.effects,
            stroke=self.stroke,
            border=self.border,
            knockout=self.knockout,
            render_cache=self.render_cache,
            uuid=self.uuid,
        )

    def render_cache_text(self, text: Optional[str] = None, footprint: 'Optional[KiCadFootprint]' = None) -> str:
        """Return resolved footprint text-box text after KiCad wrapping."""

        return self._as_board_text_box(footprint).render_cache_text(text)

    def to_text_params(self, text: Optional[str] = None, footprint: 'Optional[KiCadFootprint]' = None) -> "TextParams":
        """Convert footprint text-box content to `TextParams` for outline rendering."""

        return self._as_board_text_box(footprint).to_text_params(text)

    def get_bounds(self) -> "BoundingBox":
        from .kicad_geometry import BoundingBox

        width = self.stroke.width if self.stroke else 0.12
        hw = width / 2.0
        if self.polygon_points:
            xs = [point[0] for point in self.polygon_points]
            ys = [point[1] for point in self.polygon_points]
            return BoundingBox(
                min_x=min(xs) - hw,
                min_y=min(ys) - hw,
                max_x=max(xs) + hw,
                max_y=max(ys) + hw,
            )
        return BoundingBox(
            min_x=min(self.start_x, self.end_x) - hw,
            min_y=min(self.start_y, self.end_y) - hw,
            max_x=max(self.start_x, self.end_x) + hw,
            max_y=max(self.start_y, self.end_y) + hw,
        )

    def to_svg(self, ctx: "SvgRenderContext | None" = None) -> list[str]:
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()
        if not ctx.layer_visible(self.layer):
            return []
        if not self.border:
            return []

        x1 = min(self.start_x, self.end_x) + ctx.offset_x
        y1 = min(self.start_y, self.end_y) + ctx.offset_y
        x2 = max(self.start_x, self.end_x) + ctx.offset_x
        y2 = max(self.start_y, self.end_y) + ctx.offset_y
        width = self.stroke.width if self.stroke else 0.12
        return [
            f'<rect x="{ctx.fmt(x1)}" y="{ctx.fmt(y1)}" '
            f'width="{ctx.fmt(x2 - x1)}" height="{ctx.fmt(y2 - y1)}" '
            f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
            f'stroke-linecap:round; stroke-linejoin:round;" />'
        ]


__all__ = ["FpTextBox"]
