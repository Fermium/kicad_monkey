"""
Subtest: KiCadPcb.source_inventory(detail=...) contract
Stratum: L1_parsing
Purpose: Pin the v1.1 source-inventory API shape agreed with ``3d-viz-rework``
in ``AGENT_KICAD_VIZ_DATA_MODEL_BULLETIN.md``.

The inventory is **source-side only**: it reports what the parser saw, with
classifications ``unknown`` / ``unprocessed`` / ``ignored`` / ``passthrough``.
Downstream classifications (``mapped`` / ``derived`` / ``unsupported_expected``)
are intentionally outside this parser-owned inventory.
"""

from __future__ import annotations

import pytest

from kicad_monkey import KiCadPcb
from kicad_monkey.kicad_pcb_source_inventory import (
    INVENTORY_TYPE,
    INVENTORY_VERSION,
    VALID_DETAIL,
    build_pcb_source_inventory,
)
from kicad_monkey.testing.corpus import get_kicad_pcb_foundation_case_input_dir


_REQUIRED_TOP_LEVEL_KEYS = (
    "type",
    "version",
    "source_backend",
    "source_format",
    "source_path",
    "parser",
    "counts",
    "families",
    "unknown_elements",
    "unprocessed_elements",
    "ignored_elements",
    "passthrough_elements",
)

_REQUIRED_COUNT_KEYS = (
    "layers",
    "nets",
    "net_classes",
    "segments",
    "track_arcs",
    "vias",
    "zones",
    "footprints",
    "footprint_pads",
    "footprint_graphics",
    "footprint_text",
    "footprint_models",
    "board_graphics",
    "board_text",
    "board_outline_carriers",
    "dimensions",
    "images",
    "barcodes",
    "tables",
    "groups",
    "embedded_files",
    "unknown_elements",
    "unprocessed_elements",
    "ignored_elements",
    "passthrough_elements",
)

_REQUIRED_FAMILY_KEYS = (
    "family_id",
    "scope",
    "source_kind",
    "parser_class",
    "count",
    "parse_status",
    "notes",
)

_REQUIRED_DETAIL_ROW_KEYS = (
    "source_ref",
    "classification",
    "reason",
    "fallback_action",
    "raw_head",
    "raw_excerpt",
    "notes",
)

_REQUIRED_SOURCE_REF_KEYS = (
    "source_cad",
    "source_kind",
    "scope",
    "owner_path",
    "source_index",
    "token_path",
    "line",
    "column",
)


def _load_one_via_pcb() -> KiCadPcb:
    # Migrated 2026-05-17 from pcb_foundation/one_via/ to
    # pcb_foundation/case019__via_basic/ as part of the case<NNN>__<descriptor>
    # rename; inner .kicad_pcb retains its original descriptor name.
    case_input = get_kicad_pcb_foundation_case_input_dir("case019__via_basic")
    board_path = case_input / "one_via.kicad_pcb"
    return KiCadPcb(board_path)


def test_inventory_top_level_shape() -> None:
    pcb = _load_one_via_pcb()
    inv = pcb.source_inventory()

    for key in _REQUIRED_TOP_LEVEL_KEYS:
        assert key in inv, f"missing top-level key: {key}"

    assert inv["type"] == INVENTORY_TYPE
    assert inv["version"] == INVENTORY_VERSION
    assert inv["source_backend"] == "kicad_pcb"
    assert inv["source_format"] == "kicad_pcb_s_expr"
    assert inv["source_path"] is not None and inv["source_path"].endswith("one_via.kicad_pcb")
    assert inv["parser"]["package"] == "kicad_monkey"


def test_inventory_counts_keys_present() -> None:
    pcb = _load_one_via_pcb()
    counts = pcb.source_inventory()["counts"]
    for key in _REQUIRED_COUNT_KEYS:
        assert key in counts, f"missing count key: {key}"
        assert isinstance(counts[key], int), f"count {key} not int: {counts[key]!r}"


def test_inventory_counts_match_pcb_attributes_one_via() -> None:
    pcb = _load_one_via_pcb()
    counts = pcb.source_inventory()["counts"]

    assert counts["vias"] == len(pcb.vias)
    assert counts["vias"] >= 1  # one_via fixture has at least one via
    assert counts["layers"] == len(pcb.layers)
    assert counts["nets"] == len(pcb.nets)
    assert counts["segments"] == len(pcb.segments)
    assert counts["track_arcs"] == len(pcb.arcs)
    assert counts["zones"] == len(pcb.zones)
    assert counts["footprints"] == len(pcb.footprints)
    assert counts["dimensions"] == len(pcb.dimensions)


def test_inventory_families_well_formed_and_include_board_and_footprint_scopes() -> None:
    pcb = _load_one_via_pcb()
    inv = pcb.source_inventory()
    families = inv["families"]
    assert len(families) > 0
    scopes_seen = set()
    family_ids = set()
    for fam in families:
        for key in _REQUIRED_FAMILY_KEYS:
            assert key in fam, f"family {fam.get('family_id')!r} missing key {key}"
        assert isinstance(fam["count"], int)
        scopes_seen.add(fam["scope"])
        family_ids.add(fam["family_id"])

    # All four scopes must be represented across the family registry.
    assert {"board", "footprint", "setup", "project"} <= scopes_seen
    # Some load-bearing families must exist.
    assert "board.via" in family_ids
    assert "board.segment" in family_ids
    assert "board.footprint" in family_ids
    assert "footprint.pad" in family_ids
    assert "board.setup" in family_ids
    assert "project.net_class" in family_ids


def test_inventory_passthrough_setup_emitted_when_present() -> None:
    pcb = _load_one_via_pcb()
    inv = pcb.source_inventory()

    # one_via has a setup section, so we expect exactly one passthrough row.
    passthrough = inv["passthrough_elements"]
    assert len(passthrough) >= 1
    setup_rows = [row for row in passthrough if row["raw_head"] == "setup"]
    assert len(setup_rows) == 1
    setup_row = setup_rows[0]
    assert setup_row["classification"] == "passthrough"
    assert setup_row["reason"] == "preserved_raw"
    assert setup_row["fallback_action"] == "passthrough"
    for key in _REQUIRED_DETAIL_ROW_KEYS:
        assert key in setup_row
    for key in _REQUIRED_SOURCE_REF_KEYS:
        assert key in setup_row["source_ref"]
    assert setup_row["source_ref"]["scope"] == "setup"

    # Counts.passthrough_elements must match the list length.
    assert inv["counts"]["passthrough_elements"] == len(passthrough)


def test_inventory_detail_modes_govern_raw_excerpt() -> None:
    pcb = _load_one_via_pcb()
    summary = pcb.source_inventory(detail="summary")
    objects = pcb.source_inventory(detail="objects")

    # The setup passthrough row exists in both modes; raw_excerpt is empty in
    # summary and populated in objects/debug.
    [summary_setup] = [r for r in summary["passthrough_elements"] if r["raw_head"] == "setup"]
    [objects_setup] = [r for r in objects["passthrough_elements"] if r["raw_head"] == "setup"]
    assert summary_setup["raw_excerpt"] == ""
    assert objects_setup["raw_excerpt"] != ""


def test_inventory_rejects_unknown_detail() -> None:
    pcb = _load_one_via_pcb()
    with pytest.raises(ValueError):
        pcb.source_inventory(detail="bogus")


def test_build_function_callable_directly() -> None:
    pcb = _load_one_via_pcb()
    inv = build_pcb_source_inventory(pcb, detail="summary")
    assert inv["type"] == INVENTORY_TYPE
    assert "counts" in inv


def test_valid_detail_constant_matches_implementation() -> None:
    assert "summary" in VALID_DETAIL
    assert "objects" in VALID_DETAIL
    assert "debug" in VALID_DETAIL


def test_unknown_elements_list_well_formed() -> None:
    """Even when empty, unknown_elements must be a list (not None)."""
    pcb = _load_one_via_pcb()
    inv = pcb.source_inventory()
    for collection in (
        "unknown_elements",
        "unprocessed_elements",
        "ignored_elements",
        "passthrough_elements",
    ):
        assert isinstance(inv[collection], list)
        for row in inv[collection]:
            for key in _REQUIRED_DETAIL_ROW_KEYS:
                assert key in row, f"{collection} row missing key {key}"
            for key in _REQUIRED_SOURCE_REF_KEYS:
                assert key in row["source_ref"], f"{collection} source_ref missing key {key}"
            assert row["classification"] in (
                "unknown",
                "unprocessed",
                "ignored",
                "passthrough",
            )
