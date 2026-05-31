"""
Debug visualization tools for fp_filter__orthographic_projection_outline.

This module provides tools to visualize and debug the orthographic projection
process, helping identify issues with transforms, rotations, and translations.

Usage:
    python fp_filter_debug.py <footprint.kicad_mod> [options]

Options:
    --show-3d           Show 3D mesh in trimesh viewer
    --show-3d-before    Show mesh before KiCad transform
    --show-3d-after     Show mesh after KiCad transform
    --export-svg        Export SVG via KiCad CLI
    --compare           Show before/after comparison
    --all               Run all visualizations
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Setup Python path (now in kicad package)

import base64
import io
import logging
from typing import Any, cast

import numpy as np
import trimesh
import trimesh.transformations as tf
import zstandard as zstd

from .kicad_sexpr import parse_sexp

log = logging.getLogger(__name__)


# KiCad CLI path (adjust if needed)
KICAD_CLI = Path("C:/Program Files/KiCad/9.0/bin/kicad-cli.exe")


# =============================================================================
# STEP Extraction and Loading (refactored from fp_filters.py)
# =============================================================================

def extract_step_data_from_sexp(s_expr: list, step_exts=(".stp", ".step")) -> tuple[str | None, str | None]:
    """
    Extract embedded STEP data from a parsed s-expression.

    Returns:
        tuple: (base64_data, file_name) or (None, None) if not found
    """
    def walk(node):
        if isinstance(node, list):
            if node and node[0] == 'embedded_files':
                for file_node in node[1:]:
                    if isinstance(file_node, list) and file_node and file_node[0] == 'file':
                        name = None
                        data = None
                        for item in file_node[1:]:
                            if isinstance(item, list) and item and item[0] == 'name':
                                name = item[1]
                            if isinstance(item, list) and item and item[0] == 'data':
                                data = ''.join(str(x) for x in item[1:]).replace('\n', '').replace('\r', '').strip('|')
                        if name and any(str(name).lower().endswith(ext) for ext in step_exts) and data:
                            return data, str(name)
            for child in node:
                result = walk(child)
                if result[0]:
                    return result
        return None, None
    return walk(s_expr)


def decode_step_data(b64_data: str) -> bytes:
    """Decode base64 and decompress ZSTD."""
    compressed = base64.b64decode(b64_data)
    return zstd.decompress(compressed)


def load_step_mesh(step_bytes: bytes) -> trimesh.Trimesh:
    """
    Load STEP data and assemble into a single mesh.

    Returns the assembled mesh with all parts combined.
    """
    step_io = io.BytesIO(step_bytes)
    mesh_dict = cast(Any, trimesh).exchange.cascade.load_step(step_io, file_type="step")

    geometry = mesh_dict['geometry']
    nodes = mesh_dict['graph']

    # Build node transform map
    node_map = {}
    for node in nodes:
        if 'geometry' in node and 'matrix' in node:
            node_map[node['geometry']] = node['matrix']

    meshes = []
    skipped = []
    for name, part in geometry.items():
        transform = node_map.get(name, np.eye(4))
        verts = part['vertices']

        if verts.shape[1] == 2:
            verts = np.hstack([verts, np.zeros((verts.shape[0], 1))])
        elif verts.shape[1] != 3:
            skipped.append((name, verts.shape))
            continue

        verts_hom = np.hstack([verts, np.ones((verts.shape[0], 1))])
        verts_trans = (transform @ verts_hom.T).T[:, :3]
        meshes.append(trimesh.Trimesh(vertices=verts_trans, faces=part['faces']))

    if skipped:
        log.warning(f"Skipped {len(skipped)} geometries with unexpected shapes: {skipped}")

    # Fix winding
    for mesh in meshes:
        if not mesh.is_winding_consistent:
            mesh.invert()

    return trimesh.util.concatenate(meshes)


def get_model_transform_values(s_expr: list) -> dict:
    """
    Extract raw transform values from the (model ...) section.

    Returns:
        dict with 'offset', 'scale', 'rotate' as lists, and 'matrix' as 4x4 numpy array
    """
    for item in s_expr:
        if isinstance(item, list) and item and item[0] == 'model':
            offset = [0.0, 0.0, 0.0]
            scale = [1.0, 1.0, 1.0]
            rotate = [0.0, 0.0, 0.0]

            for sub in item[1:]:
                if isinstance(sub, list) and sub:
                    if sub[0] == 'offset':
                        for xyz in sub[1:]:
                            if isinstance(xyz, list) and xyz[0] == 'xyz':
                                offset = [float(x) for x in xyz[1:]]
                    elif sub[0] == 'scale':
                        for xyz in sub[1:]:
                            if isinstance(xyz, list) and xyz[0] == 'xyz':
                                scale = [float(x) for x in xyz[1:]]
                    elif sub[0] == 'rotate':
                        for xyz in sub[1:]:
                            if isinstance(xyz, list) and xyz[0] == 'xyz':
                                rotate = [float(x) for x in xyz[1:]]

            # Build transform matrix (same logic as original)
            m_scale = tf.scale_matrix(scale[0], [0, 0, 0])
            m_scale[1, 1] = scale[1]
            m_scale[2, 2] = scale[2]
            m_rot_x = tf.rotation_matrix(np.deg2rad(-rotate[0]), [1, 0, 0])
            m_rot_y = tf.rotation_matrix(np.deg2rad(-rotate[1]), [0, 1, 0])
            m_rot_z = tf.rotation_matrix(np.deg2rad(rotate[2]), [0, 0, 1])
            m_trans = tf.translation_matrix([offset[0], offset[1], offset[2]])
            matrix = tf.concatenate_matrices(m_scale, m_trans, m_rot_z, m_rot_y, m_rot_x)

            return {
                'offset': offset,
                'scale': scale,
                'rotate': rotate,
                'matrix': matrix
            }

    return {
        'offset': [0, 0, 0],
        'scale': [1, 1, 1],
        'rotate': [0, 0, 0],
        'matrix': np.eye(4)
    }


def extract_pads_from_sexp(s_expr: list) -> list[dict]:
    """
    Extract pad information from footprint s-expression.

    Returns list of dicts with 'name', 'center', 'size', 'rotation', 'shape'
    """
    pads = []
    for item in s_expr:
        if isinstance(item, list) and len(item) > 0 and item[0] == 'pad':
            pad = {
                'name': str(item[1]) if len(item) > 1 else '?',
                'center': [0, 0],
                'size': [0, 0],
                'rotation': 0,
                'shape': 'rect'
            }
            for sub in item:
                if isinstance(sub, list) and sub:
                    if sub[0] == 'at' and len(sub) >= 3:
                        pad['center'] = [float(sub[1]), float(sub[2])]
                        if len(sub) > 3:
                            pad['rotation'] = float(sub[3])
                    elif sub[0] == 'size' and len(sub) >= 3:
                        pad['size'] = [float(sub[1]), float(sub[2])]
                    elif sub[0] == 'shape':
                        pad['shape'] = str(sub[1]) if len(sub) > 1 else 'rect'
            pads.append(pad)
    return pads


# =============================================================================
# Visualization Functions
# =============================================================================

def show_mesh_3d(mesh: trimesh.Trimesh, title: str = "Mesh Viewer"):
    """Show mesh in trimesh's interactive 3D viewer."""
    log.info(f"Opening 3D viewer: {title}")
    log.info(f"  Bounds: {mesh.bounds}")
    log.info(f"  Center: {mesh.centroid}")
    log.info(f"  Vertices: {len(mesh.vertices)}, Faces: {len(mesh.faces)}")

    # Create a scene with the mesh and coordinate axes
    scene = trimesh.Scene()
    scene.add_geometry(mesh, node_name='model')

    # Add coordinate axes for reference
    axis_length = max(mesh.extents) * 0.5
    axes = trimesh.creation.axis(origin_size=axis_length * 0.1, axis_length=axis_length)
    scene.add_geometry(axes, node_name='axes')

    scene.show(title=title)


def export_kicad_svg(footprint_path: Path, output_dir: Path, layers: str = "F.Cu,B.Cu,F.Fab,B.Fab,User.1,User.2,User.Drawings,User.Comments,Eco1.User,Eco2.User") -> Path | None:
    """
    Export footprint to SVG using KiCad CLI.

    Returns path to the generated SVG, or None on failure.
    """
    if not KICAD_CLI.exists():
        log.error(f"KiCad CLI not found at {KICAD_CLI}")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    # kicad-cli expects a directory for input (library), not a single file
    # We need to copy the footprint to a temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        shutil.copy(footprint_path, tmp_path / footprint_path.name)

        cmd = [
            str(KICAD_CLI),
            "fp", "export", "svg",
            "--output", str(output_dir),
            "-l", layers,
            "--sketch-pads-on-fab-layers",
            str(tmp_path)
        ]

        log.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            log.error(f"KiCad CLI failed: {result.stderr}")
            return None

        # Find the generated SVG
        svg_name = footprint_path.stem + ".svg"
        svg_path = output_dir / svg_name
        if svg_path.exists():
            log.info(f"SVG exported to: {svg_path}")
            return svg_path
        else:
            # Try to find any SVG
            svgs = list(output_dir.glob("*.svg"))
            if svgs:
                log.info(f"SVG exported to: {svgs[0]}")
                return svgs[0]
            log.error("SVG not found after export")
            return None


def print_debug_info(s_expr: list, mesh_before: trimesh.Trimesh, mesh_after: trimesh.Trimesh, transform_values: dict):
    """Print detailed debug information about the transform process."""
    log.info("\n" + "="*80)
    log.info("DEBUG INFO: Orthographic Projection Transform")
    log.info("="*80)

    # Transform values from KiCad
    log.info("\n[KiCad Model Transform Values]")
    log.info(f"  Offset (X, Y, Z): {transform_values['offset']}")
    log.info(f"  Scale  (X, Y, Z): {transform_values['scale']}")
    log.info(f"  Rotate (X, Y, Z): {transform_values['rotate']} degrees")

    # Mesh bounds before transform
    log.info("\n[Mesh BEFORE Transform (after assembly, before KiCad transform)]")
    log.info(f"  Bounds min: {mesh_before.bounds[0]}")
    log.info(f"  Bounds max: {mesh_before.bounds[1]}")
    log.info(f"  Extents:    {mesh_before.extents}")
    log.info(f"  Centroid:   {mesh_before.centroid}")

    # Mesh bounds after transform
    log.info("\n[Mesh AFTER Transform (after KiCad transform + 1000x scale)]")
    log.info(f"  Bounds min: {mesh_after.bounds[0]}")
    log.info(f"  Bounds max: {mesh_after.bounds[1]}")
    log.info(f"  Extents:    {mesh_after.extents}")
    log.info(f"  Centroid:   {mesh_after.centroid}")

    # Pad information
    pads = extract_pads_from_sexp(s_expr)
    if pads:
        log.info(f"\n[Footprint Pads ({len(pads)} total)]")

        # Calculate pad bounds
        all_x = []
        all_y = []
        for pad in pads:
            cx, cy = pad['center']
            sx, sy = pad['size']
            all_x.extend([cx - sx/2, cx + sx/2])
            all_y.extend([cy - sy/2, cy + sy/2])

        if all_x and all_y:
            log.info(f"  Pad bounds X: [{min(all_x):.4f}, {max(all_x):.4f}]")
            log.info(f"  Pad bounds Y: [{min(all_y):.4f}, {max(all_y):.4f}]")
            log.info(f"  Pad center:   [{(min(all_x)+max(all_x))/2:.4f}, {(min(all_y)+max(all_y))/2:.4f}]")

        # Show first few pads
        for _i, pad in enumerate(pads[:5]):
            log.info(f"  Pad '{pad['name']}': center={pad['center']}, size={pad['size']}, rot={pad['rotation']}")
        if len(pads) > 5:
            log.info(f"  ... and {len(pads) - 5} more pads")

    # 2D projection bounds (what we'll use for fp_lines)
    log.info("\n[2D Projection (XY plane, Y inverted)]")
    proj_bounds_x = [mesh_after.bounds[0][0], mesh_after.bounds[1][0]]
    proj_bounds_y = [-mesh_after.bounds[1][1], -mesh_after.bounds[0][1]]  # Y inverted
    log.info(f"  Projection X: [{proj_bounds_x[0]:.4f}, {proj_bounds_x[1]:.4f}]")
    log.info(f"  Projection Y: [{proj_bounds_y[0]:.4f}, {proj_bounds_y[1]:.4f}]")
    log.info(f"  Projection center: [{(proj_bounds_x[0]+proj_bounds_x[1])/2:.4f}, {(proj_bounds_y[0]+proj_bounds_y[1])/2:.4f}]")

    log.info("\n" + "="*80)


def analyze_footprint(footprint_path: Path,
                      show_3d_before: bool = False,
                      show_3d_after: bool = False,
                      export_svg: bool = False,
                      svg_output_dir: Path | None = None):
    """
    Analyze a footprint file and optionally show visualizations.
    """
    log.info(f"\nAnalyzing: {footprint_path.name}")

    # Parse the footprint
    with open(footprint_path, encoding='utf-8') as f:
        text = f.read()
    s_expr = parse_sexp(text)

    # Extract STEP data
    b64_data, step_name = extract_step_data_from_sexp(s_expr)
    if not b64_data:
        log.warning("No embedded STEP data found")
        return

    log.info(f"Found embedded STEP: {step_name}")

    # Decode and load mesh
    step_bytes = decode_step_data(b64_data)
    mesh_raw = load_step_mesh(step_bytes)

    # Get transform values
    transform_values = get_model_transform_values(s_expr)

    # Create a copy for "before" state
    mesh_before = mesh_raw.copy()

    # Apply transforms (same as in fp_filter__orthographic_projection_outline)
    mesh_after = mesh_raw.copy()
    mesh_after.apply_scale(1000)  # STEP mm to KiCad internal units?
    mesh_after.apply_transform(transform_values['matrix'])

    # Print debug info
    print_debug_info(s_expr, mesh_before, mesh_after, transform_values)

    # Show 3D views if requested
    if show_3d_before:
        show_mesh_3d(mesh_before, f"{footprint_path.name} - BEFORE Transform")

    if show_3d_after:
        show_mesh_3d(mesh_after, f"{footprint_path.name} - AFTER Transform")

    # Export SVG if requested
    if export_svg:
        output_dir = svg_output_dir or footprint_path.parent / "debug_svg"
        export_kicad_svg(footprint_path, output_dir)


def compare_before_after(input_path: Path, output_dir: Path | None = None):
    """
    Run the filter on a footprint and export SVGs for both input and output.

    This allows easy visual comparison of what the filter changed.
    """
    from .kicad_filters import KiCadFilterPipeline

    output_dir = output_dir or input_path.parent / "debug_compare"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Export SVG of input (before filter)
    log.info("\n[1/3] Exporting SVG of INPUT footprint...")
    input_svg_dir = output_dir / "before"
    input_svg = export_kicad_svg(input_path, input_svg_dir)

    # Run the filter
    log.info("\n[2/3] Running fp_filter on footprint...")
    filtered_path = output_dir / f"{input_path.stem}_filtered.kicad_mod"
    KiCadFilterPipeline().filter_footprint(input_path, filtered_path)

    # Export SVG of output (after filter)
    log.info("\n[3/3] Exporting SVG of OUTPUT footprint...")
    output_svg_dir = output_dir / "after"
    output_svg = export_kicad_svg(filtered_path, output_svg_dir)

    log.info("\n" + "="*80)
    log.info("COMPARISON COMPLETE")
    log.info("="*80)
    log.info(f"\nBefore SVG: {input_svg}")
    log.info(f"After SVG:  {output_svg}")
    log.info("\nOpen both SVGs in a browser to compare the F.Fab layer outlines.")
    log.info("="*80)

    return input_svg, output_svg


def generate_html_report(input_dir: Path, output_dir: Path | None = None, report_name: str = "fp_filter_report.html"):
    """
    Generate an HTML report comparing input and output footprints.

    Processes all .kicad_mod files in input_dir, runs the filter,
    and creates a side-by-side HTML comparison.

    Args:
        input_dir: Directory containing input .kicad_mod files
        output_dir: Output directory for SVGs and HTML report (default: tools/temp/fp_report)
        report_name: Name of the HTML report file
    """
    import webbrowser

    from ._files import find_files
    from .kicad_filters import KiCadFilterPipeline

    # Always use consistent output directory
    output_dir = output_dir or (Path(__file__).parent / "test_cases" / "kicad" / "fp_filter" / "out")
    output_dir.mkdir(parents=True, exist_ok=True)

    svg_in_dir = output_dir / "svg_in"
    svg_out_dir = output_dir / "svg_out"

    svg_in_dir.mkdir(parents=True, exist_ok=True)
    svg_out_dir.mkdir(parents=True, exist_ok=True)

    # Find all footprint files
    pipeline = KiCadFilterPipeline()
    fp_files = find_files(input_dir, [".kicad_mod"], recursive=False)
    log.info(f"\nFound {len(fp_files)} footprint files to process")

    # Process each footprint
    results = []
    for i, fp_path in enumerate(sorted(fp_files)):
        fp_name = fp_path.stem
        log.info(f"\n[{i+1}/{len(fp_files)}] Processing: {fp_name}")

        try:
            # Export input SVG
            input_svg = export_kicad_svg(fp_path, svg_in_dir)

            # Run filter - output directly to out folder
            filtered_path = output_dir / fp_path.name
            pipeline.filter_footprint(fp_path, filtered_path)

            # Export output SVG
            output_svg = export_kicad_svg(filtered_path, svg_out_dir)

            results.append({
                'name': fp_name,
                'input_svg': input_svg,
                'output_svg': output_svg,
                'success': True,
                'error': None
            })
        except Exception as e:
            log.error(f"Error processing {fp_name}: {e}")
            results.append({
                'name': fp_name,
                'input_svg': None,
                'output_svg': None,
                'success': False,
                'error': str(e)
            })

    # Generate HTML report
    html_path = output_dir / report_name
    _generate_html_file(html_path, results, svg_in_dir, svg_out_dir)

    log.info(f"\nReport: {html_path}")
    log.info(f"Processed: {len([r for r in results if r['success']])} / {len(results)} footprints")

    # Auto-open in browser
    webbrowser.open(html_path.as_uri())

    return html_path


def _generate_html_file(html_path: Path, results: list, svg_in_dir: Path, svg_out_dir: Path):
    """Generate the HTML report file with embedded SVGs."""

    html_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>FP Filter Report</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: Arial, sans-serif; background: #fff; }}
        h1 {{ text-align: center; padding: 10px; font-size: 16px; border-bottom: 1px solid #ccc; }}
        .row {{ display: flex; width: 100%; border-bottom: 1px solid #ccc; }}
        .cell {{ width: 33%; padding: 5px; border-right: 1px solid #ccc; }}
        .cell:last-child {{ border-right: none; }}
        .label {{ font-size: 11px; font-weight: bold; margin-bottom: 3px; }}
        .label .name {{ color: #333; }}
        .label .tag {{ color: #666; font-weight: normal; }}
        .svg-box {{ width: 100%; }}
        .svg-box svg {{ width: 100%; height: auto; display: block; }}
        .error {{ background: #fee; }}
        .error-msg {{ color: #c00; padding: 20px; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>FP Filter Report | {total} footprints | {timestamp}</h1>
    {rows}
</body>
</html>'''

    row_template = '''
    <div class="row">
        <div class="cell">
            <div class="label"><span class="name">{fp_name}</span> <span class="tag">IN</span></div>
            <div class="svg-box">{input_svg}</div>
        </div>
        <div class="cell">
            <div class="label"><span class="name">{fp_name}</span> <span class="tag">OUT</span></div>
            <div class="svg-box">{output_svg}</div>
        </div>
    </div>'''

    error_row_template = '''
    <div class="row error">
        <div class="cell">
            <div class="label"><span class="name">{fp_name}</span> <span class="tag">ERROR</span></div>
            <div class="error-msg">{error}</div>
        </div>
        <div class="cell"></div>
    </div>'''

    # Build rows
    rows_html = []
    for result in results:
        if result['success']:
            # Read and embed SVG content
            input_svg_content = ""
            output_svg_content = ""

            if result['input_svg'] and result['input_svg'].exists():
                input_svg_content = result['input_svg'].read_text(encoding='utf-8')
                # Remove XML declaration if present
                if input_svg_content.startswith('<?xml'):
                    input_svg_content = input_svg_content.split('?>', 1)[1].strip()

            if result['output_svg'] and result['output_svg'].exists():
                output_svg_content = result['output_svg'].read_text(encoding='utf-8')
                if output_svg_content.startswith('<?xml'):
                    output_svg_content = output_svg_content.split('?>', 1)[1].strip()

            rows_html.append(row_template.format(
                fp_name=result['name'],
                input_svg=input_svg_content or '<p>SVG not available</p>',
                output_svg=output_svg_content or '<p>SVG not available</p>',
                error_class=""
            ))
        else:
            rows_html.append(error_row_template.format(
                fp_name=result['name'],
                error=result['error']
            ))

    # Generate final HTML
    from datetime import datetime

    html_content = html_template.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total=len(results),
        rows='\n'.join(rows_html)
    )

    html_path.write_text(html_content, encoding='utf-8')
    log.info(f"HTML report written to: {html_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Debug visualization for fp_filter__orthographic_projection_outline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Single footprint analysis
  python fp_filter_debug.py footprint.kicad_mod                    # Show debug info only
  python fp_filter_debug.py footprint.kicad_mod --show-3d-after    # Show 3D mesh
  python fp_filter_debug.py footprint.kicad_mod --compare          # Before/after SVG comparison

  # Batch HTML report (process entire directory)
  python fp_filter_debug.py --report input_dir/                    # Generate HTML report
  python fp_filter_debug.py --report input_dir/ --output out_dir/  # Custom output directory
        '''
    )

    parser.add_argument('footprint', type=Path, nargs='?', default=None,
                        help='Path to .kicad_mod file (or directory with --report)')
    parser.add_argument('--show-3d-before', action='store_true',
                        help='Show 3D mesh before KiCad transform')
    parser.add_argument('--show-3d-after', action='store_true',
                        help='Show 3D mesh after KiCad transform')
    parser.add_argument('--export-svg', action='store_true',
                        help='Export SVG via KiCad CLI')
    parser.add_argument('--svg-output', type=Path, default=None,
                        help='Output directory for SVG export')
    parser.add_argument('--compare', action='store_true',
                        help='Run filter and compare before/after SVGs')
    parser.add_argument('--report', action='store_true',
                        help='Generate HTML report for all footprints in directory')
    parser.add_argument('--output', type=Path, default=None,
                        help='Output directory for report')
    parser.add_argument('--all', action='store_true',
                        help='Run all visualizations')

    args = parser.parse_args()

    # Handle --report mode (batch processing)
    if args.report:
        if args.footprint is None:
            # Default to test_cases directory
            input_dir = Path(__file__).parent / "test_cases" / "kicad" / "fp_filter" / "in"
        else:
            input_dir = args.footprint

        if not input_dir.exists():
            log.error(f"Directory not found: {input_dir}")
            sys.exit(1)

        if not input_dir.is_dir():
            log.error(f"Expected directory for --report mode: {input_dir}")
            sys.exit(1)

        generate_html_report(input_dir, args.output)
        return

    # Single footprint mode
    if args.footprint is None:
        parser.print_help()
        sys.exit(0)

    if not args.footprint.exists():
        log.error(f"File not found: {args.footprint}")
        sys.exit(1)

    if args.all:
        args.show_3d_before = True
        args.show_3d_after = True
        args.export_svg = True
        args.compare = True

    # Always show debug info first
    analyze_footprint(
        args.footprint,
        show_3d_before=args.show_3d_before,
        show_3d_after=args.show_3d_after,
        export_svg=args.export_svg,
        svg_output_dir=args.svg_output
    )

    # Run comparison if requested
    if args.compare:
        compare_before_after(args.footprint, args.svg_output)


if __name__ == "__main__":
    main()
