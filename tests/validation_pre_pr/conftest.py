"""Shared fixtures for ``tests/validation_pre_pr/``.

Home for setup that more than one gate's test file needs, so a change to the
shape of "a repo with a resolvable base ref" is made once instead of copied
per file. Currently used by the worktree-only-change regression tests in
``test_workflow_checks.py`` and ``test_yaml_style_checks.py``, and by
``test_changed_paths_since_base.py``'s real-repo integration tests.

Exposed as fixtures (``git_cmd``, ``make_repo_with_base``, ``no_gh``) rather
than plain importable functions: this directory has no ``__init__.py``, so
each ``test_*.py`` file is collected as an independent top-level module, not
a submodule of a package. A ``from .conftest import ...`` relative import
would fail with "attempted relative import with no known parent package" in
that layout; pytest's fixture-injection mechanism is the layout-independent
way to share setup across files in the same directory.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture
def git_cmd() -> Callable[..., subprocess.CompletedProcess[str]]:
    """Factory fixture: ``git_cmd(repo, "add", "-A")`` runs a git command
    against ``repo`` and returns the completed process (raises on failure).
    """
    return _git


@pytest.fixture
def make_repo_with_base(
    git_cmd: Callable[..., subprocess.CompletedProcess[str]],
) -> Callable[[Path], Path]:
    """Factory fixture: call with ``tmp_path`` to build a repo with one
    commit on ``main``, pushed to a bare ``origin`` remote.

    ``_resolve_branch_base_ref`` can resolve ``refs/remotes/origin/HEAD``
    from this layout without any network-dependent ``gh`` lookup (the
    ``no_gh`` fixture below forces ``gh`` off regardless, so tests do not
    depend on that fallback ordering either).
    """

    def _build(tmp_path: Path) -> Path:
        remote_bare = tmp_path / "remote.git"
        remote_bare.mkdir()
        git_cmd(remote_bare, "init", "-q", "--bare", "--initial-branch=main")

        repo = tmp_path / "repo"
        git_cmd(tmp_path, "clone", "-q", str(remote_bare), str(repo))
        git_cmd(repo, "config", "user.name", "Test User")
        git_cmd(repo, "config", "user.email", "test@example.com")
        (repo / "README.md").write_text("seed\n", encoding="utf-8")
        git_cmd(repo, "add", "-A")
        git_cmd(repo, "commit", "-q", "-m", "chore: seed")
        git_cmd(repo, "push", "-q", "origin", "main")
        return repo

    return _build


@pytest.fixture
def no_gh(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force base-ref resolution off the network for the duration of a test:
    ``_resolve_branch_base_ref`` must fall through to
    ``refs/remotes/origin/HEAD``, never attempt ``gh pr view``.
    """
    monkeypatch.setattr("checks_common.shutil.which", lambda _name: None)
    yield
