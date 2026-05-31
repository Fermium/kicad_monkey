"""Release signoff tests for the public KiCad Monkey package."""

from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path

import kicad_monkey
from kicad_monkey import __version__, version
from kicad_monkey.kicad_api_contract import collect_public_api_contract_failures


def _project_root() -> Path:
    """Find the repository root from this test file."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("Could not locate repository root")


PACKAGE_ROOT = _project_root()
EXPECTED_VERSION = "2026.5.31"
EXPECTED_RELEASE_DATE = date(2026, 5, 31)


def test_version_contract_matches_date_based_release() -> None:
    """Verify that package metadata follows the date release contract."""
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    parsed = version()

    assert pyproject["project"]["version"] == EXPECTED_VERSION
    assert __version__ == EXPECTED_VERSION
    assert kicad_monkey.__version__ == EXPECTED_VERSION
    assert parsed.string == EXPECTED_VERSION
    assert (parsed.major, parsed.minor, parsed.patch, parsed.build) == (
        2026,
        5,
        31,
        None,
    )
    assert parsed.release_date == EXPECTED_RELEASE_DATE
    assert parsed.release_date <= date.today()


def test_changelog_mentions_package_version() -> None:
    """Verify that release notes mention the current package version."""
    changelog = (PACKAGE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = (
        PACKAGE_ROOT / "docs" / "releases" / f"{EXPECTED_RELEASE_DATE.isoformat()}.md"
    ).read_text(encoding="utf-8")

    assert f"## {EXPECTED_VERSION}" in changelog
    assert f"`{EXPECTED_VERSION}`" in release_notes


def test_public_package_metadata_is_declared() -> None:
    """Verify public package metadata needed for PyPI and GitHub is present."""
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["license"]["text"] == "MIT"
    assert project["authors"] == [{"name": "Wavenumber LLC"}]
    assert project["urls"]["Repository"] == "https://github.com/wavenumber-eng/kicad_monkey"
    assert (PACKAGE_ROOT / "LICENSE").exists()


def test_public_repository_support_files_are_declared() -> None:
    """Verify public contribution, issue, CI, and release files exist."""
    required_paths = (
        "CONTRIBUTING.md",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    )

    missing = [path for path in required_paths if not (PACKAGE_ROOT / path).exists()]

    assert missing == []


def test_developer_working_docs_are_excluded_from_release_artifacts() -> None:
    """Verify that developer-only plan and research docs are not packaged."""
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    sdist = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]

    assert "docs/**" in sdist["include"]
    assert "LICENSE" in sdist["include"]
    assert "CONTRIBUTING.md" in sdist["include"]
    assert "docs/plans/**" in sdist["exclude"]
    assert "docs/research/**" in sdist["exclude"]
    assert "tests/corpus/**" in sdist["exclude"]


def test_promoted_public_api_contract_has_no_failures() -> None:
    """Verify the promoted package-root API contract is part of L99 signoff."""
    assert collect_public_api_contract_failures() == []
