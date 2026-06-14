"""
KiCad Pad Element

One class per file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .kicad_sexpr import QuotedString, SexpList
from typing import TYPE_CHECKING

from .kicad_base import (
    FillType,
    PadType,
    PadShape,
    find_element,
    find_all_elements,
    get_value,
    get_at,
    unquote_string,
)
from .kicad_pcb_other import (
    DrillProps,
    NetRef,
    PostMachiningProps,
    ZoneLayerConnections,
)

if TYPE_CHECKING:
    from .kicad_geometry import BoundingBox, SvgRenderContext


@dataclass
class PadCustomOptions:
    """Custom pad options block: (options (clearance ...) (anchor ...))."""

    clearance: Optional[str] = None
    anchor: Optional[str] = None

    @classmethod
    def from_sexp(cls, sexp: list) -> "PadCustomOptions":
        return cls(
            clearance=unquote_string(get_value(sexp, "clearance")) or None,
            anchor=unquote_string(get_value(sexp, "anchor")) or None,
        )

    def to_sexp(self) -> list:
        result: SexpList = ["options"]
        if self.clearance:
            result.append(["clearance", self.clearance])
        if self.anchor:
            result.append(["anchor", self.anchor])
        return result


def _pad_prim_point(sexp: list, tag: str) -> Optional[Tuple[float, float]]:
    el = find_element(sexp, tag)
    if el and len(el) >= 3:
        return (float(el[1]), float(el[2]))
    return None


def _sample_arc_3pt(start, mid, end, arc_error_mm=0.05):
    """Sample a 3-point arc (start, mid, end) into points within arc_error_mm."""
    import math
    c = _circle_from_3pt(start, mid, end)
    if c is None:
        return [start, end]
    cx, cy, r = c
    if r <= 0:
        return [start, end]
    a0 = math.degrees(math.atan2(start[1] - cy, start[0] - cx))
    am_ = math.degrees(math.atan2(mid[1] - cy, mid[0] - cx))
    a1 = math.degrees(math.atan2(end[1] - cy, end[0] - cx))
    if not (min(a0, a1) <= am_ <= max(a0, a1)):
        a1 += 360.0 if a1 < a0 else -360.0
    err = max(1e-4, min(arc_error_mm, r))
    dphi = 2 * math.acos(max(-1.0, 1 - err / r))
    n = max(2, int(math.ceil(math.radians(abs(a1 - a0)) / max(dphi, 1e-3))))
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _tessellate_pts(pts_elem, arc_error_mm=0.05):
    """Expand a KiCad ``(pts ...)`` element into a flat point list, tessellating
    any embedded ``(arc (start ..)(mid ..)(end ..))`` segments. KiCad polygons
    may interleave ``xy`` vertices and ``arc`` segments."""
    out = []
    for child in pts_elem[1:]:
        if not isinstance(child, list) or not child:
            continue
        tag = str(child[0])
        if tag == "xy" and len(child) >= 3:
            out.append((float(child[1]), float(child[2])))
        elif tag == "arc":
            s = _pad_prim_point(child, "start")
            m = _pad_prim_point(child, "mid")
            e = _pad_prim_point(child, "end")
            if s and m and e:
                seg = _sample_arc_3pt(s, m, e, arc_error_mm)
                out.extend(seg if not out else seg[1:])
    return out


def _circle_from_3pt(p1, p2, p3):
    """Center+radius of the circle through three points, or None if collinear."""
    (ax, ay), (bx, by), (cx, cy) = p1, p2, p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    r = ((ax - ux) ** 2 + (ay - uy) ** 2) ** 0.5
    return (ux, uy, r)


@dataclass
class PadCustomPrimitive:
    """Custom pad primitive.

    Geometry is exposed for every KiCad primitive kind (gr_poly, gr_line,
    gr_rect, gr_circle, gr_arc), matching ``pcb_io_kicad_sexpr_parser.cpp``
    (parsePCB_SHAPE / pad primitive grammar):

    - ``gr_line``  : (start x y) (end x y)
    - ``gr_rect``  : (start x y) (end x y)
    - ``gr_circle``: (center x y) (end x y)         end = a point on the circle
    - ``gr_arc``   : (start x y) (mid x y) (end x y) | (start=center) (end=arc start) (angle deg)
    - ``gr_poly``  : (pts (xy ...) ...)
    """

    primitive_type: str
    points: List[Tuple[float, float]] = field(default_factory=list)
    width: Optional[float] = None
    fill: Optional[FillType] = None
    start: Optional[Tuple[float, float]] = None
    mid: Optional[Tuple[float, float]] = None
    end: Optional[Tuple[float, float]] = None
    center: Optional[Tuple[float, float]] = None
    angle: Optional[float] = None
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> "PadCustomPrimitive":
        primitive_type = str(sexp[0]) if sexp else ""
        points: List[Tuple[float, float]] = []
        width: Optional[float] = None
        fill: Optional[FillType] = None

        pts_elem = find_element(sexp, "pts")
        if pts_elem:
            points = _tessellate_pts(pts_elem)   # handles xy + embedded arc segments

        width_val = get_value(sexp, "width")
        if width_val is not None:
            width = float(width_val)

        fill_val = get_value(sexp, "fill")
        if fill_val is not None:
            fill_s = unquote_string(fill_val)
            if fill_s == "yes":
                fill = FillType.YES
            elif fill_s == "solid":
                fill = FillType.SOLID
            elif fill_s == "no":
                fill = FillType.NO

        angle_val = get_value(sexp, "angle")
        return cls(
            primitive_type=primitive_type,
            points=points,
            width=width,
            fill=fill,
            start=_pad_prim_point(sexp, "start"),
            mid=_pad_prim_point(sexp, "mid"),
            end=_pad_prim_point(sexp, "end"),
            center=_pad_prim_point(sexp, "center"),
            angle=float(angle_val) if angle_val is not None else None,
            _raw_sexp=sexp,
        )

    @property
    def is_filled(self) -> bool:
        """Return True when primitive should be rendered as filled geometry."""
        return self.fill in (FillType.YES, FillType.SOLID)

    def sample_points(self, arc_error_mm: float = 0.05) -> List[Tuple[float, float]]:
        """Tessellate this primitive into a list of (x, y) points in pad-local
        coordinates (mm, KiCad Y-down). Lines/rects/polys are returned exactly;
        circles/arcs are sampled to within ``arc_error_mm``.
        """
        import math

        t = self.primitive_type
        if t == "gr_poly":
            return list(self.points)
        if t == "gr_line":
            return [p for p in (self.start, self.end) if p is not None]
        if t == "gr_rect":
            if self.start and self.end:
                (x1, y1), (x2, y2) = self.start, self.end
                return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            return []

        def _sample_arc(cx, cy, r, a0, a1):
            if r <= 0:
                return []
            sweep = abs(a1 - a0)
            err = max(1e-4, min(arc_error_mm, r))
            dphi = 2 * math.acos(max(-1.0, 1 - err / r))
            n = max(2, int(math.ceil(math.radians(sweep) / max(dphi, 1e-3))))
            return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                     cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
                    for i in range(n + 1)]

        if t == "gr_circle":
            if self.center and self.end:
                cx, cy = self.center
                r = math.hypot(self.end[0] - cx, self.end[1] - cy)
                return _sample_arc(cx, cy, r, 0.0, 360.0)
            return []
        if t == "gr_arc":
            if self.start and self.mid and self.end:
                c = _circle_from_3pt(self.start, self.mid, self.end)
                if c is None:
                    return [self.start, self.end]
                cx, cy, r = c
                a0 = math.degrees(math.atan2(self.start[1] - cy, self.start[0] - cx))
                am_ = math.degrees(math.atan2(self.mid[1] - cy, self.mid[0] - cx))
                a1 = math.degrees(math.atan2(self.end[1] - cy, self.end[0] - cx))
                # ensure the sampled sweep passes through the mid point
                if not (min(a0, a1) <= am_ <= max(a0, a1)):
                    a1 += 360.0 if a1 < a0 else -360.0
                return _sample_arc(cx, cy, r, a0, a1)
            if self.start and self.end and self.angle is not None:
                cx, cy = self.start                 # old form: start == center
                sx, sy = self.end                   # end == arc start point
                r = math.hypot(sx - cx, sy - cy)
                a0 = math.degrees(math.atan2(sy - cy, sx - cx))
                return _sample_arc(cx, cy, r, a0, a0 + self.angle)
            return []
        return list(self.points)

    def to_sexp(self) -> list:
        # Prefer the verbatim parsed sexp for round-trip stability: gr_poly may
        # contain embedded arc segments that `points` has tessellated away, and
        # other primitive kinds are not rebuilt from structured fields.
        if self._raw_sexp is not None:
            return self._raw_sexp
        if self.primitive_type != "gr_poly":
            return [self.primitive_type]

        result: SexpList = [self.primitive_type]
        if self.points:
            result.append(["pts"] + [["xy", x, y] for x, y in self.points])
        if self.width is not None:
            result.append(["width", self.width])
        if self.fill is not None:
            result.append(["fill", self.fill.value])
        return result


@dataclass
class TeardropParameters:
    """Per-pad/per-via teardrop parameters block.

    Mirrors ``TEARDROP_PARAMETERS`` and ``PCB_IO_KICAD_SEXPR::formatTeardropParameters``
    (pcb_io_kicad_sexpr.cpp:781-799). Order of children on emit:
    best_length_ratio, max_length, best_width_ratio, max_width, curved_edges,
    filter_ratio, enabled, allow_two_segments, prefer_zone_connections.
    """

    best_length_ratio: Optional[float] = None
    max_length: Optional[float] = None
    best_width_ratio: Optional[float] = None
    max_width: Optional[float] = None
    curved_edges: Optional[bool] = None
    filter_ratio: Optional[float] = None
    enabled: Optional[bool] = None
    allow_two_segments: Optional[bool] = None
    prefer_zone_connections: Optional[bool] = None

    @classmethod
    def from_sexp(cls, sexp: Optional[list]) -> Optional["TeardropParameters"]:
        if sexp is None:
            return None

        def _f(name: str) -> Optional[float]:
            v = get_value(sexp, name)
            return float(v) if v is not None else None

        def _b(name: str) -> Optional[bool]:
            v = get_value(sexp, name)
            if v is None:
                return None
            return unquote_string(v).lower() in ("yes", "true", "1")

        return cls(
            best_length_ratio=_f("best_length_ratio"),
            max_length=_f("max_length"),
            best_width_ratio=_f("best_width_ratio"),
            max_width=_f("max_width"),
            curved_edges=_b("curved_edges"),
            filter_ratio=_f("filter_ratio"),
            enabled=_b("enabled"),
            allow_two_segments=_b("allow_two_segments"),
            prefer_zone_connections=_b("prefer_zone_connections"),
        )

    def to_sexp(self) -> list:
        result: list = ["teardrops"]
        if self.best_length_ratio is not None:
            result.append(["best_length_ratio", self.best_length_ratio])
        if self.max_length is not None:
            result.append(["max_length", self.max_length])
        if self.best_width_ratio is not None:
            result.append(["best_width_ratio", self.best_width_ratio])
        if self.max_width is not None:
            result.append(["max_width", self.max_width])
        if self.curved_edges is not None:
            result.append(["curved_edges", "yes" if self.curved_edges else "no"])
        if self.filter_ratio is not None:
            result.append(["filter_ratio", self.filter_ratio])
        if self.enabled is not None:
            result.append(["enabled", "yes" if self.enabled else "no"])
        if self.allow_two_segments is not None:
            result.append(["allow_two_segments", "yes" if self.allow_two_segments else "no"])
        if self.prefer_zone_connections is not None:
            result.append(["prefer_zone_connections", "yes" if self.prefer_zone_connections else "no"])
        return result


@dataclass
class Pad:
    """Footprint pad."""
    number: str
    pad_type: PadType
    shape: PadShape
    at_x: float
    at_y: float
    at_angle: float = 0.0
    size_x: float = 0.0
    size_y: float = 0.0
    drill: Optional[float] = None
    drill_oval: bool = False
    drill_width: Optional[float] = None
    drill_height: Optional[float] = None
    drill_offset_x: Optional[float] = None
    drill_offset_y: Optional[float] = None
    layers: List[str] = field(default_factory=list)
    net: NetRef = field(default_factory=NetRef)
    uuid: Optional[str] = None
    pinfunction: Optional[str] = None
    pintype: Optional[str] = None
    die_length: Optional[float] = None
    rect_delta_x: Optional[float] = None
    rect_delta_y: Optional[float] = None
    roundrect_rratio: Optional[float] = None
    chamfer_ratio: Optional[float] = None
    chamfer_corners: List[str] = field(default_factory=list)
    solder_mask_margin: Optional[float] = None
    solder_paste_margin: Optional[float] = None
    solder_paste_margin_ratio: Optional[float] = None
    clearance: Optional[float] = None
    thermal_bridge_width: Optional[float] = None
    thermal_bridge_angle: Optional[float] = None
    thermal_gap: Optional[float] = None
    teardrops: Optional[TeardropParameters] = None
    zone_connect: Optional[int] = None
    remove_unused_layers: Optional[bool] = None
    keep_end_layers: Optional[bool] = None
    backdrill: Optional[DrillProps] = None
    tertiary_drill: Optional[DrillProps] = None
    front_post_machining: Optional[PostMachiningProps] = None
    back_post_machining: Optional[PostMachiningProps] = None
    zone_layer_connections: Optional[ZoneLayerConnections] = None
    custom_options: Optional[PadCustomOptions] = None
    custom_primitives: List[PadCustomPrimitive] = field(default_factory=list)
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'Pad':
        number = unquote_string(sexp[1])
        pad_type = PadType(sexp[2])
        shape = PadShape(sexp[3])
        x, y, angle = get_at(sexp)

        size = find_element(sexp, 'size')
        size_x = float(size[1]) if size else 0.0
        size_y = float(size[2]) if size else 0.0

        # Parse drill - can be (drill SIZE) or (drill oval WIDTH HEIGHT)
        drill_elem = find_element(sexp, 'drill')
        drill = None
        drill_oval = False
        drill_width = None
        drill_height = None
        drill_offset_x = None
        drill_offset_y = None
        if drill_elem and len(drill_elem) > 1:
            if drill_elem[1] == 'oval':
                drill_oval = True
                numeric_values: list[float] = []
                for item in drill_elem[2:]:
                    if isinstance(item, list):
                        if len(item) >= 3 and item[0] == "offset":
                            drill_offset_x = float(item[1])
                            drill_offset_y = float(item[2])
                        continue
                    numeric_values.append(float(item))
                drill_width = numeric_values[0] if numeric_values else None
                drill_height = numeric_values[1] if len(numeric_values) > 1 else None
                drill = drill_width  # Use width as primary drill size
            else:
                try:
                    drill = float(drill_elem[1])
                except (ValueError, TypeError):
                    pass  # Could be other drill options
                for item in drill_elem[2:]:
                    if isinstance(item, list) and len(item) >= 3 and item[0] == "offset":
                        drill_offset_x = float(item[1])
                        drill_offset_y = float(item[2])

        layers_elem = find_element(sexp, 'layers')
        layers = [unquote_string(layer) for layer in layers_elem[1:]] if layers_elem else []

        net_elem = find_element(sexp, 'net')
        net = NetRef.from_pad_sexp(net_elem)

        uuid = unquote_string(get_value(sexp, 'uuid'))
        pinfunction = unquote_string(get_value(sexp, "pinfunction"))
        pintype = unquote_string(get_value(sexp, "pintype"))

        die_length = None
        die_length_elem = find_element(sexp, "die_length")
        if die_length_elem and len(die_length_elem) > 1:
            die_length = float(die_length_elem[1])

        rect_delta_x = None
        rect_delta_y = None
        rect_delta_elem = find_element(sexp, "rect_delta")
        if rect_delta_elem and len(rect_delta_elem) > 2:
            rect_delta_x = float(rect_delta_elem[1])
            rect_delta_y = float(rect_delta_elem[2])

        # Parse roundrect_rratio for roundrect pads
        roundrect_rratio = None
        rratio_elem = find_element(sexp, 'roundrect_rratio')
        if rratio_elem and len(rratio_elem) > 1:
            roundrect_rratio = float(rratio_elem[1])

        chamfer_ratio = None
        chamfer_ratio_elem = find_element(sexp, "chamfer_ratio")
        if chamfer_ratio_elem and len(chamfer_ratio_elem) > 1:
            chamfer_ratio = float(chamfer_ratio_elem[1])

        chamfer_corners: List[str] = []
        chamfer_elem = find_element(sexp, "chamfer")
        if chamfer_elem and len(chamfer_elem) > 1:
            chamfer_corners = [unquote_string(corner) for corner in chamfer_elem[1:]]

        solder_mask_margin = None
        solder_mask_margin_elem = find_element(sexp, "solder_mask_margin")
        if solder_mask_margin_elem and len(solder_mask_margin_elem) > 1:
            solder_mask_margin = float(solder_mask_margin_elem[1])

        solder_paste_margin = None
        solder_paste_margin_elem = find_element(sexp, "solder_paste_margin")
        if solder_paste_margin_elem and len(solder_paste_margin_elem) > 1:
            solder_paste_margin = float(solder_paste_margin_elem[1])

        solder_paste_margin_ratio = None
        solder_paste_margin_ratio_elem = find_element(sexp, "solder_paste_margin_ratio")
        if solder_paste_margin_ratio_elem and len(solder_paste_margin_ratio_elem) > 1:
            solder_paste_margin_ratio = float(solder_paste_margin_ratio_elem[1])

        clearance = None
        clearance_elem = find_element(sexp, "clearance")
        if clearance_elem and len(clearance_elem) > 1:
            try:
                clearance = float(clearance_elem[1])
            except (ValueError, TypeError):
                clearance = None  # PadCustomOptions handles "convexhull"/"outline" tokens.

        thermal_bridge_width = None
        thermal_bridge_width_elem = find_element(sexp, "thermal_bridge_width")
        if thermal_bridge_width_elem and len(thermal_bridge_width_elem) > 1:
            thermal_bridge_width = float(thermal_bridge_width_elem[1])

        thermal_bridge_angle = None
        thermal_bridge_angle_elem = find_element(sexp, "thermal_bridge_angle")
        if thermal_bridge_angle_elem and len(thermal_bridge_angle_elem) > 1:
            thermal_bridge_angle = float(thermal_bridge_angle_elem[1])

        thermal_gap = None
        thermal_gap_elem = find_element(sexp, "thermal_gap")
        if thermal_gap_elem and len(thermal_gap_elem) > 1:
            thermal_gap = float(thermal_gap_elem[1])

        teardrops = TeardropParameters.from_sexp(find_element(sexp, "teardrops"))

        zone_connect = None
        zone_connect_elem = find_element(sexp, "zone_connect")
        if zone_connect_elem and len(zone_connect_elem) > 1:
            zone_connect = int(zone_connect_elem[1])

        remove_unused_layers = None
        remove_unused_layers_elem = find_element(sexp, "remove_unused_layers")
        if remove_unused_layers_elem is not None:
            if len(remove_unused_layers_elem) > 1:
                remove_unused_layers = str(remove_unused_layers_elem[1]).lower() in ("yes", "true", "1")
            else:
                remove_unused_layers = True

        keep_end_layers = None
        keep_end_layers_elem = find_element(sexp, "keep_end_layers")
        if keep_end_layers_elem is not None:
            if len(keep_end_layers_elem) > 1:
                keep_end_layers = str(keep_end_layers_elem[1]).lower() in ("yes", "true", "1")
            else:
                keep_end_layers = True

        backdrill = None
        parsed_backdrill = DrillProps.from_sexp(find_element(sexp, "backdrill"))
        if parsed_backdrill:
            backdrill = parsed_backdrill

        tertiary_drill = None
        parsed_tertiary_drill = DrillProps.from_sexp(find_element(sexp, "tertiary_drill"))
        if parsed_tertiary_drill:
            tertiary_drill = parsed_tertiary_drill

        front_post_machining = None
        parsed_front_post_machining = PostMachiningProps.from_sexp(
            find_element(sexp, "front_post_machining")
        )
        if parsed_front_post_machining:
            front_post_machining = parsed_front_post_machining

        back_post_machining = None
        parsed_back_post_machining = PostMachiningProps.from_sexp(
            find_element(sexp, "back_post_machining")
        )
        if parsed_back_post_machining:
            back_post_machining = parsed_back_post_machining

        zone_layer_connections = None
        zone_layer_connections_elem = find_element(sexp, "zone_layer_connections")
        if zone_layer_connections_elem is not None:
            zone_layer_connections = ZoneLayerConnections.from_sexp(zone_layer_connections_elem)

        custom_options = None
        options_elem = find_element(sexp, "options")
        if options_elem:
            custom_options = PadCustomOptions.from_sexp(options_elem)

        custom_primitives: List[PadCustomPrimitive] = []
        primitives_elem = find_element(sexp, "primitives")
        if primitives_elem:
            for primitive_elem in primitives_elem[1:]:
                if isinstance(primitive_elem, list) and len(primitive_elem) > 0:
                    custom_primitives.append(PadCustomPrimitive.from_sexp(primitive_elem))

        return cls(
            number=number, pad_type=pad_type, shape=shape,
            at_x=x, at_y=y, at_angle=angle,
            size_x=size_x, size_y=size_y,
            drill=drill, drill_oval=drill_oval,
            drill_width=drill_width, drill_height=drill_height,
            drill_offset_x=drill_offset_x, drill_offset_y=drill_offset_y,
            layers=layers, net=net, uuid=uuid,
            pinfunction=pinfunction,
            pintype=pintype,
            die_length=die_length,
            rect_delta_x=rect_delta_x,
            rect_delta_y=rect_delta_y,
            roundrect_rratio=roundrect_rratio,
            chamfer_ratio=chamfer_ratio,
            chamfer_corners=chamfer_corners,
            solder_mask_margin=solder_mask_margin,
            solder_paste_margin=solder_paste_margin,
            solder_paste_margin_ratio=solder_paste_margin_ratio,
            clearance=clearance,
            thermal_bridge_width=thermal_bridge_width,
            thermal_bridge_angle=thermal_bridge_angle,
            thermal_gap=thermal_gap,
            teardrops=teardrops,
            zone_connect=zone_connect,
            remove_unused_layers=remove_unused_layers,
            keep_end_layers=keep_end_layers,
            backdrill=backdrill,
            tertiary_drill=tertiary_drill,
            front_post_machining=front_post_machining,
            back_post_machining=back_post_machining,
            zone_layer_connections=zone_layer_connections,
            custom_options=custom_options,
            custom_primitives=custom_primitives,
            _raw_sexp=sexp
        )

    def get_bounds(self) -> 'BoundingBox':
        """Get bounding box of this pad.."""
        from .kicad_geometry import BoundingBox, rotate_point

        half_w = self.size_x / 2
        half_h = self.size_y / 2

        if self.shape == PadShape.CIRCLE:
            # Circle uses width as diameter
            r = half_w
            return BoundingBox(
                min_x=self.at_x - r,
                min_y=self.at_y - r,
                max_x=self.at_x + r,
                max_y=self.at_y + r
            )
        elif self.shape == PadShape.OVAL:
            # For oval, use larger dimension as radius (conservative)
            r = max(half_w, half_h)
            return BoundingBox(
                min_x=self.at_x - r,
                min_y=self.at_y - r,
                max_x=self.at_x + r,
                max_y=self.at_y + r
            )
        elif self.shape == PadShape.CUSTOM and self.custom_primitives:
            bbox = BoundingBox()
            for primitive in self.custom_primitives:
                if primitive.primitive_type != "gr_poly" or not primitive.points:
                    continue
                hw = (primitive.width or 0.0) / 2.0
                for px, py in primitive.points:
                    if self.at_angle != 0:
                        px, py = rotate_point(px, py, -self.at_angle)
                    gx = px + self.at_x
                    gy = py + self.at_y
                    bbox.expand((gx - hw, gy - hw))
                    bbox.expand((gx + hw, gy + hw))
            if bbox.is_valid():
                return bbox
            return BoundingBox(
                min_x=self.at_x - half_w,
                min_y=self.at_y - half_h,
                max_x=self.at_x + half_w,
                max_y=self.at_y + half_h,
            )

        elif self.shape == PadShape.TRAPEZOID:
            bbox = BoundingBox()
            for x, y in self._to_trapezoid_polygon(self.at_x, self.at_y):
                bbox.expand((x, y))
            return bbox

        else:
            # Rectangle, RoundRect - compute rotated corners
            corners = [
                (-half_w, -half_h),
                (half_w, -half_h),
                (half_w, half_h),
                (-half_w, half_h),
            ]
            if self.at_angle != 0:
                corners = [rotate_point(x, y, -self.at_angle) for x, y in corners]

            bbox = BoundingBox()
            for x, y in corners:
                bbox.expand((x + self.at_x, y + self.at_y))
            return bbox

    def to_svg(self, ctx: 'SvgRenderContext | None' = None) -> List[str]:
        """Render this pad to SVG elements.."""
        from .kicad_geometry import SvgRenderContext, rotate_point

        if ctx is None:
            ctx = SvgRenderContext()

        # Check layer visibility
        if ctx.layers is not None:
            visible = False
            for layer in ctx.layers:
                if self._on_layer(layer):
                    visible = True
                    break
            if not visible:
                return []

        # Apply context offset
        pad_x = self.at_x + ctx.offset_x
        pad_y = self.at_y + ctx.offset_y

        elements = []

        if self.shape == PadShape.CIRCLE:
            # Native SVG circle
            r = self.size_x / 2
            elements.append(
                f'<circle cx="{ctx.fmt(pad_x)}" cy="{ctx.fmt(pad_y)}" r="{ctx.fmt(r)}" '
                f'style="fill:{ctx.fill}; fill-opacity:1.0; stroke:none;" />'
            )

        elif self.shape == PadShape.OVAL:
            # Oval is rendered as thick stroked line
            start, end, width = self._to_oval_segment(pad_x, pad_y)
            elements.append(
                f'<path d="M{ctx.fmt(start[0])} {ctx.fmt(start[1])} '
                f'L{ctx.fmt(end[0])} {ctx.fmt(end[1])}" '
                f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
                f'stroke-linecap:round; stroke-linejoin:round;" />'
            )

        elif self.shape == PadShape.CUSTOM and self.custom_primitives:
            for primitive in self.custom_primitives:
                if primitive.primitive_type != "gr_poly" or not primitive.points:
                    continue

                poly_points = []
                for x, y in primitive.points:
                    if self.at_angle != 0:
                        x, y = rotate_point(x, y, -self.at_angle)
                    poly_points.append((x + pad_x, y + pad_y))

                if not poly_points:
                    continue

                path_d = self._points_to_path(poly_points, ctx)
                if primitive.is_filled:
                    elements.append(
                        f'<path d="{path_d}" '
                        f'style="fill:{ctx.fill}; fill-opacity:1.0; stroke:none; fill-rule:evenodd;" />'
                    )
                else:
                    width = primitive.width if primitive.width and primitive.width > 0 else 0.01
                    elements.append(
                        f'<path d="{path_d}" '
                        f'style="fill:none; stroke:{ctx.stroke}; stroke-width:{ctx.fmt(width)}; '
                        f'stroke-linecap:round; stroke-linejoin:round;" />'
                    )

        elif self.shape == PadShape.ROUNDRECT:
            # Polygon with rounded corners
            points = self._to_roundrect_polygon(pad_x, pad_y, ctx.arc_error_mm)
            path_d = self._points_to_path(points, ctx)
            elements.append(
                f'<path d="{path_d}" '
                f'style="fill:{ctx.fill}; fill-opacity:1.0; stroke:none; fill-rule:evenodd;" />'
            )

        elif self.shape == PadShape.TRAPEZOID:
            points = self._to_trapezoid_polygon(pad_x, pad_y)
            path_d = self._points_to_path(points, ctx)
            elements.append(
                f'<path d="{path_d}" '
                f'style="fill:{ctx.fill}; fill-opacity:1.0; stroke:none; fill-rule:evenodd;" />'
            )

        else:
            # Default: rectangle
            points = self._to_rect_polygon(pad_x, pad_y)
            path_d = self._points_to_path(points, ctx)
            elements.append(
                f'<path d="{path_d}" '
                f'style="fill:{ctx.fill}; fill-opacity:1.0; stroke:none; fill-rule:evenodd;" />'
            )

        return elements

    def _on_layer(self, layer: str) -> bool:
        """Check if pad is on specified layer."""
        if layer in self.layers:
            return True
        if layer.endswith(".Cu") and "*.Cu" in self.layers:
            return True
        if layer.endswith(".Mask") and "*.Mask" in self.layers:
            return True
        if layer.endswith(".Paste") and "*.Paste" in self.layers:
            return True
        return False

    def _to_rect_polygon(self, cx: float, cy: float) -> List[Tuple[float, float]]:
        """Convert rectangle pad to polygon corners."""
        from .kicad_geometry import rotate_point

        half_w = self.size_x / 2
        half_h = self.size_y / 2

        # KiCad order: bottom-left, top-left, top-right, bottom-right (CCW)
        corners = [
            (-half_w, half_h),
            (-half_w, -half_h),
            (half_w, -half_h),
            (half_w, half_h),
        ]

        if self.at_angle != 0:
            corners = [rotate_point(x, y, -self.at_angle) for x, y in corners]

        return [(x + cx, y + cy) for x, y in corners]

    def _to_trapezoid_polygon(self, cx: float, cy: float) -> List[Tuple[float, float]]:
        """Convert trapezoid pad to polygon corners using KiCad's rect_delta math."""
        from .kicad_geometry import rotate_point

        half_w = self.size_x / 2
        half_h = self.size_y / 2
        delta_x = (self.rect_delta_x or 0.0) / 2
        delta_y = (self.rect_delta_y or 0.0) / 2

        corners = [
            (-half_w - delta_y, half_h + delta_x),
            (half_w + delta_y, half_h - delta_x),
            (half_w - delta_y, -half_h + delta_x),
            (-half_w + delta_y, -half_h - delta_x),
        ]

        if self.at_angle != 0:
            corners = [rotate_point(x, y, -self.at_angle) for x, y in corners]

        return [(x + cx, y + cy) for x, y in corners]

    def _to_oval_segment(self, cx: float, cy: float) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
        """Convert oval pad to thick segment (start, end, width)."""
        from .kicad_geometry import rotate_point

        w = self.size_x
        h = self.size_y
        angle = self.at_angle

        if w > h:
            w, h = h, w
            angle = angle + 90

        delta = h - w
        a = (0, -delta / 2)
        b = (0, delta / 2)

        if angle != 0:
            a = rotate_point(a[0], a[1], -angle)
            b = rotate_point(b[0], b[1], -angle)

        return ((a[0] + cx, a[1] + cy), (b[0] + cx, b[1] + cy), w)

    def _to_roundrect_polygon(self, cx: float, cy: float, error_mm: float = 0.005) -> List[Tuple[float, float]]:
        """Convert roundrect pad to polygon with rounded corners."""
        from .kicad_geometry import rotate_point, get_arc_to_segment_count
        import math

        half_w = self.size_x / 2
        half_h = self.size_y / 2

        rratio = self.roundrect_rratio if self.roundrect_rratio is not None else 0.25
        r = min(self.size_x, self.size_y) * rratio

        # KiCad chamfered roundrects are commonly modeled as roundrect_rratio=0
        # plus chamfer_* fields. Render those as explicit chamfer polygons.
        chamfer_points = self._to_chamfered_rect_polygon(cx, cy)
        if chamfer_points is not None and r < 0.001:
            return chamfer_points

        if r < 0.001:
            return self._to_rect_polygon(cx, cy)

        # KiCad CornerListToPolygon enforces at least 16 segments for full-circle
        # arc approximation when building rounded corners.
        num_segs = max(16, get_arc_to_segment_count(r, error_mm, 360.0))
        ang_delta = 360.0 / num_segs
        end_angle = 90.0

        last_seg = end_angle
        while last_seg > ang_delta:
            last_seg -= ang_delta

        ang_pos_start = (ang_delta + last_seg) / 2 if abs(last_seg) >= 0.001 else ang_delta

        corners = []
        corner_centers = [
            (-half_w + r, -half_h + r),
            (half_w - r, -half_h + r),
            (half_w - r, half_h - r),
            (-half_w + r, half_h - r),
        ]
        arc_start_angles = [180, 270, 0, 90]

        for corner_idx in range(4):
            ccx, ccy = corner_centers[corner_idx]
            arc_start = arc_start_angles[corner_idx]

            angle_rad = math.radians(arc_start)
            corners.append((ccx + r * math.cos(angle_rad), ccy + r * math.sin(angle_rad)))

            ang_pos = ang_pos_start
            while ang_pos < end_angle - 0.001:
                angle_deg = arc_start + ang_pos
                angle_rad = math.radians(angle_deg)
                corners.append((ccx + r * math.cos(angle_rad), ccy + r * math.sin(angle_rad)))
                ang_pos += ang_delta

            angle_rad = math.radians(arc_start + end_angle)
            corners.append((ccx + r * math.cos(angle_rad), ccy + r * math.sin(angle_rad)))

        if self.at_angle != 0:
            corners = [rotate_point(x, y, -self.at_angle) for x, y in corners]

        return [(x + cx, y + cy) for x, y in corners]

    def _to_chamfered_rect_polygon(self, cx: float, cy: float) -> Optional[List[Tuple[float, float]]]:
        """Convert chamfered roundrect pad to polygon for rratio=0 shapes."""
        from .kicad_geometry import rotate_point

        if not self.chamfer_corners:
            return None

        chamfer_ratio = self.chamfer_ratio if self.chamfer_ratio is not None else 0.0
        if chamfer_ratio <= 0:
            return None

        half_w = self.size_x / 2
        half_h = self.size_y / 2
        shorter_side = min(self.size_x, self.size_y)
        chamfer = max(0.0, chamfer_ratio * shorter_side)

        corners = [
            {"x": -half_w, "y": -half_h},  # top-left
            {"x": half_w, "y": -half_h},   # top-right
            {"x": half_w, "y": half_h},    # bottom-right
            {"x": -half_w, "y": half_h},   # bottom-left
        ]

        chamfer_set = set(self.chamfer_corners)
        corner_names = ["top_left", "top_right", "bottom_right", "bottom_left"]
        sign = [0, 1, -1, 0, 0, -1, 1, 0]

        chamfer_count = sum(1 for name in corner_names if name in chamfer_set)
        pos = 0
        for cc, name in enumerate(corner_names):
            if name not in chamfer_set:
                pos += 1
                continue

            if chamfer == 0:
                pos += 1
                continue

            corners.insert(pos + 1, dict(corners[pos]))
            corners[pos]["x"] += sign[(2 * cc) & 7] * chamfer
            corners[pos]["y"] += sign[(2 * cc - 2) & 7] * chamfer
            corners[pos + 1]["x"] += sign[(2 * cc + 1) & 7] * chamfer
            corners[pos + 1]["y"] += sign[(2 * cc - 1) & 7] * chamfer
            pos += 2

        if chamfer_count > 1 and 2 * chamfer >= shorter_side:
            dedup: List[dict[str, float]] = []
            for pt in corners:
                if not dedup:
                    dedup.append(pt)
                    continue
                if abs(pt["x"] - dedup[-1]["x"]) > 1e-9 or abs(pt["y"] - dedup[-1]["y"]) > 1e-9:
                    dedup.append(pt)
            if len(dedup) > 1 and abs(dedup[0]["x"] - dedup[-1]["x"]) < 1e-9 and abs(dedup[0]["y"] - dedup[-1]["y"]) < 1e-9:
                dedup.pop()
            corners = dedup

        points = [(pt["x"], pt["y"]) for pt in corners]
        if self.at_angle != 0:
            points = [rotate_point(x, y, -self.at_angle) for x, y in points]
        return [(x + cx, y + cy) for x, y in points]

    def _points_to_path(self, points: List[Tuple[float, float]], ctx: 'SvgRenderContext') -> str:
        """Convert points to SVG path d attribute."""
        if not points:
            return ""
        path_d = f"M {ctx.fmt(points[0][0])},{ctx.fmt(points[0][1])}\n"
        for x, y in points[1:]:
            path_d += f"{ctx.fmt(x)},{ctx.fmt(y)}\n"
        path_d += "Z"
        return path_d

    def to_sexp(self) -> list:
        result = ['pad', QuotedString(self.number), self.pad_type.value, self.shape.value]

        # KiCad's reader requires the angle slot even when zero (drift inventory #1).
        result.append(['at', self.at_x, self.at_y, self.at_angle])

        result.append(['size', self.size_x, self.size_y])

        if self.rect_delta_x is not None and self.rect_delta_y is not None:
            result.append(["rect_delta", self.rect_delta_x, self.rect_delta_y])
        if self.roundrect_rratio is not None:
            result.append(['roundrect_rratio', self.roundrect_rratio])
        if self.chamfer_ratio is not None:
            result.append(["chamfer_ratio", self.chamfer_ratio])
        if self.chamfer_corners:
            result.append(["chamfer"] + self.chamfer_corners)

        if self.drill_oval and self.drill_width is not None:
            drill_elem = ['drill', 'oval', self.drill_width]
            if self.drill_height is not None:
                drill_elem.append(self.drill_height)
            if self.drill_offset_x is not None and self.drill_offset_y is not None:
                drill_elem.append(['offset', self.drill_offset_x, self.drill_offset_y])
            result.append(drill_elem)
        elif self.drill is not None:
            drill_elem = ['drill', self.drill]
            if self.drill_offset_x is not None and self.drill_offset_y is not None:
                drill_elem.append(['offset', self.drill_offset_x, self.drill_offset_y])
            result.append(drill_elem)

        result.append(['layers'] + [QuotedString(layer) for layer in self.layers])

        net_elem = self.net.to_pad_sexp()
        if net_elem:
            result.append(net_elem)

        if self.pinfunction:
            result.append(["pinfunction", QuotedString(self.pinfunction)])
        if self.pintype:
            result.append(["pintype", QuotedString(self.pintype)])
        if self.die_length is not None:
            result.append(["die_length", self.die_length])
        if self.solder_mask_margin is not None:
            result.append(["solder_mask_margin", self.solder_mask_margin])
        if self.solder_paste_margin is not None:
            result.append(["solder_paste_margin", self.solder_paste_margin])
        if self.solder_paste_margin_ratio is not None:
            result.append(["solder_paste_margin_ratio", self.solder_paste_margin_ratio])
        # Order matches pcb_io_kicad_sexpr.cpp:1936-1973: clearance, zone_connect,
        # thermal_bridge_width, thermal_bridge_angle, thermal_gap.
        if self.clearance is not None:
            result.append(["clearance", self.clearance])
        if self.zone_connect is not None:
            result.append(["zone_connect", self.zone_connect])
        if self.thermal_bridge_width is not None:
            result.append(["thermal_bridge_width", self.thermal_bridge_width])
        if self.thermal_bridge_angle is not None:
            result.append(["thermal_bridge_angle", self.thermal_bridge_angle])
        if self.thermal_gap is not None:
            result.append(["thermal_gap", self.thermal_gap])
        if self.remove_unused_layers is not None:
            if self.remove_unused_layers:
                result.append(["remove_unused_layers"])
            else:
                result.append(["remove_unused_layers", "no"])
        if self.keep_end_layers is not None:
            if self.keep_end_layers:
                result.append(["keep_end_layers"])
            else:
                result.append(["keep_end_layers", "no"])
        if self.backdrill:
            result.append(self.backdrill.to_sexp("backdrill"))
        if self.tertiary_drill:
            result.append(self.tertiary_drill.to_sexp("tertiary_drill"))
        if self.front_post_machining:
            result.append(self.front_post_machining.to_sexp("front_post_machining"))
        if self.back_post_machining:
            result.append(self.back_post_machining.to_sexp("back_post_machining"))
        if self.zone_layer_connections is not None:
            result.append(self.zone_layer_connections.to_sexp())

        if self.custom_options:
            result.append(self.custom_options.to_sexp())

        if self.custom_primitives:
            primitives_elem: SexpList = ["primitives"]
            for primitive in self.custom_primitives:
                primitives_elem.append(primitive.to_sexp())
            result.append(primitives_elem)

        # Per pcb_io_kicad_sexpr.cpp:2104, (teardrops ...) is emitted after the
        # custom-shape primitives block (only when non-default).
        if self.teardrops is not None:
            result.append(self.teardrops.to_sexp())

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        return result
