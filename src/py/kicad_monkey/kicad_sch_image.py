"""KiCad schematic top-level (image ...) annotation.

KiCad emits this via ``SCH_IO_KICAD_SEXPR::saveBitmap`` for
``SCH_BITMAP_T`` items in
``eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr.cpp:1035``. The wire
format is::

    (image (at X Y)
        [(scale S)]
        (uuid "...")
        [(locked yes)]
        (data "<base64>" "<base64>" ...)
    )

The (data ...) payload is base64-encoded image bytes split into
76-char chunks per ``FormatStreamData`` (kicad_io_utils.cpp:55). Each
chunk is emitted as its own quoted string on a new line.

We round-trip the chunks verbatim as a list of strings — joining and
re-splitting would risk corrupting the base64 if the chunk size ever
changes upstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_value, unquote_string


# Matches a single-line ``(data "..." "..." ...)`` block as produced by
# ``format_sexp`` (which keeps tokens at depth > max_nesting inline). The
# substitution puts each chunk on its own line, mirroring KiCad's
# FormatStreamData output (kicad_io_utils.cpp:55).
_DATA_BLOCK_RE = re.compile(
    r'^(?P<indent>[ \t]*)\(data((?:[ \t]+"[^"]*")+)\)\s*$',
    re.MULTILINE,
)
_CHUNK_RE = re.compile(r'"([^"]*)"')


def format_image_data_blocks(text: str) -> str:
    """Reformat single-line ``(data "..." "..." ...)`` blocks so each
    base64 chunk lives on its own line.

    Schematic ``(image ...)`` sits at depth 1 below ``(kicad_sch ...)``
    so its ``(data ...)`` child ends up at depth >= max_nesting (=2),
    meaning ``format_sexp`` keeps it inline. KiCad refuses to load the
    file when this single line grows past its parser's expectations,
    and the oracle diff is also enormous because KiCad's own emit
    breaks on every chunk. We fix both by post-processing.
    """

    def _sub(m: re.Match[str]) -> str:
        indent = m.group('indent')
        chunks = _CHUNK_RE.findall(m.group(2))
        if not chunks:
            return m.group(0)
        lines = [f'{indent}(data "{chunks[0]}"']
        for c in chunks[1:]:
            lines.append(f'{indent}  "{c}"')
        return '\n'.join(lines) + ')'

    return _DATA_BLOCK_RE.sub(_sub, text)


@dataclass
class SchImage:
    """Top-level embedded bitmap image on a schematic sheet."""

    at_x: float = 0.0
    at_y: float = 0.0
    scale: Optional[float] = None
    uuid: str = ""
    locked: bool = False
    # Base64 chunks, in original order; each is typically <= 76 chars.
    data: List[str] = field(default_factory=list)
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchImage':
        at_elem = find_element(sexp, 'at')
        at_x = float(at_elem[1]) if at_elem and len(at_elem) > 1 else 0.0
        at_y = float(at_elem[2]) if at_elem and len(at_elem) > 2 else 0.0

        scale_elem = find_element(sexp, 'scale')
        scale: Optional[float] = None
        if scale_elem and len(scale_elem) > 1:
            scale = float(scale_elem[1])

        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        locked_elem = find_element(sexp, 'locked')
        locked = bool(locked_elem and len(locked_elem) > 1 and locked_elem[1] == 'yes')

        data: List[str] = []
        data_elem = find_element(sexp, 'data')
        if data_elem:
            for tok in data_elem[1:]:
                if isinstance(tok, str):
                    data.append(unquote_string(tok))

        return cls(at_x=at_x, at_y=at_y, scale=scale,
                   uuid=uuid, locked=locked, data=data,
                   _raw_sexp=sexp)

    def to_sexp(self) -> list:
        result: list = ['image']
        result.append(['at', self.at_x, self.at_y])
        if self.scale is not None:
            result.append(['scale', self.scale])
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        if self.locked:
            result.append(['locked', 'yes'])
        data_elem: list = ['data']
        for chunk in self.data:
            data_elem.append(QuotedString(chunk))
        result.append(data_elem)
        return result


__all__ = ['SchImage', 'format_image_data_blocks']
