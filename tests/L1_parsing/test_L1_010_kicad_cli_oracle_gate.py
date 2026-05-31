"""
Subtest: kicad-cli oracle gate
Stratum: L1_parsing
Purpose: Per-root-cause regression gate — for a curated set of minimal
reproducers, parse with kicad_monkey, emit, and assert that
``kicad-cli * upgrade --force`` accepts the result.

Each root cause from
``toolz/kicad_monkey/docs/research/2026-05-08-drift-inventory.md`` has at
least one fixture here. Cases that are known-broken pre-fix are marked
``xfail(strict=True)`` so they flip to **XPASS** (a hard failure) the
moment the fix lands — at which point the marker should be removed.

Skips entirely if no `kicad-cli` is resolvable on this machine.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kicad_monkey import KiCadSchematic, KiCadSymbolLib

try:
    from kicad_monkey.kicad_pcb import KiCadPcb
    HAVE_PCB = True
except Exception:
    HAVE_PCB = False


# ---------------------------------------------------------------------------
# Resolve kicad-cli (re-uses the harness logic in oracle_diff)
# ---------------------------------------------------------------------------

_RESEARCH = Path(__file__).resolve().parents[5] / "toolz" / "kicad_monkey" / "docs" / "research"
if str(_RESEARCH) not in sys.path:
    sys.path.insert(0, str(_RESEARCH))

try:
    from oracle_diff import _resolve_cli, _stage_file_with_siblings, CLI_VERB  # type: ignore
except Exception as exc:  # pragma: no cover - import-time only
    _resolve_cli = None  # type: ignore
    _stage_file_with_siblings = None  # type: ignore
    CLI_VERB = {}  # type: ignore
    _IMPORT_ERR = exc
else:
    _IMPORT_ERR = None


# ---------------------------------------------------------------------------
# Corpus root resolution (same dual-path convention as oracle_diff)
# ---------------------------------------------------------------------------

_ONEDRIVE_CORPUS = Path(
    r"C:\Users\EliHughes\OneDrive - Wavenumber LLC\wn_test_corpus"
)


def _find_fixture(rel: str) -> Path | None:
    """Look up a fixture under either ``$WN_TEST_CORPUS`` or the OneDrive corpus."""
    candidates: list[Path] = []
    env = os.environ.get("WN_TEST_CORPUS")
    if env:
        candidates.append(Path(env) / rel)
    candidates.append(_ONEDRIVE_CORPUS / rel)
    for p in candidates:
        if p.is_file():
            return p
    return None


# ---------------------------------------------------------------------------
# Curated minimal-reproducer cases
# ---------------------------------------------------------------------------

# Each tuple: (case_id, corpus-relative path, list[root_cause_ids], xfail_reason or None)
CASES = [
    # Guardrail — currently passes, must keep passing.
    (
        "guardrail_groups_load_save",
        r"kicad/upstream_qa/eeschema/groups_load_save/groups_load_save.kicad_sch",
        [],
        None,
    ),
    (
        "rc1_at_3tuple_sch",
        r"kicad/common/reference_schematics/input/flat_hierarchy.kicad_sch",
        ["#1"],
        # #1 fixed; #2 (empty lib_symbols dropped) and #3 (per-sheet instances)
        # are pure data-loss, not parser-fatal — they no longer block this gate.
        None,
    ),
    (
        "rc1_at_3tuple_sym",
        r"kicad/common/reference_symbols/input/C_2P_NP.kicad_sym",
        ["#1"],
        # #1 fixed; #7 (sym bulk content) was a misread of the unloadable
        # diff_sample. With #1 fixed kicad-cli loads our emit cleanly.
        None,
    ),
    (
        # Original inventory hypothesis (#4/#5/#6 — tenting / version /
        # plot-params) was wrong. Real cause: zone `(layers "*.Cu")` plural
        # form was being parsed as singular `(layer "")`, and kicad-cli
        # SEGFAULTed (rc 0xC0000005) on round-trip. Fixed via Zone.layers
        # plural-form support and FilledPolygon (island) sub-list emit.
        "rc9_zone_layers_plural",
        r"kicad/upstream_qa/pcbnew/plugins/kicad_sexpr/Issue19775_ZoneLayers/LayerWildcard.kicad_pcb",
        ["#9"],
        None,
    ),
    (
        # Root cause #8 (erratum to original inventory): KiCad uses
        # (id <bare-uuid>) NOT (uuid ...) for the first child of (generated),
        # and the parser SEGFAULTs (rc 0xC0000005) — not just rejects — when
        # the order is wrong or members are quoted. Fixed via GeneratedObject
        # parse/emit corrections.
        "rc8_generated_id_first",
        r"kicad/upstream_qa/pcbnew/tuning_generators_load_save/tuning_generators_load_save.kicad_pcb",
        ["#8"],
        None,
    ),
]


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kicad_cli() -> Path:
    if _resolve_cli is None:
        pytest.skip(f"oracle_diff harness not importable: {_IMPORT_ERR!r}")
    cli = _resolve_cli(None)
    if cli is None or not Path(cli).exists():
        pytest.skip("no kicad-cli resolvable on this machine; see toolz-tests/tools/kicad-cli/README.md")
    return Path(cli)


def _our_emit(path: Path) -> str:
    suffix = path.suffix
    if suffix == ".kicad_sch":
        return KiCadSchematic.from_file(path).to_text()
    if suffix == ".kicad_sym":
        return KiCadSymbolLib.from_file(path).to_text()
    if suffix == ".kicad_pcb":
        if not HAVE_PCB:
            pytest.skip("kicad_monkey.kicad_pcb not importable on this branch")
        pcb = KiCadPcb.from_file(path)
        if hasattr(pcb, "to_text"):
            return pcb.to_text()
        from kicad_monkey import build_sexp  # type: ignore
        return build_sexp(pcb.to_sexp())
    raise ValueError(f"Unsupported file kind: {suffix}")


# Build the parametrize list with conditional xfail markers.
def _params():
    out = []
    for case_id, rel, causes, xfail_reason in CASES:
        marks = []
        if xfail_reason:
            marks.append(pytest.mark.xfail(strict=True, reason=xfail_reason))
        out.append(pytest.param(case_id, rel, causes, id=case_id, marks=marks))
    return out


@pytest.mark.parametrize("case_id, rel, causes", _params())
def test_kicad_cli_accepts_emitted(
    case_id: str,
    rel: str,
    causes: list[str],
    kicad_cli: Path,
    tmp_path: Path,
) -> None:
    """Parse the fixture with kicad_monkey, emit it, and verify
    ``kicad-cli * upgrade --force`` returns 0."""
    src = _find_fixture(rel)
    if src is None:
        pytest.skip(f"fixture {rel!r} not found in $WN_TEST_CORPUS or OneDrive corpus")

    # Stage the source's parent directory (siblings — `.kicad_pro`, `sym-lib-table`, etc.).
    stage = tmp_path / "ours"
    target = _stage_file_with_siblings(src, stage)
    target.write_text(_our_emit(src), encoding="utf-8")

    suffix = src.suffix
    sub, verb = CLI_VERB[suffix]
    proc = subprocess.run(
        [str(kicad_cli), sub, verb, "--force", str(target)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"kicad-cli rejected emitted {case_id} ({src.name}) — root causes: {causes!r}\n"
        f"--- stdout/stderr (first 800 chars) ---\n{output[:800]}"
    )
