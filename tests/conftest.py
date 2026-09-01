"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validation.models import ValidationResult  # noqa: E402
from tests.gc_real_git import GitSandbox, git, write_and_commit  # noqa: E402
from tests.git_config_isolation import (  # noqa: E402
    restore_git_config_env,
    snapshot_git_config_env,
    strip_git_config_hooks_path,
)

_NUMBERED_GIT_CONFIG = re.compile(r"^GIT_CONFIG_(KEY|VALUE)_\d+$")


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
    # Every remaining indexed entry is inherited, so it belongs to some outer
    # process and applies to every git command a test runs, including commands
    # against the test's own sandbox. Deferring to it, which is what the
    # previous "only inject when the count is unset" guard did, meant any
    # caller using the indexed mechanism silently disarmed this protection. The
    # Copilot CLI harness sets GIT_CONFIG_COUNT=3 for safe.bareRepository, so on
    # that harness the protection was never active and the test guarding it
    # reported a skip rather than a failure. Clearing first makes index 0 free
    # by construction. The snapshot above is restored on teardown, so the
    # caller's configuration survives the session. Refs #2548, #4717.
    for name in [
        key
        for key in os.environ
        if key == "GIT_CONFIG_COUNT" or _NUMBERED_GIT_CONFIG.match(key)
    ]:
        del os.environ[name]
    os.environ["GIT_CONFIG_COUNT"] = "1"
    os.environ["GIT_CONFIG_KEY_0"] = "commit.gpgsign"
    os.environ["GIT_CONFIG_VALUE_0"] = "false"
    try:
        yield
    finally:
        restore_git_config_env(os.environ, snapshot)


@pytest.fixture(autouse=True)
def _clear_ci_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear CI from every test so behavior does not depend on ambient env.

    Tests that need CI set must do so explicitly via monkeypatch.setenv.
    Mirrors the same fixture in tests/validation/conftest.py, which only
    covers files under that package. The test_validation_*.py files
    in tests/ root and any other file in this directory that reads CI
    inherit ambient CI from the caller's environment without this fixture.
    See issue #4380.
    """
    monkeypatch.delenv("CI", raising=False)


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

# The suite owns exactly this injection (see the session fixture above), so the
# per-test sanitizer must not remove it. Everything else in the GIT_CONFIG
# family is inherited and therefore hostile.
_SUITE_OWNED_GIT_CONFIG = {
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "commit.gpgsign",
    "GIT_CONFIG_VALUE_0": "false",
}

_GIT_CONFIG_ENV_VARS = ("GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS")


_LOCAL_ENV_VARS_CACHE: list[tuple[str, ...]] = []


def _local_env_vars() -> tuple[str, ...]:
    """Every repository-scoped variable git itself honors.

    Asking git beats maintaining the list by hand. The hand-written version
    missed ``GIT_CONFIG``, which redirects ``git config`` writes at an arbitrary
    file and so is a write path into the real checkout, along with
    ``GIT_GRAFT_FILE``, ``GIT_SHALLOW_FILE``, ``GIT_REPLACE_REF_BASE``,
    ``GIT_NO_REPLACE_OBJECTS``, and ``GIT_IMPLICIT_WORK_TREE``. Refs #4717.

    Falls back to the hand-written set if git is unavailable, since an
    environment with no git cannot run the tests this protects anyway. Only a
    successful discovery is memoized; the fallback is recomputed on every
    call. A transient subprocess failure (a fork failure under load, a
    30-second timeout) is not "git is not installed", and caching it would
    pin the six-name fallback for the rest of the worker process even after
    git starts answering again, silently dropping GIT_CONFIG and the other
    five names the fallback lacks for every remaining test item in that
    worker. Refs #5379.

    Cached because the result depends only on the installed git version, not
    on per-test state: the variable *names* git honors do not change between
    test items, only the *values* the caller reads from ``os.environ`` do
    (still re-read fresh on every test, see ``_sanitize_git_environment``).
    Uncached, this spawned one ``git rev-parse`` subprocess per test item,
    roughly 30,000 short-lived processes across a full run, multiplied across
    xdist workers. Refs #5379.

    Call ``_local_env_vars.cache_clear()`` to force rediscovery. This is the
    supported seam for tests that need to change the installed git's reported
    variable set mid-run.
    """
    if _LOCAL_ENV_VARS_CACHE:
        return _LOCAL_ENV_VARS_CACHE[0]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--local-env-vars"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return _GIT_POINTER_VARS
    names = tuple(line.strip() for line in result.stdout.splitlines() if line.strip())
    discovered = names or _GIT_POINTER_VARS
    _LOCAL_ENV_VARS_CACHE.append(discovered)
    return discovered


_local_env_vars.cache_clear = _LOCAL_ENV_VARS_CACHE.clear


def _sanitize_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every inherited pointer to, and config override for, a repository.

    ``GIT_CONFIG_COUNT`` names how many ``GIT_CONFIG_KEY_n`` and
    ``GIT_CONFIG_VALUE_n`` pairs follow, so the count alone is not enough to
    delete: git ignores the pairs without it, but a later ``GIT_CONFIG_COUNT``
    set by code under test would make the stale pairs live again. The numbered
    pairs are therefore removed alongside the count.

    The suite's own ``commit.gpgsign=false`` injection is preserved. Removing it
    disarmed the protection from issue #2548 for every test and turned the test
    guarding it into a silent skip, which is a worse outcome than the leak this
    function exists to stop.
    """
    suite_owns_config = all(
        os.environ.get(name) == value
        for name, value in _SUITE_OWNED_GIT_CONFIG.items()
    )
    for name in set(_local_env_vars()) | set(_GIT_POINTER_VARS):
        if suite_owns_config and name in _SUITE_OWNED_GIT_CONFIG:
            continue
        monkeypatch.delenv(name, raising=False)
    for name in [key for key in os.environ if _NUMBERED_GIT_CONFIG.match(key)]:
        if suite_owns_config and name in _SUITE_OWNED_GIT_CONFIG:
            continue
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _isolate_tmp_path_from_parent_git_repo(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stop any test from reaching the surrounding checkout through git.

    ``GIT_CEILING_DIRECTORIES`` only bounds git's upward discovery walk. It is
    inert when ``GIT_DIR`` is already set in the environment, because an
    explicit ``GIT_DIR`` bypasses discovery entirely. Any git command run with
    only the ceiling and an inherited ``GIT_DIR`` operates on the repository
    that ``GIT_DIR`` names, not on the temp tree. Refs #4287.

    Sanitizing runs for every test, not only those requesting ``tmp_path``.
    Whether a test can damage the real checkout depends on whether it runs git,
    which is unrelated to how it spells its sandbox. Keying on ``tmp_path`` left
    the modules that build sandboxes with ``tempfile`` completely unprotected,
    including the one that exercises real worktrees and real commits. Two live
    worktrees were corrupted before that gap was found, both only ever during a
    hook-driven run, since the hook is what mutates the environment. Refs #4717.

    The ceiling still needs a path, so it stays conditional on ``tmp_path``.
    Unsetting an inherited pointer does not.
    """
    _sanitize_git_environment(monkeypatch)
    if "tmp_path" not in request.fixturenames:
        return
    tmp_path = request.getfixturevalue("tmp_path")
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
        f"Expected is_valid={is_valid}, got {result.is_valid}. Errors: {result.errors}"
    )
    if error_count is not None:
        assert len(result.errors) == error_count, (
            f"Expected {error_count} errors, got {len(result.errors)}: {result.errors}"
        )
    if warning_count is not None:
        assert len(result.warnings) == warning_count, (
            f"Expected {warning_count} warnings, got {len(result.warnings)}: {result.warnings}"
        )
    if error_substring is not None:
        assert any(error_substring in e for e in result.errors), (
            f"No error contains '{error_substring}'. Errors: {result.errors}"
        )
    if warning_substring is not None:
        assert any(warning_substring in w for w in result.warnings), (
            f"No warning contains '{warning_substring}'. Warnings: {result.warnings}"
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


@pytest.fixture
def git_sandbox() -> Iterator[GitSandbox]:
    """A disposable repository with an origin remote, for the worktree GC suites.

    Lives here rather than beside its helpers in ``tests/gc_real_git`` so the
    four suites that use it get it by pytest discovery. Importing a fixture by
    name makes the parameter that requests it read as a redefinition.

    ``.pytest_tmp`` sits inside the repository on purpose: these tests register
    worktrees and git records absolute paths, so keeping the sandbox on the same
    filesystem avoids cross-device behavior that has nothing to do with the
    thing under test.
    """
    temp_parent = Path(__file__).resolve().parents[1] / ".pytest_tmp" / "gc_worktrees"
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gc-", dir=temp_parent) as temp_dir:
        root = Path(temp_dir)
        remote = root / "origin.git"
        main = root / "repo"
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(remote)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        subprocess.run(
            ["git", "clone", str(remote), str(main)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        git(main, "config", "user.email", "test@example.com")
        git(main, "config", "user.name", "Test User")
        git(main, "config", "commit.gpgsign", "false")
        write_and_commit(main, "base.txt", "base\n", "base")
        git(main, "push", "-u", "origin", "main")
        yield GitSandbox(root=root, main=main, remote=remote)
