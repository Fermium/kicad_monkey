"""
Test L2_005: Variant-aware BOM oracle (full-equality)

Phase C Slice C-6 / Phase D Slice D-3 — validates ``assemble()``
agrees with KiCad's own ``kicad-cli sch export bom`` on the canonical
variants fixture, with full-equality assertions now that hierarchical
loading (D-1) and the BOM filter parity work (D-2) are in place.

Two layers:

1. Static-golden layer. For each ``variants_*.bom.csv`` shipped with
   KiCad's CLI suite, walk our ``assemble(sch, None, variant)`` and
   compare:
   - The set of BOM-eligible refs (effective_in_bom and not
     effective_dnp) is **equal** to the golden's ref set.
   - For every shared ref the resolved Value matches the golden Value.

2. Live ``kicad-cli`` oracle layer. Same fixture, but compares our
   answer against a live ``kicad-cli sch export bom --variant <name>``
   invocation (the exact command upstream uses) — full set equality on
   refs and value equality on every ref. Skipped if no kicad-cli is
   resolvable on this machine.

Schematic source: ``eeschema/variants/variants.kicad_sch`` — this is
the directory that ships the ``pic_sockets.kicad_sch`` sub-sheet
alongside the parent. The schematic content is byte-identical to
``cli/variants/variants.kicad_sch`` (verified upstream); we use the
eeschema/variants path so D-1's hierarchical loader sees the sub-sheet.
The static goldens still live under ``cli/variants/``.
"""

from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path

import pytest

from kicad_cli_resolver import resolve_kicad_cli
from kicad_monkey import KiCadSchematic, assemble
from kicad_monkey.testing.corpus import get_kicad_upstream_qa_dir


# ---------------------------------------------------------------------------
# Fixture lookup
# ---------------------------------------------------------------------------


def _goldens_dir() -> Path:
    """Directory containing the static BOM goldens (.bom.csv)."""
    return get_kicad_upstream_qa_dir() / "cli" / "variants"


def _variants_sch() -> Path:
    """Schematic to feed into assemble(). The eeschema/variants copy is
    byte-identical to cli/variants/variants.kicad_sch but ships the
    pic_sockets.kicad_sch sub-sheet alongside, so D-1 hierarchical
    loading resolves correctly here."""
    return get_kicad_upstream_qa_dir() / "eeschema" / "variants" / "variants.kicad_sch"


def _read_bom_refs_with_value(csv_path: Path) -> dict[str, str]:
    """Return {ref: value} from a KiCad BOM CSV (one ref per row)."""
    out: dict[str, str] = {}
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return out
    # Headers: ['Refs', 'Value'] (or close — we tolerate either order).
    header = [h.strip() for h in rows[0]]
    try:
        ref_col = header.index("Refs")
        val_col = header.index("Value")
    except ValueError:
        # Some BOM exports use 'Reference' instead — accept it.
        ref_col = header.index("Reference") if "Reference" in header else 0
        val_col = header.index("Value") if "Value" in header else 1
    for row in rows[1:]:
        if len(row) <= max(ref_col, val_col):
            continue
        refs = [r.strip() for r in row[ref_col].split(",") if r.strip()]
        value = row[val_col]
        for ref in refs:
            out[ref] = value
    return out


# ---------------------------------------------------------------------------
# Static-golden oracle
# ---------------------------------------------------------------------------


VARIANT_CASES = [
    # (variant_name passed to assemble, golden file)
    (None, "variants_default.bom.csv"),
    ("Variant 1", "variants_v1.bom.csv"),
    ("Variant2", "variants_v2.bom.csv"),
]


def _bom_eligible_refs(components) -> set[str]:
    """Refs that ``assemble()`` would expose to KiCad's BOM emit:
    in_bom set, not DNP. (Power refs are already filtered inside
    ``effective_in_bom`` by D-2.)"""
    return {
        c.reference for c in components
        if c.effective_in_bom and not c.effective_dnp
    }


class TestStaticGoldenOracle:
    """Compare ``assemble(sch, None, variant)`` against the upstream
    BOM golden — full set equality on refs and full value equality."""

    @pytest.mark.parametrize("variant_name, golden_file", VARIANT_CASES)
    def test_variant_ref_set_matches_golden(
        self, variant_name: str | None, golden_file: str,
    ) -> None:
        """Our BOM-eligible refs must equal the golden's ref set under
        every variant — no missing refs, no extras."""
        sch = KiCadSchematic.from_file(_variants_sch())
        ours = _bom_eligible_refs(assemble(sch, None, variant_name))
        golden = set(_read_bom_refs_with_value(_goldens_dir() / golden_file))

        only_ours = sorted(ours - golden)
        only_golden = sorted(golden - ours)
        assert not only_ours and not only_golden, (
            f"variant={variant_name!r}: ref-set mismatch vs {golden_file}\n"
            f"  only in ours    ({len(only_ours)}): {only_ours}\n"
            f"  only in golden  ({len(only_golden)}): {only_golden}"
        )

    @pytest.mark.parametrize("variant_name, golden_file", VARIANT_CASES)
    def test_variant_value_matches_golden(
        self, variant_name: str | None, golden_file: str,
    ) -> None:
        """For every ref both sides emit, our resolved Value must match
        the golden's Value byte-for-byte."""
        sch = KiCadSchematic.from_file(_variants_sch())
        ours = {
            c.reference: c for c in assemble(sch, None, variant_name)
            if c.effective_in_bom and not c.effective_dnp
        }
        golden = _read_bom_refs_with_value(_goldens_dir() / golden_file)

        diffs: list[str] = []
        for ref, their_value in golden.items():
            row = ours.get(ref)
            if row is None or row.symbol is None:
                continue
            if row.symbol.value != their_value:
                diffs.append(
                    f"{ref}: ours={row.symbol.value!r}  golden={their_value!r}"
                )
        assert not diffs, (
            f"variant={variant_name!r}: {len(diffs)} value mismatches "
            f"vs {golden_file}:\n" + "\n".join(diffs[:30])
        )


# ---------------------------------------------------------------------------
# Live kicad-cli oracle (broader, gated)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kicad_cli() -> Path:
    cli = resolve_kicad_cli()
    if cli is None or not Path(cli).exists():
        pytest.skip("no kicad-cli resolvable on this machine")
    return Path(cli)


def _run_kicad_cli_bom(
    cli: Path, sch_path: Path, out_dir: Path, variant: str | None,
) -> Path:
    out_path = out_dir / f"variants_{variant or 'default'}.bom.csv"
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


class TestLiveKicadCliOracle:
    """Run kicad-cli for each variant, then verify our resolver matches
    its output exactly — full ref-set equality and full value equality."""

    @pytest.mark.parametrize("variant_name", [None, "Variant 1", "Variant2"])
    def test_assemble_ref_set_matches_live_kicad_cli(
        self,
        variant_name: str | None,
        kicad_cli: Path,
        tmp_path: Path,
    ) -> None:
        sch_path = _variants_sch()
        live_csv = _run_kicad_cli_bom(kicad_cli, sch_path, tmp_path, variant_name)
        live = set(_read_bom_refs_with_value(live_csv))

        sch = KiCadSchematic.from_file(sch_path)
        ours = _bom_eligible_refs(assemble(sch, None, variant_name))

        only_ours = sorted(ours - live)
        only_live = sorted(live - ours)
        assert not only_ours and not only_live, (
            f"variant={variant_name!r}: ref-set mismatch vs kicad-cli\n"
            f"  only in ours ({len(only_ours)}): {only_ours}\n"
            f"  only in live ({len(only_live)}): {only_live}"
        )

    @pytest.mark.parametrize("variant_name", [None, "Variant 1", "Variant2"])
    def test_assemble_value_matches_live_kicad_cli(
        self,
        variant_name: str | None,
        kicad_cli: Path,
        tmp_path: Path,
    ) -> None:
        sch_path = _variants_sch()
        live_csv = _run_kicad_cli_bom(kicad_cli, sch_path, tmp_path, variant_name)
        live = _read_bom_refs_with_value(live_csv)

        sch = KiCadSchematic.from_file(sch_path)
        ours = {
            c.reference: c for c in assemble(sch, None, variant_name)
            if c.effective_in_bom and not c.effective_dnp
        }

        diffs: list[str] = []
        for ref, their_value in live.items():
            row = ours.get(ref)
            if row is None or row.symbol is None:
                continue
            if row.symbol.value != their_value:
                diffs.append(
                    f"{ref}: ours={row.symbol.value!r}  live={their_value!r}"
                )
        assert not diffs, (
            f"variant={variant_name!r}: {len(diffs)} value mismatches "
            f"vs kicad-cli:\n" + "\n".join(diffs[:30])
        )
