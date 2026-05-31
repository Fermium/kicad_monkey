"""
Test L0_013: Drawing sheet emitter (Phase F-6.5)

Pure-unit coverage for ``kicad_drawing_sheet``: ports KiCad's default
drawing-sheet template (``defaultDrawingSheet[]`` from
``drawing_sheet_default_description.cpp``) and emits ``KiCadPlotterOp``
records (PlotPoly + Rect + Text) for the page border, tick marks, tick
labels, and title-block fields.

Exercises:
- ``DEFAULT_KICAD_WKS`` parses cleanly via ``KiCadWorksheet.from_text``
- Corner resolution for all four corner refs (lt/rt/lb/rb)
- Repeat expansion drops items outside the page rect
- ``${VAR}`` and legacy ``%X`` format-code expansion
- Unknown ``${VAR}`` tokens pass through unchanged
- ``incrlabel`` increments trailing digit / alpha character
- Default A4 landscape template emits expected op-kind counts
- Title-block fields appear in emitted Text bodies
- ``page1only`` / ``notonpage1`` filtering by sheet_index
- Setup margins / linewidth / textsize honoured
"""

from __future__ import annotations

import base64
from collections import Counter
import json

import pytest

from kicad_monkey import (
    DEFAULT_KICAD_WKS,
    KiCadPlotterOpKind,
    drawing_sheet_to_ops,
    expand_format_codes,
    load_default_drawing_sheet,
)
from kicad_monkey.kicad_drawing_sheet import (
    _corner_origin_and_signs,
    _increment_label,
    _resolve_point_mm,
)
from kicad_monkey.kicad_worksheet import KiCadWorksheet


# A4 landscape page dimensions in nm (matches kicad_schematic_to_ir's
# paper_size_to_nm output for size="A4", portrait=False).
A4_W_NM = 297_000_000
A4_H_NM = 210_000_000


# ---------------------------------------------------------------------------
# Default template parses
# ---------------------------------------------------------------------------


class TestDefaultTemplateParses:
    def test_constant_is_non_empty(self):
        assert DEFAULT_KICAD_WKS
        assert "(kicad_wks" in DEFAULT_KICAD_WKS
        assert "(setup" in DEFAULT_KICAD_WKS

    def test_default_template_parses_into_worksheet(self):
        wks = load_default_drawing_sheet()
        assert isinstance(wks, KiCadWorksheet)
        # Per the cpp source: 10 lines + 2 rects + 17 tbtexts.
        assert len(wks.lines) == 10
        assert len(wks.rects) == 2
        assert len(wks.texts) == 17

    def test_default_template_setup_matches_cpp(self):
        wks = load_default_drawing_sheet()
        s = wks.setup
        assert s.text_size_x == 1.5
        assert s.text_size_y == 1.5
        assert s.linewidth == 0.15
        assert s.textlinewidth == 0.15
        assert s.left_margin == 10.0
        assert s.right_margin == 10.0
        assert s.top_margin == 10.0
        assert s.bottom_margin == 10.0


# ---------------------------------------------------------------------------
# Corner resolution
# ---------------------------------------------------------------------------


class TestCornerResolution:
    margins = {"left": 10.0, "right": 10.0, "top": 10.0, "bottom": 10.0}

    def test_ltcorner_origin_and_signs(self):
        origin_x, origin_y, sx, sy = _corner_origin_and_signs(
            "ltcorner", 297.0, 210.0, self.margins
        )
        assert (origin_x, origin_y, sx, sy) == (10.0, 10.0, +1.0, +1.0)

    def test_rtcorner_origin_and_signs(self):
        origin_x, origin_y, sx, sy = _corner_origin_and_signs(
            "rtcorner", 297.0, 210.0, self.margins
        )
        assert (origin_x, origin_y, sx, sy) == (287.0, 10.0, -1.0, +1.0)

    def test_lbcorner_origin_and_signs(self):
        origin_x, origin_y, sx, sy = _corner_origin_and_signs(
            "lbcorner", 297.0, 210.0, self.margins
        )
        assert (origin_x, origin_y, sx, sy) == (10.0, 200.0, +1.0, -1.0)

    def test_rbcorner_origin_and_signs(self):
        origin_x, origin_y, sx, sy = _corner_origin_and_signs(
            "rbcorner", 297.0, 210.0, self.margins
        )
        assert (origin_x, origin_y, sx, sy) == (287.0, 200.0, -1.0, -1.0)

    def test_default_empty_corner_is_rbcorner(self):
        # Empty string == default (matches the cpp comment block).
        assert _corner_origin_and_signs(
            "", 297.0, 210.0, self.margins
        ) == _corner_origin_and_signs(
            "rbcorner", 297.0, 210.0, self.margins
        )

    def test_unknown_corner_falls_back_to_rbcorner(self):
        assert _corner_origin_and_signs(
            "garbage", 297.0, 210.0, self.margins
        ) == _corner_origin_and_signs(
            "rbcorner", 297.0, 210.0, self.margins
        )

    def test_resolve_point_with_delta(self):
        from kicad_monkey.kicad_wks_primitives import WksCorner, WksPoint

        # ltcorner, x=50, y=2, delta=+50 should give absolute (110, 12)
        # given lm=10, tm=10.
        pt = WksPoint(x=50.0, y=2.0, corner=WksCorner.LT)
        x_mm, y_mm = _resolve_point_mm(
            pt, 297.0, 210.0, self.margins, delta_x_mm=50.0, delta_y_mm=0.0
        )
        assert x_mm == pytest.approx(110.0)
        assert y_mm == pytest.approx(12.0)

    def test_resolve_point_rbcorner_subtracts_inward(self):
        # Default corner: start (110, 34) means 110mm inward from
        # right edge, 34mm upward from bottom. On A4 landscape with
        # 10mm margins: page_w=297, page_h=210; abs = (287-110, 200-34) = (177, 166).
        from kicad_monkey.kicad_wks_primitives import WksCorner, WksPoint
        pt = WksPoint(x=110.0, y=34.0, corner=WksCorner.NONE)
        x_mm, y_mm = _resolve_point_mm(pt, 297.0, 210.0, self.margins)
        assert x_mm == pytest.approx(177.0)
        assert y_mm == pytest.approx(166.0)


# ---------------------------------------------------------------------------
# Label increment
# ---------------------------------------------------------------------------


class TestIncrementLabel:
    def test_digit_increment(self):
        assert _increment_label("1", 1) == "2"
        assert _increment_label("1", 5) == "6"
        assert _increment_label("9", 1) == "10"

    def test_multi_digit_increment(self):
        assert _increment_label("12", 3) == "15"
        assert _increment_label("99", 1) == "100"

    def test_alpha_increment(self):
        assert _increment_label("A", 1) == "B"
        assert _increment_label("A", 5) == "F"
        assert _increment_label("Z", 1) == "["

    def test_zero_increment_returns_unchanged(self):
        assert _increment_label("1", 0) == "1"
        assert _increment_label("A", 0) == "A"

    def test_empty_string_returns_unchanged(self):
        assert _increment_label("", 1) == ""

    def test_non_alphanumeric_trailing_returns_unchanged(self):
        assert _increment_label("foo!", 1) == "foo!"

    def test_prefix_preserved_around_digit(self):
        # "Page 1" → "Page 2"
        assert _increment_label("Page 1", 1) == "Page 2"


# ---------------------------------------------------------------------------
# Format-code expansion
# ---------------------------------------------------------------------------


class TestExpandFormatCodes:
    tb = {
        "title": "My Schematic",
        "date": "2026-05-09",
        "rev": "A",
        "company": "Acme",
        "comments": {1: "comment one", 2: "comment two"},
    }

    def test_expands_modern_var_tokens(self):
        out = expand_format_codes(
            "Title: ${TITLE}, Date: ${ISSUE_DATE}, Rev: ${REVISION}",
            title_block=self.tb,
        )
        assert out == "Title: My Schematic, Date: 2026-05-09, Rev: A"

    def test_expands_paper_and_kicad_version(self):
        out = expand_format_codes(
            "${KICAD_VERSION} - ${PAPER}",
            paper_name="A4",
            kicad_version="10.0.0",
        )
        assert out == "10.0.0 - A4"

    def test_sheet_index_count_tokens(self):
        out = expand_format_codes(
            "Id: ${#}/${##}",
            sheet_index=2, sheet_count=5,
        )
        assert out == "Id: 2/5"

    def test_comment_tokens(self):
        out = expand_format_codes(
            "C1: ${COMMENT1}, C2: ${COMMENT2}, C3: ${COMMENT3}",
            title_block=self.tb,
        )
        # C3 absent -> empty
        assert out == "C1: comment one, C2: comment two, C3: "

    def test_unknown_var_tokens_pass_through(self):
        out = expand_format_codes("Hello ${NOT_A_REAL_VAR}!", title_block=self.tb)
        assert out == "Hello ${NOT_A_REAL_VAR}!"

    def test_legacy_codes_expand(self):
        out = expand_format_codes(
            "%T - %D - %R - %S/%N",
            title_block=self.tb,
            sheet_index=3, sheet_count=4,
        )
        assert out == "My Schematic - 2026-05-09 - A - 3/4"

    def test_legacy_percent_percent_is_literal_percent(self):
        out = expand_format_codes("100%% complete", title_block={})
        assert out == "100% complete"

    def test_legacy_comment_codes(self):
        # %C0 maps to COMMENT1 (file-spec is 0-based, modern is 1-based,
        # same physical slot).
        out = expand_format_codes(
            "%C0 / %C1", title_block=self.tb,
        )
        assert out == "comment one / comment two"

    def test_standard_keys_precede_project_vars(self):
        out = expand_format_codes(
            "${PAPER} / ${CUSTOM}",
            paper_name="A4",
            project_vars={"PAPER": "OVERRIDDEN", "CUSTOM": "x"},
        )
        assert out == "A4 / x"

    def test_date_token_uses_project_var_not_title_block_date(self):
        out = expand_format_codes(
            "${DATE} / ${ISSUE_DATE} / %D",
            title_block={"date": "TB_DATE"},
            project_vars={"DATE": "PROJECT_DATE"},
        )
        assert out == "PROJECT_DATE / TB_DATE / TB_DATE"

    def test_filename_and_sheetpath(self):
        out = expand_format_codes(
            "File: ${FILENAME} / Sheet: ${SHEETPATH}",
            filename="design.kicad_sch", sheet_path="/sub1/",
        )
        assert out == "File: design.kicad_sch / Sheet: /sub1/"

    def test_missing_title_block_keys_resolve_to_empty(self):
        out = expand_format_codes(
            "Title: ${TITLE}", title_block=None,
        )
        assert out == "Title: "

    def test_title_block_backslash_n_renders_as_newline(self):
        out = expand_format_codes(
            "${TITLE}",
            title_block={"title": "Line 1\\nLine 2"},
        )
        assert out == "Line 1\nLine 2"


class TestRecursiveExpansion:
    """Iterative ``${VAR}`` expansion (mirrors KiCad's ExpandTextVars).

    A token's resolved value may itself contain another ``${VAR}``
    token; the second pass must pick it up. Bounded by
    ``_MAX_VAR_EXPANSION_DEPTH`` to break cycles.
    """

    def test_title_block_field_with_project_var_resolves(self):
        # Canonical F-6.5 follow-on flow: title-block field literal is
        # ``${MY_TITLE}``; project_vars defines MY_TITLE -> "Hello".
        # First pass: ${TITLE} -> "${MY_TITLE}". Second pass: resolves.
        tb = {"title": "${MY_TITLE}"}
        out = expand_format_codes(
            "Title: ${TITLE}",
            title_block=tb,
            project_vars={"MY_TITLE": "Hello"},
        )
        assert out == "Title: Hello"

    def test_chain_of_three_resolves(self):
        # ${A} -> "${B}" -> "${C}" -> "leaf"
        out = expand_format_codes(
            "${A}",
            project_vars={"A": "${B}", "B": "${C}", "C": "leaf"},
        )
        assert out == "leaf"

    def test_unknown_inner_token_passes_through(self):
        # ${A} -> "${UNKNOWN}", second pass leaves ${UNKNOWN} unchanged.
        out = expand_format_codes(
            "${A}",
            project_vars={"A": "${UNKNOWN}"},
        )
        assert out == "${UNKNOWN}"

    def test_cycle_resolves_to_literal_intermediate(self):
        # ${A} -> "${B}" -> "${A}" -> "${B}" -> ... bounded loop exits
        # before infinite recursion. Result must be one of the cycle's
        # literal forms (the loop just exits at max depth without
        # hanging).
        out = expand_format_codes(
            "${A}",
            project_vars={"A": "${B}", "B": "${A}"},
        )
        assert out in ("${A}", "${B}")

    def test_legacy_codes_run_after_modern_expansion(self):
        # Project var resolves first (recursive), then the legacy %T
        # pass picks up the title block. The two phases are
        # independent — a project var that yields ``%T`` is treated
        # as the legacy code.
        tb = {"title": "BookTitle"}
        out = expand_format_codes(
            "${A}",
            title_block=tb,
            project_vars={"A": "%T"},
        )
        assert out == "BookTitle"

    def test_no_recursion_needed_short_circuits(self):
        # Single-pass expansion still works (the loop exits at fixed
        # point on first pass).
        out = expand_format_codes(
            "${TITLE}", title_block={"title": "Plain"},
        )
        assert out == "Plain"


# ---------------------------------------------------------------------------
# End-to-end emit on default template
# ---------------------------------------------------------------------------


def _kind_counter(ops):
    return Counter(o.kind.value if hasattr(o.kind, "value") else o.kind for o in ops)


def _png_b64(width: int, height: int, pixels_per_meter: int | None = None) -> str:
    data = (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + int(width).to_bytes(4, "big")
        + int(height).to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    if pixels_per_meter is not None:
        phys = (
            int(pixels_per_meter).to_bytes(4, "big")
            + int(pixels_per_meter).to_bytes(4, "big")
            + b"\x01"
        )
        data += (9).to_bytes(4, "big") + b"pHYs" + phys + b"\x00\x00\x00\x00"
    return base64.b64encode(data).decode("ascii")


class TestDrawingSheetToOps:
    def test_default_a4_emits_expected_op_kinds(self):
        wks = load_default_drawing_sheet()
        ops = drawing_sheet_to_ops(
            wks,
            paper_width_nm=A4_W_NM,
            paper_height_nm=A4_H_NM,
            title_block={"title": "T", "date": "D", "rev": "R",
                         "company": "C", "comments": {1: "c1"}},
            paper_name="A4",
            kicad_version="10.0.0",
        )
        kinds = _kind_counter(ops)
        # title-block rect + 2 corner-marker rects (3 with repeat=2 from
        # original count of 1, but the (0,0) corner with incrx/y=2 only
        # emits 1 starting + 2 repeats = 3 rects, of which all stay
        # inside the page bounds for A4).
        assert kinds[KiCadPlotterOpKind.RECT.value] >= 3
        # PlotPoly: 4 single-line title-block dividers + 2 short verticals
        # + 4 tick lines (2 horizontal rows + 2 vertical columns) with
        # repeats clipped to A4 inner box.
        assert kinds[KiCadPlotterOpKind.PLOT_POLY.value] >= 10
        # Text: 13 single-shot title-block fields + ~20 tick labels.
        assert kinds[KiCadPlotterOpKind.TEXT.value] >= 30

    def test_default_a4_emits_total_ops_in_known_band(self):
        wks = load_default_drawing_sheet()
        ops = drawing_sheet_to_ops(
            wks, paper_width_nm=A4_W_NM, paper_height_nm=A4_H_NM,
        )
        # Computed band: 3 rects + 22 lines (border ticks for A4 landscape)
        # + 33 texts (title block + tick labels) = 58.
        # Allow ±2 for off-by-one tolerance from the 1mm IsInsidePage
        # slack.
        assert 55 <= len(ops) <= 62

    def test_title_block_fields_appear_in_text_ops(self):
        wks = load_default_drawing_sheet()
        ops = drawing_sheet_to_ops(
            wks, paper_width_nm=A4_W_NM, paper_height_nm=A4_H_NM,
            title_block={
                "title": "MY_TITLE_42",
                "date": "MY_DATE_42",
                "rev": "MY_REV_42",
                "company": "MY_CO_42",
                "comments": {1: "C1_42"},
            },
            paper_name="A4_42",
            kicad_version="VER_42",
            sheet_index=7, sheet_count=9,
        )
        text_bodies = [
            o.payload["text"]
            for o in ops
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        ]
        joined = " || ".join(text_bodies)
        assert "MY_TITLE_42" in joined
        assert "MY_DATE_42" in joined
        assert "MY_REV_42" in joined
        assert "MY_CO_42" in joined
        assert "C1_42" in joined
        assert "A4_42" in joined
        assert "VER_42" in joined
        # Sheet id "Id: 7/9"
        assert "7/9" in joined

    def test_tick_label_increments_alpha_and_digits(self):
        wks = load_default_drawing_sheet()
        ops = drawing_sheet_to_ops(
            wks, paper_width_nm=A4_W_NM, paper_height_nm=A4_H_NM,
        )
        text_bodies = [
            o.payload["text"]
            for o in ops
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        ]
        # Horizontal tick labels: "1", "2", "3", ... should appear.
        assert "1" in text_bodies
        assert "2" in text_bodies
        # Vertical tick labels: "A", "B", "C", ... should appear.
        assert "A" in text_bodies
        assert "B" in text_bodies

    def test_repeats_clipped_outside_page_rect(self):
        # Build a tiny worksheet with one tbtext repeated 100 times at
        # 50mm pitch. On a small page only a couple should survive.
        wks = KiCadWorksheet.from_text("""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 5)(right_margin 5)(top_margin 5)(bottom_margin 5))
(tbtext "1" (name "") (pos 10 1 ltcorner) (font (size 1.3 1.3)) (repeat 100) (incrx 50))
)
""")
        ops = drawing_sheet_to_ops(
            wks, paper_width_nm=100_000_000, paper_height_nm=100_000_000,
        )
        # 100 mm wide page with 5mm margins → inner [5..95]. ltcorner
        # x positions: 15, 65, 115, ... → first two fit (15, 65), 115 out.
        text_ops = [o for o in ops if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"]
        assert len(text_ops) == 2
        bodies = [o.payload["text"] for o in text_ops]
        assert bodies == ["1", "2"]

    def test_repeat_clipping_uses_exact_inner_page_bounds(self):
        wks = KiCadWorksheet.from_text("""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(tbtext "A" (name "") (pos 1 80 ltcorner) (font (size 1.3 1.3)) (repeat 2) (incry 1))
)
""")
        ops = drawing_sheet_to_ops(
            wks, paper_width_nm=100_000_000, paper_height_nm=100_000_000,
        )
        text_ops = [o for o in ops if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"]
        assert [o.payload["text"] for o in text_ops] == ["A"]

    def test_page1only_filter_drops_on_page2(self):
        wks = KiCadWorksheet.from_text("""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(tbtext "P1ONLY" (name "") (pos 50 50 ltcorner) (option page1only))
(tbtext "ALL" (name "") (pos 60 60 ltcorner))
)
""")
        ops_p1 = drawing_sheet_to_ops(
            wks, paper_width_nm=A4_W_NM, paper_height_nm=A4_H_NM,
            sheet_index=1,
        )
        ops_p2 = drawing_sheet_to_ops(
            wks, paper_width_nm=A4_W_NM, paper_height_nm=A4_H_NM,
            sheet_index=2,
        )
        bodies_p1 = sorted(o.payload["text"] for o in ops_p1)
        bodies_p2 = sorted(o.payload["text"] for o in ops_p2)
        assert "P1ONLY" in bodies_p1
        assert "ALL" in bodies_p1
        assert "P1ONLY" not in bodies_p2
        assert "ALL" in bodies_p2

    def test_notonpage1_filter_drops_on_page1(self):
        wks = KiCadWorksheet.from_text("""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(tbtext "NOTP1" (name "") (pos 50 50 ltcorner) (option notonpage1))
)
""")
        ops_p1 = drawing_sheet_to_ops(
            wks, paper_width_nm=A4_W_NM, paper_height_nm=A4_H_NM,
            sheet_index=1,
        )
        ops_p2 = drawing_sheet_to_ops(
            wks, paper_width_nm=A4_W_NM, paper_height_nm=A4_H_NM,
            sheet_index=2,
        )
        assert not any(
            o.payload["text"] == "NOTP1" for o in ops_p1
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        )
        assert any(
            o.payload["text"] == "NOTP1" for o in ops_p2
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        )

    def test_setup_linewidth_used_when_item_unset(self):
        wks = KiCadWorksheet.from_text("""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.42)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(line (name "") (start 50 50) (end 60 60))
)
""")
        ops = drawing_sheet_to_ops(
            wks, paper_width_nm=A4_W_NM, paper_height_nm=A4_H_NM,
        )
        # 0.42mm = 420_000 nm
        line_ops = [o for o in ops if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "PlotPoly"]
        assert len(line_ops) == 1
        assert line_ops[0].payload["width_nm"] == 420_000

    def test_tbtext_terminal_newline_is_trimmed_for_plotter_text(self):
        wks = KiCadWorksheet.from_text("""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(tbtext "Status\n" (name "") (pos 50 50 ltcorner))
)
""")
        ops = drawing_sheet_to_ops(
            wks,
            paper_width_nm=A4_W_NM,
            paper_height_nm=A4_H_NM,
        )

        text_ops = [
            o
            for o in ops
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        ]
        assert [op.payload["text"] for op in text_ops] == ["Status"]

    def test_tbtext_embedded_newlines_are_marked_multiline_for_svg_split(self):
        wks = KiCadWorksheet.from_text("""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(tbtext "Line 1\nLine 2" (name "") (pos 50 50 ltcorner))
)
""")
        ops = drawing_sheet_to_ops(
            wks,
            paper_width_nm=A4_W_NM,
            paper_height_nm=A4_H_NM,
        )

        text_ops = [
            o
            for o in ops
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        ]
        assert text_ops[0].payload["text"] == "Line 1\nLine 2"
        assert text_ops[0].payload["multiline"] is True

    def test_tbtext_font_color_overrides_drawing_sheet_layer_color(self):
        wks = KiCadWorksheet.from_text("""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(tbtext "Status" (name "") (pos 50 50 ltcorner)
  (font (size 1.5 1.5) (color 0 0 0 0.99)))
)
""")
        ops = drawing_sheet_to_ops(
            wks,
            paper_width_nm=A4_W_NM,
            paper_height_nm=A4_H_NM,
        )

        text_ops = [
            o
            for o in ops
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        ]
        assert text_ops[0].payload["color"] == "#000000FC"

    def test_bitmap_emits_plot_image_placeholder(self):
        wks = KiCadWorksheet.from_text("""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(bitmap (name "") (pos 20 20 ltcorner) (scale 0.5) (data "abcd"))
)
""")
        ops = drawing_sheet_to_ops(
            wks,
            paper_width_nm=A4_W_NM,
            paper_height_nm=A4_H_NM,
        )

        image_ops = [
            o
            for o in ops
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "PlotImage"
        ]
        assert len(image_ops) == 1
        assert image_ops[0].payload["x"] == 30_000_000
        assert image_ops[0].payload["y"] == 30_000_000
        assert image_ops[0].payload["image_data_b64"] == "abcd"

    def test_bitmap_uses_png_physical_density_for_extents(self):
        data_b64 = _png_b64(2048, 1587, pixels_per_meter=23622)
        wks = KiCadWorksheet.from_text(f"""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(bitmap (name "") (pos 20 20 ltcorner) (scale 0.5704761905) (data "{data_b64}"))
)
""")
        ops = drawing_sheet_to_ops(
            wks,
            paper_width_nm=A4_W_NM,
            paper_height_nm=A4_H_NM,
        )

        image_op = next(
            o
            for o in ops
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "PlotImage"
        )
        assert image_op.payload["width_nm"] == round(
            2048 * 0.5704761905 * 25.4 / 600.0 * 1_000_000
        )
        assert image_op.payload["height_nm"] == round(
            1587 * 0.5704761905 * 25.4 / 600.0 * 1_000_000
        )

    def test_bitmap_without_density_uses_300_dpi_fallback(self):
        data_b64 = _png_b64(1304, 433)
        wks = KiCadWorksheet.from_text(f"""
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(bitmap (name "") (pos 101 28) (scale 0.25) (data "{data_b64}"))
)
""")
        ops = drawing_sheet_to_ops(
            wks,
            paper_width_nm=A4_W_NM,
            paper_height_nm=A4_H_NM,
        )

        image_op = next(
            o
            for o in ops
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "PlotImage"
        )
        assert image_op.payload["width_nm"] == round(
            1304 * 0.25 * 25.4 / 300.0 * 1_000_000
        )
        assert image_op.payload["height_nm"] == round(
            433 * 0.25 * 25.4 / 300.0 * 1_000_000
        )


# ---------------------------------------------------------------------------
# Integration: schematic_to_ir's sheet_header now carries ops
# ---------------------------------------------------------------------------


class TestSheetHeaderIntegration:
    def test_sheet_header_has_drawing_sheet_ops(self, tmp_path):
        # Minimal A4 schematic with title block.
        from kicad_monkey import KiCadSchematic, schematic_to_ir
        sch_text = """
(kicad_sch (version 20240101) (generator eeschema) (generator_version "10.0")
  (uuid "test-uuid")
  (paper "A4")
  (title_block
    (title "TestTitle")
    (date "2026-05-09")
    (rev "B")
    (company "TestCo")
  )
  (lib_symbols)
  (sheet_instances (path "/" (page "1")))
)
"""
        sch_file = tmp_path / "test.kicad_sch"
        sch_file.write_text(sch_text)
        sch = KiCadSchematic.from_file(str(sch_file))
        doc = schematic_to_ir(sch, source_path=str(sch_file))
        # Find sheet_header record
        headers = [r for r in doc.records if r.kind == "sheet_header"]
        assert len(headers) == 1
        h = headers[0]
        # F-6.5: ops list must now be populated.
        assert len(h.operations) > 30
        # And carry the title block fields.
        text_bodies = [
            o.payload["text"]
            for o in h.operations
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        ]
        joined = " | ".join(text_bodies)
        assert "TestTitle" in joined
        assert "2026-05-09" in joined
        assert "TestCo" in joined
        # FILENAME resolves from source_path basename.
        assert "test.kicad_sch" in joined

    def test_schematic_to_ir_infers_adjacent_project_text_variables(self, tmp_path):
        from kicad_monkey import KiCadSchematic, schematic_to_ir

        sch_text = """
(kicad_sch (version 20240101) (generator eeschema) (generator_version "10.0")
  (uuid "test-uuid")
  (paper "A4")
  (title_block
    (title "${PROJECT_TITLE}")
    (rev "${REVISION}")
  )
  (lib_symbols)
  (sheet_instances (path "/" (page "99")))
)
"""
        sch_file = tmp_path / "test.kicad_sch"
        sch_file.write_text(sch_text)
        (tmp_path / "test.kicad_pro").write_text(
            json.dumps(
                {
                    "sheets": [["root", "Root"], ["child", "Child"]],
                    "text_variables": {
                        "PROJECT_TITLE": "Resolved Project",
                        "REVISION": "R2",
                    }
                }
            )
        )

        sch = KiCadSchematic.from_file(str(sch_file))
        doc = schematic_to_ir(sch, source_path=str(sch_file))

        text_bodies = [
            o.payload["text"]
            for r in doc.records
            if r.kind == "sheet_header"
            for o in r.operations
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        ]
        joined = " | ".join(text_bodies)
        assert "Resolved Project" in joined
        assert "Rev: R2" in joined
        assert "Id: 1/2" in joined

    def test_root_sheetname_expands_empty_but_child_sheetname_expands(self, tmp_path):
        from kicad_monkey import KiCadSchematic, schematic_to_ir

        (tmp_path / "custom.kicad_wks").write_text(
            """
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(tbtext "Sheet=${SHEETNAME}" (name "") (pos 20 20 ltcorner))
)
""",
            encoding="utf-8",
        )
        (tmp_path / "test.kicad_pro").write_text(
            json.dumps(
                {
                    "schematic": {
                        "page_layout_descr_file": "custom.kicad_wks",
                    },
                    "text_variables": {},
                }
            ),
            encoding="utf-8",
        )
        sch_file = tmp_path / "test.kicad_sch"
        sch_file.write_text(
            """
(kicad_sch (version 20240101) (generator eeschema) (generator_version "10.0")
  (uuid "test-uuid")
  (paper "A4")
  (lib_symbols)
  (sheet_instances (path "/" (page "1")))
)
""",
            encoding="utf-8",
        )

        sch = KiCadSchematic.from_file(str(sch_file))
        root_doc = schematic_to_ir(
            sch,
            source_path=str(sch_file),
            sheet_path="/",
            sheet_name="RootName",
        )
        child_doc = schematic_to_ir(
            sch,
            source_path=str(sch_file),
            sheet_path="/Child",
            sheet_name="ChildName",
        )

        def header_texts(doc):
            return [
                o.payload["text"]
                for r in doc.records
                if r.kind == "sheet_header"
                for o in r.operations
                if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
            ]

        assert "Sheet=" in header_texts(root_doc)
        assert "Sheet=RootName" not in header_texts(root_doc)
        assert "Sheet=ChildName" in header_texts(child_doc)

    def test_schematic_to_ir_loads_embedded_project_worksheet(self, tmp_path):
        import zstandard as zstd

        from kicad_monkey import KiCadSchematic, schematic_to_ir

        wks_text = """
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(tbtext "Embedded ${REVISION}" (name "") (pos 20 20 ltcorner))
)
"""
        encoded = base64.b64encode(
            zstd.ZstdCompressor().compress(wks_text.encode("utf-8"))
        ).decode("ascii")
        sch_text = f"""
(kicad_sch (version 20240101) (generator eeschema) (generator_version "10.0")
  (uuid "test-uuid")
  (paper "A4")
  (title_block
    (rev "R9")
  )
  (lib_symbols)
  (sheet_instances (path "/" (page "1")))
  (embedded_files
    (file
      (name "custom.kicad_wks")
      (type worksheet)
      (data |{encoded}|)
    )
  )
)
"""
        sch_file = tmp_path / "test.kicad_sch"
        sch_file.write_text(sch_text)
        (tmp_path / "test.kicad_pro").write_text(
            json.dumps(
                {
                    "schematic": {
                        "page_layout_descr_file": "kicad-embed://custom.kicad_wks",
                    },
                    "text_variables": {},
                }
            )
        )

        sch = KiCadSchematic.from_file(str(sch_file))
        doc = schematic_to_ir(sch, source_path=str(sch_file))

        text_bodies = [
            o.payload["text"]
            for r in doc.records
            if r.kind == "sheet_header"
            for o in r.operations
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        ]
        assert "Embedded R9" in text_bodies
        assert not any(body.startswith("Rev:") for body in text_bodies)

    def test_schematic_to_ir_loads_root_embedded_project_worksheet_for_child_sheet(self, tmp_path):
        import zstandard as zstd

        from kicad_monkey import KiCadSchematic, schematic_to_ir

        wks_text = """
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(tbtext "Root Embedded ${REVISION}" (name "") (pos 20 20 ltcorner))
)
"""
        encoded = base64.b64encode(
            zstd.ZstdCompressor().compress(wks_text.encode("utf-8"))
        ).decode("ascii")
        (tmp_path / "project.kicad_pro").write_text(
            json.dumps(
                {
                    "schematic": {
                        "page_layout_descr_file": "kicad-embed://custom.kicad_wks",
                    },
                    "text_variables": {},
                }
            )
        )
        (tmp_path / "project.kicad_sch").write_text(
            f"""
(kicad_sch (version 20240101) (generator eeschema) (generator_version "10.0")
  (uuid "root-uuid")
  (paper "A4")
  (lib_symbols)
  (sheet_instances (path "/" (page "1")))
  (embedded_files
    (file
      (name "custom.kicad_wks")
      (type worksheet)
      (data |{encoded}|)
    )
  )
)
"""
        )
        sheet_dir = tmp_path / "sheets"
        sheet_dir.mkdir()
        sch_file = sheet_dir / "child.kicad_sch"
        sch_file.write_text(
            """
(kicad_sch (version 20240101) (generator eeschema) (generator_version "10.0")
  (uuid "child-uuid")
  (paper "A4")
  (title_block
    (rev "R10")
  )
  (lib_symbols)
  (sheet_instances (path "/" (page "2")))
)
"""
        )

        sch = KiCadSchematic.from_file(str(sch_file))
        doc = schematic_to_ir(sch, source_path=str(sch_file))

        text_bodies = [
            o.payload["text"]
            for r in doc.records
            if r.kind == "sheet_header"
            for o in r.operations
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        ]
        assert "Root Embedded R10" in text_bodies
        assert not any(body.startswith("Rev:") for body in text_bodies)

    def test_schematic_to_ir_loads_ancestor_project_worksheet_file(self, tmp_path):
        from kicad_monkey import KiCadSchematic, schematic_to_ir

        wks_text = """
(kicad_wks (version 20210606) (generator pl_editor)
(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)
(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))
(tbtext "Ancestor ${REVISION}" (name "") (pos 20 20 ltcorner))
)
"""
        (tmp_path / "custom.kicad_wks").write_text(wks_text)
        (tmp_path / "project.kicad_pro").write_text(
            json.dumps(
                {
                    "schematic": {
                        "page_layout_descr_file": "kicad-embed://custom.kicad_wks",
                    },
                    "text_variables": {},
                }
            )
        )
        sheet_dir = tmp_path / "sheets"
        sheet_dir.mkdir()
        sch_file = sheet_dir / "child.kicad_sch"
        sch_file.write_text(
            """
(kicad_sch (version 20240101) (generator eeschema) (generator_version "10.0")
  (uuid "test-uuid")
  (paper "A4")
  (title_block
    (rev "R7")
  )
  (lib_symbols)
  (sheet_instances (path "/" (page "1")))
)
"""
        )

        sch = KiCadSchematic.from_file(str(sch_file))
        doc = schematic_to_ir(sch, source_path=str(sch_file))

        text_bodies = [
            o.payload["text"]
            for r in doc.records
            if r.kind == "sheet_header"
            for o in r.operations
            if (o.kind.value if hasattr(o.kind, "value") else o.kind) == "Text"
        ]
        assert "Ancestor R7" in text_bodies
