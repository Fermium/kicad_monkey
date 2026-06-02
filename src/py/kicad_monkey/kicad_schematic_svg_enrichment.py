"""Schematic SVG enrichment helpers.

The strict oracle profile suppresses these attributes. The enriched profile
uses them as a DOM lookup surface that lines up with design/netlist JSON.
"""

from __future__ import annotations

from collections.abc import Iterable
import html
import json
from typing import Any

from .kicad_plotter_ir import KiCadPlotterOp, KiCadPlotterRecord


KICAD_SCHEMATIC_SVG_ENRICHMENT_SCHEMA = "kicad_monkey.schematic.svg.enrichment.a0"
KICAD_SCHEMATIC_SVG_ENRICHMENT_METADATA_ID = "schematic-enrichment-a0"

_SCHEMATIC_RECORD_KINDS = {
    "sheet_header",
    "sheet_header_background",
    "wire",
    "bus",
    "bus_entry",
    "junction",
    "no_connect",
    "label",
    "global_label",
    "hierarchical_label",
    "text",
    "text_box",
    "graphic_polyline",
    "graphic_rectangle",
    "graphic_arc",
    "graphic_circle",
    "graphic_bezier",
    "image",
    "symbol_instance",
    "symbol_overplot",
    "sheet",
    "netclass_flag",
    "table",
}


def _clean_string(value: object) -> str:
    return str(value or "").strip()


def _record_primitive(record: KiCadPlotterRecord) -> str:
    extras = record.extras or {}
    if record.kind == "symbol_instance":
        if _is_power_symbol(record):
            return "power-symbol"
        return "symbol"
    if record.kind == "symbol_overplot":
        return "symbol-overplot"
    if record.kind == "sheet":
        return "sheet-symbol"
    if record.kind == "hierarchical_label":
        return "port"
    if record.kind == "global_label":
        return "global-label"
    if record.kind == "label":
        return "label"
    if record.kind == "bus_entry":
        return "bus-entry"
    if record.kind == "no_connect":
        return "no-connect"
    if record.kind == "netclass_flag":
        return "netclass-flag"
    if record.kind.startswith("graphic_"):
        return "graphic"
    if record.kind == "sheet_header_background":
        return "drawing-sheet-background"
    if record.kind == "sheet_header":
        return "drawing-sheet"
    if record.kind == "text_box":
        return "text-box"
    return _clean_string(extras.get("primitive")) or record.kind or "record"


def _is_power_symbol(record: KiCadPlotterRecord) -> bool:
    extras = record.extras or {}
    reference = _clean_string(extras.get("reference"))
    lib_id = _clean_string(extras.get("lib_id")).lower()
    return reference.startswith("#") or lib_id.startswith("power:")


def _shape_attrs(attrs: dict[str, object], extras: dict[str, Any]) -> None:
    shape = extras.get("shape")
    if shape is not None and str(shape) != "":
        attrs["data-shape"] = shape


def _text_attrs(attrs: dict[str, object], extras: dict[str, Any]) -> None:
    text = extras.get("text")
    if text is not None and str(text) != "":
        attrs["data-text"] = text


def _symbol_attrs(attrs: dict[str, object], record: KiCadPlotterRecord) -> None:
    extras = record.extras or {}
    reference = _clean_string(extras.get("reference"))
    if reference:
        attrs["data-component"] = reference
        attrs["data-designator"] = reference
    if record.uuid:
        attrs["data-component-uid"] = record.uuid
        attrs["data-component-uuid"] = record.uuid
    if extras.get("lib_id"):
        attrs["data-symbol-library-ref"] = extras["lib_id"]
    if extras.get("lib_name"):
        attrs["data-symbol-library-name"] = extras["lib_name"]
    if extras.get("unit") is not None:
        attrs["data-symbol-unit"] = extras["unit"]
    if extras.get("convert") is not None:
        attrs["data-symbol-convert"] = extras["convert"]
    attrs["data-symbol-role"] = "power" if _is_power_symbol(record) else "component"
    for key in (
        "in_bom",
        "on_board",
        "dnp",
        "exclude_from_sim",
        "in_pos_files",
    ):
        if key in extras:
            attrs[f"data-{key.replace('_', '-')}"] = str(bool(extras[key])).lower()


def _sheet_attrs(attrs: dict[str, object], extras: dict[str, Any]) -> None:
    if extras.get("sheet_name"):
        attrs["data-sheet-name"] = extras["sheet_name"]
    if extras.get("sheet_file"):
        attrs["data-sheet-file"] = extras["sheet_file"]
    for key in ("at_x_nm", "at_y_nm", "size_x_nm", "size_y_nm"):
        if extras.get(key) is not None:
            attrs[f"data-{key.replace('_', '-')}"] = extras[key]


def _record_layer_attrs(
    attrs: dict[str, object],
    operations: Iterable[KiCadPlotterOp],
) -> None:
    layers: list[str] = []
    for op in operations:
        payload = op.payload or {}
        layer = payload.get("layer")
        if isinstance(layer, str) and layer and layer not in layers:
            layers.append(layer)
    if len(layers) == 1:
        attrs["data-layer-name"] = layers[0]
    elif layers:
        attrs["data-layer-names"] = ",".join(layers)


def schematic_record_svg_data_attrs(
    record: KiCadPlotterRecord,
    operations: Iterable[KiCadPlotterOp],
) -> dict[str, object]:
    """Return public SVG `data-*` attrs for a schematic record group."""

    ops = list(operations)
    extras = record.extras or {}
    primitive = _record_primitive(record)
    attrs: dict[str, object] = {
        "data-primitive": primitive,
        "data-source-kind": "schematic",
    }
    if record.uuid:
        attrs["data-element-key"] = record.uuid

    _record_layer_attrs(attrs, ops)

    if record.kind in {"label", "global_label", "hierarchical_label", "text", "text_box"}:
        _text_attrs(attrs, extras)
        _shape_attrs(attrs, extras)
    elif record.kind in {"symbol_instance", "symbol_overplot"}:
        _symbol_attrs(attrs, record)
    elif record.kind == "sheet":
        _sheet_attrs(attrs, extras)
    elif record.kind == "netclass_flag":
        _shape_attrs(attrs, extras)

    return attrs


def schematic_record_has_svg_data_attrs(record: KiCadPlotterRecord) -> bool:
    """Return True when `record` is covered by the schematic SVG contract."""

    return record.kind in _SCHEMATIC_RECORD_KINDS


def schematic_svg_enrichment_payload(
    design_payload: dict[str, Any],
    *,
    source_path: object = "",
    sheet_name: object = "",
    sheet_path: object = "",
    sheet_instance_path: object = "",
    profile: object = "enriched",
) -> dict[str, Any]:
    """Return document-level metadata embedded in enriched schematic SVG."""

    return {
        "schema": KICAD_SCHEMATIC_SVG_ENRICHMENT_SCHEMA,
        "source": {
            "kicad_sch_file": str(source_path or ""),
        },
        "view": {
            "kind": "schematic_sheet",
            "profile": str(profile),
            "sheet_name": str(sheet_name or ""),
            "sheet_path": str(sheet_path or ""),
            "sheet_instance_path": str(sheet_instance_path or ""),
        },
        "design": design_payload,
    }


def schematic_root_svg_attrs(
    *,
    source_path: object = "",
    sheet_name: object = "",
    sheet_path: object = "",
    profile: object = "enriched",
) -> dict[str, object]:
    """Return root SVG attributes for enriched schematic output."""

    return {
        "data-enrichment-schema": KICAD_SCHEMATIC_SVG_ENRICHMENT_SCHEMA,
        "data-view-kind": "schematic_sheet",
        "data-profile": str(profile),
        "data-source": str(source_path or ""),
        "data-sheet-name": str(sheet_name or ""),
        "data-sheet-path": str(sheet_path or ""),
    }


def schematic_svg_enrichment_metadata_element(payload: dict[str, Any]) -> str:
    body = html.escape(json.dumps(payload, indent=2, sort_keys=True), quote=False)
    return (
        f'<metadata id="{KICAD_SCHEMATIC_SVG_ENRICHMENT_METADATA_ID}" '
        f'data-schema="{KICAD_SCHEMATIC_SVG_ENRICHMENT_SCHEMA}">\n'
        f"{body}\n"
        "</metadata>"
    )
