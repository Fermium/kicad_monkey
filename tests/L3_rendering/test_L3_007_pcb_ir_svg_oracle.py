"""Subtest: PCB IR SVG oracle.

Stratum: L3_rendering
Purpose: Verify that ``render_pcb_ir_to_svg`` reaches viewBox and gross
element-count parity with the canonical ``kicad-cli pcb export svg`` on the
existing synthetic oracle fixtures.

Comparison:

* IR: ``render_pcb_ir_to_svg(pcb, layers=...)``
* CLI: ``kicad-cli pcb export svg --layers ...``

Asserted today:

* viewBox: IR approximately matches CLI within ``viewbox_tol_mm``.
* gross counts: ``total_strokes`` and ``total_circles`` match between IR and
  CLI. ``total_strokes`` is renderer-agnostic, so KiCad ``<path>`` output and
  monkey ``<polyline>`` / ``<polygon>`` output can still compare when the
  painted geometry is equivalent.
* style-keyed counts: ``white_drill_circles``, ``white_stroke_paths``,
  ``stroke_paths_0p1000``, and ``stroke_paths_1p0000``. These metrics are
  extracted by the shared canonical SVG analyzer, which applies inherited group
  styles and element overrides before counting draw items.

Note: this oracle compares against ``kicad-cli`` as the source of truth.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synthetic_board_svg_oracle import (
    IR_ONLY_ORACLE_CASES,
    SYNTHETIC_ORACLE_CASES,
    compare_semantic_metrics,
    export_svg_with_kicad_cli,
    find_kicad_cli,
    resolve_case_board_path,
    semantic_snapshot,
)


# The L3_007 sweep covers the shared synthetic oracle list plus
# IR-only ratchet cases (currently the via-mask synthesis on
# case082's untented vias).
ALL_IR_ORACLE_CASES = SYNTHETIC_ORACLE_CASES + IR_ONLY_ORACLE_CASES


# Metrics we hold the IR renderer accountable for. The shared canonical SVG
# analyzer flattens inherited styles, so style-keyed CLI metrics are enforced
# alongside renderer-agnostic stroke / circle counts.
IR_ENFORCED_METRICS: tuple[str, ...] = (
    "viewbox",
    "total_strokes",
    "total_circles",
    "white_drill_circles",
    "white_stroke_paths",
    "stroke_paths_0p1000",
    "stroke_paths_1p0000",
)


# Cases where the IR renderer does not yet emit the same geometry as
# kicad-cli. The previous phase C dimension shape-geometry gaps closed on
# 2026-05-17; keep this map empty until a new intentional gap is documented.
IR_KNOWN_GAPS: dict[str, str] = {}


def _case_id(case) -> str:
    return case.case_id


@pytest.fixture(scope="module")
def kicad_cli_path() -> Path:
    cli = find_kicad_cli()
    if cli is None:
        pytest.skip("kicad-cli not found - skipping IR oracle checks")
    return cli


@pytest.mark.parametrize("case", ALL_IR_ORACLE_CASES, ids=_case_id)
def test_ir_svg_matches_kicad_cli_on_synthetic_cases(case, kicad_cli_path, tmp_path):
    from kicad_monkey import KiCadPcb, render_pcb_ir_to_svg

    if case.case_id in IR_KNOWN_GAPS:
        pytest.xfail(IR_KNOWN_GAPS[case.case_id])

    board_path = resolve_case_board_path(case)
    if not board_path.exists():
        pytest.skip(f"Missing synthetic board fixture: {board_path}")

    pcb = KiCadPcb.from_file(board_path)

    ir_svg = render_pcb_ir_to_svg(pcb, layers=list(case.layers))
    ir_snapshot = semantic_snapshot(ir_svg)

    cli_svg_path = tmp_path / f"{case.case_id}__cli.svg"
    export_svg_with_kicad_cli(
        kicad_cli=kicad_cli_path,
        board_path=board_path,
        layers=case.layers,
        output_path=cli_svg_path,
    )
    cli_snapshot = semantic_snapshot(cli_svg_path.read_text())

    # IR vs CLI on the enforced metrics.
    ir_vs_cli = compare_semantic_metrics(
        ir_snapshot, cli_snapshot, IR_ENFORCED_METRICS
    )
    assert not ir_vs_cli, (
        f"{case.case_id}: IR-vs-CLI mismatch for layers={','.join(case.layers)}:\n"
        + "\n".join(f"- {msg}" for msg in ir_vs_cli)
        + f"\nIR={ir_snapshot}\nCLI={cli_snapshot}"
    )
