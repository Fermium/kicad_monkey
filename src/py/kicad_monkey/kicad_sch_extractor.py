"""
KiCad Schematic Symbol Extractor

Utility to extract symbol definitions from KiCad schematic files (.kicad_sch)
and save them as individual .kicad_sym library files.

Schematics embed copies of symbols from libraries in the lib_symbols section.
This tool extracts those embedded symbols, which is useful for:
- Creating backup copies of symbols used in a design
- Extracting custom/modified symbols from old designs
- Migrating symbols between projects

Usage:
    # Extract all symbols from a schematic
    extract_symbols_from_schematic('design.kicad_sch', 'output/dir')

    # Extract symbols from all schematics in a project
    extract_symbols_from_project('project.kicad_pro', 'output/dir')

Implementation uses the OOP KiCadSchematic and KiCadSymbolLib classes for
proper parsing and serialization, ensuring round-trip fidelity.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from .kicad_schematic import KiCadSchematic
from .kicad_symbol_lib import KiCadSymbolLib

log = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """
    Sanitize a symbol name to be a valid filename.

    Removes library prefix if present and replaces invalid characters.

    Args:
        name: Symbol name (may include "Library:SymbolName" format)

    Returns:
        Valid filename string
    """
    # Remove library prefix if present
    if ':' in name:
        name = name.split(':', 1)[1]

    # Replace invalid filename characters with underscore
    invalid_chars = r'<>:"/\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')

    # Also replace spaces and other problematic characters
    name = name.replace(' ', '_')
    name = name.replace('\t', '_')
    name = name.replace('\n', '_')
    name = name.replace('\r', '_')

    return name


def extract_symbols_from_schematic(
    schematic_path: Path | str,
    output_dir: Path | str,
    overwrite: bool = False,
    filter_library: Optional[str] = None,
    skip_power: bool = False
) -> int:
    """
    Extract all symbol definitions from a KiCad schematic file.

    Extracts symbols from the lib_symbols section and saves each as an
    individual .kicad_sym library file.

    Args:
        schematic_path: Path to .kicad_sch file
        output_dir: Directory to save extracted .kicad_sym files
        overwrite: If True, overwrite existing files. If False, skip existing.
        filter_library: If set, only extract symbols from this library
        skip_power: If True, skip power symbols

    Returns:
        Number of symbols extracted
    """
    schematic_path = Path(schematic_path)
    output_dir = Path(output_dir)

    if not schematic_path.exists():
        log.error(f"Schematic file not found: {schematic_path}")
        return 0

    log.info(f"Extracting symbols from: {schematic_path.name}")

    # Parse schematic using OOP model
    try:
        sch = KiCadSchematic.from_file(schematic_path)
    except Exception as e:
        log.error(f"Failed to parse schematic: {e}")
        return 0

    if not sch.lib_symbols:
        log.info(f"  No embedded symbols found in {schematic_path.name}")
        return 0

    log.info(f"  Found {len(sch.lib_symbols)} embedded symbol(s)")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract each symbol
    extracted_count = 0
    for lib_symbol in sch.lib_symbols:
        symbol_name = lib_symbol.name

        # Parse library prefix if present
        library_name = ""
        clean_name = symbol_name
        if ':' in symbol_name:
            library_name, clean_name = symbol_name.split(':', 1)

        # Apply filters
        if filter_library and library_name != filter_library:
            log.debug(f"  Skipping '{symbol_name}' (not from library '{filter_library}')")
            continue

        if skip_power and lib_symbol.power:
            log.debug(f"  Skipping power symbol '{symbol_name}'")
            continue

        # Generate output filename
        safe_name = sanitize_filename(symbol_name)
        output_file = output_dir / f"{safe_name}.kicad_sym"

        # Check if file exists
        if output_file.exists() and not overwrite:
            log.info(f"  Skipping '{clean_name}' (file exists): {output_file.name}")
            continue

        # Create a single-symbol library
        # Update symbol name to remove library prefix
        lib_symbol.name = clean_name

        # Update subsymbol names to match
        for subsym in lib_symbol.subsymbols:
            if ':' in subsym.name:
                subsym.name = subsym.name.split(':', 1)[1]

        single_lib = KiCadSymbolLib(
            version=sch.version,
            generator="eeschema",
            generator_version=sch.generator_version,
            symbols=[lib_symbol]
        )

        # Write to file
        try:
            single_lib.to_file(output_file)
            log.info(f"  Extracted '{clean_name}' -> {output_file.name}")
            extracted_count += 1
        except Exception as e:
            log.error(f"  Failed to write symbol '{clean_name}': {e}")

    return extracted_count


def extract_symbols_from_project(
    project_path: Path | str,
    output_dir: Path | str,
    overwrite: bool = False,
    recursive: bool = True,
    filter_library: Optional[str] = None,
    skip_power: bool = False,
    skip_duplicates: bool = True
) -> int:
    """
    Extract symbols from all schematics in a KiCad project.

    Finds all .kicad_sch files in the project directory (based on .kicad_pro
    location) and extracts their embedded symbols.

    Args:
        project_path: Path to .kicad_pro file or directory containing schematics
        output_dir: Directory to save extracted .kicad_sym files
        overwrite: If True, overwrite existing files
        recursive: If True, search subdirectories for schematics
        filter_library: If set, only extract symbols from this library
        skip_power: If True, skip power symbols
        skip_duplicates: If True, skip symbols already extracted (by name)

    Returns:
        Total number of unique symbols extracted
    """
    project_path = Path(project_path)
    output_dir = Path(output_dir)

    # Determine search directory
    if project_path.is_file():
        if project_path.suffix == '.kicad_pro':
            search_dir = project_path.parent
        elif project_path.suffix == '.kicad_sch':
            # User passed a schematic file directly
            return extract_symbols_from_schematic(
                project_path, output_dir, overwrite, filter_library, skip_power
            )
        else:
            log.error(f"Expected .kicad_pro or .kicad_sch file: {project_path}")
            return 0
    elif project_path.is_dir():
        search_dir = project_path
    else:
        log.error(f"Path not found: {project_path}")
        return 0

    log.info("=" * 80)
    log.info(f"Extracting symbols from project: {search_dir}")
    log.info("=" * 80)

    # Find all schematic files
    if recursive:
        schematic_files = sorted(search_dir.rglob("*.kicad_sch"))
    else:
        schematic_files = sorted(search_dir.glob("*.kicad_sch"))

    if not schematic_files:
        log.warning(f"No .kicad_sch files found in: {search_dir}")
        return 0

    log.info(f"Found {len(schematic_files)} schematic file(s)")
    log.info("")

    # Track extracted symbols to avoid duplicates
    extracted_symbols: Set[str] = set()
    total_extracted = 0

    # Process each schematic
    for sch_file in schematic_files:
        log.info(f"Processing: {sch_file.name}")

        try:
            sch = KiCadSchematic.from_file(sch_file)
        except Exception as e:
            log.error(f"  Failed to parse: {e}")
            continue

        if not sch.lib_symbols:
            log.info("  No embedded symbols")
            continue

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Extract symbols
        for lib_symbol in sch.lib_symbols:
            symbol_name = lib_symbol.name

            # Check for duplicates across files
            if skip_duplicates and symbol_name in extracted_symbols:
                log.debug(f"  Skipping duplicate: {symbol_name}")
                continue

            # Parse library prefix
            library_name = ""
            clean_name = symbol_name
            if ':' in symbol_name:
                library_name, clean_name = symbol_name.split(':', 1)

            # Apply filters
            if filter_library and library_name != filter_library:
                continue

            if skip_power and lib_symbol.power:
                continue

            # Generate output filename
            safe_name = sanitize_filename(symbol_name)
            output_file = output_dir / f"{safe_name}.kicad_sym"

            if output_file.exists() and not overwrite:
                extracted_symbols.add(symbol_name)  # Track it as processed
                continue

            # Update symbol name
            lib_symbol.name = clean_name
            for subsym in lib_symbol.subsymbols:
                if ':' in subsym.name:
                    subsym.name = subsym.name.split(':', 1)[1]

            # Create single-symbol library
            single_lib = KiCadSymbolLib(
                version=sch.version,
                generator="eeschema",
                generator_version=sch.generator_version,
                symbols=[lib_symbol]
            )

            try:
                single_lib.to_file(output_file)
                log.info(f"  Extracted: {clean_name}")
                extracted_symbols.add(symbol_name)
                total_extracted += 1
            except Exception as e:
                log.error(f"  Failed to write '{clean_name}': {e}")

    # Summary
    log.info("")
    log.info("=" * 80)
    log.info("EXTRACTION COMPLETE")
    log.info("=" * 80)
    log.info(f"Total unique symbols extracted: {total_extracted}")
    log.info(f"Output directory: {output_dir}")
    log.info("=" * 80)

    return total_extracted


def list_symbols_in_schematic(schematic_path: Path | str) -> List[Dict[str, str]]:
    """
    List all embedded symbols in a schematic without extracting them.

    Args:
        schematic_path: Path to .kicad_sch file

    Returns:
        List of dicts with symbol info: name, library, reference, value
    """
    schematic_path = Path(schematic_path)

    if not schematic_path.exists():
        log.error(f"Schematic file not found: {schematic_path}")
        return []

    try:
        sch = KiCadSchematic.from_file(schematic_path)
    except Exception as e:
        log.error(f"Failed to parse schematic: {e}")
        return []

    result = []
    for lib_symbol in sch.lib_symbols:
        symbol_name = lib_symbol.name
        library_name = ""
        clean_name = symbol_name
        if ':' in symbol_name:
            library_name, clean_name = symbol_name.split(':', 1)

        result.append({
            'name': clean_name,
            'library': library_name,
            'full_name': symbol_name,
            'reference': lib_symbol.reference,
            'value': lib_symbol.value,
            'footprint': lib_symbol.footprint,
            'power': lib_symbol.power,
            'unit_count': lib_symbol.unit_count
        })

    return result


if __name__ == "__main__":
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python kicad_sch_extractor.py <input_path> <output_dir> [options]")
        print()
        print("  <input_path>  - Path to .kicad_sch file, .kicad_pro file, or directory")
        print("  <output_dir>  - Directory to save extracted .kicad_sym files")
        print()
        print("Options:")
        print("  --overwrite     - Overwrite existing files")
        print("  --no-recursive  - Don't search subdirectories")
        print("  --skip-power    - Skip power symbols")
        print("  --library NAME  - Only extract symbols from specified library")
        print("  --list          - List symbols without extracting")
        print()
        print("Examples:")
        print("  python kicad_sch_extractor.py design.kicad_sch symbols/")
        print("  python kicad_sch_extractor.py project.kicad_pro symbols/ --skip-power")
        print("  python kicad_sch_extractor.py design.kicad_sch . --list")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    overwrite = '--overwrite' in sys.argv
    recursive = '--no-recursive' not in sys.argv
    skip_power = '--skip-power' in sys.argv
    list_only = '--list' in sys.argv

    # Parse --library option
    filter_library = None
    for i, arg in enumerate(sys.argv):
        if arg == '--library' and i + 1 < len(sys.argv):
            filter_library = sys.argv[i + 1]
            break

    if not input_path.exists():
        print(f"Error: Input path not found: {input_path}")
        sys.exit(1)

    if list_only:
        # Just list symbols
        if input_path.suffix == '.kicad_sch':
            symbols = list_symbols_in_schematic(input_path)
            print(f"\nSymbols in {input_path.name}:")
            print("-" * 60)
            for sym in symbols:
                power_flag = " [POWER]" if sym['power'] else ""
                print(f"  {sym['full_name']}{power_flag}")
                print(f"    Reference: {sym['reference']}, Value: {sym['value']}")
                if sym['footprint']:
                    print(f"    Footprint: {sym['footprint']}")
            print(f"\nTotal: {len(symbols)} symbol(s)")
        else:
            print("Error: --list requires a .kicad_sch file")
            sys.exit(1)
    else:
        # Extract symbols
        if input_path.suffix == '.kicad_sch':
            count = extract_symbols_from_schematic(
                input_path, output_dir, overwrite, filter_library, skip_power
            )
        else:
            count = extract_symbols_from_project(
                input_path, output_dir, overwrite, recursive, filter_library, skip_power
            )

        print(f"\nDone! Extracted {count} symbol(s) to {output_dir}")
