"""Subtest: PCB IR SVG oracle.

Stratum: L3_rendering
Purpose: Verify that ``render_pcb_ir_to_svg`` reaches viewBox + gross
element-count parity with the canonical ``kicad-cli pcb export svg`` on
the existing synthetic oracle fixtures.

Comparison:

* IR     — ``render_pcb_ir_to_svg(pcb, layers=...)``
* CLI    — ``kicad-cli pcb export svg --layers ...``

Asserted today (Phases B + B.2(a) + B.2(b) complete):

* viewBox: IR ≈ CLI within ``viewbox_tol_mm`` (≤ 0.1 mm).
* gross counts: ``total_strokes`` (``<path> + <polyline> + <line> +
  <rect> + <polygon>``) and ``total_circles`` match between IR and
  CLI. ``total_strokes`` is used instead of ``total_paths`` because
  the IR renderer prefers ``<polyline>`` / ``<rect>`` while kicad-cli
  prefers ``<path>`` — same geometry, different SVG element.
  Background canvas ``<rect>`` is excluded from the count.
* style-keyed counts: ``white_drill_circles``,
  ``white_stroke_paths``, ``stroke_paths_0p1000``,
  ``stroke_paths_1p0000``. Enabled by Phase B.2(b)'s
  ``_wrap_with_style_bucket`` in ``kicad_ir_to_svg.py``, which wraps
  every rendered op fragment in a ``<g style="...">`` mirroring its
  element-local fill / stroke / stroke-width — same structural
  pattern kicad-cli uses for its style buckets. The oracle helpers
  (``_count_white_stroke_paths``, ``_count_paths_for_stroke_width``)
  count ``<path|polyline|line>`` for renderer-agnostic comparison.

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


# Metrics we hold the IR renderer accountable for. Phase B.2(b) closed
# the style-bucket gap (the IR renderer now wraps every rendered op in a
# ``<g style="...">`` mirroring its element-local fill / stroke /
# stroke-width), so the style-keyed CLI metrics are enforced alongside
# the renderer-agnostic stroke / circle counts.
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
# kicad-cli (see module docstring for context). All phase C dimension
# shape-geometry gaps closed 2026-05-17:
# - ``dim_radial`` — knee→text segment removed.
# - ``dim_orthogonal_horizontal`` — 0.1 mm marker dot at second reference.
# - ``dim_aligned_horizontal`` / ``dim_orthogonal_vertical`` — stroke-font
#   dimension value text emitted per-segment.
# - ``dim_leader_plain`` / ``dim_leader_frame_rect`` — leader value text
#   driven by ``format.override_value`` (CLI parity); frame_rect=1 emits
#   four rectangle sides around the text bounding box.
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
