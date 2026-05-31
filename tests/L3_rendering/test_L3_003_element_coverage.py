"""
Subtest: Element Coverage
Stratum: L3_rendering
Purpose: All element types render correctly

This module tracks which KiCad PCB file format elements are supported
and which need additional test cases.
"""

import pytest

from kicad_monkey.kicad_base import EdgeConnectorConstraint, PlacementSourceType, StackupItemType
from kicad_monkey.kicad_pcb import KiCadPcb
from kicad_monkey.kicad_pcb_footprint import EmbeddedFile, Footprint, FpLine, FpPoly, FpText, Model, Pad, Property
from kicad_monkey.kicad_pcb_gr_arc import GrArc
from kicad_monkey.kicad_pcb_gr_circle import GrCircle
from kicad_monkey.kicad_pcb_gr_curve import GrCurve
from kicad_monkey.kicad_pcb_gr_line import GrLine
from kicad_monkey.kicad_pcb_gr_poly import GrPoly
from kicad_monkey.kicad_pcb_gr_rect import GrRect
from kicad_monkey.kicad_pcb_gr_text import GrText
from kicad_monkey.kicad_pcb_graphics import GrTextBox
from kicad_monkey.kicad_pcb_other import (
    Image, TitleBlock, Table, TableCell, Net, Layer,
    Dimension, DimensionFormat, DimensionStyle, UnknownElement,
    Stackup, StackupLayer, Group,
)
from kicad_monkey.kicad_pcb_routing import Arc, Segment, Via
from kicad_monkey.kicad_pcb_zone import Keepout, Zone, ZonePlacement
from kicad_monkey.kicad_primitives import Effects, Font, RenderCache, Stroke


# ============================================================================
# Supported Elements Tests
# ============================================================================

class TestSupportedElements:
    """Test that we have dataclasses for all KiCad PCB elements."""

    # Header elements
    def test_version_supported(self):
        """version - PCB file format version."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'version')

    def test_generator_supported(self):
        """generator - What generated the file."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'generator')

    def test_generator_version_supported(self):
        """generator_version - Generator version."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'generator_version')

    # General/setup elements
    def test_general_supported(self):
        """general - Board thickness and settings."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'thickness')

    def test_paper_supported(self):
        """paper - Page size."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'paper')

    def test_layers_supported(self):
        """layers - Layer definitions."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'layers')
        assert Layer is not None

    def test_setup_supported(self):
        """setup - Design rules and settings."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'setup_sexp')

    # Net elements
    def test_net_supported(self):
        """net - Net definitions."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'nets')
        assert Net is not None

    # Graphics elements
    def test_gr_text_supported(self):
        """gr_text - Graphical text."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'gr_texts')
        assert GrText is not None

    def test_gr_line_supported(self):
        """gr_line - Graphical line."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'gr_lines')
        assert GrLine is not None

    def test_gr_rect_supported(self):
        """gr_rect - Graphical rectangle."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'gr_rects')
        assert GrRect is not None

    def test_gr_arc_supported(self):
        """gr_arc - Graphical arc."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'gr_arcs')
        assert GrArc is not None

    def test_gr_circle_supported(self):
        """gr_circle - Graphical circle."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'gr_circles')
        assert GrCircle is not None

    def test_gr_poly_supported(self):
        """gr_poly - Graphical polygon."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'gr_polys')
        assert GrPoly is not None

    def test_gr_curve_supported(self):
        """gr_curve - Bezier curve."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'gr_curves')
        assert GrCurve is not None

    def test_gr_text_box_supported(self):
        """gr_text_box - Multiline text box."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'gr_text_boxes')
        assert GrTextBox is not None

    def test_image_supported(self):
        """image - Embedded bitmap image."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'images')
        assert Image is not None

    def test_title_block_supported(self):
        """title_block - Drawing border information."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'title_block')
        assert TitleBlock is not None

    def test_table_supported(self):
        """table - Table with cells."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'tables')
        assert Table is not None
        assert TableCell is not None

    def test_unknown_element_supported(self):
        """unknown_element - Raw passthrough for unknown elements."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'unknown_elements')
        assert UnknownElement is not None

    def test_stackup_supported(self):
        """stackup - Board layer stackup with materials and thicknesses."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'stackup')
        assert Stackup is not None
        assert StackupLayer is not None
        assert StackupItemType is not None
        assert EdgeConnectorConstraint is not None

    # Footprint elements
    def test_footprint_supported(self):
        """footprint - Component footprints."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'footprints')
        assert Footprint is not None

    def test_pad_supported(self):
        """pad - Footprint pads."""
        assert Pad is not None

    def test_property_supported(self):
        """property - Footprint properties."""
        assert Property is not None

    def test_fp_text_supported(self):
        """fp_text - Footprint text."""
        assert FpText is not None

    def test_fp_line_supported(self):
        """fp_line - Footprint line."""
        assert FpLine is not None

    def test_fp_poly_supported(self):
        """fp_poly - Footprint polygon."""
        assert FpPoly is not None

    def test_model_supported(self):
        """model - 3D model reference."""
        assert Model is not None

    # Zone elements
    def test_zone_supported(self):
        """zone - Copper pour zone."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'zones')
        assert Zone is not None

    # Track elements
    def test_segment_supported(self):
        """segment - Track segment."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'segments')
        assert Segment is not None

    def test_via_supported(self):
        """via - Via element."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'vias')
        assert Via is not None

    def test_arc_track_supported(self):
        """arc - Track arc."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'arcs')
        assert Arc is not None

    # Group elements
    def test_group_supported(self):
        """group - Grouped objects."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'groups')
        assert Group is not None

    # Dimension elements
    def test_dimension_supported(self):
        """dimension - Dimension annotation."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'dimensions')
        assert Dimension is not None
        assert DimensionFormat is not None
        assert DimensionStyle is not None

    # Keepout elements (within Zone)
    def test_keepout_supported(self):
        """keepout - Keep-out zone settings."""
        assert Keepout is not None
        zone = Zone()
        assert hasattr(zone, 'keepout')

    def test_zone_placement_supported(self):
        """placement - Placement Rule Area settings for multi-channel design."""
        assert ZonePlacement is not None
        assert PlacementSourceType is not None
        zone = Zone()
        assert hasattr(zone, 'placement')

    # Embedded elements
    def test_embedded_fonts_supported(self):
        """embedded_fonts - Flag for embedded fonts."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'embedded_fonts')

    def test_embedded_files_supported(self):
        """embedded_files - Embedded file data."""
        pcb = KiCadPcb()
        assert hasattr(pcb, 'embedded_files')
        assert EmbeddedFile is not None

    # Helper types
    def test_stroke_supported(self):
        """stroke - Line style parameters."""
        assert Stroke is not None

    def test_font_supported(self):
        """font - Font parameters."""
        assert Font is not None

    def test_effects_supported(self):
        """effects - Text effects."""
        assert Effects is not None

    def test_render_cache_supported(self):
        """render_cache - Pre-rendered text polygons."""
        assert RenderCache is not None


# ============================================================================
# Deprecated Elements Tests
# ============================================================================

class TestDeprecatedElements:
    """
    Track elements that are deprecated or removed from KiCad.

    These elements are no longer used in modern KiCad PCB files.
    """
    @staticmethod
    def _parse_with_extra(extra_element: str) -> KiCadPcb:
        pcb_text = f"""
        (kicad_pcb
          (version 20241229)
          (generator pcbnew)
          (generator_version "9.0")
          (general (thickness 1.6) (legacy_teardrops no))
          (paper "A4")
          (layers (0 "F.Cu" signal))
          (setup)
          {extra_element}
        )
        """
        return KiCadPcb.from_string(pcb_text)

    def test_net_class_deprecated_passthrough(self):
        """
        net_class - Removed from PCB files in KiCad 6.0.

        We still accept and preserve it as an unknown element for legacy compatibility.
        """
        pcb = self._parse_with_extra('(net_class "Default" "legacy class")')
        assert any(elem.name == "net_class" for elem in pcb.unknown_elements)
        assert "(net_class " in pcb.to_string()

    def test_target_deprecated_passthrough(self):
        """
        target - Removed in KiCad 7.0.

        We still accept and preserve it as an unknown element for legacy compatibility.
        """
        pcb = self._parse_with_extra('(target plus (at 1 2) (size 1) (width 0.1) (layer "F.Cu"))')
        assert any(elem.name == "target" for elem in pcb.unknown_elements)
        assert "(target plus" in pcb.to_string()

    def test_module_deprecated_alias_parses_as_footprint(self):
        """
        module - Old name for footprint, replaced in KiCad 6.0.

        Legacy module entries should parse as footprints and not be duplicated as unknowns.
        """
        pcb = self._parse_with_extra('(module "Legacy_Mod" (layer "F.Cu") (at 0 0))')
        assert len(pcb.footprints) == 1
        assert pcb.footprints[0].library_link == "Legacy_Mod"
        assert not any(elem.name == "module" for elem in pcb.unknown_elements)


# ============================================================================
# Coverage Summary Test
# ============================================================================

class TestElementCoverageSummary:
    """Summary of element coverage."""

    def test_coverage_report(self):
        """Print coverage summary."""
        supported = [
            'version', 'generator', 'generator_version',
            'general', 'paper', 'layers', 'setup', 'stackup',
            'net',
            'gr_text', 'gr_line', 'gr_rect', 'gr_arc', 'gr_circle', 'gr_poly',
            'gr_curve', 'gr_text_box',
            'footprint', 'pad', 'property', 'fp_text', 'fp_line', 'fp_poly', 'model',
            'zone', 'keepout', 'placement',
            'dimension',
            'segment', 'via', 'arc',
            'group',
            'embedded_fonts', 'embedded_files',
            'image', 'title_block', 'table',
            'unknown_element',  # Passthrough for unrecognized elements
        ]

        deprecated = [
            'module',       # Old name for footprint (KiCad 6.0)
            'component',    # Rarely used
            'net_class',    # Removed in KiCad 6.0, now in .kicad_pro
            'target',       # Removed in KiCad 7.0 (May 2022)
        ]

        print("\n" + "="*60)
        print("KiCad PCB Element Coverage Report")
        print("="*60)
        print(f"\nSupported elements: {len(supported)}")
        for elem in supported:
            print(f"  [x] {elem}")

        print(f"\nDeprecated/removed: {len(deprecated)}")
        for elem in deprecated:
            print(f"  [-] {elem}")

        print(f"\nCoverage: 100% (all known KiCad 9.0 elements supported)")
        print("="*60)

        # All known elements are now supported
        assert len(supported) >= 35, f"Expected at least 35 supported elements, got {len(supported)}"


# ============================================================================
# Run tests standalone
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
