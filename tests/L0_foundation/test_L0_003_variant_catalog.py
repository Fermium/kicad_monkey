"""
Test L0_003: VariantCatalog model layer

Phase C Slice C-2 — pure-unit coverage for the catalog discovery
behavior. No real fixtures: we synthesize lightweight stand-ins for
``KiCadProject``, ``KiCadPcb``, and ``KiCadSchematic`` so the test
exercises only the catalog logic.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import pytest

from kicad_monkey import (
    KiCadProject,
    ProjectVariant,
    VariantCatalog,
    VariantOverride,
)
from kicad_monkey.kicad_pcb_other import BoardVariant


# ---------------------------------------------------------------------------
# Lightweight stand-ins (avoids depending on full PCB / SCH parsing)
# ---------------------------------------------------------------------------

@dataclass
class _FakeFpVariant:
    name: str


@dataclass
class _FakeFootprint:
    reference: str
    variants: list = field(default_factory=list)


@dataclass
class _FakePcb:
    variants: list = field(default_factory=list)
    footprints: list = field(default_factory=list)


@dataclass
class _FakeSchSymVariant:
    name: str


@dataclass
class _FakeSchSymInstance:
    variants: list = field(default_factory=list)


@dataclass
class _FakeSchSymbol:
    reference: str = ""
    instances: list = field(default_factory=list)


@dataclass
class _FakeSch:
    symbols: list = field(default_factory=list)
    sheets: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# from_project / from_pcb / from_overrides
# ---------------------------------------------------------------------------

class TestCatalogSources:
    def test_from_project_takes_canonical_list(self) -> None:
        proj = KiCadProject(
            variants=[
                ProjectVariant(name="A", description="alpha"),
                ProjectVariant(name="B"),
            ]
        )
        cat = VariantCatalog.from_project(proj)
        assert cat.names == ["A", "B"]
        assert cat.get("A").description == "alpha"
        assert cat.get("B").description is None
        assert "A" in cat
        assert "missing" not in cat
        assert len(cat) == 2

    def test_from_pcb_extracts_board_variants(self) -> None:
        pcb = _FakePcb(variants=[
            BoardVariant(name="X", description="board-x"),
            BoardVariant(name="Y"),
        ])
        cat = VariantCatalog.from_pcb(pcb)
        assert cat.names == ["X", "Y"]
        assert cat.get("X").description == "board-x"

    def test_from_overrides_collects_symbol_and_fp_names(self) -> None:
        sch = _FakeSch(symbols=[
            _FakeSchSymbol(
                reference="R1",
                instances=[
                    _FakeSchSymInstance(variants=[
                        _FakeSchSymVariant("V1"),
                        _FakeSchSymVariant("V2"),
                    ])
                ],
            ),
        ])
        pcb = _FakePcb(footprints=[
            _FakeFootprint(reference="R1", variants=[_FakeFpVariant("V2")]),
            _FakeFootprint(reference="R2", variants=[_FakeFpVariant("V3")]),
        ])
        cat = VariantCatalog.from_overrides(schematic=sch, pcb=pcb)
        assert cat.names == ["V1", "V2", "V3"]


# ---------------------------------------------------------------------------
# discover() — union + warning behavior
# ---------------------------------------------------------------------------

class TestCatalogDiscover:
    def test_discover_uses_canonical_when_only_project(self) -> None:
        proj = KiCadProject(variants=[ProjectVariant(name="A")])
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any warn = fail
            cat = VariantCatalog.discover(project=proj)
        assert cat.names == ["A"]

    def test_discover_no_warning_when_pcb_matches_project(self) -> None:
        proj = KiCadProject(variants=[ProjectVariant(name="A")])
        pcb = _FakePcb(variants=[BoardVariant(name="A")])
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            cat = VariantCatalog.discover(project=proj, pcb=pcb)
        assert cat.names == ["A"]

    def test_discover_warns_when_pcb_has_extra(self) -> None:
        proj = KiCadProject(variants=[ProjectVariant(name="A")])
        pcb = _FakePcb(variants=[
            BoardVariant(name="A"),
            BoardVariant(name="B"),  # not in canonical
        ])
        with pytest.warns(UserWarning, match="PCB top-level"):
            cat = VariantCatalog.discover(project=proj, pcb=pcb)
        # Extra is appended at the end
        assert cat.names == ["A", "B"]

    def test_discover_warns_when_overrides_have_extra(self) -> None:
        proj = KiCadProject(variants=[ProjectVariant(name="A")])
        sch = _FakeSch(symbols=[
            _FakeSchSymbol(reference="R1", instances=[
                _FakeSchSymInstance(variants=[_FakeSchSymVariant("Z")])
            ])
        ])
        with pytest.warns(UserWarning, match="override blocks"):
            cat = VariantCatalog.discover(project=proj, schematic=sch)
        assert cat.names == ["A", "Z"]

    def test_discover_silent_without_project(self) -> None:
        """No project → no inconsistency to warn about (no canonical)."""
        pcb = _FakePcb(variants=[BoardVariant(name="X")])
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            cat = VariantCatalog.discover(pcb=pcb)
        assert cat.names == ["X"]

    def test_discover_warning_disabled_by_flag(self) -> None:
        proj = KiCadProject(variants=[ProjectVariant(name="A")])
        pcb = _FakePcb(variants=[BoardVariant(name="B")])
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any warn = fail
            cat = VariantCatalog.discover(
                project=proj, pcb=pcb, warn_on_inconsistency=False,
            )
        assert cat.names == ["A", "B"]

    def test_canonical_description_wins_over_pcb(self) -> None:
        proj = KiCadProject(
            variants=[ProjectVariant(name="A", description="canonical")],
        )
        pcb = _FakePcb(variants=[BoardVariant(name="A", description="board-side")])
        cat = VariantCatalog.discover(project=proj, pcb=pcb)
        assert cat.get("A").description == "canonical"


# ---------------------------------------------------------------------------
# VariantOverride
# ---------------------------------------------------------------------------

class TestVariantOverride:
    def test_default_optional_fields_are_none(self) -> None:
        ov = VariantOverride(reference="R1", variant_name="V1")
        assert ov.dnp is None
        assert ov.exclude_from_bom is None
        assert ov.fields == {}

    def test_override_is_frozen(self) -> None:
        ov = VariantOverride(reference="R1", variant_name="V1")
        with pytest.raises(Exception):
            ov.dnp = True  # type: ignore[misc]
