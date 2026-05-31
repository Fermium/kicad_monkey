"""
KiCad-format netlist emit (Phase G — Slice N-5).

Renders a :class:`~kicad_monkey.KiCadNetlist` into the canonical
``kicad-cli sch export netlist --format kicadsexpr`` text shape:

.. code:: scheme

    (export (version "E")
      (design (source ...) (date ...) (tool ...) (sheet ...)*)
      (components (comp (ref ...) (value ...) ...)*)
      (libparts (libpart (lib ...) (part ...) ...)*)
      (libraries (library (logical ...))*)
      (nets (net (code "1") (name "...") (node ...)*)*))

The emit reuses :func:`format_sexp` so spacing matches kicad-cli's own
two-space indent and one-list-per-line layout. ``version "E"`` is
locked as a constant — bump :data:`KICAD_NETLIST_VERSION` when
kicad-cli changes (currently stable since KiCad 6.0).

Field rules (mirrors ``netlist_exporter_kicad.cpp``):

* ``(source ...)`` — full path to the top-level ``.kicad_sch``.
* ``(date ...)`` / ``(tool ...)`` — caller supplies; default tool is
  ``"kicad_monkey"`` and default date is the current local time
  formatted as KiCad does (``%a %d %b %Y %I:%M:%S %p``).
* ``(comp ...)`` — emits ``ref``, ``value``, ``footprint`` (when set),
  ``libsource`` (always — kicad-cli emits even when the lib was
  unresolved). Non-standard properties become ``(property ...)``
  blocks. ``sheetpath`` carries human + UUID forms; ``tstamps`` is
  the symbol's instance UUID.
* ``(libpart ...)`` — emits ``description`` / ``docs`` (when set),
  optional ``footprints`` filter list, ``fields`` (Reference / Value /
  Datasheet when set), and ``pins`` sorted by natural-numeric order.
* ``(libraries)`` — kicad-cli emits an empty list when no project-level
  ``(library ...)`` blocks are loaded; we follow.
* ``(net ...)`` — ``code`` and ``name`` always quoted; per-node emits
  ``ref``, ``pin``, optional ``pinfunction`` (the pin's name) and
  optional ``pintype`` (the electrical type token).
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from .kicad_netlist_model import (
    KiCadDesignSheet,
    KiCadLibPart,
    KiCadNet,
    KiCadNetlist,
    KiCadNetlistComponent,
)
from .kicad_sexpr import QuotedString, build_sexp, format_sexp


# Locked until kicad-cli moves; mirrors NETLIST_HEAD_VERSION in
# eeschema/netlist_exporters/netlist_exporter_kicad.cpp.
KICAD_NETLIST_VERSION = "E"


def to_kicad_sexpr(
    netlist: KiCadNetlist,
    *,
    source_path: str = "",
    tool: str = "kicad_monkey",
    date: Optional[str] = None,
) -> str:
    """Render ``netlist`` into the canonical kicad-cli netlist string.

    The returned string is freshly indented via :func:`format_sexp`
    (two-space, one list per line) and ends with a trailing newline —
    matches kicad-cli's own emit byte-for-byte modulo the
    ``(date ...)`` / ``(tool ...)`` / ``(source ...)`` lines and any
    diff in driver-resolution corner cases (covered by slice N-9).

    Args:
        netlist: the resolved internal model (typically the output of
            :func:`compile_design_netlist`).
        source_path: full path to the top-level ``.kicad_sch`` — written
            into the ``(source ...)`` line. Empty string emits an empty
            quoted string (kicad-cli does the same for unsaved
            designs).
        tool: tool identifier — emitted verbatim into ``(tool ...)``.
        date: optional pre-formatted date string. ``None`` (default)
            uses the current local time formatted as
            ``"%a %d %b %Y %I:%M:%S %p"``. Passing an empty string
            emits an empty quoted ``(date ...)``.
    """
    if date is None:
        date = datetime.now().strftime("%a %d %b %Y %I:%M:%S %p")

    sexp = ["export", ["version", QuotedString(KICAD_NETLIST_VERSION)]]
    sexp.append(_design_block(
        netlist,
        source_path=source_path,
        date=date,
        tool=tool,
    ))
    sexp.append(_components_block(netlist.components))
    sexp.append(_libparts_block(netlist.libparts))
    sexp.append(_libraries_block(netlist.libraries))
    sexp.append(_nets_block(netlist.nets))

    raw = build_sexp(sexp)
    return format_sexp(raw, indentation_size=2, max_nesting=99)


# ---------------------------------------------------------------------------
# Block builders
# ---------------------------------------------------------------------------


def _design_block(
    netlist: KiCadNetlist,
    *,
    source_path: str,
    date: str,
    tool: str,
) -> list:
    block: list = ["design"]
    block.append(["source", QuotedString(source_path)])
    block.append(["date", QuotedString(date)])
    block.append(["tool", QuotedString(tool)])
    for sheet in netlist.design_metadata.sheets:
        block.append(_sheet_block(sheet))
    return block


def _sheet_block(sheet: KiCadDesignSheet) -> list:
    block: list = [
        "sheet",
        ["number", QuotedString(str(sheet.number))],
        ["name", QuotedString(sheet.name or "/")],
        ["tstamps", QuotedString(sheet.tstamps or "/")],
    ]
    block.append(_title_block_block(sheet))
    return block


def _title_block_block(sheet: KiCadDesignSheet) -> list:
    """Emit the per-sheet ``(title_block ...)`` chunk.

    kicad-cli emits a fixed shape: ``title`` / ``company`` / ``rev`` /
    ``date`` (each bare when empty) plus 9 numbered comments (always
    present, with empty values when unset). We mirror that — keeps
    structural diffs against the kicad-cli oracle clean.
    """
    tb: list = ["title_block"]
    tb.append(_kv_or_bare("title", sheet.title))
    tb.append(_kv_or_bare("company", sheet.company))
    tb.append(_kv_or_bare("rev", sheet.revision))
    tb.append(_kv_or_bare("date", sheet.date))
    # The (source ...) line inside title_block holds the bare filename.
    # We don't track per-sheet filenames yet — emit empty for parity.
    tb.append(["source", QuotedString("")])
    for i in range(1, 10):
        tb.append([
            "comment",
            ["number", QuotedString(str(i))],
            ["value", QuotedString("")],
        ])
    return tb


def _kv_or_bare(key: str, value: str) -> list:
    """``(key)`` when value is empty, ``(key "value")`` otherwise."""
    if value:
        return [key, QuotedString(value)]
    return [key]


def _components_block(components: Iterable[KiCadNetlistComponent]) -> list:
    block: list = ["components"]
    for comp in components:
        block.append(_comp_block(comp))
    return block


def _comp_block(comp: KiCadNetlistComponent) -> list:
    out: list = ["comp", ["ref", QuotedString(comp.reference)]]
    # KiCad's netlist exporter writes the value field unconditionally,
    # substituting "~" for an empty value (see eeschema/netlist_exporters/
    # netlist_exporter_xml.cpp:228-231 — the same makeRoot path is used
    # for both kicadxml and kicadsexpr formats).
    out.append(["value", QuotedString(comp.value if comp.value else "~")])
    if comp.footprint:
        out.append(["footprint", QuotedString(comp.footprint)])
    out.append([
        "libsource",
        ["lib", QuotedString(comp.libsource_lib)],
        ["part", QuotedString(comp.libsource_part)],
        ["description", QuotedString(comp.libsource_description)],
    ])
    # Non-standard properties — sorted for determinism.
    for k in sorted(comp.properties.keys()):
        out.append([
            "property",
            ["name", QuotedString(k)],
            ["value", QuotedString(comp.properties[k])],
        ])
    out.append([
        "sheetpath",
        ["names", QuotedString(comp.sheet_path_names or "/")],
        ["tstamps", QuotedString(comp.sheet_path_uuids or "/")],
    ])
    if comp.instance_uuid:
        out.append(["tstamps", QuotedString(comp.instance_uuid)])
    return out


def _libparts_block(libparts: Iterable[KiCadLibPart]) -> list:
    block: list = ["libparts"]
    for lp in libparts:
        block.append(_libpart_block(lp))
    return block


def _libpart_block(lp: KiCadLibPart) -> list:
    out: list = [
        "libpart",
        ["lib", QuotedString(lp.lib)],
        ["part", QuotedString(lp.part)],
    ]
    if lp.description:
        out.append(["description", QuotedString(lp.description)])
    if lp.docs:
        out.append(["docs", QuotedString(lp.docs)])
    if lp.footprints_filter:
        fps: list = ["footprints"]
        for f in lp.footprints_filter:
            fps.append(["fp", QuotedString(f)])
        out.append(fps)
    if lp.fields:
        fields_block: list = ["fields"]
        for fname in sorted(lp.fields.keys()):
            fields_block.append([
                "field",
                ["name", QuotedString(fname)],
                QuotedString(lp.fields[fname]),
            ])
        out.append(fields_block)
    if lp.pins:
        pins_block: list = ["pins"]
        for pin in lp.pins:
            pins_block.append([
                "pin",
                ["num", QuotedString(pin.number)],
                ["name", QuotedString(pin.name)],
                ["type", QuotedString(pin.pin_type)],
            ])
        out.append(pins_block)
    return out


def _libraries_block(libraries: Iterable[str]) -> list:
    block: list = ["libraries"]
    for lib in libraries:
        block.append(["library", ["logical", QuotedString(lib)]])
    return block


def _nets_block(nets: Iterable[KiCadNet]) -> list:
    block: list = ["nets"]
    for net in nets:
        n: list = [
            "net",
            ["code", QuotedString(str(net.code))],
            ["name", QuotedString(net.name)],
        ]
        for term in net.terminals:
            node: list = [
                "node",
                ["ref", QuotedString(term.designator)],
                ["pin", QuotedString(term.pin)],
            ]
            if term.pin_name:
                node.append(["pinfunction", QuotedString(term.pin_name)])
            if term.pin_type:
                node.append(["pintype", QuotedString(term.pin_type)])
            n.append(node)
        block.append(n)
    return block


__all__ = [
    "KICAD_NETLIST_VERSION",
    "to_kicad_sexpr",
]
