"""Pad / footprint cases (case011–case018).

Phase 2 gap-fill. Existing slots in the pad family:

* ``case082__pad_per_layer_shapes`` (combined multi-shape grid)
* ``case083__pad_chamfered_roundrect``
* ``case084__pad_slot_hole``
* ``case085__via_mask_tenting``
* ``case122__custom_pad``

These earlier slots (011–018) cover the **simple** SMD / THT pad
shapes one at a time so the L3 board_svg oracle pins each shape's
emit without confounding it with mask expansion or custom primitives.

Cases generated here:

* ``case011__pad_smd_rect``      — single SMD rectangular pad (F.Cu).
* ``case012__pad_smd_round``     — single SMD round pad (F.Cu).
* ``case013__pad_smd_oval``      — single SMD oval pad (F.Cu).
* ``case014__pad_th_round``      — single THT round pad (all-Cu layers).
* ``case015__pad_th_rect``       — single THT rectangular pad.
* ``case016__pad_smd_bottom``    — bottom-side SMD pad (B.Cu).
* ``case017__pad_smd_array``     — 1×4 row of identical SMD rect pads.
* ``case018__pad_th_oval``       — single THT oval pad (round drill).
"""

from __future__ import annotations

from kicad_monkey.kicad_base import PadShape, PadType
from kicad_monkey.kicad_pad import Pad
from kicad_monkey.kicad_pcb import KiCadPcb
from kicad_monkey.kicad_pcb_footprint import Footprint
from kicad_monkey.kicad_pcb_other import Net, NetRef

from .common import CaseSpec, build_minimal_pcb, uid_for


_SMD_LAYERS = ("F.Cu", "F.Mask", "F.Paste")
_SMD_LAYERS_BOTTOM = ("B.Cu", "B.Mask", "B.Paste")
_TH_LAYERS = ("*.Cu", "*.Mask")


def _make_pad(
    spec: CaseSpec,
    *,
    index: int,
    number: str,
    pad_type: PadType,
    shape: PadShape,
    size: tuple[float, float],
    layers: tuple[str, ...],
    drill: float | None = None,
    drill_oval: tuple[float, float] | None = None,
    net_id: int,
    net_name: str,
) -> Pad:
    pad = Pad(
        number=number,
        pad_type=pad_type,
        shape=shape,
        at_x=0.0,
        at_y=0.0,
        size_x=size[0],
        size_y=size[1],
        layers=list(layers),
        net=NetRef(net_id, net_name) if pad_type != PadType.NP_THRU_HOLE else NetRef(),
        uuid=uid_for(spec.case_id, "pad", index),
    )
    if drill_oval is not None:
        pad.drill_oval = True
        pad.drill_width = drill_oval[0]
        pad.drill_height = drill_oval[1]
    elif drill is not None:
        pad.drill = drill
    return pad


def _wrap_footprint(spec: CaseSpec, *, index: int, x: float, y: float, layer: str, pads: list[Pad]) -> Footprint:
    return Footprint(
        library_link=f"Synthetic:{spec.case_id}_fp{index}",
        layer=layer,
        at_x=x,
        at_y=y,
        at_angle=0.0,
        uuid=uid_for(spec.case_id, "footprint", index),
        pads=pads,
    )


def _build_single_pad_case(
    spec: CaseSpec,
    *,
    pad_type: PadType,
    shape: PadShape,
    size: tuple[float, float],
    layers: tuple[str, ...],
    side: str = "F",
    drill: float | None = None,
    drill_oval: tuple[float, float] | None = None,
) -> KiCadPcb:
    pcb = build_minimal_pcb(
        case_id=spec.case_id,
        board_size=spec.board_size,
        origin=spec.origin,
        nets=[Net(0, ""), Net(1, "PAD_NET")],
    )
    ox, oy = spec.origin
    cx = ox + spec.board_size[0] / 2.0
    cy = oy + spec.board_size[1] / 2.0
    pad = _make_pad(
        spec,
        index=1,
        number="1",
        pad_type=pad_type,
        shape=shape,
        size=size,
        layers=layers,
        drill=drill,
        drill_oval=drill_oval,
        net_id=1,
        net_name="PAD_NET",
    )
    footprint_layer = "F.Cu" if side == "F" else "B.Cu"
    pcb.footprints = [
        _wrap_footprint(spec, index=1, x=cx, y=cy, layer=footprint_layer, pads=[pad])
    ]
    return pcb


def _build_pad_array(spec: CaseSpec) -> KiCadPcb:
    pcb = build_minimal_pcb(
        case_id=spec.case_id,
        board_size=spec.board_size,
        origin=spec.origin,
        nets=[Net(0, ""), Net(1, "PAD_NET")],
    )
    ox, oy = spec.origin
    width, height = spec.board_size
    y = oy + height / 2.0
    count = 4
    pitch = width / (count + 1)
    pads: list[Pad] = []
    for i in range(count):
        pads.append(
            _make_pad(
                spec,
                index=i + 1,
                number=str(i + 1),
                pad_type=PadType.SMD,
                shape=PadShape.RECT,
                size=(1.2, 0.8),
                layers=_SMD_LAYERS,
                net_id=1,
                net_name="PAD_NET",
            )
        )
    # Place pads at independent footprints to keep one-feature isolation.
    pcb.footprints = [
        _wrap_footprint(
            spec,
            index=i + 1,
            x=ox + pitch * (i + 1),
            y=y,
            layer="F.Cu",
            pads=[pad],
        )
        for i, pad in enumerate(pads)
    ]
    return pcb


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="case011__pad_smd_rect",
        family="pad",
        altium_analog="case011",
        description="Single SMD rectangular pad on F.Cu (size 2.0×1.2 mm).",
        feature_tags=("pad", "smd", "shape:rect", "layer:F.Cu"),
        board_size=(10.0, 8.0),
        builder=lambda s: _build_single_pad_case(
            s,
            pad_type=PadType.SMD,
            shape=PadShape.RECT,
            size=(2.0, 1.2),
            layers=_SMD_LAYERS,
        ),
        generator_script="generate_pads.py",
    ),
    CaseSpec(
        case_id="case012__pad_smd_round",
        family="pad",
        altium_analog="case012",
        description="Single SMD circular pad on F.Cu (diameter 1.6 mm).",
        feature_tags=("pad", "smd", "shape:circle", "layer:F.Cu"),
        board_size=(10.0, 8.0),
        builder=lambda s: _build_single_pad_case(
            s,
            pad_type=PadType.SMD,
            shape=PadShape.CIRCLE,
            size=(1.6, 1.6),
            layers=_SMD_LAYERS,
        ),
        generator_script="generate_pads.py",
    ),
    CaseSpec(
        case_id="case013__pad_smd_oval",
        family="pad",
        altium_analog="case013",
        description="Single SMD oval pad on F.Cu (2.4×1.2 mm, rotated 0°).",
        feature_tags=("pad", "smd", "shape:oval", "layer:F.Cu"),
        board_size=(10.0, 8.0),
        builder=lambda s: _build_single_pad_case(
            s,
            pad_type=PadType.SMD,
            shape=PadShape.OVAL,
            size=(2.4, 1.2),
            layers=_SMD_LAYERS,
        ),
        generator_script="generate_pads.py",
    ),
    CaseSpec(
        case_id="case014__pad_th_round",
        family="pad",
        altium_analog="case014",
        description=(
            "Single THT circular pad (size 2.0 mm, drill 0.8 mm) on all "
            "copper / mask layers."
        ),
        feature_tags=("pad", "thru_hole", "shape:circle"),
        board_size=(10.0, 8.0),
        builder=lambda s: _build_single_pad_case(
            s,
            pad_type=PadType.THRU_HOLE,
            shape=PadShape.CIRCLE,
            size=(2.0, 2.0),
            layers=_TH_LAYERS,
            drill=0.8,
        ),
        generator_script="generate_pads.py",
    ),
    CaseSpec(
        case_id="case015__pad_th_rect",
        family="pad",
        altium_analog="case015",
        description=(
            "Single THT rectangular pad (2.4×1.6 mm, drill 0.8 mm)."
        ),
        feature_tags=("pad", "thru_hole", "shape:rect"),
        board_size=(10.0, 8.0),
        builder=lambda s: _build_single_pad_case(
            s,
            pad_type=PadType.THRU_HOLE,
            shape=PadShape.RECT,
            size=(2.4, 1.6),
            layers=_TH_LAYERS,
            drill=0.8,
        ),
        generator_script="generate_pads.py",
    ),
    CaseSpec(
        case_id="case016__pad_smd_bottom",
        family="pad",
        altium_analog="case016",
        description=(
            "Single SMD rectangular pad on B.Cu — bottom-side rendering "
            "parity vs case011 (F.Cu)."
        ),
        feature_tags=("pad", "smd", "shape:rect", "layer:B.Cu"),
        board_size=(10.0, 8.0),
        builder=lambda s: _build_single_pad_case(
            s,
            pad_type=PadType.SMD,
            shape=PadShape.RECT,
            size=(2.0, 1.2),
            layers=_SMD_LAYERS_BOTTOM,
            side="B",
        ),
        generator_script="generate_pads.py",
    ),
    CaseSpec(
        case_id="case017__pad_smd_array",
        family="pad",
        altium_analog="case017",
        description=(
            "Row of four identical SMD rectangular pads on F.Cu. "
            "Multi-pad aggregate for bounding-box assembly."
        ),
        feature_tags=("pad", "smd", "shape:rect", "multiple"),
        board_size=(15.0, 6.0),
        builder=_build_pad_array,
        generator_script="generate_pads.py",
    ),
    CaseSpec(
        case_id="case018__pad_th_oval",
        family="pad",
        altium_analog="case018",
        description=(
            "Single THT oval pad (3.0×1.6 mm, round drill 0.8 mm). "
            "Oval pad outline with round drill (no slot)."
        ),
        feature_tags=("pad", "thru_hole", "shape:oval"),
        board_size=(10.0, 8.0),
        builder=lambda s: _build_single_pad_case(
            s,
            pad_type=PadType.THRU_HOLE,
            shape=PadShape.OVAL,
            size=(3.0, 1.6),
            layers=_TH_LAYERS,
            drill=0.8,
        ),
        generator_script="generate_pads.py",
    ),
)
