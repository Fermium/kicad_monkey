"""Arc cases (case007, case008, case010).

Phase 2 gap-fill. Existing slot: ``case009__arc_silk_solid`` (gr_arc on
F.SilkS, solid stroke). The slots here exercise *track* arcs on F.Cu
(``Arc`` records, not graphic ``gr_arc``):

* ``case007__arc_top_quarter`` — 90° quadrant arc.
* ``case008__arc_top_semicircle`` — 180° half-circle arc.
* ``case010__arc_top_three_quarter`` — 270° three-quarter arc.

A 360° "full circle" Arc is intentionally skipped — KiCad's three-point
arc format degenerates when start≈end. Full-circle copper coverage is
deferred to a gr_circle case in the polygon/region family (>= case039).

All arcs centered near the board midpoint at varying radii so each case
has a distinct bbox for the L3 board-svg oracle.
"""

from __future__ import annotations

import math

from kicad_monkey.kicad_pcb import KiCadPcb
from kicad_monkey.kicad_pcb_other import Net, NetRef
from kicad_monkey.kicad_pcb_routing import Arc

from .common import CaseSpec, build_minimal_pcb, uid_for


def _arc_three_points(
    center: tuple[float, float],
    radius: float,
    start_deg: float,
    end_deg: float,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Sample start / midpoint / end of an arc on a circle at ``center``."""
    cx, cy = center
    mid_deg = (start_deg + end_deg) / 2.0
    def _pt(deg: float) -> tuple[float, float]:
        rad = math.radians(deg)
        return (cx + radius * math.cos(rad), cy + radius * math.sin(rad))
    return _pt(start_deg), _pt(mid_deg), _pt(end_deg)


def _build_arc(
    spec: CaseSpec,
    *,
    radius: float,
    start_deg: float,
    end_deg: float,
    width_mm: float = 0.25,
    layer: str = "F.Cu",
) -> KiCadPcb:
    pcb = build_minimal_pcb(
        case_id=spec.case_id,
        board_size=spec.board_size,
        origin=spec.origin,
        nets=[Net(0, ""), Net(1, "ARC")],
    )
    ox, oy = spec.origin
    cx = ox + spec.board_size[0] / 2.0
    cy = oy + spec.board_size[1] / 2.0
    start, mid, end = _arc_three_points((cx, cy), radius, start_deg, end_deg)
    pcb.arcs = [
        Arc(
            start_x=start[0],
            start_y=start[1],
            mid_x=mid[0],
            mid_y=mid[1],
            end_x=end[0],
            end_y=end[1],
            width=width_mm,
            layer=layer,
            net=NetRef(1, "ARC"),
            uuid=uid_for(spec.case_id, "arc"),
        )
    ]
    return pcb


def _build_quarter(spec: CaseSpec) -> KiCadPcb:
    return _build_arc(spec, radius=5.0, start_deg=0.0, end_deg=90.0)


def _build_semicircle(spec: CaseSpec) -> KiCadPcb:
    return _build_arc(spec, radius=4.0, start_deg=0.0, end_deg=180.0)


def _build_three_quarter(spec: CaseSpec) -> KiCadPcb:
    return _build_arc(spec, radius=3.0, start_deg=0.0, end_deg=270.0)


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="case007__arc_top_quarter",
        family="arc",
        altium_analog="case007",
        description=(
            "Single 90° track arc on F.Cu (Arc record). "
            "Pressures three-point arc parsing and renderer arc decomposition."
        ),
        feature_tags=("arc", "track_arc", "angle:90", "layer:F.Cu"),
        board_size=(18.0, 18.0),
        builder=_build_quarter,
        generator_script="generate_arcs.py",
    ),
    CaseSpec(
        case_id="case008__arc_top_semicircle",
        family="arc",
        altium_analog="case008",
        description=(
            "Single 180° (semicircle) track arc on F.Cu. "
            "Endpoint colinearity through the center forces robust three-point "
            "midpoint handling."
        ),
        feature_tags=("arc", "track_arc", "angle:180", "layer:F.Cu"),
        board_size=(18.0, 14.0),
        builder=_build_semicircle,
        generator_script="generate_arcs.py",
    ),
    CaseSpec(
        case_id="case010__arc_top_three_quarter",
        family="arc",
        altium_analog="case010",
        description=(
            "Single 270° (three-quarter) track arc on F.Cu. "
            "Long sweep covering more than half the circle exercises "
            "renderer large-arc-flag selection."
        ),
        feature_tags=("arc", "track_arc", "angle:270", "layer:F.Cu"),
        board_size=(18.0, 18.0),
        builder=_build_three_quarter,
        generator_script="generate_arcs.py",
    ),
)
