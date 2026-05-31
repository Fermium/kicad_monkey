# KiCad Monkey

            ▓▓▓▓▓▓▓▓▓▓
          ▓▓▓▓▓▓▓▓▓▓▓▓▓▓
        ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
      ▓▓▓▓░░░░░░▓▓░░░░░░▓▓▓▓
  ░░░░▓▓░░░░░░░░░░░░░░░░░░▓▓░░░░
  ░░░░▓▓░░    ░░░░░░    ░░▓▓░░░░
    ░░▓▓░░  ██░░░░░░  ██░░▓▓░░
      ▓▓░░░░░░░░░░░░░░░░░░▓▓
        ▓▓░░░░░░░░░░░░░░▓▓
          ▓▓▓▓░░░░░░▓▓▓▓
  ░░          ▓▓▓▓▓▓
    ▓▓      ▓▓▓▓▓▓▓▓▓▓
    ▓▓▓▓    ▓▓▓▓▓▓▓▓▓▓
      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
          ▓▓▓▓░░▓▓░░▓▓▓▓

`kicad_monkey` is a focused Python package for KiCad source-file parsing,
round-trip modeling, close-to-format utilities, and IR-backed 2D rendering.

Current scope:

- KiCad S-expression parsing helpers
- schematic, symbol-library, PCB, footprint, project, and design OOP facades
- property cleanup and model mutation helpers
- netlist and connectivity utilities
- plotter-style IR and SVG rendering entrypoints

Larger workflow commands and heavier application orchestration should live in
downstream packages such as `kicad-cruncher`.

## Install

For library use inside an existing Python environment:

```powershell
pip install kicad-monkey
```

For development:

```powershell
git clone https://github.com/wavenumber-eng/kicad_monkey.git
cd kicad_monkey
uv sync --extra test
```

## Testing

Rack is the primary public gate:

```powershell
uv run --extra test python tests/rack.py run L0_foundation
uv run --extra test python tests/rack.py run L99_signoff
```

`L99_signoff` checks release metadata, changelog coverage, public API contract
resolution, API design-doc ownership, Rack test ownership, corpus archive
hygiene, and the current ruff/pyright ratchet state.

The redistributable KiCad corpus is transported as `tests/corpus/kicad.zip`.
The loose mirror is ignored locally; test helpers extract it on demand when no
external corpus is configured.

## API Shape

The promoted package-root API is recorded in
`kicad_monkey.kicad_api_contract`. The broad package `__all__` remains a
provisional discovery surface while `kicad-cruncher` integration proves which
symbols should graduate into the durable public contract.

The public OOP facade groups and supporting public classes are documented under
[docs/design/api](docs/design/api). L99 fails when a promoted public class or
major interface is missing design documentation or Rack test ownership.

Typical entrypoints:

```python
from kicad_monkey import KiCadDesign, KiCadPcb, KiCadSchematic

schematic = KiCadSchematic.from_file("design.kicad_sch")
board = KiCadPcb.from_file("board.kicad_pcb")
design = KiCadDesign.from_project_file("project.kicad_pro")
```

SVG generation goes through the IR-backed rendering path.

## Fixture Model

Public fixtures should be redistributable and package-local when possible.
Broader fixture families should use this shape:

- `input/`
- `reference_output/`
- `output/`

`output/` is transient and should stay local or temporary.

## Documentation

- [Architecture Decision Records](docs/adrs)
- [Design Notes](docs/design)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT.
