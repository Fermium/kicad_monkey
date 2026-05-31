# KiCad Module Architecture

**Version**: 1.1
**Last Updated**: 2026-05-31

This document defines the architectural principles and design patterns for the `tools/kicad` module. All code changes MUST adhere to these principles.

## Cross-Repo Contract Source of Truth

For shared CAD contracts (Altium + KiCad + viewers), `tools/kicad` is a consumer, not the canonical owner.

- Canonical contract root: `../wn_pcb/tools/data_models`
- Canonical PCB SVG contract location: `../wn_pcb/tools/data_models/contracts/pcb_svg`
- Canonical artifacts:
  - `SPEC.md` (human-readable vocabulary, relationships, and versioning rules)
  - `pcb_svg_enrichment_a0.schema.json` (machine-readable schema)
  - `SPEC.md` is also normative for SVG element-level `data-*` metadata semantics (not just the JSON payload schema)

Implementation notes:
- `tools/kicad` MAY keep local wrappers or fixtures for runtime convenience, but semantics MUST match the canonical contract above.
- Contract changes MUST be authored in `data_models` first, then synchronized into `tools/kicad` code/tests.
- KiCad-only docs MUST link to the canonical contract instead of redefining shared field semantics.
- Board outline/cutout feature semantics MUST be taken from canonical `SPEC.md` and not defined ad-hoc in renderer docs/tests.

## KiCad Source-Model Readiness Gate

Before Track D (`KiCad source -> generic model -> generic IPC`) becomes active
in `tools/data_models`, `tools/kicad` must pass a source-model readiness review.

This gate exists to ensure downstream converter work is built on the real
`KiCadPcb` / `KiCadFootprint` OOP surface, not on stale assumptions from the
legacy `KiCadPcbDoc` component extractor.

The active review must answer:

- does the OOP parser expose the board/file semantics required by downstream conversion?
- is the public API surface coherent enough for stable converter work?
- do current tests exercise real shared-corpus KiCad boards?
- are observed gaps parser/model gaps or converter-contract gaps?

Current review findings already require two boundary rules:

- modern KiCad boards may express connectivity with named-net tokens directly
  on pads, routes, and zones without a top-level numeric net table
- board outline carriers may live inside footprint-local `Edge.Cuts` geometry,
  not only in top-level `gr_*` graphics

The current authoritative OOP normalization for those surfaces is:

- connectivity-bearing PCB elements use the dataclass `NetRef`
  - `ordinal` is optional
  - `name` is optional
  - both may coexist and are resolved through `KiCadPcb.resolve_net_ref()`
- pad/via drill modifiers use typed dataclasses instead of ad hoc nested lists
  - `DrillProps` for `backdrill` / `tertiary_drill`
  - `PostMachiningProps` for `front_post_machining` / `back_post_machining`
  - `ZoneLayerConnections` for explicit flashed-layer overrides
- footprint pad-group metadata uses the dataclass `PadNameGroup`
  - `net_tie_pad_groups`
  - `jumper_pad_groups`
  - `duplicate_pad_numbers_are_jumpers`
- footprint placement and source-context metadata use typed dataclasses
  - `FootprintPlacement` for `path`, `sheetname`, and `sheetfile`
  - `ComponentClassRef` for `component_classes`
- KiCad 10 board-generated items are preserved as typed dataclasses
  - `Barcode` / `BarcodeMargins`
  - `GeneratedObject` / `GeneratedProperty`
- board profile discovery uses `KiCadPcb.board_outline_carriers()`
  rather than ad hoc outline scanning in each downstream consumer

Current readiness outcome:

- the KiCad source-model gate is satisfied strongly enough that future Track D
  work can target the reviewed `KiCadPcb` OOP surface directly
- the main remaining blocker is now `data_models` converter thinness, not broad
  uncertainty in the KiCad parser/model contract

The source-model review was folded into
`docs/plans/KICAD_MONKEY_REWORK_PLAN.md` and completed as part of the
2026-05-18 viz-enabling milestone.

## Design Philosophy

### Core Principles

1. **Self-Contained Module**
   - Zero external dependencies for core parsing
   - S-expression parser uses only Python stdlib
   - Module can be extracted as standalone package

2. **Parser Responsibility: Data Extraction Only**
   - Parsers extract ALL data from files without filtering
   - No business logic in parsers (e.g., BOM filtering)
   - Returns KiCad-native data structures

3. **Separation of Concerns**
   - Parsing: `kicad_pcb.py`, `kicad_footprint.py`, `kicad_sexpr.py`
   - Conversion: `data_models/converters/kicad.py` (external)
   - Rendering: `kicad_pcb_svg.py`, `kicad_footprint_svg.py`
   - Utilities: `kicad_utilities.py`, `kicad_setup.py`
   - Long-term production rendering/export should move through `data_models`
     and future shared downstream tools; KiCad-native renderers/writers are
     verification and compatibility lanes, not the strategic terminal pipeline

4. **Round-Trip Fidelity**
   - Parse -> Serialize must produce identical output
   - Preserve formatting, ordering, and whitespace where possible
   - Test with byte-for-byte comparison

5. **Source-Model Authority Before Generic Conversion**
   - The `tools/kicad` OOP model is the authoritative KiCad source boundary for
     Track D and future neutral-model conversion work
   - Significant `data_models` converter expansion must target that OOP surface
     directly
   - Local converter assumptions must be validated against the current OOP API
     and shared-corpus boards before they are treated as trusted requirements
   - Downstream code must not assume:
     - a populated top-level `pcb.nets[]` table on every modern board
     - board profile only exists in top-level `Edge.Cuts` graphics
   - Downstream code should prefer:
     - `NetRef` on pads, routes, and zones instead of tuple/int ad hoc net carriers
     - typed drill / machining / layer-override dataclasses on pads and vias
       instead of raw nested s-expression fragments
     - typed footprint pad-group carriers (`PadNameGroup`) instead of raw
       comma-delimited strings or nested token lists
     - `KiCadPcb.board_outline_carriers()` and `Footprint.outline_items()`
       instead of rediscovering outline semantics in each consumer

## Official Upstream Baseline Policy

KiCad format/readiness claims must be tied to explicit official upstream
baselines, not only to local feature branches.

At minimum, the active review should identify:

- an official release-line reference
- an official upstream development reference

## Module Structure

```
tools/kicad/
├── ARCHITECTURE.md          # This file
├── REQUIREMENTS.md          # Formal requirements (REQ-KICAD-XXX)
├── README.md                # Quick start and status
│
├── Core Parsing
│   ├── kicad_sexpr.py       # S-expression parser/builder (zero deps)
│   ├── kicad_pcb.py         # KiCadPcb OOP parser
│   ├── kicad_pcb_parser.py  # Legacy parser-equivalency harness
│   └── kicad_footprint.py   # KiCadFootprint parser
│
├── OOP Element Classes
│   ├── kicad_pcb_base.py    # Base classes
│   ├── kicad_pcb_footprint.py  # Footprint, Pad, FpText, etc.
│   ├── kicad_pcb_routing.py    # Segment, Via, Arc
│   ├── kicad_pcb_graphics.py   # GrText, GrLine, GrRect, etc.
│   ├── kicad_pcb_zone.py       # Zone
│   └── kicad_pcb_other.py      # Layer, Net
│
├── SVG Rendering
│   ├── kicad_pcb_svg.py        # Board SVG renderer
│   ├── kicad_footprint_svg.py  # Footprint SVG renderer
│   ├── kicad_stroke_font.py    # Hershey stroke font
│   └── kicad_text.py           # FreeType/HarfBuzz text
│
├── Symbol Operations
│   ├── kicad_symbol_extractor.py
│   ├── kicad_symbol_splitter.py
│   └── kicad_symbol_merger.py
│
├── Utilities
│   ├── kicad_utilities.py   # Project parsing, HTTP lib generation
│   ├── kicad_setup.py       # KiCad preferences setup
│   └── kicad_geometry.py    # Geometry utilities
│
└── tests/
    ├── conftest.py
    ├── test_*.py            # 14+ test files
    └── test_cases/          # Test data
        ├── svg/board/
        ├── svg/footprints/
        └── project/
```

## Data Flow

### PCB Parsing Flow

```
.kicad_pcb file
  -> kicad_sexpr.py parse_sexp()
  -> kicad_pcb.py KiCadPcb OOP model
  -> data_models.converters.kicad
       pcb_component_from_kicad_footprint()
       pcb_components_from_kicad_pcb()
  -> PcbComponent / Pcb
```

`kicad_pcb_parser.py` and `KiCadPcbDoc` are legacy parser-equivalency surfaces
only. They must not be used for new application code or generic model
conversion.

### Component Extraction

Conversion from typed KiCad OOP objects to `PcbComponent` is handled by the converter
layer in `data_models/converters/kicad.py`, consistent with Altium architecture.

**Converter Functions:**
```python
# In data_models/converters/kicad.py
def pcb_component_from_kicad_footprint(kicad_footprint: Footprint) -> PcbComponent:
    # Adds _source_cad="kicad", preserves DNP and exclude_from_bom flags

def pcb_components_from_kicad_pcb(pcb: KiCadPcb) -> list[PcbComponent]:
    # Batch conversion from the typed KiCadPcb object graph
```

Legacy `KiCadPcbComponent.to_pcb_component()`,
`KiCadPcbDoc.to_pcb_components()`, and `KiCadPCBParser.parse_file()` were
removed as conversion paths. Application code must use the typed `KiCadPcb`
surface.

## S-Expression Parser

### Design Goals

- **Zero dependencies**: Uses only Python stdlib
- **Round-trip safe**: Preserves structure for serialization
- **Fast**: Optimized for large files (100K+ lines)

### Key Classes

```python
# Marker for strings that need quoting
class QuotedString(str):
    """String that requires quotes in S-expression output."""
    pass

# Parse S-expression string to nested lists
def parse_sexp(text: str) -> list:
    """Parse KiCad S-expression format."""

# Build S-expression string from nested lists
def build_sexp(data: list) -> str:
    """Serialize to KiCad S-expression format."""

# Pretty-print S-expression
def format_sexp(text: str) -> str:
    """Format S-expression with proper indentation."""
```

### Known Issues (Historical)

**Quote Corruption Bug (Fixed 2024-11-29)**
- `format_sexp()` combined quote and space into single element
- When trailing space was removed, closing quote was lost
- Corrupted 600+ symbol files before discovery
- See README.md for details

## OOP Model Design

### Element Classes

All PCB elements follow a consistent pattern:

```python
@dataclass
class GrLine:
    """Graphical line element."""
    start: tuple[float, float]
    end: tuple[float, float]
    layer: str
    width: float = 0.1
    stroke: dict = None  # KiCad 8+ stroke styles

    @classmethod
    def from_sexp(cls, sexp: list) -> 'GrLine':
        """Parse from S-expression."""

    def to_sexp(self) -> list:
        """Serialize to S-expression."""
```

### Layer Handling

KiCad layers are strings (e.g., "F.Cu", "B.SilkS", "Edge.Cuts").

```python
# Standard layer names
COPPER_LAYERS = ["F.Cu", "B.Cu", "In1.Cu", ...]
SILK_LAYERS = ["F.SilkS", "B.SilkS"]
MASK_LAYERS = ["F.Mask", "B.Mask"]
```

## SVG Rendering

### Design Goals

- Match KiCad CLI output exactly
- 0.5mm coordinate tolerance for validation
- Support all element types (tracks, pads, zones, text, etc.)

### Test Methodology

1. Generate reference SVG using `kicad-cli`
2. Generate Python SVG using our renderer
3. Parse both SVGs, extract coordinates
4. Compare with tolerance (0.5mm)

### Current Status

| Component | Tests | Status |
|-----------|-------|--------|
| Board SVG | 663 | 100% pass |
| Footprint SVG | 108 | 100% pass |

## Testing Standards

### Test Organization

Tests are co-located with the module:

```
kicad/tests/
├── __init__.py
├── conftest.py           # Shared fixtures
├── test_sexpr.py         # S-expression tests
├── test_board_svg.py     # Board SVG tests (663)
├── test_footprint_svg.py # Footprint SVG tests (108)
├── test_roundtrip.py     # Parse-serialize round-trip
└── test_cases/
    ├── svg/board/        # Board test files
    ├── svg/footprints/   # Footprint test files
    └── project/          # Project test files
```

### Test Types

1. **Unit Tests**: Individual function/method testing
2. **Round-Trip Tests**: Parse -> Serialize -> Parse
3. **SVG Comparison Tests**: Compare against KiCad CLI output
4. **Integration Tests**: Full workflow testing

### Running Tests

```bash
# All KiCad tests
uv run pytest tools/kicad/tests/ -v

# Specific test file
uv run pytest tools/kicad/tests/test_board_svg.py -v

# Pattern matching
uv run pytest tools/kicad/tests/ -k "roundtrip" -v
```

## Dependencies

### Internal (Required)

- `data_models`: `PcbComponent`, `Coordinate2D`, `Assembly`

### External (Optional)

- `freetype-py`: For TrueType font rendering (optional)
- `uharfbuzz`: For text shaping (optional)

### Explicitly NOT Used

- No `sexpdata` - custom parser is faster and round-trip safe
- No `pykicad` - we need full control for round-trip fidelity

## Future Considerations

### Schematic Parsing

KiCad schematics (`.kicad_sch`) use the same S-expression format.
Parser could be extended following the same patterns.

### KiCad 9 Compatibility

Monitor for format changes in KiCad 9 release.
S-expression format is generally stable but new elements may be added.

## References

- KiCad File Formats: https://dev-docs.kicad.org/en/file-formats/
- KiCad Source (S-expr): https://gitlab.com/kicad/code/kicad/-/tree/master/common/
- This module README: `tools/kicad/README.md`
