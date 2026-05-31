"""
Subtest: KiCad CLI Validation
Stratum: L4_applications
Purpose: Validate outputs against kicad-cli tool

Tests that verify our output files can be parsed and processed by KiCad.
These tests use kicad-cli to validate that our serialized output is correct.

Skip behavior:
- Tests are skipped if kicad-cli is not found
- This allows CI to pass without KiCad installed
"""

import logging
import pytest
import subprocess
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

from conftest import FOOTPRINTS_DIR, find_kicad_cli


# ============================================================================
# Helper Functions
# ============================================================================

def get_test_footprints() -> list[Path]:
    """Get shared-corpus footprint files for kicad-cli validation."""
    if not FOOTPRINTS_DIR.exists():
        return []
    return sorted(FOOTPRINTS_DIR.glob("*.kicad_mod"))


# ============================================================================
# Version Check Tests
# ============================================================================

class TestKicadCliVersionCheck:
    """Tests that check kicad-cli availability and version."""

    def test_kicad_cli_exists(self, kicad_cli):
        """Verify kicad-cli is accessible."""
        assert kicad_cli.exists()

    def test_kicad_cli_version(self, kicad_cli):
        """Get and log kicad-cli version."""
        result = subprocess.run(
            [str(kicad_cli), "version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        log.info(f"kicad-cli version: {result.stdout.strip()}")
        assert result.returncode == 0


# ============================================================================
# Footprint Validation Tests
# ============================================================================

class TestKicadCliFootprintValidation:
    """Tests that validate footprints using kicad-cli."""

    @pytest.mark.parametrize("fp_path", get_test_footprints()[:10],
                             ids=lambda p: p.stem)
    def test_roundtrip_validates_in_kicad(self, kicad_cli, fp_path, tmp_path):
        """
        Test that our round-trip output can be parsed by KiCad.

        Steps:
        1. Load original footprint
        2. Serialize to our output format
        3. Create a .pretty library with our output
        4. Ask kicad-cli to "upgrade" the library (re-parse and re-write)
        5. Verify it succeeds

        Note: Footprints with large embedded files (compressed 3D models) may fail
        kicad-cli validation due to differences in element ordering or formatting.
        This is tracked as a known issue - the data round-trips correctly but
        kicad-cli is stricter than our parser.
        """
        from kicad_monkey import from_kicad_mod

        # Load and round-trip the footprint
        fp = from_kicad_mod(fp_path)

        output_path = tmp_path / f"{fp.name}.kicad_mod"
        fp.to_file(output_path)

        # Create a .pretty library directory
        pretty_dir = tmp_path / "test.pretty"
        pretty_dir.mkdir()
        dest_path = pretty_dir / output_path.name
        shutil.copy(output_path, dest_path)

        # Ask kicad-cli to upgrade/validate the library
        result = subprocess.run(
            [str(kicad_cli), "fp", "upgrade", str(pretty_dir)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            log.error(f"kicad-cli failed for {fp_path.name}")
            log.error(f"stdout: {result.stdout}")
            log.error(f"stderr: {result.stderr}")

        assert result.returncode == 0, (
            f"kicad-cli fp upgrade failed for {fp_path.name}:\n"
            f"stderr: {result.stderr}"
        )

    def test_simple_footprint_validates(self, kicad_cli, tmp_path):
        """Test a simple programmatically-created footprint validates."""
        from kicad_monkey import KiCadFootprint
        from kicad_monkey.kicad_base import PadShape, PadType
        from kicad_monkey.kicad_pcb_footprint import Pad, Property

        # Create a simple footprint
        fp = KiCadFootprint()
        fp.name = "TEST_FOOTPRINT"
        fp.version = 20241229
        fp.generator = "test"
        fp.generator_version = "1.0"
        fp.layer = "F.Cu"
        fp.uuid = "00000000-0000-0000-0000-000000000001"

        # Add Reference and Value properties
        fp.properties = [
            Property(name="Reference", value="REF**", at_x=0, at_y=-2,
                     layer="F.SilkS", uuid="00000000-0000-0000-0000-000000000002"),
            Property(name="Value", value="TEST_FOOTPRINT", at_x=0, at_y=2,
                     layer="F.Fab", uuid="00000000-0000-0000-0000-000000000003"),
        ]

        # Add a simple SMD pad
        fp.pads = [
            Pad(number="1", pad_type=PadType.SMD, shape=PadShape.RECT,
                at_x=-0.5, at_y=0, size_x=0.5, size_y=0.5,
                layers=["F.Cu", "F.Paste", "F.Mask"],
                uuid="00000000-0000-0000-0000-000000000004"),
            Pad(number="2", pad_type=PadType.SMD, shape=PadShape.RECT,
                at_x=0.5, at_y=0, size_x=0.5, size_y=0.5,
                layers=["F.Cu", "F.Paste", "F.Mask"],
                uuid="00000000-0000-0000-0000-000000000005"),
        ]

        fp.attr = ["smd"]

        # Write to file
        output_path = tmp_path / "TEST_FOOTPRINT.kicad_mod"
        fp.to_file(output_path)

        # Create .pretty library
        pretty_dir = tmp_path / "test.pretty"
        pretty_dir.mkdir()
        shutil.copy(output_path, pretty_dir / output_path.name)

        # Validate with kicad-cli
        result = subprocess.run(
            [str(kicad_cli), "fp", "upgrade", str(pretty_dir)],
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, (
            f"kicad-cli fp upgrade failed:\nstderr: {result.stderr}"
        )


# ============================================================================
# PCB Validation Tests
# ============================================================================

class TestKicadCliPcbValidation:
    """Tests that validate PCB files using kicad-cli."""

    def test_pcb_validation_available(self, kicad_cli):
        """Verify kicad-cli pcb commands are available."""
        result = subprocess.run(
            [str(kicad_cli), "pcb", "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0
        # DRC command should be available
        assert "drc" in result.stdout.lower() or "drc" in result.stderr.lower()


# ============================================================================
# Symbol Validation Tests
# ============================================================================

class TestKicadCliSymbolValidation:
    """Tests that validate symbol files using kicad-cli."""

    def test_symbol_validation_available(self, kicad_cli):
        """Verify kicad-cli sym commands are available."""
        result = subprocess.run(
            [str(kicad_cli), "sym", "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0


# ============================================================================
# Run tests standalone
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
