"""
Generate KiCad CLI reference SVGs for footprint SVG testing.

This script uses kicad-cli to generate black-and-white SVG files
for each footprint, one file per layer. These serve as reference
outputs for testing our Python to_svg() implementation.

Usage:
    uv run python tools/kicad/tests/generate_svg_references.py
"""

import logging
import subprocess
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

# Standard layers to export for footprints
FOOTPRINT_LAYERS = [
    "F.Cu",
    "B.Cu",
    "F.SilkS",
    "B.SilkS",
    "F.Fab",
    "B.Fab",
    "F.Mask",
    "B.Mask",
    "F.Paste",
    "B.Paste",
    "F.CrtYd",
    "B.CrtYd",
    "Edge.Cuts",
    "User.Drawings",
]

# KiCad CLI paths to check
KICAD_CLI_PATHS = [
    Path("C:/Program Files/KiCad/9.0/bin/kicad-cli.exe"),
    Path("C:/Program Files/KiCad/8.0/bin/kicad-cli.exe"),
    Path("C:/Program Files/KiCad/7.0/bin/kicad-cli.exe"),
]


def find_kicad_cli() -> Path | None:
    """Find kicad-cli executable."""
    cli = shutil.which("kicad-cli")
    if cli:
        return Path(cli)

    for path in KICAD_CLI_PATHS:
        if path.exists():
            return path

    return None


def generate_footprint_reference_svgs(
    input_dir: Path,
    output_dir: Path,
    kicad_cli: Path,
    layers: list[str] | None = None,
) -> dict[str, list[Path]]:
    """
    Generate reference SVGs for all footprints in input_dir.

    Args:
        input_dir: Directory containing .kicad_mod files
        output_dir: Directory to write reference SVGs
        kicad_cli: Path to kicad-cli executable
        layers: Layers to export (default: FOOTPRINT_LAYERS)

    Returns:
        Dict mapping footprint name to list of generated SVG paths
    """
    if layers is None:
        layers = FOOTPRINT_LAYERS

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all footprint files
    fp_files = sorted(input_dir.glob("*.kicad_mod"))
    log.info(f"Found {len(fp_files)} footprint files in {input_dir}")

    results = {}

    for fp_path in fp_files:
        fp_name = fp_path.stem
        log.info(f"Processing: {fp_name}")

        # Create a temporary .pretty directory (kicad-cli requires this)
        temp_pretty = output_dir / f"_temp_{fp_name}.pretty"
        temp_pretty.mkdir(exist_ok=True)

        # Copy footprint into temp .pretty library
        shutil.copy(fp_path, temp_pretty / fp_path.name)

        generated = []

        for layer in layers:
            # Output file: {footprint_name}__{layer}.svg
            # Replace dots in layer name with underscore for filename
            layer_safe = layer.replace(".", "_")
            svg_path = output_dir / f"{fp_name}__{layer_safe}.svg"

            # Create temp output dir for this layer
            temp_out = output_dir / f"_temp_out_{fp_name}_{layer_safe}"
            temp_out.mkdir(exist_ok=True)

            try:
                # Run kicad-cli to export SVG
                result = subprocess.run(
                    [
                        str(kicad_cli),
                        "fp", "export", "svg",
                        "--black-and-white",
                        "--layers", layer,
                        "--footprint", fp_name,
                        "--output", str(temp_out),
                        str(temp_pretty),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    log.warning(f"  {layer}: kicad-cli error: {result.stderr.strip()}")
                    continue

                # kicad-cli creates file as {footprint_name}.svg in output dir
                generated_svg = temp_out / f"{fp_name}.svg"
                if generated_svg.exists():
                    # Keep empty SVGs too so layer-level reference completeness
                    # is deterministic for parity tests.
                    content = generated_svg.read_text()
                    has_graphics = any(tag in content for tag in ("<path", "<polygon", "<circle", "<rect"))
                    shutil.move(generated_svg, svg_path)
                    generated.append(svg_path)
                    if has_graphics:
                        log.debug(f"  {layer}: generated {svg_path.name}")
                    else:
                        log.debug(f"  {layer}: generated empty {svg_path.name}")
                else:
                    log.debug(f"  {layer}: no output file generated")

            except subprocess.TimeoutExpired:
                log.error(f"  {layer}: timeout")
            except Exception as e:
                log.error(f"  {layer}: error: {e}")
            finally:
                # Clean up temp output dir
                shutil.rmtree(temp_out, ignore_errors=True)

        # Clean up temp .pretty dir
        shutil.rmtree(temp_pretty, ignore_errors=True)

        if generated:
            results[fp_name] = generated
            log.info(f"  Generated {len(generated)} SVG files")
        else:
            log.info(f"  No layers with graphics")

    return results


def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Find kicad-cli
    kicad_cli = find_kicad_cli()
    if not kicad_cli:
        log.error("kicad-cli not found. Please install KiCad.")
        return 1

    log.info(f"Using kicad-cli: {kicad_cli}")

    # Set up paths
    test_cases_dir = Path(__file__).parent / "test_cases" / "svg" / "footprints"
    input_dir = test_cases_dir / "input"
    output_dir = test_cases_dir / "reference_output"

    if not input_dir.exists():
        log.error(f"Input directory not found: {input_dir}")
        return 1

    # Generate reference SVGs
    results = generate_footprint_reference_svgs(
        input_dir=input_dir,
        output_dir=output_dir,
        kicad_cli=kicad_cli,
    )

    # Summary
    total_svgs = sum(len(svgs) for svgs in results.values())
    log.info(f"\nGenerated {total_svgs} reference SVGs for {len(results)} footprints")
    log.info(f"Output directory: {output_dir}")

    return 0


if __name__ == "__main__":
    exit(main())
