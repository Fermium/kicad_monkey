"""
KiCad PCB S-Expression Writer

This module is maintained for backwards compatibility.
All functionality has been consolidated into kicad_sexpr.py.

Prefer importing directly from kicad_sexpr:
    from .kicad_sexpr import SexpWriter, format_float, quote_string
"""

from __future__ import annotations

# Re-export everything from kicad_sexpr for backwards compatibility
from .kicad_sexpr import (
    SexpWriter,
    QuotedString,
    FormattedDataBlock,
    format_float,
    quote_string,
    INDENT_CHAR,
    INDENT_SIZE,
    XY_COLUMN_LIMIT,
    TOKEN_WRAP_THRESHOLD,
    MIME_BASE64_LENGTH,
)

__all__ = [
    'SexpWriter',
    'QuotedString',
    'FormattedDataBlock',
    'format_float',
    'quote_string',
    'INDENT_CHAR',
    'INDENT_SIZE',
    'XY_COLUMN_LIMIT',
    'TOKEN_WRAP_THRESHOLD',
    'MIME_BASE64_LENGTH',
]
