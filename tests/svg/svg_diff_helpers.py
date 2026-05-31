"""
SVG Comparison and Diff Helpers for KiCad SVG Tests

Provides utilities for comparing Python-generated SVGs with KiCad CLI reference outputs.

Usage:
    from svg_diff_helpers import create_overlay_diff, compare_svg_bounds

    # Create visual overlay diff
    create_overlay_diff(
        reference_svg="case1_kicad.svg",
        generated_svg="case1_python.svg",
        output_svg="case1_diff.svg"
    )
"""

import re
from pathlib import Path
from xml.etree import ElementTree as ET


def load_svg_content(svg_path: Path) -> tuple[str, float, float, float, float]:
    """Load SVG and extract its content and viewBox dimensions.

    Returns:
        Tuple of (inner_content, min_x, min_y, width, height)
    """
    svg_path = Path(svg_path)
    if not svg_path.exists():
        raise FileNotFoundError(f"SVG not found: {svg_path}")

    content = svg_path.read_text(encoding="utf-8")

    # Parse to get dimensions
    root = ET.fromstring(content)

    # Get viewBox
    viewbox = root.get("viewBox")
    if viewbox:
        parts = viewbox.split()
        min_x = float(parts[0])
        min_y = float(parts[1])
        width = float(parts[2])
        height = float(parts[3])
    else:
        min_x = 0
        min_y = 0
        width = float(root.get("width", "800").replace("mm", "").replace("px", ""))
        height = float(root.get("height", "600").replace("mm", "").replace("px", ""))

    # Extract inner content (everything inside the root <svg> element)
    match = re.search(r'<svg[^>]*>(.*)</svg>', content, re.DOTALL)
    inner_content = match.group(1) if match else ""

    return inner_content, min_x, min_y, width, height


def colorize_svg_content(content: str, color: str, opacity: float = 1.0) -> str:
    """Transform SVG content to use a specific color.

    Replaces stroke and fill colors with the specified color.
    Makes background rectangles transparent.
    """
    # Make fill-only rectangles (backgrounds) transparent
    def make_background_transparent(match):
        rect_content = match.group(0)
        if 'stroke=' in rect_content:
            return rect_content
        return re.sub(r'fill="[^"]*"', 'fill="none"', rect_content)

    content = re.sub(r'<rect[^>]*fill="[^"]*"[^>]*/>', make_background_transparent, content)

    # Replace stroke colors
    content = re.sub(r'stroke="[^"]*"', f'stroke="{color}"', content)

    # Replace fill colors (preserve "none")
    def replace_fill(match):
        fill_value = match.group(1)
        if fill_value.lower() == "none":
            return match.group(0)
        return f'fill="{color}"'

    content = re.sub(r'fill="([^"]*)"', replace_fill, content)

    # Remove opacity attributes that would override group opacity
    content = re.sub(r'\s*fill-opacity="[^"]*"', '', content)
    content = re.sub(r'\s*stroke-opacity="[^"]*"', '', content)

    # Add opacity wrapper if needed
    if opacity < 1.0:
        content = f'<g opacity="{opacity}">{content}</g>'

    return content


def create_overlay_diff(
    reference_svg: Path,
    generated_svg: Path,
    output_svg: Path,
    ref_color: str = "#0000FF",  # Blue
    gen_color: str = "#FF0000",  # Red
    opacity: float = 0.5,
    show_legend: bool = False,
) -> Path:
    """Create visual overlay diff between reference and generated SVG.

    Args:
        reference_svg: Path to KiCad CLI generated reference SVG
        generated_svg: Path to Python generated SVG
        output_svg: Path to write diff SVG
        ref_color: Color for reference SVG elements (default blue)
        gen_color: Color for generated SVG elements (default red)
        opacity: Opacity for both layers (0-1)

    Returns:
        Path to generated diff SVG
    """
    reference_svg = Path(reference_svg)
    generated_svg = Path(generated_svg)
    output_svg = Path(output_svg)

    # Load both SVGs
    ref_content, ref_min_x, ref_min_y, ref_width, ref_height = load_svg_content(reference_svg)
    gen_content, gen_min_x, gen_min_y, gen_width, gen_height = load_svg_content(generated_svg)

    # Use combined bounds
    min_x = min(ref_min_x, gen_min_x)
    min_y = min(ref_min_y, gen_min_y)
    max_x = max(ref_min_x + ref_width, gen_min_x + gen_width)
    max_y = max(ref_min_y + ref_height, gen_min_y + gen_height)
    width = max_x - min_x
    height = max_y - min_y

    # Colorize content
    ref_colored = colorize_svg_content(ref_content, ref_color, opacity)
    gen_colored = colorize_svg_content(gen_content, gen_color, opacity)

    # Build diff SVG
    diff_svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{width}mm" height="{height}mm"
     viewBox="{min_x} {min_y} {width} {height}"
     stroke-linecap="round" stroke-linejoin="round">
  <title>Overlay Diff: Python vs KiCad CLI</title>
  <desc>Blue=KiCad CLI (reference), Red=Python (generated). Purple=matching.</desc>

  <!-- Background (white for better visibility) -->
  <rect x="{min_x}" y="{min_y}" width="{width}" height="{height}" fill="white"/>

  <!-- Reference layer (KiCad CLI - blue) -->
  <g id="reference-layer">
    {ref_colored}
  </g>

  <!-- Generated layer (Python - red) -->
  <g id="generated-layer">
    {gen_colored}
  </g>
</svg>'''

    # Write output
    output_svg.parent.mkdir(parents=True, exist_ok=True)
    output_svg.write_text(diff_svg, encoding="utf-8")

    return output_svg


def compare_svg_bounds(
    reference_svg: Path,
    generated_svg: Path,
    tolerance: float = 1.0,
) -> tuple[bool, dict]:
    """Compare viewBox bounds of two SVGs.

    Args:
        reference_svg: Path to reference SVG
        generated_svg: Path to generated SVG
        tolerance: Maximum allowed difference in any dimension (in mm)

    Returns:
        Tuple of (passed, details dict)
    """
    _, ref_min_x, ref_min_y, ref_width, ref_height = load_svg_content(reference_svg)
    _, gen_min_x, gen_min_y, gen_width, gen_height = load_svg_content(generated_svg)

    details = {
        "ref_bounds": (ref_min_x, ref_min_y, ref_width, ref_height),
        "gen_bounds": (gen_min_x, gen_min_y, gen_width, gen_height),
        "diff_min_x": abs(ref_min_x - gen_min_x),
        "diff_min_y": abs(ref_min_y - gen_min_y),
        "diff_width": abs(ref_width - gen_width),
        "diff_height": abs(ref_height - gen_height),
    }

    passed = (
        details["diff_min_x"] <= tolerance and
        details["diff_min_y"] <= tolerance and
        details["diff_width"] <= tolerance and
        details["diff_height"] <= tolerance
    )

    return passed, details


def generate_kicad_reference_svg(
    input_file: Path,
    output_file: Path,
    file_type: str = "sym",
) -> bool:
    """Generate reference SVG using KiCad CLI.

    Args:
        input_file: Path to .kicad_sym or .kicad_sch file
        output_file: Path for output SVG
        file_type: "sym" for symbol library, "sch" for schematic

    Returns:
        True if successful, False otherwise
    """
    import subprocess

    input_file = Path(input_file)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if file_type == "sym":
        cmd = [
            "kicad-cli", "sym", "export", "svg",
            "--output", str(output_file.parent),
            str(input_file)
        ]
    elif file_type == "sch":
        cmd = [
            "kicad-cli", "sch", "export", "svg",
            "--output", str(output_file),
            str(input_file)
        ]
    else:
        raise ValueError(f"Unknown file_type: {file_type}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
