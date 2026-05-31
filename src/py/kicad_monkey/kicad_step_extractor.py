"""
KiCad STEP Model Extractor

Utility to extract embedded STEP 3D models from KiCad footprint files (.kicad_mod).
The embedded models are base64 encoded and zstd compressed.

Usage:
    # Extract from a single footprint file
    extract_step_from_footprint('path/to/file.kicad_mod', 'output/dir')

    # Extract from all footprints in a directory
    extract_step_from_directory('path/to/footprints/', 'output/dir')
"""

import base64
import sys
from pathlib import Path
from typing import Any, cast

# Setup Python path - this file is in tools/common, need to add tools/ to path

import logging

from .kicad_sexpr import parse_sexp

log = logging.getLogger(__name__)


try:
    import zstandard as _zstandard
except ImportError:
    _zstandard = None

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    trimesh = None
    TRIMESH_AVAILABLE = False


def _decompress_zstd(data: bytes) -> bytes:
    if _zstandard is not None:
        return _zstandard.ZstdDecompressor().decompress(data)
    raise RuntimeError("zstd support is unavailable; install 'zstandard'")


def find_embedded_step_data(sexp, step_exts=(".stp", ".step")) -> tuple[str, str] | None:
    """
    Traverses the parsed s-expression to find embedded STEP data.

    Args:
        sexp: Parsed s-expression structure
        step_exts: Tuple of valid STEP file extensions

    Returns:
        Tuple of (filename, base64_data) if found, else None
    """
    def walk(node):
        if isinstance(node, list):
            # Look for embedded_files section
            if node and node[0] == 'embedded_files':
                for file_node in node[1:]:
                    if isinstance(file_node, list) and file_node and file_node[0] == 'file':
                        name = None
                        data = None

                        # Extract name and data from file node
                        for item in file_node[1:]:
                            if isinstance(item, list) and item and item[0] == 'name':
                                name = str(item[1])
                            if isinstance(item, list) and item and item[0] == 'data':
                                # Join all data parts, remove newlines, strip KiCad's |...| wrapper
                                data_parts = []
                                for d in item[1:]:
                                    data_parts.append(str(d))
                                data = ''.join(data_parts).replace('\n', '').replace('\r', '').strip('|')

                        # Check if this is a STEP file with data
                        if name and any(name.lower().endswith(ext) for ext in step_exts) and data:
                            log.info(f"Found embedded STEP data for: {name}")
                            return (name, data)

            # Recurse into children
            for child in node:
                result = walk(child)
                if result:
                    return result
        return None

    return walk(sexp)


def extract_step_from_text(footprint_text: str) -> tuple[str, bytes] | None:
    """
    Extract STEP model data from footprint file text.

    Args:
        footprint_text: Contents of a .kicad_mod file

    Returns:
        Tuple of (filename, step_data_bytes) if found, else None
    """
    try:
        # Parse the footprint file using sexpr parser
        parsed = parse_sexp(footprint_text)
    except Exception as e:
        log.error(f"Failed to parse footprint file: {e}")
        return None

    # Find embedded STEP data
    result = find_embedded_step_data(parsed)
    if not result:
        return None

    filename, b64_data = result

    # Decode base64
    try:
        compressed_data = base64.b64decode(b64_data)
        log.info("Base64 decoded successfully")
    except Exception as e:
        log.error(f"Failed to decode base64 data: {e}")
        return None

    # Decompress with zstd
    try:
        step_data = _decompress_zstd(compressed_data)
        log.info("ZSTD decompressed successfully")
    except Exception as e:
        log.error(f"Failed to decompress zstd data: {e}")
        return None

    return (filename, step_data)


def view_step_file(step_path: Path) -> bool:
    """
    Open a 3D viewer for a STEP file using trimesh with enhanced lighting and colors.

    Args:
        step_path: Path to STEP file to view

    Returns:
        True if viewer opened successfully, False otherwise
    """
    if not TRIMESH_AVAILABLE:
        log.error("trimesh is not available. Install it with: uv pip install trimesh")
        return False
    tm = cast(Any, trimesh)

    step_path = Path(step_path)

    if not step_path.exists():
        log.error(f"STEP file not found: {step_path}")
        return False

    log.info(f"Loading STEP file: {step_path.name}")

    try:
        # Load the STEP file - trimesh automatically handles colors from STEP
        # Using process=False to preserve original colors better
        mesh = tm.load(str(step_path), file_type='step', process=False)

        # Create a scene for better visualization
        if isinstance(mesh, tm.Scene):
            scene = mesh
        else:
            scene = tm.Scene(mesh)

        # Enhance lighting with multiple directional lights
        # Don't use custom lights as they require complex scene graph setup
        # Instead, just significantly boost ambient lighting

        # Very high ambient light to show colors and reduce shadows
        cast(Any, scene).ambient_light = [0.5, 0.5, 0.5, 0.5]

        log.info(f"Opening viewer for: {step_path.name}")
        log.info("Controls: Left-click drag to rotate, right-click drag to pan, scroll to zoom")
        log.info("Press 'q' or close window to exit viewer")

        # Show the interactive viewer with smooth rendering
        scene.show(
            smooth=True,  # Enable smooth shading
            flags={'cull': False}  # Show both sides of surfaces
        )

        return True

    except Exception as e:
        log.error(f"Failed to view STEP file: {e}")
        import traceback
        log.error(f"Details: {traceback.format_exc()}")
        return False


def extract_step_from_footprint(
    footprint_path: Path,
    output_dir: Path | None = None,
    output_filename: str | None = None,
    view: bool = False
) -> bool:
    """
    Extract embedded STEP model from a KiCad footprint file.

    Args:
        footprint_path: Path to .kicad_mod file
        output_dir: Directory to save STEP file (default: same as footprint)
        output_filename: Custom output filename (default: use embedded filename)
        view: If True, open 3D viewer after extraction

    Returns:
        True if extraction succeeded, False otherwise
    """
    footprint_path = Path(footprint_path)

    if not footprint_path.exists():
        log.error(f"Footprint file not found: {footprint_path}")
        return False

    log.info(f"Extracting STEP model from: {footprint_path.name}")

    # Read footprint file
    try:
        with open(footprint_path, encoding='utf-8') as f:
            footprint_text = f.read()
    except Exception as e:
        log.error(f"Failed to read footprint file: {e}")
        return False

    # Extract STEP data
    result = extract_step_from_text(footprint_text)
    if not result:
        log.warning(f"No embedded STEP model found in: {footprint_path.name}")
        return False

    embedded_filename, step_data = result

    # Determine output path
    if output_dir is None:
        output_dir = footprint_path.parent
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    if output_filename is None:
        # Use embedded filename, or derive from footprint name
        if embedded_filename:
            output_filename = embedded_filename
        else:
            output_filename = footprint_path.stem + ".step"

    # Ensure .step or .stp extension
    output_filename = str(output_filename)
    if not (output_filename.lower().endswith('.step') or output_filename.lower().endswith('.stp')):
        output_filename += '.step'

    output_path = output_dir / output_filename

    # Write STEP file
    try:
        with open(output_path, 'wb') as f:
            f.write(step_data)
        log.info(f"Extracted STEP model to: {output_path}")

        # Open viewer if requested
        if view:
            view_step_file(output_path)

        return True
    except Exception as e:
        log.error(f"Failed to write STEP file: {e}")
        return False


def extract_step_from_directory(
    input_dir: Path,
    output_dir: Path | None = None,
    recursive: bool = False
) -> tuple[int, int]:
    """
    Extract STEP models from all .kicad_mod files in a directory.

    Args:
        input_dir: Directory containing .kicad_mod files
        output_dir: Directory to save STEP files (default: same as input)
        recursive: Whether to search subdirectories

    Returns:
        Tuple of (success_count, total_count)
    """
    input_dir = Path(input_dir)

    if not input_dir.exists():
        log.error(f"Input directory not found: {input_dir}")
        return (0, 0)

    # Find all .kicad_mod files
    if recursive:
        footprint_files = list(input_dir.rglob("*.kicad_mod"))
    else:
        footprint_files = list(input_dir.glob("*.kicad_mod"))

    if not footprint_files:
        log.warning(f"No .kicad_mod files found in: {input_dir}")
        return (0, 0)

    log.info("=" * 80)
    log.info(f"Extracting STEP models from {len(footprint_files)} footprint(s)")
    log.info("=" * 80)

    success_count = 0
    for footprint_file in footprint_files:
        if extract_step_from_footprint(footprint_file, output_dir):
            success_count += 1

    log.info("=" * 80)
    log.info(f"Successfully extracted {success_count} of {len(footprint_files)} STEP models")
    log.info("=" * 80)

    return (success_count, len(footprint_files))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract embedded STEP 3D models from KiCad footprint files"
    )
    parser.add_argument(
        "input",
        help="Path to .kicad_mod file or directory containing footprint files"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory for STEP files (default: same as input)"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Search subdirectories recursively (only for directory input)"
    )
    parser.add_argument(
        "-n", "--name",
        help="Custom output filename (only for single file input)"
    )
    parser.add_argument(
        "-v", "--view",
        action="store_true",
        help="Open 3D viewer after extraction (requires trimesh)"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output) if args.output else None

    if not input_path.exists():
        log.info(f"Error: Input path not found: {input_path}")
        sys.exit(1)

    # Process single file or directory
    if input_path.is_file():
        if input_path.suffix != '.kicad_mod':
            log.info(f"Error: Input file must be .kicad_mod, got: {input_path.suffix}")
            sys.exit(1)
        success = extract_step_from_footprint(input_path, output_dir, args.name, args.view)
        sys.exit(0 if success else 1)

    elif input_path.is_dir():
        if args.name:
            log.info("Warning: --name option ignored for directory input")
        if args.view:
            log.info("Warning: --view option ignored for directory input (only works for single files)")
        success_count, total_count = extract_step_from_directory(
            input_path, output_dir, args.recursive
        )
        sys.exit(0 if success_count > 0 else 1)

    else:
        log.info(f"Error: Invalid input path: {input_path}")
        sys.exit(1)
