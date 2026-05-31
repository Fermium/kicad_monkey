# KiCad Monkey Current Plan

Status: public-release baseline in progress as of 2026-05-31; complete for
the KiCad Monkey viz-enabling milestone as of 2026-05-18
Owner: kicad_monkey worktree

This is the single active plan for the KiCad Monkey rework. The previous
netlist, SVG/IR, variant, source-model, schematic OOP, and SVG coverage plans
are retired as separate planning surfaces. Use this file for current goals,
state, queue, and exit criteria.

Completion note: the milestone is complete for the intended downstream `viz`
handoff. The promoted parser/source-model, netlist, SVG/IR, manifest, and
render-cache gates are green; follow-on notes below are future hardening and
new-fixture promotion work, not blockers for consuming the KiCad Monkey class
library from `viz`.

## Restart Handoff: 2026-05-31 (public baseline)

Current branch: `kicad-monkey-public-baseline`.

Current direction: prepare `kicad-monkey` to leave the private `toolz`
workspace as a public package while keeping higher-level report/workflow code
in downstream cruncher packages such as the future `kicad-cruncher`.

Recent public-baseline work landed before this handoff:

- Package metadata, README, license, changelog, and date-version release
  contract for 2026-05-31.
- Package-root API cleanup and a reviewable promoted API contract in
  `kicad_monkey.kicad_api_contract`.
- Focused public facade coverage for schematic, PCB, footprint, project, and
  design APIs.
- Initial `L99_signoff` release gate for metadata, public API contract,
  interface design docs, source ruff, and package-wide pyright.
- Interface ownership docs under `docs/design/api/` governed by
  `docs/contracts/interface_design_manifest.v0.json`.
- Package-local KiCad corpus archive staged as `tests/corpus/kicad.zip`, with
  the loose `tests/corpus/kicad` mirror ignored and extracted on demand.
- Public contribution, issue-template, CI, and design-doc ownership rules are
  being aligned with `altium-cruncher` before the repository move.

Asset-review note:

- The staged corpus archive `tests/corpus/kicad.zip` contains the reviewed
  public KiCad fixture tree. The loose extracted mirror has 5,178 files and
  1,583,050,177 bytes; the zip is 307,084,659 bytes. Tests extract the archive
  locally when no external corpus is configured.
- The public corpus intentionally excludes generated/local-only trees,
  backup/debris files, the proprietary `fenton_fum` project, and the broken
  old `taillight` project. Former `crickets_*` project names were normalized,
  and customer-identifying strings in the retained LED assembly fixtures were
  replaced with fictitious names.
- No separate Altium move/public staging directory was found as the source for
  these KiCad assets. The current `WN_TEST_CORPUS` value points at
  `C:\eli\wn-hw\toolz-tests\corpus`, which currently has no `kicad/projects`
  tree, so this copy should be treated as sourced from the older
  `C:\eli\wn_test_corpus` location until the corpus location is reconciled.
- These copied assets still need final public-release review before the first
  public push. They are included for CI/test portability through Git LFS but
  remain excluded from sdist via `tests/corpus/**`.

Live fix made during this handoff:

- Recreated the private workspace `.venv` after removing a stale Linux-style
  `lib64` reparse point from the previous environment. `uv run` now uses
  `toolz/.venv/Scripts/python.exe` normally on Windows; the dedicated public
  verification venv remains a fallback only.
- Added `TEST_CORPUS_ROOT = tests/corpus` and made `tests/conftest.py` point
  `WN_TEST_CORPUS` there when no usable external KiCad corpus is configured.
- Added `scripts/package_kicad_corpus.py` and made CI check/extract
  `tests/corpus/kicad.zip` as the standard public corpus transport.
- Release metadata now targets the date-version release `2026.5.31`
  (`2026-05-31`).
- `version()` now falls back to source `__version__` when workspace metadata
  reports a non-date-contract distribution version such as the private
  workspace `0.1.0`.
- `KiCadObjectCollection.count()` now keeps the filtered count helper behavior
  while satisfying the inherited `Sequence.count(value)` signature for pyright.
- Package-wide pyright now reports zero diagnostics under the package
  `pyrightconfig.json`, and L99 hard-gates that run.
- App-owned KiCad symbol sync/watch behavior moved out of the public package
  boundary. `kicad_monkey` keeps parse/merge/split primitives and requires
  callers to pass library/preference paths explicitly instead of importing
  private workspace settings.
- API cleanup slice after the handoff replaced the legacy prefixed
  environment helpers with `KiCadEnvironment`, and replaced file-level prefixed
  filter exports with `KiCadFilterPipeline`. The filters
  stay in `kicad_monkey` because they encode KiCad file transforms; app and
  cruncher code decides which roots/files to process. Landed as:
  - `toolz` `38b70e3d kicad: replace prefixed environment and filter APIs`
  - `appz/lib_cruncher` `5f27ae7 lib-cruncher: use kicad object APIs`
  The separate prefixed name-index helper family was then replaced by
  `KiCadNameIndex`, keeping fast symbol/footprint name extraction available
  through an object API and removing the duplicated utility-module helpers.

Verification after the live fix:

```text
uv run --extra test pytest -q tests/L0_foundation tests/L99_signoff tests/L1_parsing/test_L1_019_project_fixture_review_set.py
-> 1301 passed
uv run --extra test pytest -q tests/L3_rendering/test_L3_014_corpus_manifest_hygiene.py
-> 11 passed
uv run --extra test pytest -q tests/L1_parsing/test_L1_008_shared_corpus_source_model_readiness.py
-> 17 passed
uv run --extra test pytest -q tests/L3_rendering/test_L3_013_design_json_contract.py
-> 3 passed
uv run --extra test pytest -q tests/L1_parsing/test_L1_010_kicad_cli_oracle_gate.py
-> 5 skipped (KiCad CLI binary is still an external tool dependency)
uv run --extra test python scripts/package_kicad_corpus.py --check
-> corpus archive valid
uv run --extra test python tests/rack.py run L0_foundation
-> 1266 passed
uv run --extra test python tests/rack.py run L99_signoff
-> 14 passed
uv run --extra test pyright
-> 0 errors, 0 warnings, 0 informations
uv run --extra test python -m build && uv run --extra test twine check dist/*
-> package build and metadata check passed
```

Next practical public-release slices:

1. Keep `src/py/kicad_monkey` package-wide ruff and pyright clean; L99 now
   hard-gates source ruff plus package pyright.
2. Prove the current API through internal `toolz`/`appz` consumers first:
   `lib_cruncher`, `pcb_cruncher`, installer/preference setup, then the future
   `kicad-cruncher`.
3. Keep L99 design-doc ownership strict for every promoted public class and
   major interface; add conformance contracts under `docs/contracts/` for any
   stable JSON/corpus/cruncher-facing format.
4. Finish the human review of `tests/corpus/kicad.zip` before pushing it to the
   public repository with Git LFS.
5. Start the sibling `kicad-cruncher` package against the public package
   boundary. Use that integration to decide which provisional `__all__` exports
   graduate into the promoted public contract.
6. Run existing `appz` and `toolz` consumers against the public/release package
   to validate the API surface before the first public tag.

## Goal

Make `kicad_monkey` a dependable KiCad backend for future `toolz/viz` KiCad
mode and for existing downstream tools. This effort is the parser/source-model,
netlist, SVG/IR, manifest corpus, and converter foundation. It does not include
the future KiCad UI work inside sch-viz.

Primary outcomes:

- `KiCadDesign.to_netlist()` matches KiCad's own netlist export on promoted
  strict-lane fixtures.
- KiCad S-expression parsing uses a KiCad-mode DSN lexer/tree builder with
  named compatibility productions instead of regex-driven structure parsing.
- `KiCadDesign.to_json(include_indexes=True)` has the closest practical shape
  to `AltiumDesign.to_json`, while preserving KiCad-specific fields under
  namespaced carriers.
- Generic `tools/data_models` bridges exist for KiCad design/netlist payloads.
- Schematic, board, symbol, and footprint SVG/IR coverage is manifest-driven
  across synthetic, upstream-QA, public-library, and real-world cases.
- `bom_cruncher` and `pcb_cruncher` still pass after this branch syncs to
  `origin/dev` and after pending `pcb_a0` data-model changes land.

The S-expression parser and render-cache OOP subplans are folded into this
document under `## Subplan: KiCad S-Expression Parser` and
`## Subplan: KiCad Render Cache OOP`.

## Restart Handoff: 2026-05-18 (current)

### Live iteration update: 2026-05-18

- **Phase E PCB SVG/IR cutover is now landed.** `KiCadPcb.to_svg()` routes
  through `render_pcb_ir_to_svg()` by default; `to_svg_ir()` remains as a
  compatibility alias and the legacy direct renderer remains explicitly
  available as `kicad_pcb_svg.render_pcb_svg`.
- Final cutover commits:
  - `toolz` `45b3e84a kicad(pcb): route to_svg through IR renderer`
  - `toolz` `31b47fb4 kicad(ir): synthesize text box knockout cache`
  - `toolz` `dc6ed0a1 kicad(ir): expand board text variables`
  - `toolz-tests` `9f6e5b1 test(kicad): ratchet PCB SVG IR cutover`
  - `toolz-tests` `ed348b9 test(kicad): cover text box knockout cache`
  - `toolz-tests` `6b3078e test(kicad): cover board text variable expansion`
- Final SVG/IR closure details:
  - Board text variable expansion now includes `board.project.text_variables`
    and feeds board-level `gr_text` before text op emission.
  - Board text-box knockout without a KiCad render-cache now synthesizes a
    typed even-odd render cache using KiCad-style stroke segment polygons plus
    the text-box frame contour. This closes `case106__text_frame_knockout`.
  - The public `to_svg()` entry point was cut over only after the unpatched
    L3_001 board SVG sweep passed on the IR renderer.
- Verification after the cutover:
  - `L0_foundation`: `1230 passed`
  - `L3_001_board_svg`: `1281 passed, 16 skipped`
  - `L3_006_synthetic_svg_oracle + L3_007_pcb_ir_svg_oracle`: `50 passed`
  - `L3_015_manifest_svg_ir_promotion`: `82 passed`
  - `L3_016_cli_svg_comparison`: `5 passed`
  - `L3_002`/`L3_003`/`L3_004`/`L3_005`: `181 passed`
  - `L4_001_project_verification`: `14 passed`
  - `ruff check` on touched source/tests: clean
- Netlist residual closure (follow-on cleanup): the pre-existing `taillight`
  drift is now closed. Hidden/dropped duplicate weak sheet-pin peers no longer
  make the one emitted terminal-bearing net depend on final materialization
  order (closing the `/DO_2` case), and the L3 real-project oracle now
  canonicalizes suffix-only permutations for repeated visible sheet-pin nets
  (same policy as the broad project-corpus gate). Oracle staging also skips
  `.history` / `.git` trees so regenerated goldens do not fail on corpus VCS
  internals.
- Netlist/design verification after the cleanup:
  - `L0_024_netlist_single_sheet + L0_025_netlist_multi_sheet`: `51 passed`
  - `L3_010_netlist_upstream_qa`: `5 passed`
  - `L3_011_netlist_kicad_cli_oracle`: `15 passed`
  - `L3_012_netlist_project_corpus_oracle`: `67 passed`
  - `L3_013_design_json_contract`: `3 passed`
  - `ruff check` on touched netlist source/tests: clean
- Final cleanup sweep verification:
  - `L3_006_synthetic_svg_oracle + L3_007_pcb_ir_svg_oracle`: `50 passed`
  - `L3_014_corpus_manifest_hygiene`: `11 passed`
  - `L3_015_manifest_svg_ir_promotion`: `82 passed`
  - `L3_016_cli_svg_comparison`: `5 passed`

### Historical Rendering Progress Notes (superseded)

The bullets below are retained to explain the path to the final SVG/IR cutover.
They are not active failures or current queue items; the live state is the
closure snapshot above.

- `toolz-tests` commit `870c662` updates the stale L0 oval-pad SVG
  expectation: IR oval pads now correctly assert as kicad-cli-style thick
  `<polyline>` segments with round caps, not filled stadium polygons.
- Full `L0_foundation` now passes locally: `1226 passed`.
- `toolz` commit `5de02fd1` threads the public PCB SVG color knobs through
  `to_svg_ir()` / `render_pcb_ir_to_svg()` and preserves explicit white
  knockout geometry in black-and-white mode. It also avoids duplicating
  synthesized drill outlines when a render requests multiple non-copper
  documentation layers together.
- `toolz-tests` commit `348e4c0` makes the L3_001 generation checks accept
  IR-native `<polygon>` / `<polyline>` shape elements where geometry is
  equivalent to legacy `<path>` output.
- Simulated L3_001 IR cutover baseline is now `42 failed, 1255 passed`
  (down from `47 failed, 1250 passed`). The old 6 generation-test bucket is
  reduced to one real charge-indicator NPTH/mask behavior issue.
- `toolz-tests` commit `e85e70d` makes L3_001 shape/circle extraction apply
  nested SVG transform matrices, so footprint-local IR output is compared in
  board coordinates instead of counting transformed shapes as mismatches.
- `toolz` commit `d368ecca` teaches the IR layer pre-filter and final SVG
  renderer that through-via apertures/drills span inner copper layers. Focused
  simulated IR case082 now closes the previous `In1.Cu` / `In2.Cu` failures;
  the remaining focused failures are charge-indicator NPTH mask semantics plus
  case082 all/outer-copper/mask/paste/silkscreen pad rendering gaps.
- An intermediate rendering batch made board
  `gr_text` opt into stroke-polylines without forcing unrelated footprint text,
  replaces fixed roundrect tessellation with KiCad arc-error tessellation, and
  adds mask-margin pad aperture variants for PCB IR. Verification:
  `L3_007` stays `26 passed`; focused simulated
  `synthetic_pad_shapes or charge_indicator_npth` is now `5 failed, 14 passed`
  (charge indicator closed; case082 F/B copper, paste, and inner copper closed).
- Follow-up rendering batch closes the focused case082/charge-indicator cluster under
  simulated IR: PCB board text now defaults to KiCad-centered alignment and
  preserves back-side mirror, custom/chamfer mask pads use rounded local buffer
  geometry for mask apertures, and `synthetic_pad_shapes or charge_indicator_npth`
  now reports `19 passed, 1278 deselected`. `L3_007` remains `26 passed`.
- Full simulated L3_001 IR cutover baseline after commit `9a430967` is
  `28 failed, 1269 passed`. The remaining failures are now concentrated in:
  KiCad stroke-font/variable text (`simple_test_kicad_font`, `case101`),
  `gr_text_box` text-frame cases (`case104`-`case108`), dimension geometry/text
  cases (`dim_*`), and `missing_elements` F.Cu/All_Layers coverage.
- Commits `cb33ffd2` (`toolz`) and `b3ae5ab` (`toolz-tests`) close the
  `missing_elements` text geometry gap and normal `gr_text_box` frame cases:
  board text boxes now default to KiCad center/center alignment, wrap within
  their text box width, and render built-in KiCad text as stroke polylines.
  L3_001 now skips zero-byte reference SVG files instead of treating an invalid
  empty oracle as a geometry failure. Focused simulated
  `missing_elements or text_frame` is down to the two knockout text-box cases
  (`case106` All/F.SilkS): `2 failed, 64 passed, 16 skipped`.
- Commit `45bfcd46` closes the dimension cluster under simulated IR by
  matching KiCad internal user-layer names (`Cmts.User`, `Dwgs.User`,
  `Eco*.User`) against the public layer names used by the L3 board SVG tests
  (`User.Comments`, `User.Drawings`, `User.Eco*`) in both the PCB IR
  prefilter and the final SVG op-visibility pass. Focused `-k "dim_"`
  now reports `112 passed, 1185 deselected`.

Latest functional commits before this docs cleanup:

- `toolz`: `db409185 kicad(netlist): stabilize weak sheet pin suffixes`
- `toolz-tests`: `e9f87a4 test(kicad): close netlist sheet pin drift`
- Working trees clean in both worktrees before this docs cleanup.

Recent commit chain (newest first):

```
db409185 kicad(netlist): stabilize weak sheet pin suffixes
80358f86 docs: record PCB SVG IR cutover
45b3e84a kicad(pcb): route to_svg through IR renderer
31b47fb4 kicad(ir): synthesize text box knockout cache
dc6ed0a1 kicad(ir): expand board text variables
4f04a233 docs: update dimension IR closure
45bfcd46 kicad(ir): match PCB user layer aliases
598ad1b4 docs: update text box IR progress
cb33ffd2 kicad(ir): align board text boxes with CLI
ebc94ba0 docs: record current IR cutover baseline

e9f87a4 test(kicad): close netlist sheet pin drift
9f6e5b1 test(kicad): ratchet PCB SVG IR cutover
ed348b9 test(kicad): cover text box knockout cache
6b3078e test(kicad): cover board text variable expansion
b3ae5ab test(kicad): cover board text box IR alignment
e85e70d test(kicad): apply SVG transforms in board comparisons
348e4c0 test(kicad): accept IR svg shape elements
870c662 test(kicad): expect oval pads as thick segment
```

Verification snapshot (post-IR cutover):

```text
L0_foundation                                      -> 1230 passed
L3_001 board_svg                                  -> 1281 passed, 16 skipped
L3_006 synthetic oracle + L3_007 IR oracle        -> 50 passed
L3_015 manifest SVG/IR promotion                  -> 82 passed
L3_016 CLI SVG comparison                         -> 5 passed
L3_002/003/004/005 SVG/rendering basics           -> 181 passed
L4_001 project verification                       -> 14 passed
ruff check touched source/tests                   -> clean
```

Broad L3 netlist/design sweep status after cleanup: green across the split
gates (`L3_010`: `5 passed`, `L3_011`: `15 passed`, `L3_012`: `67 passed`,
`L3_013`: `3 passed`). The previous `taillight` `/DO_2` vs `/DO_4` drift is
closed.


### Historical Note: Earlier Phase E Blocker 3 Closures

1. **Oval pad structural parity** (commit `0e5839e2`).
   `_render_flash_pad_oval_op` now emits a 2-point thick segment via
   `svg_polyline` (stroke-width = minor dim, linecap=round) when
   size_x ≠ size_y, and a filled circle when degenerate. Mirrors
   kicad-cli's `PCB_PLOTTER::PlotPad_Oval`. Closed 14 L3_001 layer
   cases under IR flip: case013 (×4) + case018 (×5) + one_slot_drill (×5).

2. **Chamfered roundrect structural parity** (commit `395ee046`).
   IR ROUNDRECT branch in `kicad_footprint_to_ir.py` now detects
   `chamfer_ratio > 0 + chamfer_corners` with `rratio ≈ 0` and
   dispatches to `flash_pad_custom` with the 5–8 vertex chamfered
   polygon. New helper `_chamfered_pad_local_polygon_nm` mirrors
   KiCad's `TransformRoundChamferedRectToPolygon` corner mutation.
   Closed 3 L3_001 layer cases: one_chamfer_roundrect (×3).

L3_001 IR-flip baseline: 64 → 47 failures (−17). L3_007 stays 26/26.

### Continuation message for next session

PCB SVG Phase E is closed; do not reintroduce the old env-flag cutover flow.
`KiCadPcb.to_svg()` is now the IR renderer. Use `render_pcb_svg()` only for
explicit legacy comparisons.

Next work should focus on follow-on hardening:

1. Optional hardening: add more direct L0 coverage for outline-font text-box
   knockout once a compact fixture is available. The current critical board
   stroke-font knockout is covered by L0 and L3_001 `case106`.
2. Longer full-L3 convenience: the monolithic `L3_rendering` run can exceed
   a 10-minute timeout on this workstation. The split gates listed above are
   the current practical verification path.

Validation flow for PCB SVG changes from here:

```powershell
$env:WN_TEST_CORPUS="C:/eli/wn_test_corpus"
$env:WN_TEST_SUITES_ROOT="C:/eli/agent-worktrees/kicad_monkey/toolz-tests"
uv run --project C:/eli/agent-worktrees/kicad_monkey/toolz/kicad_monkey pytest C:/eli/agent-worktrees/kicad_monkey/toolz-tests/suites/kicad_monkey/tests/L3_rendering/test_L3_001_board_svg.py -q --tb=short
uv run --project C:/eli/agent-worktrees/kicad_monkey/toolz/kicad_monkey pytest C:/eli/agent-worktrees/kicad_monkey/toolz-tests/suites/kicad_monkey/tests/L3_rendering/test_L3_006_synthetic_svg_oracle.py C:/eli/agent-worktrees/kicad_monkey/toolz-tests/suites/kicad_monkey/tests/L3_rendering/test_L3_007_pcb_ir_svg_oracle.py -q
uv run --project C:/eli/agent-worktrees/kicad_monkey/toolz/kicad_monkey pytest C:/eli/agent-worktrees/kicad_monkey/toolz-tests/suites/kicad_monkey/tests/L3_rendering/test_L3_015_manifest_svg_ir_promotion.py -q
```

Expected PCB/SVG results: L3_001 `1281 passed, 16 skipped`; L3_006+L3_007
`50 passed`; L3_015 `82 passed`.


## Historical Restart Handoff: 2026-05-16 (superseded)

This section is retained as project archaeology. Its blocked Phase E queue was
superseded by the 2026-05-18 SVG/IR cutover closure at the top of this plan.

Committed state at that time:

- `toolz`: `8cd76f13 docs: update kicad sexpr parser plan status`
- `toolz-tests`: `8487ed6 tests: cover kicad dsn sexpr parser`
- Both worktrees were clean at handoff.

Completed since the PCB SVG/IR work resumed:

- PCB IR now emits table grid geometry and first-pass dimension line/arrow
  geometry.
- KiCad S-expression parsing now uses `KicadSexprLexer` +
  `KicadSexprParser`; the old regex/Rosetta parser path and stale parser
  scaffolding are gone.
- The RoyalBlue KiCad 10 main board parser gap is resolved. The installed demo
  board parses through `KiCadPcb.from_file()` with 71 footprints, 96 nets, and
  197 teardrop pad parameter blocks.
- Overbar-only schematic text width now measures as the single visible string,
  removing the 100 nm global-label decoration rounding delta.

Current verification snapshot:

```text
pytest -q suites/kicad_monkey/tests/L0_foundation
  -> 1185 passed
pytest -q suites/kicad_monkey/tests/L1_parsing/test_L1_008_shared_corpus_source_model_readiness.py
  -> 17 passed
pytest -q suites/kicad_monkey/tests/L1_parsing/test_L1_001_pcb_roundtrip.py::TestParsing::test_parse_without_error suites/kicad_monkey/tests/L1_parsing/test_L1_001_pcb_roundtrip.py::TestSerialization::test_to_string_produces_valid_sexp suites/kicad_monkey/tests/L1_parsing/test_L1_001_pcb_roundtrip.py::TestRenderCache
  -> 79 passed
```

Superseded queue at that time:

1. PCB SVG/IR cutover Phase E — **blocked, full swap reverted 2026-05-17**.
   Attempted to flip `KiCadPcb.to_svg()` from `render_pcb_svg` to
   `render_pcb_ir_to_svg`; the IR pipeline is at 24/24 on the L3_007
   synthetic oracle but the L3_001 board_svg parity sweep flagged real
   coverage gaps in the IR renderer once it became the production path:
   - ~~Stroke-style propagation for `gr_line`/`gr_arc` (dashed, dotted,
     dash_dot, dash_dot_dot): IR currently emits one solid polyline per
     segment; kicad-cli emits one path per dash.~~ **Closed 2026-05-18.**
     New `kicad_stroke_decompose.py` module mirrors KiCad's
     `STROKE_PARAMS::Stroke` algorithm (ISO 128-2 ratios with
     correction=1.0: dash=11×w, gap=4×w, dot=0.2×w). Arc dashes are
     subdivided into 0.5° chord segments per kicad-cli; arc dots emit a
     single chord. `gr_line_to_ops` / `gr_arc_to_ops` (board) and
     `fp_line_to_ops` / `fp_arc_to_ops` (footprint, both pcb-loop and
     standalone) expand decomposable styles into per-dash
     `KiCadPlotterOp.thick_segment` ops. L3_007 ratcheted with six new
     stroke-style cases (line × 4 styles + arc dash_dot + dash_dot_dot).
   - Pad-shape edge cases: investigation 2026-05-18 confirmed `case013`
     (SMD oval), `case018` (THT oval), `case083` (chamfered roundrect),
     and `case084` (slot drill) already pass IR-vs-CLI metric parity —
     all three SMD/oval/chamfered cases ratcheted into L3_007.
     `case082__synthetic_pad_shapes` was investigated 2026-05-18 — the
     fixture name says "pad-per-layer" but actually tests rotated TH
     pads with `(drill X (offset Y Z))` plus 5 NPTH slot pads:
       1. **NPTH render-mode bug — CLOSED 2026-05-18.** The IR
          renderer's `_drill_render_mode` (in `kicad_ir_to_svg.py`)
          unconditionally returned `"black"` for `role == "npth_hole"`,
          mirroring legacy `_collect_npth_holes` which emits NPTH as
          black apertures. kicad-cli emits NPTH **identically to PTH**
          on copper/mask layers (white knockout). Removed the special
          case so NPTH follows the same layer-based mode logic as
          `pad_drill`. case082 F.Cu went from white_drill_circles
          29/34 + white_stroke_paths 10/15 → both 34/34 + 15/15.
          F.Mask gained 5 white_stroke_paths (10→15) and 5
          white_drill_circles (15→20; CLI=21, one residual round
          drill still missing). L3_007 + L0_034 baseline preserved
          (31/31 passing). L3_001 baseline unchanged (36 failures
          before and after — none of them depend on IR rendering of
          NPTH).
       2. viewBox 0.114 mm wider / 0.116 mm taller than CLI — comes
          from `compute_pcb_bounding_box` using `_to_poly()` which
          inflates by half-stroke. CLI uses centerline bbox. Same
          bug affects legacy renderer (both have identical viewBox
          drift). Affects all L3_001 IR comparisons but masked by
          L3_001's tolerance=0.5 mm coord match. Blocks case082
          ratchet into L3_007 (the F.Cu drill-knockout fix above is
          real but the viewBox metric still fails `viewbox_tol_mm=0.1`).
   - Dimension geometry parity for the legacy-failing radial / orthogonal
     / leader / aligned cases that still trip L3_001 thresholds.
     **Phase E reattempted + reverted 2026-05-18.** Flipping
     `pcb.to_svg()` to IR took L3_001 from 33 → 67 failures: dim cases
     STILL failed after the flip (IR matches CLI on count/viewBox per
     L3_007's semantic metrics, but L3_001's path-d coordinate match
     is stricter and catches sub-mm coord drift), AND ~24 pad/text/font
     cases that pass on legacy regressed under IR rendering. The IR
     renderer needs coord-level dim parity + closure of the new
     regression cases (one_chamfer_roundrect / one_slot_drill / case013 /
     case018 / case082 expansion / simple_test_kicad_font /
     synthetic_board_cutouts / 7 generation-specific tests) before
     Phase E can land. Net win is real on dims at the IR-vs-CLI level
     but not at L3_001 path-d level — needs more investigation.
   Phase E is staged via the new `KiCadPcb.to_svg_ir()` opt-in (callers
   that want the IR path can use it explicitly); `KiCadPcb.to_svg()`
   remains on the legacy direct renderer until the IR gaps above close.
   Test infrastructure was upgraded along the way: L3_001's
   `compare_svg_shapes` now handles `<polyline>`, `<polygon>`, `<rect>`,
   `<line>` shape elements and accumulates `<g transform="translate(...)">`
   from ancestor groups (it was previously only parsing `<path d="...">`,
   which silently zeroed-out IR-emitted SVGs). Path-d regex now uses a
   negative lookbehind so `data-uuid="..."` no longer pollutes coords.

   ### Phase E blocker iteration queue (2026-05-18)

   Ordered by tractability / blast-radius:

   1. ~~**viewBox half-stroke inflation** in `compute_pcb_bounding_box`.~~
      **CLOSED 2026-05-18** (commit `a66723d9`). Both
      `compute_pcb_bounding_box` and
      `compute_footprint_bounding_box_on_layers` now compute centerline-only
      bounds (no `_to_poly()` half-stroke inflation). L0_034 updated to
      pin the new exact bounds. L3_001 baseline 33 → 28 failures, no
      new regressions. case082 viewBox now matches CLI within tolerance.
   2. ~~**case082 F.Mask residual** (1 missing `white_drill_circle`,
      20/21).~~ **CLOSED 2026-05-18.** Root cause: case082 includes
      vias with explicit `(tenting (front no) (back no))` that
      kicad-cli renders as a mask opening + drill knockout on F.Mask /
      B.Mask. The IR converter emitted neither. Fixed by adding
      `via_mask_opening_to_op` + `via_mask_drill_to_op` synthesizers in
      `kicad_pcb_to_ir.py`, threading `pad_to_mask_clearance` from the
      board into `via_to_record`, and adding `via_mask_drill` to
      `_DRILL_ROLES` in `kicad_ir_to_svg.py` so the knockout renders
      white. `via_to_op` now carries `role="via_aperture"` + `layers`
      so the per-op filter restricts the copper aperture to copper
      layers (CLI does not emit it on mask). New IR-only oracle cases
      `pad_per_layer_shapes_f_mask` / `pad_per_layer_shapes_b_mask`
      ratcheted into L3_007 (now 26/26). L3_006 stays on its 2
      pre-existing legacy failures.
   3. **Regression cluster under IR rendering** (Phase E re-tested
      2026-05-18 with `KICAD_MONKEY_PCB_TO_SVG_IR=1` env flag against
      L3_001). Baseline 28 legacy failures → IR baseline 64 → after
      pad-shape fixes 47 (−17 net new). Iteration progress:
      - **Oval pad CLOSED 2026-05-18** (commit `0e5839e2`).
        `_render_flash_pad_oval_op` now emits a 2-point thick segment
        (svg_polyline + stroke-width = minor dim, linecap=round) when
        size_x≠size_y, and a filled circle when degenerate — mirrors
        kicad-cli's `PCB_PLOTTER::PlotPad_Oval`. Closed 14 layer
        cases: case013 (×4) + case018 (×5) + one_slot_drill (×5).
      - **Chamfered roundrect CLOSED 2026-05-18** (commit `395ee046`).
        IR ROUNDRECT branch now detects `chamfer_ratio>0 +
        chamfer_corners` with rratio≈0 and dispatches to
        `flash_pad_custom` with the 5–8 vertex chamfered polygon
        (helper `_chamfered_pad_local_polygon_nm` mirrors KiCad's
        `TransformRoundChamferedRectToPolygon`). Closed 3 layer cases:
        one_chamfer_roundrect (×3).
      - **6 generation tests** assume `<path d=>` element extraction
        (`extract_paths_from_svg` is path-only). IR emits
        `<polygon>`/`<polyline>`/`<rect>` for the same geometry, so
        the extractor returns `[]`. These are *test infrastructure*
        gaps, not renderer bugs:
        `test_chamfer_roundrect_pad_renders_chamfer_polygon`,
        `test_oval_drill_renders_slot_geometry`,
        `test_custom_pad_gr_poly_primitives_render_without_skip_warning`,
        `test_layers_none_matches_explicit_all_layers_drill_semantics`,
        `test_black_and_white_false_honors_custom_colors`,
        `test_charge_indicator_npth_holes_render_as_board_apertures`.
      - **case082 synthetic_pad_shapes (10 layers)**: residual
        over-emission. IR F.Cu emits 88 raw circles (60 unique after
        offset+round) vs CLI's 68 unique. Extras cluster at 4 drill
        radii (0.35/0.38/0.40/0.60 mm) × 5 dupes each = 20 over-
        emissions. The 5-at-r=0.35 set maps to the 5 footprints
        `Synthetic:drill_offset_r000…r123` (each carries a pad with
        `drill_offset` and varied `at_angle`). Need to dig: extra
        circles at the other 3 radii likely come from the 16 via
        copper apertures double-emitting (memory says 10× size 0.75
        + 5× size 1 + 1× ?). Next investigation: dump per-circle
        provenance under IR for case082 F.Cu and locate which op
        emits the dupes.
      - **Remaining clusters (~26 layer cases)**: `missing_elements`
        needs gr_curve + image + gr_text_box IR support; `case101 +
        case104–case108` cluster is stroke-font text frame geometry;
        `simple_test_kicad_font` and `synthetic_board_cutouts` need
        per-case diff. The 14 dim_* layer cases stay scoped under
        Blocker 4 (coord-level dim parity).
      Next steps: (a) finish case082 dup-circle diagnosis; (b) audit
      `gr_curve` / `image` / `gr_text_box` IR support (or accept as
      out-of-scope for first IR cutover); (c) extend
      `extract_paths_from_svg` to also pick up
      `<polygon>` / `<polyline>` / `<rect>` shape elements to close
      the 6 generation tests.
   4. **IR dimension geometry coord parity at L3_001 path-d level**
      (radial / orthogonal / leader / aligned). L3_007 metric parity
      holds (24/24) but L3_001's tolerance=0.5 mm path-d match catches
      sub-mm drift. Requires per-case CLI-vs-IR coord diff to pinpoint
      whether the gap is in dimension shape ops, stroke-font text ops,
      or coordinate transform. Deepest investigation; tackled last.
2. Phase 3 synthetic corpus — TTF text gaps remaining: case033
   (rotated TTF variant), case099 / case103 (font specials).
   These need a render_cache emission helper that runs FreeType
   during the generator pass; deferred until the helper lands.
   case101 + case104–case108 already shipped in the first Phase 3
   increment (stroke-font cases).
3. ~~Audit footprint-local table and dimension transforms before reusing
   the board-level PCB IR helpers there (Phase D).~~ **No-op, closed
   2026-05-17.** Confirmed by inspecting `kicad_footprint.Footprint` — the
   model carries `fp_line` / `fp_arc` / `fp_circle` / `fp_rect` / `fp_poly`
   / `fp_text` / `fp_text_box` / `pad` / `zone` / `model` / `property` but
   has no `fp_table` or `fp_dimension` slot. KiCad's S-expression schema
   keeps tables and dimensions at the board level only; the IR helpers
   `table_to_record` / `dimension_shape_ops` / `dimension_text_to_record`
   are only invoked from the board-level loop in `pcb_to_ir` (lines
   1514-1518) and never under a footprint-transform context. No work
   needed.
4. ~~Add typed parse errors/span propagation after the parser-only corpus
   gate is stable, so downstream tools can distinguish lex, tree, dialect,
   and OOP failures.~~ **Phase 4 closed 2026-05-17.** `SexprError` now has
   three typed subclasses (`SexprLexError`, `SexprTreeError`,
   `SexprDialectError`) each pinning their parse stage via a `phase` class
   attribute (`"lex"` / `"tree"` / `"dialect"`). `KicadSexprLexer` raises
   `SexprLexError` for token-level failures; `KicadSexprParser` raises
   `SexprTreeError` for list-tree failures. Both subclasses inherit from
   `SexprError`, so legacy `pytest.raises(SexprError, match=...)` blocks
   keep working unchanged. `with_source_path` preserves the concrete
   subclass on the copy. `SexprDialectError` is reserved for future use —
   today every entry in `PARSER_DIALECT_EXCEPTIONS` is *accepted*, not
   rejected. 7 new pinning tests in `test_L0_033_kicad_sexpr_parser.py`.
   Build/reparse/compare stages remain unchanged (handled by
   `SexpRoundtripResult.phase`).

Recently closed (2026-05-17):

- Synthetic corpus Phase 3 (stroke-font increment). Landed
  `synthetic_corpus/generate_text.py` (case101 string-replacement
  via `${SYNTHETIC_FIXTURE}` token) and
  `synthetic_corpus/generate_text_frames.py` (case104–case108
  gr_text_box variants: basic / no_border / knockout / align_left /
  rotated). Driver registers two new families (`text` /
  `text_frames`). 6 new cases written via the OO model — `GrText`
  with `${VAR}` payload exercises kicad-cli's text variable
  substitution (the staged CLI expands it to the project name);
  `GrTextBox` with stroke font renders natively without
  render_cache. References regenerated (1270 SVGs / 81 cases);
  manifest 324 → 330. L0_foundation + L1_019 + L3_007 = 1244
  passed. L3_001 12 new failures join the pre-existing 21
  legacy-renderer divergences — same Phase E pattern (legacy
  `render_pcb_svg` text emission ≠ staged kicad-cli). The TTF
  text slots (case033, case099, case103) were left out of that
  increment because they need a FreeType-driven render_cache emission helper.
- Synthetic corpus Phase 2 (case001–case025 Altium-aligned slots).
  Landed `kicad_monkey/scripts/synthetic_corpus/` package
  (`common.py` + `generate_tracks.py` / `generate_arcs.py` /
  `generate_pads.py` / `generate_vias.py` / `generate_fills.py`)
  and driver `scripts/generate_kicad_synthetic_corpus.py`. 19 new
  cases written via the OO model (no S-expr templating):
    * tracks  case001 / case002 / case003 (1 mil / 25 mil / 50 mil)
    * arcs    case007 / case008 / case010 (90° / 180° / 270°)
    * pads    case011–case018 (SMD rect/round/oval, THT round/rect,
      B.Cu SMD, 1×4 pad array, THT oval)
    * vias    case020 / case021 / case022 (small / large / 5-via array)
    * fills   case023 / case025 (3×3 mm F.Cu, 5×2.75 mm B.Cu)
  References regenerated through staged kicad-cli `76f8839fd232`
  (1190 SVGs across 75 cases) after fixing
  `toolz-tests/.../generate_board_svg_references.py` regen loop
  (`_export_board_layer` helper; per-case CLI invocation). Manifest
  rebuilt 305 → 324 cases. L0_foundation 1219 passed, L3_007 15/15,
  L1_019 + L3_007 25 passed. L3_001 21 failures isolated to
  pre-existing legacy `render_pcb_svg` divergences (case082 /
  case122 / case220–226); zero failures on Phase 2 new cases.
- Former L3_007 leader dimension xfails (`dim_leader_plain` /
  `dim_leader_frame_rect`) → diagnosed as text-content gap
  (`format.override_value` drives leader text in CLI; user gr_text is
  ignored) plus `text_frame == 1` rectangle-side emission.
  Now 15/15 across all enforced metrics.
- L3_001 board_svg pivoted to manifest-driven enumeration
  (`iter_kicad_corpus_cases(domain="board_svg")` synthetic
  case_bucket filter). `LEGACY_CASE_MAP` retired in favor of
  `LEGACY_CASE_IDS` (manifest case_id lookups). 685/685 green.

## Version Policy

Supported input format is KiCad S-expression only:

| KiCad major | Release date | Corpus lane |
|---|---|---|
| 10 | 2026-03-20 | strict oracle |
| 9 | 2025-02-20 | strict oracle |
| 8 | 2024-02-23 | compatibility candidate |
| 7 | 2023-02-12 | compatibility candidate |

Implementation rule: keep active work focused on `.kicad_pro`, `.kicad_sch`,
`.kicad_pcb`, `.kicad_sym`, and `.kicad_mod`. KiCad 9/10 cases must pass.
KiCad 7/8 may be admitted only as explicit compatibility lanes in the manifest.
KiCad 5.x and older legacy `.sch` files are out of scope.

## Current Baseline

Corpus and oracle:

- Canonical corpus root: `C:\eli\wn_test_corpus\kicad`.
- Manifest: `C:\eli\wn_test_corpus\kicad\manifest.json`, generated by
  `kicad_monkey/scripts/build_kicad_corpus_manifest.py`.
- Manifest count: 301 cases.
- Active cases: 279. Reference-only cases: 22.
- Real-world cases: 16 total, all active.
- Active `board_svg` / `pcb_ir` cases: 71 total, all active: 55 synthetic
  board fixtures plus 16 real-world projects.
- Canonical KiCad CLI oracle is resolved through
  `toolz-tests/tools/kicad-cli/MANIFEST.toml`; current staged hash:
  `f11d3da6771a`.
- The staged `f11d3da6771a` CLI supports schematic SVG/netlist export and
  recorder dumps via `KICAD_RECORDER_OUTPUT=...`. It is a locally patched
  release build from KiCad `f11d3da6771a` with high-level schematic
  `PlotText()` recorder payloads enabled; its version string is dirty by
  design: `10.0.0-912-gf11d3da677-dirty`. PCB SVG live-oracle tests must ask
  the resolver for `required_capability="pcb_svg"` because the schematic
  recorder cache does not include `_pcbnew.dll`; on the current workstation
  that resolves to the installed KiCad 10 CLI.
- Recorder provenance is tracked under
  `C:\eli\wn_test_corpus\tools\kicad-cli\f11d3da6771a\provenance.json`.
- Top-level real-world recorder oracle dumps are frozen for the retained
  real-world electronics projects under project
  `reference_output\recorder_dumps`.
  Active recorder cases are `cm5_minima_rev2.1`,
  `charge_indicator.1`, `eez_dcp405plus.1`, `icepi_zero_v13.1`,
  and `jumperless_v5r7.1`. Reference-only recorder
  cases are `canbob.1`, `cern_wren_eda_04903.1`, `taillight.1`,
  `icepi_sbc.1`, `nrf9151_feather.1`, and
  `speedy_processing_module.1`.

Active real-world strict-lane projects:

- `canbob`
- `cm5_minima_rev2`
- `celebration_led_assembly`
- `charge_indicator`
- `charge_indicator_assembly`
- `taillight`
- `taillight_assembly`
- `speedy_processing_module`
- `cern_wren_eda_04903`
- `eez_dcp405plus`
- `icepi_sbc`
- `icepi_zero_v13`
- `jumperless_v5r7`
- `nrf9151_feather`
- `yoshi_mainboard`

Normalized real-world project shape:

```text
C:\eli\wn_test_corpus\kicad\projects\<case_id>\input
C:\eli\wn_test_corpus\kicad\projects\<case_id>\output
C:\eli\wn_test_corpus\kicad\projects\<case_id>\reference_output
```

One internal-only project fixture was removed from the package-local public
baseline on 2026-05-31; retained real-world fixtures must have public-project
provenance or be synthetic/internal library samples safe for distribution.

## Verification Baseline

Current focused gates, verified 2026-05-12:

```text
pytest -q suites\kicad_monkey\tests\L0_foundation\test_L0_024_netlist_single_sheet.py suites\kicad_monkey\tests\L0_foundation\test_L0_025_netlist_multi_sheet.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_012_netlist_project_corpus_oracle.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_013_design_json_contract.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_014_corpus_manifest_hygiene.py suites\kicad_monkey\tests\L3_rendering\test_L3_015_manifest_svg_ir_promotion.py
```

Result: 47 passed; 64 passed; 3 passed; 52 passed.

Downstream smoke checks after `git fetch origin`, verified 2026-05-12:

```text
toolz\pcb_cruncher: 5 passed
appz\bom_cruncher L0_foundation: 50 passed
toolz\data_models Part A0 runtime: 7 passed
```

Additional parser regression checks from the public-corpus hardening pass:

- `test_L1_001_pcb_roundtrip.py`: 584 passed.
- `test_L1_003_oop_equivalency.py`: 300 passed.

Field-map converter checks from the design JSON alignment pass:

- `toolz\data_models` KiCad design converter: 1 passed.
- `toolz\data_models` Altium design converter parity guard: 15 passed.
- `toolz-tests` KiCad design JSON contract: 3 passed.
- Focused KiCad endpoint and design JSON contract guards: 80 passed.
- `toolz\data_models` KiCad/Altium endpoint metadata converter guards:
  16 passed.

SVG/IR oracle strengthening checks:

- Current strict comparison L0 gate:
  `test_L0_007_lib_symbol_to_ir.py`, `test_L0_008_schematic_to_ir.py`,
  `test_L0_009_ir_to_svg.py`, `test_L0_013_drawing_sheet.py`,
  `test_L0_015_op_equivalence.py`, plus recorder loader/drift coverage in
  `test_L0_010_recorder_loader.py` and `test_L0_011_recorder_drift.py`:
  375 passed.
- Current manifest recorder gate with all top-level real-world recorder oracle
  dumps: `test_L3_014_corpus_manifest_hygiene.py` plus
  `test_L3_015_manifest_svg_ir_promotion.py`: 63 passed.
- Current real-world recorder parity pass, verified 2026-05-13:
  default op equivalence canonicalizes recorder `ThickSegment` against
  unfilled two-point `PlotPoly`, splits multiline logical `Text` into
  KiCad's plotted line stream, and standalone `schematic_to_ir()` infers
  adjacent project text variables plus project sheet count for worksheet
  expansion. Current strict comparison L0 gate: 375 passed.
  Active real-world top-sheet ratios at 10um, all with zero style mismatches:
  `cm5_minima_rev2.1` 604/624, `charge_indicator.1` 464/485,
  `eez_dcp405plus.1` 298/298, `icepi_zero_v13.1` 865/905, and
  `jumperless_v5r7.1` 9950/10810.
- Current regenerated manifest SVG/IR promotion gate:
  `test_L3_015_manifest_svg_ir_promotion.py`: 46 passed.
- `test_L3_014_corpus_manifest_hygiene.py` plus
  `test_L3_015_manifest_svg_ir_promotion.py`: 63 passed.
- Full SVG-focused regression gate: 1,535 passed.

PCB SVG/IR audit gates, verified 2026-05-14:

```text
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_001_board_svg.py suites\kicad_monkey\tests\L3_rendering\test_L3_006_synthetic_svg_oracle.py
pytest -q suites\kicad_monkey\tests\L0_foundation\test_L0_019_ir_to_svg_pcb_ops.py suites\kicad_monkey\tests\L0_foundation\test_L0_020_pcb_to_ir.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_014_corpus_manifest_hygiene.py suites\kicad_monkey\tests\L3_rendering\test_L3_015_manifest_svg_ir_promotion.py
toolz\data_models KiCad converter slice: test_kicad_pad_mapping.py, test_kicad_arc_mapping.py, test_converters_kicad.py, test_converters_kicad_design.py
toolz\pcb_cruncher: suites\pcb_cruncher\tests
```

Result: 795 passed; 45 passed; 90 passed; 46 passed; 5 passed.

`git diff --check` is clean aside from existing LF-to-CRLF warnings.

PCB IR layer-filter slice, verified 2026-05-15:

```text
pytest -q suites\kicad_monkey\tests\L0_foundation\test_L0_019_ir_to_svg_pcb_ops.py suites\kicad_monkey\tests\L0_foundation\test_L0_020_pcb_to_ir.py
ruff check kicad_monkey\src\py\kicad_monkey\kicad_ir_to_svg.py kicad_monkey\src\py\kicad_monkey\kicad_pcb_to_ir.py
ruff check suites\kicad_monkey\tests\L0_foundation\test_L0_019_ir_to_svg_pcb_ops.py suites\kicad_monkey\tests\L0_foundation\test_L0_020_pcb_to_ir.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_006_synthetic_svg_oracle.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_001_board_svg.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_015_manifest_svg_ir_promotion.py::test_promoted_real_world_board_renders_review_layers_from_manifest suites\kicad_monkey\tests\L3_rendering\test_L3_015_manifest_svg_ir_promotion.py::test_custom_pads_project_board_ir_covers_custom_and_trapezoid_pads_from_manifest
```

Result: 52 passed; ruff clean; 6 passed; 789 passed; 17 passed.

PCB IR drill-overlay slice, verified 2026-05-15:

```text
pytest -q suites\kicad_monkey\tests\L0_foundation\test_L0_017_footprint_to_ir.py suites\kicad_monkey\tests\L0_foundation\test_L0_019_ir_to_svg_pcb_ops.py suites\kicad_monkey\tests\L0_foundation\test_L0_020_pcb_to_ir.py
ruff check kicad_monkey\src\py\kicad_monkey\kicad_footprint_to_ir.py kicad_monkey\src\py\kicad_monkey\kicad_pcb_to_ir.py kicad_monkey\src\py\kicad_monkey\kicad_ir_to_svg.py kicad_monkey\src\py\kicad_monkey\__init__.py
ruff check suites\kicad_monkey\tests\L0_foundation\test_L0_017_footprint_to_ir.py suites\kicad_monkey\tests\L0_foundation\test_L0_019_ir_to_svg_pcb_ops.py suites\kicad_monkey\tests\L0_foundation\test_L0_020_pcb_to_ir.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_006_synthetic_svg_oracle.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_001_board_svg.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_015_manifest_svg_ir_promotion.py::test_promoted_real_world_board_renders_review_layers_from_manifest suites\kicad_monkey\tests\L3_rendering\test_L3_015_manifest_svg_ir_promotion.py::test_custom_pads_project_board_ir_covers_custom_and_trapezoid_pads_from_manifest suites\kicad_monkey\tests\L3_rendering\test_L3_015_manifest_svg_ir_promotion.py::test_public_official_footprints_render_to_ir_and_svg_from_manifest
```

Result: 96 passed; ruff clean; 6 passed; 789 passed; 25 passed.

PCB IR text-box slice, verified 2026-05-15:

```text
pytest -q suites\kicad_monkey\tests\L0_foundation\test_L0_017_footprint_to_ir.py suites\kicad_monkey\tests\L0_foundation\test_L0_020_pcb_to_ir.py
ruff check kicad_monkey\src\py\kicad_monkey\kicad_fp_text_box.py kicad_monkey\src\py\kicad_monkey\kicad_pcb_graphics.py kicad_monkey\src\py\kicad_monkey\kicad_pcb_footprint.py kicad_monkey\src\py\kicad_monkey\kicad_footprint.py kicad_monkey\src\py\kicad_monkey\kicad_footprint_to_ir.py kicad_monkey\src\py\kicad_monkey\kicad_pcb_to_ir.py kicad_monkey\src\py\kicad_monkey\kicad_pcb_svg.py kicad_monkey\src\py\kicad_monkey\__init__.py
ruff check suites\kicad_monkey\tests\L0_foundation\test_L0_017_footprint_to_ir.py suites\kicad_monkey\tests\L0_foundation\test_L0_020_pcb_to_ir.py
python -m py_compile kicad_monkey\src\py\kicad_monkey\kicad_fp_text_box.py kicad_monkey\src\py\kicad_monkey\kicad_pcb_graphics.py kicad_monkey\src\py\kicad_monkey\kicad_pcb_footprint.py kicad_monkey\src\py\kicad_monkey\kicad_footprint.py kicad_monkey\src\py\kicad_monkey\kicad_footprint_to_ir.py kicad_monkey\src\py\kicad_monkey\kicad_pcb_to_ir.py kicad_monkey\src\py\kicad_monkey\kicad_pcb_svg.py kicad_monkey\src\py\kicad_monkey\__init__.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_015_manifest_svg_ir_promotion.py::test_promoted_real_world_board_renders_review_layers_from_manifest suites\kicad_monkey\tests\L3_rendering\test_L3_015_manifest_svg_ir_promotion.py::test_public_official_footprints_render_to_ir_and_svg_from_manifest
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_001_board_svg.py
pytest -q suites\kicad_monkey\tests\L3_rendering\test_L3_003_element_coverage.py
```

Result: 75 passed; ruff clean; py_compile clean; 24 passed; 789 passed;
46 passed. Documentation-board corpus check parsed 443 footprints, found 2
`fp_text_box` items, and emitted expanded `TP11`/`TP1` `User.4` text ops.

## Implementation State

Source model and parser:

- Schematic, symbol-library, worksheet, PCB, project, and footprint OOP parsing
  are the authoritative source-model path.
- S-expression filter/extract APIs are public and complete for current
  consumers.
- KiCad 10-era PCB surfaces are modeled: named `NetRef`, outline carriers,
  pad/via drill modifiers, footprint pad groups, placement metadata,
  component classes, barcodes, generated objects, and adjacent `.kicad_pro`
  project context.
- Public-corpus scan closed two modern parser gaps: `LayerType.AUXILIARY` and
  pad drill offsets such as `(drill oval 1 (offset -0.5 0))`.

Netlist:

- `KiCadDesign.to_netlist()`, `refresh_netlist()`,
  `to_kicad_netlist_sexpr()`, `to_netlist_json()`, `get_net()`, and
  `get_component()` are implemented.
- Live KiCad CLI parity is green for 4 supported upstream QA netlist fixtures,
  all 12 active real-world projects, and 64 broad modern project-rooted
  candidates.
- L3 netlist tests are manifest-first and stage temporary project copies so
  KiCad-generated `.kicad_prl` files do not pollute corpus `input`.

Design JSON and data models:

- `KiCadDesign.to_json(include_indexes=True)` emits
  `kicad_monkey.design.a1` with Altium-style top-level fields:
  `schema`, `generator`, `project`, `variants`, `options`, `sheets`,
  `components`, `schematic_hierarchy`, `nets`, optional `pnp`, and `indexes`.
- `KiCadDesign.to_kicad_netlist_json()` emits native KiCad netlist JSON.
- `to_netlist_json()` remains the generic `netlist_a0` bridge.
- `data_models.converters.design_from_kicad_design_json()` stamps generic
  payloads with `cad=kicad`, KiCad-owned hierarchy metadata, KiCad project
  variant metadata, and KiCad source labels on project parameters.
- Current graphical indexes cover component SVG groups and net-connected
  schematic objects. Net graphical arrays now carry wire, junction, label,
  power-port, hierarchical-port, sheet-entry, and pin refs. Indexes include
  `svg_to_component`, `component_to_nets`, `net_to_components`,
  `svg_to_net`, and `net_to_graphics`.
- Pin endpoints use Altium-style endpoint IDs (`pin:<designator>:<pin>`).
  KiCad schematic IR/SVG emits visible placed pins as nested `symbol_pin`
  groups keyed by the placed-pin UUID when available. Pin refs use those
  groups as the current render target (`svg_id` / `element_id`) and preserve
  source placed-pin identity (`source_pin_id` / `object_id`); hidden pins fall
  back to the placed symbol group because no pin group is rendered.
  The generic converter also carries distinct `source_pin_id` values in
  pin-link metadata.
- Non-pin semantic endpoints now cover KiCad power ports, hierarchical ports,
  and sheet entries with Altium-style roles (`power_port`, `port`,
  `sheet_entry`), render/source IDs, source sheet paths, and schematic
  connection points in `kicad_sch_iu`. Generic conversion merges this endpoint
  metadata onto net artifact links.

Variants and hierarchy:

- KiCad project variant catalog parsing, schematic/PCB variant override parsing,
  effective-property resolution, BOM oracle parity, POS oracle parity, and
  variant write APIs are implemented.
- Native design JSON exports KiCad variant catalog entries, schematic DNP/field
  override effects, and a KiCad-owned hierarchy envelope.
- The KiCad/Altium/generic field map is documented in
  `kicad_monkey/docs/requirements/KICAD_DESIGN_JSON_FIELD_MAP.md`. Do not
  change `altium_monkey` semantics for this effort.

SVG and IR:

- Plotter IR, IR-to-SVG, schematic-to-IR, symbol-to-IR, footprint-to-IR,
  PCB-to-IR, variant overlay, recorder loader, recorder drift tooling, and
  op-equivalence helpers are implemented.
- PCB SVG currently has two distinct paths. `KiCadPcb.to_svg()` still uses the
  direct board renderer in `kicad_pcb_svg.py`, and that path is the current
  parity baseline against stored KiCad CLI SVG references. `pcb_to_ir()` plus
  `render_ir_to_svg()` exists and is unit-covered for core plotter op dispatch.
  PCB-embedded footprint placement is applied as an SVG group transform around
  footprint-local IR records, and the IR SVG renderer now accepts
  `KiCadSvgRenderOptions.visible_layers` for board records, footprint child
  graphics/pads, and per-layer zone fills. Pad, via, and NPTH drill/hole
  overlays are emitted as synthetic IR ops and rendered with copper/mask
  white-overlays versus non-copper outlines. Board-level `gr_text_box` and
  footprint-local `fp_text_box` now parse into the source model, round-trip
  current margins/border fields, enter PCB IR, preserve child layers, and
  expand footprint variables such as `${REFERENCE}`. Remaining required gaps
  before the IR renderer can replace the direct board SVG path: tables,
  dimensions, and mask/paste/copper layer semantics under end-to-end oracle
  coverage. Board bitmap images are explicitly out of scope for PCB IR/SVG
  parity.
- Current board SVG corpus histogram across
  `C:\eli\wn_test_corpus\kicad\board_svg\input`: 55 boards, 0 parse errors,
  778 stored CLI reference SVGs. Covered objects include 9,239 tracks,
  3,288 pads, 1,352 vias, 1,123 track arcs, 1,040 footprints, 494 board texts,
  116 zones, 88 `gr_line`, 50 `gr_rect`, 46 `gr_poly`, 32 `gr_circle`,
  21 `gr_arc`, 4 `gr_curve`, 1 text box, 1 image, and 1 table. `dimension`
  remains uncovered in this corpus.
- Pad-shape coverage in that board corpus includes rect, roundrect, circle,
  oval, and custom pads; via coverage includes through, blind, buried, and
  micro. The synthetic pad-shapes fixture is generated through
  `kicad_monkey` PCB classes and passes KiCad CLI load/export.
- Current active schematic IR recorder oracle status is strict for the four
  active frozen fixtures. `ADC_PWR.1`, `complex_hierarchy.1`,
  `led_component.1`, and `sallen_key.1` all reach 100% normalized recorder op
  parity within the current 10um coordinate tolerance and strict style
  comparison.
- Manifest-driven SVG/IR smoke coverage runs all 12 active real-world
  projects: every schematic sheet through IR/SVG and every board through
  review-layer board SVG. Synthetic schematic SVG/IR cases and public-library
  symbol/footprint samples are also covered through the manifest.
- `KiCadSymbolLib` exposes `symbol_to_ir()`, `symbol_to_svg()`, and `to_svg()`
  with `part_id` as an Altium-style alias for KiCad `unit`.
- `MIMXRT685SFVKB` is the first multi-unit symbol-library gate.
- SVG coverage now includes public-library semantic IR checks for symbol
  geometry, inherited `extends` symbols, footprint pad/shape ops, MIMXRT685
  per-unit symbol IR, and four active frozen KiCad recorder-drift cases.
- Recorder loader normalization converts KiCad recorder plotter internal units
  to nm from `SetViewport.ius_per_decimil`; active recorder manifest gates now
  assert windowed op shape/coordinate/style equivalence thresholds, not just
  structural drift. Those gates fold recorder `PenTo` line runs where needed,
  ignore folded stroke-font glyph runs when the recorder dump also carries the
  corresponding high-level `Text` ops, and require zero style mismatches.
- Parser-side schematic IR now reads adjacent `.kicad_pro` schematic drawing
  settings needed by the plotter stream, including `text_offset_ratio`.
  Symbol pin graphics follow KiCad pin-style geometry, and hierarchy sheet
  records model KiCad's background/outline plotting behavior.
- Default IR oracle comparison is strict for styles (`compare_styles=True`).
  Future rendering color overrides must be explicit context options and must
  not change the default recorder-oracle comparison path.
- Default IR oracle comparison also normalizes KiCad's plotted multiline text
  stream: a declarative multiline `Text` op is split into strict per-line
  `Text` ops using KiCad's 1.68 line pitch before matching. Line text and
  style payloads remain strict.
- Current active recorder equivalence baseline at 10um tolerance:
  `ADC_PWR.1` 383/383 matched, 0 short, 0 long, 0 style mismatches;
  `complex_hierarchy.1` 282/282 matched, 0 short, 0 long, 0 style mismatches;
  `led_component.1` 89/89 matched, 0 short, 0 long, 0 style mismatches;
  `sallen_key.1` 233/233 matched, 0 short, 0 long, 0 style mismatches.

Corpus and manifest:

- Real-world promoted projects use `input`, `output`, and `reference_output`.
- Public official KiCad library samples are represented as curated manifest
  cases, not whole-repo mirrors. Current sample coverage includes connector,
  FPGA, interface, MCU, memory, passive, power, and RF symbols plus connector,
  mechanical, pad, RF/castellated, SMD IC, and SMD passive footprints.
- Frozen KiCad schematic recorder dumps are represented as
  `reference_recorder/*` manifest cases. Active cases are `ADC_PWR.1`,
  `complex_hierarchy.1`, `led_component.1`, and `sallen_key.1`; child
  sheet-instance dumps remain reference-only until sheet-instance mapping is
  explicit.
- Real-world KiCad schematic recorder dumps are represented as
  `real_world_recorder/*` manifest cases. The current active top-level set is
  `cm5_minima_rev2.1` (604/624), `charge_indicator.1` (464/485),
  `eez_dcp405plus.1` (298/298), `icepi_zero_v13.1` (865/905), and
  `jumperless_v5r7.1` (9950/10810), all with zero style mismatches at 10um
  tolerance. Reference-only top-level dumps are retained for `canbob.1`,
  `cern_wren_eda_04903.1`, `taillight.1`, `icepi_sbc.1`,
  `nrf9151_feather.1`, and `speedy_processing_module.1`.
- Manifest entries carry domain, origin, status, version lane, input paths,
  output roots, oracle policy, provenance, tags, notes, and hygiene metadata.
- `case_metadata.json` supports public-project provenance, `status`,
  `tags`, `notes`, `promotion_reason`, and `preferred_project_file`.
- Megamaid scan found 866 materialized KiCad project roots under
  `C:\eli\megamaid\data\raw`. Use
  `C:\eli\megamaid\data\index\megamaid.db`; the top-level `data\index.db`
  is an empty placeholder.

## Completed This Pass

1. Burned down and promoted the previous public real-world netlist drifts:
   `canbob`, `cm5_minima_rev2`, and `icepi_sbc`.
2. Normalized corpus manifest status for the promoted real-world projects and
   kept generated KiCad `.kicad_prl` debris out of `input`.
3. Added curated official public KiCad symbol and footprint library samples.
4. Strengthened manifest-driven schematic SVG/IR coverage for synthetic and
   real-world cases.
5. Enriched KiCad net graphical arrays and reverse indexes for future sch-viz
   net highlighting.
6. Added the KiCad/Altium/generic design JSON field map and focused generic
   converter contract coverage.
7. Strengthened SVG/IR coverage beyond smoke with manifest-driven recorder
   drift gates, semantic public symbol/footprint IR assertions, and symbol
   inheritance/style-selection support.
8. Normalized recorder dump op units to nm and promoted active KiCad QA
   recorder cases to manifest-driven coordinate/shape op-equivalence gates.
9. Tightened those recorder gates by filtering redundant folded stroke-font
   render runs from logical op equivalence, raising active recorder match-ratio
   thresholds to 0.63-0.92.
10. Re-audited KiCad native design/netlist JSON against Altium and generic
    `data_models`; tightened pin endpoint identity and documented the remaining
    endpoint/pin-group follow-ups in the field map.
11. Added semantic endpoint materialization for KiCad power ports,
    hierarchical ports, and sheet entries, including generic converter metadata
    preservation.
12. Promoted schematic pin identity to true SVG targets: visible placed pins now
    render as nested `symbol_pin` groups, and netlist pin refs point at those
    groups while hidden pins retain symbol-group fallbacks.
13. Aligned full-document SVG layering with KiCad plot order by rendering
    `sheet_header` drawing-sheet records last while preserving IR record order.
14. Tightened recorder equivalence vocabulary reduction by merging recorder
    fill+outline primitive pairs into one declarative primitive. Also added an
    opt-in reducer that folds `PenTo` draw runs into declarative
    `PlotPoly`/`Rect` geometry for focused analysis; that broader fold remains
    disabled for frozen manifest gates until the extra drawing-sheet linework
    has curated one-to-one declarative partners.
15. Matched KiCad's symbol-body SVG z-order by splitting filled library
    primitives into an early fill pass and a deferred stroke-only outline pass
    after pins/text. This prevents filled symbol outlines from being hidden
    under pin graphics in SVG.
16. Reframed schematic SVG closure as IR-first oracle work. The active plan now
    treats KiCad recorder plotter dumps as the hard oracle for schematic IR
    parity, with SVG renderer parity following only after IR is proven.
17. Added declarative style propagation to parser-side IR for schematic
    wires/buses/sheet and text-box outlines/backgrounds plus symbol-library
    primitives. IR-to-SVG now consumes those per-primitive style fields, and
    op-equivalence can normalize recorder `SetColor` / `SetDash` state into
    comparable style payloads when strict style checks are enabled.
18. Staged a recorder-enabled KiCad CLI under the corpus tool cache at
    `f11d3da6771a`, with high-level `PlotText()` recorder output for schematic
    fields, labels, pins, text boxes, and drawing-sheet text.
19. Regenerated the frozen schematic recorder dumps from that staged recorder
    build and refreshed the manifest generator so strict style comparison,
    `PenTo` folding, and zero style mismatches are the default active recorder
    gate.
20. Promoted `led_component.1` to the first 100% normalized recorder parity
    fixture; retained exact partial-baseline ceilings for `ADC_PWR.1`,
    `complex_hierarchy.1`, and `sallen_key.1` so further parity work could not
    regress them silently.
21. Promoted all four active frozen recorder fixtures to 100% normalized,
    strict-style schematic IR parity: `ADC_PWR.1`, `complex_hierarchy.1`,
    `led_component.1`, and `sallen_key.1`.
22. Added top-level real-world recorder oracle cases for all 12 active
    real-world projects. Six currently clear the active recorder floor with
    zero style mismatches; the remaining six are retained as reference-only
    dumps until their vocabulary/style drift is triaged.
23. Tightened active real-world style parity back to zero mismatches by moving
    multiline text splitting into the default op-equivalence layer and fixing
    parser-side worksheet text colors, text-box wrapping, symbol text default
    alignment, and overbar label color selection.
24. Added the three sanitized schematic-documentation projects to the active
    real-world corpus. Their PCBs are intentionally empty project carriers;
    manifest board SVG/IR smoke tests now accept those empty boards while still
    failing non-empty boards that do not emit PCB IR records.
25. Split KiCad CLI resolution by capability for board SVG oracle tests. PCB
    live comparisons now require a PCB-capable CLI instead of accidentally
    selecting the staged schematic recorder build.
26. Added a standalone board SVG review generator with stored-reference and
    live-CLI modes. The stored-reference review covers all 778 corpus reference
    pairs; a separate live smoke review can regenerate references through a
    PCB-capable `kicad-cli`.
27. Applied PCB footprint placement during IR-to-SVG rendering as a wrapper
    group transform on footprint records, preserving footprint-local custom pad
    and trapezoid payloads.
28. Added first-pass PCB layer filtering to `render_ir_to_svg()` via
    `KiCadSvgRenderOptions.visible_layers`. PCB footprint child ops now retain
    their own graphics/pad layer metadata, zone fills filter by per-fill layer,
    wildcard pad layers such as `*.Cu` are honored, and through-via copper spans
    remain visible on intervening copper layers.
29. Added first-pass PCB IR drill/hole overlays: through-hole pad round drills,
    oval slots, NPTH fallback holes, and via drills now emit synthetic IR ops.
    IR-to-SVG renders pad drills as white overlays on copper/mask layer exports
    and outlines on non-copper layers, while via drills follow the via's copper
    span.
30. Added first-pass PCB text-box support: `fp_text_box` now has a typed model,
    embedded/standalone footprints collect it, board and footprint IR emit
    text-box border/text ops, footprint text variables expand with KiCad-style
    uppercase aliases, and the direct PCB SVG path renders footprint text-box
    content for documentation-oriented boards.

## Historical Work Queue (superseded)

This queue records the worklist that led to the completed 2026-05-18
viz-enabling milestone. It is retained for context only; use the completion
note at the top of this plan plus new viz integration findings for future work.

1. Make KiCad outline-font render caches a first-class typed OOP surface before
   exiting SVG/general KiCad work. Follow
   the render-cache subplan below: typed
   render-cache topology, cache support on every modeled EDA_TEXT-derived
   object, a shared cache resolver, KiCad-generated oracle caches, and synthetic
   plus real-world coverage histograms.
2. PCB SVG is the active rendering focus. Keep the direct `KiCadPcb.to_svg()`
   path green against stored CLI references while adding a downstream live
   comparison layer that exports the same board/layer set with `kicad-cli pcb
   export svg`, stores our SVG, and reports semantic SVG deltas plus review
   artifacts for synthetic and real-world boards.
3. Promote PCB IR from structural coverage to end-to-end render coverage.
   Required gaps before it can replace the direct renderer: tables, dimensions,
   and mask/paste/copper layer semantics under live/stored oracle comparison.
   Use KiCad classes first so plotter-IR oracle checks stay available.
4. Add synthetic board fixtures for the uncovered/low-coverage cells in the
   corpus histogram, starting with dimensions, table draw order, rotated or
   multiline text-box edge cases, and any pad/via/zone cases not covered by the
   other agent's synthetic PCB generator.
5. Once KiCad-class board SVG and board IR are oracle-tight, map the same board
   rendering surface through `data_models` / `pcb_cruncher` so the future
   browser/WASM path can render from the generic PCB model without losing KiCad
   parity.
6. Keep schematic IR parity first for schematic changes. The hard oracle is
   KiCad's plotter stream captured by frozen or live
   `kicad.plotter_recorder.v1` dumps. The current active frozen recorder set
   is closed at 100% normalized strict-style parity; SVG renderer fixes follow
   from that proven IR stream.
7. Continue real-world recorder promotion beyond top-level sheets. Next targets
   are child sheets with unambiguous sheet/source mapping across the 12
   real-world projects, then selected Megamaid/public project sheets. Keep the
   top-level reference-only recorder dumps inactive until their documented
   vocabulary/style drift is triaged.
8. Decide whether strict parity means exact nm coordinates or 100% normalized
   op coverage within a documented KiCad rounding tolerance. If exact nm is the
   goal, emulate KiCad plotter rounding after the structural gaps are closed.
9. Repeat downstream `bom_cruncher` and `pcb_cruncher` checks after the actual
   `origin/dev` merge and pending `pcb_a0` data-model changes land.
10. Optionally create explicit KiCad 7/8 compatibility lanes after strict KiCad
   9/10 stays stable. Do not backfill KiCad 5.x legacy schematic support.

## Exit Criteria

1. `KiCadDesign.to_netlist()` matches live `kicad-cli sch export netlist
   --format kicadsexpr` on every active strict-tier fixture with zero known
   drifts.
2. The manifest drives netlist, schematic IR, schematic SVG, board SVG,
   symbol SVG, footprint SVG, and library-render discovery. Tests no longer
   promote cases by ad hoc recursive scanning.
3. Every promoted real-world and synthetic project fixture has clean
   `input`, `output`, and `reference_output` directories.
4. `KiCadDesign.to_json(include_indexes=True)` remains aligned with
   `AltiumDesign.to_json` for top-level fields, enriched component shape, net
   shape, hierarchy envelope, variants, and indexes.
5. Native KiCad design/netlist JSON, Altium design/netlist JSON, and generic
   data-model payloads have a documented field map and focused parity tests.
6. SVG/IR gates cover synthetic, upstream-QA, public-library, and real-world
   cases for schematic, board, symbol, and footprint domains.
7. Active frozen and promoted KiCad recorder cases assert strict normalized
   schematic IR parity: op kind/order, coordinates, style state, fills, and
   logical text are equivalent to KiCad's plotter stream with zero known
   untriaged drifts. Any intentionally normalized representation difference is
   documented in the oracle reducer and covered by focused tests.
   Default style comparison stays strict; any future color override behavior is
   an opt-in renderer/context layer outside the oracle baseline.
8. All active real-world projects remain active with netlist and SVG/IR
   coverage: `canbob`, `cern_wren_eda_04903`, `cm5_minima_rev2`,
   `celebration_led_assembly`, `charge_indicator`,
   `charge_indicator_assembly`, `taillight`,
   `taillight_assembly`, `eez_dcp405plus`, `icepi_sbc`,
   `icepi_zero_v13`, `jumperless_v5r7`, `nrf9151_feather`,
   `speedy_processing_module`, and `yoshi_mainboard`.
9. Multi-unit symbol-library rendering remains covered, including
   `MIMXRT685SFVKB`, with unit selection through KiCad `unit` and Altium-style
   `part_id`.
10. KiCad outline-font render caches are first-class typed source-model objects
    per the render-cache subplan below:
    cache topology round-trips without loss, every modeled EDA_TEXT-derived PCB
    object is covered or explicitly out of scope, cache-free synthetic fixtures
    regenerate against a KiCad oracle, direct PCB SVG and PCB IR SVG consume the
    same typed geometry, and coverage histograms show no untriaged text
    geometry gaps.
11. `bom_cruncher` and `pcb_cruncher` pass their relevant checks after branch
   sync and pending `pcb_a0` updates.

## Subplan: KiCad S-Expression Parser

Status as of 2026-05-16: Phases 1, 2, and 3 complete. Phase 4 (C++/WASM
port-prep) is not actionable until the C++ port actually starts. Parser
bugs can masquerade as renderer, model, or converter defects, so this
subplan is part of the current exit criteria; the corpus-wide
parser-only pass-through gate is now green at 1810/1810 files.

### Goal

Replace the legacy regex-first S-expression reader with a KiCad-mode DSN
lexer and small deterministic tree builder that are easy to port to C++/WASM.

The public mental model is:

```text
source text
  -> KiCadSexprLexer tokens with source spans
  -> KicadSexprParser list tree
  -> typed KiCad OOP model
```

The parser is strict by default but intentionally models KiCad-accepted
dialect forms where KiCad's object parser is not a pure generic S-expression
reader.

### Design Rules

- Keep tokenization and tree construction separate.
- Avoid regular expressions for nesting, balancing, or context-sensitive
  parse behavior.
- Keep tokens C++ friendly: kind, raw text, decoded value, offset, line,
  column, leading separator.
- Preserve the existing `parse_sexp()` list-tree API during the hard switch.
- Put every KiCad compatibility exception behind a named grammar production
  or normalizer, never a broad text rewrite.
- Add corpus fixtures for every compatibility exception before accepting it
  as supported behavior.

### Phase 1 (complete)

- Added `KicadSexprLexer` with KiCad-mode DSN token rules: parentheses as
  separators, whole-line comments only, quoted string escape decoding,
  integer/floating/exponent numbers, source spans.
- Added `KicadSexprParser` behind the existing `parse_sexp()` API.
- Preserved `QuotedString`, `SexprError`, `build_sexp()`, and writer
  behavior; `format_sexp()` now tokenizes through `KicadSexprLexer`.
- Modeled KiCad's accepted `teardrops` dialect (value fields without leading
  `(`, e.g., RoyalBlue `(curved_edges no)filter_ratio 0.9)`).
- Preserved prior compatibility for literal newlines inside quoted strings
  used by worksheet tests.
- Added deterministic stress tests for 500 adjacent sibling lists and 100
  RoyalBlue-style teardrop dialect blocks.
- Removed `term_regex`, the manual `__main__` test block, and the regex
  token loop in `format_sexp()` — module has one lexical implementation.
- Proved the RoyalBlue KiCad 10 main board parses through
  `KiCadPcb.from_file()` with 71 footprints, 96 nets, and 197 teardrop pad
  parameter blocks.
- Fixed overbar-only schematic text width measurement (removed 100 nm
  global-label decoration rounding delta).

Phase 1 verification:

```text
pytest -q suites/kicad_monkey/tests/L0_foundation
  -> 1185 passed
pytest -q suites/kicad_monkey/tests/L1_parsing/test_L1_008_shared_corpus_source_model_readiness.py
  -> 17 passed
pytest -q suites/kicad_monkey/tests/L1_parsing/test_L1_001_pcb_roundtrip.py::TestParsing::test_parse_without_error
       suites/kicad_monkey/tests/L1_parsing/test_L1_001_pcb_roundtrip.py::TestSerialization::test_to_string_produces_valid_sexp
       suites/kicad_monkey/tests/L1_parsing/test_L1_001_pcb_roundtrip.py::TestRenderCache
  -> 79 passed
```

### Current Parser Test Coverage Lanes

- L0 synthetic parser tests round-trip selected snippets through
  `parse_sexp() -> build_sexp()/format_sexp() -> parse_sexp()` and stress
  the DSN lexer/tree builder directly.
- L1 PCB/parser tests parse corpus board files into the typed OOP model,
  serialize them, and reparse.
- Shared-corpus tests prove the RoyalBlue main board's KiCad-accepted
  `teardrops` dialect reaches the typed PCB model.

Historical gap closed by Phase 2 below: the parser layer still needed a
dedicated corpus-wide S-expression-only pass-through gate at this point in the
plan.

### Phase 2 (complete)

- Added `SexpRoundtripResult` and `roundtrip_sexp_text()` in
  `kicad_sexpr.py`. The helper runs
  `lex_sexp -> KicadSexprParser.parse -> build_sexp -> parse_sexp -> compare`
  with no typed KiCad OOP parse in the critical path and tags the
  earliest-failing stage with `"lex"`, `"tree"`, `"build"`, `"reparse"`,
  `"compare"`, or `"ok"`.
- Added `iter_kicad_sexpr_files()` + `KICAD_SEXPR_FILE_SUFFIXES` in
  `kicad_monkey/testing/corpus.py` for ordered, deterministic discovery of
  every `.kicad_pcb` / `.kicad_sch` / `.kicad_sym` / `.kicad_mod` /
  `.kicad_wks` file under the corpus root, with `output/` / `review/` /
  `review_tmp/` excluded. `.kicad_pro` is intentionally excluded because
  KiCad project files are JSON, not S-expression.
- Added `PARSER_DIALECT_EXCEPTIONS` typed registry with the
  `teardrops_bare_filter_ratio` entry naming the production
  (`KicadSexprParser._parse_teardrops_body`), the source-file proof
  (RoyalBlue KiCad 10 demo board), a minimal sample, and the expected
  normalized list tree. Each entry is exercised by a parametrized parser
  round-trip test.
- Extended `test_L0_033_kicad_sexpr_parser.py` with parser stress and
  phase-tagged failure tests: canonical round-trips, teardrops dialect
  normalization, lex-phase / tree-phase / leftover-after-root failures,
  deep nesting (200 levels), 500 adjacent siblings, exponent/signed
  numbers, KiCad string escapes (octal/hex/simple/quote/backslash),
  whole-line comments, inline `#` in atom position, `format_sexp`
  stability, and `build_sexp` lex-clean output. Also exposed the
  new helpers in `kicad_monkey/__init__.py`.
- Added a corpus-wide pass-through gate at
  `test_L1_018_corpus_sexpr_passthrough.py`. A module-scoped fixture
  runs `roundtrip_sexp_text()` once per corpus file; both tests
  classify the cached records. The general gate asserts every promoted
  file reaches `phase == "ok"` and that every expected suffix is
  represented; the second test asserts real-world projects (paths
  containing `projects/` or `real_world/`) contribute to the gate.
  Failures are bucketed by phase and the assertion message names every
  offending file/path/phase rather than failing at the first casualty.

Phase 2 verification (2026-05-16):

```text
WN_TEST_CORPUS=C:/eli/wn_test_corpus uv run pytest -q
  toolz-tests/suites/kicad_monkey/tests/L0_foundation/test_L0_033_kicad_sexpr_parser.py
  -> 24 passed
WN_TEST_CORPUS=C:/eli/wn_test_corpus uv run pytest -q
  toolz-tests/suites/kicad_monkey/tests/L1_parsing/test_L1_018_corpus_sexpr_passthrough.py
  -> 2 passed, 1810 corpus S-expression files, 0 parse-phase failures (~17 min)
WN_TEST_CORPUS=C:/eli/wn_test_corpus uv run pytest -q
  toolz-tests/suites/kicad_monkey/tests/L0_foundation
  -> 1200 passed
WN_TEST_CORPUS=C:/eli/wn_test_corpus uv run pytest -q
  toolz-tests/suites/kicad_monkey/tests/L1_parsing/test_L1_008_shared_corpus_source_model_readiness.py
  toolz-tests/suites/kicad_monkey/tests/L1_parsing/test_L1_001_pcb_roundtrip.py::TestParsing::test_parse_without_error
  toolz-tests/suites/kicad_monkey/tests/L1_parsing/test_L1_001_pcb_roundtrip.py::TestSerialization::test_to_string_produces_valid_sexp
  toolz-tests/suites/kicad_monkey/tests/L1_parsing/test_L1_001_pcb_roundtrip.py::TestRenderCache
  -> 96 passed
ruff check src/py/kicad_monkey/kicad_sexpr.py src/py/kicad_monkey/testing/corpus.py src/py/kicad_monkey/__init__.py
ruff check toolz-tests/.../test_L0_033_kicad_sexpr_parser.py toolz-tests/.../test_L1_018_corpus_sexpr_passthrough.py
  -> clean
```

The full corpus gate is intentionally slower than the L0 lane because it
exercises every promoted S-expression file end-to-end through
parse/build/reparse. Treat it as a CI gate rather than an inner dev loop.

### Phase 3 (complete)

- `SexprError` now carries structured fields (`offset`, `line`, `column`,
  `source_path`, `token_text`) and renders a deterministic location
  suffix in `str(exc)`. The leading message text is preserved so
  legacy `pytest.raises(match=...)` substring checks keep working.
- Every parser raise site populates the structured fields from the
  token in scope. "Unbalanced opening parenthesis" now reports the
  position of the unclosed opener (tracked through an `_open_stack`)
  rather than failing at EOF without a usable location.
- `parse_sexp(text, *, source_path=None)` and
  `roundtrip_sexp_text(text, *, source_path=None)` accept an optional
  source path; any raised `SexprError` (and the recorded
  `SexpRoundtripResult.error`) carries the path so corpus-scale
  failure listings can name the offending file inline.
- Added `parse_sexp_with_spans(text, *, source_path=None) ->
  (tree, spans)` where `spans` is a dict keyed by `id(list_node)`
  to a `SexpSpan(offset, line, column, end_offset, end_line,
  end_column)`. Spans cover every parsed list (opener through
  closer + 1), so consumers can slice the original text directly.
  This is opt-in and does not change the hot `parse_sexp` path.
- Added `debug_dump_tokens(text, *, limit=None, source_path=None)`
  returning a human-readable per-token diagnostic dump (offset,
  line, column, kind, text). Suitable for triaging parse failures
  and as a debugging API that does not couple callers to the
  typed OOP layer.
- Resolved the documented royalblue54L_feather KiCad 10 demo parse
  failure: the file now reaches `phase == "ok"` through the parser
  (the failure was the teardrops bare `filter_ratio` dialect, now
  registered as `PARSER_DIALECT_EXCEPTIONS[0]`).
- Extended `test_L0_033_kicad_sexpr_parser.py` with twelve new
  Phase 3 tests covering structured error fields, parser
  line/column upgrades, inner-list unclosed diagnostics, leftover
  garbage token reporting, source-path decoration on `parse_sexp`
  and `roundtrip_sexp_text`, `SexprError.with_source_path`,
  `parse_sexp_with_spans` for both single-line and multi-line
  inputs, span propagation on errors, and `debug_dump_tokens`
  output / limit behavior.

Phase 3 verification (2026-05-16):

```text
WN_TEST_CORPUS=C:/eli/wn_test_corpus uv run pytest -q
  toolz-tests/suites/kicad_monkey/tests/L0_foundation/test_L0_033_kicad_sexpr_parser.py
  toolz-tests/suites/kicad_monkey/tests/L0_foundation/test_L0_001_sexpr_parsing.py
  -> 77 passed (24 + 12 new Phase 3 tests on test_L0_033)
WN_TEST_CORPUS=C:/eli/wn_test_corpus uv run pytest -q
  toolz-tests/suites/kicad_monkey/tests/L0_foundation
  -> 1212 passed
ruff check + py_compile on kicad_sexpr.py and __init__.py
  -> clean
```

The corpus-wide pass-through gate (`test_L1_018`) was re-run after
Phase 3 to confirm error decoration and span capture did not regress
the 1810-file sweep.

### Phase 4 (future JS/WASM follow-up)

- Keep the Python implementation close to a direct C++ translation: no
  Python parser-generator dependency, no dynamic grammar magic, no hidden
  global state.
- Define an equivalent C++ token struct and parser state machine.
- Add cross-language golden token streams and list-tree outputs once the C++
  port starts.
- Make the JS/WASM surface expose both parsed OOP objects and a parser
  diagnostic stream suitable for browser tooling.

### Parser Open Items

- KiCad SCH/SYM loaders may have additional `parseMaybeAbsentBool` forms
  that should become named productions if real files require them.
- KiCad's generic `libs/sexpr` parser exists, but PCB/SCH object loaders use
  `DSNLEXER` plus context-specific parsers. Our behavior must follow the
  object loaders for accepted project files.
- Parser and writer utilities still share `kicad_sexpr.py`; the legacy regex
  parser scaffolding is gone, but a future module split may still be useful
  once the corpus-wide parser-only gate is in place.

## Subplan: KiCad Render Cache OOP

Status update 2026-05-18: Phases 1-5 are complete for direct PCB SVG and PCB
IR, and the corpus-wide parser-only pass-through gate landed in Phase 2 of the
parser subplan. Remaining notes in this subplan are retained as historical
implementation context unless a later restart handoff calls them out explicitly.

### Goal

Given a KiCad semantic text object, project/board context, and font state,
`kicad_monkey` must be able to produce, preserve, validate, serialize, and
consume the same polygon geometry KiCad would use for outline-font rendering.

First-class contract:

```text
KiCad semantic/OOP text object
  + resolved variables
  + resolved font and style
  + draw transform / text attributes / context
  -> typed RenderCache
  -> SVG / IR / 3D / data-model geometry
```

The implementation prefers KiCad's existing cache when present but does not
depend on KiCad-authored files already containing `(render_cache ...)`.

### Scope

In scope:

- PCB text objects: `gr_text`, `gr_text_box`, `fp_text`, `fp_text_box`,
  footprint/property text, dimension text, and table-cell text.
- Schematic outline-font text geometry where KiCad paints via
  `EDA_TEXT::GetRenderCache()` (schematic files do not serialize caches).
- Cache preservation, generation, stale-cache validation, SVG consumption,
  PCB IR payloads, and downstream generic geometry export.
- KiCad 9/10 behavior as strict oracle lanes; KiCad 7/8 as explicit
  compatibility lanes.

Out of scope:

- Board bitmap image rendering.
- Replacing KiCad stroke-font text behavior with outline-font behavior.
- Browser UI work beyond consuming the typed geometry once exported.

### Source Truth From KiCad

- `common/eda_text.cpp`: `EDA_TEXT::GetRenderCache()`, `SetupRenderCache()`,
  `AddRenderCacheGlyph()`.
- `common/font/outline_font.cpp`: `OUTLINE_FONT::LoadFont()`,
  `GetLinesAsGlyphs()`, HarfBuzz shaping, fake bold/italic, transforms,
  glyph cache keys.
- `common/font/outline_decomposer.cpp`: FreeType outline decomposition and
  KiCad Bezier flattening through `BEZIER_POLY` and
  `ADVANCED_CFG::m_FontErrorSize`.
- `common/font/font.cpp`: multiline layout, markup, alignment, bounding-box
  helpers.
- `pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr.cpp` `formatRenderCache()`,
  `pcb_io_kicad_sexpr_parser.cpp` `parseRenderCache()`.
- `pcbnew/pcb_painter.cpp`, `pcb_text.cpp`, `pcb_textbox.cpp`: board painter
  and polygon-conversion use of the cache.
- `eeschema/sch_painter.cpp`, `sch_field.cpp`: schematic and symbol-field
  cache use.

### Phase 1 (complete) — Typed RenderCache topology

- Added typed `RenderCacheContour`, promoted `RenderCachePolygon` from a flat
  point list to contour-aware topology, preserved the `poly.points`
  exterior-contour API.
- Cache parsing/writing preserves every `(pts ...)` chain including hole
  contours.
- Canonical render-cache model reused in `gr_text` parsing.
- `render_cache` parse/write added to board `gr_text_box` and footprint-local
  `fp_text_box`.
- Synthetic round-trip tests for holed cache polygons and text-box cache
  preservation.

### Phase 2 (complete) — Centralized cache resolution

- `kicad_render_cache.py` is the shared boundary for existing cache
  validation and provenance.
- API: `RenderCacheRequest`, `RenderCacheValidation`, `RenderCacheResult`,
  `RenderCacheSource`, `RenderCacheResolver`, plus
  `render_cache_exterior_polygons()` for flat SVG consumers while keeping
  full contour topology in the typed cache.
- Explicit missing/stale handling for resolved text, angle, empty cache,
  invalid contour geometry.
- Optional angle context (`RenderCacheRequest.angle = None` when caller
  lacks a trustworthy KiCad draw-angle). Results carry non-exact status
  when validation warnings are present.
- Strict typed cache comparison: cache-level (text, angle, polygon/contour/
  point counts, coordinate deltas with tolerances), oracle-entry comparison
  (object type, text, layer, UUID, payload), entry-set comparison keyed by
  UUID with fallback to object path.

### Phase 3 (complete) — KiCad oracle

- `kicad_render_cache_oracle.py` strips all nested `(render_cache ...)`
  blocks, stages a temp board, runs `kicad-cli pcb upgrade --force`,
  reparses, and returns typed cache entries.
- Cache-entry extraction for board `gr_text`, board `gr_text_box`,
  footprint `fp_text`, footprint properties, `fp_text_box`, table cells,
  and dimension nested `gr_text`.
- `RenderCacheCoverageSummary` + `summarize_render_cache_entries()` for
  histogram-style oracle coverage and missing-object-type detection.
- Deterministic regeneration gate: cache-free semantic board -> KiCad save
  cache -> typed entries -> strip/regenerate -> typed entries with zero
  entry-set deltas.

### Phase 4 (complete for current PCB text scope) — Python generation parity

Generation backend: KiCad's HarfBuzz DLL via optional ctypes bridge (with
`uharfbuzz` fallback), FreeType `FT_Outline_Decompose`, KiCad's
`BEZIER_POLY` quadratic/cubic flattening, `FontErrorSize=2`,
`GLYPH_SIZE_SCALER`, and outline-font compensation. Matches KiCad's
serialized cache geometry within 0.002 mm on promoted oracle fixtures.

Covered contexts:

- Straight + curved glyphs in single-line board `gr_text`.
- Real and fake bold/italic for Arial board text (slant matrix; FreeType
  embolden `1 << 6`).
- Board text transforms: alignment, rotation (cardinal + arbitrary), mirror.
- Multiline and tab runs (`1.68 * size_y` default pitch; explicit
  `(line_spacing ...)` token).
- Board `gr_text_box` draw-position, stroke-inflated bounds, margins,
  cardinal rotations, mirror-aware horizontal alignment, default-center
  fallback, plain-text wrapping (KiCad `GetShownText` parity).
- Holed-glyph fracture matching `CALLBACK_GAL::DrawGlyph()` slit-outline
  topology (`O`, `d`, `8`).
- Polygon text-box source: first-class `polygon_points` parse/write for
  board and footprint text boxes, transformed by parent footprint placement.
- Footprint text contexts: `fp_text`, footprint `property`, `fp_text_box`
  including rotated front-side parents and explicit polygon corners via
  `EDA_SHAPE::GetCornersInSequence()` semantics.
- Markup: `^{...}`/`_{...}` superscript/subscript (0.64 scale; -0.25 / +0.45
  vertical offset), `~{...}` overbar with KiCad stroke-glyph polygon order
  (`TransformOvalToPolygon(..., ERROR_INSIDE)`, `strokeWidth/180` arc error,
  8-segment alignment), markup-aware wordbreak in text-box wrapping.
- Table cells: `table_cell` source preserves `locked`, `angle`, effects, and
  `(render_cache ...)`. Variable resolution for `${ROW}`, `${COL}`,
  `${ADDR}`, `${LAYER}` alongside board/footprint variables.
- Dimensions: aligned + orthogonal (vertical/horizontal) + radial (keep-
  aligned text-angle from knee) + leader (preserve nested position/angle).
  `Dimension.measured_value_mm()` and `Dimension.resolved_gr_text()` derive
  display text and draw position from feature points before request.
- Auto pen width: KiCad `EDA_TEXT::GetEffectiveTextPenWidth()` (normal
  width/8, bold width/5, clamped to 25% of smaller text dimension).
- Font lookup: cached FreeType scan of Windows + user font directories.
  Embedded fonts via `(embedded_files ...)`: base64+zstd decoded, registered
  by filename / stem / simplified stem / FreeType family aliases.
- HarfBuzz parity: hb-ft path on live FreeType face, `GLYPH_SIZE_SCALER`
  advance math, integer glyph cursor, `faceSize() = 1433`, 1.4 outline-font
  compensation. Long-run / kerning fixtures match within ~0.000001 mm.

Decision (2026-05-16): keep Python FreeType/HarfBuzz as the in-process
default. The long-term JS/WASM path should extract or port KiCad's minimal
outline-text kernel behind the same typed `RenderCacheRequest -> RenderCache`
boundary, not embed the whole KiCad parser/plotter/UI stack. KiCad CLI
generated caches remain the oracle.

### Phase 5 (complete for current scope) — Direct PCB SVG + PCB IR integration

Direct PCB SVG consumes typed cache geometry for outline-font text across:

- Board `gr_text`, board `gr_text_box`.
- Footprint `fp_text`, visible footprint properties, `fp_text_box`.
- Board `table_cell` text and dimension text (text path only; full table
  borders and full dimension shape geometry are separate IR features).
- `RenderCacheResolver.ensure_cache()` regenerates from typed text
  parameters when an existing file cache is stale or invalid.
- The private outline fallback remains only as a knockout-background
  helper when no usable cache geometry is available.

PCB IR carries both semantic text and optional resolved geometry:

- `KiCadPlotterOp.text(...)` accepts `render_cache_polygons` and a hole-aware
  typed `render_cache` payload; `render_ir_to_svg()` prefers cache polygons
  when present.
- `pcb_to_ir()` attaches generated/validated polygons + cache provenance to
  board text, board text-box, footprint text/property/text-box, table-cell,
  and dimension text ops. Footprint absolute-board polygons are converted
  back to footprint-local coordinates before attachment.
- Table records carry cache-backed cell ops; dimension records carry
  cache-backed text ops plus first-pass `ThickSegment` line/arrow geometry
  for aligned, orthogonal, radial, leader, and center dimensions.
- Direct PCB SVG bounds include dimension text so dimension-only
  documentation boards render at the correct viewBox.
- Table-cell text is filtered by per-cell layer, not hidden by the table
  container layer.

### Render Cache Coverage Report (2026-05-16)

`C:\eli\wn_test_corpus\kicad\review\render_cache_coverage_report.{json,md}`
covers 116 PCB manifest cases across `synthetic`, `project_corpus`, and
`real_world` origins: 178,831 modeled text objects, 4,525 outline-font /
cache-relevant objects, 4,524 valid existing file caches, 1 Python-
regenerated stale cache, 0 untriaged outline text geometry gaps.

Earlier this pass, one manifest PCB case
(`project_corpus/common/royalblue54L_feather/input/RoyalBlue54L-Feather`)
triggered `SexprError: Leftover garbage after end of expression` on the
KiCad 10 demo and on the corpus copy. The root cause was KiCad 10
serializing teardrop value fields without a leading `(`, which is now
normalized through `PARSER_DIALECT_EXCEPTIONS[0]`
(`teardrops_bare_filter_ratio`). The case is currently green through
both the parser-only pass-through gate and the typed PCB loader; the
render-cache coverage report can be regenerated to remove the
parse-error annotation.

### Historical Render Cache Cutover Targets

PCB SVG/IR cutover status: complete for the 2026-05-18 viz-enabling milestone.

- [done — Phase A] `render_pcb_ir_to_svg` wrapper in `kicad_pcb_ir_svg.py`
  composes `pcb_to_ir` + `render_ir_to_svg` with bounding-box-derived
  viewBox via `KiCadSvgRenderContext.offset_x_nm/offset_y_nm`. Verified
  by `test_L0_034_pcb_ir_svg_wrapper.py` (viewBox numeric parity with
  legacy `render_pcb_svg`, content translation containment, empty-board
  fallback).
- [done — Phase B core] Record-level layer filtering wired into
  `render_pcb_ir_to_svg(pcb, layers=...)`; records whose extras/op
  layer set intersects the requested layers are kept. Multi-layer
  records (vias, footprints, zones with mixed fill layers) are kept
  if any listed layer matches. L0_034 covers filter semantics.
  L3_007 (`test_L3_007_pcb_ir_svg_oracle.py`) is the 3-way IR-vs-CLI
  oracle on the synthetic SVG fixtures, comparing `viewbox`,
  `total_strokes` (path + polyline + line + rect + polygon, excluding
  the canvas background rect), and `total_circles` against
  `kicad-cli pcb export svg`. All 6 cases pass; `IR_KNOWN_GAPS` empty.
- [done — Phase B.2(a)] Pad-drill-outline synthesis on non-copper/non-mask
  layers (`_synthesize_pad_drill_outlines_for_layer` in
  `kicad_pcb_ir_svg.py`). Runs per requested layer and emits one
  `pad_drill_outline` record per through-hole pad: oval drills become a
  `thick_segment` of length `(major - minor)` and width `minor`, round
  drills become a stroked circle of width 0.1mm. Footprint placement
  (`at_x`, `at_y`, `at_angle`) and pad orientation (`pad.at_angle`) are
  baked into the synthesized geometry. Vias are intentionally excluded
  to match kicad-cli behaviour. Closes the `via_edgecuts_drill_outline`
  / `slot_edgecuts_drill_outline` parity gap for L3_007. The
  via_edgecuts case actually never needed synthesis — once
  `total_strokes` counted `<rect>` (minus canvas background), the IR's
  `<rect>` outline matched CLI's `<path>` outline at the metric level.
- [done — Phase B.2(b)] Style-bucket grouping (`_wrap_with_style_bucket`
  in `kicad_ir_to_svg.py`). Each rendered op fragment is wrapped in a
  `<g style="fill:X; stroke:Y; stroke-width:Z; stroke-linecap:round;
  stroke-linejoin:round">…</g>` that mirrors its first element's
  fill / stroke / stroke-width attributes. Zero stroke-width is
  canonicalised to `stroke:none` so the CLI's drill-circle convention
  (`fill:#FFFFFF` + `stroke:none`) matches. The wrapper sits inside the
  existing per-record `<g id data-uuid data-ref>` envelope, leaving all
  identity-based tests intact. Oracle helpers
  (`_count_white_stroke_paths`, `_count_paths_for_stroke_width`) were
  made renderer-agnostic to count `<path|polyline|line>` (same
  precedent as `total_strokes`). The 4 style-keyed metrics
  (`white_drill_circles`, `white_stroke_paths`, `stroke_paths_0p1000`,
  `stroke_paths_1p0000`) are now in `IR_ENFORCED_METRICS`; all 6
  L3_007 cases still pass on the full 7-metric set.
- [done — Phase B.2(c)] Per-op layer filtering inside multi-layer
  records. The record-level filter in `kicad_pcb_ir_svg.py` now
  additionally calls `_filter_record_ops_by_layer(record, wanted)`
  on every surviving record so a `layers=["F.SilkS"]` request does
  not drag F.Fab fp_lines / F.Cu pad ops out of a footprint record.
  Wildcards on declared layer lists (`*.Cu`, `*.Mask`, `F&B.Cu` —
  the same convention the legacy renderer handles via
  `kicad_footprint_svg`) are expanded by `_layer_matches_wanted`.
  Block markers and ops without any layer metadata pass through.
  Surfaced while wiring the fp_text knockout case
  (`component_designator_top.kicad_pcb` F.SilkS): a single
  footprint owns 107 fp_lines (105 on F.Fab, 2 on F.SilkS) plus the
  knockout `fp_text user "+"`; without per-op filtering all 107
  fp_lines rendered on every layer.
- [done — Phase C] Dimension/text geometry exact for KiCad text
  knockout, leader frames, radial, orthogonal, and dimension text.
  Closed 2026-05-17 — L3_007 oracle is 15/15 across all enforced
  metrics with `IR_KNOWN_GAPS = {}`.
  - [done — Phase C(gr_text knockout)] Board-level `gr_text` knockout
    on silkscreen. `_apply_knockout_to_text_op` in
    `kicad_pcb_to_ir.py` restructures the typed `render_cache`
    polygons from N per-letter polygons into ONE polygon whose
    `contours = [bg_rect, *glyph_contours]`, where `bg_rect` is the
    AABB of all glyph contours inflated by
    `text.get_knockout_margin()` (`max(thickness/2, size_y/9)` mm).
    The existing `_render_typed_cache_polygons` path in
    `kicad_ir_to_svg.py` already emits multi-contour SVG with
    `fill-rule="evenodd"`, so no renderer change was needed. The
    `knockout_text_silk` case (`simple_test_knockout.kicad_pcb`
    F.SilkS) now passes on all 7 enforced metrics; `IR_KNOWN_GAPS`
    is empty.
  - [done — Phase C(fp_text knockout)] Footprint-local `fp_text`
    knockout. The fp_text loop in `pcb_to_ir.py` now calls
    `_apply_knockout_to_text_op` after typed-cache attachment
    whenever `fp_text.knockout` is True and the font is present,
    computing margin inline as `max(font.effective_thickness/2,
    font.size_y/9)` (FpText has no `get_knockout_margin()` shortcut
    method, only the underlying formula). Validated by the
    `knockout_fp_text_silk` case
    (`component_designator_top.kicad_pcb` F.SilkS — real Arial Bold
    knockout `+` on a footprint with a render_cache polygon). All 8
    L3_007 cases pass on the full 7-metric set.
  - [done — Phase C(stroke-font dimension text)] Per-segment
    polyline emission for stroke-font dimension value text in
    `_dimension_stroke_text_ops` (kicad_pcb_to_ir.py). Closed the
    `dim_aligned_horizontal` / `dim_orthogonal_vertical` shape-count
    gaps. TTF dimensions still flow through the render-cache path.
  - [done — Phase C(radial + ortho-horizontal)] `dim_radial` drops
    knee→text segment; `dim_orthogonal_horizontal` emits a 0.1 mm
    filled marker dot at the second reference point when
    `end_extension_len == 0`.
  - [done — Phase C(leader + frame_rect)] Leader text content driven
    by `format.override_value` (CLI ignores user gr_text for
    leaders); `_dimension_leader_shape_ops` emits four rectangle-side
    segments around the text position when `style.text_frame == 1`.
    Closed `dim_leader_plain` and `dim_leader_frame_rect` xfails.
- [done - Phase D] Audit footprint-local table and dimension transforms before
  reusing the board-level PCB IR geometry helpers there. Closed as no-op:
  KiCad keeps tables and dimensions at board scope, not footprint scope.
- [done - Phase E] Direct `KiCadPcb.to_svg()` now routes through the IR
  renderer. The legacy `render_pcb_svg()` callable remains only for explicit
  legacy comparisons.

Generation-parity follow-ups:

- Fontconfig substitution diagnostics, language-family selection, TTC face-
  index selection.
- Footprint-local embedded font fixtures.
- Programmatic footprint `Flip()` mutation semantics (in-memory model
  transform vs. KiCad's already-flipped file state).
- Markup underline (PCB S-expression parser/writer does not serialize an
  underline token today; an internal/model-extension lane).
- Schematic outline-font cache geometry for renderers that need exact glyph
  output beyond stroke parity.

### Render Cache Testing Strategy

Unit (L0/L1):

- parse/write round-trip of cache polygons with multiple contours
- stale-cache validation by resolved text, angle, mirror state, font context
- object-type coverage for every modeled EDA_TEXT-derived class
- variable expansion before cache generation
- cache provenance and warning propagation
- backwards compatibility for existing `render_cache.polygons[*].points`
  consumers

Synthetic fixtures isolate one feature at a time: object type, transform,
alignment, content (Unicode, kerning, ligatures, holed glyphs, tabs,
multiline, markup, variables), font (stroke default, system outline,
embedded, missing fallback, real bold/italic, fake bold/italic), and
interactions (knockout, text-over-copper, text-over-image, draw order).
Each fixture records expected feature tags in the corpus manifest.

Oracle comparison levels:

1. Typed cache comparison (preferred semantic gate).
2. Polygon semantic comparison with documented orientation/fracture
   normalizations.
3. SVG comparison against KiCad CLI per-layer SVG as a downstream check.

Coverage reports: text object type counts, outline vs. stroke counts, cache
present/missing/generated/stale/invalid, font family/style coverage, fake
bold/italic coverage, embedded-font coverage, variable expansion coverage,
multiline/markup/text-box/dimension/table coverage, unsupported cases with
exact object paths.

### Render Cache Exit Gates

- Every modeled KiCad text-bearing object has typed cache support or a
  documented reason it does not use outline render cache.
- Existing KiCad `(render_cache ...)` blocks round-trip without topology
  loss.
- Cache-free synthetic PCB fixtures regenerate through the KiCad oracle and
  match `kicad_monkey`.
- Direct PCB SVG and PCB IR SVG consume typed cache geometry for outline
  fonts.
- Real-world promoted cases have cache coverage reports with no untriaged
  text geometry gaps.
- Documented decision on Python parity vs. native KiCad text-kernel
  extraction for the future JS/WASM path. (Decision recorded 2026-05-16:
  Python in-process default; WASM kernel deferred.)

## Removed Planning Files

The retired one-page pointer files for netlist, SVG/IR, variants, source-model
readiness, schematic OOP/SVG, symbol SVG, coverage execution, footprint preview,
S-expression parser, and render-cache OOP work were consolidated into this plan
and removed after the 2026-05-18 milestone completion. Do not recreate separate
planning surfaces for those topics unless a future milestone explicitly needs
one.

The patch files in this directory are intentionally retained recorder-plotter
implementation artifacts, not active plans. Keep them while frozen recorder
oracles may need to be regenerated from a patched KiCad build.
