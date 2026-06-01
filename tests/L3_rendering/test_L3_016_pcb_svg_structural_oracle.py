"""Strict PCB SVG structural oracle checks.

This lane compares canonical draw items against fresh ``kicad-cli`` output.
It is intentionally narrower than the semantic oracle: cases enter here only
when the emitter choices are expected to match, so kind sequence, effective
style, bbox, and radii all become enforced contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from svg.canonical_svg import (
    SvgDrawItem,
    analyze_svg,
    effective_style_signature,
)
from synthetic_board_svg_oracle import (
    export_svg_with_kicad_cli,
    find_kicad_cli,
    resolve_case_board_path,
)


@dataclass(frozen=True)
class StrictSvgCase:
    case_id: str
    board_relpath: str
    layers: tuple[str, ...]
    kind_sequence: tuple[str, ...]


STRICT_CASES: tuple[StrictSvgCase, ...] = (
    StrictSvgCase(
        case_id="via_basic_f_cu",
        board_relpath="case019__via_basic/one_via.kicad_pcb",
        layers=("F.Cu",),
        kind_sequence=("circle", "circle"),
    ),
    StrictSvgCase(
        case_id="via_basic_edgecuts",
        board_relpath="case019__via_basic/one_via.kicad_pcb",
        layers=("Edge.Cuts",),
        kind_sequence=("path",),
    ),
    StrictSvgCase(
        case_id="pad_chamfered_roundrect_f_cu",
        board_relpath="case083__pad_chamfered_roundrect/one_chamfer_roundrect.kicad_pcb",
        layers=("F.Cu",),
        kind_sequence=("path",),
    ),
    StrictSvgCase(
        case_id="pad_smd_oval_f_cu",
        board_relpath="case013__pad_smd_oval/case013__pad_smd_oval.kicad_pcb",
        layers=("F.Cu",),
        kind_sequence=("path",),
    ),
    StrictSvgCase(
        case_id="pad_th_oval_f_cu",
        board_relpath="case018__pad_th_oval/case018__pad_th_oval.kicad_pcb",
        layers=("F.Cu",),
        kind_sequence=("path", "circle"),
    ),
    StrictSvgCase(
        case_id="slot_copper_drill_f_cu",
        board_relpath="case084__pad_slot_hole/one_slot_drill.kicad_pcb",
        layers=("F.Cu",),
        kind_sequence=("path", "path"),
    ),
    StrictSvgCase(
        case_id="slot_edgecuts_drill_outline",
        board_relpath="case084__pad_slot_hole/one_slot_drill.kicad_pcb",
        layers=("Edge.Cuts",),
        kind_sequence=("path", "path"),
    ),
    StrictSvgCase(
        case_id="zone_fill_f_cu",
        board_relpath="case024__fill_top_zone/one_zone_filled_top.kicad_pcb",
        layers=("F.Cu",),
        kind_sequence=("path",),
    ),
)


def _case_id(case: StrictSvgCase) -> str:
    return case.case_id


@pytest.fixture(scope="module")
def kicad_cli_path() -> Path:
    cli = find_kicad_cli()
    if cli is None:
        pytest.skip("kicad-cli not found - skipping strict PCB SVG oracle checks")
    return cli


def _is_background(item: SvgDrawItem) -> bool:
    return (
        item.kind == "rect"
        and item.bbox is not None
        and item.bbox[0] == 0.0
        and item.bbox[1] == 0.0
        and str(item.style.get("fill", "")).upper() == "#FFFFFF"
    )


def _draw_items(svg: str) -> list[SvgDrawItem]:
    return [
        item for item in analyze_svg(svg).draw_items
        if not _is_background(item)
    ]


def _assert_close_tuple(
    ours: tuple[float, ...],
    reference: tuple[float, ...],
    *,
    tol: float,
) -> None:
    deltas = [abs(a - b) for a, b in zip(ours, reference)]
    assert all(delta <= tol for delta in deltas), (
        f"tuple mismatch ours={ours} reference={reference} deltas={deltas}"
    )


@pytest.mark.parametrize("case", STRICT_CASES, ids=_case_id)
def test_pcb_svg_strict_draw_items_match_kicad_cli(case, kicad_cli_path, tmp_path):
    from kicad_monkey import KiCadPcb, render_pcb_ir_to_svg

    board_path = resolve_case_board_path(case)
    if not board_path.exists():
        pytest.skip(f"Missing synthetic board fixture: {board_path}")

    pcb = KiCadPcb.from_file(board_path)
    ours_svg = render_pcb_ir_to_svg(
        pcb,
        layers=list(case.layers),
        profile="kicad_cli",
    )
    cli_svg_path = tmp_path / f"{case.case_id}__cli.svg"
    export_svg_with_kicad_cli(
        kicad_cli=kicad_cli_path,
        board_path=board_path,
        layers=case.layers,
        output_path=cli_svg_path,
    )

    ours_items = _draw_items(ours_svg)
    cli_items = _draw_items(cli_svg_path.read_text())

    assert tuple(item.kind for item in cli_items) == case.kind_sequence
    assert tuple(item.kind for item in ours_items) == case.kind_sequence
    assert len(ours_items) == len(cli_items)

    for index, (ours, reference) in enumerate(zip(ours_items, cli_items)):
        assert effective_style_signature(ours) == effective_style_signature(reference), (
            f"style mismatch at draw item {index}: "
            f"ours={effective_style_signature(ours)} "
            f"reference={effective_style_signature(reference)}"
        )
        assert ours.bbox is not None and reference.bbox is not None
        _assert_close_tuple(ours.bbox, reference.bbox, tol=0.001)
        if ours.radius is not None or reference.radius is not None:
            assert ours.radius is not None and reference.radius is not None
            assert abs(ours.radius - reference.radius) <= 0.0001
