"""Generate synthetic KiCad netlist hierarchy fixture.

The fixture targets compact netlist edge cases that are awkward to isolate in
large real-world projects:

* repeated sheet instances of the same child schematic,
* sheet-level ``on_board no`` exclusion,
* nested off-board sheet exclusion,
* wire endpoint landing mid-segment without an explicit junction,
* isolated weak pins vs. isolated named bidirectional pins.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from kicad_monkey import KiCadSchematic
from kicad_monkey.kicad_lib_subsymbol import LibSubSymbol
from kicad_monkey.kicad_lib_symbol import LibSymbol
from kicad_monkey.kicad_sch_enums import LabelShape, PinElectricalType, PinGraphicStyle
from kicad_monkey.kicad_sch_label import SchHierarchicalLabel
from kicad_monkey.kicad_sch_sheet import (
    SchSheet,
    SchSheetInstance,
    SchSheetPin,
    SchSheetProperty,
)
from kicad_monkey.kicad_sch_symbol import SchSymbol, SchSymbolInstance, SchSymbolPin
from kicad_monkey.kicad_sch_wire import SchWire
from kicad_monkey.kicad_sym_pin import SymPin
from kicad_monkey.kicad_sym_property import SymProperty


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_ROOT = (
    PACKAGE_ROOT
    / "tests"
    / "corpus"
    / ".unpacked"
    / "kicad"
    / "projects"
    / "synthetic-netlist-hierarchy"
)
PROJECT_NAME = "synthetic-netlist-hierarchy"
NAMESPACE = uuid.UUID("e5a0d3b4-9484-4703-a8c7-59dfc936b985")


def uid(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))


def pin(
    number: str,
    name: str,
    electrical: PinElectricalType,
    *,
    hide: bool = False,
) -> SymPin:
    return SymPin(
        electrical_type=electrical,
        graphic_style=PinGraphicStyle.LINE,
        at_x=0.0,
        at_y=0.0,
        at_angle=180.0,
        length=2.54,
        number=number,
        name=name,
        hide=hide,
    )


def lib_symbol(name: str, pins: list[SymPin]) -> LibSymbol:
    return LibSymbol(
        name=name,
        properties=[
            SymProperty(key="Reference", value="U", id=0),
            SymProperty(key="Value", value=name, id=1),
        ],
        subsymbols=[
            LibSubSymbol(name=f"{name}_1_0", unit=1, style=0, pins=pins),
        ],
    )


def common_libs() -> list[LibSymbol]:
    return [
        lib_symbol("SYNTH_PASSIVE", [pin("1", "~", PinElectricalType.PASSIVE)]),
        lib_symbol("SYNTH_BIDI", [pin("1", "VREF", PinElectricalType.BIDIRECTIONAL)]),
        lib_symbol(
            "SYNTH_NC",
            [pin("1", "NC", PinElectricalType.NO_CONNECT, hide=True)],
        ),
    ]


def symbol(
    lib_id: str,
    ref: str,
    value: str,
    x: float,
    y: float,
    name: str,
    *,
    instances: list[tuple[str, str]] | None = None,
) -> SchSymbol:
    sym = SchSymbol(
        lib_id=lib_id,
        at_x=x,
        at_y=y,
        at_angle=0.0,
        unit=1,
        convert=1,
        uuid=uid(f"symbol:{name}"),
    )
    sym.properties = [
        SymProperty(key="Reference", value=ref, id=0, at_x=x, at_y=y - 1.27),
        SymProperty(key="Value", value=value, id=1, at_x=x, at_y=y + 1.27),
    ]
    sym.pins = [
        SchSymbolPin(number="1", uuid=uid(f"symbol-pin:{name}:1")),
    ]
    sym.instances = [
        SchSymbolInstance(project=PROJECT_NAME, path=path, reference=iref, unit=1)
        for path, iref in (instances or [])
    ]
    return sym


def wire(name: str, *points: tuple[float, float]) -> SchWire:
    return SchWire(points=list(points), uuid=uid(f"wire:{name}"))


def hier_label(name: str, x: float, y: float, token: str) -> SchHierarchicalLabel:
    return SchHierarchicalLabel(
        text=name,
        shape=LabelShape.INPUT,
        at_x=x,
        at_y=y,
        uuid=uid(f"hier-label:{token}"),
    )


def sheet(
    file_name: str,
    sheet_name: str,
    token: str,
    x: float,
    y: float,
    *,
    on_board: bool = True,
    pins: list[SchSheetPin] | None = None,
    instance_path: str | None = None,
    page: str = "",
) -> SchSheet:
    sh = SchSheet(
        at_x=x,
        at_y=y,
        size_x=25.4,
        size_y=12.7,
        on_board=on_board,
        uuid=uid(f"sheet:{token}"),
    )
    sh.properties = [
        SchSheetProperty(
            key="Sheetname",
            value=sheet_name,
            at_x=x,
            at_y=y - 1.27,
        ),
        SchSheetProperty(
            key="Sheetfile",
            value=file_name,
            at_x=x,
            at_y=y + 1.27,
        ),
    ]
    sh.pins = pins or []
    if instance_path:
        sh.instances = [
            SchSheetInstance(project=PROJECT_NAME, path=instance_path, page=page)
        ]
    return sh


def sheet_pin(name: str, x: float, y: float, token: str) -> SchSheetPin:
    return SchSheetPin(
        name=name,
        shape=LabelShape.INPUT,
        at_x=x,
        at_y=y,
        at_angle=180.0,
        uuid=uid(f"sheet-pin:{token}:{name}"),
    )


def path_for(*sheet_tokens: str) -> str:
    parts = [uid("root")] + [uid(f"sheet:{token}") for token in sheet_tokens]
    return "/" + "/".join(parts)


def root_path() -> str:
    return "/" + uid("root")


def new_schematic(name: str) -> KiCadSchematic:
    sch = KiCadSchematic()
    sch.uuid = uid(f"schematic:{name}")
    sch.lib_symbols.extend(common_libs())
    return sch


def build_root() -> KiCadSchematic:
    sch = new_schematic("root")
    sch.uuid = uid("root")
    root = root_path()

    sch.symbols.extend([
        symbol(
            "SYNTH_PASSIVE",
            "R1",
            "root-to-cell-a",
            10.0,
            20.0,
            "root:R1",
            instances=[(root, "R1")],
        ),
        symbol(
            "SYNTH_PASSIVE",
            "R2",
            "root-to-cell-b",
            10.0,
            45.0,
            "root:R2",
            instances=[(root, "R2")],
        ),
        symbol(
            "SYNTH_PASSIVE",
            "R3",
            "root-to-offboard",
            10.0,
            70.0,
            "root:R3",
            instances=[(root, "R3")],
        ),
        symbol(
            "SYNTH_BIDI",
            "U1",
            "isolated-bidi",
            70.0,
            20.0,
            "root:U1",
            instances=[(root, "U1")],
        ),
        symbol(
            "SYNTH_PASSIVE",
            "R4",
            "isolated-weak",
            70.0,
            35.0,
            "root:R4",
            instances=[(root, "R4")],
        ),
    ])
    sch.wires.extend([
        wire("root-cell-a", (10.0, 20.0), (25.0, 20.0)),
        wire("root-cell-b", (10.0, 45.0), (25.0, 45.0)),
        wire("root-offboard", (10.0, 70.0), (25.0, 70.0)),
    ])
    sch.sheets.extend([
        sheet(
            "reused_cell.kicad_sch",
            "CELL_A",
            "cell-a",
            25.0,
            15.0,
            pins=[sheet_pin("CELL_NET", 25.0, 20.0, "cell-a")],
            instance_path=path_for("cell-a"),
            page="2",
        ),
        sheet(
            "reused_cell.kicad_sch",
            "CELL_B",
            "cell-b",
            25.0,
            40.0,
            pins=[sheet_pin("CELL_NET", 25.0, 45.0, "cell-b")],
            instance_path=path_for("cell-b"),
            page="3",
        ),
        sheet(
            "offboard_child.kicad_sch",
            "OFFBOARD_DIRECT",
            "offboard-direct",
            25.0,
            65.0,
            on_board=False,
            pins=[sheet_pin("OFF_NET", 25.0, 70.0, "offboard-direct")],
            instance_path=path_for("offboard-direct"),
            page="4",
        ),
        sheet(
            "container.kicad_sch",
            "CONTAINER",
            "container",
            105.0,
            15.0,
            pins=[],
            instance_path=path_for("container"),
            page="5",
        ),
    ])
    return sch


def build_reused_cell() -> KiCadSchematic:
    sch = new_schematic("reused-cell")
    cell_a = path_for("cell-a")
    cell_b = path_for("cell-b")
    sch.symbols.extend([
        symbol(
            "SYNTH_PASSIVE",
            "R?",
            "cell-main",
            10.0,
            10.0,
            "cell:main",
            instances=[(cell_a, "R101"), (cell_b, "R201")],
        ),
        symbol(
            "SYNTH_PASSIVE",
            "R?",
            "cell-t-tap",
            15.0,
            15.0,
            "cell:t-tap",
            instances=[(cell_a, "R102"), (cell_b, "R202")],
        ),
        symbol(
            "SYNTH_BIDI",
            "U?",
            "isolated-cell-bidi",
            35.0,
            10.0,
            "cell:bidi",
            instances=[(cell_a, "U101"), (cell_b, "U201")],
        ),
        symbol(
            "SYNTH_PASSIVE",
            "R?",
            "isolated-cell-weak",
            45.0,
            10.0,
            "cell:weak",
            instances=[(cell_a, "R103"), (cell_b, "R203")],
        ),
        symbol(
            "SYNTH_NC",
            "U?",
            "hidden-nc",
            55.0,
            10.0,
            "cell:nc",
            instances=[(cell_a, "U102"), (cell_b, "U202")],
        ),
    ])
    sch.wires.extend([
        wire("cell-horizontal", (10.0, 10.0), (25.0, 10.0)),
        wire("cell-t-stub", (15.0, 10.0), (15.0, 15.0)),
    ])
    sch.hierarchical_labels.append(hier_label("CELL_NET", 25.0, 10.0, "cell-net"))
    return sch


def build_offboard_child() -> KiCadSchematic:
    sch = new_schematic("offboard-child")
    off_path = path_for("offboard-direct")
    nested_path = path_for("container", "nested-offboard")
    sch.symbols.append(
        symbol(
            "SYNTH_PASSIVE",
            "R?",
            "offboard-only",
            10.0,
            10.0,
            "offboard:main",
            instances=[(off_path, "R901"), (nested_path, "R902")],
        )
    )
    sch.wires.append(wire("offboard-net", (10.0, 10.0), (25.0, 10.0)))
    sch.hierarchical_labels.append(hier_label("OFF_NET", 25.0, 10.0, "off-net"))
    return sch


def build_container() -> KiCadSchematic:
    sch = new_schematic("container")
    container_path = path_for("container")
    sch.symbols.append(
        symbol(
            "SYNTH_PASSIVE",
            "R?",
            "container-to-nested-offboard",
            10.0,
            20.0,
            "container:main",
            instances=[(container_path, "R301")],
        )
    )
    sch.wires.append(wire("container-offboard", (10.0, 20.0), (25.0, 20.0)))
    sch.sheets.append(
        sheet(
            "offboard_child.kicad_sch",
            "NESTED_OFFBOARD",
            "nested-offboard",
            25.0,
            15.0,
            on_board=False,
            pins=[sheet_pin("OFF_NET", 25.0, 20.0, "nested-offboard")],
            instance_path=path_for("container", "nested-offboard"),
            page="6",
        )
    )
    return sch


def schematic_text(schematic: KiCadSchematic) -> str:
    text = schematic.to_text()
    # The manifest scanner intentionally reads only simple one-line
    # `(version N)` headers. Keep generated fixtures in that canonical shape.
    return text.replace("  (version 20250114\n  )", "  (version 20250114)")


def write_project(root: Path) -> None:
    input_root = root / "input"
    if root.exists():
        shutil.rmtree(root)
    input_root.mkdir(parents=True)

    files = {
        f"{PROJECT_NAME}.kicad_sch": build_root(),
        "reused_cell.kicad_sch": build_reused_cell(),
        "offboard_child.kicad_sch": build_offboard_child(),
        "container.kicad_sch": build_container(),
    }
    for file_name, schematic in files.items():
        (input_root / file_name).write_text(schematic_text(schematic), encoding="utf-8")

    project = {
        "meta": {
            "filename": f"{PROJECT_NAME}.kicad_pro",
            "version": 1,
        },
        "schematic": {
            "subpart_first_id": 65,
            "subpart_id_separator": 0,
        },
        "text_variables": {},
    }
    (input_root / f"{PROJECT_NAME}.kicad_pro").write_text(
        json.dumps(project, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    metadata = {
        "domains": [
            "netlist",
            "netlist_project_corpus",
            "schematic_ir",
            "schematic_svg",
        ],
        "notes": (
            "Synthetic project covering repeated child schematic instances, "
            "sheet-level on_board=no exclusion, nested off-board exclusion, "
            "unmarked wire-endpoint T non-connections, and isolated pin "
            "auto-name parity."
        ),
        "oracle_policy": {
            "netlist": "kicad_cli_live",
            "schematic_ir": "smoke",
            "schematic_svg": "smoke",
        },
        "origin": "synthetic",
        "preferred_project_file": f"{PROJECT_NAME}.kicad_pro",
        "promotion_reason": "Netlist hierarchy edge-case regression fixture.",
        "provenance": {
            "license_usage": "test_fixture",
            "source_kind": "generated_synthetic_project",
            "source_path": "scripts/generate_kicad_synthetic_netlist_fixture.py",
        },
        "status": "active",
        "tags": [
            "synthetic",
            "netlist",
            "hierarchical",
            "reused_sheet_file",
            "sheet_on_board_no",
            "unmarked_wire_t_non_connection",
        ],
    }
    (root / "case_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    write_project(DEFAULT_FIXTURE_ROOT)
    print(f"Wrote {DEFAULT_FIXTURE_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
