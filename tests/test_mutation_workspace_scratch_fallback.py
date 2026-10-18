"""scratch_directory falls back to ~/worktrees when the checkout parent is read-only."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.testing import mutation_workspace_git
from scripts.testing.mutation_workspace import scratch_directory


def _fake_checkout(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path


def test_scratch_directory_falls_back_when_the_parent_is_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    repo = _fake_checkout(tmp_path / "repo")
    unwritable = repo.resolve().parent
    real_access = os.access

    def fake_access(path: str | os.PathLike[str], mode: int) -> bool:
        if mode == os.W_OK and Path(path).resolve() == unwritable:
            return False
        return real_access(path, mode)

    monkeypatch.setattr(mutation_workspace_git.os, "access", fake_access)

    scratch = scratch_directory(repo)

    assert scratch.parent == home / "worktrees"
    assert mutation_workspace_git.allowed_scratch_roots(repo)[0] == scratch


def test_scratch_directory_keeps_an_existing_sibling_when_the_parent_is_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fake_checkout(tmp_path / "repo")
    sibling = (
        repo.resolve().parent / f"{repo.name}{mutation_workspace_git.SCRATCH_DIRECTORY_SUFFIX}"
    )
    sibling.mkdir()
    monkeypatch.setattr(mutation_workspace_git.os, "access", lambda *_args: False)

    assert scratch_directory(repo) == sibling
