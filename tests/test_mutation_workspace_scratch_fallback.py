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


def test_allowed_roots_keep_both_locations_after_the_parent_becomes_writable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    repo = _fake_checkout(tmp_path / "repo")
    root = repo.resolve()
    sibling, fallback = mutation_workspace_git._external_scratch_candidates(root)
    monkeypatch.setattr(mutation_workspace_git.os, "access", lambda *_args: True)

    assert scratch_directory(repo) == sibling
    run_worktree = fallback / "run"
    run_worktree.mkdir(parents=True)

    assert mutation_workspace_git._require_scratch_path(repo, run_worktree, "remove") == (
        run_worktree.resolve()
    )


def test_allowed_roots_exclude_a_sibling_inside_another_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    outer = _fake_checkout(tmp_path / "outer")
    repo = _fake_checkout(outer / "inner")
    sibling, fallback = mutation_workspace_git._external_scratch_candidates(repo.resolve())

    roots = mutation_workspace_git.allowed_scratch_roots(repo)

    assert sibling not in roots
    assert fallback in roots


def test_allowed_roots_never_allow_the_root_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    repo = _fake_checkout(tmp_path / "repo")
    _, fallback = mutation_workspace_git._external_scratch_candidates(repo.resolve())

    with pytest.raises(mutation_workspace_git.MutationWorkspaceError):
        mutation_workspace_git._require_scratch_path(repo, fallback, "remove")
