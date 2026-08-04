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

import pytest

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
