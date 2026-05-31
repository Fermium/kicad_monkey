# KiCad PCB Foundation Synthetic Corpus Plan

Status: **DRAFT — awaiting user/3d-viz-rework review**
Date: 2026-05-17
Owner: kicad_monkey worktree
Parent plan: `KICAD_MONKEY_REWORK_PLAN.md`
Companion: `C:\eli\agent-worktrees\3d-viz-rework\toolz\data_models\docs\plans\pcb\20_PCB_A0_CONVERTER_RATCHET_V1_1_PLAN.md`

## Goal

Build a programmatically generated KiCad synthetic PCB corpus that mirrors
`altium\common\pcbdoc_synthesized\` (125 cases) so the 3d-viz-rework PCB
A0 ratchet, kicad_monkey parser / IR / SVG, and downstream consumers
(`pcb.board` v1.1, DwgScene, viz3d, IPC-2581, transcode) all have
isolated, regenerable, byte-stable cases that exercise the generic data
model one feature at a time.

The same corpus simultaneously serves:

1. **3d-viz-rework KiCad ratchet** — when the Altium leg lands and the
   ratchet pivots to KiCad, every PCB feature in the generic `pcb.board`
   shape has an isolated synthetic case to push through the
   source→`pcb.board`→SVG/DwgScene/viz3d/IPC-2581 pipeline.
2. **kicad_monkey parser / round-trip / writer pressure** — every case
   round-trips through the OO model. Where the writer can't reproduce a
   feature, we **fix kicad_monkey rather than work around** the gap.
   This is the forcing function for the OO model's coverage / fidelity.
3. **L3_007 IR oracle and L3_001 board-svg parity** — the synthetic
   cases already drive these tests; expanded coverage shrinks the time
   between regression and detection.
4. **IPC-2581 and viz3d validation (bonus)** — once 3d-viz-rework's
   `pcb.board` shape is settled, the same cases re-flow through the
   IPC-2581 writer and viz3d smoke. The generator-first design means
   regeneration is cheap; reference outputs stay current.

## Pattern (mirroring Altium pcbdoc_synthesized)

### Per-case layout

```
kicad/pcb_foundation/case<NNN>__<descriptor>/
  input/
    case<NNN>__<descriptor>.kicad_pcb
    case<NNN>__<descriptor>.kicad_pro
    case<NNN>__<descriptor>.kicad_sch   (minimal — often empty)
    case_metadata.json
  reference_output/
    board_svg/                          (kicad-cli per-layer SVGs)
      case<NNN>__<descriptor>__F_Cu.svg
      case<NNN>__<descriptor>__B_Cu.svg
      case<NNN>__<descriptor>__F_SilkS.svg
      ...
      case<NNN>__<descriptor>__All_Layers.svg
    ipc2581/                            (future, optional)
      case<NNN>__<descriptor>.xml
    viz3d/                              (future, owned by 3d-viz-rework)
      smoke.json
  output/                               (gitignored; runtime scratch)
```

### Naming

- **`case<NNN>__<descriptor>`** — three-digit zero-padded case number,
  double-underscore separator, snake_case descriptor.
- **Cross-CAD alignment** with Altium where the feature is the same. If
  Altium has `case001__track_1mil_minimum`, the KiCad analog also takes
  `case001__track_1mil_minimum`. This makes cross-CAD diffs trivial in
  the ratchet log and in case matrix CSVs.
- **KiCad-only cases** (e.g. stackup variations, embedded TTF fonts in
  the PCB stream, dimensions, etc.) take case numbers `>= 200` to leave
  headroom for Altium-side growth without renumbering.
- **N/A cases**: Altium cases with no meaningful KiCad analog
  (e.g. extruded-body Altium-only features) get a row in the case
  matrix CSV with `kicad_status = not_applicable` and a justification.

### Case metadata schema (`case_metadata.json`)

```json
{
  "case_id": "case001__track_1mil_minimum",
  "family": "track",
  "altium_analog_case_id": "case001__track_1mil_minimum",
  "kicad_min_version": "9.0",
  "feature_tags": ["track", "width:1mil", "layer:F.Cu"],
  "viz_pressure": ["copper_segment_render"],
  "ipc2581_pressure": ["routed_line"],
  "notes": "Minimum-width single segment for stroke-width rounding edge."
}
```

Status CSV (`kicad_v1_1_case_matrix.csv`) is built off these
`case_metadata.json` files plus the kicad-cli regeneration log.

## Generator architecture

### Layout

```
toolz/kicad_monkey/scripts/
  generate_kicad_synthetic_corpus.py     # driver
  synthetic_corpus/
    __init__.py
    common.py                            # board/project skeleton + cli runner
    generate_tracks.py
    generate_arcs.py
    generate_pads.py
    generate_vias.py
    generate_via_construction.py         # blind / buried / micro
    generate_fills.py                    # zones
    generate_text_stroke.py
    generate_text_ttf.py
    generate_text_frames.py
    generate_outlines.py
    generate_polygons.py                 # gr_poly variants
    generate_regions.py                  # zone regions
    generate_cutouts.py
    generate_components.py               # footprints + variants
    generate_pcblib_companions.py        # symbol library companions
    generate_stackups.py                 # 2L/4L/6L/8L/10L
    generate_groups.py
    generate_images.py                   # gr_image
    generate_barcodes.py
    generate_tables.py
    generate_dimensions.py               # supersedes existing script
    generate_embedded_files.py
    generate_misc.py                     # coverage corners
```

### Driver responsibilities

`generate_kicad_synthetic_corpus.py [--family <name>] [--case <id>] [--no-cli] [--clean]`:

1. Iterate every family generator (or a single one with `--family`).
2. Each generator yields case definitions and writes its `.kicad_pcb` /
   `.kicad_pro` / `.kicad_sch` / `case_metadata.json` under the per-case
   `input/`.
3. After write, the driver invokes the staged `kicad-cli` (resolved
   through `resolve_kicad_cli`) to produce per-layer SVGs under
   `reference_output/board_svg/`. Layer list matches
   `synthetic_board_svg_oracle.BOARD_LAYERS`.
4. Writes / updates `kicad_v1_1_case_matrix.csv` at the corpus root.
5. Optionally re-runs L3_001 and L3_007 oracles to sanity-check
   reference parity (gated by `--verify` flag).

### Generator policy: fix kicad_monkey when the OO model can't write a case

This is the **explicit pressure test** the user called out. If, while
writing a generator, the kicad_monkey OO model cannot construct a
feature the case needs (missing setter, wrong default, can't serialize
a blind via, can't emit embedded TTF font, etc.), the generator does
**not** drop down to raw string templating. Instead:

1. Open a kicad_monkey writer/OO model gap issue.
2. Fix it (parse/round-trip/L0 tests cover regressions).
3. Resume the generator.

Hand-written S-expression fallback is reserved for genuine
parser-only-coverage cases (e.g. truly unknown / future tokens) and
must be explicitly flagged in `case_metadata.json.notes`.

## Migration of existing cases (56 cases)

All 14 Phase-1 (`pcb_foundation/`) + 42 Phase-2-synthetic
(`board_svg/input/`) cases get a **one-shot rename** into
`case<NNN>__<descriptor>` slots aligned with Altium where possible.

**Phase A — write the descriptor map.** A single CSV
(`kicad_v1_1_case_rename_map.csv`) lists `old_path -> new_case_id ->
new_path` for every existing case. The map is reviewed against the
Altium case list 1:1.

**Phase B — apply moves.** Driver script renames the directories,
updates the manifest (`build_kicad_corpus_manifest.py` already picks
up `pcb_foundation/<case>/input/*.kicad_pcb` automatically; new layout
is identical), and updates any test path constants in
`synthetic_board_svg_oracle.SYNTHETIC_ORACLE_CASES`.

**Phase C — regenerate reference SVGs** via staged kicad-cli to ensure
filenames pick up the new case prefix.

**Phase D — run the full sweep.** L0 + L3_007 must stay green. L3_001
pivots to manifest-driven enumeration (already queued).

### Proposed mapping — existing cases → case numbers

| Existing case (location) | Proposed case_id | Family |
|---|---|---|
| `pcb_foundation/one_via` | `case019__via_10hole_20dia` (or one-via aligned) | via |
| `pcb_foundation/one_slot_drill` | `case084__pad_slot_hole` | pad |
| `pcb_foundation/one_zone_filled_top` | `case024__fill_top_100x100` | fill |
| `pcb_foundation/board_outline` | `case037__outline_rounded_rect` (or rect) | outline |
| `pcb_foundation/component_designator_top` | `case066__comp_smd_top_r1` (or text-on-fp) | component |
| `pcb_foundation/simple_test_knockout` | `case201__text_knockout_basic` (KiCad-only family) | text_knockout |
| `pcb_foundation/simple_text_knockout2` | `case202__text_knockout_variant` | text_knockout |
| `pcb_foundation/dim_aligned_horizontal` | `case220__dim_aligned_horizontal` (KiCad-only) | dimension |
| `pcb_foundation/dim_center` | `case221__dim_center` | dimension |
| `pcb_foundation/dim_leader_frame_rect` | `case222__dim_leader_frame_rect` | dimension |
| `pcb_foundation/dim_leader_plain` | `case223__dim_leader_plain` | dimension |
| `pcb_foundation/dim_orthogonal_horizontal` | `case224__dim_orthogonal_horizontal` | dimension |
| `pcb_foundation/dim_orthogonal_vertical` | `case225__dim_orthogonal_vertical` | dimension |
| `pcb_foundation/dim_radial` | `case226__dim_radial` | dimension |
| `board_svg/input/one_track_top_copper` | `case005__track_top_10mil` (closest analog; verify width) | track |
| `board_svg/input/multiple_tracks_45_top_copper` | `case004__track_multiple` | track |
| `board_svg/input/multiple_tracks_curves` | `case010__arc_top_semicircle` (or track+arc) | track/arc |
| `board_svg/input/silk_arc_top` | `case009__arc_top_quarter` (on silk variant) | arc |
| `board_svg/input/silk_arc_top_dashed`/`dotted`/`dash_dot`/`dash_dot_dot` | `case230-233__arc_silk_<stroke>` | arc-stroke |
| `board_svg/input/silk_bezier_top` | `case234__poly_silk_bezier` | bezier |
| `board_svg/input/silk_circle_top`, `silk_circle_top_filled` | `case235__circle_silk`, `case236__circle_silk_filled` | circle |
| `board_svg/input/silk_line_top` + 4 stroke variants | `case240-244__line_silk_<stroke>` | line |
| `board_svg/input/silk_lines_top` | `case245__line_silk_multiple` | line |
| `board_svg/input/silk_poly_top`, `filled`, `not_filled` | `case039__poly_d_shape` (analog) + variants | poly |
| `board_svg/input/silk_rect_top`, `filled` | `case044__poly_rect_top_solid` + variant | poly_rect |
| `board_svg/input/simple_text` + 270/90/bold/mirrored | `case026-029__text_stroke_*` (stroke) | text_stroke |
| `board_svg/input/simple_test_60`, `italic`, `kicad_font`, `left_bottom`, `right_top` | text rotation/justification | text_stroke |
| `board_svg/input/complex_font*` (3 cases) | `case030-033__text_ttf_arial_*` (TTF variants) | text_ttf |
| `board_svg/input/one_chamfer_roundrect` | `case083__pad_roundrect_smd` (chamfered variant) | pad |
| `board_svg/input/one_custom_pad` | `case122__custom_pad` | pad |
| `board_svg/input/one_mask_tenting_vias` | `case085__pad_tenting` (via variant) | via_tenting |
| `board_svg/input/synthetic_board_cutouts` | `case057-061__cutout_*` (multi-cutout) | cutout |
| `board_svg/input/synthetic_pad_shapes` | `case082__pad_per_layer_shapes` (combined) | pad |
| `board_svg/input/knockout_zone` | `case250__zone_knockout` (KiCad-only) | zone_knockout |
| `board_svg/input/missing_elements` | `case260__coverage_missing_elements` | coverage_corner |

**Final mapping happens in Phase A** of the migration; each existing
fixture gets a content audit (what does the `.kicad_pcb` actually
contain?) and the descriptor is locked in.

## New case roadmap (programmatic generation)

Cases below the dotted line are **gaps to fill** — generated from
scratch by the family generators. The Altium analog (left) is the
source-of-truth for naming and parameters; KiCad-only features
(right) get the `>= 200` slots.

### Altium-aligned families (case001–case125)

Generated for every Altium case where KiCad has the same feature.

| Altium case # | Family | KiCad coverage | Generator |
|---|---|---|---|
| 001–006 | track | widths (1/10/25/50 mil), layers (top/bottom/inner), multiple | `generate_tracks.py` |
| 007–010 | arc | wide / full circle / quarter / semicircle, layers | `generate_arcs.py` |
| 011–018 | pad | smd / th, round / rect / octagon, sizes, layers, mixed array | `generate_pads.py` |
| 019–022 | via | sizes (10/12/20 hole/dia), multiple | `generate_vias.py` |
| 023–025 | fill | layers, sizes | `generate_fills.py` |
| 026–029 | text_stroke | sizes, rotations, layers, hello | `generate_text_stroke.py` |
| 030–033 | text_ttf | arial bold / italic / hello / rotated | `generate_text_ttf.py` |
| 034–038 | outline | chamfered / half-circle / octagon / rounded | `generate_outlines.py` |
| 039–045 | poly | shapes (d/diamond/L/pentagon/rect/triangle), layers, multiple | `generate_polygons.py` |
| 046–051 | region | shapes, multiple | `generate_regions.py` |
| 052–056 | net | mixed primitives, polys, via-in-poly | `generate_components.py` (net assignments) |
| 057–061 | cutout | circle / arc / rect / multiple / with copper | `generate_cutouts.py` |
| 062–067 | component | rotations / smd top+bottom / nets / multiple | `generate_components.py` |
| 068–080 | pcblib companion | footprint library variants | `generate_pcblib_companions.py` |
| 081–085 | pad advanced | mask expansion / per-layer shapes / roundrect / slot / tenting | `generate_pads.py` |
| 086–089 | via advanced | **blind / buried / micro / mixed spans** ← KiCad supports! | `generate_via_construction.py` |
| 090–096 | poly / region advanced | holes / net / hatched / large / fills | `generate_polygons.py` |
| 097–098 | stackup | 4-layer, 6-layer simple | `generate_stackups.py` |
| 099, 103 | font specials | monkey_font, bunny_font (KiCad equivalents) | `generate_text_ttf.py` |
| 100 | power plane | hatched copper plane | `generate_fills.py` |
| 101 | string replacement | text variable substitution | `generate_text_stroke.py` |
| 102 | pad stress | offset / rotation combos | `generate_pads.py` |
| 104–108 | text frame | overflow / wrap / justification | `generate_text_frames.py` |
| 106 | barcode | gr_barcode (KiCad supports) | `generate_barcodes.py` |
| 109–110 | 3D models | with embedded / no embed (refs only, no extruded-body) | `generate_components.py` |
| 111 | cutout arc holes | arc-bounded cutouts | `generate_cutouts.py` |
| 112–117 | HLR projections | **N/A in KiCad** (no HLR) | matrix: `not_applicable` |
| 118 | TC2030 ASSY TP pads | test point pad combos | `generate_pads.py` |
| 120 | via backdrill | KiCad supports drill_to_layer on vias | `generate_via_construction.py` |
| 121 | pcbdoc extract | parser corner | `generate_misc.py` |
| 122 | custom pad | custom outline pad | `generate_pads.py` |

### KiCad-specific families (case200+)

KiCad supports several features Altium doesn't expose the same way.
These get fresh slots:

| Case # | Family | Coverage |
|---|---|---|
| 200–209 | text_knockout | gr_text knockout, fp_text knockout (existing + variants on every layer) |
| 210–219 | text_alignment | KiCad-specific alignment / hjustify / vjustify matrix |
| 220–229 | dimension | aligned / center / leader_plain / leader_frame_rect / orthogonal_h / orthogonal_v / radial (existing) + future leader+frame variants |
| 230–249 | graphic strokes | KiCad `(stroke (type dashed/dotted/dash_dot/dash_dot_dot))` on line / arc / rect / poly / circle |
| 250–259 | zone advanced | knockout zone, keepout (no-track/no-via/no-fp), thermal relief, rule areas |
| 260–269 | coverage corner | missing_elements, unknown tokens, passthrough setup, deeply nested footprints |
| 270–289 | stackup advanced | 8L / 10L rigid; flex (1-layer); rigid-flex (multi-stackup zones); HDI build-up |
| 290–299 | embedded files | embedded fonts (TTF), embedded images (gr_image), embedded models (3D refs), embedded barcodes |
| 300–309 | groups | grouped graphics, nested groups, group-level locks |
| 310–319 | tables | gr_table, fp_table, text-table content |
| 320–329 | image | gr_image at scale / rotation / layers |
| 330–339 | net classes | multi-class boards, class assignments via pcbnew rules |
| 340–349 | properties | board variables, project text variables, kicad_pro `text_variables` |

## Test wiring

### Manifest builder

`build_kicad_corpus_manifest.py` already iterates
`pcb_foundation/<case>/input/*.kicad_pcb` via `_pcb_foundation_case(...)`
(per memory: `layout="case_bucket"`, `domains=["pcb_foundation",
"pcb_ir","board_svg"]`). New cases get picked up automatically — no
manifest code changes required for cases that follow the layout.

After all moves land, **remove** the legacy `board_svg/input/*/*.kicad_pcb`
loop from `_topic_cases()`.

### Stratum tests

- **L0** parser smoke — every case must parse without error.
- **L1_001 PCB roundtrip** — every case must round-trip byte-stably
  (or with a documented diff for cases generated by hand-written
  fallback).
- **L1_019 source_inventory** — every case yields a valid inventory
  dict. Future: family-specific assertions on `unknown_elements`.
- **L3_001 board_svg** — pivots to manifest-driven; pairs each case's
  `input/<board>.kicad_pcb` with `reference_output/board_svg/<board>__*.svg`.
- **L3_007 IR oracle** — synthetic oracle case table pulls from the
  same manifest; xfail dictionary keys lock to new case IDs.
- **(future)** L4/L5 IPC-2581 emit per case, viz3d smoke per case.

### Reference regeneration

`generate_kicad_synthetic_corpus.py --regen-refs` walks every case
and re-invokes staged kicad-cli. Used after kicad-cli upgrades and
when generator parameters change.

## Phased execution

### Phase 0 — plan ack (this doc)

User + 3d-viz-rework review of:
1. Per-case layout and naming convention.
2. The migration mapping table (existing 56 → caseNNN slots).
3. The new-case roadmap above (Altium-aligned + KiCad-only families).
4. Generator policy (fix kicad_monkey when writer is short).

### Phase 1 — migration of existing 56 cases

1. Write `kicad_v1_1_case_rename_map.csv` (one row per existing case;
   user reviews).
2. Apply moves; regenerate per-layer SVG refs.
3. Update `SYNTHETIC_ORACLE_CASES` and any string-literal case IDs in
   tests.
4. Pivot L3_001 to manifest-driven enumeration.
5. Remove legacy `board_svg/input/*` loop from manifest builder.
6. Bulletin: post status.

### Phase 2 — generator scaffold + tracks/arcs/pads/vias/fills

1. Write `synthetic_corpus/common.py` (board+project skeleton, cli runner).
2. Write `generate_tracks.py`, `generate_arcs.py`, `generate_pads.py`,
   `generate_vias.py`, `generate_fills.py`.
3. Fill case001–case025 slots. Where existing fixtures already cover a
   slot, the generator validates parity and the existing file stays.
4. Iterate until kicad_monkey writer supports every needed feature
   programmatically. Each gap = a kicad_monkey commit.

### Phase 3 — text (stroke + TTF + frames)

`generate_text_stroke.py`, `generate_text_ttf.py`,
`generate_text_frames.py`. Fill case026–case033, case099, case101,
case103–108. Heavy pressure on kicad_monkey text rendering / render
cache emission / Newstroke renderer.

### Phase 4 — outlines / polys / regions / cutouts

Fill case034–case061. Covers board outlines, gr_poly variants, zone
regions, cutouts.

### Phase 5 — components / pcblib / nets

Fill case052–case080. Footprint variants, library companions, net
assignments. Pressure on `Footprint` OO + parse/write symmetry.

### Phase 6 — advanced pads / vias / stackups

Fill case081–case098. **Blind / buried / micro vias** and
**multi-layer stackups** — biggest KiCad-side coverage gain.

### Phase 7 — KiCad-only families (case200+)

Knockout, alignment, dimensions (extend existing), stroke variants,
zone advanced, coverage corners, stackup advanced (rigid-flex), embedded
files, groups, tables, images, net classes, property substitution.

### Phase 8 — IPC-2581 + viz3d wiring (bonus)

Add `reference_output/ipc2581/` per case (generated by kicad_monkey's
IPC-2581 writer once it exists or by staged kicad-cli if it gains
IPC-2581 export). Hook viz3d smoke. These are 3d-viz-rework consumers
of the corpus.

## Exit criteria (v1.1)

- All 56 existing cases renamed and slotted into `case<NNN>__`.
- All Altium-aligned slots (cases 001–122 minus N/A HLR slice) have a
  KiCad analog or a documented `kicad_status=not_applicable` row.
- KiCad-only families (200+) cover stackup variations, blind/buried,
  embedded fonts, knockout text, dimensions, stroke styles.
- Every case is programmatically regenerable via the driver script.
- kicad_monkey OO model can write every case that isn't explicitly a
  parser-only coverage corner.
- `kicad_v1_1_case_matrix.csv` (mirroring Altium's) is current and
  auto-derived from `case_metadata.json` files.
- L0 / L1_001 / L1_019 / L3_001 / L3_007 all green across the full
  corpus.
- 3d-viz-rework can iterate the corpus from their ratchet without
  per-case path negotiation.

## Risks / known limitations

- **No KiCad extruded-body analog** for Altium's STEP/extruded
  body cases (case068, case109, etc.). Treat as
  `kicad_status=not_applicable`.
- **HLR (hidden-line removal) projections** are Altium-specific
  (case112–117). N/A.
- **kicad-cli IPC-2581 export** may not be available in the staged
  builds; the IPC-2581 path may need kicad_monkey-side writer first.
- **Embedded TTF font handling** may need kicad_monkey OO model
  extensions (parse/round-trip of `(embedded_fonts ...)` section).
- **Rigid-flex multi-stackup zones** are KiCad 9+ and may stress the
  current `(setup (stackup ...))` parser.

Each risk becomes a kicad_monkey OO-model commit when the relevant
generator runs into it (per the "fix kicad_monkey first" policy).

## Open items (for review)

1. **Case number alignment**: keep Altium's gaps (e.g. case119 missing,
   case117 jumps to case120) in the KiCad list too? My take: yes —
   easier cross-CAD diffs.
2. **Naming style**: I propose snake_case descriptors with feature
   parameters as suffixes (e.g. `case005__track_top_10mil` includes
   layer and width). OK?
3. **Generator language / dependencies**: Python with kicad_monkey OO
   model + staged kicad-cli. No new deps. OK?
4. **Reference SVG regeneration cadence**: every case regenerated on
   every kicad-cli upgrade? I'd default to "regenerate when CLI
   manifest changes" + opt-in `--regen-refs` flag.
5. **Test coverage of generator itself**: should each generator have
   an L0-style "writes 1 case successfully" smoke test, or rely on the
   downstream stratum tests? I'd vote for the latter (downstream tests
   already validate the artifact).
6. **Per-case `.kicad_sch`**: minimal-empty or omit entirely? KiCad
   projects work without `.kicad_sch`, but consumers may expect it.
   I'd write a 1-line empty sch by default; cases that test schematic
   linkage override.

## Sign-off needed before execution

- User: confirm naming convention + family roadmap + generator policy.
- 3d-viz-rework (bulletin): confirm the case matrix CSV will be
  consumed alongside the Altium one; confirm v1.1 ratchet entry point
  for KiCad uses this corpus.

Once both ack, Phase 1 (migration mapping CSV + execution) begins.
