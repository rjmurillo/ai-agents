"""Tests for locating a scratch root outside every enclosing repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.external_scratch import (
    make_external_dir,
    outside_every_repository,
    remove_external_dir,
)


def test_returns_parent_of_a_single_enclosing_repository(tmp_path: Path) -> None:
    """One repository above the start yields the directory just above it."""
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    inner = repo / "src" / "pkg"
    inner.mkdir(parents=True)

    assert outside_every_repository(inner) == tmp_path


def test_skips_past_the_outer_repository_for_a_nested_worktree(tmp_path: Path) -> None:
    """A worktree nested under its main repository resolves above both.

    This is the shape that made the fixture resolve back inside the checkout:
    the immediate parent of the worktree is still inside the main repository.
    """
    main = tmp_path / "ai-agents"
    (main / ".git").mkdir(parents=True)
    worktree = main / ".wt" / "probe"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: ../../.git/worktrees/probe\n")

    assert outside_every_repository(worktree) == tmp_path
    assert main not in outside_every_repository(worktree).parents
    assert outside_every_repository(worktree) != main.parent.joinpath("ai-agents")


def test_recognises_a_git_file_as_a_repository_marker(tmp_path: Path) -> None:
    """A worktree marks its root with a ``.git`` file, not a directory."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n")

    assert outside_every_repository(repo) == tmp_path


def test_returns_the_start_when_no_repository_encloses_it(tmp_path: Path) -> None:
    """With no repository on the chain there is nothing to climb past."""
    bare = tmp_path / "plain" / "deep"
    bare.mkdir(parents=True)

    assert outside_every_repository(bare) == bare


def test_returns_the_parent_when_the_start_is_itself_a_repository(
    tmp_path: Path,
) -> None:
    """The start counts as its own enclosing repository."""
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)

    assert outside_every_repository(repo) == tmp_path


def test_result_has_no_repository_at_or_above_it(tmp_path: Path) -> None:
    """The contract the callers depend on, asserted directly.

    Three repositories stacked on one chain stand in for any depth, so the
    guarantee is checked rather than the arithmetic that produces it.
    """
    outer = tmp_path / "outer"
    middle = outer / "middle"
    inner = middle / "inner"
    inner.mkdir(parents=True)
    for level in (outer, middle, inner):
        (level / ".git").mkdir()
    start = inner / "tests"
    start.mkdir()

    result = outside_every_repository(start)

    assert result == tmp_path
    assert not any((c / ".git").exists() for c in (result, *result.parents))


def test_remove_drops_the_root_once_it_is_empty(tmp_path: Path) -> None:
    """The last worker out removes the shared root, so no empty dir is left."""
    root = tmp_path / ".pytest-external-checkout"
    path = make_external_dir(root, "a")
    (path / "file.txt").write_text("x")

    remove_external_dir(path)

    assert not path.exists()
    assert not root.exists()


def test_remove_keeps_a_root_a_sibling_still_uses(tmp_path: Path) -> None:
    """A root holding another worker's directory survives the first removal."""
    root = tmp_path / ".pytest-external-checkout"
    mine = make_external_dir(root, "mine")
    theirs = make_external_dir(root, "theirs")

    remove_external_dir(mine)

    assert not mine.exists()
    assert theirs.is_dir()


def test_remove_tolerates_a_root_already_gone(tmp_path: Path) -> None:
    """Removing a directory whose root vanished raises nothing."""
    remove_external_dir(tmp_path / "gone-root" / "child")

    assert not (tmp_path / "gone-root").exists()


def test_make_retries_when_a_sibling_removes_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A root deleted mid-create is recreated on the next attempt."""
    root = tmp_path / ".pytest-external-checkout"
    real_mkdir = Path.mkdir
    calls = {"n": 0}

    def flaky_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise FileNotFoundError(str(self))
        real_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "mkdir", flaky_mkdir)

    path = make_external_dir(root, "child")

    assert path.is_dir()
    assert calls["n"] >= 2


def test_make_gives_up_after_three_missing_root_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A root that never stays put surfaces the error instead of looping."""

    def always_missing(self: Path, *args: object, **kwargs: object) -> None:
        raise FileNotFoundError(str(self))

    monkeypatch.setattr(Path, "mkdir", always_missing)

    with pytest.raises(FileNotFoundError):
        make_external_dir(tmp_path / "root", "child")
