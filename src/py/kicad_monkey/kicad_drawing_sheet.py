"""
Drawing sheet (kicad_wks) to KiCadPlotterOp emission.

Ports KiCad's default drawing-sheet template (the
``defaultDrawingSheet[]`` C string in
``common/drawing_sheet/drawing_sheet_default_description.cpp``) and
provides an emitter that resolves corner-relative positions, expands
repeats, substitutes ``${VAR}`` / legacy ``%X`` format codes, and emits
PlotPoly + Text + PlotImage ops in the canonical
:class:`kicad_monkey.KiCadPlotterOp` vocabulary.

Design notes:

* Coordinates in ``.kicad_wks`` files are mm relative to one of the
  page corners (default ``rbcorner`` = bottom-right). The corner ref
  determines the sign of each axis: a positive ``x`` always grows
  *inward* from the corner toward the opposite corner; same for ``y``.
* Margins are inset from the page border. Items are clipped against
  the inner box (left_margin, top_margin) → (page_w - right_margin,
  page_h - bottom_margin). Repeats whose resolved start or end falls
  outside this box are skipped, mirroring KiCad's
  ``DRAWINGSHEET_DATAITEM::IsInsidePage(ii)``.
* tbtext repeat increments the trailing alpha or numeric character in
  the source text (``"1" → "1","2",...``; ``"A" → "A","B","C",...``).
  The ``incrlabel`` field defaults to ``1`` when absent — KiCad's
  ``DRAWINGSHEET_DATAITEM_TEXT::m_IncrementLabel`` ctor default.
* Format-code expansion mirrors KiCad's ``ExpandTextVars`` for
  ``${VAR}`` and the legacy ``%X`` syntax (per the cpp comment block).
  Unknown ``${VAR}`` tokens are left in place; unknown ``%X`` codes
  pass through.

The caller can pass ``project_vars`` to provide custom variables from a
``.kicad_pro`` file. Built-in sheet and title variables take precedence
over same-named project variables.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import TYPE_CHECKING, List, Optional, cast

from ._api_markers import public_api
from .kicad_plotter_ir import (
    KiCadFillType,
    KiCadHorizAlign,
    KiCadPlotterOp,
    KiCadVertAlign,
    styled_plotter_op,
)
from .kicad_lib_symbol_to_ir import rgba_to_hex
from .kicad_schematic_style import (
    DEFAULT_SCHEMATIC_TEXT_PEN_WIDTH_NM,
    LAYER_SCHEMATIC_DRAWINGSHEET,
    apply_default_text_style,
)

_WORKSHEET_BITMAP_DEFAULT_DPI = 300.0

if TYPE_CHECKING:
    from .kicad_worksheet import KiCadWorksheet
    from .kicad_wks_bitmap import WksBitmap
    from .kicad_wks_line import WksLine
    from .kicad_wks_primitives import WksPoint
    from .kicad_wks_rect import WksRect
    from .kicad_wks_text import WksTbText


# ---------------------------------------------------------------------------
# Default drawing sheet template
# ---------------------------------------------------------------------------


# Verbatim copy of ``defaultDrawingSheet[]`` from
# ``common/drawing_sheet/drawing_sheet_default_description.cpp``
# (commit 76f8839fd232; matches the staged kicad-cli build). The
# ``\n`` are part of the file content as KiCad's parser expects.
DEFAULT_KICAD_WKS = (
    "(kicad_wks (version 20210606) (generator pl_editor)\n"
    "(setup (textsize 1.5 1.5)(linewidth 0.15)(textlinewidth 0.15)\n"
    "(left_margin 10)(right_margin 10)(top_margin 10)(bottom_margin 10))\n"
    "(rect (name \"\") (start 110 34) (end 2 2) (comment \"rect around the title block\"))\n"
    "(rect (name \"\") (start 0 0 ltcorner) (end 0 0) (repeat 2) (incrx 2) (incry 2))\n"
    "(line (name \"\") (start 50 2 ltcorner) (end 50 0 ltcorner) (repeat 30) (incrx 50))\n"
    "(tbtext \"1\" (name \"\") (pos 25 1 ltcorner) (font (size 1.3 1.3)) (repeat 100) (incrx 50))\n"
    "(line (name \"\") (start 50 2 lbcorner) (end 50 0 lbcorner) (repeat 30) (incrx 50))\n"
    "(tbtext \"1\" (name \"\") (pos 25 1 lbcorner) (font (size 1.3 1.3)) (repeat 100) (incrx 50))\n"
    "(line (name \"\") (start 0 50 ltcorner) (end 2 50 ltcorner) (repeat 30) (incry 50))\n"
    "(tbtext \"A\" (name \"\") (pos 1 25 ltcorner) (font (size 1.3 1.3)) (justify center) (repeat 100) (incry 50))\n"
    "(line (name \"\") (start 0 50 rtcorner) (end 2 50 rtcorner) (repeat 30) (incry 50))\n"
    "(tbtext \"A\" (name \"\") (pos 1 25 rtcorner) (font (size 1.3 1.3)) (justify center) (repeat 100) (incry 50))\n"
    "(tbtext \"Date: ${ISSUE_DATE}\" (name \"\") (pos 87 6.9))\n"
    "(line (name \"\") (start 110 5.5) (end 2 5.5))\n"
    "(tbtext \"${KICAD_VERSION}\" (name \"\") (pos 109 4.1) (comment \"Kicad version\"))\n"
    "(line (name \"\") (start 110 8.5) (end 2 8.5))\n"
    "(tbtext \"Rev: ${REVISION}\" (name \"\") (pos 24 6.9) (font bold))\n"
    "(tbtext \"Size: ${PAPER}\" (name \"\") (pos 109 6.9) (comment \"Paper format name\"))\n"
    "(tbtext \"Id: ${#}/${##}\" (name \"\") (pos 24 4.1) (comment \"Sheet id\"))\n"
    "(line (name \"\") (start 110 12.5) (end 2 12.5))\n"
    "(tbtext \"Title: ${TITLE}\" (name \"\") (pos 109 10.7) (font (size 2 2) bold italic))\n"
    "(tbtext \"File: ${FILENAME}\" (name \"\") (pos 109 14.3))\n"
    "(line (name \"\") (start 110 18.5) (end 2 18.5))\n"
    "(tbtext \"Sheet: ${SHEETPATH}\" (name \"\") (pos 109 17))\n"
    "(tbtext \"${COMPANY}\" (name \"\") (pos 109 20) (font bold) (comment \"Company name\"))\n"
    "(tbtext \"${COMMENT1}\" (name \"\") (pos 109 23) (comment \"Comment 0\"))\n"
    "(tbtext \"${COMMENT2}\" (name \"\") (pos 109 26) (comment \"Comment 1\"))\n"
    "(tbtext \"${COMMENT3}\" (name \"\") (pos 109 29) (comment \"Comment 2\"))\n"
    "(tbtext \"${COMMENT4}\" (name \"\") (pos 109 32) (comment \"Comment 3\"))\n"
    "(line (name \"\") (start 90 8.5) (end 90 5.5))\n"
    "(line (name \"\") (start 26 8.5) (end 26 2))\n"
    ")\n"
)


@public_api
def load_default_drawing_sheet() -> "KiCadWorksheet":
    """Parse :data:`DEFAULT_KICAD_WKS` into a :class:`KiCadWorksheet`."""
    from .kicad_worksheet import KiCadWorksheet
    return KiCadWorksheet.from_text(DEFAULT_KICAD_WKS)


# ---------------------------------------------------------------------------
# Unit conversion (mirrors kicad_lib_symbol_to_ir.mm_to_nm but lifted
# here to avoid a dep on the symbol module for callers that only need
# the drawing sheet)
# ---------------------------------------------------------------------------


_MM_PER_NM = 1_000_000


def _mm_to_nm(value_mm: float) -> int:
    return int(round(value_mm * _MM_PER_NM))


def _drawing_sheet_pen_width_nm(value_mm: float) -> int:
    return max(_mm_to_nm(value_mm), DEFAULT_SCHEMATIC_TEXT_PEN_WIDTH_NM)


def _drawing_sheet_text_pen_width_nm(
    *,
    size_x_nm: int,
    size_y_nm: int,
    pen_width_mm: float,
    bold: bool,
) -> int:
    if bold:
        auto_bold_width_nm = int(round(min(abs(size_x_nm), abs(size_y_nm)) / 5.0))
        return max(auto_bold_width_nm, DEFAULT_SCHEMATIC_TEXT_PEN_WIDTH_NM)
    return _drawing_sheet_pen_width_nm(pen_width_mm)


def _png_dimensions_and_density(data_b64: str) -> tuple[int, int, int | None, int | None]:
    if not data_b64:
        return 0, 0, None, None
    try:
        data = base64.b64decode(data_b64, validate=False)
    except (binascii.Error, ValueError):
        return 0, 0, None, None
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return 0, 0, None, None

    width = 0
    height = 0
    ppm_x: int | None = None
    ppm_y: int | None = None
    pos = 8
    size = len(data)
    while pos + 8 <= size:
        chunk_len = int.from_bytes(data[pos:pos + 4], "big")
        chunk_type = data[pos + 4:pos + 8]
        chunk_start = pos + 8
        chunk_end = chunk_start + chunk_len
        if chunk_end + 4 > size:
            break
        chunk = data[chunk_start:chunk_end]
        if chunk_type == b"IHDR" and chunk_len >= 8:
            width = int.from_bytes(chunk[0:4], "big")
            height = int.from_bytes(chunk[4:8], "big")
        elif chunk_type == b"pHYs" and chunk_len >= 9 and chunk[8] == 1:
            ppm_x = int.from_bytes(chunk[0:4], "big") or None
            ppm_y = int.from_bytes(chunk[4:8], "big") or None
        pos = chunk_end + 4
    return width, height, ppm_x, ppm_y


def _bitmap_ppi_from_ppm(pixels_per_meter: int | None) -> int | None:
    if pixels_per_meter is None or pixels_per_meter <= 0:
        return None
    return int(round(float(pixels_per_meter) * 0.0254)) or None


def _bitmap_extent_nm(size_px: int, scale: float, pixels_per_meter: int | None) -> int:
    if size_px <= 0:
        return 0
    ppi = _bitmap_ppi_from_ppm(pixels_per_meter)
    if ppi is not None:
        return _mm_to_nm(float(size_px) * float(scale) * 25.4 / ppi)
    return _mm_to_nm(
        float(size_px) * float(scale) * 25.4 / _WORKSHEET_BITMAP_DEFAULT_DPI
    )


# ---------------------------------------------------------------------------
# Format-code expansion
# ---------------------------------------------------------------------------


# Maps the modern ``${VAR}`` token NAME (no braces) to the title-block
# / sheet-context dict key.  KiCad's TITLE_BLOCK resolver handles
# ``ISSUE_DATE``; ``DATE`` is not a title-block alias and must fall
# through to project text variables.
_STANDARD_VAR_KEYS = {
    "ISSUE_DATE": "date",
    "REVISION": "rev",
    "REV": "rev",
    "TITLE": "title",
    "COMPANY": "company",
    "PAPER": "paper",
    "FILENAME": "filename",
    "SHEETPATH": "sheetpath",
    "SHEETNAME": "sheetname",
    "KICAD_VERSION": "kicad_version",
    "#": "sheet_index",
    "##": "sheet_count",
    "SHEETNUMBER": "sheet_index",
    "SHEETCOUNT": "sheet_count",
}

# Comments are 1-9 (the default template uses 1-4); also accept the
# legacy COMMENT0..COMMENT8 spelling some older files use.
for _i in range(1, 10):
    _STANDARD_VAR_KEYS[f"COMMENT{_i}"] = f"comment{_i}"

# Legacy printf-style codes per the cpp comment block.
_LEGACY_CODE_KEYS = {
    "K": "kicad_version",
    "Z": "paper",
    "Y": "company",
    "D": "date",
    "R": "rev",
    "S": "sheet_index",
    "N": "sheet_count",
    "F": "filename",
    "P": "sheetpath",
    "T": "title",
}

_VAR_RE = re.compile(r"\$\{([^}]*)\}")
# Match %% (literal percent), %Cx (comment with single digit), or %X (single-letter code).
_LEGACY_RE = re.compile(r"%(%|C[0-9]|[A-Za-z])")

# Maximum number of ``${VAR}`` substitution passes before giving up.
# Mirrors KiCad's ``ADVANCED_CFG::m_ResolveTextRecursionDepth`` (default
# 5; we use a slightly larger bound to tolerate test fixtures that
# chain a few extra hops). Cycles (``${A}`` → ``${B}`` → ``${A}``) are
# detected by tracking whether the previous pass changed the buffer:
# once a fixed point is reached the loop exits early.
_MAX_VAR_EXPANSION_DEPTH = 10


def _resolve_context_value(name: str, ctx: dict, project_vars: dict) -> Optional[str]:
    """Return the resolved string for a token NAME (no braces / no %)."""
    key = _STANDARD_VAR_KEYS.get(name)
    if key is not None and key in ctx and ctx[key] is not None:
        value = str(ctx[key]).replace("\\n", "\n")
        if value == f"${{{name}}}" and name in project_vars:
            return str(project_vars[name])
        return value
    if name in project_vars:
        return str(project_vars[name])
    return None


def expand_format_codes(
    text: str,
    *,
    title_block: Optional[dict] = None,
    sheet_index: int = 1,
    sheet_count: int = 1,
    paper_name: str = "",
    filename: str = "",
    sheet_path: str = "/",
    sheet_name: str = "",
    kicad_version: str = "",
    project_vars: Optional[dict] = None,
) -> str:
    """Substitute ``${VAR}`` and legacy ``%X`` format codes.

    See the module docstring for the supported set. Unknown
    ``${VAR}`` tokens pass through unchanged (matches KiCad's
    ``ExpandTextVars`` behaviour). Unknown legacy ``%X`` codes also
    pass through unchanged.
    """
    tb = title_block or {}
    pv = project_vars or {}
    comments = tb.get("comments", {}) or {}

    ctx: dict = {
        "title": tb.get("title", "") or "",
        "date": tb.get("date", "") or "",
        "rev": tb.get("rev", "") or "",
        "company": tb.get("company", "") or "",
        "paper": paper_name,
        "filename": filename,
        "sheetpath": sheet_path,
        "sheetname": sheet_name,
        "kicad_version": kicad_version,
        "sheet_index": str(sheet_index),
        "sheet_count": str(sheet_count),
    }
    for i in range(1, 10):
        # comments may be keyed by int or str; tolerate both.
        v = comments.get(i)
        if v is None:
            v = comments.get(str(i))
        ctx[f"comment{i}"] = v or ""

    def _modern(m: re.Match) -> str:
        name = m.group(1).strip()
        resolved = _resolve_context_value(name, ctx, pv)
        if resolved is None:
            return m.group(0)  # leave unchanged
        return resolved

    def _legacy(m: re.Match) -> str:
        code = m.group(1)
        if code == "%":
            return "%"
        if code.startswith("C") and len(code) == 2:
            try:
                idx = int(code[1])
            except ValueError:
                return m.group(0)
            # Legacy "%C0" → COMMENT1 (file-spec uses 0-based, modern
            # ${COMMENTn} is 1-based; same physical slot).
            return ctx.get(f"comment{idx + 1}", "")
        key = _LEGACY_CODE_KEYS.get(code)
        if key is None:
            return m.group(0)
        return ctx.get(key, "")

    # Iterative ``${VAR}`` expansion with bounded depth — mirrors
    # KiCad's ``ExpandTextVars`` recursion. Each pass substitutes the
    # tokens we know how to resolve; if any substitute itself contains
    # a ``${VAR}`` token (e.g. project_vars fed back through a
    # title-block field), the next pass picks it up. Stops at fixed
    # point or after _MAX_VAR_EXPANSION_DEPTH passes — whichever
    # comes first. Cycles thus resolve to the literal previous-pass
    # text rather than infinite-looping.
    out = text
    for _ in range(_MAX_VAR_EXPANSION_DEPTH):
        next_out = _VAR_RE.sub(_modern, out)
        if next_out == out:
            break
        out = next_out
    out = _LEGACY_RE.sub(_legacy, out)
    return out


# ---------------------------------------------------------------------------
# Corner resolution + repeat increment
# ---------------------------------------------------------------------------


def _corner_origin_and_signs(
    corner_value: str,
    page_w_mm: float,
    page_h_mm: float,
    margins: dict,
) -> tuple:
    """Return ``(origin_x_mm, origin_y_mm, sign_x, sign_y)`` for a corner.

    ``corner_value`` is the raw string from ``WksCorner.value``: one of
    ``""`` (default → rbcorner), ``"ltcorner"``, ``"rtcorner"``,
    ``"lbcorner"``, ``"rbcorner"``.
    """
    lm = margins["left"]
    rm = margins["right"]
    tm = margins["top"]
    bm = margins["bottom"]

    # Default empty corner == rbcorner (bottom-right).
    if not corner_value or corner_value == "rbcorner":
        return (page_w_mm - rm, page_h_mm - bm, -1.0, -1.0)
    if corner_value == "ltcorner":
        return (lm, tm, +1.0, +1.0)
    if corner_value == "rtcorner":
        return (page_w_mm - rm, tm, -1.0, +1.0)
    if corner_value == "lbcorner":
        return (lm, page_h_mm - bm, +1.0, -1.0)
    # Forward-compat: unknown corner → behave as default rbcorner.
    return (page_w_mm - rm, page_h_mm - bm, -1.0, -1.0)


def _resolve_point_mm(
    point: "WksPoint",
    page_w_mm: float,
    page_h_mm: float,
    margins: dict,
    *,
    delta_x_mm: float = 0.0,
    delta_y_mm: float = 0.0,
) -> tuple:
    """Resolve a ``WksPoint`` (with corner ref) to absolute (x_mm, y_mm).

    ``delta_x_mm`` / ``delta_y_mm`` are added to the local-frame
    coordinate before applying the corner signs — used for repeat
    expansion (the increments are in the local frame, not absolute).
    """
    origin_x, origin_y, sx, sy = _corner_origin_and_signs(
        point.corner.value, page_w_mm, page_h_mm, margins
    )
    abs_x = origin_x + sx * (point.x + delta_x_mm)
    abs_y = origin_y + sy * (point.y + delta_y_mm)
    return abs_x, abs_y


def _is_inside_page(
    x_mm: float, y_mm: float, page_w_mm: float, page_h_mm: float, margins: dict
) -> bool:
    inner_lt_x = margins["left"]
    inner_lt_y = margins["top"]
    inner_rb_x = page_w_mm - margins["right"]
    inner_rb_y = page_h_mm - margins["bottom"]
    return inner_lt_x <= x_mm <= inner_rb_x and inner_lt_y <= y_mm <= inner_rb_y


# ---------------------------------------------------------------------------
# Label increment for tbtext repeat
# ---------------------------------------------------------------------------


def _increment_label(text: str, increment: int) -> str:
    """Increment the trailing alpha or numeric segment of *text* by *increment*.

    Matches KiCad's ``DRAWINGSHEET_DATAITEM_TEXT::IncrementLabel``.
    Returns the original text unchanged if the trailing character is
    neither digit nor alpha, or if increment is 0.
    """
    if not text or increment == 0:
        return text
    last = text[-1]
    if last.isdigit():
        # Extract trailing digit run, increment as integer.
        i = len(text) - 1
        while i >= 0 and text[i].isdigit():
            i -= 1
        prefix = text[: i + 1]
        try:
            n = int(text[i + 1 :])
        except ValueError:
            return text
        return f"{prefix}{n + increment}"
    if last.isalpha():
        # Increment the trailing letter; ASCII-style ('A'+1='B').
        new_char = chr(ord(last) + increment)
        return text[:-1] + new_char
    return text


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------


def _justify_to_aligns(justify: list) -> tuple:
    """Map a list of justify tokens to ``(h_align, v_align)``.

    KiCad worksheet defaults are LEFT / CENTER (per
    ``DRAWINGSHEET_DATAITEM_TEXT`` ctor).
    """
    h = KiCadHorizAlign.LEFT
    v = KiCadVertAlign.CENTER
    for token in justify or []:
        if token == "left":
            h = KiCadHorizAlign.LEFT
        elif token == "center":
            # ``center`` alone is conventionally h-align by KiCad's
            # parser; vertical centering uses the explicit ``top`` /
            # ``bottom`` tokens. CENTER is already the v-default.
            h = KiCadHorizAlign.CENTER
        elif token == "right":
            h = KiCadHorizAlign.RIGHT
        elif token == "top":
            v = KiCadVertAlign.TOP
        elif token == "bottom":
            v = KiCadVertAlign.BOTTOM
    return h, v


# ---------------------------------------------------------------------------
# Per-element op emitters
# ---------------------------------------------------------------------------


def _line_repeat_ops(
    line: "WksLine",
    page_w_mm: float,
    page_h_mm: float,
    margins: dict,
    default_linewidth_mm: float,
) -> List[KiCadPlotterOp]:
    import math
    ops: List[KiCadPlotterOp] = []
    count = max(1, line.repeat.count)
    incr_x = line.repeat.incr_x
    incr_y = line.repeat.incr_y
    width_mm = line.linewidth if not math.isnan(line.linewidth) else default_linewidth_mm

    for ii in range(count):
        dx = incr_x * ii
        dy = incr_y * ii
        sx_mm, sy_mm = _resolve_point_mm(
            line.start, page_w_mm, page_h_mm, margins,
            delta_x_mm=dx, delta_y_mm=dy,
        )
        ex_mm, ey_mm = _resolve_point_mm(
            line.end, page_w_mm, page_h_mm, margins,
            delta_x_mm=dx, delta_y_mm=dy,
        )
        if ii > 0 and not (
            _is_inside_page(sx_mm, sy_mm, page_w_mm, page_h_mm, margins)
            and _is_inside_page(ex_mm, ey_mm, page_w_mm, page_h_mm, margins)
        ):
            continue
        ops.append(
            styled_plotter_op(
                KiCadPlotterOp.plot_poly(
                    points=[(_mm_to_nm(sx_mm), _mm_to_nm(sy_mm)),
                            (_mm_to_nm(ex_mm), _mm_to_nm(ey_mm))],
                    fill=KiCadFillType.NO_FILL,
                    width_nm=_drawing_sheet_pen_width_nm(width_mm),
                ),
                stroke_color=LAYER_SCHEMATIC_DRAWINGSHEET,
            )
        )
    return ops


def _rect_repeat_ops(
    rect: "WksRect",
    page_w_mm: float,
    page_h_mm: float,
    margins: dict,
    default_linewidth_mm: float,
) -> List[KiCadPlotterOp]:
    import math
    ops: List[KiCadPlotterOp] = []
    count = max(1, rect.repeat.count)
    incr_x = rect.repeat.incr_x
    incr_y = rect.repeat.incr_y
    width_mm = rect.linewidth if not math.isnan(rect.linewidth) else default_linewidth_mm

    for ii in range(count):
        dx = incr_x * ii
        dy = incr_y * ii
        sx_mm, sy_mm = _resolve_point_mm(
            rect.start, page_w_mm, page_h_mm, margins,
            delta_x_mm=dx, delta_y_mm=dy,
        )
        ex_mm, ey_mm = _resolve_point_mm(
            rect.end, page_w_mm, page_h_mm, margins,
            delta_x_mm=dx, delta_y_mm=dy,
        )
        if ii > 0 and not (
            _is_inside_page(sx_mm, sy_mm, page_w_mm, page_h_mm, margins)
            and _is_inside_page(ex_mm, ey_mm, page_w_mm, page_h_mm, margins)
        ):
            continue
        # Emit as a 5-point closed PlotPoly so it diffs against KiCad's
        # ``PLOTTER::Rect`` recorder dump (which generally also lands as
        # 4 PenTo + 1 close, but for rect we model it as the analogous
        # outline; KiCad's Rect virtual is recorded separately as ``Rect``
        # so we use the matching op kind).
        ops.append(
            styled_plotter_op(
                KiCadPlotterOp.rect(
                    x1=_mm_to_nm(sx_mm),
                    y1=_mm_to_nm(sy_mm),
                    x2=_mm_to_nm(ex_mm),
                    y2=_mm_to_nm(ey_mm),
                    fill=KiCadFillType.NO_FILL,
                    width_nm=_drawing_sheet_pen_width_nm(width_mm),
                ),
                stroke_color=LAYER_SCHEMATIC_DRAWINGSHEET,
            )
        )
    return ops


def _tbtext_repeat_ops(
    text: "WksTbText",
    page_w_mm: float,
    page_h_mm: float,
    margins: dict,
    default_text_size_mm: float,
    default_textlinewidth_mm: float,
    expand_kwargs: dict,
) -> List[KiCadPlotterOp]:
    import math
    ops: List[KiCadPlotterOp] = []
    count = max(1, text.repeat.count)
    incr_x = text.repeat.incr_x
    incr_y = text.repeat.incr_y
    # KiCad's IncrementLabel default is 1 when not specified on disk;
    # our parser stores 0 for absent. Treat 0 as "use 1" only when the
    # repeat itself is non-trivial — otherwise honour explicit 0.
    incr_label = text.repeat.incr_label or (1 if count > 1 else 0)

    size_x_mm = text.font.size_x or default_text_size_mm
    size_y_mm = text.font.size_y or default_text_size_mm
    pen_width_mm = (
        text.font.linewidth
        if not math.isnan(text.font.linewidth)
        else default_textlinewidth_mm
    )
    h_align, v_align = _justify_to_aligns(text.justify)

    for ii in range(count):
        dx = incr_x * ii
        dy = incr_y * ii
        x_mm, y_mm = _resolve_point_mm(
            text.pos, page_w_mm, page_h_mm, margins,
            delta_x_mm=dx, delta_y_mm=dy,
        )
        if ii > 0 and not _is_inside_page(x_mm, y_mm, page_w_mm, page_h_mm, margins):
            continue
        body = text.text
        if ii > 0 and incr_label:
            body = _increment_label(body, ii * incr_label)
        body = expand_format_codes(body, **expand_kwargs)
        if body.endswith("\r\n"):
            body = body[:-2]
        elif body.endswith(("\r", "\n")):
            body = body[:-1]
        size_x_nm = _mm_to_nm(size_x_mm)
        size_y_nm = _mm_to_nm(size_y_mm)
        bold = bool(text.font.bold)
        text_style = {
            "size_x_nm": size_x_nm,
            "size_y_nm": size_y_nm,
            "h_align": h_align,
            "v_align": v_align,
            "pen_width_nm": _drawing_sheet_text_pen_width_nm(
                size_x_nm=size_x_nm,
                size_y_nm=size_y_nm,
                pen_width_mm=pen_width_mm,
                bold=bold,
            ),
            "italic": bool(text.font.italic),
            "bold": bold,
            "font_face": text.font.face or "",
        }
        font_color = rgba_to_hex(text.font.color)
        if font_color is not None:
            text_style["color"] = font_color
        if "\n" in body:
            text_style["multiline"] = True
        text_kwargs = apply_default_text_style(
            text_style,
            LAYER_SCHEMATIC_DRAWINGSHEET,
        )
        ops.append(
            KiCadPlotterOp.text(
                x=_mm_to_nm(x_mm),
                y=_mm_to_nm(y_mm),
                text=body,
                orient_deg=float(text.rotate),
                **text_kwargs,
            )
        )
    return ops


def _bitmap_repeat_ops(
    bitmap: "WksBitmap",
    page_w_mm: float,
    page_h_mm: float,
    margins: dict,
) -> List[KiCadPlotterOp]:
    repeat = getattr(bitmap, "repeat", None)
    count = max(1, int(getattr(repeat, "count", 1) or 1))
    incr_x = float(getattr(repeat, "incr_x", 0.0) or 0.0)
    incr_y = float(getattr(repeat, "incr_y", 0.0) or 0.0)
    image_data_b64 = bitmap.pngdata
    width_px, height_px, ppm_x, ppm_y = _png_dimensions_and_density(image_data_b64)
    scale = float(bitmap.scale)
    width_nm = _bitmap_extent_nm(width_px, scale, ppm_x)
    height_nm = _bitmap_extent_nm(height_px, scale, ppm_y)

    ops: List[KiCadPlotterOp] = []
    for ii in range(count):
        dx = incr_x * ii
        dy = incr_y * ii
        x_mm, y_mm = _resolve_point_mm(
            bitmap.pos,
            page_w_mm,
            page_h_mm,
            margins,
            delta_x_mm=dx,
            delta_y_mm=dy,
        )
        if ii > 0 and not _is_inside_page(x_mm, y_mm, page_w_mm, page_h_mm, margins):
            continue
        ops.append(
            styled_plotter_op(
                KiCadPlotterOp.plot_image(
                    x=_mm_to_nm(x_mm),
                    y=_mm_to_nm(y_mm),
                    width_nm=width_nm,
                    height_nm=height_nm,
                    scale=scale,
                    image_data_b64=image_data_b64,
                    image_format="png",
                ),
                stroke_color=LAYER_SCHEMATIC_DRAWINGSHEET,
            )
        )
    return ops


# ---------------------------------------------------------------------------
# Top-level emitter
# ---------------------------------------------------------------------------


@public_api
def drawing_sheet_to_ops(
    wks: "KiCadWorksheet",
    *,
    paper_width_nm: int,
    paper_height_nm: int,
    title_block: Optional[dict] = None,
    sheet_index: int = 1,
    sheet_count: int = 1,
    paper_name: str = "",
    filename: str = "",
    sheet_path: str = "/",
    sheet_name: str = "",
    kicad_version: str = "",
    project_vars: Optional[dict] = None,
) -> List[KiCadPlotterOp]:
    """Emit a flat list of :class:`KiCadPlotterOp` for a worksheet.

    Walks the worksheet's items in original on-disk order (so the
    emitted ops match the order KiCad's draw-list builder produces),
    resolves corner-relative positions against the page rectangle
    (``paper_width_nm`` × ``paper_height_nm``) and the worksheet's
    setup margins, expands repeats with per-iteration ``incrx`` /
    ``incry`` (clipped to the inner page rect with 1mm slack), expands
    ``${VAR}`` / legacy ``%X`` format codes in tbtext bodies, and
    emits PlotPoly + Rect + Text ops.

    Polygon worksheet items are not emitted; worksheet bitmaps are surfaced
    as ``PlotImage`` placeholders with
    the embedded PNG payload preserved for downstream renderers.
    """
    page_w_mm = paper_width_nm / _MM_PER_NM
    page_h_mm = paper_height_nm / _MM_PER_NM

    setup = wks.setup
    margins = {
        "left": setup.left_margin,
        "right": setup.right_margin,
        "top": setup.top_margin,
        "bottom": setup.bottom_margin,
    }
    expand_kwargs = {
        "title_block": title_block,
        "sheet_index": sheet_index,
        "sheet_count": sheet_count,
        "paper_name": paper_name,
        "filename": filename,
        "sheet_path": sheet_path,
        "sheet_name": sheet_name,
        "kicad_version": kicad_version,
        "project_vars": project_vars,
    }

    ops: List[KiCadPlotterOp] = []
    # Walk in original on-disk order via _ordered_items when available;
    # fall back to per-type lists in their default order.
    ordered = wks._ordered_items or (
        [("rect", r) for r in wks.rects]
        + [("line", line) for line in wks.lines]
        + [("tbtext", t) for t in wks.texts]
        + [("bitmap", b) for b in wks.bitmaps]
    )

    for kind, item in ordered:
        # Skip per-page visibility filter (notonpage1 / page1only) when
        # the option restricts emission to a different page.
        opt = getattr(item, "option", "") or ""
        if opt == "page1only" and sheet_index != 1:
            continue
        if opt == "notonpage1" and sheet_index == 1:
            continue

        if kind == "line":
            ops.extend(_line_repeat_ops(
                cast("WksLine", item), page_w_mm, page_h_mm, margins, setup.linewidth
            ))
        elif kind == "rect":
            ops.extend(_rect_repeat_ops(
                cast("WksRect", item), page_w_mm, page_h_mm, margins, setup.linewidth
            ))
        elif kind == "tbtext":
            ops.extend(_tbtext_repeat_ops(
                cast("WksTbText", item), page_w_mm, page_h_mm, margins,
                default_text_size_mm=setup.text_size_x,
                default_textlinewidth_mm=setup.textlinewidth,
                expand_kwargs=expand_kwargs,
            ))
        elif kind == "bitmap":
            ops.extend(_bitmap_repeat_ops(cast("WksBitmap", item), page_w_mm, page_h_mm, margins))
        # Polygon worksheet items are currently not emitted.

    return ops


__all__ = [
    "DEFAULT_KICAD_WKS",
    "drawing_sheet_to_ops",
    "expand_format_codes",
    "load_default_drawing_sheet",
]
