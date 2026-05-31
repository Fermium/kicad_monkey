"""
Test L2_006: Project mutation kicad-cli oracle

Phase C Slice C-7. End-to-end gate: mutate a ``.kicad_pro``
(add a variant), save it next to its sibling ``.kicad_sch``, then run
``kicad-cli sch export bom --variant <new>`` and verify the cli
accepts the file and produces a non-empty BOM.

Skipped if no kicad-cli is resolvable.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kicad_monkey import KiCadProject
from kicad_monkey.testing.corpus import get_kicad_upstream_qa_dir


_RESEARCH = (
    Path(__file__).resolve().parents[5]
    / "toolz" / "kicad_monkey" / "docs" / "research"
)
if str(_RESEARCH) not in sys.path:
    sys.path.insert(0, str(_RESEARCH))

try:
    from oracle_diff import _resolve_cli  # type: ignore
except Exception as exc:  # pragma: no cover
    _resolve_cli = None  # type: ignore
    _IMPORT_ERR = exc
else:
    _IMPORT_ERR = None


@pytest.fixture(scope="module")
def kicad_cli() -> Path:
    if _resolve_cli is None:
        pytest.skip(f"oracle_diff harness not importable: {_IMPORT_ERR!r}")
    cli = _resolve_cli(None)
    if cli is None or not Path(cli).exists():
        pytest.skip(
            "no kicad-cli resolvable on this machine; "
            "see toolz-tests/tools/kicad-cli/README.md"
        )
    return Path(cli)


def _stage_variants_project(dst: Path) -> Path:
    """Copy the cli/variants project + its sibling .kicad_sch into *dst*.
    Returns the staged .kicad_sch path."""
    src_dir = get_kicad_upstream_qa_dir() / "cli" / "variants"
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("variants.kicad_pro", "variants.kicad_sch"):
        shutil.copyfile(src_dir / name, dst / name)
    return dst / "variants.kicad_sch"


def test_added_variant_accepted_by_kicad_cli(
    kicad_cli: Path, tmp_path: Path,
) -> None:
    """Add a new variant to the project, save, then verify
    ``kicad-cli sch export bom --variant <new>`` succeeds."""
    sch = _stage_variants_project(tmp_path)
    project = KiCadProject.from_file(tmp_path / "variants.kicad_pro")
    project.add_variant("Mutation_C7", description="C-7 oracle test")
    project.save()  # uses project_path = staged .kicad_pro

    out_csv = tmp_path / "out.csv"
    cmd = [
        str(kicad_cli), "sch", "export", "bom",
        "--variant", "Mutation_C7",
        "--exclude-dnp",
        "--fields", "Reference,Value",
        "--labels", "Refs,Value",
        "-o", str(out_csv),
        str(sch),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    output = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, (
        "kicad-cli rejected mutated project:\n"
        f"  cmd: {cmd}\n"
        f"  output: {output[:800]}"
    )
    assert out_csv.exists() and out_csv.stat().st_size > 0, (
        "kicad-cli succeeded but produced no BOM output"
    )
    text = out_csv.read_text(encoding="utf-8")
    # Sanity: header + at least one data row.
    assert text.count("\n") >= 2, f"BOM unexpectedly short: {text!r}"


def test_renamed_variant_then_export_succeeds(
    kicad_cli: Path, tmp_path: Path,
) -> None:
    """Rename an existing variant in the project, save, then export
    the BOM under the new name. Validates that the .kicad_pro write
    path doesn't corrupt the schema."""
    sch = _stage_variants_project(tmp_path)
    project = KiCadProject.from_file(tmp_path / "variants.kicad_pro")
    # Pick the first existing variant and rename it.
    existing = project.variants[0].name
    new_name = "RenamedByC7"
    assert project.rename_variant(existing, new_name)
    project.save()

    out_csv = tmp_path / "renamed.csv"
    cmd = [
        str(kicad_cli), "sch", "export", "bom",
        "--variant", new_name,
        "--exclude-dnp",
        "--fields", "Reference,Value",
        "--labels", "Refs,Value",
        "-o", str(out_csv),
        str(sch),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"kicad-cli rejected renamed-variant project: {proc.stderr[:400]}"
    )
    assert out_csv.exists() and out_csv.stat().st_size > 0
