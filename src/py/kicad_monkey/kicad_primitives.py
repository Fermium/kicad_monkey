"""
KiCad Primitives - Stroke, Font, Effects, RenderCache

Shared building block classes used by PCB, footprint, symbol, and schematic elements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .kicad_defaults import KICAD_DEFAULT_TEXT_SIZE_MM
from .kicad_sexpr import QuotedString, SexpList
from .kicad_base import (
    StrokeType,
    find_element,
    find_all_elements,
    get_value,
    has_flag,
    unquote_string,
)


@dataclass
class Stroke:
    """Stroke parameters for graphical elements."""
    width: float = 0.0
    type: StrokeType = StrokeType.DEFAULT
    color: Optional[Tuple[int, int, int, float]] = None

    @classmethod
    def from_sexp(cls, sexp: list) -> 'Stroke':
        stroke_elem = find_element(sexp, 'stroke')
        if not stroke_elem:
            return cls()

        width = get_value(stroke_elem, 'width', 0.0)
        type_str = get_value(stroke_elem, 'type', 'default')
        stroke_type = StrokeType(type_str) if type_str else StrokeType.DEFAULT

        # (color R G B A) — KiCad emits this when a non-default stroke
        # colour is set; preserve it on round-trip.
        color: Optional[Tuple[int, int, int, float]] = None
        color_elem = find_element(stroke_elem, 'color')
        if color_elem and len(color_elem) >= 5:
            try:
                color = (
                    int(color_elem[1]),
                    int(color_elem[2]),
                    int(color_elem[3]),
                    float(color_elem[4]),
                )
            except (ValueError, TypeError):
                color = None

        return cls(width=float(width), type=stroke_type, color=color)

    def to_sexp(self) -> list:
        result: SexpList = ['stroke', ['width', self.width], ['type', self.type.value]]
        if self.color is not None:
            r, g, b, a = self.color
            result.append(['color', r, g, b, a])
        return result


@dataclass
class Font:
    """Font parameters for text elements.

    Mirrors EDA_TEXT::Format (kicad/common/eda_text.cpp:1090). Emit
    order: face, size, line_spacing, thickness, bold, italic, color.
    KiCad serializes ``(size height width)`` even though the in-memory
    ``TEXT_ATTRIBUTES`` vector stores ``x=width`` and ``y=height``.

    ``thickness`` is `None` when the source omitted ``(thickness ...)``
    (KiCad calls this "auto thickness"); only emit ``(thickness X)``
    when an explicit value is set, matching the ``!GetAutoThickness()``
    guard at eda_text.cpp:1108. ``color`` is similarly elided when
    UNSPECIFIED (eda_text.cpp:1120).
    """
    face: Optional[str] = None
    size_x: float = KICAD_DEFAULT_TEXT_SIZE_MM
    size_y: float = KICAD_DEFAULT_TEXT_SIZE_MM
    thickness: Optional[float] = None
    bold: bool = False
    italic: bool = False
    line_spacing: Optional[float] = None
    color: Optional[Tuple[int, int, int, float]] = None

    @classmethod
    def from_sexp(cls, sexp: list) -> 'Font':
        font_elem = find_element(sexp, 'font')
        if not font_elem:
            return cls()

        face = get_value(font_elem, 'face')
        size_elem = find_element(font_elem, 'size')
        size_y = (
            float(size_elem[1])
            if size_elem and len(size_elem) > 1
            else KICAD_DEFAULT_TEXT_SIZE_MM
        )
        size_x = (
            float(size_elem[2])
            if size_elem and len(size_elem) > 2
            else KICAD_DEFAULT_TEXT_SIZE_MM
        )
        thickness_elem = find_element(font_elem, 'thickness')
        thickness = float(thickness_elem[1]) if thickness_elem and len(thickness_elem) > 1 else None
        bold = has_flag(font_elem, 'bold') or get_value(font_elem, 'bold') == 'yes'
        italic = has_flag(font_elem, 'italic') or get_value(font_elem, 'italic') == 'yes'

        line_spacing_elem = find_element(font_elem, 'line_spacing')
        line_spacing = (float(line_spacing_elem[1])
                        if line_spacing_elem and len(line_spacing_elem) > 1
                        else None)

        color: Optional[Tuple[int, int, int, float]] = None
        color_elem = find_element(font_elem, 'color')
        if color_elem and len(color_elem) >= 5:
            color = (int(color_elem[1]), int(color_elem[2]),
                     int(color_elem[3]), float(color_elem[4]))

        return cls(
            face=unquote_string(face) if face else None,
            size_x=size_x,
            size_y=size_y,
            thickness=thickness,
            bold=bold,
            italic=italic,
            line_spacing=line_spacing,
            color=color,
        )

    @property
    def effective_thickness(self) -> float:
        """Resolve `thickness` to a concrete number for renderers that
        need a width. Falls back to KiCad's `GetEffectiveTextPenWidth()`
        normal/bold auto-thickness rules when no explicit value was set."""
        if self.thickness is not None:
            return self.thickness
        text_width = abs(self.size_x) or abs(self.size_y)
        if not text_width:
            return 0.15
        pen_width = text_width / 5.0 if self.bold else text_width / 8.0
        min_size = min(abs(self.size_x), abs(self.size_y))
        if min_size:
            pen_width = min(pen_width, min_size * 0.25)
        return pen_width

    def to_sexp(self) -> list:
        # Order matches EDA_TEXT::Format (eda_text.cpp:1090):
        # face, size, line_spacing, thickness, bold, italic, color.
        result: SexpList = ['font']
        if self.face:
            result.append(['face', QuotedString(self.face)])
        result.append(['size', self.size_y, self.size_x])
        if self.line_spacing is not None and self.line_spacing != 1.0:
            result.append(['line_spacing', self.line_spacing])
        if self.thickness is not None:
            result.append(['thickness', self.thickness])
        if self.bold:
            result.append(['bold', 'yes'])
        if self.italic:
            result.append(['italic', 'yes'])
        if self.color is not None:
            r, g, b, a = self.color
            result.append(['color', r, g, b, a])
        return result


@dataclass
class Effects:
    """Text effects including font and justification."""
    font: Font = field(default_factory=Font)
    justify: Optional[List[str]] = None
    hide: bool = False
    # Optional hyperlink URL — EDA_TEXT::Format writes `(href "url")` inside
    # (effects ...) after justify when HasHyperlink() (eda_text.cpp:1145).
    href: Optional[str] = None

    @classmethod
    def from_sexp(cls, sexp: list) -> 'Effects':
        effects_elem = find_element(sexp, 'effects')
        if not effects_elem:
            return cls()

        font = Font.from_sexp(effects_elem)
        justify_elem = find_element(effects_elem, 'justify')
        justify = list(justify_elem[1:]) if justify_elem else None
        # KiCad 9 nested (hide yes) inside (effects ...); KiCad 10 emits
        # (hide yes) as a sibling at the parent (property/text) level and
        # EDA_TEXT::Format no longer writes hide. Accept either form.
        hide = (has_flag(effects_elem, 'hide')
                or get_value(effects_elem, 'hide') == 'yes')

        href_elem = find_element(effects_elem, 'href')
        href = unquote_string(href_elem[1]) if href_elem and len(href_elem) > 1 else None

        return cls(font=font, justify=justify, hide=hide, href=href)

    def to_sexp(self) -> list:
        result = ['effects', self.font.to_sexp()]
        if self.justify:
            result.append(['justify'] + self.justify)
        if self.hide:
            result.append('hide')
        if self.href is not None:
            result.append(['href', QuotedString(self.href)])
        return result


@dataclass
class RenderCacheContour:
    """A closed contour from a KiCad text render cache polygon."""

    points: List[Tuple[float, float]] = field(default_factory=list)

    @classmethod
    def from_pts_sexp(cls, sexp: list) -> 'RenderCacheContour':
        points: List[Tuple[float, float]] = []
        for xy in find_all_elements(sexp, 'xy'):
            if len(xy) >= 3:
                points.append((float(xy[1]), float(xy[2])))
        return cls(points=points)

    def to_sexp(self) -> list:
        return ['pts'] + [['xy', p[0], p[1]] for p in self.points]


@dataclass(init=False)
class RenderCachePolygon:
    """A polygon from render_cache.

    KiCad stores each glyph polygon as one or more ``(pts ...)`` chains.  The
    first chain is the exterior outline and later chains are holes.  Older
    callers used ``poly.points`` directly, so that property remains a
    compatibility alias for the exterior contour.
    """

    contours: List[RenderCacheContour] = field(default_factory=list)

    def __init__(
        self,
        points: Optional[List[Tuple[float, float]]] = None,
        contours: Optional[Sequence[RenderCacheContour | List[Tuple[float, float]]]] = None,
    ) -> None:
        if contours is not None:
            self.contours = [self._coerce_contour(contour) for contour in contours]
        elif points is not None:
            self.contours = [RenderCacheContour(points=list(points))]
        else:
            self.contours = []

    @staticmethod
    def _coerce_contour(
        contour: RenderCacheContour | List[Tuple[float, float]]
    ) -> RenderCacheContour:
        if isinstance(contour, RenderCacheContour):
            return contour
        return RenderCacheContour(points=list(contour))

    @property
    def points(self) -> List[Tuple[float, float]]:
        if not self.contours:
            return []
        return self.contours[0].points

    @points.setter
    def points(self, value: List[Tuple[float, float]]) -> None:
        if self.contours:
            self.contours[0] = RenderCacheContour(points=list(value))
        else:
            self.contours.append(RenderCacheContour(points=list(value)))

    @property
    def hole_contours(self) -> List[RenderCacheContour]:
        return self.contours[1:]

    @property
    def has_holes(self) -> bool:
        return len(self.contours) > 1

    @classmethod
    def from_sexp(cls, sexp: list) -> 'RenderCachePolygon':
        contours = [
            RenderCacheContour.from_pts_sexp(pts_elem)
            for pts_elem in find_all_elements(sexp, 'pts')
        ]
        return cls(contours=contours)

    def to_sexp(self) -> list:
        if not self.contours:
            return ['polygon', ['pts']]
        return ['polygon'] + [contour.to_sexp() for contour in self.contours]


@dataclass
class RenderCache:
    """Render cache containing pre-computed text polygons."""
    text: str = ""
    angle: float = 0.0
    polygons: List[RenderCachePolygon] = field(default_factory=list)

    @classmethod
    def from_sexp(cls, sexp: list) -> Optional['RenderCache']:
        rc_elem = find_element(sexp, 'render_cache')
        if not rc_elem or len(rc_elem) < 3:
            return None

        text = unquote_string(rc_elem[1])
        angle = float(rc_elem[2])

        polygons = []
        for poly_elem in find_all_elements(rc_elem, 'polygon'):
            polygons.append(RenderCachePolygon.from_sexp(poly_elem))

        return cls(text=text, angle=angle, polygons=polygons)

    def to_sexp(self) -> list:
        result = ['render_cache', QuotedString(self.text), self.angle]
        for poly in self.polygons:
            result.append(poly.to_sexp())
        return result


@dataclass
class Justify:
    """Text justification settings for schematic elements.

    Parses from (justify left top mirror) style elements.
    """
    horizontal: str = "center"  # left, center, right
    vertical: str = "center"    # top, center, bottom
    mirror: bool = False

    @classmethod
    def from_sexp(cls, sexp: list) -> 'Justify':
        """Parse from (justify left top mirror) style element."""
        h, v, m = "center", "center", False
        if not sexp:
            return cls(h, v, m)
        for item in sexp[1:]:
            if item in ("left", "right"):
                h = item
            elif item in ("top", "bottom"):
                v = item
            elif item == "mirror":
                m = True
        return cls(horizontal=h, vertical=v, mirror=m)

    def to_sexp(self) -> list:
        """Serialize to S-expression list. Returns empty list if all defaults."""
        result = ['justify']
        if self.horizontal != "center":
            result.append(self.horizontal)
        if self.vertical != "center":
            result.append(self.vertical)
        if self.mirror:
            result.append('mirror')
        return result if len(result) > 1 else []


__all__ = [
    'Stroke',
    'Font',
    'Effects',
    'Justify',
    'RenderCacheContour',
    'RenderCachePolygon',
    'RenderCache',
]
