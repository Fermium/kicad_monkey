"""
KiCad Worksheet Primitives - Shared types for worksheet elements.

Includes:
- WksCorner: Corner reference enum
- WksPoint: Position with optional corner reference
- WksSetup: Page layout defaults
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .kicad_base import find_element, get_value
from .kicad_sexpr import SexpList


class WksCorner(Enum):
    """Corner reference for worksheet element positions.

    Coordinates are relative to this corner of the page.
    Default (no corner specified) means right-bottom corner.
    """
    NONE = ""           # Default: right-bottom
    LT = "ltcorner"     # Left-top
    RT = "rtcorner"     # Right-top
    LB = "lbcorner"     # Left-bottom
    RB = "rbcorner"     # Right-bottom


@dataclass
class WksPoint:
    """Position in a worksheet with optional corner reference.

    Worksheet coordinates are relative to a corner of the page.
    The corner reference determines which page corner the position
    is measured from.
    """
    x: float = 0.0
    y: float = 0.0
    corner: WksCorner = WksCorner.NONE

    @classmethod
    def from_sexp(cls, sexp: list, tag: str = 'pos') -> 'WksPoint':
        """Parse from (pos X Y [corner]) or (start X Y [corner]) etc."""
        elem = find_element(sexp, tag)
        if not elem:
            return cls()

        x = float(elem[1]) if len(elem) > 1 else 0.0
        y = float(elem[2]) if len(elem) > 2 else 0.0

        # Check for corner reference
        corner = WksCorner.NONE
        if len(elem) > 3 and isinstance(elem[3], str):
            try:
                corner = WksCorner(elem[3])
            except ValueError:
                pass

        return cls(x=x, y=y, corner=corner)

    def to_sexp(self, tag: str = 'pos') -> list:
        """Serialize to S-expression list."""
        result: SexpList = [tag, self.x, self.y]
        if self.corner != WksCorner.NONE:
            result.append(self.corner.value)
        return result


@dataclass
class WksSetup:
    """Page layout setup defaults.

    S-expression format:
        (setup (textsize 1.5 1.5) (linewidth 0.15) (textlinewidth 0.15)
            (left_margin 10) (right_margin 10) (top_margin 10) (bottom_margin 10))
    """
    text_size_x: float = 1.5
    text_size_y: float = 1.5
    linewidth: float = 0.15
    textlinewidth: float = 0.15
    left_margin: float = 10.0
    right_margin: float = 10.0
    top_margin: float = 10.0
    bottom_margin: float = 10.0

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'WksSetup':
        """Parse from (setup ...) element."""
        # textsize is (textsize X Y)
        textsize_elem = find_element(sexp, 'textsize')
        text_size_x = float(textsize_elem[1]) if textsize_elem and len(textsize_elem) > 1 else 1.5
        text_size_y = float(textsize_elem[2]) if textsize_elem and len(textsize_elem) > 2 else text_size_x

        linewidth = float(get_value(sexp, 'linewidth', 0.15))
        textlinewidth = float(get_value(sexp, 'textlinewidth', 0.15))
        left_margin = float(get_value(sexp, 'left_margin', 10.0))
        right_margin = float(get_value(sexp, 'right_margin', 10.0))
        top_margin = float(get_value(sexp, 'top_margin', 10.0))
        bottom_margin = float(get_value(sexp, 'bottom_margin', 10.0))

        return cls(
            text_size_x=text_size_x,
            text_size_y=text_size_y,
            linewidth=linewidth,
            textlinewidth=textlinewidth,
            left_margin=left_margin,
            right_margin=right_margin,
            top_margin=top_margin,
            bottom_margin=bottom_margin,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result: SexpList = ['setup']

        result.append(['textsize', self.text_size_x, self.text_size_y])
        result.append(['linewidth', self.linewidth])
        result.append(['textlinewidth', self.textlinewidth])

        # KiCad always emits all four margins (ds_data_model_io.cpp:226-229),
        # even when they match the page-layout defaults.
        result.append(['left_margin', self.left_margin])
        result.append(['right_margin', self.right_margin])
        result.append(['top_margin', self.top_margin])
        result.append(['bottom_margin', self.bottom_margin])

        return result


def parse_option(sexp: list) -> str:
    """Parse a KiCad worksheet ``(option ...)`` flag.

    KiCad's formatOptions writes one of ``(option page1only)`` or
    ``(option notonpage1)`` on items whose page-visibility setting differs
    from the default. The token is bare. We return ``""`` when absent.
    """
    elem = find_element(sexp, 'option')
    if not elem or len(elem) < 2:
        return ""
    val = elem[1]
    if isinstance(val, str) and val in ('page1only', 'notonpage1'):
        return val
    return ""


@dataclass
class WksRepeat:
    """Repeat settings for worksheet elements.

    Elements can be repeated with incremental position offsets.
    """
    count: int = 1
    incr_x: float = 0.0
    incr_y: float = 0.0
    incr_label: int = 0  # For text: increment the numeric part of label

    @classmethod
    def from_sexp(cls, sexp: list) -> 'WksRepeat':
        """Parse repeat settings from element S-expression."""
        count = int(get_value(sexp, 'repeat', 1))
        incr_x = float(get_value(sexp, 'incrx', 0.0))
        incr_y = float(get_value(sexp, 'incry', 0.0))
        incr_label = int(get_value(sexp, 'incrlabel', 0))

        return cls(count=count, incr_x=incr_x, incr_y=incr_y, incr_label=incr_label)

    def to_sexp_items(self) -> list:
        """Return list of S-expression items to append to parent."""
        result = []
        if self.count != 1:
            result.append(['repeat', self.count])
        if self.incr_x != 0.0:
            result.append(['incrx', self.incr_x])
        if self.incr_y != 0.0:
            result.append(['incry', self.incr_y])
        if self.incr_label != 0:
            result.append(['incrlabel', self.incr_label])
        return result
