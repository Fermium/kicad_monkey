from __future__ import annotations

import os

from _suite_paths import TEST_CORPUS_ROOT, TESTS_REPO_ROOT, ensure_import_paths

ensure_import_paths()
os.environ.setdefault("WN_TEST_SUITES_ROOT", str(TESTS_REPO_ROOT))

_configured_corpus = os.environ.get("WN_TEST_CORPUS")
if not _configured_corpus or not (os.path.isdir(os.path.join(_configured_corpus, "kicad"))):
    os.environ["WN_TEST_CORPUS"] = str(TEST_CORPUS_ROOT)

# Point the outline-font shaper at the staged oracle's HarfBuzz so render-cache
# generation uses the same hb_ft (hinted, integer-cursor) advance path as the
# kicad-cli oracle. Without this, the pure-uharfbuzz fallback drifts by a few
# microns per glyph and the L2_009 oracle comparisons fail at tolerance.
if not os.environ.get("KICAD_HARFBUZZ_DLL"):
    from kicad_cli_resolver import resolve_kicad_cli

    _oracle_cli = resolve_kicad_cli(required_capability="pcb_svg")
    if _oracle_cli is not None:
        _harfbuzz_dll = _oracle_cli.parent / "harfbuzz.dll"
        if _harfbuzz_dll.is_file():
            os.environ["KICAD_HARFBUZZ_DLL"] = str(_harfbuzz_dll)
