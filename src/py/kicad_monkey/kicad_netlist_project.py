"""
Project-side enrichment for the KiCad netlist.

The :class:`~kicad_monkey.KiCadNetlist` is built by the connectivity
compiler from schematic data alone. KiCad stores net-class metadata in
the ``.kicad_pro`` sidecar, not in any ``.kicad_sch`` — so once a
project is loaded we can enrich the netlist by:

1. Adding :class:`KiCadNetClass` entries from
   ``project.net_settings.classes``.
2. Assigning a class name to each :class:`KiCadNet` based on the
   project's ``netclass_assignments`` (exact net-name → list of classes)
   and ``netclass_patterns`` (wildcard pattern → class).

This module is the single authoritative place for that mapping; the
kicadsexpr emitter doesn't write net-class info (kicad-cli's
``--format kicadsexpr`` doesn't either) but JSON payloads surface it
directly.

Pattern matching uses ``fnmatch`` semantics (``*`` / ``?`` / ``[seq]``)
which lines up with KiCad's own wildcard mode for net-class assignment
patterns. Regex-mode patterns are not yet supported.
"""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING

from .kicad_netlist_model import KiCadNetClass, KiCadNetlist

if TYPE_CHECKING:  # pragma: no cover
    from .kicad_project import KiCadProject


def apply_project_net_classes(
    netlist: KiCadNetlist, project: "KiCadProject | None"
) -> None:
    """Populate ``netlist.net_classes`` and ``net.net_class`` from project.

    No-op when *project* is ``None`` or carries no ``net_settings``.
    Safe to call repeatedly — the function clears
    ``netlist.net_classes`` and re-assigns ``net.net_class`` from
    scratch each invocation.

    Resolution order per net:
    1. exact match in ``netclass_assignments`` (first class wins),
    2. first matching pattern in ``netclass_patterns``,
    3. ``"Default"`` as the implicit fallback (matches kicad-cli's
       behaviour when no rule applies).
    """
    if project is None or project.net_settings is None:
        return

    settings = project.net_settings

    # Build the class catalog. KiCad's "Default" class is always
    # present — duplicate-by-name entries are deduped (last wins).
    by_name: dict[str, KiCadNetClass] = {}
    for cls in settings.classes:
        if not cls.name:
            continue
        by_name[cls.name] = KiCadNetClass(
            name=cls.name,
            description=str(cls.raw.get("description", "") or ""),
        )
    if "Default" not in by_name:
        by_name["Default"] = KiCadNetClass(name="Default")

    # Stable order: classes from project first (by their declared
    # order in the .kicad_pro), then the synthetic "Default" if it
    # wasn't already there.
    ordered: list[KiCadNetClass] = []
    seen: set[str] = set()
    for cls in settings.classes:
        if cls.name and cls.name in by_name and cls.name not in seen:
            ordered.append(by_name[cls.name])
            seen.add(cls.name)
    if "Default" not in seen:
        ordered.append(by_name["Default"])
    netlist.net_classes = ordered

    # Resolution helper. Returns the assigned class name or "Default".
    def _resolve(net_name: str) -> str:
        # 1. exact assignments
        names = settings.netclass_assignments.get(net_name)
        if names:
            for candidate in names:
                if candidate in by_name:
                    return candidate
        # 2. wildcard patterns
        for pat in settings.netclass_patterns:
            if pat.netclass_name not in by_name:
                continue
            if not pat.pattern:
                continue
            if fnmatch.fnmatchcase(net_name, pat.pattern):
                return pat.netclass_name
        # 3. fallback
        return "Default"

    for net in netlist.nets:
        net.net_class = _resolve(net.name)


__all__ = [
    "apply_project_net_classes",
]
