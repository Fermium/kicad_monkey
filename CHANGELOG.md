# Changelog

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
