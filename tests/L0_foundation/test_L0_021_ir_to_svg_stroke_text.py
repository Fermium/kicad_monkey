"""
Test L0_021: stroke-text mode in :mod:`kicad_monkey.kicad_ir_to_svg`.

When ``KiCadSvgRenderOptions.text_as_polygons=True`` (or via the
``polytext()`` factory), the IR ``Text`` op is tessellated through
``KiCadStrokeFontRenderer`` and emitted as ``<polyline>`` strokes
instead of ``<text>``. This locks down the wiring + the mode-switch
contract; visual glyph fidelity vs `kicad-cli` is covered by an
oracle-parity test in a higher stratum.

Pen-width default (when caller passes 0 / None) follows KiCad's
``STROKE_FONT_THICKNESS_RATIO`` — 0.15 normal, 0.20 bold — relative
to ``size_y_nm``.
"""

from __future__ import annotations

import pytest

from kicad_monkey import (
    KiCadPlotterOp,
    KiCadSvgRenderContext,
    KiCadSvgRenderOptions,
    render_op,
)


def _native_ctx() -> KiCadSvgRenderContext:
    return KiCadSvgRenderContext(
        sheet_width_nm=297_000_000,
        sheet_height_nm=210_000_000,
        options=KiCadSvgRenderOptions(text_as_polygons=False),
    )


def _polytext_ctx() -> KiCadSvgRenderContext:
    return KiCadSvgRenderContext(
        sheet_width_nm=297_000_000,
        sheet_height_nm=210_000_000,
        options=KiCadSvgRenderOptions(text_as_polygons=True),
    )


def _text_op(text: str = "ABC", **overrides) -> KiCadPlotterOp:
    kwargs: dict = dict(
        x=10_000_000, y=20_000_000, text=text, orient_deg=0.0,
        size_x_nm=1_270_000, size_y_nm=1_270_000,
    )
    kwargs.update(overrides)
    return KiCadPlotterOp.text(**kwargs)


# ---------------------------------------------------------------------------
# Native vs polytext mode switch
# ---------------------------------------------------------------------------


def test_native_mode_emits_text_element():
    out = render_op(_text_op(), ctx=_native_ctx())
    assert "<text " in out
    assert "<polyline " not in out


def test_polytext_mode_emits_polylines_only():
    out = render_op(_text_op(), ctx=_polytext_ctx())
    assert "<polyline " in out
    assert "<text " not in out


def test_polytext_mode_emits_multiple_strokes_for_multi_letter_text():
    out = render_op(_text_op("HI"), ctx=_polytext_ctx())
    # HI has at least 4 distinct strokes (H=3 + I=1 in Hershey).
    assert out.count("<polyline ") >= 4


def test_polytext_factory_enables_polygon_text():
    """``KiCadSvgRenderOptions.polytext()`` defaults flip the flag on."""
    opts = KiCadSvgRenderOptions.polytext()
    assert opts.text_as_polygons is True


def test_kicad_native_factory_keeps_text_element_path():
    """``KiCadSvgRenderOptions.kicad_native()`` mirrors kicad-cli SVG."""
    opts = KiCadSvgRenderOptions.kicad_native()
    assert opts.text_as_polygons is False


# ---------------------------------------------------------------------------
# Empty text + no-op behaviour
# ---------------------------------------------------------------------------


def test_polytext_empty_text_returns_empty_fragment():
    op = _text_op(text="")
    assert render_op(op, ctx=_polytext_ctx()) == ""


def test_polytext_whitespace_only_text_emits_no_polylines():
    """Pure-space text contributes cursor-advance only — no strokes."""
    out = render_op(_text_op("   "), ctx=_polytext_ctx())
    assert "<polyline " not in out


# ---------------------------------------------------------------------------
# Pen-width default (STROKE_FONT_THICKNESS_RATIO)
# ---------------------------------------------------------------------------


def test_polytext_default_pen_width_is_15_percent_of_font_height():
    """``size_y_nm * 0.15`` for normal weight (1_270_000 nm → ~190_500 nm)."""
    op = _text_op("X", pen_width_nm=0)
    out = render_op(op, ctx=_polytext_ctx())
    # 190_500 nm → 0.1905 mm in default 1mm-per-nm-million units
    assert 'stroke-width="0.1905"' in out


def test_polytext_explicit_pen_width_honoured():
    """A non-zero pen_width_nm overrides the default ratio."""
    op = _text_op("X", pen_width_nm=300_000)  # 0.3 mm
    out = render_op(op, ctx=_polytext_ctx())
    assert 'stroke-width="0.3"' in out


def test_polytext_bold_default_pen_width_is_20_percent_of_font_height():
    """Bold text uses the heavier ratio (0.20 → 254_000 nm → 0.254 mm)."""
    op = _text_op("X", pen_width_nm=0, bold=True)
    out = render_op(op, ctx=_polytext_ctx())
    assert 'stroke-width="0.254"' in out


# ---------------------------------------------------------------------------
# Coordinate sanity
# ---------------------------------------------------------------------------


def test_polytext_strokes_lie_near_anchor_position():
    """Text anchored at (10mm, 20mm) → all polyline coords near (10, 20)."""
    import re

    out = render_op(_text_op("X"), ctx=_polytext_ctx())
    point_pattern = re.compile(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
    coords = [(float(mx), float(my)) for mx, my in point_pattern.findall(out)]
    assert coords, "stroke-text should emit at least one coord"
    # All strokes should be within ~5 mm of the anchor (one font cell).
    for cx, cy in coords:
        assert 5.0 <= cx <= 15.0
        assert 15.0 <= cy <= 25.0


def test_polytext_orientation_rotates_strokes():
    """Rotating the op should rotate the emitted polylines."""
    out_0 = render_op(_text_op("X", orient_deg=0.0), ctx=_polytext_ctx())
    out_90 = render_op(_text_op("X", orient_deg=90.0), ctx=_polytext_ctx())
    assert out_0 != out_90
    assert "<polyline " in out_0
    assert "<polyline " in out_90
