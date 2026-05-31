# ADR-003: Design Documentation And Test Ownership Signoff

Status: accepted
Date: 2026-05-31

## Context

`kicad-monkey` is moving from the private `toolz` workspace into a public
library package. Downstream tools, including `kicad-cruncher`, need a stable
parser/model/rendering surface with clear intent before depending on it.

The package intentionally keeps a broad package-root export surface while the
first cruncher workflows prove what should become durable public API. The
promoted public contract is the narrower, reviewable set recorded in
`kicad_monkey.kicad_api_contract`.

## Decision

Design documentation is part of release signoff.

Every promoted public class in `kicad_monkey.kicad_api_contract` must have a
machine-readable design section under `docs/design/api/*.html`:

- section attribute: `data-interface="<ClassName>"`;
- section attributes for Rack stratum, test file, and test target;
- rationale, purpose, test requirements, and working definition.

Major public interfaces that are not sufficiently described by class export
status are listed in `docs/contracts/interface_design_manifest.v0.json`. The
manifest is explicit because major-interface ownership is a design decision,
not only an AST property.

`docs/design/index.html` is the master human and machine entry point.
`docs/design/styles.css` is the shared style file. Design HTML stays simple and
easy to inspect with text tooling.

Stable machine-readable contracts that leave the package boundary belong under
`docs/contracts/` and need conformance tests before release.

Planning notes are local working artifacts, not public release artifacts. When a
plan completes, the relevant durable decisions, API intent, status, and test
ownership move into ADRs, design docs, release notes, or contracts as
appropriate. `docs/plans/` is ignored to keep future planning scratch work out
of public commits.

## Consequences

`L99_signoff` fails when promoted public classes, major interfaces, design-doc
entry points, or Rack test ownership links are missing.

The broad package-root `__all__` remains available as a provisional discovery
surface for early `kicad-cruncher` work. Moving a provisional export into the
promoted public contract requires design docs and tests in the same change.
