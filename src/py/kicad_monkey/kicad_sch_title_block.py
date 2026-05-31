"""
KiCad Schematic Title Block

Title block and paper size definitions for schematic documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .kicad_sexpr import QuotedString, SexpList
from .kicad_base import find_all_elements, get_value, unquote_string


@dataclass
class TitleBlock:
    """Schematic title block (appears in schematic border).

    Contains metadata about the schematic: title, date, revision, company, etc.
    Comments are numbered 1-9.

    S-expression format:
        (title_block
            (title "Project Title")
            (date "2025-01-18")
            (rev "1.0")
            (company "Company Name")
            (comment 1 "Comment 1")
            (comment 2 "Comment 2")
            ...
        )
    """
    title: str = ""
    date: str = ""
    rev: str = ""
    company: str = ""
    comments: Dict[int, str] = field(default_factory=dict)  # 1-9

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'TitleBlock':
        """Parse from (title_block (title "...") (date "...") ...)."""
        title = unquote_string(get_value(sexp, 'title', ''))
        date = unquote_string(get_value(sexp, 'date', ''))
        rev = unquote_string(get_value(sexp, 'rev', ''))
        company = unquote_string(get_value(sexp, 'company', ''))

        comments = {}
        for comment_elem in find_all_elements(sexp, 'comment'):
            if len(comment_elem) >= 3:
                num = int(comment_elem[1])
                text = unquote_string(comment_elem[2])
                comments[num] = text

        return cls(
            title=title, date=date, rev=rev, company=company,
            comments=comments, _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result: SexpList = ['title_block']

        if self.title:
            result.append(['title', QuotedString(self.title)])
        if self.date:
            result.append(['date', QuotedString(self.date)])
        if self.rev:
            result.append(['rev', QuotedString(self.rev)])
        if self.company:
            result.append(['company', QuotedString(self.company)])

        for num in sorted(self.comments.keys()):
            result.append(['comment', num, QuotedString(self.comments[num])])

        return result


@dataclass
class PaperSize:
    """Paper/page size settings.

    Standard sizes: A4, A3, A2, A1, A0, A, B, C, D, E, USLetter, USLegal
    Custom size uses "User" with explicit width/height.

    S-expression format:
        (paper "A4")
        (paper "User" 400 300)
        (paper "A4" portrait)
    """
    size: str = "A4"
    width: Optional[float] = None  # Custom width (if size == "User")
    height: Optional[float] = None  # Custom height
    portrait: bool = False

    @classmethod
    def from_sexp(cls, sexp: list) -> 'PaperSize':
        """Parse from (paper "A4") or (paper "User" W H) format."""
        if not sexp or len(sexp) < 2:
            return cls()

        size = unquote_string(sexp[1])
        width = None
        height = None
        portrait = False

        # Check for custom dimensions
        idx = 2
        if len(sexp) > 2 and isinstance(sexp[2], (int, float)):
            width = float(sexp[2])
            idx = 3
        if len(sexp) > 3 and isinstance(sexp[3], (int, float)):
            height = float(sexp[3])
            idx = 4

        # Check for portrait flag
        if 'portrait' in sexp[idx:]:
            portrait = True

        return cls(size=size, width=width, height=height, portrait=portrait)

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = ['paper', QuotedString(self.size)]
        if self.width is not None:
            result.append(self.width)
        if self.height is not None:
            result.append(self.height)
        if self.portrait:
            result.append('portrait')
        return result
