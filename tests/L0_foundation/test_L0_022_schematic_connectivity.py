"""
Test L0_022: schematic connectivity primitives (Phase G — Slice N-1).

Pure-unit coverage for the four netlist-foundation helpers in
:mod:`kicad_monkey.kicad_schematic_connectivity`:

* :func:`compute_pin_position` — placement transform (rotate / mirror /
  translate) with the lib-Y-up → schematic-Y-down flip baked in.
* :func:`iter_symbol_pins` — multi-unit + multi-style sub-symbol
  selection.
* :class:`CoordinateIndex` — float-tolerant coord hashing keyed by
  KiCad's 100-nm internal-unit grid.
* :class:`ConnectivityGraph` — union-find over wire / bus / bus-entry
  endpoints, with junction registration.
* :func:`detect_no_connects` — coord-key set of ``no_connect`` markers.

Tests are fixture-free — every input is synthesized from the public
dataclass constructors so the helpers can be exercised without a
on-disk ``.kicad_sch`` parse.
"""

from __future__ import annotations

import math

import pytest

from kicad_monkey import (
    ConnectivityGraph,
    CoordinateIndex,
    SCH_IU_PER_MM,
    compute_pin_position,
    detect_no_connects,
    iter_symbol_pins,
    iu_key_to_mm,
    snap_mm_to_iu,
)
from kicad_monkey.kicad_lib_subsymbol import LibSubSymbol
from kicad_monkey.kicad_lib_symbol import LibSymbol
from kicad_monkey.kicad_sch_enums import PinElectricalType, PinGraphicStyle
from kicad_monkey.kicad_sch_junction import SchJunction
from kicad_monkey.kicad_sch_no_connect import SchNoConnect
from kicad_monkey.kicad_sch_symbol import SchSymbol
from kicad_monkey.kicad_sch_wire import SchBusEntry, SchWire
from kicad_monkey.kicad_sym_pin import SymPin


# ---------------------------------------------------------------------------
# Helpers — synthesized fixture builders
# ---------------------------------------------------------------------------


def _pin(at_x: float, at_y: float, *, number: str = "1", angle: float = 0.0,
         length: float = 2.54) -> SymPin:
    return SymPin(
        electrical_type=PinElectricalType.PASSIVE,
        graphic_style=PinGraphicStyle.LINE,
        at_x=at_x, at_y=at_y, at_angle=angle, length=length,
        number=number, name="~",
    )


def _placed(lib_id: str = "Device:R", *, at_x: float = 0.0, at_y: float = 0.0,
            angle: float = 0.0, mirror: str | None = None,
            unit: int = 1, convert: int = 1) -> SchSymbol:
    return SchSymbol(
        lib_id=lib_id, at_x=at_x, at_y=at_y, at_angle=angle,
        mirror=mirror, unit=unit, convert=convert,
    )


def _libsym(name: str, *subsymbols: LibSubSymbol) -> LibSymbol:
    return LibSymbol(name=name, subsymbols=list(subsymbols))


def _subsym(*pins: SymPin, unit: int = 1, style: int = 0,
            name_suffix: str = "") -> LibSubSymbol:
    return LibSubSymbol(
        name=f"sym_{unit}_{style}{name_suffix}",
        unit=unit, style=style, pins=list(pins),
    )


# ---------------------------------------------------------------------------
# Coordinate snapping
# ---------------------------------------------------------------------------


def test_snap_mm_to_iu_uses_100nm_grid():
    assert snap_mm_to_iu(0.0, 0.0) == (0, 0)
    assert snap_mm_to_iu(1.0, 1.0) == (10_000, 10_000)
    assert snap_mm_to_iu(0.5, -2.54) == (5_000, -25_400)


def test_snap_mm_to_iu_collapses_float_drift():
    """Values within < 50 nm should hash to the same key (KiCad's IU)."""
    a = snap_mm_to_iu(127.0, 88.9)
    b = snap_mm_to_iu(127.0 + 1e-9, 88.9 - 1e-9)
    assert a == b


def test_iu_key_to_mm_round_trip():
    key = snap_mm_to_iu(12.345, -6.789)
    x_mm, y_mm = iu_key_to_mm(key)
    assert x_mm == pytest.approx(12.345)
    assert y_mm == pytest.approx(-6.789)


# ---------------------------------------------------------------------------
# compute_pin_position
# ---------------------------------------------------------------------------


def test_pin_position_at_origin_no_transform():
    """Lib pin at (5, 0) Y-up → screen-Y (5, 0); placement at origin."""
    sym = _placed(at_x=0.0, at_y=0.0)
    pin = _pin(5.0, 0.0)
    x, y = compute_pin_position(sym, pin)
    assert (x, y) == pytest.approx((5.0, 0.0))


def test_pin_position_y_flip():
    """Lib pin Y-up at (0, 3) → schematic Y-down at (0, -3)."""
    sym = _placed(at_x=0.0, at_y=0.0)
    pin = _pin(0.0, 3.0)
    x, y = compute_pin_position(sym, pin)
    assert (x, y) == pytest.approx((0.0, -3.0))


def test_pin_position_translation():
    sym = _placed(at_x=100.0, at_y=50.0)
    pin = _pin(2.54, 0.0)
    x, y = compute_pin_position(sym, pin)
    assert (x, y) == pytest.approx((102.54, 50.0))


def test_pin_position_rotation_90():
    """KiCad ``ORIENT_90`` TRANSFORM(0, -1, -1, 0): pin (5, 0) → (0, -5)."""
    sym = _placed(at_x=0.0, at_y=0.0, angle=90.0)
    pin = _pin(5.0, 0.0)  # lib Y-up; Y-flip → (5, 0); rotate −90 (CW) → (0, −5).
    x, y = compute_pin_position(sym, pin)
    assert (x, y) == pytest.approx((0.0, -5.0))


def test_pin_position_rotation_180():
    sym = _placed(at_x=0.0, at_y=0.0, angle=180.0)
    pin = _pin(5.0, 0.0)
    x, y = compute_pin_position(sym, pin)
    assert (x, y) == pytest.approx((-5.0, 0.0))


def test_pin_position_rotation_270():
    """KiCad ``ORIENT_270`` TRANSFORM(0, 1, 1, 0): pin (5, 0) → (0, 5)."""
    sym = _placed(at_x=0.0, at_y=0.0, angle=270.0)
    pin = _pin(5.0, 0.0)
    x, y = compute_pin_position(sym, pin)
    assert (x, y) == pytest.approx((0.0, 5.0))


def test_pin_position_mirror_x_flips_y():
    """``mirror = "x"`` flips the Y component (KiCad ``y2 *= -1``)."""
    sym = _placed(at_x=0.0, at_y=0.0, mirror="x")
    pin = _pin(0.0, 3.0)  # lib Y-up; Y-flip → (0, -3); mirror x → (0, 3)
    x, y = compute_pin_position(sym, pin)
    assert (x, y) == pytest.approx((0.0, 3.0))


def test_pin_position_mirror_y_flips_x():
    sym = _placed(at_x=0.0, at_y=0.0, mirror="y")
    pin = _pin(5.0, 0.0)  # lib (5, 0); Y-flip (5, 0); mirror y → (-5, 0)
    x, y = compute_pin_position(sym, pin)
    assert (x, y) == pytest.approx((-5.0, 0.0))


def test_pin_position_combined_rotate_mirror_translate():
    """KiCad ORIENT_90 + MIRROR_X for pin (5, 0): result (0, 5) before translate."""
    sym = _placed(at_x=10.0, at_y=20.0, angle=90.0, mirror="x")
    pin = _pin(5.0, 0.0)
    # lib (5, 0) → Y-flip (5, 0) → rotate −90 (CW) (0, −5) → mirror x (0, 5) → +(10, 20) = (10, 25)
    x, y = compute_pin_position(sym, pin)
    assert (x, y) == pytest.approx((10.0, 25.0))


def test_pin_position_arbitrary_angle_uses_trig():
    """Non-multiple-of-90 angles fall back to sin/cos (CW direction)."""
    sym = _placed(angle=45.0)
    pin = _pin(2.0, 0.0)
    x, y = compute_pin_position(sym, pin)
    # lib (2, 0) → Y-flip (2, 0) → rotate −45° (CW): (2*cos45, −2*sin45)
    expected_x = 2.0 * math.cos(math.radians(45.0))
    expected_y = -2.0 * math.sin(math.radians(45.0))
    assert x == pytest.approx(expected_x, abs=1e-9)
    assert y == pytest.approx(expected_y, abs=1e-9)


# ---------------------------------------------------------------------------
# iter_symbol_pins — sub-symbol selection
# ---------------------------------------------------------------------------


def test_iter_symbol_pins_single_unit():
    sub = _subsym(_pin(0, 0, number="1"), _pin(2.54, 0, number="2"), unit=1)
    lib = _libsym("R", sub)
    sym = _placed("Device:R")
    pins = list(iter_symbol_pins(sym, lib))
    assert {p[0] for p in pins} == {"1", "2"}


def test_iter_symbol_pins_multi_unit_filters_by_unit():
    """Pins from a different unit must NOT appear when iterating unit=2."""
    sub_u1 = _subsym(_pin(0, 0, number="1"), unit=1)
    sub_u2 = _subsym(_pin(0, 0, number="2"), unit=2)
    lib = _libsym("LM358", sub_u1, sub_u2)

    sym1 = _placed("Amp:LM358", unit=1)
    sym2 = _placed("Amp:LM358", unit=2)
    nums1 = {p[0] for p in iter_symbol_pins(sym1, lib)}
    nums2 = {p[0] for p in iter_symbol_pins(sym2, lib)}
    assert nums1 == {"1"}
    assert nums2 == {"2"}


def test_iter_symbol_pins_unit_zero_shared_across_units():
    """``unit == 0`` sub-symbols are common to all units."""
    shared = _subsym(_pin(0, 0, number="V+"), unit=0)
    sub_u1 = _subsym(_pin(0, 0, number="1"), unit=1)
    lib = _libsym("LM358", shared, sub_u1)
    sym = _placed("Amp:LM358", unit=1)
    nums = {p[0] for p in iter_symbol_pins(sym, lib)}
    assert nums == {"V+", "1"}


def test_iter_symbol_pins_style_zero_shared_across_body_styles():
    # KiCad body-style convention is 1-indexed in the file format
    # (``_<unit>_<style>`` suffix and the placed-symbol ``convert`` field):
    # style=1 is the base body, style=2 is the De Morgan alternate, and
    # style=0 marks "common to all body styles". A normal placement
    # (convert=1) selects style=0 + style=1; a De Morgan placement
    # (convert=2) selects style=0 + style=2.
    shared = _subsym(_pin(0, 0, number="0"), unit=1, style=0)
    base = _subsym(_pin(0, 0, number="1"), unit=1, style=1)
    demorgan = _subsym(_pin(0, 0, number="2"), unit=1, style=2)
    lib = _libsym("Gate", shared, base, demorgan)
    sym_normal = _placed("Gate:Foo", unit=1, convert=1)
    sym_demorgan = _placed("Gate:Foo", unit=1, convert=2)
    n0 = {p[0] for p in iter_symbol_pins(sym_normal, lib)}
    n1 = {p[0] for p in iter_symbol_pins(sym_demorgan, lib)}
    assert n0 == {"0", "1"}  # shared + base body
    assert n1 == {"0", "2"}  # shared + De Morgan body


# ---------------------------------------------------------------------------
# CoordinateIndex
# ---------------------------------------------------------------------------


def test_coordinate_index_collocated_items_share_bucket():
    idx = CoordinateIndex()
    idx.add(10.0, 20.0, "wire-A")
    idx.add(10.0, 20.0, "pin-X")
    assert sorted(idx.get(10.0, 20.0)) == ["pin-X", "wire-A"]


def test_coordinate_index_distant_items_separate():
    idx = CoordinateIndex()
    idx.add(10.0, 20.0, "A")
    idx.add(10.0, 21.0, "B")
    assert idx.get(10.0, 20.0) == ["A"]
    assert idx.get(10.0, 21.0) == ["B"]


def test_coordinate_index_membership_via_int_key():
    idx = CoordinateIndex()
    key = idx.add(10.0, 20.0, "X")
    assert key in idx


def test_coordinate_index_membership_via_float_pair():
    idx = CoordinateIndex()
    idx.add(10.0, 20.0, "X")
    assert (10.0, 20.0) in idx
    assert (10.0, 21.0) not in idx


def test_coordinate_index_coords_returns_all_keys():
    idx = CoordinateIndex()
    idx.add(0.0, 0.0, "a")
    idx.add(2.54, 2.54, "b")
    coords = idx.coords()
    assert snap_mm_to_iu(0.0, 0.0) in coords
    assert snap_mm_to_iu(2.54, 2.54) in coords
    assert len(coords) == 2


# ---------------------------------------------------------------------------
# ConnectivityGraph
# ---------------------------------------------------------------------------


def test_three_pin_wire_chain_unifies_all_endpoints():
    """A→B + B→C wire pair → all three coords in one component."""
    g = ConnectivityGraph()
    w1 = SchWire(points=[(0.0, 0.0), (10.0, 0.0)])
    w2 = SchWire(points=[(10.0, 0.0), (20.0, 0.0)])
    g.add_wire(w1)
    g.add_wire(w2)
    component = g.flood(snap_mm_to_iu(0.0, 0.0))
    assert snap_mm_to_iu(10.0, 0.0) in component
    assert snap_mm_to_iu(20.0, 0.0) in component
    assert len(component) == 3


def test_disjoint_wires_form_separate_components():
    g = ConnectivityGraph()
    g.add_wire(SchWire(points=[(0, 0), (5, 0)]))
    g.add_wire(SchWire(points=[(10, 0), (15, 0)]))
    comps = g.components()
    assert len(comps) == 2


def test_multi_segment_wire_unifies_all_corner_points():
    g = ConnectivityGraph()
    g.add_wire(SchWire(points=[(0, 0), (10, 0), (10, 10), (0, 10)]))
    assert g.flood(snap_mm_to_iu(0, 0)) == {
        snap_mm_to_iu(0, 0),
        snap_mm_to_iu(10, 0),
        snap_mm_to_iu(10, 10),
        snap_mm_to_iu(0, 10),
    }


def test_bus_entry_registers_both_endpoints_as_separate_singletons():
    """Bus-entries do NOT union wire-side with bus-side.

    A ``SchBusEntry`` is a visual diagonal connecting a bus-side coord
    to a wire-side coord; the actual electrical connection happens via
    a local label on the wire-side that matches a bus member. Unioning
    here would collapse every wire-side tap into the bus's component.
    """
    g = ConnectivityGraph()
    entry = SchBusEntry(at_x=10.0, at_y=10.0, size_x=2.54, size_y=2.54)
    g.add_bus_entry(entry)
    a = snap_mm_to_iu(10.0, 10.0)
    b = snap_mm_to_iu(12.54, 12.54)
    assert g.has(10.0, 10.0)
    assert g.has(12.54, 12.54)
    # Both endpoints registered, but live in their own singleton
    # components — flood from one must NOT include the other.
    assert g.flood(a) == {a}
    assert g.flood(b) == {b}


def test_junctions_register_as_nodes_only():
    """Junctions don't create edges — they only mark coords."""
    g = ConnectivityGraph()
    j = SchJunction(at_x=5.0, at_y=5.0)
    g.add_junctions([j])
    assert g.has(5.0, 5.0)
    # Solo junction: its component should be just itself.
    assert g.flood(snap_mm_to_iu(5.0, 5.0)) == {snap_mm_to_iu(5.0, 5.0)}


def test_junction_coincident_with_wire_endpoint_already_unioned():
    g = ConnectivityGraph()
    g.add_wire(SchWire(points=[(0, 0), (5, 5)]))
    g.add_junctions([SchJunction(at_x=5.0, at_y=5.0)])
    # Junction at (5, 5) is the wire's endpoint → component holds both.
    comp = g.flood(snap_mm_to_iu(0, 0))
    assert snap_mm_to_iu(5, 5) in comp


def test_find_creates_singleton_for_unknown_coord():
    g = ConnectivityGraph()
    key = snap_mm_to_iu(7.0, 7.0)
    root = g.find(key)
    assert root == key
    assert g.flood(key) == {key}


def test_components_count_matches_wire_topology():
    """Three disjoint wires → three components."""
    g = ConnectivityGraph()
    g.add_wire(SchWire(points=[(0, 0), (1, 0)]))
    g.add_wire(SchWire(points=[(10, 0), (11, 0)]))
    g.add_wire(SchWire(points=[(20, 0), (21, 0)]))
    assert len(g.components()) == 3


# ---------------------------------------------------------------------------
# detect_no_connects
# ---------------------------------------------------------------------------


class _FakeSchematic:
    """Tiny stub matching the only attribute :func:`detect_no_connects` reads."""

    def __init__(self, no_connects):
        self.no_connects = no_connects


def test_detect_no_connects_collects_all_marker_coords():
    nc1 = SchNoConnect(at_x=10.0, at_y=20.0)
    nc2 = SchNoConnect(at_x=15.0, at_y=25.0)
    sch = _FakeSchematic([nc1, nc2])
    assert detect_no_connects(sch) == {
        snap_mm_to_iu(10.0, 20.0),
        snap_mm_to_iu(15.0, 25.0),
    }


def test_detect_no_connects_empty_when_none_present():
    sch = _FakeSchematic([])
    assert detect_no_connects(sch) == set()


def test_detect_no_connects_tolerates_missing_attribute():
    """Caller may pass a partial stub (e.g. a different parser); fall through cleanly."""
    class Bare:
        pass
    assert detect_no_connects(Bare()) == set()
