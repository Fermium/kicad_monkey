"""Shared corpus helpers for private kicad_monkey tests."""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, Iterable


def _require_dir(path: Path, *, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"{label} is not a directory: {path}")
    return path


def get_test_corpus_root() -> Path:
    value = os.environ.get("WN_TEST_CORPUS")
    if not value:
        raise RuntimeError("WN_TEST_CORPUS must be set for private kicad_monkey tests")
    return _require_dir(Path(value), label="WN_TEST_CORPUS")


def get_kicad_corpus_root() -> Path:
    return _require_dir(get_test_corpus_root() / "kicad", label="KiCad corpus root")


def get_kicad_corpus_manifest_path() -> Path:
    """Return the canonical KiCad corpus manifest path."""
    return get_kicad_corpus_root() / "manifest.json"


def load_kicad_corpus_manifest(*, required: bool = True) -> dict[str, Any] | None:
    """Load ``$WN_TEST_CORPUS/kicad/manifest.json``.

    The manifest is the registry for promoted KiCad test assets. Legacy tests
    still have path helpers below while coverage migrates to manifest queries.
    """
    manifest_path = get_kicad_corpus_manifest_path()
    if not manifest_path.exists():
        if required:
            raise FileNotFoundError(f"KiCad corpus manifest not found: {manifest_path}")
        return None
    data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"KiCad corpus manifest must be a JSON object: {manifest_path}")
    return data


def iter_kicad_corpus_cases(
    *,
    domain: str | None = None,
    origin: str | None = None,
    status: str | Iterable[str] | None = "active",
    required: bool = True,
) -> Iterable[dict[str, Any]]:
    """Yield manifest case entries filtered by domain/origin/status."""
    manifest = load_kicad_corpus_manifest(required=required)
    if manifest is None:
        return

    statuses: set[str] | None
    if status is None:
        statuses = None
    elif isinstance(status, str):
        statuses = {status}
    else:
        statuses = {str(item) for item in status}

    for case in manifest.get("cases") or []:
        if not isinstance(case, dict):
            continue
        if domain is not None and domain not in (case.get("domains") or []):
            continue
        if origin is not None and case.get("origin") != origin:
            continue
        if statuses is not None and str(case.get("status", "")) not in statuses:
            continue
        yield case


def get_kicad_corpus_case(
    case_id: str,
    *,
    required: bool = True,
) -> dict[str, Any] | None:
    """Return one manifest case by id."""
    for case in iter_kicad_corpus_cases(status=None, required=required):
        if case.get("id") == case_id:
            return case
    if required:
        raise KeyError(f"KiCad corpus case not found in manifest: {case_id}")
    return None


def resolve_kicad_manifest_path(case: dict[str, Any], key: str) -> Path | None:
    """Resolve a manifest relative path field against the KiCad corpus root."""
    value = case.get(key)
    if value in (None, ""):
        return None
    return get_kicad_corpus_root() / str(value)


def get_kicad_common_dir() -> Path:
    return _require_dir(get_kicad_corpus_root() / "common", label="KiCad common corpus")


def get_kicad_common_case_dir(case_name: str) -> Path:
    return _require_dir(get_kicad_common_dir() / case_name, label=f"KiCad common case '{case_name}'")


def get_kicad_topic_dir(topic: str) -> Path:
    return _require_dir(get_kicad_corpus_root() / topic, label=f"KiCad topic '{topic}'")


def get_kicad_topic_input_dir(topic: str) -> Path:
    return _require_dir(get_kicad_topic_dir(topic) / "input", label=f"KiCad topic input '{topic}'")


def get_kicad_common_boards_dir() -> Path:
    return _require_dir(get_kicad_common_dir() / "board" / "input", label="KiCad common boards input")


def get_kicad_common_board_case_dir(case_name: str) -> Path:
    return _require_dir(get_kicad_common_boards_dir() / case_name, label=f"KiCad common board case '{case_name}'")


def get_kicad_common_footprints_dir() -> Path:
    return _require_dir(
        get_kicad_common_dir() / "footprints" / "input",
        label="KiCad common footprints input",
    )


def get_kicad_common_reference_symbols_dir() -> Path:
    return _require_dir(
        get_kicad_common_dir() / "reference_symbols" / "input",
        label="KiCad reference symbols input",
    )


def get_kicad_common_reference_schematics_dir() -> Path:
    return _require_dir(
        get_kicad_common_dir() / "reference_schematics" / "input",
        label="KiCad reference schematics input",
    )


def get_kicad_common_reference_worksheets_dir() -> Path:
    return _require_dir(
        get_kicad_common_dir() / "reference_worksheets" / "input",
        label="KiCad reference worksheets input",
    )


def get_kicad_common_board_case_file(case_name: str, filename: str) -> Path:
    case_dir = _require_dir(get_kicad_common_boards_dir() / case_name, label=f"KiCad board case '{case_name}'")
    return case_dir / filename


def get_kicad_topic_case_file(topic: str, case_name: str, filename: str) -> Path:
    case_dir = _require_dir(get_kicad_topic_dir(topic) / "input" / case_name, label=f"KiCad topic case '{topic}/{case_name}'")
    return case_dir / filename


def get_kicad_pcb_foundation_dir() -> Path:
    """Return the synthetic-PCB foundation corpus root.

    Layout (matches Altium ``pcbdoc_synthesized``):

        <corpus>/kicad/pcb_foundation/<case>/
            input/<case files>
            reference_output/<oracle outputs>
            output/<test-run regenerated artifacts>

    Used by parsing, IR, SVG, IPC, viz, and data-model validation.
    """
    return _require_dir(
        get_kicad_corpus_root() / "pcb_foundation",
        label="KiCad PCB foundation corpus",
    )


def get_kicad_pcb_foundation_case_dir(case_name: str) -> Path:
    return _require_dir(
        get_kicad_pcb_foundation_dir() / case_name,
        label=f"KiCad pcb_foundation case '{case_name}'",
    )


def get_kicad_pcb_foundation_case_input_dir(case_name: str) -> Path:
    return _require_dir(
        get_kicad_pcb_foundation_case_dir(case_name) / "input",
        label=f"KiCad pcb_foundation case input '{case_name}'",
    )


def get_kicad_pcb_foundation_case_reference_output_dir(case_name: str) -> Path:
    return _require_dir(
        get_kicad_pcb_foundation_case_dir(case_name) / "reference_output",
        label=f"KiCad pcb_foundation case reference_output '{case_name}'",
    )


def get_kicad_upstream_qa_dir() -> Path:
    """Mirrored KiCad ``qa/data/`` tree (curated 41-file slice).

    Refresh via ``toolz/kicad_monkey/scripts/sync_upstream_qa_fixtures.py``.
    """
    return _require_dir(
        get_kicad_corpus_root() / "upstream_qa",
        label="KiCad upstream qa mirror",
    )


KICAD_SEXPR_FILE_SUFFIXES: tuple[str, ...] = (
    ".kicad_pcb",
    ".kicad_sch",
    ".kicad_sym",
    ".kicad_mod",
    ".kicad_wks",
)
"""KiCad S-expression file suffixes used by the parser-only pass-through gate.

``.kicad_pro`` is intentionally absent: KiCad project files are JSON, not
S-expression, so they cannot exercise ``parse_sexp``/``build_sexp``.
"""


def iter_kicad_sexpr_files(
    *,
    root: Path | None = None,
    suffixes: Iterable[str] | None = None,
    exclude_dirs: Iterable[str] = ("output", "review", "review_tmp"),
) -> Iterable[Path]:
    """Yield every KiCad S-expression file under ``root`` in stable order.

    Defaults to the canonical corpus root and the full set of S-expression
    file types. ``exclude_dirs`` drops generated/output trees so the
    pass-through gate does not chase stale or derived artefacts.
    """
    base = root if root is not None else get_kicad_corpus_root()
    allowed = tuple(s.lower() for s in (suffixes or KICAD_SEXPR_FILE_SUFFIXES))
    excluded = {name for name in exclude_dirs}

    found: list[Path] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in allowed:
            continue
        parts = set(path.relative_to(base).parts[:-1])
        if parts & excluded:
            continue
        found.append(path)

    found.sort()
    yield from found


def get_kicad_netlist_upstream_qa_dir() -> Path:
    """Mirrored KiCad ``qa/data/eeschema/netlists/`` tree (14 cases).

    Refresh via ``toolz/kicad_monkey/scripts/sync_upstream_qa_netlist_fixtures.py``.
    Each subdirectory is one case with a ``.kicad_sch`` (+ optional sub-
    schematics, ``.kicad_pro``) and a golden ``.net`` produced by
    upstream's own KiCad build.
    """
    return _require_dir(
        get_kicad_corpus_root() / "netlist" / "upstream_qa",
        label="KiCad netlist upstream qa mirror",
    )
