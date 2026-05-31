"""KiCad synthetic corpus generator package.

Per-family generators produce one ``.kicad_pcb`` + ``.kicad_pro`` +
``.kicad_sch`` + ``case_metadata.json`` per case under
``<corpus>/kicad/pcb_foundation/case<NNN>__<descriptor>/input/``.

See ``docs/plans/KICAD_PCB_FOUNDATION_SYNTHETIC_CORPUS_PLAN.md`` for the
naming convention and case roadmap.
"""

from __future__ import annotations

from .common import (
    BOARD_VERSION,
    GENERATOR_VERSION,
    CaseSpec,
    build_minimal_pcb,
    case_metadata,
    minimal_project_json,
    minimal_schematic_text,
    rectangular_outline,
    standard_layers,
    standard_setup_sexp,
    uid_for,
    write_case_artifacts,
)

__all__ = (
    "BOARD_VERSION",
    "GENERATOR_VERSION",
    "CaseSpec",
    "build_minimal_pcb",
    "case_metadata",
    "minimal_project_json",
    "minimal_schematic_text",
    "rectangular_outline",
    "standard_layers",
    "standard_setup_sexp",
    "uid_for",
    "write_case_artifacts",
)
