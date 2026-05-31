"""Shared KiCad CLI resolver for corpus-backed oracle tests."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal


def _corpus_roots() -> list[Path]:
    roots: list[Path] = []
    env_corpus = os.environ.get("WN_TEST_CORPUS")
    if env_corpus:
        roots.append(Path(env_corpus))
    roots.append(Path(r"C:\eli\wn_test_corpus"))
    roots.append(
        Path(r"C:\Users\EliHughes\OneDrive - Wavenumber LLC\wn_test_corpus")
    )

    out: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        key = root.resolve() if root.exists() else root
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _manifest_short_hashes() -> list[str]:
    """Return staged CLI hashes in manifest order.

    The manifest is authoritative because the corpus can contain stale
    experimental builds that should not be used just because their mtime is
    newer.
    """
    tests_repo_root = Path(__file__).resolve().parents[3]
    manifest = tests_repo_root / "tools" / "kicad-cli" / "MANIFEST.toml"
    if not manifest.exists():
        return []

    hashes: list[str] = []
    for match in re.finditer(
        r'^\s*short_hash\s*=\s*"([^"]+)"\s*$',
        manifest.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    ):
        hashes.append(match.group(1))
    return hashes


KiCadCliCapability = Literal["any", "pcb_svg"]


def _iter_kicad_cli_candidates() -> list[Path]:
    """Return kicad-cli candidates in the shared oracle resolution order."""
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: Path) -> None:
        key = candidate.resolve() if candidate.exists() else candidate
        if key in seen:
            return
        seen.add(key)
        candidates.append(candidate)

    env_cli = os.environ.get("KICAD_CLI")
    if env_cli:
        add(Path(env_cli))

    manifest_hashes = _manifest_short_hashes()
    for corpus_root in _corpus_roots():
        corpus_tools = corpus_root / "tools" / "kicad-cli"
        for short_hash in manifest_hashes:
            add(corpus_tools / short_hash / "bin" / "kicad-cli.exe")

    for corpus_root in _corpus_roots():
        corpus_tools = corpus_root / "tools" / "kicad-cli"
        if not corpus_tools.exists():
            continue
        staged = sorted(
            (d for d in corpus_tools.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        for staged_dir in staged:
            add(staged_dir / "bin" / "kicad-cli.exe")

    cli = shutil.which("kicad-cli")
    if cli:
        add(Path(cli))

    add(Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"))
    add(Path(r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"))
    return candidates


def _supports_pcb_svg(candidate: Path) -> bool:
    """Probe whether a kicad-cli executable can load the PCB SVG exporter."""
    if not candidate.exists():
        return False
    if os.name == "nt" and not (candidate.parent / "_pcbnew.dll").exists():
        return False

    try:
        result = subprocess.run(
            [str(candidate), "pcb", "export", "svg", "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return result.returncode == 0


def resolve_kicad_cli(
    *, required_capability: KiCadCliCapability = "any"
) -> Path | None:
    """Find the KiCad 9/10 oracle binary.

    Resolution policy:
    1. explicit ``$KICAD_CLI``;
    2. manifest-listed staged corpus builds, in manifest order;
    3. any other staged corpus build as a fallback;
    4. ``PATH``;
    5. installed KiCad 10/9.
    """
    for candidate in _iter_kicad_cli_candidates():
        if not candidate.exists():
            continue
        if required_capability == "pcb_svg" and not _supports_pcb_svg(candidate):
            continue
        if required_capability == "any":
            return candidate
        if required_capability == "pcb_svg":
            return candidate
    return None
