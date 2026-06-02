# SVG Contract

KiCad Monkey has two PCB SVG output profiles:

- `review`: enriched SVG for inspection and downstream applications
- `kicad_cli`: metadata-free SVG shaped for KiCad CLI oracle comparison

Do not use `review` SVG as the strict KiCad CLI parity artifact. Oracle tests
that compare against `kicad-cli pcb export svg` must request
`profile="kicad_cli"`.

## PCB SVG

PCB review SVG uses millimeter user coordinates. SVG ids are render-artifact
lookup keys. Downstream tools should prefer documented `data-*` attributes and
the embedded metadata payload for semantic identity.

When PCB metadata is enabled, the root SVG carries:

- `data-stage`
- `data-group-mode`
- `data-enrichment-schema`
- `data-view-kind`
- `data-profile`
- `data-source`
- `data-included-layers`

PCB primitive groups carry `data-primitive` values including:

- `track`
- `arc`
- `via`
- `via-hole`
- `zone`
- `footprint`
- `pad`
- `pad-hole`
- `graphic`
- `text`
- `dimension`

Layer metadata uses KiCad layer names directly:

- `data-layer-name` for one layer
- `data-layer-names` for multiple layers
- `data-layer-role` / `data-layer-roles` for normalized roles

Electrical and component relationships are emitted when known:

- `data-net-index`, `data-net-id`, `data-net`
- `data-net-class`, `data-net-classes`
- `data-component`, `data-component-uid`, `data-component-uuid`
- `data-footprint`
- `data-pad-designator`, `data-pad-number`
- `data-pad-type`, `data-pad-shape`

Drill geometry uses:

- `data-primitive="pad-hole"` or `data-primitive="via-hole"`
- `data-hole-owner`
- `data-hole-kind`
- `data-hole-plating`
- `data-hole-render`

## PCB Enrichment Metadata

PCB review SVG embeds document-level JSON metadata as:

```xml
<metadata id="pcb-enrichment-a0" data-schema="kicad_monkey.pcb.svg.enrichment.a0">
  ...
</metadata>
```

The schema file is `pcb_svg_enrichment_a0.schema.json`.

The payload records:

- source PCB path
- board bounding box, auxiliary origin, and thickness
- emitted view information
- layer maps and normalized layer roles
- net, netclass, and component lookup tables
- component placement summaries

## Schematic SVG

Schematic SVG uses source-owned ids as the DOM lookup surface. The semantic
relationship sidecar is the KiCad design/netlist JSON payload:

- `components[].svg_id` points to the component SVG group id
- `nets[].graphical` groups related schematic SVG ids by record type
- `nets[].graphical.pins[]` maps designator/pin pairs to SVG ids
- `nets[].endpoints[]` provides semantic trace endpoints

Downstream tools should not infer schematic connectivity from rendered text or
group nesting alone.
