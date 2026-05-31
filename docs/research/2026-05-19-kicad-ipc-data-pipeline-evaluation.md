# KiCad IPC Data Pipeline Evaluation

Date: 2026-05-19
Status: research note / recommended architecture

## Verdict

Yes, the IPC path is viable for the rendering data pipeline, but the clean
implementation is not to rebuild `pcb_a0` from the IPC wrapper objects.

Use IPC as a **live acquisition and mutation layer**:

1. ask KiCad for the current board as KiCad board-file text
   (`Board.get_as_string()`)
2. hydrate the existing `kicad_monkey.KiCadPcb` object model from that string
3. attach project/source context
4. pass the hydrated `KiCadPcb` into the existing direct
   `data_models.converters.kicad_stackup.pcb_from_kicad_pcb(...)` path
5. stream the resulting `pcb_a0` or derived viz payload to the browser

This keeps one authoritative KiCad source model in our codebase. IPC does not
become a second parser or a second source-to-`pcb_a0` converter.

## Source Findings

Official/current sources checked:

- KiCad IPC add-on docs:
  https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/
- KiCad IPC developer docs:
  https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-kicad-developers/
- `kicad-python` KiCad API docs:
  https://docs.kicad.org/kicad-python-main/kicad.html
- `kicad-python` Board API docs:
  https://docs.kicad.org/kicad-python-main/board.html
- `kicad-python` Project API docs:
  https://docs.kicad.org/kicad-python-main/project.html
- `kicad-python` source for `Board.get_as_string()`:
  https://gitlab.com/kicad/code/kicad-python/-/blob/main/kipy/board.py

Important API facts:

- `Board.get_as_string() -> str` returns the current board as KiCad board-file
  text.
- `Board.get_selection_as_string() -> str` returns selected items in KiCad
  board-file text.
- The Python implementation sends KiCad's `SaveDocumentToString` command for
  `get_as_string()`, so the source is the live open board document, not a file
  reread performed by our daemon.
- `KiCad.get_board()` returns the board open in the running GUI session.
- `Board.get_project()` gives a `Project`; `Project.path` and `Project.name`
  are exposed.
- `Project.get_net_classes()` and `Project.get_text_variables()` are exposed.
- `KiCad.get_text_as_shapes(...)` can return KiCad-generated polygonal text
  shapes for text/textbox objects. Treat this as a useful validation or fallback
  for text geometry, not as the primary board hydration path.
- KiCad 9/10 IPC is GUI-session oriented and PCB-editor focused. Schematic IPC
  should remain a later lane.
- IPC is request/reply and handled on KiCad's UI thread, so snapshot frequency
  must be controlled.

## Local Code Findings

`kicad_monkey.KiCadPcb` already has the correct hydration surface:

- `KiCadPcb.from_string(content)`
- `KiCadPcb.from_file(path)`
- `KiCadPcb.to_string()`

The source model already parses and preserves the data required by 2D/3D viz:

- board graphics: `gr_line`, `gr_arc`, `gr_rect`, `gr_circle`, `gr_poly`,
  `gr_curve`, `gr_text`, `gr_text_box`
- board outline carriers, including footprint-local `Edge.Cuts`, through
  `KiCadPcb.board_outline_carriers()`
- footprints, pads, footprint-local graphics/text/properties
- 3D model references and transforms
- board/footprint embedded files
- render cache polygons on text/text boxes
- stackup/setup, nets, zones, vias, tracks, dimensions, images, tables,
  groups, generated items, barcodes, variants, and unknown elements

The direct KiCad PCB to `pcb_a0` path already exists in
`data_models.converters.kicad_stackup.pcb_from_kicad_pcb(...)` and pulls from
the `KiCadPcb` object model:

- layers and stackup
- components/footprints
- pads, padstacks, holes, vias
- routing/copper primitives and zones
- board graphics and text objects
- text render-cache geometry
- dimensions
- board profile/outline
- nets, net classes, diff-pair/impedance metadata where available
- embedded 3D files and external STEP references

## Recommended Runtime Pipeline

```text
KiCad GUI board
  |
  | kicad-python IPC
  v
Board.get_as_string()
  |
  v
KiCadPcb.from_string(board_text)
  |
  | attach source_path, project sidecar/context, model search roots
  v
pcb_from_kicad_pcb(KiCadPcb, model_search_paths=...)
  |
  v
pcb_a0
  |
  v
viz 2D/3D payload / websocket snapshot
```

Do not map every `kipy.board_types.*` object directly to `pcb_a0` for the
production path. The IPC wrappers are useful for edits, selection, hit-testing,
quick targeted queries, and validation, but the board-file string is a more
complete and stable input for our source parser.

## Why The Board String Is The Right Boundary

Advantages:

- It uses KiCad's own current document serialization.
- It includes objects that may not be convenient or fully exposed through the
  typed IPC wrappers.
- It preserves KiCad syntax-level detail that `kicad_monkey` already knows how
  to parse.
- It lets `kicad_monkey` keep owning compatibility with KiCad file-format
  evolution.
- It lets the existing `pcb_a0` converter keep one source surface.
- It avoids coupling viz to `kipy` protobuf object shapes.

The alternative, IPC-object-to-`pcb_a0`, would duplicate a lot of code and would
need separate coverage for every board item class, every KiCad release, and
every converter edge case. It is only worth doing for small targeted deltas or
where IPC gives us KiCad-computed geometry we cannot otherwise compute.

## Source/Project Context

`KiCadPcb.from_string(...)` cannot infer the project file from disk on its own.
The IPC acquisition layer should attach context after parsing:

- `pcb.source_path`: derived from `Board.name` / document path where available
- `pcb.project`: load `KiCadProjectSidecar.from_file(project_file)` when the
  project file exists
- snapshot metadata:
  - KiCad version
  - API version
  - project path
  - board filename/path
  - document token or daemon session id
  - SHA-256 of `board_text`

If the project path is unavailable or the board is unsaved, still hydrate the
board string, but mark external asset resolution as degraded.

## Project Context Acquisition

The daemon should get project context in layers:

1. Connect to the intended KiCad instance using the socket/token handed to the
   plugin:
   - `KICAD_API_SOCKET`
   - `KICAD_API_TOKEN`
2. Retrieve the active/open board:
   - `kicad.get_board()`, or
   - `kicad.get_open_documents(DocumentType.DOCTYPE_PCB)` plus an explicit
     board selector passed by the plugin bootstrap.
3. Read the board document specifier:
   - `board.document`
   - `board.name`
4. Read the associated project:
   - `project = board.get_project()`
   - `project.name`
   - `project.path`
   - `project.get_text_variables()`
   - `project.get_net_classes()`
5. Resolve project/board paths:
   - KiCad's `ProjectSpecifier.path` is the project directory.
   - KiCad's `ProjectSpecifier.name` is the project name without
     `.kicad_pro`.
   - The normal project file candidate is:
     `Path(project.path) / f"{project.name}.kicad_pro"`.
   - The board path candidate is:
     `Path(project.path) / board.name`, unless `board.name` is already an
     absolute path.
6. Load the full project sidecar from disk when available:
   - `KiCadProjectSidecar.from_file(project_file)`
   - attach it to `pcb.project`
   - attach the resolved board path to `pcb.source_path`
7. Overlay or record live IPC project values:
   - IPC text variables and net classes may reflect unsaved GUI changes.
   - The disk `.kicad_pro` sidecar is more complete for current
     `kicad_monkey` conversion, but may be stale if project settings were
     edited and not saved.

For the first live-viz implementation, prefer:

- disk `.kicad_pro` when it exists, because our parser already understands
  project net settings, text variables, variants, and board design settings
- IPC `Project.get_text_variables()` as a live freshness overlay for text
  expansion metadata
- IPC `Project.get_net_classes()` as a fallback/validation source, not the
  only source of project topology, until we map the IPC netclass wrapper into
  `KiCadProjectNetSettings`

The plugin bootstrap should pass an explicit board selector to the daemon when
possible. `KiCad.get_board()` currently returns the first open PCB document. In
normal PCB-editor plugin usage that is likely enough, but an explicit
`project_path` + `board_filename` handshake avoids ambiguity if KiCad grows
multi-board or multiple open PCB workflows.

Recommended snapshot context:

```python
{
    "kicad_version": str(kicad.get_version()),
    "api_version": str(kicad.get_api_version()),
    "project_name": project.name,
    "project_dir": project.path,
    "project_file": str(project_file) if project_file else "",
    "board_name": board.name,
    "board_file": str(board_path) if board_path else "",
    "board_document": {
        "type": int(board.document.type),
        "board_filename": str(board.document.board_filename),
    },
    "project_text_variables": dict(project.get_text_variables().items()),
}
```

`TextVariables` exposes dict-like `items()`, `keys()`, and `values()` helpers
in current `kicad-python`.

## 3D Model Data

Initial implementation scope:

- Start with embedded 3D models only.
- Treat external model reference resolution as a follow-on hardening lane, not
  a blocker for the first live IPC/viz bridge.

Embedded models:

- If the board string contains KiCad embedded files, the existing parser and
  converter can carry them forward into `pcb_a0.embedded_files`.

External STEP/WRL/etc. model references:

- The board string carries footprint model references and transforms.
- The existing converter can embed external STEP payloads when
  `model_search_paths` resolves the files.
- The daemon should build search roots from:
  - project directory / `${KIPRJMOD}`
  - project-local `3d/`, `libs/`, and project root
  - user-configured extra model roots
  - KiCad environment model dirs if visible in the plugin process, such as
    `KICAD*_3DMODEL_DIR`

This is the main data-side gap to harden. If the plugin process cannot see the
same KiCad path variables as the GUI, the daemon needs a small resolver config
or an IPC-backed fallback.

Longer term, model-reference resolution should become an explicit parser/source
context service rather than an ad hoc daemon-only behavior. The source model can
keep the raw KiCad model ref, while a resolver layer attaches resolved local
paths, provenance, and optional embedded payloads for downstream converters.

KiCad's `Board.export_3d(...)` is useful as a fallback for "give me KiCad's
whole 3D export", but it should not be the core path if we want our existing
geometer/triangle synthesis and `pcb_a0` semantics.

## Text And Render Cache Data

Primary path:

- Use `Board.get_as_string()` and parse KiCad's serialized text/render-cache
  data through `KiCadPcb.from_string(...)`.
- Let the existing render-cache resolver/generator handle missing or stale
  caches.
- Let the existing converter emit text objects and render-cache-derived
  geometry into `pcb_a0`.

Validation/fallback path:

- For tricky live text cases, call `KiCad.get_text_as_shapes(...)` on IPC text
  objects and compare or substitute KiCad-computed polygons.
- This should stay optional because mapping IPC text wrappers back into the
  parsed `KiCadPcb` source tree introduces identity/shape stitching work.

## Live Update Strategy

Start simple:

- Poll `Board.get_as_string()` at a low rate or on explicit browser refresh.
- Hash the returned string.
- If unchanged, do nothing.
- If changed, reparse and reconvert to a fresh `pcb_a0` snapshot.
- Diff on stable `source_ref.uuid` / KIID-derived ids in the `pcb_a0` payload
  before sending to the browser.

For interactive edits initiated by viz:

- Use IPC typed objects and `Board.update_items(...)` for the write.
- After the commit, reacquire the board string and regenerate the authoritative
  snapshot.

Do not try to edit the board text string and push it back into KiCad. The IPC
API gives item update APIs; use those for mutation and the serialized string
only for read/hydrate.

## Proposed `kicad_monkey` API Shape

Keep the core parser independent of `kicad-python`. Add an optional IPC
acquisition module or extra:

```python
@dataclass(frozen=True)
class KiCadIpcBoardSnapshot:
    board_text: str
    board_path: Path | None
    project_path: Path | None
    kicad_version: str
    api_version: str
    digest: str
    metadata: dict[str, object]


class KiCadIpcBoardSource:
    def __init__(self, kicad=None, *, model_search_paths=None): ...
    def capture(self) -> KiCadIpcBoardSnapshot: ...
    def hydrate(self, snapshot: KiCadIpcBoardSnapshot) -> KiCadPcb: ...
```

Implementation rules:

- Import `kipy` lazily so normal `kicad_monkey` users do not need KiCad IPC
  dependencies installed.
- Keep websocket/HTTP daemon code outside the parser model. The daemon can live
  in `viz` or a bridge package and depend on this optional acquisition module.
- Keep conversion in `data_models`; do not add `pcb_a0` construction logic to
  `kicad_monkey`.
- Expose stable source ids in converter output so browser-side diffs and
  write-back commands can address KiCad KIIDs.

## Spike Plan

1. Add a tiny optional `kicad_monkey` IPC snapshot module with lazy `kipy`
   imports and unit tests using fake `Board` / `Project` objects.
2. Manual script:
   - connect to KiCad
   - call `Board.get_as_string()`
   - hydrate `KiCadPcb.from_string(...)`
   - attach project context
   - call `pcb_from_kicad_pcb(...)`
   - run `validate_pcb_model(...)`
   - write `pcb_a0` JSON
3. Prove unsaved edit visibility:
   - move a footprint in KiCad without saving
   - recapture through IPC
   - verify the hydrated `KiCadPcb` and `pcb_a0` show the moved location
4. Prove asset coverage:
   - embedded STEP model
   - external STEP via `${KIPRJMOD}`
   - stock KiCad library model via `KICAD*_3DMODEL_DIR`
5. Prove text coverage:
   - board text with render cache
   - text box with knockout
   - missing/stale cache path through existing generator
   - optional comparison to `KiCad.get_text_as_shapes(...)`
6. Add daemon snapshot contract:
   - `snapshot_id`
   - board digest
   - `pcb_a0` payload or payload URL
   - source-id map for KIID -> `pcb_a0` entity ids

## Answer To The Design Question

Yes, hydrate our object model from IPC, but hydrate it from KiCad's serialized
live board text, not from per-object IPC wrappers.

The clean boundary is:

- `kicad_monkey`: optional IPC acquisition -> `KiCadPcb`
- `data_models`: `KiCadPcb` -> `pcb_a0`
- `viz` daemon: session, websocket, polling/diff, command routing
- IPC typed objects: edits, selection, hit tests, targeted validation
