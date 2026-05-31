"""
Legacy KiCad PcbDoc parser

Parse KiCad .kicad_pcb (PCB layout) files to extract component placements.

KiCad PCB files use S-expression format (human-readable), making them easier
to parse than binary Altium files.

New code should use :class:`kicad_monkey.KiCadPcb`. This module remains for
legacy parser-equivalency tests and does not provide generic model conversion.

Key Sections:
    - setup/aux_axis_origin: Board origin coordinates
    - footprint: Component placements with properties

Example:
    from kicad_monkey.kicad_pcb_parser import KiCadPcbDoc

    pcbdoc = KiCadPcbDoc.from_file("design.kicad_pcb")
    components = pcbdoc.components
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .kicad_base import FRONT_COPPER_LAYER
from .kicad_sexpr import parse_sexp

log = logging.getLogger(__name__)


def get_first_or_value(variable: Any) -> Any:
    """Get the first element of a list or return the value directly."""
    if isinstance(variable, list):
        if len(variable) > 0:
            return variable[0]
        return None
    return variable


@dataclass
class KiCadPcbComponent:
    """
    Component instance from KiCad .kicad_pcb file.

    This is a KiCad-specific representation that stores data in KiCad's format.

    Attributes:
        designator: Component reference (e.g., "R1", "U1")
        footprint: Footprint name (e.g., "R_0603_1608Metric")
        layer: Side of PCB ("TOP" or "BOTTOM")
        x_mm: X position in millimeters
        y_mm: Y position in millimeters
        rotation: Component rotation in degrees (0.0 to 360.0)
        dnp: True if component is marked Do Not Populate
        exclude_from_bom: True if component has KiCad exclude_from_bom attribute
        parameters: Dict of component properties from KiCad
        raw_sexp: Original S-expression data
    """
    designator: str
    footprint: str
    layer: str
    x_mm: float
    y_mm: float
    rotation: float = 0.0
    dnp: bool = False
    exclude_from_bom: bool = False
    parameters: dict[str, Any] | None = None
    raw_sexp: Any = None

    def __post_init__(self) -> None:
        """Initialize default mutable fields."""
        if self.parameters is None:
            self.parameters = {}

    def to_pcb_component(
        self,
        origin_x_mm: float = 0.0,
        origin_y_mm: float = 0.0,
        id: str | None = None
    ) -> Any:
        """
        Convert to generic CAD-agnostic PcbComponent data model.

        This legacy conversion hook was removed with the public API cleanup.
        Use ``kicad_monkey.KiCadPcb`` and
        ``data_models.converters.kicad.pcb_component_from_kicad_footprint()``
        instead.
        """
        _ = (origin_x_mm, origin_y_mm, id)
        raise RuntimeError(
            "KiCadPcbComponent.to_pcb_component() was removed. Parse with "
            "kicad_monkey.KiCadPcb and convert with "
            "data_models.converters.kicad.pcb_component_from_kicad_footprint()."
        )


class KiCadPcbDoc:
    """
    KiCad .kicad_pcb file parser.

    Parses KiCad PCB files to extract component placements and board info.

    Attributes:
        filepath: Path to .kicad_pcb file
        components: List of KiCadPcbComponent instances (KiCad-specific format)
        origin_x_mm: Board origin X coordinate in mm (from aux_axis_origin)
        origin_y_mm: Board origin Y coordinate in mm (from aux_axis_origin)

    Example:
        pcbdoc = KiCadPcbDoc.from_file("design.kicad_pcb")
        log.info(f"Found {len(pcbdoc.components)} components")

        # New conversion code should use kicad_monkey.KiCadPcb.
    """

    def __init__(self, filepath: Path) -> None:
        """
        Initialize KiCad PcbDoc parser.

        Args:
            filepath: Path to .kicad_pcb file
        """
        self.filepath = filepath
        self.components: list[KiCadPcbComponent] = []
        self.origin_x_mm: float = 0.0
        self.origin_y_mm: float = 0.0
        self.nets: dict[int, str] = {}  # net_id -> net_name

    @classmethod
    def from_file(cls, filepath: Path, verbose: bool = False) -> 'KiCadPcbDoc':
        """
        Parse a KiCad .kicad_pcb file.

        Args:
            filepath: Path to .kicad_pcb file
            verbose: If True, print detailed parsing info

        Returns:
            KiCadPcbDoc instance

        Raises:
            FileNotFoundError: If file doesn't exist
            Exception: If parsing fails
        """
        filepath = Path(filepath).resolve()

        if not filepath.exists():
            raise FileNotFoundError(f"KiCad PCB file not found: {filepath}")

        if verbose:
            log.info(f"Parsing KiCad PCB: {filepath.name}")

        pcbdoc = cls(filepath)
        pcbdoc._parse(verbose=verbose)

        if verbose:
            log.info(f"Parsed {len(pcbdoc.components)} components")

        return pcbdoc

    def _parse(self, verbose: bool = False) -> None:
        """
        Parse KiCad PCB file.

        Args:
            verbose: If True, print parsing progress
        """
        # Read and parse S-expression file
        with open(self.filepath, encoding='utf-8') as f:
            pcb_content = f.read()

        parsed = parse_sexp(pcb_content)

        # Parse board origin, nets, and components
        for item in parsed:
            # Parse setup section for board origin
            if get_first_or_value(item) == 'setup':
                self._parse_setup(item, verbose)

            # Parse net definitions
            if get_first_or_value(item) == 'net':
                self._parse_net(item, verbose)

            # Parse footprint section for components
            if get_first_or_value(item) == 'footprint':
                comp = self._parse_footprint(item, verbose)
                if comp:  # Skip components excluded from BOM
                    self.components.append(comp)

    def _parse_setup(self, setup_sexp: Any, verbose: bool) -> None:
        """Parse setup section for board origin."""
        for item in setup_sexp:
            if get_first_or_value(item) == 'aux_axis_origin':
                self.origin_x_mm = float(item[1])
                self.origin_y_mm = float(item[2])
                if verbose:
                    log.info(f"  Board origin: ({self.origin_x_mm}, {self.origin_y_mm}) mm")

    def _parse_net(self, net_sexp: Any, verbose: bool) -> None:
        """Parse net definition.

        Format: (net <id> "<name>")
        Example: (net 1 "GND")
        """
        if len(net_sexp) >= 3:
            net_id = int(net_sexp[1])
            net_name = net_sexp[2]
            self.nets[net_id] = net_name
            if verbose:
                log.info(f"  Net {net_id}: {net_name}")

    def _parse_footprint(self, footprint_sexp: Any, verbose: bool) -> KiCadPcbComponent | None:
        """
        Parse a footprint section to extract component data.

        Args:
            footprint_sexp: S-expression for footprint section
            verbose: If True, print parsing info

        Returns:
            KiCadPcbComponent or None if excluded from BOM
        """
        # Extract footprint name (part after colon)
        # e.g., "resistor:R0402_0.40MM_HD" -> "R0402_0.40MM_HD"
        footprint_full = footprint_sexp[1] if len(footprint_sexp) > 1 else ""
        footprint_name = footprint_full.split(':', 1)[1] if ':' in footprint_full else footprint_full

        # Extract component properties
        designator = self._get_reference(footprint_sexp)
        layer = self._get_layer(footprint_sexp)
        parameters = self._get_parameters(footprint_sexp)
        dnp = self._is_dnp(footprint_sexp)
        exclude_from_bom = self._is_exclude_from_bom(footprint_sexp)

        # Extract position and rotation
        x_mm, y_mm, rotation = self._get_position(footprint_sexp)

        if verbose:
            log.info(f"  Found component: {designator}")

        return KiCadPcbComponent(
            designator=designator,
            footprint=footprint_name,
            layer=layer,
            x_mm=x_mm,
            y_mm=y_mm,
            rotation=rotation,
            dnp=dnp,
            exclude_from_bom=exclude_from_bom,
            parameters=parameters,
            raw_sexp=footprint_sexp
        )

    @staticmethod
    def _get_reference(sexp_item: Any) -> str:
        """Extract reference designator from footprint S-expression."""
        for i in sexp_item:
            if get_first_or_value(i) == 'property':
                if i[1] == 'Reference':
                    return i[2]
        return ""

    @staticmethod
    def _get_parameters(sexp_item: Any) -> dict[str, str]:
        """Extract component properties from footprint S-expression."""
        result = {}
        for i in sexp_item:
            if get_first_or_value(i) == 'property':
                if i[1] != 'Reference':
                    result[i[1]] = i[2]
        return result

    @staticmethod
    def _get_layer(sexp_item: Any) -> str:
        """Extract layer from footprint S-expression."""
        for i in sexp_item:
            if get_first_or_value(i) == "layer":
                if FRONT_COPPER_LAYER in i[1]:
                    return "TOP"
                else:
                    return "BOTTOM"
        log.error("Layer not found in component")
        return "TOP"  # Default

    @staticmethod
    def _get_position(sexp_item: Any) -> tuple[float, float, float]:
        """
        Extract position and rotation from footprint S-expression.

        Returns:
            Tuple of (x_mm, y_mm, rotation_degrees)
        """
        for i in sexp_item:
            if get_first_or_value(i) == "at":
                x_mm = float(i[1])
                y_mm = float(i[2])
                # Rotation is optional (third element in 'at' field)
                rotation = float(i[3]) if len(i) > 3 else 0.0
                return (x_mm, y_mm, rotation)
        return (0.0, 0.0, 0.0)

    @staticmethod
    def _is_dnp(sexp_item: Any) -> bool:
        """Check if component is marked DNP."""
        for i in sexp_item:
            if "attr" in get_first_or_value(i):
                for a in i:
                    if "dnp" in get_first_or_value(a):
                        return True
        return False

    @staticmethod
    def _is_exclude_from_bom(sexp_item: Any) -> bool:
        """Check if component is excluded from BOM."""
        for i in sexp_item:
            if "attr" in get_first_or_value(i):
                for a in i:
                    if "exclude_from_bom" in get_first_or_value(a):
                        return True
        return False

    def to_pcb_components(self) -> list[Any]:
        """
        Convert all components to generic CAD-agnostic PcbComponent data models.

        This legacy conversion hook was removed with the public API cleanup.
        Use ``kicad_monkey.KiCadPcb`` and
        ``data_models.converters.kicad.pcb_components_from_kicad_pcb()``
        instead.
        """
        raise RuntimeError(
            "KiCadPcbDoc.to_pcb_components() was removed. Parse with "
            "kicad_monkey.KiCadPcb and convert with "
            "data_models.converters.kicad.pcb_components_from_kicad_pcb()."
        )

    def get_unique_footprints(self) -> set[str]:
        """
        Get unique footprint names used in the design.

        Returns:
            Set of unique footprint names
        """
        return {comp.footprint for comp in self.components if comp.footprint}

    def to_pcb_data(self) -> Any:
        """
        Convert KiCadPcbDoc to generic PCBData format.

        This legacy conversion hook was removed with the public API cleanup.
        Use ``kicad_monkey.KiCadPcb`` and the data_models KiCad converters
        instead.
        """
        raise RuntimeError(
            "KiCadPcbDoc.to_pcb_data() was removed. Parse with "
            "kicad_monkey.KiCadPcb and use the data_models KiCad converters."
        )

    def __str__(self) -> str:
        """String representation."""
        return f"KiCadPcbDoc({self.filepath.name}, {len(self.components)} components)"

    def __repr__(self) -> str:
        """Developer representation."""
        return f"KiCadPcbDoc(filepath={self.filepath}, components={len(self.components)})"


# ============================================================================
# Retired Legacy Wrapper
# ============================================================================

class KiCadPCBParser:
    """Retired wrapper retained only to fail legacy callers clearly."""

    def __init__(self) -> None:
        """Initialize parser."""
        pass

    def parse_file(self, pcb_path: Path, pro_path: Path | None = None) -> Any:
        """
        Parse KiCad PCB file to generic PCBData format.

        This legacy wrapper was removed with the public API cleanup.
        """
        _ = (pcb_path, pro_path)
        raise RuntimeError(
            "KiCadPCBParser.parse_file() was removed. Use kicad_monkey.KiCadPcb "
            "and the data_models KiCad converters."
        )

    def _parse_netclasses_from_pro(self, pro_path: Path, nets: dict[int, str]) -> dict[str, list[int]]:
        """
        Parse netclass assignments from .kicad_pro file.

        Args:
            pro_path: Path to .kicad_pro file
            nets: Dict of {net_id: net_name} from PCBData

        Returns:
            Dict of {netclass_name: [net_ids]}

        Note:
            KiCad .kicad_pro format: {net_name: [netclass_names]}
            We need to invert this to: {netclass_name: [net_ids]}
        """
        import json

        # Create reverse lookup: net_name -> net_id
        net_name_to_id = {name: net_id for net_id, name in nets.items()}

        # Read .kicad_pro file
        with open(pro_path, encoding='utf-8') as f:
            pro_data = json.load(f)

        # Get netclass assignments: {net_name: [netclass_names]}
        netclass_assignments = pro_data.get('net_settings', {}).get('netclass_assignments', {})
        if not netclass_assignments:
            return {}

        # Invert to {netclass_name: [net_ids]}
        netclasses: dict[str, list[int]] = {}
        unmatched_nets = []

        for net_name, netclass_list in netclass_assignments.items():
            # Try exact match first
            net_id = net_name_to_id.get(net_name)

            # If no exact match, try suffix matching (for hierarchical path differences)
            # e.g., "/ADC/CLK+" in .pro might be "/TOP_LEVEL_IO/ADC/CLK+" in .pcb
            if net_id is None:
                # Only try suffix match if the net name looks like a hierarchical path
                if '/' in net_name:
                    for pcb_net_name, pcb_net_id in net_name_to_id.items():
                        # Check if PCB net name ends with the .pro net name
                        # This handles "/ADC/CLK+" matching "/TOP_LEVEL_IO/ADC/CLK+"
                        if pcb_net_name.endswith(net_name):
                            net_id = pcb_net_id
                            break

            if net_id is None:
                # Net name not found in PCB - may be removed or renamed net
                unmatched_nets.append(net_name)
                continue

            # Add this net ID to each netclass it belongs to
            for netclass_name in netclass_list:
                if netclass_name not in netclasses:
                    netclasses[netclass_name] = []
                netclasses[netclass_name].append(net_id)

        # Log unmatched nets if verbose mode was enabled
        if unmatched_nets and len(unmatched_nets) < 10:
            # Don't spam if there are many unmatched (likely old/removed nets)
            log.warning(f"Could not match {len(unmatched_nets)} nets from .kicad_pro to .kicad_pcb")

        return netclasses
