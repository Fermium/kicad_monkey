"""Fill (zone) cases (case023, case025).

Phase 2 gap-fill. Existing slot: ``case024__fill_top_zone`` (rectangular
F.Cu zone, hatched edge, fill enabled).

New cases generated here:

* ``case023__fill_top_small`` — small F.Cu zone (3×3 mm).
* ``case025__fill_bottom_zone`` — rectangular zone on B.Cu (mirror of
  the case024 placement, opposite copper layer).

The bottom-layer variant exercises layer mirroring on the B.Cu render
path. Bigger / inner-layer / hatched-fill variants land in case090+
during Phase 6 (poly/region advanced).

The filled-polygon geometry is emitted as the same rectangle as the
outline. kicad-cli does not re-fill on export; pre-emitting the filled
polygon keeps the L3 board_svg oracle non-empty without depending on a
pcbnew CLI fill pass.
"""

from __future__ import annotations

from kicad_monkey.kicad_pcb import KiCadPcb
from kicad_monkey.kicad_pcb_other import Net, NetRef
from kicad_monkey.kicad_pcb_zone import FilledPolygon, Zone, ZonePolygon

from .common import CaseSpec, build_minimal_pcb, uid_for


def _build_zone_rect(
    spec: CaseSpec,
    *,
    rect_size: tuple[float, float],
    layer: str,
) -> KiCadPcb:
    pcb = build_minimal_pcb(
        case_id=spec.case_id,
        board_size=spec.board_size,
        origin=spec.origin,
        nets=[Net(0, "")],
    )
    ox, oy = spec.origin
    margin_x = (spec.board_size[0] - rect_size[0]) / 2.0
    margin_y = (spec.board_size[1] - rect_size[1]) / 2.0
    x0 = ox + margin_x
    y0 = oy + margin_y
    x1 = x0 + rect_size[0]
    y1 = y0 + rect_size[1]
    rect_pts = [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]

    pcb.zones = [
        Zone(
            net=NetRef(0, ""),
            has_explicit_net_name=True,
            layers=[layer],
            layers_plural=False,
            uuid=uid_for(spec.case_id, "zone"),
            hatch_style="edge",
            hatch_pitch=0.5,
            connect_pads_clearance=0.5,
            min_thickness=0.25,
            fill_enabled=True,
            thermal_gap=0.5,
            thermal_bridge_width=0.5,
            island_removal_mode=1,
            island_area_min=10.0,
            polygons=[ZonePolygon(points=rect_pts)],
            filled_polygons=[FilledPolygon(layer=layer, island=True, points=rect_pts)],
        )
    ]
    return pcb


def _build_fill_top_small(spec: CaseSpec) -> KiCadPcb:
    return _build_zone_rect(spec, rect_size=(3.0, 3.0), layer="F.Cu")


def _build_fill_bottom_zone(spec: CaseSpec) -> KiCadPcb:
    return _build_zone_rect(spec, rect_size=(5.0, 2.75), layer="B.Cu")


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="case023__fill_top_small",
        family="fill",
        altium_analog="case023",
        description=(
            "Small 3×3 mm filled zone on F.Cu. "
            "Pressures small-area fill rendering and viewBox tolerance."
        ),
        feature_tags=("fill", "zone", "layer:F.Cu", "size:3x3"),
        board_size=(10.0, 8.0),
        builder=_build_fill_top_small,
        generator_script="generate_fills.py",
    ),
    CaseSpec(
        case_id="case025__fill_bottom_zone",
        family="fill",
        altium_analog="case025",
        description=(
            "Rectangular filled zone on B.Cu (5×2.75 mm). "
            "Pressures bottom-side fill rendering — layer mirror parity "
            "with the F.Cu baseline (case024)."
        ),
        feature_tags=("fill", "zone", "layer:B.Cu"),
        board_size=(10.0, 5.0),
        builder=_build_fill_bottom_zone,
        generator_script="generate_fills.py",
    ),
)
