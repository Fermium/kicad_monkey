"""
KiCad Schematic Hierarchical Sheet

Hierarchical sheet symbols and pins for multi-sheet designs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple

from ._api_markers import public_api
from .kicad_defaults import (
    KICAD_DEFAULT_SHEET_HEIGHT_MM,
    KICAD_DEFAULT_SHEET_WIDTH_MM,
)
from .kicad_sexpr import QuotedString
from .kicad_base import (
    find_element,
    find_all_elements,
    get_value,
    has_flag,
    parse_maybe_absent_bool,
    unquote_string,
)
from .kicad_primitives import Stroke, Effects
from .kicad_sch_enums import LabelShape, StandardSheetPropertyKey
from .kicad_sch_symbol import SchSymbolInstanceVariant


@dataclass
class SchSheetPin:
    """Pin on a hierarchical sheet symbol.

    Connects signals from the parent sheet into the child sheet.

    S-expression format:
        (pin "PinName" TYPE
            (at X Y ANGLE)
            (uuid "...")
            (effects
                (font (size 1.27 1.27))
                (justify left)
            )
        )

    TYPE is one of: input, output, bidirectional, tri_state, passive
    """
    name: str = ""
    shape: LabelShape = LabelShape.INPUT
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    effects: Optional[Effects] = None
    uuid: str = ""

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchSheetPin':
        """Parse from (pin "name" TYPE (at X Y A) ...)."""
        name = unquote_string(sexp[1]) if len(sexp) > 1 else ""

        # Shape/type is the second positional argument
        shape_str = sexp[2] if len(sexp) > 2 and isinstance(sexp[2], str) else "input"
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
        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        return cls(
            name=name, shape=shape,
            at_x=at_x, at_y=at_y, at_angle=at_angle,
            effects=effects, uuid=uuid, _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result = ['pin', QuotedString(self.name), self.shape.value]

        # KiCad's reader requires the angle slot even when zero (drift inventory #1).
        result.append(['at', self.at_x, self.at_y, self.at_angle])

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        if self.effects:
            result.append(self.effects.to_sexp())

        return result


@dataclass
class SchSheetProperty:
    """Property on a hierarchical sheet (like Sheetname, Sheetfile).

    Sheet properties are routed through SCH_IO_KICAD_SEXPR::saveField
    (sch_io_kicad_sexpr.cpp:997 / called at :1117). KiCad always emits
    ``(show_name yes/no)`` and ``(do_not_autoplace yes/no)`` via
    KICAD_FORMAT::FormatBool, plus an optional ``(hide yes)`` when
    !IsVisible.

    S-expression format:
        (property "Sheetname" "PowerSupply"
            (at X Y ANGLE)
            [(hide yes)]
            (show_name yes/no)
            (do_not_autoplace yes/no)
            (effects
                (font (size 3.81 3.81) ...)
                (justify left bottom)
            )
        )
    """
    key: str = ""
    value: str = ""
    at_x: float = 0.0
    at_y: float = 0.0
    at_angle: float = 0.0
    show_name: bool = False
    do_not_autoplace: bool = False
    hide: bool = False
    effects: Optional[Effects] = None

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchSheetProperty':
        """Parse from (property "key" "value" (at X Y A) ...)."""
        key = unquote_string(sexp[1]) if len(sexp) > 1 else ""
        value = unquote_string(sexp[2]) if len(sexp) > 2 else ""

        # Position
        at_elem = find_element(sexp, 'at')
        at_x = float(at_elem[1]) if at_elem and len(at_elem) > 1 else 0.0
        at_y = float(at_elem[2]) if at_elem and len(at_elem) > 2 else 0.0
        at_angle = float(at_elem[3]) if at_elem and len(at_elem) > 3 else 0.0

        # KiCad has used three forms for these flags across versions:
        #   - bare token  `show_name`
        #   - empty list  `(show_name)`
        #   - sub-list    `(show_name yes/no)`  (KiCad 10 canonical)
        def _bool_flag(name: str) -> bool:
            if has_flag(sexp, name):
                return True
            elem = find_element(sexp, name)
            if elem is None:
                return False
            if len(elem) <= 1:
                return True
            return elem[1] == 'yes'

        show_name = _bool_flag('show_name')
        do_not_autoplace = _bool_flag('do_not_autoplace')
        effects = Effects.from_sexp(sexp)
        hide = _bool_flag('hide') or (effects is not None and effects.hide)

        return cls(
            key=key, value=value,
            at_x=at_x, at_y=at_y, at_angle=at_angle,
            show_name=show_name,
            do_not_autoplace=do_not_autoplace,
            hide=hide,
            effects=effects, _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list.

        Mirrors saveField (sch_io_kicad_sexpr.cpp:997) emit order:
        property, at, [hide], show_name, do_not_autoplace, effects.
        KiCad 10's parser rejects the bare-token `show_name` form, so
        we emit the (show_name yes) sub-list when True.
        kicad-cli canonicalises both yes/no on save; emitting only the
        true case lets oracle-style upgrade reach parity.
        """
        result = ['property', QuotedString(self.key), QuotedString(self.value)]

        # KiCad's reader requires the angle slot even when zero (drift inventory #1).
        result.append(['at', self.at_x, self.at_y, self.at_angle])

        if self.hide:
            result.append(['hide', 'yes'])

        if self.show_name:
            result.append(['show_name', 'yes'])

        if self.do_not_autoplace:
            result.append(['do_not_autoplace', 'yes'])

        if self.effects:
            result.append(self.effects.to_sexp())

        return result


@dataclass
class SchSheetInstance:
    """Per-project sheet instance path emitted inside (sheet (instances ...)).

    KiCad emits these via saveSheet (sch_io_kicad_sexpr.cpp:1208) as::

        (instances
            (project "ProjectName"
                (path "/UUID/.../UUID" (page "1") [(variant ...)]*)
            )
        )

    The variant overrides reuse the same shape as
    ``SchSymbolInstanceVariant`` — saveSheet (line 1214) elides the
    bool fields when they match the sheet's defaults but does not emit
    on_board / in_pos_files at all, so those will round-trip as None.
    """
    project: str = ""
    path: str = ""
    page: str = ""
    variants: List[SchSymbolInstanceVariant] = field(default_factory=list)

    @classmethod
    def from_sexp(cls, project_name: str, path_elem: list) -> 'SchSheetInstance':
        path = unquote_string(path_elem[1]) if len(path_elem) > 1 else ""
        page = unquote_string(get_value(path_elem, 'page', ''))
        variants = [SchSymbolInstanceVariant.from_sexp(v)
                    for v in find_all_elements(path_elem, 'variant')]
        return cls(project=project_name, path=path, page=page, variants=variants)


@public_api
@dataclass
class SchSheet:
    """Hierarchical sheet symbol in a schematic.

    Represents a sub-schematic that can be navigated into.
    Contains pins for signal connections between sheets.

    S-expression format:
        (sheet
            (at X Y)
            (size W H)
            (exclude_from_sim no)
            (in_bom yes)
            (on_board yes)
            (dnp no)
            (stroke (width 0.254) (type solid))
            (fill (color 255 255 255 1))
            (uuid "...")
            (property "Sheetname" "..." (at X Y A) (effects ...))
            (property "Sheetfile" "..." (at X Y A) (effects ...))
            (pin "PinName" input (at X Y A) (uuid "...") (effects ...))
            ...
        )
    """
    at_x: float = 0.0
    at_y: float = 0.0
    size_x: float = KICAD_DEFAULT_SHEET_WIDTH_MM
    size_y: float = KICAD_DEFAULT_SHEET_HEIGHT_MM

    # Flags
    exclude_from_sim: bool = False
    in_bom: bool = True
    on_board: bool = True
    dnp: bool = False
    fields_autoplaced: bool = False

    stroke: Stroke = field(default_factory=Stroke)
    fill_color: Optional[Tuple[int, int, int, float]] = None

    uuid: str = ""

    # Properties (Sheetname, Sheetfile, custom)
    properties: List[SchSheetProperty] = field(default_factory=list)

    # Pins connecting to child sheet
    pins: List[SchSheetPin] = field(default_factory=list)

    # Per-project instance paths (with optional variant overrides)
    instances: List[SchSheetInstance] = field(default_factory=list)

    _raw_sexp: Optional[list] = field(default=None, repr=False)

    @classmethod
    def from_sexp(cls, sexp: list) -> 'SchSheet':
        """Parse from (sheet (at X Y) (size W H) ...)."""
        # Position
        at_elem = find_element(sexp, 'at')
        at_x = float(at_elem[1]) if at_elem and len(at_elem) > 1 else 0.0
        at_y = float(at_elem[2]) if at_elem and len(at_elem) > 2 else 0.0

        # Size
        size_elem = find_element(sexp, 'size')
        size_x = (
            float(size_elem[1])
            if size_elem and len(size_elem) > 1
            else KICAD_DEFAULT_SHEET_WIDTH_MM
        )
        size_y = (
            float(size_elem[2])
            if size_elem and len(size_elem) > 2
            else KICAD_DEFAULT_SHEET_HEIGHT_MM
        )

        # Flags
        exclude_from_sim_val = get_value(sexp, 'exclude_from_sim', 'no')
        exclude_from_sim = exclude_from_sim_val == 'yes' if exclude_from_sim_val else False

        in_bom_val = get_value(sexp, 'in_bom', 'yes')
        in_bom = in_bom_val == 'yes' if in_bom_val else True

        on_board_val = get_value(sexp, 'on_board', 'yes')
        on_board = on_board_val == 'yes' if on_board_val else True

        dnp_val = get_value(sexp, 'dnp', 'no')
        dnp = dnp_val == 'yes' if dnp_val else False

        # KiCad 10 emits `(fields_autoplaced yes)` via KICAD_FORMAT::FormatBool;
        # parser uses parseMaybeAbsentBool(true) — empty `(fields_autoplaced)` means True.
        fields_autoplaced = parse_maybe_absent_bool(sexp, 'fields_autoplaced') or False

        stroke = Stroke.from_sexp(sexp)

        # Fill color
        fill_color = None
        fill_elem = find_element(sexp, 'fill')
        if fill_elem:
            color_elem = find_element(fill_elem, 'color')
            if color_elem and len(color_elem) >= 5:
                fill_color = (
                    int(color_elem[1]),
                    int(color_elem[2]),
                    int(color_elem[3]),
                    float(color_elem[4])
                )

        uuid = unquote_string(get_value(sexp, 'uuid', ''))

        # Properties
        properties = []
        for prop_elem in find_all_elements(sexp, 'property'):
            properties.append(SchSheetProperty.from_sexp(prop_elem))

        # Pins
        pins = []
        for pin_elem in find_all_elements(sexp, 'pin'):
            pins.append(SchSheetPin.from_sexp(pin_elem))

        # Instance paths (saveSheet, sch_io_kicad_sexpr.cpp:1208)
        instances = []
        instances_elem = find_element(sexp, 'instances')
        if instances_elem:
            for project_elem in find_all_elements(instances_elem, 'project'):
                project_name = unquote_string(project_elem[1]) if len(project_elem) > 1 else ""
                for path_elem in find_all_elements(project_elem, 'path'):
                    instances.append(SchSheetInstance.from_sexp(project_name, path_elem))

        return cls(
            at_x=at_x, at_y=at_y,
            size_x=size_x, size_y=size_y,
            exclude_from_sim=exclude_from_sim,
            in_bom=in_bom, on_board=on_board, dnp=dnp,
            fields_autoplaced=fields_autoplaced,
            stroke=stroke, fill_color=fill_color,
            uuid=uuid, properties=properties, pins=pins,
            instances=instances,
            _raw_sexp=sexp
        )

    def to_sexp(self) -> list:
        """Serialize to S-expression list."""
        result: list = ['sheet']
        result.append(['at', self.at_x, self.at_y])
        result.append(['size', self.size_x, self.size_y])

        result.append(['exclude_from_sim', 'yes' if self.exclude_from_sim else 'no'])
        result.append(['in_bom', 'yes' if self.in_bom else 'no'])
        result.append(['on_board', 'yes' if self.on_board else 'no'])
        result.append(['dnp', 'yes' if self.dnp else 'no'])

        if self.fields_autoplaced:
            result.append(['fields_autoplaced', 'yes'])

        result.append(self.stroke.to_sexp())

        if self.fill_color:
            result.append(['fill', ['color', self.fill_color[0], self.fill_color[1],
                                    self.fill_color[2], self.fill_color[3]]])

        if self.uuid:
            result.append(['uuid', QuotedString(self.uuid)])

        for prop in self.properties:
            result.append(prop.to_sexp())

        for pin in self.pins:
            result.append(pin.to_sexp())

        # Instance paths
        if self.instances:
            instances_elem: list = ['instances']
            # Group by project, preserving first-seen order.
            by_project: dict = {}
            for inst in self.instances:
                by_project.setdefault(inst.project, []).append(inst)
            for project_name, project_instances in by_project.items():
                project_elem: list = ['project', QuotedString(project_name)]
                for inst in project_instances:
                    path_elem: list = ['path', QuotedString(inst.path)]
                    if inst.page:
                        path_elem.append(['page', QuotedString(inst.page)])
                    for variant in inst.variants:
                        path_elem.append(variant.to_sexp())
                    project_elem.append(path_elem)
                instances_elem.append(project_elem)
            result.append(instances_elem)

        return result

    # Convenience properties
    @property
    def sheet_name(self) -> str:
        """Get sheet name from properties.

        Pre-9.0 schematics (file format ``20200828`` and older) used
        the spaced keys ``"Sheet name"`` / ``"Sheet file"``; the
        modern format (``20210126`` onward) collapsed them to
        ``"Sheetname"`` / ``"Sheetfile"``. Accept both so the upstream
        QA netlist fixtures (and any older user files) still resolve
        their sub-sheets.
        """
        return self.get_property_value(
            StandardSheetPropertyKey.SHEET_NAME,
            legacy_key=StandardSheetPropertyKey.LEGACY_SHEET_NAME,
        )

    @property
    def sheet_file(self) -> str:
        """Get sheet file from properties (accepts pre-9.0 ``Sheet file``)."""
        return self.get_property_value(
            StandardSheetPropertyKey.SHEET_FILE,
            legacy_key=StandardSheetPropertyKey.LEGACY_SHEET_FILE,
        )

    @public_api
    def get_property_object(
        self,
        key: str | StandardSheetPropertyKey,
        *,
        legacy_key: str | StandardSheetPropertyKey | None = None,
    ) -> SchSheetProperty | None:
        """Get a sheet property object by key."""
        key_text = str(key)
        legacy_key_text = str(legacy_key) if legacy_key is not None else None
        for prop in self.properties:
            if prop.key == key_text or prop.key == legacy_key_text:
                return prop
        return None

    @public_api
    def get_property(self, key: str | StandardSheetPropertyKey) -> Optional[str]:
        """Get property value by key."""
        prop = self.get_property_object(key)
        return prop.value if prop is not None else None

    @public_api
    def get_property_value(
        self,
        key: str | StandardSheetPropertyKey,
        default: str = "",
        *,
        legacy_key: str | StandardSheetPropertyKey | None = None,
    ) -> str:
        """Get property value by key, returning default when absent."""
        prop = self.get_property_object(key, legacy_key=legacy_key)
        return prop.value if prop is not None else default

    @public_api
    def set_property_value(
        self,
        key: str | StandardSheetPropertyKey,
        value: str,
        *,
        create: bool = False,
    ) -> bool:
        """Set property value. Returns True if a property was updated or created."""
        prop = self.get_property_object(key)
        if prop is not None:
            prop.value = value
            return True
        if create:
            self.upsert_property(key, value)
            return True
        return False

    @public_api
    def upsert_property(
        self,
        key: str | StandardSheetPropertyKey,
        value: str,
    ) -> SchSheetProperty:
        """Create or update a sheet property and return the property object."""
        prop = self.get_property_object(key)
        if prop is not None:
            prop.value = value
            return prop
        prop = SchSheetProperty(key=str(key), value=value)
        self.properties.append(prop)
        return prop

    @public_api
    def remove_property(self, key: str | StandardSheetPropertyKey) -> bool:
        """Remove a sheet property by key."""
        key_text = str(key)
        for index, prop in enumerate(self.properties):
            if prop.key == key_text:
                del self.properties[index]
                return True
        return False

    @public_api
    def iter_properties(self) -> Iterator[SchSheetProperty]:
        """Iterate over hierarchical sheet properties."""
        return iter(self.properties)
