"""
Subtest: Parser Equivalency
Stratum: L1_parsing
Purpose: Different parsing approaches produce identical results

Verifies that the new KiCadPcb OOP model produces equivalent component data
to the existing KiCadPcbDoc (simple BOM parser).

This ensures we can eventually consolidate to ONE PCB parser without losing data.
"""

import pytest
from pathlib import Path

from kicad_monkey.kicad_pcb import KiCadPcb, from_kicad_pcb
from kicad_monkey.kicad_pcb_parser import KiCadPcbDoc
from kicad_monkey.kicad_pcb_footprint import Footprint

from conftest import get_all_pcb_files, get_pcb_test_ids


def get_footprint_reference(fp: Footprint) -> str | None:
    """Extract reference designator from footprint properties."""
    for prop in fp.properties:
        if prop.name == "Reference":
            return prop.value
    return None


# ============================================================================
# Parser Equivalency Tests
# ============================================================================

class TestParserEquivalency:
    """
    Verify the new OOP parser (KiCadPcb) can extract the same component data
    as the existing BOM parser (KiCadPcbDoc).
    """

    @pytest.mark.parametrize("pcb_path", get_all_pcb_files(), ids=get_pcb_test_ids())
    def test_footprint_count_matches(self, pcb_path: Path):
        """Both parsers should find the same number of footprints."""
        # Parse with both parsers
        oop_pcb = from_kicad_pcb(pcb_path)
        bom_pcb = KiCadPcbDoc.from_file(pcb_path, verbose=False)

        # Note: KiCadPcbDoc filters out NO_BOM and exclude_from_bom components
        # KiCadPcb includes ALL footprints
        # So we compare raw footprint count
        assert len(oop_pcb.footprints) >= len(bom_pcb.components), \
            f"OOP parser found fewer footprints ({len(oop_pcb.footprints)}) " \
            f"than BOM parser components ({len(bom_pcb.components)})"

    @pytest.mark.parametrize("pcb_path", get_all_pcb_files(), ids=get_pcb_test_ids())
    def test_reference_designators_match(self, pcb_path: Path):
        """All component references from BOM parser should exist in OOP parser."""
        oop_pcb = from_kicad_pcb(pcb_path)
        bom_pcb = KiCadPcbDoc.from_file(pcb_path, verbose=False)

        # Get reference designators from both
        oop_refs = {get_footprint_reference(fp) for fp in oop_pcb.footprints}
        oop_refs.discard(None)  # Remove None values
        bom_refs = {comp.designator for comp in bom_pcb.components}

        # BOM refs should be a subset of OOP refs (BOM filters some out)
        missing = bom_refs - oop_refs
        assert not missing, \
            f"BOM parser has refs not found in OOP parser: {missing}"

    @pytest.mark.parametrize("pcb_path", get_all_pcb_files(), ids=get_pcb_test_ids())
    def test_footprint_names_match(self, pcb_path: Path):
        """Footprint names should match for same reference designator."""
        oop_pcb = from_kicad_pcb(pcb_path)
        bom_pcb = KiCadPcbDoc.from_file(pcb_path, verbose=False)

        # Build lookup by reference
        oop_by_ref = {}
        for fp in oop_pcb.footprints:
            ref = get_footprint_reference(fp)
            if ref:
                oop_by_ref[ref] = fp

        mismatches = []
        for comp in bom_pcb.components:
            if comp.designator in oop_by_ref:
                oop_fp = oop_by_ref[comp.designator]
                # Extract footprint name (after colon) from library_link
                oop_fp_name = oop_fp.library_link.split(':', 1)[-1] if ':' in oop_fp.library_link else oop_fp.library_link
                if oop_fp_name != comp.footprint:
                    mismatches.append(f"{comp.designator}: BOM='{comp.footprint}' vs OOP='{oop_fp_name}'")

        assert not mismatches, \
            "Footprint name mismatches:\n" + "\n".join(mismatches[:10])

    @pytest.mark.parametrize("pcb_path", get_all_pcb_files(), ids=get_pcb_test_ids())
    def test_positions_match(self, pcb_path: Path):
        """Component positions should match (within tolerance)."""
        oop_pcb = from_kicad_pcb(pcb_path)
        bom_pcb = KiCadPcbDoc.from_file(pcb_path, verbose=False)

        # Build lookup by reference
        oop_by_ref = {}
        for fp in oop_pcb.footprints:
            ref = get_footprint_reference(fp)
            if ref:
                oop_by_ref[ref] = fp

        mismatches = []
        tolerance = 0.001  # mm

        for comp in bom_pcb.components:
            if comp.designator in oop_by_ref:
                oop_fp = oop_by_ref[comp.designator]

                # BOM parser stores raw positions (before origin adjustment)
                # OOP parser stores at_x, at_y directly from file
                dx = abs(oop_fp.at_x - comp.x_mm)
                dy = abs(oop_fp.at_y - comp.y_mm)

                if dx > tolerance or dy > tolerance:
                    mismatches.append(
                        f"{comp.designator}: BOM=({comp.x_mm}, {comp.y_mm}) "
                        f"vs OOP=({oop_fp.at_x}, {oop_fp.at_y})"
                    )

        assert not mismatches, \
            f"Position mismatches (tolerance={tolerance}mm):\n" + "\n".join(mismatches[:10])

    @pytest.mark.parametrize("pcb_path", get_all_pcb_files(), ids=get_pcb_test_ids())
    def test_layers_match(self, pcb_path: Path):
        """Component layer (TOP/BOTTOM) should match."""
        oop_pcb = from_kicad_pcb(pcb_path)
        bom_pcb = KiCadPcbDoc.from_file(pcb_path, verbose=False)

        # Build lookup by reference
        oop_by_ref = {}
        for fp in oop_pcb.footprints:
            ref = get_footprint_reference(fp)
            if ref:
                oop_by_ref[ref] = fp

        mismatches = []
        for comp in bom_pcb.components:
            if comp.designator in oop_by_ref:
                oop_fp = oop_by_ref[comp.designator]

                # OOP parser stores layer name directly, BOM normalizes to TOP/BOTTOM
                oop_layer = "TOP" if "F.Cu" in oop_fp.layer else "BOTTOM"

                if oop_layer != comp.layer:
                    mismatches.append(
                        f"{comp.designator}: BOM='{comp.layer}' vs OOP='{oop_layer}'"
                    )

        assert not mismatches, \
            "Layer mismatches:\n" + "\n".join(mismatches[:10])

    @pytest.mark.parametrize("pcb_path", get_all_pcb_files(), ids=get_pcb_test_ids())
    def test_rotation_matches(self, pcb_path: Path):
        """Component rotation should match (within tolerance)."""
        oop_pcb = from_kicad_pcb(pcb_path)
        bom_pcb = KiCadPcbDoc.from_file(pcb_path, verbose=False)

        # Build lookup by reference
        oop_by_ref = {}
        for fp in oop_pcb.footprints:
            ref = get_footprint_reference(fp)
            if ref:
                oop_by_ref[ref] = fp

        mismatches = []
        tolerance = 0.01  # degrees

        for comp in bom_pcb.components:
            if comp.designator in oop_by_ref:
                oop_fp = oop_by_ref[comp.designator]

                # Normalize rotations to 0-360 range
                oop_rot = oop_fp.at_angle % 360 if oop_fp.at_angle else 0
                bom_rot = comp.rotation % 360 if comp.rotation else 0

                # Handle wraparound (359.9 vs 0.1)
                diff = abs(oop_rot - bom_rot)
                if diff > 180:
                    diff = 360 - diff

                if diff > tolerance:
                    mismatches.append(
                        f"{comp.designator}: BOM={bom_rot}deg vs OOP={oop_rot}deg"
                    )

        assert not mismatches, \
            f"Rotation mismatches (tolerance={tolerance}deg):\n" + "\n".join(mismatches[:10])


# ============================================================================
# Origin Handling Tests
# ============================================================================

class TestOriginHandling:
    """Test that origin (aux_axis_origin) handling is consistent."""

    @pytest.mark.parametrize("pcb_path", get_all_pcb_files(), ids=get_pcb_test_ids())
    def test_origin_parsed(self, pcb_path: Path):
        """Both parsers should parse the board origin."""
        oop_pcb = KiCadPcb.from_file(pcb_path)
        bom_pcb = KiCadPcbDoc.from_file(pcb_path, verbose=False)

        assert bom_pcb.origin_x_mm is not None
        assert bom_pcb.origin_y_mm is not None
        assert oop_pcb.aux_axis_origin_mm == pytest.approx(
            (bom_pcb.origin_x_mm, bom_pcb.origin_y_mm)
        )


# ============================================================================
# Run tests standalone
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
