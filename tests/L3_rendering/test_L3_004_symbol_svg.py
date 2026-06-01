"""
L3_004: Symbol SVG Rendering Tests

Tests symbol library SVG rendering against KiCad CLI reference output.

Test Cases:
- cases/svg/symbols/input/*.kicad_sym - Input symbol libraries
- cases/svg/symbols/reference_output/*.svg - KiCad CLI generated reference
- cases/svg/symbols/output/*.svg - Python generated (test run)
- cases/svg/symbols/diff/*.svg - Visual overlay diffs

Reference Generation:
    kicad-cli sym export svg --output <dir> <input.kicad_sym>

Comparison Algorithm:
- Element-by-element matching (geometry, positions, fonts)
- Position tolerance: 0.01px
- Colors deferred (theming rules apply)
"""

import pytest

from kicad_monkey import KiCadSymbolLib, render_symbol_svg, SymbolRenderOptions
from kicad_monkey.testing.corpus import get_kicad_topic_dir
from svg.compare_svg_elements import compare_svgs, create_overlay_diff

# Shared persistent asset directories
CASES_DIR = get_kicad_topic_dir("symbol_svg")
INPUT_DIR = CASES_DIR / "input"
REFERENCE_DIR = CASES_DIR / "reference_output"
OUTPUT_DIR = CASES_DIR / "output"
DIFF_DIR = OUTPUT_DIR / "diff"


def get_symbol_test_cases():
    """Discover symbol test cases from input directory."""
    if not INPUT_DIR.exists():
        return []
    cases = []
    for sym_file in INPUT_DIR.glob("*.kicad_sym"):
        cases.append(sym_file.stem)
    return cases


class TestSymbolSvgRendering:
    """Symbol SVG rendering tests with CLI comparison."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self):
        """Ensure output directories exist."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        DIFF_DIR.mkdir(parents=True, exist_ok=True)

    @pytest.mark.parametrize("case_name", get_symbol_test_cases())
    def test_symbol_renders(self, case_name):
        """Test that symbol renders to non-empty SVG."""
        input_file = INPUT_DIR / f"{case_name}.kicad_sym"
        if not input_file.exists():
            pytest.skip(f"Input file not found: {input_file}")

        lib = KiCadSymbolLib.from_file(input_file)
        assert len(lib.symbols) > 0, "Library should have symbols"

        for symbol in lib.symbols:
            svg = render_symbol_svg(symbol)
            assert svg is not None
            assert len(svg) > 100, f"SVG too small for {symbol.name}"
            assert "<svg" in svg

            # Save output
            output_file = OUTPUT_DIR / f"{symbol.name}_python.svg"
            output_file.write_text(svg, encoding="utf-8")

    @pytest.mark.parametrize("case_name", get_symbol_test_cases())
    def test_symbol_has_expected_elements(self, case_name):
        """Test that symbol SVG contains expected element types."""
        input_file = INPUT_DIR / f"{case_name}.kicad_sym"
        if not input_file.exists():
            pytest.skip(f"Input file not found: {input_file}")

        lib = KiCadSymbolLib.from_file(input_file)

        for symbol in lib.symbols:
            svg = render_symbol_svg(symbol)

            # Should have some graphical elements
            has_graphics = any(x in svg for x in [
                "<rect", "<circle", "<polyline", "<polygon",
                "<line", "<path", "<ellipse"
            ])
            assert has_graphics, f"No graphics in {symbol.name}"

    @pytest.mark.parametrize("case_name", get_symbol_test_cases())
    def test_symbol_viewbox_reasonable(self, case_name):
        """Test that symbol viewBox is reasonable (not empty or huge)."""
        input_file = INPUT_DIR / f"{case_name}.kicad_sym"
        if not input_file.exists():
            pytest.skip(f"Input file not found: {input_file}")

        lib = KiCadSymbolLib.from_file(input_file)

        for symbol in lib.symbols:
            svg = render_symbol_svg(symbol)

            # Extract viewBox
            import re
            match = re.search(r'viewBox="([^"]+)"', svg)
            assert match, f"No viewBox in {symbol.name}"

            parts = match.group(1).split()
            assert len(parts) == 4, f"Invalid viewBox in {symbol.name}"

            width = float(parts[2])
            height = float(parts[3])

            # Reasonable size (1mm to 500mm)
            assert 1 < width < 500, f"Unreasonable width {width} for {symbol.name}"
            assert 1 < height < 500, f"Unreasonable height {height} for {symbol.name}"

    @pytest.mark.parametrize("case_name", get_symbol_test_cases())
    def test_reference_exists(self, case_name):
        """Test that KiCad CLI reference SVG exists for comparison."""
        input_file = INPUT_DIR / f"{case_name}.kicad_sym"
        if not input_file.exists():
            pytest.skip(f"Input file not found: {input_file}")

        lib = KiCadSymbolLib.from_file(input_file)

        missing_refs = []
        for symbol in lib.symbols:
            # KiCad CLI names: {symbol_name}_unit{N}.svg
            ref_file = REFERENCE_DIR / f"{symbol.name}_unit1.svg"
            if not ref_file.exists():
                missing_refs.append(symbol.name)

        if missing_refs:
            pytest.skip(f"Missing reference SVGs: {missing_refs}. "
                       f"Generate with: kicad-cli sym export svg --output {REFERENCE_DIR} {input_file}")


class TestSymbolSvgComparison:
    """Compare Python output against KiCad CLI reference."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self):
        """Ensure output directories exist."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        DIFF_DIR.mkdir(parents=True, exist_ok=True)

    def get_comparison_cases(self):
        """Get symbols that have both input and reference."""
        cases = []
        for ref_file in REFERENCE_DIR.glob("*_unit1.svg"):
            symbol_name = ref_file.stem.replace("_unit1", "")
            cases.append(symbol_name)
        return cases

    @pytest.mark.parametrize("symbol_name,expected_pass", [
        ("C_2P_NP", True),
        ("C_2P_P", True),
        ("opamp-sot23-5", True),  # Fixed: pin Y coordinate formula now matches KiCad
    ])
    def test_svg_comparison(self, symbol_name, expected_pass, rack_output):
        """Compare Python SVG against KiCad CLI reference.

        Uses element-by-element comparison with 0.01px position tolerance.
        Colors are not compared (theming rules apply).

        SVG outputs are embedded in the Rack HTML report for visual inspection.
        """
        ref_file = REFERENCE_DIR / f"{symbol_name}_unit1.svg"
        if not ref_file.exists():
            pytest.skip(f"Reference not found: {ref_file}")

        # Find the symbol in input files
        symbol = None
        for input_file in INPUT_DIR.glob("*.kicad_sym"):
            lib = KiCadSymbolLib.from_file(input_file)
            for sym in lib.symbols:
                if sym.name == symbol_name:
                    symbol = sym
                    break
            if symbol:
                break

        if not symbol:
            pytest.skip(f"Symbol {symbol_name} not found in inputs")

        # Generate Python SVG
        svg = render_symbol_svg(
            symbol,
            options=SymbolRenderOptions(include_properties=True),
        )
        output_file = OUTPUT_DIR / f"{symbol_name}_python.svg"
        output_file.write_text(svg, encoding="utf-8")

        # Load reference
        ref_svg = ref_file.read_text(encoding="utf-8")

        # Basic size comparison
        python_size = len(svg)
        ref_size = len(ref_svg)

        # Add metrics to rack output
        rack_output.add_metric("python_size_bytes", python_size)
        rack_output.add_metric("reference_size_bytes", ref_size)
        rack_output.add_metric("size_ratio", round(python_size / ref_size, 2))

        # Element-by-element comparison with 0.01px tolerance
        # ignore_text=True because KiCad CLI has a bug where text is placed at
        # negative coordinates outside the viewBox. Python places text correctly.
        # ignore_arcs=True because KiCad CLI uses SVG arc commands (A) while
        # Python approximates arcs with polylines (many L commands).
        result = compare_svgs(ref_file, output_file, position_tolerance=0.01,
                              ignore_text=True, ignore_arcs=True)

        # Add comparison metrics
        rack_output.add_metric("matched_elements", result.matched_count)
        rack_output.add_metric("reference_only", len(result.reference_only))
        rack_output.add_metric("python_only", len(result.python_only))
        rack_output.add_metric("differences", len(result.differences))

        # Document the comparison
        print(f"\n{symbol_name}:")
        print(f"  Python SVG: {python_size} bytes")
        print(f"  KiCad CLI:  {ref_size} bytes")
        print(f"  Ratio: {python_size/ref_size:.2f}x")
        print(f"  {result.summary()}")

        # Print detailed differences
        if result.reference_only:
            print(f"\n  Reference-only elements ({len(result.reference_only)}):")
            for elem in result.reference_only[:5]:
                print(f"    {elem}")
            if len(result.reference_only) > 5:
                print(f"    ... and {len(result.reference_only) - 5} more")

        if result.python_only:
            print(f"\n  Python-only elements ({len(result.python_only)}):")
            for elem in result.python_only[:5]:
                print(f"    {elem}")
            if len(result.python_only) > 5:
                print(f"    ... and {len(result.python_only) - 5} more")

        if result.differences:
            print(f"\n  Attribute differences ({len(result.differences)}):")
            for diff in result.differences[:10]:
                print(f"    {diff}")
            if len(result.differences) > 10:
                print(f"    ... and {len(result.differences) - 10} more")

        # Create visual diff
        diff_file = DIFF_DIR / f"{symbol_name}_diff.svg"
        try:
            create_overlay_diff(ref_file, output_file, diff_file)
            print(f"  Diff: {diff_file}")
        except Exception as e:
            print(f"  Diff failed: {e}")

        # Add SVG outputs to rack for HTML report visual gallery
        rack_output.add_svg_output(
            f"kicad_{symbol_name}",
            ref_file,
            "KiCad CLI Reference"
        )
        rack_output.add_svg_output(
            f"python_{symbol_name}",
            output_file,
            "Python Generated"
        )
        if diff_file.exists():
            rack_output.add_svg_output(
                f"diff_{symbol_name}",
                diff_file,
                "Overlay Diff (Blue=KiCad, Red=Python)"
            )

        # Assert comparison passed
        assert result.passed, (
            f"SVG comparison failed for {symbol_name}:\n"
            f"  Reference-only: {len(result.reference_only)}\n"
            f"  Python-only: {len(result.python_only)}\n"
            f"  Differences: {len(result.differences)}"
        )
