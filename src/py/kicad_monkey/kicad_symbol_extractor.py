"""
KiCad Symbol Extractor

Utility to extract symbols from KiCad schematic files (.kicad_sch) and save them
as individual .kicad_sym files. Useful for importing local project symbols into
a library structure.

Usage:
    # Extract from a single schematic
    extract_symbols_from_schematic('path/to/file.kicad_sch', 'output/dir')

    # Extract from all schematics in a project
    extract_symbols_from_project('path/to/project.kicad_pro', 'output/dir')
"""

import logging
from pathlib import Path

from .kicad_sexpr import build_sexp, format_sexp, parse_sexp

log = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """
    Sanitize a symbol name to be a valid filename.

    Replaces invalid filename characters with underscores.

    Args:
        name: Symbol name (may include library prefix like "speedy:HMCAD1511TR")

    Returns:
        Valid filename string
    """
    # Remove library prefix if present (e.g., "speedy:HMCAD1511TR" -> "HMCAD1511TR")
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


def extract_symbols_from_text(schematic_text: str) -> list[tuple[str, str]]:
    """
    Extract symbol definitions from schematic file text using sexpr parser.

    Args:
        schematic_text: Contents of a .kicad_sch file

    Returns:
        List of (symbol_name, symbol_sexp) tuples
    """
    symbols = []

    try:
        # Parse the entire schematic using sexpr parser
        parsed = parse_sexp(schematic_text)
    except Exception as e:
        log.error(f"Failed to parse schematic file: {e}")
        return symbols

    # The parsed structure is a list: ['kicad_sch', (version ...), (lib_symbols ...), ...]
    # Find the lib_symbols section
    lib_symbols = None
    for item in parsed:
        if isinstance(item, list) and len(item) > 0 and item[0] == 'lib_symbols':
            lib_symbols = item
            break

    if not lib_symbols:
        return symbols

    # Extract all symbol definitions from lib_symbols
    # lib_symbols structure: ['lib_symbols', [symbol ...], [symbol ...], ...]
    for item in lib_symbols[1:]:  # Skip the 'lib_symbols' keyword
        if isinstance(item, list) and len(item) > 1 and item[0] == 'symbol':
            # item[1] is the symbol name (could be QuotedString or str)
            symbol_name = str(item[1])

            # Remove library prefix if present (e.g., "library:symbol" -> "symbol")
            clean_symbol_name = symbol_name
            if ':' in symbol_name:
                clean_symbol_name = symbol_name.split(':', 1)[1]

            # Update the symbol name in the parsed structure to remove library prefix
            item[1] = clean_symbol_name

            # Also update any sub-symbol references that have the full prefixed name
            # Sub-symbols follow the pattern: "original_symbol_name_1_0", "original_symbol_name_2_0", etc.
            # We need to update them to: "clean_symbol_name_1_0", "clean_symbol_name_2_0", etc.
            def update_subsymbol_names(node):
                """Recursively update sub-symbol names to use clean symbol name"""
                if isinstance(node, list):
                    for _i, child in enumerate(node):
                        # Check if this is a symbol definition with a name
                        if isinstance(child, list) and len(child) > 1 and child[0] == 'symbol':
                            child_name = str(child[1])
                            # Check if this is a sub-symbol (ends with _N_N pattern)
                            # Original might be "library:symbol_1_0" or just "symbol_1_0"
                            # We need it to be "clean_symbol_1_0"
                            if '_' in child_name:
                                # Extract the suffix (like "_1_0")
                                parts = child_name.split('_')
                                # Check if last two parts are numbers (unit and style indices)
                                if len(parts) >= 3:
                                    try:
                                        int(parts[-2])  # unit number
                                        int(parts[-1])  # style number
                                        # This is a sub-symbol, reconstruct with clean name
                                        suffix = '_' + '_'.join(parts[-2:])
                                        child[1] = clean_symbol_name + suffix
                                    except ValueError:
                                        # Not a standard sub-symbol pattern, leave it
                                        pass
                        # Recurse into children
                        update_subsymbol_names(child)

            # Update sub-symbol names throughout the symbol tree
            update_subsymbol_names(item)

            # Convert the symbol back to S-expression string
            symbol_sexp = build_sexp(item)
            symbols.append((clean_symbol_name, symbol_sexp))

    return symbols


def create_symbol_file_content(symbol_name: str, symbol_sexp: str) -> str:
    """
    Create a complete .kicad_sym file content from a symbol S-expression.

    Args:
        symbol_name: Name of the symbol
        symbol_sexp: The symbol S-expression from the schematic

    Returns:
        Complete .kicad_sym file content with header and footer
    """
    # Parse the symbol to get it as a list structure
    try:
        symbol_parsed = parse_sexp(symbol_sexp)
    except Exception:
        # If parsing fails, use string concatenation fallback
        content = f"""(kicad_symbol_lib
\t(version 20241209)
\t(generator "kicad_symbol_editor")
\t(generator_version "9.0")
\t{symbol_sexp}
)
"""
        return content

    # Build the library structure with proper formatting
    library_structure = [
        'kicad_symbol_lib',
        ['version', 20241209],
        ['generator', 'kicad_symbol_editor'],
        ['generator_version', '9.0'],
        symbol_parsed
    ]

    # Convert to formatted S-expression
    sexp_str = build_sexp(library_structure)
    formatted = format_sexp(sexp_str, indentation_size=2, max_nesting=2)

    return formatted


def extract_symbols_from_schematic(
    schematic_path: Path,
    output_dir: Path,
    overwrite: bool = False
) -> int:
    """
    Extract all symbols from a KiCad schematic file and save them as individual .kicad_sym files.

    Args:
        schematic_path: Path to .kicad_sch file
        output_dir: Directory to save extracted symbol files
        overwrite: If True, overwrite existing files. If False, skip existing files.

    Returns:
        Number of symbols extracted
    """
    schematic_path = Path(schematic_path)
    output_dir = Path(output_dir)

    if not schematic_path.exists():
        log.error(f"Schematic file not found: {schematic_path}")
        return 0

    log.info(f"Extracting symbols from: {schematic_path.name}")

    # Read schematic file
    try:
        with open(schematic_path, encoding='utf-8') as f:
            schematic_text = f.read()
    except Exception as e:
        log.error(f"Failed to read schematic file: {e}")
        return 0

    # Extract symbols
    symbols = extract_symbols_from_text(schematic_text)

    if not symbols:
        log.info(f"  No embedded symbols found in {schematic_path.name}")
        return 0

    log.info(f"  Found {len(symbols)} symbol(s)")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save each symbol to its own file
    extracted_count = 0
    for symbol_name, symbol_sexp in symbols:
        # Sanitize the filename
        safe_name = sanitize_filename(symbol_name)
        output_file = output_dir / f"{safe_name}.kicad_sym"

        # Check if file exists
        if output_file.exists() and not overwrite:
            log.info(f"  Skipping '{symbol_name}' (file exists): {output_file.name}")
            continue

        # Create the complete symbol file content
        file_content = create_symbol_file_content(symbol_name, symbol_sexp)

        # Write to file
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(file_content)
            log.info(f"  Extracted '{symbol_name}' -> {output_file.name}")
            extracted_count += 1
        except Exception as e:
            log.error(f"  Failed to write symbol '{symbol_name}': {e}")

    return extracted_count


def find_schematics_in_project(project_path: Path) -> list[Path]:
    """
    Find all schematic files associated with a KiCad project.

    Looks for .kicad_sch files in the same directory as the project file.
    The main schematic typically has the same base name as the project.

    Args:
        project_path: Path to .kicad_pro file

    Returns:
        List of paths to schematic files
    """
    project_path = Path(project_path)
    project_dir = project_path.parent
    project_name = project_path.stem

    schematics = []

    # Look for main schematic with same name as project
    main_schematic = project_dir / f"{project_name}.kicad_sch"
    if main_schematic.exists():
        schematics.append(main_schematic)

    # Find all other .kicad_sch files in the project directory
    for schematic_file in project_dir.glob("*.kicad_sch"):
        if schematic_file not in schematics:
            schematics.append(schematic_file)

    return schematics


def extract_symbols_from_project(
    project_path: Path,
    output_dir: Path,
    overwrite: bool = False
) -> int:
    """
    Extract all symbols from all schematics in a KiCad project.

    Args:
        project_path: Path to .kicad_pro file
        output_dir: Directory to save extracted symbol files
        overwrite: If True, overwrite existing files. If False, skip existing files.

    Returns:
        Total number of symbols extracted
    """
    project_path = Path(project_path)

    if not project_path.exists():
        log.error(f"Project file not found: {project_path}")
        return 0

    log.info("=" * 80)
    log.info(f"Extracting symbols from project: {project_path.name}")
    log.info("=" * 80)

    # Find all schematics
    schematics = find_schematics_in_project(project_path)

    if not schematics:
        log.warning(f"No schematic files found for project: {project_path.name}")
        return 0

    log.info(f"Found {len(schematics)} schematic file(s)")

    # Extract symbols from each schematic
    total_extracted = 0
    for schematic in schematics:
        count = extract_symbols_from_schematic(schematic, output_dir, overwrite)
        total_extracted += count

    log.info("=" * 80)
    log.info(f"Total symbols extracted: {total_extracted}")
    log.info("=" * 80)

    return total_extracted


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        log.info("Usage:")
        log.info("  python kicad_symbol_extractor.py <input_file> <output_dir> [--overwrite]")
        log.info("")
        log.info("  <input_file>  - Path to .kicad_sch or .kicad_pro file")
        log.info("  <output_dir>  - Directory to save extracted .kicad_sym files")
        log.info("  --overwrite   - Overwrite existing files (optional)")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    overwrite = '--overwrite' in sys.argv

    if not input_file.exists():
        log.info(f"Error: Input file not found: {input_file}")
        sys.exit(1)

    # Determine if it's a project or schematic file
    if input_file.suffix == '.kicad_pro':
        count = extract_symbols_from_project(input_file, output_dir, overwrite)
    elif input_file.suffix == '.kicad_sch':
        count = extract_symbols_from_schematic(input_file, output_dir, overwrite)
    else:
        log.info("Error: Input file must be .kicad_pro or .kicad_sch")
        sys.exit(1)

    log.info(f"\nDone! Extracted {count} symbol(s) to {output_dir}")
