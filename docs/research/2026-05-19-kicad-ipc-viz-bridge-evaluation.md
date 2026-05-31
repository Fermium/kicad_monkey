# KiCad IPC Viz Bridge Evaluation

Date: 2026-05-19
Status: research note / recommended implementation spike

## Verdict

The mechanics are feasible for a live KiCad PCB bridge:

- read the active board from a running KiCad GUI session
- serialize a board snapshot into the existing `pcb_a0` / viz payload path
- stream snapshots and deltas to a browser over a local daemon websocket
- select and cross-probe board objects
- move footprints and silkscreen board items and write the accepted positions
  back through KiCad IPC

The right implementation is not browser-to-KiCad directly. Use a KiCad IPC
plugin action that starts or attaches to a local Python daemon. The daemon owns
the KiCad IPC socket/token, serves the browser UI on `127.0.0.1`, and exposes a
small websocket command protocol to the browser.

## Key KiCad IPC Facts

Official sources checked:

- KiCad IPC API overview:
  https://dev-docs.kicad.org/en/apis-and-binding/
- IPC for KiCad developers:
  https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-kicad-developers/
- IPC for add-on developers:
  https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/
- `kicad-python` docs:
  https://docs.kicad.org/kicad-python-main/
- Board API docs:
  https://docs.kicad.org/kicad-python-main/board.html
- KiCad addon/PCM packaging docs:
  https://dev-docs.kicad.org/en/addons/index.html
- Local KiCad source checked for implementation details:
  - `common/settings/common_settings.cpp`
  - `common/api/api_server.cpp`
  - `common/api/api_plugin_manager.cpp`
  - `common/api/api_plugin.cpp`
  - `common/paths.cpp`
  - `kicad/kicad.cpp`

Findings:

- KiCad 9.0+ exposes an IPC API intended to replace the deprecated SWIG Python
  bindings. The official Python wrapper is `kicad-python` / `kipy`.
- The API connects to a running KiCad process through a local socket/named pipe.
  KiCad-launched plugins receive `KICAD_API_SOCKET` and `KICAD_API_TOKEN`.
- The KiCad user preference is `api.enable_server` in `kicad_common.json`.
  KiCad starts the IPC server only when that preference is enabled.
- IPC is request/reply today. KiCad does not provide async notifications to
  API clients yet.
- API handling crosses onto KiCad's main UI thread. High-rate IPC writes will
  interfere with the editor; live UX must throttle IPC and keep browser-side
  drag previews local.
- In KiCad 9/10, the IPC API and IPC plugin system are PCB-editor focused. The
  docs describe wider schematic/headless coverage as KiCad 11+ work.

## Board API Surfaces That Matter

Current `kicad-python` board docs expose the primitives we need:

- Snapshot:
  - `KiCad().get_board()`
  - `board.get_footprints()`
  - `board.get_pads()`
  - `board.get_tracks()`
  - `board.get_vias()`
  - `board.get_shapes()`
  - `board.get_text()`
  - `board.get_zones()`
  - `board.get_nets()`
  - `board.get_stackup()`
  - `board.get_as_string()`
- Identity and lookup:
  - board items carry `id` / KIID identity
  - `board.get_items_by_id(...)`
  - `board.get_item_bounding_box(...)`
- Selection/cross-probe:
  - `board.get_selection(...)`
  - `board.add_to_selection(...)`
  - `board.clear_selection()`
  - `board.remove_from_selection(...)`
  - `board.hit_test(...)`
  - `board.interactive_move(...)`
- Mutation:
  - `board.update_items(...)` updates existing items by internal UUID
  - `board.create_items(...)`
  - `board.remove_items(...)`
  - `board.begin_commit()`, `board.push_commit(...)`, `board.drop_commit(...)`

The official `kicad-python` examples include a `move_footprints.py` script that
gets footprints, edits `footprint.position` / `footprint.orientation`, and calls
`board.update_items(footprints)`. That is the exact mechanism to prove first.

## Proposed Architecture

```text
KiCad PCB editor
  |
  | IPC plugin action: "Open Viz Live"
  v
Python plugin bootstrap
  |
  | passes KICAD_API_SOCKET, KICAD_API_TOKEN, project/board context
  v
Local daemon on 127.0.0.1
  |-- kicad-python client
  |-- snapshot/diff worker
  |-- pcb_a0/viz payload adapter
  |-- HTTP static server for the browser app
  `-- websocket command server
        |
        v
Browser viz 2D/3D app
```

The daemon should be the only process that talks to KiCad IPC. The browser
should only know a random localhost port plus a one-time token.

## Startup, Registration, and Automation

A plugin does not discover the active KiCad connection by scanning the machine
when KiCad launches it. KiCad injects the connection information into the
plugin process:

- `KICAD_API_SOCKET`: socket/named-pipe path for this KiCad instance.
- `KICAD_API_TOKEN`: token for this KiCad instance.

That only happens for an IPC plugin/action that KiCad knows about. Registration
means placing a plugin directory with a valid `plugin.json` under one of the
directories KiCad scans:

- stock plugins
- PCM / third-party plugins
- user plugins, normally
  `${KICAD_DOCUMENTS_HOME}/<version>/plugins/<plugin-name>`

On Windows with defaults, the user plugin path is typically:

```text
C:\Users\<user>\Documents\KiCad\<version>\plugins\<plugin-name>\plugin.json
```

`plugin.json` must have a reverse-DNS-style plugin `identifier`, a `runtime`
of `python` or `exec`, and one or more actions with relative entrypoints. KiCad
prefixes action identifiers with the plugin identifier, validates the manifest
against `api.v1.schema.json`, and launches the entrypoint as a separate process.

External tools do not have to be registered. A script or daemon can call
`kipy.KiCad()` directly, and the Python client will use the environment
variables if present or the default platform socket path if they are absent.
This is good for local development when only one KiCad instance is open. It is
not the most robust production path because the external daemon must handle
socket ambiguity and cannot rely on KiCad passing the instance token.

For a one-button UX, reuse the existing `lib_cruncher` / `kicad_monkey`
automation and add a small launcher layer:

1. Discover KiCad installs with `kicad__find_installations()` and select the
   highest stable version.
2. Discover KiCad config directories with `kicad__find_config_paths()`.
3. Update `kicad_common.json` with backup and set `api.enable_server: true`.
   This should be done while KiCad is not running or followed by a KiCad restart,
   because running KiCad owns its settings state.
4. Install or refresh the Viz Live IPC plugin in the user plugin directory.
5. Launch KiCad with a project file argument:
   `kicad.exe <path-to-board>.kicad_pro`.
   KiCad's main launcher accepts `.kicad_pro` / legacy `.pro` positional args
   and loads that project at startup.
6. The user clicks the registered "Open Viz Live" action, or a future helper
   can poll for an already-running daemon handshake after startup.

Launching with a board file is less clean from the project manager path: current
KiCad manager startup validates positional args as project files. For our flow,
open the project and let the plugin connect to whichever PCB editor session is
active. If we need to force the PCB editor open, prove that separately in a
spike rather than baking it into the first launcher.

For the board currently open in KiCad, a quick manual connection test can be a
plain external `kipy.KiCad().get_board()` probe if the API preference is already
enabled and only one KiCad instance is open. The production bridge should still
start through the registered plugin action so the daemon receives the exact
socket/token for that open session.

Local smoke result on 2026-05-19:

- Command used an ephemeral `uv run --with kicad-python python -` environment.
- No `KICAD_API_SOCKET` or `KICAD_API_TOKEN` were present in the shell.
- `kipy.KiCad()` connected through the default socket to the open KiCad GUI.
- KiCad version: `10.0.0`; API version: `10.0.1`.
- Open board: `11-10080__yoshi-mainboard__A.kicad_pcb`.
- `board.get_footprints()` returned 35 footprints.

## Near-Term Plugin Scaffolding Pilot

Before building Viz Live, build a few small registered KiCad plugins. This gives
us immediate utility and exercises the packaging/install/debug workflow while
the failure surface is still small.

The first concrete pilot has shifted to a board-level assembly projection
plugin. It is related to the footprint filters, but operates on the open board:
it uses embedded STEP models, geometer HLR projection, and KiCad IPC write-back
to place generated assembly graphics on configured board layers. See:

- `docs/research/2026-05-19-kicad-board-assembly-projection-plugin.md`

The earlier Wavenumber footprint-filter plugin remains useful as a smaller
file-based exercise:

- High value now: our KiCad conversion flow already depends on footprint
  cleanup, fab-layer cleanup, zero-sized pad fixes, text/font normalization,
  embedded-model naming, and 3D-model projection outlines.
- Low coupling: it can reuse the existing `kicad_monkey` filter entry points
  such as `kicad__fp_filter(...)` and does not need the full viz daemon or
  browser protocol.
- Good packaging practice: it still needs `plugin.json`, a Python entrypoint,
  `requirements.txt`, plugin installation, KiCad API enablement, interpreter
  setup, logging, and a predictable reload loop.

Recommended first plugin actions:

1. `Filter Footprint File...`
   - Scope: start with `pcb` or `project_manager` so it is easy to reach from
     KiCad while we prove registration.
   - Behavior: prompt for a `.kicad_mod`, make a timestamped backup, run
     `kicad__fp_filter(input, input)`, then report success/failure.
   - This is intentionally file-based and avoids live editor mutation.

2. `Filter Footprint Folder...`
   - Prompt for a `.pretty` directory, filter each `.kicad_mod`, write backups
     and a simple JSON/HTML report.
   - This mirrors existing batch use in `lib_cruncher` migration tools.

3. Later: `Filter Selected Board Footprints`
   - Requires more care because live board footprints are open editor state.
   - Do not rewrite the board file behind KiCad while the board is open.
   - Either mutate typed footprint child items through IPC, or require an
     explicit closed-file workflow.

This pilot should not start by editing an open PCB file on disk. KiCad owns the
open document and may overwrite or conflict with external file writes.

## Standard Plugin Tooling To Build

Add reusable local tooling so new KiCad plugins are cheap to create and install:

- `scaffold`:
  - creates a plugin directory from a template
  - writes `plugin.json`
  - writes `requirements.txt`
  - writes a Python entrypoint with logging and error handling
  - optionally adds light/dark PNG icons
- `validate`:
  - checks identifier format, action scopes, relative entrypoints, readable
    files, and `requirements.txt`
  - optionally validates against KiCad's `api.v1.schema.json` when available
- `install`:
  - discovers KiCad versions with `kicad__find_config_paths()`
  - resolves the user plugin directory
    `${KICAD_DOCUMENTS_HOME}/<version>/plugins`
  - copies or symlinks the plugin into place
  - can install into a selected KiCad major/minor version
- `configure`:
  - reuses existing preference backup/update behavior
  - ensures `kicad_common.json` has `api.enable_server: true`
  - optionally records the Python interpreter path for KiCad plugin venvs
- `package`:
  - builds a PCM-compatible ZIP with `metadata.json`, `plugins/...`, and
    resources
  - emits checksums and a manifest suitable for private/internal distribution
- `smoke-test`:
  - verifies plugin files are installed
  - optionally connects with `kipy.KiCad().ping()`
  - runs a simple action script directly under `uv` for fast local iteration

KiCad's Python plugin manager creates a per-plugin virtual environment and then
installs `requirements.txt` with pip. Current source requires
`requirements.txt` to be readable for Python plugins, so templates should always
include it even if it only contains comments or a local editable/package line.

For early development, prefer a tiny Python entrypoint that delegates into our
repo code. For distribution, prefer a package/requirements strategy that does
not depend on a developer checkout path.

## Runtime Data Flow

Startup:

1. User clicks the KiCad toolbar action.
2. Plugin starts daemon if needed.
3. Daemon connects to KiCad using `kipy.KiCad()`.
4. Daemon opens `http://127.0.0.1:<port>/?token=<session-token>`.
5. Browser requests an initial scene snapshot.

Snapshot:

1. Daemon reads board objects through IPC.
2. Adapter maps IPC objects to the same semantic anchors used by viz:
   component refs, pad names, nets, layers, board item KIID, source path.
3. Adapter emits `pcb_a0` or a thin live-viz variant of that payload.
4. Browser renders through the existing 3D/2D viz pipeline.

Edit:

1. Browser hit test chooses a semantic object, not a visual label.
2. Browser drag previews locally at frame rate.
3. On mouseup, browser sends a command such as:
   `{op:"move-footprint", id:"...", dx_nm:..., dy_nm:..., angle_delta_deg:...}`.
4. Daemon reloads the item by KIID, validates lock/layer/grid rules, applies
   the new position, and calls `board.update_items(...)` inside a commit.
5. Daemon polls/reloads the item after the update and broadcasts the accepted
   KiCad-authoritative state.

## What Is Feasible Now

Components:

- Moving footprints is a strong yes. The API exposes footprint position and
  orientation updates, commit grouping, and an official movement example.
- Best UX: browser-local drag preview, single IPC update on release, optional
  low-rate preview updates only if KiCad needs to visually follow along.

Silkscreen:

- Moving board-level silkscreen shapes/text is likely yes. Board graphic shapes
  expose `move(...)` / `rotate(...)`, text exposes position/layer/value, and
  `board.update_items(...)` is generic over existing board items.
- Scope this first to top-level `BoardShape`, `BoardText`, and `BoardTextBox`
  on `F.SilkS` / `B.SilkS`.
- Footprint-local silkscreen graphics should normally move with the footprint.
  Editing individual footprint-local silkscreen primitives from the browser is
  a second-order feature; prove top-level board items first.

Cross-probing:

- Browser -> KiCad selection is feasible with selection APIs.
- KiCad -> Browser selection is feasible but polling-based unless KiCad adds
  notifications. Start with polling `board.get_selection(...)` at a low rate.

Net-aware visualization:

- Board net data is exposed through nets and connected item queries.
- For full schematic netlist semantics, keep using the `kicad_monkey`
  source-model/netlist layer as the offline/high-fidelity source. IPC can be
  the live board-state channel.

Schematic live mode:

- Treat as a later KiCad 11+ lane. KiCad 9/10 IPC is PCB-editor focused.
  `kicad_monkey` remains the right schematic parser/netlist source for current
  viz work.

## Major Risks

- No async notifications: use polling/diff, not subscription semantics.
- UI-thread handling: throttle reads/writes, batch updates, and avoid IPC during
  every browser drag frame.
- API version drift: target a concrete KiCad baseline and gate features by
  `kicad.get_version()` / `kicad.get_api_version()`.
- Mutation semantics: prove `update_items` for each object class we care about.
  Footprints should be first, then board silkscreen text/shapes.
- Object identity: confirm KIID stability across save/reload and board reopen.
- IPC action lifetime: decide whether the toolbar action blocks while the
  daemon runs, or starts a detached daemon and returns immediately.
- Security: bind to loopback only, use a random token, validate websocket
  `Origin`, and never expose KiCad's IPC socket/token to browser JavaScript.

## Distribution / Install Strategy

There are two manifests:

- `plugin.json`: IPC plugin/action manifest consumed by KiCad.
- `metadata.json`: PCM package metadata consumed by the Plugin and Content
  Manager.

Recommended stages:

1. Developer/manual install:
   - Put the plugin under `${KICAD_DOCUMENTS_HOME}/<version>/plugins/<name>`.
   - Include `plugin.json` with a Python or executable runtime action.
   - For Windows users this usually lands under
     `C:\Users\<user>\Documents\KiCad\<version>\plugins`.

2. Single-file install:
   - Build a PCM ZIP with:
     ```text
     plugins/
       plugin.json
       viz_live.py
       ...
     resources/
       icon.png
     metadata.json
     ```
   - Users can install that ZIP with PCM "Install from file".

3. Private/internal distribution:
   - Host a PCM repository JSON and package ZIPs.
   - Users add the repository URL in PCM.

4. Public distribution:
   - Submit package metadata to KiCad's official addon metadata repository.
   - Official repository requires public downloads, SHA-256 metadata, issue
     tracker/source hosting, and open-source licensing for code.

For this plugin, use PCM metadata `type: "plugin"`, `runtime: "ipc"` for the
package version, and target KiCad 9.0.1+ or 10.0+ depending on the API methods
used by the first release.

## Recommended Spike

Spike 1: minimal IPC action and daemon.

- KiCad toolbar action starts the daemon and opens the browser.
- Daemon connects to KiCad and returns version, board filename, footprint count,
  shape count, text count, and net count.

Spike 2: live snapshot into viz.

- Emit a simple JSON snapshot from IPC:
  footprints, pads, nets, board outline, top-level silk text/shapes.
- Adapt it into the current `pcb_a0` / 3D-viz scene ingestion path.
- Keep high-fidelity KiCad parsing/rendering in `kicad_monkey`; use IPC for
  active-state deltas.

Spike 3: write-back.

- Move one footprint by KIID with `board.update_items(...)`.
- Group the move with `begin_commit()` / `push_commit(...)`.
- Verify KiCad undo/redo sees one operation.

Spike 4: silkscreen.

- Move a top-level `gr_text` or graphic shape on `F.SilkS`.
- Verify layer filtering, lock handling, and undo/redo.

Spike 5: cross-probe loop.

- Browser click selects KiCad object.
- KiCad selection polling updates browser highlight.
- Add conflict handling if KiCad changes the object during a browser drag.

## Fit With Current Toolz Work

This should be an extension of the packaged viz flow, not a replacement for the
current KiCad Monkey class library.

- `kicad_monkey` remains the offline/high-fidelity source parser, netlist, and
  SVG/IR backend.
- IPC becomes the live session adapter that can fetch current board state and
  apply editor mutations.
- `pcb_a0` remains the neutral payload target for viz. If the model is changing
  in the 3D-viz worktree, the daemon adapter should target that contract after
  it settles.
- Viz interaction architecture already expects source-owned semantic hit
  results and command routing. The IPC bridge should preserve KIID/component/
  pad/net anchors and route browser edits as explicit commands.
