"""
Test L2_008: Variant write API kicad-cli oracle

Phase E Slice E-2 — end-to-end validation that overrides written via
``SchSymbol.set_variant_override`` and ``Footprint.set_variant_override``
are honored by KiCad's own ``kicad-cli`` exporters.

Strategy:

1. Load ``eeschema/variants/`` schematic.
2. Mutate a real symbol to add a fresh variant override (DNP under the
   new variant), under the existing "Variant 1" name so kicad-cli can
   resolve it from the schematic's variant catalog.
3. Save to a temp working copy (preserving the sub-sheet).
4. Run ``kicad-cli sch export bom --variant "Variant 1" --exclude-dnp``
   and confirm the mutated ref is **excluded** from the BOM (proving
   our DNP write was picked up by kicad-cli's resolver).
5. Sanity check: under the default variant the same ref is still in the
   BOM (proving the override is variant-scoped, not global).

Skipped if no kicad-cli is resolvable on this machine.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
from pathlib import Path

import pytest

from kicad_cli_resolver import resolve_kicad_cli
from kicad_monkey import KiCadSchematic, assemble
from kicad_monkey.testing.corpus import get_kicad_upstream_qa_dir


# ---------------------------------------------------------------------------
# CLI resolution
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kicad_cli() -> Path:
    cli = resolve_kicad_cli()
    if cli is None or not Path(cli).exists():
        pytest.skip("no kicad-cli resolvable on this machine")
    return Path(cli)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_bom_refs(csv_path: Path) -> set[str]:
    out: set[str] = set()
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cell = row.get("Refs") or row.get("Reference") or ""
            for ref in cell.split(","):
                ref = ref.strip()
                if ref:
                    out.add(ref)
    return out


def _stage_variants_dir(tmp_path: Path) -> Path:
    """Copy the variants directory to a temp working dir so we can write
    a mutated schematic without touching the corpus."""
    src = get_kicad_upstream_qa_dir() / "eeschema" / "variants"
    dst = tmp_path / "variants"
    shutil.copytree(src, dst)
    return dst


def _run_bom(
    cli: Path, sch_path: Path, out_dir: Path, variant: str | None,
) -> Path:
    out_path = out_dir / f"out_{variant or 'default'}.bom.csv"
    cmd = [str(cli), "sch", "export", "bom"]
    if variant:
        cmd.extend(["--variant", variant])
    cmd.extend([
        "--exclude-dnp",
        "--fields", "Reference,Value",
        "--labels", "Refs,Value",
        "-o", str(out_path),
        str(sch_path),
    ])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(
            f"kicad-cli failed (rc={proc.returncode}):\n"
            f"  cmd: {cmd}\n"
            f"  stdout: {proc.stdout[:400]}\n"
            f"  stderr: {proc.stderr[:400]}"
        )
    return out_path


# ---------------------------------------------------------------------------
# End-to-end oracle
# ---------------------------------------------------------------------------


class TestVariantWriteEndToEnd:
    def test_added_dnp_override_excludes_ref_from_kicad_cli_bom(
        self, kicad_cli: Path, tmp_path: Path,
    ) -> None:
        """Add a DNP override under 'Variant 1' to a ref currently in
        that variant's BOM, save, then run kicad-cli BOM export. The ref
        must drop from the variant BOM but remain in the default BOM.
        """
        staged = _stage_variants_dir(tmp_path)
        sch_path = staged / "variants.kicad_sch"

        # Pre-mutation baseline: which refs are in the variant BOM today?
        baseline_csv = _run_bom(kicad_cli, sch_path, tmp_path, "Variant 1")
        baseline = _read_bom_refs(baseline_csv)
        default_csv = _run_bom(kicad_cli, sch_path, tmp_path, None)
        default = _read_bom_refs(default_csv)

        # Pick any ref present in both baselines so we observe a clean drop.
        target_ref = next(iter(sorted(baseline & default)))

        # Mutate: add (or update) a (variant ...) block under Variant 1
        # on the matching symbol's instance, marking dnp=yes.
        sch = KiCadSchematic.from_file(sch_path)
        # Symbols may have multiple instances (hierarchy); we update the
        # one whose .reference matches. The walker exposes instances per
        # symbol; we filter at the symbol level by .reference.
        matched = [
            (sym, inst)
            for sym in sch.symbols
            for inst in sym.instances
            if inst.reference == target_ref
        ]
        if not matched:
            # Hierarchical sub-sheet symbol — fall through to walker.
            for sub_sym, _ in sch.walk_symbols():
                for inst in sub_sym.instances:
                    if inst.reference == target_ref:
                        matched.append((sub_sym, inst))
        assert matched, (
            f"could not find symbol instance for ref={target_ref!r} "
            f"in mutated schematic — fixture drift?"
        )
        # Just take the first match (typically there's only one).
        sym, inst = matched[0]
        sym.set_variant_override(
            "Variant 1",
            dnp=True,
            instance_path=inst.path,
            project=inst.project,
        )

        # Save back to the same path. This goes through our emitter.
        sch_path.write_text(sch.to_text(), encoding="utf-8")

        # Re-run kicad-cli for both variants on the mutated schematic.
        new_variant_csv = _run_bom(
            kicad_cli, sch_path, tmp_path, "Variant 1",
        )
        new_variant = _read_bom_refs(new_variant_csv)
        new_default_csv = _run_bom(kicad_cli, sch_path, tmp_path, None)
        new_default = _read_bom_refs(new_default_csv)

        # The ref must now be excluded from Variant 1's BOM (DNP took).
        assert target_ref not in new_variant, (
            f"after mutation, kicad-cli still emits {target_ref!r} for "
            f"Variant 1 — DNP override didn't propagate.\n"
            f"  baseline Variant 1 BOM size: {len(baseline)}\n"
            f"  post-mutation Variant 1 BOM size: {len(new_variant)}"
        )
        # The default BOM should still include it (override is scoped).
        assert target_ref in new_default, (
            f"after mutation, default-variant BOM lost {target_ref!r} — "
            f"the override should be variant-scoped."
        )

        # And our own assemble() agrees with kicad-cli on the mutated tree.
        sch_after = KiCadSchematic.from_file(sch_path)
        comps = assemble(sch_after, None, "Variant 1")
        comp = next((c for c in comps if c.reference == target_ref), None)
        assert comp is not None
        assert comp.effective_dnp is True, (
            f"assemble disagrees with kicad-cli on {target_ref!r}: "
            f"effective_dnp should be True under Variant 1"
        )
