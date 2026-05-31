# KiCad Design JSON Field Map

Status: active contract reference as of 2026-05-12.

This document maps the KiCad-native payloads used by `kicad_monkey` to the
current neutral design/netlist JSON bridge. The goal is practical parity for
future conversion: keep KiCad source semantics intact and make the generic
`wn.design.a0` / `wn.netlist.a0` bridge straightforward.

## Scope

- KiCad native design JSON: `kicad_monkey.design.a1`, produced by
  `KiCadDesign.to_json(include_indexes=True)`.
- KiCad native netlist JSON: produced by `KiCadDesign.to_kicad_netlist_json()`.
- Generic netlist JSON: produced by `KiCadDesign.to_netlist_json()`.
- Generic design/netlist bridge: `wn.design.a0` with embedded
  `wn.netlist.a0`.

## Mapping Principles

- Native KiCad payloads preserve KiCad-specific names, IDs, hierarchy, and
  variant details under KiCad-owned fields.
- Generic data-model payloads keep portable electrical meaning in first-class
  fields and carry source-specific details through `source`, `metadata`,
  parameters, and artifact links.
- SVG object IDs are render/source links, not the electrical source of truth.
  Nets and terminals remain authoritative for connectivity.
- Indexes are lookup accelerators for viewers and tests. The component, net,
  variant, and hierarchy arrays are the canonical payload data.

## Top-Level Design Payload

| KiCad `kicad_monkey.design.a1` | Portable design concept | Generic `wn.design.a0` mapping |
|---|---|---|
| `schema` | `schema` | `source.source_schema`, `metadata.source_schema` |
| `generator` | `generator` | `source.generator`, `netlist.source.generator` |
| `project` | `project` | `source.project`, `netlist.source.project` |
| `options` | `options` | Native only for now |
| `sheets` | `sheets` | `metadata.sheet_count`, `netlist.metadata.sheet_count` |
| `components` | `components` | `netlist.components` |
| `nets` | `nets` | `netlist.nets` |
| `net_classes` | `net_classes` | `netlist.net_classes` |
| `net_name_to_classes` | `net_name_to_classes` | `DesignNet.net_class`, `DesignNetClass.nets` |
| `variants` | `variants` | `Design.variants`, `metadata.kicad_project_variants` |
| `schematic_hierarchy` | `schematic_hierarchy` | `metadata.kicad_schematic_hierarchy` |
| `pnp` | PnP/BOM side data | Native only for now |
| `indexes` | `indexes` / enrichment lookups | Native only; represented generically through artifact links |

## Components

| KiCad component field | Portable concept | Generic mapping |
|---|---|---|
| `designator` | `designator` | `DesignComponent.designator` |
| `svg_id` | `svg_id` | `DesignComponent.links[]` as `sch-svg` / `component` |
| `value` | `value` | `DesignComponent.value` |
| `footprint` | `footprint` | `DesignComponent.footprint` |
| `description` | `description` | `DesignComponent.description` |
| `library_ref` | library/source fields | `DesignComponent.parameters` as KiCad source metadata |
| `hierarchy` | hierarchy/source paths | KiCad-native field; portable hierarchy is top-level metadata |
| `classification` | component classification metadata | `DesignComponent.parameters` until a generic classification model exists |
| `parameters` | `parameters` | `DesignComponent.parameters` |

Component pin references are created from net terminals and graphical pin refs.
`terminals[].designator` and `terminals[].pin` create
`DesignComponentPin.number`, `DesignComponentPin.name`, `DesignComponentPin.net`,
and `DesignNet.connections`.

## Nets

| KiCad net field | Portable concept | Generic mapping |
|---|---|---|
| `name` | `name` | `DesignNet.name` |
| `aliases` | `aliases` | `DesignNet.aliases` |
| `terminals` | `terminals` | `DesignNet.connections`, component pins |
| `graphical.wires` | `graphical.wires` | `DesignNet.links[]` role `wire` |
| `graphical.junctions` | `graphical.junctions` | `DesignNet.links[]` role `junction` |
| `graphical.labels` | `graphical.labels` | `DesignNet.links[]` role `label` |
| `graphical.power_ports` | `graphical.power_ports` | `DesignNet.links[]` role `power-port` |
| `graphical.ports` | `graphical.ports` | `DesignNet.links[]` role `port` |
| `graphical.sheet_entries` | `graphical.sheet_entries` | `DesignNet.links[]` role `sheet-entry` |
| `graphical.pins` | `graphical.pins` | `DesignNet.links[]` and `DesignComponentPin.links[]` role `pin` |
| `net_class` / `net_name_to_classes` | `net_name_to_classes` | `DesignNet.net_class`, `DesignNetClass.nets` |
| `endpoints` | `endpoints` | Native source tracing; useful fields are also represented as artifact links |
| `driver_priority`, `driver_kind`, `source_sheets` | No stable portable peer | KiCad-native only for now |

The generic converter treats `net_name_to_classes` as the primary class lookup.
`net_classes` is also imported so class descriptions and explicit memberships
are retained.

### Pin and Endpoint Identity

KiCad schematic SVG emits the placed symbol as the stable top-level SVG group
and visible pins as nested `symbol_pin` SVG groups. KiCad uses this shape:

- `graphical.pins[].svg_id`: visible pin SVG group ID when rendered; hidden or
  otherwise unrendered pins fall back to the placed symbol SVG group UUID.
- `graphical.pins[].source_pin_id`: KiCad placed-symbol pin UUID when it differs
  from `svg_id`. When the pin group itself is keyed by that UUID, `svg_id`
  already carries the source identity.
- `endpoints[].endpoint_id`: `pin:<designator>:<pin>`.
- `endpoints[].element_id`: current render target, normally the pin SVG group
  for visible pins.
- `endpoints[].object_id`: source electrical object ID; for KiCad pins this is
  the placed-symbol pin UUID when available.
- Non-pin semantic endpoints use portable role names: `power_port`, `port`,
  and `sheet_entry`.
- Non-pin `endpoints[].element_id` is the current render target
  (for example the power symbol or sheet group), while `object_id` is the
  source electrical object (for example the placed power pin or sheet pin).
- KiCad endpoint connection points use `connection_point.units =
  "kicad_sch_iu"` where one unit is 100 nm in schematic coordinates.

## Graphical Indexes

`indexes` exists for viewers, corpus audits, and manual review. Current
KiCad-owned indexes are:

- `svg_to_component`: SVG group ID to component designator.
- `component_to_nets`: component designator to connected net names.
- `net_to_components`: net name to connected component designators.
- `svg_to_net`: SVG group ID to net name.
- `net_to_graphics`: net name to related schematic SVG group IDs.

The generic model does not copy these maps verbatim. It preserves the useful
cross-references as `DesignArtifactLink` entries on components, nets, and pins.
When KiCad pin refs carry a distinct `source_pin_id`, the generic converter
stores it in pin-link metadata while `element_id` remains the current render
target.
For non-pin endpoints, the generic converter merges endpoint metadata onto the
matching net artifact links so source object IDs and connection points survive
conversion to `wn.design.a0`.

## Variants

| KiCad variant field | Portable concept | Generic mapping |
|---|---|---|
| `name` | `name` | `DesignVariant.name` |
| `dnp` | `dnp` | `DesignVariant.dnp` |
| `parameter_overrides` | `parameter_overrides` | `DesignVariant.parameter_overrides` |
| KiCad schematic/PCB effective overrides | variation rows | Native entries plus generic overrides where portable |
| `kicad_project_variant` | project variant metadata | `Design.metadata.kicad_project_variants[]` |

The generic `DesignVariant` remains intentionally small. KiCad-native project
variant catalog data is preserved in design metadata so it is not lost during
future conversion to richer generic variant models.

## Hierarchy

KiCad hierarchy is exported in `schematic_hierarchy` with KiCad sheet/document
semantics. The generic converter stores it at
`Design.metadata.kicad_schematic_hierarchy` while keeping the source-specific
namespace distinct.

## Netlist Payloads

- `KiCadDesign.to_kicad_netlist_json()` is the native KiCad netlist view and is
  the JSON peer of the KiCad S-expression netlist export.
- `KiCadDesign.to_netlist_json()` is the generic `netlist_a0` bridge for
  downstream logical consumers.
- `KiCadDesign.to_json(include_indexes=True)` embeds logical net data in the
  design JSON shape so downstream converters can map it into `wn.design.a0` /
  `wn.netlist.a0`.

Native raw netlist JSON (`kicad_monkey.netlist.a1`) uses `components`, `nets`,
`terminals`, `graphical`, `aliases`, and `endpoints`. KiCad adds `net_classes`
and `design` metadata so the JSON remains a useful peer of the KiCad
S-expression export without dropping project/class context.

## Current Test Locks

- `tests/L3_rendering/test_L3_013_design_json_contract.py` locks real fixture
  design JSON shape and generic conversion availability.
- `tests/L0_foundation/test_L0_029_design_netlist_api.py` locks KiCad pin and
  non-pin endpoint ID/object/render-target semantics.
- `tests/L0_foundation/test_L0_024_netlist_single_sheet.py` and
  `tests/L0_foundation/test_L0_025_netlist_multi_sheet.py` lock compiler
  endpoint materialization for power ports, hierarchical ports, and sheet
  entries.
