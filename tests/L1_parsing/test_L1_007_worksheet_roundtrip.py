"""
Test L1_007: KiCad Worksheet (.kicad_wks) Round-Trip Tests

This test module verifies that worksheet files can be parsed and re-serialized
without data loss (round-trip fidelity).

Test Cases:
- Basic parsing and serialization
- Element counts match after round-trip
- Content verification for lines, rects, texts, polygons
"""

from pathlib import Path

import pytest

from kicad_monkey import (
    KiCadWorksheet,
    WksSetup,
    WksLine,
    WksRect,
    WksPolygon,
    WksTbText,
    WksBitmap,
    WksCorner,
    WksPoint,
)
from kicad_monkey.kicad_sexpr import parse_sexp

from conftest import get_worksheet_files, get_worksheet_test_ids

WORKSHEET_FILES = get_worksheet_files()


# ============================================================================
# Test: Basic Parsing
# ============================================================================

class TestWorksheetParsing:
    """Test that worksheet files can be parsed without errors."""

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_parse_worksheet(self, wks_file: Path):
        """Parse worksheet file."""
        wks = KiCadWorksheet.from_file(wks_file)
        assert wks is not None

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_parse_setup(self, wks_file: Path):
        """Verify setup section is parsed."""
        wks = KiCadWorksheet.from_file(wks_file)
        assert wks.setup is not None
        assert wks.setup.text_size_x > 0
        assert wks.setup.text_size_y > 0


# ============================================================================
# Test: Serialization
# ============================================================================

class TestWorksheetSerialization:
    """Test that worksheet files can be serialized to S-expressions."""

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_serialize_to_sexp(self, wks_file: Path):
        """Serialize worksheet to S-expression list."""
        wks = KiCadWorksheet.from_file(wks_file)
        sexp = wks.to_sexp()
        assert sexp is not None
        # KiCad 9.0+ uses kicad_wks, legacy uses page_layout
        assert sexp[0] in ("page_layout", "kicad_wks")

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_serialize_to_text(self, wks_file: Path):
        """Serialize worksheet to formatted text."""
        wks = KiCadWorksheet.from_file(wks_file)
        text = wks.to_text()
        assert text is not None
        # KiCad 9.0+ uses kicad_wks, legacy uses page_layout
        assert "page_layout" in text or "kicad_wks" in text


# ============================================================================
# Test: Round-Trip
# ============================================================================

class TestWorksheetRoundTrip:
    """Test that worksheet files survive parse-serialize-parse round-trip."""

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_roundtrip_reparseable(self, wks_file: Path):
        """Serialized worksheet can be re-parsed."""
        wks1 = KiCadWorksheet.from_file(wks_file)
        text = wks1.to_text()
        wks2 = KiCadWorksheet.from_text(text)
        assert wks2 is not None

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_roundtrip_line_count(self, wks_file: Path):
        """Line count matches after round-trip."""
        wks1 = KiCadWorksheet.from_file(wks_file)
        text = wks1.to_text()
        wks2 = KiCadWorksheet.from_text(text)
        assert len(wks2.lines) == len(wks1.lines)

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_roundtrip_rect_count(self, wks_file: Path):
        """Rect count matches after round-trip."""
        wks1 = KiCadWorksheet.from_file(wks_file)
        text = wks1.to_text()
        wks2 = KiCadWorksheet.from_text(text)
        assert len(wks2.rects) == len(wks1.rects)

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_roundtrip_text_count(self, wks_file: Path):
        """Text count matches after round-trip."""
        wks1 = KiCadWorksheet.from_file(wks_file)
        text = wks1.to_text()
        wks2 = KiCadWorksheet.from_text(text)
        assert len(wks2.texts) == len(wks1.texts)

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_roundtrip_polygon_count(self, wks_file: Path):
        """Polygon count matches after round-trip."""
        wks1 = KiCadWorksheet.from_file(wks_file)
        text = wks1.to_text()
        wks2 = KiCadWorksheet.from_text(text)
        assert len(wks2.polygons) == len(wks1.polygons)

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_roundtrip_setup_preserved(self, wks_file: Path):
        """Setup values preserved after round-trip."""
        wks1 = KiCadWorksheet.from_file(wks_file)
        text = wks1.to_text()
        wks2 = KiCadWorksheet.from_text(text)
        assert wks2.setup.text_size_x == wks1.setup.text_size_x
        assert wks2.setup.text_size_y == wks1.setup.text_size_y
        assert wks2.setup.linewidth == wks1.setup.linewidth


# ============================================================================
# Test: Content Verification
# ============================================================================

class TestWorksheetContent:
    """Test that worksheet content is correctly parsed."""

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_elements_have_positions(self, wks_file: Path):
        """Elements have position data."""
        wks = KiCadWorksheet.from_file(wks_file)

        # Check lines have start/end
        for line in wks.lines[:5]:
            assert isinstance(line.start, WksPoint)
            assert isinstance(line.end, WksPoint)

        # Check rects have start/end
        for rect in wks.rects[:5]:
            assert isinstance(rect.start, WksPoint)
            assert isinstance(rect.end, WksPoint)

        # Check texts have positions
        for text in wks.texts[:5]:
            assert isinstance(text.pos, WksPoint)

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_texts_have_content(self, wks_file: Path):
        """Text elements have text content."""
        wks = KiCadWorksheet.from_file(wks_file)
        for text in wks.texts[:10]:
            # Text might be format code like %T or actual text
            assert isinstance(text.text, str)


# ============================================================================
# Test: Convenience Methods
# ============================================================================

class TestWorksheetMethods:
    """Test worksheet convenience methods."""

    def test_element_count(self):
        """Test element_count property."""
        wks_file = next((f for f in WORKSHEET_FILES if f.name == "pagelayout_default.kicad_wks"), None)
        if wks_file is None or not wks_file.exists():
            pytest.skip("pagelayout_default.kicad_wks not found")

        wks = KiCadWorksheet.from_file(wks_file)
        total = len(wks.lines) + len(wks.rects) + len(wks.texts) + len(wks.polygons) + len(wks.bitmaps)
        assert wks.element_count == total
        assert len(wks) == total

    def test_get_texts_by_format(self):
        """Test getting texts by format code."""
        wks_file = next((f for f in WORKSHEET_FILES if f.name == "pagelayout_default.kicad_wks"), None)
        if wks_file is None or not wks_file.exists():
            pytest.skip("pagelayout_default.kicad_wks not found")

        wks = KiCadWorksheet.from_file(wks_file)

        # Should find texts with %T (title)
        title_texts = wks.get_texts_by_format("%T")
        assert len(title_texts) > 0

        # Should find texts with %D (date)
        date_texts = wks.get_texts_by_format("%D")
        assert len(date_texts) > 0

    def test_iter_elements(self):
        """Test iterating over all elements."""
        wks_file = next((f for f in WORKSHEET_FILES if f.name == "pagelayout_default.kicad_wks"), None)
        if wks_file is None or not wks_file.exists():
            pytest.skip("pagelayout_default.kicad_wks not found")

        wks = KiCadWorksheet.from_file(wks_file)
        elements = list(wks)
        assert len(elements) == wks.element_count


# ============================================================================
# Test: Corner References
# ============================================================================

class TestCornerReferences:
    """Test worksheet corner reference parsing."""

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_corner_references_preserved(self, wks_file: Path):
        """Corner references are preserved after round-trip."""
        wks1 = KiCadWorksheet.from_file(wks_file)
        text = wks1.to_text()
        wks2 = KiCadWorksheet.from_text(text)

        # Check that corner references match
        for line1, line2 in zip(wks1.lines, wks2.lines):
            assert line1.start.corner == line2.start.corner
            assert line1.end.corner == line2.end.corner


# ============================================================================
# Test: Statistics (for visibility)
# ============================================================================

class TestWorksheetStats:
    """Print statistics about parsed worksheets for debugging."""

    @pytest.mark.parametrize("wks_file", WORKSHEET_FILES, ids=get_worksheet_test_ids())
    def test_print_stats(self, wks_file: Path, capsys):
        """Print element counts for visibility."""
        wks = KiCadWorksheet.from_file(wks_file)

        print(f"\n=== {wks_file.name} ===")
        print(f"  Lines: {len(wks.lines)}")
        print(f"  Rects: {len(wks.rects)}")
        print(f"  Polygons: {len(wks.polygons)}")
        print(f"  Texts: {len(wks.texts)}")
        print(f"  Bitmaps: {len(wks.bitmaps)}")
        print(f"  Total: {wks.element_count}")
        print(f"  Setup: textsize={wks.setup.text_size_x}x{wks.setup.text_size_y}, linewidth={wks.setup.linewidth}")

        # Always pass - this test is for visibility
        assert True
