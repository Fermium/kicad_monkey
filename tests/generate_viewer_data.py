"""
Generate board_list.json and viewer.html for the SVG comparison viewer.

Scans the reference_output and output folders and runs comparison tests
to populate the viewer with pass/fail status for each board/layer.
"""

import json
import re
import logging
from pathlib import Path

log = logging.getLogger(__name__)

TEST_CASES_DIR = Path(__file__).parent / "test_cases" / "svg" / "board"
INPUT_DIR = TEST_CASES_DIR / "input"
REFERENCE_DIR = TEST_CASES_DIR / "reference_output"
OUTPUT_DIR = TEST_CASES_DIR / "output"

# Standard layers
TEST_LAYERS = [
    "All Layers",  # Combined view first
    "F.Cu", "B.Cu", "In1.Cu", "In2.Cu",
    "F.SilkS", "B.SilkS", "F.Fab", "B.Fab",
    "F.Mask", "B.Mask", "F.Paste", "B.Paste",
    "F.CrtYd", "B.CrtYd", "Edge.Cuts",
    "User.Drawings", "User.Comments",
]


def extract_path_coords(path_d: str, precision: int = 2):
    """Extract coordinate pairs from SVG path data."""
    coords = []
    numbers = re.findall(r'-?\d+\.?\d*', path_d)
    for i in range(0, len(numbers) - 1, 2):
        x = round(float(numbers[i]), precision)
        y = round(float(numbers[i + 1]), precision)
        coords.append((x, y))
    return coords


def extract_paths_from_svg(svg_content: str):
    """Extract all path d= attributes from SVG."""
    pattern = r'd="([^"]+)"'
    return re.findall(pattern, svg_content)


def compare_svgs(our_svg: str, ref_svg: str, tolerance: float = 0.5) -> tuple[bool, str]:
    """Compare two SVGs and return (match, message)."""
    our_paths = extract_paths_from_svg(our_svg)
    ref_paths = extract_paths_from_svg(ref_svg)

    # Aggregate all coordinates
    our_raw_coords = []
    for path in our_paths:
        our_raw_coords.extend(extract_path_coords(path))

    ref_raw_coords = []
    for path in ref_paths:
        ref_raw_coords.extend(extract_path_coords(path))

    # Center coordinates
    def center_coords(coords, precision=2):
        if not coords:
            return set()
        min_x = min(c[0] for c in coords)
        min_y = min(c[1] for c in coords)
        return {(round(x - min_x, precision), round(y - min_y, precision)) for x, y in coords}

    our_all_coords = center_coords(our_raw_coords)
    ref_all_coords = center_coords(ref_raw_coords)

    if our_all_coords == ref_all_coords:
        return True, f"Exact match ({len(our_all_coords)} coords)"

    # Calculate difference
    only_in_ours = our_all_coords - ref_all_coords
    only_in_ref = ref_all_coords - our_all_coords

    if len(only_in_ours) <= 5 and len(only_in_ref) <= 5:
        return True, f"Minor diff ({len(only_in_ours)}/{len(only_in_ref)})"

    # Tolerance matching
    matched_ours = set()
    matched_ref = set()

    for our_coord in only_in_ours:
        for ref_coord in only_in_ref:
            if (abs(our_coord[0] - ref_coord[0]) <= tolerance and
                abs(our_coord[1] - ref_coord[1]) <= tolerance):
                matched_ours.add(our_coord)
                matched_ref.add(ref_coord)
                break

    total_unique = len(our_all_coords | ref_all_coords)
    exact_matches = len(our_all_coords & ref_all_coords)
    tolerance_matches = len(matched_ours)
    total_matched = exact_matches + tolerance_matches
    match_pct = total_matched / total_unique * 100 if total_unique > 0 else 100

    if match_pct >= 85:
        return True, f"{match_pct:.1f}% match"

    return False, f"{match_pct:.1f}% match"


def generate_html(boards_data: dict, output_path: Path):
    """Generate the viewer HTML with embedded data."""

    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KiCad Board SVG Comparison Viewer</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e; color: #eee; padding: 20px;
        }
        h1 { text-align: center; margin-bottom: 20px; color: #00d4ff; }
        .controls {
            display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap;
            align-items: center; background: #16213e; padding: 15px; border-radius: 8px;
        }
        .controls label { font-weight: 500; }
        .controls select {
            padding: 8px 12px; border: 1px solid #444; border-radius: 4px;
            background: #0f3460; color: #eee; font-size: 14px;
        }
        .status { margin-left: auto; padding: 8px 16px; border-radius: 4px; font-weight: 500; }
        .status.pass { background: #0d7a3a; }
        .status.fail { background: #9a2d2d; }
        .status.visual { background: #1e6091; }
        .status.missing { background: #666; }
        .comparison { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .panel { background: #16213e; border-radius: 8px; overflow: hidden; }
        .panel-header {
            padding: 12px 16px; background: #0f3460; font-weight: 600;
            display: flex; justify-content: space-between; align-items: center;
        }
        .panel-header .coords { font-size: 12px; color: #888; }
        .svg-container {
            padding: 20px; min-height: 400px; display: flex;
            align-items: center; justify-content: center; background: #fff;
        }
        .svg-container svg { max-width: 100%; max-height: 600px; }
        .svg-container.no-svg { color: #666; background: #1a1a2e; }
        .svg-container img { max-width: 100%; max-height: 600px; }
        .stats {
            margin-top: 20px; padding: 15px; background: #16213e; border-radius: 8px;
        }
        .stats h3 { margin-bottom: 10px; color: #00d4ff; }
        .stats-grid {
            display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px;
        }
        .stat-item { padding: 10px; background: #0f3460; border-radius: 4px; }
        .stat-label { font-size: 12px; color: #888; }
        .stat-value { font-size: 18px; font-weight: 600; }
        .layer-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; }
        .layer-btn {
            padding: 6px 12px; border: none; border-radius: 4px;
            cursor: pointer; font-size: 13px; transition: all 0.2s;
        }
        .layer-btn.pass { background: #0d7a3a; color: white; }
        .layer-btn.fail { background: #9a2d2d; color: white; }
        .layer-btn.visual { background: #1e6091; color: white; }
        .layer-btn.missing { background: #444; color: #ccc; }
        .layer-btn:hover { transform: scale(1.05); }
        .layer-btn.active { outline: 2px solid #00d4ff; outline-offset: 2px; }
    </style>
</head>
<body>
    <h1>KiCad Board SVG Comparison Viewer</h1>
    <div class="controls">
        <label>Board: <select id="board-select"></select></label>
        <label>Layer: <select id="layer-select"></select></label>
        <div class="status" id="status">Select a board</div>
    </div>
    <div class="layer-list" id="layer-buttons"></div>
    <div class="comparison">
        <div class="panel">
            <div class="panel-header">
                <span>Our Output</span>
                <span class="coords" id="our-coords"></span>
            </div>
            <div class="svg-container" id="our-svg">Select a board and layer</div>
        </div>
        <div class="panel">
            <div class="panel-header">
                <span>KiCad Reference</span>
                <span class="coords" id="ref-coords"></span>
            </div>
            <div class="svg-container" id="ref-svg">Select a board and layer</div>
        </div>
    </div>
    <div class="stats">
        <h3>Test Summary</h3>
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-label">Total Boards</div>
                <div class="stat-value" id="total-boards">-</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Total Tests</div>
                <div class="stat-value" id="total-tests">-</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Passed</div>
                <div class="stat-value" id="passed-tests" style="color: #4ade80;">-</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Failed</div>
                <div class="stat-value" id="failed-tests" style="color: #f87171;">-</div>
            </div>
        </div>
    </div>

    <script>
        // Embedded test data
        const testData = ''' + json.dumps(boards_data, indent=2) + ''';

        let currentBoard = null;
        let currentLayer = null;

        function updateDisplay() {
            if (!currentBoard || !currentLayer) return;
            const board = testData[currentBoard];
            if (!board) return;

            const layerSafe = currentLayer.replace('.', '_').replace(' ', '_');
            const ourPath = `output/${currentBoard}/${currentBoard}__${layerSafe}.svg`;
            const refPath = `reference_output/${currentBoard}/${currentBoard}__${layerSafe}.svg`;

            // Use img tags which work with file:// protocol
            document.getElementById('our-svg').innerHTML =
                `<img src="${ourPath}" onerror="this.parentElement.innerHTML='No output SVG'" alt="Our output">`;
            document.getElementById('ref-svg').innerHTML =
                `<img src="${refPath}" onerror="this.parentElement.innerHTML='No reference SVG'" alt="Reference">`;

            // Update status
            const result = board.layers[currentLayer];
            const status = document.getElementById('status');
            if (result === 'pass') {
                status.className = 'status pass';
                status.textContent = 'PASSED';
            } else if (result === 'fail') {
                status.className = 'status fail';
                status.textContent = 'FAILED';
            } else if (result === 'visual') {
                status.className = 'status visual';
                status.textContent = 'VISUAL ONLY';
            } else {
                status.className = 'status missing';
                status.textContent = result || 'Missing';
            }

            updateLayerButtons();
        }

        function updateLayerButtons() {
            const container = document.getElementById('layer-buttons');
            const board = testData[currentBoard];
            if (!board) return;

            container.innerHTML = '';
            for (const layer of board.layerOrder) {
                const btn = document.createElement('button');
                btn.className = 'layer-btn';
                btn.textContent = layer;

                const result = board.layers[layer];
                if (result === 'pass') btn.classList.add('pass');
                else if (result === 'fail') btn.classList.add('fail');
                else if (result === 'visual') btn.classList.add('visual');
                else btn.classList.add('missing');

                if (layer === currentLayer) btn.classList.add('active');

                btn.onclick = () => {
                    currentLayer = layer;
                    document.getElementById('layer-select').value = layer;
                    updateDisplay();
                };
                container.appendChild(btn);
            }
        }

        function populateBoardSelect() {
            const select = document.getElementById('board-select');
            const boards = Object.keys(testData).sort();
            for (const board of boards) {
                const opt = document.createElement('option');
                opt.value = board;
                opt.textContent = board;
                select.appendChild(opt);
            }
            if (boards.length > 0) {
                currentBoard = boards[0];
                select.value = currentBoard;
                populateLayerSelect();
            }
        }

        function populateLayerSelect() {
            const select = document.getElementById('layer-select');
            select.innerHTML = '';
            const board = testData[currentBoard];
            if (!board) return;

            for (const layer of board.layerOrder) {
                const opt = document.createElement('option');
                opt.value = layer;
                opt.textContent = layer;
                select.appendChild(opt);
            }
            if (board.layerOrder.length > 0) {
                currentLayer = board.layerOrder[0];
                select.value = currentLayer;
            }
        }

        function updateStats() {
            const boards = Object.keys(testData);
            let total = 0, passed = 0, failed = 0;

            for (const board of boards) {
                for (const result of Object.values(testData[board].layers)) {
                    if (result === 'visual') continue;  // Don't count visual-only
                    total++;
                    if (result === 'pass') passed++;
                    else if (result === 'fail') failed++;
                }
            }

            document.getElementById('total-boards').textContent = boards.length;
            document.getElementById('total-tests').textContent = total;
            document.getElementById('passed-tests').textContent = passed;
            document.getElementById('failed-tests').textContent = failed;
        }

        // Event listeners
        document.getElementById('board-select').addEventListener('change', (e) => {
            currentBoard = e.target.value;
            populateLayerSelect();
            updateDisplay();
        });

        document.getElementById('layer-select').addEventListener('change', (e) => {
            currentLayer = e.target.value;
            updateDisplay();
        });

        // Initialize
        populateBoardSelect();
        updateStats();
        updateDisplay();
    </script>
</body>
</html>'''

    output_path.write_text(html_content)
    log.info(f"Generated {output_path}")


def main():
    """Generate board_list.json and viewer.html."""
    logging.basicConfig(level=logging.INFO)

    boards_data = {}

    # Find all board folders in reference_output
    if not REFERENCE_DIR.exists():
        log.error(f"Reference directory not found: {REFERENCE_DIR}")
        return

    board_folders = sorted([f for f in REFERENCE_DIR.iterdir() if f.is_dir()])
    log.info(f"Found {len(board_folders)} board folders")

    for board_folder in board_folders:
        board_name = board_folder.name
        layers = {}
        layer_order = []

        for layer in TEST_LAYERS:
            layer_safe = layer.replace(".", "_").replace(" ", "_")
            ref_path = board_folder / f"{board_name}__{layer_safe}.svg"

            if ref_path.exists():
                layer_order.append(layer)

                # "All Layers" is visual reference only - don't test
                if layer == "All Layers":
                    layers[layer] = "visual"
                    continue

                # Check if our output exists
                out_path = OUTPUT_DIR / board_name / f"{board_name}__{layer_safe}.svg"

                if out_path.exists():
                    # Compare the SVGs
                    try:
                        ref_svg = ref_path.read_text()
                        our_svg = out_path.read_text()
                        match, msg = compare_svgs(our_svg, ref_svg)
                        layers[layer] = "pass" if match else "fail"
                    except Exception as e:
                        log.warning(f"Error comparing {board_name}/{layer}: {e}")
                        layers[layer] = "error"
                else:
                    layers[layer] = "missing"

        if layer_order:
            boards_data[board_name] = {
                "layers": layers,
                "layerOrder": layer_order,
            }
            passed = sum(1 for v in layers.values() if v == "pass")
            total = len(layers)
            log.info(f"  {board_name}: {passed}/{total} layers pass")

    # Write JSON
    json_path = TEST_CASES_DIR / "board_list.json"
    with open(json_path, "w") as f:
        json.dump({"boards": boards_data}, f, indent=2)

    # Write HTML with embedded data
    html_path = TEST_CASES_DIR / "viewer.html"
    generate_html(boards_data, html_path)

    # Summary (exclude "visual" from counts)
    total_tests = sum(
        sum(1 for v in b["layers"].values() if v != "visual")
        for b in boards_data.values()
    )
    passed_tests = sum(
        sum(1 for v in b["layers"].values() if v == "pass")
        for b in boards_data.values()
    )

    log.info(f"\nGenerated {json_path}")
    log.info(f"Generated {html_path}")
    log.info(f"Total: {len(boards_data)} boards, {total_tests} tests, {passed_tests} passed ({100*passed_tests/total_tests:.1f}%)")


if __name__ == "__main__":
    main()
