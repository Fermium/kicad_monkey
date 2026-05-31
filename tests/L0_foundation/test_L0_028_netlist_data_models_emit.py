"""L0 foundation tests — Phase G Slice N-6.

Covers ``kicad_netlist_to_data_models_netlist``: the bridge from the
internal :class:`KiCadNetlist` model into the cross-CAD ``netlist_a0``
shape exposed by the ``data_models`` package.

Tests use hand-crafted :class:`KiCadNetlist` fixtures so they don't
depend on schematic parsing — the bridge is a pure structural
transform.
"""

from __future__ import annotations

import pytest

from data_models import (
    DesignComponent,
    DesignComponentPin,
    DesignNet,
    DesignNetConnection,
    Netlist,
)

from kicad_monkey import (
    KiCadDesignMetadata,
    KiCadDesignSheet,
    KiCadLibPart,
    KiCadLibPartPin,
    KiCadNet,
    KiCadNetlist,
    KiCadNetlistComponent,
    KiCadNetlistTerminal,
    kicad_netlist_to_data_models_netlist,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _comp(reference: str, **kw) -> KiCadNetlistComponent:
    base = dict(
        value="",
        footprint="",
        libsource_lib="",
        libsource_part="",
        libsource_description="",
        sheet_path_names="/",
        sheet_path_uuids="/",
        instance_uuid="",
        properties={},
    )
    base.update(kw)
    return KiCadNetlistComponent(reference=reference, **base)


def _term(designator: str, pin: str, *, pin_name: str = "", pin_type: str = "") -> KiCadNetlistTerminal:
    return KiCadNetlistTerminal(
        designator=designator,
        pin=pin,
        pin_name=pin_name,
        pin_type=pin_type,
    )


def _libpart_R() -> KiCadLibPart:  # noqa: N802 — match KiCad style
    return KiCadLibPart(
        lib="Device",
        part="R",
        description="Resistor",
        pins=[
            KiCadLibPartPin(number="1", name="~", pin_type="passive"),
            KiCadLibPartPin(number="2", name="~", pin_type="passive"),
        ],
    )


# ---------------------------------------------------------------------------
# Top-level shape
# ---------------------------------------------------------------------------


def test_returns_data_models_netlist_instance():
    nl = KiCadNetlist()
    out = kicad_netlist_to_data_models_netlist(nl)
    assert isinstance(out, Netlist)
    assert out.schema == "wn.netlist.a0"
    assert out.type == "netlist_a0"


def test_empty_netlist_round_trips_through_json():
    nl = KiCadNetlist()
    out = kicad_netlist_to_data_models_netlist(nl)
    raw = out.to_json()
    restored = Netlist.from_json(raw)
    assert restored.components == []
    assert restored.nets == []
    assert restored.metadata.get("sheets") == []


def test_source_block_marks_kicad_origin():
    nl = KiCadNetlist(
        design_metadata=KiCadDesignMetadata(
            source="/abs/design.kicad_sch",
            date="Mon 10 May 2026 06:30:00 PM",
            tool="kicad_monkey",
        )
    )
    out = kicad_netlist_to_data_models_netlist(nl)
    assert out.source["cad"] == "kicad"
    assert out.source["tool"] == "kicad_monkey"
    assert out.source["date"] == "Mon 10 May 2026 06:30:00 PM"
    assert out.source["source_path"] == "/abs/design.kicad_sch"


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


def test_component_designator_value_footprint():
    comp = _comp(
        "R1",
        value="10k",
        footprint="Resistor_SMD:R_0402_1005Metric",
        libsource_lib="Device",
        libsource_part="R",
        libsource_description="Resistor",
        instance_uuid="abc-123",
    )
    nl = KiCadNetlist(components=[comp])
    out = kicad_netlist_to_data_models_netlist(nl)
    assert len(out.components) == 1
    dc = out.components[0]
    assert isinstance(dc, DesignComponent)
    assert dc.designator == "R1"
    assert dc.value == "10k"
    assert dc.footprint == "Resistor_SMD:R_0402_1005Metric"
    assert dc.description == "Resistor"
    assert dc.uid == "abc-123"


def test_component_parameters_carry_kicad_namespace():
    comp = _comp(
        "C1",
        value="100n",
        libsource_lib="Device",
        libsource_part="C",
        sheet_path_names="/sub/",
        sheet_path_uuids="/u1/u2/",
        instance_uuid="uuid-c1",
        in_bom=True,
        on_board=False,
        dnp=True,
        properties={"MPN": "GRM155R71H104KE14D"},
    )
    out = kicad_netlist_to_data_models_netlist(KiCadNetlist(components=[comp]))
    dc = out.components[0]
    p = dc.parameters
    assert p["_source_cad"] == "kicad"
    assert p["kicad_libsource_lib"] == "Device"
    assert p["kicad_libsource_part"] == "C"
    assert p["kicad_sheet_path_names"] == "/sub/"
    assert p["kicad_sheet_path_uuids"] == "/u1/u2/"
    assert p["kicad_instance_uuid"] == "uuid-c1"
    assert p["kicad_in_bom"] == "true"
    assert p["kicad_on_board"] == "false"
    assert p["kicad_dnp"] == "true"
    # Custom property carries through.
    assert p["MPN"] == "GRM155R71H104KE14D"


def test_component_pins_attached_from_libpart_with_resolved_nets():
    comp = _comp(
        "R1",
        value="10k",
        libsource_lib="Device",
        libsource_part="R",
    )
    nl = KiCadNetlist(
        components=[comp],
        libparts=[_libpart_R()],
        nets=[
            KiCadNet(name="VCC", code=1, terminals=[_term("R1", "1", pin_name="~")]),
            KiCadNet(name="GND", code=2, terminals=[_term("R1", "2", pin_name="~")]),
        ],
    )
    out = kicad_netlist_to_data_models_netlist(nl)
    dc = out.components[0]
    assert len(dc.pins) == 2
    by_num = {pin.number: pin for pin in dc.pins}
    assert by_num["1"].net == "VCC"
    assert by_num["1"].name == "~"
    assert by_num["2"].net == "GND"
    assert isinstance(by_num["1"], DesignComponentPin)


def test_component_pin_net_empty_when_unconnected():
    comp = _comp(
        "R1",
        libsource_lib="Device",
        libsource_part="R",
    )
    nl = KiCadNetlist(components=[comp], libparts=[_libpart_R()])
    out = kicad_netlist_to_data_models_netlist(nl)
    assert all(pin.net == "" for pin in out.components[0].pins)


def test_component_without_matching_libpart_emits_no_pins():
    comp = _comp("U1", libsource_lib="MCU_ST_STM32F0", libsource_part="STM32F042F4Px")
    out = kicad_netlist_to_data_models_netlist(KiCadNetlist(components=[comp]))
    assert out.components[0].pins == []


# ---------------------------------------------------------------------------
# Nets
# ---------------------------------------------------------------------------


def test_nets_become_design_nets_with_connections():
    nl = KiCadNetlist(
        nets=[
            KiCadNet(
                name="SDA",
                code=1,
                terminals=[
                    _term("U1", "1", pin_name="SDA", pin_type="bidirectional"),
                    _term("R1", "1"),
                ],
            ),
        ],
    )
    out = kicad_netlist_to_data_models_netlist(nl)
    assert len(out.nets) == 1
    dn = out.nets[0]
    assert isinstance(dn, DesignNet)
    assert dn.name == "SDA"
    assert dn.aliases == []
    assert len(dn.connections) == 2
    assert isinstance(dn.connections[0], DesignNetConnection)
    assert dn.connections[0].designator == "U1"
    assert dn.connections[0].pin == "1"
    assert dn.connections[0].pin_name == "SDA"
    assert dn.connections[1].designator == "R1"
    assert dn.connections[1].pin == "1"


def test_nets_preserve_aliases_when_set():
    net = KiCadNet(name="DATA[0]", code=1)
    # Aliases are an optional attribute on KiCadNet — set if present.
    if hasattr(net, "aliases"):
        net.aliases = ["BUS_DATA0"]
    out = kicad_netlist_to_data_models_netlist(KiCadNetlist(nets=[net]))
    if hasattr(net, "aliases"):
        assert out.nets[0].aliases == ["BUS_DATA0"]


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_metadata_carries_sheets():
    sheets = [
        KiCadDesignSheet(number=1, name="/", tstamps="/abc/", title="Top",
                         company="ACME", revision="A", date="2026-01-01"),
        KiCadDesignSheet(number=2, name="/sub/", tstamps="/abc/def/"),
    ]
    nl = KiCadNetlist(design_metadata=KiCadDesignMetadata(sheets=sheets))
    out = kicad_netlist_to_data_models_netlist(nl)
    md_sheets = out.metadata["sheets"]
    assert len(md_sheets) == 2
    assert md_sheets[0]["number"] == 1
    assert md_sheets[0]["title"] == "Top"
    assert md_sheets[0]["company"] == "ACME"
    assert md_sheets[0]["revision"] == "A"
    assert md_sheets[1]["name"] == "/sub/"
    assert md_sheets[1]["tstamps"] == "/abc/def/"


def test_metadata_includes_libraries_when_set():
    nl = KiCadNetlist(libraries=["Device", "MCU_ST"])
    out = kicad_netlist_to_data_models_netlist(nl)
    assert out.metadata["kicad_libraries"] == ["Device", "MCU_ST"]


def test_metadata_omits_libraries_when_empty():
    nl = KiCadNetlist(libraries=[])
    out = kicad_netlist_to_data_models_netlist(nl)
    assert "kicad_libraries" not in out.metadata


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_full_netlist_round_trips_through_json():
    nl = KiCadNetlist(
        components=[
            _comp(
                "R1",
                value="10k",
                footprint="Resistor_SMD:R_0402_1005Metric",
                libsource_lib="Device",
                libsource_part="R",
                libsource_description="Resistor",
                instance_uuid="r1-uuid",
                properties={"MPN": "PN-001"},
            ),
        ],
        libparts=[_libpart_R()],
        nets=[
            KiCadNet(name="VCC", code=1,
                     terminals=[_term("R1", "1", pin_name="~", pin_type="passive")]),
            KiCadNet(name="GND", code=2,
                     terminals=[_term("R1", "2", pin_name="~", pin_type="passive")]),
        ],
        design_metadata=KiCadDesignMetadata(
            source="/proj/board.kicad_sch",
            date="Mon 10 May 2026",
            tool="kicad_monkey",
            sheets=[KiCadDesignSheet(number=1, name="/", tstamps="/root/")],
        ),
    )
    out = kicad_netlist_to_data_models_netlist(nl)
    raw = out.to_json()
    restored = Netlist.from_json(raw)

    assert restored.source["cad"] == "kicad"
    assert restored.source["source_path"] == "/proj/board.kicad_sch"
    assert restored.metadata["sheets"][0]["tstamps"] == "/root/"

    assert len(restored.components) == 1
    rc = restored.components[0]
    assert rc.designator == "R1"
    assert rc.value == "10k"
    assert rc.uid == "r1-uuid"
    assert rc.parameters["MPN"] == "PN-001"
    assert rc.parameters["_source_cad"] == "kicad"

    by_num = {pin.number: pin for pin in rc.pins}
    assert by_num["1"].net == "VCC"
    assert by_num["2"].net == "GND"

    assert len(restored.nets) == 2
    assert restored.nets[0].connections[0].designator == "R1"
