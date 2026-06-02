# Contracts

This folder stores stable, machine-readable contract files used by public
release signoff.

Current contracts:

- `interface_design_manifest.v0.json`: explicitly listed major public
  interfaces that require design-doc sections and Rack test ownership.
- `pcb_svg_enrichment_a0.schema.json`: document-level metadata embedded in
  enriched PCB SVG output.
- `svg.md`: human-readable SVG enrichment and linkage contract.

The promoted package-root API contract lives in source at
`src/py/kicad_monkey/kicad_api_contract.py` so it can be imported by tests,
CI, and downstream consumers. `L99_signoff` verifies that every promoted public
class from that contract has a design-doc section under `docs/design/api/`.

New stable JSON outputs, configuration files, corpus manifest formats, or
downstream cruncher-facing data contracts should be added here with matching
conformance tests before release.
