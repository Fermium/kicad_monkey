"""Shared synthetic-board SVG oracle helpers for KiCad CLI parity checks."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple
from xml.etree import ElementTree as ET

from kicad_monkey.testing.corpus import get_kicad_pcb_foundation_dir

from kicad_cli_resolver import resolve_kicad_cli

GROUP_STYLE_RE = re.compile(r'<g style="([^"]*)">(.*?)</g>', re.DOTALL)
VIEWBOX_RE = re.compile(r'viewBox="([^"]+)"')
WHITE_GROUP_TAGS = ("fill:#FFFFFF", "stroke:none")
SVG_NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
SVG_PATH_TOKEN_RE = re.compile(
    r"[MmLlHhVvZz]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?"
)
UNSUPPORTED_AREA_PATH_RE = re.compile(r"[AaCcQqSsTt]")


@dataclass(frozen=True)
class SyntheticOracleCase:
    """Synthetic case configuration for semantic oracle checks."""

    case_id: str
    board_relpath: str
    layers: Tuple[str, ...]
    metrics: Tuple[str, ...]
    minimums: Tuple[Tuple[str, int], ...]


def _local_svg_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


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


def _iter_svg_elements_with_style(
    element: ET.Element,
    inherited: dict[str, str] | None = None,
):
    style = dict(inherited or {})
    style.update(_parse_style(element.attrib.get("style")))
    for attr_name in ("fill", "stroke", "stroke-width"):
        attr_value = element.attrib.get(attr_name)
        if attr_value is not None:
            style[attr_name] = attr_value.strip()

    yield element, style
    for child in list(element):
        yield from _iter_svg_elements_with_style(child, style)


def _is_black(value: str | None) -> bool:
    if value is None:
        return False
    compact = value.strip().replace(" ", "").upper()
    return compact in {"#000", "#000000", "BLACK"}


def _style_float(style: dict[str, str], name: str, default: float = 0.0) -> float:
    raw = style.get(name)
    if raw is None:
        return default
    match = SVG_NUMBER_RE.search(raw)
    if match is None:
        return default
    return float(match.group(0))


def _attr_float(element: ET.Element, name: str, default: float = 0.0) -> float:
    raw = element.attrib.get(name)
    if raw is None:
        return default
    match = SVG_NUMBER_RE.search(raw)
    if match is None:
        return default
    return float(match.group(0))


def _polygon_from_points(points: list[tuple[float, float]]):
    from shapely.geometry import Polygon

    if len(points) < 3:
        return None
    geom = Polygon(points)
    if geom.is_empty or geom.area <= 0:
        return None
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom if not geom.is_empty else None


def _path_fill_geometries(d_attr: str):
    """Return polygons for simple M/L/H/V/Z SVG paths used by KiCad pads."""
    if UNSUPPORTED_AREA_PATH_RE.search(d_attr):
        return []

    geoms = []
    tokens = SVG_PATH_TOKEN_RE.findall(d_attr.replace(",", " "))
    idx = 0
    cmd = ""
    current: tuple[float, float] = (0.0, 0.0)
    subpath: list[tuple[float, float]] = []

    def finish_subpath() -> None:
        nonlocal subpath
        geom = _polygon_from_points(subpath)
        if geom is not None:
            geoms.append(geom)
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
    return geoms


def _filled_geometry_for_element(element: ET.Element):
    from shapely.geometry import Point, box

    tag = _local_svg_name(element.tag)
    if tag == "circle":
        radius = _attr_float(element, "r")
        if radius <= 0:
            return None
        return Point(
            _attr_float(element, "cx"),
            _attr_float(element, "cy"),
        ).buffer(radius, quad_segs=32)

    if tag == "rect":
        width = _attr_float(element, "width")
        height = _attr_float(element, "height")
        if width <= 0 or height <= 0:
            return None
        x = _attr_float(element, "x")
        y = _attr_float(element, "y")
        return box(x, y, x + width, y + height)

    if tag == "polygon":
        points_attr = element.attrib.get("points", "")
        points: list[tuple[float, float]] = []
        for pair in points_attr.split():
            coords = [float(value) for value in pair.split(",") if value]
            if len(coords) == 2:
                points.append((coords[0], coords[1]))
        return _polygon_from_points(points)

    if tag == "path":
        geoms = _path_fill_geometries(element.attrib.get("d", ""))
        if not geoms:
            return None
        if len(geoms) == 1:
            return geoms[0]
        from shapely.ops import unary_union

        return unary_union(geoms)

    return None


def _filled_black_ink_area(svg: str) -> float:
    """Approximate black filled SVG area, including stroke around filled shapes."""
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return 0.0

    geoms = []
    for element, style in _iter_svg_elements_with_style(root):
        if not _is_black(style.get("fill")):
            continue
        geom = _filled_geometry_for_element(element)
        if geom is None or geom.is_empty:
            continue

        stroke = style.get("stroke")
        stroke_width = _style_float(style, "stroke-width")
        if _is_black(stroke) and stroke_width > 0:
            geom = geom.buffer(stroke_width / 2.0, quad_segs=16, join_style=1)
        geoms.append(geom)

    if not geoms:
        return 0.0

    from shapely.ops import unary_union

    return round(float(unary_union(geoms).area), 4)


SYNTHETIC_ORACLE_CASES: Tuple[SyntheticOracleCase, ...] = (
    SyntheticOracleCase(
        case_id="via_copper_drill",
        board_relpath="case019__via_basic/one_via.kicad_pcb",
        layers=("F.Cu",),
        metrics=("viewbox", "white_drill_circles", "total_circles"),
        minimums=(("white_drill_circles", 1),),
    ),
    SyntheticOracleCase(
        case_id="via_edgecuts_drill_outline",
        board_relpath="case019__via_basic/one_via.kicad_pcb",
        layers=("Edge.Cuts",),
        metrics=("viewbox",),
        minimums=(),
    ),
    SyntheticOracleCase(
        case_id="slot_copper_drill_fill",
        board_relpath="case084__pad_slot_hole/one_slot_drill.kicad_pcb",
        layers=("F.Cu",),
        metrics=("viewbox", "white_stroke_paths"),
        minimums=(("white_stroke_paths", 1),),
    ),
    SyntheticOracleCase(
        case_id="slot_edgecuts_drill_outline",
        board_relpath="case084__pad_slot_hole/one_slot_drill.kicad_pcb",
        layers=("Edge.Cuts",),
        metrics=("viewbox", "stroke_paths_1p0000"),
        minimums=(("stroke_paths_1p0000", 1),),
    ),
    SyntheticOracleCase(
        case_id="zone_fill_top_copper",
        board_relpath="case024__fill_top_zone/one_zone_filled_top.kicad_pcb",
        layers=("F.Cu",),
        metrics=("viewbox", "total_strokes", "total_circles"),
        minimums=(("total_strokes", 1),),
    ),
    SyntheticOracleCase(
        case_id="outline_only_edgecuts",
        board_relpath="case037__outline_rect/board_outline.kicad_pcb",
        layers=("Edge.Cuts",),
        metrics=("viewbox",),
        minimums=(),
    ),
    # Phase C lead-in: knockout text on silkscreen — one ``gr_text``
    # with ``knockout`` modifier on F.SilkS. Validates that the IR
    # renderer's text-knockout geometry matches kicad-cli structurally.
    SyntheticOracleCase(
        case_id="knockout_text_silk",
        board_relpath="case200__text_knockout_basic/simple_test_knockout.kicad_pcb",
        layers=("F.SilkS",),
        metrics=("viewbox",),
        minimums=(),
    ),
    # Phase C: footprint-local ``fp_text`` knockout on silkscreen.
    # ``component_designator_top.kicad_pcb`` contains an ``fp_text user
    # "+"`` with ``knockout`` modifier on F.SilkS using an Arial Bold
    # face with a real ``render_cache`` polygon. Validates that the IR
    # renderer applies the same fill-rule-evenodd compound polygon
    # treatment to footprint-local text that it does for board-level
    # ``gr_text``.
    SyntheticOracleCase(
        case_id="knockout_fp_text_silk",
        board_relpath="case066__comp_smd_top_designator/component_designator_top.kicad_pcb",
        layers=("F.SilkS",),
        metrics=("viewbox",),
        minimums=(),
    ),
    # Phase C dimensions: synthetic per-type dimension fixtures. ``dim_center``
    # is the only case with full IR-vs-CLI metric parity today (crosshair has
    # no value text). The other six types embed a tessellated dimension-value
    # text on Cmts.User that the IR renderer does not yet emit — they are
    # registered here for fixture stability and listed as known gaps in
    # ``test_L3_007_pcb_ir_svg_oracle.py``.
    SyntheticOracleCase(
        case_id="dim_center",
        board_relpath="case221__dim_center/dim_center.kicad_pcb",
        layers=("Cmts.User",),
        metrics=("viewbox", "total_strokes"),
        minimums=(("total_strokes", 2),),
    ),
    SyntheticOracleCase(
        case_id="dim_aligned_horizontal",
        board_relpath="case220__dim_aligned_horizontal/dim_aligned_horizontal.kicad_pcb",
        layers=("Cmts.User",),
        metrics=("viewbox",),
        minimums=(),
    ),
    SyntheticOracleCase(
        case_id="dim_orthogonal_horizontal",
        board_relpath="case224__dim_orthogonal_horizontal/dim_orthogonal_horizontal.kicad_pcb",
        layers=("Cmts.User",),
        metrics=("viewbox",),
        minimums=(),
    ),
    SyntheticOracleCase(
        case_id="dim_orthogonal_vertical",
        board_relpath="case225__dim_orthogonal_vertical/dim_orthogonal_vertical.kicad_pcb",
        layers=("Cmts.User",),
        metrics=("viewbox",),
        minimums=(),
    ),
    SyntheticOracleCase(
        case_id="dim_leader_plain",
        board_relpath="case223__dim_leader_plain/dim_leader_plain.kicad_pcb",
        layers=("Cmts.User",),
        metrics=("viewbox",),
        minimums=(),
    ),
    SyntheticOracleCase(
        case_id="dim_leader_frame_rect",
        board_relpath="case222__dim_leader_frame_rect/dim_leader_frame_rect.kicad_pcb",
        layers=("Cmts.User",),
        metrics=("viewbox",),
        minimums=(),
    ),
    SyntheticOracleCase(
        case_id="dim_radial",
        board_relpath="case226__dim_radial/dim_radial.kicad_pcb",
        layers=("Cmts.User",),
        metrics=("viewbox",),
        minimums=(),
    ),
    # Phase C stroke-style decomposition: dashed/dotted/dash-dot line and
    # arc gr_* primitives. kicad-cli decomposes these into per-dash
    # ``ThickSegment`` calls via ``STROKE_PARAMS::Stroke`` rather than
    # using CSS ``stroke-dasharray``. The IR converter now mirrors that
    # decomposition in :mod:`kicad_stroke_decompose`. Each dash becomes
    # one IR ``thick_segment`` op → one SVG element, so ``total_strokes``
    # parity verifies the algorithm.
    SyntheticOracleCase(
        case_id="line_silk_dashed",
        board_relpath="case243__line_silk_dashed/silk_line_top_dashed.kicad_pcb",
        layers=("F.SilkS",),
        metrics=("viewbox", "total_strokes"),
        minimums=(("total_strokes", 1),),
    ),
    SyntheticOracleCase(
        case_id="line_silk_dotted",
        board_relpath="case244__line_silk_dotted/silk_line_top_dotted.kicad_pcb",
        layers=("F.SilkS",),
        metrics=("viewbox", "total_strokes"),
        minimums=(("total_strokes", 1),),
    ),
    SyntheticOracleCase(
        case_id="line_silk_dash_dot",
        board_relpath="case245__line_silk_dash_dot/silk_line_top_dash_dot.kicad_pcb",
        layers=("F.SilkS",),
        metrics=("viewbox", "total_strokes"),
        minimums=(("total_strokes", 1),),
    ),
    SyntheticOracleCase(
        case_id="line_silk_dash_dot_dot",
        board_relpath="case246__line_silk_dash_dot_dot/silk_line_top_dash_dot_dot.kicad_pcb",
        layers=("F.SilkS",),
        metrics=("viewbox", "total_strokes"),
        minimums=(("total_strokes", 1),),
    ),
    SyntheticOracleCase(
        case_id="arc_silk_dash_dot",
        board_relpath="case232__arc_silk_dash_dot/silk_arc_top_dash_dot.kicad_pcb",
        layers=("F.SilkS",),
        metrics=("viewbox", "total_strokes"),
        minimums=(("total_strokes", 1),),
    ),
    SyntheticOracleCase(
        case_id="arc_silk_dash_dot_dot",
        board_relpath="case233__arc_silk_dash_dot_dot/silk_arc_top_dash_dot_dot.kicad_pcb",
        layers=("F.SilkS",),
        metrics=("viewbox", "total_strokes"),
        minimums=(("total_strokes", 1),),
    ),
    # Pad-shape parity ratchet (2026-05-18). These three cases were
    # previously suspected of IR pad-shape divergence but actually pass
    # IR-vs-CLI metric parity (verified 2026-05-18 across F.Cu). Pinning
    # them here so any regression in the pad emitters trips immediately.
    SyntheticOracleCase(
        case_id="pad_smd_oval_top_copper",
        board_relpath="case013__pad_smd_oval/case013__pad_smd_oval.kicad_pcb",
        layers=("F.Cu",),
        metrics=("viewbox", "total_strokes"),
        minimums=(("total_strokes", 1),),
    ),
    SyntheticOracleCase(
        case_id="pad_th_oval_top_copper",
        board_relpath="case018__pad_th_oval/case018__pad_th_oval.kicad_pcb",
        layers=("F.Cu",),
        metrics=("viewbox", "total_strokes", "total_circles"),
        minimums=(("total_strokes", 1),),
    ),
    SyntheticOracleCase(
        case_id="pad_chamfered_roundrect_top_copper",
        board_relpath="case083__pad_chamfered_roundrect/one_chamfer_roundrect.kicad_pcb",
        layers=("F.Cu",),
        metrics=("viewbox", "total_strokes", "filled_black_ink_area"),
        minimums=(("total_strokes", 1),),
    ),
)


# IR-only oracle cases pin behaviours covered by the PCB IR renderer.
# Consumed exclusively by ``test_L3_007_pcb_ir_svg_oracle``.
IR_ONLY_ORACLE_CASES: Tuple[SyntheticOracleCase, ...] = (
    # Phase E blocker #2 (2026-05-18): case082 has 16 vias including
    # 3 untented variants (``(tenting (front no) (back no))`` etc.)
    # that produce mask openings + drill knockouts on F.Mask / B.Mask.
    # Pins the via-mask synthesis in :func:`via_to_record`
    # (``via_mask_opening`` + ``via_mask_drill`` ops) against CLI.
    SyntheticOracleCase(
        case_id="pad_per_layer_shapes_f_mask",
        board_relpath="case082__pad_per_layer_shapes/synthetic_pad_shapes.kicad_pcb",
        layers=("F.Mask",),
        metrics=("viewbox", "total_circles", "white_drill_circles"),
        minimums=(("white_drill_circles", 1),),
    ),
    SyntheticOracleCase(
        case_id="pad_per_layer_shapes_b_mask",
        board_relpath="case082__pad_per_layer_shapes/synthetic_pad_shapes.kicad_pcb",
        layers=("B.Mask",),
        metrics=("viewbox", "total_circles", "white_drill_circles"),
        minimums=(("white_drill_circles", 1),),
    ),
)


def pcb_foundation_dir() -> Path:
    """Return the synthetic PCB foundation corpus root.

    Migrated 2026-05-17 from ``<corpus>/kicad/board_svg/input/<case>/`` to
    the per-case ``<corpus>/kicad/pcb_foundation/<case>/{input,
    reference_output, output}/`` layout used by all kicad_monkey
    validation work (parsing, IR, SVG, IPC, viz, data-model).
    """
    return get_kicad_pcb_foundation_dir()


def resolve_case_board_path(case: SyntheticOracleCase) -> Path:
    """Resolve a case's board path on disk.

    ``case.board_relpath`` stays in its original ``<case>/<file>`` form;
    this helper injects the ``input/`` segment for the pcb_foundation
    per-case layout.
    """
    case_dir, _, filename = case.board_relpath.partition("/")
    return pcb_foundation_dir() / case_dir / "input" / filename


def find_kicad_cli() -> Path | None:
    """Find a KiCad 9/10 ``kicad-cli`` executable."""
    return resolve_kicad_cli(required_capability="pcb_svg")


def export_svg_with_kicad_cli(
    *,
    kicad_cli: Path,
    board_path: Path,
    layers: Iterable[str],
    output_path: Path,
    timeout_s: int = 60,
) -> None:
    """Export board SVG with kicad-cli using deterministic CLI options."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    layer_csv = ",".join(layers)

    result = subprocess.run(
        [
            str(kicad_cli),
            "pcb",
            "export",
            "svg",
            "--black-and-white",
            "--layers",
            layer_csv,
            "--mode-single",
            "--page-size-mode",
            "2",
            "--exclude-drawing-sheet",
            "--drill-shape-opt",
            "2",
            "--output",
            str(output_path),
            str(board_path),
        ],
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"kicad-cli export failed ({board_path.name}, layers={layer_csv}): {result.stderr.strip()}"
        )
    if not output_path.exists():
        raise RuntimeError(
            f"kicad-cli export produced no output ({board_path.name}, layers={layer_csv})"
        )


def _extract_viewbox(svg: str) -> Tuple[float, float, float, float]:
    match = VIEWBOX_RE.search(svg)
    if not match:
        raise ValueError("SVG missing viewBox")
    parts = [float(p) for p in match.group(1).split()]
    if len(parts) != 4:
        raise ValueError(f"Unexpected viewBox format: {match.group(1)}")
    return tuple(round(v, 4) for v in parts)  # type: ignore[return-value]


def _count_white_drill_circles(svg: str) -> int:
    total = 0
    for style, body in GROUP_STYLE_RE.findall(svg):
        if all(tag in style for tag in WHITE_GROUP_TAGS):
            total += len(re.findall(r"<circle\b", body))
    return total


def _count_paths_for_stroke_width(svg: str, target_width: float, tol: float = 1e-3) -> int:
    total = 0
    for style, body in GROUP_STYLE_RE.findall(svg):
        if "fill:none" not in style:
            continue
        width_match = re.search(r"stroke-width:([0-9.]+)", style)
        if not width_match:
            continue
        width = float(width_match.group(1))
        if abs(width - target_width) <= tol:
            total += len(re.findall(r"<(?:path|polyline|line)\b", body))
    return total


def _count_white_stroke_paths(svg: str) -> int:
    total = 0
    for style, body in GROUP_STYLE_RE.findall(svg):
        if "fill:none" in style and "stroke:#FFFFFF" in style:
            total += len(re.findall(r"<(?:path|polyline|line)\b", body))
    return total


def semantic_snapshot(svg: str) -> Dict[str, object]:
    """Extract semantic metrics used for synthetic oracle comparison.

    ``total_strokes`` is a renderer-agnostic count of stroked /
    bounded-geometry elements:
    ``<path> + <polyline> + <line> + <rect> + <polygon>``. It exists so
    renderers that prefer ``<polyline>``/``<rect>`` can be compared against
    renderers that emit ``<path>`` for everything (such as ``kicad-cli``)
    without false negatives on element choice. The ``<rect>`` count excludes the
    canvas background ``<rect>`` (added on the very first line by the
    IR document envelope) by filtering on ``x="0" y="0"`` fills.
    """
    background_rects = len(
        re.findall(r'<rect\s+x="0"\s+y="0"[^>]*fill="#[Ff][Ff][Ff][Ff][Ff][Ff]"', svg)
    )
    return {
        "viewbox": _extract_viewbox(svg),
        "total_paths": len(re.findall(r"<path\b", svg)),
        "total_circles": len(re.findall(r"<circle\b", svg)),
        "total_strokes": (
            len(re.findall(r"<path\b", svg))
            + len(re.findall(r"<polyline\b", svg))
            + len(re.findall(r"<line\b", svg))
            + max(len(re.findall(r"<rect\b", svg)) - background_rects, 0)
            + len(re.findall(r"<polygon\b", svg))
        ),
        "white_drill_circles": _count_white_drill_circles(svg),
        "white_stroke_paths": _count_white_stroke_paths(svg),
        "stroke_paths_0p1000": _count_paths_for_stroke_width(svg, 0.1),
        "stroke_paths_1p0000": _count_paths_for_stroke_width(svg, 1.0),
        "filled_black_ink_area": _filled_black_ink_area(svg),
    }


def compare_semantic_metrics(
    ours: Dict[str, object],
    reference: Dict[str, object],
    selected_metrics: Iterable[str],
    *,
    # Keep this semantic check focused on gross canvas drift. Canonical KiCad
    # CLI builds differ by ~0.07 mm on these tiny board outlines.
    viewbox_tol_mm: float = 0.1,
) -> list[str]:
    """Compare selected semantic metrics and return mismatch messages."""
    issues: list[str] = []
    for metric in selected_metrics:
        if metric == "viewbox":
            ours_vb = ours.get("viewbox")
            ref_vb = reference.get("viewbox")
            if not isinstance(ours_vb, tuple) or not isinstance(ref_vb, tuple):
                issues.append("viewbox metric malformed")
                continue
            deltas = [abs(float(a) - float(b)) for a, b in zip(ours_vb, ref_vb)]
            if any(delta > viewbox_tol_mm for delta in deltas):
                issues.append(
                    f"viewBox mismatch ours={ours_vb} ref={ref_vb} deltas={tuple(round(d, 4) for d in deltas)}"
                )
            continue

        if metric == "filled_black_ink_area":
            ours_area = float(ours.get(metric, 0.0))
            ref_area = float(reference.get(metric, 0.0))
            tolerance = max(0.005, abs(ref_area) * 0.02)
            delta = abs(ours_area - ref_area)
            if delta > tolerance:
                issues.append(
                    f"{metric} mismatch ours={ours_area} ref={ref_area} "
                    f"delta={round(delta, 4)} tolerance={round(tolerance, 4)}"
                )
            continue

        ours_value = ours.get(metric)
        ref_value = reference.get(metric)
        if ours_value != ref_value:
            issues.append(f"{metric} mismatch ours={ours_value} ref={ref_value}")
    return issues
