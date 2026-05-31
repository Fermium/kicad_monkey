# Phase F-6.2 — Recorder vs kicad_monkey drift baseline

Date: 2026-05-09
Branch: `kicad_monkey`
Tooling: `kicad_monkey.compute_recorder_drift` (this slice)

## Purpose

Capture a frozen baseline of the structural gap between
`kicad-cli sch export svg` (with the F-6 RECORDER_PLOTTER patch
emitting `kicad.plotter_recorder.v1` JSON) and the kicad_monkey
toolchain (`KiCadSchematic.from_file → schematic_to_ir`), so subsequent
slices can drive the gap to zero with a clear before/after metric.

Baseline run: all 4 corpus reference schematics for which we have a
recorder dump:

| Fixture            | Recorder ops | Recorder geom ops | kicad_monkey ops | Coverage |
|--------------------|-------------:|------------------:|-----------------:|---------:|
| led_component      |          373 |                70 |                0 |     0.0% |
| sallen_key         |        1 293 |               277 |               39 |    14.1% |
| complex_hierarchy  |        2 258 |               937 |               56 |     6.0% |
| ADC_PWR            |        2 214 |               549 |               42 |     7.7% |

"Geometric ops" excludes pure state ops (`SetColor`, `SetCurrentLineWidth`,
`SetDash`, `SetViewport`, `SetPageSettings`, `StartPlot`, `EndPlot`,
`StartBlock`, `EndBlock`, `PenTo`) which are not emitted by kicad_monkey's
declarative IR.

## Drift breakdown

### Recorder-only op kinds (kicad_monkey emits zero of these)

Across all 4 fixtures, kicad_monkey's `schematic_to_ir` never emits:

- **All state ops** — by design (declarative pen state baked into each op
  payload). The fold pass (F-6.3 candidate) will collapse runs of
  `SetColor` + `SetCurrentLineWidth` + `SetDash` + `PenTo` segments into
  the equivalent `PlotPoly` / `Circle` / `Rect` / `Text` ops with explicit
  pen state.
- `Rect` — appears in every fixture (2, 3, 43, 2). Mostly title-block
  border + symbol-decoration boxes.
- `Text` — appears in every fixture (33, 33, 33, 69). Sourced from
  drawing-sheet (title-block fields = 33 entries on every fixture
  ⇒ default `pageLayout.kicad_wks` template) plus per-symbol pin
  numbers/names (delta in ADC_PWR, complex_hierarchy).
- `ArcThreePoint` — ADC_PWR only (24). Inductor symbol bodies.
- `PlotPoly` — every fixture (recorder side). kicad_monkey emits
  `PlotPoly` for wires/buses/bus_entries already, but the recorder
  vastly outnumbers it because of symbol bodies (rectangle outlines /
  pin polylines / etc.).

### kicad_monkey-only op kinds

None on any fixture. Every kind kicad_monkey emits is also present in
the recorder.

### Canvas drift

| Paper size | Drift (Δw_nm, Δh_nm) |
|------------|---------------------:|
| A4 (3 fixtures) |       (2200, 7200) |
| D  (ADC_PWR)   |              (0, 0) |

A4 shows a fixed +2.2 µm × +7.2 µm offset; D-size matches exactly. The
A4 drift is `PAGE_INFO::GetWidthMils()`-rounded (mil → IU) vs
kicad_monkey's exact mm→nm. Sub-pixel at any reasonable render scale.

## Where the kicad_monkey gap lives

In priority order:

1. **Symbol body composition** — `schematic_to_ir` emits
   `symbol_instance` records with empty `operations[]`. They need to be
   composed against `lib_symbol_to_ir` (F-3) at the right
   placement/rotation/mirror/unit/style. This single change closes the
   majority of the geometric-op gap.

2. **Drawing sheet (title block + page border)** — `sheet_header`
   records have empty `operations[]`. KiCad's drawing-sheet drawing is
   a separate pipeline (`DS_DATA_MODEL` + `DS_DRAW_ITEM_*` resolved
   against `pageLayout.kicad_wks`). Likely a self-contained
   sub-converter (`drawing_sheet_to_ops`) reading the .kicad_wks file.

3. **Hierarchical sheet boxes** — `sheet` records currently empty;
   need `Rect` outline + sheet-name `Text` + sheet-file `Text` +
   pin-port shapes.

4. **Symbol pin numbers/names** — F-3 explicitly defers; pin-wire is
   emitted but pin-number/pin-name texts aren't.

5. **Label decoration shapes** — F-4 emits the text body only; the
   global/hier label arrow/box outlines are deferred.

6. **No-connect glyph polish** — currently 2-segment X; recorder may
   use a single `PlotPoly` with two sub-polys plus a `SetColor`. To
   verify against fixtures.

## Suggested next slices (to drive coverage up)

- **F-6.3 PenTo→PlotPoly fold pass** on the recorder side, so the same
  geometry is comparable kind-for-kind, not state-stream-vs-batch.
  Pure recorder-side normalisation; no schematic-side change.
- **F-6.4 Symbol body composition in `schematic_to_ir`** — biggest
  single coverage jump. Needs a lib-symbol resolver (project +
  `sym-lib-table` lookup) and the `lib_symbol_to_ir` invocation per
  instance. Will likely jump every fixture from 0–14% into 40–60%
  range.
- **F-6.5 Drawing-sheet converter** — moderate-effort, well-bounded
  (reads template file, instantiates per-page).
- **F-6.6 Coordinate equivalence** — once op-kind histograms align
  within a few percent, pivot from histogram drift to per-op
  coordinate diffing (sorted point-set comparison with tolerance).

The drift report tool itself is now wired in and tested
(`test_L0_011_recorder_drift.py`, 34 passing) — every subsequent slice
can re-run it for an objective before/after.
