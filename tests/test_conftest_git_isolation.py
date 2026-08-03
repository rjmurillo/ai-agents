"""Behavioral tests for the tmp_path git isolation fixture (issue #4287).

The fixture must unset GIT pointer variables (GIT_DIR, GIT_WORK_TREE, etc.)
before setting GIT_CEILING_DIRECTORIES, otherwise an inherited GIT_DIR causes
git commands in tmp_path to operate on the real repository rather than the
temp directory.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def test_git_ceiling_directories_is_set(tmp_path: Path) -> None:
    """The fixture sets GIT_CEILING_DIRECTORIES to tmp_path's parent."""
    ceiling = os.environ.get("GIT_CEILING_DIRECTORIES", "")
    assert str(tmp_path.parent) in ceiling


def test_git_dir_is_unset(tmp_path: Path) -> None:
    """GIT_DIR is unset so git discovery in tmp_path cannot escape.

    Issue #4287: GIT_CEILING_DIRECTORIES is inert when GIT_DIR is set because
    GIT_DIR skips discovery entirely.
    """
    assert "GIT_DIR" not in os.environ


def test_git_work_tree_is_unset(tmp_path: Path) -> None:
    """GIT_WORK_TREE is unset."""
    assert "GIT_WORK_TREE" not in os.environ


def test_git_common_dir_is_unset(tmp_path: Path) -> None:
    """GIT_COMMON_DIR is unset."""
    assert "GIT_COMMON_DIR" not in os.environ


def test_git_index_file_is_unset(tmp_path: Path) -> None:
    """GIT_INDEX_FILE is unset."""
    assert "GIT_INDEX_FILE" not in os.environ


def test_git_init_creates_repo_inside_tmp_path(tmp_path: Path) -> None:
    """git init inside tmp_path produces a repo there, not elsewhere.

    This is the functional test: if GIT_DIR were inherited and pointed at the
    real repo, git init would re-init that repo and create nothing in tmp_path.
    """
    result = subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path / "repo")],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "LC_ALL": "C"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "repo" / ".git").exists()


def test_git_config_writes_inside_tmp_path(tmp_path: Path) -> None:
    """git config writes into the tmp_path repo, not the real checkout.

    The real-world damage described in issue #4287: a working checkout was
    left with core.bare=true and a stale attributesFile path after a test
    set GIT_DIR and ran git config without the isolation guard.
    """
    repo = tmp_path / "isolated"
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)],
        capture_output=True,
        env={**os.environ, "LC_ALL": "C"},
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
        env={**os.environ, "LC_ALL": "C"},
    )
    result = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "user.email"],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "LC_ALL": "C"},
        check=False,
    )
    assert result.stdout.strip() == "test@example.com"


def test_hostile_git_dir_is_neutralised(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The isolation fixture clears GIT_DIR before the test body runs.

    Negative control: verify os.environ at test start (after the autouse
    fixture) does not contain GIT_DIR, even in an environment where it
    could be present from a parent process.
    """
    # After the autouse fixture, GIT_DIR must not be in os.environ.
    assert "GIT_DIR" not in os.environ, (
        "GIT_DIR still in os.environ after isolation fixture ran; "
        "the fixture is not clearing pointer variables (issue #4287)"
    )
    # Setting it now via monkeypatch simulates a test that introduces GIT_DIR.
    # The fixture already ran, so this is a test-body-only mutation - it does
    # not invalidate the fixture guarantee for this test, but confirms monkeypatch
    # itself works and the fixture cleared it before we got here.
    real_git_dir = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        capture_output=True,
        encoding="utf-8",
        check=False,
    ).stdout.strip()
    if real_git_dir and Path(real_git_dir).exists():
        monkeypatch.setenv("GIT_DIR", real_git_dir)
        assert os.environ.get("GIT_DIR") == real_git_dir  # monkeypatch works
