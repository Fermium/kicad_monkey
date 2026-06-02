# SVG Enrichment Contract Plan

Date: 2026-06-02
Status: In progress
Owner: kicad_monkey rendering/API cleanup

## Context

`kicad_cruncher pcb_svg` needs SVG output that can be inspected as a drawing
and queried as a semantic scene. Altium Monkey already solves this with two
layers:

- element-level `data-*` attributes on PCB SVG primitives
- an embedded document-level JSON lookup payload

KiCad Monkey should follow that shape closely, but use KiCad-native schema ids,
field names, units, and source concepts. This enriched output is for review and
application workflows. It must not be used by strict KiCad CLI oracle lanes.
`profile="oracle"` remains metadata-free. `profile="enriched"` is the
metadata-bearing application/review profile.

## Contract Targets

PCB enriched SVG:

- root SVG attributes identify the enrichment schema, view kind, source file,
  included layers, and rendering profile
- record and block groups expose `data-primitive`
- layer metadata uses KiCad layer names directly, plus a normalized role
- routed items expose `data-net-id`, `data-net`, and project netclass data when
  available
- footprints expose `data-component`, `data-component-uuid`, and footprint
  library link
- pads expose `data-pad-number`, `data-pad-type`, `data-pad-shape`, component
  linkage, and net linkage
- drill geometry exposes `data-primitive="pad-hole"` or
  `data-primitive="via-hole"` with owner, round/slot geometry, plating, and
  dimension metadata
- vias expose `data-via-type`, drill/size metadata, and KiCad IPC-4761-style
  fabrication settings when present

PCB document payload:

- schema id: `kicad_monkey.pcb.svg.enrichment.a0`
- metadata element id: `pcb-enrichment-a0`
- payload includes `schema`, `source`, `board`, `view`, `layers`, `lookup`,
  and `components`
- `board.stackup` carries KiCad stackup details for downstream colorization and
  fabrication-aware views
- coordinates are KiCad-native millimeters unless the field explicitly says
  otherwise

Schematic review SVG and design JSON:

- schematic SVG keeps source-owned ids as the DOM lookup surface
- design/netlist JSON remains the semantic sidecar
- components expose `svg_id`
- nets expose `graphical` SVG ids and semantic `endpoints`
- contract docs state that downstream tools should not infer connectivity from
  rendered text or group nesting

## Implementation Slices

1. Add PCB enrichment docs and schema under `docs/contracts`.
2. Emit PCB record-level metadata for tracks, arcs, vias, zones, graphics,
   text, dimensions, and footprints.
3. Add pad-level block groups inside PCB footprint records so pads and pad
   holes have their own SVG metadata.
4. Embed PCB document metadata payload and root attributes for enriched output
   only.
5. Add focused L0 conformance tests for:
   - `profile="oracle"` suppressing all enrichment
   - routed track/via net attributes
   - footprint/pad/pad-hole component and net attributes
   - metadata payload schema identity and lookup fields
   - stackup payload
   - round/slot hole metadata
   - via fabrication metadata
6. Add schematic contract docs and L0/L3 checks proving existing
   `components[].svg_id`, `nets[].graphical`, and `nets[].endpoints` remain
   aligned with rendered SVG ids.
7. Run focused SVG tests, L0 foundation, pyright/ruff slices, then commit.

## Notes

The first PCB pass should prefer stable semantic attributes over promising
globally stable DOM ids. Like Altium Monkey, SVG `id` values are render-artifact
lookup keys; downstream tools should use documented `data-*` fields and the
metadata payload for semantic identity.

## Progress Log

- 2026-06-02: Landed initial PCB SVG enrichment in `a3bf767`. Added
  `kicad_monkey.pcb.svg.enrichment.a0`, root SVG attrs, embedded payload,
  record-level track/via/zone/footprint attrs, pad/pad-hole block attrs, and
  focused L0 tests.
- 2026-06-02: Added schematic sidecar linkage coverage proving design JSON
  `components[].svg_id`, `nets[].graphical`, pin refs, and endpoint
  `element_id` values resolve to rendered SVG ids.
- 2026-06-02: Renamed public PCB SVG profiles to `enriched` and `oracle`.
  Added round/slot drill metadata, `plated`/`non_plated` hole plating,
  separate `data-via-type`, IPC-4761-style via fabrication attributes, and
  `board.stackup` in the enrichment payload/schema. Added focused L0 coverage
  plus a Speedy real-world guard for filled/capped 0.15 mm vias.
