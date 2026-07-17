#!/usr/bin/env python3
"""Regression coverage for Issue #3111: dev tools split across two dev tables.

The development toolchain lives in two ``pyproject.toml`` tables that different
uv commands read:

* ``[project.optional-dependencies].dev`` (the ``dev`` extra) is what
  ``uv pip install -e ".[dev]"`` installs. uv's pip interface ignores
  dependency groups, so this extra must carry the full tool list.
* ``[dependency-groups].dev`` (the ``dev`` group) is what a plain ``uv sync``
  installs by default. ``uv sync`` does not install extras unless ``--extra`` is
  passed, so this group must also carry the full tool list.

Before #3111 the group held only ``pytest-cov``. A fresh ``uv sync`` therefore
installed pytest (pulled in transitively) but not Ruff, mypy, Bandit, or
pip-audit, so the environment looked ready until the lint and type gates failed.

These tests pin two invariants:

1. Every required dev tool is present in both tables (so both install paths
   yield a complete toolchain).
2. The two ``dev`` declarations do not drift apart, so a future edit to one
   table without the other fails here instead of on a contributor's machine.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Base package names (PEP 503 normalized) that both local commit/push gates and
# CI require. A plain ``uv sync`` and ``uv pip install -e ".[dev]"`` must each
# make all of these importable/runnable.
REQUIRED_DEV_TOOLS = frozenset(
    {"pytest", "pytest-cov", "bandit", "pip-audit", "ruff", "mypy"}
)

# Splits a PEP 508 requirement string at the first character that ends the
# package name: an extras bracket, a version/marker operator, or whitespace.
_NAME_BOUNDARY = re.compile(r"[<>=!~;\[\s@]")


def normalize_name(requirement: str) -> str:
    """Return the PEP 503 normalized project name from a requirement string.

    ``"bandit[sarif]>=1.9.4"`` -> ``"bandit"``; ``"pytest-cov>=7.1.0"`` ->
    ``"pytest-cov"``. Names are lowercased and runs of ``.``, ``_`` and ``-``
    collapse to a single ``-`` so ``pip_audit`` and ``pip-audit`` compare equal.
    """
    raw_name = _NAME_BOUNDARY.split(requirement.strip(), maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", raw_name).lower()


def dev_dependency_drift(
    extra_dev: list[str], group_dev: list[str]
) -> set[str]:
    """Return requirement strings present in exactly one of the two dev tables.

    An empty set means the extra and the group are in parity. A non-empty set
    names the drift so the caller can report which table is missing which pin.
    """
    return set(extra_dev).symmetric_difference(set(group_dev))


def missing_required_tools(requirements: list[str]) -> set[str]:
    """Return required tool names absent from ``requirements``."""
    present = {normalize_name(req) for req in requirements}
    return set(REQUIRED_DEV_TOOLS) - present


def _load_dev_tables() -> tuple[list[str], list[str]]:
    """Read the extra ``dev`` list and the group ``dev`` list from pyproject."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    extra_dev = data["project"]["optional-dependencies"]["dev"]
    group_dev = data["dependency-groups"]["dev"]
    return extra_dev, group_dev


# --- Real pyproject invariants -------------------------------------------------


def test_extra_and_group_dev_do_not_drift() -> None:
    extra_dev, group_dev = _load_dev_tables()

    drift = dev_dependency_drift(extra_dev, group_dev)

    assert drift == set(), (
        "pyproject.toml [project.optional-dependencies].dev and "
        f"[dependency-groups].dev have drifted: {sorted(drift)}. Keep the two "
        "dev tables identical (Issue #3111)."
    )


def test_plain_uv_sync_group_installs_all_required_tools() -> None:
    _extra_dev, group_dev = _load_dev_tables()

    missing = missing_required_tools(group_dev)

    assert missing == set(), (
        "[dependency-groups].dev is missing required tools a plain 'uv sync' "
        f"must install: {sorted(missing)} (Issue #3111)."
    )


def test_pip_install_extra_installs_all_required_tools() -> None:
    extra_dev, _group_dev = _load_dev_tables()

    missing = missing_required_tools(extra_dev)

    assert missing == set(), (
        "[project.optional-dependencies].dev is missing required tools "
        f"'uv pip install -e \".[dev]\"' must install: {sorted(missing)}."
    )


# --- Helper unit coverage (positive, negative, edge) ---------------------------


def test_drift_helper_returns_empty_when_lists_equal_ignoring_order() -> None:
    extra = ["ruff>=0.15.16", "mypy>=2.1.0"]
    group = ["mypy>=2.1.0", "ruff>=0.15.16"]

    assert dev_dependency_drift(extra, group) == set()


def test_drift_helper_flags_tool_missing_from_group() -> None:
    # Reproduces the #3111 shape: the group omits tools the extra declares.
    extra = ["ruff>=0.15.16", "mypy>=2.1.0", "pytest-cov>=7.1.0"]
    group = ["pytest-cov>=7.1.0"]

    assert dev_dependency_drift(extra, group) == {"ruff>=0.15.16", "mypy>=2.1.0"}


def test_drift_helper_flags_version_specifier_mismatch() -> None:
    extra = ["ruff>=0.15.16"]
    group = ["ruff>=0.14.0"]

    assert dev_dependency_drift(extra, group) == {"ruff>=0.15.16", "ruff>=0.14.0"}


def test_missing_required_tools_flags_absent_tools() -> None:
    group = ["pytest-cov>=7.1.0"]

    missing = missing_required_tools(group)

    assert {"ruff", "mypy", "bandit", "pip-audit", "pytest"} <= missing
    assert "pytest-cov" not in missing


def test_missing_required_tools_empty_when_all_present() -> None:
    complete = [
        "pytest>=9.0.3",
        "pytest-cov>=7.1.0",
        "bandit[sarif]>=1.9.4",
        "pip-audit>=2.10.0",
        "ruff>=0.15.16",
        "mypy>=2.1.0",
    ]

    assert missing_required_tools(complete) == set()


def test_normalize_name_strips_extras_and_specifiers() -> None:
    assert normalize_name("bandit[sarif]>=1.9.4") == "bandit"
    assert normalize_name("pytest-cov>=7.1.0") == "pytest-cov"
    assert normalize_name("pip_audit>=2.10.0") == "pip-audit"
    assert normalize_name("mypy") == "mypy"
