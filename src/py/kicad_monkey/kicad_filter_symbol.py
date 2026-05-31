"""
Symbol filters for KiCad .kicad_sym files.

These filters operate on parsed s-expressions and modify symbol library data.
"""
import logging
from typing import Any

from .kicad_base import find_all_elements, unquote_string
from .kicad_sexpr import QuotedString

log = logging.getLogger(__name__)


# Standard properties that should be kept by sym_filter__remove_nonstandard_properties
STANDARD_PROPERTIES = {'Reference', 'Value', 'Description', 'Footprint', 'Datasheet'}

# Properties whose values are cleared by sym_filter__clear_property_values
PROPERTIES_TO_CLEAR = {'Value', 'Description', 'Footprint', 'Datasheet'}


def sym_filter__remove_nonstandard_properties(unfiltered_s_expression: Any) -> Any:
    """
    Removes property entries that aren't in the standard KiCad set
    (Reference, Value, Description, Footprint, Datasheet).

    Mutates ``unfiltered_s_expression`` in place and returns it. Handles
    multi-symbol libraries (multiple symbol definitions in one file).
    """
    log.info("\nRunning sym_filter__remove_nonstandard_properties()...\n")

    properties_removed = 0
    for symbol in find_all_elements(unfiltered_s_expression, 'symbol'):
        symbol_name = symbol[1] if len(symbol) > 1 else "unknown"
        log.info(f"Processing symbol: {symbol_name}")
        # Walk in reverse so removals don't disturb iteration.
        for i in range(len(symbol) - 1, -1, -1):
            elem = symbol[i]
            if not (isinstance(elem, list) and len(elem) >= 2 and elem[0] == 'property'):
                continue
            name = unquote_string(elem[1])
            if name not in STANDARD_PROPERTIES:
                log.info(f"  - Removing property '{name}' from symbol '{symbol_name}'")
                symbol.pop(i)
                properties_removed += 1

    if properties_removed > 0:
        log.info(f"Success: Removed {properties_removed} non-standard property/properties.")
    else:
        log.warning("Warning: No non-standard properties found to remove.")

    log.info("\nDone! S-expression has been filtered...")
    return unfiltered_s_expression


def sym_filter__clear_property_values(unfiltered_s_expression: Any) -> Any:
    """
    Clears the value of Value/Description/Footprint/Datasheet properties on every
    symbol (Reference is preserved). Mutates in place and returns the input.
    """
    log.info("\nRunning sym_filter__clear_property_values()...\n")

    properties_cleared = 0
    for symbol in find_all_elements(unfiltered_s_expression, 'symbol'):
        symbol_name = symbol[1] if len(symbol) > 1 else "unknown"
        log.info(f"Processing symbol: {symbol_name}")
        for prop in symbol:
            if not (isinstance(prop, list) and len(prop) >= 3 and prop[0] == 'property'):
                continue
            name = unquote_string(prop[1])
            if name not in PROPERTIES_TO_CLEAR:
                continue
            old_value = str(prop[2])
            if old_value in ('""', ''):
                continue
            log.info(
                f"  - Clearing property '{name}' value from '{old_value}' to \"\" "
                f"in symbol '{symbol_name}'"
            )
            prop[2] = QuotedString("")
            properties_cleared += 1

    if properties_cleared > 0:
        log.info(f"Success: Cleared {properties_cleared} property value(s).")
    else:
        log.warning("Warning: No property values needed clearing.")

    log.info("\nDone! S-expression has been filtered...")
    return unfiltered_s_expression


# Font definitions for Reference / Value standardization.
_REFERENCE_FONT = ['font',
                   ['face', QuotedString('Arial')],
                   ['size', 2.1844, 2.1844],
                   ['bold', 'yes']]

_VALUE_FONT = ['font',
               ['face', QuotedString('Arial')],
               ['size', 1.524, 1.524]]


def _standardize_property_font(prop: list, symbol_name: str, fonts_fixed_ref: list) -> list:
    """Replace or add font on a Reference/Value property's effects subtree.

    Returns the (mutated) prop. fonts_fixed_ref is a 1-element list used as a
    mutable counter so the closure can update it.
    """
    name = unquote_string(prop[1])
    is_reference = (name == 'Reference')
    new_font = _REFERENCE_FONT if is_reference else _VALUE_FONT
    label = 'Reference' if is_reference else 'Value'
    desc = 'Arial 2.1844 bold' if is_reference else 'Arial 1.524'

    for effects in prop:
        if not (isinstance(effects, list) and len(effects) > 0 and effects[0] == 'effects'):
            continue
        # Replace any existing font child; otherwise append.
        font_found = False
        for j, eff in enumerate(effects):
            if isinstance(eff, list) and len(eff) > 0 and eff[0] == 'font':
                effects[j] = list(new_font)
                font_found = True
                log.info(f"  - Updating {label} font to {desc} in symbol '{symbol_name}'")
                fonts_fixed_ref[0] += 1
                break
        if not font_found:
            effects.append(list(new_font))
            log.info(f"  - Adding {label} font {desc} in symbol '{symbol_name}'")
            fonts_fixed_ref[0] += 1
    return prop


def sym_filter__standardize_reference_value_fonts(unfiltered_s_expression: Any) -> Any:
    """
    Standardizes fonts on Reference (Arial 2.1844 bold) and Value (Arial 1.524)
    properties in every symbol. Mutates in place and returns the input.
    """
    log.info("\nRunning sym_filter__standardize_reference_value_fonts()...\n")

    fonts_fixed = [0]
    for symbol in find_all_elements(unfiltered_s_expression, 'symbol'):
        symbol_name = symbol[1] if len(symbol) > 1 else "unknown"
        log.info(f"Processing symbol: {symbol_name}")
        for prop in symbol:
            if not (isinstance(prop, list) and len(prop) >= 2 and prop[0] == 'property'):
                continue
            if unquote_string(prop[1]) in ('Reference', 'Value'):
                _standardize_property_font(prop, symbol_name, fonts_fixed)

    if fonts_fixed[0] > 0:
        log.info(f"Success: Fixed {fonts_fixed[0]} Reference/Value font(s).")
    else:
        log.warning("Warning: No Reference/Value fonts needed fixing.")

    log.info("\nDone! S-expression has been filtered...")
    return unfiltered_s_expression
