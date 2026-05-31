# kicad_monkey content-drift work plan (Phase B continuation)

Living plan for picking off content-drift buckets after the parser-fatal
fixes (#1, #8, #9) closed all actionable EMIT rejections.

Source of truth for prioritisation: `_drift_summary.py` against the
latest `oracle_diff_report.json` in this directory.

## Aggregate token totals (post-#9)

| token | count | notes |
|---|---:|---|
| `<other>` | 41 494 | catch-all (mostly hierarchical-sch/wks shape) |
| `thickness` | 19 922 | text effects + stroke thickness — defaults? |
| `font` | 17 355 | always co-occurs with effects/size |
| `size` | 17 287 | always co-occurs with effects/font |
| `effects` | 17 263 | wraps font/size/justify/hide |
| `hide` | 15 481 | (hide yes) / (hide no) round-trip |
| `do_not_autoplace` | 3 957 | symbol property attribute |
| `show_name` | 3 809 | symbol property attribute |
| `face` | 1 238 | font face elision |
| `xy/pts` | 1 454 | inline-vs-multi-line layout (cosmetic) |
| `uuid` | 824 | uuid round-trip mismatches |

## Aggregate token totals (post-#10 — Slice 10 a+b complete)

| token | count | notes |
|---|---:|---|
| `<other>` | 41 422 | unchanged — hierarchical-sch shape (Slice 15) |
| `xy` | 927 | xy / pts inline-vs-multi-line (cosmetic) |
| `uuid` | 824 | unchanged — Slice 14 |
| `pts` | 527 | xy / pts inline-vs-multi-line |
| `wire` | 490 | schematic wire round-trip |
| `type` | 398 | likely stroke (type default) elision |
| `stroke` | 392 | likely stroke shape drift |
| `width` | 392 | co-occurs with stroke |
| `do_not_autoplace` | 307 | dropped from 3 957 — Slice 12 |
| `tbtext` | 224 | worksheet (`.kicad_wks`) — Slice 16 |
| `color` | 210 | likely stroke colour or text colour |
| `font` | 143 | dropped from 17 355 (Slice 10a/b) |

`thickness`, `size`, `effects`, `hide`, `show_name`, `face` all dropped
out of the top 20 — Slice 10 closes the v9→v10 text-effects bucket.

## Worst-offender fixtures

```
+16047/-14238  Regulator_Switching.kicad_sym  (effects/font/size/thickness/hide)
+ 4347/-11905  FE.kicad_sch                   (<other>/do_not_autoplace/show_name/effects)
+ 3480/-33337  top_level.kicad_sch            (<other> dominates — hierarchical-sch shape)
+ 3335/- 2796  Connector_Audio.kicad_sym      (effects/font/size/thickness/hide)
+ 3262/- 2804  Converter_ACDC.kicad_sym       (effects/font/size/thickness/hide)
+ 3099/- 2639  StickHub.kicad_sch             (thickness/effects/font/size/show_name)
```

Effects/font/size/thickness/hide cluster across virtually every symbol
fixture — single root cause, broad blast radius. Address first.

## Slice queue (in priority order)

1. **Slice 10 — text effects default elision (effects/font/size/hide).**
   KiCad elides default text effects fields where we emit them
   verbatim, or vice versa. Pick smallest reproducer (e.g.
   `Connector_Audio.kicad_sym`) and align our emitters against KiCad
   source (`kicad/eeschema/sch_io/kicad_sexpr/sch_io_kicad_sexpr.cpp`,
   `kicad/common/font/font_io.cpp`).
2. **Slice 11 — stroke `thickness` default elision.** Likely same
   class of bug as #10 but on `(stroke (width N) (type default))` and
   `(stroke (thickness N))` blocks.
3. **Slice 12 — symbol property attributes (`do_not_autoplace`,
   `show_name`).** Investigate whether they are default-on or
   default-off in current KiCad and align.
4. **Slice 13 — `face` font face elision (`(font (face "...")` form).**
5. **Slice 14 — `(uuid ...)` round-trip drift.** 824 mismatches —
   likely a small number of fixtures with structural ordering issues.
6. **Slice 15 — hierarchical schematic `<other>` bucket.** Audit
   `top_level.kicad_sch` / `FE.kicad_sch`; this is most likely the
   per-sheet `(instances ...)` (#3) plus other structural elements.
7. **Slice 16 — `.kicad_wks` worksheet drift** (`Wavenumber.kicad_wks`).

## Method

For every slice:
1. Read smallest exemplar fixture diff and identify the syntactic
   change (added/removed line, value change, ordering).
2. Locate the corresponding emit/parse site in the KiCad C++ source at
   `C:\eli\kicad_build\kicad\` and use it as the canonical reference.
3. Apply targeted fix; do NOT touch unrelated code.
4. Add a regression case to `test_L1_010_kicad_cli_oracle_gate.py` if
   there is a clear minimal reproducer; otherwise rely on full oracle
   re-run.
5. Re-run oracle, confirm bucket shrinks substantially, confirm no
   new EMIT rejections.
6. Run `pytest toolz-tests/suites/kicad_monkey/tests/L1_parsing/`
   and confirm 0 regressions.
7. Commit toolz + toolz-tests as separate commits per the workflow rule.
8. Update this file: tick off the slice, add any new findings.

## Status tracker

- [x] **Slice 1 (#1)** — `(at X Y angle)` 3-tuple at all rotated sites
- [x] **Slice 8 (#8)** — `(generated)` `(id ...)` first-child ordering
- [x] **Slice 9 (#9)** — Zone `(layers)` plural form + `(island)` flag
- [x] **Slice 10** — text effects default elision (effects/font/thickness/hide)
  - 10a: `(thickness X)` elided per `EDA_TEXT::Format` auto-thickness guard
  - 10b: `(hide yes)` hoisted to property/pin level per `saveField`
    (sch_io_kicad_sexpr_lib_cache.cpp) — accept v9 nested form on parse,
    canonicalise emit at parent level for `SymProperty` / `SymPin`
  - Smoke: `Connector_Audio.kicad_sym` and `Regulator_Switching.kicad_sym`
    drop to **0** diff lines via `_diff_one.py`
- [x] **Slice 11** — stroke colour round-trip (renamed from "stroke thickness elision")
  - Phase A inventory hypothesis (19 922 `thickness` mismatches as
    "stroke thickness") was actually FONT thickness — closed by Slice 10a.
  - Real residual `stroke`/`type`/`width`/`color` bucket: `Stroke`
    declared `color: Optional[Tuple[int,int,int,float]]` but never
    parsed or emitted it. Source `(stroke (width 0) (type solid)
    (color 0 0 0 1))` was being silently downgraded to `(stroke
    (width 0) (type solid))`.
  - Fix: parse `(color R G B A)` inside `(stroke ...)` and emit
    when present. Smoke: `ADC_PWR.kicad_sch` 123 → 63 diff lines.
- [x] **Slice 12** — symbol property attributes (`show_name`, `do_not_autoplace`)
  - KiCad 10 emits these as `(name yes/no)` sub-lists via
    `KICAD_FORMAT::FormatBool` (`saveField`, `sch_io_kicad_sexpr_lib_cache.cpp`).
    KiCad 10's reader REJECTS the bare-token form mid-property, so
    emitting `do_not_autoplace` as a bare flag (our v9 behaviour) was
    causing kicad-cli to fail to load schematics with hidden power
    symbols (`#PWR090` etc.).
  - Parse: accept `(name yes/no)` sub-list AND the legacy bare-token form.
  - Emit: `(show_name yes)` / `(do_not_autoplace yes)` sub-list when True,
    elide when False — kicad-cli canonicalises to explicit yes/no on save.
  - Smoke: `ADC_PWR.kicad_sch` drops from a kicad-cli REJECT (rc=3) to
    123 diff lines (residual is `(stroke ... (color 0 0 0 1))` — Slice 11).
- [x] **Slice 12c** — lib_symbol `(power global)`/`(power local)` form
  - Parser at sch_io_kicad_sexpr_parser.cpp:377 accepts `(power)` /
    `(power global)` / `(power local)`; emit at lib_cache.cpp:401 always
    writes the explicit form. Our previous bare-token emit was dropped
    on round-trip. Smoke: ADC_PWR 49 -> 43 lines.
- [x] **Slice 12d** — `(fields_autoplaced yes)` FormatBool form
  - KiCad 10 uses parseMaybeAbsentBool(true) at parser.cpp:3270; our
    has_flag() parse + bare-token emit lost the data on round-trip.
    Added `parse_maybe_absent_bool` helper and routed all five sites
    (SchSymbol, SchLabel*, SchSheet) through it. Smoke: ADC_PWR 43 -> 37.
- [x] **Slice 17** — top-level `(text ...)` SCH_TEXT annotations
  - `KiCadSchematic.from_sexp` declared `texts: list` and serialised it
    in `to_sexp`, but `find_all_elements(sexp, 'text')` was never called
    — every plain SCH_TEXT_T was silently dropped (content loss).
    Added `SchText` dataclass per saveText (sch_io_kicad_sexpr.cpp:1431).
    Smoke: ADC_PWR 37 -> 0 (full parity).

## Aggregate token totals (post-#17 — re-run on 73 fixtures)

ok 49/73, diff 20/73, skipped_cli 9 (older v9 fixtures), emit-rejected 4,
parse/emit error 4. Top drift tokens:

| token | count | notes |
|---|---:|---|
| `<other>` | 40 311 | dominated by hierarchical-sch + worksheet |
| `xy` | 553 | inline-vs-multi-line cosmetic |
| `uuid` | 407 | Slice 14 |
| `tbtext` | 224 | worksheet (Slice 16) |
| `name`/`line`/`pos` | ~200 | mostly worksheet |
| `pts`/`start`/`end` | ~150 | schematic polyline / rectangle (#18) |
| `wire` | 116 | schematic wire round-trip |
| `stroke`/`width`/`color` | ~280 | residual stroke drift |
| `polyline` | 33 | schematic polyline graphics (#18) |

Worst-offender fixtures (after #17):
```
+30 791  top_level.kicad_sch    (text_box / exclude_from_sim / size / margins / stroke)
+ 8 083  FE.kicad_sch           (text_box / margins / stroke)
+    99  variants.kicad_sch     (polyline / pts / xy)
+    40  StickHub.kicad_sch     (polyline / pts / xy)
+    28  groups_load_save.kicad_sch  (rectangle / start / end)
+    22  sallen_key.kicad_sch   (text_box)
+    27  variant_test.kicad_sch (variant / name / in_pos_files)
+    14  complex_hierarchy.kicad_sch  (instances / project / path / page)
+    14  flat_hierarchy.kicad_sch     (instances / project / path / page)
```

text_box is the dominant remaining content-loss bug (38 k+ lines across
three fixtures). polyline + rectangle are the same shape.

- [x] **Slice 18** — top-level schematic `(text_box ...)` content loss (closed pre-summary)
- [x] **Slice 19a** — `kicad_sexpr` string escape semantics aligned with
      KiCad's dsnlexer.cpp:655 / richio.cpp:472 (Quotes). Unescape recognises
      \" \\ \a \b \f \n \r \t \v \xNN; emit only escapes \n \r \\ \" per
      OUTPUTFORMATTER::Quotes. Centralised in `_unescape_kicad_string` /
      `_escape_kicad_string`; 5 call sites routed through them.
      Smoke: `sallen_key.kicad_sch` 16 -> 0 lines.
- [x] **Slice 19b** — top-level schematic `(polyline ...)` / `(rectangle ...)`
      content loss. New `kicad_sch_shapes.py` mirroring formatPoly /
      formatRect (sch_io_kicad_sexpr_common.cpp:325 / :273). Differs from
      the lib-symbol form in `aIsPrivate=false`, `aInvertY=false`, optional
      `(locked yes)`, and `uuid` emitted as `QuotedString` per Quotew.
      Smoke: variants 99 -> 36, StickHub 40 -> 0, groups_load_save 28 -> 11.
      Arc/circle/bezier dispatch is identical but no current fixture
      exercises them — deferred until they show up in oracle drift.
- [x] **Slice 20** — per-symbol variant overrides on instance paths.
      KiCad emits `(variant (name "...") [(dnp ...)] [(exclude_from_sim ...)]
      [(in_bom ...)] [(on_board ...)] [(in_pos_files ...)] [(field ...)]*)`
      under each `(path ...)` per saveSymbol (sch_io_kicad_sexpr.cpp:953).
      Each bool elided when matching the parent symbol's default —
      `Optional[bool]` round-trips that.
      Smoke: variant_test 27 -> 0; variants residual 36 -> 18 (sheet-level).
- [x] **Slice 21** — per-sheet `(instances ...)` block on hierarchical sheets.
      saveSheet (sch_io_kicad_sexpr.cpp:1208) emits an entire
      `(instances (project ... (path "/UUID/..." (page "1") [(variant ...)]*)))`
      block inside every `(sheet ...)`, and we were dropping it whole. Added
      `SchSheetInstance` reusing `SchSymbolInstanceVariant` (sheet variants
      only emit dnp/exclude_from_sim/in_bom but the dataclass elides None).
      Smoke: variants 18 -> 0, complex_hierarchy 14 -> 0, flat_hierarchy 14 -> 0.
- [x] **Slice 22** — top-level `(group "name" (uuid) [(locked yes)] [(lib_id)] (members ...))`
      content loss. New `SchGroup` mirroring saveGroup
      (sch_io_kicad_sexpr.cpp:1656). KiCad early-returns on empty groups so
      we never round-trip a member-less group.
      Smoke: groups_load_save 11 -> 0.
- [x] **Slice 23** — top-level `(image ...)` SCH_BITMAP_T content loss.
      New `SchImage` mirroring saveBitmap (sch_io_kicad_sexpr.cpp:1035) +
      FormatStreamData (kicad_io_utils.cpp:55). Stores base64 chunks
      verbatim as `List[str]`. Because `(data ...)` ends up at depth 3
      under `(kicad_sch (image (data ...)))`, `format_sexp(max_nesting=2)`
      keeps the chunks inline, producing million-character lines that
      kicad-cli rejected. Added `format_image_data_blocks(text)` post-
      processor invoked from `KiCadSchematic.to_text()` after `format_sexp`
      to put each chunk on its own line.
      Smoke: top_level.kicad_sch 29 707 -> 66 (cli now loads), FE.kicad_sch
      7 437 -> 44 (cli now loads).
- [x] **Slice 24** — top-level `(netclass_flag ...)` properties + ordering.
      saveText for SCH_DIRECTIVE_LABEL_T (sch_io_kicad_sexpr.cpp:1431)
      emits text, length, shape, at, fields_autoplaced, effects, uuid,
      locked, then per-field saveField. We were missing the trailing
      property children entirely and had locked/uuid in the wrong order.
      Added `properties: List[SymProperty]`, `fields_autoplaced`, `locked`
      to SchNetclassFlag; emit reordered to match saveText.
      Smoke: top_level 113 -> 42, FE 48 -> 0.
- [x] **Slice 25** — top-level `(rule_area ...)` content loss. saveRuleArea
      (sch_io_kicad_sexpr.cpp:1373) wraps the inner shape with locked +
      4 always-emitted FormatBool flags (exclude_from_sim, in_bom,
      on_board, dnp). New `SchRuleArea` dataclass; recognised polyline /
      rectangle inner shapes parsed via `kicad_sch_shapes`, arc/circle/
      bezier round-tripped raw.
      Smoke: top_level 42 -> 21.
- [x] **Slice 26** — sheet `(property ...)` `(show_name yes)` form. We
      used `has_flag()` (bare-token only) so KiCad 10's `(show_name yes)`
      sub-list form was lost on round-trip. Aligned SchSheetProperty with
      SymProperty: `_bool_flag` helper, sub-list emit, added
      `do_not_autoplace` and `hide` fields, reordered emit (property, at,
      hide, show_name, do_not_autoplace, effects).
      Smoke: top_level 21 -> 6.
- [x] **Slice 27** — font color + line_spacing fields. EDA_TEXT::Format
      (eda_text.cpp:1090) emit order is face, size, line_spacing,
      thickness, bold, italic, color. We were missing `color` (parse +
      emit) and `line_spacing` parse. Added both to Font, reordered
      to_sexp() to match upstream.
      Smoke: top_level 6 -> 0, FE 0 (full parity for both).
- [ ] **Slice 13** — font face elision (dropped out of top 20 — likely closed by Slice 10)
- [ ] **Slice 14** — `(uuid ...)` round-trip drift (407 — was 824)
- [ ] **Slice 15** — hierarchical-sch `<other>` 40 311 (per-sheet instances —
      partially addressed by #21 but `top_level.kicad_sch` / `FE.kicad_sch`
      may have remaining structural drift; re-check post-22 oracle)
- [x] **Slice 16** — `.kicad_wks` worksheet drift. Closed in three
      sub-slices (16a/16b/16c). All 73 L1_007 round-trip tests pass and
      full L1_parsing suite (2845 tests) passes unchanged.
  - 16a (9b82d0f4): preserve `(data ...)` chunk lines on bitmaps —
    `WksBitmap.data_chunks: List[str]` round-trips KiCad's 76-char
    base64 chunk shape per `FormatStreamData` (kicad_io_utils.cpp:55).
    `_format_data_blocks` regex rewrites the inlined emit to one chunk
    per line.
  - 16b (ddb83528): preserve interleaved on-disk element order via
    `_ordered_items: List[Tuple[str, Any]]` — KiCad's
    `DS_DATA_MODEL::GetItem` walks an insertion-ordered vector, so
    item order IS data.
  - 16c (d969af30): align item-body emit with `ds_data_model_io.cpp`.
    Re-emit `name` (always, even empty), positions, `option`, repeat
    tail, `comment` last; pts sections last on polygons; data block
    last on bitmaps. NaN sentinel for missing `linewidth`. Added
    `option`, `face`, `color` (font), justify-as-list, full setup
    margin emit (KiCad never elides). Also fixed a `format_sexp`
    double-space bug at `)<sp><sp>(` for adjacent inline siblings,
    and updated `_format_data_blocks` to handle the
    `max_nesting=3` shape where the closing `)` of `(data ...)` lands
    on its own line.

      Remaining drift (deferred — purely cosmetic/textual, not data-loss):
      | fixture | src | out | delta | notes |
      |---|---:|---:|---:|---|
      | gost_landscape | 90 | 600 | +510 | whitespace-only delta (identical after normalising) |
      | A4_ISO5457 | 86 | 541 | +455 | source uses `(name rect1:Rect)` unquoted (legacy form) |
      | pagelayout_default | 36 | 189 | +153 | source legacy: sparse setup, no `(name "")`, comment ordered first |
      | pagelayout_logo | 192 | 823 | +631 | same as default; source omits unset margins |
      | Wavenumber | 2735 | 2755 | +20 | source uses `-0.0000000000001137` fixed-point, our `str()` emits `-1.137e-13` |

      None of these are content drift — values round-trip mathematically.
      Closing them would require: (a) storing original quoted/unquoted
      forms for `(name ...)`, (b) suppressing always-emit-name when
      empty (changes KiCad's modern emit shape — wrong), (c) custom
      float formatter for very small numbers (re-attempting Slice 31a
      restricted to `.kicad_wks`), (d) tab indent option in
      `format_sexp`. Defer until shown to be worth the complexity.

## Post-Slice-27 oracle status (current)

Oracle: `ok=59/73`, `diff=5/73`, `kicad_rejected_emit=4`, `parse_emit_errors=4`,
`skipped_cli=9` (older v9 fixtures kicad-cli 10.0.0 can't load).

Remaining DIFF fixtures (all small):

```
+0/-1  reference_images_load_save.kicad_pcb  (locked)
+0/-1  pic_sockets.kicad_sch                  (body_styles)
+1/-1  groups_load_save_v20231212.kicad_pcb   (uuid)
+1/-2  EmptyZone.kicad_pcb                    (priority, thermal_gap)
+0/-6  LayerEnumerate.kicad_pcb               (property, layer, hatch_position, xy)
```

All schematic round-trip [DIFF]s are closed; remaining work is 4 PCB
fixtures + 1 schematic single-line `(body_styles ...)` flag round-trip.

Next slice candidates by leverage (small, surgical):

- **28** — PCB image `(locked ...)` flag round-trip
- **29** — symbol library `(body_styles ...)` round-trip
- **30** — PCB group `(uuid ...)` ordering
- **31** — PCB zone `(priority ...)` / `(thermal_gap ...)` defaults
- **32** — PCB layer `(hatch_position ...)` content loss

- [x] **Slice 28** — PCB image `(locked yes)` round-trip + emit-order
      alignment with `format(PCB_REFERENCE_IMAGE*)`
      (pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr.cpp:1116). Smoke:
      reference_images_load_save.kicad_pcb 1 -> 0.
- [x] **Slice 29** — `lib_symbol` `(body_styles ...)` round-trip per
      sch_io_kicad_sexpr_lib_cache.cpp:410 / parser.cpp:940. Smoke:
      pic_sockets.kicad_sch 1 -> 0.
- [x] **Slice 30** — PCB group accept legacy `(id ...)` per
      pcb_io_kicad_sexpr_parser.cpp:7155. Smoke:
      groups_load_save_v20231212.kicad_pcb 1 -> 0.
- [x] **Slice 31** — PCB zone `(priority N)` round-trip per
      pcb_io_kicad_sexpr.cpp:2954. Smoke: EmptyZone 2 -> 1 (priority
      closed; `thermal_gap` 1-line drift originally diagnosed as a
      kicad-cli upstream lexer bug — later (2026-05-09) determined to
      be a stale staged binary built by kicad-win-builder against a
      pre-`934a5bac34` source clone. Fix `934a5bac34` is upstream
      since 2026-02-25; re-staging from canonical source as
      `76f8839fd232` resolved the drift with no kicad_monkey change).
  - 31a (REVERTED, a9cf2ac1): tried to fix the thermal_gap drift by
    avoiding scientific notation in build_sexp float emit. KiCad's
    DSN_LEXER truncates `3e-06` to `3` on read, so the source value
    `(thermal_gap 0.000003)` round-tripped as `(thermal_gap 3)`. Fix
    formatted small floats as `{:.10f}` strip-trailing-zeros, mirroring
    EDA_UNIT_UTILS::FormatInternalUnits at common/eda_units.cpp:194.
    HOWEVER variants.kicad_pcb regressed by 156 lines: that fixture
    contains arc endpoints written as `(end ... -1e-06)` in the source,
    KiCad's parser truncates these to `-1` and renormalises the arc
    geometry from the truncated values. Pre-fix our `str(-1e-06)` emit
    reproduced the same truncation, so both sides matched after arc
    renormalisation. Post-fix we emitted `-0.000001` (precise),
    kicad-cli renormalised the arc from the precise value, and the
    arc mid-points diverged from ref. Net trade was -1 line on
    EmptyZone vs +156 on variants — reverted.
- [x] **Slice 32** — PCB zone per-layer `(property (layer ...) (hatch_position (xy ...)))`
      round-trip per pcb_io_kicad_sexpr.cpp:3139. Smoke:
      LayerEnumerate.kicad_pcb 6 -> 0.

## Phase B end-of-run state (post-Slice-32)

> **Note (2026-05-09):** the framing below attributes 1 diff and 4
> emit_err to "upstream kicad-cli bugs". That diagnosis was wrong.
> Both buckets were artifacts of a stale staged kicad-cli built by
> kicad-win-builder against a pre-`934a5bac34` source clone. Re-staging
> from canonical source as `76f8839fd232` cleared them. See the
> "Phase B end-of-run state (post-Slice-38, 2026-05-09)" section
> below for the corrected baseline.

```
files       : 73
ok          : 63
diff        :  1   <- EmptyZone thermal_gap (later determined: stale oracle)
emit_err    :  4   <- kicad-cli rejects the SOURCE (api_kitchen_sink x2,
                     corrupted_stackup, ScientificNotation) — last 3
                     also stale-oracle artifacts
cli_skipped :  5   <- worksheet (.kicad_wks) fixtures, Slice 16 deferred
```

All actionable schematic + PCB round-trip drift on the upstream QA
corpus is closed. The remaining EmptyZone diff was originally
attributed to a kicad-cli upstream issue
(`(thermal_gap 0.000003)` -> `(thermal_gap 3)` truncation); later
determined to be a stale staged binary, not an upstream bug. 3 of the
4 EMIT_ERRs were similarly stale-oracle artifacts. The 5 CLI_SKIPs
are .kicad_wks worksheets, deferred to Slice 16.

## Phase B end-of-run state (post-Slice-16, 2026-05-08)

> **Note (2026-05-09):** the "upstream lexer bug" attribution below
> was wrong — see post-mortem
> `2026-05-08-kicad-pcb-scientific-notation-bug.md`. Superseded by
> the "post-Slice-38" section below.

Slice 16 closed in three sub-slices (16a/b/c). Worksheet round-trip
data fidelity achieved: all 73 L1_007 tests pass; bitmap chunk
preservation, interleaved on-disk element order preservation, and
full per-item emit-shape alignment with ds_data_model_io.cpp. Full
L1_parsing suite (2845 tests) continues to pass.

Remaining drift across the whole corpus is now confined to:
- **EmptyZone.kicad_pcb**: 1-line `(thermal_gap 3)` truncation. (Originally
  attributed to upstream kicad-cli lexer; later determined to be a
  stale staged binary built against a pre-`934a5bac34` clone.)
- **5 .kicad_wks fixtures**: cosmetic textual drift only — sparse-setup legacy formatting, unquoted-name legacy forms, scientific-notation float emit, tab-vs-space indent. No data loss; no test impact.
- **4 emit_err** sources kicad-cli itself rejects (3 of these also resolved by the corrected oracle).

Continuing work would target either of:
- ~~Upstream the kicad-cli scientific-notation lexer fix.~~
  (Already upstream as `934a5bac34`, 2026-02-25 — nothing to submit.)
- Re-attempt selective float formatting (cosmetic only, low value).
- Move on to higher-level Phase C work (variant model, consumer
  cleanup, PCB part-2 review, higher-level tools).

## Slices 33-38 (api_kitchen_sink + content-loss bisect, 2026-05-09)

After re-staging kicad-cli `76f8839fd232` (FROM_CHARS_FLAGS scientific-
notation fix), the remaining EmptyZone diff and ScientificNotation
emit-rejection both went green automatically, leaving
`api_kitchen_sink.kicad_pcb` (and `_v...`) as the only remaining
`kicad_rejected_emit`. Bisect on the top-level child list located the
parser-fatal at child #44 (a via with broken tenting). Rolling forward
through the remaining drift on that fixture closed six more sites:

- [x] **Slice 33 (99354251)** — `api_kitchen_sink.kicad_sch` top-level
      shapes and label/symbol fields. (Was a peer fixture; bundled here
      for completeness — closed alongside the PCB work.)
- [x] **Slice 34 (43a896bb)** — Stop emitting kicad-cli-rejecting
      dimension/via fields.
  - `DimensionStyle.to_sexp(dimension_type=...)`: emit
    `arrow_direction`/`extension_height` only on aligned/orthogonal,
    `text_frame` only on leader (per PCB_IO_KICAD_SEXPR::format(PCB_DIMENSION*)
    and `pcb_io_kicad_sexpr_parser.cpp:4761` `dynamic_cast<PCB_DIM_ALIGNED*>`
    parser assertion).
  - `Via.tenting`/`covering`/`plugging` refactored from `Optional[str]`
    to `Optional[FrontBackOptBool]` matching `parseFrontBackOptBool` /
    `FormatOptBool` (`pcb_io_kicad_sexpr.cpp:2780-2821`); added
    `capping`/`filling` simple-bool fields. Emit order: tenting,
    capping, covering, plugging, filling.
- [x] **Slice 35 (12432e8f)** — Preserve `net_tie_pad_groups`
      separator on round-trip. Added `PadNameGroup.raw_token` to retain
      KiCad's verbatim user-string (commas vs spaces vs mixed); falls
      back to canonical join when absent.
- [x] **Slice 36 (d34b331f)** — Round-trip pad clearance / thermal_*
      / teardrops fields. New `TeardropParameters` (9-field block per
      `formatTeardropParameters`) plus `Pad.clearance`,
      `Pad.thermal_bridge_width`, `Pad.thermal_gap`. Emit ordering
      tracks `pcb_io_kicad_sexpr.cpp:1936-1973` and `:2104` (teardrops
      after primitives).
- [x] **Slice 37 (4744f0c4)** — Round-trip arc segments inside
      `(gr_poly (pts ...))`. Added `pts_segments: List[list]` to
      capture original ordered child list (mixed `(xy ...)` /
      `(arc (start) (mid) (end))`); emit replays verbatim when
      populated, falls back to xy synthesis otherwise.
- [x] **Slice 38 (f8ba9d5b)** — `(locked yes)` round-trip on
      `gr_circle` (between fill and layer per `:1092-1098`) and
      `(locked yes)` + `(name "...")` round-trip on `zone` (locked
      after `(zone` per `:2917`, name between uuid and hatch per
      `:2935-2936`).

## Phase B end-of-run state (post-Slice-38, 2026-05-09)

Oracle re-run against staged kicad-cli `76f8839fd232`:

```
files       : 73
ok          : 68
diff        :  0
emit_err    :  0
parse_err   :  0
cli_skipped :  5   <- all .kicad_wks (kicad-cli has no upgrade verb for them)
```

All actionable round-trip drift on the upstream-QA corpus is closed.
Every PCB and SCH/SYM fixture that kicad-cli can oracle now matches
byte-for-byte after parse → emit → kicad-cli upgrade. The 5 skipped
fixtures are `.kicad_wks` worksheets which kicad-cli cannot upgrade;
their residual drift is purely textual/cosmetic (legacy unquoted
forms, sparse setup blocks, scientific-notation float emit, tab
indent), with no data loss.

## Next-step options (deferred decision)

With Phase B effectively closed, three independent directions remain:

1. **Re-verify and (if confirmed) file the residual scientific-notation
   parser bug upstream.** Note: the EmptyZone scientific-notation
   truncation we kept seeing was already fixed upstream in
   `934a5bac34` (2026-02-25, Ian McInerney) — confirmed in `83f0dea3`
   / `73bf7b85`. The "fix" applied in this run was simply re-staging
   a corpus binary built from canonical source. There is NO local
   patch waiting to be upstreamed. What may still warrant a formal
   bug report is the broader scope captured in `dc21c079`
   (`docs/research/upstream-pcbnew-scientific-notation.md`),
   reproducible against upstream's own QA fixture
   `Issue23125_EmptyZone`. Re-verify against canonical-source
   kicad-cli first; if any path still mis-parses, file at
   gitlab.com/kicad/code/kicad/-/issues with the empirical scope
   table and reproducer.
2. **Re-attempt selective float formatting for `.kicad_wks`-only
   emit.** Would close the 5 cosmetic-drift worksheets at the cost
   of complexity in `format_sexp` / a per-format float emitter. Pure
   cosmetics — no test gate currently fails.
3. **Move on to Phase C.** Higher-level tooling on top of the now-
   solid round-trip foundation: variant model surfacing, consumer
   API cleanup, PCB part-2 review, higher-level transforms. This is
   where the corpus-stable parser actually pays off.

Recommended: **option 3 (Phase C)** — round-trip is now a reliable
oracle and further drift work has rapidly diminishing returns, while
higher-level tooling is gated on this baseline. Option 1 is a
parallel out-of-tree task that doesn't block kicad_monkey work and
can be done opportunistically.
