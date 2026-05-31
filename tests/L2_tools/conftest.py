"""L2_tools pytest configuration and shared corpus helpers."""

from pathlib import Path

import pytest

from kicad_monkey.testing.corpus import (
    get_kicad_common_board_case_file,
    get_kicad_common_footprints_dir,
    get_kicad_common_reference_symbols_dir,
    get_kicad_topic_input_dir,
)
from _suite_paths import KICAD_MODULE_ROOT, KICAD_PACKAGE_ROOT

PROJECT_ROOT = KICAD_PACKAGE_ROOT
STRATUM_DIR = Path(__file__).parent

SPEEDY_PCB_PATH = get_kicad_common_board_case_file("speedy", "speedy.kicad_pcb")
SPEEDY_SYMBOL_SCHEMATIC_PATH = get_kicad_common_board_case_file("speedy", "TPS62A02_BUCK.kicad_sch")
COMMON_FOOTPRINTS_DIR = get_kicad_common_footprints_dir()
COMMON_REFERENCE_SYMBOLS_DIR = get_kicad_common_reference_symbols_dir()
STEP_MODEL_EXTRACT_DIR = get_kicad_topic_input_dir("step_model_extract")


@pytest.fixture
def speedy_pcb_path() -> Path:
    return SPEEDY_PCB_PATH


@pytest.fixture
def speedy_symbol_schematic_path() -> Path:
    return SPEEDY_SYMBOL_SCHEMATIC_PATH


@pytest.fixture
def common_footprints_dir() -> Path:
    return COMMON_FOOTPRINTS_DIR


@pytest.fixture
def common_reference_symbols_dir() -> Path:
    return COMMON_REFERENCE_SYMBOLS_DIR


@pytest.fixture
def step_model_extract_dir() -> Path:
    return STEP_MODEL_EXTRACT_DIR
