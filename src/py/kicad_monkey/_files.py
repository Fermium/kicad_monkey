"""Small file and composition helpers kept local to kicad_monkey."""

from __future__ import annotations

from pathlib import Path


def compose(*funcs):
    """Apply functions left-to-right."""

    def composed(arg):
        result = arg
        for func in funcs:
            result = func(result)
        return result

    return composed


def find_files(directory: Path, extensions: list[str], recursive: bool = True) -> list[Path]:
    """Find files matching the given extensions."""
    path = Path(directory)
    matching_files: list[Path] = []
    normalized_exts = [
        ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        for ext in extensions
    ]

    search_pattern = path.rglob("*") if recursive else path.glob("*")
    for file_path in search_pattern:
        if file_path.is_file() and file_path.suffix.lower() in normalized_exts:
            matching_files.append(file_path)

    return matching_files
