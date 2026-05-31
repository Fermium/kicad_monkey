"""
Bus connectivity and member-level cross-tap merging.

Buses in KiCad are a *separate* connectivity domain from wires. A bus
carries multiple named signals (members) and is named by a bus-form
label/hier_label/sheet_pin (e.g. ``D[0..7]``, ``{SCL,SDA}``,
``Foo{Bus1}``). Wires tap into a bus via :class:`SchBusEntry` and pick
up the bus's chosen-member name via a local label on the wire stub.

This module builds, for each sheet:

* :class:`BusSubgraph` records — one per physically-connected bus on
  the sheet, with its drivers + tapped wire-side coords.
* A coord lookup so other compilers can ask "is this coord on a bus,
  and if so which one?".

It also exposes :func:`merge_bus_member_taps_within_sheet`, which
unions wire union-find roots that tap the *same* bus member name. This
is the within-sheet equivalent of KiCad's
``CONNECTION_GRAPH::propagateToNeighbors`` for bus members:
two wire stubs labeled ``ROW0`` and physically connected only through
a bus collapse to one net once the bus's chosen name expands to
include ``ROW0`` as a member.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
)

from .kicad_bus_expansion import (
    canonical_bus_member_name,
    expand_bus_label,
    is_bus_label,
)
from .kicad_netlist_model import KiCadDriverKind, KiCadDriverPriority
from .kicad_schematic_connectivity import (
    ConnectivityGraph,
    CoordKey,
    snap_mm_to_iu,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .kicad_schematic import KiCadSchematic


# ---------------------------------------------------------------------------
# Driver record — narrowed copy of compiler._LabelDriver to avoid an
# import cycle.
# ---------------------------------------------------------------------------


@dataclass
class BusDriver:
    """A label-style driver that lands on bus coords."""

    text: str
    coord: CoordKey
    priority: KiCadDriverPriority
    kind: KiCadDriverKind


@dataclass
class BusSubgraph:
    """One physically-connected bus on a sheet.

    * ``coords`` — every snapped coord key that lies on a bus segment
      (including bus-entry bus-side endpoints).
    * ``drivers`` — labels / hier-labels / sheet-pins / global-labels
      whose coord falls on the bus.
    * ``tap_wire_coords`` — wire-side endpoint of each bus_entry on this
      bus. Other compilers map these to wire-UF roots to figure out
      which wires tap which member.
    * ``chosen_name`` — the bus's resolved name (bus expression),
      picked by ``compareDrivers`` priority + alphabetical tiebreak
      across the bus drivers. Empty when no bus-form driver was found.
    * ``chosen_priority`` / ``chosen_kind`` — provenance of the chosen
      driver, used by the cross-sheet merge.
    * ``members`` — the ordered list of expanded member names per
      :func:`expand_bus_label`. Empty when no chosen-name.
    """

    coords: Set[CoordKey] = field(default_factory=set)
    drivers: List[BusDriver] = field(default_factory=list)
    tap_wire_coords: List[CoordKey] = field(default_factory=list)
    chosen_name: str = ""
    chosen_priority: KiCadDriverPriority = KiCadDriverPriority.NONE
    chosen_kind: KiCadDriverKind = KiCadDriverKind.NONE
    members: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Point-on-segment helper (duplicates the integer cross-product test in
# kicad_netlist_compiler to avoid an import cycle).
# ---------------------------------------------------------------------------


def _point_on_segment(p: CoordKey, a: CoordKey, b: CoordKey) -> bool:
    px, py = p
    ax, ay = a
    bx, by = b
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if cross != 0:
        return False
    if px < min(ax, bx) or px > max(ax, bx):
        return False
    if py < min(ay, by) or py > max(ay, by):
        return False
    return True


# ---------------------------------------------------------------------------
# Bus-alias dict helpers
# ---------------------------------------------------------------------------


def collect_bus_aliases(schematic: "KiCadSchematic") -> Dict[str, List[str]]:
    """Flatten ``schematic.bus_aliases`` into a ``{name: [members]}`` dict.

    Returns an empty dict when the schematic has no aliases.
    """
    out: Dict[str, List[str]] = {}
    for alias in getattr(schematic, "bus_aliases", ()) or ():
        name = getattr(alias, "name", "") or ""
        members = list(getattr(alias, "members", ()) or [])
        if name:
            out[name] = members
    return out


# ---------------------------------------------------------------------------
# BusSubgraph builder
# ---------------------------------------------------------------------------


def build_bus_subgraphs(
    schematic: "KiCadSchematic",
    bus_aliases: Optional[Dict[str, List[str]]] = None,
) -> List[BusSubgraph]:
    """Build :class:`BusSubgraph` records for every bus on the sheet.

    Uses a *separate* union-find over bus segment endpoints + bus-entry
    bus-side endpoints. Returns subgraphs sorted by their lexically
    smallest coord for determinism.

    ``bus_aliases`` — caller-supplied alias map. When ``None``, the
    schematic's own ``bus_aliases`` are used.
    """
    if bus_aliases is None:
        bus_aliases = collect_bus_aliases(schematic)

    # --- 1. Bus union-find over bus segment endpoints --------------------
    bus_parent: Dict[CoordKey, CoordKey] = {}

    def bus_make(k: CoordKey) -> None:
        if k not in bus_parent:
            bus_parent[k] = k

    def bus_find(k: CoordKey) -> CoordKey:
        bus_make(k)
        while bus_parent[k] != k:
            bus_parent[k] = bus_parent[bus_parent[k]]
            k = bus_parent[k]
        return k

    def bus_union(a: CoordKey, b: CoordKey) -> None:
        ra, rb = bus_find(a), bus_find(b)
        if ra != rb:
            bus_parent[rb] = ra

    bus_segments: List[Tuple[CoordKey, CoordKey]] = []
    for bus in getattr(schematic, "buses", ()) or ():
        prev: Optional[CoordKey] = None
        for x_mm, y_mm in bus.points:
            cur = snap_mm_to_iu(float(x_mm), float(y_mm))
            bus_make(cur)
            if prev is not None and prev != cur:
                bus_union(prev, cur)
                bus_segments.append((prev, cur))
            prev = cur

    # Wire segments — needed only to classify bus_entry endpoints.
    wire_segments: List[Tuple[CoordKey, CoordKey]] = []
    for wire in getattr(schematic, "wires", ()) or ():
        prev = None
        for x_mm, y_mm in wire.points:
            cur = snap_mm_to_iu(float(x_mm), float(y_mm))
            if prev is not None and prev != cur:
                wire_segments.append((prev, cur))
            prev = cur

    # --- 2. Classify bus_entry endpoints + add tap info ------------------
    bus_entry_taps: List[Tuple[CoordKey, CoordKey]] = []  # (bus_side, wire_side)
    for entry in getattr(schematic, "bus_entries", ()) or ():
        a = snap_mm_to_iu(entry.at_x, entry.at_y)
        b = snap_mm_to_iu(entry.at_x + entry.size_x, entry.at_y + entry.size_y)
        a_on_bus = any(_point_on_segment(a, p, q) for p, q in bus_segments)
        b_on_bus = any(_point_on_segment(b, p, q) for p, q in bus_segments)
        a_on_wire = any(_point_on_segment(a, p, q) for p, q in wire_segments)
        b_on_wire = any(_point_on_segment(b, p, q) for p, q in wire_segments)

        if a_on_bus and not b_on_bus:
            bus_side, wire_side = a, b
        elif b_on_bus and not a_on_bus:
            bus_side, wire_side = b, a
        elif a_on_bus and b_on_bus:
            # Both endpoints land on bus segments — degenerate. Pick whichever
            # is NOT on a wire (or fall back to ``b``).
            if a_on_wire and not b_on_wire:
                bus_side, wire_side = b, a
            else:
                bus_side, wire_side = a, b
        else:
            # Neither classifies cleanly — fall back to KiCad's convention
            # of ``at = wire-side``, ``at + size = bus-side``.
            bus_side, wire_side = b, a

        bus_make(bus_side)
        # Union the bus-side coord into the bus segment it lies on so the
        # group identity carries to interior-point taps.
        for p, q in bus_segments:
            if _point_on_segment(bus_side, p, q):
                bus_union(bus_side, p)
                break

        bus_entry_taps.append((bus_side, wire_side))

    # --- 3. Group coords by bus root -------------------------------------
    bus_groups: Dict[CoordKey, Set[CoordKey]] = {}
    for k in bus_parent:
        r = bus_find(k)
        bus_groups.setdefault(r, set()).add(k)

    # Bus segments grouped by root for point-on-bus driver attach.
    segs_by_root: Dict[CoordKey, List[Tuple[CoordKey, CoordKey]]] = {}
    for a, b in bus_segments:
        r = bus_find(a)
        segs_by_root.setdefault(r, []).append((a, b))

    # --- 4. Build BusSubgraph per group ---------------------------------
    root_to_idx: Dict[CoordKey, int] = {}
    out: List[BusSubgraph] = []
    for r, coords in bus_groups.items():
        root_to_idx[r] = len(out)
        out.append(BusSubgraph(coords=set(coords)))

    for bus_side, wire_side in bus_entry_taps:
        r = bus_find(bus_side)
        out[root_to_idx[r]].tap_wire_coords.append(wire_side)

    # --- 5. Attach drivers to bus subgraphs -----------------------------
    def _find_idx(coord: CoordKey) -> Optional[int]:
        if coord in bus_parent:
            return root_to_idx[bus_find(coord)]
        for r, segs in segs_by_root.items():
            for p, q in segs:
                if _point_on_segment(coord, p, q):
                    return root_to_idx[r]
        return None

    # Collect bus-form drivers as we attach them; any bus-form driver
    # whose coord does NOT land on a drawn bus also needs a synthetic
    # subgraph (KiCad treats a standalone bus-form hier_label /
    # sheet_pin / label as its own bus connection even without a
    # drawn (bus …) anchor — see SCH_HIERLABEL / SCH_SHEET_PIN
    # connection setup in connection_graph.cpp).
    _orphans: List[BusDriver] = []

    def _attach_or_orphan(driver: BusDriver) -> None:
        idx = _find_idx(driver.coord)
        if idx is not None:
            out[idx].drivers.append(driver)
        elif is_bus_label(driver.text) or driver.text in bus_aliases:
            _orphans.append(driver)

    for label in getattr(schematic, "labels", ()) or ():
        c = snap_mm_to_iu(label.at_x, label.at_y)
        _attach_or_orphan(BusDriver(
            text=label.text, coord=c,
            priority=KiCadDriverPriority.LOCAL_LABEL,
            kind=KiCadDriverKind.LOCAL_LABEL,
        ))
    for label in getattr(schematic, "global_labels", ()) or ():
        c = snap_mm_to_iu(label.at_x, label.at_y)
        _attach_or_orphan(BusDriver(
            text=label.text, coord=c,
            priority=KiCadDriverPriority.GLOBAL,
            kind=KiCadDriverKind.GLOBAL_LABEL,
        ))
    for label in getattr(schematic, "hierarchical_labels", ()) or ():
        c = snap_mm_to_iu(label.at_x, label.at_y)
        _attach_or_orphan(BusDriver(
            text=label.text, coord=c,
            priority=KiCadDriverPriority.HIER_LABEL,
            kind=KiCadDriverKind.HIER_LABEL,
        ))
    for sheet in getattr(schematic, "sheets", ()) or ():
        for pin in getattr(sheet, "pins", ()) or ():
            c = snap_mm_to_iu(pin.at_x, pin.at_y)
            _attach_or_orphan(BusDriver(
                text=pin.name, coord=c,
                priority=KiCadDriverPriority.SHEET_PIN,
                kind=KiCadDriverKind.SHEET_PIN,
            ))

    # Synthesise virtual bus subgraphs for orphan bus-form drivers,
    # grouping by (driver_text). Two orphans with the same bus text on
    # the same sheet (e.g. two ``(label "MXA[0..10]" …)`` placements on
    # disjoint wires) share one virtual subgraph so the downstream
    # member-level UF sees them as one bus.
    by_text: Dict[str, int] = {}
    for od in _orphans:
        idx = by_text.get(od.text)
        if idx is None:
            idx = len(out)
            out.append(BusSubgraph(coords={od.coord}))
            by_text[od.text] = idx
        else:
            out[idx].coords.add(od.coord)
        out[idx].drivers.append(od)

    # --- 6. Resolve chosen name + member expansion per subgraph ---------
    for bs in out:
        # Only bus-form drivers contribute to naming. A non-bus-form
        # label that happens to fall on a bus coord (e.g. annotation) is
        # ignored for bus naming purposes.
        bus_form_drivers = [
            d for d in bs.drivers
            if is_bus_label(d.text) or d.text in bus_aliases
        ]
        if not bus_form_drivers:
            continue
        # compareDrivers: highest priority wins; ties → alphabetical;
        # ties on name → insertion order (stable sort).
        bus_form_drivers_indexed = list(enumerate(bus_form_drivers))
        bus_form_drivers_indexed.sort(
            key=lambda t: (-int(t[1].priority), t[1].text, t[0]),
        )
        _, best = bus_form_drivers_indexed[0]
        bs.chosen_name = best.text
        bs.chosen_priority = best.priority
        bs.chosen_kind = best.kind
        bs.members = list(expand_bus_label(best.text, bus_aliases))

    return out


# ---------------------------------------------------------------------------
# Within-sheet member merge — wire UF mutation
# ---------------------------------------------------------------------------


def merge_bus_member_taps_within_sheet(
    cgraph: ConnectivityGraph,
    bus_subgraphs: Iterable[BusSubgraph],
    wire_label_drivers: Iterable["object"],
) -> None:
    """Union wire-UF roots that tap the same bus member.

    For each bus subgraph that has a resolved member list, look at every
    wire stub tapping out of it. The wire stub's name (its LOCAL_LABEL
    driver, when present) tells us which member it represents. Wires
    representing the same member must end up on the same net — so we
    union their wire-UF roots in ``cgraph``.

    ``wire_label_drivers`` is the compiler's already-collected
    :class:`_LabelDriver` list (only ``LOCAL_LABEL`` entries are
    inspected). Caller must have run ``_attach_drivers_to_segments``
    first so each label coord is properly unioned into its wire
    component.
    """
    # Build a fast root → first-seen label-text map for LOCAL labels.
    label_text_by_root: Dict[CoordKey, str] = {}
    for ld in wire_label_drivers:
        kind = getattr(ld, "kind", None)
        if kind != KiCadDriverKind.LOCAL_LABEL:
            continue
        coord = getattr(ld, "coord", None)
        if coord is None:
            continue
        root = cgraph.find(coord)
        label_text_by_root.setdefault(
            root,
            canonical_bus_member_name(getattr(ld, "text", "") or ""),
        )

    for bs in bus_subgraphs:
        if not bs.members:
            continue
        member_set = {canonical_bus_member_name(m) for m in bs.members}
        # Group tap-wire UF roots by member name.
        roots_by_member: Dict[str, List[CoordKey]] = {}
        for tap_coord in bs.tap_wire_coords:
            if not cgraph.has(tap_coord[0] / 1, tap_coord[1] / 1):
                # ``has`` expects mm; use raw key check instead.
                pass
            # Direct check by raw key: ``ConnectivityGraph._parent`` is private,
            # so use ``find`` which seeds the node on access. We only want to
            # consult existing roots — skip when the coord wasn't seeded.
            # ``find`` would create a fresh singleton; cheap and harmless but
            # we still want a real wire-side coord.
            root = cgraph.find(tap_coord)
            text = label_text_by_root.get(root)
            if text is None or text not in member_set:
                continue
            roots_by_member.setdefault(text, []).append(root)
        for roots in roots_by_member.values():
            if len(roots) < 2:
                continue
            for k in roots[1:]:
                cgraph.union(roots[0], k)


__all__ = [
    "BusDriver",
    "BusSubgraph",
    "build_bus_subgraphs",
    "collect_bus_aliases",
    "merge_bus_member_taps_within_sheet",
]
