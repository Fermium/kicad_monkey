"""
KiCad Schematic Labels

Label, global label, and hierarchical label elements for net naming.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .kicad_sexpr import QuotedString
from .kicad_base import find_element, get_value, parse_maybe_absent_bool, unquote_string
from .kicad_primitives import Effects
from .kicad_sch_enums import LabelShape


@dataclass
class SchLabel:
    """Local net label.

    Labels a wire with a net name that's local to the current schematic sheet.

    S-expression format:
        (label "SIGNAL_NAME"
            (at X Y ANGLE)
            (effects
                (font (size 1.27 1.27) ...)
                (justify left bottom)
            )
            (uuid "...")
        )
    """
    text: str = ""
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    effects: Optional[Effects] = None
    fields_autoplaced: bool = False
    uuid: str = ""
    # Trailing (property ...) fields — saveText writes saveField() for each
    # SCH_FIELD on the label (e.g. user-added "Net Class" attributes).
    properties: list = field(default_factory=list)

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchLabel':
        """Parse from (label "text" (at X Y A) (effects ...) (uuid "..."))."""
        from .kicad_sym_property import SymProperty
        from .kicad_base import find_all_elements

        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        # Position
        at_elem = find_element(sexp, 'at')
        at_x = float(at_elem[1]) if at_elem and len(at_elem) > 1 else 0.0
        at_y = float(at_elem[2]) if at_elem and len(at_elem) > 2 else 0.0
        at_angle = float(at_elem[3]) if at_elem and len(at_elem) > 3 else 0.0

        effects = Effects.from_sexp(sexp)
        # KiCad 10 emits `(fields_autoplaced yes)` via KICAD_FORMAT::FormatBool;
        # parser uses parseMaybeAbsentBool(true) — empty `(fields_autoplaced)` means True.
        fields_autoplaced = parse_maybe_absent_bool(sexp, 'fields_autoplaced') or False
        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        properties = [SymProperty.from_sexp(e) for e in find_all_elements(sexp, 'property')]

        return cls(
            text=text,
            at_x=at_x, at_y=at_y, at_angle=at_angle,
            effects=effects, fields_autoplaced=fields_autoplaced,
            uuid=uuid, properties=properties, _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = ['label', QuotedString(self.text)]

        # KiCad's reader requires the angle slot even when zero (drift inventory #1).
        result.append(['at', self.at_x, self.at_y, self.at_angle])

        if self.fields_autoplaced:
            result.append(['fields_autoplaced', 'yes'])

        if self.effects:
            result.append(self.effects.to_sexp())

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        for prop in self.properties:
            result.append(prop.to_sexp())

        return result


@dataclass
class SchGlobalLabel:
    """Global net label.

    Labels a net that connects across all schematic sheets in the project.
    Has a shape indicator (input, output, bidirectional, etc.).

    S-expression format:
        (global_label "SIGNAL_NAME"
            (shape output)
            (at X Y ANGLE)
            (effects
                (font (size 1.27 1.27) ...)
                (justify left)
            )
            (uuid "...")
            (property "Intersheetrefs" "${INTERSHEET_REFS}" ...)
        )
    """
    text: str = ""
    shape: LabelShape = LabelShape.INPUT
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    effects: Optional[Effects] = None
    fields_autoplaced: bool = False
    uuid: str = ""
    # Properties (like Intersheetrefs) stored as list of property elements
    properties: list = field(default_factory=list)

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchGlobalLabel':
        """Parse from (global_label "text" (shape X) (at X Y A) ...)."""
        from .kicad_sym_property import SymProperty

        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        # Shape
        shape_str = get_value(sexp, 'shape', 'input')
        try:
            shape = LabelShape(shape_str)
        except ValueError:
            shape = LabelShape.INPUT

        # Position
        at_elem = find_element(sexp, 'at')
        at_x = float(at_elem[1]) if at_elem and len(at_elem) > 1 else 0.0
        at_y = float(at_elem[2]) if at_elem and len(at_elem) > 2 else 0.0
        at_angle = float(at_elem[3]) if at_elem and len(at_elem) > 3 else 0.0

        effects = Effects.from_sexp(sexp)
        # KiCad 10 emits `(fields_autoplaced yes)` via KICAD_FORMAT::FormatBool;
        # parser uses parseMaybeAbsentBool(true) — empty `(fields_autoplaced)` means True.
        fields_autoplaced = parse_maybe_absent_bool(sexp, 'fields_autoplaced') or False
        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        # Properties (like Intersheetrefs)
        properties = []
        from .kicad_base import find_all_elements
        for prop_elem in find_all_elements(sexp, 'property'):
            properties.append(SymProperty.from_sexp(prop_elem))

        return cls(
            text=text, shape=shape,
            at_x=at_x, at_y=at_y, at_angle=at_angle,
            effects=effects, fields_autoplaced=fields_autoplaced,
            uuid=uuid, properties=properties, _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = ['global_label', QuotedString(self.text)]
        result.append(['shape', self.shape.value])

        # KiCad's reader requires the angle slot even when zero (drift inventory #1).
        result.append(['at', self.at_x, self.at_y, self.at_angle])

        if self.fields_autoplaced:
            result.append(['fields_autoplaced', 'yes'])

        if self.effects:
            result.append(self.effects.to_sexp())

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        for prop in self.properties:
            result.append(prop.to_sexp())

        return result


@dataclass
class SchHierarchicalLabel:
    """Hierarchical sheet label.

    Labels a connection point on the current sheet that connects to
    a sheet pin on a hierarchical sheet symbol.

    S-expression format:
        (hierarchical_label "SIGNAL_NAME"
            (shape output)
            (at X Y ANGLE)
            (effects
                (font (size 1.524 1.524) ...)
                (justify right)
            )
            (uuid "...")
        )
    """
    text: str = ""
    shape: LabelShape = LabelShape.INPUT
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    effects: Optional[Effects] = None
    fields_autoplaced: bool = False
    uuid: str = ""

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchHierarchicalLabel':
        """Parse from (hierarchical_label "text" (shape X) (at X Y A) ...)."""
        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        # Shape
        shape_str = get_value(sexp, 'shape', 'input')
        try:
            shape = LabelShape(shape_str)
        except ValueError:
            shape = LabelShape.INPUT

        # Position
        at_elem = find_element(sexp, 'at')
        at_x = float(at_elem[1]) if at_elem and len(at_elem) > 1 else 0.0
        at_y = float(at_elem[2]) if at_elem and len(at_elem) > 2 else 0.0
        at_angle = float(at_elem[3]) if at_elem and len(at_elem) > 3 else 0.0

        effects = Effects.from_sexp(sexp)
        # KiCad 10 emits `(fields_autoplaced yes)` via KICAD_FORMAT::FormatBool;
        # parser uses parseMaybeAbsentBool(true) — empty `(fields_autoplaced)` means True.
        fields_autoplaced = parse_maybe_absent_bool(sexp, 'fields_autoplaced') or False
        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        return cls(
            text=text, shape=shape,
            at_x=at_x, at_y=at_y, at_angle=at_angle,
            effects=effects, fields_autoplaced=fields_autoplaced,
            uuid=uuid, _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = ['hierarchical_label', QuotedString(self.text)]
        result.append(['shape', self.shape.value])

        # KiCad's reader requires the angle slot even when zero (drift inventory #1).
        result.append(['at', self.at_x, self.at_y, self.at_angle])

        if self.fields_autoplaced:
            result.append(['fields_autoplaced', 'yes'])

        if self.effects:
            result.append(self.effects.to_sexp())

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        return result


@dataclass
class SchNetclassFlag:
    """Net class flag annotation (SCH_DIRECTIVE_LABEL_T with shape token).

    Emitted by saveText (sch_io_kicad_sexpr.cpp:1431) which dispatches
    on SCH_DIRECTIVE_LABEL_T to add ``(length ...)`` and on label types
    to add ``(shape ...)``, ``(fields_autoplaced ...)`` and trailing
    ``saveField()`` calls for each property.

    S-expression format:
        (netclass_flag "ClassLabel"
            (length L)
            (shape round)
            (at X Y ANGLE)
            [(fields_autoplaced yes)]
            (effects ...)
            (uuid "...")
            [(locked yes)]
            [(property "Name" "Value" ...)]*
        )
    """
    text: str = ""
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    length: float = 2.54
    shape: str = "round"  # round, rectangle, diamond, dot
    effects: Optional[Effects] = None
    fields_autoplaced: bool = False
    uuid: str = ""
    locked: bool = False
    # Properties (Net Class, Component Class, etc.) — emitted via saveField
    # at the tail of saveText. Stored as SymProperty instances.
    properties: list = field(default_factory=list)

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchNetclassFlag':
        """Parse from (netclass_flag "text" ...)."""
        from .kicad_sym_property import SymProperty
        from .kicad_base import find_all_elements

        text = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        # Position
        at_elem = find_element(sexp, 'at')
        at_x = float(at_elem[1]) if at_elem and len(at_elem) > 1 else 0.0
        at_y = float(at_elem[2]) if at_elem and len(at_elem) > 2 else 0.0
        at_angle = float(at_elem[3]) if at_elem and len(at_elem) > 3 else 0.0

        length = float(get_value(sexp, 'length', 2.54))
        shape = get_value(sexp, 'shape', 'round')

        effects = Effects.from_sexp(sexp)
        fields_autoplaced = parse_maybe_absent_bool(sexp, 'fields_autoplaced') or False
        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        locked_elem = find_element(sexp, 'locked')
        locked = bool(locked_elem and len(locked_elem) > 1 and locked_elem[1] == 'yes')

        properties = [SymProperty.from_sexp(e) for e in find_all_elements(sexp, 'property')]

        return cls(
            text=text,
            at_x=at_x, at_y=at_y, at_angle=at_angle,
            length=length, shape=shape,
            effects=effects, fields_autoplaced=fields_autoplaced,
            uuid=uuid, locked=locked, properties=properties,
            _raw_sexp=sexp,
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list.

        Mirrors saveText emit order for SCH_DIRECTIVE_LABEL_T:
        text, length, shape, at, fields_autoplaced, effects, uuid,
        locked, properties.
        """
        result = ['netclass_flag', QuotedString(self.text)]
        result.append(['length', self.length])
        result.append(['shape', self.shape])
        # KiCad's reader requires the angle slot even when zero (drift inventory #1).
        result.append(['at', self.at_x, self.at_y, self.at_angle])

        if self.fields_autoplaced:
            result.append(['fields_autoplaced', 'yes'])

        if self.effects:
            result.append(self.effects.to_sexp())

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        if self.locked:
            result.append(['locked', 'yes'])

        for prop in self.properties:
            result.append(prop.to_sexp())

        return result
