"""Internal data model for resolved KiCad netlists.

The netlist compiler, KiCad s-expression emitter, KiCad-native JSON payload,
and generic netlist bridge all derive their output from these dataclasses.
Graph traversal lives in :mod:`kicad_netlist_compiler`; this module only owns
the resolved data shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Driver-priority enum — mirrors eeschema/connection_graph.h::PRIORITY
# ---------------------------------------------------------------------------


class KiCadDriverPriority(IntEnum):
    """Driver-priority tiers, copied verbatim from KiCad source.

    Matches ``CONNECTION_SUBGRAPH::PRIORITY`` in
    ``eeschema/connection_graph.h``. The integer values are stable
    (we serialise them into ``KiCadNet.driver_priority``) — do NOT
    reorder.
    """

    INVALID = -1
    NONE = 0
    PIN = 1
    SHEET_PIN = 2
    HIER_LABEL = 3
    LOCAL_LABEL = 4
    LOCAL_POWER_PIN = 5
    GLOBAL_POWER_PIN = 6
    GLOBAL = 7


class KiCadDriverKind(StrEnum):
    """Symbolic name for the kind of driver chosen on a subgraph.

    Stored on :attr:`KiCadNet.driver_kind` so the JSON bridge can
    round-trip cleanly. ``StrEnum`` makes each member compare equal to
    its string value (e.g. ``KiCadDriverKind.PIN == "pin"``).
    """

    PIN = "pin"
    SHEET_PIN = "sheet_pin"
    HIER_LABEL = "hier_label"
    LOCAL_LABEL = "local_label"
    LOCAL_POWER_PIN = "local_power_pin"
    GLOBAL_POWER_PIN = "global_power_pin"
    GLOBAL_LABEL = "global_label"
    NONE = ""


# ---------------------------------------------------------------------------
# Pin-type enum — mirrors eeschema/sch_pin.h::ELECTRICAL_PINTYPE values
# ---------------------------------------------------------------------------


class KiCadPinType(StrEnum):
    """Electrical pin type strings as emitted by ``kicad-cli`` netlists."""

    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRI_STATE = "tri_state"
    PASSIVE = "passive"
    FREE = "free"
    UNSPECIFIED = "unspecified"
    POWER_IN = "power_in"
    POWER_OUT = "power_out"
    OPEN_COLLECTOR = "open_collector"
    OPEN_EMITTER = "open_emitter"
    NO_CONNECT = "no_connect"


# ---------------------------------------------------------------------------
# Terminal — one (component, pin) connection on a net
# ---------------------------------------------------------------------------


@dataclass
class KiCadNetlistTerminal:
    """A single (component, pin) connection participating in a net.

    Field order + name set is chosen to match the ``(node ...)`` block
    KiCad emits inside ``(net ...)``::

        (node (ref "R1") (pin "1") (pinfunction "GND") (pintype "passive"))
    """

    designator: str
    pin: str
    pin_name: str = ""        # KiCad: "pinfunction"
    pin_type: str = ""        # one of :class:`KiCadPinType` values
    sheet_path: str = ""      # canonical UUID-form sheet path
    source_pin_id: str = ""   # placed-symbol pin UUID, when available
    svg_id: str = ""          # current render target, usually pin SVG group

    def __post_init__(self) -> None:
        # Normalise so emitters can rely on these being plain strings.
        self.designator = str(self.designator)
        self.pin = str(self.pin)
        self.source_pin_id = str(self.source_pin_id or "")
        self.svg_id = str(self.svg_id or "")


@dataclass
class KiCadNetEndpoint:
    """Source-owned semantic endpoint for schematic net tracing."""

    endpoint_id: str
    role: str
    element_id: str = ""
    object_id: str = ""
    name: str = ""
    source_sheet: str = ""
    connection_point: Optional[tuple[int, int]] = None

    def __post_init__(self) -> None:
        self.endpoint_id = str(self.endpoint_id or "")
        self.role = str(self.role or "")
        self.element_id = str(self.element_id or "")
        self.object_id = str(self.object_id or "")
        self.name = str(self.name or "")
        self.source_sheet = str(self.source_sheet or "")


# ---------------------------------------------------------------------------
# Net — driver-resolved connectivity group with a stable name + code
# ---------------------------------------------------------------------------


@dataclass
class KiCadNet:
    """A resolved net — what KiCad calls a ``CONNECTION_SUBGRAPH``.

    * ``name`` — final net name (e.g. ``"/sub/SIG"``, ``"GND"``,
      ``"Net-(R1-1)"``).
    * ``code`` — sequential code starting at 1; matches kicad-cli's
      net-code numbering convention (assigned in compile order). Slot
      kept stable so emitters can write ``(net (code "<N>") …)`` directly.
    * ``terminals`` — every (designator, pin) attached to the net.
    * ``driver_priority`` — :class:`KiCadDriverPriority` integer of the
      chosen driver. ``NONE`` means the name is auto-generated.
    * ``driver_kind`` — symbolic name for the driver's source item.
    * ``auto_named`` — convenience flag (``True`` when driver is None).
    * ``aliases`` — alternate names (e.g. bus member names) the net
      also responds to. Empty for plain nets.
    * ``graphical`` — SVG/source-object IDs associated with this net,
      grouped by source object type. Pins are added by the design JSON layer
      because the component SVG IDs live on the component rows.
    * ``is_bus`` — True when the underlying subgraph drives a bus
      label (filled at compile time but unused by the kicadsexpr emit;
      bus expansion happens before nets are materialised).
    * ``net_class`` — name of the assigned net-class from the project's
      ``.kicad_pro``. ``""`` means unassigned (kicad-cli's "Default").
      Populated lazily by :func:`apply_project_net_classes`.
    """

    name: str
    code: int = 0
    terminals: List[KiCadNetlistTerminal] = field(default_factory=list)
    driver_priority: int = int(KiCadDriverPriority.NONE)
    driver_kind: str = ""
    auto_named: bool = False
    aliases: List[str] = field(default_factory=list)
    graphical: Dict[str, List[str]] = field(default_factory=dict)
    is_bus: bool = False
    net_class: str = ""
    endpoints: List[KiCadNetEndpoint] = field(default_factory=list)

    def add_terminal(self, terminal: KiCadNetlistTerminal) -> None:
        self.terminals.append(terminal)

    def add_endpoint(self, endpoint: KiCadNetEndpoint) -> None:
        self.endpoints.append(endpoint)


# ---------------------------------------------------------------------------
# Component — placed-symbol view tailored for netlist emit
# ---------------------------------------------------------------------------


@dataclass
class KiCadNetlistComponentUnit:
    """Per-unit pin metadata emitted inside a component ``(units ...)`` block."""

    name: str
    pins: List[str] = field(default_factory=list)


@dataclass
class KiCadNetlistComponent:
    """One row of the ``(components …)`` block in the kicadsexpr emit.

    Filled by the design-level netlist compiler from placed schematic symbols.
    """

    reference: str
    value: str = ""
    footprint: str = ""
    datasheet: str = ""
    description: str = ""
    fields: Dict[str, str] = field(default_factory=dict)
    libsource_lib: str = ""
    libsource_part: str = ""
    libsource_description: str = ""
    sheet_path_names: str = ""
    sheet_path_uuids: str = ""
    instance_uuid: str = ""
    instance_uuids: List[str] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)
    units: List[KiCadNetlistComponentUnit] = field(default_factory=list)
    in_bom: bool = True
    on_board: bool = True
    dnp: bool = False


# ---------------------------------------------------------------------------
# Lib-part — unique (lib, part) entry for ``(libparts …)``
# ---------------------------------------------------------------------------


@dataclass
class KiCadLibPartPin:
    """One pin entry inside a ``(libpart …)``."""

    number: str
    name: str
    pin_type: str = ""


@dataclass
class KiCadLibPart:
    """Library symbol descriptor populated from referenced schematic symbols."""

    lib: str
    part: str
    description: str = ""
    docs: str = ""
    footprints_filter: List[str] = field(default_factory=list)
    fields: Dict[str, str] = field(default_factory=dict)
    pins: List[KiCadLibPartPin] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level netlist envelope
# ---------------------------------------------------------------------------


@dataclass
class KiCadDesignSheet:
    """Per-sheet record for the ``(design …)`` block."""

    number: int
    name: str          # "/" or "/sub/" — human-readable sheet path
    tstamps: str       # "/<root_uuid>/" or "/<root>/<child>/" — UUID form
    title: str = ""
    company: str = ""
    revision: str = ""
    date: str = ""


@dataclass
class KiCadDesignMetadata:
    """``(design …)`` block contents — source / date / tool / sheets."""

    source: str = ""
    date: str = ""
    tool: str = "kicad_monkey"
    sheets: List[KiCadDesignSheet] = field(default_factory=list)


@dataclass
class KiCadNetClass:
    """A KiCad net-class definition.

    Mirrors the subset of ``net_settings.classes[]`` that's relevant
    when emitting a netlist — class identity (name) plus optional
    description. PCB-side electrical constants (track width,
    clearance, etc.) live on :class:`KiCadProjectNetClass` and aren't
    duplicated here.
    """

    name: str
    description: str = ""


@dataclass
class KiCadNetlist:
    """Top-level netlist payload."""

    nets: List[KiCadNet] = field(default_factory=list)
    components: List[KiCadNetlistComponent] = field(default_factory=list)
    libparts: List[KiCadLibPart] = field(default_factory=list)
    libraries: List[str] = field(default_factory=list)
    net_classes: List[KiCadNetClass] = field(default_factory=list)
    design_metadata: KiCadDesignMetadata = field(default_factory=KiCadDesignMetadata)

    def get_net(self, name: str) -> Optional[KiCadNet]:
        for n in self.nets:
            if n.name == name or name in n.aliases:
                return n
        return None

    def get_component(self, reference: str) -> Optional[KiCadNetlistComponent]:
        for c in self.components:
            if c.reference == reference:
                return c
        return None


__all__ = [
    "KiCadDriverPriority",
    "KiCadDriverKind",
    "KiCadPinType",
    "KiCadNetlistTerminal",
    "KiCadNetEndpoint",
    "KiCadNet",
    "KiCadNetlistComponentUnit",
    "KiCadNetlistComponent",
    "KiCadLibPartPin",
    "KiCadLibPart",
    "KiCadDesignSheet",
    "KiCadDesignMetadata",
    "KiCadNetClass",
    "KiCadNetlist",
]
