"""
KiCad Worksheet Text Element (tbtext).

S-expression format:
    (tbtext "Text or %FORMAT" (name "text1:Text") (comment "description")
        (pos X Y [corner]) (font (size X Y) (linewidth W) [bold] [italic])
        (justify [left|center|right]) (rotate A)
        (repeat N) (incrx X) (incry Y) (incrlabel N))

Format codes:
    %T - Title
    %D - Date
    %R - Revision
    %K - KiCad version
    %S - Sheet number
    %N - Total sheets
    %P - Sheet path
    %Y - Company name
    %F - Filename
    %C0-%C9 - Comments 0-9
    %Z - Paper size name
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_value, has_flag, unquote_string
from .kicad_wks_primitives import WksPoint, WksCorner, WksRepeat, parse_option


_LINEWIDTH_UNSET = float('nan')


@dataclass
class WksFont:
    """Font settings for worksheet text.

    Mirrors the optional sub-fields KiCad emits in ds_data_model_io.cpp:
    face, linewidth, size, bold, italic, color.
    """
    size_x: float = 0.0
    size_y: float = 0.0
    linewidth: float = field(default=_LINEWIDTH_UNSET)
    bold: bool = False
    italic: bool = False
    face: str = ""
    # KiCad color: r, g, b in [0,255] and a in [0,1]; None means absent.
    color: Optional[Tuple[int, int, int, float]] = None

    @classmethod
    def from_sexp(cls, sexp: list) -> 'WksFont':
        """Parse from (font ...) element within parent."""
        elem = find_element(sexp, 'font')
        if not elem:
            return cls()

        size_elem = find_element(elem, 'size')
        if size_elem:
            size_x = float(size_elem[1]) if len(size_elem) > 1 else 0.0
            size_y = float(size_elem[2]) if len(size_elem) > 2 else size_x
        else:
            size_x = 0.0
            size_y = 0.0

        lw_elem = find_element(elem, 'linewidth')
        linewidth = float(lw_elem[1]) if lw_elem and len(lw_elem) > 1 else _LINEWIDTH_UNSET
        bold = has_flag(elem, 'bold')
        italic = has_flag(elem, 'italic')
        face = unquote_string(get_value(elem, 'face', ''))

        color: Optional[Tuple[int, int, int, float]] = None
        color_elem = find_element(elem, 'color')
        if color_elem and len(color_elem) >= 5:
            color = (int(color_elem[1]), int(color_elem[2]),
                     int(color_elem[3]), float(color_elem[4]))

        return cls(
            size_x=size_x,
            size_y=size_y,
            linewidth=linewidth,
            bold=bold,
            italic=italic,
            face=face,
            color=color,
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list per ds_data_model_io.cpp:262."""
        result: list = ['font']

        if self.face:
            result.append(['face', QuotedString(self.face)])

        if not math.isnan(self.linewidth):
            result.append(['linewidth', self.linewidth])

        if self.size_x != 0.0 or self.size_y != 0.0:
            result.append(['size', self.size_x, self.size_y])

        if self.bold:
            result.append('bold')

        if self.italic:
            result.append('italic')

        if self.color is not None:
            r, g, b, a = self.color
            result.append(['color', r, g, b, a])

        # Only emit (font ...) when at least one option is non-default —
        # KiCad guards with the same predicate (line 260 of the writer).
        return result if len(result) > 1 else []


@dataclass
class WksTbText:
    """Title block text element in a worksheet.

    Text can contain format codes that are substituted with
    document metadata when rendered.
    """
    text: str = ""
    pos: WksPoint = field(default_factory=WksPoint)
    font: WksFont = field(default_factory=WksFont)
    # Free-form justify tokens (KiCad emits any of: center, right, top, bottom).
    # Stored as a list of bare tokens to preserve the exact set.
    justify: list = field(default_factory=list)
    rotate: float = 0.0
    name: str = ""
    comment: str = ""
    option: str = ""
    repeat: WksRepeat = field(default_factory=WksRepeat)
    max_len: float = 0.0  # Maximum text length (0 = unlimited)
    max_height: float = 0.0  # Maximum text height (0 = unlimited)

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'WksTbText':
        """Parse from (tbtext "text" ...) element."""
        # Text is the second element (after 'tbtext')
        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        pos = cls._parse_pos(sexp)
        font = WksFont.from_sexp(sexp)
        rotate = float(get_value(sexp, 'rotate', 0.0))
        name = unquote_string(get_value(sexp, 'name', ''))
        comment = unquote_string(get_value(sexp, 'comment', ''))
        option = parse_option(sexp)
        repeat = WksRepeat.from_sexp(sexp)
        max_len = float(get_value(sexp, 'maxlen', 0.0))
        max_height = float(get_value(sexp, 'maxheight', 0.0))

        # Justify is one or more bare tokens from {center, right, top, bottom}.
        justify_elem = find_element(sexp, 'justify')
        justify: list = []
        if justify_elem:
            for item in justify_elem[1:]:
                if isinstance(item, str) and item in ('left', 'center', 'right', 'top', 'bottom'):
                    justify.append(item)

        return cls(
            text=text,
            pos=pos,
            font=font,
            justify=justify,
            rotate=rotate,
            name=name,
            comment=comment,
            option=option,
            repeat=repeat,
            max_len=max_len,
            max_height=max_height,
            _raw_sexp=sexp
        )

    @staticmethod
    def _parse_pos(sexp: list) -> WksPoint:
        """Parse position from (pos X Y [corner])."""
        elem = find_element(sexp, 'pos')
        if not elem:
            return WksPoint()

        x = float(elem[1]) if len(elem) > 1 else 0.0
        y = float(elem[2]) if len(elem) > 2 else 0.0

        corner = WksCorner.NONE
        if len(elem) > 3 and isinstance(elem[3], str):
            try:
                corner = WksCorner(elem[3])
            except ValueError:
                pass

        return WksPoint(x=x, y=y, corner=corner)

    def to_sexp(self) -> list:
        """Serialize to S-expression list per ds_data_model_io.cpp:244."""
        result: list = ['tbtext', QuotedString(self.text)]

        result.append(['name', QuotedString(self.name)])
        result.append(self.pos.to_sexp('pos'))

        if self.option:
            result.append(['option', self.option])

        if self.rotate != 0.0:
            result.append(['rotate', self.rotate])

        font_sexp = self.font.to_sexp()
        if font_sexp:
            result.append(font_sexp)

        if self.justify:
            result.append(['justify', *self.justify])

        if self.max_len > 0.0:
            result.append(['maxlen', self.max_len])

        if self.max_height > 0.0:
            result.append(['maxheight', self.max_height])

        result.extend(self.repeat.to_sexp_items())

        if self.comment:
            result.append(['comment', QuotedString(self.comment)])

        return result
