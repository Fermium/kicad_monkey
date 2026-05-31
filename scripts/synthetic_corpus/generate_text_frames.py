"""gr_text_box (text frame) cases (case104–case108).

Phase 3 gap-fill. Existing fixtures only exercise gr_text_box once
(``case260__coverage_missing_elements``); these new cases isolate the
text-frame render path under varying border / knockout / justify /
rotation conditions, with stroke-font effects so kicad-cli renders
them natively without a pre-emitted render_cache.

Cases generated here:

* ``case104__text_frame_basic`` — single-line text in a bordered box,
  default centered justify.
* ``case105__text_frame_no_border`` — no visible border, text only.
* ``case106__text_frame_knockout`` — knockout text frame on F.SilkS.
* ``case107__text_frame_align_left`` — multi-line text with explicit
  ``(justify left top)``.
* ``case108__text_frame_rotated`` — bordered box rotated 30°.

Each fixture is a small (≤ 20 mm) board with a single gr_text_box on
F.SilkS so the L3 board_svg oracle ties one feature per case.
"""

from __future__ import annotations

from kicad_monkey.kicad_base import StrokeType
from kicad_monkey.kicad_pcb import KiCadPcb
from kicad_monkey.kicad_pcb_gr_text import Effects, Font
from kicad_monkey.kicad_pcb_graphics import GrTextBox
from kicad_monkey.kicad_primitives import Stroke

from .common import CaseSpec, build_minimal_pcb, uid_for


def _build_text_box(
    spec: CaseSpec,
    *,
    text: str,
    box_size: tuple[float, float],
    justify: list[str] | None = None,
    border: bool | None = True,
    knockout: bool | None = None,
    angle: float = 0.0,
    layer: str = "F.SilkS",
    font_size: float = 1.2,
    thickness: float = 0.18,
    stroke_width: float = 0.15,
) -> KiCadPcb:
    pcb = build_minimal_pcb(
        case_id=spec.case_id,
        board_size=spec.board_size,
        origin=spec.origin,
    )
    ox, oy = spec.origin
    width, height = spec.board_size
    box_w, box_h = box_size
    # Center the box on the board.
    cx = ox + width / 2.0
    cy = oy + height / 2.0
    start_x = cx - box_w / 2.0
    start_y = cy - box_h / 2.0
    end_x = cx + box_w / 2.0
    end_y = cy + box_h / 2.0

    effects = Effects(
        font=Font(size_x=font_size, size_y=font_size, thickness=thickness),
        justify=justify,
    )

    box = GrTextBox(
        text=text,
        start_x=start_x,
        start_y=start_y,
        end_x=end_x,
        end_y=end_y,
        margins=(1.0, 1.0, 1.0, 1.0),
        angle=angle,
        layer=layer,
        effects=effects,
        stroke=Stroke(width=stroke_width, type=StrokeType.DEFAULT) if border else None,
        border=border,
        knockout=knockout,
        uuid=uid_for(spec.case_id, "gr_text_box"),
    )
    pcb.gr_text_boxes = [box]
    return pcb


def _build_basic(spec: CaseSpec) -> KiCadPcb:
    return _build_text_box(spec, text="FRAME", box_size=(12.0, 5.0))


def _build_no_border(spec: CaseSpec) -> KiCadPcb:
    return _build_text_box(
        spec, text="NO BORDER", box_size=(14.0, 5.0), border=False
    )


def _build_knockout(spec: CaseSpec) -> KiCadPcb:
    return _build_text_box(
        spec,
        text="KNOCKOUT",
        box_size=(13.0, 5.0),
        knockout=True,
    )


def _build_align_left(spec: CaseSpec) -> KiCadPcb:
    return _build_text_box(
        spec,
        text="LINE 1\\nLINE 2",
        box_size=(14.0, 7.0),
        justify=["left", "top"],
    )


def _build_rotated(spec: CaseSpec) -> KiCadPcb:
    return _build_text_box(
        spec,
        text="ROT30",
        box_size=(12.0, 5.0),
        angle=30.0,
    )


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="case104__text_frame_basic",
        family="text_frame",
        altium_analog="case104",
        description=(
            "Single-line gr_text_box with a default solid border on F.SilkS. "
            "Baseline text-frame render."
        ),
        feature_tags=("text_frame", "gr_text_box", "border", "layer:F.SilkS"),
        board_size=(20.0, 12.0),
        builder=_build_basic,
        generator_script="generate_text_frames.py",
    ),
    CaseSpec(
        case_id="case105__text_frame_no_border",
        family="text_frame",
        altium_analog="case105",
        description=(
            "gr_text_box rendered without a border (border=no, no stroke). "
            "Exercises the text-only path through the frame renderer."
        ),
        feature_tags=("text_frame", "gr_text_box", "no_border", "layer:F.SilkS"),
        board_size=(20.0, 12.0),
        builder=_build_no_border,
        generator_script="generate_text_frames.py",
    ),
    CaseSpec(
        case_id="case106__text_frame_knockout",
        family="text_frame",
        altium_analog="case106",
        description=(
            "Knockout gr_text_box on F.SilkS — glyphs cut through a "
            "filled background rectangle."
        ),
        feature_tags=("text_frame", "gr_text_box", "knockout", "layer:F.SilkS"),
        board_size=(20.0, 12.0),
        builder=_build_knockout,
        generator_script="generate_text_frames.py",
    ),
    CaseSpec(
        case_id="case107__text_frame_align_left",
        family="text_frame",
        altium_analog="case107",
        description=(
            "Two-line gr_text_box with explicit (justify left top). "
            "Pressures multi-line layout and justify propagation."
        ),
        feature_tags=("text_frame", "gr_text_box", "multiline", "justify:left_top"),
        board_size=(20.0, 14.0),
        builder=_build_align_left,
        generator_script="generate_text_frames.py",
    ),
    CaseSpec(
        case_id="case108__text_frame_rotated",
        family="text_frame",
        altium_analog="case108",
        description=(
            "gr_text_box rotated 30°. Exercises angle handling on both "
            "the border rectangle and the embedded text."
        ),
        feature_tags=("text_frame", "gr_text_box", "rotation:30", "layer:F.SilkS"),
        board_size=(22.0, 14.0),
        builder=_build_rotated,
        generator_script="generate_text_frames.py",
    ),
)
