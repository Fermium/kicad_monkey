# PCB SVG Oracle Hardening Plan

Date: 2026-06-01
Status: In progress
Owner: kicad_monkey rendering/API cleanup
Depends on: `2026-06-01-pcb-svg-parity-audit-and-fix.md`

## Context

`kicad_cruncher pcb_svg` exposed board-layer SVG gaps that current
`kicad_monkey` tests did not catch. The taillight issues were geometric
placement and arc sweep defects. The Speedy U17 issue was different: the pad
coordinates were correct, but filled copper pads inherited a nonzero plot
stroke and therefore painted too large.

The current PCB SVG checks are useful but not sufficient for long-term KiCad
parity:

- `test_L3_001_board_svg.py` compares stored KiCad CLI SVG references for
  synthetic `pcb_foundation` cases by extracting coordinate sets. It tolerates
  representation differences such as KiCad `<path>` versus monkey `<polygon>`.
- `test_L3_006_synthetic_svg_oracle.py` and
  `test_L3_007_pcb_ir_svg_oracle.py` compare semantic snapshots such as
  viewBox, element counts, stroke buckets, drill counts, and now filled black
  ink area.
- Real-world `board_svg` cases currently generate review output and have a
  few targeted assertions, but they are not broadly compared against KiCad CLI
  layer by layer.

Fresh KiCad CLI inspection on 2026-06-01 shows the structural gap:

- Stock KiCad CLI SVG does not preserve UUIDs or `data-*` attributes.
- Stock KiCad CLI uses a top plot group and style buckets, commonly emitting
  filled copper as `<path style="fill:#000000; ... stroke:none;
  fill-rule:evenodd;">`.
- Current monkey review output emits source-object groups with `id`,
  `data-uuid`, and `data-ref`, and often emits equivalent geometry as
  `<polygon>` or `<polyline>`.

Example: `case083__pad_chamfered_roundrect` F.Cu

- KiCad CLI fresh output: `1 g`, `1 path`, no ids/data.
- Monkey output: metadata groups, background/outline, `1 polygon`.
- Filled black area now matches, but DOM structure does not.

Example: `speedy_processing_module` F.Cu

- KiCad CLI fresh output: `800 g`, `3357 path`, `2937 circle`, no ids/data.
- Monkey output: `11442 g`, `179 path`, `782 polygon`, `2396 polyline`,
  `2937 circle`, and thousands of source metadata groups.

This plan improves tests so `kicad_monkey` can target the same plotting
decisions KiCad makes, not only visual similarity.

## Progress Log

- 2026-06-01: Landed checkpoint `68b74ec` for the first geometry fixes:
  arc sweep parity, footprint-local pad placement, pad orientation, filled
  pad stroke suppression, and drill overlay ordering.
- 2026-06-01: Started Phase 1 profile plumbing. Added explicit
  `KiCadSvgRenderProfile` support, propagated `profile` / `options` through
  `render_pcb_ir_to_svg`, `KiCadPcb.to_svg`, `KiCadPcb.to_svg_ir`, and
  `KiCadFootprint.to_svg`, and added L0 coverage proving `kicad_cli`
  suppresses monkey-only source metadata while default review output keeps it.
- 2026-06-01: During the broad L3 SVG oracle rerun, `case082` mask-layer
  checks exposed an NPTH mask mismatch. Removed the synthetic black NPTH mask
  aperture so mask layers emit only the KiCad CLI-matching white NPTH drill.
  Verified with `test_L0_034_pcb_ir_svg_wrapper.py`,
  `test_L3_006_synthetic_svg_oracle.py`, and
  `test_L3_007_pcb_ir_svg_oracle.py`.
- 2026-06-01: Added the first canonical SVG analyzer under `tests/svg/`.
  It parses draw items with inherited styles, flattened transforms, element
  histograms, path command families, bbox/area summaries, and the semantic
  metric dict used by synthetic PCB SVG oracle tests. Removed the older
  duplicate regex/XML metric implementation from
  `tests/synthetic_board_svg_oracle.py` while leaving active symbol/schematic
  SVG helpers in place.
- 2026-06-01: Added the first strict structural PCB SVG oracle case
  (`case019` F.Cu via). This lane renders monkey output with
  `profile="kicad_cli"` and compares canonical draw-item kind sequence,
  normalized paint style, bbox, and radii against fresh KiCad CLI SVG.

## Goals

1. Add explicit PCB SVG output profiles so tests can request KiCad-compatible
   structure while review/tooling can still request enriched UUID/data groups.
2. Build a canonical SVG analyzer that compares all draw objects, relevant
   styles, transforms, and painted geometry.
3. Add structural and semantic oracle gates for all synthetic PCB SVG cases.
4. Add broad real-world PCB SVG metrics and review artifacts for all active
   real-world board cases, with staged ratcheting into enforced tests.
5. Use recorder dumps where available to move from layer-level matching toward
   per-source-object plotter parity.
6. Keep `kicad_monkey` standalone and MIT by using KiCad C++ and `kicad-cli`
   as behavior references, not copied implementation.

Non-goals:

- Do not require exact raw SVG text equality.
- Do not require source-object identity from stock KiCad CLI SVG; it does not
  carry that data.
- Do not move PCB SVG rendering policy into `kicad_cruncher`.
- Do not block public package use on a local KiCad install. CLI-backed tests
  must be explicit, staged, and documented.

## Output Profiles

Add a first-class PCB SVG render profile concept. The exact API can be an enum
or `Literal`, but the behavior must be explicit and testable.

Initial profiles:

1. `kicad_cli`
   - Intended for oracle tests.
   - Suppress monkey source metadata groups by default.
   - Suppress monkey-only IDs and `data-*` attributes.
   - Prefer KiCad CLI DOM choices where known.
   - Use KiCad-like style bucket formatting where practical.
   - Use black-and-white defaults matching the current CLI oracle command.

2. `review`
   - Intended for local human review and downstream tools.
   - Preserve source-object wrapper groups.
   - Include `id`, `data-uuid`, and `data-ref`.
   - Allow extra grouping that helps inspection.
   - Continue writing corpus-local `output/board_svg` review artifacts.

3. `tooling`
   - Optional follow-on profile if `kicad_cruncher` needs machine-readable
     stable IDs but not all visual-review decoration.
   - Should be documented only after a concrete consumer needs it.

API shape:

```python
pcb.to_svg(layers=["F.Cu"], profile="kicad_cli")
pcb.to_svg(layers=["F.Cu"], profile="review")
render_pcb_ir_to_svg(pcb, layers=["F.Cu"], options=KiCadSvgRenderOptions(...))
```

Implementation requirements:

- `KiCadPcb.to_svg` and `KiCadPcb.to_svg_ir` accept `options` and/or
  `profile` without removing existing parameters.
- `KiCadFootprint.to_svg` follows the same profile rules where practical.
- `KiCadSvgRenderOptions.include_metadata` and `include_ids` are honored by
  `render_record` and nested block rendering.
- Existing tests that assert `data-ref` or `data-uuid` request `review`
  explicitly.
- Oracle tests request `kicad_cli` explicitly.
- The default profile is a deliberate API decision. Do not silently change it
  until current internal consumers are audited. During implementation, prefer
  adding explicit profile parameters before changing defaults.

## Canonical SVG Analyzer

Create a reusable test helper, likely under `tests/svg/` or
`tests/svg_oracle/`, that parses an SVG into canonical draw items.

Input:

- SVG text from KiCad CLI or monkey.
- Optional layer name, board/case id, and comparison policy.

Output:

- `SvgDocumentSnapshot`
  - viewBox
  - width/height
  - top-level transform summary
  - style bucket histogram
  - element kind histogram
  - draw item list
  - aggregate metrics

- `SvgDrawItem`
  - sequence index
  - source element kind: `path`, `circle`, `polygon`, `polyline`, `rect`,
    `line`, etc.
  - effective style after inherited group styles are applied:
    - fill
    - stroke
    - stroke width
    - fill rule
    - opacity / fill opacity / stroke opacity when present
    - dash pattern, linecap, linejoin
  - flattened transform matrix
  - board-space bbox
  - approximate area for filled geometry
  - approximate stroke area or path length for stroked geometry
  - circle radius for circles
  - normalized point/path signature
  - raw path command family summary, such as `M/L/Z`, `M/A`, `M/C`

Supported geometry in the first pass:

- `circle`
- `rect`
- `line`
- `polyline`
- `polygon`
- simple `path` commands: `M`, `L`, `H`, `V`, `Z`
- arc path commands enough to detect arc flags and sampled endpoints

Follow-on geometry:

- cubic and quadratic paths from text or font outlines
- compound paths and holes with `fill-rule:evenodd`
- exact stroke expansion for non-round caps/joins if needed

Rules:

- Do not compare raw whitespace or numeric formatting.
- Compare effective styles, not only literal element attributes.
- Flatten transforms before comparing geometry.
- Preserve enough original structure to enforce "KiCad used path here, monkey
  should use path here" on strict synthetic cases.

## Comparison Policies

Use multiple comparison strengths rather than one global rule.

### Strict Synthetic Structural Policy

Used for focused synthetic cases.

Enforce:

- same draw item count by layer;
- same draw item kind sequence where the case is intended to pin emitter
  choice;
- same effective fill/stroke/stroke-width/fill-rule;
- bbox within small tolerance;
- area within small tolerance;
- circle radii within small tolerance;
- path command family where the case pins path-vs-polygon behavior.

This policy should fail if KiCad emits a filled path with `stroke:none` and
monkey emits a filled polygon with a nonzero stroke.

### Synthetic Semantic Policy

Used for broad synthetic cases where representation parity is not yet pinned.

Enforce:

- viewBox tolerance;
- element kind histogram within explicit case policy;
- style bucket histogram;
- filled black/white area;
- stroke-width histograms;
- drill knockout counts;
- circle radii histograms;
- coordinate match or bbox/area signature match.

This is the current oracle lane, strengthened and made reusable.

### Real-World Metrics Policy

Used initially for all real-world PCB SVG cases.

Generate but do not fail on all metrics at first:

- viewBox delta;
- element count delta;
- style bucket delta;
- filled area delta by color/style;
- white knockout area and count;
- stroke-width histogram delta;
- circle radius histogram delta;
- largest bbox/area offenders;
- layer runtime and file size.

Then ratchet stable cases into enforced gates with documented thresholds.

## Recorder And Object Identity Plan

Stock KiCad CLI SVG does not include UUIDs, so it cannot directly prove
per-source-object parity. The special KiCad recorder build is the path to
object identity.

Current local corpus already contains recorder dumps for several real-world
cases under paths such as:

- `tests/corpus/.unpacked/kicad/projects/speedy_processing_module/reference_output/recorder_dumps/`
- `tests/corpus/.unpacked/kicad/projects/taillight/reference_output/recorder_dumps/`

Implementation plan:

1. Inventory recorder dump schema for PCB SVG cases.
   - Confirm whether source object UUID, layer, role, and record boundaries
     are present for PCB output.
   - If not present, update the recorder patch before relying on it for
     object-level tests.

2. Extend or reuse existing recorder tooling:
   - `kicad_recorder_loader.py`
   - `kicad_recorder_drift.py`
   - `kicad_op_equivalence.py`
   - `test_L3_015_manifest_svg_ir_promotion.py`

3. Add per-record comparison:
   - KiCad recorder document grouped by source object/layer/role.
   - Monkey `pcb_to_ir` document grouped the same way.
   - Compare op kind sequence, style state, layer metadata, coordinates, and
     pad/drill roles before SVG rendering.

4. Use SVG structure comparison after record parity:
   - Render one record or small record group with `profile="kicad_cli"`.
   - Compare canonical draw items against recorder-derived expectations or
     CLI output.

Result:

- Stock CLI SVG remains the final visual/DOM oracle.
- Recorder output becomes the source-object oracle.
- Review SVG can keep enriched UUID groups without blocking strict CLI parity.

## Implementation Phases

### Phase 0: Baseline And Test Fixtures

1. Keep fresh generated CLI examples for local review only:
   - `case083__pad_chamfered_roundrect` F.Cu.
   - `speedy_processing_module` F.Cu.
2. Document the observed structure counts in this plan.
3. Ensure generated `__cli_fresh.svg` outputs stay ignored and are not added to
   the tracked corpus unless deliberately promoted.
4. Add a small helper command or script for regenerating one layer:
   - input board path;
   - layer list;
   - output path;
   - KiCad CLI path/version recorded in adjacent JSON.

Exit criteria:

- Any engineer can regenerate a KiCad CLI SVG and monkey SVG for one case/layer
  and inspect the same output locations.

### Phase 1: SVG Profile Plumbing

1. Add profile support to render options.
2. Make metadata emission conditional:
   - `svg_group` already supports id/data attributes.
   - `render_record` must pass id/data only when profile/options request it.
3. Preserve existing review behavior through explicit `profile="review"` in
   review tests.
4. Add `profile="kicad_cli"` to strict oracle generation.
5. Add L0 tests:
   - default/options behavior is stable;
   - `kicad_cli` suppresses record ids/data;
   - `review` includes record ids/data;
   - style buckets still wrap draw items correctly.

Exit criteria:

- `pcb.to_svg(profile="kicad_cli")` produces no monkey-only `data-*`.
- `pcb.to_svg(profile="review")` preserves UUID/data review hooks.
- Existing downstream tests that need metadata pass by requesting review mode.

### Phase 2: KiCad-Like Emitter Choices

Target the most important KiCad structural choices first.

1. Filled pads and filled polygons.
   - KiCad CLI commonly emits filled pad polygons as `<path>` with
     `stroke:none` and `fill-rule:evenodd`.
   - Decide whether monkey's `kicad_cli` profile converts filled polygons to
     path output while review mode may keep polygons.
   - Add strict synthetic tests for pad circle, rect, roundrect, custom pad,
     trapezoid, and regular polygon.

2. Vias/drills.
   - Preserve KiCad-like `circle` output where CLI emits circles.
   - Ensure white drill knockouts are ordered above copper.

3. Tracks and arcs.
   - Compare KiCad path/polyline decisions for straight tracks and arcs.
   - Add path command family checks for arcs.

4. Text and stroked text.
   - Keep current per-segment text mode where it is known to match CLI better.
   - Do not block this phase on exact font/path parity unless it affects PCB
     copper/mask geometry.

Exit criteria:

- `case083__pad_chamfered_roundrect` can run under strict structural policy.
- U17-style filled pad stroke inflation remains impossible.

### Phase 3: Canonical SVG Snapshot Library

1. Implement parser and canonical data structures.
2. Add unit tests with hand-authored SVG snippets:
   - inherited group style;
   - element style overriding group style;
   - nested transform flattening;
   - path/polygon/circle/rect extraction;
   - filled area including stroke;
   - stroke-width histograms;
   - path command family extraction.
3. Replace ad hoc area/style code in `tests/synthetic_board_svg_oracle.py`
   with this shared analyzer.
4. Keep existing function names as wrappers initially to reduce churn.

Exit criteria:

- Existing `test_L3_006` and `test_L3_007` pass through the new analyzer.
- New analyzer tests run without KiCad CLI.

### Phase 4: Synthetic Oracle Ratchet

1. Choose strict initial synthetic cases:
   - `case083__pad_chamfered_roundrect`
   - `case013__pad_smd_oval`
   - `case018__pad_th_oval`
   - `case084__pad_slot_hole`
   - `case019__via_basic`
   - arc sweep matrix case from the parity plan when added.
2. Add per-case policy declarations:
   - strict structural;
   - semantic only;
   - known text or zone tolerance.
3. Store comparison artifacts under case-local output:
   - monkey SVG;
   - CLI SVG;
   - canonical snapshot JSON;
   - diff/metrics JSON.
4. Fail CI on strict synthetic mismatches.

Exit criteria:

- Synthetic strict cases fail on path-vs-polygon/style regressions where
  emitter choice is intentionally pinned.
- Synthetic semantic cases catch area/style/count regressions.

### Phase 5: Real-World Broad Metrics

1. Generate all individual layer views for every active real-world
   `board_svg` case except documented schematic-only `_assembly` cases.
2. For each layer:
   - generate KiCad CLI SVG when CLI is available;
   - generate monkey `kicad_cli` SVG;
   - generate monkey `review` SVG;
   - generate canonical snapshots and metrics JSON.
3. Write outputs under each case's ignored `output/board_svg` folder.
4. Add a review index page with links to:
   - CLI SVG;
   - monkey CLI-mode SVG;
   - monkey review-mode SVG;
   - metrics JSON;
   - optional overlay.
5. Start as non-failing/manual for all real-world projects.
6. Promote stable cases/layers to enforced thresholds:
   - taillight F.Cu and Edge.Cuts;
   - charge_indicator selected copper/mask layers;
   - speedy F.Cu U17 region and selected layer metrics;
   - yoshi F.Cu/B.Cu via/drill metrics after visual review.

Exit criteria:

- One command populates real-world board SVG review artifacts and metrics for
  all active projects.
- At least taillight, charge_indicator, and speedy have enforced targeted
  regression tests.

### Phase 6: Recorder Object Parity

1. Audit recorder dumps for object identity.
2. Add missing recorder metadata if the patched KiCad build lacks PCB object
   UUID/layer/role boundaries.
3. Add a recorder-vs-monkey IR comparison lane for PCB records:
   - op kind sequence;
   - coordinates;
   - style;
   - layers;
   - roles;
   - record grouping.
4. Use object-level comparison to explain SVG structural mismatches.

Exit criteria:

- For at least one synthetic board and one real-world board, failures can be
  reported at source-object granularity rather than only board/layer level.

### Phase 7: CI And Signoff

Define test lanes:

- L0: no KiCad required.
  - profile option tests;
  - canonical SVG analyzer tests;
  - primitive emitter tests;
  - focused regression tests.

- L3 synthetic CLI:
  - requires standard KiCad CLI with `pcb export svg`;
  - strict structural and semantic oracle cases;
  - skips cleanly when CLI is unavailable unless running signoff.

- L3 real-world review:
  - manual or scheduled at first;
  - writes artifacts and metrics;
  - selected targeted real-world tests enforced.

- L99 release signoff:
  - requires documented KiCad CLI capability;
  - runs strict synthetic oracle;
  - runs targeted real-world regressions;
  - optionally runs broad metrics generation and checks no newly enforced
    thresholds fail.

Exit criteria:

- Public CI remains deterministic.
- Local/release signoff can require KiCad CLI explicitly.
- Missing KiCad capability reports a clear skip/failure policy.

## Files Likely To Change

Implementation:

- `src/py/kicad_monkey/kicad_sch_svg_renderer.py`
- `src/py/kicad_monkey/kicad_ir_to_svg.py`
- `src/py/kicad_monkey/kicad_pcb_ir_svg.py`
- `src/py/kicad_monkey/kicad_pcb.py`
- `src/py/kicad_monkey/kicad_footprint.py`
- possible new module: `tests/svg_oracle/canonical_svg.py`

Tests:

- `tests/L0_foundation/test_L0_006_svg_primitives.py`
- `tests/L0_foundation/test_L0_019_ir_to_svg_pcb_ops.py`
- `tests/L0_foundation/test_L0_034_pcb_ir_svg_wrapper.py`
- `tests/L3_rendering/test_L3_001_board_svg.py`
- `tests/L3_rendering/test_L3_006_synthetic_svg_oracle.py`
- `tests/L3_rendering/test_L3_007_pcb_ir_svg_oracle.py`
- `tests/L3_rendering/test_L3_015_manifest_svg_ir_promotion.py`
- `tests/synthetic_board_svg_oracle.py`
- review generation scripts under `tests/`

Docs:

- `docs/design/` PCB/IR/SVG contract document after implementation.
- `docs/adrs/ADR-002-kicad-test-corpus-and-lanes.md` if CI/test lane policy
  changes.
- `tests/README.md` for commands and artifact locations.

## Execution Order

Recommended commit-sized slices:

1. Add profile option and metadata gating.
2. Update tests to request `review` where they rely on ids/data.
3. Add `kicad_cli` profile use in oracle tests.
4. Add canonical SVG analyzer with unit tests.
5. Replace current semantic snapshot internals with analyzer-backed metrics.
6. Add strict structural policy for `case083`.
7. Add more synthetic strict cases.
8. Add real-world metrics generation command/page.
9. Add recorder object-parity audit and first enforced recorder comparison.
10. Promote durable decisions from this plan into design docs.

## Completion Criteria Before Returning To kicad_cruncher

- `kicad_monkey` can produce both KiCad-compatible and enriched PCB SVG
  outputs intentionally.
- Strict synthetic PCB SVG tests check effective styles and emitter choices for
  core pad/via/drill primitives.
- Area/style regressions like Speedy U17 fail without human review.
- Real-world PCB SVG review artifacts are generated consistently under the
  corpus-local output folders.
- At least taillight, charge_indicator, and speedy have targeted enforced
  real-world regressions.
- The public API and design docs explain which SVG profile consumers should
  use:
  - `kicad_cli` for oracle parity;
  - `review` for visual inspection and debug;
  - future `tooling` only if a consumer needs it.
- Relevant L0 and L3 rendering lanes pass, with KiCad CLI dependency behavior
  documented.
