# ADR-001: Source Layout And API Conventions

## Status

Accepted

## Date

2026-03-18

## Context

`kicad-monkey` is a standalone Python package. Public release work needs a
stable source layout and an API style that downstream users can consume without
knowing the original development workspace.

## Decision

Python source lives under `src/py/kicad_monkey/`.

Package-local tests live under `tests/` and are organized by Rack stratum.

The preferred public API uses explicit facade classes and named operations:

```python
from kicad_monkey import KiCadPcb, KiCadSchematic

board = KiCadPcb.from_file("board.kicad_pcb")
schematic = KiCadSchematic.from_file("design.kicad_sch")
board.save("out.kicad_pcb")
schematic.save("out.kicad_sch")
```

Package-root exports are intentionally broad during the first public release,
but the promoted public contract is the narrower list in
`kicad_monkey.kicad_api_contract`.

## Consequences

- The package can be built, tested, and published without a monorepo path
  bootstrap.
- Public tests move with the package.
- Adding new promoted public classes requires design documentation and Rack
  test ownership.
