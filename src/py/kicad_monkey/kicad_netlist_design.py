"""
Multi-sheet KiCad netlist compiler.

Walks a hierarchical :class:`~kicad_monkey.KiCadSchematic` design,
compiles each sheet via :func:`compile_sheet_subgraphs`, then performs
cross-sheet union-find based on:

1. ``sheet_pin`` (parent) ↔ ``hierarchical_label`` (child) pairing by
   pin / label name — the standard KiCad way to bridge a parent
   subgraph into the matching child subgraph.
2. Cross-sheet ``global_label`` text-equality merge — all subgraphs
   driven by the same global-label text collapse to one net.
3. Cross-sheet ``global_power_pin`` value-equality merge — all
   subgraphs driven by a power symbol with the same value collapse to
   one net.

After merging, the highest-priority driver across the merged group
names the net (KiCad's ``compareDrivers`` rules — same as the
single-sheet path). Sequential net codes are assigned in stable
discovery order.

The resulting netlist includes resolved nets plus component, library-part,
library, sheet, and net-class metadata needed by the emitters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
)

from .kicad_bus_connectivity import (
    BusSubgraph,
    build_bus_subgraphs,
    collect_bus_aliases,
)
from .kicad_bus_expansion import canonical_bus_member_name, is_bus_label
from .kicad_netlist_compiler import (
    Subgraph,
    _append_unique_endpoint,
    _empty_graphical_map,
    _is_power_symbol,
    _label_driver_endpoint,
    _normalize_netlist_pin_number,
    _pin_kind,
    _power_pin_endpoint,
    _resolve_instance_reference,
    compile_sheet_subgraphs,
    name_net,
)
from .kicad_netlist_model import (
    KiCadDesignSheet,
    KiCadDriverKind,
    KiCadDriverPriority,
    KiCadLibPart,
    KiCadLibPartPin,
    KiCadNet,
    KiCadNetlist,
    KiCadNetlistComponent,
    KiCadNetlistTerminal,
)
from .kicad_schematic_connectivity import CoordKey

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .kicad_sch_sheet import SchSheet
    from .kicad_schematic import KiCadSchematic


# ---------------------------------------------------------------------------
# Compiled-sheet records
# ---------------------------------------------------------------------------


@dataclass
class CompiledSheet:
    """One sheet instance in the design — its compiled subgraphs + paths.

    * ``sheet_path`` — canonical UUID-form path (e.g. ``"/<uuid>/<uuid>/"``).
      Used for net naming when the chosen driver is a local label /
      hier label / sheet pin.
    * ``sheet_path_human`` — human-readable path built from each
      sheet's ``Sheetname`` (e.g. ``"/sub_a/inner/"``).
    * ``schematic`` — the :class:`KiCadSchematic` this sheet refers to.
    * ``subgraphs`` — output of :func:`compile_sheet_subgraphs`.
    * ``parent_sheet`` — the :class:`SchSheet` placement that brought
      this sheet into the design (``None`` for the root).
    * ``parent`` — the parent :class:`CompiledSheet` (``None`` for root).
    * ``coord_to_sg`` — derived index from each subgraph coord to its
      subgraph index inside ``subgraphs`` (used by the merge step).
    """

    sheet_path: str = "/"
    sheet_path_human: str = "/"
    schematic: Optional["KiCadSchematic"] = None
    subgraphs: List[Subgraph] = field(default_factory=list)
    parent_sheet: Optional["SchSheet"] = None
    parent: Optional["CompiledSheet"] = None
    coord_to_sg: Dict[CoordKey, int] = field(default_factory=dict)
    bus_subgraphs: List[BusSubgraph] = field(default_factory=list)
    # Per bus-subgraph index → mapping {member_name: wire_sg_idx}.
    # Built alongside ``bus_subgraphs`` so the cross-sheet bus member
    # merge can look up "which wire subgraph carries member ``X`` of
    # bus ``i``?" without re-walking taps.
    bus_member_wire_sg: List[Dict[str, int]] = field(default_factory=list)
    # Design-wide bus alias map — only the root sheet carries this;
    # populated by ``compile_design_subgraphs``. Empty on non-root.
    bus_aliases_design: Dict[str, List[str]] = field(default_factory=dict)


def _merge_graphical_ids(
    target: Dict[str, List[str]],
    source: Dict[str, List[str]],
) -> None:
    for key, values in (source or {}).items():
        dest = target.setdefault(key, [])
        for value in values or ():
            if value and value not in dest:
                dest.append(value)


# ---------------------------------------------------------------------------
# Design walk — yields CompiledSheet shells (subgraphs not yet filled)
# ---------------------------------------------------------------------------


def _walk_design_sheets(top: "KiCadSchematic") -> Iterator[CompiledSheet]:
    """Yield ``CompiledSheet`` records for every sheet in the hierarchy.

    Order: parent before child. The root's ``sheet_path`` is always
    ``"/"`` — kicad-cli uses the same convention; the top schematic's
    own UUID never appears in the path (instance-path UUIDs come from
    the parent's ``SchSheet`` placeholders, not the child's own
    ``(uuid …)``). Each child level appends ``"<sheet_placeholder_uuid>/"``.
    """
    root = CompiledSheet(
        sheet_path="/",
        sheet_path_human="/",
        schematic=top,
    )
    yield root
    yield from _walk_children(top, root)


def _walk_children(
    parent_sch: "KiCadSchematic",
    parent_cs: CompiledSheet,
) -> Iterator[CompiledSheet]:
    for sheet in getattr(parent_sch, "sheets", ()):
        child_sch = parent_sch.sub_schematics.get(sheet.sheet_file)
        if child_sch is None:
            continue
        # UUID-form path: extend with this sheet placeholder's uuid.
        child_uuid = sheet.uuid or sheet.sheet_file
        child_path = f"{parent_cs.sheet_path}{child_uuid}/"
        child_human = f"{parent_cs.sheet_path_human}{sheet.sheet_name or sheet.sheet_file}/"
        cs = CompiledSheet(
            sheet_path=child_path,
            sheet_path_human=child_human,
            schematic=child_sch,
            parent_sheet=sheet,
            parent=parent_cs,
        )
        yield cs
        yield from _walk_children(child_sch, cs)


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------


def _build_legacy_instance_lookup(
    compiled: List[CompiledSheet],
) -> Dict[str, str]:
    """Flatten every loaded schematic's legacy ``symbol_instances`` block
    into a ``{path -> reference}`` map (path normalised by ``rstrip("/")``).

    Pre-20210126 fixtures keep per-instance reference overrides on the
    *top* schematic only, with paths in ``/<sheet_uuid>/<symbol_uuid>``
    form (the symbol's own UUID is the trailing segment). Modern
    fixtures move this onto each :class:`SchSymbol`'s ``instances``
    block, which :func:`_resolve_instance_reference` already handles.
    Walk every schematic in the design (deduped by ``id``) so a
    standalone-loaded sub-sheet whose own file carries the legacy
    block is also covered.
    """
    out: Dict[str, str] = {}
    seen: set = set()
    for cs in compiled:
        sch = cs.schematic
        if sch is None or id(sch) in seen:
            continue
        seen.add(id(sch))
        for inst in getattr(sch, "symbol_instances", ()) or ():
            path = (getattr(inst, "path", "") or "").rstrip("/")
            ref = getattr(inst, "reference", "") or ""
            if path and ref:
                out.setdefault(path, ref)
    return out


def _build_legacy_unit_lookup(
    compiled: List[CompiledSheet],
) -> Dict[str, int]:
    """Same as :func:`_build_legacy_instance_lookup` but for ``unit``.

    Legacy ``(symbol_instances …)`` records carry both ``reference``
    and ``unit``. The unit lookup is the only authoritative source of
    per-sheet-path unit for placements whose schematic body lacks a
    ``(unit N)`` token (which is the norm for pre-20210126 fixtures).
    """
    out: Dict[str, int] = {}
    seen: set = set()
    for cs in compiled:
        sch = cs.schematic
        if sch is None or id(sch) in seen:
            continue
        seen.add(id(sch))
        for inst in getattr(sch, "symbol_instances", ()) or ():
            path = (getattr(inst, "path", "") or "").rstrip("/")
            unit = int(getattr(inst, "unit", 1) or 1)
            if path:
                out.setdefault(path, unit)
    return out


def _canonical_instance_path(top: "KiCadSchematic", sheet_path: str) -> str:
    """Build the modern canonical instance path for *sheet_path*.

    KiCad's modern ``(instances …)`` block uses paths like
    ``/<top_sch_uuid>/<child_sheet_uuid>/…`` — i.e. the path always
    *starts* with the top schematic's own UUID. Our :class:`CompiledSheet`
    convention strips that leading segment (root = ``"/"``), so to match
    a sym's modern instance entry we have to prepend ``top.uuid`` back.

    Returns a string with trailing ``/`` stripped to match the equality
    comparison done in :func:`_resolve_instance_reference`.
    """
    top_uuid = (getattr(top, "uuid", "") or "").strip()
    if not top_uuid:
        return sheet_path.rstrip("/")
    # sheet_path always starts with "/" — concat directly (e.g. "/abc/").
    return f"/{top_uuid}{sheet_path}".rstrip("/")


def compile_design_subgraphs(
    top: "KiCadSchematic",
    *,
    subpart_first_id: int = ord("A"),
    subpart_id_separator: int = 0,
) -> List[CompiledSheet]:
    """Compile every sheet in the hierarchy.

    Returns a list of :class:`CompiledSheet` instances (root first) with
    their ``subgraphs`` and ``coord_to_sg`` populated. Cross-sheet
    merging is *not* applied — call :func:`merge_design_nets` for that.
    """
    out: List[CompiledSheet] = list(_walk_design_sheets(top))
    legacy_lookup = _build_legacy_instance_lookup(out)
    legacy_unit_lookup = _build_legacy_unit_lookup(out)
    # KiCad treats bus aliases as design-wide: any sheet's
    # ``(bus_alias …)`` declaration is visible to every other sheet
    # in the hierarchy when resolving bus labels. Collect them across
    # all compiled sheets up front; later sheets override earlier ones
    # on name collision (mirrors KiCad's last-loaded-wins behaviour).
    aliases: Dict[str, List[str]] = {}
    for cs in out:
        if cs.schematic is None:
            raise ValueError(f"Compiled sheet {cs.sheet_path!r} has no schematic")
        aliases.update(collect_bus_aliases(cs.schematic))
    for cs in out:
        if cs.schematic is None:
            raise ValueError(f"Compiled sheet {cs.sheet_path!r} has no schematic")
        canonical = _canonical_instance_path(top, cs.sheet_path)
        cs.subgraphs = compile_sheet_subgraphs(
            cs.schematic, cs.sheet_path,
            legacy_lookup=legacy_lookup,
            canonical_path=canonical,
            bus_aliases=aliases,
            subpart_first_id=subpart_first_id,
            subpart_id_separator=subpart_id_separator,
            legacy_unit_lookup=legacy_unit_lookup,
        )
        for i, sg in enumerate(cs.subgraphs):
            for c in sg.coords:
                cs.coord_to_sg[c] = i
        # Bus subgraphs — built post-compile so the cross-sheet merge
        # can pair bus-form sheet_pins / hier_labels by chosen_name and
        # promote per-member nets to the parent bus's chosen-name. We
        # rebuild rather than thread state out of compile_sheet_subgraphs
        # to keep that API focused; the cost is one extra pass per sheet.
        cs.bus_subgraphs = build_bus_subgraphs(cs.schematic, aliases)
        cs.bus_member_wire_sg = _map_bus_members_to_wire_sgs(cs)
    # Stash the merged alias map on the root sheet so the cross-sheet
    # bus merge can expand the winning bus driver's label against the
    # same alias dictionary every sheet's compile used.
    if out:
        out[0].bus_aliases_design = aliases
    return out


def _map_bus_members_to_wire_sgs(cs: CompiledSheet) -> List[Dict[str, int]]:
    """For each bus subgraph, return ``{member_name: wire_sg_idx}``.

    Two seeding sources contribute to the mapping, matching KiCad's
    ``CONNECTION_GRAPH::propagateToNeighbors`` behaviour:

    1. **Bus-entry taps**: each ``tap_wire_coord`` (the wire-side end
       of a bus_entry) lands inside a wire subgraph; its LOCAL_LABEL
       whose text matches a bus member tells us which member that wire
       carries.
    2. **Name-only joins**: any wire subgraph on the same sheet with a
       LOCAL_LABEL or HIER_LABEL whose text equals a bus member name
       — even without a physical bus_entry — is treated as carrying
       that bus member. This is how a sheet that only declares the
       bus through a ``(hierarchical_label "FOO[0..N]" …)`` interface
       (no actual bus drawn inside) still gets its local labels
       ``FOO0…FOON`` merged into the bus's cross-sheet member net.
    """
    out: List[Dict[str, int]] = []
    # Pre-index every wire subgraph on this sheet by its label text so
    # the name-only join is O(N+M) rather than O(N*M*L).
    label_to_sg: Dict[str, int] = {}
    for sg_i, sg in enumerate(cs.subgraphs):
        for ld in sg.label_drivers:
            if ld.kind not in (
                KiCadDriverKind.LOCAL_LABEL,
                KiCadDriverKind.HIER_LABEL,
            ):
                continue
            text = ld.text or ""
            if text:
                label_to_sg.setdefault(canonical_bus_member_name(text), sg_i)
    for bsg in cs.bus_subgraphs:
        member_by_canonical: Dict[str, str] = {}
        for member in bsg.members:
            member_by_canonical.setdefault(canonical_bus_member_name(member), member)
        per_bus: Dict[str, int] = {}
        # 1. Bus-entry taps.
        for tap in bsg.tap_wire_coords:
            wire_sg_idx = cs.coord_to_sg.get(tap)
            if wire_sg_idx is None:
                continue
            wsg = cs.subgraphs[wire_sg_idx]
            for ld in wsg.label_drivers:
                if ld.kind != KiCadDriverKind.LOCAL_LABEL:
                    continue
                member = member_by_canonical.get(
                    canonical_bus_member_name(ld.text or "")
                )
                if member is not None:
                    per_bus.setdefault(member, wire_sg_idx)
                    break
        # 2. Name-only joins: pull any wire subgraph on this sheet
        # whose LOCAL/HIER_LABEL text equals a bus member.
        for m in bsg.members:
            if m in per_bus:
                continue
            sg_idx = label_to_sg.get(canonical_bus_member_name(m))
            if sg_idx is not None:
                per_bus[m] = sg_idx
        out.append(per_bus)
    return out


# ---------------------------------------------------------------------------
# Cross-sheet merge — union-find over (sheet_index, sg_index) pairs
# ---------------------------------------------------------------------------


def _make_union_find(n: int) -> Tuple[List[int], List[int]]:
    return list(range(n)), [0] * n


def _uf_find(parent: List[int], k: int) -> int:
    while parent[k] != k:
        parent[k] = parent[parent[k]]
        k = parent[k]
    return k


def _uf_union(parent: List[int], rank: List[int], a: int, b: int) -> None:
    ra, rb = _uf_find(parent, a), _uf_find(parent, b)
    if ra == rb:
        return
    if rank[ra] < rank[rb]:
        ra, rb = rb, ra
    parent[rb] = ra
    if rank[ra] == rank[rb]:
        rank[ra] += 1


def _flatten(
    compiled: List[CompiledSheet],
) -> Tuple[List[Tuple[int, int]], Dict[Tuple[int, int], int]]:
    """Number every (sheet_idx, sg_idx) pair sequentially.

    Returns ``(flat_keys, key_to_idx)``. ``flat_keys[i]`` is the
    ``(sheet_idx, sg_idx)`` tuple at flat index ``i``;
    ``key_to_idx[(sheet_idx, sg_idx)]`` is the inverse mapping.
    """
    flat: List[Tuple[int, int]] = []
    idx: Dict[Tuple[int, int], int] = {}
    for s_i, cs in enumerate(compiled):
        for g_i, _ in enumerate(cs.subgraphs):
            idx[(s_i, g_i)] = len(flat)
            flat.append((s_i, g_i))
    return flat, idx


def merge_design_nets(compiled: List[CompiledSheet]) -> List[KiCadNet]:
    """Cross-sheet union + name + materialise into :class:`KiCadNet` list.

    Merge rules:

    1. Each ``SchSheet`` pin on a parent's compiled subgraph pairs
       with the child schematic's ``hierarchical_label`` of the same
       text → union those subgraphs.
    2. All subgraphs driven by a ``GLOBAL_LABEL`` with the same text →
       union.
    3. All subgraphs driven by a global ``power_pin`` with the same
       value → union.

    After merging, each merged group's nets are named via
    :func:`name_net` using the highest-priority driver across the
    group, with sheet path taken from the *first* sheet (in
    discovery order) that contributes a driver.
    """
    flat_keys, key_to_idx = _flatten(compiled)
    n = len(flat_keys)
    parent, rank = _make_union_find(n)

    # ---- 1. sheet_pin ↔ hier_label pairing --------------------------------
    # For each parent CompiledSheet, walk its SchSheet placements; for
    # each pin on those placements, find:
    #   (a) the parent subgraph that contains the pin's coord
    #   (b) the child CompiledSheet (whose .parent_sheet is this SchSheet)
    #   (c) the child subgraph driven by a hier_label of matching name
    sheet_to_index = {id(cs): s_i for s_i, cs in enumerate(compiled)}
    for s_i, parent_cs in enumerate(compiled):
        for child_cs in compiled:
            if child_cs.parent is not parent_cs:
                continue
            sheet = child_cs.parent_sheet
            if sheet is None:
                continue
            child_idx = sheet_to_index[id(child_cs)]
            # Build a name → child-subgraph index lookup once.
            hier_by_name: Dict[str, int] = {}
            for g_i, sg in enumerate(child_cs.subgraphs):
                for ld in sg.label_drivers:
                    if ld.kind == KiCadDriverKind.HIER_LABEL:
                        hier_by_name.setdefault(ld.text, g_i)
            # Walk this sheet placeholder's pins.
            from .kicad_schematic_connectivity import snap_mm_to_iu
            for pin in sheet.pins:
                coord = snap_mm_to_iu(pin.at_x, pin.at_y)
                parent_g = parent_cs.coord_to_sg.get(coord)
                if parent_g is None:
                    continue
                child_g = hier_by_name.get(pin.name)
                if child_g is None:
                    continue
                _uf_union(
                    parent, rank,
                    key_to_idx[(s_i, parent_g)],
                    key_to_idx[(child_idx, child_g)],
                )

    # ---- 2. Cross-sheet global label merge --------------------------------
    by_global_text: Dict[str, List[int]] = {}
    for s_i, cs in enumerate(compiled):
        for g_i, sg in enumerate(cs.subgraphs):
            for ld in sg.label_drivers:
                if ld.kind == KiCadDriverKind.GLOBAL_LABEL:
                    by_global_text.setdefault(ld.text, []).append(
                        key_to_idx[(s_i, g_i)])
    for group in by_global_text.values():
        for k in group[1:]:
            _uf_union(parent, rank, group[0], k)

    # ---- 3. Cross-sheet global power-pin merge ----------------------------
    by_power_value: Dict[str, List[int]] = {}
    for s_i, cs in enumerate(compiled):
        for g_i, sg in enumerate(cs.subgraphs):
            for pd in sg.pin_drivers:
                if pd.is_power and pd.priority == KiCadDriverPriority.GLOBAL_POWER_PIN:
                    by_power_value.setdefault(pd.power_value, []).append(
                        key_to_idx[(s_i, g_i)])
    for group in by_power_value.values():
        for k in group[1:]:
            _uf_union(parent, rank, group[0], k)

    # ---- 4. Cross-sheet BUS member promotion -----------------------------
    # Pair parent bus subgraphs (containing a bus-form sheet_pin) with
    # child bus subgraphs (containing a matching hier_label) via a bus-
    # level union-find. Resolve the winning bus driver across each bus-
    # UF group, expand its bus expression, then for each member position
    # union the wire subgraphs that tap that member across all bus
    # subgraphs in the group. Each merged wire group also gets an
    # "override" candidate carrying the winning bus's chosen-name-at-
    # member so the net is named e.g. ``/top.x`` instead of ``/a/x``.
    overrides_by_flat: Dict[int, List[_BusMemberOverride]] = {}
    _merge_buses_cross_sheet(
        compiled, sheet_to_index,
        parent, rank, key_to_idx, overrides_by_flat,
    )

    # ---- Materialise merged nets ------------------------------------------
    return _materialise_nets(compiled, flat_keys, parent, overrides_by_flat)


@dataclass
class _BusMemberOverride:
    """A synthetic driver injected by cross-sheet bus member promotion.

    ``text`` is the winning bus's chosen-name expanded at this member
    position (e.g. ``"top.x"``). The ``priority`` / ``kind`` come from
    the winning bus driver (typically the parent's LOCAL_LABEL bus
    label, the parent's SHEET_PIN, or the child's HIER_LABEL — whichever
    wins :func:`compareDrivers`). ``depth`` is the path-depth of the
    sheet that owns the winning driver (used as the candidate tiebreak
    in :func:`_materialise_nets`). ``sheet_path_uuid`` is the canonical
    sheet path supplied to :func:`name_net` so the emitted net name
    carries the expected sheet prefix (e.g. ``"/"`` for a root bus).
    """

    text: str
    priority: KiCadDriverPriority
    kind: KiCadDriverKind
    depth: int
    sheet_path: str  # human-readable sheet path used by name_net


def _merge_buses_cross_sheet(
    compiled: List[CompiledSheet],
    sheet_to_index: Dict[int, int],
    parent: List[int],
    rank: List[int],
    key_to_idx: Dict[Tuple[int, int], int],
    overrides_by_flat: Dict[int, List[_BusMemberOverride]],
) -> None:
    """Cross-sheet + within-sheet bus member-level union-find.

    Operates over ``(sheet_idx, bus_sg_idx, member_pos)`` tuples — each
    represents one bus member instance in the design. Two unions:

    * **Cross-sheet**: a parent bus subgraph (containing a bus-form
      sheet_pin) unions with the matching child bus subgraph (containing
      a hier_label of identical text) **by position** for every shared
      position index.
    * **Within-sheet**: two bus subgraphs on the same sheet whose
      expanded member sets share a name union the corresponding member
      positions by name. This is how prefix-bus-alias chains like
      ``test{a_xyz}`` ↔ ``test{b_x}`` propagate ``test.x`` between
      physically-separate buses on the same sheet.

    Each member-UF group then resolves a winning bus driver
    (``compareDrivers``: priority → depth → name) and:

    * unions the wire subgraphs tapped at the matching member position
      across the group (in the main wire UF), and
    * stamps an override on each tap so :func:`_materialise_nets` names
      the merged net using the winning driver's expanded member at the
      winning sheet's path.
    """
    from .kicad_schematic_connectivity import snap_mm_to_iu

    # Flatten member positions: (sheet_idx, bus_sg_idx, member_pos).
    member_flat: List[Tuple[int, int, int]] = []
    member_idx: Dict[Tuple[int, int, int], int] = {}
    for s_i, cs in enumerate(compiled):
        for b_i, bsg in enumerate(cs.bus_subgraphs):
            for pos in range(len(bsg.members)):
                member_idx[(s_i, b_i, pos)] = len(member_flat)
                member_flat.append((s_i, b_i, pos))
    if not member_flat:
        return

    m_parent, m_rank = _make_union_find(len(member_flat))

    # --- 4a. Within-sheet member-name overlap -------------------------
    # KiCad treats two bus subgraphs on the same sheet whose member
    # names overlap as referring to the same logical net at every
    # shared name (e.g. ``test{a_xyz}.test.x`` ≡ ``test{b_x}.test.x``).
    for s_i, cs in enumerate(compiled):
        name_to_pairs: Dict[str, List[Tuple[int, int]]] = {}
        for b_i, bsg in enumerate(cs.bus_subgraphs):
            for pos, m in enumerate(bsg.members):
                name_to_pairs.setdefault(
                    canonical_bus_member_name(m),
                    [],
                ).append((b_i, pos))
        for pairs in name_to_pairs.values():
            if len(pairs) < 2:
                continue
            base = member_idx[(s_i, pairs[0][0], pairs[0][1])]
            for b_i, pos in pairs[1:]:
                _uf_union(m_parent, m_rank, base, member_idx[(s_i, b_i, pos)])

    # --- 4b. Cross-sheet sheet_pin ↔ hier_label (pair by member NAME) ---
    # KiCad pairs members across a sheet boundary by *name* (matching
    # ``SCH_CONNECTION::IsSubsetOf`` semantics): a parent's ``{SCL SDA}``
    # paired with a child's ``{SDA SCL}`` connects SCL↔SCL and SDA↔SDA
    # regardless of position. Members that exist on only one side stay
    # un-paired.
    for s_i, parent_cs in enumerate(compiled):
        for child_cs in compiled:
            if child_cs.parent is not parent_cs:
                continue
            sheet = child_cs.parent_sheet
            if sheet is None:
                continue
            child_idx = sheet_to_index[id(child_cs)]
            # Index child bus subgraphs by HIER_LABEL bus driver text.
            hier_bus_by_name: Dict[str, int] = {}
            for b_i, bsg in enumerate(child_cs.bus_subgraphs):
                for bd in bsg.drivers:
                    if bd.kind != KiCadDriverKind.HIER_LABEL:
                        continue
                    if is_bus_label(bd.text):
                        hier_bus_by_name.setdefault(bd.text, b_i)
            for pin in sheet.pins:
                pin_name = pin.name or ""
                if not is_bus_label(pin_name):
                    continue
                pin_coord = snap_mm_to_iu(pin.at_x, pin.at_y)
                parent_b: Optional[int] = None
                for b_i, bsg in enumerate(parent_cs.bus_subgraphs):
                    if pin_coord in bsg.coords:
                        parent_b = b_i
                        break
                if parent_b is None:
                    continue
                child_b = hier_bus_by_name.get(pin_name)
                if child_b is None:
                    continue
                parent_bsg = parent_cs.bus_subgraphs[parent_b]
                child_bsg = child_cs.bus_subgraphs[child_b]
                # Hybrid pairing:
                #   1. Pair members that share a name (handles
                #      ``{SCL SDA}`` ↔ ``{SDA SCL}`` order-reversed
                #      groups in group_bus_matching).
                #   2. Then positionally pair the remaining unmatched
                #      members on each side (handles cases like
                #      ``top{a_xyz}`` ↔ ``{a_xyz}`` where alias members
                #      differ only by the parent's prefix; KiCad joins
                #      by alias index when no names overlap).
                child_pos_by_name: Dict[str, int] = {}
                for c_pos, c_name in enumerate(child_bsg.members):
                    child_pos_by_name.setdefault(
                        canonical_bus_member_name(c_name),
                        c_pos,
                    )
                matched_parent: set[int] = set()
                matched_child: set[int] = set()
                for p_pos, p_name in enumerate(parent_bsg.members):
                    c_pos = child_pos_by_name.get(
                        canonical_bus_member_name(p_name)
                    )
                    if c_pos is None or c_pos in matched_child:
                        continue
                    a = member_idx[(s_i, parent_b, p_pos)]
                    b = member_idx[(child_idx, child_b, c_pos)]
                    _uf_union(m_parent, m_rank, a, b)
                    matched_parent.add(p_pos)
                    matched_child.add(c_pos)
                # Positional fallback over un-matched leftovers.
                unmatched_parent = [
                    p_pos for p_pos in range(len(parent_bsg.members))
                    if p_pos not in matched_parent
                ]
                unmatched_child = [
                    c_pos for c_pos in range(len(child_bsg.members))
                    if c_pos not in matched_child
                ]
                for p_pos, c_pos in zip(unmatched_parent, unmatched_child):
                    a = member_idx[(s_i, parent_b, p_pos)]
                    b = member_idx[(child_idx, child_b, c_pos)]
                    _uf_union(m_parent, m_rank, a, b)

    # --- 4c. Resolve winner + promote per member-UF group ------------
    m_groups: Dict[int, List[int]] = {}
    for k in range(len(member_flat)):
        r = _uf_find(m_parent, k)
        m_groups.setdefault(r, []).append(k)

    for group in m_groups.values():
        # compareDrivers across all bus drivers attached to bus subgraphs
        # touching this group's member positions. Each candidate carries
        # the (bus subgraph, member position) it represents so we can
        # recover the winning member's NAME via ``bsg.members[pos]``.
        candidates: List[Tuple[
            int, int, str, str, int,
            KiCadDriverKind, KiCadDriverPriority, str,
            BusSubgraph, int,
        ]] = []
        for k in group:
            s_i, b_i, pos = member_flat[k]
            cs = compiled[s_i]
            bsg = cs.bus_subgraphs[b_i]
            depth = cs.sheet_path_human.count("/")
            for idx, bd in enumerate(bsg.drivers):
                if not is_bus_label(bd.text):
                    continue
                candidates.append((
                    -int(bd.priority), depth,
                    cs.sheet_path_human, bd.text, idx,
                    bd.kind, bd.priority, cs.sheet_path_human,
                    bsg, pos,
                ))
        if not candidates:
            continue
        # Tie-break order: priority (desc) → depth (asc) → sheet_path
        # (asc) → driver name (asc) → drivers insertion order. The
        # sheet_path tiebreaker matches KiCad's de-facto behaviour
        # where the first-processed sibling subgraph (sheet ordering)
        # provides the canonical bus-member name — see prefix_bus_alias
        # where Subsheet 1 (with HIER_LABEL ``Foo{Bus1}``) wins over
        # Subsheet2 (``Bar{Bus1}``) despite "Bar" < "Foo" alphabetically.
        candidates.sort(key=lambda t: (t[0], t[1], t[2], t[3], t[4]))
        best = candidates[0]
        win_kind = best[5]
        win_prio = best[6]
        win_sp_human = best[7]
        win_bsg = best[8]
        win_pos = best[9]
        win_depth = best[1]
        if win_pos >= len(win_bsg.members):
            continue
        member_name = win_bsg.members[win_pos]

        # Collect tap wire subgraphs and union in the main wire UF.
        wire_flat_keys: List[int] = []
        for k in group:
            s_i, b_i, pos = member_flat[k]
            cs = compiled[s_i]
            bsg = cs.bus_subgraphs[b_i]
            if pos >= len(bsg.members):
                continue
            own_member = bsg.members[pos]
            wire_sg_idx = cs.bus_member_wire_sg[b_i].get(own_member)
            if wire_sg_idx is None:
                continue
            wire_flat_keys.append(key_to_idx[(s_i, wire_sg_idx)])
        if not wire_flat_keys:
            continue
        base_key = wire_flat_keys[0]
        for k in wire_flat_keys[1:]:
            _uf_union(parent, rank, base_key, k)
        override = _BusMemberOverride(
            text=member_name,
            priority=win_prio,
            kind=win_kind,
            depth=win_depth,
            sheet_path=win_sp_human,
        )
        for k in wire_flat_keys:
            overrides_by_flat.setdefault(k, []).append(override)


def _sheet_pin_suffix_indices(compiled: List[CompiledSheet]) -> Dict[int, int]:
    """Return ``id(_LabelDriver) -> source-order suffix index`` for sheet pins.

    Hidden/dropped duplicate weak sheet-pin peers can still affect the suffix
    on the one emitted terminal-bearing net. Using schematic discovery order
    keeps that single visible suffix stable when final materialisation order is
    spatially different. Visible duplicate suffix ownership is non-semantic and
    canonicalized by the L3 oracle tests.
    """
    grouped: Dict[str, List[Tuple[int, int, int]]] = {}
    fallback_order = 0
    for cs in compiled:
        for sg in cs.subgraphs:
            for ld in sg.label_drivers:
                if ld.kind != KiCadDriverKind.SHEET_PIN:
                    continue
                fake = Subgraph(
                    chosen_priority=KiCadDriverPriority.SHEET_PIN,
                    chosen_kind=KiCadDriverKind.SHEET_PIN,
                    chosen_name=ld.text,
                )
                base_name, _auto = name_net(fake, sheet_path=cs.sheet_path_human)
                source_order = int(getattr(ld, "source_order", fallback_order) or 0)
                grouped.setdefault(base_name, []).append((
                    source_order,
                    fallback_order,
                    id(ld),
                ))
                fallback_order += 1

    out: Dict[int, int] = {}
    for entries in grouped.values():
        entries.sort(key=lambda t: (t[0], t[1]))
        for suffix_idx, (_source_order, _fallback, label_id) in enumerate(entries):
            out[label_id] = suffix_idx
    return out


def _materialise_nets(
    compiled: List[CompiledSheet],
    flat_keys: List[Tuple[int, int]],
    uf_parent: List[int],
    overrides_by_flat: Optional[Dict[int, List["_BusMemberOverride"]]] = None,
) -> List[KiCadNet]:
    """Walk merged groups, pick driver, emit terminals, assign codes."""
    # Group by union-find root, preserving discovery order of the
    # smallest member of each group.
    groups: Dict[int, List[int]] = {}
    first_seen: Dict[int, int] = {}
    for k in range(len(flat_keys)):
        r = _uf_find(uf_parent, k)
        groups.setdefault(r, []).append(k)
        first_seen.setdefault(r, k)

    # Sort groups by the order their first member appears.
    ordered_roots = sorted(groups.keys(), key=lambda r: first_seen[r])

    nets: List[KiCadNet] = []
    code = 1
    sheet_pin_suffix_indices = _sheet_pin_suffix_indices(compiled)
    seen_sheet_pin_net_names: Dict[str, int] = {}
    for r in ordered_roots:
        group = groups[r]
        # Combine label / pin drivers across all subgraphs. Track each
        # subgraph's sheet_path_human alongside its drivers so we can
        # later pick the sheet_path of the subgraph that contributed
        # the chosen driver (matches kicad-cli's ``Connection::Sheet()``
        # of the resolved driver — the child sheet for HIER_LABEL, the
        # parent for SHEET_PIN, etc.).
        merged = Subgraph()
        merged_graphical = _empty_graphical_map()
        member_sheet_paths: List[str] = []
        for k in group:
            s_i, g_i = flat_keys[k]
            cs = compiled[s_i]
            sg = cs.subgraphs[g_i]
            merged.coords |= sg.coords
            merged.label_drivers.extend(sg.label_drivers)
            merged.pin_drivers.extend(sg.pin_drivers)
            _merge_graphical_ids(merged_graphical, sg.graphical)
            if sg.no_connect:
                merged.no_connect = True
            member_sheet_paths.append(cs.sheet_path_human)

        # Skip groups that have no drivers AND no pins (truly empty).
        if not merged.pin_drivers and not merged.label_drivers:
            continue

        # Sheet-aware driver resolution — mirrors kicad-cli's
        # ``CONNECTION_GRAPH::compareDrivers`` (connection_graph.cpp):
        # priority (high wins) → sheet-path depth (shallower wins,
        # since SHEET_PIN/HIER_LABEL bridges act as renames climbing
        # toward the root) → alphabetical name → insertion order.
        # Replaces the single-sheet ``_resolve_driver`` here so the
        # cross-sheet merge naming matches kicad-cli even when the
        # group spans multiple hierarchy levels (e.g. SUB_OUTPUT
        # bridging through SUBSUB_OUTPUT).
        # Candidate sort key:
        #   0 -priority   (higher priority wins)
        #   1 depth       (shallower wins — mirrors KiCad's
        #                  ``shorterPath`` rule at
        #                  ``connection_graph.cpp:3188``)
        #   2 shape_rank  (SHEET_PIN-vs-SHEET_PIN: L_OUTPUT shape wins —
        #                  mirrors compareDrivers rule 4 at
        #                  ``connection_graph.cpp:193-206``. Non-sheet-pin
        #                  candidates always get rank 1 so the dimension
        #                  is a no-op outside priority == SHEET_PIN.)
        #   3 implicit    (explicit power symbols beat implicit hidden
        #                  power pins when both carry GLOBAL_POWER_PIN)
        #   4 full_name   (alphabetical on sheet_path + label_text — this
        #                  is KiCad's post-propagation rule (e) at
        #                  ``connection_graph.cpp:3196-3203``: among
        #                  same-strength, same-priority candidates with
        #                  equal-or-shorter paths, the alphabetically
        #                  lower CONNECTION NAME wins. CONNECTION NAME
        #                  bakes in the sheet path, so we must compare
        #                  the concatenated string — not the label text
        #                  alone. Fixes the LED daisy-chain where
        #                  HIER_LABELs ``DO`` at ``/LED_Controller2/``
        #                  and ``DIN`` at ``/LED_Controller3/`` tie on
        #                  priority+depth; full-name compare picks
        #                  ``/LED_Controller2/DO`` because
        #                  ``"/LED_Controller2/DO" < "/LED_Controller3/DIN"``.)
        #   5 sheet_path  (legacy secondary tiebreak — now redundant
        #                  with full_name but kept for stability)
        #   6 idx         (insertion order — final stable tiebreak)
        candidates: List[Tuple[
            int, int, int, int, str, str, int, KiCadDriverKind, str, str,
            Optional[int],
        ]] = []
        for k, sp_human in zip(group, member_sheet_paths):
            s_i, g_i = flat_keys[k]
            sg = compiled[s_i].subgraphs[g_i]
            # Depth: root "/" = 1 slash, "/sub/" = 2 slashes, etc.
            depth = sp_human.count("/")
            for idx, ld in enumerate(sg.label_drivers):
                shape_rank = (
                    0 if ld.kind == KiCadDriverKind.SHEET_PIN
                    and ld.shape == "output"
                    else 1
                )
                # KiCad's CONNECTION_NAME for global labels is the bare
                # label text (global labels are sheet-independent); for
                # hier/local labels and sheet pins it's the sheet-scoped
                # name. Only sheet-scoped candidates use sp_human in the
                # alphabetic tiebreak.
                if ld.kind == KiCadDriverKind.GLOBAL_LABEL:
                    full_name = ld.name
                else:
                    full_name = sp_human + ld.name
                candidates.append((
                    -int(ld.priority), depth, shape_rank, 0,
                    full_name, sp_human, idx,
                    ld.kind, ld.name, sp_human,
                    id(ld) if ld.kind == KiCadDriverKind.SHEET_PIN else None,
                ))
            pin_offset = len(sg.label_drivers)
            for idx, pd in enumerate(sg.pin_drivers):
                disp = pd.power_value if pd.is_power and pd.power_value else pd.name
                # GLOBAL/LOCAL power pins compare on bare power_value
                # (KiCad's CONNECTION_NAME for a power pin is the
                # symbol value with no sheet path) so e.g. "+5V" beats
                # "VCC" globally regardless of which sub-sheet the
                # contributing pin sits on. PIN-priority candidates
                # (real component pins) still compare on sheet-scoped
                # full names.
                if pd.is_power and pd.priority in (
                    KiCadDriverPriority.GLOBAL_POWER_PIN,
                    KiCadDriverPriority.LOCAL_POWER_PIN,
                ):
                    full_name = disp
                else:
                    full_name = sp_human + disp
                implicit_rank = 1 if getattr(pd, "is_implicit_hidden_power", False) else 0
                candidates.append((
                    -int(pd.priority), depth, 1, implicit_rank,
                    full_name, sp_human, pin_offset + idx,
                    _pin_kind(pd.priority), disp, sp_human, None,
                ))
        # Inject bus-member override candidates so cross-sheet bus
        # promotion can win name resolution. Per KiCad's
        # ``propagateToNeighbors`` rule, the bus driver's chosen member
        # name *overrides* wire-side drivers below GLOBAL_POWER_PIN;
        # only GLOBAL_POWER_PIN / GLOBAL labels on the wire defeat the
        # bus promotion. Encode this by giving the override an effective
        # sort priority of ``max(bus_driver_priority, LOCAL_POWER_PIN)``
        # — beats LOCAL_LABEL (priority 4) but loses to GLOBAL_POWER_PIN
        # (priority 6) and GLOBAL (priority 7). The override's
        # ``sheet_path`` is the winning bus driver's human-readable
        # path, kept in slot 6 alongside other candidates.
        if overrides_by_flat:
            inj_idx = 0
            for k in group:
                for ov in overrides_by_flat.get(k, ()):
                    effective_prio = max(
                        int(ov.priority),
                        int(KiCadDriverPriority.LOCAL_POWER_PIN),
                    )
                    candidates.append((
                        -effective_prio, ov.depth, 1, 0,
                        ov.text, ov.sheet_path, inj_idx,
                        ov.kind, ov.text, ov.sheet_path, None,
                    ))
                    inj_idx += 1

        if not candidates:
            merged.chosen_priority = KiCadDriverPriority.NONE
            merged.chosen_kind = KiCadDriverKind.NONE
            merged.chosen_name = ""
            chosen_sheet_path = "/"
            chosen_sheet_pin_id = None
        else:
            candidates.sort(
                key=lambda t: (t[0], t[1], t[2], t[3], t[4], t[5], t[6])
            )
            best = candidates[0]
            merged.chosen_priority = KiCadDriverPriority(-best[0])
            merged.chosen_kind = best[7]
            merged.chosen_name = best[8]
            chosen_sheet_path = best[9]
            chosen_sheet_pin_id = best[10]

        net_name, auto_named = name_net(merged, sheet_path=chosen_sheet_path)
        # KiCad appends ``_N`` for repeated weak sheet-pin nets. Real
        # sheet-pin drivers use a source-order suffix so hidden/dropped
        # duplicate peers do not make a single visible net depend on final
        # materialisation order; synthetic sheet-pin-like overrides fall
        # back to materialisation order. Strong labels with the same visible
        # name should already have merged; suffixing those would hide a real
        # connectivity gap.
        if merged.chosen_kind == KiCadDriverKind.SHEET_PIN:
            suffix_index = (
                sheet_pin_suffix_indices.get(chosen_sheet_pin_id)
                if chosen_sheet_pin_id is not None
                else None
            )
            if suffix_index is not None:
                if suffix_index:
                    net_name = f"{net_name}_{suffix_index}"
            else:
                net_name_count = seen_sheet_pin_net_names.get(net_name, 0)
                seen_sheet_pin_net_names[net_name] = net_name_count + 1
                if net_name_count:
                    net_name = f"{net_name}_{net_name_count}"

        net = KiCadNet(
            name=net_name,
            code=code,
            driver_priority=int(merged.chosen_priority),
            driver_kind=str(merged.chosen_kind),
            auto_named=auto_named,
            graphical=merged_graphical,
        )
        # Terminals — sorted by (designator, pin_number).
        ordered_pins = sorted(
            merged.pin_drivers,
            key=lambda p: (p.designator, p.pin_number),
        )
        seen: set = set()
        for pd in ordered_pins:
            if not pd.designator:
                continue
            # Mirrors KiCad's filter in
            # ``netlist_exporter_xml.cpp::writeListOfNets`` (line 1247):
            # ``if refText[0] == '#' continue;``. This drops both
            # ``power:`` symbols (``#PWR0101``) and ``PWR_FLAG``
            # placements (``#FLG01``) from the net node list — they
            # influence net naming but are virtual connectors, not real
            # terminals.
            if pd.designator.startswith("#"):
                continue
            key = (pd.designator, pd.pin_number)
            if key in seen:
                continue
            seen.add(key)
            # Find the sheet path of the contributing subgraph.
            owning_sheet_path = "/"
            for k in group:
                s_i, g_i = flat_keys[k]
                if pd in compiled[s_i].subgraphs[g_i].pin_drivers:
                    owning_sheet_path = compiled[s_i].sheet_path
                    break
            net.add_terminal(KiCadNetlistTerminal(
                designator=pd.designator,
                pin=pd.pin_number,
                pin_name=pd.pin_name,
                pin_type=pd.pin_type,
                sheet_path=owning_sheet_path,
                source_pin_id=pd.source_uuid,
                svg_id=pd.pin_svg_uuid or pd.svg_uuid,
            ))
        for k in group:
            s_i, g_i = flat_keys[k]
            cs = compiled[s_i]
            sg = cs.subgraphs[g_i]
            for ld in sg.label_drivers:
                _append_unique_endpoint(
                    net,
                    _label_driver_endpoint(ld, source_sheet=cs.sheet_path),
                )
            for pd in sg.pin_drivers:
                _append_unique_endpoint(
                    net,
                    _power_pin_endpoint(pd, source_sheet=cs.sheet_path),
                )
        # KiCad's writeListOfNets only emits a <net> element when at
        # least one non-``#`` pin was added (``added`` flag in
        # netlist_exporter_xml.cpp:1250). Nets composed entirely of
        # power-symbol / PWR_FLAG pins are dropped.
        if not net.terminals:
            continue
        nets.append(net)
        code += 1

    return nets


# ---------------------------------------------------------------------------
# Component and libpart collation
# ---------------------------------------------------------------------------
#
# Walks every ``CompiledSheet`` to materialise the ``(components ...)`` and
# ``(libparts ...)`` blocks the kicadsexpr emit needs. The walk
# mirrors KiCad's own logic in ``netlist_exporter_xml.cpp::makeListOfNets``:
#
# * Components are deduped by symbol UUID — a multi-unit symbol placed on
#   different sheets shows up once per *placement*, not once per unit. The
#   ``instance_uuid`` field carries the per-placement UUID so the emit
#   matches kicad-cli's ``(tstamps ...)`` line.
# * Libparts are deduped by ``(lib, part)`` across every loaded schematic's
#   ``lib_symbols`` cache. Pin metadata is taken from the union of the
#   library symbol's subsymbols (KiCad emits one pin per number per
#   libpart, regardless of unit).
# * Power symbols (``LibSymbol.power == True`` or ``lib_id`` starting with
#   ``"power:"``) are still emitted in both blocks — kicad-cli does the
#   same; the libpart row carries the power-symbol metadata so downstream
#   tools (BOM, schematic preview) can identify them.

# Standard property keys that are surfaced as top-level fields on a
# ``(comp ...)`` rather than inside a ``(property ...)`` block.
_STANDARD_COMPONENT_FIELDS = ("Reference", "Value", "Footprint", "Datasheet")


# ---------------------------------------------------------------------------
# Component-value text-variable expansion
# ---------------------------------------------------------------------------
#
# KiCad's ``ResolveTextVar`` resolves ``${VAR}`` tokens against the
# symbol's own properties first, then falls back to project-scoped
# ``text_variables``. Lookups are case-insensitive and unknown tokens
# pass through unchanged. We mirror the same precedence here when
# emitting component fields so a top-level ``value`` like
# ``${ALTIUM_VALUE}`` lands as the resolved string in the netlist
# (matches kicad-cli's emit).

_NETLIST_VAR_RE = re.compile(r"\$\{([^}]*)\}")
_NETLIST_VAR_MAX_DEPTH = 10


def _expand_property_vars(
    text: str,
    sym: object,
    project_vars: Dict[str, str],
    *,
    skip_key: str = "",
) -> str:
    """Resolve ``${VAR}`` tokens in ``text`` using symbol properties + project vars.

    ``skip_key`` is the property name currently being expanded — passed
    in so the recursive expansion doesn't loop on a ``Value =
    ${VALUE}`` self-reference. Lookup is case-insensitive against
    ``sym.properties`` first, then ``project_vars``. Unknown tokens are
    left in place; the loop terminates at a fixed point or after
    :data:`_NETLIST_VAR_MAX_DEPTH` passes.
    """
    if not text or "${" not in text:
        return text or ""

    sym_props: Dict[str, str] = {}
    for prop in getattr(sym, "properties", ()) or ():
        pkey = getattr(prop, "key", "")
        if not pkey:
            continue
        if skip_key and pkey.lower() == skip_key.lower():
            continue
        sym_props[pkey.lower()] = getattr(prop, "value", "") or ""

    proj_lc = {str(k).lower(): str(v) for k, v in (project_vars or {}).items()}

    def _resolve(name: str) -> Optional[str]:
        key = name.strip().lower()
        if key in sym_props:
            return sym_props[key]
        if key in proj_lc:
            return proj_lc[key]
        return None

    def _sub(m: "re.Match[str]") -> str:
        resolved = _resolve(m.group(1))
        if resolved is None:
            return m.group(0)
        return resolved

    out = text
    for _ in range(_NETLIST_VAR_MAX_DEPTH):
        nxt = _NETLIST_VAR_RE.sub(_sub, out)
        if nxt == out:
            break
        out = nxt
    return out


def _split_lib_id(lib_id: str) -> Tuple[str, str]:
    """Split a ``"Lib:Part"`` lib_id. Return ``("", lib_id)`` when no colon."""
    if ":" in lib_id:
        head, tail = lib_id.split(":", 1)
        return head, tail
    return "", lib_id


def _natural_pin_key(num: str) -> Tuple[int, object]:
    """Sort pin numbers numerically when possible, alphabetically otherwise."""
    try:
        return (0, int(num))
    except (TypeError, ValueError):
        return (1, str(num))


def collect_design_components(
    compiled: List[CompiledSheet],
    project_vars: Optional[Dict[str, str]] = None,
) -> List[KiCadNetlistComponent]:
    """Walk every compiled sheet, emit one :class:`KiCadNetlistComponent`
    per placed :class:`SchSymbol` *per CompiledSheet*.

    Dedupe key: ``(sym.uuid, cs.sheet_path)``. The same library
    schematic is reused across hierarchical sub-sheet instances, so a
    single :class:`SchSymbol` object lands once per CompiledSheet —
    each placement has its own per-instance reference number stored in
    :attr:`SchSymbol.instances` keyed by sheet path. Synthetic test
    fixtures often skip both UUIDs and the instances block; for those
    we fall back to ``(sym.reference, cs.sheet_path)`` and the bare
    ``sym.reference`` value.
    """
    seen: set = set()
    out: List[KiCadNetlistComponent] = []
    pv: Dict[str, str] = dict(project_vars or {})
    legacy_lookup = _build_legacy_instance_lookup(compiled)
    top_sch = compiled[0].schematic if compiled else None

    for cs in compiled:
        sch = cs.schematic
        if sch is None:
            continue
        for sym in getattr(sch, "symbols", ()):
            if hasattr(sch, "get_lib_symbol_for_symbol"):
                lib_sym = sch.get_lib_symbol_for_symbol(sym)
            elif hasattr(sch, "get_lib_symbol"):
                lib_sym = sch.get_lib_symbol(sym.lib_id)
            else:
                lib_sym = None
            # kicad-cli's netlist export omits power symbols from the
            # components block — their refs are auto-generated bookkeeping
            # ("#PWR0123") that downstream BOM / placement tooling never
            # consumes. Match that behaviour so the kicadsexpr emit is
            # byte-stable against the golden.
            #
            # PWR_FLAG is intentionally *not* a "power symbol" for net
            # naming (see ``_is_power_symbol`` — letting it drive would
            # outrank +5V/GND alphabetically and collapse unrelated nets),
            # but it shares the same components-block omission rule with
            # real power symbols (kicad-cli drops it too).
            if _is_power_symbol(sym, lib_sym) or sym.lib_id == "power:PWR_FLAG":
                continue
            # kicad-cli drops ``(on_board no)`` symbols from the
            # components block. ``dnp`` alone is not enough — symbols
            # with ``dnp yes`` but ``on_board yes`` (e.g. dual-population
            # placements) still appear in the netlist. Pin collection
            # applies the same gate so the emitted net node list does
            # not reference components that KiCad omitted.
            if not getattr(sym, "on_board", True):
                continue

            uid = sym.uuid or ""
            key = (uid or sym.reference, cs.sheet_path)
            if key in seen:
                continue
            seen.add(key)

            lib, part = _split_lib_id(sym.lib_id)

            description = ""
            if lib_sym is not None:
                description = getattr(lib_sym, "description", "") or ""

            # Non-standard properties — preserved verbatim into the comp's
            # ``(property ...)`` blocks (kicad-cli emits user-defined
            # property values literally, no ``${VAR}`` expansion).
            # Reference / Value / Footprint / Datasheet are surfaced as
            # top-level fields on the comp.
            properties: Dict[str, str] = {}
            for prop in getattr(sym, "properties", ()):
                pkey = getattr(prop, "key", "")
                if not pkey or pkey in _STANDARD_COMPONENT_FIELDS:
                    continue
                properties[pkey] = getattr(prop, "value", "") or ""

            canonical = (
                _canonical_instance_path(top_sch, cs.sheet_path)
                if top_sch is not None else None
            )
            reference = _resolve_instance_reference(
                sym, cs.sheet_path,
                legacy_lookup=legacy_lookup,
                canonical_path=canonical,
            )
            # KiCad drops bookkeeping symbols whose resolved reference starts
            # with "#". This catches custom-library power symbols that do not
            # carry the modern `(power)` token but still use `#PWR` refs.
            if reference.startswith("#"):
                continue
            # Top-level ``value`` is the only comp-row field where
            # kicad-cli applies ``${VAR}`` expansion — resolve against
            # the symbol's own properties first, then the project's
            # ``text_variables``. Footprint / datasheet stay literal
            # (kicad-cli emits them verbatim even when they contain
            # tokens).
            value = _expand_property_vars(
                sym.value, sym, pv, skip_key="Value"
            )

            out.append(KiCadNetlistComponent(
                reference=reference,
                value=value,
                footprint=sym.footprint,
                libsource_lib=lib,
                libsource_part=part,
                libsource_description=description,
                sheet_path_names=cs.sheet_path_human,
                sheet_path_uuids=cs.sheet_path,
                instance_uuid=uid,
                properties=properties,
                in_bom=getattr(sym, "in_bom", True),
                on_board=getattr(sym, "on_board", True),
                dnp=getattr(sym, "dnp", False),
            ))

    return out


def collect_design_libparts(
    compiled: List[CompiledSheet],
) -> List[KiCadLibPart]:
    """Walk every loaded schematic's ``lib_symbols`` cache, emit one
    :class:`KiCadLibPart` per unique ``(lib, part)``.

    Pin list is the union of every subsymbol's pins, deduped by pin
    number with KiCad's natural-numeric ordering. Standard fields
    (Reference, Value, Footprint, Datasheet) are surfaced into
    ``KiCadLibPart.fields``; everything else is dropped (kicad-cli does
    the same — non-standard properties don't roundtrip through the
    libpart block).
    """
    seen: set = set()
    out: List[KiCadLibPart] = []

    for cs in compiled:
        sch = cs.schematic
        if sch is None:
            continue
        lib_symbols = getattr(sch, "lib_symbols", None) or ()
        # ``lib_symbols`` is a flat list of :class:`LibSymbol`; the
        # symbol's ``name`` field carries the full ``"Lib:Part"`` form
        # (or sometimes a bare ``"Part"`` for legacy fixtures — handled
        # by :func:`_split_lib_id`).
        for lib_sym in lib_symbols:
            lib_id = getattr(lib_sym, "name", "") or ""
            if not lib_id:
                continue
            lib, part = _split_lib_id(lib_id)
            key = (lib, part)
            if key in seen:
                continue
            seen.add(key)

            # Standard fields — only emit when set.
            fields: Dict[str, str] = {}
            for fname in _STANDARD_COMPONENT_FIELDS:
                v = ""
                if hasattr(lib_sym, "get_property_value"):
                    v = lib_sym.get_property_value(fname, "") or ""
                if v:
                    fields[fname] = v

            # Pins — combine across subsymbols, dedupe by number.
            pin_seen: set = set()
            pins: List[KiCadLibPartPin] = []
            for sub in getattr(lib_sym, "subsymbols", ()):
                for pin in getattr(sub, "pins", ()):
                    num = _normalize_netlist_pin_number(getattr(pin, "number", "") or "")
                    if not num or num in pin_seen:
                        continue
                    pin_seen.add(num)
                    elec = getattr(pin, "electrical_type", None)
                    pin_type = getattr(elec, "value", None)
                    if pin_type is None:
                        pin_type = str(elec) if elec is not None else ""
                    pins.append(KiCadLibPartPin(
                        number=num,
                        name=getattr(pin, "name", "") or "",
                        pin_type=str(pin_type),
                    ))
            pins.sort(key=lambda p: _natural_pin_key(p.number))

            description = getattr(lib_sym, "description", "") or ""
            docs = getattr(lib_sym, "datasheet", "") or ""

            out.append(KiCadLibPart(
                lib=lib,
                part=part,
                description=description,
                docs=docs,
                footprints_filter=[],
                fields=fields,
                pins=pins,
            ))

    return out


def _design_sheet_records(
    compiled: List[CompiledSheet],
) -> List[KiCadDesignSheet]:
    """Build one :class:`KiCadDesignSheet` per compiled sheet.

    Sheet numbering starts at 1; ``name`` is the human path,
    ``tstamps`` is the canonical UUID path. ``title`` / ``company`` /
    ``revision`` / ``date`` are pulled from the schematic's title block
    when present; otherwise empty strings (the emit normalises empty
    strings to bare ``(title)`` etc., matching kicad-cli).
    """
    out: List[KiCadDesignSheet] = []
    for i, cs in enumerate(compiled, start=1):
        title = company = revision = date = ""
        sch = cs.schematic
        if sch is not None:
            tb = getattr(sch, "title_block", None)
            if tb is not None:
                title = getattr(tb, "title", "") or ""
                company = getattr(tb, "company", "") or ""
                # TitleBlock uses ``rev`` (KiCad's own token); we surface
                # it as ``revision`` on KiCadDesignSheet to match the
                # generic ``netlist_a0`` field naming.
                revision = getattr(tb, "rev", "") or ""
                date = getattr(tb, "date", "") or ""
        out.append(KiCadDesignSheet(
            number=i,
            name=cs.sheet_path_human,
            tstamps=cs.sheet_path,
            title=title,
            company=company,
            revision=revision,
            date=date,
        ))
    return out


def compile_design_netlist(
    top: "KiCadSchematic",
    project_vars: Optional[Dict[str, str]] = None,
    *,
    subpart_first_id: int = ord("A"),
    subpart_id_separator: int = 0,
) -> KiCadNetlist:
    """Full design pipeline — compile + merge + materialise to KiCadNetlist.

    Populates all four output blocks:

    * ``nets`` — driver-resolved subgraphs after cross-sheet merge
    * ``components`` — one record per placed symbol
    * ``libparts`` — one record per unique ``(lib, part)``
    * ``design_metadata.sheets`` — sheet table for the ``(design ...)`` block

    ``design_metadata.source`` / ``date`` / ``tool`` stay empty here —
    they're filled by the emit target (the kicadsexpr emitter takes them
    as keyword arguments so caller controls the timestamp / tool string).
    """
    compiled = compile_design_subgraphs(
        top,
        subpart_first_id=subpart_first_id,
        subpart_id_separator=subpart_id_separator,
    )
    netlist = KiCadNetlist()
    netlist.nets = merge_design_nets(compiled)
    netlist.components = collect_design_components(compiled, project_vars)
    netlist.libparts = collect_design_libparts(compiled)
    netlist.design_metadata.sheets = _design_sheet_records(compiled)
    return netlist


__all__ = [
    "CompiledSheet",
    "compile_design_subgraphs",
    "merge_design_nets",
    "compile_design_netlist",
    "collect_design_components",
    "collect_design_libparts",
]
