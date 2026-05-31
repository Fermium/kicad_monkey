"""
Subtest: Project Verification
Stratum: L4_applications
Purpose: Validate real KiCad project processing end-to-end

Tests that verify complete project workflows work correctly,
including project parsing, component extraction, and rendering.
"""

import logging
from pathlib import Path

import pytest

log = logging.getLogger(__name__)

from conftest import PROJECT_DIR


# ============================================================================
# Helper Functions
# ============================================================================

def get_project_dirs() -> list[Path]:
    """Get shared project directories used by application tests."""
    if PROJECT_DIR.exists() and list(PROJECT_DIR.glob("*.kicad_pro")):
        return [PROJECT_DIR]
    return []


def get_project_pcbs() -> list[Path]:
    """Get all PCB files in project directories."""
    pcbs = []
    for proj_dir in get_project_dirs():
        pcbs.extend(proj_dir.glob("*.kicad_pcb"))
    return sorted(pcbs)


def get_project_schematics() -> list[Path]:
    """Get all schematic files in project directories."""
    schematics = []
    for proj_dir in get_project_dirs():
        schematics.extend(proj_dir.glob("*.kicad_sch"))
    return sorted(schematics)


# ============================================================================
# Project Structure Tests
# ============================================================================

class TestProjectStructure:
    """Tests for project file structure and parsing."""

    def test_project_directory_exists(self):
        """Verify test project directory exists."""
        assert PROJECT_DIR.exists(), f"Project directory not found: {PROJECT_DIR}"

    def test_has_test_projects(self):
        """Verify we have at least one test project."""
        projects = get_project_dirs()
        assert len(projects) > 0, "No test projects found"

    @pytest.mark.parametrize("proj_dir", get_project_dirs(),
                             ids=lambda p: p.name)
    def test_project_has_pro_file(self, proj_dir):
        """Each project should have a .kicad_pro file."""
        pro_files = list(proj_dir.glob("*.kicad_pro"))
        assert len(pro_files) >= 1, f"No .kicad_pro file in {proj_dir.name}"

    @pytest.mark.parametrize("proj_dir", get_project_dirs(),
                             ids=lambda p: p.name)
    def test_project_has_pcb_file(self, proj_dir):
        """Each project should have at least one PCB file."""
        pcb_files = list(proj_dir.glob("*.kicad_pcb"))
        assert len(pcb_files) >= 1, f"No .kicad_pcb file in {proj_dir.name}"

    @pytest.mark.parametrize("proj_dir", get_project_dirs(),
                             ids=lambda p: p.name)
    def test_project_has_schematic_file(self, proj_dir):
        """Each project should have at least one schematic file."""
        sch_files = list(proj_dir.glob("*.kicad_sch"))
        assert len(sch_files) >= 1, f"No .kicad_sch file in {proj_dir.name}"


# ============================================================================
# PCB Loading Tests
# ============================================================================

class TestPcbLoading:
    """Tests for loading PCB files from projects."""

    @pytest.mark.parametrize("pcb_path", get_project_pcbs(),
                             ids=lambda p: p.stem)
    def test_pcb_loads_successfully(self, pcb_path):
        """PCB file should load without errors."""
        from kicad_monkey import KiCadPcb

        pcb = KiCadPcb.from_file(pcb_path)
        assert pcb is not None

    @pytest.mark.parametrize("pcb_path", get_project_pcbs(),
                             ids=lambda p: p.stem)
    def test_pcb_has_footprints(self, pcb_path):
        """Loaded PCB should have footprints."""
        from kicad_monkey import KiCadPcb

        pcb = KiCadPcb.from_file(pcb_path)
        # Most real PCBs have footprints (allow empty for simple test cases)
        assert pcb.footprints is not None

    @pytest.mark.parametrize("pcb_path", get_project_pcbs(),
                             ids=lambda p: p.stem)
    def test_pcb_has_layers(self, pcb_path):
        """Loaded PCB should have layer definitions."""
        from kicad_monkey import KiCadPcb

        pcb = KiCadPcb.from_file(pcb_path)
        assert pcb.layers is not None
        assert len(pcb.layers) > 0


# ============================================================================
# Component Extraction Tests
# ============================================================================

class TestComponentExtraction:
    """Tests for extracting components from projects."""

    @pytest.mark.parametrize("pcb_path", get_project_pcbs(),
                             ids=lambda p: p.stem)
    def test_footprints_have_reference(self, pcb_path):
        """Footprints should have reference designators."""
        from kicad_monkey import KiCadPcb

        pcb = KiCadPcb.from_file(pcb_path)

        for fp in pcb.footprints:
            # Look for Reference property
            refs = [p for p in fp.properties if p.name == "Reference"]
            assert len(refs) >= 1, f"Footprint {fp.library_link} missing Reference property"

    @pytest.mark.parametrize("pcb_path", get_project_pcbs(),
                             ids=lambda p: p.stem)
    def test_footprints_have_value(self, pcb_path):
        """Footprints should have Value property."""
        from kicad_monkey import KiCadPcb

        pcb = KiCadPcb.from_file(pcb_path)

        for fp in pcb.footprints:
            # Look for Value property
            vals = [p for p in fp.properties if p.name == "Value"]
            assert len(vals) >= 1, f"Footprint {fp.library_link} missing Value property"


# ============================================================================
# Rendering Pipeline Tests
# ============================================================================

class TestRenderingPipeline:
    """Tests for the rendering pipeline on real projects."""

    @pytest.mark.parametrize("pcb_path", get_project_pcbs(),
                             ids=lambda p: p.stem)
    def test_pcb_renders_to_svg(self, pcb_path):
        """PCB should render to SVG without errors."""
        from kicad_monkey import KiCadPcb

        pcb = KiCadPcb.from_file(pcb_path)
        svg = pcb.to_svg(layers=["F.Cu"])

        assert svg is not None
        assert "<svg" in svg
        assert "</svg>" in svg

    @pytest.mark.parametrize("pcb_path", get_project_pcbs(),
                             ids=lambda p: p.stem)
    def test_pcb_renders_all_copper_layers(self, pcb_path):
        """PCB should render all copper layers."""
        from kicad_monkey import KiCadPcb

        pcb = KiCadPcb.from_file(pcb_path)

        # Render front and back copper
        for layer in ["F.Cu", "B.Cu"]:
            svg = pcb.to_svg(layers=[layer])
            assert svg is not None
            assert "<svg" in svg


# ============================================================================
# Round-Trip Tests
# ============================================================================

class TestRoundTrip:
    """Tests for round-trip processing of project files."""

    @pytest.mark.parametrize("pcb_path", get_project_pcbs(),
                             ids=lambda p: p.stem)
    def test_pcb_roundtrip_preserves_footprint_count(self, pcb_path, tmp_path):
        """Round-trip should preserve footprint count."""
        from kicad_monkey import KiCadPcb

        # Load original
        pcb1 = KiCadPcb.from_file(pcb_path)
        original_count = len(pcb1.footprints)

        # Write and reload
        output_path = tmp_path / pcb_path.name
        pcb1.to_file(output_path)
        pcb2 = KiCadPcb.from_file(output_path)

        assert len(pcb2.footprints) == original_count

    @pytest.mark.parametrize("pcb_path", get_project_pcbs(),
                             ids=lambda p: p.stem)
    def test_pcb_roundtrip_preserves_net_count(self, pcb_path, tmp_path):
        """Round-trip should preserve net count."""
        from kicad_monkey import KiCadPcb

        # Load original
        pcb1 = KiCadPcb.from_file(pcb_path)
        original_count = len(pcb1.nets)

        # Write and reload
        output_path = tmp_path / pcb_path.name
        pcb1.to_file(output_path)
        pcb2 = KiCadPcb.from_file(output_path)

        assert len(pcb2.nets) == original_count


# ============================================================================
# Run tests standalone
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
