"""Canonical SVG snapshots for KiCad CLI parity tests.

The oracle tests compare behavior, not raw SVG text. This helper parses SVG
into draw items with inherited styles and flattened transforms so tests can
reason about the objects KiCad and kicad_monkey actually paint.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable
from xml.etree import ElementTree as ET


SVG_NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
SVG_PATH_TOKEN_RE = re.compile(
    r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?"
)
SVG_TRANSFORM_RE = re.compile(r"([A-Za-z]+)\(([^)]*)\)")
DRAW_TAGS = {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect"}
STROKE_TAGS = {"path", "polyline", "line", "rect", "polygon"}

AffineMatrix = tuple[float, float, float, float, float, float]
BBox = tuple[float, float, float, float]


IDENTITY: AffineMatrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


@dataclass(frozen=True)
class SvgDrawItem:
    """One painted SVG object with effective style and geometry summary."""

    index: int
    kind: str
    style: dict[str, str]
    transform: AffineMatrix
    bbox: BBox | None
    rings: tuple[tuple[tuple[float, float], ...], ...]
    area: float
    stroke_width: float
    radius: float | None
    command_family: str


@dataclass(frozen=True)
class SvgDocumentSnapshot:
    """Canonical summary for one SVG document."""

    viewbox: BBox
    width: str | None
    height: str | None
    draw_items: tuple[SvgDrawItem, ...]
    element_kind_histogram: dict[str, int]
    style_histogram: dict[str, int]


def _local_svg_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _numbers(raw: str | None) -> list[float]:
    if not raw:
        return []
    return [float(match.group(0)) for match in SVG_NUMBER_RE.finditer(raw)]


def _parse_style(style: str | None) -> dict[str, str]:
    if not style:
        return {}
    parsed: dict[str, str] = {}
    for item in style.split(";"):
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _parse_viewbox(root: ET.Element) -> BBox:
    parts = _numbers(root.attrib.get("viewBox"))
    if len(parts) == 4:
        return tuple(round(value, 4) for value in parts)  # type: ignore[return-value]
    width = _numbers(root.attrib.get("width"))
    height = _numbers(root.attrib.get("height"))
    return (0.0, 0.0, width[0] if width else 0.0, height[0] if height else 0.0)


def _matrix_multiply(left: AffineMatrix, right: AffineMatrix) -> AffineMatrix:
    la, lb, lc, ld, le, lf = left
    ra, rb, rc, rd, re, rf = right
    return (
        la * ra + lc * rb,
        lb * ra + ld * rb,
        la * rc + lc * rd,
        lb * rc + ld * rd,
        la * re + lc * rf + le,
        lb * re + ld * rf + lf,
    )


def _apply_matrix(matrix: AffineMatrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


def _translation(tx: float, ty: float = 0.0) -> AffineMatrix:
    return (1.0, 0.0, 0.0, 1.0, tx, ty)


def _scale(sx: float, sy: float | None = None) -> AffineMatrix:
    return (sx, 0.0, 0.0, sx if sy is None else sy, 0.0, 0.0)


def _rotation(angle_deg: float) -> AffineMatrix:
    radians = math.radians(angle_deg)
    cos_a = math.cos(radians)
    sin_a = math.sin(radians)
    return (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)


def _parse_transform(transform: str | None) -> AffineMatrix:
    matrix = IDENTITY
    if not transform:
        return matrix

    for match in SVG_TRANSFORM_RE.finditer(transform):
        name = match.group(1).strip().lower()
        values = _numbers(match.group(2))
        item = IDENTITY
        if name == "matrix" and len(values) >= 6:
            item = tuple(values[:6])  # type: ignore[assignment]
        elif name == "translate" and values:
            item = _translation(values[0], values[1] if len(values) > 1 else 0.0)
        elif name == "scale" and values:
            item = _scale(values[0], values[1] if len(values) > 1 else None)
        elif name == "rotate" and values:
            item = _rotation(values[0])
            if len(values) >= 3:
                item = _matrix_multiply(
                    _matrix_multiply(_translation(values[1], values[2]), item),
                    _translation(-values[1], -values[2]),
                )
        matrix = _matrix_multiply(matrix, item)
    return matrix


def _points_bbox(points: Iterable[tuple[float, float]]) -> BBox | None:
    pts = list(points)
    if not pts:
        return None
    xs = [x for x, _y in pts]
    ys = [y for _x, y in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _parse_points(raw: str | None) -> list[tuple[float, float]]:
    values = _numbers(raw)
    return list(zip(values[::2], values[1::2]))


def _path_command_family(path_data: str) -> str:
    commands = re.findall(r"[A-Za-z]", path_data)
    return "/".join(commands)


def _simple_path_subpaths(path_data: str) -> list[list[tuple[float, float]]]:
    """Parse simple M/L/H/V/Z paths into point rings."""

    if re.search(r"[AaCcQqSsTt]", path_data):
        return []

    tokens = SVG_PATH_TOKEN_RE.findall(path_data.replace(",", " "))
    idx = 0
    cmd = ""
    current = (0.0, 0.0)
    subpath: list[tuple[float, float]] = []
    subpaths: list[list[tuple[float, float]]] = []

    def finish_subpath() -> None:
        nonlocal subpath
        if len(subpath) >= 2:
            subpaths.append(subpath)
        subpath = []

    def read_number() -> float | None:
        nonlocal idx
        if idx >= len(tokens) or re.fullmatch(r"[A-Za-z]", tokens[idx]):
            return None
        value = float(tokens[idx])
        idx += 1
        return value

    while idx < len(tokens):
        token = tokens[idx]
        if re.fullmatch(r"[A-Za-z]", token):
            cmd = token
            idx += 1
            if cmd in "Zz":
                finish_subpath()
            continue

        if cmd in "Mm":
            x = read_number()
            y = read_number()
            if x is None or y is None:
                break
            if cmd == "m":
                x += current[0]
                y += current[1]
            if subpath:
                finish_subpath()
            current = (x, y)
            subpath = [current]
            cmd = "l" if cmd == "m" else "L"
            continue

        if cmd in "Ll":
            x = read_number()
            y = read_number()
            if x is None or y is None:
                break
            if cmd == "l":
                x += current[0]
                y += current[1]
            current = (x, y)
            subpath.append(current)
            continue

        if cmd in "Hh":
            x = read_number()
            if x is None:
                break
            if cmd == "h":
                x += current[0]
            current = (x, current[1])
            subpath.append(current)
            continue

        if cmd in "Vv":
            y = read_number()
            if y is None:
                break
            if cmd == "v":
                y += current[1]
            current = (current[0], y)
            subpath.append(current)
            continue

        break

    if subpath:
        finish_subpath()
    return subpaths


def _is_color(value: str | None, *accepted: str) -> bool:
    if value is None:
        return False
    compact = value.strip().replace(" ", "").upper()
    return compact in {item.upper() for item in accepted}


def _is_black(value: str | None) -> bool:
    return _is_color(value, "#000", "#000000", "BLACK")


def _is_white(value: str | None) -> bool:
    return _is_color(value, "#FFF", "#FFFFFF", "WHITE")


def _style_float(style: dict[str, str], name: str, default: float = 0.0) -> float:
    values = _numbers(style.get(name))
    return values[0] if values else default


def _effective_stroke(style: dict[str, str]) -> str | None:
    stroke = style.get("stroke")
    if stroke is None:
        return None
    if stroke.strip().lower() == "none":
        return "none"
    if _style_float(style, "stroke-width") == 0.0:
        return "none"
    return stroke


def _style_key(style: dict[str, str]) -> str:
    parts: list[str] = []
    fill = style.get("fill")
    stroke = _effective_stroke(style)
    if fill is not None:
        parts.append(f"fill:{fill}")
    if stroke is not None:
        parts.append(f"stroke:{stroke}")
    if stroke not in {None, "none"} and "stroke-width" in style:
        parts.append(f"stroke-width:{style['stroke-width']}")
    for key in ("fill-rule", "stroke-linecap", "stroke-linejoin"):
        if key in style:
            parts.append(f"{key}:{style[key]}")
    return "; ".join(parts)


def _element_style(element: ET.Element, inherited: dict[str, str]) -> dict[str, str]:
    style = dict(inherited)
    style.update(_parse_style(element.attrib.get("style")))
    for attr_name in (
        "fill",
        "stroke",
        "stroke-width",
        "fill-rule",
        "opacity",
        "fill-opacity",
        "stroke-opacity",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-dasharray",
    ):
        attr_value = element.attrib.get(attr_name)
        if attr_value is not None:
            style[attr_name] = attr_value.strip()
    return style


def _polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def _item_geometry(
    element: ET.Element,
    kind: str,
    matrix: AffineMatrix,
) -> tuple[BBox | None, tuple[tuple[tuple[float, float], ...], ...], float, float | None]:
    if kind == "circle":
        cx = _numbers(element.attrib.get("cx"))
        cy = _numbers(element.attrib.get("cy"))
        radius = _numbers(element.attrib.get("r"))
        if not cx or not cy or not radius:
            return (None, (), 0.0, None)
        r = radius[0]
        samples = [
            (cx[0] - r, cy[0]),
            (cx[0] + r, cy[0]),
            (cx[0], cy[0] - r),
            (cx[0], cy[0] + r),
        ]
        transformed = [_apply_matrix(matrix, x, y) for x, y in samples]
        return (_points_bbox(transformed), (), math.pi * r * r, r)

    if kind == "ellipse":
        cx = _numbers(element.attrib.get("cx"))
        cy = _numbers(element.attrib.get("cy"))
        rx = _numbers(element.attrib.get("rx"))
        ry = _numbers(element.attrib.get("ry"))
        if not cx or not cy or not rx or not ry:
            return (None, (), 0.0, None)
        samples = [
            (cx[0] - rx[0], cy[0]),
            (cx[0] + rx[0], cy[0]),
            (cx[0], cy[0] - ry[0]),
            (cx[0], cy[0] + ry[0]),
        ]
        transformed = [_apply_matrix(matrix, x, y) for x, y in samples]
        return (_points_bbox(transformed), (), math.pi * rx[0] * ry[0], None)

    if kind == "rect":
        x = _numbers(element.attrib.get("x")) or [0.0]
        y = _numbers(element.attrib.get("y")) or [0.0]
        width = _numbers(element.attrib.get("width"))
        height = _numbers(element.attrib.get("height"))
        if not width or not height:
            return (None, (), 0.0, None)
        corners = [
            (x[0], y[0]),
            (x[0] + width[0], y[0]),
            (x[0] + width[0], y[0] + height[0]),
            (x[0], y[0] + height[0]),
        ]
        transformed = [_apply_matrix(matrix, px, py) for px, py in corners]
        return (
            _points_bbox(transformed),
            (tuple(transformed),),
            _polygon_area(transformed),
            None,
        )

    if kind == "line":
        x1 = _numbers(element.attrib.get("x1")) or [0.0]
        y1 = _numbers(element.attrib.get("y1")) or [0.0]
        x2 = _numbers(element.attrib.get("x2")) or [0.0]
        y2 = _numbers(element.attrib.get("y2")) or [0.0]
        transformed = [
            _apply_matrix(matrix, x1[0], y1[0]),
            _apply_matrix(matrix, x2[0], y2[0]),
        ]
        return (_points_bbox(transformed), (), 0.0, None)

    if kind in {"polygon", "polyline"}:
        points = _parse_points(element.attrib.get("points"))
        transformed = [_apply_matrix(matrix, x, y) for x, y in points]
        area = _polygon_area(transformed) if kind == "polygon" else 0.0
        rings = (tuple(transformed),) if kind == "polygon" and len(transformed) >= 3 else ()
        return (_points_bbox(transformed), rings, area, None)

    if kind == "path":
        subpaths = _simple_path_subpaths(element.attrib.get("d", ""))
        transformed_paths = [
            [_apply_matrix(matrix, x, y) for x, y in subpath]
            for subpath in subpaths
        ]
        points = [point for subpath in transformed_paths for point in subpath]
        if not points:
            fallback = _parse_points(element.attrib.get("d"))
            points = [_apply_matrix(matrix, x, y) for x, y in fallback]
        area = sum(_polygon_area(path) for path in transformed_paths)
        rings = tuple(tuple(path) for path in transformed_paths if len(path) >= 3)
        return (_points_bbox(points), rings, area, None)

    return (None, (), 0.0, None)


def _is_background_rect(item: SvgDrawItem) -> bool:
    if item.kind != "rect" or item.bbox is None:
        return False
    min_x, min_y, _max_x, _max_y = item.bbox
    return min_x == 0.0 and min_y == 0.0 and _is_white(item.style.get("fill"))


def analyze_svg(svg: str) -> SvgDocumentSnapshot:
    """Parse ``svg`` and return a canonical draw-item snapshot."""

    root = ET.fromstring(svg)
    items: list[SvgDrawItem] = []

    def walk(
        element: ET.Element,
        inherited_style: dict[str, str],
        inherited_matrix: AffineMatrix,
    ) -> None:
        style = _element_style(element, inherited_style)
        matrix = _matrix_multiply(
            inherited_matrix,
            _parse_transform(element.attrib.get("transform")),
        )
        kind = _local_svg_name(element.tag)
        if kind in DRAW_TAGS:
            bbox, rings, area, radius = _item_geometry(element, kind, matrix)
            items.append(
                SvgDrawItem(
                    index=len(items),
                    kind=kind,
                    style=style,
                    transform=matrix,
                    bbox=bbox,
                    rings=rings,
                    area=round(area, 4),
                    stroke_width=_style_float(style, "stroke-width"),
                    radius=round(radius, 4) if radius is not None else None,
                    command_family=_path_command_family(
                        element.attrib.get("d", "")
                    )
                    if kind == "path"
                    else "",
                )
            )

        for child in list(element):
            walk(child, style, matrix)

    walk(root, {}, IDENTITY)
    style_histogram = Counter(_style_key(item.style) for item in items)
    return SvgDocumentSnapshot(
        viewbox=_parse_viewbox(root),
        width=root.attrib.get("width"),
        height=root.attrib.get("height"),
        draw_items=tuple(items),
        element_kind_histogram=dict(Counter(item.kind for item in items)),
        style_histogram=dict(style_histogram),
    )


def _filled_black_ink_area(snapshot: SvgDocumentSnapshot) -> float:
    """Approximate black filled area, including black stroke expansion."""

    try:
        from shapely.geometry import Point, Polygon, box
        from shapely.ops import unary_union
    except Exception:
        return round(sum(item.area for item in snapshot.draw_items), 4)

    geoms = []
    for item in snapshot.draw_items:
        if not _is_black(item.style.get("fill")) or item.bbox is None:
            continue
        min_x, min_y, max_x, max_y = item.bbox
        geom = None
        if item.kind == "circle" and item.radius is not None:
            cx = (min_x + max_x) / 2.0
            cy = (min_y + max_y) / 2.0
            geom = Point(cx, cy).buffer(item.radius, quad_segs=32)
        elif item.kind == "rect":
            geom = box(min_x, min_y, max_x, max_y)
        elif item.rings:
            ring_geoms = []
            for ring in item.rings:
                if len(ring) < 3:
                    continue
                candidate = Polygon(ring)
                if not candidate.is_valid:
                    candidate = candidate.buffer(0)
                if not candidate.is_empty:
                    ring_geoms.append(candidate)
            if ring_geoms:
                geom = unary_union(ring_geoms)
        elif item.area > 0:
            geom = box(min_x, min_y, max_x, max_y)
        if geom is None or geom.is_empty:
            continue
        stroke = _effective_stroke(item.style)
        if _is_black(stroke) and item.stroke_width > 0:
            geom = geom.buffer(item.stroke_width / 2.0, quad_segs=16, join_style=1)
        geoms.append(geom)

    if not geoms:
        return 0.0
    return round(float(unary_union(geoms).area), 4)


def semantic_metrics(svg: str) -> dict[str, object]:
    """Return the metric dict used by synthetic PCB SVG oracle checks."""

    snapshot = analyze_svg(svg)
    draw_items = [
        item for item in snapshot.draw_items
        if not _is_background_rect(item)
    ]
    stroke_items = [item for item in draw_items if item.kind in STROKE_TAGS]
    return {
        "viewbox": snapshot.viewbox,
        "total_paths": sum(1 for item in draw_items if item.kind == "path"),
        "total_circles": sum(1 for item in draw_items if item.kind == "circle"),
        "total_strokes": len(stroke_items),
        "white_drill_circles": sum(
            1
            for item in draw_items
            if item.kind == "circle"
            and _is_white(item.style.get("fill"))
            and _effective_stroke(item.style) == "none"
        ),
        "white_stroke_paths": sum(
            1
            for item in stroke_items
            if item.style.get("fill") == "none"
            and _is_white(_effective_stroke(item.style))
        ),
        "stroke_paths_0p1000": sum(
            1
            for item in stroke_items
            if item.style.get("fill") == "none"
            and abs(item.stroke_width - 0.1) <= 1e-3
        ),
        "stroke_paths_1p0000": sum(
            1
            for item in stroke_items
            if item.style.get("fill") == "none"
            and abs(item.stroke_width - 1.0) <= 1e-3
        ),
        "filled_black_ink_area": _filled_black_ink_area(snapshot),
    }
