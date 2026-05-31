"""Shared scaffolding for Phase 2+ KiCad synthetic corpus generators.

All cases land under ``<corpus>/kicad/pcb_foundation/<case_id>/input/``
with this five-file shape:

* ``<case_id>.kicad_pcb``
* ``<case_id>.kicad_pro``
* ``<case_id>.kicad_sch``
* ``case_metadata.json``

Reference SVGs live in the sibling ``reference_output/`` directory and
are regenerated via ``generate_board_svg_references.py`` (Phase 2 driver
delegates to that script — it already resolves the staged kicad-cli
build through ``resolve_kicad_cli``).

The minimal board ``standard_setup_sexp()`` / ``standard_layers()`` /
``rectangular_outline()`` mirror the conventions established by
``generate_kicad_synthetic_dimensions.py`` (Edge.Cuts stroke 0.05 mm
stays within the L3 viewBox tolerance).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from kicad_monkey.kicad_base import LayerType, Stroke, StrokeType
from kicad_monkey.kicad_pcb import KiCadPcb
from kicad_monkey.kicad_pcb_gr_line import GrLine
from kicad_monkey.kicad_pcb_other import Layer, Net


BOARD_VERSION = 20241229
GENERATOR_VERSION = "9.0"
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "wavenumber/kicad/synthetic-corpus")


def uid_for(*parts: object) -> str:
    """Stable UUIDv5 derived from the synthetic corpus namespace."""
    return str(uuid.uuid5(NAMESPACE, "/".join(str(p) for p in parts)))


def _q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def standard_layers() -> list[Layer]:
    """Two-copper-layer stack used by the foundation case bucket."""
    return [
        Layer(0, "F.Cu", LayerType.SIGNAL),
        Layer(2, "B.Cu", LayerType.SIGNAL),
        Layer(9, "F.Adhes", LayerType.USER, "F.Adhesive"),
        Layer(11, "B.Adhes", LayerType.USER, "B.Adhesive"),
        Layer(13, "F.Paste", LayerType.USER),
        Layer(15, "B.Paste", LayerType.USER),
        Layer(5, "F.SilkS", LayerType.USER, "F.Silkscreen"),
        Layer(7, "B.SilkS", LayerType.USER, "B.Silkscreen"),
        Layer(1, "F.Mask", LayerType.USER),
        Layer(3, "B.Mask", LayerType.USER),
        Layer(17, "Dwgs.User", LayerType.USER, "User.Drawings"),
        Layer(19, "Cmts.User", LayerType.USER, "User.Comments"),
        Layer(21, "Eco1.User", LayerType.USER, "User.Eco1"),
        Layer(23, "Eco2.User", LayerType.USER, "User.Eco2"),
        Layer(25, "Edge.Cuts", LayerType.USER),
        Layer(27, "Margin", LayerType.USER),
        Layer(31, "F.CrtYd", LayerType.USER, "F.Courtyard"),
        Layer(29, "B.CrtYd", LayerType.USER, "B.Courtyard"),
        Layer(35, "F.Fab", LayerType.USER),
        Layer(33, "B.Fab", LayerType.USER),
    ]


def standard_setup_sexp() -> list[object]:
    return [
        "setup",
        ["pad_to_mask_clearance", 0.0],
        ["allow_soldermask_bridges_in_footprints", "no"],
    ]


def rectangular_outline(
    *,
    case_id: str,
    width: float,
    height: float,
    origin: tuple[float, float] = (0.0, 0.0),
    stroke_width: float = 0.05,
) -> list[GrLine]:
    """Build a closed Edge.Cuts rectangle at ``origin`` with given size."""
    x0, y0 = origin
    x1, y1 = x0 + width, y0 + height
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    lines: list[GrLine] = []
    for i, (start, end) in enumerate(zip(corners, corners[1:] + corners[:1]), start=1):
        lines.append(
            GrLine(
                start_x=start[0],
                start_y=start[1],
                end_x=end[0],
                end_y=end[1],
                layer="Edge.Cuts",
                stroke=Stroke(width=stroke_width, type=StrokeType.DEFAULT),
                uuid=uid_for(case_id, "outline", i),
            )
        )
    return lines


def build_minimal_pcb(
    *,
    case_id: str,
    board_size: tuple[float, float],
    origin: tuple[float, float] = (0.0, 0.0),
    nets: Sequence[Net] = (Net(0, ""),),
    generator: str = "generate_kicad_synthetic_corpus.py",
) -> KiCadPcb:
    """PCB scaffold: layers, setup, rectangular outline, nets."""
    pcb = KiCadPcb()
    pcb.version = BOARD_VERSION
    pcb.generator = generator
    pcb.generator_version = GENERATOR_VERSION
    pcb.thickness = 1.6
    pcb.paper = "A4"
    pcb.layers = standard_layers()
    pcb.setup_sexp = standard_setup_sexp()
    pcb.nets = list(nets)
    pcb.gr_lines = rectangular_outline(
        case_id=case_id,
        width=board_size[0],
        height=board_size[1],
        origin=origin,
    )
    return pcb


def minimal_project_json(project_name: str) -> str:
    data = {
        "board": {
            "design_settings": {
                "defaults": {
                    "board_outline_line_width": 0.05,
                    "copper_line_width": 0.2,
                    "silk_line_width": 0.12,
                }
            }
        },
        "meta": {"filename": f"{project_name}.kicad_pro", "version": 1},
        "net_settings": {
            "classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.25}],
            "meta": {"version": 3},
            "net_colors": {},
            "netclass_assignments": {},
            "netclass_patterns": [],
        },
        "project": {"files": []},
        "text_variables": {"SYNTHETIC_FIXTURE": project_name},
    }
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def minimal_schematic_text(project_name: str, *, generator_name: str) -> str:
    return (
        f"(kicad_sch\n"
        f"  (version 20250114)\n"
        f"  (generator {_q(generator_name)})\n"
        f"  (generator_version {_q(GENERATOR_VERSION)})\n"
        f"  (uuid {_q(uid_for(project_name, 'schematic'))})\n"
        f"  (paper {_q('A4')})\n"
        f"  (lib_symbols)\n"
        f"  (sheet_instances\n"
        f"    (path {_q('/')}\n"
        f"      (page {_q('1')})\n"
        f"    )\n"
        f"  )\n"
        f"  (embedded_fonts no)\n"
        f")\n"
    )


@dataclass(frozen=True)
class CaseSpec:
    """Definition of a single synthetic foundation case.

    ``builder(spec)`` returns a fully populated ``KiCadPcb`` that is then
    serialized to ``<case_id>.kicad_pcb``. Family generators expose a
    ``CASES`` tuple of these specs.
    """
    case_id: str
    family: str
    altium_analog: str  # "kicad_only" or "caseNNN"
    description: str
    feature_tags: tuple[str, ...]
    board_size: tuple[float, float]
    builder: Callable[["CaseSpec"], KiCadPcb]
    generator_script: str
    origin: tuple[float, float] = (100.0, 90.0)
    notes: tuple[str, ...] = ()

    @property
    def board_filename(self) -> str:
        return f"{self.case_id}.kicad_pcb"


def case_metadata(spec: CaseSpec) -> dict[str, object]:
    return {
        "case_id": spec.case_id,
        "family": spec.family,
        "altium_analog_case_id": spec.altium_analog,
        "kicad_min_version": "9.0",
        "origin": "synthetic",
        "status": "active",
        "domains": ["board_svg", "pcb_ir", "pcb_data_models"],
        "tags": [
            "synthetic",
            "data_models",
            "board_svg",
            "focused_feature_case",
            *spec.feature_tags,
        ],
        "test_intent": spec.description,
        "feature_coverage": {
            "pcb": [spec.family],
            "board_svg": [f"{spec.family}_rendering"],
        },
        "oracle_policy": {"board_svg": "smoke", "pcb_ir": "smoke"},
        "provenance": {
            "source_kind": "synthetic",
            "source_path": None,
            "license_usage": "test_fixture",
            "generator": f"kicad_monkey/scripts/synthetic_corpus/{spec.generator_script}",
        },
        "notes": [
            f"Generated case: {spec.case_id} ({spec.family}).",
            "Regenerate via scripts/generate_kicad_synthetic_corpus.py instead of "
            "hand-editing the .kicad_pcb or metadata.",
            *spec.notes,
        ],
    }


def write_case_artifacts(
    corpus_root: Path,
    spec: CaseSpec,
    *,
    force: bool,
    dry_run: bool,
) -> list[Path]:
    """Write all four per-case files to the foundation bucket."""
    case_dir = corpus_root / "kicad" / "pcb_foundation" / spec.case_id / "input"
    board_path = case_dir / spec.board_filename
    project_path = case_dir / f"{spec.case_id}.kicad_pro"
    schematic_path = case_dir / f"{spec.case_id}.kicad_sch"
    metadata_path = case_dir / "case_metadata.json"

    pcb_text = spec.builder(spec).to_string()
    project_text = minimal_project_json(spec.case_id)
    schematic_text = minimal_schematic_text(
        spec.case_id, generator_name=spec.generator_script
    )
    metadata_text = (
        json.dumps(case_metadata(spec), indent=2, sort_keys=True) + "\n"
    )

    files: list[tuple[Path, str]] = [
        (board_path, pcb_text),
        (project_path, project_text),
        (schematic_path, schematic_text),
        (metadata_path, metadata_text),
    ]

    existing = [p for p, _ in files if p.exists()]
    if existing and not force:
        joined = "\n".join(str(p) for p in existing)
        raise FileExistsError(
            f"refusing to overwrite case {spec.case_id} without --force:\n{joined}"
        )

    if dry_run:
        return [p for p, _ in files]

    for path, text in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return [p for p, _ in files]


def filter_specs(
    specs: Iterable[CaseSpec],
    *,
    only: Iterable[str] | None = None,
) -> list[CaseSpec]:
    """Optionally narrow a family's specs to specific case ids."""
    if not only:
        return list(specs)
    wanted = set(only)
    return [s for s in specs if s.case_id in wanted]
