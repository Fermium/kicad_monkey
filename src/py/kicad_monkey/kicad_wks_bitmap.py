"""
KiCad Worksheet Bitmap Element.

S-expression format (KiCad 9.0+):
    (bitmap (name "logo:Bitmap") (pos X Y [corner]) (scale S)
        (data "BASE64_LINE1"
              "BASE64_LINE2"
              ...))

Legacy format:
    (bitmap ... (pngdata "BASE64_ENCODED_PNG_DATA"))

The (data ...) payload is base64-encoded image bytes split into 76-char
chunks per KICAD_FORMAT::FormatStreamData (kicad_io_utils.cpp:55). We
round-trip the chunks verbatim as a list of strings to preserve KiCad's
exact emit shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_value, unquote_string
from .kicad_wks_primitives import WksPoint, WksCorner, WksRepeat, parse_option


@dataclass
class WksBitmap:
    """Bitmap image element in a worksheet.

    Bitmaps are embedded as base64-encoded PNG data.
    """
    pos: WksPoint = field(default_factory=WksPoint)
    scale: float = 1.0
    name: str = ""
    comment: str = ""
    option: str = ""
    repeat: WksRepeat = field(default_factory=WksRepeat)

    # Base64-encoded PNG data, preserved as the original chunk list so
    # round-tripping matches KiCad's FormatStreamData line breaks.
    data_chunks: List[str] = field(default_factory=list)

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @property
    def pngdata(self) -> str:
        """Concatenated base64 payload (chunks joined)."""
        return "".join(self.data_chunks)

    @pngdata.setter
    def pngdata(self, value: str) -> None:
        """Set payload as a single concatenated string. Chunked layout is lost."""
        self.data_chunks = [value] if value else []

    @classmethod
    def from_sexp(cls, sexp: list) -> 'WksBitmap':
        """Parse from (bitmap ...) element."""
        pos = cls._parse_pos(sexp)
        scale = float(get_value(sexp, 'scale', 1.0))
        name = unquote_string(get_value(sexp, 'name', ''))
        comment = unquote_string(get_value(sexp, 'comment', ''))
        option = parse_option(sexp)
        repeat = WksRepeat.from_sexp(sexp)

        # Parse bitmap data - try 'data' first (KiCad 9.0+), then 'pngdata' (legacy)
        data_chunks: List[str] = []
        data_elem = find_element(sexp, 'data')
        if data_elem:
            # KiCad 9.0+ format: (data "line1" "line2" ...) — preserve chunks.
            for item in data_elem[1:]:
                if isinstance(item, str):
                    data_chunks.append(unquote_string(item))
        else:
            # Legacy format: (pngdata "...")
            pngdata_elem = find_element(sexp, 'pngdata')
            if pngdata_elem and len(pngdata_elem) > 1:
                data_chunks.append(unquote_string(pngdata_elem[1]))

        return cls(
            pos=pos,
            scale=scale,
            name=name,
            comment=comment,
            option=option,
            repeat=repeat,
            data_chunks=data_chunks,
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
        """Serialize to S-expression list per ds_data_model_io.cpp:399."""
        result: list = ['bitmap']

        result.append(['name', QuotedString(self.name)])
        result.append(self.pos.to_sexp('pos'))

        if self.option:
            result.append(['option', self.option])

        result.append(['scale', self.scale])

        result.extend(self.repeat.to_sexp_items())

        if self.comment:
            result.append(['comment', QuotedString(self.comment)])

        if self.data_chunks:
            # KiCad 9.0+ format: (data "chunk1" "chunk2" ...) — one chunk per
            # line per FormatStreamData (kicad_io_utils.cpp:55). The on-disk
            # line break shape is recovered by ``_format_data_blocks`` in
            # kicad_worksheet.
            data_elem: list = ['data']
            for chunk in self.data_chunks:
                data_elem.append(QuotedString(chunk))
            result.append(data_elem)

        return result
