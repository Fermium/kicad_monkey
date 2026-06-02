"""PCB SVG enrichment helpers.

This module owns the KiCad-native review SVG metadata contract. The strict
`kicad_cli` renderer profile does not use these helpers.
"""

from __future__ import annotations

from collections.abc import Iterable
import html
import json
from pathlib import Path
from typing import Any

from .kicad_plotter_ir import KiCadPlotterOp, KiCadPlotterRecord


KICAD_PCB_SVG_ENRICHMENT_SCHEMA = "kicad_monkey.pcb.svg.enrichment.a0"
KICAD_PCB_SVG_ENRICHMENT_METADATA_ID = "pcb-enrichment-a0"


_GRAPHIC_KINDS = {
    "gr_line",
    "gr_arc",
    "gr_circle",
    "gr_rect",
    "gr_poly",
    "gr_curve",
}

_PCB_RECORD_KINDS = {
    *_GRAPHIC_KINDS,
    "gr_text",
    "gr_text_box",
    "segment",
    "track_arc",
    "via",
    "zone_fill",
    "footprint",
    "pad_drill_outline",
    "dimension",
    "table",
}


def pcb_layer_role(layer_name: str) -> str:
    """Return a normalized role for a KiCad PCB layer name."""

    layer = str(layer_name or "")
    if layer.endswith(".Cu") or layer == "*.Cu" or layer == "F&B.Cu":
        return "copper"
    if layer.endswith(".SilkS"):
        return "silkscreen"
    if layer.endswith(".Mask") or layer == "*.Mask":
        return "soldermask"
    if layer.endswith(".Paste"):
        return "paste"
    if layer.endswith(".Fab"):
        return "fab"
    if layer.endswith(".Courtyard"):
        return "courtyard"
    if layer == "Edge.Cuts":
        return "board-outline"
    if layer == "DRILLS":
        return "drill"
    if layer.endswith(".User") or layer.startswith("User."):
        return "user"
    return "other"


def _clean_string(value: object) -> str:
    return str(value or "").strip()


def _join_values(values: Iterable[object]) -> str:
    return ",".join(
        value for value in (_clean_string(item) for item in values) if value
    )


def _record_layers(
    record: KiCadPlotterRecord,
    operations: Iterable[KiCadPlotterOp],
) -> list[str]:
    layers: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str) and value and value not in layers:
            layers.append(value)

    extras = record.extras or {}
    add(extras.get("layer"))
    for key in ("layers", "fill_layers"):
        raw = extras.get(key)
        if isinstance(raw, (list, tuple)):
            for item in raw:
                add(item)

    for op in operations:
        payload = op.payload or {}
        add(payload.get("layer"))
        raw_layers = payload.get("layers")
        if isinstance(raw_layers, (list, tuple)):
            for item in raw_layers:
                add(item)

    return layers


def _record_primitive(
    record: KiCadPlotterRecord,
    *,
    data_ref: str | None,
) -> str:
    if data_ref == "drill_overlay":
        if record.kind == "via":
            return "via-hole"
        if record.kind == "pad_drill_outline":
            return "pad-hole"
        return "hole"

    if record.kind == "segment":
        return "track"
    if record.kind == "track_arc":
        return "arc"
    if record.kind == "via":
        return "via"
    if record.kind == "zone_fill":
        return "zone"
    if record.kind == "footprint":
        return "footprint"
    if record.kind == "gr_text":
        return "text"
    if record.kind == "gr_text_box":
        return "text-box"
    if record.kind == "dimension":
        return "dimension"
    if record.kind == "table":
        return "table"
    if record.kind in _GRAPHIC_KINDS:
        return "graphic"
    return record.kind or "record"


def _net_attrs(extras: dict[str, Any]) -> dict[str, object]:
    attrs: dict[str, object] = {}
    net_id = extras.get("net_id")
    net_name = extras.get("net_name")
    if net_id is not None:
        attrs["data-net-index"] = net_id
        attrs["data-net-id"] = net_id
    if net_name:
        attrs["data-net"] = net_name
    net_classes = extras.get("net_classes")
    if isinstance(net_classes, (list, tuple)) and net_classes:
        attrs["data-net-class"] = str(net_classes[0])
        attrs["data-net-classes"] = _join_values(net_classes)
    elif extras.get("net_class"):
        attrs["data-net-class"] = extras["net_class"]
        attrs["data-net-classes"] = extras["net_class"]
    return attrs


def pcb_record_svg_data_attrs(
    record: KiCadPlotterRecord,
    operations: Iterable[KiCadPlotterOp],
    *,
    data_ref: str | None = None,
) -> dict[str, object]:
    """Return public SVG `data-*` attrs for a PCB record group."""

    ops = list(operations)
    extras = record.extras or {}
    primitive = _record_primitive(record, data_ref=data_ref)
    attrs: dict[str, object] = {"data-primitive": primitive}

    if record.uuid:
        attrs["data-element-key"] = record.uuid

    layers = _record_layers(record, ops)
    if len(layers) == 1:
        attrs["data-layer-name"] = layers[0]
        attrs["data-layer-role"] = pcb_layer_role(layers[0])
    elif layers:
        attrs["data-layer-names"] = _join_values(layers)
        attrs["data-layer-roles"] = _join_values(
            sorted({pcb_layer_role(layer) for layer in layers})
        )

    attrs.update(_net_attrs(extras))

    if record.kind == "footprint":
        if extras.get("reference"):
            attrs["data-component"] = extras["reference"]
        if record.uuid:
            attrs["data-component-uid"] = record.uuid
            attrs["data-component-uuid"] = record.uuid
        if extras.get("library_link"):
            attrs["data-footprint"] = extras["library_link"]

    if primitive in {"via", "via-hole"}:
        if record.uuid:
            attrs["data-hole-owner"] = record.uuid
        attrs["data-hole-kind"] = extras.get("via_type", "through")
        attrs["data-hole-plating"] = "plated"
        if primitive == "via-hole":
            attrs["data-hole-render"] = "drill"

    return attrs


def pcb_record_has_svg_data_attrs(record: KiCadPlotterRecord) -> bool:
    """Return True when `record` is a PCB record covered by this contract."""

    return record.kind in _PCB_RECORD_KINDS


def svg_attrs_to_string(attrs: dict[str, object]) -> str | None:
    parts: list[str] = []
    for key, value in attrs.items():
        if value is None or str(value) == "":
            continue
        attr = str(key).strip().replace("_", "-")
        if not attr:
            continue
        if not attr.startswith("data-"):
            attr = f"data-{attr}"
        if not all(ch.isalnum() or ch in "-_:" for ch in attr):
            continue
        parts.append(f'{attr}="{html.escape(str(value), quote=True)}"')
    return " ".join(parts) or None


def project_net_name_to_classes(pcb: Any) -> dict[str, list[str]]:
    project = getattr(pcb, "project", None)
    net_settings = getattr(project, "net_settings", None)
    assignments = getattr(net_settings, "netclass_assignments", None)
    if not isinstance(assignments, dict):
        return {}
    return {
        str(name): [str(item) for item in values if str(item)]
        for name, values in assignments.items()
        if str(name) and isinstance(values, (list, tuple))
    }


def pcb_root_svg_attrs(
    pcb: Any,
    *,
    layers: Iterable[str] | None,
    profile: str,
) -> dict[str, object]:
    source_path = getattr(pcb, "source_path", None)
    included_layers = [str(layer) for layer in layers] if layers is not None else []
    return {
        "data-stage": "review",
        "data-group-mode": "source-record",
        "data-enrichment-schema": KICAD_PCB_SVG_ENRICHMENT_SCHEMA,
        "data-view-kind": "layer_set" if included_layers else "board",
        "data-profile": profile,
        "data-mirror-x": "false",
        "data-source": Path(source_path).name if source_path else "",
        "data-included-layers": _join_values(included_layers),
    }


def _layer_payload(pcb: Any) -> dict[str, Any]:
    layers = list(getattr(pcb, "layers", []) or [])
    names = [str(getattr(layer, "canonical_name", "") or "") for layer in layers]
    ordinals = {
        str(getattr(layer, "ordinal")): str(getattr(layer, "canonical_name", "") or "")
        for layer in layers
        if getattr(layer, "ordinal", None) is not None
    }
    return {
        "all_layer_names": [name for name in names if name],
        "layer_ordinal_to_name": ordinals,
        "layer_name_to_role": {
            name: pcb_layer_role(name) for name in names if name
        },
        "layer_name_to_display_name": {
            str(getattr(layer, "canonical_name", "") or ""): str(
                getattr(layer, "user_name", None)
                or getattr(layer, "canonical_name", "")
                or ""
            )
            for layer in layers
            if getattr(layer, "canonical_name", "")
        },
    }


def _component_parameters(footprint: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for prop in getattr(footprint, "properties", []) or []:
        name = str(getattr(prop, "name", "") or "")
        if not name:
            continue
        out[name] = str(getattr(prop, "value", "") or "")
    return dict(sorted(out.items()))


def _component_payload(footprint: Any, index: int) -> dict[str, Any]:
    get_property = getattr(footprint, "get_property_value", None)
    designator = (
        get_property("Reference", "") if callable(get_property) else ""
    ) or ""
    value = get_property("Value", "") if callable(get_property) else ""
    return {
        "index": int(index),
        "designator": str(designator),
        "unique_id": str(getattr(footprint, "uuid", "") or ""),
        "footprint": str(getattr(footprint, "library_link", "") or ""),
        "value": str(value or ""),
        "description": str(getattr(footprint, "descr", "") or ""),
        "layer": str(getattr(footprint, "layer", "") or ""),
        "x_mm": float(getattr(footprint, "at_x", 0.0) or 0.0),
        "y_mm": float(getattr(footprint, "at_y", 0.0) or 0.0),
        "rotation_deg": float(getattr(footprint, "at_angle", 0.0) or 0.0),
        "parameters": _component_parameters(footprint),
    }


def pcb_svg_enrichment_payload(
    pcb: Any,
    *,
    layers: Iterable[str] | None,
    bbox: Any,
    profile: str,
) -> dict[str, Any]:
    source_path = getattr(pcb, "source_path", None)
    included_layers = [str(layer) for layer in layers] if layers is not None else []
    components = [
        _component_payload(footprint, index)
        for index, footprint in enumerate(getattr(pcb, "footprints", []) or [])
    ]
    net_index_to_name = {
        str(getattr(net, "ordinal")): str(getattr(net, "name", "") or "")
        for net in getattr(pcb, "nets", []) or []
        if getattr(net, "ordinal", None) is not None
    }
    component_index_to_designator = {
        str(component["index"]): component["designator"]
        for component in components
        if component["designator"]
    }
    component_index_to_uid = {
        str(component["index"]): component["unique_id"]
        for component in components
        if component["unique_id"]
    }
    return {
        "schema": KICAD_PCB_SVG_ENRICHMENT_SCHEMA,
        "source": {
            "kicad_pcb_file": str(source_path) if source_path else "",
        },
        "board": {
            "bbox_mm": [
                float(getattr(bbox, "min_x", 0.0)),
                float(getattr(bbox, "min_y", 0.0)),
                float(getattr(bbox, "max_x", 0.0)),
                float(getattr(bbox, "max_y", 0.0)),
            ],
            "aux_axis_origin_mm": list(getattr(pcb, "aux_axis_origin_mm", (0.0, 0.0))),
            "thickness_mm": float(getattr(pcb, "thickness", 0.0) or 0.0),
        },
        "view": {
            "kind": "layer_set" if included_layers else "board",
            "included_layers": included_layers,
            "profile": str(profile),
            "includes_board_outline": (
                not included_layers or "Edge.Cuts" in included_layers
            ),
        },
        "layers": _layer_payload(pcb),
        "lookup": {
            "net_index_to_name": net_index_to_name,
            "net_name_to_classes": project_net_name_to_classes(pcb),
            "component_index_to_designator": component_index_to_designator,
            "component_index_to_uid": component_index_to_uid,
        },
        "components": components,
    }


def pcb_svg_enrichment_metadata_element(payload: dict[str, Any]) -> str:
    body = html.escape(json.dumps(payload, indent=2, sort_keys=True), quote=False)
    return (
        f'<metadata id="{KICAD_PCB_SVG_ENRICHMENT_METADATA_ID}" '
        f'data-schema="{KICAD_PCB_SVG_ENRICHMENT_SCHEMA}">\n'
        f"{body}\n"
        "</metadata>"
    )
