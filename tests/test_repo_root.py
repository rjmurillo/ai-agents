"""Tests for scripts.github_core.repo -- worktree-aware repo root resolution."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts.github_core.repo import get_repo_root


def _completed(stdout: str = "", rc: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr="")


class TestGetRepoRoot:
    """get_repo_root returns the parent of git-common-dir."""

    @patch("scripts.github_core.repo.subprocess.run")
    def test_absolute_git_common_dir(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout="/home/user/repo/.git\n")
        result = get_repo_root()
        assert result == Path("/home/user/repo")

    @patch("scripts.github_core.repo.subprocess.run")
    def test_relative_git_common_dir(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout=".git\n")
        result = get_repo_root()
        assert result is not None
        assert result.is_absolute()

    @patch("scripts.github_core.repo.subprocess.run")
    def test_worktree_resolves_to_main_repo(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout="/home/user/repo/.git\n")
        result = get_repo_root()
        assert result == Path("/home/user/repo")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "rev-parse", "--git-common-dir"]

    @patch("scripts.github_core.repo.subprocess.run")
    def test_start_dir_passed_as_git_c_flag(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout="/home/user/repo/.git\n")
        get_repo_root(start_dir="/tmp/worktree")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "-C", "/tmp/worktree", "rev-parse", "--git-common-dir"]

    @patch("scripts.github_core.repo.subprocess.run")
    def test_returns_none_on_nonzero_exit(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(rc=1)
        assert get_repo_root() is None

    @patch("scripts.github_core.repo.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run: patch) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        assert get_repo_root() is None

    @patch("scripts.github_core.repo.subprocess.run")
    def test_returns_none_when_git_not_found(self, mock_run: patch) -> None:
        mock_run.side_effect = FileNotFoundError
        assert get_repo_root() is None

    @patch("scripts.github_core.repo.subprocess.run")
    def test_custom_timeout_passed(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout="/repo/.git\n")
        get_repo_root(timeout=5)
        assert mock_run.call_args[1]["timeout"] == 5

    @patch("scripts.github_core.repo.subprocess.run")
    def test_relative_path_resolved_against_start_dir(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout=".git\n")
        result = get_repo_root(start_dir="/tmp/my-worktree")
        assert result == Path("/tmp/my-worktree")
