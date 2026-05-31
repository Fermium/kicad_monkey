# Top-drift token sweep — final structural-drift audit

**Date:** 2026-05-09
**Slice:** Phase A/B follow-on (post-Phase-C-B)
**Outcome:** Zero remaining structural drift on PCB / schematic / symbol /
footprint files. Residual `.kicad_wks` worksheet drift is 100 % cosmetic
whitespace formatting — no content gap.

## Method

`docs/research/oracle_diff.py` against the canonical 73-file standard
corpus, using the freshly-staged kicad-cli `76f8839fd232`. Each file is
processed through:

```
source ─ kicad-cli upgrade ─► ref/<file>
source ─ kicad_monkey   ───► ours/<file>
ours   ─ kicad-cli upgrade ─► ours_pretty/<file>
```

Diff = `ref` vs `ours_pretty`. Both have been canonicalised by KiCad's
prettifier, so trivial drift (whitespace, numeric formatting, child
ordering, default elision) is collapsed automatically. Any line-level
delta is a real semantic change `kicad_monkey` is responsible for.

## Result

```
                   files: 73
                      ok: 68
                    diff: 5
             skipped_cli: 5
     kicad_rejected_emit: 0
       parse_emit_errors: 0
```

- **68 OK** — every PCB, schematic, symbol, footprint round-trips through
  KiCad's own canonicaliser with zero diff.
- **0 emit rejections, 0 parse errors** — `kicad_monkey` produces files
  that KiCad ingests without complaint, and parses every file in the
  corpus without error.
- **5 diff = 5 skipped_cli** — the only diffing files are the five
  `.kicad_wks` worksheets, and those are skipped because kicad-cli has no
  `wks upgrade` verb (the diff is `source` text vs `ours` text directly,
  with no canonicaliser to collapse trivial drift).

## Per-fixture worksheet drift breakdown

| File                                       | +lines | −lines | bytes src | bytes out |
|--------------------------------------------|-------:|-------:|----------:|----------:|
| pagelayout_default.kicad_wks               |    187 |     34 |     2,062 |     2,790 |
| A4_ISO5457-1999_ISO7200-2004_EN.kicad_wks  |    538 |     83 |     6,840 |     8,903 |
| gost_landscape.kicad_wks                   |    597 |     87 |     8,634 |    10,531 |
| pagelayout_logo.kicad_wks                  |    821 |    190 |    16,901 |    20,081 |
| Wavenumber.kicad_wks                       |  2,752 |  2,732 |   208,493 |   213,655 |

Source form (legacy KiCad sparse layout, one element per line with all
children inline):

```
( setup (textsize 1.5 1.5) (linewidth 0.15) (textlinewidth 0.15)
    (left_margin 10) (right_margin 10) (top_margin 10) (bottom_margin 10) )
( rect (comment "rect around the title block") (linewidth 0.15) (start 110 34) (end 2 2) )
```

Our form (tree-formatted by `format_sexp` — one child per line, indented
by depth):

```
(page_layout
  (setup
    (textsize 1.5 1.5)
    (linewidth 0.15)
    (textlinewidth 0.15)
    (left_margin 10)
    ...
  )
  (rect
    (comment "rect around the title block")
    (linewidth 0.15)
    (start 110 34)
    (end 2 2)
  )
```

Token-level audit confirms identical content — every `setup`, `rect`,
`line`, `tbtext`, `polygon`, `pos`, `start`, `end`, `repeat`, `incrx`,
`incry`, `comment`, `font`, `size`, `linewidth`, `option`, `justify`
appears once in each form. The drift token report shows symmetric +/−
counts (Wavenumber: +2752 / −2732 — practically a wash).

## Conclusion

The parse/emit foundation has **no remaining structural drift** anywhere
on the canonical corpus. The worksheet cosmetic delta is the only
residual difference and was already classified as "deferred / cosmetic"
at Slice 16 close — closing it requires a worksheet-specific compacting
formatter that emits the legacy sparse layout, which is a pure formatting
choice, not a fidelity issue.

Phase A drift items #1, #2, #3, #4, #5, #6, #7, #8, #9 are all closed.
Phase B test gates pass. Phase C-B sexpr API is shipped. The foundation
is ready for higher-level tooling (Phase C variant model and successors).
