"""KiCad text-variable helpers.

KiCad text fields use ``${NAME}`` placeholders in board, footprint, drawing
sheet, and table text. This module centralizes the small substitution policy
used by renderers so equivalent callers do not drift on case handling.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any

_TEXT_VARIABLE_RE = re.compile(r"\$\{([^}]+)\}")


def _add_variable(variables: dict[str, str], name: object, value: object) -> None:
    key = str(name)
    if not key:
        return
    text = str(value)
    variables[key] = text
    variables[key.lower()] = text
    variables[key.upper()] = text


def normalize_text_variables(values: Mapping[Any, Any] | None) -> dict[str, str]:
    """Return text variables with original, lower, and upper-case keys."""

    variables: dict[str, str] = {}
    for key, value in (values or {}).items():
        if value is None:
            continue
        _add_variable(variables, key, value)
    return variables


def object_property_text_variables(properties: Iterable[Any] | None) -> dict[str, str]:
    """Return text variables from objects with ``name/key`` and ``value`` fields."""

    variables: dict[str, str] = {}
    for prop in properties or []:
        key = getattr(prop, "key", getattr(prop, "name", None))
        value = getattr(prop, "value", None)
        if key is None or value is None:
            continue
        _add_variable(variables, key, value)
    return variables


def board_text_variables(board: Any) -> dict[str, str]:
    """Return board/project text variables available to board-level text."""

    variables: dict[str, str] = {}
    if board is None:
        return variables

    project = getattr(board, "project", None)
    variables.update(normalize_text_variables(getattr(project, "text_variables", {})))
    variables.update(object_property_text_variables(getattr(board, "properties", [])))
    return variables


def footprint_text_variables(footprint: Any) -> dict[str, str]:
    """Return footprint-local text variables from footprint properties."""

    if footprint is None:
        return {}
    return object_property_text_variables(getattr(footprint, "properties", []))


def table_cell_text_variables(cell: Any, table: Any = None) -> dict[str, str]:
    """Return KiCad's table-cell-local text variables for a cell."""

    variables: dict[str, str] = {}
    if cell is None:
        return variables

    cells = list(getattr(table, "cells", []) or [])
    column_count = int(getattr(table, "column_count", 0) or 0)
    index = next(
        (idx for idx, candidate in enumerate(cells) if candidate is cell),
        None,
    )
    if table is not None and index is not None and column_count > 0:
        row = index // column_count
        column = index % column_count
        addr = f"{chr(ord('A') + (column % 26))}{row + 1}"
        _add_variable(variables, "ROW", row + 1)
        _add_variable(variables, "COL", column + 1)
        _add_variable(variables, "ADDR", addr)

    layer = getattr(cell, "layer", None)
    if layer is not None:
        _add_variable(variables, "LAYER", layer)

    return variables


def substitute_text_variables(text: str, variables: Mapping[str, str]) -> str:
    """Substitute KiCad ``${VAR}`` text variables with resolved values."""

    if "${" not in text:
        return text

    lookup = normalize_text_variables(variables)

    def replace_var(match: re.Match[str]) -> str:
        var_name = match.group(1)
        return lookup.get(var_name, match.group(0))

    return _TEXT_VARIABLE_RE.sub(replace_var, text)


def project_text_variables(project: Any) -> dict[str, str]:
    """Return project-level text variables without case-expanded aliases."""

    return {
        str(key): str(value)
        for key, value in (getattr(project, "text_variables", {}) or {}).items()
        if key is not None and value is not None
    }


__all__ = [
    "board_text_variables",
    "footprint_text_variables",
    "normalize_text_variables",
    "object_property_text_variables",
    "project_text_variables",
    "substitute_text_variables",
    "table_cell_text_variables",
]
