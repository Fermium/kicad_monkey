"""L1_parsing pytest configuration and fixtures."""

from pathlib import Path

import pytest

from kicad_monkey.testing.corpus import (
    get_kicad_common_boards_dir,
    get_kicad_common_footprints_dir,
    get_kicad_common_reference_schematics_dir,
    get_kicad_common_reference_symbols_dir,
    get_kicad_common_reference_worksheets_dir,
)
from _suite_paths import KICAD_MODULE_ROOT, KICAD_PACKAGE_ROOT

PROJECT_ROOT = KICAD_PACKAGE_ROOT
STRATUM_DIR = Path(__file__).parent


@pytest.fixture
def test_cases_dir() -> Path:
    """Return the shared KiCad board corpus directory."""
    return get_kicad_common_boards_dir()


@pytest.fixture
def board_test_cases_dir() -> Path:
    """Return the shared board corpus directory."""
    return get_kicad_common_boards_dir()


@pytest.fixture
def footprint_test_cases_dir() -> Path:
    """Return the shared footprint corpus directory."""
    return get_kicad_common_footprints_dir()


def get_all_pcb_files() -> list[Path]:
    """Discover all .kicad_pcb files in the shared KiCad board corpus."""
    return sorted(get_kicad_common_boards_dir().glob("**/*.kicad_pcb"))


def get_pcb_test_ids() -> list[str]:
    """Get human-readable test case IDs for PCB files."""
    return [p.parent.name for p in get_all_pcb_files()]


def get_all_footprint_files() -> list[Path]:
    """Discover all .kicad_mod files in the shared KiCad footprint corpus."""
    return sorted(get_kicad_common_footprints_dir().glob("*.kicad_mod"))


def get_footprint_test_ids() -> list[str]:
    """Get human-readable test IDs (footprint filenames without extension)."""
    return [p.stem for p in get_all_footprint_files()]


def get_sample_footprints(max_count: int = 50) -> list[Path]:
    """Get a representative sample of footprints for faster testing."""
    all_fps = get_all_footprint_files()
    if len(all_fps) <= max_count:
        return all_fps

    # Take evenly spaced samples
    step = len(all_fps) // max_count
    return [all_fps[i] for i in range(0, len(all_fps), step)][:max_count]


def get_sample_footprint_ids(max_count: int = 50) -> list[str]:
    """Get IDs for sample footprints."""
    return [p.stem for p in get_sample_footprints(max_count)]


# =============================================================================
# Symbol Library Test Cases (stratum-local)
# =============================================================================

def get_symbol_files() -> list[Path]:
    """Discover all shared reference symbol libraries."""
    return sorted(get_kicad_common_reference_symbols_dir().glob("*.kicad_sym"))


def get_symbol_test_ids() -> list[str]:
    """Get human-readable test IDs (symbol filenames without extension)."""
    return [p.stem for p in get_symbol_files()]


# =============================================================================
# Schematic Test Cases (stratum-local)
# =============================================================================

def get_schematic_files() -> list[Path]:
    """Discover all shared reference schematics."""
    return sorted(get_kicad_common_reference_schematics_dir().glob("*.kicad_sch"))


def get_schematic_test_ids() -> list[str]:
    """Get human-readable test IDs (schematic filenames without extension)."""
    return [p.stem for p in get_schematic_files()]


def get_worksheet_files() -> list[Path]:
    """Discover all shared reference worksheets."""
    return sorted(get_kicad_common_reference_worksheets_dir().glob("*.kicad_wks"))


def get_worksheet_test_ids() -> list[str]:
    """Get human-readable worksheet IDs."""
    return [p.stem for p in get_worksheet_files()]
