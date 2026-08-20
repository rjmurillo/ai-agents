"""Shared fixtures for the reviewer-findings contract suite.

Kept separate from ``_helpers.py`` because pytest auto-discovers fixtures in
``conftest.py`` with no import needed by the test module; a fixture function
would also work if imported into the module namespace, but a dedicated
conftest is the documented, unambiguous pattern. ``PLUGIN_ROOTS`` itself
lives in ``_helpers.py`` (single source of truth shared with the
converse-guard test in the test module); loaded here by file path for the
same reason the test module does: pytest here runs under
``--import-mode=importlib`` (pyproject.toml), which never adds a test
file's own directory to sys.path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_HELPERS_PATH = Path(__file__).resolve().parent / "_helpers.py"
_helpers_spec = importlib.util.spec_from_file_location(
    "reviewer_findings_test_helpers", _HELPERS_PATH
)
assert _helpers_spec is not None and _helpers_spec.loader is not None
_helpers = importlib.util.module_from_spec(_helpers_spec)
_helpers_spec.loader.exec_module(_helpers)

PLUGIN_ROOTS: dict[str, Path] = _helpers.PLUGIN_ROOTS


@pytest.fixture(params=list(PLUGIN_ROOTS), ids=list(PLUGIN_ROOTS))
def plugin_root(request: pytest.FixtureRequest) -> Path:
    """Each shipped copy of the two skills, checked independently."""
    return PLUGIN_ROOTS[request.param]
