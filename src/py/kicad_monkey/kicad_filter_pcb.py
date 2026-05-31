"""
PCB filters for KiCad .kicad_pcb files.

These filters operate on parsed s-expressions and modify PCB data.
"""
import logging
from typing import Any

from ._files import compose
from .kicad_base import find_element
from .kicad_filter_footprint import (
    fp_filter__add_fab_bounding_orthogonal_convex,
    fp_filter__clean_fab,
    fp_filter__fix_fp_text_font_to_arial,
    fp_filter__fix_zero_sized_pads,
    fp_filter__normalized_embedded_model_naming,
)

log = logging.getLogger(__name__)


def pcb_filter__reset_layer_user_names(unfiltered_s_expression: Any) -> Any:
    """
    Removes custom user names from layer definitions, restoring KiCad defaults.

    KiCad layer format:
        (layer_number "canonical_name" type "user_name")
    becomes:
        (layer_number "canonical_name" type)

    Example:
        (0 "F.Cu" signal "Top Layer")  -> (0 "F.Cu" signal)
        (5 "F.SilkS" user "Top Overlay") -> (5 "F.SilkS" user)
    """
    log.info("\nRunning pcb_filter__reset_layer_user_names()...")

    layers = find_element(unfiltered_s_expression, 'layers')
    if layers is None:
        log.info("  No layers section found")
        return unfiltered_s_expression

    log.info(f"  Found layers section with {len(layers) - 1} layer definitions")
    layers_reset = 0
    for i, layer_def in enumerate(layers):
        if i == 0 or not isinstance(layer_def, list):
            continue
        # Layer format: (number "name" type ["user_name"])
        if len(layer_def) > 3:
            old_user_name = layer_def[3]
            layers[i] = layer_def[:3]
            layers_reset += 1
            log.info(f"    Reset layer {layer_def[1]}: removed user name '{old_user_name}'")

    if layers_reset > 0:
        log.info(f"  Reset {layers_reset} layer(s) to default names")
    else:
        log.info("  No layers with custom user names found")

    return unfiltered_s_expression


def pcb_filter__process_embedded_footprints(unfiltered_s_expression: Any) -> Any:
    """
    Applies the footprint filter chain to every embedded footprint in the PCB.

    Note: STEP models in PCB files are embedded at the PCB level, not in
    individual footprints — orthographic_projection_outline is therefore
    not part of this chain.
    """
    log.info("\nRunning pcb_filter__process_embedded_footprints()...\n")

    # Footprint filter chain -- same as KiCadFilterPipeline.filter_footprint minus orthographic projection.
    footprint_filter = compose(
        fp_filter__normalized_embedded_model_naming,
        fp_filter__add_fab_bounding_orthogonal_convex,
        fp_filter__fix_fp_text_font_to_arial,
        fp_filter__fix_zero_sized_pads,
        fp_filter__clean_fab,
    )

    footprints_processed = 0
    footprints_found = 0
    for i, item in enumerate(unfiltered_s_expression):
        if not (isinstance(item, list) and len(item) > 0 and item[0] == 'footprint'):
            continue
        footprints_found += 1
        footprint_name = item[1] if len(item) > 1 else "unknown"
        log.info(f"Processing embedded footprint #{footprints_found}: {footprint_name}")
        try:
            unfiltered_s_expression[i] = footprint_filter(item)
            footprints_processed += 1
            log.info(f"  [OK] Successfully processed {footprint_name}")
        except Exception as e:
            import traceback
            log.error(f"Error processing footprint {footprint_name}: {e}")
            log.error(f"Traceback: {traceback.format_exc()}")
            # Keep the original footprint if filtering fails (no replacement).

    log.info(f"\nFootprints found: {footprints_found}")
    if footprints_processed > 0:
        log.info(f"Success: Processed {footprints_processed} embedded footprint(s).")
    else:
        log.warning("Warning: No footprints were successfully processed.")

    return unfiltered_s_expression
