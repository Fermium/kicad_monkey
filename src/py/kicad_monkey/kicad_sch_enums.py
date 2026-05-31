"""
Schematic-specific enums for KiCad symbol and schematic files.

These enums are specific to schematic/symbol parsing and are not used
by PCB or footprint parsers. Shared enums (like StrokeType, FillType)
remain in kicad_base.py.
"""

from enum import Enum, IntEnum, StrEnum


class PinElectricalType(Enum):
    """Pin electrical type (KiCad ELECTRICAL_PINTYPE).

    Defines the electrical characteristics of a pin for ERC (Electrical Rules Check).
    """
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRI_STATE = "tri_state"
    PASSIVE = "passive"
    FREE = "free"
    UNSPECIFIED = "unspecified"
    POWER_IN = "power_in"
    POWER_OUT = "power_out"
    OPEN_COLLECTOR = "open_collector"
    OPEN_EMITTER = "open_emitter"
    NO_CONNECT = "no_connect"

    @classmethod
    def _missing_(cls, value):
        # Pre-20210123 schematics use "unconnected" as the no-connect
        # pin token; KiCad renamed it to "no_connect" in that bump
        # (see eeschema/sch_file_versions.h). Accept the legacy spelling.
        if value == "unconnected":
            return cls.NO_CONNECT
        return None


class PinGraphicStyle(Enum):
    """Pin graphic style (KiCad GRAPHIC_PINSHAPE).

    Defines the visual appearance of the pin connection point.
    """
    LINE = "line"
    INVERTED = "inverted"
    CLOCK = "clock"
    INVERTED_CLOCK = "inverted_clock"
    INPUT_LOW = "input_low"
    CLOCK_LOW = "clock_low"
    OUTPUT_LOW = "output_low"
    EDGE_CLOCK_HIGH = "edge_clock_high"
    NON_LOGIC = "non_logic"


class LabelShape(Enum):
    """Global/hierarchical label shape.

    Defines the visual shape of net labels that indicate signal direction.
    """
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRI_STATE = "tri_state"
    PASSIVE = "passive"
    DOT = "dot"
    ROUND = "round"
    DIAMOND = "diamond"
    RECTANGLE = "rectangle"


class PowerFlagType(Enum):
    """Power symbol type for power ports."""
    POWER_IN = "power_in"
    POWER_OUT = "power_out"


class StandardPropertyKey(StrEnum):
    """Standard KiCad schematic/symbol property keys."""
    REFERENCE = "Reference"
    VALUE = "Value"
    FOOTPRINT = "Footprint"
    DATASHEET = "Datasheet"
    DESCRIPTION = "Description"


class StandardSheetPropertyKey(StrEnum):
    """Standard hierarchical sheet property keys."""
    SHEET_NAME = "Sheetname"
    SHEET_FILE = "Sheetfile"
    LEGACY_SHEET_NAME = "Sheet name"
    LEGACY_SHEET_FILE = "Sheet file"


class PropertyId(IntEnum):
    """Standard KiCad property ID numbers (ordinals).

    KiCad assigns fixed ordinal numbers to standard properties.
    User-defined properties start at 5 and increment.
    """
    REFERENCE = 0
    VALUE = 1
    FOOTPRINT = 2
    DATASHEET = 3
    DESCRIPTION = 4
    USER_START = 5


_STANDARD_PROPERTY_ID_BY_KEY: dict[str, PropertyId] = {
    StandardPropertyKey.REFERENCE: PropertyId.REFERENCE,
    StandardPropertyKey.VALUE: PropertyId.VALUE,
    StandardPropertyKey.FOOTPRINT: PropertyId.FOOTPRINT,
    StandardPropertyKey.DATASHEET: PropertyId.DATASHEET,
    StandardPropertyKey.DESCRIPTION: PropertyId.DESCRIPTION,
}


def standard_property_id_for_key(key: str) -> PropertyId | None:
    """Return the fixed KiCad property ordinal for a standard key."""
    return _STANDARD_PROPERTY_ID_BY_KEY.get(str(key))


__all__ = [
    'PinElectricalType',
    'PinGraphicStyle',
    'LabelShape',
    'PowerFlagType',
    'StandardPropertyKey',
    'StandardSheetPropertyKey',
    'PropertyId',
    'standard_property_id_for_key',
]
