"""
Smoke tests for the maintained KiCad SVG rendering entry points.

This module used to be skipped because it referenced the pre-rename
``kicad`` package. Keep it lightweight: detailed oracle comparison lives
in the L3 rendering suite, while these tests protect the public SVG APIs
and diff helpers from regressing.
"""

from __future__ import annotations

import pytest

from kicad_monkey import (
    KiCadSchematic,
    KiCadSymbolLib,
    SchematicTheme,
    SymbolRenderOptions,
    SymbolTheme,
    render_schematic_svg,
    render_symbol_svg,
)
from kicad_monkey.testing.corpus import get_kicad_topic_dir

from .svg_diff_helpers import compare_svg_bounds, create_overlay_diff


SYMBOL_CASES_DIR = get_kicad_topic_dir("symbol_svg") / "input"
SCHEMATIC_CASES_DIR = get_kicad_topic_dir("schematic_svg") / "input"


def _load_symbol(case_file: str, symbol_name: str | None = None):
    sym_path = SYMBOL_CASES_DIR / case_file
    if not sym_path.exists():
        pytest.skip(f"Symbol file not found: {sym_path}")

    lib = KiCadSymbolLib.from_file(sym_path)
    assert lib.symbols, "Library should have at least one symbol"
    if symbol_name is None:
        return lib.symbols[0]

    for symbol in lib.symbols:
        if symbol.name == symbol_name:
            return symbol
    pytest.skip(f"Symbol {symbol_name!r} not found in {sym_path}")


def _load_sallen_key():
    sch_path = SCHEMATIC_CASES_DIR / "sallen_key.kicad_sch"
    if not sch_path.exists():
        pytest.skip(f"Schematic file not found: {sch_path}")
    return KiCadSchematic.from_file(sch_path)


class TestSymbolSvgRendering:
    """Tests for symbol library SVG rendering."""

    def test_simple_capacitor_symbol(self, tmp_path):
        symbol = _load_symbol("Capacitor.kicad_sym", "C_2P_NP")
        svg = render_symbol_svg(symbol)

        assert svg is not None
        assert len(svg) > 100
        assert "<svg" in svg
        assert any(tag in svg for tag in ("<rect", "<path", "<line", "<polyline"))

        output_path = tmp_path / "capacitor.svg"
        output_path.write_text(svg, encoding="utf-8")
        assert output_path.exists()

    def test_symbol_preview_omits_properties_by_default(self):
        symbol = _load_symbol("Capacitor.kicad_sym", "C_2P_NP")

        preview_svg = render_symbol_svg(symbol)
        cli_style_svg = render_symbol_svg(
            symbol,
            options=SymbolRenderOptions(include_properties=True),
        )

        assert "<desc>C?</desc>" not in preview_svg
        assert "<desc>${VALUE}</desc>" not in preview_svg
        assert "<desc>C?</desc>" in cli_style_svg
        assert "<desc>${VALUE}</desc>" in cli_style_svg

    def test_opamp_symbol(self, tmp_path):
        symbol = _load_symbol("opamp-sot23-5.kicad_sym", "opamp-sot23-5")
        svg = render_symbol_svg(symbol)

        assert svg is not None
        assert len(svg) > 100
        assert any(tag in svg for tag in ("<polyline", "<polygon", "<path"))

        (tmp_path / "opamp.svg").write_text(svg, encoding="utf-8")

    def test_multipart_symbol_renders_pin_text(self, tmp_path):
        symbol = _load_symbol("MIMXRT685SFVKB.kicad_sym", "MIMXRT685SFVKB")
        svg = render_symbol_svg(symbol, options=SymbolRenderOptions(unit=1))

        assert 'class="stroked-text pin-name"' in svg
        assert 'class="stroked-text pin-number"' in svg
        assert "VDD1V8_1" in svg
        assert "A13" in svg

        (tmp_path / "rt685_unit1.svg").write_text(svg, encoding="utf-8")

    def test_black_and_white_theme(self, tmp_path):
        symbol = _load_symbol("Capacitor.kicad_sym", "C_2P_NP")

        svg_bw = render_symbol_svg(symbol, theme=SymbolTheme(black_and_white=True))

        assert svg_bw is not None
        assert len(svg_bw) > 100
        assert "#000000" in svg_bw or "black" in svg_bw.lower()

        (tmp_path / "capacitor_bw.svg").write_text(svg_bw, encoding="utf-8")


class TestSchematicSvgRendering:
    """Tests for schematic SVG rendering."""

    def test_simple_schematic(self, tmp_path):
        sch = _load_sallen_key()
        assert len(sch.symbols) > 0

        svg = render_schematic_svg(sch)

        assert svg is not None
        assert len(svg) > 1000
        assert "<svg" in svg
        assert "<line" in svg or "wire" in svg.lower()
        assert 'data-ref="symbol_instance"' in svg or 'class="symbol"' in svg

        (tmp_path / "sallen_key.svg").write_text(svg, encoding="utf-8")

    def test_schematic_black_and_white(self, tmp_path):
        sch = _load_sallen_key()

        svg_color = render_schematic_svg(sch)
        svg_bw = render_schematic_svg(
            sch,
            theme=SchematicTheme(black_and_white=True),
        )

        assert svg_bw is not None
        assert "#000000" in svg_bw
        assert svg_color != svg_bw

        (tmp_path / "schematic_color.svg").write_text(svg_color, encoding="utf-8")
        (tmp_path / "schematic_bw.svg").write_text(svg_bw, encoding="utf-8")

    def test_schematic_with_labels(self, tmp_path):
        sch = _load_sallen_key()
        assert len(sch.labels) > 0

        svg = render_schematic_svg(sch)

        assert "<text" in svg
        assert "label" in svg.lower()

        (tmp_path / "schematic_with_labels.svg").write_text(svg, encoding="utf-8")


class TestSvgDiffHelpers:
    """Tests for SVG diff helper functions."""

    def test_create_overlay_diff(self, tmp_path):
        svg1 = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">
  <rect x="10" y="10" width="80" height="80" fill="none" stroke="red"/>
</svg>"""

        svg2 = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">
  <rect x="12" y="12" width="76" height="76" fill="none" stroke="blue"/>
</svg>"""

        ref_path = tmp_path / "reference.svg"
        gen_path = tmp_path / "generated.svg"
        diff_path = tmp_path / "diff.svg"

        ref_path.write_text(svg1, encoding="utf-8")
        gen_path.write_text(svg2, encoding="utf-8")

        result = create_overlay_diff(ref_path, gen_path, diff_path)

        assert result == diff_path
        assert diff_path.exists()

        diff_content = diff_path.read_text(encoding="utf-8")
        assert "reference-layer" in diff_content
        assert "generated-layer" in diff_content

    def test_compare_svg_bounds(self, tmp_path):
        svg1 = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">
  <rect x="10" y="10" width="80" height="80"/>
</svg>"""

        svg2 = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0.5 0.5 99 99">
  <rect x="10" y="10" width="80" height="80"/>
</svg>"""

        ref_path = tmp_path / "reference.svg"
        gen_path = tmp_path / "generated.svg"

        ref_path.write_text(svg1, encoding="utf-8")
        gen_path.write_text(svg2, encoding="utf-8")

        passed, details = compare_svg_bounds(ref_path, gen_path, tolerance=1.0)

        assert passed
        assert details["diff_min_x"] == 0.5
        assert details["diff_min_y"] == 0.5
