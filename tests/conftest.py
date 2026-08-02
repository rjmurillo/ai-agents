"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import os
import shutil
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validation.models import ValidationResult  # noqa: E402
from tests.git_config_isolation import (  # noqa: E402
    restore_git_config_env,
    snapshot_git_config_env,
    strip_git_config_hooks_path,
)


@pytest.fixture(autouse=True, scope="session")
def _isolate_git_config_for_test_git() -> Iterator[None]:
    """Make git-config hermetic for all git subprocesses in the suite.

    Two host-environment leaks break ``tmp_path`` fixture commits, so both are
    neutralized here (the whole ``GIT_CONFIG*`` namespace is snapshotted and
    restored on teardown):

    1. ``commit.gpgsign`` (issue #2548). Some environments (e.g. Claude web
       containers) set a global ``commit.gpgsign`` backed by a signing server
       that rejects fixture commits with HTTP 400, breaking the ~57 tests that
       create commits. Injecting ``commit.gpgsign=false`` via
       ``GIT_CONFIG_COUNT`` gives it command-line precedence over host config.

    2. ``core.hooksPath`` (issue #2996). ``git -c core.hooksPath=/abs push``
       re-exports the override to child processes via ``GIT_CONFIG_PARAMETERS``.
       An *absolute* hooks path (used when pushing from a linked worktree)
       resolves inside every fixture repo, so each ``git commit`` runs the real
       pre-commit hook and fails outside the repo (~84 failures observed on the
       #2925 push). ``GIT_CONFIG_PARAMETERS`` outranks the indexed form, so an
       empty override cannot win; the leaked key is stripped instead.

    No test sets ``GIT_CONFIG_COUNT``, so index 0 is free after the strip; if
    some outer process already uses the indexed mechanism, gpgsign injection is
    skipped and left to that process.
    """
    snapshot = snapshot_git_config_env(os.environ)
    strip_git_config_hooks_path(os.environ)
    if not os.environ.get("GIT_CONFIG_COUNT"):
        os.environ["GIT_CONFIG_COUNT"] = "1"
        os.environ["GIT_CONFIG_KEY_0"] = "commit.gpgsign"
        os.environ["GIT_CONFIG_VALUE_0"] = "false"
    try:
        yield
    finally:
        restore_git_config_env(os.environ, snapshot)


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


_GIT_POINTER_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


@pytest.fixture(autouse=True)
def _isolate_tmp_path_from_parent_git_repo(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prevent repo-local pytest temp dirs from discovering the parent checkout.

    ``GIT_CEILING_DIRECTORIES`` only bounds git's upward discovery walk. It is
    inert when ``GIT_DIR`` is already set in the environment, because an
    explicit ``GIT_DIR`` bypasses discovery entirely. Any git command run with
    only the ceiling and an inherited ``GIT_DIR`` operates on the repository
    that ``GIT_DIR`` names, not on the temp tree. This fixture unsets every
    pointer variable before setting the ceiling so that a hostile caller
    environment cannot silently redirect git operations away from ``tmp_path``.
    Refs #4287.
    """
    if "tmp_path" not in request.fixturenames:
        return
    tmp_path = request.getfixturevalue("tmp_path")
    for name in _GIT_POINTER_VARS:
        monkeypatch.delenv(name, raising=False)
    existing = os.environ.get("GIT_CEILING_DIRECTORIES")
    ceiling = str(tmp_path.parent)
    value = ceiling if not existing else f"{ceiling}{os.pathsep}{existing}"
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", value)


@pytest.fixture
def external_tmp_path() -> Iterator[Path]:
    """Create a temp directory outside the checkout for path-boundary tests."""
    # Imported here rather than at module scope: the helper lives under `tests`,
    # which only becomes importable after the sys.path insert above.
    from tests.external_scratch import outside_every_repository

    root = outside_every_repository(PROJECT_ROOT) / f".pytest-external-{PROJECT_ROOT.name}"
    path = root / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


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
