"""Split multi-symbol KiCad libraries into single-symbol library files."""

from __future__ import annotations

import logging
from pathlib import Path

from .kicad_sexpr import build_sexp, parse_sexp
from .kicad_symbol_extractor import create_symbol_file_content, sanitize_filename

log = logging.getLogger(__name__)


def _normalize_symbol_tree(symbol_node: list) -> tuple[str, str]:
    original_name = str(symbol_node[1])
    clean_name = original_name.split(":", 1)[1] if ":" in original_name else original_name
    symbol_node[1] = clean_name

    def update_subsymbol_names(node: object) -> None:
        if not isinstance(node, list):
            return
        for child in node:
            if isinstance(child, list) and len(child) > 1 and child[0] == "symbol":
                child_name = str(child[1])
                if ":" in child_name:
                    child_name = child_name.split(":", 1)[1]
                if "_" in child_name:
                    parts = child_name.split("_")
                    if len(parts) >= 3:
                        try:
                            int(parts[-2])
                            int(parts[-1])
                            child[1] = clean_name + "_" + "_".join(parts[-2:])
                        except ValueError:
                            pass
            update_subsymbol_names(child)

    update_subsymbol_names(symbol_node)
    return clean_name, build_sexp(symbol_node)


def split_symbol_library(input_path: Path | str, output_dir: Path | str, overwrite: bool = False) -> int:
    """Split a `.kicad_sym` library into one file per top-level symbol."""
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        log.error("Symbol library not found: %s", input_path)
        return 0

    try:
        text = input_path.read_text(encoding="utf-8")
        parsed = parse_sexp(text)
    except Exception as exc:  # pragma: no cover - defensive error path
        log.error("Failed to parse symbol library %s: %s", input_path, exc)
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)

    extracted = 0
    for item in parsed[1:]:
        if not (isinstance(item, list) and len(item) > 1 and item[0] == "symbol"):
            continue

        clean_name, symbol_sexp = _normalize_symbol_tree(item)
        output_path = output_dir / f"{sanitize_filename(clean_name)}.kicad_sym"
        if output_path.exists() and not overwrite:
            continue

        output_path.write_text(create_symbol_file_content(clean_name, symbol_sexp), encoding="utf-8")
        extracted += 1

    return extracted
