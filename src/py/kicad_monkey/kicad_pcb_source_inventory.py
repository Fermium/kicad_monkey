"""KiCad PCB source-inventory report.

Produces a programmatic dict describing what the parser actually consumed from a
``.kicad_pcb`` (and, when adjacent, the ``.kicad_pro`` sidecar).

Contract: see ``AGENT_KICAD_VIZ_DATA_MODEL_BULLETIN.md`` (3d-viz-rework /
kicad_monkey v1.1 ratchet hand-off, 2026-05-17T14:33 entry).

Source-side only. Classifies elements as:

* ``unknown``       parser saw an S-expression family it doesn't know.
* ``unprocessed``   parser typed the object, but no downstream generic mapping
                    consumes it yet.
* ``ignored``       known editor-only / session / UI data intentionally ignored.
* ``passthrough``   known raw or partially parsed source data preserved for
                    possible re-emission / debug.

Downstream classifications (``mapped``, ``derived``, ``unsupported_expected``)
are intentionally NOT computed here; that's the job of data_models comparing
this inventory to the v1.1 object map.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .kicad_pcb import KiCadPcb
    from .kicad_pcb_footprint import Footprint
    from .kicad_pcb_other import UnknownElement


INVENTORY_TYPE = "kicad.pcb.source_inventory"
INVENTORY_VERSION = "a0"

VALID_DETAIL = ("summary", "objects", "debug")


def _parser_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("kicad-monkey")
    except Exception:
        return None


def _raw_excerpt(raw_sexp: Any, *, limit: int = 200) -> str:
    """Return a short single-line string excerpt of an S-expression node."""
    try:
        text = repr(raw_sexp)
    except Exception:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 1] + "\u2026"
    return text


def _source_ref(
    *,
    source_kind: str,
    scope: str,
    owner_path: str,
    source_index: int,
    token_path: list[Any],
    line: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    return {
        "source_cad": "kicad",
        "source_kind": source_kind,
        "scope": scope,
        "owner_path": owner_path,
        "source_index": source_index,
        "token_path": list(token_path),
        "line": line,
        "column": column,
    }


def _detail_row(
    *,
    source_ref: dict[str, Any],
    classification: str,
    reason: str,
    fallback_action: str,
    raw_head: str,
    raw_excerpt: str = "",
    notes: str = "",
) -> dict[str, Any]:
    return {
        "source_ref": source_ref,
        "classification": classification,
        "reason": reason,
        "fallback_action": fallback_action,
        "raw_head": raw_head,
        "raw_excerpt": raw_excerpt,
        "notes": notes,
    }


# Family registry: (family_id, scope, source_kind, parser_class, attr, parse_status, notes).
# ``attr`` is read off KiCadPcb for board-scope families. Footprint sub-families
# are aggregated separately.
_BOARD_FAMILIES: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("board.layer",            "board", "layer",           "Layer",          "layers",          "parsed", ""),
    ("board.net",              "board", "net",             "Net",            "nets",            "parsed", ""),
    ("board.property",         "board", "property",        "BoardProperty",  "properties",      "parsed", ""),
    ("board.variant",          "board", "variant",         "BoardVariant",   "variants",        "parsed", ""),
    ("board.gr_text",          "board", "gr_text",         "GrText",         "gr_texts",        "parsed", ""),
    ("board.gr_line",          "board", "gr_line",         "GrLine",         "gr_lines",        "parsed", ""),
    ("board.gr_rect",          "board", "gr_rect",         "GrRect",         "gr_rects",        "parsed", ""),
    ("board.gr_arc",           "board", "gr_arc",          "GrArc",          "gr_arcs",         "parsed", ""),
    ("board.gr_circle",        "board", "gr_circle",       "GrCircle",       "gr_circles",      "parsed", ""),
    ("board.gr_poly",          "board", "gr_poly",         "GrPoly",         "gr_polys",        "parsed", ""),
    ("board.gr_curve",         "board", "gr_curve",        "GrCurve",        "gr_curves",       "parsed", ""),
    ("board.gr_text_box",      "board", "gr_text_box",     "GrTextBox",      "gr_text_boxes",   "parsed", ""),
    ("board.image",            "board", "image",           "Image",          "images",          "parsed", ""),
    ("board.barcode",          "board", "barcode",         "Barcode",        "barcodes",        "parsed", ""),
    ("board.table",            "board", "table",           "Table",          "tables",          "parsed", ""),
    ("board.footprint",        "board", "footprint",       "Footprint",      "footprints",      "parsed", ""),
    ("board.zone",             "board", "zone",            "Zone",           "zones",           "parsed", ""),
    ("board.dimension",        "board", "dimension",       "Dimension",      "dimensions",      "parsed", ""),
    ("board.segment",          "board", "segment",         "Segment",        "segments",        "parsed", ""),
    ("board.via",              "board", "via",             "Via",            "vias",            "parsed", ""),
    ("board.arc",              "board", "arc",             "Arc",            "arcs",            "parsed", ""),
    ("board.group",            "board", "group",           "Group",          "groups",          "parsed", ""),
    ("board.generated",        "board", "generated",       "GeneratedObject","generated_items", "parsed", ""),
    ("board.embedded_file",    "board", "file",            "EmbeddedFile",   "embedded_files",  "parsed", ""),
)

# Footprint sub-family registry: (family_id, source_kind, parser_class, attr).
_FOOTPRINT_SUB_FAMILIES: tuple[tuple[str, str, str, str], ...] = (
    ("footprint.pad",          "pad",          "Pad",        "pads"),
    ("footprint.property",     "property",     "Property",   "properties"),
    ("footprint.fp_line",      "fp_line",      "FpLine",     "fp_lines"),
    ("footprint.fp_arc",       "fp_arc",       "GrArc",      "fp_arcs"),
    ("footprint.fp_circle",    "fp_circle",    "GrCircle",   "fp_circles"),
    ("footprint.fp_rect",      "fp_rect",      "GrRect",     "fp_rects"),
    ("footprint.fp_poly",      "fp_poly",      "FpPoly",     "fp_polys"),
    ("footprint.fp_text",      "fp_text",      "FpText",     "fp_texts"),
    ("footprint.fp_text_box",  "fp_text_box",  "GrTextBox",  "fp_text_boxes"),
    ("footprint.image",        "image",        "Image",      "images"),
    ("footprint.barcode",      "barcode",      "Barcode",    "barcodes"),
    ("footprint.table",        "table",        "Table",      "tables"),
    ("footprint.dimension",    "dimension",    "Dimension",  "dimensions"),
    ("footprint.zone",         "zone",         "Zone",       "zones"),
    ("footprint.group",        "group",        "Group",      "groups"),
    ("footprint.model",        "model",        "Model",      "models"),
    ("footprint.embedded_file","file",         "EmbeddedFile","embedded_files"),
)


def _count_attr(obj: Any, attr: str) -> int:
    value = getattr(obj, attr, None)
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 0


def _board_outline_carrier_count(pcb: "KiCadPcb") -> int:
    try:
        return len(pcb.board_outline_carriers())
    except Exception:
        return 0


def _net_class_count(pcb: "KiCadPcb") -> int:
    project = getattr(pcb, "project", None)
    if project is None:
        return 0
    net_settings = getattr(project, "net_settings", None)
    if net_settings is None:
        return 0
    classes = getattr(net_settings, "classes", None) or []
    return len(classes)


def _iter_footprint_unknown(
    pcb: "KiCadPcb",
) -> Iterable[tuple[int, "Footprint", "UnknownElement"]]:
    for fp_index, footprint in enumerate(pcb.footprints or []):
        for unknown in getattr(footprint, "unknown_elements", []) or []:
            yield fp_index, footprint, unknown


def _setup_passthrough_entry(pcb: "KiCadPcb", *, include_excerpt: bool) -> dict[str, Any] | None:
    setup_sexp = getattr(pcb, "setup_sexp", None)
    if not setup_sexp:
        return None
    return _detail_row(
        source_ref=_source_ref(
            source_kind="setup",
            scope="setup",
            owner_path="board",
            source_index=0,
            token_path=["kicad_pcb", "setup"],
        ),
        classification="passthrough",
        reason="preserved_raw",
        fallback_action="passthrough",
        raw_head="setup",
        raw_excerpt=_raw_excerpt(setup_sexp) if include_excerpt else "",
        notes="setup section preserved verbatim for round-trip; not decomposed into typed members yet",
    )


def _unknown_entry_board(
    unknown: "UnknownElement",
    *,
    index: int,
    include_excerpt: bool,
) -> dict[str, Any]:
    name = str(getattr(unknown, "name", "") or "")
    return _detail_row(
        source_ref=_source_ref(
            source_kind=name or "unknown",
            scope="board",
            owner_path="board",
            source_index=index,
            token_path=["kicad_pcb", name],
        ),
        classification="unknown",
        reason="unknown_head",
        fallback_action="passthrough",
        raw_head=name,
        raw_excerpt=_raw_excerpt(getattr(unknown, "raw_sexp", None)) if include_excerpt else "",
        notes="",
    )


def _unknown_entry_footprint(
    unknown: "UnknownElement",
    *,
    fp_index: int,
    footprint: "Footprint",
    index: int,
    include_excerpt: bool,
) -> dict[str, Any]:
    name = str(getattr(unknown, "name", "") or "")
    library_link = str(getattr(footprint, "library_link", "") or "")
    return _detail_row(
        source_ref=_source_ref(
            source_kind=name or "unknown",
            scope="footprint",
            owner_path=f"footprints[{fp_index}]",
            source_index=index,
            token_path=["kicad_pcb", "footprint", library_link, name],
        ),
        classification="unknown",
        reason="unknown_head",
        fallback_action="passthrough",
        raw_head=name,
        raw_excerpt=_raw_excerpt(getattr(unknown, "raw_sexp", None)) if include_excerpt else "",
        notes=f"library_link={library_link!r}" if library_link else "",
    )


def build_pcb_source_inventory(
    pcb: "KiCadPcb",
    *,
    detail: str = "summary",
) -> dict[str, Any]:
    """Build a ``kicad.pcb.source_inventory`` dict for ``pcb``.

    ``detail`` controls how much per-object information is emitted:

    * ``"summary"`` (default): counts, families, and any unknown / ignored /
      passthrough detail rows that exist (with empty ``raw_excerpt``).
    * ``"objects"``: same as summary, with raw excerpts on detail rows.
    * ``"debug"``: same as ``"objects"`` for now; reserved for richer
      per-object dumps as the contract evolves.
    """
    if detail not in VALID_DETAIL:
        raise ValueError(f"detail must be one of {VALID_DETAIL}, got {detail!r}")
    include_excerpt = detail in ("objects", "debug")

    source_path = getattr(pcb, "source_path", None)
    source_path_str: str | None
    if isinstance(source_path, Path):
        source_path_str = str(source_path)
    elif source_path is None:
        source_path_str = None
    else:
        source_path_str = str(source_path)

    # ---- per-family parsed counts on the board ----------------------------
    family_rows: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    for family_id, scope, source_kind, parser_class, attr, status, notes in _BOARD_FAMILIES:
        count = _count_attr(pcb, attr)
        family_counts[attr] = count
        family_rows.append(
            {
                "family_id": family_id,
                "scope": scope,
                "source_kind": source_kind,
                "parser_class": parser_class,
                "count": count,
                "parse_status": status,
                "notes": notes,
            }
        )

    # ---- footprint sub-family counts (aggregated across all footprints) --
    fp_sub_counts: dict[str, int] = {attr: 0 for _, _, _, attr in _FOOTPRINT_SUB_FAMILIES}
    for footprint in pcb.footprints or []:
        for _, _, _, attr in _FOOTPRINT_SUB_FAMILIES:
            fp_sub_counts[attr] += _count_attr(footprint, attr)
    for family_id, source_kind, parser_class, attr in _FOOTPRINT_SUB_FAMILIES:
        family_rows.append(
            {
                "family_id": family_id,
                "scope": "footprint",
                "source_kind": source_kind,
                "parser_class": parser_class,
                "count": fp_sub_counts[attr],
                "parse_status": "parsed",
                "notes": "aggregated across all footprints",
            }
        )

    # ---- setup (passthrough) family row ----------------------------------
    has_setup = bool(getattr(pcb, "setup_sexp", None))
    family_rows.append(
        {
            "family_id": "board.setup",
            "scope": "setup",
            "source_kind": "setup",
            "parser_class": "raw_sexp",
            "count": 1 if has_setup else 0,
            "parse_status": "passthrough",
            "notes": "preserved verbatim; not decomposed into typed members yet",
        }
    )

    # ---- project sidecar family rows --------------------------------------
    project = getattr(pcb, "project", None)
    net_class_count = _net_class_count(pcb)
    family_rows.append(
        {
            "family_id": "project.net_class",
            "scope": "project",
            "source_kind": "net_class",
            "parser_class": "KiCadProjectNetClass",
            "count": net_class_count,
            "parse_status": "parsed" if project is not None else "absent",
            "notes": "sourced from adjacent .kicad_pro net_settings.classes[]",
        }
    )

    # ---- detail rows -------------------------------------------------------
    unknown_elements_out: list[dict[str, Any]] = []
    unprocessed_elements_out: list[dict[str, Any]] = []
    ignored_elements_out: list[dict[str, Any]] = []
    passthrough_elements_out: list[dict[str, Any]] = []

    for index, unknown in enumerate(getattr(pcb, "unknown_elements", []) or []):
        unknown_elements_out.append(
            _unknown_entry_board(unknown, index=index, include_excerpt=include_excerpt)
        )

    fp_unknown_index = 0
    for fp_index, footprint, unknown in _iter_footprint_unknown(pcb):
        unknown_elements_out.append(
            _unknown_entry_footprint(
                unknown,
                fp_index=fp_index,
                footprint=footprint,
                index=fp_unknown_index,
                include_excerpt=include_excerpt,
            )
        )
        fp_unknown_index += 1

    setup_row = _setup_passthrough_entry(pcb, include_excerpt=include_excerpt)
    if setup_row is not None:
        passthrough_elements_out.append(setup_row)

    # ---- counts block -----------------------------------------------------
    counts = {
        "layers": family_counts.get("layers", 0),
        "nets": family_counts.get("nets", 0),
        "net_classes": net_class_count,
        "segments": family_counts.get("segments", 0),
        "track_arcs": family_counts.get("arcs", 0),
        "vias": family_counts.get("vias", 0),
        "zones": family_counts.get("zones", 0),
        "footprints": family_counts.get("footprints", 0),
        "footprint_pads": fp_sub_counts.get("pads", 0),
        "footprint_graphics": (
            fp_sub_counts.get("fp_lines", 0)
            + fp_sub_counts.get("fp_arcs", 0)
            + fp_sub_counts.get("fp_circles", 0)
            + fp_sub_counts.get("fp_rects", 0)
            + fp_sub_counts.get("fp_polys", 0)
        ),
        "footprint_text": fp_sub_counts.get("fp_texts", 0) + fp_sub_counts.get("fp_text_boxes", 0),
        "footprint_models": fp_sub_counts.get("models", 0),
        "board_graphics": (
            family_counts.get("gr_lines", 0)
            + family_counts.get("gr_arcs", 0)
            + family_counts.get("gr_circles", 0)
            + family_counts.get("gr_rects", 0)
            + family_counts.get("gr_polys", 0)
            + family_counts.get("gr_curves", 0)
        ),
        "board_text": family_counts.get("gr_texts", 0) + family_counts.get("gr_text_boxes", 0),
        "board_outline_carriers": _board_outline_carrier_count(pcb),
        "dimensions": family_counts.get("dimensions", 0),
        "images": family_counts.get("images", 0),
        "barcodes": family_counts.get("barcodes", 0),
        "tables": family_counts.get("tables", 0),
        "groups": family_counts.get("groups", 0),
        "embedded_files": family_counts.get("embedded_files", 0),
        "unknown_elements": len(unknown_elements_out),
        "unprocessed_elements": len(unprocessed_elements_out),
        "ignored_elements": len(ignored_elements_out),
        "passthrough_elements": len(passthrough_elements_out),
    }

    inventory: dict[str, Any] = {
        "type": INVENTORY_TYPE,
        "version": INVENTORY_VERSION,
        "source_backend": "kicad_pcb",
        "source_format": "kicad_pcb_s_expr",
        "source_path": source_path_str,
        "parser": {
            "package": "kicad_monkey",
            "version": _parser_version(),
        },
        "counts": counts,
        "families": family_rows,
        "unknown_elements": unknown_elements_out,
        "unprocessed_elements": unprocessed_elements_out,
        "ignored_elements": ignored_elements_out,
        "passthrough_elements": passthrough_elements_out,
    }
    return inventory


__all__ = [
    "INVENTORY_TYPE",
    "INVENTORY_VERSION",
    "VALID_DETAIL",
    "build_pcb_source_inventory",
]
