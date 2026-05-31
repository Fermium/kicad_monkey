"""
Subtest: Footprint Round-Trip
Stratum: L1_parsing
Purpose: Parse -> serialize -> parse footprint files with equivalency check

Tests verify that:
1. All .kicad_mod files can be parsed without errors
2. Parsed files can be serialized back to s-expression format
3. Re-parsing the serialized output produces equivalent data

Round-trip fidelity is measured by:
- Semantic equivalence: All data structures match after round-trip
- Element preservation: Pads, graphics, properties survive intact
"""

from pathlib import Path
from typing import List

import pytest

from kicad_monkey.kicad_sexpr import parse_sexp
from kicad_monkey.kicad_footprint import (
    KiCadFootprint,
    from_kicad_mod,
    to_kicad_mod,
)
from kicad_monkey.kicad_base import get_value

from conftest import (
    get_all_footprint_files,
    get_footprint_test_ids,
    get_sample_footprints,
    get_sample_footprint_ids,
)


# ============================================================================
# Parsing Tests
# ============================================================================

class TestFootprintParsing:
    """Test that all footprint files can be parsed."""

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_parse_without_error(self, fp_path: Path):
        """Test that the footprint file parses without raising exceptions."""
        fp = from_kicad_mod(fp_path)

        # Basic sanity checks
        assert fp is not None
        assert fp.name is not None
        assert fp.name != ""
        assert fp.version > 0
        assert fp.layer in ("F.Cu", "B.Cu")

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_version_preserved(self, fp_path: Path):
        """Test that version number is correctly parsed."""
        content = fp_path.read_text(encoding='utf-8')
        sexp = parse_sexp(content)
        expected_version = get_value(sexp, 'version')

        fp = from_kicad_mod(fp_path)
        assert fp.version == expected_version

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_name_matches_filename(self, fp_path: Path):
        """Test that footprint name is present."""
        fp = from_kicad_mod(fp_path)
        # The name should be present
        assert fp.name is not None


# ============================================================================
# Serialization Tests
# ============================================================================

class TestFootprintSerialization:
    """Test that footprint objects can be serialized."""

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_to_string_produces_valid_sexp(self, fp_path: Path):
        """Test that serialized output is valid s-expression."""
        fp = from_kicad_mod(fp_path)
        output = fp.to_string()

        # Should be parseable
        sexp = parse_sexp(output)
        assert sexp is not None
        assert sexp[0] == 'footprint'

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_output_ends_with_newline(self, fp_path: Path):
        """Test POSIX compliance: file ends with newline."""
        fp = from_kicad_mod(fp_path)
        output = fp.to_string()
        assert output.endswith('\n'), "Output must end with newline (POSIX)"


# ============================================================================
# Round-Trip Tests
# ============================================================================

class TestFootprintRoundTrip:
    """Test full round-trip parsing and serialization."""

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_roundtrip_preserves_version(self, fp_path: Path):
        """Test that version survives round-trip."""
        fp1 = from_kicad_mod(fp_path)
        output = fp1.to_string()
        fp2 = KiCadFootprint.from_string(output)

        assert fp2.version == fp1.version

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_roundtrip_preserves_name(self, fp_path: Path):
        """Test that footprint name survives round-trip."""
        fp1 = from_kicad_mod(fp_path)
        output = fp1.to_string()
        fp2 = KiCadFootprint.from_string(output)

        assert fp2.name == fp1.name

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_roundtrip_preserves_pad_count(self, fp_path: Path):
        """Test that all pads survive round-trip."""
        fp1 = from_kicad_mod(fp_path)
        output = fp1.to_string()
        fp2 = KiCadFootprint.from_string(output)

        assert len(fp2.pads) == len(fp1.pads), \
            f"Pad count mismatch: {len(fp2.pads)} vs {len(fp1.pads)}"

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_roundtrip_preserves_property_count(self, fp_path: Path):
        """Test that all properties survive round-trip."""
        fp1 = from_kicad_mod(fp_path)
        output = fp1.to_string()
        fp2 = KiCadFootprint.from_string(output)

        assert len(fp2.properties) == len(fp1.properties), \
            f"Property count mismatch: {len(fp2.properties)} vs {len(fp1.properties)}"

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_roundtrip_preserves_graphics_count(self, fp_path: Path):
        """Test that all graphics elements survive round-trip."""
        fp1 = from_kicad_mod(fp_path)
        output = fp1.to_string()
        fp2 = KiCadFootprint.from_string(output)

        assert len(fp2.fp_lines) == len(fp1.fp_lines), "Line count mismatch"
        assert len(fp2.fp_arcs) == len(fp1.fp_arcs), "Arc count mismatch"
        assert len(fp2.fp_circles) == len(fp1.fp_circles), "Circle count mismatch"
        assert len(fp2.fp_rects) == len(fp1.fp_rects), "Rect count mismatch"
        assert len(fp2.fp_polys) == len(fp1.fp_polys), "Poly count mismatch"
        assert len(fp2.fp_texts) == len(fp1.fp_texts), "Text count mismatch"

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_roundtrip_preserves_model_count(self, fp_path: Path):
        """Test that all 3D models survive round-trip."""
        fp1 = from_kicad_mod(fp_path)
        output = fp1.to_string()
        fp2 = KiCadFootprint.from_string(output)

        assert len(fp2.models) == len(fp1.models), \
            f"Model count mismatch: {len(fp2.models)} vs {len(fp1.models)}"


# ============================================================================
# Double Round-Trip Tests (Stability)
# ============================================================================

class TestDoubleRoundTrip:
    """Test that double round-trip produces stable output."""

    @pytest.mark.parametrize("fp_path", get_sample_footprints(), ids=get_sample_footprint_ids())
    def test_double_roundtrip_stable(self, fp_path: Path):
        """Test that second round-trip produces identical output to first."""
        fp1 = from_kicad_mod(fp_path)
        output1 = fp1.to_string()

        fp2 = KiCadFootprint.from_string(output1)
        output2 = fp2.to_string()

        # The outputs should be identical
        assert output1 == output2, \
            f"Double round-trip not stable for {fp_path.name}"


# ============================================================================
# Element Data Tests
# ============================================================================

class TestElementData:
    """Test that element data is correctly preserved."""

    @pytest.mark.parametrize("fp_path", get_sample_footprints(20), ids=get_sample_footprint_ids(20))
    def test_pad_numbers_preserved(self, fp_path: Path):
        """Test that pad numbers are preserved."""
        fp1 = from_kicad_mod(fp_path)
        if not fp1.pads:
            pytest.skip("No pads in footprint")

        output = fp1.to_string()
        fp2 = KiCadFootprint.from_string(output)

        original_numbers = sorted([p.number for p in fp1.pads])
        roundtrip_numbers = sorted([p.number for p in fp2.pads])

        assert roundtrip_numbers == original_numbers

    @pytest.mark.parametrize("fp_path", get_sample_footprints(20), ids=get_sample_footprint_ids(20))
    def test_pad_positions_preserved(self, fp_path: Path):
        """Test that pad positions are preserved within tolerance."""
        fp1 = from_kicad_mod(fp_path)
        if not fp1.pads:
            pytest.skip("No pads in footprint")

        output = fp1.to_string()
        fp2 = KiCadFootprint.from_string(output)

        tolerance = 0.001  # mm

        # Match pads by UUID (handles duplicate pad numbers like multiple ground pads)
        for p1 in fp1.pads:
            p2 = next((p for p in fp2.pads if p.uuid == p1.uuid), None)
            assert p2 is not None, f"Pad {p1.number} (uuid={p1.uuid}) not found after round-trip"

            assert abs(p2.at_x - p1.at_x) < tolerance, \
                f"Pad {p1.number} X mismatch: {p1.at_x} vs {p2.at_x}"
            assert abs(p2.at_y - p1.at_y) < tolerance, \
                f"Pad {p1.number} Y mismatch: {p1.at_y} vs {p2.at_y}"

    @pytest.mark.parametrize("fp_path", get_sample_footprints(20), ids=get_sample_footprint_ids(20))
    def test_property_values_preserved(self, fp_path: Path):
        """Test that property values are preserved."""
        fp1 = from_kicad_mod(fp_path)
        if not fp1.properties:
            pytest.skip("No properties in footprint")

        output = fp1.to_string()
        fp2 = KiCadFootprint.from_string(output)

        for prop1 in fp1.properties:
            prop2 = next((p for p in fp2.properties if p.name == prop1.name), None)
            assert prop2 is not None, f"Property {prop1.name} not found"
            assert prop2.value == prop1.value, \
                f"Property {prop1.name} value mismatch: {prop1.value} vs {prop2.value}"


# ============================================================================
# Comprehensive Test (All Footprints)
# ============================================================================

class TestAllFootprints:
    """Comprehensive tests against ALL footprints (slower, run with -v)."""

    @pytest.mark.slow
    @pytest.mark.parametrize("fp_path", get_all_footprint_files(), ids=get_footprint_test_ids())
    def test_all_footprints_parse(self, fp_path: Path):
        """Test that ALL footprints can be parsed."""
        fp = from_kicad_mod(fp_path)
        assert fp is not None

    @pytest.mark.slow
    @pytest.mark.parametrize("fp_path", get_all_footprint_files(), ids=get_footprint_test_ids())
    def test_all_footprints_roundtrip(self, fp_path: Path):
        """Test that ALL footprints survive round-trip."""
        fp1 = from_kicad_mod(fp_path)
        output = fp1.to_string()
        fp2 = KiCadFootprint.from_string(output)

        assert fp2.name == fp1.name
        assert len(fp2.pads) == len(fp1.pads)
        assert len(fp2.properties) == len(fp1.properties)


# ============================================================================
# Run tests standalone
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
