"""
KiCad PCB Graphics - Graphical elements (gr_line, gr_arc, gr_circle, etc.)

These are board-level graphical elements (as opposed to footprint graphics).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext, TextParams
    from .kicad_pcb_polygon_ops import PolygonSet

from .kicad_sexpr import QuotedString
from .kicad_base import (
    EDGE_CUTS_LAYER,
    FillType,
    FRONT_SILKSCREEN_LAYER,
    find_element,
    find_all_elements,
    get_value,
    get_at,
    has_flag,
    parse_maybe_absent_bool,
    unquote_string,
)
from .kicad_primitives import Stroke, Effects, Font, RenderCache


@dataclass
class GrText:
    """Graphical text element."""
    text: str
    at_x: float
    at_y: float
    at_angle: float = 0.0
    layer: str = FRONT_SILKSCREEN_LAYER
    knockout: bool = False
    uuid: Optional[str] = None
    effects: Effects = field(default_factory=Effects)
    render_cache: Optional[RenderCache] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'GrText':
        text = unquote_string(sexp[1])
        x, y, angle = get_at(sexp)

        layer_elem = find_element(sexp, 'layer')
        layer = unquote_string(layer_elem[1]) if layer_elem else FRONT_SILKSCREEN_LAYER
        knockout = has_flag(layer_elem, 'knockout') if layer_elem else False

        uuid = unquote_string(get_value(sexp, 'uuid'))
        effects = Effects.from_sexp(sexp)
        render_cache = RenderCache.from_sexp(sexp)

        return cls(
            text=text,
            at_x=x, at_y=y, at_angle=angle,
            layer=layer,
            knockout=knockout,
            uuid=uuid,
            effects=effects,
            render_cache=render_cache,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        result = ['gr_text', QuotedString(self.text)]

        # KiCad's reader requires the angle slot even when zero (drift inventory #1).
        result.append(['at', self.at_x, self.at_y, self.at_angle])

        layer_elem = ['layer', QuotedString(self.layer)]
        if self.knockout:
            layer_elem.append('knockout')
        result.append(layer_elem)

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        result.append(self.effects.to_sexp())

        if self.render_cache:
            result.append(self.render_cache.to_sexp())

        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this text.."""
        from .kicad_geometry import BoundingBox

        # Estimate text size based on font size and text length
        font_size = self.effects.font.size_y if self.effects else 1.0
        char_width = font_size * 0.6  # Approximate character width
        text_width = len(self.text) * char_width
        text_height = font_size

        # Center the text box around the position
        hw = text_width / 2
        hh = text_height / 2

        return BoundingBox(
            min_x=self.at_x - hw,
            min_y=self.at_y - hh,
            max_x=self.at_x + hw,
            max_y=self.at_y + hh
        )

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> List[str]:
        """Render this text to SVG elements..

        Note: Full text rendering requires stroke font support.
        This is a placeholder that returns bounds rectangle for now.
        """
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        # For now, return empty - full text rendering requires stroke font
        # The actual SVG rendering happens in the board renderer with stroke fonts
        return []


@dataclass
class GrLine:
    """Graphical line element."""
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    angle: float = 0.0
    layer: str = EDGE_CUTS_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'GrLine':
        start = find_element(sexp, 'start')
        end = find_element(sexp, 'end')

        start_x = float(start[1]) if start else 0.0
        start_y = float(start[2]) if start else 0.0
        end_x = float(end[1]) if end else 0.0
        end_y = float(end[2]) if end else 0.0

        angle = float(get_value(sexp, 'angle', 0.0))
        layer = unquote_string(get_value(sexp, 'layer', EDGE_CUTS_LAYER))
        stroke = Stroke.from_sexp(sexp)
        uuid = unquote_string(get_value(sexp, 'uuid'))

        return cls(
            start_x=start_x, start_y=start_y,
            end_x=end_x, end_y=end_y,
            angle=angle,
            layer=layer,
            stroke=stroke,
            uuid=uuid,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        result = ['gr_line',
                  ['start', self.start_x, self.start_y],
                  ['end', self.end_x, self.end_y]]
        if self.angle != 0:
            result.append(['angle', self.angle])
        result.append(self.stroke.to_sexp())
        result.append(['layer', QuotedString(self.layer)])
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this line.."""
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
        """Render this line to SVG elements.."""
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        sx = self.start_x + ctx.offset_x
        sy = self.start_y + ctx.offset_y
        ex = self.end_x + ctx.offset_x
        ey = self.end_y + ctx.offset_y
        width = self.stroke.width if self.stroke else 0.12

        return [
            f'<path d="M{ctx.fmt(sx)} {ctx.fmt(sy)} L{ctx.fmt(ex)} {ctx.fmt(ey)}" '
            f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
            f'stroke-linecap:round; stroke-linejoin:round;" />'
        ]


@dataclass
class GrRect:
    """Graphical rectangle element."""
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    layer: str = EDGE_CUTS_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    fill: FillType = FillType.NO
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'GrRect':
        start = find_element(sexp, 'start')
        end = find_element(sexp, 'end')

        start_x = float(start[1]) if start else 0.0
        start_y = float(start[2]) if start else 0.0
        end_x = float(end[1]) if end else 0.0
        end_y = float(end[2]) if end else 0.0

        layer = unquote_string(get_value(sexp, 'layer', EDGE_CUTS_LAYER))
        stroke = Stroke.from_sexp(sexp)
        fill_val = get_value(sexp, 'fill', 'no')
        fill = FillType(fill_val) if isinstance(fill_val, str) else FillType.NO
        uuid = unquote_string(get_value(sexp, 'uuid'))

        return cls(
            start_x=start_x, start_y=start_y,
            end_x=end_x, end_y=end_y,
            layer=layer,
            stroke=stroke,
            fill=fill,
            uuid=uuid,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        result = ['gr_rect',
                  ['start', self.start_x, self.start_y],
                  ['end', self.end_x, self.end_y],
                  self.stroke.to_sexp(),
                  ['fill', self.fill.value],
                  ['layer', QuotedString(self.layer)]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this rectangle.."""
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
        """Render this rectangle to SVG elements.."""
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        x1 = min(self.start_x, self.end_x) + ctx.offset_x
        y1 = min(self.start_y, self.end_y) + ctx.offset_y
        x2 = max(self.start_x, self.end_x) + ctx.offset_x
        y2 = max(self.start_y, self.end_y) + ctx.offset_y
        width = self.stroke.width if self.stroke else 0.12

        is_filled = self.fill == FillType.SOLID

        if is_filled:
            return [
                f'<path d="M{ctx.fmt(x1)} {ctx.fmt(y1)} '
                f'L{ctx.fmt(x2)} {ctx.fmt(y1)} L{ctx.fmt(x2)} {ctx.fmt(y2)} '
                f'L{ctx.fmt(x1)} {ctx.fmt(y2)} Z" '
                f'style="fill:{ctx.fill}; stroke:none;" />'
            ]
        else:
            return [
                f'<path d="M{ctx.fmt(x1)} {ctx.fmt(y1)} '
                f'L{ctx.fmt(x2)} {ctx.fmt(y1)} L{ctx.fmt(x2)} {ctx.fmt(y2)} '
                f'L{ctx.fmt(x1)} {ctx.fmt(y2)} Z" '
                f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
                f'stroke-linecap:round; stroke-linejoin:round;" />'
            ]


@dataclass
class GrArc:
    """Graphical arc element."""
    start_x: float
    start_y: float
    mid_x: float
    mid_y: float
    end_x: float
    end_y: float
    layer: str = EDGE_CUTS_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'GrArc':
        start = find_element(sexp, 'start')
        mid = find_element(sexp, 'mid')
        end = find_element(sexp, 'end')

        return cls(
            start_x=float(start[1]) if start else 0.0,
            start_y=float(start[2]) if start else 0.0,
            mid_x=float(mid[1]) if mid else 0.0,
            mid_y=float(mid[2]) if mid else 0.0,
            end_x=float(end[1]) if end else 0.0,
            end_y=float(end[2]) if end else 0.0,
            layer=unquote_string(get_value(sexp, 'layer', EDGE_CUTS_LAYER)),
            stroke=Stroke.from_sexp(sexp),
            uuid=unquote_string(get_value(sexp, 'uuid')),
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        result = ['gr_arc',
                  ['start', self.start_x, self.start_y],
                  ['mid', self.mid_x, self.mid_y],
                  ['end', self.end_x, self.end_y],
                  self.stroke.to_sexp(),
                  ['layer', QuotedString(self.layer)]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this arc.."""
        from .kicad_geometry import BoundingBox
        from .kicad_pcb_polygon_ops import arc_to_polygon

        width = self.stroke.width if self.stroke else 0.12

        # Use arc_to_polygon for accurate bounds
        start = (self.start_x, self.start_y)
        mid = (self.mid_x, self.mid_y)
        end = (self.end_x, self.end_y)
        contour = arc_to_polygon(start, mid, end, width)

        bbox = BoundingBox()
        for x, y in contour:
            bbox.expand((x, y))
        return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> List[str]:
        """Render this arc to SVG elements.."""
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        width = self.stroke.width if self.stroke else 0.12

        # Calculate SVG arc parameters
        ax, ay = self.start_x, self.start_y
        bx, by = self.mid_x, self.mid_y
        cx, cy = self.end_x, self.end_y

        # Midpoints and perpendicular bisectors
        d_ab = ((ax + bx) / 2, (ay + by) / 2)
        d_bc = ((bx + cx) / 2, (by + cy) / 2)
        ab = (bx - ax, by - ay)
        bc = (cx - bx, cy - by)
        perp_ab = (-ab[1], ab[0])
        perp_bc = (-bc[1], bc[0])

        det = perp_ab[0] * perp_bc[1] - perp_ab[1] * perp_bc[0]

        if abs(det) < 1e-10:
            # Collinear - render as line
            sx = self.start_x + ctx.offset_x
            sy = self.start_y + ctx.offset_y
            ex = self.end_x + ctx.offset_x
            ey = self.end_y + ctx.offset_y
            return [
                f'<path d="M{ctx.fmt(sx)} {ctx.fmt(sy)} L{ctx.fmt(ex)} {ctx.fmt(ey)}" '
                f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
                f'stroke-linecap:round; stroke-linejoin:round;" />'
            ]

        dx = d_bc[0] - d_ab[0]
        dy = d_bc[1] - d_ab[1]
        t = (dx * perp_bc[1] - dy * perp_bc[0]) / det

        center_x = d_ab[0] + t * perp_ab[0]
        center_y = d_ab[1] + t * perp_ab[1]
        radius = math.sqrt((ax - center_x) ** 2 + (ay - center_y) ** 2)

        # Determine arc direction
        v1 = (cx - ax, cy - ay)
        v2 = (bx - ax, by - ay)
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        is_cw = cross <= 0

        if is_cw:
            svg_start = (self.end_x, self.end_y)
            svg_end = (self.start_x, self.start_y)
        else:
            svg_start = (self.start_x, self.start_y)
            svg_end = (self.end_x, self.end_y)

        # Calculate angle span
        angle_at_start = math.atan2(ay - center_y, ax - center_x)
        angle_at_end = math.atan2(cy - center_y, cx - center_x)
        angle = angle_at_end - angle_at_start

        if is_cw:
            while angle < 0:
                angle += 2 * math.pi
        else:
            while angle > 0:
                angle -= 2 * math.pi

        large_arc_flag = 1 if abs(angle) > math.pi else 0
        sweep_flag = 0

        sx = svg_start[0] + ctx.offset_x
        sy = svg_start[1] + ctx.offset_y
        ex = svg_end[0] + ctx.offset_x
        ey = svg_end[1] + ctx.offset_y

        return [
            f'<path d="M{ctx.fmt(sx)} {ctx.fmt(sy)} '
            f'A{ctx.fmt(radius)} {ctx.fmt(radius)} 0 {large_arc_flag} {sweep_flag} '
            f'{ctx.fmt(ex)} {ctx.fmt(ey)}" '
            f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
            f'stroke-linecap:round; stroke-linejoin:round;" />'
        ]


@dataclass
class GrCircle:
    """Graphical circle element."""
    center_x: float
    center_y: float
    end_x: float
    end_y: float
    layer: str = EDGE_CUTS_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    fill: FillType = FillType.NO
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'GrCircle':
        center = find_element(sexp, 'center')
        end = find_element(sexp, 'end')

        return cls(
            center_x=float(center[1]) if center else 0.0,
            center_y=float(center[2]) if center else 0.0,
            end_x=float(end[1]) if end else 0.0,
            end_y=float(end[2]) if end else 0.0,
            layer=unquote_string(get_value(sexp, 'layer', EDGE_CUTS_LAYER)),
            stroke=Stroke.from_sexp(sexp),
            fill=FillType(get_value(sexp, 'fill', 'no')),
            uuid=unquote_string(get_value(sexp, 'uuid')),
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        result = ['gr_circle',
                  ['center', self.center_x, self.center_y],
                  ['end', self.end_x, self.end_y],
                  self.stroke.to_sexp(),
                  ['fill', self.fill.value],
                  ['layer', QuotedString(self.layer)]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this circle.."""
        from .kicad_geometry import BoundingBox

        # Radius is distance from center to end point
        radius = math.sqrt(
            (self.end_x - self.center_x) ** 2 +
            (self.end_y - self.center_y) ** 2
        )
        width = self.stroke.width if self.stroke else 0.12
        hw = width / 2

        return BoundingBox(
            min_x=self.center_x - radius - hw,
            min_y=self.center_y - radius - hw,
            max_x=self.center_x + radius + hw,
            max_y=self.center_y + radius + hw
        )

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> List[str]:
        """Render this circle to SVG elements.."""
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        cx = self.center_x + ctx.offset_x
        cy = self.center_y + ctx.offset_y
        radius = math.sqrt(
            (self.end_x - self.center_x) ** 2 +
            (self.end_y - self.center_y) ** 2
        )
        width = self.stroke.width if self.stroke else 0.12

        is_filled = self.fill == FillType.SOLID

        if is_filled:
            return [
                f'<circle cx="{ctx.fmt(cx)}" cy="{ctx.fmt(cy)}" r="{ctx.fmt(radius)}" '
                f'style="fill:{ctx.fill}; stroke:none;" />'
            ]
        else:
            return [
                f'<circle cx="{ctx.fmt(cx)}" cy="{ctx.fmt(cy)}" r="{ctx.fmt(radius)}" '
                f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)};" />'
            ]


@dataclass
class GrPoly:
    """Graphical polygon element."""
    points: List[Tuple[float, float]] = field(default_factory=list)
    layer: str = EDGE_CUTS_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    fill: FillType = FillType.NO
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'GrPoly':
        pts_elem = find_element(sexp, 'pts')
        points = []
        if pts_elem:
            for xy in find_all_elements(pts_elem, 'xy'):
                if len(xy) >= 3:
                    points.append((float(xy[1]), float(xy[2])))

        return cls(
            points=points,
            layer=unquote_string(get_value(sexp, 'layer', EDGE_CUTS_LAYER)),
            stroke=Stroke.from_sexp(sexp),
            fill=FillType(get_value(sexp, 'fill', 'no')),
            uuid=unquote_string(get_value(sexp, 'uuid')),
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        pts = ['pts'] + [['xy', p[0], p[1]] for p in self.points]
        result = ['gr_poly', pts,
                  self.stroke.to_sexp(),
                  ['fill', self.fill.value],
                  ['layer', QuotedString(self.layer)]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this polygon.."""
        from .kicad_geometry import BoundingBox

        if not self.points:
            return BoundingBox()

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
        is_filled = self.fill == FillType.SOLID

        # Build path
        path_data = f"M{ctx.fmt(self.points[0][0] + ctx.offset_x)} {ctx.fmt(self.points[0][1] + ctx.offset_y)}"
        for x, y in self.points[1:]:
            path_data += f" L{ctx.fmt(x + ctx.offset_x)} {ctx.fmt(y + ctx.offset_y)}"
        path_data += " Z"

        if is_filled:
            return [
                f'<path d="{path_data}" style="fill:{ctx.fill}; stroke:none;" />'
            ]
        else:
            return [
                f'<path d="{path_data}" '
                f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
                f'stroke-linecap:round; stroke-linejoin:round;" />'
            ]


@dataclass
class GrCurve:
    """Graphical Bezier curve element (gr_curve)."""
    points: List[Tuple[float, float]] = field(default_factory=list)  # 4 control points
    layer: str = FRONT_SILKSCREEN_LAYER
    stroke: Stroke = field(default_factory=Stroke)
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'GrCurve':
        pts_elem = find_element(sexp, 'pts')
        points = []
        if pts_elem:
            for xy in find_all_elements(pts_elem, 'xy'):
                if len(xy) >= 3:
                    points.append((float(xy[1]), float(xy[2])))

        return cls(
            points=points,
            layer=unquote_string(get_value(sexp, 'layer', FRONT_SILKSCREEN_LAYER)),
            stroke=Stroke.from_sexp(sexp),
            uuid=unquote_string(get_value(sexp, 'uuid')),
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        pts = ['pts'] + [['xy', p[0], p[1]] for p in self.points]
        result = ['gr_curve', pts,
                  self.stroke.to_sexp(),
                  ['layer', QuotedString(self.layer)]]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        return result

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this curve.."""
        from .kicad_geometry import BoundingBox

        if not self.points:
            return BoundingBox()

        width = self.stroke.width if self.stroke else 0.12
        hw = width / 2

        # Control point bounding box is a conservative bound for Bezier
        bbox = BoundingBox()
        for x, y in self.points:
            bbox.expand((x - hw, y - hw))
            bbox.expand((x + hw, y + hw))
        return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> List[str]:
        """Render this curve to SVG elements.."""
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        if len(self.points) < 4:
            return []

        width = self.stroke.width if self.stroke else 0.12

        # Cubic Bezier: M start C cp1 cp2 end
        p0 = self.points[0]
        p1 = self.points[1]
        p2 = self.points[2]
        p3 = self.points[3]

        return [
            f'<path d="M{ctx.fmt(p0[0] + ctx.offset_x)} {ctx.fmt(p0[1] + ctx.offset_y)} '
            f'C{ctx.fmt(p1[0] + ctx.offset_x)} {ctx.fmt(p1[1] + ctx.offset_y)} '
            f'{ctx.fmt(p2[0] + ctx.offset_x)} {ctx.fmt(p2[1] + ctx.offset_y)} '
            f'{ctx.fmt(p3[0] + ctx.offset_x)} {ctx.fmt(p3[1] + ctx.offset_y)}" '
            f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
            f'stroke-linecap:round; stroke-linejoin:round;" />'
        ]


@dataclass
class GrTextBox:
    """Graphical text box element (gr_text_box)."""
    text: str = ""
    start_x: float = 0.0
    start_y: float = 0.0
    end_x: float = 0.0
    end_y: float = 0.0
    margins: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # left, top, right, bottom
    angle: float = 0.0
    polygon_points: Optional[List[Tuple[float, float]]] = None
    layer: str = FRONT_SILKSCREEN_LAYER
    locked: bool = False
    effects: Optional[Effects] = None
    stroke: Optional[Stroke] = None
    border: Optional[bool] = None
    knockout: Optional[bool] = None
    render_cache: Optional[RenderCache] = None
    uuid: Optional[str] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

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

    @classmethod
    def from_sexp(cls, sexp: list) -> 'GrTextBox':
        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        start = find_element(sexp, 'start')
        end = find_element(sexp, 'end')
        polygon_points = cls._parse_pts(sexp)
        start_x = float(start[1]) if start else 0.0
        start_y = float(start[2]) if start else 0.0
        end_x = float(end[1]) if end else 0.0
        end_y = float(end[2]) if end else 0.0
        if polygon_points and not (start and end):
            xs = [point[0] for point in polygon_points]
            ys = [point[1] for point in polygon_points]
            start_x = min(xs)
            start_y = min(ys)
            end_x = max(xs)
            end_y = max(ys)

        margins_elem = find_element(sexp, 'margins')
        margins = (0.0, 0.0, 0.0, 0.0)
        if margins_elem and len(margins_elem) >= 5:
            margins = (float(margins_elem[1]), float(margins_elem[2]),
                      float(margins_elem[3]), float(margins_elem[4]))

        effects = None
        effects_elem = find_element(sexp, 'effects')
        if effects_elem:
            # Effects.from_sexp expects the parent sexp (to find 'effects' element)
            effects = Effects.from_sexp(sexp)

        stroke = None
        stroke_elem = find_element(sexp, 'stroke')
        if stroke_elem:
            stroke = Stroke.from_sexp(sexp)

        locked = parse_maybe_absent_bool(sexp, 'locked')
        border = parse_maybe_absent_bool(sexp, 'border')
        knockout = parse_maybe_absent_bool(sexp, 'knockout')
        render_cache = RenderCache.from_sexp(sexp)

        return cls(
            text=text,
            start_x=start_x, start_y=start_y,
            end_x=end_x, end_y=end_y,
            margins=margins,
            angle=float(get_value(sexp, 'angle', 0.0)),
            polygon_points=polygon_points or None,
            layer=unquote_string(get_value(sexp, 'layer', FRONT_SILKSCREEN_LAYER)),
            locked=bool(locked),
            effects=effects,
            stroke=stroke,
            border=border,
            knockout=knockout,
            render_cache=render_cache,
            uuid=unquote_string(get_value(sexp, 'uuid')),
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        result = ['gr_text_box', QuotedString(self.text)]
        if self.locked:
            result.append(['locked', 'yes'])
        if self.polygon_points:
            result.append(["pts"] + [["xy", x, y] for x, y in self.polygon_points])
        else:
            result.extend([
                ['start', self.start_x, self.start_y],
                ['end', self.end_x, self.end_y],
            ])
        result.append(['margins', self.margins[0], self.margins[1],
                      self.margins[2], self.margins[3]])
        if self.angle != 0.0:
            result.append(['angle', self.angle])
        result.append(['layer', QuotedString(self.layer)])
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        if self.effects:
            result.append(self.effects.to_sexp())
        if self.border is not None:
            result.append(['border', 'yes' if self.border else 'no'])
        if self.stroke:
            result.append(self.stroke.to_sexp())
        if self.knockout is not None:
            result.append(['knockout', 'yes' if self.knockout else 'no'])
        if self.render_cache:
            result.append(self.render_cache.to_sexp())
        return result

    @property
    def font(self) -> Font:
        """Return text-box font parameters, with KiCad defaults if absent."""

        return self.effects.font if self.effects else Effects().font

    @property
    def is_mirrored(self) -> bool:
        if self.effects and self.effects.justify:
            return 'mirror' in self.effects.justify
        return False

    @property
    def h_align(self) -> str:
        if self.effects and self.effects.justify:
            if 'left' in self.effects.justify:
                return 'left'
            if 'right' in self.effects.justify:
                return 'right'
        if self.effects:
            return 'center'
        return 'left'

    @property
    def v_align(self) -> str:
        if self.effects and self.effects.justify:
            if 'top' in self.effects.justify:
                return 'top'
            if 'bottom' in self.effects.justify:
                return 'bottom'
        return 'center'

    def _bbox_stroke_inflate(self) -> float:
        if self.stroke and self.stroke.width > 0.0:
            return self.stroke.width / 2.0
        return 0.0

    def _corners_in_sequence(self) -> list[Tuple[float, float]]:
        """Mirror KiCad's `EDA_SHAPE::GetCornersInSequence()` for rectangles."""

        inflate = self._bbox_stroke_inflate()
        if self.polygon_points:
            xs = [point[0] for point in self.polygon_points]
            ys = [point[1] for point in self.polygon_points]
            left = min(xs) - inflate
            right = max(xs) + inflate
            top = min(ys) - inflate
            bottom = max(ys) + inflate
        else:
            left = min(self.start_x, self.end_x) - inflate
            right = max(self.start_x, self.end_x) + inflate
            top = min(self.start_y, self.end_y) - inflate
            bottom = max(self.start_y, self.end_y) + inflate
        angle = self.angle % 360.0
        cardinal = (
            math.isclose(angle, 0.0, abs_tol=1e-9)
            or math.isclose(angle, 90.0, abs_tol=1e-9)
            or math.isclose(angle, 180.0, abs_tol=1e-9)
            or math.isclose(angle, 270.0, abs_tol=1e-9)
        )

        if self.polygon_points and not cardinal:
            corners = list(self.polygon_points)
            while len(corners) < 4:
                last_x, last_y = corners[-1]
                corners.append((last_x + 0.00001, last_y + 0.00001))

            min_x = min(corners, key=lambda point: point[0])
            max_x = max(corners, key=lambda point: point[0])
            min_y = min(corners, key=lambda point: point[1])
            max_y = max(corners, key=lambda point: point[1])

            if angle < 90.0:
                return [min_x, min_y, max_x, max_y]
            if angle < 180.0:
                return [max_y, min_x, min_y, max_x]
            if angle < 270.0:
                return [max_x, max_y, min_x, min_y]
            return [min_y, max_x, max_y, min_x]

        if math.isclose(angle, 90.0, abs_tol=1e-9):
            return [(left, bottom), (left, top), (right, top), (right, bottom)]
        if math.isclose(angle, 180.0, abs_tol=1e-9):
            return [(right, bottom), (left, bottom), (left, top), (right, top)]
        if math.isclose(angle, 270.0, abs_tol=1e-9):
            return [(right, top), (right, bottom), (left, bottom), (left, top)]
        return [(left, top), (right, top), (right, bottom), (left, bottom)]

    def _rotated_offset(self, x: float, y: float) -> Tuple[float, float]:
        radians = math.radians(self.angle)
        cos_a = math.cos(radians)
        sin_a = math.sin(radians)
        return (x * cos_a + y * sin_a, y * cos_a - x * sin_a)

    def _draw_position(self, *, is_flipped: bool = False) -> Tuple[float, float]:
        """Return KiCad's `PCB_TEXTBOX::GetDrawPos()` in millimeters."""

        corners = self._corners_in_sequence()
        mid_top = (
            (corners[0][0] + corners[1][0]) / 2.0,
            (corners[0][1] + corners[1][1]) / 2.0,
        )
        mid_bottom = (
            (corners[3][0] + corners[2][0]) / 2.0,
            (corners[3][1] + corners[2][1]) / 2.0,
        )
        mid_left = (
            (corners[0][0] + corners[3][0]) / 2.0,
            (corners[0][1] + corners[3][1]) / 2.0,
        )
        mid_right = (
            (corners[1][0] + corners[2][0]) / 2.0,
            (corners[1][1] + corners[2][1]) / 2.0,
        )
        center = (
            sum(point[0] for point in corners) / 4.0,
            sum(point[1] for point in corners) / 4.0,
        )

        h_align = self.h_align
        if self.is_mirrored != is_flipped:
            if h_align == 'left':
                h_align = 'right'
            elif h_align == 'right':
                h_align = 'left'
        v_align = self.v_align

        anchors = {
            ('left', 'top'): corners[0],
            ('center', 'top'): mid_top,
            ('right', 'top'): corners[1],
            ('left', 'center'): mid_left,
            ('center', 'center'): center,
            ('right', 'center'): mid_right,
            ('left', 'bottom'): corners[3],
            ('center', 'bottom'): mid_bottom,
            ('right', 'bottom'): corners[2],
        }
        anchor_x, anchor_y = anchors[(h_align, v_align)]

        margin_left, margin_top, margin_right, margin_bottom = self.margins
        offset_x = 0.0
        offset_y = 0.0
        if h_align == 'left':
            offset_x = margin_left
        elif h_align == 'right':
            offset_x = -margin_right
        if v_align == 'top':
            offset_y = margin_top
        elif v_align == 'bottom':
            offset_y = -margin_bottom

        offset_x, offset_y = self._rotated_offset(offset_x, offset_y)
        return (anchor_x + offset_x, anchor_y + offset_y)

    def _wrap_width(self) -> float:
        """Return KiCad's text-box column width in millimeters."""

        corners = self._corners_in_sequence()
        width = math.hypot(
            corners[1][0] - corners[0][0],
            corners[1][1] - corners[0][1],
        )
        angle = self.angle % 360.0
        if math.isclose(angle, 0.0, abs_tol=1e-9) or math.isclose(angle, 180.0, abs_tol=1e-9):
            width -= self.margins[0] + self.margins[2]
        else:
            width -= self.margins[1] + self.margins[3]
        return max(width, 0.0)

    def render_cache_text(self, text: Optional[str] = None) -> str:
        """Return resolved text after KiCad text-box wrapping."""

        from .kicad_geometry import HAlign, TextParams, VAlign
        from .kicad_text import KiCadTextRenderer

        h_align_map = {'left': HAlign.LEFT, 'center': HAlign.CENTER, 'right': HAlign.RIGHT}
        v_align_map = {'top': VAlign.TOP, 'center': VAlign.CENTER, 'bottom': VAlign.BOTTOM}
        font = self.font
        params = TextParams(
            text=self.text if text is None else text,
            font_name=font.face or "Arial",
            size_x=font.size_x,
            size_y=font.size_y,
            stroke_width=font.effective_thickness,
            bold=font.bold,
            italic=font.italic,
            h_align=h_align_map.get(self.h_align, HAlign.LEFT),
            v_align=v_align_map.get(self.v_align, VAlign.CENTER),
            line_spacing=font.line_spacing or 1.0,
            layer=self.layer,
        )
        return KiCadTextRenderer().linebreak_text(params, self._wrap_width())

    def to_text_params(self, text: Optional[str] = None) -> 'TextParams':
        """Convert board text-box content to `TextParams` for outline rendering."""

        from .kicad_geometry import HAlign, TextParams, VAlign

        h_align_map = {'left': HAlign.LEFT, 'center': HAlign.CENTER, 'right': HAlign.RIGHT}
        v_align_map = {'top': VAlign.TOP, 'center': VAlign.CENTER, 'bottom': VAlign.BOTTOM}
        font = self.font
        draw_x, draw_y = self._draw_position()
        wrapped_text = self.render_cache_text(text)

        return TextParams(
            text=wrapped_text,
            font_name=font.face or "Arial",
            size_x=font.size_x,
            size_y=font.size_y,
            position_x=draw_x,
            position_y=draw_y,
            angle=self.angle,
            bold=font.bold,
            italic=font.italic,
            mirrored=self.is_mirrored,
            h_align=h_align_map.get(self.h_align, HAlign.LEFT),
            v_align=v_align_map.get(self.v_align, VAlign.CENTER),
            stroke_width=font.effective_thickness,
            line_spacing=font.line_spacing or 1.0,
            knockout=bool(self.knockout),
            layer=self.layer,
        )

    def _to_poly(self, error: float = 0.005) -> 'PolygonSet':
        """Convert gr_text_box to a PolygonSet (border rectangle only for now)."""
        from .kicad_pcb_polygon_ops import PolygonSet

        # For now, just render the border rectangle
        # Full implementation would also render the text content
        if self.border and self.stroke and self.stroke.width > 0:
            # Create a stroked rectangle
            # For a stroked rectangle, we'd need to create capsules for each edge
            # For simplicity, just return the outline for now
            points = [
                (self.start_x, self.start_y),
                (self.end_x, self.start_y),
                (self.end_x, self.end_y),
                (self.start_x, self.end_y),
            ]
            return PolygonSet(outlines=[points])
        return PolygonSet()

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this text box.."""
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
        """Render this text box to SVG elements..

        Note: Full text rendering requires stroke font support.
        This renders the border only for now.
        """
        from .kicad_geometry import SvgRenderContext

        if ctx is None:
            ctx = SvgRenderContext()

        if not ctx.layer_visible(self.layer):
            return []

        elements = []

        # Render border if enabled
        if self.border:
            x1 = min(self.start_x, self.end_x) + ctx.offset_x
            y1 = min(self.start_y, self.end_y) + ctx.offset_y
            x2 = max(self.start_x, self.end_x) + ctx.offset_x
            y2 = max(self.start_y, self.end_y) + ctx.offset_y
            width = self.stroke.width if self.stroke else 0.12

            elements.append(
                f'<path d="M{ctx.fmt(x1)} {ctx.fmt(y1)} '
                f'L{ctx.fmt(x2)} {ctx.fmt(y1)} L{ctx.fmt(x2)} {ctx.fmt(y2)} '
                f'L{ctx.fmt(x1)} {ctx.fmt(y2)} Z" '
                f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
                f'stroke-linecap:round; stroke-linejoin:round;" />'
            )

        # Text content would be rendered here with stroke font
        # For now, text rendering happens in the board renderer

        return elements


__all__ = [
    'GrText',
    'GrLine',
    'GrRect',
    'GrArc',
    'GrCircle',
    'GrPoly',
    'GrCurve',
    'GrTextBox',
]
