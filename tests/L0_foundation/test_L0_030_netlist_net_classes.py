"""L0 tests for net-class assignment from .kicad_pro.

Validates :func:`apply_project_net_classes` plus KiCad-native JSON plumbing
for net-class membership.
"""

from __future__ import annotations

from kicad_monkey.kicad_netlist_model import (
    KiCadNet,
    KiCadNetClass,
    KiCadNetlist,
    KiCadNetlistComponent,
    KiCadNetlistTerminal,
)
from kicad_monkey.kicad_netlist_project import apply_project_net_classes
from kicad_monkey.kicad_design_json import kicad_netlist_to_json
from kicad_monkey.kicad_project import KiCadProject


def _net(name: str) -> KiCadNet:
    return KiCadNet(
        name=name,
        terminals=[KiCadNetlistTerminal(designator="R1", pin="1")],
    )


def _project_with_net_classes(raw_net_settings: dict) -> KiCadProject:
    """Build a KiCadProject from a minimal raw .kicad_pro shape."""
    raw = {"net_settings": raw_net_settings}
    return KiCadProject._from_raw(raw, project_path=None)


# ---------------------------------------------------------------------------
# apply_project_net_classes
# ---------------------------------------------------------------------------


def test_apply_with_no_project_is_noop():
    nl = KiCadNetlist(nets=[_net("VCC")])
    apply_project_net_classes(nl, None)
    assert nl.net_classes == []
    assert nl.nets[0].net_class == ""


def test_apply_synthesizes_default_class_when_project_omits_it():
    project = _project_with_net_classes({"classes": []})
    nl = KiCadNetlist(nets=[_net("VCC")])
    apply_project_net_classes(nl, project)
    assert [c.name for c in nl.net_classes] == ["Default"]
    assert nl.nets[0].net_class == "Default"


def test_apply_preserves_project_class_order():
    project = _project_with_net_classes({
        "classes": [
            {"name": "Default"},
            {"name": "Power"},
            {"name": "Diff"},
        ],
    })
    nl = KiCadNetlist(nets=[])
    apply_project_net_classes(nl, project)
    assert [c.name for c in nl.net_classes] == ["Default", "Power", "Diff"]


def test_apply_assigns_via_exact_assignment():
    project = _project_with_net_classes({
        "classes": [{"name": "Default"}, {"name": "Power"}],
        "netclass_assignments": {"VCC": ["Power"], "GND": ["Power"]},
    })
    nl = KiCadNetlist(nets=[_net("VCC"), _net("GND"), _net("SIG")])
    apply_project_net_classes(nl, project)
    by_name = {n.name: n.net_class for n in nl.nets}
    assert by_name == {"VCC": "Power", "GND": "Power", "SIG": "Default"}


def test_apply_assigns_via_wildcard_pattern():
    project = _project_with_net_classes({
        "classes": [{"name": "Default"}, {"name": "USB"}],
        "netclass_patterns": [
            {"pattern": "USB_*", "netclass": "USB"},
        ],
    })
    nl = KiCadNetlist(nets=[_net("USB_DP"), _net("USB_DN"), _net("VCC")])
    apply_project_net_classes(nl, project)
    by_name = {n.name: n.net_class for n in nl.nets}
    assert by_name == {"USB_DP": "USB", "USB_DN": "USB", "VCC": "Default"}


def test_apply_exact_assignment_wins_over_pattern():
    project = _project_with_net_classes({
        "classes": [{"name": "Default"}, {"name": "USB"}, {"name": "HSUSB"}],
        "netclass_assignments": {"USB_DP": ["HSUSB"]},
        "netclass_patterns": [
            {"pattern": "USB_*", "netclass": "USB"},
        ],
    })
    nl = KiCadNetlist(nets=[_net("USB_DP"), _net("USB_DN")])
    apply_project_net_classes(nl, project)
    by_name = {n.name: n.net_class for n in nl.nets}
    assert by_name == {"USB_DP": "HSUSB", "USB_DN": "USB"}


def test_apply_falls_back_to_default_when_referenced_class_missing():
    project = _project_with_net_classes({
        "classes": [{"name": "Default"}],  # no "Power" class declared
        "netclass_assignments": {"VCC": ["Power"]},
    })
    nl = KiCadNetlist(nets=[_net("VCC")])
    apply_project_net_classes(nl, project)
    assert nl.nets[0].net_class == "Default"


def test_apply_is_idempotent():
    project = _project_with_net_classes({
        "classes": [{"name": "Default"}, {"name": "Power"}],
        "netclass_assignments": {"VCC": ["Power"]},
    })
    nl = KiCadNetlist(nets=[_net("VCC")])
    apply_project_net_classes(nl, project)
    apply_project_net_classes(nl, project)
    assert [c.name for c in nl.net_classes] == ["Default", "Power"]
    assert nl.nets[0].net_class == "Power"


# ---------------------------------------------------------------------------
# KiCad-native JSON
# ---------------------------------------------------------------------------


def test_kicad_json_emits_net_classes_with_membership():
    nl = KiCadNetlist(
        nets=[_net("VCC"), _net("GND"), _net("SIG")],
        net_classes=[
            KiCadNetClass(name="Default"),
            KiCadNetClass(name="Power", description="rails"),
        ],
    )
    nl.nets[0].net_class = "Power"  # VCC
    nl.nets[1].net_class = "Power"  # GND
    nl.nets[2].net_class = "Default"

    out = kicad_netlist_to_json(nl)

    by_name = {row["name"]: row for row in out["net_classes"]}
    assert set(by_name) == {"Default", "Power"}
    assert sorted(by_name["Power"]["nets"]) == ["GND", "VCC"]
    assert by_name["Power"]["description"] == "rails"
    assert by_name["Default"]["nets"] == ["SIG"]


def test_kicad_json_assigns_net_class_on_each_net():
    nl = KiCadNetlist(
        nets=[_net("VCC")],
        net_classes=[KiCadNetClass(name="Power")],
    )
    nl.nets[0].net_class = "Power"

    out = kicad_netlist_to_json(nl)
    assert out["nets"][0]["net_class"] == "Power"


def test_kicad_json_payload_contains_component_and_net_class_sections():
    nl = KiCadNetlist(
        components=[KiCadNetlistComponent(reference="R1", value="10k")],
        nets=[_net("VCC")],
        net_classes=[KiCadNetClass(name="Default"), KiCadNetClass(name="Power")],
    )
    nl.nets[0].net_class = "Power"

    payload = kicad_netlist_to_json(nl)
    by_name = {row["name"]: row for row in payload["net_classes"]}
    assert set(by_name) == {"Default", "Power"}
    assert payload["components"][0]["designator"] == "R1"
    assert payload["nets"][0]["net_class"] == "Power"
