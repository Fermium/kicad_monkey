"""
KiCad schematic connectivity primitives.

Foundation for the netlist generator. Provides:

* :func:`compute_pin_position` — apply a placed
  :class:`~kicad_monkey.SchSymbol`'s ``at_x`` / ``at_y`` / ``at_angle``
  / ``mirror`` transform to a library :class:`~kicad_monkey.SymPin`'s
  Y-up (mm) coords and return the world-space (sheet, Y-down) external
  connection point in mm.
* :func:`iter_symbol_pins` — convenience walker that yields every active
  pin (per ``unit`` + ``convert``) of a placed symbol with its already-
  transformed world coordinates.
* :class:`CoordinateIndex` — float-tolerant spatial index keyed by the
  KiCad internal-unit grid (100 nm = 0.0001 mm); avoids floating-point
  drift when multiple items collocate.
* :class:`ConnectivityGraph` — union-find over wire endpoints, junction
  positions, and bus-entry diagonal endpoints. Supports
  :meth:`flood` to walk any given coord's connected component.
* :func:`detect_no_connects` — returns the set of snapped coordinate
  keys carrying ``no_connect`` markers; the netlist compiler will use
  this to mark pins that are intentionally unconnected.

All public coordinates returned to callers are mm floats matching the
on-disk schematic convention; the index uses snapped int keys
internally for exact equality.

Y-axis convention: KiCad library pins (`.kicad_sym`) are stored with
Y-up; placed-schematic coordinates are Y-down. The transform applied
here mirrors :mod:`kicad_schematic_to_ir`'s ``_placement_transform``
(rotate → mirror → translate, with the lib coord Y-flipped first to
enter the schematic's screen frame).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Iterator, List, Optional, Set, Tuple

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .kicad_lib_symbol import LibSymbol
    from .kicad_lib_subsymbol import LibSubSymbol
    from .kicad_sch_junction import SchJunction
    from .kicad_sch_symbol import SchSymbol
    from .kicad_sch_wire import SchBusEntry, SchWire
    from .kicad_schematic import KiCadSchematic
    from .kicad_sym_pin import SymPin


# ---------------------------------------------------------------------------
# Coordinate snapping
# ---------------------------------------------------------------------------

# KiCad's internal schematic unit (SCH_IU) = 100 nm = 0.0001 mm. Snapping
# float mm coords to this grid before hashing matches KiCad's own
# VECTOR2I-based equality (eeschema/connection_graph.cpp uses VECTOR2I
# keys throughout). 1 mm = 10_000 IU.
SCH_IU_PER_MM: int = 10_000

# A coord key is the snapped (x_iu, y_iu) integer tuple — exact equality
# under set/dict membership.
CoordKey = Tuple[int, int]


def snap_mm_to_iu(x_mm: float, y_mm: float) -> CoordKey:
    """Snap an (x_mm, y_mm) float pair to KiCad's 100-nm internal grid.

    Returns a hashable ``(x_iu, y_iu)`` integer tuple. Uses banker's
    rounding via Python's built-in :func:`round`.
    """
    return (
        int(round(x_mm * SCH_IU_PER_MM)),
        int(round(y_mm * SCH_IU_PER_MM)),
    )


def iu_key_to_mm(key: CoordKey) -> Tuple[float, float]:
    """Inverse of :func:`snap_mm_to_iu` — for diagnostic / debug output."""
    return (key[0] / SCH_IU_PER_MM, key[1] / SCH_IU_PER_MM)


# ---------------------------------------------------------------------------
# Pin-position transform
# ---------------------------------------------------------------------------


def _rotate(x: float, y: float, angle_deg: float) -> Tuple[float, float]:
    """Rotate (x, y) by ``angle_deg`` around the origin.

    Uses exact integer arithmetic for 0/90/180/270 degree multiples; falls
    back to ``math.cos`` / ``math.sin`` for arbitrary angles. Matches the
    convention in :mod:`kicad_plotter_transform` so the netlist sees the
    same geometry as the IR.
    """
    a = float(angle_deg) % 360.0
    if a == 0.0:
        return x, y
    if a == 90.0:
        return -y, x
    if a == 180.0:
        return -x, -y
    if a == 270.0:
        return y, -x
    rad = math.radians(a)
    c, s = math.cos(rad), math.sin(rad)
    return x * c - y * s, x * s + y * c


def compute_pin_position(symbol: "SchSymbol", lib_pin: "SymPin") -> Tuple[float, float]:
    """Return the world-space external connection point of ``lib_pin``.

    Library pin coords are Y-up mm; the placed schematic uses Y-down mm.
    This helper mirrors KiCad's ``SCH_SYMBOL`` ``TRANSFORM`` composition:

    1. Y-flip (lib Y-up → schematic Y-down). This is the ``ORIENT_0`` base
       ``TRANSFORM(1, 0, 0, -1)``.
    2. Rotate by ``symbol.at_angle`` clockwise (eeschema's "rotate CCW"
       in screen-Y-down view = clockwise in math-Y-up). Composed onto the
       base transform, so e.g. angle=90 yields ``TRANSFORM(0, -1, -1, 0)``
       and pin (0, 3.81) → (-3.81, 0).
    3. Mirror per ``symbol.mirror`` (``"x"`` flips Y of result;
       ``"y"`` flips X). Matches KiCad's ``SYM_MIRROR_X`` which
       does ``y2 *= -1`` on the transform.
    4. Translate to ``(symbol.at_x, symbol.at_y)``.

    Returns the connection-end coordinate (the wire-attach point), not
    the body anchor. See :class:`SymPin` for the convention.
    """
    # Step 1: Y-flip — enter the screen-Y frame.
    x = float(lib_pin.at_x)
    y = -float(lib_pin.at_y)

    # Step 2: rotation by symbol angle — KiCad's stored ``angle`` value
    # rotates the symbol clockwise in screen-Y-down view (= negative
    # angle in standard math CCW convention).
    x, y = _rotate(x, y, -symbol.at_angle)

    # Step 3: mirror.
    if symbol.mirror == "x":
        y = -y
    elif symbol.mirror == "y":
        x = -x

    # Step 4: translate to placement origin.
    return (x + symbol.at_x, y + symbol.at_y)


def _select_active_subsymbols(
    lib_symbol: "LibSymbol",
    *,
    unit: int,
    convert: int,
) -> List["LibSubSymbol"]:
    """Return subsymbols matching the placed symbol's ``unit`` + ``convert``.

    Mirrors KiCad's ``LIB_SYMBOL::Plot`` filter: a sub-symbol is active when
    ``sub.unit == 0`` (shared across units) OR ``sub.unit == placed.unit``
    AND when ``sub.style == 0`` (shared across body styles) OR
    ``sub.style == placed.convert``. Both ``convert`` and the file-format
    ``_<unit>_<style>`` suffix are 1-indexed in KiCad sexpr libs (style=1
    is the base body, style=2 is the De Morgan alternate); a stored value
    of 0 marks "common to all body styles".
    """
    out: List["LibSubSymbol"] = []
    for sub in lib_symbol.subsymbols:
        unit_ok = (sub.unit == 0) or (sub.unit == int(unit))
        style_ok = (sub.style == 0) or (sub.style == int(convert))
        if unit_ok and style_ok:
            out.append(sub)
    return out


def iter_symbol_pins(
    symbol: "SchSymbol",
    lib_symbol: "LibSymbol",
    unit_override: int | None = None,
) -> Iterator[Tuple[str, float, float, "SymPin"]]:
    """Walk every active pin of a placed symbol.

    Yields ``(pin_number, world_x_mm, world_y_mm, lib_pin)`` for each pin
    in the active sub-symbols (per :func:`_select_active_subsymbols`).
    Hidden pins (``pin.hide == True``) are still yielded — the netlist
    compiler decides whether to include them (e.g. hidden power pins on
    power symbols are intentionally connected).

    ``unit_override``, when supplied, replaces ``symbol.unit`` for sub-
    symbol selection. Legacy schematics omit ``(unit N)`` from the
    symbol body and only stamp the unit via the top-level
    ``(symbol_instances …)`` block, so a sheet-path-aware caller (the
    netlist compiler) resolves the real unit and passes it in here.
    """
    unit = symbol.unit if unit_override is None else unit_override
    for sub in _select_active_subsymbols(
        lib_symbol, unit=unit, convert=symbol.convert
    ):
        for pin in sub.pins:
            wx, wy = compute_pin_position(symbol, pin)
            yield (pin.number, wx, wy, pin)


# ---------------------------------------------------------------------------
# CoordinateIndex — spatial hash with grid snapping
# ---------------------------------------------------------------------------


@dataclass
class CoordinateIndex:
    """Float-tolerant spatial index keyed by snapped ``(x_iu, y_iu)``.

    Items are stored in lists per coord key so multiple objects sharing
    the same connection point coexist (e.g. a label, a junction, and a
    pin all landing at the same coord). Items can be of any type — the
    index is a generic hash-bucket.

    Use :meth:`add` to store, :meth:`get` for the bucket of a coord,
    :meth:`coords` for the set of populated keys, and :meth:`__contains__`
    for membership testing.
    """

    _buckets: dict = field(default_factory=dict)

    def add(self, x_mm: float, y_mm: float, item: object) -> CoordKey:
        key = snap_mm_to_iu(x_mm, y_mm)
        bucket = self._buckets.setdefault(key, [])
        bucket.append(item)
        return key

    def add_key(self, key: CoordKey, item: object) -> None:
        self._buckets.setdefault(key, []).append(item)

    def get(self, x_mm: float, y_mm: float) -> List[object]:
        return list(self._buckets.get(snap_mm_to_iu(x_mm, y_mm), []))

    def get_key(self, key: CoordKey) -> List[object]:
        return list(self._buckets.get(key, []))

    def coords(self) -> Set[CoordKey]:
        return set(self._buckets.keys())

    def __contains__(self, key) -> bool:  # type: ignore[override]
        if isinstance(key, tuple) and len(key) == 2 and isinstance(key[0], int):
            return key in self._buckets
        # treat as (x_mm, y_mm) float tuple
        if isinstance(key, tuple) and len(key) == 2:
            return snap_mm_to_iu(float(key[0]), float(key[1])) in self._buckets
        return False

    def __len__(self) -> int:
        return len(self._buckets)


# ---------------------------------------------------------------------------
# ConnectivityGraph — union-find over wire/bus/junction/bus_entry endpoints
# ---------------------------------------------------------------------------


class ConnectivityGraph:
    """Union-find over schematic connectivity coords.

    Nodes are coord keys (snapped int tuples). Edges are added by
    :meth:`add_edge`. After all edges are added, :meth:`find` returns the
    canonical representative of any coord's component, and :meth:`flood`
    returns the full coord set of a component.

    Wire / bus segments contribute one edge per consecutive point pair.
    Junctions contribute no edges directly — they only mark intersections
    that the compiler should treat as connected (see
    :meth:`add_junctions`). Bus entries contribute one edge between the
    diagonal endpoints (the wire-side and bus-side of the entry).
    """

    def __init__(self) -> None:
        self._parent: dict = {}
        self._rank: dict = {}
        self._members: dict = {}  # root -> list of coord keys (lazy)

    # --- internal union-find primitives -----------------------------------

    def _make(self, key: CoordKey) -> None:
        if key not in self._parent:
            self._parent[key] = key
            self._rank[key] = 0

    def find(self, key: CoordKey) -> CoordKey:
        """Return the root of ``key``'s component (creating one if absent)."""
        self._make(key)
        # Path compression
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        cur = key
        while self._parent[cur] != root:
            nxt = self._parent[cur]
            self._parent[cur] = root
            cur = nxt
        return root

    def union(self, a: CoordKey, b: CoordKey) -> CoordKey:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return ra
        # Union by rank.
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1
        return ra

    # --- public edge-adding API -------------------------------------------

    def add_node(self, x_mm: float, y_mm: float) -> CoordKey:
        key = snap_mm_to_iu(x_mm, y_mm)
        self._make(key)
        return key

    def add_key_node(self, key: CoordKey) -> CoordKey:
        """Register an already-snapped coordinate key."""
        self._make(key)
        return key

    def add_edge(
        self,
        a_mm: Tuple[float, float],
        b_mm: Tuple[float, float],
    ) -> Tuple[CoordKey, CoordKey]:
        ka = snap_mm_to_iu(a_mm[0], a_mm[1])
        kb = snap_mm_to_iu(b_mm[0], b_mm[1])
        self.union(ka, kb)
        return ka, kb

    def add_wire(self, wire: "SchWire") -> List[CoordKey]:
        """Add every consecutive point pair in ``wire.points`` as an edge."""
        return self._add_polyline(wire.points)

    def add_bus(self, bus) -> List[CoordKey]:
        """Register bus segment coords as nodes only — no edges into the
        wire union-find domain.

        Buses do NOT electrically tie wires together in KiCad. A bus is
        a naming construct (``D[0..7]``, bus aliases, bus groups); the
        wires that tap into it via :class:`SchBusEntry` get their net
        identity from a *local label* on the wire-side. Unioning bus
        points into the wire graph would collapse every wire that taps
        the same bus into one mega-net.
        """
        keys: List[CoordKey] = []
        for x_mm, y_mm in bus.points:
            keys.append(self.add_node(x_mm, y_mm))
        return keys

    def _add_polyline(self, points: Iterable[Tuple[float, float]]) -> List[CoordKey]:
        keys: List[CoordKey] = []
        prev: Optional[CoordKey] = None
        for x_mm, y_mm in points:
            cur = snap_mm_to_iu(x_mm, y_mm)
            self._make(cur)
            keys.append(cur)
            if prev is not None and prev != cur:
                self.union(prev, cur)
            prev = cur
        return keys

    def add_bus_entry(self, entry: "SchBusEntry") -> Tuple[CoordKey, CoordKey]:
        """Register a bus-entry's two endpoints as nodes only — no edge.

        A :class:`SchBusEntry` is a visual diagonal connecting one bus
        coord (``at_x, at_y``) to one wire coord
        (``at_x+size_x, at_y+size_y``). It does NOT electrically union
        the two sides — the wire-side coord must carry a local label
        whose name matches a member of the bus carried at the bus-side
        coord. Unioning here would collapse every wire-side tap into
        the bus's component.
        """
        a = self.add_node(entry.at_x, entry.at_y)
        b = self.add_node(entry.at_x + entry.size_x, entry.at_y + entry.size_y)
        return a, b

    def add_junctions(self, junctions: Iterable["SchJunction"]) -> List[CoordKey]:
        """Register junction positions as nodes.

        Junctions don't create edges — they only mark a coord as a
        valid intersection. Wires landing on the same coord are already
        unioned via shared endpoints. The netlist compiler uses the set
        of junction coords to disambiguate "wires crossing without
        connecting" from "wires connected at a T".
        """
        keys: List[CoordKey] = []
        for j in junctions:
            keys.append(self.add_node(j.at_x, j.at_y))
        return keys

    # --- queries ----------------------------------------------------------

    def flood(self, key: CoordKey) -> Set[CoordKey]:
        """Return the set of all coord keys in ``key``'s component."""
        if key not in self._parent:
            return set()
        root = self.find(key)
        return {k for k in self._parent if self.find(k) == root}

    def components(self) -> List[Set[CoordKey]]:
        """Return all connected components as a list of coord-key sets."""
        groups: dict = {}
        for k in self._parent:
            r = self.find(k)
            groups.setdefault(r, set()).add(k)
        return list(groups.values())

    def has(self, x_mm: float, y_mm: float) -> bool:
        return snap_mm_to_iu(x_mm, y_mm) in self._parent


# ---------------------------------------------------------------------------
# No-connect detection
# ---------------------------------------------------------------------------


def detect_no_connects(schematic: "KiCadSchematic") -> Set[CoordKey]:
    """Return the set of snapped coord keys carrying ``no_connect`` markers.

    The netlist compiler treats a pin landing on a no-connect coord as
    intentionally unconnected — KiCad ERC suppresses warnings for such
    pins, and the resulting net is named ``unconnected-(<ref>-<pin>)``
    in the kicad-cli netlist.
    """
    out: Set[CoordKey] = set()
    for nc in getattr(schematic, "no_connects", ()):
        out.add(snap_mm_to_iu(nc.at_x, nc.at_y))
    return out


__all__ = [
    "SCH_IU_PER_MM",
    "CoordKey",
    "snap_mm_to_iu",
    "iu_key_to_mm",
    "compute_pin_position",
    "iter_symbol_pins",
    "CoordinateIndex",
    "ConnectivityGraph",
    "detect_no_connects",
]
