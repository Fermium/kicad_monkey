# Changelog

## 2026.6.10

- Fix pin-name markup rendering in symbol SVG output: `~{...}` overbar,
  `_{...}` subscript, and `^{...}` superscript are now parsed and rendered
  instead of being drawn literally (GitHub issue #1). Markup works for both
  the KiCad stroke font and TTF-faced pin fonts, with bar position, glyph
  scaling, and baseline offsets matching `kicad-cli sym export svg`.
- Align the default symbol SVG theme with KiCad CLI output (body fill,
  outline stroke widths, pin-number color). Custom theme overrides remain
  available and unchanged.
- Add stroke-font markup unit coverage, TTF-face overbar regression cases,
  and strict element-level symbol SVG parity tests against the KiCad CLI
  reference output.
- Pin the staged KiCad CLI oracle builds in `tools/kicad-cli/MANIFEST.toml`
  so test references resolve deterministically instead of by file mtime.
- Refresh the redistributable test corpus archive: add overbar markup
  fixtures (stroke and TTF variants), exclude regenerable runtime products
  (`output/`, `_stage/`, `.kicad_prl`) from packaging and hygiene checks,
  and remove editor/backup debris.

## 2026.6.3

- Publish the 2026-06-03 public package build for downstream KiCad SVG and
  design-review consumers.
- Carry forward the 2026.6.2 enriched PCB/SVG metadata and schematic instance
  API surface as the current audited `kicad-monkey` release.

## 2026.6.2

- Harden PCB SVG rendering against KiCad CLI oracle output, including custom
  pads, NPTH mask apertures, filled polygons, track arcs, stroke widths,
  render-cache fill rules, dimensions, and review-layer naming.
- Add strict PCB SVG structural-oracle tests and promote additional synthetic
  and real-world SVG parity cases.
- Add PCB SVG render profiles and enriched PCB SVG metadata for components,
  pads, vias, tracks, zones, drills, stackup, project variables, and net
  linkage.
- Add enriched schematic SVG metadata with design JSON, view-local net indexes,
  and SVG-to-net linkage for schematic review workflows.
- Normalize design and schematic hierarchy contract revisions to `a0`.
- Add the public schematic hierarchy instance API for enumerating repeated
  sheet instances, parent/child navigation, source-file usage lookup, and
  per-instance schematic IR rendering.
- Add `uv.lock` for reproducible uv-based development and CI workflows.
- Refresh README developer examples for loading designs, extracting netlists,
  rendering SVG, and mutating KiCad model objects.

## 2026.5.31

- First public release of `kicad-monkey`.
- Establish the `2026.5.31` date-versioned package baseline.
- Include the public parser/model/rendering API surface, release signoff gates,
  and redistributable KiCad corpus archive needed for initial `kicad-cruncher`
  integration work.
