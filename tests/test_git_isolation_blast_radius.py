"""The test suite must not be able to reach the surrounding checkout.

These are negative controls for ``tests/conftest.py``. They set a hostile
environment of the exact shape git hands to a hook, then assert that a decoy
repository standing in for the developer's checkout is untouched.

They exist because the previous isolation fixture only ran for tests that
requested ``tmp_path``, so modules building sandboxes with ``tempfile`` were
unprotected, and because the config-injection family was never unset at all.
Two live worktrees were corrupted before either gap was found. Asserting the
fixture's internals would not have caught it; asserting the blast radius does.
Refs #4717, #4287, #4698.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.conftest import (
    _GIT_CONFIG_ENV_VARS,
    _GIT_POINTER_VARS,
    _NUMBERED_GIT_CONFIG,
)

_HOSTILE_CONFIG = {
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "core.bare",
    "GIT_CONFIG_VALUE_0": "true",
}


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def decoy_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real repository standing in for the developer's checkout."""
    repo = tmp_path_factory.mktemp("decoy")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "decoy@example.invalid")
    _git(repo, "config", "user.name", "Decoy")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "kept.txt").write_text("original\n", encoding="utf-8")
    _git(repo, "add", "kept.txt")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-qm", "base")
    return repo


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def test_pointer_vars_are_unset_without_tmp_path() -> None:
    """Isolation must not depend on the test requesting ``tmp_path``.

    This test deliberately does not use the ``tmp_path`` fixture. Under the
    previous predicate it would have received no sanitizing whatsoever, so a
    pointer inherited from a hook environment would still be set here.

    Reading ``os.environ`` inside the body is the real check: the autouse
    fixture has already run by this point, so this observes the environment the
    test actually executes in rather than a snapshot taken at import time.
    """
    leaked = [name for name in _GIT_POINTER_VARS if name in os.environ]
    assert not leaked, (
        f"git pointer vars leaked into a test that did not request tmp_path: "
        f"{leaked}"
    )


def test_config_injection_vars_are_unset() -> None:
    """``GIT_CONFIG_*`` applies to every git command and must not survive."""
    leaked = [name for name in _GIT_CONFIG_ENV_VARS if name in os.environ]
    leaked += [k for k in os.environ if _NUMBERED_GIT_CONFIG.match(k)]
    assert not leaked, f"git config injection vars leaked into the test: {leaked}"


# The module that builds real repositories and real worktrees with ``tempfile``
# rather than ``tmp_path``. It received no isolation at all under the previous
# predicate, which makes it the honest subject for a blast-radius control.
_AT_RISK_MODULE = "tests/test_gc_worktrees_real_git.py"


def test_hostile_environment_at_startup_cannot_reach_the_decoy(
    decoy_repo: Path,
) -> None:
    """The real threat model: pytest inherits a hostile environment.

    Git exports ``GIT_CONFIG_COUNT`` and friends to hooks, and the pre-commit
    and pre-push stages run pytest, so a suite launched from a hook starts with
    pointers and config it never set. This runs a child pytest over the module
    that manipulates real repositories under exactly that environment, then
    asserts the decoy standing in for the developer's checkout is untouched.

    A child process is required. The autouse fixture sanitizes at test entry,
    so a hostile value assigned inside a test body is not something it can or
    should defend against; only the inherited case is in scope.

    The subject is a real module rather than a synthetic probe on purpose. A
    probe written to a temp directory would sit outside the ``tests`` tree and
    so would never load ``tests/conftest.py``, which makes it a test of pytest
    conftest scoping rather than of this fixture.
    """
    repo_root = Path(__file__).resolve().parents[1]
    before = _head(decoy_repo)

    hostile = dict(os.environ)
    hostile["GIT_DIR"] = str(decoy_repo / ".git")
    hostile["GIT_INDEX_FILE"] = str(decoy_repo / ".git" / "index")
    hostile.update(_HOSTILE_CONFIG)

    subprocess.run(
        ["python", "-m", "pytest", _AT_RISK_MODULE, "-q", "-p", "no:randomly"],
        cwd=str(repo_root),
        env=hostile,
        capture_output=True,
        text=True,
        check=False,
    )

    assert _head(decoy_repo) == before, (
        "a child pytest run under a hook-shaped environment committed into the "
        "decoy repository; this is the corruption in #4717"
    )
    bare = subprocess.run(
        ["git", "config", "--get", "core.bare"],
        cwd=str(decoy_repo),
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    assert bare != "true", (
        "injected core.bare=true reached the decoy config; this is #4698"
    )
