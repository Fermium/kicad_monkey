"""
IR-backed KiCad schematic SVG rendering entry points.

The public schematic SVG surface now follows the same shape as the board
and footprint renderers: parser model -> plotter IR -> SVG renderer.  This
module keeps the historical ``render_schematic_svg`` import path available
as a compatibility wrapper, but it no longer contains a direct schematic
renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from .kicad_sch_svg_renderer import KiCadSvgRenderContext, KiCadSvgRenderOptions

if TYPE_CHECKING:
    from .kicad_plotter_ir import KiCadPlotterDocument, KiCadPlotterOp, KiCadPlotterRecord
    from .kicad_schematic import KiCadSchematic


@dataclass
class SchematicTheme:
    """Compatibility theme for schematic SVG output."""

    black_and_white: bool = False
    background_color: str | None = "#FFFFFF"
    color_overrides: dict[str, str] | None = None


SchematicSvgContext = KiCadSvgRenderContext


@dataclass
class SchematicRenderOptions:
    """Compatibility options for schematic SVG output."""

    margin: float = 5.0
    include_page_border: bool = True
    include_title_block: bool = True
    include_background: bool = True
    text_as_polygons: bool = False


def _source_path_text(schematic: "KiCadSchematic", source_path: str | Path | None) -> str | None:
    if source_path is not None:
        return str(source_path)
    parsed_source = getattr(schematic, "source_path", None)
    return str(parsed_source) if parsed_source is not None else None


def _document_id(schematic: "KiCadSchematic", document_id: str | None, source_path: str | None) -> str | None:
    if document_id is not None:
        return document_id
    uuid = getattr(schematic, "uuid", "")
    if uuid:
        return str(uuid)
    if source_path:
        return Path(source_path).stem
    return None


def _sheet_name(sheet_name: str, source_path: str | None) -> str:
    if sheet_name:
        return sheet_name
    if source_path:
        return Path(source_path).stem
    return ""


def _op_kind(op: "KiCadPlotterOp") -> str:
    kind = op.kind
    value = getattr(kind, "value", None)
    return str(value) if value is not None else str(kind)


def _is_sheet_background_op(op: "KiCadPlotterOp", doc: "KiCadPlotterDocument") -> bool:
    if _op_kind(op) != "rect":
        return False
    payload = op.payload or {}
    raw_fill = payload.get("fill", "") or ""
    fill_value = getattr(raw_fill, "value", None)
    fill = str(fill_value) if fill_value is not None else str(raw_fill)
    if fill not in {"filled", "background"}:
        return False
    canvas = doc.canvas or {}
    try:
        width = int(canvas.get("width_nm", 0) or 0)
        height = int(canvas.get("height_nm", 0) or 0)
        x1 = int(payload.get("x1", 0) or 0)
        y1 = int(payload.get("y1", 0) or 0)
        x2 = int(payload.get("x2", 0) or 0)
        y2 = int(payload.get("y2", 0) or 0)
    except (TypeError, ValueError):
        return False
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    return left == 0 and top == 0 and right == width and bottom == height


def _filter_records_for_options(
    doc: "KiCadPlotterDocument",
    options: SchematicRenderOptions,
) -> "KiCadPlotterDocument":
    records: list["KiCadPlotterRecord"] = []
    changed = False
    for record in doc.records:
        if record.kind != "sheet_header":
            records.append(record)
            continue
        if not options.include_page_border:
            changed = True
            continue
        if options.include_background:
            records.append(record)
            continue
        ops = [op for op in record.operations if not _is_sheet_background_op(op, doc)]
        if len(ops) != len(record.operations):
            changed = True
            record = replace(record, operations=ops)
        records.append(record)
    return replace(doc, records=records) if changed else doc


def _svg_options_from_compat(
    theme: SchematicTheme,
    options: SchematicRenderOptions,
) -> KiCadSvgRenderOptions:
    return KiCadSvgRenderOptions(
        black_and_white=theme.black_and_white,
        background_color=theme.background_color if options.include_background else None,
        color_overrides=theme.color_overrides,
        text_as_polygons=options.text_as_polygons,
    )


def render_schematic_svg(
    schematic: "KiCadSchematic",
    theme: SchematicTheme | None = None,
    options: SchematicRenderOptions | None = None,
    *,
    source_path: str | Path | None = None,
    document_id: str | None = None,
    sheet_index: int = 1,
    sheet_count: int = 1,
    sheet_path: str = "/",
    sheet_instance_path: str | None = None,
    sheet_name: str = "",
    project_vars: dict | None = None,
    render_options: KiCadSvgRenderOptions | None = None,
) -> str:
    """Render a KiCad schematic to SVG through the plotter-IR pipeline."""

    from .kicad_ir_to_svg import render_ir_to_svg
    from .kicad_schematic_to_ir import schematic_to_ir

    compat_theme = theme if theme is not None else SchematicTheme()
    compat_options = options if options is not None else SchematicRenderOptions()
    resolved_source = _source_path_text(schematic, source_path)

    doc = schematic_to_ir(
        schematic,
        source_path=resolved_source,
        document_id=_document_id(schematic, document_id, resolved_source),
        sheet_index=sheet_index,
        sheet_count=sheet_count,
        sheet_path=sheet_path,
        sheet_instance_path=sheet_instance_path,
        sheet_name=_sheet_name(sheet_name, resolved_source),
        project_vars=project_vars,
    )
    doc = _filter_records_for_options(doc, compat_options)
    svg_options = render_options or _svg_options_from_compat(compat_theme, compat_options)
    return render_ir_to_svg(doc, options=svg_options)


def render_schematic_to_file(
    schematic: "KiCadSchematic",
    output_path: Path,
    theme: SchematicTheme | None = None,
    options: SchematicRenderOptions | None = None,
    **kwargs,
) -> None:
    """Render a schematic to an SVG file."""

    svg = render_schematic_svg(schematic, theme=theme, options=options, **kwargs)
    Path(output_path).write_text(svg, encoding="utf-8")


__all__ = [
    "SchematicRenderOptions",
    "SchematicSvgContext",
    "SchematicTheme",
    "render_schematic_svg",
    "render_schematic_to_file",
]
