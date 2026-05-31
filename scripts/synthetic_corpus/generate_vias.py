"""Via cases (case020–case022).

Phase 2 gap-fill. Existing slot: ``case019__via_basic`` (single 0.6/0.3
through via at the case origin).

New cases generated here:

* ``case020__via_small`` — small via (size 0.45 mm, drill 0.2 mm).
* ``case021__via_large`` — large via (size 1.2 mm, drill 0.5 mm).
* ``case022__via_multiple`` — five vias in a row at varying sizes.

All vias are F.Cu↔B.Cu through-vias on a two-copper-layer board to
isolate drill / annular-ring rendering from blind/buried/micro tests
(those land in case086+ during Phase 6).
"""

from __future__ import annotations

from kicad_monkey.kicad_pcb import KiCadPcb
from kicad_monkey.kicad_pcb_other import Net, NetRef
from kicad_monkey.kicad_pcb_routing import Via

from .common import CaseSpec, build_minimal_pcb, uid_for


def _make_via(
    spec: CaseSpec,
    *,
    index: int,
    x: float,
    y: float,
    size: float,
    drill: float,
) -> Via:
    return Via(
        at_x=x,
        at_y=y,
        size=size,
        drill=drill,
        layers=["F.Cu", "B.Cu"],
        net=NetRef(0),
        uuid=uid_for(spec.case_id, "via", index),
    )


def _build_via_small(spec: CaseSpec) -> KiCadPcb:
    pcb = build_minimal_pcb(
        case_id=spec.case_id,
        board_size=spec.board_size,
        origin=spec.origin,
        nets=[Net(0, "")],
    )
    ox, oy = spec.origin
    cx = ox + spec.board_size[0] / 2.0
    cy = oy + spec.board_size[1] / 2.0
    pcb.vias = [_make_via(spec, index=1, x=cx, y=cy, size=0.45, drill=0.2)]
    return pcb


def _build_via_large(spec: CaseSpec) -> KiCadPcb:
    pcb = build_minimal_pcb(
        case_id=spec.case_id,
        board_size=spec.board_size,
        origin=spec.origin,
        nets=[Net(0, "")],
    )
    ox, oy = spec.origin
    cx = ox + spec.board_size[0] / 2.0
    cy = oy + spec.board_size[1] / 2.0
    pcb.vias = [_make_via(spec, index=1, x=cx, y=cy, size=1.2, drill=0.5)]
    return pcb


def _build_via_multiple(spec: CaseSpec) -> KiCadPcb:
    pcb = build_minimal_pcb(
        case_id=spec.case_id,
        board_size=spec.board_size,
        origin=spec.origin,
        nets=[Net(0, "")],
    )
    ox, oy = spec.origin
    width, height = spec.board_size
    y = oy + height / 2.0
    pitch = width / 6.0
    sizes = [(0.45, 0.2), (0.6, 0.3), (0.8, 0.4), (1.0, 0.45), (1.2, 0.5)]
    pcb.vias = [
        _make_via(
            spec,
            index=i + 1,
            x=ox + pitch * (i + 1),
            y=y,
            size=size,
            drill=drill,
        )
        for i, (size, drill) in enumerate(sizes)
    ]
    return pcb


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="case020__via_small",
        family="via",
        altium_analog="case020",
        description=(
            "Single small through via (size 0.45 mm, drill 0.2 mm). "
            "Pressures small annular-ring rendering and drill-circle parity."
        ),
        feature_tags=("via", "size:0.45", "drill:0.2"),
        board_size=(10.0, 8.0),
        builder=_build_via_small,
        generator_script="generate_vias.py",
    ),
    CaseSpec(
        case_id="case021__via_large",
        family="via",
        altium_analog="case021",
        description=(
            "Single large through via (size 1.2 mm, drill 0.5 mm). "
            "Larger annulus for thick-stroke renderer checks."
        ),
        feature_tags=("via", "size:1.2", "drill:0.5"),
        board_size=(10.0, 8.0),
        builder=_build_via_large,
        generator_script="generate_vias.py",
    ),
    CaseSpec(
        case_id="case022__via_multiple",
        family="via",
        altium_analog="case022",
        description=(
            "Five through vias in a row at varying sizes. "
            "Exercises per-via geometry and bounding-box aggregation."
        ),
        feature_tags=("via", "multiple"),
        board_size=(18.0, 8.0),
        builder=_build_via_multiple,
        generator_script="generate_vias.py",
    ),
)
