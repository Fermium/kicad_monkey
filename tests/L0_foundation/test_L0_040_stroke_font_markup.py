"""
L0_040: Stroke Font Text Markup Tests

Regression tests for GitHub issue #1: ``~{}`` overbar (and ``^{}``/``_{}``
super/subscript) markup in pin names was rendered literally by the stroke
font engine instead of being parsed.

Pins the markup parser and glyph emission against KiCad's C++ behavior
(common/font/font.cpp drawMarkup, common/font/stroke_font.cpp
GetTextAsGlyphs, include/font/font_metrics.h):
- marker char (~ ^ _) is only special when immediately followed by ``{``
- overbar: one extra 2-point horizontal bar, trimmed 0.1*size_x at each
  end, at baseline - 1.23 * size_y
- super/subscript: glyphs scaled by 0.8; width contribution scaled by 0.8
- overbar does not change text advance width
"""

import pytest

from kicad_monkey.kicad_stroke_font import (
    OVERBAR_POSITION_FACTOR,
    OVERBAR_TRIM_RATIO,
    SUPER_SUB_SIZE_MULTIPLIER,
    MarkupNode,
    get_renderer,
    has_markup,
    parse_markup,
)

SIZE = 1.27  # mm, KiCad default font size


class TestHasMarkup:
    def test_plain_text(self):
        assert not has_markup("HPI_INT")  # bare _ is literal
        assert not has_markup("~RESET")   # bare ~ is literal
        assert not has_markup("X^2")      # bare ^ is literal
        assert not has_markup("")

    def test_markup_forms(self):
        assert has_markup("~{HPI_INT}")
        assert has_markup("U_{REF}")
        assert has_markup("X^{2}")
        assert has_markup("~{A_{2}B}")


class TestParseMarkup:
    def test_plain(self):
        nodes = parse_markup("ABC")
        assert len(nodes) == 1
        assert nodes[0].text == "ABC"
        assert nodes[0].marker == ""

    def test_overbar(self):
        nodes = parse_markup("~{HPI_INT}")
        assert len(nodes) == 1
        assert nodes[0].marker == "~"
        assert len(nodes[0].children) == 1
        assert nodes[0].children[0].text == "HPI_INT"

    def test_subscript_with_prefix(self):
        nodes = parse_markup("U_{REF}")
        assert [n.marker for n in nodes] == ["", "_"]
        assert nodes[0].text == "U"
        assert nodes[1].children[0].text == "REF"

    def test_superscript(self):
        nodes = parse_markup("X^{2}")
        assert [n.marker for n in nodes] == ["", "^"]
        assert nodes[1].children[0].text == "2"

    def test_nested(self):
        nodes = parse_markup("~{A_{2}B}")
        assert len(nodes) == 1
        assert nodes[0].marker == "~"
        inner = nodes[0].children
        assert [n.marker for n in inner] == ["", "_", ""]
        assert inner[0].text == "A"
        assert inner[1].children[0].text == "2"
        assert inner[2].text == "B"

    def test_bare_marker_is_literal(self):
        # Marker char NOT followed by '{' stays literal (KiCad MARKUP rule).
        nodes = parse_markup("~RESET")
        assert len(nodes) == 1
        assert nodes[0].text == "~RESET"
        assert nodes[0].marker == ""

    def test_unmatched_close_brace_is_literal(self):
        nodes = parse_markup("A}B")
        assert len(nodes) == 1
        assert nodes[0].text == "A}B"


class TestOverbarRendering:
    @pytest.fixture
    def renderer(self):
        return get_renderer()

    def _render(self, renderer, text):
        return renderer.render_text_polylines(
            text, 0.0, 0.0, SIZE, SIZE, h_align="left", v_align="bottom"
        )

    def test_overbar_adds_exactly_one_bar(self, renderer):
        plain = self._render(renderer, "HPI")
        overbar = self._render(renderer, "~{HPI}")
        assert len(overbar) == len(plain) + 1

    def test_glyphs_identical_to_plain(self, renderer):
        """Overbar must not shift the glyphs (width is unchanged)."""
        plain = self._render(renderer, "HPI")
        overbar = self._render(renderer, "~{HPI}")
        bars = [p for p in overbar if p not in plain]
        assert len(bars) == 1, "all glyph polylines should match plain text"

    def test_bar_geometry(self, renderer):
        plain = self._render(renderer, "HPI")
        overbar = self._render(renderer, "~{HPI}")
        bar = [p for p in overbar if p not in plain][0]

        # 2-point horizontal segment
        assert len(bar) == 2
        (x1, y1), (x2, y2) = bar
        assert y1 == pytest.approx(y2)

        # Above all glyph ink (y-down coordinates)
        glyph_min_y = min(y for poly in plain for _, y in poly)
        assert y1 < glyph_min_y

        # Trimmed by 0.1 * size_x at each end:
        # bar spans [trim, advance_width - trim] from the text start.
        advance = renderer._calculate_text_width("HPI") * SIZE
        trim = OVERBAR_TRIM_RATIO * SIZE
        assert abs(x2 - x1) == pytest.approx(advance - 2 * trim, abs=1e-9)

        # Vertical position: 1.23 * size_y above the internal baseline.
        # Hershey glyph ink-bottom sits 1/21 size below that baseline, so
        # measured from ink-bottom the bar is (1.23 + 1/21) * size_y up.
        # This exact relation was verified against the kicad-cli oracle
        # (OVERBAR_TEST_unit1.svg: bar y 7.8111 vs ink-bottom 9.4336).
        ink_bottom_y = max(y for poly in plain for _, y in poly)
        assert ink_bottom_y - y1 == pytest.approx(
            (OVERBAR_POSITION_FACTOR + 1.0 / 21.0) * SIZE, abs=1e-6
        )

    def test_no_literal_markup_glyphs(self, renderer):
        """~ { } must not appear as drawn glyphs (the original bug)."""
        overbar = self._render(renderer, "~{HPI}")
        # Literal rendering of "~{HPI}" would need glyphs for ~ { } too:
        # 3 extra characters worth of strokes. The fixed renderer emits
        # plain-HPI glyph count + 1 bar.
        plain = self._render(renderer, "HPI")
        assert len(overbar) == len(plain) + 1
        # And the advance width must equal the plain text width.
        assert renderer._calculate_text_width("~{HPI}") == pytest.approx(
            renderer._calculate_text_width("HPI")
        )


class TestSuperSubscriptRendering:
    @pytest.fixture
    def renderer(self):
        return get_renderer()

    def _render(self, renderer, text):
        return renderer.render_text_polylines(
            text, 0.0, 0.0, SIZE, SIZE, h_align="left", v_align="bottom"
        )

    @staticmethod
    def _ink_height(polylines):
        ys = [y for poly in polylines for _, y in poly]
        return max(ys) - min(ys)

    def test_scaled_to_080(self, renderer):
        plain_2 = self._render(renderer, "2")
        sub = self._render(renderer, "_{2}")
        sup = self._render(renderer, "^{2}")
        h = self._ink_height(plain_2)
        assert self._ink_height(sub) == pytest.approx(
            h * SUPER_SUB_SIZE_MULTIPLIER, rel=1e-6
        )
        assert self._ink_height(sup) == pytest.approx(
            h * SUPER_SUB_SIZE_MULTIPLIER, rel=1e-6
        )

    def test_subscript_below_superscript(self, renderer):
        """Subscript ink sits lower than superscript ink (y-down)."""
        sub = self._render(renderer, "X_{2}")
        sup = self._render(renderer, "X^{2}")
        sub_max_y = max(y for poly in sub for _, y in poly)
        sup_max_y = max(y for poly in sup for _, y in poly)
        assert sub_max_y > sup_max_y

    def test_width_scaled(self, renderer):
        w_x = renderer._calculate_text_width("X")
        w_2 = renderer._calculate_text_width("2")
        w_sub = renderer._calculate_text_width("X_{2}")
        assert w_sub == pytest.approx(w_x + w_2 * SUPER_SUB_SIZE_MULTIPLIER)


class TestPlainTextUnchanged:
    """Plain text (no markup) must take the identical legacy code path."""

    def test_plain_render_stable(self):
        renderer = get_renderer()
        polys = renderer.render_text_polylines(
            "HPI_INT", 0.0, 0.0, SIZE, SIZE, h_align="center", v_align="center"
        )
        assert len(polys) > 0
        # Bare underscore is literal: glyph count includes the underscore.
        underscore_only = renderer.render_text_polylines(
            "_", 0.0, 0.0, SIZE, SIZE
        )
        assert len(underscore_only) >= 1

    def test_markup_node_defaults(self):
        node = MarkupNode()
        assert node.text == ""
        assert node.marker == ""
        assert node.children == []
