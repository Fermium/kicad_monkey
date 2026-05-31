"""
Subtest: Component Indexing
Stratum: L2_tools
Purpose: Index and lookup components from PCB

Tests for KiCad footprint and symbol name extraction functions.
These tests verify the fast regex-based extraction functions work correctly
for various file formats and edge cases.
"""

import pytest

from kicad_monkey import KiCadNameIndex

from conftest import COMMON_FOOTPRINTS_DIR, COMMON_REFERENCE_SYMBOLS_DIR


NAME_INDEX = KiCadNameIndex()


# ============================================================================
# Footprint Name Extraction Tests
# ============================================================================

class TestFootprintNameExtraction:
    """Tests for KiCadNameIndex.footprint_names method."""

    def test_extract_quoted_footprint_name(self, tmp_path):
        """Test extraction of quoted footprint name."""
        fp_file = tmp_path / "test.kicad_mod"
        fp_file.write_text('(footprint "SOT-23"\n\t(version 20241229)\n)')

        result = NAME_INDEX.footprint_names(fp_file)

        assert result == ["SOT-23"]

    def test_extract_footprint_with_special_chars(self, tmp_path):
        """Test extraction of footprint name with special characters."""
        fp_file = tmp_path / "test.kicad_mod"
        fp_file.write_text('(footprint "QFN-48-1EP_7x7mm_P0.5mm_EP5.1x5.1mm"\n\t(version 20241229)\n)')

        result = NAME_INDEX.footprint_names(fp_file)

        assert result == ["QFN-48-1EP_7x7mm_P0.5mm_EP5.1x5.1mm"]

    def test_extract_module_format(self, tmp_path):
        """Test extraction from older 'module' format."""
        fp_file = tmp_path / "test.kicad_mod"
        fp_file.write_text('(module "R0402_HD"\n\t(layer F.Cu)\n)')

        result = NAME_INDEX.footprint_names(fp_file)

        assert result == ["R0402_HD"]

    def test_extract_unquoted_name(self, tmp_path):
        """Test extraction of unquoted footprint name."""
        fp_file = tmp_path / "test.kicad_mod"
        fp_file.write_text('(footprint SimpleName\n\t(version 20241229)\n)')

        result = NAME_INDEX.footprint_names(fp_file)

        assert result == ["SimpleName"]

    def test_fallback_to_filename(self, tmp_path):
        """Test fallback to filename when no name found in content."""
        fp_file = tmp_path / "MyFootprint.kicad_mod"
        # Malformed file without proper footprint/module declaration
        fp_file.write_text('(something_else "content")')

        result = NAME_INDEX.footprint_names(fp_file)

        assert result == ["MyFootprint"]

    def test_real_footprint_file(self):
        """Test extraction from a real shared-corpus footprint file."""
        fp_file = COMMON_FOOTPRINTS_DIR / "SOT-23.kicad_mod"

        if not fp_file.exists():
            pytest.skip(f"Test file not found: {fp_file}")

        result = NAME_INDEX.footprint_names(fp_file)

        assert result == ["SOT-23"]

    def test_footprint_with_library_prefix(self, tmp_path):
        """Test that library prefixes are extracted correctly (not stripped)."""
        fp_file = tmp_path / "test.kicad_mod"
        fp_file.write_text('(footprint "wn_fp:SOT-23"\n\t(version 20241229)\n)')

        result = NAME_INDEX.footprint_names(fp_file)

        # The function extracts the name as-is from the file
        assert result == ["wn_fp:SOT-23"]


# ============================================================================
# Symbol Name Extraction Tests
# ============================================================================

class TestSymbolNameExtraction:
    """Tests for KiCadNameIndex.symbol_names method."""

    def test_extract_single_symbol(self, tmp_path):
        """Test extraction of single symbol from library."""
        sym_file = tmp_path / "test.kicad_sym"
        sym_file.write_text('''(kicad_symbol_lib
    (version 20241209)
    (generator "kicad_symbol_editor")
    (symbol "C_2P_NP"
        (pin_numbers (hide yes))
    )
)''')

        result = NAME_INDEX.symbol_names(sym_file)

        assert result == ["C_2P_NP"]

    def test_extract_multiple_symbols(self, tmp_path):
        """Test extraction of multiple symbols from library."""
        sym_file = tmp_path / "test.kicad_sym"
        sym_file.write_text('''(kicad_symbol_lib
    (version 20241209)
    (generator "kicad_symbol_editor")
    (symbol "Symbol_A"
        (pin_numbers (hide yes))
    )
    (symbol "Symbol_B"
        (pin_numbers (hide yes))
    )
)''')

        result = NAME_INDEX.symbol_names(sym_file)

        assert "Symbol_A" in result
        assert "Symbol_B" in result
        assert len(result) == 2

    def test_skip_unit_subsymbols(self, tmp_path):
        """Test that unit sub-symbols (e.g., LM358_1_1) are skipped."""
        sym_file = tmp_path / "test.kicad_sym"
        sym_file.write_text('''(kicad_symbol_lib
    (version 20241209)
    (symbol "LM358"
        (pin_numbers (hide yes))
        (symbol "LM358_1_1"
            (rectangle (start 0 0) (end 10 10))
        )
        (symbol "LM358_2_1"
            (rectangle (start 0 0) (end 10 10))
        )
    )
)''')

        result = NAME_INDEX.symbol_names(sym_file)

        # Should only include the main symbol, not the unit definitions
        assert result == ["LM358"]

    def test_keep_symbols_with_underscore_not_units(self, tmp_path):
        """Test that symbols with underscores that aren't units are kept."""
        sym_file = tmp_path / "test.kicad_sym"
        sym_file.write_text('''(kicad_symbol_lib
    (version 20241209)
    (symbol "R_2P_NP"
        (pin_numbers (hide yes))
    )
    (symbol "C_ARRAY_4"
        (pin_numbers (hide yes))
    )
)''')

        result = NAME_INDEX.symbol_names(sym_file)

        # Both should be included - they don't match the unit pattern
        assert "R_2P_NP" in result
        assert "C_ARRAY_4" in result

    def test_fallback_to_filename(self, tmp_path):
        """Test fallback to filename when no symbol found."""
        sym_file = tmp_path / "MySymbol.kicad_sym"
        # Empty or malformed file
        sym_file.write_text('(kicad_symbol_lib)')

        result = NAME_INDEX.symbol_names(sym_file)

        assert result == ["MySymbol"]

    def test_real_symbol_file(self):
        """Test extraction from a real shared-corpus symbol file."""
        sym_file = COMMON_REFERENCE_SYMBOLS_DIR / "Capacitor.kicad_sym"

        if not sym_file.exists():
            pytest.skip(f"Test file not found: {sym_file}")

        result = NAME_INDEX.symbol_names(sym_file)

        # Should extract the main symbol name
        assert len(result) >= 1
        # The file contains C_2P_NP symbol
        assert "C_2P_NP" in result

    def test_symbol_with_library_prefix(self, tmp_path):
        """Test extraction of symbol with library prefix."""
        sym_file = tmp_path / "test.kicad_sym"
        sym_file.write_text('''(kicad_symbol_lib
    (version 20241209)
    (symbol "wn_sym:Resistor"
        (pin_numbers (hide yes))
    )
)''')

        result = NAME_INDEX.symbol_names(sym_file)

        assert result == ["wn_sym:Resistor"]


# ============================================================================
# Footprint Dictionary Builder Tests
# ============================================================================

class TestFootprintDictBuilder:
    """Tests for KiCadNameIndex.build_footprint_index method."""

    def test_build_dict_from_directory(self, tmp_path):
        """Test building footprint dict from directory with multiple files."""
        # Create test files
        (tmp_path / "resistor.kicad_mod").write_text('(footprint "R0402")')
        (tmp_path / "capacitor.kicad_mod").write_text('(footprint "C0603")')

        result = NAME_INDEX.build_footprint_index(tmp_path)

        assert "R0402" in result
        assert "C0603" in result
        assert len(result) == 2

    def test_build_dict_with_nested_directories(self, tmp_path):
        """Test building dict recursively."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "top.kicad_mod").write_text('(footprint "TopFP")')
        (subdir / "nested.kicad_mod").write_text('(footprint "NestedFP")')

        result = NAME_INDEX.build_footprint_index(tmp_path)

        assert "TopFP" in result
        assert "NestedFP" in result

    def test_real_footprint_directory(self):
        """Test building dict from the shared common footprint corpus."""
        fp_dir = COMMON_FOOTPRINTS_DIR

        if not fp_dir.exists():
            pytest.skip(f"Test directory not found: {fp_dir}")

        result = NAME_INDEX.build_footprint_index(fp_dir)

        # Should have many footprints
        assert len(result) > 10
        # Check a specific footprint we know exists
        assert "SOT-23" in result


# ============================================================================
# Symbol Dictionary Builder Tests
# ============================================================================

class TestSymbolDictBuilder:
    """Tests for KiCadNameIndex.build_symbol_index method."""

    def test_build_dict_from_directory(self, tmp_path):
        """Test building symbol dict from directory."""
        (tmp_path / "res.kicad_sym").write_text('''(kicad_symbol_lib
    (symbol "Resistor"))''')
        (tmp_path / "cap.kicad_sym").write_text('''(kicad_symbol_lib
    (symbol "Capacitor"))''')

        result = NAME_INDEX.build_symbol_index(tmp_path)

        assert "Resistor" in result
        assert "Capacitor" in result

    def test_real_symbol_directory(self):
        """Test building dict from the shared reference symbol corpus."""
        sym_dir = COMMON_REFERENCE_SYMBOLS_DIR

        if not sym_dir.exists():
            pytest.skip(f"Test directory not found: {sym_dir}")

        result = NAME_INDEX.build_symbol_index(sym_dir)

        # Should have symbols
        assert len(result) > 0


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Edge case tests for the extraction functions."""

    def test_footprint_empty_file(self, tmp_path):
        """Test handling of empty file."""
        fp_file = tmp_path / "empty.kicad_mod"
        fp_file.write_text("")

        result = NAME_INDEX.footprint_names(fp_file)

        # Should fallback to filename
        assert result == ["empty"]

    def test_symbol_empty_file(self, tmp_path):
        """Test handling of empty symbol file."""
        sym_file = tmp_path / "empty.kicad_sym"
        sym_file.write_text("")

        result = NAME_INDEX.symbol_names(sym_file)

        # Should fallback to filename
        assert result == ["empty"]

    def test_footprint_whitespace_in_name(self, tmp_path):
        """Test footprint with spaces in name."""
        fp_file = tmp_path / "test.kicad_mod"
        fp_file.write_text('(footprint "My Custom Footprint")')

        result = NAME_INDEX.footprint_names(fp_file)

        assert result == ["My Custom Footprint"]

    def test_symbol_unicode_name(self, tmp_path):
        """Test symbol with unicode characters."""
        sym_file = tmp_path / "test.kicad_sym"
        sym_file.write_text('''(kicad_symbol_lib
    (symbol "Résistance_100Ω"))''', encoding='utf-8')

        result = NAME_INDEX.symbol_names(sym_file)

        assert result == ["Résistance_100Ω"]

    def test_footprint_returns_list(self, tmp_path):
        """Test that footprint function always returns a list."""
        fp_file = tmp_path / "test.kicad_mod"
        fp_file.write_text('(footprint "Test")')

        result = NAME_INDEX.footprint_names(fp_file)

        assert isinstance(result, list)
        assert len(result) == 1

    def test_symbol_returns_list(self, tmp_path):
        """Test that symbol function always returns a list."""
        sym_file = tmp_path / "test.kicad_sym"
        sym_file.write_text('(kicad_symbol_lib (symbol "Test"))')

        result = NAME_INDEX.symbol_names(sym_file)

        assert isinstance(result, list)


# ============================================================================
# Run tests standalone
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
