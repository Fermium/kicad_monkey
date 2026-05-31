"""
Bridge from :class:`~kicad_monkey.KiCadNetlist` to ``data_models.Netlist``.

Renders the KiCad-specific internal model into the generic ``netlist_a0``
shape so consumers can speak one schema regardless of source CAD.

Mapping rules:

* ``DesignComponent.designator`` ← ``KiCadNetlistComponent.reference``
* ``DesignComponent.uid`` ← instance UUID (placement-unique).
* ``DesignComponent.value`` / ``footprint`` ← direct.
* ``DesignComponent.description`` ← ``libsource_description``.
* ``DesignComponent.parameters`` ← KiCad properties merged with a
  ``_source_cad: "kicad"`` namespace plus the standard fields kicad-cli
  drops in (``libsource_lib`` / ``libsource_part`` / ``sheet_path``
  human + UUID forms / ``instance_uuid`` / ``in_bom`` / ``on_board`` /
  ``dnp``). All keys are strings to keep the dict round-trippable
  through JSON without surprises.
* ``DesignComponentPin`` rows are derived from the matching ``KiCadLibPart``
  (so we always emit a stable pin list per component, with ``net``
  populated from the resolved netlist).
* ``DesignNet.name`` ← direct. ``aliases`` carries any net-name aliases
  (bus member alternates etc.).
* ``DesignNetConnection`` ← one per terminal; ``pin_name`` from KiCad's
  pin function (the symbol-pin name).
* ``DesignNetClass`` rows mirror ``KiCadNetlist.net_classes`` after project
  net classes have been applied. Each row carries the class name plus the
  list of nets currently assigned to it; a synthetic ``"Default"`` class
  always exists as the implicit fallback.
* ``Netlist.metadata`` carries project-level info (sheets, kicad version
  marker, source path).
* ``Netlist.source`` carries ``{"cad": "kicad", "tool": ..., "date": ...}``.

The reverse direction (``netlist_a0`` → ``KiCadNetlist``) is intentionally
not implemented — the canonical KiCad netlist format is the kicadsexpr
emit, not the generic JSON.
"""

from __future__ import annotations

import importlib
from typing import Dict, List

from .kicad_netlist_model import (
    KiCadLibPart,
    KiCadNet,
    KiCadNetlist,
    KiCadNetlistComponent,
)


def kicad_netlist_to_data_models_netlist(netlist: KiCadNetlist):
    """Convert a :class:`KiCadNetlist` into a ``data_models.Netlist``.

    Args:
        netlist: the resolved internal model.

    Returns:
        A ``data_models.Netlist`` instance with components / nets /
        net_classes / metadata populated.
    """
    # Imported lazily so kicad_monkey doesn't pay the data_models import
    # cost unless the bridge is actually used.
    data_models = importlib.import_module("data_models")
    DesignComponent = getattr(data_models, "DesignComponent")
    DesignComponentPin = getattr(data_models, "DesignComponentPin")
    DesignNet = getattr(data_models, "DesignNet")
    DesignNetClass = getattr(data_models, "DesignNetClass")
    DesignNetConnection = getattr(data_models, "DesignNetConnection")
    Netlist = getattr(data_models, "Netlist")

    libpart_index: Dict[tuple, KiCadLibPart] = {
        (lp.lib, lp.part): lp for lp in netlist.libparts
    }

    # First pass — figure out which net each (designator, pin) sits on
    # so the per-component pin list can carry it directly.
    pin_to_net: Dict[tuple, str] = {}
    for net in netlist.nets:
        for term in net.terminals:
            pin_to_net[(term.designator, term.pin)] = net.name

    components = [
        _component_to_data_models(comp, libpart_index, pin_to_net,
                                   DesignComponent, DesignComponentPin)
        for comp in netlist.components
    ]

    nets = [_net_to_data_models(net, DesignNet, DesignNetConnection)
            for net in netlist.nets]

    net_classes = _build_net_classes(netlist, DesignNetClass)

    metadata = _build_metadata(netlist)
    source = {
        "cad": "kicad",
        "tool": netlist.design_metadata.tool,
        "date": netlist.design_metadata.date,
        "source_path": netlist.design_metadata.source,
    }

    return Netlist(
        components=components,
        nets=nets,
        net_classes=net_classes,
        metadata=metadata,
        source=source,
    )


# ---------------------------------------------------------------------------
# Per-record converters
# ---------------------------------------------------------------------------


def _component_to_data_models(
    comp: KiCadNetlistComponent,
    libpart_index: Dict[tuple, KiCadLibPart],
    pin_to_net: Dict[tuple, str],
    DesignComponent,  # noqa: N803 — passed in for lazy import
    DesignComponentPin,  # noqa: N803
):
    parameters = _component_parameters(comp)

    libpart = libpart_index.get((comp.libsource_lib, comp.libsource_part))
    pins = []
    if libpart is not None:
        for pin in libpart.pins:
            pins.append(DesignComponentPin(
                number=pin.number,
                name=pin.name,
                net=pin_to_net.get((comp.reference, pin.number), ""),
            ))

    return DesignComponent(
        designator=comp.reference,
        uid=comp.instance_uuid,
        value=comp.value,
        footprint=comp.footprint,
        description=comp.libsource_description,
        parameters=parameters,
        pins=pins,
    )


def _component_parameters(comp: KiCadNetlistComponent) -> Dict[str, str]:
    """Merge KiCad component metadata into a JSON-stable dict."""
    out: Dict[str, str] = {"_source_cad": "kicad"}
    if comp.libsource_lib:
        out["kicad_libsource_lib"] = comp.libsource_lib
    if comp.libsource_part:
        out["kicad_libsource_part"] = comp.libsource_part
    if comp.sheet_path_names:
        out["kicad_sheet_path_names"] = comp.sheet_path_names
    if comp.sheet_path_uuids:
        out["kicad_sheet_path_uuids"] = comp.sheet_path_uuids
    if comp.instance_uuid:
        out["kicad_instance_uuid"] = comp.instance_uuid
    out["kicad_in_bom"] = "true" if comp.in_bom else "false"
    out["kicad_on_board"] = "true" if comp.on_board else "false"
    out["kicad_dnp"] = "true" if comp.dnp else "false"
    # User-defined component properties carried last so they can override
    # the defaults if a project deliberately uses a colliding key.
    for key, value in comp.properties.items():
        out[key] = value
    return out


def _net_to_data_models(net: KiCadNet, DesignNet, DesignNetConnection):  # noqa: N803
    aliases: List[str] = []
    # KiCadNet stores aliases lazily on ``aliases`` if the compiler set
    # them — fall back to empty list.
    raw_aliases = getattr(net, "aliases", None)
    if raw_aliases:
        aliases = list(raw_aliases)

    connections = [
        DesignNetConnection(
            designator=term.designator,
            pin=term.pin,
            pin_name=term.pin_name,
        )
        for term in net.terminals
    ]
    return DesignNet(
        name=net.name,
        net_class=net.net_class,
        aliases=aliases,
        connections=connections,
    )


def _build_net_classes(netlist: KiCadNetlist, DesignNetClass):  # noqa: N803
    """Build the ``net_classes`` list with per-class net membership.

    The membership list is computed from the live ``netlist.nets``
    assignments rather than re-derived from the project — that way the
    JSON payload stays internally consistent (every net listed under a
    class is actually present in the netlist).
    """
    by_class: Dict[str, List[str]] = {cls.name: [] for cls in netlist.net_classes}
    for net in netlist.nets:
        if net.net_class and net.net_class in by_class:
            by_class[net.net_class].append(net.name)
    return [
        DesignNetClass(
            name=cls.name,
            nets=list(by_class.get(cls.name, [])),
            description=cls.description,
        )
        for cls in netlist.net_classes
    ]


def _build_metadata(netlist: KiCadNetlist) -> Dict[str, object]:
    sheets = [
        {
            "number": sheet.number,
            "name": sheet.name,
            "tstamps": sheet.tstamps,
            "title": sheet.title,
            "company": sheet.company,
            "revision": sheet.revision,
            "date": sheet.date,
        }
        for sheet in netlist.design_metadata.sheets
    ]
    metadata: Dict[str, object] = {"sheets": sheets}
    if netlist.libraries:
        metadata["kicad_libraries"] = list(netlist.libraries)
    return metadata


__all__ = [
    "kicad_netlist_to_data_models_netlist",
]
