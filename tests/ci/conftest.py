"""Shared fixtures for tests/ci.

Issue #4541: subprocess tests that build their environment from
``{**os.environ, **env}`` inherit the GitHub Actions writer variables from the
runner and fail only on CI, not locally. This autouse fixture removes those
variables from ``os.environ`` for the duration of every test in this package.

A test that needs one of these variables must set it explicitly via
``monkeypatch.setenv``. That makes the safe form the default form and makes
CI-only failures visible locally.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import bulk_cancel_guard
from tests.ci.bulk_cancel_cli_fixtures import (
    HEALTHY_TYPES,
    REOPEN_OMITTED_TYPES,
    write_workflows,
)

_GHA_WRITER_VARS = (
    "GITHUB_STEP_SUMMARY",
    "GITHUB_OUTPUT",
    "GITHUB_ENV",
    "GITHUB_PATH",
)


@pytest.fixture(autouse=True)
def _scrub_gha_writer_vars(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove GitHub Actions writer variables from os.environ.

    Subprocess helpers that build their env from ``{**os.environ, **overrides}``
    will not see these variables unless the test sets them explicitly. Tests that
    exercise the summary-file branch set ``GITHUB_STEP_SUMMARY`` directly, so
    they are unaffected by this fixture.
    """
    for var in _GHA_WRITER_VARS:
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def workflows(tmp_path: Path) -> Path:
    """A workflow corpus where every incident workflow subscribes to reopened."""
    return write_workflows(tmp_path / "healthy", HEALTHY_TYPES)


@pytest.fixture
def workflows_missing_reopened(tmp_path: Path) -> Path:
    """The 2026-08-09 shape: one required workflow omits ``reopened``."""
    return write_workflows(tmp_path / "omitted", REOPEN_OMITTED_TYPES)


@pytest.fixture(autouse=True)
def _bulk_cancel_default_manifest_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Redirect the guard's default manifest path into tmp_path.

    ``scripts/bulk_cancel_guard.py:_DEFAULT_MANIFEST_PATH`` resolves under this
    repo's own ``.agents/scratch/`` so a real ``--confirm`` run always leaves a
    manifest. Left unpatched, any test exercising ``--confirm`` without
    ``--manifest`` writes into the actual working tree (testing.md MUST 4).
    Autouse and package-wide for the same reason the scrub fixture above is:
    the safe form should be the default form, and a test that forgets is exactly
    the one that pollutes the tree. Nested under a subdirectory so tests also
    exercise ``write_manifest``'s ``mkdir(parents=True)``.
    """
    default_path = tmp_path / "default-manifests" / "bulk-cancel-recovery.json"
    monkeypatch.setattr(bulk_cancel_guard, "_DEFAULT_MANIFEST_PATH", default_path)
    return default_path


@pytest.fixture
def _zero_non_target_aggregate_counts() -> Iterator[None]:
    """Return zero from auxiliary counters only for tests that opt in."""
    with (
        patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.cli_exit_contract_ratchet.current_count", return_value=0),
    ):
        yield
