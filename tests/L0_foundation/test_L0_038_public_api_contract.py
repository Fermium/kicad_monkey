"""Public API contract coverage for promoted package-root exports."""

from __future__ import annotations

import json
from collections import Counter

import pytest

import kicad_monkey
from kicad_monkey.kicad_api_contract import (
    PUBLIC_API_MARKER_ROOT_NAMES,
    PUBLIC_API_ROOT_NAMES,
    PublicApiStratum,
    collect_public_api_contract_failures,
    iter_public_api_exports,
    resolve_public_api_root,
)


def test_promoted_public_api_contract_resolves_cleanly():
    assert collect_public_api_contract_failures() == []


def test_promoted_public_api_contract_is_reviewable_by_stratum():
    exports = iter_public_api_exports()
    names = [export.name for export in exports]
    duplicate_names = sorted(name for name, count in Counter(names).items() if count > 1)

    assert duplicate_names == []
    assert tuple(names) == PUBLIC_API_ROOT_NAMES
    assert set(PUBLIC_API_MARKER_ROOT_NAMES).issubset(PUBLIC_API_ROOT_NAMES)
    assert {export.stratum for export in exports} == set(PublicApiStratum)


def test_promoted_public_api_roots_are_package_exports():
    package_exports = set(getattr(kicad_monkey, "__all__"))

    for name in PUBLIC_API_ROOT_NAMES:
        assert name in package_exports
        assert resolve_public_api_root(name) is getattr(kicad_monkey, name)


@pytest.mark.parametrize("name", PUBLIC_API_MARKER_ROOT_NAMES)
def test_promoted_facade_roots_have_public_api_marker(name):
    assert getattr(resolve_public_api_root(name), "__public_api__", False) is True


def test_public_api_resolver_rejects_unpromoted_names():
    with pytest.raises(KeyError):
        resolve_public_api_root("__not_a_public_api__")


def test_project_parameter_reader_does_not_require_private_toolz_settings(tmp_path):
    project_path = tmp_path / "demo.kicad_pro"
    project_path.write_text(
        json.dumps({"text_variables": {"TITLE": "Demo"}}),
        encoding="utf-8",
    )

    reader = resolve_public_api_root("read_kicad_pro_parameters")

    assert reader(project_path) == {"TITLE": "Demo"}
