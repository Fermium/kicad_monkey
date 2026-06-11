"""
KiCad Stroke Font Renderer

Implements KiCad's Hershey-based stroke font for rendering text elements.
Based on KiCad's common/font/stroke_font.cpp and common/newstroke_font.cpp

This implementation uses the exact algorithm from KiCad to ensure pixel-perfect
matching with KiCad CLI SVG output.

Hershey encoding format:
- First 2 chars: width bounds (left, right)
- " R" = pen up (start new stroke)
- Other pairs: coordinate (char - 'R') * SCALE

Constants from KiCad (stroke_font.cpp line 45-48):
- STROKE_FONT_SCALE = 1/21 (normalize coordinates)
- FONT_OFFSET = -8 (baseline adjustment for Y)
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass
import math
import json
from pathlib import Path

# Constants from KiCad stroke_font.cpp
STROKE_FONT_SCALE = 1.0 / 21.0
FONT_OFFSET = -8
ITALIC_TILT = 1.0 / 8.0  # tan(angle) for italic (from font.h line 61)

# Markup constants from KiCad:
# - OVERBAR_POSITION_FACTOR: KIFONT::METRICS::m_OverbarHeight (font_metrics.h),
#   the distance between the text baseline and the overbar, in glyph heights.
# - OVERBAR_TRIM_RATIO: font.cpp drawMarkup() shortens the bar by
#   ``aSize.x * 0.1`` at each end so its rounded caps don't overhang.
# - SUPER_SUB_SIZE_MULTIPLIER / SUPER_HEIGHT_OFFSET / SUB_HEIGHT_OFFSET:
#   STROKE_FONT::GetTextAsGlyphs() (stroke_font.cpp).
OVERBAR_POSITION_FACTOR = 1.23
OVERBAR_TRIM_RATIO = 0.1
SUPER_SUB_SIZE_MULTIPLIER = 0.8
SUPER_HEIGHT_OFFSET = 0.35
SUB_HEIGHT_OFFSET = 0.15

_MARKUP_MARKERS = ("~{", "^{", "_{")


@dataclass
class MarkupNode:
    """One node of KiCad's lightweight text markup tree.

    Either a plain-text run (``marker == ""``) or a marked span
    (``marker`` in ``~`` overbar / ``^`` superscript / ``_`` subscript)
    whose content lives in ``children``.
    """

    text: str = ""
    marker: str = ""
    children: "List[MarkupNode]" = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.children is None:
            self.children = []


def has_markup(text: str) -> bool:
    """Return True when *text* contains KiCad ``~{}`` / ``^{}`` / ``_{}`` markup."""
    return any(marker in text for marker in _MARKUP_MARKERS)


def parse_markup(text: str) -> "List[MarkupNode]":
    """Parse KiCad's ``~{}`` (overbar), ``^{}`` (superscript) and ``_{}``
    (subscript) markup into a node tree.

    Mirrors KiCad's MARKUP parser semantics: a marker character is only
    special when immediately followed by ``{``; everything else (including
    bare ``~``/``^``/``_`` and unmatched ``}``) is literal text.
    """

    def parse_parts(index: int, stop_on_brace: bool = False) -> Tuple[List[MarkupNode], int]:
        parts: List[MarkupNode] = []
        buffer: List[str] = []

        def flush_buffer() -> None:
            if buffer:
                parts.append(MarkupNode(text="".join(buffer)))
                buffer.clear()

        while index < len(text):
            char = text[index]
            if stop_on_brace and char == "}":
                flush_buffer()
                return parts, index + 1

            if index + 1 < len(text) and char in "^_~" and text[index + 1] == "{":
                flush_buffer()
                children, index = parse_parts(index + 2, stop_on_brace=True)
                parts.append(MarkupNode(marker=char, children=children))
                continue

            buffer.append(char)
            index += 1

        flush_buffer()
        return parts, index

    parts, _index = parse_parts(0)
    return parts

# Load glyph data from JSON file
_GLYPH_DATA_FILE = Path(__file__).parent / "kicad_stroke_font_data.json"


def _load_glyph_data() -> List[str]:
    """Load glyph data from JSON file."""
    if _GLYPH_DATA_FILE.exists():
        with open(_GLYPH_DATA_FILE, "r") as f:
            return json.load(f)
    else:
        # Fallback to basic ASCII if JSON not found
        return _BASIC_ASCII_GLYPHS


# Fallback basic ASCII glyphs (same as before, for when JSON is not available)
_BASIC_ASCII_GLYPHS = [
    # U+20 SPACE
    "JZ",
    # U+21 !
    "MWRYSZR[QZRYR[ RRSQGRFSGRSRF",
    # U+22 "
    "JZNFNJ RVFVJ",
    # U+23 #
    "H]LM[M RRDL_ RYVJV RS_YD",
    # U+24 $
    "H\\LZO[T[VZWYXWXUWSVRTQPPNOMNLLLJMHNGPFUFXG RRCR^",
    # U+25 %
    "F^J[ZF RMFOGPIOKMLKKJIKGMF RYZZXYVWUUVTXUZW[YZ",
    # U+26 &
    "E_[[Z[XZUWPQNNMKMINGPFQFSGTITJSLRMLQKRJTJWKYLZN[Q[SZTYWUXRXP",
    # U+27 '
    "MWSFQJ",
    # U+28 (
    "KYVcUbS_R]QZPUPQQLRISGUDVC",
    # U+29 )
    "KYNcObQ_R]SZTUTQSLRIQGODNC",
    # U+2A *
    "JZRFRK RMIRKWI ROORKUO",
    # U+2B +
    "E_JSZS RR[RK",
    # U+2C ,
    "MWSZS[R]Q^",
    # U+2D -
    "E_JSZS",
    # U+2E .
    "MWRYSZR[QZRYR[",
    # U+2F /
    "G][EI`",
    # U+30 0
    "H\\QFSFUGVHWJXNXSWWVYUZS[Q[OZNYMWLSLNMJNHOGQF",
    # U+31 1
    "H\\X[L[ RR[RFPINKLL",
    # U+32 2
    "H\\LHMGOFTFVGWHXJXLWOK[X[",
    # U+33 3
    "H\\KFXFQNTNVOWPXRXWWYVZT[N[LZKY",
    # U+34 4
    "H\\VMV[ RQELTYT",
    # U+35 5
    "H\\WFMFLPMOONTNVOWPXRXWWYVZT[O[MZLY",
    # U+36 6
    "H\\VFRFPGOHMKLOLWMYNZP[T[VZWYXWXRWPVOTNPNNOMPLR",
    # U+37 7
    "H\\KFYFP[",
    # U+38 8
    "H\\PONNMMLKLJMHNGPFTFVGWHXJXKWMVNTOPONPMQLSLWMYNZP[T[VZWYXWXSWQVPTO",
    # U+39 9
    "H\\N[R[TZUYWVXRXJWHVGTFPFNGMHLJLOMQNRPSTSVRWQXO",
    # U+3A :
    "MWRYSZR[QZRYR[ RRNSORPQORNRP",
    # U+3B ;
    "MWSZS[R]Q^ RRNSORPQORNRP",
    # U+3C <
    "E_ZMJSZY",
    # U+3D =
    "E_JPZP RZVJV",
    # U+3E >
    "E_JMZSJY",
    # U+3F ?
    "I[QYRZQ[PZQYQ[ RMGOFTFVGWIWKVMUNSORPQRQS",
    # U+40 @
    "D_VQUPSOQOOPNQMSMUNWOXQYSYUXVW RVOVWWXXXZW[U[PYMVKRJNKKMIPHTIXK[N]R^V]Y[",
    # U+41 A
    "I[MUWU RK[RFY[",
    # U+42 B
    "G\\SPVQWRXTXWWYVZT[L[LFSFUGVHWJWLVNUOSPLP",
    # U+43 C
    "F[WYVZS[Q[NZLXKVJRJOKKLINGQFSFVGWH",
    # U+44 D
    "G\\L[LFQFTGVIWKXOXRWVVXTZQ[L[",
    # U+45 E
    "H[MPTP RW[M[MFWF",
    # U+46 F
    "HZTPMP RM[MFWF",
    # U+47 G
    "F[VGTFQFNGLIKKJOJRKVLXNZQ[S[VZWYWRSR",
    # U+48 H
    "G]L[LF RLPXP RX[XF",
    # U+49 I
    "MWR[RF",
    # U+4A J
    "JZUFUUTXRZO[M[",
    # U+4B K
    "G\\L[LF RX[OO RXFLR",
    # U+4C L
    "HYW[M[MF",
    # U+4D M
    "F^K[KFRUYFY[",
    # U+4E N
    "G]L[LFX[XF",
    # U+4F O
    "G]PFTFVGXIYMYTXXVZT[P[NZLXKTKMLINGPF",
    # U+50 P
    "G\\L[LFTFVGWHXJXMWOVPTQLQ",
    # U+51 Q
    "G]Z]X\\VZSWQVOV RP[NZLXKTKMLINGPFTFVGXIYMYTXXVZT[P[",
    # U+52 R
    "G\\X[QQ RL[LFTFVGWHXJXMWOVPTQLQ",
    # U+53 S
    "H\\LZO[T[VZWYXWXUWSVRTQPPNOMNLLLJMHNGPFUFXG",
    # U+54 T
    "JZLFXF RR[RF",
    # U+55 U
    "G]LFLWMYNZP[T[VZWYXWXF",
    # U+56 V
    "I[KFR[YF",
    # U+57 W
    "F^IFN[RLV[[F",
    # U+58 X
    "H\\KFY[ RYFK[",
    # U+59 Y
    "I[RQR[ RKFRQYF",
    # U+5A Z
    "H\\KFYFK[Y[",
    # U+5B [
    "KYVbQbQDVD",
    # U+5C \
    "KYID[_",
    # U+5D ]
    "KYNbSbSDND",
    # U+5E ^
    "LXNHREVH",
    # U+5F _
    "JZJ]Z]",
    # U+60 `
    "NVPESH",
    # U+61 a
    "I\\W[WPVNTMPMNN RWZU[P[NZMXMVNTPSUSWR",
    # U+62 b
    "H[M[MF RMNOMSMUNVOWQWWVYUZS[O[MZ",
    # U+63 c
    "HZVZT[P[NZMYLWLQMONNPMTMVN",
    # U+64 d
    "I\\W[WF RWZU[Q[OZNYMWMQNOONQMUMWN",
    # U+65 e
    "I[VZT[P[NZMXMPNNPMTMVNWPWRMT",
    # U+66 f
    "MYOMWM RR[RISGUFWF",
    # U+67 g
    "I\\WMW^V`UaSbPbNa RWZU[Q[OZNYMWMQNOONQMUMWN",
    # U+68 h
    "H[M[MF RV[VPUNSMPMNNMO",
    # U+69 i
    "MWR[RM RRFQGRHSGRFRH",
    # U+6A j
    "MWRMR_QaObNb RRFQGRHSGRFRH",
    # U+6B k
    "IZN[NF RPSV[ RVMNU",
    # U+6C l
    "MXU[SZRXRF",
    # U+6D m
    "D`I[IM RIOJNLMOMQNRPR[ RRPSNUMXMZN[P[[",
    # U+6E n
    "I\\NMN[ RNOONQMTMVNWPW[",
    # U+6F o
    "H[P[NZMYLWLQMONNPMSMUNVOWQWWVYUZS[P[",
    # U+70 p
    "H[MMMb RMNOMSMUNVOWQWWVYUZS[O[MZ",
    # U+71 q
    "I\\WMWb RWZU[Q[OZNYMWMQNOONQMUMWN",
    # U+72 r
    "KXP[PM RPQQORNTMVM",
    # U+73 s
    "J[NZP[T[VZWXWWVUTTQTOSNQNPONQMTMVN",
    # U+74 t
    "MYOMWM RRFRXSZU[W[",
    # U+75 u
    "H[VMV[ RMMMXNZP[S[UZVY",
    # U+76 v
    "JZMMR[WM",
    # U+77 w
    "G]JMN[RQV[ZM",
    # U+78 x
    "IZL[WM RLMW[",
    # U+79 y
    "JZMMR[ RWMR[P`OaMb",
    # U+7A z
    "IZLMWML[W[",
    # U+7B {
    "KYVcUcSbR`RVQTOSQRRPRFSDUCVC",
    # U+7C |
    "H\\RbRD",
    # U+7D }
    "KYNcOcQbR`RVSTUSSRRPRFQDOCNC",
    # U+7E ~
    "KZMSNRPQTSVRWQ",
]


@dataclass
class StrokeGlyph:
    """Parsed glyph data."""

    width: float  # Glyph width (normalized)
    strokes: List[List[Tuple[float, float]]]  # List of polylines


def parse_hershey_glyph(encoded: str) -> StrokeGlyph:
    """Parse a Hershey-encoded glyph string.

    This exactly matches KiCad's loadNewStrokeFont() in stroke_font.cpp lines 99-191

    Args:
        encoded: The encoded glyph string from newstroke_font

    Returns:
        StrokeGlyph with width and list of strokes (polylines)
    """
    if len(encoded) < 2:
        return StrokeGlyph(width=0.0, strokes=[])

    # First two chars are width bounds (stroke_font.cpp lines 143-146)
    glyph_start_x = (ord(encoded[0]) - ord("R")) * STROKE_FONT_SCALE
    glyph_end_x = (ord(encoded[1]) - ord("R")) * STROKE_FONT_SCALE
    glyph_width = glyph_end_x - glyph_start_x

    strokes: List[List[Tuple[float, float]]] = []
    current_stroke: List[Tuple[float, float]] = []

    i = 2
    while i + 1 < len(encoded):
        c0 = encoded[i]
        c1 = encoded[i + 1]

        if c0 == " " and c1 == "R":
            # Pen up - save current stroke and start new one (line 148-151)
            if current_stroke:
                strokes.append(current_stroke)
                current_stroke = []
        else:
            # Coordinate pair (lines 154-169)
            # X: subtract glyph_start_x to normalize to 0-based coords
            x = (ord(c0) - ord("R")) * STROKE_FONT_SCALE - glyph_start_x
            # Y: add FONT_OFFSET before scaling (historical baseline adjustment)
            y = (ord(c1) - ord("R") + FONT_OFFSET) * STROKE_FONT_SCALE
            current_stroke.append((x, y))

        i += 2

    # Don't forget the last stroke
    if current_stroke:
        strokes.append(current_stroke)

    return StrokeGlyph(width=glyph_width, strokes=strokes)


# Load and cache glyph data
_glyph_data: Optional[List[str]] = None
_glyph_cache: dict = {}


def _get_glyph_data() -> List[str]:
    """Get the glyph data, loading from file if needed."""
    global _glyph_data
    if _glyph_data is None:
        _glyph_data = _load_glyph_data()
    return _glyph_data


def get_glyph(char: str) -> Optional[StrokeGlyph]:
    """Get parsed glyph for a character.

    Args:
        char: Single character

    Returns:
        StrokeGlyph or None if character not available
    """
    if char in _glyph_cache:
        return _glyph_cache[char]

    # Calculate index (Unicode codepoint - space)
    idx = ord(char) - 0x20

    glyph_data = _get_glyph_data()
    if idx < 0 or idx >= len(glyph_data):
        return None

    glyph = parse_hershey_glyph(glyph_data[idx])
    _glyph_cache[char] = glyph
    return glyph


def get_space_width() -> float:
    """Get the width of a space character."""
    glyph = get_glyph(" ")
    return glyph.width if glyph else 0.0


def _rotate_point_kicad(x: float, y: float, angle_deg: float) -> Tuple[float, float]:
    """Rotate point using KiCad's algorithm.

    KiCad uses CLOCKWISE rotation (trigo.cpp lines 295-330):
        x' = x*cos + y*sin
        y' = y*cos - x*sin

    Standard CCW rotation would be:
        x' = x*cos - y*sin
        y' = x*sin + y*cos
    """
    if angle_deg == 0:
        return (x, y)

    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # KiCad clockwise rotation formula
    rx = x * cos_a + y * sin_a
    ry = y * cos_a - x * sin_a

    return (rx, ry)


class KiCadStrokeFontRenderer:
    """Renders text as line segments using KiCad's stroke font.

    This implementation exactly matches KiCad's STROKE_FONT::GetTextAsGlyphs()
    and STROKE_GLYPH::Transform() to produce pixel-perfect SVG output.
    """

    def __init__(self):
        self._space_width = get_space_width()

    def render_text_polylines(
        self,
        text: str,
        pos_x: float,
        pos_y: float,
        size_x: float,
        size_y: float,
        angle: float = 0.0,
        h_align: str = "left",
        v_align: str = "bottom",
        mirror: bool = False,
        italic: bool = False,
    ) -> List[List[Tuple[float, float]]]:
        """Render text to list of polylines.

        Args:
            text: Text string to render
            pos_x, pos_y: Position in mm (this is the anchor point)
            size_x, size_y: Font size in mm
            angle: Rotation angle in degrees
            h_align: Horizontal alignment ("left", "center", "right")
            v_align: Vertical alignment ("top", "center", "bottom")
            mirror: Mirror text horizontally
            italic: Apply italic tilt

        Returns:
            List of polylines, each polyline is list of (x, y) points in mm
        """
        if not text:
            return []

        # Calculate total text width for alignment
        total_width = self._calculate_text_width(text) * size_x

        # Horizontal alignment offset
        if h_align == "center":
            offset_x = -total_width / 2
        elif h_align == "right":
            offset_x = -total_width
        else:
            offset_x = 0.0

        # Vertical alignment offset
        # Font metrics in normalized coordinates (after FONT_OFFSET + STROKE_FONT_SCALE)
        # Capital letters: 'F' (top) to '[' (bottom) in Hershey encoding
        cap_top = -20.0 / 21.0  # -0.9524
        cap_bottom = 1.0 / 21.0  # +0.0476
        cap_center = (cap_top + cap_bottom) / 2  # -0.4524

        # Empirical adjustment to match KiCad SVG output
        BASELINE_ADJ = 0.0024
        if v_align == "center":
            offset_y = (-cap_center - cap_bottom + BASELINE_ADJ) * size_y
        elif v_align == "top":
            offset_y = (-cap_top + BASELINE_ADJ) * size_y
        else:  # bottom
            offset_y = (-cap_bottom + BASELINE_ADJ) * size_y

        # Pre-compute rotation
        # KiCad stores angles with CCW positive, but SVG uses CW positive
        # So we negate the angle to match SVG coordinate conventions
        angle_rad = math.radians(-angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Italic tilt
        tilt = ITALIC_TILT if italic else 0.0

        polylines: List[List[Tuple[float, float]]] = []
        cursor_x = offset_x

        def transform_point(sx: float, sy: float, *, point_tilt: float) -> Tuple[float, float]:
            # Italic tilt (add, not subtract, to match KiCad behavior)
            if point_tilt != 0:
                sx += sy * point_tilt

            # Mirror
            if mirror:
                sx = -sx

            # Rotate (standard CCW rotation in coordinate space)
            rx = sx * cos_a - sy * sin_a
            ry = sx * sin_a + sy * cos_a

            # Translate to final position
            return (rx + pos_x, ry + pos_y)

        def emit_chars(chars: str, glyph_size_x: float, glyph_size_y: float, style_dy: float) -> None:
            nonlocal cursor_x
            for char in chars:
                if char == " ":
                    cursor_x += self._space_width * glyph_size_x
                    continue

                glyph = get_glyph(char)
                if glyph is None:
                    glyph = get_glyph("?")
                    if glyph is None:
                        continue

                for stroke in glyph.strokes:
                    if len(stroke) < 2:
                        continue

                    polyline: List[Tuple[float, float]] = []
                    for gx, gy in stroke:
                        # Scale and add cursor offset
                        sx = gx * glyph_size_x + cursor_x
                        sy = gy * glyph_size_y + offset_y + style_dy
                        polyline.append(transform_point(sx, sy, point_tilt=tilt))

                    polylines.append(polyline)

                cursor_x += glyph.width * glyph_size_x

        def walk(nodes: List[MarkupNode], subscript: bool, superscript: bool) -> None:
            nonlocal cursor_x
            for node in nodes:
                if not node.marker:
                    # Plain text run. Sub/superscript scale and baseline shift
                    # mirror STROKE_FONT::GetTextAsGlyphs() (subscript wins
                    # the offset when both flags are inherited).
                    if subscript or superscript:
                        glyph_size_x = size_x * SUPER_SUB_SIZE_MULTIPLIER
                        glyph_size_y = size_y * SUPER_SUB_SIZE_MULTIPLIER
                        if subscript:
                            style_dy = glyph_size_y * SUB_HEIGHT_OFFSET
                        else:
                            style_dy = -glyph_size_y * SUPER_HEIGHT_OFFSET
                    else:
                        glyph_size_x = size_x
                        glyph_size_y = size_y
                        style_dy = 0.0
                    emit_chars(node.text, glyph_size_x, glyph_size_y, style_dy)
                    continue

                bar_start_x = cursor_x
                walk(
                    node.children,
                    subscript or node.marker == "_",
                    superscript or node.marker == "^",
                )
                if node.marker == "~":
                    # Overbar per FONT::drawMarkup(): a single bar from the
                    # span's start cursor to its end cursor, trimmed a little
                    # at both ends, at 1.23 glyph heights above the baseline.
                    # The bar is never italic-tilted (Transform gets tilt=0).
                    trim = size_x * OVERBAR_TRIM_RATIO
                    bar_y = offset_y - size_y * OVERBAR_POSITION_FACTOR
                    polylines.append([
                        transform_point(bar_start_x + trim, bar_y, point_tilt=0.0),
                        transform_point(cursor_x - trim, bar_y, point_tilt=0.0),
                    ])

        if has_markup(text):
            walk(parse_markup(text), False, False)
        else:
            emit_chars(text, size_x, size_y, 0.0)

        return polylines

    def render_text(
        self,
        text: str,
        pos_x: float,
        pos_y: float,
        size_x: float,
        size_y: float,
        angle: float = 0.0,
        h_align: str = "left",
        v_align: str = "bottom",
        mirror: bool = False,
        italic: bool = False,
    ) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """Render text to list of line segments.

        Args:
            text: Text string to render
            pos_x, pos_y: Position in mm
            size_x, size_y: Font size in mm
            angle: Rotation angle in degrees (counter-clockwise)
            h_align: Horizontal alignment ("left", "center", "right")
            v_align: Vertical alignment ("top", "center", "bottom")
            mirror: Mirror text horizontally
            italic: Apply italic tilt

        Returns:
            List of ((x1,y1), (x2,y2)) line segments in mm
        """
        polylines = self.render_text_polylines(
            text, pos_x, pos_y, size_x, size_y, angle, h_align, v_align, mirror, italic
        )

        segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        for polyline in polylines:
            for i in range(len(polyline) - 1):
                segments.append((polyline[i], polyline[i + 1]))

        return segments

    def _calculate_text_width(self, text: str) -> float:
        """Calculate normalized text width (markup-aware)."""
        if has_markup(text):
            return self._markup_nodes_width(parse_markup(text), styled=False)
        return self._plain_run_width(text, scale=1.0)

    def _plain_run_width(self, text: str, *, scale: float) -> float:
        width = 0.0
        for char in text:
            if char == " ":
                width += self._space_width * scale
            else:
                glyph = get_glyph(char)
                if glyph:
                    width += glyph.width * scale
        return width

    def _markup_nodes_width(self, nodes: "List[MarkupNode]", *, styled: bool) -> float:
        width = 0.0
        for node in nodes:
            if not node.marker:
                scale = SUPER_SUB_SIZE_MULTIPLIER if styled else 1.0
                width += self._plain_run_width(node.text, scale=scale)
            else:
                width += self._markup_nodes_width(
                    node.children,
                    styled=styled or node.marker in "_^",
                )
        return width


# Module-level renderer instance
_renderer: Optional[KiCadStrokeFontRenderer] = None


def get_renderer() -> KiCadStrokeFontRenderer:
    """Get the singleton stroke font renderer."""
    global _renderer
    if _renderer is None:
        _renderer = KiCadStrokeFontRenderer()
    return _renderer
