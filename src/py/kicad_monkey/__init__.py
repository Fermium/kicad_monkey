"""
KiCad File Format Module

Parsers, filters, extractors, and utilities for KiCad files
(.kicad_pcb, .kicad_sch, .kicad_sym, .kicad_mod, .kicad_wks, etc.).

The library exposes two complementary tracks:

OOP track — typed dataclasses for callers that need to read geometry
or topology (e.g. layout-to-neutral-model converters, SVG render):

    >>> from kicad_monkey import KiCadPcb
    >>> pcb = KiCadPcb.from_file("board.kicad_pcb")
    >>> pcb.footprints[0].reference
    >>> pcb.to_file("output.kicad_pcb")

    >>> from kicad_monkey import KiCadFootprint, KiCadSchematic, KiCadSymbolLib
    >>> sch = KiCadSchematic.from_file("design.kicad_sch")
    >>> lib = KiCadSymbolLib.from_file("library.kicad_sym")
    >>> fp  = KiCadFootprint.from_file("resistor.kicad_mod")

S-Expression track — parse → mutate → re-emit for filter / extract
use cases that don't need the typed model. Round-trip is byte-stable
on the upstream-QA corpus, so pass-through is a first-class fallback
for unknown / uninteresting children:

    >>> from kicad_monkey import parse_sexp, format_sexp
    >>> from kicad_monkey import find_element, find_all_elements, get_value
    >>> sexp = parse_sexp(open("board.kicad_pcb").read())
    >>> for fp_sexp in find_all_elements(sexp, "footprint"):
    ...     ref = get_value(find_element(fp_sexp, "property"), "Reference")

File-level filters compose well with the s-expression track:

    >>> from kicad_monkey import KiCadFilterPipeline
    >>> KiCadFilterPipeline().filter_footprint(in_path, out_path)

Or call individual filter functions directly on a parsed s-expression:

    >>> from kicad_monkey import sym_filter__clear_property_values
    >>> filtered = sym_filter__clear_property_values(parse_sexp(text))

Extractors pull embedded artifacts out without loading the full OOP
model:

    >>> from kicad_monkey import (
    ...     extract_footprints_from_pcb,
    ...     extract_symbols_from_text,
    ...     extract_step_from_footprint,
    ... )

Project Utilities:
    >>> from kicad_monkey import read_kicad_pro_parameters
    >>> params = read_kicad_pro_parameters("project.kicad_pro")

Symbol Library Operations (class methods):
    >>> lib = KiCadSymbolLib.from_directory('symbols/', recursive=True)
    >>> lib.to_file('merged.kicad_sym')
    >>> lib.split_to_directory('output/')

The two extractor modules ``kicad_symbol_extractor`` and
``kicad_sch_extractor`` both define a function called
``extract_symbols_from_schematic`` with different return contracts
(parsed-sexpr-tuples vs. write-to-disk). Import them via the explicit
module path when you need a specific one:

    >>> from kicad_monkey.kicad_symbol_extractor import extract_symbols_from_schematic
    >>> from kicad_monkey.kicad_sch_extractor   import extract_symbols_from_schematic

NOTE: Heavy modules (parsers, filters, extractors, geometry utilities)
are lazy-loaded on first access to keep import times fast. The
s-expression parser and read helpers are always available.
"""

from __future__ import annotations

from typing import Any

from ._version import Version, __version__, parse_version, version

# Self-contained S-expression parser (no external dependencies)
from .kicad_sexpr import (
    PARSER_DIALECT_EXCEPTIONS,
    ParserDialectException,
    QuotedString,
    SexpRoundtripResult,
    SexpSpan,
    SexprBuilder,
    SexprDialectError,
    SexprError,
    SexprItem,
    SexprLexError,
    SexprTreeError,
    build_sexp,
    debug_dump_tokens,
    format_sexp,
    parse_sexp,
    parse_sexp_with_spans,
    roundtrip_sexp_text,
    string_to_sexp,
    validate_bare_string,
)

__all__ = [
    # Package metadata
    "__version__",
    "Version",
    "parse_version",
    "version",
    # S-expression parsing
    "parse_sexp",
    "build_sexp",
    "format_sexp",
    "SexprItem",
    "string_to_sexp",
    "validate_bare_string",
    "QuotedString",
    "SexprError",
    "SexprLexError",
    "SexprTreeError",
    "SexprDialectError",
    "SexprBuilder",
    "SexpRoundtripResult",
    "roundtrip_sexp_text",
    "PARSER_DIALECT_EXCEPTIONS",
    "ParserDialectException",
    "SexpSpan",
    "parse_sexp_with_spans",
    "debug_dump_tokens",
    # S-expression read helpers (kicad_base — lazy loaded)
    "find_element",
    "find_all_elements",
    "get_value",
    "get_values",
    "has_flag",
    "parse_maybe_absent_bool",
    "unquote_string",
    # S-expression mutation primitives (kicad_base — lazy loaded)
    "replace_element",
    "remove_element",
    "remove_all_elements",
    "set_value",
    "walk",
    "find_path",
    "transform_descendants",
    # Environment and filter framework entry points (lazy loaded)
    "KiCadEnvironment",
    "KiCadFilterPipeline",
    "KiCadNameIndex",
    # Filter framework — formatting helpers (lazy loaded)
    "format_kicad_sexp",
    # Filter framework — individual filters (lazy loaded)
    "fp_filter__add_fab_bounding_orthogonal_convex",
    "fp_filter__clean_fab",
    "fp_filter__clean_layers",
    "fp_filter__fix_fp_text_font_to_arial",
    "fp_filter__fix_zero_sized_pads",
    "fp_filter__normalized_embedded_model_naming",
    "fp_filter__orthographic_projection_outline",
    "pcb_filter__process_embedded_footprints",
    "pcb_filter__reset_layer_user_names",
    "sch_filter__remove_altium_value_property",
    "sym_filter__clear_property_values",
    "sym_filter__remove_nonstandard_properties",
    "sym_filter__standardize_reference_value_fonts",
    # Extractors — footprint (lazy loaded)
    "extract_footprints_from_text",
    "extract_footprints_from_pcb",
    "extract_footprints_from_project",
    # Extractors — symbol (lazy loaded; parses sexpr)
    "extract_symbols_from_text",
    "create_symbol_file_content",
    # Extractors — schematic file-level (lazy loaded; writes files)
    "list_symbols_in_schematic",
    # Extractors — STEP (lazy loaded)
    "find_embedded_step_data",
    "extract_step_from_text",
    "extract_step_from_footprint",
    "extract_step_from_directory",
    "view_step_file",
    # New OOP model - PCB (lazy loaded)
    "KiCadPcb",
    "from_kicad_pcb",
    "to_kicad_pcb",
    # New OOP model - Footprint (lazy loaded)
    "KiCadFootprint",
    "from_kicad_mod",
    "to_kicad_mod",
    # New OOP model - Symbol Library (lazy loaded)
    "KiCadSymbolLib",
    "LibSymbol",
    "LibSubSymbol",
    "SymProperty",
    "SymPin",
    "SymRectangle",
    "SymCircle",
    "SymArc",
    "SymPolyline",
    "SymBezier",
    "SymText",
    "SymTextBox",
    "SymFill",
    "SymFillType",
    "KiCadObjectCollection",
    # Shared KiCad defaults (lazy loaded)
    "KICAD_DEFAULT_BOARD_THICKNESS_MM",
    "KICAD_DEFAULT_PAPER",
    "KICAD_DEFAULT_PIN_NAME_OFFSET_MM",
    "KICAD_DEFAULT_SHEET_HEIGHT_MM",
    "KICAD_DEFAULT_SHEET_WIDTH_MM",
    "KICAD_DEFAULT_TEXT_SIZE_MM",
    "KICAD_FOOTPRINT_FILE_VERSION",
    "KICAD_FOOTPRINT_GENERATOR",
    "KICAD_GENERATOR_VERSION",
    "KICAD_PCB_FILE_VERSION",
    "KICAD_PCB_GENERATOR",
    "KICAD_SCHEMATIC_FILE_VERSION",
    "KICAD_SCHEMATIC_GENERATOR",
    "KICAD_SYMBOL_LIB_FILE_VERSION",
    "KICAD_SYMBOL_LIB_GENERATOR",
    # Shared primitives (lazy loaded)
    "Stroke",
    "Font",
    "Effects",
    "Justify",
    "RenderCacheContour",
    "RenderCachePolygon",
    "RenderCache",
    "RenderCacheRequest",
    "RenderCacheResolver",
    "RenderCacheResult",
    "RenderCacheSource",
    "RenderCacheValidation",
    "board_text_variables",
    "ensure_render_cache",
    "footprint_text_variables",
    "generate_render_cache_from_text_params",
    "render_cache_exterior_polygons",
    "render_cache_request_for_board_text",
    "render_cache_request_for_dimension_text",
    "render_cache_request_for_footprint_property",
    "render_cache_request_for_footprint_text",
    "render_cache_request_for_footprint_text_box",
    "render_cache_request_for_table_cell",
    "substitute_text_variables",
    "table_cell_text_variables",
    "KiCadRenderCacheOracleError",
    "RenderCacheComparison",
    "RenderCacheCoverageObject",
    "RenderCacheCoverageSummary",
    "RenderCacheEntrySetComparison",
    "RenderCacheOracleEntry",
    "RenderCacheOracleResult",
    "build_render_cache_coverage_report",
    "build_render_cache_coverage_report_from_pcb",
    "collect_render_cache_requests_from_pcb",
    "compare_render_cache_entries",
    "compare_render_cache_entry_sets",
    "compare_render_caches",
    "extract_render_cache_entries_from_pcb",
    "render_cache_coverage_markdown",
    "run_kicad_pcb_render_cache_save_oracle",
    "summarize_render_cache_entries",
    "summarize_render_cache_requests",
    "strip_render_cache_blocks",
    "strip_render_cache_blocks_from_sexp",
    "write_render_cache_coverage_report",
    # Schematic enums (lazy loaded)
    "PinElectricalType",
    "PinGraphicStyle",
    "LabelShape",
    "StandardPropertyKey",
    "StandardSheetPropertyKey",
    "PropertyId",
    # New OOP model - Schematic Document (lazy loaded)
    "KiCadSchematic",
    "SchSymbol",
    "SchWire",
    "SchBus",
    "SchBusEntry",
    "SchJunction",
    "SchNoConnect",
    "SchLabel",
    "SchGlobalLabel",
    "SchHierarchicalLabel",
    "SchSheet",
    "SchTextBox",
    "TitleBlock",
    "PaperSize",
    # New OOP model - Worksheet (lazy loaded)
    "KiCadWorksheet",
    "WksSetup",
    "WksLine",
    "WksRect",
    "WksPolygon",
    "WksTbText",
    "WksBitmap",
    "WksCorner",
    "WksPoint",
    # OOP element classes (lazy loaded)
    "Footprint",
    "Pad",
    "FpText",
    "FpTextBox",
    "FpLine",
    "FpPoly",
    "Zone",
    "Segment",
    "Via",
    "Arc",
    "GrText",
    "GrLine",
    "GrRect",
    "GrArc",
    "GrCircle",
    "GrPoly",
    "GrCurve",
    "GrTextBox",
    "Layer",
    "Net",
    "NetRef",
    "OutlineCarrier",
    "BarcodeMargins",
    "Barcode",
    "DrillLayerSpan",
    "DrillProps",
    "PostMachiningProps",
    "ZoneLayerConnections",
    "PadNameGroup",
    "BoardVariant",
    "FootprintVariantField",
    "FootprintVariant",
    "FootprintPlacement",
    "ComponentClassRef",
    "GeneratedProperty",
    "GeneratedObject",
    "KiCadProject",
    "KiCadProjectBoardDesignSettings",
    "KiCadProjectDiffPairDimensions",
    "KiCadProjectNetClass",
    "KiCadProjectNetClassPattern",
    "KiCadProjectNetSettings",
    "KiCadProjectSidecar",
    "KiCadProjectTuningPatternDefaults",
    "KiCadProjectTuningPatternSettings",
    "ProjectVariant",
    "find_adjacent_kicad_project_path",
    # Variant model (lazy loaded)
    "AssemblyComponent",
    "EffectiveFootprintProperties",
    "EffectiveSymbolProperties",
    "VariantCatalog",
    "VariantOverride",
    "assemble",
    "collect_footprint_overrides",
    "collect_symbol_overrides",
    "resolve_footprint",
    "resolve_symbol",
    # Geometry utilities (lazy loaded)
    "BoundingBox",
    "SvgRenderContext",
    "rotate_point",
    # Symbol SVG rendering (lazy loaded)
    "SymbolTheme",
    "SymbolSvgContext",
    "SymbolRenderOptions",
    "render_symbol_svg",
    "render_library_svg",
    # Schematic SVG rendering (lazy loaded)
    "SchematicTheme",
    "SchematicSvgContext",
    "SchematicRenderOptions",
    "render_schematic_svg",
    "render_schematic_to_file",
    # Project utilities (lazy loaded)
    "read_kicad_pro_parameters",
    "make_kicad_httplib",
    "setup_kicad_preferences",
    # Plotter IR (lazy loaded)
    "KICAD_PLOTTER_IR_SCHEMA",
    "KiCadFillType",
    "KiCadHorizAlign",
    "KiCadLineStyle",
    "KiCadPenAction",
    "KiCadPlotterBounds",
    "KiCadPlotterDocument",
    "KiCadPlotterOp",
    "KiCadPlotterOpKind",
    "KiCadPlotterRecord",
    "KiCadVertAlign",
    "make_brush",
    "make_font",
    "make_pen",
    "styled_plotter_op",
    # SVG primitive layer (lazy loaded)
    "KiCadJunctionZOrder",
    "KiCadSvgRenderContext",
    "KiCadSvgRenderOptions",
    "KiCadVariantDimMode",
    "fmt_user_number",
    "svg_arc",
    "svg_bezier",
    "svg_circle",
    "svg_document",
    "svg_ellipse",
    "svg_group",
    "svg_line",
    "svg_path",
    "svg_polygon",
    "svg_polyline",
    "svg_rect",
    "svg_text",
    "svg_text_or_poly",
    "svg_text_poly",
    "KiCadSvgPreferenceTheme",
    "load_kicad_svg_preference_theme",
    "schematic_svg_options_from_preferences",
    "symbol_theme_from_preferences",
    # LibSymbol → IR converter (lazy loaded)
    "arc_to_op",
    "bezier_to_op",
    "circle_to_op",
    "lib_symbol_to_ir",
    "mm_to_nm",
    "pin_to_ops",
    "polyline_to_op",
    "rectangle_to_op",
    "rgba_to_hex",
    "stroke_type_to_line_style",
    "stroke_width_nm",
    "subsymbol_to_record",
    "sym_fill_to_kicad_fill",
    "text_to_op",
    "y_to_ir",
    # Schematic → IR converter (lazy loaded)
    "DEFAULT_BUS_WIDTH_MM",
    "DEFAULT_JUNCTION_DIAMETER_MM",
    "DEFAULT_LABEL_SIZE_RATIO",
    "DEFAULT_NO_CONNECT_HALF_MM",
    "DEFAULT_TEXT_SIZE_MM",
    "DEFAULT_WIRE_WIDTH_MM",
    "bus_entry_to_op",
    "bus_to_op",
    "global_label_decoration_to_op",
    "global_label_to_op",
    "hierarchical_label_decoration_to_op",
    "hierarchical_label_to_op",
    "junction_to_op",
    "label_to_op",
    "no_connect_to_ops",
    "paper_size_to_nm",
    "sch_text_to_op",
    "schematic_arc_to_ops",
    "schematic_bezier_to_ops",
    "schematic_circle_to_ops",
    "schematic_image_to_op",
    "schematic_polyline_to_ops",
    "schematic_rectangle_to_ops",
    "schematic_to_ir",
    "sheet_background_to_op",
    "sheet_outline_to_op",
    "sheet_pin_decoration_to_op",
    "sheet_pin_to_op",
    "sheet_property_to_op",
    "symbol_property_to_op",
    "text_box_outline_to_op",
    "text_box_to_ops",
    "wire_to_op",
    # IR → SVG renderer (lazy loaded)
    "render_ir_to_svg",
    "render_op",
    "render_record",
    "render_records",
    # Recorder JSON loader (lazy loaded)
    "KICAD_PLOTTER_RECORDER_SCHEMA",
    "load_recorder_dict",
    "load_recorder_file",
    "normalise_recorder_op_units",
    "translate_recorder_canvas",
    "translate_recorder_op",
    # Recorder drift report (lazy loaded)
    "KICAD_RECORDER_DRIFT_SCHEMA",
    "RecorderDriftReport",
    "compute_recorder_drift",
    # Stroked-text fold (lazy loaded)
    "STROKED_TEXT_FOLD_KIND",
    "STROKED_TEXT_FOLD_MIN_POINTS",
    "STROKED_TEXT_FOLD_MIN_RUN",
    "fold_recorder_document",
    "fold_stroked_text_runs",
    "is_stroked_text_glyph",
    # Op-by-op equivalence diff (lazy loaded)
    "KICAD_OP_EQUIVALENCE_SCHEMA",
    "MATCH_STRATEGY_BY_KIND",
    "MATCH_STRATEGY_POSITIONAL",
    "MATCH_STRATEGY_WINDOWED_BY_KIND",
    "MATCH_WINDOW_UNBOUNDED",
    "KiCadOpDivergence",
    "OpEquivalenceReport",
    "compute_op_equivalence",
    # Plotter-IR coordinate transform (lazy loaded)
    "KiCadPlotterTransform2D",
    "apply_transform_to_op",
    "apply_transform_to_ops",
    "transform_orient",
    "transform_point",
    # Drawing sheet emitter (lazy loaded)
    "DEFAULT_KICAD_WKS",
    "drawing_sheet_to_ops",
    "expand_format_codes",
    "load_default_drawing_sheet",
    # Design aggregator (lazy loaded)
    "KiCadDesign",
    # Footprint → IR converter (lazy loaded)
    "footprint_to_ir",
    "footprint_to_record",
    "fp_arc_to_op",
    "fp_circle_to_op",
    "fp_fill_to_kicad_fill",
    "fp_line_to_op",
    "fp_poly_to_op",
    "fp_rect_to_op",
    "fp_text_box_to_ops",
    "fp_text_to_op",
    "pad_drill_to_ops",
    "pad_to_ops",
    "property_to_op",
    # Variant overlay (lazy loaded)
    "KiCadVariantOverlayPolicy",
    "VARIANT_STATE_ACTIVE",
    "VARIANT_STATE_DIMMED",
    "VARIANT_STATE_KEY",
    "annotate_record_variant_state",
    "apply_variant_overlay",
    "compute_record_variant_state",
    # PCB → IR converter (lazy loaded)
    "pcb_to_ir",
    "gr_line_to_op",
    "gr_line_to_record",
    "gr_arc_to_op",
    "gr_arc_to_record",
    "gr_circle_to_op",
    "gr_circle_to_record",
    "gr_rect_to_op",
    "gr_rect_to_record",
    "gr_poly_to_op",
    "gr_poly_to_record",
    "gr_curve_to_op",
    "gr_curve_to_record",
    "gr_text_to_op",
    "gr_text_to_record",
    "gr_text_box_to_ops",
    "gr_text_box_to_record",
    "track_segment_to_op",
    "track_segment_to_record",
    "track_arc_to_op",
    "track_arc_to_record",
    "via_drill_to_op",
    "via_to_op",
    "via_to_record",
    "zone_filled_polygon_to_op",
    "zone_to_record",
    "pcb_footprint_to_record",
    # PCB IR → SVG wrapper (lazy loaded)
    "render_pcb_ir_to_svg",
    # Schematic connectivity primitives (lazy loaded)
    "SCH_IU_PER_MM",
    "snap_mm_to_iu",
    "iu_key_to_mm",
    "compute_pin_position",
    "iter_symbol_pins",
    "CoordinateIndex",
    "ConnectivityGraph",
    "detect_no_connects",
    # Bus label expansion (lazy loaded)
    "is_bus_label",
    "parse_bus_vector",
    "parse_bus_group",
    "expand_bus_label",
    # Netlist model + single-sheet compiler (lazy loaded)
    "KiCadDriverPriority",
    "KiCadDriverKind",
    "KiCadPinType",
    "KiCadNetlistTerminal",
    "KiCadNetEndpoint",
    "KiCadNet",
    "KiCadNetlistComponent",
    "KiCadLibPart",
    "KiCadLibPartPin",
    "KiCadDesignSheet",
    "KiCadDesignMetadata",
    "KiCadNetlist",
    "Subgraph",
    "compile_sheet_subgraphs",
    "compile_sheet_netlist",
    "name_net",
    # Multi-sheet netlist compile (lazy loaded)
    "CompiledSheet",
    "compile_design_subgraphs",
    "merge_design_nets",
    "compile_design_netlist",
    "collect_design_components",
    "collect_design_libparts",
    # KiCad-format netlist emit (lazy loaded)
    "KICAD_NETLIST_VERSION",
    "to_kicad_sexpr",
    # Generic netlist_a0 bridge (lazy loaded)
    "kicad_netlist_to_data_models_netlist",
]


def __getattr__(name: str) -> Any:
    """Lazy import for modules with external dependencies."""
    # New OOP PCB Model
    if name in ("KiCadPcb", "from_kicad_pcb", "to_kicad_pcb"):
        from .kicad_pcb import KiCadPcb, from_kicad_pcb, to_kicad_pcb
        return {"KiCadPcb": KiCadPcb,
                "from_kicad_pcb": from_kicad_pcb,
                "to_kicad_pcb": to_kicad_pcb}[name]
    # New OOP Footprint Model
    if name in ("KiCadFootprint", "from_kicad_mod", "to_kicad_mod"):
        from .kicad_footprint import KiCadFootprint, from_kicad_mod, to_kicad_mod
        return {"KiCadFootprint": KiCadFootprint,
                "from_kicad_mod": from_kicad_mod,
                "to_kicad_mod": to_kicad_mod}[name]
    # New OOP Symbol Library Model
    if name == "KiCadSymbolLib":
        from .kicad_symbol_lib import KiCadSymbolLib
        return KiCadSymbolLib
    if name in ("LibSymbol", "LibSubSymbol"):
        from .kicad_lib_symbol import LibSymbol
        from .kicad_lib_subsymbol import LibSubSymbol
        return {"LibSymbol": LibSymbol, "LibSubSymbol": LibSubSymbol}[name]
    if name == "SymProperty":
        from .kicad_sym_property import SymProperty
        return SymProperty
    if name == "SymPin":
        from .kicad_sym_pin import SymPin
        return SymPin
    if name in ("SymRectangle", "SymFill", "SymFillType"):
        from .kicad_sym_rectangle import SymRectangle, SymFill, SymFillType
        return {"SymRectangle": SymRectangle, "SymFill": SymFill, "SymFillType": SymFillType}[name]
    if name == "KiCadObjectCollection":
        from .kicad_object_collection import KiCadObjectCollection
        return KiCadObjectCollection
    if name in (
        "KICAD_DEFAULT_BOARD_THICKNESS_MM",
        "KICAD_DEFAULT_PAPER",
        "KICAD_DEFAULT_PIN_NAME_OFFSET_MM",
        "KICAD_DEFAULT_SHEET_HEIGHT_MM",
        "KICAD_DEFAULT_SHEET_WIDTH_MM",
        "KICAD_DEFAULT_TEXT_SIZE_MM",
        "KICAD_FOOTPRINT_FILE_VERSION",
        "KICAD_FOOTPRINT_GENERATOR",
        "KICAD_GENERATOR_VERSION",
        "KICAD_PCB_FILE_VERSION",
        "KICAD_PCB_GENERATOR",
        "KICAD_SCHEMATIC_FILE_VERSION",
        "KICAD_SCHEMATIC_GENERATOR",
        "KICAD_SYMBOL_LIB_FILE_VERSION",
        "KICAD_SYMBOL_LIB_GENERATOR",
    ):
        from .kicad_defaults import (
            KICAD_DEFAULT_BOARD_THICKNESS_MM,
            KICAD_DEFAULT_PAPER,
            KICAD_DEFAULT_PIN_NAME_OFFSET_MM,
            KICAD_DEFAULT_SHEET_HEIGHT_MM,
            KICAD_DEFAULT_SHEET_WIDTH_MM,
            KICAD_DEFAULT_TEXT_SIZE_MM,
            KICAD_FOOTPRINT_FILE_VERSION,
            KICAD_FOOTPRINT_GENERATOR,
            KICAD_GENERATOR_VERSION,
            KICAD_PCB_FILE_VERSION,
            KICAD_PCB_GENERATOR,
            KICAD_SCHEMATIC_FILE_VERSION,
            KICAD_SCHEMATIC_GENERATOR,
            KICAD_SYMBOL_LIB_FILE_VERSION,
            KICAD_SYMBOL_LIB_GENERATOR,
        )
        return {
            "KICAD_DEFAULT_BOARD_THICKNESS_MM": KICAD_DEFAULT_BOARD_THICKNESS_MM,
            "KICAD_DEFAULT_PAPER": KICAD_DEFAULT_PAPER,
            "KICAD_DEFAULT_PIN_NAME_OFFSET_MM": KICAD_DEFAULT_PIN_NAME_OFFSET_MM,
            "KICAD_DEFAULT_SHEET_HEIGHT_MM": KICAD_DEFAULT_SHEET_HEIGHT_MM,
            "KICAD_DEFAULT_SHEET_WIDTH_MM": KICAD_DEFAULT_SHEET_WIDTH_MM,
            "KICAD_DEFAULT_TEXT_SIZE_MM": KICAD_DEFAULT_TEXT_SIZE_MM,
            "KICAD_FOOTPRINT_FILE_VERSION": KICAD_FOOTPRINT_FILE_VERSION,
            "KICAD_FOOTPRINT_GENERATOR": KICAD_FOOTPRINT_GENERATOR,
            "KICAD_GENERATOR_VERSION": KICAD_GENERATOR_VERSION,
            "KICAD_PCB_FILE_VERSION": KICAD_PCB_FILE_VERSION,
            "KICAD_PCB_GENERATOR": KICAD_PCB_GENERATOR,
            "KICAD_SCHEMATIC_FILE_VERSION": KICAD_SCHEMATIC_FILE_VERSION,
            "KICAD_SCHEMATIC_GENERATOR": KICAD_SCHEMATIC_GENERATOR,
            "KICAD_SYMBOL_LIB_FILE_VERSION": KICAD_SYMBOL_LIB_FILE_VERSION,
            "KICAD_SYMBOL_LIB_GENERATOR": KICAD_SYMBOL_LIB_GENERATOR,
        }[name]
    if name == "SymCircle":
        from .kicad_sym_circle import SymCircle
        return SymCircle
    if name == "SymArc":
        from .kicad_sym_arc import SymArc
        return SymArc
    if name == "SymPolyline":
        from .kicad_sym_polyline import SymPolyline
        return SymPolyline
    if name == "SymBezier":
        from .kicad_sym_bezier import SymBezier
        return SymBezier
    if name == "SymText":
        from .kicad_sym_text import SymText
        return SymText
    if name == "SymTextBox":
        from .kicad_sym_text_box import SymTextBox
        return SymTextBox
    # Shared primitives
    if name in (
        "Stroke",
        "Font",
        "Effects",
        "Justify",
        "RenderCacheContour",
        "RenderCachePolygon",
        "RenderCache",
    ):
        from .kicad_primitives import (
            Effects,
            Font,
            Justify,
            RenderCache,
            RenderCacheContour,
            RenderCachePolygon,
            Stroke,
        )
        return {
            "Stroke": Stroke,
            "Font": Font,
            "Effects": Effects,
            "Justify": Justify,
            "RenderCacheContour": RenderCacheContour,
            "RenderCachePolygon": RenderCachePolygon,
            "RenderCache": RenderCache,
        }[name]
    if name in (
        "RenderCacheRequest",
        "RenderCacheResolver",
        "RenderCacheResult",
        "RenderCacheSource",
        "RenderCacheValidation",
        "board_text_variables",
        "ensure_render_cache",
        "footprint_text_variables",
        "generate_render_cache_from_text_params",
        "render_cache_exterior_polygons",
        "render_cache_request_for_board_text",
        "render_cache_request_for_dimension_text",
        "render_cache_request_for_footprint_property",
        "render_cache_request_for_footprint_text",
        "render_cache_request_for_footprint_text_box",
        "render_cache_request_for_table_cell",
        "substitute_text_variables",
        "table_cell_text_variables",
    ):
        from .kicad_render_cache import (
            RenderCacheRequest,
            RenderCacheResolver,
            RenderCacheResult,
            RenderCacheSource,
            RenderCacheValidation,
            board_text_variables,
            ensure_render_cache,
            footprint_text_variables,
            generate_render_cache_from_text_params,
            render_cache_exterior_polygons,
            render_cache_request_for_board_text,
            render_cache_request_for_dimension_text,
            render_cache_request_for_footprint_property,
            render_cache_request_for_footprint_text,
            render_cache_request_for_footprint_text_box,
            render_cache_request_for_table_cell,
            substitute_text_variables,
            table_cell_text_variables,
        )
        return {
            "RenderCacheRequest": RenderCacheRequest,
            "RenderCacheResolver": RenderCacheResolver,
            "RenderCacheResult": RenderCacheResult,
            "RenderCacheSource": RenderCacheSource,
            "RenderCacheValidation": RenderCacheValidation,
            "board_text_variables": board_text_variables,
            "ensure_render_cache": ensure_render_cache,
            "footprint_text_variables": footprint_text_variables,
            "generate_render_cache_from_text_params": generate_render_cache_from_text_params,
            "render_cache_exterior_polygons": render_cache_exterior_polygons,
            "render_cache_request_for_board_text": render_cache_request_for_board_text,
            "render_cache_request_for_dimension_text": render_cache_request_for_dimension_text,
            "render_cache_request_for_footprint_property": render_cache_request_for_footprint_property,
            "render_cache_request_for_footprint_text": render_cache_request_for_footprint_text,
            "render_cache_request_for_footprint_text_box": render_cache_request_for_footprint_text_box,
            "render_cache_request_for_table_cell": render_cache_request_for_table_cell,
            "substitute_text_variables": substitute_text_variables,
            "table_cell_text_variables": table_cell_text_variables,
        }[name]
    if name in (
        "KiCadRenderCacheOracleError",
        "RenderCacheComparison",
        "RenderCacheCoverageObject",
        "RenderCacheCoverageSummary",
        "RenderCacheEntrySetComparison",
        "RenderCacheOracleEntry",
        "RenderCacheOracleResult",
        "build_render_cache_coverage_report",
        "build_render_cache_coverage_report_from_pcb",
        "collect_render_cache_requests_from_pcb",
        "compare_render_cache_entries",
        "compare_render_cache_entry_sets",
        "compare_render_caches",
        "extract_render_cache_entries_from_pcb",
        "render_cache_coverage_markdown",
        "run_kicad_pcb_render_cache_save_oracle",
        "summarize_render_cache_entries",
        "summarize_render_cache_requests",
        "strip_render_cache_blocks",
        "strip_render_cache_blocks_from_sexp",
        "write_render_cache_coverage_report",
    ):
        from .kicad_render_cache_oracle import (
            KiCadRenderCacheOracleError,
            RenderCacheComparison,
            RenderCacheCoverageObject,
            RenderCacheCoverageSummary,
            RenderCacheEntrySetComparison,
            RenderCacheOracleEntry,
            RenderCacheOracleResult,
            build_render_cache_coverage_report,
            build_render_cache_coverage_report_from_pcb,
            collect_render_cache_requests_from_pcb,
            compare_render_cache_entries,
            compare_render_cache_entry_sets,
            compare_render_caches,
            extract_render_cache_entries_from_pcb,
            render_cache_coverage_markdown,
            run_kicad_pcb_render_cache_save_oracle,
            summarize_render_cache_entries,
            summarize_render_cache_requests,
            strip_render_cache_blocks,
            strip_render_cache_blocks_from_sexp,
            write_render_cache_coverage_report,
        )
        return {
            "KiCadRenderCacheOracleError": KiCadRenderCacheOracleError,
            "RenderCacheComparison": RenderCacheComparison,
            "RenderCacheCoverageObject": RenderCacheCoverageObject,
            "RenderCacheCoverageSummary": RenderCacheCoverageSummary,
            "RenderCacheEntrySetComparison": RenderCacheEntrySetComparison,
            "RenderCacheOracleEntry": RenderCacheOracleEntry,
            "RenderCacheOracleResult": RenderCacheOracleResult,
            "build_render_cache_coverage_report": build_render_cache_coverage_report,
            "build_render_cache_coverage_report_from_pcb": build_render_cache_coverage_report_from_pcb,
            "collect_render_cache_requests_from_pcb": collect_render_cache_requests_from_pcb,
            "compare_render_cache_entries": compare_render_cache_entries,
            "compare_render_cache_entry_sets": compare_render_cache_entry_sets,
            "compare_render_caches": compare_render_caches,
            "extract_render_cache_entries_from_pcb": extract_render_cache_entries_from_pcb,
            "render_cache_coverage_markdown": render_cache_coverage_markdown,
            "run_kicad_pcb_render_cache_save_oracle": run_kicad_pcb_render_cache_save_oracle,
            "summarize_render_cache_entries": summarize_render_cache_entries,
            "summarize_render_cache_requests": summarize_render_cache_requests,
            "strip_render_cache_blocks": strip_render_cache_blocks,
            "strip_render_cache_blocks_from_sexp": strip_render_cache_blocks_from_sexp,
            "write_render_cache_coverage_report": write_render_cache_coverage_report,
        }[name]
    if name in (
        "KiCadProject",
        "KiCadProjectBoardDesignSettings",
        "KiCadProjectDiffPairDimensions",
        "KiCadProjectNetClass",
        "KiCadProjectNetClassPattern",
        "KiCadProjectNetSettings",
        "KiCadProjectSidecar",
        "KiCadProjectTuningPatternDefaults",
        "KiCadProjectTuningPatternSettings",
        "ProjectVariant",
        "find_adjacent_kicad_project_path",
    ):
        from .kicad_project import (
            KiCadProject,
            KiCadProjectBoardDesignSettings,
            KiCadProjectDiffPairDimensions,
            KiCadProjectNetClass,
            KiCadProjectNetClassPattern,
            KiCadProjectNetSettings,
            KiCadProjectSidecar,
            KiCadProjectTuningPatternDefaults,
            KiCadProjectTuningPatternSettings,
            ProjectVariant,
            find_adjacent_kicad_project_path,
        )
        return {
            "KiCadProject": KiCadProject,
            "KiCadProjectBoardDesignSettings": KiCadProjectBoardDesignSettings,
            "KiCadProjectDiffPairDimensions": KiCadProjectDiffPairDimensions,
            "KiCadProjectNetClass": KiCadProjectNetClass,
            "KiCadProjectNetClassPattern": KiCadProjectNetClassPattern,
            "KiCadProjectNetSettings": KiCadProjectNetSettings,
            "KiCadProjectSidecar": KiCadProjectSidecar,
            "KiCadProjectTuningPatternDefaults": KiCadProjectTuningPatternDefaults,
            "KiCadProjectTuningPatternSettings": KiCadProjectTuningPatternSettings,
            "ProjectVariant": ProjectVariant,
            "find_adjacent_kicad_project_path": find_adjacent_kicad_project_path,
        }[name]
    if name in (
        "AssemblyComponent",
        "EffectiveFootprintProperties", "EffectiveSymbolProperties",
        "VariantCatalog", "VariantOverride",
        "assemble",
        "collect_footprint_overrides", "collect_symbol_overrides",
        "resolve_footprint", "resolve_symbol",
    ):
        from .kicad_variants import (
            AssemblyComponent,
            EffectiveFootprintProperties, EffectiveSymbolProperties,
            VariantCatalog, VariantOverride,
            assemble,
            collect_footprint_overrides, collect_symbol_overrides,
            resolve_footprint, resolve_symbol,
        )
        return {
            "AssemblyComponent": AssemblyComponent,
            "EffectiveFootprintProperties": EffectiveFootprintProperties,
            "EffectiveSymbolProperties": EffectiveSymbolProperties,
            "VariantCatalog": VariantCatalog,
            "VariantOverride": VariantOverride,
            "assemble": assemble,
            "collect_footprint_overrides": collect_footprint_overrides,
            "collect_symbol_overrides": collect_symbol_overrides,
            "resolve_footprint": resolve_footprint,
            "resolve_symbol": resolve_symbol,
        }[name]
    # Schematic enums
    if name in (
        "PinElectricalType",
        "PinGraphicStyle",
        "LabelShape",
        "StandardPropertyKey",
        "StandardSheetPropertyKey",
        "PropertyId",
    ):
        from .kicad_sch_enums import (
            LabelShape,
            PinElectricalType,
            PinGraphicStyle,
            PropertyId,
            StandardPropertyKey,
            StandardSheetPropertyKey,
        )
        return {
            "PinElectricalType": PinElectricalType,
            "PinGraphicStyle": PinGraphicStyle,
            "LabelShape": LabelShape,
            "StandardPropertyKey": StandardPropertyKey,
            "StandardSheetPropertyKey": StandardSheetPropertyKey,
            "PropertyId": PropertyId,
        }[name]
    # New OOP Schematic Document Model
    if name == "KiCadSchematic":
        from .kicad_schematic import KiCadSchematic
        return KiCadSchematic
    if name == "SchSymbol":
        from .kicad_sch_symbol import SchSymbol
        return SchSymbol
    if name in ("SchWire", "SchBus", "SchBusEntry"):
        from .kicad_sch_wire import SchWire, SchBus, SchBusEntry
        return {"SchWire": SchWire, "SchBus": SchBus, "SchBusEntry": SchBusEntry}[name]
    if name == "SchJunction":
        from .kicad_sch_junction import SchJunction
        return SchJunction
    if name == "SchNoConnect":
        from .kicad_sch_no_connect import SchNoConnect
        return SchNoConnect
    if name in ("SchLabel", "SchGlobalLabel", "SchHierarchicalLabel"):
        from .kicad_sch_label import SchLabel, SchGlobalLabel, SchHierarchicalLabel
        return {"SchLabel": SchLabel, "SchGlobalLabel": SchGlobalLabel,
                "SchHierarchicalLabel": SchHierarchicalLabel}[name]
    if name == "SchSheet":
        from .kicad_sch_sheet import SchSheet
        return SchSheet
    if name == "SchTextBox":
        from .kicad_sch_text_box import SchTextBox
        return SchTextBox
    if name in ("TitleBlock", "PaperSize"):
        from .kicad_sch_title_block import TitleBlock, PaperSize
        return {"TitleBlock": TitleBlock, "PaperSize": PaperSize}[name]
    # New OOP Worksheet Model
    if name == "KiCadWorksheet":
        from .kicad_worksheet import KiCadWorksheet
        return KiCadWorksheet
    if name in ("WksSetup", "WksCorner", "WksPoint"):
        from .kicad_wks_primitives import WksSetup, WksCorner, WksPoint
        return {"WksSetup": WksSetup, "WksCorner": WksCorner, "WksPoint": WksPoint}[name]
    if name == "WksLine":
        from .kicad_wks_line import WksLine
        return WksLine
    if name == "WksRect":
        from .kicad_wks_rect import WksRect
        return WksRect
    if name == "WksPolygon":
        from .kicad_wks_polygon import WksPolygon
        return WksPolygon
    if name == "WksTbText":
        from .kicad_wks_text import WksTbText
        return WksTbText
    if name == "WksBitmap":
        from .kicad_wks_bitmap import WksBitmap
        return WksBitmap
    # OOP Element classes
    if name in ("Footprint", "Pad", "FpText", "FpTextBox", "FpLine", "FpPoly"):
        from .kicad_pcb_footprint import Footprint, Pad, FpText, FpTextBox, FpLine, FpPoly
        return {"Footprint": Footprint, "Pad": Pad, "FpText": FpText,
                "FpTextBox": FpTextBox, "FpLine": FpLine, "FpPoly": FpPoly}[name]
    if name in ("Zone",):
        from .kicad_pcb_zone import Zone
        return Zone
    if name in ("Segment", "Via", "Arc"):
        from .kicad_pcb_routing import Segment, Via, Arc
        return {"Segment": Segment, "Via": Via, "Arc": Arc}[name]
    if name in ("GrText", "GrLine", "GrRect", "GrArc", "GrCircle", "GrPoly", "GrCurve", "GrTextBox"):
        from .kicad_pcb_graphics import GrText, GrLine, GrRect, GrArc, GrCircle, GrPoly, GrCurve, GrTextBox
        return {"GrText": GrText, "GrLine": GrLine, "GrRect": GrRect,
                "GrArc": GrArc, "GrCircle": GrCircle, "GrPoly": GrPoly,
                "GrCurve": GrCurve, "GrTextBox": GrTextBox}[name]
    if name in (
        "Layer",
        "Net",
        "NetRef",
        "OutlineCarrier",
        "BarcodeMargins",
        "Barcode",
        "DrillLayerSpan",
        "DrillProps",
        "PostMachiningProps",
        "ZoneLayerConnections",
        "PadNameGroup",
        "BoardVariant",
        "FootprintVariantField",
        "FootprintVariant",
        "FootprintPlacement",
        "ComponentClassRef",
        "GeneratedProperty",
        "GeneratedObject",
    ):
        from .kicad_pcb_other import (
            Barcode,
            BarcodeMargins,
            BoardVariant,
            ComponentClassRef,
            DrillLayerSpan,
            DrillProps,
            FootprintPlacement,
            FootprintVariant,
            FootprintVariantField,
            GeneratedObject,
            GeneratedProperty,
            Layer,
            Net,
            NetRef,
            OutlineCarrier,
            PadNameGroup,
            PostMachiningProps,
            ZoneLayerConnections,
        )
        return {
            "Layer": Layer,
            "Net": Net,
            "NetRef": NetRef,
            "OutlineCarrier": OutlineCarrier,
            "BarcodeMargins": BarcodeMargins,
            "Barcode": Barcode,
            "DrillLayerSpan": DrillLayerSpan,
            "DrillProps": DrillProps,
            "PostMachiningProps": PostMachiningProps,
            "ZoneLayerConnections": ZoneLayerConnections,
            "PadNameGroup": PadNameGroup,
            "BoardVariant": BoardVariant,
            "FootprintVariantField": FootprintVariantField,
            "FootprintVariant": FootprintVariant,
            "FootprintPlacement": FootprintPlacement,
            "ComponentClassRef": ComponentClassRef,
            "GeneratedProperty": GeneratedProperty,
            "GeneratedObject": GeneratedObject,
        }[name]
    # Geometry utilities
    if name in ("BoundingBox", "SvgRenderContext", "rotate_point"):
        from .kicad_geometry import BoundingBox, SvgRenderContext, rotate_point
        return {"BoundingBox": BoundingBox, "SvgRenderContext": SvgRenderContext,
                "rotate_point": rotate_point}[name]
    # Symbol SVG rendering
    if name in ("SymbolTheme", "SymbolSvgContext", "SymbolRenderOptions", "render_symbol_svg", "render_library_svg"):
        from .kicad_symbol_svg import (
            SymbolTheme,
            SymbolSvgContext,
            SymbolRenderOptions,
            render_symbol_svg,
            render_library_svg,
        )
        return {
            "SymbolTheme": SymbolTheme,
            "SymbolSvgContext": SymbolSvgContext,
            "SymbolRenderOptions": SymbolRenderOptions,
            "render_symbol_svg": render_symbol_svg,
            "render_library_svg": render_library_svg,
        }[name]
    # Schematic SVG rendering
    if name in ("SchematicTheme", "SchematicSvgContext", "SchematicRenderOptions", "render_schematic_svg", "render_schematic_to_file"):
        from .kicad_sch_svg import (
            SchematicTheme,
            SchematicSvgContext,
            SchematicRenderOptions,
            render_schematic_svg,
            render_schematic_to_file,
        )
        return {
            "SchematicTheme": SchematicTheme,
            "SchematicSvgContext": SchematicSvgContext,
            "SchematicRenderOptions": SchematicRenderOptions,
            "render_schematic_svg": render_schematic_svg,
            "render_schematic_to_file": render_schematic_to_file,
        }[name]
    # Project utilities
    if name in ("read_kicad_pro_parameters", "make_kicad_httplib", "setup_kicad_preferences"):
        from .kicad_utilities import (
            make_kicad_httplib,
            read_kicad_pro_parameters,
            setup_kicad_preferences,
        )
        return {
            "read_kicad_pro_parameters": read_kicad_pro_parameters,
            "make_kicad_httplib": make_kicad_httplib,
            "setup_kicad_preferences": setup_kicad_preferences,
        }[name]
    # S-expression read + mutation helpers (kicad_base)
    if name in (
        "find_element",
        "find_all_elements",
        "get_value",
        "get_values",
        "has_flag",
        "parse_maybe_absent_bool",
        "unquote_string",
        "replace_element",
        "remove_element",
        "remove_all_elements",
        "set_value",
        "walk",
        "find_path",
        "transform_descendants",
    ):
        from .kicad_base import (
            find_all_elements,
            find_element,
            find_path,
            get_value,
            get_values,
            has_flag,
            parse_maybe_absent_bool,
            remove_all_elements,
            remove_element,
            replace_element,
            set_value,
            transform_descendants,
            unquote_string,
            walk,
        )
        return {
            "find_element": find_element,
            "find_all_elements": find_all_elements,
            "get_value": get_value,
            "get_values": get_values,
            "has_flag": has_flag,
            "parse_maybe_absent_bool": parse_maybe_absent_bool,
            "unquote_string": unquote_string,
            "replace_element": replace_element,
            "remove_element": remove_element,
            "remove_all_elements": remove_all_elements,
            "set_value": set_value,
            "walk": walk,
            "find_path": find_path,
            "transform_descendants": transform_descendants,
        }[name]
    # Filter framework — entry points, helpers, individual filters
    if name == "KiCadEnvironment":
        from .kicad_environment import KiCadEnvironment
        return KiCadEnvironment
    if name == "KiCadNameIndex":
        from .kicad_name_index import KiCadNameIndex
        return KiCadNameIndex
    if name in (
        "KiCadFilterPipeline",
        "format_kicad_sexp",
        "fp_filter__add_fab_bounding_orthogonal_convex",
        "fp_filter__clean_fab",
        "fp_filter__clean_layers",
        "fp_filter__fix_fp_text_font_to_arial",
        "fp_filter__fix_zero_sized_pads",
        "fp_filter__normalized_embedded_model_naming",
        "fp_filter__orthographic_projection_outline",
        "pcb_filter__process_embedded_footprints",
        "pcb_filter__reset_layer_user_names",
        "sch_filter__remove_altium_value_property",
        "sym_filter__clear_property_values",
        "sym_filter__remove_nonstandard_properties",
        "sym_filter__standardize_reference_value_fonts",
    ):
        from .kicad_filter_core import (
            KiCadFilterPipeline,
            format_kicad_sexp,
            fp_filter__clean_fab,
            fp_filter__fix_fp_text_font_to_arial,
            fp_filter__fix_zero_sized_pads,
            fp_filter__normalized_embedded_model_naming,
            fp_filter__orthographic_projection_outline,
            pcb_filter__process_embedded_footprints,
            pcb_filter__reset_layer_user_names,
            sch_filter__remove_altium_value_property,
            sym_filter__clear_property_values,
            sym_filter__remove_nonstandard_properties,
            sym_filter__standardize_reference_value_fonts,
        )
        from .kicad_filter_footprint import (
            fp_filter__add_fab_bounding_orthogonal_convex,
            fp_filter__clean_layers,
        )
        return {
            "KiCadFilterPipeline": KiCadFilterPipeline,
            "format_kicad_sexp": format_kicad_sexp,
            "fp_filter__add_fab_bounding_orthogonal_convex": fp_filter__add_fab_bounding_orthogonal_convex,
            "fp_filter__clean_fab": fp_filter__clean_fab,
            "fp_filter__clean_layers": fp_filter__clean_layers,
            "fp_filter__fix_fp_text_font_to_arial": fp_filter__fix_fp_text_font_to_arial,
            "fp_filter__fix_zero_sized_pads": fp_filter__fix_zero_sized_pads,
            "fp_filter__normalized_embedded_model_naming": fp_filter__normalized_embedded_model_naming,
            "fp_filter__orthographic_projection_outline": fp_filter__orthographic_projection_outline,
            "pcb_filter__process_embedded_footprints": pcb_filter__process_embedded_footprints,
            "pcb_filter__reset_layer_user_names": pcb_filter__reset_layer_user_names,
            "sch_filter__remove_altium_value_property": sch_filter__remove_altium_value_property,
            "sym_filter__clear_property_values": sym_filter__clear_property_values,
            "sym_filter__remove_nonstandard_properties": sym_filter__remove_nonstandard_properties,
            "sym_filter__standardize_reference_value_fonts": sym_filter__standardize_reference_value_fonts,
        }[name]
    # Extractors — footprint
    if name in (
        "extract_footprints_from_text",
        "extract_footprints_from_pcb",
        "extract_footprints_from_project",
    ):
        from .kicad_footprint_extractor import (
            extract_footprints_from_pcb,
            extract_footprints_from_project,
            extract_footprints_from_text,
        )
        return {
            "extract_footprints_from_text": extract_footprints_from_text,
            "extract_footprints_from_pcb": extract_footprints_from_pcb,
            "extract_footprints_from_project": extract_footprints_from_project,
        }[name]
    # Extractors — symbol (parses sexpr)
    if name in ("extract_symbols_from_text", "create_symbol_file_content"):
        from .kicad_symbol_extractor import (
            create_symbol_file_content,
            extract_symbols_from_text,
        )
        return {
            "extract_symbols_from_text": extract_symbols_from_text,
            "create_symbol_file_content": create_symbol_file_content,
        }[name]
    # Extractors — schematic file-level (writes files)
    if name == "list_symbols_in_schematic":
        from .kicad_sch_extractor import list_symbols_in_schematic
        return list_symbols_in_schematic
    # Extractors — STEP
    if name in (
        "find_embedded_step_data",
        "extract_step_from_text",
        "extract_step_from_footprint",
        "extract_step_from_directory",
        "view_step_file",
    ):
        from .kicad_step_extractor import (
            extract_step_from_directory,
            extract_step_from_footprint,
            extract_step_from_text,
            find_embedded_step_data,
            view_step_file,
        )
        return {
            "find_embedded_step_data": find_embedded_step_data,
            "extract_step_from_text": extract_step_from_text,
            "extract_step_from_footprint": extract_step_from_footprint,
            "extract_step_from_directory": extract_step_from_directory,
            "view_step_file": view_step_file,
        }[name]
    # Plotter IR
    if name in (
        "KICAD_PLOTTER_IR_SCHEMA",
        "KiCadFillType",
        "KiCadHorizAlign",
        "KiCadLineStyle",
        "KiCadPenAction",
        "KiCadPlotterBounds",
        "KiCadPlotterDocument",
        "KiCadPlotterOp",
        "KiCadPlotterOpKind",
        "KiCadPlotterRecord",
        "KiCadVertAlign",
        "make_brush",
        "make_font",
        "make_pen",
        "styled_plotter_op",
    ):
        from . import kicad_plotter_ir as _ir
        return getattr(_ir, name)
    # SVG primitive layer
    if name in (
        "KiCadJunctionZOrder",
        "KiCadSvgRenderContext",
        "KiCadSvgRenderOptions",
        "KiCadVariantDimMode",
        "fmt_user_number",
        "svg_arc",
        "svg_bezier",
        "svg_circle",
        "svg_document",
        "svg_ellipse",
        "svg_group",
        "svg_line",
        "svg_path",
        "svg_polygon",
        "svg_polyline",
        "svg_rect",
        "svg_text",
        "svg_text_or_poly",
        "svg_text_poly",
    ):
        from . import kicad_sch_svg_renderer as _svg
        return getattr(_svg, name)
    if name in (
        "KiCadSvgPreferenceTheme",
        "load_kicad_svg_preference_theme",
        "schematic_svg_options_from_preferences",
        "symbol_theme_from_preferences",
    ):
        from . import kicad_svg_preferences as _prefs
        return getattr(_prefs, name)
    # LibSymbol → IR converter
    if name in (
        "arc_to_op",
        "bezier_to_op",
        "circle_to_op",
        "lib_symbol_to_ir",
        "mm_to_nm",
        "pin_to_ops",
        "polyline_to_op",
        "polyline_to_op_from_points",
        "rectangle_to_op",
        "rgba_to_hex",
        "stroke_type_to_line_style",
        "stroke_width_nm",
        "subsymbol_to_record",
        "sym_fill_to_kicad_fill",
        "text_to_op",
        "y_to_ir",
    ):
        from . import kicad_lib_symbol_to_ir as _libir
        return getattr(_libir, name)
    # Schematic → IR converter
    if name in (
        "DEFAULT_BUS_WIDTH_MM",
        "DEFAULT_JUNCTION_DIAMETER_MM",
        "DEFAULT_LABEL_SIZE_RATIO",
        "DEFAULT_NO_CONNECT_HALF_MM",
        "DEFAULT_TEXT_SIZE_MM",
        "DEFAULT_WIRE_WIDTH_MM",
        "bus_entry_to_op",
        "bus_to_op",
        "global_label_decoration_to_op",
        "global_label_to_op",
        "hierarchical_label_decoration_to_op",
        "hierarchical_label_to_op",
        "junction_to_op",
        "label_to_op",
        "no_connect_to_ops",
        "paper_size_to_nm",
        "sch_text_to_op",
        "schematic_arc_to_ops",
        "schematic_bezier_to_ops",
        "schematic_circle_to_ops",
        "schematic_image_to_op",
        "schematic_polyline_to_ops",
        "schematic_rectangle_to_ops",
        "schematic_to_ir",
        "sheet_background_to_op",
        "sheet_outline_to_op",
        "sheet_pin_decoration_to_op",
        "sheet_pin_to_op",
        "sheet_property_to_op",
        "symbol_property_to_op",
        "text_box_outline_to_op",
        "text_box_to_ops",
        "wire_to_op",
    ):
        from . import kicad_schematic_to_ir as _schir
        return getattr(_schir, name)
    # IR → SVG renderer
    if name in (
        "render_ir_to_svg",
        "render_op",
        "render_record",
        "render_records",
    ):
        from . import kicad_ir_to_svg as _irsvg
        return getattr(_irsvg, name)
    # Recorder JSON loader
    if name in (
        "KICAD_PLOTTER_RECORDER_SCHEMA",
        "load_recorder_dict",
        "load_recorder_file",
        "normalise_recorder_op_units",
        "translate_recorder_canvas",
        "translate_recorder_op",
    ):
        from . import kicad_recorder_loader as _recld
        return getattr(_recld, name)
    # Recorder drift report
    if name in (
        "KICAD_RECORDER_DRIFT_SCHEMA",
        "RecorderDriftReport",
        "compute_recorder_drift",
    ):
        from . import kicad_recorder_drift as _recdr
        return getattr(_recdr, name)
    # Plotter-IR coordinate transform
    if name in (
        "KiCadPlotterTransform2D",
        "apply_transform_to_op",
        "apply_transform_to_ops",
        "transform_orient",
        "transform_point",
    ):
        from . import kicad_plotter_transform as _xform
        return getattr(_xform, name)
    # Drawing sheet emitter
    if name in (
        "DEFAULT_KICAD_WKS",
        "drawing_sheet_to_ops",
        "expand_format_codes",
        "load_default_drawing_sheet",
    ):
        from . import kicad_drawing_sheet as _dsh
        return getattr(_dsh, name)
    # Stroked-text fold
    if name in (
        "STROKED_TEXT_FOLD_KIND",
        "STROKED_TEXT_FOLD_MIN_POINTS",
        "STROKED_TEXT_FOLD_MIN_RUN",
        "fold_recorder_document",
        "fold_stroked_text_runs",
        "is_stroked_text_glyph",
    ):
        from . import kicad_recorder_stroked_text_fold as _stf
        return getattr(_stf, name)
    # Op-by-op equivalence diff
    if name in (
        "KICAD_OP_EQUIVALENCE_SCHEMA",
        "MATCH_STRATEGY_BY_KIND",
        "MATCH_STRATEGY_POSITIONAL",
        "MATCH_STRATEGY_WINDOWED_BY_KIND",
        "MATCH_WINDOW_UNBOUNDED",
        "KiCadOpDivergence",
        "OpEquivalenceReport",
        "compute_op_equivalence",
    ):
        from . import kicad_op_equivalence as _opeq
        return getattr(_opeq, name)
    # Design aggregator
    if name == "KiCadDesign":
        from .kicad_design import KiCadDesign
        return KiCadDesign
    # Variant overlay
    if name in (
        "KiCadVariantOverlayPolicy",
        "VARIANT_STATE_ACTIVE",
        "VARIANT_STATE_DIMMED",
        "VARIANT_STATE_KEY",
        "annotate_record_variant_state",
        "apply_variant_overlay",
        "compute_record_variant_state",
    ):
        from . import kicad_variant_overlay as _vo
        return getattr(_vo, name)
    # Footprint → IR converter
    if name in (
        "footprint_to_ir",
        "footprint_to_record",
        "fp_arc_to_op",
        "fp_circle_to_op",
        "fp_fill_to_kicad_fill",
        "fp_line_to_op",
        "fp_poly_to_op",
        "fp_rect_to_op",
        "fp_text_box_to_ops",
        "fp_text_to_op",
        "pad_drill_to_ops",
        "pad_to_ops",
        "property_to_op",
    ):
        from . import kicad_footprint_to_ir as _fpir
        return getattr(_fpir, name)
    # PCB → IR converter
    if name in (
        "pcb_to_ir",
        "gr_line_to_op",
        "gr_line_to_record",
        "gr_arc_to_op",
        "gr_arc_to_record",
        "gr_circle_to_op",
        "gr_circle_to_record",
        "gr_rect_to_op",
        "gr_rect_to_record",
        "gr_poly_to_op",
        "gr_poly_to_record",
        "gr_curve_to_op",
        "gr_curve_to_record",
        "gr_text_to_op",
        "gr_text_to_record",
        "gr_text_box_to_ops",
        "gr_text_box_to_record",
        "track_segment_to_op",
        "track_segment_to_record",
        "track_arc_to_op",
        "track_arc_to_record",
        "via_drill_to_op",
        "via_to_op",
        "via_to_record",
        "zone_filled_polygon_to_op",
        "zone_to_record",
        "pcb_footprint_to_record",
    ):
        from . import kicad_pcb_to_ir as _pcbir
        return getattr(_pcbir, name)
    # PCB IR → SVG wrapper
    if name == "render_pcb_ir_to_svg":
        from .kicad_pcb_ir_svg import render_pcb_ir_to_svg
        return render_pcb_ir_to_svg
    # Schematic connectivity
    if name in (
        "SCH_IU_PER_MM",
        "snap_mm_to_iu",
        "iu_key_to_mm",
        "compute_pin_position",
        "iter_symbol_pins",
        "CoordinateIndex",
        "ConnectivityGraph",
        "detect_no_connects",
    ):
        from . import kicad_schematic_connectivity as _conn
        return getattr(_conn, name)
    # Bus label expansion
    if name in (
        "is_bus_label",
        "parse_bus_vector",
        "parse_bus_group",
        "expand_bus_label",
    ):
        from . import kicad_bus_expansion as _bus
        return getattr(_bus, name)
    # Netlist model
    if name in (
        "KiCadDriverPriority",
        "KiCadDriverKind",
        "KiCadPinType",
        "KiCadNetlistTerminal",
        "KiCadNetEndpoint",
        "KiCadNet",
        "KiCadNetlistComponent",
        "KiCadLibPart",
        "KiCadLibPartPin",
        "KiCadDesignSheet",
        "KiCadDesignMetadata",
        "KiCadNetlist",
    ):
        from . import kicad_netlist_model as _nlm
        return getattr(_nlm, name)
    # Single-sheet netlist compiler
    if name in (
        "Subgraph",
        "compile_sheet_subgraphs",
        "compile_sheet_netlist",
        "name_net",
    ):
        from . import kicad_netlist_compiler as _nlc
        return getattr(_nlc, name)
    # Multi-sheet netlist compile
    if name in (
        "CompiledSheet",
        "compile_design_subgraphs",
        "merge_design_nets",
        "compile_design_netlist",
        "collect_design_components",
        "collect_design_libparts",
    ):
        from . import kicad_netlist_design as _nld
        return getattr(_nld, name)
    # KiCad-format netlist emit
    if name in (
        "KICAD_NETLIST_VERSION",
        "to_kicad_sexpr",
    ):
        from . import kicad_netlist_kicadsexpr as _nlk
        return getattr(_nlk, name)
    # Generic netlist_a0 bridge
    if name in ("kicad_netlist_to_data_models_netlist",):
        from . import kicad_netlist_data_models as _nldm
        return getattr(_nldm, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
