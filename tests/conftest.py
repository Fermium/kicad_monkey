from __future__ import annotations

import os

from _suite_paths import TEST_CORPUS_ROOT, TESTS_REPO_ROOT, ensure_import_paths

ensure_import_paths()
os.environ.setdefault("WN_TEST_SUITES_ROOT", str(TESTS_REPO_ROOT))

_configured_corpus = os.environ.get("WN_TEST_CORPUS")
if not _configured_corpus or not (os.path.isdir(os.path.join(_configured_corpus, "kicad"))):
    os.environ["WN_TEST_CORPUS"] = str(TEST_CORPUS_ROOT)
