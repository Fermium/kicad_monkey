"""
Test L1_014: Project (.kicad_pro) round-trip + mutation lock

Phase C Slice C-7. Locks the .kicad_pro write path:

1. Byte-equal round-trip via ``to_text`` on every ``.kicad_pro`` in the
   upstream-QA mirror — KiCad writes via ``nlohmann::json::dump(2)``
   and we must produce identical output for the read/edit/save flow
   to be safe.
2. Variant catalog mutators (``add_variant``, ``remove_variant``,
   ``rename_variant``) round-trip through reload.
3. Generic ``set_path`` / ``get_path`` dotted-key escape hatch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kicad_monkey import KiCadProject
from kicad_monkey.testing.corpus import get_kicad_upstream_qa_dir


# ---------------------------------------------------------------------------
# Round-trip lock — byte-equal on every upstream-QA project file
# ---------------------------------------------------------------------------


def _all_kicad_pro_files() -> list[Path]:
    return sorted(get_kicad_upstream_qa_dir().rglob("*.kicad_pro"))


@pytest.mark.parametrize(
    "kicad_pro",
    _all_kicad_pro_files(),
    ids=lambda p: p.relative_to(get_kicad_upstream_qa_dir()).as_posix(),
)
def test_kicad_pro_round_trip_byte_equal(kicad_pro: Path) -> None:
    """``to_text`` must reproduce the on-disk file byte-for-byte."""
    original = kicad_pro.read_text(encoding="utf-8")
    project = KiCadProject.from_file(kicad_pro)
    assert project.to_text() == original


# ---------------------------------------------------------------------------
# Variant catalog mutators
# ---------------------------------------------------------------------------


@pytest.fixture
def variants_pro() -> Path:
    return get_kicad_upstream_qa_dir() / "cli" / "variants" / "variants.kicad_pro"


class TestAddVariant:
    def test_add_appends_to_catalog(self, variants_pro: Path) -> None:
        project = KiCadProject.from_file(variants_pro)
        before = [v.name for v in project.variants]
        added = project.add_variant("ZetaTest", description="for unit test")
        after = [v.name for v in project.variants]
        assert added.name == "ZetaTest"
        assert added.description == "for unit test"
        assert after == before + ["ZetaTest"]

    def test_add_with_no_description_omits_key(self, variants_pro: Path) -> None:
        """KiCad's own emit drops the description key when blank — we
        must too, or we drift on round-trip."""
        project = KiCadProject.from_file(variants_pro)
        project.add_variant("NoDescTest")
        raw_entry = project.raw["schematic"]["variants"][-1]
        assert raw_entry == {"name": "NoDescTest"}
        assert "description" not in raw_entry

    def test_add_duplicate_raises(self, variants_pro: Path) -> None:
        project = KiCadProject.from_file(variants_pro)
        project.add_variant("Dup")
        with pytest.raises(ValueError, match="already exists"):
            project.add_variant("Dup")

    def test_add_round_trips_through_reload(
        self, variants_pro: Path, tmp_path: Path,
    ) -> None:
        """add → save → reload must show the new variant."""
        project = KiCadProject.from_file(variants_pro)
        project.add_variant("CycleTest", description="ping")
        out = tmp_path / "variants.kicad_pro"
        project.save(out)

        reloaded = KiCadProject.from_file(out)
        names = [v.name for v in reloaded.variants]
        assert "CycleTest" in names
        # Description survives the JSON round-trip.
        cycle = next(v for v in reloaded.variants if v.name == "CycleTest")
        assert cycle.description == "ping"

    def test_add_only_changes_variants_block(
        self, variants_pro: Path, tmp_path: Path,
    ) -> None:
        """Outside ``schematic.variants``, the file must be byte-equal
        to the original. Any drift would mean we're reformatting
        unrelated keys."""
        project = KiCadProject.from_file(variants_pro)
        project.add_variant("OnlyVariantsTest")
        out = tmp_path / "variants.kicad_pro"
        project.save(out)

        new_data = json.loads(out.read_text(encoding="utf-8"))
        old_data = json.loads(variants_pro.read_text(encoding="utf-8"))
        # Strip variants list from both, compare the rest.
        new_data["schematic"].pop("variants", None)
        old_data["schematic"].pop("variants", None)
        assert new_data == old_data


class TestRemoveVariant:
    def test_remove_existing_returns_entry(self, variants_pro: Path) -> None:
        project = KiCadProject.from_file(variants_pro)
        existing = project.variants[0].name
        removed = project.remove_variant(existing)
        assert removed is not None
        assert removed.name == existing
        assert existing not in [v.name for v in project.variants]

    def test_remove_missing_returns_none(self, variants_pro: Path) -> None:
        project = KiCadProject.from_file(variants_pro)
        assert project.remove_variant("NoSuchVariantXYZ") is None

    def test_remove_round_trips(
        self, variants_pro: Path, tmp_path: Path,
    ) -> None:
        project = KiCadProject.from_file(variants_pro)
        target = project.variants[0].name
        project.remove_variant(target)
        out = tmp_path / "variants.kicad_pro"
        project.save(out)

        reloaded = KiCadProject.from_file(out)
        assert target not in [v.name for v in reloaded.variants]


class TestRenameVariant:
    def test_rename_existing_returns_true(self, variants_pro: Path) -> None:
        project = KiCadProject.from_file(variants_pro)
        old = project.variants[0].name
        assert project.rename_variant(old, "RenamedXYZ") is True
        assert "RenamedXYZ" in [v.name for v in project.variants]
        assert old not in [v.name for v in project.variants]

    def test_rename_missing_returns_false(self, variants_pro: Path) -> None:
        project = KiCadProject.from_file(variants_pro)
        assert project.rename_variant("NoSuchVariant", "NewName") is False

    def test_rename_to_existing_raises(self, variants_pro: Path) -> None:
        project = KiCadProject.from_file(variants_pro)
        names = [v.name for v in project.variants]
        if len(names) < 2:
            pytest.skip("fixture has fewer than 2 variants")
        with pytest.raises(ValueError, match="already exists"):
            project.rename_variant(names[0], names[1])


# ---------------------------------------------------------------------------
# Generic dotted-path escape hatch
# ---------------------------------------------------------------------------


class TestSetPath:
    def test_set_simple_top_level(self, variants_pro: Path) -> None:
        project = KiCadProject.from_file(variants_pro)
        project.set_path("custom_field", 42)
        assert project.raw["custom_field"] == 42
        assert project.get_path("custom_field") == 42

    def test_set_nested_creates_intermediate_dicts(self, variants_pro: Path) -> None:
        project = KiCadProject.from_file(variants_pro)
        project.set_path("a.b.c", "deep")
        assert project.raw["a"] == {"b": {"c": "deep"}}
        assert project.get_path("a.b.c") == "deep"

    def test_set_through_non_dict_raises(self, variants_pro: Path) -> None:
        project = KiCadProject.from_file(variants_pro)
        project.set_path("x", [1, 2, 3])
        with pytest.raises(TypeError, match="non-dict"):
            project.set_path("x.y", 1)

    def test_set_round_trips_through_save(
        self, variants_pro: Path, tmp_path: Path,
    ) -> None:
        project = KiCadProject.from_file(variants_pro)
        project.set_path("meta.test_marker", "set_path_works")
        out = tmp_path / "variants.kicad_pro"
        project.save(out)
        reloaded = KiCadProject.from_file(out)
        assert reloaded.get_path("meta.test_marker") == "set_path_works"
