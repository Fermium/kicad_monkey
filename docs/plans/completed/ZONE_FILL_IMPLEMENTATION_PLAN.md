# KiCad Zone Fill - Python Implementation Plan

## Current Status (2025-12-13)

**SVG Rendering Status**: 663/663 tests passing with current tolerance-based matching.

**Zone Fill Implementation**: Phase 1 & 2 COMPLETE
- `kicad_zone_utils.py` - PolygonSet wrapper for Clipper2/pyclipr ✅
- `kicad_zone_filler.py` - Zone fill algorithm skeleton ✅
- Boolean operations (subtract, add, intersection, xor) ✅
- Inflate/deflate with corner strategies ✅
- Track/circle/segment polygon generation ✅
- Basic zone fill working (simple zones with no components) ✅

**Remaining Issue**: Zone fills in stored `.kicad_pcb` files may differ from KiCad CLI output because KiCad CLI re-computes zone fills during export (with `--check-zones` flag). To achieve exact matching, we need to implement zone fill computation in Python.

**Recent Fixes Completed**:
- Arc direction now matches KiCad exactly (native SVG `A` command with correct start/end swapping)
- Bezier rendering uses native SVG `C` command
- Unfilled polygons render as stroked closed paths (not filled capsules)

## Objective

Implement a Python zone fill algorithm that produces **100% identical output** to KiCad's `kicad-cli` zone fill computation, enabling our SVG renderer to match KiCad CLI exactly.

## KiCad Zone Fill Algorithm Analysis

### Source Files Analyzed
- `pcbnew/zone_filler.cpp` - Main fill orchestrator (~2500 lines)
- `pcbnew/zone.cpp` - Zone outline smoothing
- `libs/kimath/src/geometry/shape_poly_set.cpp` - Clipper2 wrapper

### Algorithm Type
**NOT flood-fill** - KiCad uses polygon boolean operations via Clipper2:
- Union, Subtract, Intersect operations
- Inflate/Deflate (morphological operations)
- All computation done on polygon sets, not pixels

### Core Algorithm: `fillCopperZone()` (zone_filler.cpp:1916)

```
INPUT: aSmoothedOutline (zone boundary with corner smoothing applied)

1. Initialize
   - half_min_width = zone.min_thickness / 2
   - epsilon = 0.001mm (prevents floating-point edge cases)
   - aFillPolys = aSmoothedOutline

2. Knockout Thermal Reliefs
   - For each thermal-connected pad, create relief pattern
   - aFillPolys.BooleanSubtract(thermalReliefs)

3. Build Clearance Holes
   - For each non-connected pad/track/via:
     - Get clearance from DRC rules
     - Expand item shape by clearance
     - Add to clearanceHoles polygon set

4. Build Thermal Spokes
   - For each thermal-connected pad:
     - Create 4 cardinal spokes (polygon rectangles)
     - Test point at spoke index 3 for hit-testing

5. Test Spokes Against Zone Body
   - Create testAreas = aFillPolys - clearanceHoles
   - Deflate testAreas by (half_min_width - epsilon) [CHAMFER strategy]
   - Inflate testAreas by (half_min_width - epsilon) [CHAMFER strategy]
   - For each spoke:
     - If testPt inside testAreas → add spoke to aFillPolys
     - Else if testPt inside another spoke AND mutual → add spoke

6. Subtract Clearance Holes
   - aFillPolys.BooleanSubtract(clearanceHoles)

7. Prune Thin Features (Minimum Width)
   - Deflate by (half_min_width - epsilon) [CHAMFER_ALL_CORNERS]
   - Remove islands where max(bbox) < min_thickness
   - Apply hatch pattern if configured (while deflated)
   - OR connect_nearby_polys() for solid fill
   - Inflate by (half_min_width - epsilon) [ROUND_ALL_CORNERS]

8. Final Trimming
   - aFillPolys.BooleanIntersection(aMaxExtents)  // trim to zone outline
   - aFillPolys.BooleanSubtract(clearanceHoles)   // re-trim clearances
   - subtractHigherPriorityZones()                // respect zone priority

9. Fracture
   - aFillPolys.Fracture()  // prepare for rendering

OUTPUT: aFillPolys (filled zone polygon set)
```

### Key Parameters

| Parameter | Source | Purpose |
|-----------|--------|---------|
| `min_thickness` | Zone property | Minimum copper width |
| `clearance` | DRC rules | Pad/track clearances |
| `thermal_gap` | Zone property | Thermal relief gap |
| `spoke_width` | Zone property | Thermal spoke width |
| `corner_smoothing` | Zone property | Fillet/chamfer radius |
| `m_maxError` | Design settings | Arc approximation accuracy |

### Clipper2 Operations Used

| Operation | KiCad Method | Clipper2 Equivalent |
|-----------|--------------|---------------------|
| Union | `BooleanAdd()` | `ClipType::Union` |
| Subtract | `BooleanSubtract()` | `ClipType::Difference` |
| Intersect | `BooleanIntersection()` | `ClipType::Intersection` |
| Inflate | `Inflate()` | `ClipperOffset` with positive amount |
| Deflate | `Deflate()` | `ClipperOffset` with negative amount |

### Corner Strategies

| Strategy | Clipper2 JoinType | Usage |
|----------|-------------------|-------|
| `CHAMFER_ALL_CORNERS` | `JoinType::Square` | Deflate (fast) |
| `ROUND_ALL_CORNERS` | `JoinType::Round` | Inflate (final) |
| `ALLOW_ACUTE_CORNERS` | `JoinType::Miter` (limit=10) | Not used in fill |

---

## Python Implementation Plan

### Phase 1: Dependencies & Infrastructure

**Required Libraries:**
```python
# pyproject.toml additions
"pyclipr",      # Clipper2 Python bindings (boolean ops, offset)
"shapely",      # Already have - for polygon utilities
```

**New Module Structure:**
```
tools/kicad/
├── kicad_zone_filler.py      # Main zone fill algorithm
├── kicad_zone_clearances.py  # Clearance hole computation
├── kicad_zone_thermals.py    # Thermal relief & spoke generation
└── kicad_zone_utils.py       # Polygon utilities (inflate/deflate)
```

### Phase 2: Polygon Operations Wrapper

Create `kicad_zone_utils.py` to wrap pyclipr with KiCad-compatible API:

```python
import pyclipr
from enum import Enum
from typing import List, Tuple

class CornerStrategy(Enum):
    CHAMFER_ALL_CORNERS = "chamfer"
    ROUND_ALL_CORNERS = "round"
    ALLOW_ACUTE_CORNERS = "miter"

class PolygonSet:
    """KiCad SHAPE_POLY_SET equivalent."""

    def __init__(self, polygons: List[List[Tuple[float, float]]] = None):
        self.polygons = polygons or []

    def boolean_subtract(self, other: 'PolygonSet') -> 'PolygonSet':
        """Clipper2 difference operation."""
        pc = pyclipr.Clipper()
        pc.addPaths(self.polygons, pyclipr.Subject)
        pc.addPaths(other.polygons, pyclipr.Clip)
        result = pc.execute(pyclipr.Difference, pyclipr.FillRule.EvenOdd)
        return PolygonSet(result)

    def boolean_add(self, other: 'PolygonSet') -> 'PolygonSet':
        """Clipper2 union operation."""
        pc = pyclipr.Clipper()
        pc.addPaths(self.polygons, pyclipr.Subject)
        pc.addPaths(other.polygons, pyclipr.Clip)
        result = pc.execute(pyclipr.Union, pyclipr.FillRule.EvenOdd)
        return PolygonSet(result)

    def boolean_intersection(self, other: 'PolygonSet') -> 'PolygonSet':
        """Clipper2 intersection operation."""
        pc = pyclipr.Clipper()
        pc.addPaths(self.polygons, pyclipr.Subject)
        pc.addPaths(other.polygons, pyclipr.Clip)
        result = pc.execute(pyclipr.Intersection, pyclipr.FillRule.EvenOdd)
        return PolygonSet(result)

    def inflate(self, amount: float, strategy: CornerStrategy, max_error: float) -> 'PolygonSet':
        """Clipper2 offset (inflate) operation."""
        po = pyclipr.ClipperOffset()

        join_type = {
            CornerStrategy.CHAMFER_ALL_CORNERS: pyclipr.JoinType.Square,
            CornerStrategy.ROUND_ALL_CORNERS: pyclipr.JoinType.Round,
            CornerStrategy.ALLOW_ACUTE_CORNERS: pyclipr.JoinType.Miter,
        }[strategy]

        po.addPaths(self.polygons, join_type, pyclipr.EndType.Polygon)
        po.arcTolerance = max_error
        result = po.execute(amount)
        return PolygonSet(result)

    def deflate(self, amount: float, strategy: CornerStrategy, max_error: float) -> 'PolygonSet':
        """Deflate = inflate with negative amount."""
        return self.inflate(-amount, strategy, max_error)
```

### Phase 3: Zone Fill Algorithm

Create `kicad_zone_filler.py`:

```python
class ZoneFiller:
    """Python implementation of KiCad's zone fill algorithm."""

    def __init__(self, pcb: 'KiCadPcb'):
        self.pcb = pcb
        self.max_error = pcb.design_settings.get('max_error', 0.005)  # 5 microns

    def fill_zone(self, zone: 'Zone', layer: str) -> PolygonSet:
        """Fill a single zone on a single layer."""

        # Step 1: Get smoothed outline
        smoothed_outline = self._build_smoothed_outline(zone)
        max_extents = smoothed_outline.clone()

        # Step 2: Initialize fill
        fill_polys = smoothed_outline.clone()

        # Step 3: Knockout thermal reliefs
        thermal_pads, no_connection_pads = self._categorize_pads(zone, layer)
        thermal_reliefs = self._build_thermal_reliefs(zone, layer, thermal_pads)
        fill_polys = fill_polys.boolean_subtract(thermal_reliefs)

        # Step 4: Build clearance holes
        clearance_holes = self._build_clearance_holes(zone, layer, no_connection_pads)

        # Step 5: Build and test thermal spokes
        spokes = self._build_thermal_spokes(zone, layer, thermal_pads)
        test_areas = fill_polys.boolean_subtract(clearance_holes)

        # Min-width pruning for spoke testing
        half_min_width = zone.min_thickness / 2
        epsilon = 0.001  # mm

        if half_min_width - epsilon > epsilon:
            test_areas = test_areas.deflate(
                half_min_width - epsilon,
                CornerStrategy.CHAMFER_ALL_CORNERS,
                self.max_error
            )
            test_areas = test_areas.inflate(
                half_min_width - epsilon,
                CornerStrategy.CHAMFER_ALL_CORNERS,
                self.max_error
            )

        # Test spokes and add valid ones
        for spoke in spokes:
            test_pt = spoke.points[3]  # Test point at index 3
            if test_areas.contains(test_pt):
                fill_polys.add_outline(spoke)
                continue
            # Check mutual containment with other spokes
            for other in spokes:
                if other is not spoke:
                    if other.contains(test_pt) and spoke.contains(other.points[3]):
                        fill_polys.add_outline(spoke)
                        break

        # Step 6: Subtract clearance holes
        fill_polys = fill_polys.boolean_subtract(clearance_holes)

        # Step 7: Min-width pruning
        if half_min_width - epsilon > epsilon:
            fill_polys = fill_polys.deflate(
                half_min_width - epsilon,
                CornerStrategy.CHAMFER_ALL_CORNERS,
                self.max_error
            )

            # Remove tiny islands
            fill_polys = self._remove_small_islands(fill_polys, zone.min_thickness)

            # Connect nearby polygons (for solid fill)
            fill_polys = self._connect_nearby_polys(fill_polys, zone.min_thickness)

            # Re-inflate
            fill_polys = fill_polys.inflate(
                half_min_width - epsilon,
                CornerStrategy.ROUND_ALL_CORNERS,
                self.max_error
            )

        # Step 8: Final trimming
        fill_polys = fill_polys.boolean_intersection(max_extents)
        fill_polys = fill_polys.boolean_subtract(clearance_holes)

        # Step 9: Subtract higher-priority zones
        fill_polys = self._subtract_higher_priority_zones(zone, layer, fill_polys)

        return fill_polys
```

### Phase 4: Clearance Computation

Create `kicad_zone_clearances.py`:

```python
def build_clearance_holes(zone, layer, pcb) -> PolygonSet:
    """Build clearance polygons for all items that need clearance from zone."""
    holes = PolygonSet()

    # Pad clearances
    for footprint in pcb.footprints:
        for pad in footprint.pads:
            if not pad.on_layer(layer):
                continue
            if pad.net == zone.net:
                continue  # Same net - no clearance

            clearance = get_pad_zone_clearance(zone, pad, layer)
            pad_shape = pad.get_shape_polygon(layer)
            expanded = pad_shape.inflate(clearance, CornerStrategy.ROUND_ALL_CORNERS, 0.005)
            holes = holes.boolean_add(expanded)

    # Track clearances
    for segment in pcb.segments:
        if segment.layer != layer:
            continue
        if segment.net == zone.net:
            continue

        clearance = get_track_zone_clearance(zone, segment, layer)
        track_shape = segment_to_polygon(segment)
        expanded = track_shape.inflate(clearance, CornerStrategy.ROUND_ALL_CORNERS, 0.005)
        holes = holes.boolean_add(expanded)

    # Via clearances
    for via in pcb.vias:
        if layer not in via.layers:
            continue
        if via.net == zone.net:
            continue

        clearance = get_via_zone_clearance(zone, via, layer)
        via_shape = circle_to_polygon(via.position, via.size / 2)
        expanded = via_shape.inflate(clearance, CornerStrategy.ROUND_ALL_CORNERS, 0.005)
        holes = holes.boolean_add(expanded)

    return holes
```

### Phase 5: Thermal Spokes

Create `kicad_zone_thermals.py`:

```python
def build_thermal_spokes(zone, layer, pads) -> List[Polygon]:
    """Build thermal relief spokes for connected pads."""
    spokes = []

    for pad in pads:
        # Get thermal parameters
        spoke_width = zone.thermal_spoke_width
        gap = zone.thermal_gap

        # Get pad center and rotation
        cx, cy = pad.position
        rotation = pad.rotation

        # Create 4 cardinal spokes
        for angle in [0, 90, 180, 270]:
            spoke = create_spoke_polygon(
                cx, cy,
                spoke_width,
                gap,
                angle + rotation,
                pad.size
            )
            spokes.append(spoke)

    return spokes

def create_spoke_polygon(cx, cy, width, gap, angle, pad_size) -> Polygon:
    """Create a single thermal spoke as a polygon.

    The spoke is a rectangle extending from the pad edge outward.
    Point at index 3 is the test point for containment checking.
    """
    # Spoke length extends beyond pad
    length = max(pad_size) + gap * 2

    # Create spoke rectangle centered at origin
    half_w = width / 2
    points = [
        (-half_w, 0),           # 0: inner left
        (half_w, 0),            # 1: inner right
        (half_w, length),       # 2: outer right
        (0, length * 0.75),     # 3: TEST POINT (middle, 3/4 out)
        (-half_w, length),      # 4: outer left
    ]

    # Rotate and translate
    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    rotated = []
    for x, y in points:
        rx = x * cos_a - y * sin_a + cx
        ry = x * sin_a + y * cos_a + cy
        rotated.append((rx, ry))

    return Polygon(rotated)
```

### Phase 6: Integration with SVG Renderer

Update `kicad_pcb_svg.py` to optionally recompute zone fills:

```python
def render_pcb_svg(pcb, layers, recompute_zones=False):
    """Render PCB to SVG.

    Args:
        recompute_zones: If True, recompute zone fills to match KiCad CLI.
                        If False, use stored zone fills from file.
    """
    if recompute_zones:
        filler = ZoneFiller(pcb)
        for zone in pcb.zones:
            for layer in zone.layers:
                if layers is None or layer in layers:
                    zone.filled_polygons[layer] = filler.fill_zone(zone, layer)

    # ... rest of rendering ...
```

---

## Implementation Phases

### Phase 1: Foundation ✅ COMPLETE
- [x] Add `pyclipr` dependency to pyproject.toml
- [x] Create `kicad_zone_utils.py` with PolygonSet wrapper
- [x] Boolean operations (subtract, add, intersection, xor)
- [x] Inflate/deflate with corner strategies
- [x] Track/circle/segment polygon generation

### Phase 2: Basic Fill ✅ COMPLETE
- [x] Create `kicad_zone_filler.py` skeleton
- [x] Implement outline parsing (from zone polygons)
- [x] Implement basic fill (no thermals, no clearances)
- [x] Test against simple zone (no pads)

### Phase 3: Clearances (Next)
- [ ] Implement pad clearance computation (integrated in zone_filler.py)
- [ ] Implement track/via clearance computation
- [ ] Test against zone with obstacles (tracks, vias, pads)

### Phase 4: Thermals
- [ ] Implement thermal relief knockout (integrated in zone_filler.py)
- [ ] Implement spoke generation
- [ ] Implement spoke hit-testing
- [ ] Test against zone with thermal pads

### Phase 5: Min-Width & Polish
- [x] Implement deflate/inflate min-width pruning (basic implementation done)
- [x] Implement island removal (remove_small_islands)
- [ ] Implement connect_nearby_polys
- [ ] Implement priority zone subtraction
- [ ] Full integration testing

### Phase 6: SVG Integration
- [ ] Add `recompute_zones` option to SVG renderer
- [ ] Run fill_bad board tests
- [ ] Debug coordinate differences
- [ ] Achieve 100% match

---

## Critical Implementation Details

### 1. Coordinate Precision
KiCad uses integer coordinates in nanometers internally:
```python
# KiCad internal units: 1 nm = 1 IU
# File format uses mm
# Conversion: 1mm = 1,000,000 IU

def mm_to_iu(mm: float) -> int:
    return int(mm * 1_000_000)

def iu_to_mm(iu: int) -> float:
    return iu / 1_000_000
```

### 2. Epsilon Values
```python
EPSILON_MM = 0.001  # 1 micron - prevents floating-point edge cases
```

### 3. Arc Tolerance (max_error)
```python
# From design settings, typically 0.005mm (5 microns)
# Controls polygon approximation of curves
max_error = pcb.design_settings.get('max_error', 0.005)
```

### 4. Corner Strategy Mapping
```python
# Deflate uses CHAMFER (fast, fewer points)
# Final inflate uses ROUND (smooth, more points)
DEFLATE_STRATEGY = CornerStrategy.CHAMFER_ALL_CORNERS
INFLATE_STRATEGY = CornerStrategy.ROUND_ALL_CORNERS
```

---

## Testing Strategy

### Unit Tests
1. Boolean operations match Clipper2
2. Inflate/deflate produces correct results
3. Spoke generation creates valid polygons
4. Clearance computation matches expected values

### Integration Tests
1. Simple zone (rectangle, no obstacles) → exact match
2. Zone with single pad clearance → exact match
3. Zone with thermal connection → exact match
4. Complex zone (fill_bad test case) → exact match

### Validation
```python
def validate_zone_fill(ours: PolygonSet, reference: PolygonSet) -> bool:
    """Compare our zone fill against KiCad CLI reference."""
    # Extract all coordinates
    our_coords = set(flatten_coords(ours))
    ref_coords = set(flatten_coords(reference))

    # Check exact match
    return our_coords == ref_coords
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| pyclipr version mismatch | Coordinate differences | Pin exact version, test against KiCad's Clipper2 version |
| Floating-point precision | Rounding errors | Use integer math like KiCad, apply epsilon consistently |
| DRC rule complexity | Wrong clearances | Start with simple cases, incrementally add rule support |
| Performance | Slow for complex boards | Profile early, consider caching |

---

## References

- [pyclipr on PyPI](https://pypi.org/project/pyclipr/)
- [pyclipr on GitHub](https://github.com/drlukeparry/pyclipr)
- [Clipper2 Documentation](https://www.angusj.com/clipper2/Docs/Overview.htm)
- KiCad Source: `pcbnew/zone_filler.cpp`
- KiCad Source: `libs/kimath/src/geometry/shape_poly_set.cpp`
