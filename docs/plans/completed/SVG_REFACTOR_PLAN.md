# SVG Refactor Execution Plan

**Goal**: Refactor SVG rendering to use decentralized `to_svg()` methods while passing all existing tests.

**Approach**: Incremental changes with test validation at each phase.

**Status**: ALL PHASES COMPLETE (2025-12-25). SVG refactor finished. All element classes have get_bounds() and to_svg() methods. Deprecated modules marked.

---

## Phase 0: Foundation (COMPLETE)

- [x] Add `Bounded` protocol to `kicad_geometry.py`
- [x] Add `SvgRenderable` protocol to `kicad_geometry.py`
- [x] Add `SvgRenderContext` to `kicad_geometry.py`
- [x] Add `rotate_point()` to `kicad_geometry.py`
- [x] Add `get_arc_to_segment_count()` to `kicad_geometry.py`
- [x] Update `REQUIREMENTS.md` with REQ-KICAD-070 through 075
- [x] Create `TESTING.md`

---

## Phase 1: Split kicad_pcb_footprint.py (COMPLETE)

**Status**: COMPLETE - All classes split into individual files.

**Current state**: 857 lines, 10+ classes in one file.

**Target**: One class per file.

| Class | New File | Lines (approx) |
|-------|----------|----------------|
| Pad | `kicad_pad.py` | 130 |
| FpText | `kicad_fp_text.py` | 100 |
| Property | `kicad_property.py` | 120 |
| FpLine | `kicad_fp_line.py` | 60 |
| FpArc | `kicad_fp_arc.py` | 80 |
| FpCircle | `kicad_fp_circle.py` | 60 |
| FpRect | `kicad_fp_rect.py` | 60 |
| FpPoly | `kicad_fp_poly.py` | 70 |
| Model | `kicad_model.py` | 80 |
| EmbeddedFile | `kicad_model.py` | 50 |

**Steps**:
1. Create new files with class moved from kicad_pcb_footprint.py
2. Update imports in kicad_pcb_footprint.py to re-export from new files
3. Update imports in kicad_footprint.py
4. Run tests to verify no breakage
5. Once stable, delete classes from kicad_pcb_footprint.py (keep as re-export hub or delete entirely)

**Test checkpoint**: `uv run pytest tools/kicad/tests/ -v`

---

## Phase 2: Add get_bounds() to Footprint Elements (COMPLETE)

**Status**: COMPLETE - All element classes have get_bounds() methods.

Implement `Bounded` protocol on each element class.

| Class | Complexity | Notes |
|-------|------------|-------|
| Pad | Medium | Handle rotation, all pad shapes |
| FpText | Medium | Text bounds estimation |
| FpLine | Simple | start/end + stroke width |
| FpArc | Medium | Arc extent calculation |
| FpCircle | Simple | center + radius + stroke |
| FpRect | Simple | corners + stroke width |
| FpPoly | Simple | Point iteration |
| Property | Medium | Same as FpText |

**Steps**:
1. Add `get_bounds() -> BoundingBox` to each class
2. Move bounding box logic from `kicad_footprint_svg.py:compute_*` functions
3. Update `KiCadFootprint` to use element `get_bounds()`
4. Run tests

**Test checkpoint**: `uv run pytest tools/kicad/tests/ -v`

---

## Phase 3: Add to_svg() to Pad Class (COMPLETE)

**Status**: COMPLETE - Pad.to_svg() handles all shape types.

Start with `Pad` - the most complex element with multiple shape types.

**Current logic in kicad_footprint_svg.py**:
- `pad_to_rect_polygon()` → Pad.to_svg() for rect shape
- `pad_to_circle_polygon()` → Pad.to_svg() for circle shape
- `pad_to_oval_thick_segment()` → Pad.to_svg() for oval shape
- `pad_to_roundrect_polygon()` → Pad.to_svg() for roundrect shape
- `pad_to_rect_with_rounded_corners()` → for mask expansion

**Steps**:
1. Add `to_svg(ctx: SvgRenderContext | None = None) -> list[str]` to Pad
2. Move pad rendering logic from kicad_footprint_svg.py
3. Handle layer filtering via `ctx.layer_visible()`
4. Return SVG element strings (path, circle)
5. Test Pad.to_svg() in isolation
6. Run full test suite

**Test checkpoint**: `uv run pytest tools/kicad/tests/test_footprint_svg.py -v`

---

## Phase 4: Add to_svg() to Other Footprint Elements (COMPLETE)

**Status**: COMPLETE - All footprint element classes have to_svg() methods.

| Class | SVG Output | Notes |
|-------|------------|-------|
| FpLine | `<path d="M...L..."/>` | Stroked line |
| FpArc | `<path d="M...A..."/>` | SVG arc command |
| FpCircle | `<circle/>` or `<path/>` | Filled vs stroked |
| FpRect | `<path d="M...L...Z"/>` | 4-corner polygon |
| FpPoly | `<path d="M...L...Z"/>` | Multi-point polygon |
| FpText | `<path/>` segments | Stroke font rendering |
| Property | `<path/>` segments | Same as FpText |

**Steps**:
1. Add `to_svg()` to each class
2. Move rendering logic from kicad_footprint_svg.py
3. Test each class
4. Run full test suite after each class

**Test checkpoint**: After each class, run `uv run pytest tools/kicad/tests/test_footprint_svg.py -v`

---

## Phase 5: Update KiCadFootprint.to_svg() (COMPLETE)

**Status**: COMPLETE - KiCadFootprint.to_svg() now composes from element to_svg() calls.

Compose SVG from element `to_svg()` calls.

**Current signature** (kicad_footprint.py:370):
```python
def to_svg(self, layers=None, fill="#000000", stroke="#000000", black_and_white=True) -> str:
```

**New signature**:
```python
def to_svg(self, ctx: SvgRenderContext | None = None) -> list[str]:
```

**Steps**:
1. Create default context if None
2. Compute bounding box from all elements
3. Collect SVG elements from all children:
   ```python
   elements = []
   for pad in self.pads:
       elements.extend(pad.to_svg(ctx))
   for line in self.fp_lines:
       elements.extend(line.to_svg(ctx))
   # ... etc
   return elements
   ```
4. Add wrapper method `to_svg_document()` that builds complete SVG with header/viewBox
5. Update tests to use new API
6. Run full test suite

**Test checkpoint**: `uv run pytest tools/kicad/tests/test_footprint_svg.py -v`

---

## Phase 6: Deprecate kicad_footprint_svg.py (COMPLETE)

**Status**: COMPLETE - Module marked as deprecated, BoundingBox/rotate_point imports updated.

Once all logic is in element classes:

1. Mark functions as deprecated with warnings
2. Update any remaining callers
3. Run tests
4. Delete file (or keep as empty/minimal)

**Test checkpoint**: `uv run pytest tools/kicad/tests/ -v`

---

## Phase 7: Repeat for PCB Elements (COMPLETE)

**Status**: COMPLETE - All PCB element classes have get_bounds() and to_svg() methods.

Same pattern for board-level elements in `kicad_pcb_*.py`:

| File | Classes | Status |
|------|---------|--------|
| kicad_pcb_routing.py | Segment, Via, Arc | COMPLETE |
| kicad_pcb_graphics.py | GrText, GrLine, GrRect, GrCircle, GrArc, GrPoly, GrCurve, GrTextBox | COMPLETE |
| kicad_pcb_zone.py | Zone | COMPLETE |
| kicad_pcb_footprint.py | Footprint (embedded) | COMPLETE |

**Steps completed**:
1. [x] Add `get_bounds()` to each class
2. [x] Add `to_svg()` to each class
3. [ ] Move logic from `kicad_pcb_svg.py` (deferred to Phase 8)
4. [ ] Update `KiCadPcb.to_svg()` to compose (deferred to Phase 8)
5. [x] Run tests - 2807 passed, 21 skipped

**Test checkpoint**: `uv run pytest tools/kicad/tests/ -v` - PASS

---

## Phase 8: Deprecate kicad_pcb_svg.py (COMPLETE)

**Status**: COMPLETE - Module and key functions marked as deprecated (2025-12-25).

Deprecated functions with docstring notices and warnings:
- [x] `compute_pcb_bounding_box()` - warns to use element get_bounds() methods (REQ-KICAD-071)
- [x] `_process_footprint()` - docstring refers to Footprint.to_svg() (REQ-KICAD-072)
- [x] `_process_graphics()` - docstring refers to element to_svg() methods (REQ-KICAD-072)
- [x] Module docstring updated with deprecation notice

The `render_pcb_svg()` function remains as the primary entry point.

---

## Phase 9: Final Cleanup (COMPLETE)

**Status**: COMPLETE (2025-12-25)

- [x] Update `__init__.py` exports - Added BoundingBox, SvgRenderContext, rotate_point, GrTextBox
- [x] Update REQUIREMENTS.md - REQ-KICAD-071, 072, 074 marked IMPLEMENTED
- [x] Add `KiCadPcb.get_bounds()` method (composes from element get_bounds())
- [x] Add `KiCadPcb.to_svg_elements()` method (composes from element to_svg())
- [x] Keep `KiCadPcb.to_svg()` using render_pcb_svg() for kicad-cli compatibility
- [x] Run full test suite - 2807 passed, 21 skipped

**Note**: The `to_svg()` method continues to use the full-featured `render_pcb_svg()`
for kicad-cli compatible output. The new `to_svg_elements()` method demonstrates the
decentralized pattern but doesn't include all rendering features (drill layers, mask
expansion, stroke batching, etc.). Future work could migrate render_pcb_svg() logic
to element classes.

**Final test**: `uv run pytest tools/kicad/tests/ -v` - ALL PASS

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing tests | Run tests after each small change |
| Import cycles | Careful dependency ordering, use TYPE_CHECKING |
| Performance regression | Benchmark before/after on large boards |
| Missing edge cases | Existing test coverage should catch |

---

## Estimated Effort

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| 1: Split files | Small | None |
| 2: get_bounds() | Medium | Phase 1 |
| 3: Pad.to_svg() | Medium | Phase 2 |
| 4: Other elements to_svg() | Medium | Phase 3 |
| 5: KiCadFootprint.to_svg() | Small | Phase 4 |
| 6: Deprecate footprint_svg | Small | Phase 5 |
| 7: PCB elements | Large | Phase 6 |
| 8: Deprecate pcb_svg | Small | Phase 7 |
| 9: Cleanup | Small | Phase 8 |

---

## Success Criteria

**Footprint SVG Refactor (Phases 0-6)** - COMPLETE
- [x] All 108 footprint SVG tests pass
- [x] One class per file (REQ-KICAD-070)
- [x] All footprint elements have get_bounds() (REQ-KICAD-071)
- [x] All footprint elements have to_svg() (REQ-KICAD-072)
- [x] kicad_footprint_svg.py deprecated

**PCB SVG Refactor (Phases 7-9)** - ALL COMPLETE
- [x] All 2807 tests pass (21 skipped - expected)
- [x] No new test skips
- [x] All PCB elements have get_bounds() (REQ-KICAD-071)
- [x] All PCB elements have to_svg() (REQ-KICAD-072)
- [x] kicad_pcb_svg.py deprecated (Phase 8)
- [x] __init__.py exports updated (Phase 9)
- [x] REQUIREMENTS.md updated (Phase 9)
- [x] KiCadPcb.get_bounds() composes from element get_bounds()
- [x] KiCadPcb.to_svg_elements() composes from element to_svg()
