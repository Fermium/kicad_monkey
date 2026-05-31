"""
KiCad Worksheet (.kicad_wks) File Parser.

Worksheets define the page layout template for schematics and PCBs,
including borders, title blocks, and company logos.

Example:
    >>> wks = KiCadWorksheet.from_file("template.kicad_wks")
    >>> print(f"Elements: {len(wks.lines)} lines, {len(wks.rects)} rects")
    >>> wks.to_file("output.kicad_wks")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

from ._api_markers import public_api
from .kicad_sexpr import parse_sexp, build_sexp, format_sexp, QuotedString, SexpList
from .kicad_base import find_element, get_value, unquote_string

from .kicad_wks_primitives import WksSetup
from .kicad_wks_line import WksLine
from .kicad_wks_rect import WksRect
from .kicad_wks_polygon import WksPolygon
from .kicad_wks_text import WksTbText
from .kicad_wks_bitmap import WksBitmap


# format_sexp keeps tokens at depth > max_nesting inline. (bitmap ... (data
# "chunk1" "chunk2" ...)) lives at depth 2/3 so its data chunks end up on a
# single line. KiCad emits one chunk per line via FormatStreamData
# (kicad_io_utils.cpp:55); this regex rewrites the inlined form to that shape.
# Match both shapes that can come out of format_sexp:
#   max_nesting=2:  "    (data \"a\" \"b\")"
#   max_nesting=3:  "    (data \"a\" \"b\"\n    )"
# The chunks live inline (depth >= max_nesting), but the closing ')' may end
# up on its own line at the parent indent when max_nesting=3.
_DATA_BLOCK_RE = re.compile(
    r'^(?P<indent>[ \t]*)\(data((?:[ \t]+"[^"]*")+)[ \t]*(?:\n[ \t]*)?\)[ \t]*$',
    re.MULTILINE,
)
_CHUNK_RE = re.compile(r'"([^"]*)"')


def _format_data_blocks(text: str) -> str:
    def _sub(m: re.Match[str]) -> str:
        indent = m.group('indent')
        chunks = _CHUNK_RE.findall(m.group(2))
        if not chunks:
            return m.group(0)
        lines = [f'{indent}(data "{chunks[0]}"']
        for c in chunks[1:]:
            lines.append(f'{indent}  "{c}"')
        # KiCad emits the closing ')' on its own line at the data block's
        # parent indent (PRETTIFIED_FILE_OUTPUTFORMATTER post-processes
        # ds_data_model_io.cpp's stream output).
        lines.append(f'{indent})')
        return '\n'.join(lines)

    return _DATA_BLOCK_RE.sub(_sub, text)


def _collapse_leaf_lines(text: str) -> str:
    """Inline closing parens of leaf elements on their own line.

    ``format_sexp`` always wraps a closing ``)`` to its own line at any
    depth ``< max_nesting``, even for leaf elements that contain no
    nested ``(``. KiCad's PRETTIFIED_FILE_OUTPUTFORMATTER keeps short
    leaf elements on one line, e.g. ``(version 20231118)``. This pass
    collapses lines of the form::

        (token args
        )

    back into ``(token args)`` whenever the opening line has exactly
    one ``(`` and no ``)``.
    """
    lines = text.split('\n')
    out: List[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if i + 1 < len(lines) and lines[i + 1].strip() == ')':
            if cur.count('(') == 1 and ')' not in cur:
                out.append(cur.rstrip() + ')')
                i += 2
                continue
        out.append(cur)
        i += 1
    return '\n'.join(out)


@dataclass
class KiCadWorksheet:
    """KiCad worksheet/page layout template (.kicad_wks).

    Worksheets define the drawing border, title block, and other
    fixed elements that appear on schematic and PCB sheets.

    Elements can use corner references to position themselves relative
    to different corners of the page, enabling responsive layouts.

    Supports two formats:
    - KiCad 9.0+: (kicad_wks (version ...) (generator ...) ...)
    - Legacy: (page_layout (setup ...) ...)

    Example:
        >>> wks = KiCadWorksheet.from_file("template.kicad_wks")
        >>> for text in wks.texts:
        ...     print(f"{text.text} at ({text.pos.x}, {text.pos.y})")
    """
    # KiCad 9.0+ metadata (optional for legacy files)
    version: int = 0  # 0 means legacy format without version
    generator: str = ""
    generator_version: str = ""

    setup: WksSetup = field(default_factory=WksSetup)

    # Graphic elements
    lines: List[WksLine] = field(default_factory=list)
    rects: List[WksRect] = field(default_factory=list)
    polygons: List[WksPolygon] = field(default_factory=list)
    texts: List[WksTbText] = field(default_factory=list)
    bitmaps: List[WksBitmap] = field(default_factory=list)

    # Original on-disk element order, preserved as (kind, item) tuples so the
    # round-trip emits items in their source order. KiCad never re-orders
    # graphical items on save (DS_DATA_MODEL::GetItem just walks an
    # insertion-ordered vector), so element order IS data.
    _ordered_items: List[Tuple[str, Any]] = field(default_factory=list, repr=False)

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    @public_api
    def from_file(cls, path: Path | str) -> 'KiCadWorksheet':
        """Load worksheet from file."""
        path = Path(path)
        text = path.read_text(encoding='utf-8')
        return cls.from_text(text)

    @classmethod
    def from_text(cls, text: str) -> 'KiCadWorksheet':
        """Parse worksheet from text."""
        sexp = parse_sexp(text)
        return cls.from_sexp(sexp)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'KiCadWorksheet':
        """Parse from S-expression list."""
        # Check for KiCad 9.0+ format (kicad_wks with version/generator)
        version = 0
        generator = ""
        generator_version = ""

        version_val = get_value(sexp, 'version', None)
        if version_val is not None:
            version = int(version_val)
            generator = unquote_string(get_value(sexp, 'generator', ''))
            generator_version = unquote_string(get_value(sexp, 'generator_version', ''))

        # Setup section
        setup_elem = find_element(sexp, 'setup')
        setup = WksSetup.from_sexp(setup_elem) if setup_elem else WksSetup()

        # Walk top-level children in source order so we can preserve the
        # interleaved emit order while still populating the per-type lists.
        lines: List[WksLine] = []
        rects: List[WksRect] = []
        polygons: List[WksPolygon] = []
        texts: List[WksTbText] = []
        bitmaps: List[WksBitmap] = []
        ordered: List[Tuple[str, Any]] = []

        for child in sexp[1:]:
            if not isinstance(child, list) or not child:
                continue
            tag = child[0]
            if tag == 'line':
                item = WksLine.from_sexp(child)
                lines.append(item)
                ordered.append(('line', item))
            elif tag == 'rect':
                item = WksRect.from_sexp(child)
                rects.append(item)
                ordered.append(('rect', item))
            elif tag == 'polygon':
                item = WksPolygon.from_sexp(child)
                polygons.append(item)
                ordered.append(('polygon', item))
            elif tag == 'tbtext':
                item = WksTbText.from_sexp(child)
                texts.append(item)
                ordered.append(('tbtext', item))
            elif tag == 'bitmap':
                item = WksBitmap.from_sexp(child)
                bitmaps.append(item)
                ordered.append(('bitmap', item))

        return cls(
            version=version,
            generator=generator,
            generator_version=generator_version,
            setup=setup,
            lines=lines,
            rects=rects,
            polygons=polygons,
            texts=texts,
            bitmaps=bitmaps,
            _ordered_items=ordered,
            _raw_sexp=sexp
        )

    @public_api
    def to_file(self, path: Path | str) -> None:
        """Write worksheet to file."""
        path = Path(path)
        text = self.to_text()
        path.write_text(text, encoding='utf-8')

    def to_text(self) -> str:
        """Serialize to formatted S-expression text."""
        sexp = self.to_sexp()
        raw = build_sexp(sexp)
        # max_nesting=3 keeps font children (face/size/...) on their own lines
        # the way KiCad's PRETTIFIED_FILE_OUTPUTFORMATTER emits them.
        text = format_sexp(raw, indentation_size=2, max_nesting=3)
        # Bitmap (data ...) chunks land at depth >= max_nesting and would
        # otherwise be inlined on a single line. Re-split each chunk onto its
        # own line, mirroring KiCad's FormatStreamData (kicad_io_utils.cpp:55).
        text = _format_data_blocks(text)
        # Collapse leaf-element wrapping: format_sexp puts the closing ')' of
        # every depth-1/2 element on its own line; KiCad keeps short leaf
        # forms inline (e.g. "(version 20231118)").
        return _collapse_leaf_lines(text)

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        # Use kicad_wks format if version is set, otherwise legacy page_layout
        if self.version > 0:
            result: SexpList = ['kicad_wks']
            result.append(['version', self.version])
            if self.generator:
                result.append(['generator', QuotedString(self.generator)])
            if self.generator_version:
                result.append(['generator_version', QuotedString(self.generator_version)])
        else:
            result: SexpList = ['page_layout']

        result.append(self.setup.to_sexp())

        # If we have a preserved on-disk ordering, walk it. Items added after
        # parse (or absent from _ordered_items) fall through to the per-type
        # tail emit so user-constructed objects still serialize.
        seen: set[int] = set()
        if self._ordered_items:
            for kind, item in self._ordered_items:
                seen.add(id(item))
                result.append(item.to_sexp())

        for rect in self.rects:
            if id(rect) not in seen:
                result.append(rect.to_sexp())
        for line in self.lines:
            if id(line) not in seen:
                result.append(line.to_sexp())
        for polygon in self.polygons:
            if id(polygon) not in seen:
                result.append(polygon.to_sexp())
        for text in self.texts:
            if id(text) not in seen:
                result.append(text.to_sexp())
        for bitmap in self.bitmaps:
            if id(bitmap) not in seen:
                result.append(bitmap.to_sexp())

        return result

    # Convenience methods
    @property
    def element_count(self) -> int:
        """Total number of elements in the worksheet."""
        return (len(self.lines) + len(self.rects) + len(self.polygons) +
                len(self.texts) + len(self.bitmaps))

    @public_api
    def get_texts_by_format(self, format_code: str) -> List[WksTbText]:
        """Get all text elements containing a specific format code.

        Args:
            format_code: Format code like '%T' (title), '%D' (date), etc.

        Returns:
            List of text elements containing that format code.
        """
        return [t for t in self.texts if format_code in t.text]

    @public_api
    def get_element_by_name(self, name: str) -> Optional[WksLine | WksRect | WksPolygon | WksTbText | WksBitmap]:
        """Get an element by its name attribute.

        Args:
            name: Element name (e.g., "text1:Text", "rect1:Rect")

        Returns:
            The element if found, None otherwise.
        """
        for elem_list in [self.lines, self.rects, self.polygons, self.texts, self.bitmaps]:
            for elem in elem_list:
                if elem.name == name:
                    return elem
        return None

    def __len__(self) -> int:
        """Total number of elements."""
        return self.element_count

    def __iter__(self) -> Iterator[WksLine | WksRect | WksPolygon | WksTbText | WksBitmap]:
        """Iterate over all elements."""
        yield from self.rects
        yield from self.lines
        yield from self.polygons
        yield from self.texts
        yield from self.bitmaps
