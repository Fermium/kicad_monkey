"""L0_foundation pytest configuration and fixtures."""

import pytest


@pytest.fixture
def simple_sexp_samples():
    """Sample S-expressions for testing.

    Provides a dictionary of test S-expression strings covering:
    - Simple atoms and numbers
    - Nested lists
    - Quoted strings
    - Mixed types
    - Escaped characters
    - Empty strings
    """
    return {
        "simple": "(test 123)",
        "nested": "(outer (inner 1 2) 3)",
        "quoted": '(data "quoted string")',
        "mixed": '(test "string" 123 4.5)',
        "escaped": r'(data "with \"escaped quotes\"")',
        "empty_string": '(test "")',
    }
