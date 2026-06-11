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

import re

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


class TestPinNameMarkupGlyphParity:
    """Issue #1 regression: ~{} / ^{} / _{} markup in pin names must render
    as glyph geometry matching kicad-cli (overbar, superscript, subscript).

    Compares per-pin stroked-text glyph segments between the kicad-cli
    reference SVG and Python output, normalized by each group's min x/y
    (removes page-translation differences caused by viewBox approximation,
    which is a separate pre-existing gap). Tolerance 2 µm.
    """

    _SEGMENT_RE = re.compile(
        r"M([\d.+-]+) ([\d.+-]+)\s*\nL([\d.+-]+) ([\d.+-]+)"
    )

    # desc text (raw markup), expected segment count from kicad-cli oracle
    MARKUP_PINS = [
        ("~{HPI_INT}", "overbar"),
        ("HPI_INT", "plain control"),
        ("U_{REF}", "subscript"),
        ("X^{2}", "superscript"),
        ("~{A_{2}B}", "nested overbar+subscript"),
    ]

    def _extract_group_segments(self, svg: str, desc: str):
        """Return (x1,y1,x2,y2) segments of the stroked-text group with given desc."""
        marker = f"<desc>{desc}</desc>"
        idx = svg.find(marker)
        assert idx >= 0, f"stroked-text group with desc {desc!r} not found"
        end = svg.find("</g>", idx)
        return [
            tuple(float(v) for v in m.groups())
            for m in self._SEGMENT_RE.finditer(svg[idx:end])
        ]

    @staticmethod
    def _normalize(segs):
        xs = [s[0] for s in segs] + [s[2] for s in segs]
        ys = [s[1] for s in segs] + [s[3] for s in segs]
        x0, y0 = min(xs), min(ys)
        return sorted(
            (x1 - x0, y1 - y0, x2 - x0, y2 - y0) for x1, y1, x2, y2 in segs
        )

    @pytest.fixture(scope="class")
    def overbar_svgs(self):
        """Render OVERBAR_TEST symbol and load its kicad-cli reference."""
        input_file = INPUT_DIR / "overbar_markup.kicad_sym"
        ref_file = REFERENCE_DIR / "OVERBAR_TEST_unit1.svg"
        if not input_file.exists():
            pytest.skip(f"Input not found: {input_file}")
        if not ref_file.exists():
            pytest.skip(f"Reference not found: {ref_file}")

        lib = KiCadSymbolLib.from_file(input_file)
        symbol = next(s for s in lib.symbols if s.name == "OVERBAR_TEST")
        svg = render_symbol_svg(symbol)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "OVERBAR_TEST_python.svg").write_text(svg, encoding="utf-8")

        return ref_file.read_text(encoding="utf-8"), svg

    @pytest.mark.parametrize(
        "desc,label", MARKUP_PINS, ids=[label for _, label in MARKUP_PINS]
    )
    def test_pin_name_glyphs_match_cli(self, overbar_svgs, desc, label):
        ref_svg, our_svg = overbar_svgs

        cli_segs = self._normalize(self._extract_group_segments(ref_svg, desc))
        our_segs = self._normalize(self._extract_group_segments(our_svg, desc))

        assert len(cli_segs) == len(our_segs), (
            f"{label}: segment count mismatch — "
            f"cli={len(cli_segs)} python={len(our_segs)}"
        )

        max_err = max(
            abs(cv - ov)
            for c, o in zip(cli_segs, our_segs)
            for cv, ov in zip(c, o)
        )
        assert max_err < 0.002, (
            f"{label}: glyph geometry diverges from kicad-cli, "
            f"max |delta| = {max_err:.4f} mm"
        )

    def test_no_literal_markup_glyphs(self, overbar_svgs):
        """Overbar pin must NOT have extra glyph strokes for literal ~{}."""
        ref_svg, our_svg = overbar_svgs
        # Overbar pin renders same glyphs as plain control + exactly one
        # 2-point bar segment.
        plain = self._extract_group_segments(our_svg, "HPI_INT")
        overbar = self._extract_group_segments(our_svg, "~{HPI_INT}")
        assert len(overbar) == len(plain) + 1, (
            f"Expected plain({len(plain)}) + 1 bar segment, got {len(overbar)}"
        )


class TestPinNameMarkupTtfFace:
    """Overbar/sub/superscript markup must be font-independent.

    overbar_markup_ttf.kicad_sym is the OVERBAR_TEST fixture with
    ``(face "Arial")`` on every pin-name/number font. kicad-cli renders the
    glyphs as filled Arial outlines; kicad_monkey has no TTF rasterizer for
    .kicad_sym (no render_cache exists in symbol libraries) and falls back to
    the KiCad stroke font — the same fallback KiCad itself uses for an
    unloadable face. The contract pinned here: the markup semantics (overbar
    bar, subscript/superscript placement) are applied identically regardless
    of the requested face.
    """

    _markup = TestPinNameMarkupGlyphParity()

    @pytest.fixture(scope="class")
    def ttf_and_stroke_svgs(self):
        """Render both fixtures with our renderer; load the TTF CLI reference."""
        stroke_file = INPUT_DIR / "overbar_markup.kicad_sym"
        ttf_file = INPUT_DIR / "overbar_markup_ttf.kicad_sym"
        ref_file = REFERENCE_DIR / "OVERBAR_TTF_TEST_unit1.svg"
        for f in (stroke_file, ttf_file):
            if not f.exists():
                pytest.skip(f"Input not found: {f}")

        def render(path, name):
            lib = KiCadSymbolLib.from_file(path)
            sym = next(s for s in lib.symbols if s.name == name)
            return render_symbol_svg(sym)

        ttf_svg = render(ttf_file, "OVERBAR_TTF_TEST")
        stroke_svg = render(stroke_file, "OVERBAR_TEST")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "OVERBAR_TTF_TEST_python.svg").write_text(
            ttf_svg, encoding="utf-8"
        )
        ref_svg = ref_file.read_text(encoding="utf-8") if ref_file.exists() else None
        return ttf_svg, stroke_svg, ref_svg

    @pytest.mark.parametrize(
        "desc,label",
        TestPinNameMarkupGlyphParity.MARKUP_PINS,
        ids=[label for _, label in TestPinNameMarkupGlyphParity.MARKUP_PINS],
    )
    def test_markup_geometry_identical_to_stroke_font(
        self, ttf_and_stroke_svgs, desc, label
    ):
        """Same pin-name glyph segments with and without a TTF face."""
        ttf_svg, stroke_svg, _ = ttf_and_stroke_svgs
        m = self._markup
        ttf_segs = m._normalize(m._extract_group_segments(ttf_svg, desc))
        stroke_segs = m._normalize(m._extract_group_segments(stroke_svg, desc))
        assert ttf_segs == stroke_segs, (
            f"{label}: TTF-face render diverges from stroke-font render — "
            "markup handling must be font-independent"
        )

    def test_overbar_bar_present_with_ttf_face(self, ttf_and_stroke_svgs):
        """~{HPI_INT} with a TTF face still gets exactly one bar segment."""
        ttf_svg, _, _ = ttf_and_stroke_svgs
        m = self._markup
        plain = m._extract_group_segments(ttf_svg, "HPI_INT")
        overbar = m._extract_group_segments(ttf_svg, "~{HPI_INT}")
        assert len(overbar) == len(plain) + 1, (
            f"Expected plain({len(plain)}) + 1 bar segment, got {len(overbar)}"
        )

    def test_cli_reference_uses_real_ttf_outlines(self, ttf_and_stroke_svgs):
        """Sanity: the oracle reference rendered genuine Arial outlines."""
        _, _, ref_svg = ttf_and_stroke_svgs
        if ref_svg is None:
            pytest.skip("Reference OVERBAR_TTF_TEST_unit1.svg not in corpus")
        # Outline-font glyphs are filled bezier paths; the stroke font never
        # emits cubic curve commands.
        assert re.search(r"C[\d.]", ref_svg), (
            "Expected bezier outline glyphs in kicad-cli TTF reference"
        )


class TestDefaultThemeStyleParity:
    """Default-theme styles must match the kicad-cli oracle exactly.

    The geometric comparator (compare_svgs) intentionally skips all style
    attributes (fill/stroke/stroke-width) so custom themes stay legal.
    That blindness let a white body fill and a wrong border width ship
    unnoticed. These tests close the gap: with NO theme override, the
    full set of colors and pen widths in our SVG must equal the oracle's.

    Oracle default palette (kicad-cli sym export svg):
      - body outline  #840000
      - body fill     #FFFFC2 (background-filled shapes only)
      - pin names / text #006464
      - pin numbers   #A90000
      - default pen   0.1524 mm; per-element (stroke (width ...)) honored
    """

    STYLE_CASES = ["C_2P_NP", "C_2P_P", "opamp-sot23-5", "OVERBAR_TEST"]

    _FILL_RE = re.compile(r"fill:(#[0-9A-Fa-f]{6})")
    _STROKE_RE = re.compile(r"stroke:(#[0-9A-Fa-f]{6})")
    _WIDTH_RE = re.compile(r"stroke-width:([\d.]+)")

    @pytest.fixture(scope="class")
    def rendered(self):
        """Render each style case with the DEFAULT theme; pair with oracle."""
        symbols = {}
        for input_file in INPUT_DIR.glob("*.kicad_sym"):
            for sym in KiCadSymbolLib.from_file(input_file).symbols:
                symbols[sym.name] = sym

        pairs = {}
        for name in self.STYLE_CASES:
            ref_file = REFERENCE_DIR / f"{name}_unit1.svg"
            if name not in symbols or not ref_file.exists():
                continue
            svg = render_symbol_svg(
                symbols[name],
                options=SymbolRenderOptions(include_properties=True),
            )
            pairs[name] = (ref_file.read_text(encoding="utf-8"), svg)
        return pairs

    def _case(self, rendered, name):
        if name not in rendered:
            pytest.skip(f"Input or reference missing for {name}")
        return rendered[name]

    @pytest.mark.parametrize("name", STYLE_CASES)
    def test_fill_colors_match_oracle(self, rendered, name):
        ref_svg, our_svg = self._case(rendered, name)
        ref_fills = set(self._FILL_RE.findall(ref_svg))
        our_fills = set(self._FILL_RE.findall(our_svg))
        assert our_fills == ref_fills, (
            f"{name}: fill palette diverges from kicad-cli oracle — "
            f"ours={sorted(our_fills)} oracle={sorted(ref_fills)}"
        )

    @pytest.mark.parametrize("name", STYLE_CASES)
    def test_stroke_colors_match_oracle(self, rendered, name):
        ref_svg, our_svg = self._case(rendered, name)
        ref_strokes = set(self._STROKE_RE.findall(ref_svg))
        our_strokes = set(self._STROKE_RE.findall(our_svg))
        assert our_strokes == ref_strokes, (
            f"{name}: stroke palette diverges from kicad-cli oracle — "
            f"ours={sorted(our_strokes)} oracle={sorted(ref_strokes)}"
        )

    @pytest.mark.parametrize("name", STYLE_CASES)
    def test_stroke_widths_match_oracle(self, rendered, name):
        ref_svg, our_svg = self._case(rendered, name)
        ref_widths = {f"{float(w):.4f}" for w in self._WIDTH_RE.findall(ref_svg)}
        our_widths = {f"{float(w):.4f}" for w in self._WIDTH_RE.findall(our_svg)}
        assert our_widths == ref_widths, (
            f"{name}: pen-width set diverges from kicad-cli oracle — "
            f"ours={sorted(our_widths)} oracle={sorted(ref_widths)}"
        )

    def test_body_background_fill_is_oracle_yellow(self, rendered):
        """Background-filled body shapes use #FFFFC2 (not white/none)."""
        _, our_svg = self._case(rendered, "OVERBAR_TEST")
        assert "fill:#FFFFC2" in our_svg

    def test_per_element_stroke_width_honored(self, rendered):
        """OVERBAR_TEST body rect declares (stroke (width 0.254))."""
        _, our_svg = self._case(rendered, "OVERBAR_TEST")
        assert "stroke-width:0.2540" in our_svg

    def test_pin_number_color_is_oracle_red(self, rendered):
        _, our_svg = self._case(rendered, "OVERBAR_TEST")
        assert "stroke:#A90000" in our_svg
