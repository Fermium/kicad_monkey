"""
Subtest: Source Model Hygiene
Stratum: L1_parsing
Purpose: Keep the authoritative KiCad source-model surface typed and free of ad hoc layer literals.

This is intentionally scoped to the KiCad OOP source-model boundary. Transitional
renderers, cruncher entry points, and debug helpers are not part of the stable
parser/model contract and are reviewed separately.
"""

from __future__ import annotations

import ast
from pathlib import Path

from conftest import KICAD_MODULE_ROOT


CORE_SOURCE_MODEL_PATTERNS: tuple[str, ...] = (
    "kicad_base.py",
    "kicad_geometry.py",
    "kicad_footprint.py",
    "kicad_property.py",
    "kicad_pad.py",
    "kicad_pcb.py",
    "kicad_pcb_parser.py",
    "kicad_pcb_footprint.py",
    "kicad_pcb_routing.py",
    "kicad_pcb_zone.py",
    "kicad_pcb_other.py",
    "kicad_pcb_graphics.py",
    "kicad_primitives.py",
    "kicad_fp_*.py",
    "kicad_pcb_gr_*.py",
)

COMMON_LAYER_LITERALS: frozenset[str] = frozenset(
    {
        "F.Cu",
        "B.Cu",
        "F.SilkS",
        "B.SilkS",
        "F.Mask",
        "B.Mask",
        "F.Paste",
        "B.Paste",
        "Edge.Cuts",
    }
)


def _iter_core_source_model_modules() -> list[Path]:
    modules: list[Path] = []
    seen: set[Path] = set()

    for pattern in CORE_SOURCE_MODEL_PATTERNS:
        for path in sorted(KICAD_MODULE_ROOT.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            modules.append(path)

    return modules


def _parse_module(module_path: Path) -> ast.Module:
    return ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))


def _missing_annotations(module_path: Path) -> list[str]:
    tree = _parse_module(module_path)
    problems: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        missing_parts: list[str] = []
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            if arg.arg in {"self", "cls"}:
                continue
            if arg.annotation is None:
                missing_parts.append(f"arg:{arg.arg}")

        if node.args.vararg and node.args.vararg.annotation is None:
            missing_parts.append(f"vararg:{node.args.vararg.arg}")

        if node.args.kwarg and node.args.kwarg.annotation is None:
            missing_parts.append(f"kwarg:{node.args.kwarg.arg}")

        if node.returns is None:
            missing_parts.append("return")

        if missing_parts:
            problems.append(f"{module_path.name}:{node.lineno}:{node.name}:{', '.join(missing_parts)}")

    return problems


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    docstring_ids: set[int] = set()

    def mark(body: list[ast.stmt]) -> None:
        if not body:
            return
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstring_ids.add(id(first.value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            mark(node.body)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            mark(node.body)

    return docstring_ids


def _raw_common_layer_literals(module_path: Path) -> list[str]:
    if module_path.name == "kicad_base.py":
        return []

    tree = _parse_module(module_path)
    ignored_ids = _docstring_constant_ids(tree)
    problems: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in ignored_ids:
            continue
        if node.value in COMMON_LAYER_LITERALS:
            problems.append(f"{module_path.name}:{node.lineno}:{node.value}")

    return problems


def test_core_source_model_modules_have_complete_type_annotations() -> None:
    modules = _iter_core_source_model_modules()
    assert modules, "Expected at least one KiCad source-model module to review"

    problems: list[str] = []
    for module_path in modules:
        problems.extend(_missing_annotations(module_path))

    assert not problems, "Missing type annotations:\n" + "\n".join(problems)


def test_core_source_model_modules_centralize_common_layer_literals() -> None:
    modules = _iter_core_source_model_modules()
    assert modules, "Expected at least one KiCad source-model module to review"

    problems: list[str] = []
    for module_path in modules:
        problems.extend(_raw_common_layer_literals(module_path))

    assert not problems, "Raw common layer literals should stay centralized in kicad_base:\n" + "\n".join(problems)
