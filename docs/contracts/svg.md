# SVG Contract

KiCad Monkey has two PCB SVG output profiles:

- `enriched`: source-aware SVG for inspection and downstream applications
- `oracle`: metadata-free SVG shaped for KiCad CLI oracle comparison

Do not use `enriched` SVG as the strict KiCad CLI parity artifact. Oracle tests
that compare against `kicad-cli pcb export svg` must request
`profile="oracle"`.

## PCB SVG

PCB enriched SVG uses millimeter user coordinates. SVG ids are render-artifact
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

The embedded PCB metadata also records imported/user layer aliases. Use
`layers.layers[].display_name` or `layers.layer_name_to_display_name` for UI
labels, and `layers.layer_name_to_user_name` when the original KiCad user alias
must be distinguished from the canonical layer name.

Electrical and component relationships are emitted when known:

- `data-net-index`, `data-net-id`, `data-net`
- `data-net-class`, `data-net-classes`
- `data-component`, `data-component-uid`, `data-component-uuid`
- `data-footprint`
- `data-pad-designator`, `data-pad-number`
- `data-pad-type`, `data-pad-shape`

Footprint child metadata is emitted for enriched SVG only:

- `data-ref="property"` with `data-footprint-text-role` of `designator`,
  `value`, or `property`
- `data-ref="fp_text"` / `data-ref="fp_text_box"` with
  `data-footprint-text-role="user"` when applicable
- `data-ref="fp_line"`, `fp_arc`, `fp_circle`, `fp_rect`, or `fp_poly` with
  `data-primitive="footprint-graphic"`
- `data-footprint-primitive` and `data-footprint-graphic-kind` identify the
  source footprint item class

Drill geometry uses:

- `data-primitive="pad-hole"` or `data-primitive="via-hole"`
- `data-hole-owner`
- `data-hole-kind`: `round` or `slot`
- `data-hole-plating`: `plated`, `non_plated`, or `unknown`
- `data-hole-render`
- `data-hole-diameter-mm` for round holes
- `data-hole-width-mm` / `data-hole-height-mm` for slot holes

Via metadata uses:

- `data-via-type`: `through`, `blind`, `buried`, or `micro`
- `data-via-drill-mm`
- `data-via-size-mm`
- `data-ipc4761-*` attributes for KiCad via fabrication settings when present,
  including tenting, covering, plugging, capping, and filling

## PCB Enrichment Metadata

PCB enriched SVG embeds document-level JSON metadata as:

```xml
<metadata id="pcb-enrichment-a0" data-schema="kicad_monkey.pcb.svg.enrichment.a0">
  ...
</metadata>
```

The schema file is `pcb_svg_enrichment_a0.schema.json`.

The payload records:

- source PCB path
- project-level text variables
- board bounding box, auxiliary origin, thickness, and stackup
- emitted view information
- layer maps, user aliases, display names, and normalized layer roles
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
