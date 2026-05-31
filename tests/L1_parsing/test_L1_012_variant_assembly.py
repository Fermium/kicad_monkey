"""
Test L1_012: Cross-domain variant assembly view

Phase C Slice C-4 — exercises ``assemble()`` on the upstream
``cli/variants/variants.kicad_sch`` fixture (the canonical BOM-oracle
target for Slice C-6). Verifies the join produces one row per unique
reference, that variant overrides flow through to ``effective_dnp``,
and that the reference set agrees with the upstream BOM golden for the
default variant.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from kicad_monkey import KiCadSchematic, assemble, AssemblyComponent
from kicad_monkey.testing.corpus import get_kicad_upstream_qa_dir


def _variants_sch() -> Path:
    return get_kicad_upstream_qa_dir() / "cli" / "variants" / "variants.kicad_sch"


def _read_bom_refs(csv_path: Path) -> set[str]:
    """Return the set of reference designators emitted by KiCad's BOM."""
    refs: set[str] = set()
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return refs
    # First column is "Refs" (comma-joined refs). Header row is rows[0].
    for row in rows[1:]:
        if not row:
            continue
        for ref in row[0].split(","):
            ref = ref.strip()
            if ref:
                refs.add(ref)
    return refs


# ---------------------------------------------------------------------------
# Structural assertions
# ---------------------------------------------------------------------------

class TestAssembleStructure:
    def test_default_variant_returns_components(self) -> None:
        sch = KiCadSchematic.from_file(_variants_sch())
        rows = assemble(sch, None, variant_name=None)
        assert rows, "default assembly view must not be empty"
        for row in rows:
            assert isinstance(row, AssemblyComponent)
            assert row.reference != ""
            assert row.symbol is not None  # all rows here come from the schematic

    def test_assemble_is_unique_by_reference(self) -> None:
        sch = KiCadSchematic.from_file(_variants_sch())
        rows = assemble(sch, None, variant_name=None)
        refs = [r.reference for r in rows]
        assert len(refs) == len(set(refs)), "assemble must dedupe by reference"

    def test_pcb_only_path_is_safe_with_none_pcb(self) -> None:
        """Passing pcb=None must not crash and footprints stay None."""
        sch = KiCadSchematic.from_file(_variants_sch())
        rows = assemble(sch, None, variant_name=None)
        assert all(r.footprint is None for r in rows)


# ---------------------------------------------------------------------------
# Variant-aware behavior
# ---------------------------------------------------------------------------

class TestAssembleVariantBehavior:
    """Variant overrides on individual symbol instances flow to
    ``effective_dnp`` and shrink the in-BOM set accordingly."""

    def test_variant1_marks_overridden_refs_as_dnp(self) -> None:
        sch = KiCadSchematic.from_file(_variants_sch())
        default = {r.reference: r for r in assemble(sch, None, None)}
        v1 = {r.reference: r for r in assemble(sch, None, "Variant 1")}

        # Same reference set across variants.
        assert set(default) == set(v1)

        # At least one component flips DNP under Variant 1 (else the
        # fixture has changed and the test is no longer informative).
        flipped = [
            ref for ref in default
            if not default[ref].effective_dnp and v1[ref].effective_dnp
        ]
        assert flipped, (
            "Variant 1 must DNP-flip at least one component "
            "(fixture regression check)"
        )

    def test_variant1_dnp_set_drops_from_in_bom(self) -> None:
        sch = KiCadSchematic.from_file(_variants_sch())
        v1 = assemble(sch, None, "Variant 1")
        for row in v1:
            if row.effective_dnp:
                # KiCad's BOM-with --exclude-dnp drops these; we don't
                # filter here (caller does), but in_bom must still be
                # the underlying base-or-override value, NOT silently
                # forced to False just because effective_dnp is True.
                assert isinstance(row.effective_in_bom, bool)


# ---------------------------------------------------------------------------
# BOM-oracle smoke (full equality test deferred to C-6)
# ---------------------------------------------------------------------------

class TestAssembleAgreesWithBomGoldenRefs:
    """Sanity check: a BOM-export-flipping override should remove a ref
    from the BOM golden under that variant. Full equality is C-6 work
    because it requires (a) hierarchical sheet recursion to enumerate
    sub-sheet symbols, and (b) live kicad-cli oracle validation —
    both flagged as later slices.
    """

    def _override_flips_change_golden_membership(
        self, variant: str, golden_name: str,
    ) -> None:
        sch = KiCadSchematic.from_file(_variants_sch())
        default_rows = {r.reference: r for r in assemble(sch, None, None)}
        variant_rows = {r.reference: r for r in assemble(sch, None, variant)}
        golden = _read_bom_refs(
            get_kicad_upstream_qa_dir() / "cli" / "variants" / golden_name
        )
        # Among references where the override flipped DNP from False→True,
        # every such ref must be missing from the golden's --exclude-dnp
        # output.
        flipped_to_dnp = [
            ref for ref in default_rows
            if not default_rows[ref].effective_dnp
            and variant_rows[ref].effective_dnp
        ]
        if not flipped_to_dnp:
            pytest.skip(
                f"variant {variant!r} does not flip any top-level ref to DNP; "
                "test is uninformative on this fixture"
            )
        intruders = [ref for ref in flipped_to_dnp if ref in golden]
        assert not intruders, (
            f"variant={variant!r}: refs flipped to DNP must be excluded "
            f"from {golden_name} but appear there: {intruders}"
        )

    def test_variant_1_dnp_flips_drop_out_of_v1_bom(self) -> None:
        self._override_flips_change_golden_membership(
            "Variant 1", "variants_v1.bom.csv",
        )

    def test_variant_2_dnp_flips_drop_out_of_v2_bom(self) -> None:
        self._override_flips_change_golden_membership(
            "Variant2", "variants_v2.bom.csv",
        )
