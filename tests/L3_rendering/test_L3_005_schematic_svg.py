"""
L3_005: Schematic SVG Rendering Tests

Tests schematic SVG rendering against KiCad CLI reference output.

Test Cases:
- cases/svg/schematics/input/*.kicad_sch - Input schematic files
- cases/svg/schematics/reference_output/*.svg - KiCad CLI generated reference
- cases/svg/schematics/output/*.svg - Python generated (test run)
- cases/svg/schematics/diff/*.svg - Visual overlay diffs

Reference Generation:
    kicad-cli sch export svg --output <dir> --exclude-drawing-sheet <input.kicad_sch>
"""

import pytest
import re

from kicad_monkey import KiCadSchematic, render_schematic_svg
from kicad_monkey.testing.corpus import get_kicad_topic_dir

# Shared persistent asset directories
CASES_DIR = get_kicad_topic_dir("schematic_svg")
INPUT_DIR = CASES_DIR / "input"
REFERENCE_DIR = CASES_DIR / "reference_output"
OUTPUT_DIR = CASES_DIR / "output"
DIFF_DIR = OUTPUT_DIR / "diff"


def get_schematic_test_cases():
    """Discover schematic test cases from input directory."""
    if not INPUT_DIR.exists():
        return []
    return [f.stem for f in INPUT_DIR.glob("*.kicad_sch")]


class TestSchematicSvgRendering:
    """Schematic SVG rendering tests."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self):
        """Ensure output directories exist."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        DIFF_DIR.mkdir(parents=True, exist_ok=True)

    @pytest.mark.parametrize("case_name", get_schematic_test_cases())
    def test_schematic_renders(self, case_name):
        """Test that schematic renders to non-empty SVG."""
        input_file = INPUT_DIR / f"{case_name}.kicad_sch"
        if not input_file.exists():
            pytest.skip(f"Input file not found: {input_file}")

        sch = KiCadSchematic.from_file(input_file)
        svg = render_schematic_svg(sch)

        assert svg is not None
        assert len(svg) > 500, f"SVG too small for {case_name}"
        assert "<svg" in svg

        # Save output
        output_file = OUTPUT_DIR / f"{case_name}_python.svg"
        output_file.write_text(svg, encoding="utf-8")

    @pytest.mark.parametrize("case_name", get_schematic_test_cases())
    def test_schematic_has_wires(self, case_name):
        """Test that schematic SVG contains wires."""
        input_file = INPUT_DIR / f"{case_name}.kicad_sch"
        if not input_file.exists():
            pytest.skip(f"Input file not found: {input_file}")

        sch = KiCadSchematic.from_file(input_file)

        if len(sch.wires) == 0:
            pytest.skip(f"Schematic {case_name} has no wires")

        svg = render_schematic_svg(sch)

        assert (
            '<line' in svg
            or 'class="wire"' in svg
            or 'data-ref="wire"' in svg
        ), f"No wires rendered in {case_name}"

    @pytest.mark.parametrize("case_name", get_schematic_test_cases())
    def test_schematic_has_symbols(self, case_name):
        """Test that schematic SVG contains symbols."""
        input_file = INPUT_DIR / f"{case_name}.kicad_sch"
        if not input_file.exists():
            pytest.skip(f"Input file not found: {input_file}")

        sch = KiCadSchematic.from_file(input_file)

        if len(sch.symbols) == 0:
            pytest.skip(f"Schematic {case_name} has no symbols")

        svg = render_schematic_svg(sch)

        assert (
            'class="symbol"' in svg
            or 'data-ref="symbol_instance"' in svg
        ), f"No symbols rendered in {case_name}"

    @pytest.mark.parametrize("case_name", get_schematic_test_cases())
    def test_schematic_viewbox_reasonable(self, case_name):
        """Test that schematic viewBox is reasonable."""
        input_file = INPUT_DIR / f"{case_name}.kicad_sch"
        if not input_file.exists():
            pytest.skip(f"Input file not found: {input_file}")

        sch = KiCadSchematic.from_file(input_file)
        svg = render_schematic_svg(sch)

        # Extract viewBox
        match = re.search(r'viewBox="([^"]+)"', svg)
        assert match, f"No viewBox in {case_name}"

        parts = match.group(1).split()
        assert len(parts) == 4, f"Invalid viewBox in {case_name}"

        width = float(parts[2])
        height = float(parts[3])

        # Reasonable size (10mm to 1000mm)
        assert 10 < width < 1000, f"Unreasonable width {width} for {case_name}"
        assert 10 < height < 1000, f"Unreasonable height {height} for {case_name}"


class TestSchematicSvgComparison:
    """Compare Python output against KiCad CLI reference."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self):
        """Ensure output directories exist."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        DIFF_DIR.mkdir(parents=True, exist_ok=True)

    @pytest.mark.parametrize("case_name", get_schematic_test_cases())
    def test_reference_exists(self, case_name):
        """Test that KiCad CLI reference SVG exists."""
        ref_file = REFERENCE_DIR / f"{case_name}.svg"
        if not ref_file.exists():
            input_file = INPUT_DIR / f"{case_name}.kicad_sch"
            pytest.skip(f"Reference not found. Generate with:\n"
                       f"  kicad-cli sch export svg --output {REFERENCE_DIR} "
                       f"--exclude-drawing-sheet {input_file}")

    @pytest.mark.parametrize("case_name", get_schematic_test_cases())
    def test_svg_comparison(self, case_name):
        """Compare Python SVG against KiCad CLI reference.

        Documents differences between Python renderer and KiCad CLI.
        Creates visual diff for manual inspection.
        """
        input_file = INPUT_DIR / f"{case_name}.kicad_sch"
        ref_file = REFERENCE_DIR / f"{case_name}.svg"

        if not input_file.exists():
            pytest.skip(f"Input not found: {input_file}")
        if not ref_file.exists():
            pytest.skip(f"Reference not found: {ref_file}")

        # Generate Python SVG
        sch = KiCadSchematic.from_file(input_file)
        svg = render_schematic_svg(sch)
        output_file = OUTPUT_DIR / f"{case_name}_python.svg"
        output_file.write_text(svg, encoding="utf-8")

        # Load reference
        ref_svg = ref_file.read_text(encoding="utf-8")

        # Extract and compare metrics
        python_metrics = self._extract_svg_metrics(svg, "Python")
        ref_metrics = self._extract_svg_metrics(ref_svg, "KiCad CLI")

        print(f"\n{case_name}:")
        print(f"  Python: {python_metrics}")
        print(f"  KiCad:  {ref_metrics}")

        # Create visual diff
        try:
            from svg.svg_diff_helpers import create_overlay_diff
            diff_file = DIFF_DIR / f"{case_name}_diff.svg"
            create_overlay_diff(ref_file, output_file, diff_file)
            print(f"  Diff: {diff_file}")
        except Exception as e:
            print(f"  Diff failed: {e}")

        # Count major elements
        python_lines = svg.count("<line")
        ref_lines = ref_svg.count("<line") + ref_svg.count("<path")

        python_rects = svg.count("<rect")
        ref_rects = ref_svg.count("<rect")

        print(f"  Lines: Python={python_lines}, KiCad~={ref_lines}")
        print(f"  Rects: Python={python_rects}, KiCad={ref_rects}")

        # Basic assertions
        assert len(svg) > 500, "Python SVG too small"
        assert len(ref_svg) > 500, "Reference SVG too small"

    def _extract_svg_metrics(self, svg: str, label: str) -> dict:
        """Extract basic metrics from SVG."""
        metrics = {"label": label}

        # Size
        metrics["bytes"] = len(svg)

        # ViewBox
        match = re.search(r'viewBox="([^"]+)"', svg)
        if match:
            parts = match.group(1).split()
            if len(parts) == 4:
                metrics["viewBox"] = f"{parts[2]}x{parts[3]}"

        return metrics


class TestSchematicSvgKnownIssues:
    """Track known differences between Python and KiCad CLI output.

    These tests document current limitations and should be fixed over time.
    """

    def test_coordinate_system_difference(self):
        """Document: KiCad CLI uses full page, Python crops to content."""
        # KiCad CLI: viewBox="0 0 297.0022 210.0072" (full A4 page)
        # Python:    viewBox="147.4 35.64 102.71 96.36" (content bounds + margin)
        #
        # Decision needed: Should Python match full page or stay cropped?
        pass

    def test_text_rendering_difference(self):
        """Document: KiCad CLI renders text as vector paths, Python uses <text>."""
        # KiCad CLI: <path d="M 165.753..." /> (Hershey stroke font)
        # Python:    <text x="..." y="...">1</text>
        #
        # Vector paths are more accurate but harder to generate.
        # Consider implementing kicad_stroke_font.py for exact match.
        pass

    def test_color_scheme_difference(self):
        """Document: Colors don't exactly match KiCad default theme."""
        # KiCad CLI: #840000 (body), #A90000 (pin numbers)
        # Python:    #A52A2A (body), #008484 (pins)
        #
        # Need to extract exact colors from KiCad's default color scheme.
        pass

    def test_style_format_difference(self):
        """Document: KiCad uses inline styles, Python uses CSS classes."""
        # KiCad CLI: style="fill:#840000; stroke-width:0.2540;"
        # Python:    class="body-outline" with CSS in <style>
        #
        # This is a style choice - CSS is more maintainable.
        pass
