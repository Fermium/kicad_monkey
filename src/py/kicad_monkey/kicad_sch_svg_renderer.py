"""
KiCad schematic / symbol SVG renderer.

Phase F-2 ships the *primitive* layer: flat ``svg_*`` functions, the
mutable :class:`KiCadSvgRenderContext` (transforms, defaults, options
slot, font manager hook) and the :class:`KiCadSvgRenderOptions`
dataclass with named factories for the common output profiles. No
parser integration yet -- the higher-level
``render_schematic_svg(...)`` and ``render_ir_to_svg(...)`` entry
points land in F-4 / F-5.

API shape mirrors ``altium_monkey.altium_sch_svg_renderer``: each
primitive is a module-level function returning an SVG fragment string,
both renderer entry points share these helpers, and option presets
plug into a single ``ctx.options`` slot.

Coordinates received by every ``svg_*`` function are KiCad internal
units (nm, ``int``). The context's ``scale`` (user-units per nm) and
``offset_*_nm`` are applied on emission. ``flip_y`` mirrors the Y
axis around ``sheet_height_nm`` when set.
"""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Iterable

from .kicad_plotter_ir import (
    KiCadFillType,
    KiCadHorizAlign,
    KiCadLineStyle,
    KiCadVertAlign,
)


# =============================================================================
# Options
# =============================================================================


class KiCadJunctionZOrder(Enum):
    """Where to render schematic junction dots in the Z stack."""

    NATIVE = auto()           # match kicad-cli order (inline with wires)
    ALWAYS_ON_TOP = auto()    # collect and render after all wires (cleaner)


class KiCadVariantDimMode(Enum):
    """How DNP / exclude-from-bom items are visually dimmed."""

    NONE = auto()             # no overlay
    DIM_OVERLAY = auto()      # draw a translucent rectangle over the item
    GREYSCALE = auto()        # convert item colour to greyscale


@dataclass
class KiCadSvgRenderOptions:
    """
    Top-level rendering knobs. Mutable so callers can tweak after
    construction. The named factories below cover the common profiles.
    """

    # ---- output unit selection ----
    # Multiplier from KiCad nm to SVG user units. Default = 1e-6 emits
    # millimetres (KiCad internal-unit nanometres / 1e6 = mm), which
    # matches kicad-cli's default mm-based viewBox.
    output_unit_per_nm: float = 1e-6
    # SVG width/height suffix ("mm", "in", "px", ""). Empty string
    # emits unitless dimensions (raw user units).
    output_unit_suffix: str = "mm"

    # ---- colour / theme ----
    # When True, force black-on-white (parity with `kicad-cli sch
    # export svg --black-and-white`). When False, honour per-item
    # colours.
    black_and_white: bool = False
    # Background fill colour for the page rect; ``None`` skips the
    # background.
    background_color: str | None = "#FFFFFF"
    # Optional colour remap keyed by source SVG colour.  This lets callers
    # apply KiCad colour-theme preferences without altering IR payloads.
    color_overrides: dict[str, str] | None = None
    # Optional fallback colours used when an IR op does not carry an
    # explicit fill/stroke colour. PCB SVG uses these to preserve the
    # public ``to_svg(fill=..., stroke=..., black_and_white=False)`` API.
    default_fill_color: str | None = None
    default_stroke_color: str | None = None
    # Optional PCB layer filter.  ``None`` renders all layers; a sequence
    # restricts IR rendering to matching PCB layers such as ``F.Cu`` or
    # ``F.SilkS``. Schematic rendering ignores this unless records carry
    # layer metadata.
    visible_layers: tuple[str, ...] | list[str] | None = None

    # ---- text rendering ----
    # When True, emit text glyphs as SVG ``<path>`` polygons via font
    # tessellation. When False (default), emit standard ``<text>``
    # nodes.
    text_as_polygons: bool = False
    # When True, ``svg_text_poly`` emits one SVG element per individual
    # line segment of each Hershey glyph stroke (matches ``kicad-cli pcb
    # export svg`` granularity, which records one ``MoveTo``/``LineTo``
    # pair per segment). When False (default), each stroke is emitted
    # as a single ``<polyline>`` — fewer DOM nodes but coarser-grained
    # than CLI for structural parity. ``render_pcb_ir_to_svg`` flips
    # this to True so PCB IR output reaches per-segment parity with
    # the canonical CLI SVG.
    text_polyline_per_segment: bool = False
    # Polygon flatten tolerance in nm (smaller = smoother + larger).
    polygon_text_tolerance_nm: int = 5_000
    # Legacy compatibility flag for older KiCad SVG baseline experiments.
    # Standard SVG text now always emits KiCad-compatible font metrics.
    truncate_font_size_for_baseline: bool = False
    # Optional visual font override.  When set, emitted SVG text and
    # textLength metrics use this face instead of per-item/default faces.
    font_face_override: str | None = None

    # ---- bezier rendering ----
    # When True, flatten beziers to line segments. When False, emit
    # SVG cubic Bezier ``C`` commands.
    bezier_as_lines: bool = False
    # Number of line segments when ``bezier_as_lines`` is True.
    bezier_segment_count: int = 32

    # ---- junction handling ----
    junction_z_order: KiCadJunctionZOrder = KiCadJunctionZOrder.ALWAYS_ON_TOP
    junction_color_override: str | None = None

    # ---- variant-aware overlay (Phase F-8 hook) ----
    variant_dim_mode: KiCadVariantDimMode = KiCadVariantDimMode.NONE
    variant_dim_color: str = "#FFFFFF"
    variant_dim_opacity: float = 0.6

    # ---- metadata ----
    # When True, primitives that have a UUID / reference designator
    # add ``data-uuid`` / ``data-ref`` attributes for downstream
    # tooling (sch-viz / pcb-viz).
    include_metadata: bool = False
    include_ids: bool = False

    # ---- xml header ----
    include_xml_declaration: bool = True

    # ---- factories ----

    @classmethod
    def kicad_native(cls) -> "KiCadSvgRenderOptions":
        """Match ``kicad-cli sch export svg`` defaults."""
        return cls(
            black_and_white=False,
            text_as_polygons=False,
            bezier_as_lines=False,
            junction_z_order=KiCadJunctionZOrder.NATIVE,
            truncate_font_size_for_baseline=True,
        )

    @classmethod
    def onscreen(cls) -> "KiCadSvgRenderOptions":
        """Match the eeschema GAL on-screen look."""
        return cls(
            black_and_white=False,
            text_as_polygons=False,
            bezier_as_lines=False,
            junction_z_order=KiCadJunctionZOrder.ALWAYS_ON_TOP,
            truncate_font_size_for_baseline=False,
        )

    @classmethod
    def review_default(cls) -> "KiCadSvgRenderOptions":
        """Clean review export: anti-aliased, junctions on top, real fonts."""
        return cls(
            black_and_white=False,
            text_as_polygons=False,
            bezier_as_lines=False,
            junction_z_order=KiCadJunctionZOrder.ALWAYS_ON_TOP,
            truncate_font_size_for_baseline=False,
            include_metadata=True,
        )

    @classmethod
    def polytext(cls) -> "KiCadSvgRenderOptions":
        """On-screen rendering with text emitted as polygon paths."""
        return cls(
            black_and_white=False,
            text_as_polygons=True,
            bezier_as_lines=False,
            junction_z_order=KiCadJunctionZOrder.ALWAYS_ON_TOP,
        )

    @classmethod
    def black_and_white_native(cls) -> "KiCadSvgRenderOptions":
        """Match ``kicad-cli sch export svg --black-and-white``."""
        opts = cls.kicad_native()
        opts.black_and_white = True
        return opts


# =============================================================================
# Context
# =============================================================================


@dataclass
class KiCadSvgRenderContext:
    """
    Mutable rendering context. Threaded through every ``svg_*``
    primitive. Carries the active transform stack, colour/pen state,
    sheet dims, font hooks and the options bundle.

    Mirrors ``altium_monkey.SchSvgRenderContext`` in spirit, but with
    KiCad-native units (nm) and a slimmer field set.
    """

    # ---- transforms ----
    offset_x_nm: int = 0
    offset_y_nm: int = 0
    # User-units-per-nm; takes priority over ``options.output_unit_per_nm``
    # when set (None defers to options).
    scale: float | None = None
    # Stroke-width scale multiplier (None mirrors ``scale``).
    stroke_scale: float | None = None
    # Mirror Y around ``sheet_height_nm``.
    flip_y: bool = False

    # ---- sheet ----
    sheet_width_nm: int = 0
    sheet_height_nm: int = 0
    sheet_area_color: str = "#FFFFFF"

    # ---- placement (component-local origin transforms) ----
    placement_x_nm: int = 0
    placement_y_nm: int = 0
    rotation_deg: int = 0           # 0 / 90 / 180 / 270
    mirror_x: bool = False
    mirror_y: bool = False

    # ---- pen / colour state (mirrors PLOTTER state) ----
    current_color: str = "#000000"
    current_line_width_nm: int = 152_400  # KiCad default 6 mil ~= 152400 nm
    current_line_style: KiCadLineStyle = KiCadLineStyle.SOLID

    # ---- text variable substitution ----
    parameters: dict[str, str] = field(default_factory=dict)

    # ---- font hook ----
    # Set in F-5 to a real KiFont newstroke / variable-TTF resolver.
    # F-2 leaves it None and ``svg_text`` emits standard ``<text>``.
    font_manager: Any | None = None

    # ---- group / layer tracking ----
    current_layer: str = ""
    current_net: str = ""
    current_group_label: str = ""

    # ---- junction collector (when options.junction_z_order = ALWAYS_ON_TOP) ----
    deferred_junctions: list[str] = field(default_factory=list)
    connection_points: set[tuple[int, int]] = field(default_factory=set)

    # ---- options ----
    options: KiCadSvgRenderOptions = field(default_factory=KiCadSvgRenderOptions)

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def effective_scale(self) -> float:
        """Resolved nm-to-user-unit multiplier."""
        return self.scale if self.scale is not None else self.options.output_unit_per_nm

    def effective_stroke_scale(self) -> float:
        return (
            self.stroke_scale
            if self.stroke_scale is not None
            else self.effective_scale()
        )

    def to_user_x(self, x_nm: int | float) -> float:
        """Apply offset + scale on X."""
        return float(x_nm + self.offset_x_nm) * self.effective_scale()

    def to_user_y(self, y_nm: int | float) -> float:
        """Apply offset + scale on Y, with optional flip around sheet height."""
        if self.flip_y and self.sheet_height_nm > 0:
            return float(self.sheet_height_nm - y_nm + self.offset_y_nm) * self.effective_scale()
        return float(y_nm + self.offset_y_nm) * self.effective_scale()

    def to_user_length(self, nm: int | float) -> float:
        """Scale a non-positional length (radius, width, ...)."""
        return float(nm) * self.effective_scale()

    def to_stroke_width(self, width_nm: int | float) -> float:
        """Scale a stroke width by the (possibly distinct) stroke scale."""
        return float(width_nm) * self.effective_stroke_scale()

    def push_offset(self, dx_nm: int, dy_nm: int) -> "KiCadSvgRenderContext":
        """Return a shallow copy with offset translated by (dx, dy)."""
        from copy import copy as _copy
        nc = _copy(self)
        nc.offset_x_nm = self.offset_x_nm + int(dx_nm)
        nc.offset_y_nm = self.offset_y_nm + int(dy_nm)
        return nc

    def resolve_color(self, color: str | None) -> str:
        """Apply black-and-white override + None → current_color fallback."""
        resolved = self.current_color if color is None else color
        if self.options.black_and_white:
            if _color_override_key_no_alpha(resolved) == "#FFFFFF":
                return "#FFFFFF"
            return "#000000"
        if self.options.color_overrides:
            return (
                self.options.color_overrides.get(_color_override_key(resolved))
                or self.options.color_overrides.get(_color_override_key_no_alpha(resolved))
                or resolved
            )
        return resolved


# =============================================================================
# Number / colour formatting
# =============================================================================


def fmt_user_number(value: float) -> str:
    """
    Compact user-unit number formatter. Snaps near-integers to int and
    strips trailing zeros so SVG diffs against kicad-cli stay quiet.
    """
    if abs(value - round(value)) <= 1e-9:
        return str(int(round(value)))
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _ki_round(value: float) -> int:
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def _nm_to_schematic_iu(value_nm: int | float) -> int:
    return _ki_round(float(value_nm) / 100.0)


def _schematic_iu_to_nm(value_iu: int) -> int:
    return int(value_iu) * 100


def _fmt_color(color: str) -> str:
    """Pass-through colour formatter (already normalised at IR layer)."""
    return color


def _color_override_key(color: str | None) -> str:
    text = re.sub(r"\s+", "", str(color or "")).upper()
    if text.startswith("#") and len(text) in {7, 9}:
        return text
    return text


def _color_override_key_no_alpha(color: str | None) -> str:
    key = _color_override_key(color)
    if key.startswith("#") and len(key) == 9 and key.endswith("FF"):
        return key[:7]
    return key


def _fmt_dasharray(line_style: KiCadLineStyle, stroke_width: float) -> str | None:
    """
    Translate a KiCad LINE_STYLE enum to an SVG ``stroke-dasharray``
    string sized relative to the stroke width. Returns ``None`` for
    SOLID / DEFAULT.
    """
    if line_style in (KiCadLineStyle.SOLID, KiCadLineStyle.DEFAULT):
        return None
    sw = max(stroke_width, 0.0001)
    if line_style == KiCadLineStyle.DASH:
        return f"{sw * 4:.3f} {sw * 2:.3f}"
    if line_style == KiCadLineStyle.DOT:
        return f"{sw:.3f} {sw * 2:.3f}"
    if line_style == KiCadLineStyle.DASH_DOT:
        return f"{sw * 4:.3f} {sw * 2:.3f} {sw:.3f} {sw * 2:.3f}"
    if line_style == KiCadLineStyle.DASH_DOT_DOT:
        return (
            f"{sw * 4:.3f} {sw * 2:.3f} "
            f"{sw:.3f} {sw * 2:.3f} {sw:.3f} {sw * 2:.3f}"
        )
    return None


# =============================================================================
# Pen / fill attribute helpers
# =============================================================================


def _fill_attribute(fill: KiCadFillType | str | None, *, ctx: KiCadSvgRenderContext,
                    fill_color: str | None) -> str:
    """
    Translate a KiCad FILL_T to ``fill="..."`` and (if applicable)
    ``fill-opacity="..."``. Returns the string fragment ready to splice
    inside a tag, or ``""`` for no-fill.
    """
    if fill is None:
        return 'fill="none"'
    if isinstance(fill, str):
        try:
            fill = KiCadFillType(fill)
        except ValueError:
            return 'fill="none"'
    if fill == KiCadFillType.NO_FILL:
        return 'fill="none"'
    color = ctx.resolve_color(
        fill_color or ctx.options.default_fill_color or ctx.current_color
    )
    if fill == KiCadFillType.FILLED_WITH_BG_BODYCOLOR:
        return f'fill="{ctx.sheet_area_color}"'
    return f'fill="{color}"'


def _stroke_attributes(
    *,
    ctx: KiCadSvgRenderContext,
    color: str | None,
    width_nm: int | float,
    line_style: KiCadLineStyle | str | None = None,
) -> str:
    """
    Build the stroke-related attribute group as a single string.
    Handles colour, width, dash, line-cap, line-join.
    """
    stroke_color = ctx.resolve_color(
        color or ctx.options.default_stroke_color or ctx.current_color
    )
    stroke_width = ctx.to_stroke_width(width_nm)
    if isinstance(line_style, str):
        try:
            line_style = KiCadLineStyle(line_style)
        except ValueError:
            line_style = ctx.current_line_style
    elif line_style is None:
        line_style = ctx.current_line_style
    parts = [
        f'stroke="{stroke_color}"',
        f'stroke-width="{fmt_user_number(stroke_width)}"',
        'stroke-linecap="round"',
        'stroke-linejoin="round"',
    ]
    dash = _fmt_dasharray(line_style, stroke_width)
    if dash:
        parts.append(f'stroke-dasharray="{dash}"')
    return " ".join(parts)


# =============================================================================
# Primitive emitters
# =============================================================================


def svg_line(
    x1_nm: int, y1_nm: int, x2_nm: int, y2_nm: int,
    *,
    ctx: KiCadSvgRenderContext,
    color: str | None = None,
    width_nm: int | float | None = None,
    line_style: KiCadLineStyle | str | None = None,
) -> str:
    """Emit a single ``<line>`` element."""
    w = ctx.current_line_width_nm if width_nm is None else width_nm
    return (
        f'<line x1="{fmt_user_number(ctx.to_user_x(x1_nm))}" '
        f'y1="{fmt_user_number(ctx.to_user_y(y1_nm))}" '
        f'x2="{fmt_user_number(ctx.to_user_x(x2_nm))}" '
        f'y2="{fmt_user_number(ctx.to_user_y(y2_nm))}" '
        f'{_stroke_attributes(ctx=ctx, color=color, width_nm=w, line_style=line_style)} />'
    )


def svg_rect(
    x1_nm: int, y1_nm: int, x2_nm: int, y2_nm: int,
    *,
    ctx: KiCadSvgRenderContext,
    fill: KiCadFillType | str | None = KiCadFillType.NO_FILL,
    fill_color: str | None = None,
    stroke_color: str | None = None,
    width_nm: int | float | None = None,
    corner_radius_nm: int = 0,
    line_style: KiCadLineStyle | str | None = None,
) -> str:
    """Emit a ``<rect>``. Coordinates are unordered; the function normalises."""
    ux1 = ctx.to_user_x(x1_nm)
    ux2 = ctx.to_user_x(x2_nm)
    uy1 = ctx.to_user_y(y1_nm)
    uy2 = ctx.to_user_y(y2_nm)
    x = min(ux1, ux2)
    y = min(uy1, uy2)
    width = abs(ux2 - ux1)
    height = abs(uy2 - uy1)
    w = ctx.current_line_width_nm if width_nm is None else width_nm
    radius_attr = ""
    if corner_radius_nm > 0:
        r = ctx.to_user_length(corner_radius_nm)
        radius_attr = f' rx="{fmt_user_number(r)}" ry="{fmt_user_number(r)}"'
    return (
        f'<rect x="{fmt_user_number(x)}" y="{fmt_user_number(y)}" '
        f'width="{fmt_user_number(width)}" height="{fmt_user_number(height)}"{radius_attr} '
        f'{_fill_attribute(fill, ctx=ctx, fill_color=fill_color)} '
        f'{_stroke_attributes(ctx=ctx, color=stroke_color, width_nm=w, line_style=line_style)} />'
    )


def svg_circle(
    cx_nm: int, cy_nm: int, radius_nm: int | float,
    *,
    ctx: KiCadSvgRenderContext,
    fill: KiCadFillType | str | None = KiCadFillType.NO_FILL,
    fill_color: str | None = None,
    stroke_color: str | None = None,
    width_nm: int | float | None = None,
    line_style: KiCadLineStyle | str | None = None,
) -> str:
    """Emit a ``<circle>``."""
    w = ctx.current_line_width_nm if width_nm is None else width_nm
    return (
        f'<circle cx="{fmt_user_number(ctx.to_user_x(cx_nm))}" '
        f'cy="{fmt_user_number(ctx.to_user_y(cy_nm))}" '
        f'r="{fmt_user_number(ctx.to_user_length(radius_nm))}" '
        f'{_fill_attribute(fill, ctx=ctx, fill_color=fill_color)} '
        f'{_stroke_attributes(ctx=ctx, color=stroke_color, width_nm=w, line_style=line_style)} />'
    )


def svg_ellipse(
    cx_nm: int, cy_nm: int, rx_nm: int | float, ry_nm: int | float,
    *,
    ctx: KiCadSvgRenderContext,
    fill: KiCadFillType | str | None = KiCadFillType.NO_FILL,
    fill_color: str | None = None,
    stroke_color: str | None = None,
    width_nm: int | float | None = None,
    line_style: KiCadLineStyle | str | None = None,
) -> str:
    """Emit an ``<ellipse>``."""
    w = ctx.current_line_width_nm if width_nm is None else width_nm
    return (
        f'<ellipse cx="{fmt_user_number(ctx.to_user_x(cx_nm))}" '
        f'cy="{fmt_user_number(ctx.to_user_y(cy_nm))}" '
        f'rx="{fmt_user_number(ctx.to_user_length(rx_nm))}" '
        f'ry="{fmt_user_number(ctx.to_user_length(ry_nm))}" '
        f'{_fill_attribute(fill, ctx=ctx, fill_color=fill_color)} '
        f'{_stroke_attributes(ctx=ctx, color=stroke_color, width_nm=w, line_style=line_style)} />'
    )


def _arc_endpoint_path(
    *,
    ctx: KiCadSvgRenderContext,
    start_x: float, start_y: float,
    mid_x: float, mid_y: float,
    end_x: float, end_y: float,
) -> str | None:
    """
    Build an SVG path ``d`` attribute for an arc defined by start /
    mid / end. Returns ``None`` if the three points are collinear.
    """
    # Compute centre by perpendicular-bisector intersection.
    ax, ay = float(start_x), float(start_y)
    bx, by = float(mid_x), float(mid_y)
    cx, cy = float(end_x), float(end_y)
    d_denom = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d_denom) < 1e-9:
        return None  # collinear
    a_sq = ax * ax + ay * ay
    b_sq = bx * bx + by * by
    c_sq = cx * cx + cy * cy
    ux = (a_sq * (by - cy) + b_sq * (cy - ay) + c_sq * (ay - by)) / d_denom
    uy = (a_sq * (cx - bx) + b_sq * (ax - cx) + c_sq * (bx - ax)) / d_denom
    radius = math.hypot(ax - ux, ay - uy)
    # SVG large-arc / sweep flags. Determine sweep by cross-product sign
    # of (start->mid) and (start->end).
    cross_sm = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    sweep_flag = 1 if cross_sm < 0 else 0
    # Determine large-arc by cumulative angle.
    ang_a = math.atan2(ay - uy, ax - ux)
    ang_c = math.atan2(cy - uy, cx - ux)

    def _normalise(angle: float) -> float:
        while angle < 0:
            angle += 2 * math.pi
        while angle >= 2 * math.pi:
            angle -= 2 * math.pi
        return angle

    a0 = _normalise(ang_a)
    a2 = _normalise(ang_c)
    if sweep_flag == 0:
        # CCW from a0 to a2; mid should fall between
        sweep_total = (a2 - a0) % (2 * math.pi)
    else:
        sweep_total = (a0 - a2) % (2 * math.pi)
    large_arc_flag = 1 if sweep_total > math.pi else 0

    sx = fmt_user_number(ctx.to_user_x(start_x))
    sy = fmt_user_number(ctx.to_user_y(start_y))
    ex = fmt_user_number(ctx.to_user_x(end_x))
    ey = fmt_user_number(ctx.to_user_y(end_y))
    r_user = fmt_user_number(ctx.to_user_length(radius))
    return (
        f"M {sx} {sy} A {r_user} {r_user} 0 "
        f"{large_arc_flag} {sweep_flag} {ex} {ey}"
    )


def svg_arc(
    start_x_nm: int | float, start_y_nm: int | float,
    mid_x_nm: int | float, mid_y_nm: int | float,
    end_x_nm: int | float, end_y_nm: int | float,
    *,
    ctx: KiCadSvgRenderContext,
    fill: KiCadFillType | str | None = KiCadFillType.NO_FILL,
    fill_color: str | None = None,
    stroke_color: str | None = None,
    width_nm: int | float | None = None,
    line_style: KiCadLineStyle | str | None = None,
) -> str:
    """
    Emit an arc as ``<path d="M ... A ... ">`` from three points. Falls
    back to a straight ``<line>`` if the three points are collinear.
    """
    d = _arc_endpoint_path(
        ctx=ctx,
        start_x=start_x_nm, start_y=start_y_nm,
        mid_x=mid_x_nm, mid_y=mid_y_nm,
        end_x=end_x_nm, end_y=end_y_nm,
    )
    if d is None:
        return svg_line(
            int(start_x_nm), int(start_y_nm), int(end_x_nm), int(end_y_nm),
            ctx=ctx, color=stroke_color, width_nm=width_nm, line_style=line_style,
        )
    w = ctx.current_line_width_nm if width_nm is None else width_nm
    return (
        f'<path d="{d}" '
        f'{_fill_attribute(fill, ctx=ctx, fill_color=fill_color)} '
        f'{_stroke_attributes(ctx=ctx, color=stroke_color, width_nm=w, line_style=line_style)} />'
    )


def _points_attr(points: Iterable[tuple[int, int]] | Iterable[Iterable[int]],
                 *, ctx: KiCadSvgRenderContext) -> str:
    return " ".join(
        f"{fmt_user_number(ctx.to_user_x(point[0]))},{fmt_user_number(ctx.to_user_y(point[1]))}"
        for p in points
        for point in (tuple(p),)
    )


def svg_polygon(
    points: Iterable[tuple[int, int]] | Iterable[Iterable[int]],
    *,
    ctx: KiCadSvgRenderContext,
    fill: KiCadFillType | str | None = KiCadFillType.FILLED_SHAPE,
    fill_color: str | None = None,
    stroke_color: str | None = None,
    width_nm: int | float | None = None,
    line_style: KiCadLineStyle | str | None = None,
) -> str:
    """Emit a closed ``<polygon>``."""
    w = ctx.current_line_width_nm if width_nm is None else width_nm
    return (
        f'<polygon points="{_points_attr(points, ctx=ctx)}" '
        f'{_fill_attribute(fill, ctx=ctx, fill_color=fill_color)} '
        f'{_stroke_attributes(ctx=ctx, color=stroke_color, width_nm=w, line_style=line_style)} />'
    )


def svg_polyline(
    points: Iterable[tuple[int, int]] | Iterable[Iterable[int]],
    *,
    ctx: KiCadSvgRenderContext,
    stroke_color: str | None = None,
    width_nm: int | float | None = None,
    line_style: KiCadLineStyle | str | None = None,
) -> str:
    """Emit an open ``<polyline>``."""
    w = ctx.current_line_width_nm if width_nm is None else width_nm
    return (
        f'<polyline points="{_points_attr(points, ctx=ctx)}" '
        f'fill="none" '
        f'{_stroke_attributes(ctx=ctx, color=stroke_color, width_nm=w, line_style=line_style)} />'
    )


def svg_path(
    d: str,
    *,
    ctx: KiCadSvgRenderContext,
    fill: KiCadFillType | str | None = KiCadFillType.NO_FILL,
    fill_color: str | None = None,
    stroke_color: str | None = None,
    width_nm: int | float | None = None,
    line_style: KiCadLineStyle | str | None = None,
) -> str:
    """Emit a ``<path>`` with caller-built ``d`` string."""
    w = ctx.current_line_width_nm if width_nm is None else width_nm
    return (
        f'<path d="{d}" '
        f'{_fill_attribute(fill, ctx=ctx, fill_color=fill_color)} '
        f'{_stroke_attributes(ctx=ctx, color=stroke_color, width_nm=w, line_style=line_style)} />'
    )


def _bezier_path_d(
    *,
    ctx: KiCadSvgRenderContext,
    start_x: int, start_y: int,
    ctrl1_x: int, ctrl1_y: int,
    ctrl2_x: int, ctrl2_y: int,
    end_x: int, end_y: int,
) -> str:
    if ctx.options.bezier_as_lines:
        # Flatten to N line segments via cubic interpolation.
        n = max(2, ctx.options.bezier_segment_count)
        pts: list[str] = []
        for i in range(n + 1):
            t = i / n
            mt = 1 - t
            x = (
                mt ** 3 * start_x
                + 3 * mt ** 2 * t * ctrl1_x
                + 3 * mt * t ** 2 * ctrl2_x
                + t ** 3 * end_x
            )
            y = (
                mt ** 3 * start_y
                + 3 * mt ** 2 * t * ctrl1_y
                + 3 * mt * t ** 2 * ctrl2_y
                + t ** 3 * end_y
            )
            ux = fmt_user_number(ctx.to_user_x(x))
            uy = fmt_user_number(ctx.to_user_y(y))
            pts.append(f"L {ux} {uy}" if i > 0 else f"M {ux} {uy}")
        return " ".join(pts)
    return (
        f"M {fmt_user_number(ctx.to_user_x(start_x))} {fmt_user_number(ctx.to_user_y(start_y))} "
        f"C {fmt_user_number(ctx.to_user_x(ctrl1_x))} {fmt_user_number(ctx.to_user_y(ctrl1_y))} "
        f"{fmt_user_number(ctx.to_user_x(ctrl2_x))} {fmt_user_number(ctx.to_user_y(ctrl2_y))} "
        f"{fmt_user_number(ctx.to_user_x(end_x))} {fmt_user_number(ctx.to_user_y(end_y))}"
    )


def svg_bezier(
    start_x_nm: int, start_y_nm: int,
    ctrl1_x_nm: int, ctrl1_y_nm: int,
    ctrl2_x_nm: int, ctrl2_y_nm: int,
    end_x_nm: int, end_y_nm: int,
    *,
    ctx: KiCadSvgRenderContext,
    fill: KiCadFillType | str | None = KiCadFillType.NO_FILL,
    fill_color: str | None = None,
    stroke_color: str | None = None,
    width_nm: int | float | None = None,
    line_style: KiCadLineStyle | str | None = None,
) -> str:
    """Emit a cubic Bezier as either a single ``C`` path or a flattened polyline."""
    d = _bezier_path_d(
        ctx=ctx,
        start_x=start_x_nm, start_y=start_y_nm,
        ctrl1_x=ctrl1_x_nm, ctrl1_y=ctrl1_y_nm,
        ctrl2_x=ctrl2_x_nm, ctrl2_y=ctrl2_y_nm,
        end_x=end_x_nm, end_y=end_y_nm,
    )
    return svg_path(
        d, ctx=ctx, fill=fill, fill_color=fill_color,
        stroke_color=stroke_color, width_nm=width_nm, line_style=line_style,
    )


# ---- text ----

_H_ALIGN_TO_SVG = {
    KiCadHorizAlign.LEFT: "start",
    KiCadHorizAlign.CENTER: "middle",
    KiCadHorizAlign.RIGHT: "end",
    KiCadHorizAlign.INDETERMINATE: "start",
}

_V_ALIGN_TEXT_POS_IU = {
    KiCadVertAlign.TOP: lambda size_y_iu: size_y_iu,
    KiCadVertAlign.CENTER: lambda size_y_iu: size_y_iu // 2,
    KiCadVertAlign.BOTTOM: lambda size_y_iu: 0,
    KiCadVertAlign.INDETERMINATE: lambda size_y_iu: 0,
}


def _coerce_text_aligns(
    h_align: KiCadHorizAlign | str,
    v_align: KiCadVertAlign | str,
) -> tuple[KiCadHorizAlign, KiCadVertAlign]:
    if isinstance(h_align, str):
        try:
            h_align = KiCadHorizAlign(h_align)
        except ValueError:
            h_align = KiCadHorizAlign.LEFT
    if isinstance(v_align, str):
        try:
            v_align = KiCadVertAlign(v_align)
        except ValueError:
            v_align = KiCadVertAlign.BOTTOM
    return h_align, v_align


def _resolve_text_anchor(h_align: KiCadHorizAlign | str) -> str:
    if isinstance(h_align, str):
        try:
            h_align = KiCadHorizAlign(h_align)
        except ValueError:
            h_align = KiCadHorizAlign.LEFT
    return _H_ALIGN_TO_SVG[h_align]


def _substitute_parameters(text: str, params: dict[str, str]) -> str:
    """
    KiCad text-variable substitution: ``${VAR}`` -> ``params["VAR"]``.
    Unknown variables pass through unchanged so callers can detect
    the miss.
    """
    if "${" not in text or not params:
        return text
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "$" and i + 1 < n and text[i + 1] == "{":
            close = text.find("}", i + 2)
            if close > 0:
                name = text[i + 2 : close]
                if name in params:
                    out.append(params[name])
                    i = close + 1
                    continue
        out.append(text[i])
        i += 1
    return "".join(out)


def svg_text(
    x_nm: int, y_nm: int, text: str,
    *,
    ctx: KiCadSvgRenderContext,
    color: str | None = None,
    size_x_nm: int = 1_270_000,
    size_y_nm: int = 1_270_000,
    orient_deg: float = 0.0,
    h_align: KiCadHorizAlign | str = KiCadHorizAlign.LEFT,
    v_align: KiCadVertAlign | str = KiCadVertAlign.BOTTOM,
    italic: bool = False,
    bold: bool = False,
    font_face: str = "",
    pen_width_nm: int | float | None = None,
    mirror: bool = False,
) -> str:
    """
    Emit a ``<text>`` element. Phase F-2 ships only the standard SVG
    text path; the polygon-text path lands in F-5 once the font
    manager is wired in.
    """
    if ctx.options.text_as_polygons and ctx.font_manager is not None:
        # Hook for F-5: ctx.font_manager.tessellate(...). Until that
        # lands we silently fall through to standard <text>.
        pass

    substituted = _substitute_parameters(text, ctx.parameters)
    h_align, v_align = _coerce_text_aligns(h_align, v_align)
    h_anchor = _resolve_text_anchor(h_align)
    # KiCad's SVG plotter writes invisible SVG text using integer schematic
    # IUs: text_pos.y is adjusted by aSize.y/2 or aSize.y, and font-size is
    # aSize.x * 4 / 3 with integer division.
    size_x_iu = abs(_nm_to_schematic_iu(size_x_nm))
    size_y_iu = abs(_nm_to_schematic_iu(size_y_nm))
    font_size_nm = _schematic_iu_to_nm(size_x_iu * 4 // 3)
    baseline_offset_nm = _schematic_iu_to_nm(_V_ALIGN_TEXT_POS_IU[v_align](size_y_iu))
    size_user = ctx.to_user_length(font_size_nm)
    baseline_y_user = ctx.to_user_y(y_nm) + ctx.to_user_length(baseline_offset_nm)
    color_resolved = ctx.resolve_color(color)
    effective_font_face = ctx.options.font_face_override or font_face
    text_length_attr = ""
    if substituted:
        try:
            from .kicad_schematic_to_ir import _schematic_outline_text_width_nm

            text_length_nm = _schematic_outline_text_width_nm(
                substituted,
                int(size_x_nm),
                bold=bold,
                italic=italic,
                font_face=effective_font_face,
            )
        except Exception:
            text_length_nm = 0
        if text_length_nm > 0:
            text_length_attr = (
                f'textLength="{fmt_user_number(ctx.to_user_length(text_length_nm))}" '
                'lengthAdjust="spacingAndGlyphs" '
            )
    style_parts: list[str] = []
    if italic:
        style_parts.append("font-style: italic")
    if bold:
        style_parts.append("font-weight: bold")
    if effective_font_face:
        style_parts.append(f'font-family: "{effective_font_face}"')
    style_attr = (
        f' style="{html.escape("; ".join(style_parts), quote=True)}"'
        if style_parts
        else ""
    )

    transform_attr = ""
    if abs(orient_deg) > 1e-9:
        ux = fmt_user_number(ctx.to_user_x(x_nm))
        uy = fmt_user_number(ctx.to_user_y(y_nm))
        svg_orient_deg = -float(orient_deg)
        transform_attr = f' transform="rotate({fmt_user_number(svg_orient_deg)} {ux} {uy})"'

    return (
        f'<text x="{fmt_user_number(ctx.to_user_x(x_nm))}" '
        f'y="{fmt_user_number(baseline_y_user)}" '
        f'font-size="{fmt_user_number(size_user)}" '
        f'fill="{color_resolved}" '
        f'{text_length_attr}'
        f'text-anchor="{h_anchor}"'
        f'{transform_attr}{style_attr}>'
        f'{html.escape(substituted)}</text>'
    )


_STROKE_TEXT_THICKNESS_RATIO = 0.15
_STROKE_TEXT_BOLD_THICKNESS_RATIO = 0.20


_H_ALIGN_TO_STROKE = {
    KiCadHorizAlign.LEFT: "left",
    KiCadHorizAlign.CENTER: "center",
    KiCadHorizAlign.RIGHT: "right",
    KiCadHorizAlign.INDETERMINATE: "left",
}

_V_ALIGN_TO_STROKE = {
    KiCadVertAlign.TOP: "top",
    KiCadVertAlign.CENTER: "center",
    KiCadVertAlign.BOTTOM: "bottom",
    KiCadVertAlign.INDETERMINATE: "bottom",
}


def _resolve_stroke_alignment(
    h_align: KiCadHorizAlign | str,
    v_align: KiCadVertAlign | str,
) -> tuple[str, str]:
    """Map IR enum / GR_TEXT_*_ALIGN_* strings to stroke-renderer tokens."""
    if isinstance(h_align, str):
        try:
            h_align = KiCadHorizAlign(h_align)
        except ValueError:
            h_align = KiCadHorizAlign.LEFT
    if isinstance(v_align, str):
        try:
            v_align = KiCadVertAlign(v_align)
        except ValueError:
            v_align = KiCadVertAlign.BOTTOM
    return _H_ALIGN_TO_STROKE[h_align], _V_ALIGN_TO_STROKE[v_align]


def svg_text_poly(
    x_nm: int, y_nm: int, text: str,
    *,
    ctx: KiCadSvgRenderContext,
    color: str | None = None,
    size_x_nm: int = 1_270_000,
    size_y_nm: int = 1_270_000,
    orient_deg: float = 0.0,
    h_align: KiCadHorizAlign | str = KiCadHorizAlign.LEFT,
    v_align: KiCadVertAlign | str = KiCadVertAlign.BOTTOM,
    italic: bool = False,
    bold: bool = False,
    font_face: str = "",
    pen_width_nm: int | float | None = None,
    mirror: bool = False,
) -> str:
    """
    Emit text as ``<polyline>`` strokes via :class:`KiCadStrokeFontRenderer`.

    Mirrors KiCad's STROKE_FONT::GetTextAsGlyphs() so the polylines line
    up with kicad-cli's stroked-text export. The renderer takes mm and
    returns mm; we scale back to nm before calling :func:`svg_polyline`.

    Pen width defaults to ``size_y_nm * 0.15`` (KiCad's
    ``STROKE_FONT_THICKNESS_RATIO``) for normal weight, ``* 0.20`` for
    bold, when the caller passes 0 / None / a value smaller than that.
    The ``font_face`` arg is currently ignored (newstroke only); a
    real TTF resolver lands when ``ctx.font_manager`` is populated.
    """
    substituted = _substitute_parameters(text, ctx.parameters)
    if not substituted:
        return ""

    # Default pen width derived from font height per KiCad convention.
    ratio = _STROKE_TEXT_BOLD_THICKNESS_RATIO if bold else _STROKE_TEXT_THICKNESS_RATIO
    default_pen_nm = int(round(size_y_nm * ratio))
    if pen_width_nm is None or int(pen_width_nm) <= 0:
        effective_pen_nm = default_pen_nm
    else:
        effective_pen_nm = int(pen_width_nm)

    h_stroke, v_stroke = _resolve_stroke_alignment(h_align, v_align)

    from .kicad_stroke_font import get_renderer

    renderer = get_renderer()
    polylines_mm = renderer.render_text_polylines(
        text=substituted,
        pos_x=x_nm / 1_000_000.0,
        pos_y=y_nm / 1_000_000.0,
        size_x=size_x_nm / 1_000_000.0,
        size_y=size_y_nm / 1_000_000.0,
        angle=orient_deg,
        h_align=h_stroke,
        v_align=v_stroke,
        mirror=mirror,
        italic=italic,
    )
    if not polylines_mm:
        return ""

    per_segment = bool(ctx.options.text_polyline_per_segment) if ctx is not None else False

    fragments: list[str] = []
    for polyline in polylines_mm:
        if len(polyline) < 2:
            continue
        nm_points = [
            (int(round(px * 1_000_000)), int(round(py * 1_000_000)))
            for px, py in polyline
        ]
        if per_segment:
            # One ``<polyline>`` per line segment — mirrors kicad-cli's
            # per-MoveTo/LineTo recording granularity for parity in
            # PCB IR oracle metrics.
            for i in range(len(nm_points) - 1):
                fragments.append(
                    svg_polyline(
                        [nm_points[i], nm_points[i + 1]],
                        ctx=ctx,
                        stroke_color=color,
                        width_nm=effective_pen_nm,
                    )
                )
        else:
            fragments.append(
                svg_polyline(
                    nm_points,
                    ctx=ctx,
                    stroke_color=color,
                    width_nm=effective_pen_nm,
                )
            )
    return "\n".join(fragments)


def svg_text_or_poly(*args: Any, **kwargs: Any) -> str:
    """Dispatch to :func:`svg_text_poly` if options request it, else :func:`svg_text`."""
    ctx = kwargs.get("ctx")
    if ctx is not None and ctx.options.text_as_polygons:
        return svg_text_poly(*args, **kwargs)
    return svg_text(*args, **kwargs)


# ---- group ----


def svg_group(
    content: str | Iterable[str],
    *,
    label: str | None = None,
    transform: str | None = None,
    data_uuid: str | None = None,
    data_ref: str | None = None,
    extra_attrs: str | None = None,
) -> str:
    """Wrap a body in ``<g>`` with optional id / transform / data-* hooks."""
    body = content if isinstance(content, str) else "\n".join(s for s in content if s)
    parts: list[str] = []
    if label:
        parts.append(f'id="{html.escape(label, quote=True)}"')
    if transform:
        parts.append(f'transform="{transform}"')
    if data_uuid:
        parts.append(f'data-uuid="{html.escape(data_uuid, quote=True)}"')
    if data_ref:
        parts.append(f'data-ref="{html.escape(data_ref, quote=True)}"')
    if extra_attrs:
        parts.append(extra_attrs)
    attrs = (" " + " ".join(parts)) if parts else ""
    return f"<g{attrs}>\n{body}\n</g>"


# ---- document envelope ----


def svg_document(
    body: str | Iterable[str],
    *,
    ctx: KiCadSvgRenderContext,
    width_nm: int | None = None,
    height_nm: int | None = None,
    background_color: str | None = None,
) -> str:
    """
    Wrap ``body`` in an ``<svg>`` envelope sized from the context's
    sheet dims (or explicit overrides) and the resolved scale.
    """
    w_nm = width_nm if width_nm is not None else ctx.sheet_width_nm
    h_nm = height_nm if height_nm is not None else ctx.sheet_height_nm
    width = ctx.to_user_length(w_nm) if w_nm > 0 else 0.0
    height = ctx.to_user_length(h_nm) if h_nm > 0 else 0.0
    suffix = ctx.options.output_unit_suffix
    bg = (
        background_color
        if background_color is not None
        else ctx.options.background_color
    )

    body_text = body if isinstance(body, str) else "\n".join(s for s in body if s)
    parts: list[str] = []
    if ctx.options.include_xml_declaration:
        parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{fmt_user_number(width)}{suffix}" '
        f'height="{fmt_user_number(height)}{suffix}" '
        f'viewBox="0 0 {fmt_user_number(width)} {fmt_user_number(height)}">'
    )
    if bg is not None and width > 0 and height > 0:
        parts.append(
            f'  <rect x="0" y="0" width="{fmt_user_number(width)}" '
            f'height="{fmt_user_number(height)}" fill="{bg}" />'
        )
    parts.append(body_text)
    parts.append("</svg>")
    return "\n".join(parts)


__all__ = [
    "KiCadJunctionZOrder",
    "KiCadSvgRenderContext",
    "KiCadSvgRenderOptions",
    "KiCadVariantDimMode",
    "fmt_user_number",
    "svg_arc",
    "svg_bezier",
    "svg_circle",
    "svg_document",
    "svg_ellipse",
    "svg_group",
    "svg_line",
    "svg_path",
    "svg_polygon",
    "svg_polyline",
    "svg_rect",
    "svg_text",
    "svg_text_or_poly",
    "svg_text_poly",
]
