# KiCad Rack Migration Plan

**Version**: 1.0
**Date**: 2026-01-17
**Status**: Planning

---

## Overview

This document outlines the migration of KiCad module tests from a flat pytest structure to the Rack test framework architecture. Rack provides strata-based test organization, structured reporting, and cross-language portability.

---

## Strata Structure

```
L0_foundation     - S-expression parser & core data structures
L1_parsing        - OOP model parsing + round-trip (proves data models work)
L2_tools          - Lower-level tools (split, merge, filters, file fixes)
L3_rendering      - SVG rendering (validated against kicad-cli)
L4_applications   - High-level tooling (kicad_cruncher, day-to-day workflows)
```

---

## L0_foundation - S-Expression & Core Data

**Purpose**: Test the foundational parsing layer that everything else depends on

**Concerns**: `sexpr`, `coordinate`, `geometry`

**Philosophy**: Pure algorithmic tests with zero file dependencies. If this fails, nothing above it matters.

**Code Under Test**:

| Module | Key Functions/Classes |
|--------|----------------------|
| `kicad_sexpr.py` | `parse_sexp()`, `SexprBuilder`, `QuotedString`, `SexprError` |
| `kicad_geometry.py` | `BoundingBox`, coordinate utilities, `SvgRenderContext` |
| `kicad_pcb_base.py` | Base element classes, protocols |

**Proposed Subtests**:

```toml
[[subtests]]
file = "test_L0_001_sexpr_parsing.py"
name = "S-Expression Parsing"
description = "Parse KiCad S-expression format to nested lists"
test_case_type = "algorithmic"
# Tests: atoms, strings, quoted strings, nested lists, unicode

[[subtests]]
file = "test_L0_002_sexpr_builder.py"
name = "S-Expression Builder"
description = "Build S-expressions from Python data structures"
test_case_type = "algorithmic"
# Tests: atoms, lists, quoted strings, nested structures

[[subtests]]
file = "test_L0_003_quoted_strings.py"
name = "Quoted String Handling"
description = "REQ-KICAD-021: Round-trip quoted string preservation"
test_case_type = "algorithmic"
# Tests: strings with spaces, special chars, escaping

[[subtests]]
file = "test_L0_004_bounding_box.py"
name = "Bounding Box"
description = "REQ-KICAD-071: BoundingBox operations and math"
test_case_type = "algorithmic"
# Tests: union, intersection, contains, expand, transform

[[subtests]]
file = "test_L0_005_render_context.py"
name = "Render Context"
description = "SvgRenderContext options and transformations"
test_case_type = "algorithmic"
# Tests: layer filtering, color mapping, coordinate transforms
```

**Migration Source**: Extract from `test_sexpr.py`

---

## L1_parsing - Data Model Validation

**Purpose**: Prove the OOP data models are correct via parsing + round-trip

**Concerns**: `parsing`, `pcb`, `footprint`, `roundtrip`

**Philosophy**: If we can parse → serialize → parse and get equivalent results, the data model is sound. This stratum validates the entire OOP model layer.

**Current Scope**: PCB (`.kicad_pcb`) and Footprint (`.kicad_mod`)
**Future Scope**: Schematic (`.kicad_sch`) and Symbol (`.kicad_sym`) after framework transition

**Code Under Test**:

| Module | Key Classes/Functions |
|--------|----------------------|
| `kicad_pcb.py` | `KiCadPcb` - complete PCB parser |
| `kicad_footprint.py` | `KiCadFootprint` - footprint parser |
| `kicad_pad.py` | `Pad` (rect, circle, oval, roundrect, custom) |
| `kicad_fp_*.py` | `FpText`, `FpLine`, `FpArc`, `FpCircle`, `FpRect`, `FpPoly` |
| `kicad_pcb_routing.py` | `Segment`, `Via`, `Arc` |
| `kicad_pcb_graphics.py` | `GrText`, `GrLine`, `GrRect`, `GrArc`, `GrCircle`, `GrPoly`, `GrCurve` |
| `kicad_pcb_zone.py` | `Zone` |
| `kicad_property.py` | `Property` |
| `kicad_model.py` | `Model` (3D) |

**Proposed Subtests**:

```toml
[[subtests]]
file = "test_L1_001_pcb_roundtrip.py"
name = "PCB Round-Trip"
description = "Parse → serialize → parse PCB files with equivalency check"
test_cases = "cases/pcb/"
test_case_type = "reference"
# Validates: KiCadPcb, all routing elements, all graphics, zones

[[subtests]]
file = "test_L1_002_footprint_roundtrip.py"
name = "Footprint Round-Trip"
description = "Parse → serialize → parse footprint files with equivalency check"
test_cases = "cases/footprints/"
test_case_type = "reference"
# Validates: KiCadFootprint, Pad (all shapes), FpText, FpLine, etc.

[[subtests]]
file = "test_L1_003_oop_equivalency.py"
name = "OOP Model Equivalency"
description = "OOP model data matches raw sexp after parsing"
test_cases = "cases/pcb/"
test_case_type = "reference"
# Validates: all OOP accessors return correct values

[[subtests]]
file = "test_L1_004_parser_equivalency.py"
name = "Parser Equivalency"
description = "Different parsing approaches produce identical results"
test_case_type = "reference"
# Validates: consistency across parsing methods

[[subtests]]
file = "test_L1_005_element_roundtrip.py"
name = "Element-Level Round-Trip"
description = "Individual element types serialize correctly"
test_case_type = "synthetic"
# Validates: each element type in isolation (crafted test cases)

# FUTURE (after framework transition)
# [[subtests]]
# file = "test_L1_006_schematic_roundtrip.py"
# name = "Schematic Round-Trip"
# description = "Parse → serialize → parse schematic files"
# test_cases = "cases/schematic/"
# test_case_type = "reference"

# [[subtests]]
# file = "test_L1_007_symbol_roundtrip.py"
# name = "Symbol Round-Trip"
# description = "Parse → serialize → parse symbol files"
# test_cases = "cases/symbols/"
# test_case_type = "reference"
```

**Migration Source**: `test_roundtrip.py`, `test_kicad_footprint_roundtrip.py`, `test_oop_equivalency.py`, `test_parser_equivalency.py`

---

## L2_tools - Lower-Level Tools

**Purpose**: Test discrete tools that operate on KiCad files

**Concerns**: `tools`, `extraction`, `splitting`, `merging`, `filters`, `cleanup`

**Philosophy**: Tools are composable operations - extract, split, merge, filter, fix. Each tool does one thing well. This stratum tests them in isolation.

**Current Scope**: Symbol/footprint extraction, splitting, merging
**Future Scope**: Filters (footprint filter, symbol filter), automated file fixes/cleanups

**Code Under Test**:

| Module | Purpose |
|--------|---------|
| `kicad_symbol_extractor.py` | Extract symbols from .kicad_sym |
| `kicad_symbol_splitter.py` | Split multi-symbol files into individual files |
| `kicad_symbol_merger.py` | Merge individual symbol files back together |
| `lib_cruncher.kicad_symbol_sync` | Synchronize symbols between app-managed libraries |
| `kicad_footprint_extractor.py` | Extract footprints from projects |
| `kicad_pcb_parser.py` | Extract component data from PCB |
| `kicad_step_extractor.py` | Extract 3D STEP models |
| `kicad_filter_*.py` | Filter modules (footprint, symbol, schematic) |

**Proposed Subtests**:

```toml
[[subtests]]
file = "test_L2_001_symbol_extraction.py"
name = "Symbol Extraction"
description = "Extract symbols from .kicad_sym files"
test_cases = "cases/symbols/"
test_case_type = "reference"

[[subtests]]
file = "test_L2_002_footprint_extraction.py"
name = "Footprint Extraction"
description = "Extract footprints from projects"
test_cases = "cases/extraction/"
test_case_type = "reference"

[[subtests]]
file = "test_L2_003_symbol_splitting.py"
name = "Symbol Splitting"
description = "Split multi-symbol libraries to individual files"
test_cases = "cases/split/"
test_case_type = "reference"

[[subtests]]
file = "test_L2_004_symbol_merging.py"
name = "Symbol Merging"
description = "Merge individual symbol files into library"
test_case_type = "synthetic"

[[subtests]]
file = "test_L2_005_component_indexing.py"
name = "Component Indexing"
description = "Index and lookup components from PCB"
test_cases = "cases/pcb/"
test_case_type = "reference"

[[subtests]]
file = "test_L2_006_step_extraction.py"
name = "3D Model Extraction"
description = "Extract STEP models from boards"
test_cases = "cases/step/"
test_case_type = "reference"

# FUTURE
# [[subtests]]
# file = "test_L2_007_footprint_filter.py"
# name = "Footprint Filter"
# description = "Filter/transform footprint files"
# test_case_type = "reference"

# [[subtests]]
# file = "test_L2_008_symbol_filter.py"
# name = "Symbol Filter"
# description = "Filter/transform symbol files"
# test_case_type = "reference"

# [[subtests]]
# file = "test_L2_009_file_cleanup.py"
# name = "File Cleanup"
# description = "Automated file fixes and normalization"
# test_case_type = "synthetic"
```

**Migration Source**: `test_kicad_extractors.py`, `test_kicad_indexing.py`

---

## L3_rendering - SVG Validation

**Purpose**: SVG output matches kicad-cli ground truth (REQ-KICAD-039)

**Concerns**: `rendering`, `svg`, `layers`, `text`, `fonts`

**Philosophy**: Rendering is visual output - if it doesn't match kicad-cli, it's wrong. This stratum has the most tests (771+) and highest value for catching regressions.

**Code Under Test**:

| Module | Purpose |
|--------|---------|
| `kicad_pcb_svg.py` | Board-level SVG rendering |
| `kicad_footprint_svg.py` | Footprint-level SVG rendering |
| Element classes | `.to_svg()` methods on all elements |
| `kicad_stroke_font.py` | Hershey stroke font rendering |
| `kicad_text.py` | FreeType/HarfBuzz text rendering |
| `kicad_geometry.py` | `SvgRenderContext` |

**Proposed Subtests**:

```toml
[[subtests]]
file = "test_L3_001_board_svg.py"
name = "Board SVG Rendering"
description = "Board SVG matches kicad-cli reference output"
test_cases = "cases/svg/board/"
test_case_type = "reference"
# 663 tests: 47 boards × multiple layers

[[subtests]]
file = "test_L3_002_footprint_svg.py"
name = "Footprint SVG Rendering"
description = "Footprint SVG matches kicad-cli reference output"
test_cases = "cases/svg/footprints/"
test_case_type = "reference"
# 108 tests: 106 footprints × layers

[[subtests]]
file = "test_L3_003_element_coverage.py"
name = "Element Coverage"
description = "REQ-KICAD-032: All element types render correctly"
test_cases = "cases/svg/board/"
test_case_type = "reference"
# Validates: segment, via, arc, pad (all types), zone, gr_*, fp_*

[[subtests]]
file = "test_L3_004_layer_support.py"
name = "Layer Support"
description = "REQ-KICAD-031: All standard layers render correctly"
test_case_type = "reference"
# Validates: Cu, SilkS, Mask, Paste, Fab, CrtYd, Edge.Cuts, User.*

[[subtests]]
file = "test_L3_005_stroke_font.py"
name = "Stroke Font Rendering"
description = "Hershey stroke font text rendering"
test_case_type = "synthetic"
# Validates: rotation, scaling, mirroring, all glyphs

[[subtests]]
file = "test_L3_006_coordinate_accuracy.py"
name = "Coordinate Accuracy"
description = "REQ-KICAD-030: 0.5mm coordinate tolerance"
test_case_type = "reference"
# Validates: coordinate precision across all element types
```

**Migration Source**: `test_board_svg.py`, `test_footprint_svg.py`, `test_element_coverage.py`

**Dependencies**:

```toml
[[dependencies.internal_tools]]
name = "kicad-cli"
purpose = "Generate reference SVG outputs (ground truth)"
required_for = ["L3_rendering"]
note = "System-installed, regenerate via generate_*_references.py scripts"
```

---

## L4_applications - High-Level Tooling

**Purpose**: End-to-end application workflows for day-to-day use

**Concerns**: `applications`, `workflow`, `cruncher`, `integration`

**Philosophy**: Applications compose all prior layers into user-facing tools. `kicad_cruncher` will be the main entry point (like `altium_cruncher`). This stratum tests the full stack.

**Current Scope**: Project verification, CLI validation
**Future Scope**: `kicad_cruncher` commands, HTTP library server, preferences setup

**Code Under Test**:

| Module | Purpose |
|--------|---------|
| `kicad_cruncher.py` | Main CLI entry point |
| `kicad_cruncher__gui.py` | DearPyGUI interface |
| `kicad_utilities.py` | Project parsing, HTTP library generation |
| `kicad_setup.py` | KiCad preferences configuration |
| `kicad_part_converter.py` | Part data model conversion |

**Proposed Subtests**:

```toml
[[subtests]]
file = "test_L4_001_project_verification.py"
name = "Project Verification"
description = "Validate real KiCad project processing end-to-end"
test_cases = "cases/project/speedy/"
test_case_type = "reference"
# Full project: parse, extract components, render, convert

[[subtests]]
file = "test_L4_002_kicad_cli_validation.py"
name = "KiCad CLI Validation"
description = "Validate outputs against kicad-cli tool"
test_case_type = "reference"

[[subtests]]
file = "test_L4_003_part_conversion.py"
name = "Part Conversion"
description = "Convert KiCad components to Part data model"
test_cases = "cases/project/"
test_case_type = "reference"

[[subtests]]
file = "test_L4_004_http_library.py"
name = "HTTP Library Server"
description = "Test HTTP library generation for KiCad"
test_case_type = "synthetic"

# FUTURE
# [[subtests]]
# file = "test_L4_005_cruncher_commands.py"
# name = "Cruncher Commands"
# description = "Test kicad_cruncher CLI commands"
# test_case_type = "synthetic"

# [[subtests]]
# file = "test_L4_006_preferences_setup.py"
# name = "Preferences Setup"
# description = "KiCad preferences and library table configuration"
# test_case_type = "synthetic"
```

**Migration Source**: `test_verification.py`, `test_kicad_cli_validation.py`

---

## Test Migration Map

| Existing Test | Lines | Tests | Target Stratum | Target Subtest |
|--------------|-------|-------|----------------|----------------|
| `test_sexpr.py` | 371 | ~30 | L0_foundation | L0_001, L0_002, L0_003 |
| `test_roundtrip.py` | 375 | ~40 | L1_parsing | L1_001 |
| `test_kicad_footprint_roundtrip.py` | 313 | ~100 | L1_parsing | L1_002 |
| `test_oop_equivalency.py` | 534 | ~50 | L1_parsing | L1_003 |
| `test_parser_equivalency.py` | 217 | ~20 | L1_parsing | L1_004 |
| `test_kicad_extractors.py` | 402 | ~30 | L2_tools | L2_001, L2_002 |
| `test_kicad_indexing.py` | 339 | ~25 | L2_tools | L2_005 |
| `test_board_svg.py` | 622 | 663 | L3_rendering | L3_001 |
| `test_footprint_svg.py` | 290 | 108 | L3_rendering | L3_002 |
| `test_element_coverage.py` | 349 | ~50 | L3_rendering | L3_003 |
| `test_verification.py` | 150 | ~10 | L4_applications | L4_001 |
| `test_kicad_cli_validation.py` | 205 | ~15 | L4_applications | L4_002 |

**Total**: ~4,167 lines, ~1,141+ tests

---

## Directory Structure

```
tools/kicad/tests/
├── rack.toml                     # Master configuration
├── rack.py                       # CLI tool (copy from altium)
├── rack_architecture.md          # Framework specification (copy from altium)
├── rack_results/                 # Results (gitignored)
│
├── L0_foundation/
│   ├── STRATUM.toml
│   ├── conftest.py
│   ├── test_L0_001_sexpr_parsing.py
│   ├── test_L0_002_sexpr_builder.py
│   ├── test_L0_003_quoted_strings.py
│   ├── test_L0_004_bounding_box.py
│   ├── test_L0_005_render_context.py
│   └── cases/
│       └── sexpr/
│
├── L1_parsing/
│   ├── STRATUM.toml
│   ├── conftest.py
│   ├── test_L1_001_pcb_roundtrip.py
│   ├── test_L1_002_footprint_roundtrip.py
│   ├── test_L1_003_oop_equivalency.py
│   ├── test_L1_004_parser_equivalency.py
│   ├── test_L1_005_element_roundtrip.py
│   └── cases/
│       ├── pcb/
│       └── footprints/
│
├── L2_tools/
│   ├── STRATUM.toml
│   ├── conftest.py
│   ├── test_L2_001_symbol_extraction.py
│   ├── test_L2_002_footprint_extraction.py
│   ├── test_L2_003_symbol_splitting.py
│   ├── test_L2_004_symbol_merging.py
│   ├── test_L2_005_component_indexing.py
│   ├── test_L2_006_step_extraction.py
│   └── cases/
│       ├── symbols/
│       ├── extraction/
│       └── split/
│
├── L3_rendering/
│   ├── STRATUM.toml
│   ├── conftest.py
│   ├── test_L3_001_board_svg.py
│   ├── test_L3_002_footprint_svg.py
│   ├── test_L3_003_element_coverage.py
│   ├── test_L3_004_layer_support.py
│   ├── test_L3_005_stroke_font.py
│   ├── test_L3_006_coordinate_accuracy.py
│   ├── cases/
│   │   └── svg/
│   │       ├── board/
│   │       │   ├── input/
│   │       │   ├── reference_output/
│   │       │   └── output/
│   │       └── footprints/
│   │           ├── input/
│   │           ├── reference_output/
│   │           └── output/
│   └── helpers/
│       ├── generate_board_svg_references.py
│       ├── generate_footprint_svg_references.py
│       └── svg_compare.py
│
├── L4_applications/
│   ├── STRATUM.toml
│   ├── conftest.py
│   ├── test_L4_001_project_verification.py
│   ├── test_L4_002_kicad_cli_validation.py
│   ├── test_L4_003_part_conversion.py
│   ├── test_L4_004_http_library.py
│   └── cases/
│       └── project/
│           └── speedy/
│
├── common/                       # Shared helpers (cross-stratum)
│   ├── __init__.py
│   └── fixtures.py
│
└── legacy/                       # During migration only
    └── (original test files)
```

---

## rack.toml Template

```toml
[rack]
name = "KiCad Module Tests"
version = "1.0"
description = "Test suite for KiCad file format parsing, tools, and rendering"
note = "Initial rack framework setup - migrating from flat test structure"

[strata]
order = [
    "L0_foundation",
    "L1_parsing",
    "L2_tools",
    "L3_rendering",
    "L4_applications",
]
default_enabled = [
    "L0_foundation",
    "L1_parsing",
    "L2_tools",
    "L3_rendering",
    "L4_applications",
]

# Concerns hierarchy
[concerns.sexpr]
description = "S-expression parsing and building"

[concerns.parsing]
description = "File parsing and data model validation"

[concerns."parsing.pcb"]
description = "PCB file parsing"

[concerns."parsing.footprint"]
description = "Footprint file parsing"

[concerns.tools]
description = "Lower-level file manipulation tools"

[concerns."tools.extraction"]
description = "Symbol/footprint extraction"

[concerns."tools.splitting"]
description = "Library splitting"

[concerns."tools.merging"]
description = "Library merging"

[concerns.rendering]
description = "SVG rendering pipeline"

[concerns."rendering.board"]
description = "Board SVG rendering"

[concerns."rendering.footprint"]
description = "Footprint SVG rendering"

[concerns."rendering.text"]
description = "Text/font rendering"

[concerns.applications]
description = "High-level application workflows"

[dependencies]
python_packages = [
    "pytest",
    "pytest-json-report",
    "tomli-w",
]

[[dependencies.internal_tools]]
name = "kicad-cli"
purpose = "Generate reference SVG outputs (ground truth)"
required_for = ["L3_rendering"]
note = "System-installed KiCad CLI tool"
```

---

## Key Differences from Altium Rack

| Aspect | Altium | KiCad |
|--------|--------|-------|
| Ground truth | Altium Bridge (C# SDK) | kicad-cli (command-line tool) |
| Reference generation | Complex (requires Altium install) | Simple (scripts call kicad-cli) |
| Interop testing | L4 with C# validation | Not needed (no SDK) |
| File complexity | Binary OLE containers | Text S-expressions |
| Stratum count | 7 (L0-L6) | 5 (L0-L4) |

---

## Migration Phases

### Phase 1: Framework Setup (Do First)

**Tasks**:
1. Copy `rack.py` from `tools/altium/tests/rack.py`
2. Copy `rack_architecture.md` from `tools/altium/tests/rack_architecture.md`
3. Create `rack.toml` with strata configuration
4. Create empty stratum directories with STRATUM.toml files
5. Move existing tests to `legacy/` folder
6. Add `rack_results/` to `.gitignore`
7. Verify `rack list` works

**Acceptance**: `rack list` shows all 5 strata

### Phase 2: L3_rendering (Highest Value - 771 tests)

**Rationale**: This stratum has the most tests and provides the most regression protection. Migrating it first proves the framework works at scale.

**Tasks**:
1. Create `L3_rendering/STRATUM.toml` with full manifest
2. Move `test_board_svg.py` → `L3_rendering/test_L3_001_board_svg.py`
3. Move `test_footprint_svg.py` → `L3_rendering/test_L3_002_footprint_svg.py`
4. Move `test_element_coverage.py` → `L3_rendering/test_L3_003_element_coverage.py`
5. Move `tests/test_cases/svg/` → `L3_rendering/cases/svg/`
6. Move reference generation scripts to `L3_rendering/helpers/`
7. Create `L3_rendering/conftest.py` with shared fixtures
8. Verify `rack run L3` passes all 771 tests

**Acceptance**: `rack run L3` shows 771/771 tests passing

### Phase 3: L0_foundation (Fastest)

**Rationale**: Quick wins, builds confidence in the framework.

**Tasks**:
1. Create `L0_foundation/STRATUM.toml`
2. Split `test_sexpr.py` into:
   - `test_L0_001_sexpr_parsing.py`
   - `test_L0_002_sexpr_builder.py`
   - `test_L0_003_quoted_strings.py`
3. Create new subtests:
   - `test_L0_004_bounding_box.py`
   - `test_L0_005_render_context.py`
4. Verify `rack run L0` passes

**Acceptance**: `rack run L0` shows all subtests passing

### Phase 4: L1_parsing

**Tasks**:
1. Create `L1_parsing/STRATUM.toml`
2. Move `test_roundtrip.py` → `L1_parsing/test_L1_001_pcb_roundtrip.py`
3. Move `test_kicad_footprint_roundtrip.py` → `L1_parsing/test_L1_002_footprint_roundtrip.py`
4. Move `test_oop_equivalency.py` → `L1_parsing/test_L1_003_oop_equivalency.py`
5. Move `test_parser_equivalency.py` → `L1_parsing/test_L1_004_parser_equivalency.py`
6. Set up shared test cases in `L1_parsing/cases/`
7. Verify `rack run L1` passes

**Acceptance**: `rack run L1` shows all subtests passing

### Phase 5: L2_tools and L4_applications

**Tasks**:
1. Create `L2_tools/STRATUM.toml`
2. Move `test_kicad_extractors.py` → split into L2_001, L2_002
3. Move `test_kicad_indexing.py` → `L2_tools/test_L2_005_component_indexing.py`
4. Create `L4_applications/STRATUM.toml`
5. Move `test_verification.py` → `L4_applications/test_L4_001_project_verification.py`
6. Move `test_kicad_cli_validation.py` → `L4_applications/test_L4_002_kicad_cli_validation.py`
7. Verify `rack run L2` and `rack run L4` pass

**Acceptance**: `rack run` (all strata) shows all tests passing

### Phase 6: Cleanup

**Tasks**:
1. Remove `legacy/` folder
2. Update `TESTING.md` to reference rack commands
3. Update `README.md` with rack usage
4. Verify `rack run` executes full suite
5. Generate HTML report: `rack report`

**Acceptance**: Full test suite runs via `rack run`, `legacy/` removed

---

## Files to Copy from Altium

| Source | Destination | Notes |
|--------|-------------|-------|
| `tools/altium/tests/rack.py` | `tools/kicad/tests/rack.py` | Main CLI tool |
| `tools/altium/tests/rack_architecture.md` | `tools/kicad/tests/rack_architecture.md` | Framework specification |

**Note**: `rack.py` is designed to be project-agnostic (RACK-033). It should work without modification. Project-specific configuration goes in `rack.toml` and `STRATUM.toml` files.

---

## Success Criteria

1. **All existing tests pass**: Zero regressions during migration
2. **Rack CLI works**: `rack run`, `rack list`, `rack status`, `rack report` all functional
3. **HTML reports generate**: Visual reports with drill-down to subtests
4. **Strata ordering respected**: L0 runs before L1, etc.
5. **Concern filtering works**: `rack run --concern rendering` runs only L3
6. **Documentation updated**: TESTING.md, README.md reference rack commands

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-17 | Initial migration plan |
