"""Tests for scripts.github_core.repo -- worktree-aware repo root resolution."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts.github_core.repo import get_repo_root


def _completed(stdout: str = "", rc: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr="")


class TestGetRepoRoot:
    """get_repo_root returns the current worktree root."""

    @patch("scripts.github_core.repo.subprocess.run")
    def test_absolute_show_toplevel(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout="/home/user/repo\n")
        result = get_repo_root()
        assert result == Path("/home/user/repo")

    @patch("scripts.github_core.repo.subprocess.run")
    def test_relative_show_toplevel(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout=".\n")
        result = get_repo_root()
        assert result is not None
        assert result.is_absolute()

    @patch("scripts.github_core.repo.subprocess.run")
    def test_worktree_resolves_to_checkout_root(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout="/home/user/worktree\n")
        result = get_repo_root()
        assert result == Path("/home/user/worktree")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "rev-parse", "--show-toplevel"]

    @patch("scripts.github_core.repo.subprocess.run")
    def test_start_dir_passed_as_git_c_flag(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout="/home/user/worktree\n")
        get_repo_root(start_dir="/home/user/worktree")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "-C", "/home/user/worktree", "rev-parse", "--show-toplevel"]

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
        mock_run.return_value = _completed(stdout="/repo\n")
        get_repo_root(timeout=5)
        assert mock_run.call_args[1]["timeout"] == 5

    @patch("scripts.github_core.repo.subprocess.run")
    def test_relative_path_resolved_against_start_dir(self, mock_run: patch) -> None:
        mock_run.return_value = _completed(stdout=".\n")
        result = get_repo_root(start_dir="/home/user/my-worktree")
        assert result == Path("/home/user/my-worktree")
