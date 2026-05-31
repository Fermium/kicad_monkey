from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath

TESTS_DIR = Path(__file__).resolve().parent
KICAD_PACKAGE_ROOT = TESTS_DIR.parent
KICAD_MODULE_ROOT = KICAD_PACKAGE_ROOT / "src" / "py" / "kicad_monkey"
TESTS_REPO_ROOT = KICAD_PACKAGE_ROOT
TEST_CORPUS_DIR = TESTS_DIR / "corpus"
TEST_CORPUS_ARCHIVE = TEST_CORPUS_DIR / "kicad.zip"
TEST_CORPUS_UNPACKED_DIR = TEST_CORPUS_DIR / ".unpacked"


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _archive_stamp(archive: Path) -> str:
    stat = archive.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}\n"


def _safe_extract_corpus_archive(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    target_root = target.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            name = member.filename.replace("\\", "/")
            rel = PurePosixPath(name)
            if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                raise RuntimeError(f"Unsafe corpus archive member: {member.filename!r}")
            if rel.parts[0] != "kicad":
                raise RuntimeError(f"Corpus archive must contain a top-level kicad/ directory: {member.filename!r}")
            destination = (target / Path(*rel.parts)).resolve()
            if not _is_inside(destination, target_root):
                raise RuntimeError(f"Unsafe corpus archive destination: {destination}")
        zf.extractall(target)


def _ensure_local_test_corpus() -> Path:
    loose_root = TEST_CORPUS_DIR / "kicad"
    if loose_root.is_dir():
        return TEST_CORPUS_DIR
    if not TEST_CORPUS_ARCHIVE.is_file():
        return TEST_CORPUS_DIR

    stamp = _archive_stamp(TEST_CORPUS_ARCHIVE)
    marker = TEST_CORPUS_UNPACKED_DIR / ".kicad.zip.stamp"
    extracted_root = TEST_CORPUS_UNPACKED_DIR / "kicad"
    if extracted_root.is_dir() and marker.is_file() and marker.read_text(encoding="utf-8") == stamp:
        return TEST_CORPUS_UNPACKED_DIR

    if not _is_inside(TEST_CORPUS_UNPACKED_DIR, TEST_CORPUS_DIR):
        raise RuntimeError(f"Refusing to extract outside test corpus directory: {TEST_CORPUS_UNPACKED_DIR}")
    temp_root = TEST_CORPUS_UNPACKED_DIR / "_extracting_kicad"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    TEST_CORPUS_UNPACKED_DIR.mkdir(parents=True, exist_ok=True)
    _safe_extract_corpus_archive(TEST_CORPUS_ARCHIVE, temp_root)
    unpacked_kicad = temp_root / "kicad"
    if not unpacked_kicad.is_dir():
        raise RuntimeError(f"Corpus archive did not produce kicad/: {TEST_CORPUS_ARCHIVE}")
    if extracted_root.exists():
        shutil.rmtree(extracted_root)
    unpacked_kicad.rename(extracted_root)
    shutil.rmtree(temp_root)
    marker.write_text(stamp, encoding="utf-8")
    return TEST_CORPUS_UNPACKED_DIR


TEST_CORPUS_ROOT = _ensure_local_test_corpus()


def ensure_import_paths() -> None:
    paths = [TESTS_DIR, KICAD_PACKAGE_ROOT / "src" / "py"]
    for path in paths:
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)
