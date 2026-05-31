"""
Schematic filters for KiCad .kicad_sch files.

These filters operate on parsed s-expressions and modify schematic data.
"""
import logging
from typing import Any

from .kicad_base import find_all_elements, find_element, unquote_string

log = logging.getLogger(__name__)


def sch_filter__remove_altium_value_property(unfiltered_s_expression: Any) -> Any:
    """
    Removes the "ALTIUM_VALUE" property from every symbol in the lib_symbols
    section. Mutates ``unfiltered_s_expression`` in place and returns it.
    """
    log.info("\nRunning sch_filter__remove_altium_value_property()...\n")

    lib_symbols = find_element(unfiltered_s_expression, 'lib_symbols')
    if lib_symbols is None:
        log.warning("Warning: No lib_symbols section found.")
        return unfiltered_s_expression

    properties_removed = 0
    for symbol in find_all_elements(lib_symbols, 'symbol'):
        symbol_name = symbol[1] if len(symbol) > 1 else "unknown"
        # Walk properties in reverse so removals don't disturb iteration.
        for i in range(len(symbol) - 1, -1, -1):
            elem = symbol[i]
            if (isinstance(elem, list) and len(elem) >= 2
                    and elem[0] == 'property'
                    and unquote_string(elem[1]) == 'ALTIUM_VALUE'):
                log.info(f"  - Removing 'ALTIUM_VALUE' from symbol '{symbol_name}'")
                symbol.pop(i)
                properties_removed += 1

    if properties_removed > 0:
        log.info(f"Success: Removed {properties_removed} ALTIUM_VALUE property/properties.")
    else:
        log.warning("Warning: No ALTIUM_VALUE properties found to remove.")

    return unfiltered_s_expression
