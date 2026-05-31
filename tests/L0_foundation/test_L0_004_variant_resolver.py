"""
Test L0_004: Effective-properties resolver

Phase C Slice C-3 — exercises ``resolve_symbol`` / ``resolve_footprint``
in isolation, covering the four merge paths the plan calls out: no
override, partial scalar override, full override, and field
replacement / addition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from kicad_monkey import (
    EffectiveSymbolProperties,
    EffectiveFootprintProperties,
    resolve_symbol,
    resolve_footprint,
)


# ---------------------------------------------------------------------------
# Lightweight stand-ins
# ---------------------------------------------------------------------------

@dataclass
class _SymProp:
    key: str
    value: str


@dataclass
class _SymVariant:
    name: str
    dnp: Optional[bool] = None
    exclude_from_sim: Optional[bool] = None
    in_bom: Optional[bool] = None
    on_board: Optional[bool] = None
    in_pos_files: Optional[bool] = None
    fields: list = field(default_factory=list)  # list[(name, value)]


@dataclass
class _SymInstance:
    variants: list = field(default_factory=list)


@dataclass
class _Sym:
    lib_id: str = "Device:R"
    dnp: bool = False
    exclude_from_sim: bool = False
    in_bom: bool = True
    on_board: bool = True
    in_pos_files: bool = True
    properties: list = field(default_factory=list)
    instances: list = field(default_factory=list)


def _make_sym(*, ref="R1", value="10k", overrides=None, base=None) -> _Sym:
    base = base or {}
    sym = _Sym(
        properties=[
            _SymProp(key="Reference", value=ref),
            _SymProp(key="Value", value=value),
        ],
        **base,
    )
    if overrides:
        sym.instances = [_SymInstance(variants=overrides)]
    return sym


@dataclass
class _FpField:
    name: str
    value: str


@dataclass
class _FpVariant:
    name: str
    dnp: Optional[bool] = None
    exclude_from_bom: Optional[bool] = None
    exclude_from_pos_files: Optional[bool] = None
    fields: list = field(default_factory=list)


@dataclass
class _FpProp:
    name: str
    value: str


@dataclass
class _Fp:
    library_link: str = "Resistor_SMD:R_0603_1608Metric"
    attr: list = field(default_factory=list)
    properties: list = field(default_factory=list)
    variants: list = field(default_factory=list)

    @property
    def is_dnp(self) -> bool:
        return "dnp" in self.attr

    @property
    def is_excluded_from_bom(self) -> bool:
        return "exclude_from_bom" in self.attr

    @property
    def is_excluded_from_pos_files(self) -> bool:
        return "exclude_from_pos_files" in self.attr


def _make_fp(*, ref="R1", value="10k", attrs=None, overrides=None) -> _Fp:
    fp = _Fp(
        attr=list(attrs or []),
        properties=[
            _FpProp(name="Reference", value=ref),
            _FpProp(name="Value", value=value),
        ],
        variants=list(overrides or []),
    )
    return fp


# ---------------------------------------------------------------------------
# Symbol resolver — 4 merge paths
# ---------------------------------------------------------------------------

class TestResolveSymbol:
    def test_no_variant_returns_base(self) -> None:
        sym = _make_sym(ref="R1", value="10k")
        eff = resolve_symbol(sym, None)
        assert isinstance(eff, EffectiveSymbolProperties)
        assert eff.reference == "R1"
        assert eff.value == "10k"
        assert eff.dnp is False
        assert eff.in_bom is True
        assert eff.fields["Reference"] == "R1"
        assert eff.fields["Value"] == "10k"

    def test_variant_name_with_no_override_returns_base(self) -> None:
        """Variant name does not match any override → base unchanged."""
        sym = _make_sym(
            ref="R1", value="10k",
            overrides=[_SymVariant(name="Variant1", dnp=True)],
        )
        eff = resolve_symbol(sym, "MissingVariant")
        assert eff.dnp is False
        assert eff.value == "10k"

    def test_partial_scalar_override(self) -> None:
        """Only ``dnp`` is overridden; other scalars fall back to base."""
        sym = _make_sym(
            ref="R1", value="10k",
            base={"in_bom": True, "on_board": True, "exclude_from_sim": False},
            overrides=[_SymVariant(name="V", dnp=True)],
        )
        eff = resolve_symbol(sym, "V")
        assert eff.dnp is True
        assert eff.in_bom is True       # fall-through
        assert eff.on_board is True     # fall-through
        assert eff.exclude_from_sim is False  # fall-through

    def test_full_scalar_override(self) -> None:
        sym = _make_sym(
            ref="R1", value="10k",
            base={"in_bom": True, "on_board": True, "exclude_from_sim": False, "in_pos_files": True},
            overrides=[_SymVariant(
                name="V",
                dnp=True,
                exclude_from_sim=True,
                in_bom=False,
                on_board=False,
                in_pos_files=False,
            )],
        )
        eff = resolve_symbol(sym, "V")
        assert eff.dnp is True
        assert eff.exclude_from_sim is True
        assert eff.in_bom is False
        assert eff.on_board is False
        assert eff.in_pos_files is False

    def test_field_replacement_and_addition(self) -> None:
        """Override fields **replace by name**; new keys are added."""
        sym = _make_sym(
            ref="R1", value="10k",
            overrides=[_SymVariant(
                name="V",
                fields=[("Value", "47k"), ("MPN", "MFR-XYZ")],
            )],
        )
        eff = resolve_symbol(sym, "V")
        assert eff.value == "47k"           # replaced
        assert eff.fields["Value"] == "47k"
        assert eff.fields["MPN"] == "MFR-XYZ"  # newly added
        assert eff.fields["Reference"] == "R1"  # untouched

    def test_field_blank_override_replaces(self) -> None:
        """An override with empty-string value blanks the base field."""
        sym = _make_sym(
            ref="R1", value="10k",
            overrides=[_SymVariant(name="V", fields=[("Value", "")])],
        )
        eff = resolve_symbol(sym, "V")
        assert eff.value == ""
        assert eff.fields["Value"] == ""

    def test_value_override_does_not_change_reference(self) -> None:
        sym = _make_sym(
            ref="R1", value="10k",
            overrides=[_SymVariant(name="V", fields=[("Value", "100k")])],
        )
        eff = resolve_symbol(sym, "V")
        assert eff.reference == "R1"


# ---------------------------------------------------------------------------
# Footprint resolver — 4 merge paths
# ---------------------------------------------------------------------------

class TestResolveFootprint:
    def test_no_variant_returns_base(self) -> None:
        fp = _make_fp(ref="R1", value="10k", attrs=["smd"])
        eff = resolve_footprint(fp, None)
        assert isinstance(eff, EffectiveFootprintProperties)
        assert eff.reference == "R1"
        assert eff.dnp is False
        assert eff.exclude_from_bom is False
        assert eff.fields["Reference"] == "R1"

    def test_variant_name_with_no_override_returns_base(self) -> None:
        fp = _make_fp(
            ref="R1", value="10k", attrs=["smd"],
            overrides=[_FpVariant(name="V", dnp=True)],
        )
        eff = resolve_footprint(fp, "Missing")
        assert eff.dnp is False

    def test_partial_scalar_override(self) -> None:
        fp = _make_fp(
            ref="R1", value="10k", attrs=["smd"],
            overrides=[_FpVariant(name="V", dnp=True)],
        )
        eff = resolve_footprint(fp, "V")
        assert eff.dnp is True
        assert eff.exclude_from_bom is False
        assert eff.exclude_from_pos_files is False

    def test_full_scalar_override(self) -> None:
        fp = _make_fp(
            ref="R1", value="10k", attrs=["smd"],
            overrides=[_FpVariant(
                name="V", dnp=True,
                exclude_from_bom=True,
                exclude_from_pos_files=True,
            )],
        )
        eff = resolve_footprint(fp, "V")
        assert eff.dnp is True
        assert eff.exclude_from_bom is True
        assert eff.exclude_from_pos_files is True

    def test_dnp_attr_promotes_to_base(self) -> None:
        """Base ``dnp`` derives from ``fp.attr`` (KiCad convention)."""
        fp = _make_fp(ref="R1", value="10k", attrs=["smd", "dnp"])
        eff = resolve_footprint(fp, None)
        assert eff.dnp is True

    def test_dnp_attr_can_be_overridden_to_false(self) -> None:
        fp = _make_fp(
            ref="R1", value="10k", attrs=["smd", "dnp"],
            overrides=[_FpVariant(name="V", dnp=False)],
        )
        eff = resolve_footprint(fp, "V")
        assert eff.dnp is False

    def test_field_replacement_and_addition(self) -> None:
        fp = _make_fp(
            ref="R1", value="10k", attrs=["smd"],
            overrides=[_FpVariant(name="V", fields=[
                _FpField(name="Value", value="47k"),
                _FpField(name="Vendor", value="Acme"),
            ])],
        )
        eff = resolve_footprint(fp, "V")
        assert eff.fields["Value"] == "47k"
        assert eff.fields["Vendor"] == "Acme"
        assert eff.fields["Reference"] == "R1"
