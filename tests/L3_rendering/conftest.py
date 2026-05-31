"""L3_rendering pytest configuration and fixtures."""

import sys
from pathlib import Path

import pytest

from kicad_monkey.testing.corpus import get_kicad_topic_dir
from _suite_paths import KICAD_MODULE_ROOT, KICAD_PACKAGE_ROOT, WORKSPACE_ROOT


def _add_local_wn_rack_to_path() -> None:
    """Prefer a local wn-rack checkout when this suite runs from a worktree."""
    for root in (WORKSPACE_ROOT, *WORKSPACE_ROOT.parents):
        candidate = root / "wn-rack" / "src"
        if (candidate / "rack" / "cli.py").is_file():
            candidate_text = str(candidate)
            if candidate_text not in sys.path:
                sys.path.insert(0, candidate_text)
            return


_add_local_wn_rack_to_path()

# wn-rack is declared as a dev dep of kicad_monkey but environments
# without it (e.g. minimal CI lanes) should still run SVG equivalence tests.
# Defer the import; when unavailable, use a no-op collector for optional report
# artifacts while preserving the test assertions themselves.
try:
    from rack.cli import RackOutput, clear_current_output, set_current_output
    _RACK_AVAILABLE = True
    _RACK_IMPORT_ERR: 'BaseException | None' = None
except Exception as _exc:  # pragma: no cover
    _RACK_AVAILABLE = False
    _RACK_IMPORT_ERR = _exc
    RackOutput = None  # type: ignore[assignment]
    clear_current_output = None  # type: ignore[assignment]
    set_current_output = None  # type: ignore[assignment]

PROJECT_ROOT = KICAD_PACKAGE_ROOT

# Test cases directory (legacy local location for synthetic/support files only)
STRATUM_DIR = Path(__file__).parent
TESTS_DIR = STRATUM_DIR.parent
TEST_CASES_DIR = TESTS_DIR / "test_cases"

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# SVG-specific test directories
SVG_TEST_DIR = TEST_CASES_DIR / "svg"
# Legacy ``board_svg/`` topic dir was retired 2026-05-17 — synthetic
# boards now live under ``kicad/pcb_foundation/<case>/`` via
# ``get_kicad_pcb_foundation_dir()``. The schematic/footprint topic dirs
# still follow the topic_dir pattern.
FOOTPRINT_SVG_DIR = get_kicad_topic_dir("footprint_svg")


@pytest.fixture
def test_cases_dir() -> Path:
    """Return the central test_cases directory path."""
    return TEST_CASES_DIR


@pytest.fixture
def svg_test_dir() -> Path:
    """Return the SVG test cases directory."""
    return SVG_TEST_DIR


@pytest.fixture
def footprint_svg_input_dir() -> Path:
    """Return the footprint SVG input directory."""
    return FOOTPRINT_SVG_DIR / "input"


@pytest.fixture
def footprint_svg_reference_dir() -> Path:
    """Return the footprint SVG reference output directory."""
    return FOOTPRINT_SVG_DIR / "reference_output"


@pytest.fixture
def footprint_svg_output_dir() -> Path:
    """Return the footprint SVG test output directory."""
    output_dir = STRATUM_DIR / "output" / "footprint_svg"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# =============================================================================
# RackOutput Fixture (RACK-027)
# =============================================================================

@pytest.fixture
def rack_output(request):
    """
    Provide a RackOutput instance for collecting structured test data.

    The fixture automatically:
    - Sets test_id, test_file, test_name from pytest
    - Saves output to rack_results/output/ after test completes
    - Makes output available via get_current_output() for nested calls

    Usage in tests:
        def test_example(rack_output):
            rack_output.add_metric("file_size", 12345)
            rack_output.add_svg_output("python", output_file, "Python Generated")
            assert condition

    The output is saved regardless of test outcome.
    """
    if not _RACK_AVAILABLE:
        class NoopRackOutput:
            def __init__(self):
                self.metrics = {}
                self.timings = {}
                self.comparisons = []
                self.attachments = []
                self.svg_outputs = []
                self.tags = []
                self.status = None

            def add_metric(self, name, value):
                self.metrics[name] = value

            def add_svg_output(self, name, path, description=""):
                self.svg_outputs.append({
                    "name": name,
                    "path": str(path),
                    "description": description,
                })

            def save(self):
                return None

        yield NoopRackOutput()
        return
    # Create output with test identification
    output = RackOutput(
        test_id=request.node.nodeid,
        test_file=request.node.fspath.basename if request.node.fspath else "",
        test_name=request.node.name,
    )

    # Make available to nested code via thread-local storage
    set_current_output(output)

    # Yield to test
    yield output

    # After test completes, save output if any data was collected
    has_data = (
        output.metrics
        or output.timings
        or output.comparisons
        or output.attachments
        or output.svg_outputs
        or output.tags
        or output.status
    )

    if has_data:
        output.save()

    # Clean up thread-local storage
    clear_current_output()
