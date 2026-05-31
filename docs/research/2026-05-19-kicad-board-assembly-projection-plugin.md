# KiCad Board Assembly Projection Plugin Evaluation

Date: 2026-05-19
Status: research note / recommended plugin spike

Implementation update: the installable plugin plan now targets
footprint-local HLR graphics first so generated outlines move with parts during
placement. The board-level path below remains useful as a lower-risk IPC/write-back
debugging fallback and report/overlay path, but it is no longer the first
product workflow.

## Verdict

This is a feasible and useful first registered KiCad plugin, but the scope
should be split carefully.

Start with a board-level assembly projection action:

1. connect to the active KiCad board through the IPC plugin action
2. acquire the live board text with `Board.get_as_string()`
3. hydrate `kicad_monkey.KiCadPcb`
4. extract embedded STEP model bytes and KiCad model placement metadata
5. run geometer HLR projection
6. write generated board-level graphics onto configured user/fab layers through
   KiCad IPC
7. record generated item ids in a sidecar manifest so reruns can clean only our
   generated objects

Do not start by broadly wiping all user drawing layers or rewriting the open PCB
file on disk. KiCad owns the open document. Mutate the live board through IPC
and keep the generated graphics cleanup narrow.

## Existing Code Assets

`kicad_monkey` already has most of the KiCad data-side pieces:

- `kicad_filter_footprint.py`
  - `fp_filter__clean_layers(...)` removes footprint-local graphics from
    `F.Fab`, `B.Fab`, `User.*`, and Eco layers.
  - `fp_filter__orthographic_projection_outline(...)` already extracts embedded
    STEP payloads, decodes KiCad's base64/zstd embedded data, applies model
    offset/scale/rotation, flattens with Trimesh/Shapely, and adds footprint
    fab-layer `fp_line` geometry.
- `kicad_model.py`
  - parses `model` path, `offset`, `scale`, `rotate`
  - parses embedded file payloads
- `data_models.converters.kicad_stackup`
  - resolves external model search roots
  - maps footprint model refs into `PcbEmbedded3DModel`
  - preserves KiCad model offset/scale/rotation metadata
  - has component-owned placement math for the 3D viz model path

That means the plugin should not create a second KiCad parser. It should reuse
the existing board string -> `KiCadPcb` path and replace the old Trimesh
projection backend with the geometer HLR contract.

## 3D Viz Worktree Reference

The `C:/eli/agent-worktrees/3d-viz-rework/toolz` worktree has two important
references for this plugin.

First, `pcb_cruncher/src/py/pcb_cruncher/pcb_cruncher_cmd_pcb_a0.py` already
uses the intended KiCad boundary:

```text
KiCad .kicad_pcb/.kicad_pro
  -> kicad_monkey.KiCadPcb / KiCadDesign
  -> data_models.converters.kicad_stackup.pcb_from_kicad_pcb(...)
  -> pcb_a0 JSON
```

Second, `data_models/src/py/data_models/converters/kicad_stackup.py` contains
the prototype KiCad model placement logic we should reuse rather than recode:

- `_kicad_model_offset_to_board_mm(...)` projects KiCad footprint model offsets
  into the generic Y-up board frame.
- Bottom-side placement mirrors the local Y contribution, matching the comment
  that KiCad applies `Rz(footprint) * Ry(pi) * Rz(pi)` before the model-local
  offset.
- `_models_3d_from_kicad_footprints(...)` flattens footprint model references
  into component-owned `PcbEmbedded3DModel` records.
- It stores board-space `offset_x_nm` / `offset_y_nm`, model `offset_z_nm`,
  negated KiCad rotations, scale, side, source ids, and metadata:
  - `model_2d_rotation`
  - `kicad_model_offset_mm`
  - `kicad_model_rotation_deg`
  - `kicad_model_transform_order`

The transform-order metadata is the key reference for the assembly projection
plugin:

```text
T_footprint Rz_footprint bottom_flip T_model Rz(-model_z) Ry(-model_y) Rx(-model_x) S
```

The plugin should factor or call the same KiCad pose logic to produce both:

- the `PcbEmbedded3DModel` records consumed by viz
- the pre-HLR model transform consumed by assembly projection generation

Do not make `PcbEmbedded3DModel` itself the only pose contract. It is the
viewer payload shape, not the complete transform authority. Add a generic
KiCad model pose builder that emits a source-level pose record first, then
derive downstream payloads from that record:

- `matrix_4x4_mm`: the full KiCad model-to-board transform, including
  footprint placement, bottom-side transform, model offset, model rotations,
  and scale
- `pose_signature`: a stable rounded tuple/hash for projection and mesh cache
  keys
- source metadata: footprint UUID/reference, component reference, model path,
  embedded-file reference, side, and transform-order label
- adapters:
  - `to_pcb_a0_model(...)` for the existing viz model payload
  - `to_geometer_transform(...)` for a future geometer transform option
  - direct matrix consumption by the Python/OCP reference backend

That keeps KiCad pose math in one place. The Python reference implementation,
the current `pcb_a0` converter, and the future geometer integration should all
consume the same pose object instead of recomputing placement independently.

The 3D-viz worktree also carries a newer
`emit_component_geometry_at_board_scope` option in `pcb_from_kicad_pcb(...)`.
That is useful for viewer payload shape, but the assembly projection plugin
does not depend on it. The model pose logic is the part to share.

There is also an older, Altium-oriented projection implementation worth using
as a mechanics reference:

- `viz/src/py/viz/altium_pcb_svg_assembly_projection.py`
  - caches by model hash + projection settings + pose signature
  - loads STEP once
  - applies a `transform_matrix` to the OCCT shape with
    `BRepBuilderAPI_Transform`
  - then runs HLR on the transformed shape
- `viz/src/py/viz/altium_pcb_gltf_renderer.py`
  - composes STEP instance transforms before render/projection
  - uses a pose signature so repeated models share cached projection geometry

Do not copy the Altium transform formula for KiCad; use the KiCad converter's
transform order. The transferable lesson is the mechanics: cache by pose,
pre-transform the 3D shape, then run HLR.

## Geometer Fit

The current geometer worktree already exposes the right projection primitive:

- CLI:
  - `geometer step-project-hlr input.step output.json`
  - `geometer step-project-svg input.step output.svg --mode simple --view top`
  - `geometer step-project-svg input.step output.svg --mode detail --curve-mode native-arcs`
- C/C++/WASM API:
  - `step_hlr_projection_from_bytes(...)`
  - C ABI byte-buffer functions
  - browser and non-browser WASM artifacts
- output schema:
  - `geometry.projection.a0`
  - per-view `simple` and `detail`
  - line segments and native arcs when requested

The local geometer perf note says the poly HLR path is now the default and
keeps the HLR phase in the interactive range for the 36-model corpus. Heavy
models are still dominated by STEP read/mesh time, so the plugin must cache by:

- STEP payload hash
- model transform
- view spec
- simple/detail mode
- HLR options

Important gap: geometer's public HLR options currently accept views and HLR
quality settings, but not a model pose/transform matrix. The 3D-viz worktree's
OCP projection path proves the right mechanics: transform the shape first, then
run HLR. For correct KiCad assembly projections, geometer needs the same
capability because KiCad model rotations can include X/Y rotations and
non-uniform scale. The production fix is to add a geometer option/API for a
model transform or pre-transform the OCCT shape before projection.

For a first smoke test, it is acceptable to prove the IPC write path with
identity or simple Z-only transformed models, but that should be marked as a
temporary restriction.

## KiCad IPC Write-Back Fit

Local `kicad-python` introspection confirms the PCB write primitives we need:

- `BoardSegment`
- `BoardArc`
- `BoardCircle`
- `BoardPolygon`
- `BoardText`
- `BoardTextBox`
- `GraphicAttributes` / `StrokeAttributes`
- `BoardLayer` enum entries for `BL_Dwgs_User`, `BL_Eco1_User`,
  `BL_Eco2_User`, `BL_F_Fab`, `BL_B_Fab`, and `BL_User_1` through
  `BL_User_44`

The board API exposes:

- `board.create_items(...)`
- `board.update_items(...)`
- `board.remove_items(...)`
- `board.remove_items_by_id(...)`
- `board.begin_commit()`
- `board.push_commit(...)`
- `board.drop_commit(...)`

So the first plugin can write board-level generated graphics with undo/redo
support and without touching the board file behind KiCad.

## Board-Level Versus Footprint-Local

Use board-level graphics first.

Advantages:

- safest IPC mutation path
- easy to group into one undo operation
- does not mutate library footprints
- avoids writing an open board file directly
- works naturally for a board-level "assembly drawing" artifact

Tradeoff:

- if the user moves a footprint after generation, board-level generated lines do
  not follow it automatically.

That tradeoff is acceptable for v1. Rerun the action after placement changes, or
later add a low-rate refresh mode. Footprint-local graphics that follow the
component are a second phase, after proving nested footprint graphics can be
created/removed reliably through IPC. Offline footprint-library filtering can
continue to use the existing file-based filter path.

## Cleaning Strategy

Do not default to "delete all drawings from User.* / F.Fab / B.Fab" at board
level. That is too destructive for real boards.

Recommended cleanup layers:

1. Maintain a project sidecar manifest, for example:
   `.wavenumber/kicad_assembly_projection.json`
2. Store:
   - generated board item KIIDs
   - source board digest
   - footprint UUID/reference
   - target layer
   - source model hash
   - HLR options hash
3. On rerun, remove items by recorded KIID first.
4. If a recorded item no longer exists, ignore it.
5. Offer an explicit "force clean target layers" option for recovery, but keep
   it opt-in and scoped to configured target layers.

If KiCad groups are exposed well enough through IPC, grouping generated items
under a named group such as `wn:assembly-projection:<board-digest>` would be a
useful second cleanup anchor. Do not rely on group support until it is proven in
a smoke test.

## Suggested User Controls

Minimum first version:

- target top layer: default one dedicated user layer, not `F.Fab`
- target bottom layer: default one dedicated user layer, not `B.Fab`
- side selection: top, bottom, or both
- clean previous generated projection: on by default
- default mode: `simple`
- selected refs/libraries in `detail`
- line width
- curve mode: native arcs or polyline
- source model scope: embedded STEP only

Later:

- preview generated projection before apply
- per-part config table
- skip excluded/DNP parts
- include reference/value text
- use fab layers instead of user layers when explicitly selected
- external model resolution roots

The preview should be a local browser/canvas page fed by the same
`geometry.projection.a0` result that would be written to KiCad. It does not need
to be a KiCad-native wx dialog for the first implementation.

## Geometry Backend Options

### Option A: call existing geometer from the plugin

Recommended for the first real spike.

Use the geometer CLI or C ABI as the projection backend and keep the KiCad
plugin focused on orchestration, caching, cleanup, and IPC write-back.

Pros:

- reuses the code already designed for HLR
- keeps `geometry.projection.a0` as the boundary
- avoids duplicating OCCT HLR logic in Python
- lets browser/viz and KiCad plugin consume the same projection schema

Cons:

- current native `dist/geometer.exe` is Windows-only in practice
- cross-platform distribution requires geometer native builds, wheels, or a
  robust WASM runner story
- geometer needs a model-transform option/API for correct KiCad poses

### Option B: Python/OCP reference backend in kicad_monkey

Recommended as a validation/reference backend, not as the default production
plugin dependency.

As of 2026-05-19, `cadquery-ocp` 7.9.3.1 is on PyPI with binary wheels for
CPython 3.10-3.13 on Windows x86-64, Linux x86-64/aarch64, and macOS
x86-64/arm64. That fits KiCad's Python plugin manager better than conda-only
packages because KiCad creates a per-plugin venv and installs from
`requirements.txt`.

Use this backend to validate pose math and projection parity while geometer
remains the intended production HLR engine. It should expose the same backend
contract as geometer:

```python
class ReferenceOcctProjectionBackend(AssemblyProjectionBackend):
    def project_step(
        self,
        step_bytes: bytes,
        *,
        pose: KiCadModelPose,
        options: dict,
    ) -> dict:
        ...
```

Internal mechanics should mirror the geometer approach:

- load STEP bytes through OCP/OCCT
- apply `pose.matrix_4x4_mm` to the shape with `BRepBuilderAPI_Transform`
- run OCCT HLR, initially `HLRBRep_Algo`
- emit the same `geometry.projection.a0` shape and an optional dev SVG

This gives us a Python-only place to inspect matrices, dump overlays, and
compare pose-sensitive results for top, bottom, rotated, offset, and scaled
models. It also proves the exact transform payload that geometer should accept
later.

Risks:

- large binary dependency
- must match the Python version KiCad uses for plugin venvs
- would duplicate geometer's HLR extraction, snapping, simple/detail schema,
  and perf tuning if it becomes production code
- packaging failure modes move into the KiCad plugin install path if it is
  accidentally required by the normal plugin

Guard it behind an optional extra such as `kicad_monkey[occt-reference]` and
keep normal plugin installs independent of OCP unless we explicitly decide to
ship that dependency later.

### Option C: pythonocc-core through conda

Useful for local experiments, not a good PCM/plugin dependency. Current
`pythonocc-core` is available through conda-forge on Windows, macOS, and Linux,
but KiCad's plugin venv flow is pip/requirements based, not conda based.

### Option D: package geometer as Python wheels

Best long-term distribution story.

Build a small `geometer-python` package exposing the existing C ABI and ship
platform wheels. Then the plugin can depend on that package in
`requirements.txt` while all HLR logic remains in geometer.

## Recommended Implementation Shape

Keep the layers separate:

- `kicad_monkey.assembly_projection`
  - board text hydration helpers
  - embedded model extraction
  - generic KiCad model pose calculation shared with the `pcb_a0` converter,
    Python/OCP reference backend, and future geometer transform API
  - projection cache keys
  - optional `reference_occt` backend guarded behind an extra dependency
  - conversion from `geometry.projection.a0` to generated KiCad item records
- `kicad_monkey.ipc`
  - lazy `kipy` imports
  - current board capture
  - typed IPC write/remove helpers
- plugin package
  - `plugin.json`
  - action entrypoint
  - config loading
  - report/preview launching
  - logging
- geometer
  - HLR backend
  - model transform support
  - native/WASM/wheel distribution

Proposed core API:

```python
@dataclass(frozen=True)
class AssemblyProjectionConfig:
    top_layer: str
    bottom_layer: str
    default_mode: str = "simple"
    detail_refs: tuple[str, ...] = ()
    clean_previous: bool = True
    line_width_mm: float = 0.12
    curve_mode: str = "native_arcs"
    source_scope: str = "embedded_step"


@dataclass(frozen=True)
class KiCadModelPose:
    matrix_4x4_mm: tuple[tuple[float, float, float, float], ...]
    pose_signature: tuple[float, ...]
    side: str
    transform_order: str
    source_ref: dict[str, str]

    def to_geometer_transform(self) -> dict:
        ...


class AssemblyProjectionBackend:
    def project_step(self, step_bytes: bytes, *, pose: KiCadModelPose, options: dict) -> dict:
        ...


class ReferenceOcctProjectionBackend(AssemblyProjectionBackend):
    def project_step(self, step_bytes: bytes, *, pose: KiCadModelPose, options: dict) -> dict:
        ...


class KiCadAssemblyProjectionWriter:
    def remove_previous(self, manifest: ProjectionManifest) -> None:
        ...

    def create_projection_items(self, items: list[GeneratedProjectionItem]) -> list[str]:
        ...
```

## Spike Plan

1. Pose builder and Python/OCP reference spike
   - Factor the KiCad pose builder from the `pcb_a0` converter so projection
     and viz consume the same transform contract.
   - Emit a `KiCadModelPose` with a full 4x4 matrix and stable pose signature.
   - Add a Python/OCP reference backend in `kicad_monkey` behind an optional
     dependency.
   - Project one embedded STEP through the reference backend and emit JSON plus
     a dev SVG.

2. One-footprint geometer smoke test
   - Parse a board string or `.kicad_pcb`.
   - Pick one footprint with embedded STEP.
   - Decode the model bytes.
   - Run geometer HLR to JSON and SVG.
   - For the first smoke test, allow identity/simple-Z-only transforms if
     geometer has not accepted the generic pose transform yet.
   - Do not write KiCad yet.

3. IPC write spike
   - Convert simple projection segments/arcs to `BoardSegment` / `BoardArc`.
   - Write to `BL_User_1` or another explicitly configured layer.
   - Wrap create calls in one KiCad commit.
   - Verify undo removes the generated graphics.

4. Cleanup spike
   - Store generated KIIDs in the sidecar manifest.
   - Rerun and remove old generated items by id before writing new ones.
   - Add an explicit force-clean-target-layer recovery path.

5. Pose fidelity and geometer parity spike
   - Add geometer model-transform support or an equivalent pre-transform path.
   - Feed geometer from `KiCadModelPose.to_geometer_transform(...)`; do not
     add a second KiCad pose calculation inside the geometer integration.
   - Compare Python/OCP reference output against geometer output for the same
     embedded STEP bytes, view, options, and pose signature.
   - Compare generated projection against the existing
     `fp_filter__orthographic_projection_outline(...)` output for a corpus of
     embedded models with nonzero offset/scale/rotation.

6. Board plugin v1
   - Registered action.
   - Embedded STEP only.
   - Board-level generated graphics only.
   - Simple/detail per ref from config.
   - Basic HTML/JSON report.

7. UI/preview
   - Local browser preview using the generated `geometry.projection.a0`.
   - Config editing for target layers, clean mode, simple/detail overrides, and
     source selection.

## Hard Walls / Things To Prove

- Whether KiCad IPC exposes enough group support to use groups as a cleanup
  anchor. Do not assume it for v1.
- Exact `BoardArc` construction semantics from geometer arc center/start/end.
- Correct unit and axis mapping from geometer mm/Y-up output into KiCad board
  coordinates.
- Correct bottom-side mirroring and footprint rotation for board-level output.
- Shared KiCad pose-builder parity between `pcb_a0` model output and generated
  assembly projections.
- Python/OCP reference backend must stay optional/test-oriented unless we make
  an explicit distribution decision.
- Reference and geometer backends must emit the same projection schema; no
  private reference-only geometry contract.
- Geometer model-transform support for X/Y rotations and non-uniform scale.
- Cross-platform geometer distribution. Windows-only CLI is fine for an
  internal first spike, but not for a distributable plugin.

## Sources Checked

Local source:

- `toolz/kicad_monkey/src/py/kicad_monkey/kicad_filter_footprint.py`
- `toolz/kicad_monkey/src/py/kicad_monkey/kicad_model.py`
- `toolz/data_models/src/py/data_models/converters/kicad_stackup.py`
- `C:/eli/agent-worktrees/3d-viz-rework/toolz/pcb_cruncher/src/py/pcb_cruncher/pcb_cruncher_cmd_pcb_a0.py`
- `C:/eli/agent-worktrees/3d-viz-rework/toolz/data_models/src/py/data_models/converters/kicad_stackup.py`
- `C:/eli/agent-worktrees/3d-viz-rework/toolz/viz/src/py/viz/altium_pcb_svg_assembly_projection.py`
- `C:/eli/agent-worktrees/3d-viz-rework/toolz/viz/src/py/viz/altium_pcb_gltf_renderer.py`
- `C:/eli/agent-worktrees/3d-viz-rework/geometer/INTERFACES.md`
- `C:/eli/agent-worktrees/3d-viz-rework/geometer/docs/requirements/002_step_hlr_projection.md`
- `C:/eli/agent-worktrees/3d-viz-rework/geometer/src/cpp/lib/geometer/projection.h`

External/current package sources:

- `cadquery-ocp` PyPI:
  https://pypi.org/project/cadquery-ocp/
- CadQuery PyPI install notes:
  https://pypi.org/project/cadquery/
- `pythonocc-core` conda-forge:
  https://anaconda.org/conda-forge/pythonocc-core
- CadQuery OCP source:
  https://github.com/CadQuery/OCP
- Open Cascade pythonOCC project page:
  https://dev.opencascade.org/project/pythonocc
