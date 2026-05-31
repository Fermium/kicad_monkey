# Plan: Improve KiCad SVG Testing Accuracy

## Goals
1. **Separate footprint vs PCB testing** - Footprints are simpler, should have tighter tolerances
2. **Measure and report actual accuracy** - Generate error reports by element type in test output folder
3. **Get speedy and taillight passing** - Important production boards

## Current State
- `test_board_svg.py` line 292: `compare_svg_shapes()` uses 0.5mm tolerance for all elements
- 47 board test cases, 117 footprint test cases
- **speedy**: 15/17 layers failing (zones, mask expansion, pads)
- **taillight**: 1/17 layers failing (B.Fab - Unicode omega character)

---

## Implementation Plan

### Phase 1: Create Shared Comparison Utilities

Create `tools/kicad/tests/svg_comparison/` module:

**Files to create:**
```
tools/kicad/tests/svg_comparison/
    __init__.py
    element_types.py      # ElementType enum
    tolerances.py         # Per-element-type tolerance config
    coordinate_extractor.py  # Extract coords from SVG (refactor from test_board_svg.py)
    comparator.py         # Compare SVGs, return detailed results
    report_generator.py   # Generate JSON + Markdown reports
```

**Key data structures:**

```python
# element_types.py
class ElementType(Enum):
    TRACK = "track"
    VIA = "via"
    PAD = "pad"
    ZONE = "zone"
    GR_LINE = "gr-line"
    GR_CIRCLE = "gr-circle"
    GR_ARC = "gr-arc"
    GR_RECT = "gr-rect"
    GR_POLY = "gr-poly"
    GR_TEXT = "gr-text"
    DRILL = "drill"
    UNKNOWN = "unknown"

# tolerances.py
BOARD_TOLERANCES = {
    ElementType.TRACK: 0.1,
    ElementType.VIA: 0.1,
    ElementType.PAD: 0.1,
    ElementType.ZONE: 0.5,      # Zones re-computed at export
    ElementType.GR_LINE: 0.2,
    ElementType.GR_TEXT: None,  # Special handling
}

FOOTPRINT_TOLERANCES = {
    ElementType.PAD: 0.05,      # Tighter for footprints
    ElementType.GR_LINE: 0.1,
}
```

### Phase 2: Add Debug Mode to SVG Renderer

**File:** `tools/kicad/kicad_pcb_svg.py`

Add `debug_mode: bool = False` parameter to `render_pcb_svg()`. When True, wrap elements in groups with `data-element-type` attributes:

```xml
<g data-element-type="track">
  <path d="..." />
</g>
<g data-element-type="zone">
  <path d="..." />
</g>
```

**Changes at lines ~1168-1260:**
- Wrap `filled_elements` loop with element type groups
- Wrap `circle_elements` with via/pad classification
- Wrap `stroked_elements` with track/gr-line classification

### Phase 3: Create Detailed Comparison and Reporting

**comparator.py** - Return structured results:

```python
@dataclass
class ElementComparison:
    element_type: ElementType
    our_count: int
    ref_count: int
    exact_matches: int
    tolerance_matches: int
    unmatched_ours: int
    unmatched_ref: int
    worst_error_mm: float

@dataclass
class ComparisonResult:
    board_name: str
    layer: str
    passed: bool
    overall_match_pct: float
    element_results: dict[ElementType, ElementComparison]

def compare_svgs(our_svg: str, ref_svg: str, tolerances: dict) -> ComparisonResult:
    # Extract elements by type from both SVGs
    # Compare each type with its specific tolerance
    # Return detailed breakdown
```

**report_generator.py** - Generate reports in output folder:

```python
def generate_reports(result: ComparisonResult, output_dir: Path) -> None:
    # Generate {board}_{layer}_report.json
    # Generate {board}_{layer}_report.md
```

**Report structure (JSON):**
```json
{
  "board": "speedy",
  "layer": "F.Cu",
  "passed": false,
  "overall_match_pct": 78.5,
  "elements": {
    "track": {"count": 7494, "matched": 7480, "tolerance_mm": 0.1, "worst_error_mm": 0.08},
    "zone": {"count": 52, "matched": 40, "tolerance_mm": 0.5, "worst_error_mm": 1.2},
    "pad": {"count": 533, "matched": 533, "tolerance_mm": 0.1, "worst_error_mm": 0.0}
  }
}
```

### Phase 4: Update Test Files

**test_board_svg.py:**
- Import from `svg_comparison` module
- Use `compare_svgs()` with `BOARD_TOLERANCES`
- Call `generate_reports()` for every test (pass or fail)
- Remove `SKIP_TESTS` for speedy/taillight (let them run and report)

**test_footprint_svg.py:**
- Use `FOOTPRINT_TOLERANCES` (tighter)
- Generate reports per footprint

### Phase 5: Address Problem Boards

**Speedy (zone/mask/pad issues):**
- Run with new reporting to identify exactly which element types fail
- Zone tolerance at 0.5mm with 85% threshold (existing)
- Investigate mask expansion in pad rendering

**Taillight (Unicode issue):**
- Classify text elements separately
- For unsupported glyphs, either:
  - Skip text comparison for those elements
  - Document in report as known limitation

---

## Files to Modify

| File | Changes |
|------|---------|
| `tools/kicad/kicad_pcb_svg.py` | Add `debug_mode` param, wrap elements in typed groups |
| `tools/kicad/tests/test_board_svg.py` | Use new comparison module, generate reports |
| `tools/kicad/tests/test_footprint_svg.py` | Use new comparison module with tighter tolerances |
| `tools/kicad/REQUIREMENTS.md` | Update REQ-KICAD-030 with per-element tolerances |

## New Files

| File | Purpose |
|------|---------|
| `tests/svg_comparison/__init__.py` | Package exports |
| `tests/svg_comparison/element_types.py` | ElementType enum |
| `tests/svg_comparison/tolerances.py` | Tolerance configs |
| `tests/svg_comparison/coordinate_extractor.py` | Refactored from test_board_svg.py |
| `tests/svg_comparison/comparator.py` | Main comparison logic |
| `tests/svg_comparison/report_generator.py` | JSON/Markdown report generation |

---

## Success Criteria

1. All existing passing tests continue to pass
2. Error reports generated in `test_cases/svg/board/output/{board}/` for each layer
3. Reports show breakdown by element type with actual error measurements
4. Speedy/taillight run without skip, generate detailed reports showing specific failures
5. Footprint tests use tighter tolerances (0.05-0.1mm vs 0.5mm for boards)

## Execution Order

1. Create `svg_comparison/` module with element types and tolerances
2. Add `debug_mode` to `render_pcb_svg()`
3. Implement coordinate extraction by element type
4. Implement comparison logic with per-type tolerances
5. Implement report generation
6. Update `test_board_svg.py` to use new module
7. Update `test_footprint_svg.py` with tighter tolerances
8. Run tests, analyze speedy/taillight reports
9. Iterate on tolerances based on actual measurements
