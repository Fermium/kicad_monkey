"""KiCad schematic top-level (group ...) annotation.

KiCad emits this via ``SCH_IO_KICAD_SEXPR::saveGroup`` for
``SCH_GROUP_T`` items in
``eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr.cpp:1656``. The wire
format is::

    (group "name"
        (uuid "...")
        [(locked yes)]
        [(lib_id "Lib:DesignBlock")]
        (members "uuid1" "uuid2" ...)
    )

Empty groups are not emitted at all (``saveGroup`` early-returns when
``GetItems().empty()`` per line 1659), so we never have to round-trip
a member-less group.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_value, unquote_string


@dataclass
class SchGroup:
    """Top-level grouping annotation on a schematic sheet."""

    name: str = ""
    uuid: str = ""
    locked: bool = False
    lib_id: Optional[str] = None
    members: List[str] = field(default_factory=list)
    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchGroup':
        name = unquote_string(sexp[1]) if len(sexp) > 1 else ""
        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        locked_elem = find_element(sexp, 'locked')
        locked = bool(locked_elem and len(locked_elem) > 1 and locked_elem[1] == 'yes')

        lib_id_elem = find_element(sexp, 'lib_id')
        lib_id = unquote_string(lib_id_elem[1]) if lib_id_elem and len(lib_id_elem) > 1 else None

        members: List[str] = []
        members_elem = find_element(sexp, 'members')
        if members_elem:
            for tok in members_elem[1:]:
                members.append(unquote_string(tok) if isinstance(tok, str) else str(tok))

        return cls(
            name=name, uuid=uuid, locked=locked,
            lib_id=lib_id, members=members,
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        result: list = ['group', QuotedString(self.name)]
        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])
        if self.locked:
            result.append(['locked', 'yes'])
        if self.lib_id is not None:
            result.append(['lib_id', QuotedString(self.lib_id)])
        # ``saveGroup`` always emits the (members ...) token (it
        # early-returns on empty groups).
        members_elem: list = ['members']
        for m in self.members:
            members_elem.append(QuotedString(m))
        result.append(members_elem)
        return result


__all__ = ['SchGroup']
