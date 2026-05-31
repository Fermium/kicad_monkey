"""
Subtest: Corpus-Wide S-Expression Parser Pass-Through Gate
Stratum: L1_parsing
Purpose: Prove every promoted KiCad S-expression file in the shared corpus
round-trips through the parser/writer without the typed OOP layer.

This parser-only gate must run ``parse_sexp -> build_sexp -> parse_sexp`` only
and tag failures by parse
phase (``lex`` / ``tree`` / ``build`` / ``reparse`` / ``compare``) so a
downstream SVG/IR failure cannot hide a low-level parse defect.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from kicad_monkey.kicad_sexpr import roundtrip_sexp_text
from kicad_monkey.testing.corpus import (
    KICAD_SEXPR_FILE_SUFFIXES,
    iter_kicad_sexpr_files,
)


# Failures are aggregated and surfaced in one shot so the report points at
# every offending file/phase, not just the first ``pytest -x`` casualty.
_REAL_WORLD_PATH_MARKERS: tuple[str, ...] = ("projects", "real_world")


@dataclass(frozen=True)
class _RoundtripRecord:
    path: Path
    phase: str
    error: str


@pytest.fixture(scope="module")
def corpus_roundtrip_records() -> list[_RoundtripRecord]:
    """Roundtrip every corpus S-expression file once and cache the results.

    Both tests in this module classify the same record set so the full
    corpus walk only runs once per session.
    """
    records: list[_RoundtripRecord] = []
    for path in iter_kicad_sexpr_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            records.append(_RoundtripRecord(path, "read", f"OSError: {exc}"))
            continue
        result = roundtrip_sexp_text(text)
        records.append(_RoundtripRecord(path, result.phase, result.error or ""))
    return records


def _is_real_world(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return any(marker in parts for marker in _REAL_WORLD_PATH_MARKERS)


def test_corpus_sexpr_files_round_trip_through_parser_only_gate(
    corpus_roundtrip_records: list[_RoundtripRecord],
) -> None:
    """Lex, parse, build, re-parse, and compare every corpus S-expression file.

    Files are discovered through the canonical corpus root; no manifest
    promotion gate is required because this is a structural parser
    contract. Failures are bucketed by phase and the assertion message
    names every offending file.
    """
    assert corpus_roundtrip_records, (
        "No KiCad S-expression files discovered under corpus root"
    )

    by_suffix: Counter[str] = Counter()
    by_phase: Counter[str] = Counter()
    failures: list[_RoundtripRecord] = []

    for record in corpus_roundtrip_records:
        by_suffix[record.path.suffix.lower()] += 1
        by_phase[record.phase] += 1
        if record.phase != "ok":
            failures.append(record)

    if failures:
        lines = [
            f"  [{record.phase}] {record.path}: {record.error[:240]}"
            for record in failures[:50]
        ]
        extra = "" if len(failures) <= 50 else f"  ... ({len(failures) - 50} more)"
        message = (
            f"Parser-only pass-through gate failed for {len(failures)} of "
            f"{len(corpus_roundtrip_records)} files. Phase breakdown: "
            f"{dict(by_phase)}. Suffix breakdown: {dict(by_suffix)}.\n"
            + "\n".join(lines)
            + extra
        )
        pytest.fail(message)

    # Sanity: every expected file type is represented in the corpus walk so
    # the gate cannot accidentally degenerate to "only PCBs".
    missing_suffixes = [s for s in KICAD_SEXPR_FILE_SUFFIXES if by_suffix[s] == 0]
    assert not missing_suffixes, (
        f"Corpus walk found no files for suffixes: {missing_suffixes}"
    )


def test_corpus_real_world_projects_have_parser_only_passthrough_coverage(
    corpus_roundtrip_records: list[_RoundtripRecord],
) -> None:
    """Real-world projects must contribute to the parser-only gate.

    This ensures the gate is not satisfied by synthetic single-file fixtures
    alone; promoted real-world projects supply the parser surface that
    breaks downstream SVG/IR work if it regresses.
    """
    real_world = [r for r in corpus_roundtrip_records if _is_real_world(r.path)]

    assert real_world, (
        "No real-world S-expression files found under corpus root; the "
        "manifest's promoted projects must contribute parser-only coverage."
    )

    failures = [r for r in real_world if r.phase != "ok"]

    if failures:
        lines = [
            f"  [{r.phase}] {r.path}: {r.error[:240]}"
            for r in failures[:20]
        ]
        extra = "" if len(failures) <= 20 else f"  ... ({len(failures) - 20} more)"
        pytest.fail(
            f"Parser-only pass-through failed on {len(failures)} of "
            f"{len(real_world)} real-world files:\n"
            + "\n".join(lines)
            + extra
        )
