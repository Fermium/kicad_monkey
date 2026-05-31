# KiCad Footprint SVG Implementation Status

## Overview

Implementing `KiCadFootprint.to_svg()` to match KiCad CLI's SVG output.

## Files

- `kicad_footprint.py` - Added `to_svg()` method
- `kicad_footprint_svg.py` - SVG rendering implementation
- `tests/generate_svg_references.py` - Script to generate reference SVGs using kicad-cli
- `tests/test_footprint_svg.py` - Pytest comparing our output to references
- `tests/test_cases/svg/footprints/input/` - 106 test footprints
- `tests/test_cases/svg/footprints/reference_output/` - 517 KiCad CLI reference SVGs
- `tests/test_cases/svg/footprints/output/` - Our generated SVGs for comparison

## Current Status: 100% Pass Rate

**Test Results:** 108 passed, 0 failed, 2 skipped (out of 110 tests)

### Completed
- [x] Reference SVG generator using kicad-cli
- [x] Basic `to_svg()` implementation with layer filtering
- [x] Wildcard layer handling (`*.Cu`, `*.Mask`, `*.Paste`)
- [x] SMD rectangular pad rendering as filled paths
- [x] Rectangle corner order matching KiCad (bottom-left, top-left, top-right, bottom-right)
- [x] Oval pad rendering as thick stroked segment (ThickSegment)
- [x] Circle pad rendering as native SVG `<circle>` elements
- [x] Roundrect pad rendering with KiCad's exact arc approximation algorithm
- [x] Full footprint bounding box calculation (including text elements)
- [x] Test infrastructure with coordinate normalization

### All Tests Pass

No rendering differences remain. Our implementation matches KiCad CLI's SVG output exactly.

### Skipped (no F.Cu content)
- NHD-3.12-25664UCY2 (display footprint, no copper pads)
- TBA15-11EGWA (no copper pads)

## KiCad Source Code Reference

Key source files consulted from `C:\eli\kicad_build\kicad`:

- `common/plotters/SVG_plotter.cpp` - SVG output format details
- `common/plotters/PS_plotter.cpp` - FlashPadOval, FlashPadRect, FlashPadCircle implementations
- `pcbnew/plot_brditems_plotter.cpp` - Pad plotting logic
- `pcbnew/pcb_plotter.cpp` - Footprint SVG export, ComputeBoundingBox usage
- `pcbnew/board.cpp` - BOARD::ComputeBoundingBox implementation
- `pcbnew/footprint.cpp` - FOOTPRINT::GetBoundingBox implementation
- `pcbnew/pcbnew_jobs_handler.cpp` - doFpExportSvg implementation

### Key Insights from Source

1. **Bounding Box**: KiCad uses the full footprint bounding box (all layers, including text) for SVG viewBox
2. **Oval Pads**: Rendered using `ThickSegment` - a stroked line with round caps
3. **Rectangle Order**: Corners start at bottom-left, go counterclockwise (up first)
4. **Circle Pads**: Rendered as native SVG `<circle>` elements (filled, no stroke)
5. **Roundrect Pads**: Rendered using `TransformRoundChamferedRectToPolygon()` → `CornerListToPolygon()` - polygon with rounded corners
6. **Corner Radius**: For roundrect pads, `radius = min(width, height) * roundrect_rratio` (default rratio = 0.25)
7. **Arc Segment Count**: For standalone footprints, uses `ARC_HIGH_DEF = 0.005mm` error tolerance
8. **Arc Algorithm**: `GetArcToSegmentCount()` calculates segments from error/radius ratio, minimum 16 segments per 360°
9. **Arc Point Distribution**: `CornerListToPolygon()` uses special first/last segment equalization (lines 284-300)
   - Calculates `lastSeg = endAngle % angDelta`
   - Starts arc at `angPosStart = (angDelta + lastSeg) / 2` to ensure equal first/last segments
   - Includes explicit edge points at 0° and 90° of each corner arc

## Test Commands

```bash
# Run all SVG comparison tests
uv run pytest tools/kicad/tests/test_footprint_svg.py -v

# Run just the comparison tests (fastest)
uv run pytest tools/kicad/tests/test_footprint_svg.py::TestFootprintSvgComparison -v

# Regenerate reference SVGs (requires kicad-cli)
uv run python tools/kicad/tests/generate_svg_references.py
```
