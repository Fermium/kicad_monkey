"""
Test L1_015: Hierarchical schematic loading

Phase D Slice D-1. Locks the new ``KiCadSchematic`` hierarchy behaviors:

1. Loading a schematic with sub-sheets resolves and parses each
   referenced ``Sheetfile`` into ``sub_schematics`` (keyed by the
   relative path that appears in the parent's sheet property).
2. ``walk_symbols()`` traverses the full hierarchy and yields the
   correct number of symbols across top + sub-sheets.
3. ``walk_sheets()`` yields each sheet/child pair in declaration order.
4. Loading a flat schematic (no sub-sheets) leaves
   ``sub_schematics`` empty and ``walk_symbols`` equivalent to the
   top-level symbols list.
5. Round-trip is unaffected — the new fields are runtime-only and
   never appear in ``to_text``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kicad_monkey import KiCadSchematic
from kicad_monkey.kicad_sch_sheet import SchSheet, SchSheetProperty
from kicad_monkey.kicad_sch_symbol import SchSymbol
from kicad_monkey.kicad_sym_property import SymProperty
from kicad_monkey.testing.corpus import get_kicad_upstream_qa_dir


@pytest.fixture
def variants_sch() -> Path:
    """Hierarchical fixture: one parent + one sub-sheet (pic_sockets)."""
    return get_kicad_upstream_qa_dir() / "eeschema" / "variants" / "variants.kicad_sch"


@pytest.fixture
def flat_sch() -> Path:
    """Flat fixture: no sub-sheets — cli/variants ships only the parent."""
    return get_kicad_upstream_qa_dir() / "cli" / "variants" / "variants.kicad_sch"


class TestHierarchicalLoad:
    def test_source_path_set_after_from_file(self, variants_sch: Path) -> None:
        sch = KiCadSchematic.from_file(variants_sch)
        assert sch.source_path is not None
        assert sch.source_path.resolve() == variants_sch.resolve()

    def test_sub_schematics_keyed_by_sheetfile(self, variants_sch: Path) -> None:
        sch = KiCadSchematic.from_file(variants_sch)
        # The parent declares exactly one sub-sheet.
        sheet_files = {s.sheet_file for s in sch.sheets}
        assert "pic_sockets.kicad_sch" in sheet_files
        assert "pic_sockets.kicad_sch" in sch.sub_schematics

    def test_sub_schematic_is_loaded(self, variants_sch: Path) -> None:
        sch = KiCadSchematic.from_file(variants_sch)
        child = sch.sub_schematics["pic_sockets.kicad_sch"]
        assert isinstance(child, KiCadSchematic)
        # Sub-sheet has its own symbols.
        assert len(child.symbols) > 0
        # Sub-sheet's source_path resolves under the parent's directory.
        assert child.source_path is not None
        assert child.source_path.parent == sch.source_path.parent

    def test_reused_sheet_file_loads_under_each_parent(self, tmp_path: Path) -> None:
        """The same schematic file can be instantiated in multiple branches."""

        def sheet(file_name: str, name: str, uuid: str) -> SchSheet:
            sh = SchSheet(uuid=uuid)
            sh.properties = [
                SchSheetProperty(key="Sheetname", value=name),
                SchSheetProperty(key="Sheetfile", value=file_name),
            ]
            return sh

        def symbol(ref: str) -> SchSymbol:
            sym = SchSymbol(lib_id="Device:R")
            sym.properties = [
                SymProperty(key="Reference", value=ref),
                SymProperty(key="Value", value="10k"),
            ]
            return sym

        grand = KiCadSchematic()
        grand.uuid = "grand"
        grand.symbols.append(symbol("R_GRAND"))

        child_a = KiCadSchematic()
        child_a.uuid = "child-a"
        child_a.sheets.append(sheet("grand.kicad_sch", "grand", "grand-a"))

        child_b = KiCadSchematic()
        child_b.uuid = "child-b"
        child_b.sheets.append(sheet("grand.kicad_sch", "grand", "grand-b"))

        root = KiCadSchematic()
        root.uuid = "root"
        root.sheets.extend([
            sheet("child_a.kicad_sch", "child_a", "sheet-a"),
            sheet("child_b.kicad_sch", "child_b", "sheet-b"),
        ])

        (tmp_path / "root.kicad_sch").write_text(root.to_text(), encoding="utf-8")
        (tmp_path / "child_a.kicad_sch").write_text(child_a.to_text(), encoding="utf-8")
        (tmp_path / "child_b.kicad_sch").write_text(child_b.to_text(), encoding="utf-8")
        (tmp_path / "grand.kicad_sch").write_text(grand.to_text(), encoding="utf-8")

        sch = KiCadSchematic.from_file(tmp_path / "root.kicad_sch")
        loaded_a = sch.sub_schematics["child_a.kicad_sch"]
        loaded_b = sch.sub_schematics["child_b.kicad_sch"]
        assert "grand.kicad_sch" in loaded_a.sub_schematics
        assert "grand.kicad_sch" in loaded_b.sub_schematics

        grand_prefixes = [
            prefix
            for sym, prefix, _owner in sch.walk_symbols()
            if sym.reference == "R_GRAND"
        ]
        assert grand_prefixes == [
            "/root/sheet-a/grand-a",
            "/root/sheet-b/grand-b",
        ]


class TestWalkSymbols:
    def test_walk_visits_top_then_children(self, variants_sch: Path) -> None:
        sch = KiCadSchematic.from_file(variants_sch)
        walked = list(sch.walk_symbols())
        # Top-level symbols come first, in placement order.
        top_count = len(sch.symbols)
        for i, (sym, _, owner) in enumerate(walked[:top_count]):
            assert owner is sch
            assert sym is sch.symbols[i]
        # Sub-sheet symbols follow.
        for sym, _, owner in walked[top_count:]:
            assert owner is sch.sub_schematics["pic_sockets.kicad_sch"]

    def test_walk_count_matches_sum(self, variants_sch: Path) -> None:
        sch = KiCadSchematic.from_file(variants_sch)
        expected = len(sch.symbols) + sum(
            len(child.symbols) for child in sch.sub_schematics.values()
        )
        assert len(list(sch.walk_symbols())) == expected

    def test_walk_prefix_is_hierarchical_uuid_path(self, variants_sch: Path) -> None:
        sch = KiCadSchematic.from_file(variants_sch)
        top_uuid = sch.uuid
        assert top_uuid  # variants.kicad_sch carries one
        # Top-level symbols use just "/<top_uuid>".
        top_prefix = "/" + top_uuid
        for sym, prefix, owner in sch.walk_symbols():
            if owner is sch:
                assert prefix == top_prefix
            else:
                assert prefix.startswith(top_prefix + "/")

    def test_flat_walk_equals_top_symbols(self, flat_sch: Path) -> None:
        sch = KiCadSchematic.from_file(flat_sch)
        assert sch.sub_schematics == {}
        walked = [s for s, _, _ in sch.walk_symbols()]
        assert walked == sch.symbols


class TestWalkSheets:
    def test_walk_sheets_yields_pairs(self, variants_sch: Path) -> None:
        sch = KiCadSchematic.from_file(variants_sch)
        pairs = list(sch.walk_sheets())
        assert len(pairs) == 1  # variants has exactly one sub-sheet
        sheet, child = pairs[0]
        assert sheet.sheet_file == "pic_sockets.kicad_sch"
        assert child is sch.sub_schematics["pic_sockets.kicad_sch"]

    def test_walk_sheets_empty_on_flat(self, flat_sch: Path) -> None:
        sch = KiCadSchematic.from_file(flat_sch)
        # Flat fixture's sheets either don't exist or can't be resolved
        # (cli/variants is missing pic_sockets.kicad_sch). Either way,
        # walk_sheets yields nothing because sub_schematics is empty.
        assert list(sch.walk_sheets()) == []


class TestHierarchyDoesNotAffectSerialization:
    def test_to_text_succeeds_after_hierarchy_load(self, variants_sch: Path) -> None:
        """to_text must still produce valid schematic output — the new
        ``source_path`` / ``sub_schematics`` fields are runtime-only and
        must not leak into the s-expression form. (Byte-equal round-trip
        on this older fixture is covered elsewhere; here we just lock
        that hierarchy loading didn't break serialization.)"""
        sch = KiCadSchematic.from_file(variants_sch)
        out = sch.to_text()
        assert out.startswith("(kicad_sch")
        assert "source_path" not in out
        assert "sub_schematics" not in out

    def test_top_level_symbol_count_unchanged(self, variants_sch: Path) -> None:
        """Hierarchy loading must not duplicate or drop top-level
        symbols. ``len(sch)`` (which counts top-level placed symbols)
        equals what the bare ``from_text`` produces."""
        text = variants_sch.read_text(encoding="utf-8")
        flat = KiCadSchematic.from_text(text)
        nested = KiCadSchematic.from_file(variants_sch)
        assert len(nested.symbols) == len(flat.symbols)


class TestMissingSubSheetIsTolerated:
    def test_dangling_sheetfile_skipped(self, flat_sch: Path) -> None:
        """cli/variants/variants.kicad_sch declares pic_sockets.kicad_sch
        but the file isn't shipped alongside it. Loading must succeed
        with sub_schematics empty rather than raising."""
        sch = KiCadSchematic.from_file(flat_sch)
        # Parent loaded fine.
        assert sch.source_path is not None
        # Dangling sheetfile reference left no entry in sub_schematics.
        assert "pic_sockets.kicad_sch" not in sch.sub_schematics
