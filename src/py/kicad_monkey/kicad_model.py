"""
KiCad 3D Model and Embedded File Elements

One class per file.
Note: Model and EmbeddedFile are kept together as they're closely related.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from .kicad_sexpr import QuotedString, FormattedDataBlock
from .kicad_base import (
    MIME_BASE64_LENGTH,
    find_element,
    get_value,
    unquote_string,
)


@dataclass
class Model:
    """3D model reference."""
    path: str
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    rotate: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'Model':
        path = unquote_string(sexp[1])

        offset_elem = find_element(sexp, 'offset')
        offset = (0.0, 0.0, 0.0)
        if offset_elem:
            xyz = find_element(offset_elem, 'xyz')
            if xyz:
                offset = (float(xyz[1]), float(xyz[2]), float(xyz[3]))

        scale_elem = find_element(sexp, 'scale')
        scale = (1.0, 1.0, 1.0)
        if scale_elem:
            xyz = find_element(scale_elem, 'xyz')
            if xyz:
                scale = (float(xyz[1]), float(xyz[2]), float(xyz[3]))

        rotate_elem = find_element(sexp, 'rotate')
        rotate = (0.0, 0.0, 0.0)
        if rotate_elem:
            xyz = find_element(rotate_elem, 'xyz')
            if xyz:
                rotate = (float(xyz[1]), float(xyz[2]), float(xyz[3]))

        return cls(path=path, offset=offset, scale=scale, rotate=rotate, _raw_sexp=sexp)

    def to_sexp(self) -> list:
        result = ['model', QuotedString(self.path)]
        result.append(['offset', ['xyz', self.offset[0], self.offset[1], self.offset[2]]])
        result.append(['scale', ['xyz', self.scale[0], self.scale[1], self.scale[2]]])
        result.append(['rotate', ['xyz', self.rotate[0], self.rotate[1], self.rotate[2]]])
        return result


@dataclass
class EmbeddedFile:
    """Embedded file (font, model, etc.)."""
    name: str
    file_type: str
    data: str  # Base64 encoded data
    checksum: str = ""

    @classmethod
    def from_sexp(cls, sexp: list) -> 'EmbeddedFile':
        name = unquote_string(get_value(sexp, 'name', ''))
        file_type = get_value(sexp, 'type', 'other')

        # Parse data - may be pipe-delimited or quoted strings
        data_elem = find_element(sexp, 'data')
        data_parts = []
        if data_elem:
            for item in data_elem[1:]:
                if isinstance(item, (str, QuotedString)):
                    # Remove pipe delimiters
                    s = str(item).strip('|')
                    data_parts.append(s)
        data = ''.join(data_parts)

        checksum = unquote_string(get_value(sexp, 'checksum', ''))

        return cls(name=name, file_type=file_type, data=data, checksum=checksum)

    def to_sexp(self) -> list:
        result = ['file',
                  ['name', QuotedString(self.name)],
                  ['type', self.file_type]]

        # Format base64 with proper KiCad line wrapping
        # KiCad format:
        #   (data |BASE64_LINE1
        #       BASE64_LINE2
        #       ...
        #       BASE64_LAST|
        #   )
        # First line starts with |, last line ends with |
        # Subsequent lines get indentation added by SexpWriter
        lines = [self.data[i:i+MIME_BASE64_LENGTH] for i in range(0, len(self.data), MIME_BASE64_LENGTH)]

        formatted_parts = []
        for i, line in enumerate(lines):
            if i == 0:
                # First line: |BASE64 (no leading newline, directly after "data ")
                if len(lines) == 1:
                    # Single line: |BASE64|
                    formatted_parts.append(f'|{line}|')
                else:
                    formatted_parts.append(f'|{line}')
            elif i == len(lines) - 1:
                # Last line: BASE64| (has leading newline, SexpWriter adds indent)
                formatted_parts.append(f'\n{line}|')
            else:
                # Middle lines: BASE64 (has leading newline, SexpWriter adds indent)
                formatted_parts.append(f'\n{line}')
        # Note: Don't add trailing newline - SexpWriter handles the newline before closing paren

        data_block = FormattedDataBlock(''.join(formatted_parts))
        result.append(['data', data_block])

        if self.checksum:
            result.append(['checksum', QuotedString(self.checksum)])

        return result
