"""Subtest: Synthetic Board SVG Oracle
Stratum: L3_rendering
Purpose: Focused semantic parity checks against kicad-cli for synthetic fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synthetic_board_svg_oracle import (
    SYNTHETIC_ORACLE_CASES,
    compare_semantic_metrics,
    export_svg_with_kicad_cli,
    find_kicad_cli,
    resolve_case_board_path,
    semantic_snapshot,
)


def _case_id(case) -> str:
    return case.case_id


@pytest.fixture(scope="module")
def kicad_cli_path() -> Path:
    cli = find_kicad_cli()
    if cli is None:
        pytest.skip("kicad-cli not found - skipping synthetic oracle checks")
    return cli


@pytest.mark.parametrize("case", SYNTHETIC_ORACLE_CASES, ids=_case_id)
def test_synthetic_case_matches_kicad_cli_semantics(case, kicad_cli_path, tmp_path):
    from kicad_monkey import KiCadPcb

    board_path = resolve_case_board_path(case)
    if not board_path.exists():
        pytest.skip(f"Missing synthetic board fixture: {board_path}")

    pcb = KiCadPcb.from_file(board_path)
    our_svg = pcb.to_svg(layers=list(case.layers))
    our_snapshot = semantic_snapshot(our_svg)

    for metric_name, minimum in case.minimums:
        assert int(our_snapshot[metric_name]) >= minimum, (
            f"{case.case_id}: our metric {metric_name} below expected minimum "
            f"({our_snapshot[metric_name]} < {minimum})"
        )

    cli_svg_path = tmp_path / f"{case.case_id}__cli.svg"
    export_svg_with_kicad_cli(
        kicad_cli=kicad_cli_path,
        board_path=board_path,
        layers=case.layers,
        output_path=cli_svg_path,
    )
    ref_snapshot = semantic_snapshot(cli_svg_path.read_text())

    for metric_name, minimum in case.minimums:
        assert int(ref_snapshot[metric_name]) >= minimum, (
            f"{case.case_id}: kicad-cli metric {metric_name} below expected minimum "
            f"({ref_snapshot[metric_name]} < {minimum})"
        )

    mismatches = compare_semantic_metrics(our_snapshot, ref_snapshot, case.metrics)
    assert not mismatches, (
        f"{case.case_id}: semantic mismatch for layers={','.join(case.layers)}:\n"
        + "\n".join(f"- {msg}" for msg in mismatches)
        + f"\nour={our_snapshot}\nref={ref_snapshot}"
    )
