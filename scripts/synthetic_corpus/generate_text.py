"""Stroke-font text cases (Phase 3 gap-fill).

Existing slots in the text family are already covered:

* ``case026-029__text_stroke_*`` — basic / bold / italic / KiCad font.
* ``case030-032__text_ttf_arial*`` — Arial with pre-emitted render_cache.
* ``case210-215__text_stroke_*`` — alignment / rotation variants.

New cases generated here:

* ``case101__text_stroke_variable`` — gr_text using a ``${VAR}`` token
  resolved against ``text_variables`` in the .kicad_pro. Pressures the
  kicad-cli text expansion path.

The TTF-only slots ``case033`` (rotated TTF), ``case099`` and ``case103``
(font specials) remain open in Phase 3 — they require a render_cache
emission helper that runs FreeType during the generator pass.
``generate_text_frames.py`` handles the gr_text_box gaps (case104–108).
"""

from __future__ import annotations

from kicad_monkey.kicad_pcb import KiCadPcb
from kicad_monkey.kicad_pcb_gr_text import Effects, Font, GrText

from .common import CaseSpec, build_minimal_pcb, uid_for


def _build_text_variable(spec: CaseSpec) -> KiCadPcb:
    pcb = build_minimal_pcb(
        case_id=spec.case_id,
        board_size=spec.board_size,
        origin=spec.origin,
    )
    ox, oy = spec.origin
    cx = ox + spec.board_size[0] / 2.0
    cy = oy + spec.board_size[1] / 2.0
    # Variable name matches the SYNTHETIC_FIXTURE entry in
    # `minimal_project_json` so kicad-cli resolves it on export.
    text = GrText(
        text="${SYNTHETIC_FIXTURE}",
        at_x=cx,
        at_y=cy,
        at_angle=0.0,
        layer="F.SilkS",
        uuid=uid_for(spec.case_id, "gr_text"),
        effects=Effects(font=Font(size_x=1.0, size_y=1.0, thickness=0.15)),
    )
    pcb.gr_texts = [text]
    return pcb


CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="case101__text_stroke_variable",
        family="text",
        altium_analog="case101",
        description=(
            "gr_text whose payload is a ${VAR} token. The project file "
            "defines SYNTHETIC_FIXTURE in `text_variables`, so kicad-cli "
            "should expand it to the case_id before rendering."
        ),
        feature_tags=("text", "stroke", "variable_substitution", "layer:F.SilkS"),
        board_size=(20.0, 8.0),
        builder=_build_text_variable,
        generator_script="generate_text.py",
    ),
)
