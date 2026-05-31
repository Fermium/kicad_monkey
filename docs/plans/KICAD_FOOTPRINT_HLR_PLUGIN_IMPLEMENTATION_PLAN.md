# KiCad Footprint HLR Plugin Implementation Plan

Date: 2026-05-19
Status: executing - Phase 0 scaffold in progress

## Execution Log

### 2026-05-19 - Phase 0 Scaffold

Implemented the first app-owned plugin scaffold:

- `appz/kicad_plugins/footprint_hlr/plugin.json`
- thin `main.py` KiCad action entrypoint
- `footprint_hlr_plugin.action` Phase 0 IPC diagnostic action
- optional footprint-local probe line gated behind
  `WN_FOOTPRINT_HLR_PROBE=1`
- shared installer at `appz/kicad_plugins/shared/install.py`
- direct `footprint_hlr/install.ps1`
- best-effort appz setup integration with `-SkipKicadPluginInstall`

Local install was run and copied the plugin into discovered user plugin
folders:

- `C:\Users\EliHughes\Documents\KiCad\9.0\plugins`
- `C:\Users\EliHughes\Documents\KiCad\9.99\plugins`
- `C:\Users\EliHughes\Documents\KiCad\10.0\plugins`
- `C:\Users\EliHughes\Documents\KiCad\10.99\plugins`

Still needs live KiCad validation:

- KiCad discovers the plugin in PCB editor.
- The action connects to the active board.
- Selected footprint detection works against KiCad's runtime wrappers.
- `WN_FOOTPRINT_HLR_PROBE=1` adds a footprint-local line.
- KiCad undo removes the probe line.

### 2026-05-19 - KiCad IPC Preference Diagnostics

Live test setup found that the local plugin files were installed under
`Documents\KiCad\<version>\plugins`, but KiCad IPC was disabled in all checked
local KiCad config versions:

- `9.0`
- `9.99`
- `10.0`
- `10.99`

The 9.x config also referenced a missing Python interpreter at
`C:\Program Files\KiCad\9.0\bin\pythonw.exe` on this machine.

Updated the appz plugin installer to report disabled IPC API settings and
missing Python interpreter paths after install. The installer now enables the
KiCad IPC API preference by default during plugin install, and fills a missing
or invalid Python interpreter path when a matching KiCad install can be found.
KiCad should be closed when this runs so it does not rewrite the preference on
exit. Added installer/setup flags for preference automation:

- `footprint_hlr/install.ps1 -EnableApi`
- `footprint_hlr/install.ps1 -SkipApiSetup`
- `footprint_hlr/install.ps1 -PythonInterpreter <path>`
- `appz/setup.ps1 -EnableKicadApi`
- `appz/setup.ps1 -SkipKicadApiSetup`
- `appz/setup.ps1 -KicadPythonInterpreter <path>`

Validation guidance changed: local IPC plugins installed this way should be
checked from the PCB editor's action plugin surfaces, not from the Plugin and
Content Manager package list. The Plugin and Content Manager tracks PCM
packages; this dev install copies a local IPC plugin directly into the user
plugin folder.

### 2026-05-20 - Dialog Cleanup Path Live Board Iteration

Validated the dialog-driven cleanup path on the Yoshi board in KiCad 10.0.3.
Normal footprint-local drawing objects on the selected target layer are removed
from targeted footprint definitions, and the plugin now explicitly handles
KiCad's mandatory footprint fields. `Reference`, `Value`, `Datasheet`, and
`Description` are stored outside `definition.items`, so they are hidden and
copied back through the footprint-instance setters when they live on the target
layer. This closes the first observed live-board leftover: visible bottom-side
`Value` fields such as `SMT Testpoint 35mil` on `B.Fab` test points.

User retest after restarting KiCad confirmed the hidden-field cleanup worked.
The Yoshi board was intentionally left unsaved, so it remains useful for future
repeatable plugin test iterations.

### 2026-05-20 - Browser SVG Footprint Preview

Added a browser-dialog SVG preview scaffold to make cleanup/generation choices
inspectable before applying them. Each footprint row can request a live SVG from
the plugin server. The preview is rendered from the board top side and includes
representative copper pad geometry plus footprint-local objects and mandatory
fields on the currently selected target layer. Changing the target layer
reloads the row previews.

This is intentionally a narrow plugin-local renderer for the live IPC workflow:
standard copper pad shapes, target-layer graphic primitives, target text, and
visible mandatory fields. It is a practical validation surface now, and should
later be replaced or backed by the shared `kicad_monkey` SVG/IR renderer once
the installable-plugin dependency path is settled.

Remaining implementation scope is still HLR generation itself:

- embedded STEP extraction
- shared KiCad model pose builder
- projection backend integration
- generated geometry manifest / selective refresh

## Goal

Build an installable KiCad IPC plugin that can add, clean, and refresh HLR
assembly projection geometry inside board footprint instances.

The first user-facing workflow is legacy board cleanup:

1. Open a board in KiCad PCB editor.
2. Select one or more footprints, or choose a filtered set.
3. Run the Wavenumber footprint HLR action.
4. The plugin extracts each selected footprint's embedded STEP model.
5. The plugin generates footprint-local HLR geometry.
6. The plugin writes generated `fp_line` / `fp_arc` geometry into the
   footprint definition on the correct side layer.
7. Moving or rotating the footprint in KiCad carries the generated outline with
   the part.

This replaces the earlier board-level-first recommendation for this plugin.
Board-level graphics are still useful for reports and one-off debugging, but
they do not move with a part during placement. The plugin target is therefore
footprint-local geometry.

## Product Shape

Plugin name:

- `Wavenumber Footprint HLR`

Initial action:

- `Generate / Update Footprint HLR`

Primary scope:

- KiCad PCB editor, operating on placed footprints in the active board.

Later scopes:

- Footprint editor / footprint-library cleanup.
- Batch file cleanup over `.pretty` libraries.

Default behavior:

- Operate on selected footprints.
- Skip footprints with no embedded STEP model.
- Generate HLR only, without adding duplicate reference/value text.
- Write to `F.Fab` for front-side footprints and `B.Fab` for back-side
  footprints.
- Clean only previous Wavenumber-generated geometry when a manifest exists.
- Produce a report listing updated, skipped, failed, and cleaned footprints.

Opt-in behavior:

- Update all footprints.
- Update footprints matching reference, value, library id, or footprint name.
- Force clean selected target layers in selected footprints before generation.
- Use a dedicated user layer instead of fab layers.
- Add center reference text.
- Use detailed HLR for selected references while defaulting the rest to simple
  HLR.

## Non-Goals For V1

- External model reference resolution. V1 uses embedded STEP only.
- Full KiCad library cleanup from inside the PCB plugin. V1 operates on board
  footprint instances first.
- Shipping OCP / OCCT as a mandatory plugin dependency.
- Mutating the open board file on disk behind KiCad.
- Broad deletion of all user/fab graphics without explicit user selection.

## Key Design Decisions

### Repository Boundary

`appz` owns installable KiCad plugins and plugin-specific UX/packaging.
`kicad_monkey` owns reusable KiCad parsing, pose, projection, and IPC helper
code.

Use a dedicated app-level plugin home:

```text
appz/kicad_plugins/
```

The first plugin lives under:

```text
appz/kicad_plugins/footprint_hlr/
```

Shared KiCad plugin installer/scaffold code also belongs under
`appz/kicad_plugins/`, not inside `kicad_monkey`, because we expect more KiCad
plugins after footprint HLR. Low-level reusable helpers should be factored into
`kicad_monkey` only when they are useful outside this one plugin.

### Footprint-Local Output

Generated geometry must live under the footprint definition, not as board-level
graphics. That is the only way the outline naturally follows footprint moves,
rotation, side changes, and placement edits.

For board instances, the plugin should generate HLR in footprint-local
coordinates:

```text
STEP bytes
  -> model-local KiCad transform
  -> footprint-local projection
  -> fp_line/fp_arc children on F.Fab or B.Fab
```

The board placement transform is not applied to the generated child geometry.
KiCad applies the footprint transform when rendering and editing the part.

### Shared Pose Builder

Create one source of truth for KiCad model placement:

```python
@dataclass(frozen=True)
class KiCadModelPose:
    model_to_footprint_4x4_mm: tuple[tuple[float, float, float, float], ...]
    model_to_board_4x4_mm: tuple[tuple[float, float, float, float], ...] | None
    pose_signature: tuple[float, ...]
    side: str
    transform_order: str
    source_ref: dict[str, str]

    def to_geometer_transform(self, *, frame: str = "footprint") -> dict:
        ...
```

The footprint HLR plugin consumes `model_to_footprint_4x4_mm`.
The viz path and board-level debug/report path can consume
`model_to_board_4x4_mm`.
Future geometer integration consumes the same pose object through
`to_geometer_transform(...)`.

This prevents three separate KiCad pose implementations:

- `pcb_a0` conversion
- footprint-local HLR generation
- future geometer transform API

### Backend Contract

All projection backends return the same payload:

```text
geometry.projection.a0
```

Backends:

- `ReferenceOcctProjectionBackend`
  - optional Python/OCP backend
  - used to validate pose math and conversion to footprint-local shapes
  - not required for normal plugin install unless explicitly selected
- `GeometerProjectionBackend`
  - production target
  - initially CLI/C ABI from local geometer build
  - later Python wheel or packaged native artifact
- `LegacyTrimeshProjectionBackend`
  - compatibility/reference wrapper around the existing
    `fp_filter__orthographic_projection_outline(...)` behavior
  - useful only as a fallback or regression comparison

### IPC Ownership

KiCad owns the open board. The plugin must update the live board through IPC
and use KiCad's undo/redo system.

Expected mutation flow:

```text
board.begin_commit()
  -> mutate selected FootprintInstance.definition child items
  -> board.update_items([footprint_instance, ...])
  -> board.push_commit("Wavenumber Footprint HLR")
```

If nested footprint definition mutation cannot be made reliable through IPC,
that is a hard wall for the live plugin. A file-side fallback can still support
offline library cleanup, but it should not silently rewrite the open PCB file
behind KiCad.

## Package Layout

Proposed reusable helper modules in `toolz/kicad_monkey`:

```text
kicad_monkey/src/py/kicad_monkey/assembly_projection/
  __init__.py
  config.py
  embedded_model.py
  footprint_geometry.py
  manifest.py
  pose.py
  projection_backend.py
  projection_to_kicad.py
  reference_occt.py

kicad_monkey/src/py/kicad_monkey/ipc/
  __init__.py
  board_session.py
  footprint_update.py
  plugin_paths.py
```

Proposed plugin/application modules in `appz`:

```text
appz/kicad_plugins/
  README.md
  pyproject.toml                  # optional if plugins become uv workspace packages
  shared/
    __init__.py
    install.py
    kicad_discovery.py
    plugin_manifest.py
    preference_setup.py
    reporting.py

  footprint_hlr/
    README.md
    plugin.json
    requirements.txt
    main.py                       # KiCad action entrypoint, intentionally thin
    src/py/footprint_hlr_plugin/
      __init__.py
      action.py
      config.py
      report.py
    resources/
    tests/
```

Installer/dev tooling:

```text
appz/kicad_plugins/shared/install.py
appz/kicad_plugins/footprint_hlr/install.ps1
appz/kicad_plugins/footprint_hlr/package.ps1
```

The installer should reuse existing KiCad discovery/preferences helpers from
`appz/lib_cruncher` where practical, including install-path discovery and the
IPC-enable preference if that preference key is stable enough to modify.

The plugin package should depend on `kicad-monkey` for low-level helpers rather
than vendoring KiCad parsing/projection logic into `appz`.

## Plugin Registration

`plugin.json` should be a thin action registration file. Draft shape:

```json
{
  "identifier": "com.wavenumber.kicad-monkey.footprint-hlr",
  "name": "Wavenumber Footprint HLR",
  "description": "Generate footprint-local HLR assembly outlines from embedded STEP models.",
  "version": "0.1.0",
  "runtime": {
    "type": "python"
  },
  "actions": [
    {
      "identifier": "generate-update-footprint-hlr",
      "name": "Generate / Update Footprint HLR",
      "description": "Generate or refresh HLR outlines inside selected footprints.",
      "entrypoint": "main.py",
      "show-button": true,
      "scopes": ["pcb"]
    }
  ]
}
```

Validate this file against KiCad's current add-on schema before first install.
Keep the runtime entrypoint small; it should import a tested library function
and then report success/failure to KiCad.

## Configuration

Project config path:

- `<project>/.wavenumber/kicad_footprint_hlr.config.json`

Plugin user config path:

- KiCad plugin settings path when exposed by IPC.

Suggested config:

```json
{
  "target": {
    "scope": "selected",
    "refs": [],
    "footprint_patterns": [],
    "include_front": true,
    "include_back": true
  },
  "layers": {
    "front": "F.Fab",
    "back": "B.Fab"
  },
  "projection": {
    "default_mode": "simple",
    "detail_refs": [],
    "curve_mode": "native_arcs",
    "line_width_mm": 0.12
  },
  "clean": {
    "mode": "generated_only",
    "force_clean_target_layers": false
  },
  "backend": {
    "name": "geometer",
    "geometer_exe": null,
    "allow_reference_occt": false
  }
}
```

## Manifest

Project manifest path:

- `<project>/.wavenumber/kicad_footprint_hlr.manifest.json`

The manifest is the primary safety mechanism for selective cleanup. Store one
record per generated footprint/model/projection set:

```json
{
  "schema": "wavenumber.kicad_footprint_hlr.manifest.v1",
  "board_path": "example.kicad_pcb",
  "board_digest": "...",
  "records": [
    {
      "footprint_uuid": "...",
      "reference": "U12",
      "value": "STM32...",
      "footprint_path": "Package_QFP:LQFP-64_10x10mm_P0.5mm",
      "model_ref": "kicad-embed://...",
      "embedded_file_ref": "...",
      "step_sha256": "...",
      "pose_signature": [],
      "projection_options_sha256": "...",
      "target_layer": "F.Fab",
      "generated_uuids": ["..."],
      "created_at": "2026-05-19T00:00:00Z"
    }
  ]
}
```

Cleaning order:

1. For each targeted footprint, remove generated child items by UUID from the
   manifest.
2. If a manifest UUID is missing, ignore it and continue.
3. If `force_clean_target_layers` is enabled, remove matching drawing/text
   items from configured target layers for the targeted footprints only.
4. Generate new geometry.
5. Store new generated UUIDs and source hashes.

Do not default to deleting all `F.Fab`, `B.Fab`, `User.*`, or Eco graphics
across a board.

## Core Data Flow

```text
KiCad action launch
  -> lazy import kipy
  -> connect using KiCad-provided IPC environment
  -> get active board
  -> get selected footprints or target list
  -> board.get_as_string()
  -> KiCadPcb.from_string(...)
  -> map IPC footprint wrappers to parsed footprints by UUID/reference
  -> extract embedded STEP bytes
  -> build KiCadModelPose
  -> project STEP in footprint-local frame
  -> convert projection to fp_line/fp_arc records
  -> clean generated child items in targeted footprint definitions
  -> insert new generated child items
  -> board.update_items(...)
  -> push one KiCad commit
  -> write manifest/report
```

## Geometry Conversion Rules

Input:

- `geometry.projection.a0`
- selected view: footprint-local top view
- units: mm at the backend boundary

Output:

- `fp_line` for line segments
- `fp_arc` for native arcs when curve mode is `native_arcs`
- polyline approximation for arcs only when the backend does not provide native
  arcs or when IPC arc creation is not reliable
- UUID on every generated child item
- target side layer from config
- stroke width from config

Coordinate rules to prove:

- KiCad footprint-local XY convention vs projection backend XY convention.
- Whether Y inversion is needed after OCCT/geometer output.
- Bottom-side footprint-local graphics behavior in board editor.
- KiCad `fp_arc` mid-point semantics vs geometer center/start/end arcs.

Until those are proven, keep a debug SVG overlay and a one-footprint visual
fixture in the plan.

## UI Plan

Phase 1 UI:

- Simple local browser page launched by the plugin.
- Enumerate all board footprints and preselect KiCad-selected footprints. If
  no KiCad footprints are selected, preselect all footprints.
- Group rows by footprint library id / footprint name.
- Controls for selecting all, visible filtered rows, or only the KiCad
  selection.
- Per-footprint `simple` / `detailed` mode.
- Target layer selection, including current active non-copper layer when
  possible and an `Auto Fab` option that maps front footprints to `F.Fab` and
  back footprints to `B.Fab`.
- Explicit force-clean target-layer checkbox. This removes matching
  footprint-local drawing/text items only from targeted footprints.
- Hidden footprint metadata stamp (`WN_HLR_META`) recording the last
  clean/generate time, mode, layer, clean count, and backend/options summary.
- If nothing is selected in the dialog, show a clear KiCad notification/report
  and make no changes.
- Write an HTML/JSON report beside the manifest once projection generation is
  wired.

Phase 2 UI:

- Preview from the same `geometry.projection.a0` payload before applying.
- Backend controls for geometer / reference backend and cache invalidation.

Phase 3 UI:

- Integrate the same controls into broader KiCad cleanup tooling.

## Implementation Phases

### Phase 0 - IPC And Installer Proof

Deliverables:

- Minimal installable IPC plugin under `appz/kicad_plugins/footprint_hlr/`
  with `plugin.json`.
- Dev installer that places or links the plugin into the discovered KiCad user
  plugin directory, implemented under `appz/kicad_plugins/shared/` where it can
  be reused by later KiCad plugins.
- Action button visible in PCB editor.
- Action can connect to the active board and report selected footprints.
- Action can add one temporary footprint-local line to one selected footprint,
  update the board through IPC, and undo cleanly.
- Action can remove that temporary line by UUID.

Acceptance criteria:

- Installed plugin appears in KiCad without manual file copying.
- Running the action against one selected footprint changes the live board.
- Moving the footprint moves the test line.
- KiCad undo removes the test line.
- No board file is rewritten directly.

Hard wall:

- If IPC cannot reliably mutate nested footprint child items, pause the live
  plugin and switch only the offline library-clean path to implementation.

### Phase 1 - Shared Pose Builder

Deliverables:

- `kicad_monkey.assembly_projection.pose`.
- `KiCadModelPose` with both footprint-local and board-space matrices.
- Refactor or mirror the current `data_models.converters.kicad_stackup` KiCad
  model transform order.
- Unit tests covering top, bottom, footprint rotation, model offset, X/Y/Z
  rotations, non-uniform scale, and pose signature stability.

Acceptance criteria:

- `pcb_a0` converter and projection path can consume the same pose builder.
- Existing `PcbEmbedded3DModel` output remains unchanged unless deliberately
  updated with tests.
- A one-model debug dump shows matrix values and projected bounds.

### Phase 2 - Embedded Model Extraction

Deliverables:

- Shared embedded STEP extraction helper for board-embedded footprints and
  standalone `.kicad_mod` footprints.
- Hashing of decompressed STEP bytes.
- Report entries for missing, malformed, or unsupported models.

Acceptance criteria:

- V1 processes embedded `.step` / `.stp`.
- V1 skips external references with a clear report entry.
- No duplicated embedded-data parsing logic remains in the plugin entrypoint.

### Phase 3 - Reference Projection Backend

Deliverables:

- Optional `ReferenceOcctProjectionBackend`.
- Optional dependency extra, for example `kicad_monkey[occt-reference]`.
- Dev command that projects one embedded STEP to JSON and SVG.
- Conversion from reference output to `geometry.projection.a0`.

Acceptance criteria:

- One selected footprint can be projected in footprint-local frame.
- Debug SVG aligns with the generated footprint-local coordinates.
- The backend is not required for normal plugin install.

### Phase 4 - Geometer Backend

Deliverables:

- `GeometerProjectionBackend`.
- Configurable geometer executable path or library binding.
- Transform handoff from `KiCadModelPose.to_geometer_transform(frame="footprint")`.
- Cache by STEP hash, pose signature, view, mode, curve mode, and backend
  version.

Acceptance criteria:

- Geometer and the Python/OCP reference backend agree on projection bounds and
  centroid for a small fixture set.
- V1 can run without OCP installed when geometer is available.

### Phase 5 - Footprint Update Engine

Deliverables:

- `projection_to_kicad.py` converting projection lines/arcs to footprint child
  graphics.
- `manifest.py` with read/write/update and generated-UUID lookup.
- `ipc.footprint_update` helpers for:
  - target footprint discovery
  - generated child removal
  - target-layer force clean
  - generated child insertion
  - commit/rollback handling

Acceptance criteria:

- Selected-footprint update works for at least one front and one back
  footprint.
- Rerun replaces previous generated geometry instead of duplicating it.
- Force clean affects only targeted footprints and configured layers.
- Undo/redo behaves as one KiCad operation.

### Phase 6 - Plugin V1

Deliverables:

- Installed `appz/kicad_plugins/footprint_hlr` plugin action using
  selected-footprint defaults.
- Config file loading.
- Report generation.
- Dev installer and package builder under `appz/kicad_plugins`.
- Documentation for install, run, clean, and recovery.

Acceptance criteria:

- Works on a real legacy board with embedded STEP footprints.
- Handles skipped footprints gracefully.
- Leaves unrelated board graphics alone.
- Worktree tests pass.

### Phase 7 - Library Clean Mode

Deliverables:

- Offline batch command over `.pretty` directories.
- Reuse the same pose, projection, cleanup, and conversion core.
- Options compatible with the current footprint filter naming and clean-layer
  behavior.

Acceptance criteria:

- Can clean/update standalone `.kicad_mod` files.
- Can run in dry-run/report mode.
- Can preserve embedded model data formatting where required by existing
  kicad_monkey round-trip constraints.

## Testing Plan

Unit tests:

- Pose matrix composition.
- Embedded STEP extraction/decompression.
- Projection cache keys.
- `geometry.projection.a0` to `fp_line` / `fp_arc`.
- Manifest generated-only cleanup.
- Force-clean layer filtering.

Golden fixtures:

- Front footprint with embedded STEP and zero rotation.
- Front footprint with model offset and Z rotation.
- Footprint with model X/Y rotations.
- Non-uniform model scale.
- Back-side footprint.
- Footprint with pre-existing user/fab drawings that must survive
  generated-only cleanup.

Manual KiCad smoke tests:

- Install plugin.
- Run action on one selected footprint.
- Move/rotate footprint and confirm HLR follows.
- Undo/redo.
- Rerun and confirm no duplicates.
- Force clean selected target layer and confirm unrelated footprints survive.
- Save/reopen board and confirm generated footprint graphics persist.

## Open Questions To Resolve First

1. Exact KiCad IPC API for mutating `FootprintInstance.definition` children.
2. Whether IPC exposes selected footprints directly or selection must be
   filtered from generic selected board items.
3. Whether child UUIDs can be set before insertion and read back after
   `board.update_items(...)`.
4. How KiCad represents footprint-local arcs through IPC.
5. Whether footprint child groups are exposed well enough to group generated
   items. Do not rely on this for V1.
6. Exact plugin install location and dependency install behavior for KiCad
   versions we support.
7. Whether `appz/lib_cruncher` can safely enable the IPC API preference across
   installed KiCad versions.

## Source Notes

Local:

- `kicad_monkey/docs/research/2026-05-19-kicad-board-assembly-projection-plugin.md`
- `kicad_monkey/docs/research/2026-05-19-kicad-ipc-data-pipeline-evaluation.md`
- `kicad_monkey/src/py/kicad_monkey/kicad_filter_footprint.py`
- `data_models/src/py/data_models/converters/kicad_stackup.py`
- `C:/eli/agent-worktrees/3d-viz-rework/toolz/data_models/src/py/data_models/converters/kicad_stackup.py`
- `C:/eli/agent-worktrees/3d-viz-rework/geometer/INTERFACES.md`

External:

- KiCad IPC add-on developer docs:
  https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/
- KiCad Python board API docs:
  https://docs.kicad.org/kicad-python-main/board.html
- KiCad add-on schema:
  https://go.kicad.org/api/schemas/v1
