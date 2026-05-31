"""Track segment cases (case001–case003).

Phase 2 gap-fill. Existing slots already covered by the corpus:

* ``case004__track_multiple_45`` — multiple F.Cu tracks at 45°.
* ``case005__track_top_default`` — single F.Cu track, default width.
* ``case006__track_with_curves`` — F.Cu tracks with arc-track segments.

New cases generated here:

* ``case001__track_top_1mil`` — minimum-width F.Cu segment (0.0254 mm).
* ``case002__track_top_25mil`` — medium F.Cu segment (0.635 mm).
* ``case003__track_top_50mil`` — wide F.Cu segment (1.27 mm).

All three exercise stroke-width rounding and viewBox-tolerance edges on
a single segment, isolating the track-render path. Origin (100, 90) mm
matches the existing one-feature foundation cases.
"""

from __future__ import annotations

from kicad_monkey.kicad_pcb import KiCadPcb
from kicad_monkey.kicad_pcb_other import Net, NetRef
from kicad_monkey.kicad_pcb_routing import Segment

from .common import CaseSpec, build_minimal_pcb, uid_for


MIL_TO_MM = 0.0254


def _build_single_track(spec: CaseSpec, *, width_mm: float, layer: str) -> KiCadPcb:
    pcb = build_minimal_pcb(
        case_id=spec.case_id,
        board_size=spec.board_size,
        origin=spec.origin,
        nets=[Net(0, ""), Net(1, "TRACK")],
    )
    ox, oy = spec.origin
    width, height = spec.board_size
    # Centered horizontal segment, 1/3 board width from each edge.
    margin_x = width / 3.0
    y = oy + height / 2.0
    pcb.segments = [
        Segment(
            start_x=ox + margin_x,
            start_y=y,
            end_x=ox + width - margin_x,
            end_y=y,
            width=width_mm,
            layer=layer,
            net=NetRef(1, "TRACK"),
            uuid=uid_for(spec.case_id, "segment"),
        )
    ]
    return pcb


def _build_track_1mil(spec: CaseSpec) -> KiCadPcb:
    return _build_single_track(spec, width_mm=1.0 * MIL_TO_MM, layer="F.Cu")


def _build_track_25mil(spec: CaseSpec) -> KiCadPcb:
    return _build_single_track(spec, width_mm=25.0 * MIL_TO_MM, layer="F.Cu")


def _build_track_50mil(spec: CaseSpec) -> KiCadPcb:
    return _build_single_track(spec, width_mm=50.0 * MIL_TO_MM, layer="F.Cu")


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="case001__track_top_1mil",
        family="track",
        altium_analog="case001",
        description=(
            "Single F.Cu track segment at 1 mil width (0.0254 mm). "
            "Pressures stroke-width rounding at the minimum-width edge."
        ),
        feature_tags=("track", "width:1mil", "layer:F.Cu"),
        board_size=(15.0, 10.0),
        builder=_build_track_1mil,
        generator_script="generate_tracks.py",
    ),
    CaseSpec(
        case_id="case002__track_top_25mil",
        family="track",
        altium_analog="case002",
        description=(
            "Single F.Cu track segment at 25 mil width (0.635 mm). "
            "Mid-range stroke width for renderer parity."
        ),
        feature_tags=("track", "width:25mil", "layer:F.Cu"),
        board_size=(15.0, 10.0),
        builder=_build_track_25mil,
        generator_script="generate_tracks.py",
    ),
    CaseSpec(
        case_id="case003__track_top_50mil",
        family="track",
        altium_analog="case003",
        description=(
            "Single F.Cu track segment at 50 mil width (1.27 mm). "
            "Wide stroke that visibly inflates bbox vs centerline."
        ),
        feature_tags=("track", "width:50mil", "layer:F.Cu"),
        board_size=(15.0, 10.0),
        builder=_build_track_50mil,
        generator_script="generate_tracks.py",
    ),
)
