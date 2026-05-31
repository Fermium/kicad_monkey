# kicad_monkey drift inventory — Phase A complete

Source: `oracle_diff.py` against the OneDrive corpus (73 fixtures), using
the freshly-staged `kicad-cli` at commit `99c64afbf83f` (matches the
upstream_qa fixture commit, supports format `20260326`).

Report: `oracle_diff_report.json` (regenerated 2026-05-08).

## Headline numbers

| metric | count |
| --- | ---: |
| files | 73 |
| OK (zero diff after pretty) | 3 |
| DIFF (loads cleanly both sides, content drift) | 7 |
| EMIT (ours rejected by KiCad) | 59 |
| SKIP (no kicad-cli verb for kind) | 4 |
| `.kicad_wks` (no upgrade verb at all) | 5 |

By file kind (emit-rejected / total):

| kind | rejected | total | rate |
| --- | ---: | ---: | --- |
| `.kicad_sym` | 37 | 37 | 100 % |
| `.kicad_sch` | 14 | 16 | 87 % |
| `.kicad_pcb` | 4 | 15 | 27 % |
| `.kicad_wks` | n/a | 5 | (cli has no `wks upgrade`) |

The two `.kicad_sch` files that load both sides are
`groups_load_save.kicad_sch` (no embedded properties / pins; only
top-level groups + rectangles) and `variants.kicad_pcb` (PCB sibling
under the same fixture dir). All 11 PCB files that pass loading still
have small content diffs.

## Root causes

Numbered to match `kicad_monkey.md`. Each cause names the smallest
reproducer in the corpus that exhibits only this cause cleanly.

### #1 — `(at X Y)` 2-tuple where KiCad now requires 3-tuple `(at X Y angle)`

**Severity:** parser-fatal — alone responsible for nearly all sym/sch
emit rejections.

Pattern (every site):

```python
if self.at_angle != 0:
    result.append(['at', self.at_x, self.at_y, self.at_angle])
else:
    result.append(['at', self.at_x, self.at_y])  # ← KiCad rejects
```

KiCad's reader for `property`, `pin`, `text`, `label`, `sheet`,
`fp_text`, etc. requires the angle slot even when zero. Surgically
patching `(at X Y)` → `(at X Y 0)` in `flat_hierarchy.kicad_sch` and
`C_2P_NP.kicad_sym` makes them load.

Fix sites (must always emit 3-tuple, including angle 0):

| file | line(s) | context |
| --- | --- | --- |
| `kicad_property.py` | 120-126 | footprint Property |
| `kicad_sym_property.py` | 94-97 | symbol library Property |
| `kicad_sch_symbol.py` | 218-222 | placed schematic Symbol |
| `kicad_sch_sheet.py` | 76-80, 139-143 | Sheet, SheetPin |
| `kicad_sch_label.py` | 69-73, 160-164, 243-247, 314-318 | Label / GlobalLabel / HierarchicalLabel / NetClassFlag |
| `kicad_sym_text.py` | 55-59 | symbol library text |
| `kicad_sym_text_box.py` | 69-73 | symbol library text_box |
| `kicad_sym_pin.py` | 131-133 | symbol library pin |
| `kicad_pad.py` | 674-678 | footprint pad |
| `kicad_fp_text.py` | 127-131 | footprint fp_text |
| `kicad_pcb_footprint.py` | 247-251 | placed footprint |
| `kicad_pcb_graphics.py` | 71-75 | pcb graphics text |
| `kicad_pcb_gr_text.py` | 238-242 | pcb gr_text |

Sites that legitimately emit 2-tuple (positions without rotation — DO
NOT change): `kicad_sch_no_connect.py:48`, `kicad_sch_wire.py:172`,
`kicad_sch_junction.py:68`, `kicad_sch_sheet.py:272`,
`kicad_pcb_other.py:1043`, `kicad_pcb_routing.py:228`.

### #2 — Empty `(lib_symbols)` block dropped on emit

**Severity:** data-loss, not parser-fatal.

`kicad_schematic.py:319-324` only emits when `self.lib_symbols` is
non-empty. KiCad always emits the empty form `(lib_symbols)`.

### #3 — Per-sheet `(instances ...)` sub-block never parsed/emitted

**Severity:** data-loss.

`kicad_sch_sheet.py` contains zero references to `instances`. KiCad
emits `(instances (project "<name>" (path "/<uuid>" (page "N"))))`
inside each `(sheet ...)`. Round-tripping a hierarchical schematic
loses per-instance page numbers.

### #4 — PCB pad-tenting block format (v20260101)

**Severity:** parser-fatal on the affected fixtures.

KiCad v20260101 split the legacy single-line `(tenting front back)`
into separate multi-block forms:

```
(tenting   (front yes) (back yes))
(covering  (front no)  (back no))
(plugging  (front no)  (back no))
(capping no)
(filling no)
```

Our emit still produces the legacy single-line form, which the new
parser rejects. Reproducer: `LayerWildcard.kicad_pcb` (80-line diff,
isolates this issue plus #5/#6).

Likely site: PCB setup-block emitter for solder-mask / drill plating
fields. Needs both the parser to accept the new multi-block forms and
the emitter to round-trip them.

### #5 — Hardcoded `version` / `generator_version` on PCB emit

**Severity:** data-loss; combined with #4 it is also parser-fatal
(version stamp lies about the format).

For every PCB emit-rejected file, the diff shows:

```
-(version 20260101)
+(version 20241229)
-(generator_version "10.99")
+(generator_version "9.0")
```

We are not preserving the source's version stamp on round-trip; we
emit a constant. Investigate `kicad_pcb.py` / wherever the top-level
`(kicad_pcb (version ...) (generator ...) (generator_version ...))`
header is built.

(Schematic emitters appear to do the right thing — no `version`/
`generator_version` differences in the sch diffs.)

### #6 — PCB plot-params drift (HPGL fields, `plotinvisibletext`)

**Severity:** content drift; possibly parser-fatal in combination with
#5 if the new format spec drops these fields.

Ours emits:
```
(hpglpennumber 1)
(hpglpenspeed 20)
(hpglpendiameter 15)
(plotinvisibletext no)
```

…that the v20260101 source omits. Either (a) we emit defaults that the
new format elides, or (b) v20260101 dropped these fields outright and
KiCad refuses files that still carry them. Fixture: same as #4.

### #7 — Symbol-library files: bulk content lost on emit

**Severity:** data-loss + parser-fatal.

For every `.kicad_sym` fixture, ours_pretty is dramatically smaller
than the canonical reference (e.g. `C_2P_NP.kicad_sym`: 22 lines vs
183). Even after the canonical pass, almost the entire body is
missing.

This is consistent with #1 (the first emit failure aborts the
canonicalisation early) — but the symbol path may also have an
independent emitter that's silently dropping properties / pins. Worth
inspecting after #1 lands; many of the sym fixtures should resolve to
DIFF rather than EMIT once the `at` 3-tuple is fixed.

### Minor: top-token drift buckets remaining (post-#1 hypothesis)

From the new oracle summary, the largest residual drift token counts
are:

```
<other> 662k, effects 158k, font 158k, size 158k, at 94k, pin 69k,
name 66k, length 65k, number 65k, property 49k, alternate 43k,
type 41k, show_name 25k, do_not_autoplace 25k, stroke 22k, hide 21k,
width 21k, fill 19k, start 17k, end 17k
```

These come from files where ours fails to canonicalise; after #1 lands
the same buckets should narrow significantly. The persistent ones to
re-evaluate then are `effects/font/size` (likely default elision
mismatch on text effects) and `alternate/show_name/do_not_autoplace`
(symbol property attributes).

## Phase B plan (test-first, comprehensive)

The user direction is **comprehensive fix, not one bug at a time.** The
proposed order:

1. **Tests first.** Add a regression case under `toolz-tests/suites/
   kicad_monkey/` with one minimal-reproducer fixture per root cause
   that asserts `kicad-cli * upgrade --force` exits 0 on the emitted
   file. The smallest ones are: `groups_load_save.kicad_sch` (already
   passes — guard rail), `flat_hierarchy.kicad_sch` (#1), `C_2P_NP.
   kicad_sym` (#1 + #7), `LayerWildcard.kicad_pcb` (#4 + #5 + #6).
2. **Land #1** as one mechanical change touching the 13 emit sites
   listed above.
3. **Land #2 / #3** in `kicad_schematic.py` and `kicad_sch_sheet.py`.
4. **Land #5** (preserve PCB `version`/`generator_version` on parse).
5. **Land #4** (PCB tenting multi-block parse + emit).
6. **Re-run oracle.** Expect `EMIT → DIFF` for the bulk of fixtures.
7. **Triage residual DIFF buckets** (#6, top-token list) one cause at
   a time.

Step 1 is the only one that can land on `main` independently of the
others; 2-5 should ship together in one branch since they share the
oracle harness as their gate.

## Erratum (2026-05-08): root cause #9 — Zone `(layers ...)` plural form

The original #4/#5/#6 hypothesis for **`LayerWildcard.kicad_pcb`** /
**`LayerEnumerate.kicad_pcb`** (PCB tenting multi-block, hardcoded
version, plot-params drift) turned out to be **wrong**. The actual
cause — and a kicad-cli **segfault** (rc `0xC0000005`), not a soft
rejection — is in `kicad_pcb_zone.py::Zone`:

1. **Singular vs plural layer assignment.** KiCad zones can carry their
   layers as either `(layer "X")` (single) or `(layers "A" "B" ...)`
   (multi-layer / wildcard, e.g. `"*.Cu"`). Our parser only read the
   singular form, so multi-layer / wildcard zones came back with an
   empty `layer` field, and we emitted `(layer "")` — kicad-cli
   segfaults on a zone with no valid layer.
2. **Empty `(net_name "")` round-trip.** Our emit had
   `if self.has_explicit_net_name and self.net.name:` — too strict; it
   dropped the empty form on round-trip.
3. **`(island_removal_mode N)` and `(island_area_min N)` in `(fill ...)`.**
   Never parsed or emitted. Data-loss on the affected fixtures.
4. **`(island)` flag in `(filled_polygon ...)`.** `(island)` parses as
   a sub-list `["island"]` (not a bare token), so `has_flag()` was
   missing it, and emit produced a bare `island` token after the
   `(layer ...)` sub-list — malformed and round-trip-unstable.

Fix: rework `Zone` with `layers: List[str]` + `layers_plural: bool`
preserving the source form on round-trip, add `island_removal_mode` /
`island_area_min` fields, fix the `(net_name "")` emit condition, fix
`FilledPolygon.island` parse via `find_element` and emit `(island)` as
a single-element sub-list.

Result: `LayerWildcard.kicad_pcb` and `LayerEnumerate.kicad_pcb` flip
from EMIT-rejected to OK. After this and the #8 fix, the remaining 4
EMIT-rejected fixtures are all upstream_qa **negative** fixtures
(intentionally bad input — `api_kitchen_sink` ×2, `corrupted_stackup`,
`ScientificNotation`); zero actionable emit rejections remain on the
73-file corpus.

## Erratum (2026-05-08): root cause #8 — `(generated)` `(id ...)` ordering

While bisecting the post-#1 PCB residue, the original #4/#5/#6
hypotheses for `tuning_generators_load_save.kicad_pcb` turned out to
be **wrong**. The actual bug — and the one causing kicad-cli to
**segfault** (rc `0xC0000005`) rather than just reject — is in the
`(generated ...)` block emit, in `kicad_pcb_other.py::GeneratedObject`:

1. **Wrong identifier token.** KiCad uses `(id <bare-uuid>)` as the
   FIRST child of `(generated ...)`, not `(uuid "...")`. Our parser
   was reading `(uuid ...)` (always missed) and our emitter never
   produced any identifier — `(id ...)` fell into the generic
   `properties` bucket and was emitted *after* `(type)/(name)/(layer)`.
2. **Order-sensitive segfault.** kicad-cli does not gracefully reject
   misordered children — it crashes. Moving `(id ...)` to the first
   position is sufficient to flip the fixture from segfault to OK.
3. **Cosmetic: `(members ...)` quoting.** Source uses bare uuid tokens;
   we wrapped them in `QuotedString`. Quoting alone does NOT cause the
   crash, but unquoting matches canonical form.

Fix: parse `(id ...)`, add `id` to `known_elements`, emit `(id ...)`
first (no quotes), emit members as bare tokens.

Result: `tuning_generators_load_save.kicad_pcb` and
`tuning_generators_load_save_v20231212.kicad_pcb` flip from
EMIT-rejected to **OK** (zero diff after canonicalisation).

Remaining 6 emit-rejected fixtures:
- 4 "negative" upstream_qa fixtures (`api_kitchen_sink` ×2,
  `corrupted_stackup`, `ScientificNotation`) — source itself unloadable.
  **Erratum (2026-05-09):** this "source itself unloadable" diagnosis
  was largely wrong. 3 of these (`ScientificNotation`,
  `corrupted_stackup`, `api_kitchen_sink.kicad_pcb`) became OK once we
  re-staged kicad-cli `76f8839fd232` from canonical source — the
  prior staged binary came from kicad-win-builder and predated
  `934a5bac34` (FROM_CHARS_FLAGS). `api_kitchen_sink.kicad_sch` was a
  real kicad_monkey emit drift (closed in Slice 33). See
  `2026-05-08-kicad-pcb-scientific-notation-bug.md`.
- 2 LayerEnumerate / LayerWildcard PCB fixtures — actually have zone
  / version / plot-params drift consistent with #4/#5/#6.

## Post-#1 status (2026-05-08, after fix landed)

Fix applied: 12 emit-site files (16 sites) collapsed `if angle != 0`
branch into a single `(at X Y angle)` 3-tuple emit. `kicad_sym_pin.py`
already did this; six legitimate 2-tuple positional sites were left
alone.

Re-running the oracle gives:

| metric | before | after |
| ---: | ---: | ---: |
| ok | 3 | 3 |
| diff (load both, drift) | 7 | 62 |
| emit-rejected (we wrote what KiCad rejects) | 59 | 8 |
| `<other>` token diff | 662k | 41k |

The remaining 8 emit-rejections fall into two clean buckets:

- **4 PCB v20260101 fixtures** still tied to **#4 / #5 / #6**:
  `LayerEnumerate.kicad_pcb`, `LayerWildcard.kicad_pcb`,
  `tuning_generators_load_save.kicad_pcb` (×2 versions).
- **4 upstream_qa "negative" fixtures** where the *source itself* won't
  load (api_kitchen_sink schematic + pcb, corrupted_stackup,
  ScientificNotation). These appear to be intentional bad-input
  fixtures from upstream qa; not our bug.
  > **Erratum (2026-05-09):** the "intentional bad-input" framing was
  > wrong. 3 of these were artifacts of a stale staged kicad-cli built
  > by kicad-win-builder against a pre-`934a5bac34` source clone. After
  > re-staging from canonical source, `ScientificNotation`,
  > `corrupted_stackup`, and `api_kitchen_sink.kicad_pcb` all load
  > cleanly. `api_kitchen_sink.kicad_sch` was a real kicad_monkey emit
  > drift, closed in Slice 33.

So the actionable remaining surface is just **PCB pad-tenting / version
/ plot-params** (#4/#5/#6). #2 and #3 are pure data-loss buckets to
audit after the PCB work.
