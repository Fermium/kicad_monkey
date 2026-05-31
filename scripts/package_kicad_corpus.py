"""Build or validate the public KiCad test-corpus archive."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path, PurePosixPath


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PACKAGE_ROOT / "tests" / "corpus" / "kicad"
DEFAULT_ARCHIVE = PACKAGE_ROOT / "tests" / "corpus" / "kicad.zip"

EXCLUDED_DIR_NAMES = {".git", ".history", ".pytest_cache", "__pycache__", "output", "review", "review_tmp"}
EXCLUDED_FILE_NAMES = {".DS_Store", "Thumbs.db", "fp-info-cache"}
EXCLUDED_SUFFIXES = {".bak", ".kicad_prl", ".lck", ".log", ".tmp", ".zip"}


def _is_excluded_dir(path: Path) -> bool:
    return path.name in EXCLUDED_DIR_NAMES or path.name.lower().endswith("-backups")


def _is_excluded_file(path: Path) -> bool:
    name = path.name
    lower_name = name.lower()
    return (
        name in EXCLUDED_FILE_NAMES
        or path.suffix.lower() in EXCLUDED_SUFFIXES
        or lower_name.startswith("~")
        and lower_name.endswith((".kicad_pro.lck", ".kicad_prl.lck"))
    )


def _iter_source_files(source: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(source.rglob("*")):
        rel_parts = path.relative_to(source).parts
        if any(_is_excluded_dir(Path(part)) for part in rel_parts[:-1]):
            continue
        if path.is_dir():
            continue
        if _is_excluded_file(path):
            continue
        files.append(path)
    return files


def _find_debris(source: Path) -> list[Path]:
    debris: list[Path] = []
    for path in sorted(source.rglob("*")):
        if path.is_dir() and _is_excluded_dir(path):
            debris.append(path)
        elif path.is_file() and _is_excluded_file(path):
            debris.append(path)
    return debris


def _check_archive_member(name: str) -> str | None:
    normalized = name.replace("\\", "/")
    rel = PurePosixPath(normalized)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        return f"unsafe archive path: {name}"
    if rel.parts[0] != "kicad":
        return f"archive member is not under kicad/: {name}"
    if any(part in EXCLUDED_DIR_NAMES or part.lower().endswith("-backups") for part in rel.parts[:-1]):
        return f"archive contains excluded directory member: {name}"
    leaf = Path(rel.name)
    if _is_excluded_file(leaf):
        return f"archive contains generated/editor debris: {name}"
    return None


def validate_archive(archive: Path) -> list[str]:
    if not archive.is_file():
        return [f"archive not found: {archive}"]
    errors: list[str] = []
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        if not any(name.startswith("kicad/") and not name.endswith("/") for name in names):
            errors.append("archive does not contain files under kicad/")
        for name in names:
            error = _check_archive_member(name)
            if error:
                errors.append(error)
    return errors


def build_archive(source: Path, archive: Path) -> None:
    if not source.is_dir():
        raise SystemExit(f"source corpus not found: {source}")
    debris = _find_debris(source)
    if debris:
        preview = "\n".join(f"  - {path.relative_to(source.parent)}" for path in debris[:25])
        extra = "" if len(debris) <= 25 else f"\n  ... {len(debris) - 25} more"
        raise SystemExit(f"refusing to package generated/editor debris:\n{preview}{extra}")

    files = _iter_source_files(source)
    if not files:
        raise SystemExit(f"no corpus files found under {source}")

    archive.parent.mkdir(parents=True, exist_ok=True)
    temp_archive = archive.with_name(f"{archive.name}.tmp.zip")
    if temp_archive.exists():
        temp_archive.unlink()

    with zipfile.ZipFile(temp_archive, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            rel = path.relative_to(source.parent).as_posix()
            info = zipfile.ZipInfo(rel)
            info.date_time = (2026, 5, 31, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes(), compresslevel=9)

    temp_archive.replace(archive)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--check", action="store_true", help="validate the existing archive instead of rebuilding it")
    args = parser.parse_args(argv)

    source = args.source.resolve()
    archive = args.archive.resolve()
    if args.check:
        errors = validate_archive(archive)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print(f"archive ok: {archive}")
        return 0

    build_archive(source, archive)
    errors = validate_archive(archive)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    size_mib = archive.stat().st_size / (1024 * 1024)
    print(f"wrote {archive} ({size_mib:.2f} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
