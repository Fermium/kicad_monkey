"""
Test L0_024: single-sheet netlist compiler (Phase G — Slice N-3).

Pure-unit coverage for :mod:`kicad_monkey.kicad_netlist_compiler` and the
underlying :mod:`kicad_monkey.kicad_netlist_model`. Inputs are
synthesized :class:`KiCadSchematic` instances built via the public
dataclass constructors — no on-disk fixture needed.

Covers:

* :class:`KiCadDriverPriority` integer values match KiCad's
  ``CONNECTION_SUBGRAPH::PRIORITY`` (eeschema/connection_graph.h).
* :func:`_resolve_driver` (exercised via :func:`compile_sheet_subgraphs`)
  picks the highest-priority driver and breaks ties alphabetically on
  the driver name, falling back to insertion order.
* :func:`name_net` formatting rules:
  - GLOBAL label  → ``/<text>``
  - LOCAL_LABEL / HIER_LABEL / SHEET_PIN → ``<sheet_path><text>``
  - GLOBAL_POWER_PIN / LOCAL_POWER_PIN  → bare ``<value>``
  - PIN-only / NONE → ``Net-(<ref>-<pin>)`` with alphabetical
    ``(designator, pin_number)`` selection of the seed terminal.
* :func:`compile_sheet_subgraphs` end-to-end on hand-built schematics:
  two pins joined by a wire collapse to one subgraph; a label landing on
  the wire wins over the auto-name; a global label outranks a local
  label; a global power pin produces a bare net name.
* :func:`compile_sheet_netlist` materialises terminals sorted by
  ``(designator, pin_number)`` and skips floating wire stubs.
"""

from __future__ import annotations

from typing import List, Optional

from kicad_monkey import (
    KiCadDriverKind,
    KiCadDriverPriority,
    KiCadNet,
    KiCadNetlist,
    KiCadNetlistTerminal,
    Subgraph,
    compile_sheet_netlist,
    compile_sheet_subgraphs,
    name_net,
)
from kicad_monkey.kicad_lib_subsymbol import LibSubSymbol
from kicad_monkey.kicad_lib_symbol import LibSymbol
from kicad_monkey.kicad_netlist_compiler import (
    _LabelDriver,
    _PinDriver,
    _resolve_driver,
)
from kicad_monkey.kicad_sch_enums import LabelShape, PinElectricalType, PinGraphicStyle
from kicad_monkey.kicad_sch_label import (
    SchGlobalLabel,
    SchHierarchicalLabel,
    SchLabel,
)
from kicad_monkey.kicad_sch_junction import SchJunction
from kicad_monkey.kicad_sch_symbol import SchSymbol, SchSymbolPin
from kicad_monkey.kicad_sch_sheet import SchSheet, SchSheetPin, SchSheetProperty
from kicad_monkey.kicad_sch_wire import SchWire
from kicad_monkey.kicad_schematic import KiCadSchematic
from kicad_monkey.kicad_sym_pin import SymPin
from kicad_monkey.kicad_sym_property import SymProperty


# ---------------------------------------------------------------------------
# Synthesized fixture builders
# ---------------------------------------------------------------------------


def _pin(at_x: float, at_y: float, *, number: str = "1",
         angle: float = 180.0, length: float = 0.0,
         electrical: PinElectricalType = PinElectricalType.PASSIVE,
         name: str = "~", hide: bool = False) -> SymPin:
    """Build a SymPin whose connection point is exactly (at_x, at_y).

    KiCad library pins use Y-up, with ``length`` extending the pin away
    from the symbol body in the direction implied by ``at_angle``. We
    set ``length=0`` so the pin's connection point and lib-coord origin
    coincide — keeps the placement transform math trivial in tests.
    """
    return SymPin(
        electrical_type=electrical,
        graphic_style=PinGraphicStyle.LINE,
        at_x=at_x, at_y=at_y, at_angle=angle, length=length,
        number=number, name=name, hide=hide,
    )


def _libsym(
    name: str,
    *pins: SymPin,
    power: bool = False,
    power_kind: Optional[str] = None,
) -> LibSymbol:
    sub = LibSubSymbol(name=f"{name}_1_0", unit=1, style=0, pins=list(pins))
    return LibSymbol(name=name, power=power, power_kind=power_kind,
                     subsymbols=[sub])


def _placed(
    lib_id: str,
    *,
    reference: str,
    value: str = "",
    at_x: float = 0.0,
    at_y: float = 0.0,
    angle: float = 0.0,
    mirror: Optional[str] = None,
    unit: int = 1,
    convert: int = 1,
) -> SchSymbol:
    sym = SchSymbol(
        lib_id=lib_id, at_x=at_x, at_y=at_y, at_angle=angle,
        mirror=mirror, unit=unit, convert=convert,
    )
    sym.properties = [
        SymProperty(key="Reference", value=reference, id=0),
        SymProperty(key="Value", value=value or reference, id=1),
    ]
    return sym


def _wire(*points) -> SchWire:
    return SchWire(points=[tuple(p) for p in points])


def _sheet_pin(name: str, at_x: float, at_y: float) -> SchSheetPin:
    return SchSheetPin(name=name, shape=LabelShape.OUTPUT, at_x=at_x, at_y=at_y)


def _sheet(uuid: str, name: str, file_name: str, *pins: SchSheetPin) -> SchSheet:
    sh = SchSheet(uuid=uuid)
    sh.properties = [
        SchSheetProperty(key="Sheetname", value=name),
        SchSheetProperty(key="Sheetfile", value=file_name),
    ]
    sh.pins = list(pins)
    return sh


def _empty_sch() -> KiCadSchematic:
    return KiCadSchematic()


# ---------------------------------------------------------------------------
# KiCadDriverPriority — values must match KiCad's PRIORITY enum exactly
# ---------------------------------------------------------------------------


def test_driver_priority_integer_values_match_kicad():
    """Mirrors eeschema/connection_graph.h::CONNECTION_SUBGRAPH::PRIORITY."""
    assert int(KiCadDriverPriority.NONE) == 0
    assert int(KiCadDriverPriority.PIN) == 1
    assert int(KiCadDriverPriority.SHEET_PIN) == 2
    assert int(KiCadDriverPriority.HIER_LABEL) == 3
    assert int(KiCadDriverPriority.LOCAL_LABEL) == 4
    assert int(KiCadDriverPriority.LOCAL_POWER_PIN) == 5
    assert int(KiCadDriverPriority.GLOBAL_POWER_PIN) == 6
    assert int(KiCadDriverPriority.GLOBAL) == 7


def test_driver_priority_ordering_strict():
    assert (
        KiCadDriverPriority.PIN
        < KiCadDriverPriority.SHEET_PIN
        < KiCadDriverPriority.HIER_LABEL
        < KiCadDriverPriority.LOCAL_LABEL
        < KiCadDriverPriority.LOCAL_POWER_PIN
        < KiCadDriverPriority.GLOBAL_POWER_PIN
        < KiCadDriverPriority.GLOBAL
    )


# ---------------------------------------------------------------------------
# _resolve_driver — direct unit tests
# ---------------------------------------------------------------------------


def _make_subgraph(*,
                   labels: List[_LabelDriver] = None,
                   pins: List[_PinDriver] = None) -> Subgraph:
    sg = Subgraph()
    sg.label_drivers = list(labels or [])
    sg.pin_drivers = list(pins or [])
    return sg


def _label(text: str, priority: KiCadDriverPriority,
           kind: KiCadDriverKind) -> _LabelDriver:
    return _LabelDriver(text=text, coord=(0, 0), priority=priority, kind=kind)


def _pin_drv(designator: str, pin_number: str, *,
             priority: KiCadDriverPriority = KiCadDriverPriority.PIN,
             is_power: bool = False, power_value: str = "") -> _PinDriver:
    return _PinDriver(
        designator=designator, pin_number=pin_number, pin_name="",
        pin_type="passive", coord=(0, 0),
        priority=priority, is_power=is_power, power_value=power_value,
    )


def test_resolve_picks_highest_priority_label():
    sg = _make_subgraph(labels=[
        _label("LOCAL", KiCadDriverPriority.LOCAL_LABEL,
               KiCadDriverKind.LOCAL_LABEL),
        _label("VCC", KiCadDriverPriority.GLOBAL,
               KiCadDriverKind.GLOBAL_LABEL),
    ])
    _resolve_driver(sg)
    assert sg.chosen_priority == KiCadDriverPriority.GLOBAL
    assert sg.chosen_kind == KiCadDriverKind.GLOBAL_LABEL
    assert sg.chosen_name == "VCC"


def test_resolve_label_outranks_pin():
    sg = _make_subgraph(
        labels=[_label("SIG", KiCadDriverPriority.LOCAL_LABEL,
                       KiCadDriverKind.LOCAL_LABEL)],
        pins=[_pin_drv("R1", "1")],
    )
    _resolve_driver(sg)
    assert sg.chosen_priority == KiCadDriverPriority.LOCAL_LABEL
    assert sg.chosen_name == "SIG"


def test_resolve_alphabetical_tiebreak_within_priority():
    """Same priority — alphabetical on display name wins."""
    sg = _make_subgraph(labels=[
        _label("ZULU", KiCadDriverPriority.LOCAL_LABEL,
               KiCadDriverKind.LOCAL_LABEL),
        _label("ALPHA", KiCadDriverPriority.LOCAL_LABEL,
               KiCadDriverKind.LOCAL_LABEL),
        _label("MIKE", KiCadDriverPriority.LOCAL_LABEL,
               KiCadDriverKind.LOCAL_LABEL),
    ])
    _resolve_driver(sg)
    assert sg.chosen_name == "ALPHA"


def test_resolve_no_candidates_yields_none():
    sg = _make_subgraph()
    _resolve_driver(sg)
    assert sg.chosen_priority == KiCadDriverPriority.NONE
    assert sg.chosen_kind == KiCadDriverKind.NONE
    assert sg.chosen_name == ""


def test_resolve_global_power_pin_uses_value():
    """Power-symbol pin candidate uses ``power_value`` as display name."""
    sg = _make_subgraph(pins=[
        _pin_drv("#PWR01", "1",
                 priority=KiCadDriverPriority.GLOBAL_POWER_PIN,
                 is_power=True, power_value="GND"),
    ])
    _resolve_driver(sg)
    assert sg.chosen_priority == KiCadDriverPriority.GLOBAL_POWER_PIN
    assert sg.chosen_kind == KiCadDriverKind.GLOBAL_POWER_PIN
    assert sg.chosen_name == "GND"


# ---------------------------------------------------------------------------
# name_net — formatting rules
# ---------------------------------------------------------------------------


def test_name_net_global_label_emits_bare():
    # kicad-cli's netlist exporter emits global-label net names without
    # any sheet-path prefix (parity with power-symbol value names) — the
    # ``sheet_path`` argument is intentionally ignored for GLOBAL_LABEL.
    sg = Subgraph(chosen_priority=KiCadDriverPriority.GLOBAL,
                  chosen_kind=KiCadDriverKind.GLOBAL_LABEL,
                  chosen_name="VCC")
    name, auto = name_net(sg, sheet_path="/anything/")
    assert name == "VCC"
    assert auto is False


def test_name_net_global_power_pin_bare():
    sg = Subgraph(chosen_priority=KiCadDriverPriority.GLOBAL_POWER_PIN,
                  chosen_kind=KiCadDriverKind.GLOBAL_POWER_PIN,
                  chosen_name="GND")
    name, auto = name_net(sg, sheet_path="/sub/")
    assert name == "GND"
    assert auto is False


def test_name_net_local_power_pin_bare():
    sg = Subgraph(chosen_priority=KiCadDriverPriority.LOCAL_POWER_PIN,
                  chosen_kind=KiCadDriverKind.LOCAL_POWER_PIN,
                  chosen_name="VLOCAL")
    name, _ = name_net(sg)
    assert name == "VLOCAL"


def test_name_net_local_label_prefixes_sheet_path():
    sg = Subgraph(chosen_priority=KiCadDriverPriority.LOCAL_LABEL,
                  chosen_kind=KiCadDriverKind.LOCAL_LABEL,
                  chosen_name="SIG")
    name, auto = name_net(sg, sheet_path="/sub/")
    assert name == "/sub/SIG"
    assert auto is False


def test_name_net_local_label_root_sheet():
    sg = Subgraph(chosen_priority=KiCadDriverPriority.LOCAL_LABEL,
                  chosen_kind=KiCadDriverKind.LOCAL_LABEL,
                  chosen_name="DATA")
    name, _ = name_net(sg, sheet_path="/")
    assert name == "/DATA"


def test_name_net_hier_label_prefixes_sheet_path():
    sg = Subgraph(chosen_priority=KiCadDriverPriority.HIER_LABEL,
                  chosen_kind=KiCadDriverKind.HIER_LABEL,
                  chosen_name="CLK")
    name, _ = name_net(sg, sheet_path="/sub/")
    assert name == "/sub/CLK"


def test_name_net_sheet_pin_prefixes_sheet_path():
    sg = Subgraph(chosen_priority=KiCadDriverPriority.SHEET_PIN,
                  chosen_kind=KiCadDriverKind.SHEET_PIN,
                  chosen_name="OUT")
    name, _ = name_net(sg, sheet_path="/parent/")
    assert name == "/parent/OUT"


def test_name_net_sheet_path_normalised_to_trailing_slash():
    """Caller may forget the trailing slash; we add it."""
    sg = Subgraph(chosen_priority=KiCadDriverPriority.LOCAL_LABEL,
                  chosen_kind=KiCadDriverKind.LOCAL_LABEL,
                  chosen_name="X")
    name, _ = name_net(sg, sheet_path="/sub")
    assert name == "/sub/X"


def test_compile_duplicate_sheet_pin_names_get_kicad_suffixes():
    sch = _empty_sch()
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.append(libR)
    sch.symbols.append(_placed("Device:R", reference="R1", at_x=10.0, at_y=10.0))
    sch.symbols.append(_placed("Device:R", reference="R2", at_x=20.0, at_y=10.0))
    sch.sheets.append(_sheet("s1", "child1", "missing.kicad_sch",
                             _sheet_pin("OUT", 10.0, 10.0)))
    sch.sheets.append(_sheet("s2", "child2", "missing.kicad_sch",
                             _sheet_pin("OUT", 20.0, 10.0)))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    by_name = {
        net.name: sorted((t.designator, t.pin) for t in net.terminals)
        for net in nl.nets
    }
    assert by_name["/OUT"] == [("R1", "1")]
    assert by_name["/OUT_1"] == [("R2", "1")]


def test_compile_sheet_entry_graphical_uses_sheet_pin_svg_group_id():
    sch = _empty_sch()
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.append(libR)
    sch.symbols.append(_placed("Device:R", reference="R1", at_x=10.0, at_y=10.0))
    sch.sheets.append(
        _sheet(
            "sheet-uuid",
            "child",
            "child.kicad_sch",
            SchSheetPin(
                name="OUT",
                shape=LabelShape.OUTPUT,
                at_x=10.0,
                at_y=10.0,
                uuid="sheet-pin-uuid",
            ),
        )
    )

    nl = compile_sheet_netlist(sch, sheet_path="/")

    assert len(nl.nets) == 1
    net = nl.nets[0]
    assert net.graphical["sheet_entries"] == ["sheet-pin-uuid"]
    endpoint = next(item for item in net.endpoints if item.role == "sheet_entry")
    assert endpoint.element_id == "sheet-pin-uuid"
    assert endpoint.object_id == "sheet-pin-uuid"


def test_compile_terminal_uses_visible_pin_svg_group_id():
    sch = _empty_sch()
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sym = _placed("Device:R", reference="R1", at_x=10.0, at_y=10.0)
    sym.uuid = "symbol-uuid"
    sym.pins = [SchSymbolPin(number="1", uuid="pin-uuid")]
    sch.lib_symbols.append(libR)
    sch.symbols.append(sym)

    nl = compile_sheet_netlist(sch, sheet_path="/")

    assert len(nl.nets) == 1
    term = nl.nets[0].terminals[0]
    assert term.designator == "R1"
    assert term.pin == "1"
    assert term.source_pin_id == "pin-uuid"
    assert term.svg_id == "pin-uuid"


def test_compile_hidden_pin_terminal_falls_back_to_symbol_svg_id():
    sch = _empty_sch()
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1", hide=True))
    sym = _placed("Device:R", reference="R1", at_x=10.0, at_y=10.0)
    sym.uuid = "symbol-uuid"
    sym.pins = [SchSymbolPin(number="1", uuid="pin-uuid")]
    sch.lib_symbols.append(libR)
    sch.symbols.append(sym)

    nl = compile_sheet_netlist(sch, sheet_path="/")

    term = nl.nets[0].terminals[0]
    assert term.source_pin_id == "pin-uuid"
    assert term.svg_id == "symbol-uuid"


def test_name_net_no_driver_uses_alphabetical_pin():
    """When no driver — auto-name from first pin (sorted designator+pin).

    ``_pin_drv`` builds drivers with ``pin_name=""`` so the suffix
    follows KiCad's ``SCH_PIN::GetDefaultNetName`` Pad-prefix rule
    (empty pin name ⇒ ``Pad<number>``). Multi-pin subgraph → ``Net-(``
    prefix.
    """
    sg = Subgraph(
        chosen_priority=KiCadDriverPriority.NONE,
        chosen_kind=KiCadDriverKind.NONE,
        chosen_name="",
        pin_drivers=[
            _pin_drv("R5", "2"),
            _pin_drv("R1", "3"),
            _pin_drv("R1", "1"),
        ],
    )
    name, auto = name_net(sg)
    assert name == "Net-(R1-Pad1)"
    assert auto is True


# ---------------------------------------------------------------------------
# compile_sheet_subgraphs — end-to-end on synthetic schematics
# ---------------------------------------------------------------------------


def test_name_net_blank_pin_number_sentinel_omits_pad_number():
    """KiCad treats library pin number ``"~"`` as blank in netlist output."""
    sg = Subgraph(
        chosen_priority=KiCadDriverPriority.NONE,
        chosen_kind=KiCadDriverKind.NONE,
        chosen_name="",
        pin_drivers=[
            _PinDriver(
                designator="HOLE1",
                pin_number="~",
                pin_name="1",
                pin_type="passive+no_connect",
                coord=(0, 0),
                priority=KiCadDriverPriority.PIN,
                is_power=False,
            ),
        ],
    )
    name, auto = name_net(sg)
    assert name == "unconnected-(HOLE1-1-Pad)"
    assert auto is True


def test_compile_uses_kicad9_lib_name_for_local_symbol_lookup():
    sch = _empty_sch()
    lib_osc = _libsym("OSC_LOCAL_1", _pin(0.0, 0.0, number="3", name="OUTPUT"))
    lib_r = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.extend([lib_osc, lib_r])

    osc = _placed("vendor:OSC_LOCAL", reference="U1", at_x=10.0, at_y=10.0)
    osc.lib_name = "OSC_LOCAL_1"
    sch.symbols.append(osc)
    sch.symbols.append(_placed("Device:R", reference="R1", at_x=10.0, at_y=10.0))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    net = nl.get_net("Net-(U1-OUTPUT)")
    assert net is not None, [n.name for n in nl.nets]
    assert sorted((t.designator, t.pin) for t in net.terminals) == [
        ("R1", "1"),
        ("U1", "3"),
    ]


def _two_resistors_with_wire() -> KiCadSchematic:
    """Two passive symbols, pin-1 of each on the same horizontal wire.

    Layout (Y-down): ``R1@(10,10), pin1`` ─wire─ ``R2@(50,10), pin1``.
    Both resistors expose pin "1" at the placement origin (length=0).
    """
    sch = _empty_sch()

    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"),
                   _pin(0.0, -2.54, number="2"))
    sch.lib_symbols.append(libR)
    sch.symbols.append(_placed("Device:R", reference="R1", value="10k",
                               at_x=10.0, at_y=10.0))
    sch.symbols.append(_placed("Device:R", reference="R2", value="10k",
                               at_x=50.0, at_y=10.0))
    sch.wires.append(_wire((10.0, 10.0), (50.0, 10.0)))
    return sch


def test_compile_two_pins_on_wire_form_one_subgraph():
    sch = _two_resistors_with_wire()
    sgs = compile_sheet_subgraphs(sch, sheet_path="/")
    # One driver-bearing subgraph (the wire-connected pin1s) plus
    # potentially one per dangling pin2. Filter to the ones with > 1 pin.
    multi_pin_sgs = [s for s in sgs if len(s.pin_drivers) >= 2]
    assert len(multi_pin_sgs) == 1
    sg = multi_pin_sgs[0]
    refs = sorted({pd.designator for pd in sg.pin_drivers})
    assert refs == ["R1", "R2"]


def test_wire_endpoint_landing_mid_segment_without_junction_stays_separate():
    sch = _empty_sch()
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.append(libR)
    sch.symbols.append(_placed("Device:R", reference="R1", at_x=0.0, at_y=0.0))
    sch.symbols.append(_placed("Device:R", reference="R2", at_x=5.0, at_y=5.0))
    sch.wires.append(_wire((0.0, 0.0), (10.0, 0.0)))
    sch.wires.append(_wire((5.0, 0.0), (5.0, 5.0)))

    sgs = compile_sheet_subgraphs(sch, sheet_path="/")
    multi_pin_sgs = [s for s in sgs if len(s.pin_drivers) >= 2]
    assert multi_pin_sgs == []


def test_junction_landing_mid_segment_forms_t_connection():
    sch = _empty_sch()
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.append(libR)
    sch.symbols.append(_placed("Device:R", reference="R1", at_x=0.0, at_y=0.0))
    sch.symbols.append(_placed("Device:R", reference="R2", at_x=5.0, at_y=5.0))
    sch.wires.append(_wire((0.0, 0.0), (10.0, 0.0)))
    sch.wires.append(_wire((5.0, 0.0), (5.0, 5.0)))
    sch.junctions.append(SchJunction(at_x=5.0, at_y=0.0))

    sgs = compile_sheet_subgraphs(sch, sheet_path="/")
    multi_pin_sgs = [s for s in sgs if len(s.pin_drivers) >= 2]
    assert len(multi_pin_sgs) == 1
    refs = sorted({pd.designator for pd in multi_pin_sgs[0].pin_drivers})
    assert refs == ["R1", "R2"]


def test_compile_local_label_overrides_pin_auto_name():
    sch = _two_resistors_with_wire()
    sch.labels.append(SchLabel(text="SIG", at_x=30.0, at_y=10.0))
    nl = compile_sheet_netlist(sch, sheet_path="/")
    sig = nl.get_net("/SIG")
    assert sig is not None, [n.name for n in nl.nets]
    refs = sorted({t.designator for t in sig.terminals})
    assert refs == ["R1", "R2"]
    assert sig.driver_priority == int(KiCadDriverPriority.LOCAL_LABEL)


def test_compile_global_label_outranks_local_label():
    sch = _two_resistors_with_wire()
    sch.labels.append(SchLabel(text="LOCAL", at_x=20.0, at_y=10.0))
    sch.global_labels.append(SchGlobalLabel(text="GLOBAL", at_x=40.0, at_y=10.0))
    nl = compile_sheet_netlist(sch, sheet_path="/")
    # Global label wins — emitted bare (no sheet-path prefix).
    assert nl.get_net("GLOBAL") is not None
    # The local label is shadowed (same subgraph, lower priority).
    assert nl.get_net("/LOCAL") is None


def test_compile_global_power_pin_yields_bare_net_name():
    sch = _empty_sch()
    libGND = _libsym(
        "power:GND",
        _pin(0.0, 0.0, number="1", electrical=PinElectricalType.POWER_IN),
        power=True, power_kind="global",
    )
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.extend([libGND, libR])
    # Power symbol value carries the net name.
    power = _placed("power:GND", reference="#PWR01", value="GND",
                    at_x=10.0, at_y=10.0)
    power.uuid = "power-symbol-uuid"
    power.pins = [SchSymbolPin(number="1", uuid="power-pin-uuid")]
    sch.symbols.append(power)
    sch.symbols.append(_placed("Device:R", reference="R1", value="10k",
                               at_x=10.0, at_y=10.0))
    nl = compile_sheet_netlist(sch, sheet_path="/")
    gnd = nl.get_net("GND")
    assert gnd is not None
    refs = sorted({t.designator for t in gnd.terminals})
    assert "R1" in refs
    assert gnd.driver_priority == int(KiCadDriverPriority.GLOBAL_POWER_PIN)
    assert [
        (
            endpoint.endpoint_id,
            endpoint.role,
            endpoint.element_id,
            endpoint.object_id,
            endpoint.name,
            endpoint.connection_point,
        )
        for endpoint in gnd.endpoints
    ] == [
        (
            "power_port:power-pin-uuid",
            "power_port",
            "power-symbol-uuid",
            "power-pin-uuid",
            "GND",
            (100000, 100000),
        )
    ]


def test_compile_hidden_power_pin_names_net_when_no_explicit_power_symbol():
    sch = _empty_sch()
    libU = _libsym(
        "Test:HiddenPower",
        _pin(
            0.0, 0.0,
            number="1",
            electrical=PinElectricalType.POWER_IN,
            name="VCC",
            hide=True,
        ),
    )
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.extend([libU, libR])
    sch.symbols.append(_placed("Test:HiddenPower", reference="U1", at_x=0.0, at_y=0.0))
    sch.symbols.append(_placed("Device:R", reference="R1", at_x=0.0, at_y=0.0))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    vcc = nl.get_net("VCC")
    assert vcc is not None, [n.name for n in nl.nets]
    assert sorted((t.designator, t.pin) for t in vcc.terminals) == [
        ("R1", "1"),
        ("U1", "1"),
    ]


def test_compile_explicit_power_symbol_names_net_over_hidden_power_pin():
    sch = _empty_sch()
    libGND = _libsym(
        "power:GND",
        _pin(0.0, 0.0, number="1", electrical=PinElectricalType.POWER_IN),
        power=True,
        power_kind="global",
    )
    libJ = _libsym(
        "Test:Shield",
        _pin(
            0.0, 0.0,
            number="1",
            electrical=PinElectricalType.POWER_IN,
            name="D1S",
            hide=True,
        ),
        _pin(0.0, 0.0, number="2", electrical=PinElectricalType.PASSIVE, name="GND"),
    )
    sch.lib_symbols.extend([libGND, libJ])
    sch.symbols.append(_placed("power:GND", reference="#PWR01", value="GND"))
    sch.symbols.append(_placed("Test:Shield", reference="J1"))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    gnd = nl.get_net("GND")
    assert gnd is not None, [n.name for n in nl.nets]
    assert nl.get_net("D1S") is None
    assert sorted((t.designator, t.pin) for t in gnd.terminals) == [
        ("#PWR01", "1"),
        ("J1", "1"),
        ("J1", "2"),
    ]


def test_compile_same_sheet_local_label_merges_with_power_value():
    sch = _empty_sch()
    libGND = _libsym(
        "power:GND",
        _pin(0.0, 0.0, number="1", electrical=PinElectricalType.POWER_IN),
        power=True, power_kind="global",
    )
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.extend([libGND, libR])
    sch.symbols.append(_placed("power:GND", reference="#PWR01", value="GND",
                               at_x=0.0, at_y=0.0))
    sch.symbols.append(_placed("Device:R", reference="R1", value="10k",
                               at_x=10.0, at_y=10.0))
    sch.labels.append(SchLabel(text="GND", at_x=10.0, at_y=10.0))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    gnd = nl.get_net("GND")
    assert gnd is not None, [n.name for n in nl.nets]
    assert ("R1", "1") in {(t.designator, t.pin) for t in gnd.terminals}
    assert nl.get_net("/GND") is None


def test_compile_duplicate_pin_numbers_are_jumpers_union_internal_pins():
    sch = _empty_sch()
    libPWR = _libsym(
        "power:+2V5",
        _pin(0.0, 0.0, number="1", electrical=PinElectricalType.POWER_IN),
        power=True, power_kind="global",
    )
    libTB = _libsym(
        "Test:TB",
        _pin(0.0, 0.0, number="1"),
        _pin(10.0, 0.0, number="1"),
    )
    libTB.duplicate_pin_numbers_are_jumpers = True
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.extend([libPWR, libTB, libR])
    sch.symbols.append(_placed("power:+2V5", reference="#PWR01",
                               value="+2V5", at_x=0.0, at_y=0.0))
    sch.symbols.append(_placed("Test:TB", reference="TB1",
                               at_x=0.0, at_y=0.0))
    sch.symbols.append(_placed("Device:R", reference="R1",
                               at_x=10.0, at_y=0.0))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    net = nl.get_net("+2V5")
    assert net is not None, [n.name for n in nl.nets]
    terms = sorted({
        (t.designator, t.pin)
        for t in net.terminals
        if not t.designator.startswith("#")
    })
    assert terms == [
        ("R1", "1"),
        ("TB1", "1"),
    ]
    assert nl.get_net("Net-(R1-Pad1)") is None


def test_compile_jumper_pin_groups_union_internal_pins():
    sch = _empty_sch()
    libPWR = _libsym(
        "power:+3.3V",
        _pin(0.0, 0.0, number="1", electrical=PinElectricalType.POWER_IN),
        power=True, power_kind="global",
    )
    libU = _libsym(
        "Test:Matrix",
        _pin(0.0, 0.0, number="1", electrical=PinElectricalType.INPUT, name=""),
        _pin(10.0, 0.0, number="3", electrical=PinElectricalType.INPUT, name=""),
    )
    libU.jumper_pin_groups = [["1", "3"]]
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.extend([libPWR, libU, libR])
    sch.symbols.append(_placed("power:+3.3V", reference="#PWR01",
                               value="+3.3V", at_x=0.0, at_y=0.0))
    sch.symbols.append(_placed("Test:Matrix", reference="U1",
                               at_x=0.0, at_y=0.0))
    sch.symbols.append(_placed("Device:R", reference="R1",
                               at_x=10.0, at_y=0.0))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    net = nl.get_net("+3.3V")
    assert net is not None, [n.name for n in nl.nets]
    terms = sorted({
        (t.designator, t.pin)
        for t in net.terminals
        if not t.designator.startswith("#")
    })
    assert terms == [
        ("R1", "1"),
        ("U1", "1"),
        ("U1", "3"),
    ]
    assert nl.get_net("Net-(R1-Pad1)") is None


def test_compile_isolated_pin_gets_auto_name():
    """A single pin with no wire and no label → ``unconnected-(R1-Pad1)``
    placeholder.

    KiCad emits these too — every component pin lands on *some* net.
    The ``unconnected-(`` prefix matches KiCad's
    ``SCH_PIN::GetDefaultNetName`` for truly isolated single-pin nets;
    the ``Pad`` suffix prefix is used because the lib pin's name
    (``~``) is the empty/placeholder convention.
    """
    sch = _empty_sch()
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.append(libR)
    sch.symbols.append(_placed("Device:R", reference="R1",
                               at_x=10.0, at_y=10.0))
    nl = compile_sheet_netlist(sch, sheet_path="/")
    auto = nl.get_net("unconnected-(R1-Pad1)")
    assert auto is not None
    assert auto.auto_named is True
    assert len(auto.terminals) == 1
    assert auto.terminals[0].designator == "R1"
    assert auto.terminals[0].pin == "1"


def test_compile_isolated_one_pin_bidirectional_symbol_gets_unconnected_auto_name():
    sch = _empty_sch()
    libU = _libsym(
        "Test:Bidi",
        _pin(
            0.0, 0.0,
            number="1",
            name="VREF",
            electrical=PinElectricalType.BIDIRECTIONAL,
        ),
    )
    sch.lib_symbols.append(libU)
    sch.symbols.append(_placed("Test:Bidi", reference="U1", at_x=10.0, at_y=10.0))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    auto = nl.get_net("unconnected-(U1-VREF-Pad1)")
    assert auto is not None
    assert auto.auto_named is True
    assert [(t.designator, t.pin) for t in auto.terminals] == [("U1", "1")]
    assert nl.get_net("Net-(U1-VREF)") is None


def test_compile_isolated_named_bidirectional_pin_on_multi_pin_symbol_gets_normal_auto_name():
    sch = _empty_sch()
    libU = _libsym(
        "Test:BidiPair",
        _pin(
            0.0, 0.0,
            number="1",
            name="VREF",
            electrical=PinElectricalType.BIDIRECTIONAL,
        ),
        _pin(
            5.0, 0.0,
            number="2",
            name="IO",
            electrical=PinElectricalType.BIDIRECTIONAL,
        ),
    )
    sch.lib_symbols.append(libU)
    sch.symbols.append(_placed("Test:BidiPair", reference="U1", at_x=10.0, at_y=10.0))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    auto = nl.get_net("Net-(U1-VREF)")
    assert auto is not None
    assert auto.auto_named is True
    assert [(t.designator, t.pin) for t in auto.terminals] == [("U1", "1")]
    assert nl.get_net("unconnected-(U1-VREF-Pad1)") is None


def test_compile_hidden_no_connect_pins_at_same_coord_stay_separate():
    sch = _empty_sch()
    libU = _libsym(
        "Test:BGA",
        _pin(
            0.0, 0.0,
            number="A1",
            electrical=PinElectricalType.NO_CONNECT,
            name="NC",
            hide=True,
        ),
        _pin(
            0.0, 0.0,
            number="A2",
            electrical=PinElectricalType.NO_CONNECT,
            name="NC",
            hide=True,
        ),
    )
    sch.lib_symbols.append(libU)
    sch.symbols.append(_placed("Test:BGA", reference="U1", at_x=10.0, at_y=10.0))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    by_name = {
        net.name: sorted((t.designator, t.pin) for t in net.terminals)
        for net in nl.nets
    }
    assert by_name["unconnected-(U1-NC-PadA1)"] == [("U1", "A1")]
    assert by_name["unconnected-(U1-NC-PadA2)"] == [("U1", "A2")]


def test_compile_offboard_symbols_do_not_emit_net_terminals():
    sch = _empty_sch()
    libR = _libsym("Device:R", _pin(0.0, 0.0, number="1"))
    sch.lib_symbols.append(libR)
    offboard = _placed("Device:R", reference="R1", at_x=0.0, at_y=0.0)
    offboard.on_board = False
    sch.symbols.append(offboard)
    sch.symbols.append(_placed("Device:R", reference="R2", at_x=10.0, at_y=0.0))
    sch.wires.append(_wire((0.0, 0.0), (10.0, 0.0)))
    sch.labels.append(SchLabel(text="SIG", at_x=5.0, at_y=0.0))

    nl = compile_sheet_netlist(sch, sheet_path="/")
    sig = nl.get_net("/SIG")
    assert sig is not None, [n.name for n in nl.nets]
    assert sorted((t.designator, t.pin) for t in sig.terminals) == [("R2", "1")]


def test_compile_floating_wire_stub_dropped():
    """A wire with no pins on its endpoints is a stub — kicad-cli skips."""
    sch = _empty_sch()
    sch.wires.append(_wire((0.0, 0.0), (10.0, 0.0)))
    nl = compile_sheet_netlist(sch, sheet_path="/")
    assert nl.nets == []


def test_compile_hier_label_named_with_sheet_path():
    sch = _two_resistors_with_wire()
    sch.hierarchical_labels.append(
        SchHierarchicalLabel(text="CLK", at_x=30.0, at_y=10.0))
    nl = compile_sheet_netlist(sch, sheet_path="/sub/")
    clk = nl.get_net("/sub/CLK")
    assert clk is not None
    assert clk.driver_priority == int(KiCadDriverPriority.HIER_LABEL)


def test_compile_terminals_sorted_by_ref_then_pin():
    """Terminals on a net come out sorted by (designator, pin_number)."""
    sch = _empty_sch()
    libR = _libsym("Device:R",
                   _pin(0.0, 0.0, number="1"),
                   _pin(0.0, -2.54, number="2"))
    sch.lib_symbols.append(libR)
    # Three resistors all on a common wire — pin1 of each.
    for ref, x in [("R3", 30.0), ("R1", 10.0), ("R2", 20.0)]:
        sch.symbols.append(_placed("Device:R", reference=ref,
                                   at_x=x, at_y=0.0))
    sch.wires.append(_wire((10.0, 0.0), (30.0, 0.0)))
    sch.labels.append(SchLabel(text="BUS", at_x=20.0, at_y=0.0))
    nl = compile_sheet_netlist(sch, sheet_path="/")
    bus = nl.get_net("/BUS")
    assert bus is not None
    refs = [t.designator for t in bus.terminals]
    assert refs == ["R1", "R2", "R3"]


def test_compile_assigns_sequential_codes_starting_at_offset():
    sch = _two_resistors_with_wire()
    nl = compile_sheet_netlist(sch, sheet_path="/", code_offset=42)
    codes = sorted(n.code for n in nl.nets)
    # Codes are sequential starting at 42 — exact count depends on subgraph
    # discovery, but every net must have a code >= 42 and they're contiguous.
    assert codes[0] == 42
    assert codes == list(range(codes[0], codes[0] + len(codes)))


# ---------------------------------------------------------------------------
# Net + Terminal model — basic shape checks
# ---------------------------------------------------------------------------


def test_kicadnet_get_net_by_name_or_alias():
    nl = KiCadNetlist()
    nl.nets.append(KiCadNet(name="VCC", code=1, aliases=["+5V"]))
    assert nl.get_net("VCC") is nl.nets[0]
    assert nl.get_net("+5V") is nl.nets[0]
    assert nl.get_net("nope") is None


def test_kicadnet_terminal_normalises_strings():
    """Designator / pin are coerced to ``str`` in :meth:`__post_init__`."""
    t = KiCadNetlistTerminal(designator=1, pin=2)  # type: ignore[arg-type]
    assert t.designator == "1"
    assert t.pin == "2"
