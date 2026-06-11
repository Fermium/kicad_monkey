"""
Test L2_007: Variant-aware pick-and-place (pos) oracle

Phase E Slice E-1 — symmetric counterpart to L2_005's BOM oracle.
Validates that ``assemble()``'s ``effective_in_pos_files`` flag (combined
with the footprint's PCB-side DNP attribute) matches KiCad's own
``kicad-cli pcb export pos`` output exactly.

Two semantics points worth noting:

1. **Pos export is PCB-driven, not schematic-driven.** ``kicad-cli pcb
   export pos`` walks the ``.kicad_pcb`` only — schematic-side variant
   ``dnp`` overrides do not propagate to the PCB unless the user has
   run "Update PCB from Schematic". The pos oracle therefore filters
   on ``c.footprint.dnp`` rather than ``c.effective_dnp`` (which ORs
   schematic + PCB sides for BOM purposes).

2. **The upstream QA fixtures don't include per-footprint variant
   overrides on the PCB side.** The variant catalog exists on the
   PCB but no ``(variant ...)`` override blocks are attached to
   footprints. So pos output is identical across variants for the
   shipping fixtures — but the oracle still proves we agree, and the
   PCB-side ``(attr exclude_from_pos_files)`` filter is exercised
   (7 footprints in the fixture have it set).

Schematic source: ``eeschema/variants/`` (same as L2_005). The PCB
ships 63 footprints; pos export emits 56 (7 are excluded via
``(attr exclude_from_pos_files)``).
"""

from __future__ import annotations

import csv
import subprocess
import tempfile
from pathlib import Path

import pytest

from kicad_cli_resolver import resolve_kicad_cli
from kicad_monkey import KiCadSchematic, KiCadPcb, assemble
from kicad_monkey.testing.corpus import get_kicad_upstream_qa_dir


# ---------------------------------------------------------------------------
# Fixture lookup
# ---------------------------------------------------------------------------


def _variants_dir() -> Path:
    return get_kicad_upstream_qa_dir() / "eeschema" / "variants"


def _variants_sch() -> Path:
    return _variants_dir() / "variants.kicad_sch"


def _variants_pcb() -> Path:
    return _variants_dir() / "variants.kicad_pcb"


# ---------------------------------------------------------------------------
# kicad-cli resolution
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kicad_cli() -> Path:
    # `pcb export pos` needs the pcbnew kiface; schematic-only staged builds
    # cannot run it.
    cli = resolve_kicad_cli(required_capability="pcb_svg")
    if cli is None or not Path(cli).exists():
        pytest.skip("no PCB-capable kicad-cli resolvable on this machine")
    return Path(cli)


def _run_kicad_cli_pos(
    cli: Path, pcb_path: Path, out_dir: Path, variant: str | None,
) -> Path:
    out_path = out_dir / f"pos_{variant or 'default'}.csv"
    cmd = [str(cli), "pcb", "export", "pos", "--format", "csv"]
    if variant:
        cmd.extend(["--variant", variant])
    cmd.extend([
        "--exclude-dnp",
        "-o", str(out_path),
        str(pcb_path),
    ])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(
            f"kicad-cli pos failed (rc={proc.returncode}):\n"
            f"  cmd: {cmd}\n"
            f"  stdout: {proc.stdout[:400]}\n"
            f"  stderr: {proc.stderr[:400]}"
        )
    return out_path


def _read_pos_csv(path: Path) -> dict[str, dict[str, str]]:
    """Return {ref: row_dict} from a kicad-cli pos CSV."""
    out: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ref = row.get("Ref") or row.get("Reference") or ""
            if ref:
                out[ref] = row
    return out


def _pos_eligible_refs(components) -> set[str]:
    """Refs that ``assemble()`` would expose to KiCad's pos emit:
    have a footprint, in_pos_files set, and PCB-side DNP not set.
    Pos export is PCB-side authoritative, so we use ``footprint.dnp``
    rather than ``effective_dnp`` (which ORs schematic + PCB)."""
    return {
        c.reference for c in components
        if c.footprint is not None
        and c.effective_in_pos_files
        and not c.footprint.dnp
    }


# ---------------------------------------------------------------------------
# Live oracle
# ---------------------------------------------------------------------------


VARIANTS = [None, "Variant 1", "Variant2"]


class TestLiveKicadCliPosOracle:
    """Run kicad-cli pos export for each variant; verify our filter matches."""

    @pytest.mark.parametrize("variant_name", VARIANTS)
    def test_pos_ref_set_matches_live_kicad_cli(
        self, variant_name: str | None, kicad_cli: Path, tmp_path: Path,
    ) -> None:
        live_csv = _run_kicad_cli_pos(
            kicad_cli, _variants_pcb(), tmp_path, variant_name
        )
        live = set(_read_pos_csv(live_csv))

        sch = KiCadSchematic.from_file(_variants_sch())
        pcb = KiCadPcb.from_file(_variants_pcb())
        ours = _pos_eligible_refs(assemble(sch, pcb, variant_name))

        only_ours = sorted(ours - live)
        only_live = sorted(live - ours)
        assert not only_ours and not only_live, (
            f"variant={variant_name!r}: pos ref-set mismatch vs kicad-cli\n"
            f"  only in ours ({len(only_ours)}): {only_ours}\n"
            f"  only in live ({len(only_live)}): {only_live}"
        )

    @pytest.mark.parametrize("variant_name", VARIANTS)
    def test_pos_value_matches_live_kicad_cli(
        self, variant_name: str | None, kicad_cli: Path, tmp_path: Path,
    ) -> None:
        """For every ref kicad-cli emits, our resolved Value (taken
        from the footprint side) matches the pos CSV's Val column."""
        live_csv = _run_kicad_cli_pos(
            kicad_cli, _variants_pcb(), tmp_path, variant_name
        )
        live = _read_pos_csv(live_csv)

        sch = KiCadSchematic.from_file(_variants_sch())
        pcb = KiCadPcb.from_file(_variants_pcb())
        ours = {c.reference: c for c in assemble(sch, pcb, variant_name)}

        diffs: list[str] = []
        for ref, row in live.items():
            comp = ours.get(ref)
            if comp is None or comp.footprint is None:
                continue
            our_value = comp.footprint.fields.get("Value", "")
            their_value = row.get("Val", "")
            if our_value != their_value:
                diffs.append(
                    f"{ref}: ours={our_value!r}  live={their_value!r}"
                )
        assert not diffs, (
            f"variant={variant_name!r}: {len(diffs)} value mismatches "
            f"vs kicad-cli pos:\n" + "\n".join(diffs[:30])
        )


# ---------------------------------------------------------------------------
# Structural invariant — exclude_from_pos_files is honored
# ---------------------------------------------------------------------------


class TestPosFilterInvariant:
    def test_attr_exclude_from_pos_files_is_filtered(self) -> None:
        """Footprints with the PCB-side ``(attr exclude_from_pos_files)``
        flag must have ``effective_in_pos_files=False`` regardless of
        variant. Locks the base filter that backs kicad-cli pos."""
        sch = KiCadSchematic.from_file(_variants_sch())
        pcb = KiCadPcb.from_file(_variants_pcb())
        comps = assemble(sch, pcb, None)
        excluded_fps = {
            fp_ref for fp_ref, fp in (
                (c.reference, c.footprint) for c in comps
                if c.footprint is not None
            )
            if fp.exclude_from_pos_files
        }
        # Fixture sanity: the eeschema/variants PCB has 7 such footprints.
        assert len(excluded_fps) >= 1, (
            "fixture sanity: at least one fp should have "
            "exclude_from_pos_files set"
        )
        for ref in excluded_fps:
            comp = next(c for c in comps if c.reference == ref)
            assert comp.effective_in_pos_files is False, (
                f"{ref} has exclude_from_pos_files but assemble() "
                f"reported effective_in_pos_files=True"
            )

    def test_virtual_refs_excluded_from_pos(self) -> None:
        """``#``-prefixed refs are filtered defensively even if a
        footprint exists for them — power refs should never reach pos."""
        sch = KiCadSchematic.from_file(_variants_sch())
        pcb = KiCadPcb.from_file(_variants_pcb())
        comps = assemble(sch, pcb, None)
        for c in comps:
            if c.reference.startswith("#"):
                assert c.effective_in_pos_files is False
