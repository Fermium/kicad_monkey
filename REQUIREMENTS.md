# KiCad Monkey Requirements

**Version**: 2026.5.31
**Last Updated**: 2026-05-31

This document defines formal requirements for the public `kicad-monkey`
package.
Requirements use the format `REQ-KICAD-XXX` for traceability in code and tests.

---

## Architecture Requirements

### REQ-KICAD-001: Zero External Dependencies for Core Parsing

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |

**Requirement**: The S-expression parser (`kicad_sexpr.py`) and core file parsers MUST use only Python standard library.

**Rationale**:
- Module can be extracted as standalone package
- No dependency conflicts with other tools
- Faster imports and smaller footprint

**Verification**: Import test - core modules import without third-party packages.

---

### REQ-KICAD-002: Parser Responsibility - Data Extraction Only

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |

**Requirement**: KiCad parsers MUST extract ALL data from files without filtering or business logic.

**Rationale**:
- Different consumers may have different filtering requirements
- Filtering belongs in downstream applications
- Enables parser to be a general-purpose library

**Verification**: Code review - no filtering logic in parser modules.

---

### REQ-KICAD-003: Converter Layer Separation

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | MEDIUM |
| **Added** | 2025-12-18 |
| **Implemented** | 2025-12-18 |

**Requirement**: Conversion from typed KiCad footprint objects to neutral
component models MUST be outside the parser.

**Rationale**:
- Separation of concerns (parsing vs. conversion)
- Allows downstream converters to add application-specific metadata

**Implementation**:
- Legacy `KiCadPcbComponent.to_pcb_component()` and `KiCadPcbDoc.to_pcb_components()` conversion hooks were removed
- Application code should parse with `KiCadPcb` and adapt from the typed object
  graph

**Verification**: Parser modules do not own neutral component-model policy.

---

### REQ-KICAD-004: Canonical PCB SVG Contract Location

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2026-02-28 |
| **Implemented** | 2026-02-28 |

**Requirement**: Stable SVG metadata emitted by `kicad-monkey` MUST have a
documented package contract and conformance tests.

**Rules**:
- Contract files belong under `docs/contracts/` once promoted.
- Contract changes need matching conformance tests.
- SVG element-level metadata (`data-*` attributes) and board outline/cutout
  semantics must not drift silently.

**Verification**:
- [x] `L99_signoff` checks the current contract/design-doc manifest.

---

### REQ-KICAD-005: Source-Model Readiness Gate Before Track D

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2026-03-16 |
| **Implemented** | 2026-03-16 |

**Requirement**: Significant downstream neutral-model expansion work MUST be
gated on an explicit source-model readiness review of the `kicad-monkey` OOP
parser/model.

**Scope**:
- Review the real `KiCadPcb` / `KiCadFootprint` / related OOP API surfaces
  that downstream converters depend on
- Validate the parser/model on a curated shared KiCad corpus, not just legacy
  parser fixtures
- Record current parser/model gaps separately from downstream converter gaps
- Treat the KiCad OOP model as the source-truth boundary for Track D, not the
  legacy `KiCadPcbDoc` component extractor

**Rationale**:
- Converter work is only worth doing if the underlying KiCad source model is
  trustworthy and stable
- Source-model probing showed that the real `KiCadPcb` object already carries
  more board data than early downstream converters used
- We need to avoid misclassifying converter-contract drift as parser failure

**Verification**:
- [x] Source-model readiness outcome is recorded in `ARCHITECTURE.md`
- [x] Parser-readiness tests cover curated shared-corpus KiCad boards
- [x] The current blocker list distinguishes parser/model issues from converter issues

---

### REQ-KICAD-006: Official Upstream Baseline For Format Review

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2026-03-16 |
| **Implemented** | 2026-03-16 |

**Requirement**: KiCad format-readiness review and parser-coverage claims MUST
be anchored to explicit official KiCad source baselines.

**Rules**:
- Use an official release-line reference and an official upstream development
  reference when comparing format coverage
- Do not use a local feature branch as the only truth source
- Record the exact upstream refs used by the current review in the active plan

**Current baseline**:
- `upstream/master` at fetch time
- current KiCad 10 release-line tag `10.0.0-rc2`

**Verification**:
- [x] Active KiCad source-model review plan records exact upstream refs
- [x] Review findings call out whether they were observed on release-line or development-line code

---

### REQ-KICAD-007: Named-Net Syntax Preservation On Modern Boards

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2026-03-16 |
| **Implemented** | 2026-03-16 |

**Requirement**: The KiCad OOP parser MUST preserve named-net syntax when a
board uses direct net-name tokens on pads, routing, or zones instead of a
top-level numeric net table.

**Rules**:
- Do not assume every modern KiCad board emits top-level `(net <id> <name>)`
  entries
- Preserve net identity on the element carriers that actually express it
- Connectivity-bearing OOP elements MUST use a typed dataclass carrier rather
  than tuple/int ad hoc net payloads
- The authoritative OOP carrier is `NetRef { ordinal?, name? }`
- Readiness and converter work MUST not assume `pcb.nets[]` is always populated
  on modern boards

**Verification**:
- [x] Shared-corpus readiness tests cover a named-net board without a top-level net table
- [x] Pads, segments, vias, arcs, and zones preserve their local net-name payloads on that board
- [x] Pads, segments, vias, arcs, and zones expose typed `NetRef` carriers

---

### REQ-KICAD-008: Footprint-Local Board Profile Carriers

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2026-03-16 |
| **Implemented** | 2026-03-16 |

**Requirement**: The KiCad readiness review MUST treat footprint-local
`Edge.Cuts` geometry as a valid board-profile carrier.

**Rules**:
- Do not assume board profile always appears only as top-level `gr_*`
  `Edge.Cuts` graphics
- Readiness tests and downstream converter work MUST account for outline
  carriers embedded in footprints or board-outline helper footprints
- The authoritative OOP API for combined outline discovery is
  `KiCadPcb.board_outline_carriers()`

**Verification**:
- [x] Shared-corpus readiness tests cover a board with footprint-local `Edge.Cuts`
- [x] Review findings distinguish top-level vs footprint-local outline carriers

---

### REQ-KICAD-009: Typed Pad/Via Drill Modifier Surface

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2026-03-16 |
| **Implemented** | 2026-03-16 |

**Requirement**: The KiCad OOP model MUST expose pad/via drill modifier and
post-machining semantics as typed dataclasses instead of raw nested token
payloads.

**Rules**:
- `backdrill` and `tertiary_drill` MUST map to a typed `DrillProps` carrier
- `front_post_machining` and `back_post_machining` MUST map to a typed
  `PostMachiningProps` carrier
- explicit `zone_layer_connections` MUST map to a typed
  `ZoneLayerConnections` carrier
- the typed carriers MUST survive parse -> serialize -> parse round-trip

**Verification**:
- [x] Pads and vias expose typed drill/machining/layer-override dataclasses
- [x] Round-trip tests cover typed drill/machining/layer-override metadata
- [x] Shared-corpus readiness tests cover explicit `zone_layer_connections`

---

### REQ-KICAD-010: Typed Footprint Pad-Group Surface

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | MEDIUM |
| **Added** | 2026-03-16 |
| **Implemented** | 2026-03-16 |

**Requirement**: The KiCad OOP model MUST expose footprint pad-group semantics
as typed dataclasses instead of raw strings or nested token lists.

**Rules**:
- `net_tie_pad_groups` MUST map to typed `PadNameGroup` objects
- `jumper_pad_groups` MUST map to typed `PadNameGroup` objects
- `duplicate_pad_numbers_are_jumpers` MUST remain explicit on the `Footprint`
  model
- the pad-group semantics MUST survive parse -> serialize -> parse round-trip

**Verification**:
- [x] Footprints expose typed pad-group carriers
- [x] Shared-corpus readiness tests cover `net_tie_pad_groups`
- [x] Round-trip tests cover `duplicate_pad_numbers_are_jumpers` and
      `jumper_pad_groups`

---

### REQ-KICAD-013: Typed Footprint Placement And Component-Class Surface

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2026-03-16 |
| **Implemented** | 2026-03-16 |

**Requirement**: The KiCad OOP model MUST expose footprint placement context
and component-class membership as typed dataclasses instead of raw unknown
elements.

**Rules**:
- `path`, `sheetname`, and `sheetfile` MUST map to `FootprintPlacement`
- `component_classes` MUST map to typed `ComponentClassRef` entries
- the typed placement and class metadata MUST survive parse -> serialize ->
  parse round-trip

**Verification**:
- [x] Footprints expose `placement: FootprintPlacement`
- [x] Footprints expose `component_classes: list[ComponentClassRef]`
- [x] Round-trip tests cover typed placement metadata and component classes
- [x] Shared-corpus readiness tests cover typed footprint placement metadata

---

### REQ-KICAD-014: Typed Barcode And Generated-Object Surface

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2026-03-16 |
| **Implemented** | 2026-03-16 |

**Requirement**: KiCad 10 board/footprint barcode elements and board-level
`generated` objects MUST be modeled as typed dataclasses and survive round-trip.

**Rules**:
- board and footprint `barcode` elements MUST map to `Barcode` /
  `BarcodeMargins`
- top-level `generated` items MUST map to `GeneratedObject` /
  `GeneratedProperty`
- the typed carriers MUST survive parse -> serialize -> parse round-trip

**Verification**:
- [x] Board and footprint barcode elements are first-class typed objects
- [x] Board-level generated objects are first-class typed objects
- [x] Round-trip tests cover barcodes and generated objects
- [x] Shared-corpus readiness tests cover board-level generated tuning patterns

---

### REQ-KICAD-080: Board Feature Metadata Strictness

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2026-02-28 |

**Requirement**: When SVG metadata emission is enabled, board outline geometry MUST emit explicit board feature typing:
- Outer profile path: `data-feature="board-outline"`
- Cutout paths: `data-feature="board-cutout"` and `data-feature-index` (0-based, contiguous per view)

---

### REQ-KICAD-081: Element Identity Contract

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2026-02-28 |

**Requirement**: The shared SVG contract MUST define a stable per-export element identity field (`data-element-key`) distinct from SVG DOM `id`, with optional source-native UID attachment via `data-source-uid` when available.

---

### REQ-KICAD-082: Layer Role Normalization

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2026-02-28 |

**Requirement**: Shared SVG metadata MUST include a tool-agnostic layer role classification (`data-layer-role`) while preserving tool-native layer identifiers.

**Allowed Roles**:
- `copper`
- `silkscreen`
- `soldermask`
- `paste`
- `mechanical`
- `drill`
- `other`

---

### REQ-KICAD-083: Primitive Linkage Minimum Set

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2026-02-28 |

**Requirement**: Net/component linkage metadata MUST be emitted where applicable on conductive/layout primitives at minimum: `track`, `arc`, `pad`, `via`, `region`, `fill`, and polygon primitives.

---

### REQ-KICAD-084: Pad Pin Mapping Fields

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2026-02-28 |

**Requirement**: Pad geometry intended for viewer-side connectivity and design-sidecar linkage MUST include:
- `data-component` (reference designator)
- `data-component-index`
- `data-pad-number` (footprint pin/pad number)

---

### REQ-KICAD-085: Board Cutout Scope Boundary

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2026-02-28 |

**Requirement**: `board-cutout` features represent board-profile voids only. Drill and slot hole geometry remains classified as hole primitives (`pad-hole`, `via-hole`, etc.), not board-cutout.

---

### REQ-KICAD-086: Cross-Tool Contract Conformance Suite

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2026-02-28 |

**Requirement**: A shared SVG contract conformance suite MUST be executable by
supported CAD pipelines and MUST fail CI on semantic drift in required metadata
fields.

---

## Data Model Requirements

### REQ-KICAD-010: Source CAD Identification

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |
| **Implemented** | 2025-12-18 |

**Requirement**: All `PcbComponent` instances from KiCad MUST include `_source_cad: "kicad"` in params.

**Rationale**:
- Allows downstream consumers to identify source CAD system
- Enables CAD-specific filtering logic
- Required by REQ-BOM-002

**Implementation**: Downstream component converters should add `_source_cad:
"kicad"` to neutral component outputs derived from KiCad footprints.

**Verification**: Unit test `test_source_cad_set` in `test_converters_kicad.py`.

---

### REQ-KICAD-011: DNP Flag Preservation

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |
| **Implemented** | 2025-12-18 |

**Requirement**: Components with KiCad's `dnp` attribute MUST have `DNP: True` in `PcbComponent.params`.

**Rationale**: Allows downstream BOM filtering to respect DNP status.

**Implementation**: The typed `Footprint` parser preserves KiCad's `dnp`
attribute so downstream converters can map it to neutral component metadata.

**Verification**: Unit tests `test_dnp_true_preserved` and `test_dnp_false_not_added` in `test_converters_kicad.py`.

---

### REQ-KICAD-012: Exclude From BOM Preservation

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |
| **Implemented** | 2025-12-18 |

**Requirement**: Components with KiCad's `exclude_from_bom` attribute MUST have `exclude_from_bom: True` in `PcbComponent.params`.

**Rationale**:
- KiCad's source-level no-BOM flag
- Allows downstream BOM consumers to filter without knowledge of KiCad internals

**Implementation**:
- The typed `Footprint` parser extracts KiCad's `exclude_from_bom` attribute
- Converter preserves it in params and on the generic component field

**Verification**: Unit test `test_exclude_from_bom_true_preserved` in `test_converters_kicad.py`.

---

## S-Expression Requirements

### REQ-KICAD-020: Round-Trip Fidelity

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |

**Requirement**: `parse_sexp()` followed by `build_sexp()` MUST produce output that KiCad accepts without error.

**Note**: Exact byte-for-byte match is NOT required due to whitespace normalization.

**Verification**: Round-trip test with KiCad validation.

---

### REQ-KICAD-021: Quoted String Handling

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |

**Requirement**: Strings containing spaces, quotes, or special characters MUST be properly quoted in output.

**Implementation**: Use `QuotedString` class to mark strings requiring quotes.

**Verification**: Unit tests for special character handling.

---

### REQ-KICAD-022: Unicode Support

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | MEDIUM |
| **Added** | 2025-12-18 |

**Requirement**: S-expression parser MUST handle UTF-8 encoded files correctly.

**Verification**: Unit test with Unicode component names.

---

## SVG Rendering Requirements

### REQ-KICAD-030: Coordinate Accuracy

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |

**Requirement**: SVG output coordinates MUST match KiCad CLI output within 0.5mm tolerance.

**Rationale**: Ensures visual fidelity for documentation and review.

**Verification**: Automated comparison tests against KiCad CLI reference.

---

### REQ-KICAD-031: Layer Support

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |

**Requirement**: SVG renderer MUST support all standard KiCad layers:

| Category | Layers |
|----------|--------|
| Copper | F.Cu, B.Cu, In1.Cu-In30.Cu |
| Silkscreen | F.SilkS, B.SilkS |
| Mask | F.Mask, B.Mask |
| Paste | F.Paste, B.Paste |
| Fabrication | F.Fab, B.Fab |
| Courtyard | F.CrtYd, B.CrtYd |
| Edge | Edge.Cuts |
| User | User.1-User.9 |

**Verification**: Test cases cover all layer types.

---

### REQ-KICAD-032: Element Coverage

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |

**Requirement**: SVG renderer MUST support these element types:

| Element | Description |
|---------|-------------|
| segment | Track segments |
| via | Vias (all types) |
| arc | Track arcs |
| pad | Pads (SMD, TH, custom) |
| zone | Filled zones |
| gr_line | Graphical lines |
| gr_rect | Graphical rectangles |
| gr_circle | Graphical circles |
| gr_arc | Graphical arcs |
| gr_poly | Graphical polygons |
| gr_curve | Bezier curves |
| gr_text | Text labels |
| fp_text | Footprint text |
| fp_line | Footprint lines |
| fp_poly | Footprint polygons |

**Verification**: Element coverage test matrix.

---

## Testing Requirements

### REQ-KICAD-039: KiCad-CLI Validation as Ground Truth

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-25 |

**Requirement**: SVG output MUST be validated against `kicad-cli` reference output using a comprehensive battery of tests.

**Rationale**:
- `kicad-cli` is the authoritative SVG renderer
- Matching its output ensures visual fidelity
- Automated comparison catches regressions

**Test Structure**:
```
tests/test_cases/svg/
├── board/
│   ├── input/           # .kicad_pcb test files
│   ├── reference_output/ # kicad-cli generated SVGs
│   └── output/          # Python generated SVGs (for comparison)
└── footprints/
    ├── input/           # .kicad_mod test files
    ├── reference_output/ # kicad-cli generated SVGs
    └── output/          # Python generated SVGs (for comparison)
```

**Test Coverage**:
- Simple geometry (lines, rects, circles, arcs, polygons)
- All pad shapes (rect, circle, oval, roundrect, custom)
- Text rendering (stroke font, TrueType)
- All layer types (copper, silk, mask, paste, fab, etc.)
- Complex real-world boards (multi-layer, 100+ footprints)

**Comparison Method**:
- Extract coordinates from SVG paths and circles
- Normalize for bounding box offset differences
- Compare with 0.5mm tolerance (REQ-KICAD-030)
- Accept 85%+ coordinate match for zone-heavy boards

**Verification**: All non-skipped tests pass; skipped tests documented with known issues.

---

### REQ-KICAD-040: Self-Contained Tests

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |

**Requirement**: Public package tests MUST be in `tests/`.

**Rationale**: Module can be extracted with tests intact.

**Verification**: Release CI runs Rack from the package-local `tests/` tree.

---

### REQ-KICAD-041: Test Case Organization

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | MEDIUM |
| **Added** | 2025-12-18 |

**Requirement**: Test data MUST be organized in `tests/test_cases/` with clear structure:

```
test_cases/
├── svg/
│   ├── board/       # Board SVG test cases
│   └── footprints/  # Footprint SVG test cases
├── project/         # Project file test cases
└── sexpr/           # S-expression test cases
```

---

### REQ-KICAD-042: Reference Output Generation

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | MEDIUM |
| **Added** | 2025-12-18 |

**Requirement**: SVG reference outputs MUST be generated using `kicad-cli` for authoritative comparison.

**Scripts**:
- `tests/generate_board_svg_references.py`
- `tests/generate_svg_references.py`

---

## Error Handling Requirements

### REQ-KICAD-050: Parse Error Recovery

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | MEDIUM |
| **Added** | 2025-12-18 |

**Requirement**: Parsers SHOULD log warnings for unrecognized elements but continue parsing.

**Rationale**: New KiCad versions may add elements; graceful degradation is preferred.

---

### REQ-KICAD-051: Clear Error Messages

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | MEDIUM |
| **Added** | 2025-12-18 |

**Requirement**: Parse errors MUST include file path and line number when available.

**Format**: `"Parse error in {file}:{line}: {message}"`

---

## Compatibility Requirements

### REQ-KICAD-060: KiCad Version Support

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-18 |

**Requirement**: Module MUST support KiCad 7.x and 8.x file formats.

**Note**: KiCad 6.x is deprecated but may work with warnings.

**Verification**: Test cases from KiCad 7 and 8 projects.

---

### REQ-KICAD-061: Forward Compatibility

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | MEDIUM |
| **Added** | 2025-12-18 |

**Requirement**: Unknown S-expression elements SHOULD be preserved in round-trip operations.

**Rationale**: Allows files from newer KiCad versions to pass through without data loss.

---

## Code Organization Requirements

### REQ-KICAD-070: One Class Per File

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-25 |

**Requirement**: Each major class SHOULD be in its own file for clarity and maintainability.

**Rationale**:
- Easier to locate and maintain code
- Reduces merge conflicts
- Clearer module boundaries

**Applies To**:
- `kicad_pcb_footprint.py` → split into `kicad_pad.py`, `kicad_fp_text.py`, etc.
- Element classes (Pad, FpText, FpLine, FpArc, FpCircle, FpRect, FpPoly, Property, Model)

**Verification**: Code review - each class file contains one primary class.

---

### REQ-KICAD-071: Bounded Protocol

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2025-12-25 |
| **Implemented** | 2025-12-25 |

**Requirement**: All spatial elements MUST implement `get_bounds() -> BoundingBox`.

**Implementation**: All element classes now have `get_bounds()` methods:
- Footprint elements: Pad, FpText, FpLine, FpArc, FpCircle, FpRect, FpPoly, Property
- PCB routing: Segment, Via, Arc
- PCB graphics: GrText, GrLine, GrRect, GrArc, GrCircle, GrPoly, GrCurve, GrTextBox
- Containers: Zone, Footprint (transforms child bounds to board coordinates)

**Definition** (in `kicad_geometry.py`):
```python
class Bounded(Protocol):
    def get_bounds(self) -> BoundingBox: ...
```

**Rationale**:
- Enables bounding box calculation for any element
- Used by SVG rendering, filters, spatial queries
- Uniform interface across all element types

**Applies To**: Pad, FpText, FpLine, FpArc, FpCircle, FpRect, FpPoly, Zone, Segment, Via, GrText, etc.

**Verification**: Type checking with mypy; unit tests for each element type.

---

### REQ-KICAD-072: SvgRenderable Protocol

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2025-12-25 |
| **Implemented** | 2025-12-25 |

**Requirement**: All renderable elements MUST implement `to_svg(ctx) -> list[str]`.

**Implementation**: All element classes now have `to_svg()` methods:
- Footprint elements: Pad, FpText, FpLine, FpArc, FpCircle, FpRect, FpPoly, Property
- PCB routing: Segment, Via, Arc
- PCB graphics: GrText, GrLine, GrRect, GrArc, GrCircle, GrPoly, GrCurve, GrTextBox
- Containers: Zone, Footprint (composes from child to_svg() calls)

**Definition** (in `kicad_geometry.py`):
```python
class SvgRenderable(Protocol):
    def to_svg(self, ctx: SvgRenderContext | None = None) -> list[str]: ...
```

**Rationale**:
- Each element knows how to render itself
- Parent containers compose child elements
- Decentralized rendering logic (no mega renderer files)

**Signature**:
- `ctx`: Render context with transform, style, layer filter options
- Returns: List of SVG element strings (not a complete document)

**Applies To**: Pad, FpText, FpLine, FpArc, FpCircle, FpRect, FpPoly, Zone, Segment, Via, GrText, KiCadFootprint, KiCadPcb, etc.

**Verification**: Type checking; SVG comparison tests pass.

---

### REQ-KICAD-073: SvgRenderContext

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | HIGH |
| **Added** | 2025-12-25 |

**Requirement**: SVG rendering MUST use `SvgRenderContext` for transform and style options.

**Definition** (in `kicad_geometry.py`):
```python
@dataclass
class SvgRenderContext:
    offset_x: float = 0.0
    offset_y: float = 0.0
    rotation: float = 0.0
    layers: list[str] | None = None  # None = all layers
    fill: str = "#000000"
    stroke: str = "#000000"
    black_and_white: bool = True
    arc_error_mm: float = 0.005  # ARC_HIGH_DEF
    precision: int = 4  # Decimal places for coordinates
```

**Design Principles**:
1. **Minimal core**: Include only what's needed for kicad-cli validation parity
2. **Extensible**: New fields with defaults can be added without breaking callers
3. **Don't over-engineer**: Add features when there's a real use case

**Future Extensions** (add when needed):
- Filters (element/layer filtering beyond simple layer list)
- Custom colors (layer color overrides)
- SVG tag metadata (custom attributes, IDs, classes)
- Scale/mirror transforms

**Rationale**:
- Centralizes rendering options
- Enables nested transforms (footprint in PCB)
- Consistent style across elements

**Verification**: Unit tests for context application; SVG output matches kicad-cli.

---

### REQ-KICAD-074: Decentralized SVG Rendering

| Field | Value |
|-------|-------|
| **Status** | IMPLEMENTED |
| **Priority** | HIGH |
| **Added** | 2025-12-25 |
| **Implemented** | 2025-12-25 |

**Requirement**: SVG rendering logic MUST be distributed to element classes, NOT centralized in mega renderer files.

**Implementation**:
- Each element class (Pad, FpLine, Segment, GrLine, etc.) has `to_svg(ctx) -> list[str]`
- `KiCadFootprint.to_svg()` composes elements via `el.to_svg(ctx)` calls
- `Footprint.to_svg()` (board-embedded) uses transformed context for child elements
- Shared geometry utilities in `kicad_geometry.py`
- `kicad_footprint_svg.py` marked deprecated
- `kicad_pcb_svg.py` internal functions marked deprecated; `render_pcb_svg()` remains as entry point

**Rationale**:
- Single responsibility principle
- Easier to test individual elements
- New element types just implement `to_svg()`

**Verification**: All 2807 tests pass; deprecated functions emit warnings.

---

### REQ-KICAD-075: Geometry Utilities Location

| Field | Value |
|-------|-------|
| **Status** | APPROVED |
| **Priority** | MEDIUM |
| **Added** | 2025-12-25 |

**Requirement**: Shared geometry utilities MUST be in `kicad_geometry.py`.

**Utilities to include**:
- `rotate_point(x, y, angle_deg, cx, cy)` - Rotate point around center
- `get_arc_to_segment_count(radius, error_max, arc_angle)` - Arc approximation
- `BoundingBox` - Axis-aligned bounding box (already exists)
- `Contour` - Closed polygon (already exists)
- Protocols: `Bounded`, `SvgRenderable`
- Context: `SvgRenderContext`

**Rationale**:
- Single location for geometry code
- Not SVG-specific (usable for other renderers, filters)
- Avoids duplication across element files

**Verification**: No geometry utilities duplicated in element files.

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.2 | 2025-12-25 | REQ-KICAD-071, 072, 074 marked IMPLEMENTED (SVG refactor complete) |
| 1.1 | 2025-12-25 | Added REQ-KICAD-070 through 075 for SVG refactoring |
| 1.0 | 2025-12-18 | Initial requirements baseline |
