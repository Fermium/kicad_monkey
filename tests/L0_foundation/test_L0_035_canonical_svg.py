"""Test L0_035: canonical SVG oracle analyzer."""

from __future__ import annotations

from svg.canonical_svg import analyze_svg, semantic_metrics


def test_analyzer_applies_inherited_style_and_element_overrides():
    svg = """<svg viewBox="0 0 10 10">
<g style="fill:#000000; stroke:#000000; stroke-width:0.2">
  <circle cx="5" cy="5" r="1" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="0" />
</g>
</svg>"""

    snapshot = analyze_svg(svg)
    item = snapshot.draw_items[0]
    metrics = semantic_metrics(svg)

    assert item.kind == "circle"
    assert item.style["fill"] == "#FFFFFF"
    assert item.style["stroke"] == "#FFFFFF"
    assert item.stroke_width == 0.0
    assert metrics["white_drill_circles"] == 1


def test_analyzer_flattens_nested_transforms_into_bbox():
    svg = """<svg viewBox="0 0 20 30">
<g transform="translate(10 20) rotate(90)">
  <rect x="0" y="0" width="2" height="4" fill="#000000" />
</g>
</svg>"""

    item = analyze_svg(svg).draw_items[0]

    assert item.bbox == (6.0, 20.0, 10.0, 22.0)
    assert item.area == 8.0


def test_analyzer_extracts_simple_path_family_bbox_and_area():
    svg = """<svg viewBox="0 0 10 10">
<path d="M 0 0 L 4 0 L 4 3 Z" fill="#000000" stroke="none" />
</svg>"""

    item = analyze_svg(svg).draw_items[0]
    metrics = semantic_metrics(svg)

    assert item.command_family == "M/L/L/Z"
    assert item.bbox == (0.0, 0.0, 4.0, 3.0)
    assert item.area == 6.0
    assert metrics["filled_black_ink_area"] == 6.0


def test_semantic_metrics_exclude_canvas_background_rect():
    svg = """<svg viewBox="0 0 10 10">
<rect x="0" y="0" width="10" height="10" fill="#FFFFFF" />
<polyline points="1,1 9,1" fill="none" stroke="#000000" stroke-width="0.1" />
</svg>"""

    metrics = semantic_metrics(svg)

    assert metrics["total_strokes"] == 1
    assert metrics["total_circles"] == 0
    assert metrics["stroke_paths_0p1000"] == 1

