"""Lightweight KiCad symbol and footprint name indexing."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

__all__ = ["KiCadNameIndex"]


def _iter_files(starting_path: Path, suffix: str) -> list[Path]:
    root = Path(starting_path)
    return sorted(path for path in root.rglob(f"*{suffix}") if path.is_file())


def _is_fuzzy_match(search_term: str, target: str) -> bool:
    search_lower = search_term.lower()
    target_lower = target.lower()

    if search_lower == target_lower:
        return True
    if search_lower in target_lower or target_lower in search_lower:
        return True

    search_parts = re.split(r"[-_\s]+", search_lower)
    target_parts = re.split(r"[-_\s]+", target_lower)
    if all(any(search_part in target_part for target_part in target_parts) for search_part in search_parts):
        return True

    try:
        fuzz = importlib.import_module("rapidfuzz.fuzz")
    except ImportError:
        return False
    return fuzz.token_sort_ratio(search_lower, target_lower) > 70


class KiCadNameIndex:
    """Fast symbol and footprint name extraction for KiCad library files."""

    def symbol_names(self, filename: Path | str) -> list[str]:
        """Extract top-level symbol names from a `.kicad_sym` file."""
        path = Path(filename)
        with path.open(encoding="utf-8") as f:
            head = f.read(2000)

        symbols: list[str] = []
        for match in re.finditer(r'\(symbol\s+"([^"]+)"', head):
            name = match.group(1)
            if "_" in name and name.rsplit("_", 1)[-1].isdigit():
                parts = name.rsplit("_", 2)
                if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
                    continue
            symbols.append(name)

        if not symbols:
            symbols.append(path.stem)

        return symbols

    def footprint_names(self, filename: Path | str) -> list[str]:
        """Extract the declared footprint name from a `.kicad_mod` file."""
        path = Path(filename)
        with path.open(encoding="utf-8") as f:
            head = f.read(500)

        match = re.search(r'\((?:footprint|module)\s+"([^"]+)"', head)
        if match:
            return [match.group(1)]

        match = re.search(r"\((?:footprint|module)\s+(\S+)", head)
        if match:
            return [match.group(1)]

        return [path.stem]

    def build_symbol_index(self, starting_path: Path | str) -> dict[str, list[Path]]:
        """Build a symbol-name -> files index for a directory tree."""
        symbol_index: dict[str, list[Path]] = {}

        for path in _iter_files(Path(starting_path), ".kicad_sym"):
            for symbol in self.symbol_names(path):
                symbol_index.setdefault(symbol, []).append(path)

        return symbol_index

    def build_footprint_index(self, starting_path: Path | str) -> dict[str, list[Path]]:
        """Build a footprint-name -> files index for a directory tree."""
        footprint_index: dict[str, list[Path]] = {}

        for path in _iter_files(Path(starting_path), ".kicad_mod"):
            for footprint in self.footprint_names(path):
                footprint_index.setdefault(footprint, []).append(path)

        return footprint_index

    def find_symbols(
        self,
        symbol_name: str,
        starting_path: Path | str,
        *,
        fuzzy: bool = False,
    ) -> list[dict[str, Path | str]]:
        """Find symbol files that declare the requested symbol name."""
        matches: list[dict[str, Path | str]] = []

        for path in _iter_files(Path(starting_path), ".kicad_sym"):
            for symbol in self.symbol_names(path):
                if symbol == symbol_name or (fuzzy and _is_fuzzy_match(symbol_name, symbol)):
                    matches.append({"name": symbol, "file": path})

        return matches

    def find_footprints(
        self,
        footprint_name: str,
        starting_path: Path | str,
        *,
        fuzzy: bool = False,
    ) -> list[dict[str, Path | str]]:
        """Find footprint files that declare the requested footprint name or library folder."""
        matches: list[dict[str, Path | str]] = []

        for path in _iter_files(Path(starting_path), ".kicad_mod"):
            library = path.parent.name
            for footprint in self.footprint_names(path):
                if (
                    footprint == footprint_name
                    or library == footprint_name
                    or (
                        fuzzy
                        and (
                            _is_fuzzy_match(footprint_name, footprint)
                            or _is_fuzzy_match(footprint_name, library)
                        )
                    )
                ):
                    matches.append({"name": footprint, "file": path, "library": library})

        return matches
