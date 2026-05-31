"""L4_applications pytest configuration and shared corpus fixtures."""

import shutil
from pathlib import Path

import pytest

from kicad_monkey.testing.corpus import (
    get_kicad_common_board_case_dir,
    get_kicad_common_footprints_dir,
)
from _suite_paths import KICAD_MODULE_ROOT, KICAD_PACKAGE_ROOT

PROJECT_ROOT = KICAD_PACKAGE_ROOT
STRATUM_DIR = Path(__file__).parent
TESTS_DIR = STRATUM_DIR.parent

PROJECT_DIR = get_kicad_common_board_case_dir("speedy")
FOOTPRINTS_DIR = get_kicad_common_footprints_dir()


# ============================================================================
# KiCad CLI Discovery
# ============================================================================

# Default KiCad CLI paths (Windows)
KICAD_CLI_PATHS = [
    Path("C:/Program Files/KiCad/9.0/bin/kicad-cli.exe"),
    Path("C:/Program Files/KiCad/8.0/bin/kicad-cli.exe"),
    Path("C:/Program Files/KiCad/7.0/bin/kicad-cli.exe"),
]


def find_kicad_cli() -> Path | None:
    """Find kicad-cli executable."""
    # Check PATH first
    cli = shutil.which("kicad-cli")
    if cli:
        return Path(cli)

    # Check common install locations
    for path in KICAD_CLI_PATHS:
        if path.exists():
            return path

    return None


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_cases_dir() -> Path:
    """Return the KiCad shared corpus root for application tests."""
    return PROJECT_DIR.parent.parent.parent


@pytest.fixture
def project_dir() -> Path:
    """Return the shared project directory."""
    return PROJECT_DIR


@pytest.fixture
def speedy_project_dir() -> Path:
    """Return the shared speedy project directory."""
    return PROJECT_DIR


@pytest.fixture
def footprints_dir() -> Path:
    """Return the shared footprints directory."""
    return FOOTPRINTS_DIR


@pytest.fixture
def kicad_cli():
    """Fixture that provides kicad-cli path or skips test."""
    cli = find_kicad_cli()
    if cli is None:
        pytest.skip("kicad-cli not found - skipping validation tests")
    return cli
