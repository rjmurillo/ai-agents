"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validation.models import ValidationResult  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _disable_commit_signing_for_test_git() -> Iterator[None]:
    """Neutralize host ``commit.gpgsign`` for all git subprocesses in the suite.

    Some environments (e.g. Claude web containers) set a global
    ``commit.gpgsign`` backed by a signing server that rejects commits made in
    ``tmp_path`` fixture repos with HTTP 400, breaking the ~57 tests that create
    commits (adr-review, metrics, merge-resolver, worktree tests, ...). Injecting
    ``commit.gpgsign=false`` via ``GIT_CONFIG_COUNT`` gives it command-line
    precedence over host config, so fixtures commit cleanly without per-fixture
    edits (issue #2548). The signing-sensitive tests still RUN (they are not
    skipped); only the signing requirement is removed.

    No test sets ``GIT_CONFIG_COUNT``, so index 0 is free; if some outer process
    already uses the indexed mechanism, this fixture leaves it untouched.
    """
    keys = ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")
    prior = {k: os.environ.get(k) for k in keys}
    if not os.environ.get("GIT_CONFIG_COUNT"):
        os.environ["GIT_CONFIG_COUNT"] = "1"
        os.environ["GIT_CONFIG_KEY_0"] = "commit.gpgsign"
        os.environ["GIT_CONFIG_VALUE_0"] = "false"
    try:
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(autouse=True)
def _default_project_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to the ai-agents project repo (issue #2610).

    ``is_project_repo()`` now resolves repository identity from the git origin
    remote, not from an incidental ``.agents/`` directory. A ``tmp_path`` fixture
    has no such remote, so without this default each guard would treat the test
    as a consumer repo and skip its real work. The suite genuinely runs inside
    the project repo, so ``"1"`` is the correct default. Consumer-repo
    simulation tests override ``AI_AGENTS_PROJECT_REPO`` to ``"0"`` (or unset it
    and stub the git lookup) to exercise the skip path.
    """
    monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "1")


def assert_validation_result(
    result: ValidationResult,
    *,
    is_valid: bool,
    error_count: int | None = None,
    warning_count: int | None = None,
    error_substring: str | None = None,
    warning_substring: str | None = None,
) -> None:
    """Assert properties of a ValidationResult.

    Args:
        result: The ValidationResult to check.
        is_valid: Expected validity.
        error_count: Expected number of errors (None to skip check).
        warning_count: Expected number of warnings (None to skip check).
        error_substring: Substring that must appear in at least one error.
        warning_substring: Substring that must appear in at least one warning.
    """
    assert result.is_valid is is_valid, (
        f"Expected is_valid={is_valid}, got {result.is_valid}. "
        f"Errors: {result.errors}"
    )
    if error_count is not None:
        assert len(result.errors) == error_count, (
            f"Expected {error_count} errors, got {len(result.errors)}: "
            f"{result.errors}"
        )
    if warning_count is not None:
        assert len(result.warnings) == warning_count, (
            f"Expected {warning_count} warnings, got {len(result.warnings)}: "
            f"{result.warnings}"
        )
    if error_substring is not None:
        assert any(error_substring in e for e in result.errors), (
            f"No error contains '{error_substring}'. Errors: {result.errors}"
        )
    if warning_substring is not None:
        assert any(warning_substring in w for w in result.warnings), (
            f"No warning contains '{warning_substring}'. "
            f"Warnings: {result.warnings}"
        )


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture
def temp_test_dir(tmp_path: Path) -> Path:
    """Create and return a temporary directory for test files."""
    test_dir = tmp_path / "test_workspace"
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir

