"""
KiCad project / design aggregator (Phase F-6.5 follow-on).

A :class:`KiCadDesign` ties together the three on-disk artefacts that
make up a single KiCad project:

* ``.kicad_pro`` — :class:`KiCadProject` (text variables, net settings,
  variant catalog).
* ``.kicad_sch`` — one or more :class:`KiCadSchematic` instances. The
  parser already recurses into sub-sheets via ``Sheetfile``; this
  class is the aggregator that owns the top-level entry sheet plus a
  cache of any explicitly-loaded extras.
* ``.kicad_pcb`` — lazy :class:`KiCadPcb`. Loaded on first access so
  schematic-only workflows don't pay the parse cost.

The primary motivation is **cross-document ``${VAR}`` resolution**:
title-block text in ``.kicad_sch`` / ``.kicad_pcb`` may reference
custom variables defined under ``text_variables`` in the sidecar
``.kicad_pro``. F-6.5 already plumbed the ``project_vars`` dict
through :func:`drawing_sheet_to_ops` and :func:`schematic_to_ir`;
:class:`KiCadDesign` is the seam that fills that dict in automatically.
KiCad's built-in sheet/title variables still take precedence over
same-named project text variables.

Parallel to ``altium_monkey``'s :class:`AltiumDesign`. Intentionally
minimal in this slice: typed views over the underlying parsers, a
single drop-in :meth:`to_schematic_ir` wrapper, and the discovery
helpers needed to walk a project from any of its file types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Optional

from ._api_markers import public_api
from .kicad_project import (
    KiCadProject,
    find_adjacent_kicad_project_path,
)

if TYPE_CHECKING:
    from .kicad_netlist_model import KiCadNet, KiCadNetlist, KiCadNetlistComponent
    from .kicad_pcb import KiCadPcb
    from .kicad_plotter_ir import KiCadPlotterDocument
    from .kicad_schematic import KiCadSchematic


@public_api
@dataclass
class KiCadDesign:
    """Composed KiCad design: project + schematics + (lazy) PCB.

    Construct via the ``from_*`` classmethods; direct construction is
    supported for tests but won't auto-populate adjacent files.
    """

    project: Optional[KiCadProject] = None
    schematics: list["KiCadSchematic"] = field(default_factory=list)
    pcb_path: Optional[Path] = None
    project_path: Optional[Path] = None
    _pcb: Optional["KiCadPcb"] = field(default=None, repr=False)
    _netlist: Optional["KiCadNetlist"] = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    @public_api
    def from_file(cls, path: Path | str) -> "KiCadDesign":
        """Load a design from a `.kicad_pro`, `.kicad_sch`, or `.kicad_pcb` path."""
        source_path = Path(path)
        suffix = source_path.suffix.lower()
        if suffix == ".kicad_pro":
            return cls.from_project_file(source_path)
        if suffix == ".kicad_sch":
            return cls.from_schematic_file(source_path)
        if suffix == ".kicad_pcb":
            return cls.from_pcb_file(source_path)
        raise ValueError(
            f"unsupported KiCad design file suffix {source_path.suffix!r}; "
            "expected .kicad_pro, .kicad_sch, or .kicad_pcb"
        )

    @classmethod
    @public_api
    def from_project_file(cls, path: Path | str) -> "KiCadDesign":
        """Load `.kicad_pro` and any adjacent top-level `.kicad_sch` /
        `.kicad_pcb` (matched by stem). Sub-sheets are pulled in
        recursively via the schematic parser.
        """
        from .kicad_schematic import KiCadSchematic

        project_path = Path(path)
        project = KiCadProject.from_file(project_path)

        stem = project_path.stem
        parent = project_path.parent
        sch_candidate = parent / f"{stem}.kicad_sch"
        pcb_candidate = parent / f"{stem}.kicad_pcb"

        schematics: list[KiCadSchematic] = []
        if sch_candidate.is_file():
            schematics.append(KiCadSchematic(sch_candidate))

        pcb_path = pcb_candidate if pcb_candidate.is_file() else None

        return cls(
            project=project,
            schematics=schematics,
            pcb_path=pcb_path,
            project_path=project_path,
        )

    @classmethod
    @public_api
    def from_schematic_file(cls, path: Path | str) -> "KiCadDesign":
        """Load a `.kicad_sch` (with recursive sub-sheets) and any
        adjacent `.kicad_pro` discovered by stem / single-sibling rule.
        """
        from .kicad_schematic import KiCadSchematic

        sch_path = Path(path)
        sch = KiCadSchematic(sch_path)
        project_path = find_adjacent_kicad_project_path(sch_path)
        project = KiCadProject.from_file(project_path) if project_path else None
        return cls(
            project=project,
            schematics=[sch],
            pcb_path=None,
            project_path=project_path,
        )

    @classmethod
    @public_api
    def from_pcb_file(cls, path: Path | str) -> "KiCadDesign":
        """Load a `.kicad_pcb` (lazily) and any adjacent `.kicad_pro`
        discovered by stem / single-sibling rule.
        """
        pcb_path = Path(path)
        project_path = find_adjacent_kicad_project_path(pcb_path)
        project = KiCadProject.from_file(project_path) if project_path else None
        return cls(
            project=project,
            schematics=[],
            pcb_path=pcb_path,
            project_path=project_path,
        )

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def text_variables(self) -> dict[str, str]:
        """Project-scoped ``${VAR}`` substitutions.

        Empty dict when no `.kicad_pro` is associated. Returns a copy
        so callers can mutate freely without poisoning the project's
        own dict.
        """
        if self.project is None:
            return {}
        return dict(self.project.text_variables)

    @property
    def pcb(self) -> Optional["KiCadPcb"]:
        """Loaded :class:`KiCadPcb`, parsing on first access."""
        if self._pcb is not None:
            return self._pcb
        if self.pcb_path is None:
            return None
        from .kicad_pcb import KiCadPcb

        self._pcb = KiCadPcb(self.pcb_path)
        return self._pcb

    @property
    def top_schematic(self) -> Optional["KiCadSchematic"]:
        """First-loaded entry-point schematic, if any."""
        return self.schematics[0] if self.schematics else None

    @public_api
    def iter_schematics(self) -> Iterator["KiCadSchematic"]:
        """Iterate over schematics owned by this design."""
        return iter(self.schematics)

    @public_api
    def add_schematic(self, schematic: "KiCadSchematic") -> "KiCadSchematic":
        """Append a schematic to this design."""
        self.schematics.append(schematic)
        self._netlist = None
        return schematic

    @public_api
    def remove_schematic(self, schematic: "KiCadSchematic") -> bool:
        """Remove a schematic by identity."""
        for index, candidate in enumerate(self.schematics):
            if candidate is schematic:
                del self.schematics[index]
                self._netlist = None
                return True
        return False

    @public_api
    def iter_objects(self, *, include_pcb: bool = True) -> Iterator[object]:
        """Iterate over project, schematic, and optional PCB documents."""
        if self.project is not None:
            yield self.project
        yield from self.schematics
        if include_pcb:
            pcb = self.pcb
            if pcb is not None:
                yield pcb

    @public_api
    @property
    def objects(self):
        """Live read-only query view over design-owned documents."""
        from .kicad_object_collection import KiCadObjectCollection

        return KiCadObjectCollection(lambda: self.iter_objects(), owner=self)

    # ------------------------------------------------------------------
    # IR convenience
    # ------------------------------------------------------------------

    def to_schematic_ir(
        self,
        schematic: Optional["KiCadSchematic"] = None,
        *,
        sheet_index: int = 1,
        sheet_count: int = 1,
        sheet_path: str = "/",
        sheet_instance_path: Optional[str] = None,
        sheet_name: str = "",
        document_id: Optional[str] = None,
        extra_vars: Optional[dict] = None,
    ) -> "KiCadPlotterDocument":
        """Convert a schematic to a :class:`KiCadPlotterDocument` with
        ``project_vars`` automatically populated from the project's
        ``text_variables``.

        ``extra_vars`` overrides project-level text variables when
        supplied. KiCad built-in sheet/title variables still take
        precedence over same-named project text variables. If
        ``schematic`` is ``None`` the design's :attr:`top_schematic`
        is used.
        """
        from .kicad_schematic_to_ir import schematic_to_ir

        target = schematic if schematic is not None else self.top_schematic
        if target is None:
            raise ValueError(
                "no schematic supplied and design has no top schematic loaded"
            )

        merged: dict[str, str] = self.text_variables
        if extra_vars:
            merged.update({str(k): str(v) for k, v in extra_vars.items()})

        source_path = None
        if getattr(target, "source_path", None) is not None:
            source_path = str(target.source_path)

        return schematic_to_ir(
            target,
            source_path=source_path,
            document_id=document_id,
            sheet_index=sheet_index,
            sheet_count=sheet_count,
            sheet_path=sheet_path,
            sheet_instance_path=sheet_instance_path,
            sheet_name=sheet_name,
            project_vars=merged,
        )

    @public_api
    def to_pcb_ir(
        self,
        *,
        document_id: Optional[str] = None,
    ) -> "KiCadPlotterDocument":
        """Convert the associated PCB to plotter IR."""
        pcb = self.pcb
        if pcb is None:
            raise ValueError("design has no PCB loaded or associated")
        source_path = str(self.pcb_path) if self.pcb_path is not None else None
        return pcb.to_ir(source_path=source_path, document_id=document_id)

    @public_api
    def to_pcb_svg(self, **kwargs) -> str:
        """Render the associated PCB to SVG."""
        pcb = self.pcb
        if pcb is None:
            raise ValueError("design has no PCB loaded or associated")
        return pcb.to_svg(**kwargs)


    # ------------------------------------------------------------------
    # Netlist API — Phase G Slice N-7
    # ------------------------------------------------------------------

    def to_netlist(self) -> "KiCadNetlist":
        """Compile (and cache) the unified design netlist.

        Walks the entry-point schematic recursively via
        :func:`compile_design_netlist`, returning a fully-populated
        :class:`KiCadNetlist` (nets / components / libparts /
        design_metadata.sheets). Subsequent calls return the cached
        instance — call :meth:`refresh_netlist` to discard the cache
        and recompile (useful when the underlying schematics have been
        edited in place).

        Raises:
            ValueError: when the design has no top schematic loaded.
        """
        if self._netlist is None:
            self._netlist = self._compile_netlist()
        return self._netlist

    def refresh_netlist(self) -> "KiCadNetlist":
        """Discard the cached netlist and recompile from scratch."""
        self._netlist = None
        return self.to_netlist()

    def to_kicad_netlist_sexpr(
        self,
        *,
        tool: str = "kicad_monkey",
        date: Optional[str] = None,
    ) -> str:
        """Render the design as a kicad-cli–style ``(export ...)`` netlist.

        The ``(source ...)`` line is filled with the top schematic's
        absolute path when known. ``tool`` and ``date`` mirror
        :func:`to_kicad_sexpr` semantics — pass ``date=""`` to suppress
        the timestamp (useful for byte-stable test goldens).
        """
        from .kicad_netlist_kicadsexpr import to_kicad_sexpr

        netlist = self.to_netlist()
        source_path = ""
        top = self.top_schematic
        if top is not None and getattr(top, "source_path", None) is not None:
            source_path = str(top.source_path)
        return to_kicad_sexpr(
            netlist,
            source_path=source_path,
            tool=tool,
            date=date,
        )

    def to_netlist_json(self) -> dict:
        """Render the design as a generic ``netlist_a0`` JSON dict.

        Bridges through ``data_models.Netlist.to_json`` so consumers
        (sch-viz, BOM, exporters) can validate against the cross-CAD
        contract.
        """
        from .kicad_netlist_data_models import (
            kicad_netlist_to_data_models_netlist,
        )

        return kicad_netlist_to_data_models_netlist(self.to_netlist()).to_json()

    def to_json(self, include_indexes: bool = True) -> dict:
        """Render a KiCad-native, Altium-shaped design JSON payload.

        This is intentionally distinct from :meth:`to_netlist_json`, which
        remains the generic ``data_models`` bridge.  The payload returned here
        uses KiCad-owned schema IDs while mirroring the top-level terminology
        used by ``altium_monkey.design.a1`` for cross-CAD comparisons and
        future schematic-visualizer integration.
        """
        from .kicad_design_json import kicad_design_to_json

        return kicad_design_to_json(self, include_indexes=include_indexes)

    def to_json_text(self, *, include_indexes: bool = True, indent: int = 2) -> str:
        """Render :meth:`to_json` as formatted JSON text."""
        return json.dumps(
            self.to_json(include_indexes=include_indexes),
            indent=indent,
            ensure_ascii=False,
        ) + "\n"

    def save_json(
        self,
        path: Path | str,
        *,
        include_indexes: bool = True,
        indent: int = 2,
    ) -> None:
        """Write :meth:`to_json_text` to disk."""
        Path(path).write_text(
            self.to_json_text(include_indexes=include_indexes, indent=indent),
            encoding="utf-8",
        )

    def to_kicad_netlist_json(self) -> dict:
        """Render the internal netlist as a KiCad-native raw JSON payload."""
        from .kicad_design_json import kicad_netlist_to_json

        return kicad_netlist_to_json(self.to_netlist())

    def get_net(self, name: str) -> Optional["KiCadNet"]:
        """Look up a net by name (parity with altium_monkey)."""
        return self.to_netlist().get_net(name)

    def get_component(self, reference: str) -> Optional["KiCadNetlistComponent"]:
        """Look up a component by reference designator."""
        return self.to_netlist().get_component(reference)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compile_netlist(self) -> "KiCadNetlist":
        from .kicad_netlist_design import compile_design_netlist
        from .kicad_netlist_project import apply_project_net_classes

        top = self.top_schematic
        if top is None:
            raise ValueError(
                "cannot compile netlist: design has no top schematic loaded"
            )

        # Multi-unit ref suffixing follows the project's schematic
        # settings (subpart_first_id / subpart_id_separator). Defaults
        # (``A``, no separator) match KiCad's own defaults when no
        # ``.kicad_pro`` is loaded.
        subpart_first_id = ord("A")
        subpart_id_separator = 0
        project = self.project
        if project is not None:
            v = project.get_path("schematic.subpart_first_id")
            if isinstance(v, int):
                subpart_first_id = v
            v = project.get_path("schematic.subpart_id_separator")
            if isinstance(v, int):
                subpart_id_separator = v

        netlist = compile_design_netlist(
            top, self.text_variables,
            subpart_first_id=subpart_first_id,
            subpart_id_separator=subpart_id_separator,
        )
        # Slice N-10: project-side enrichment (net classes from .kicad_pro).
        # No-op when no .kicad_pro is loaded.
        apply_project_net_classes(netlist, self.project)
        return netlist


__all__ = ["KiCadDesign"]
