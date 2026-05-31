"""
Test L1_013: Variant data round-trip lock

Phase C Slice C-5 — regression locks for the existing low-level
variant carriers. Each test parses a fixture, re-emits it via
``to_text()``, reparses, and asserts the variant payload survives
unchanged. Drift here would silently corrupt assembly variants on any
caller round-tripping a board / schematic file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kicad_monkey import KiCadPcb, KiCadSchematic
from kicad_monkey.testing.corpus import get_kicad_upstream_qa_dir


# ---------------------------------------------------------------------------
# Helpers — normalize variant payloads into hashable / comparable shapes
# ---------------------------------------------------------------------------

def _sch_variant_signature(sch: KiCadSchematic) -> list[tuple]:
    """Per-symbol-instance variant signature, sorted for stable compare."""
    out: list[tuple] = []
    for sym in sch.symbols:
        ref = getattr(sym, "reference", "") or ""
        for inst in getattr(sym, "instances", []) or []:
            for v in getattr(inst, "variants", []) or []:
                out.append((
                    ref, inst.path, v.name,
                    v.dnp, v.exclude_from_sim,
                    v.in_bom, v.on_board, v.in_pos_files,
                    tuple(sorted(v.fields)),
                ))
    return sorted(out)


def _sheet_variant_signature(sch: KiCadSchematic) -> list[tuple]:
    """Per-sheet-instance variant signature."""
    out: list[tuple] = []
    for sheet in getattr(sch, "sheets", []) or []:
        sheet_name = getattr(sheet, "name", "") or getattr(sheet, "uuid", "")
        for inst in getattr(sheet, "instances", []) or []:
            for v in getattr(inst, "variants", []) or []:
                out.append((
                    sheet_name, inst.path, v.name,
                    v.dnp, v.exclude_from_sim,
                    v.in_bom, v.on_board, v.in_pos_files,
                    tuple(sorted(v.fields)),
                ))
    return sorted(out)


def _none_sentinel(v):
    """Coerce Optional[bool] to a sortable / comparable shape (always str)."""
    if v is None:
        return "<none>"
    return "true" if v else "false"


def _pcb_board_catalog_signature(pcb: KiCadPcb) -> list[tuple]:
    """Top-level (variants ...) catalog signature."""
    return sorted(
        (bv.name, bv.description or "") for bv in (pcb.variants or [])
    )


def _pcb_footprint_variant_signature(pcb: KiCadPcb) -> list[tuple]:
    """Per-footprint variant override signature."""
    out: list[tuple] = []
    for fp in pcb.footprints:
        ref = ""
        for prop in getattr(fp, "properties", []) or []:
            if getattr(prop, "name", None) == "Reference":
                ref = getattr(prop, "value", "") or ""
                break
        for fv in getattr(fp, "variants", []) or []:
            field_pairs = tuple(sorted(
                (f.name, f.value) for f in (fv.fields or [])
            ))
            out.append((
                ref, fv.name,
                _none_sentinel(fv.dnp),
                _none_sentinel(fv.exclude_from_bom),
                _none_sentinel(fv.exclude_from_pos_files),
                field_pairs,
            ))
    return sorted(out)


# ---------------------------------------------------------------------------
# Symbol-instance variants on schematic
# ---------------------------------------------------------------------------

class TestSchSymbolInstanceVariantRoundTrip:
    @pytest.fixture
    def variants_sch(self) -> Path:
        return get_kicad_upstream_qa_dir() / "cli" / "variants" / "variants.kicad_sch"

    def test_fixture_has_symbol_variants(self, variants_sch: Path) -> None:
        sch = KiCadSchematic.from_file(variants_sch)
        sig = _sch_variant_signature(sch)
        assert sig, (
            "fixture must contain at least one per-symbol-instance variant "
            "block to exercise this round-trip lock"
        )

    def test_symbol_variants_round_trip(self, variants_sch: Path) -> None:
        sch1 = KiCadSchematic.from_file(variants_sch)
        text = sch1.to_text()
        sch2 = KiCadSchematic.from_text(text)
        assert _sch_variant_signature(sch1) == _sch_variant_signature(sch2)

    def test_sheet_instance_variants_round_trip(self, variants_sch: Path) -> None:
        sch1 = KiCadSchematic.from_file(variants_sch)
        sig1 = _sheet_variant_signature(sch1)
        # The cli/variants fixture has at least one per-sheet variant
        # entry (Variant 1 with exclude_from_sim).
        text = sch1.to_text()
        sch2 = KiCadSchematic.from_text(text)
        sig2 = _sheet_variant_signature(sch2)
        assert sig1 == sig2


# ---------------------------------------------------------------------------
# PCB top-level catalog
# ---------------------------------------------------------------------------

class TestPcbBoardCatalogRoundTrip:
    @pytest.fixture
    def variant_test_pcb(self) -> Path:
        return (
            get_kicad_upstream_qa_dir()
            / "pcbnew" / "variant_test" / "variant_test.kicad_pcb"
        )

    def test_fixture_has_board_catalog(self, variant_test_pcb: Path) -> None:
        pcb = KiCadPcb.from_file(variant_test_pcb)
        assert pcb.variants, (
            "variant_test.kicad_pcb must define a top-level (variants ...) "
            "catalog to exercise this round-trip lock"
        )

    def test_board_catalog_round_trip(self, variant_test_pcb: Path) -> None:
        pcb1 = KiCadPcb.from_file(variant_test_pcb)
        text = pcb1.to_string()
        pcb2 = KiCadPcb.from_string(text)
        assert _pcb_board_catalog_signature(pcb1) == _pcb_board_catalog_signature(pcb2)


# ---------------------------------------------------------------------------
# Per-footprint variant overrides
# ---------------------------------------------------------------------------

class TestFootprintVariantRoundTrip:
    @pytest.fixture
    def variant_test_pcb(self) -> Path:
        return (
            get_kicad_upstream_qa_dir()
            / "pcbnew" / "variant_test" / "variant_test.kicad_pcb"
        )

    def test_fixture_has_footprint_variants(self, variant_test_pcb: Path) -> None:
        pcb = KiCadPcb.from_file(variant_test_pcb)
        sig = _pcb_footprint_variant_signature(pcb)
        assert sig, (
            "variant_test.kicad_pcb must contain per-footprint (variant ...) "
            "blocks to exercise this round-trip lock"
        )

    def test_footprint_variants_round_trip(self, variant_test_pcb: Path) -> None:
        pcb1 = KiCadPcb.from_file(variant_test_pcb)
        text = pcb1.to_string()
        pcb2 = KiCadPcb.from_string(text)
        assert (
            _pcb_footprint_variant_signature(pcb1)
            == _pcb_footprint_variant_signature(pcb2)
        )

    def test_footprint_variants_with_field_overrides(self, variant_test_pcb: Path) -> None:
        """Specifically lock the field-override path (most fragile)."""
        pcb = KiCadPcb.from_file(variant_test_pcb)
        with_fields = [
            sig for sig in _pcb_footprint_variant_signature(pcb) if sig[5]
        ]
        assert with_fields, (
            "fixture must have at least one footprint variant with field "
            "overrides to lock that path"
        )

    def test_eeschema_variants_pcb_round_trip(self) -> None:
        """Second corpus fixture for added coverage."""
        pcb_path = (
            get_kicad_upstream_qa_dir()
            / "eeschema" / "variants" / "variants.kicad_pcb"
        )
        pcb1 = KiCadPcb.from_file(pcb_path)
        sig1 = _pcb_footprint_variant_signature(pcb1)
        if not sig1:
            pytest.skip("eeschema/variants.kicad_pcb has no per-fp variants")
        text = pcb1.to_string()
        pcb2 = KiCadPcb.from_string(text)
        assert sig1 == _pcb_footprint_variant_signature(pcb2)
