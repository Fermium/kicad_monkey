"""Focused project/design public API cleanup coverage."""

from __future__ import annotations

import json

import pytest

from kicad_monkey import KiCadDesign, KiCadObjectCollection, KiCadPcb, KiCadSchematic
from kicad_monkey.kicad_design_json import KICAD_DESIGN_JSON_SCHEMA
from kicad_monkey.kicad_project import KiCadProject, ProjectVariant


_MIN_SCH_TEXT = """(kicad_sch (version 20250114) (generator "eeschema")
  (generator_version "9.0")
  (uuid "11111111-2222-3333-4444-555555555555")
  (paper "A4")
)
"""

_MIN_PCB_TEXT = """(kicad_pcb
  (version 20241229)
  (generator "pcbnew")
  (generator_version "9.0")
  (general (thickness 1.6) (legacy_teardrops no))
  (paper "A4")
  (layers)
  (embedded_fonts no)
)
"""


def _write_project(path, text_variables=None):
    path.write_text(
        json.dumps(
            {
                "text_variables": dict(text_variables or {}),
                "schematic": {
                    "variants": [
                        {"name": "Default"},
                        {"name": "Alt", "description": "alternate assembly"},
                    ]
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_schematic(path):
    path.write_text(_MIN_SCH_TEXT, encoding="utf-8")


def _write_pcb(path):
    path.write_text(_MIN_PCB_TEXT, encoding="utf-8")


def test_project_json_text_variable_and_variant_helpers(tmp_path):
    project = KiCadProject.from_json_dict(
        {
            "text_variables": {"TITLE": "Demo"},
            "schematic": {"variants": [{"name": "Default"}]},
        }
    )

    assert project.get_text_variable("TITLE") == "Demo"
    assert project.get_variant("Default") == ProjectVariant("Default")
    assert list(project.iter_variants()) == [ProjectVariant("Default")]

    project.set_text_variable("REV", "A")
    assert project.text_variables["REV"] == "A"
    assert project.raw["text_variables"]["REV"] == "A"
    assert project.remove_text_variable("REV") is True
    assert "REV" not in project.raw["text_variables"]

    out = tmp_path / "demo.kicad_pro"
    project.to_file(out)
    loaded = KiCadProject.from_file(out)
    assert loaded.to_json()["text_variables"] == {"TITLE": "Demo"}


def test_design_from_file_dispatches_by_suffix(tmp_path):
    pro = tmp_path / "demo.kicad_pro"
    sch = tmp_path / "demo.kicad_sch"
    pcb = tmp_path / "demo.kicad_pcb"
    _write_project(pro, {"TITLE": "Demo"})
    _write_schematic(sch)
    _write_pcb(pcb)

    assert KiCadDesign.from_file(pro).project_path == pro
    assert isinstance(KiCadDesign.from_file(sch).top_schematic, KiCadSchematic)
    assert KiCadDesign.from_file(pcb).pcb_path == pcb

    with pytest.raises(ValueError, match="unsupported"):
        KiCadDesign.from_file(tmp_path / "demo.txt")


def test_design_document_query_and_pcb_ir(tmp_path):
    pro = tmp_path / "demo.kicad_pro"
    sch = tmp_path / "demo.kicad_sch"
    pcb = tmp_path / "demo.kicad_pcb"
    _write_project(pro, {"TITLE": "Demo"})
    _write_schematic(sch)
    _write_pcb(pcb)

    design = KiCadDesign.from_project_file(pro)

    assert isinstance(design.objects, KiCadObjectCollection)
    assert isinstance(design.objects.first(KiCadProject), KiCadProject)
    assert isinstance(design.objects.first(KiCadSchematic), KiCadSchematic)
    assert isinstance(design.objects.first(KiCadPcb), KiCadPcb)

    doc = design.to_pcb_ir(document_id="board")
    assert doc.source_kind == "PCB"
    assert doc.document_id == "board"


def test_design_schematic_mutators_and_json_text(tmp_path):
    pro = tmp_path / "demo.kicad_pro"
    sch = tmp_path / "demo.kicad_sch"
    _write_project(pro, {})
    _write_schematic(sch)

    design = KiCadDesign.from_project_file(pro)
    extra = KiCadSchematic.from_text(_MIN_SCH_TEXT)

    assert design.add_schematic(extra) is extra
    assert list(design.iter_schematics())[-1] is extra
    assert design.remove_schematic(extra) is True

    text = design.to_json_text(include_indexes=False)
    payload = json.loads(text)
    assert payload["schema"] == KICAD_DESIGN_JSON_SCHEMA
