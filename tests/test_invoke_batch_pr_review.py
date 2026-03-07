"""Tests for invoke_batch_pr_review.py worktree management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.invoke_batch_pr_review import (
    WorktreeStatus,
    get_pr_branch,
    get_worktree_status,
    main,
    print_status_table,
)


class TestGetPrBranch:
    @patch("scripts.invoke_batch_pr_review.run_gh")
    def test_returns_branch_name(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = MagicMock(
            returncode=0, stdout='{"headRefName": "feat/my-branch"}'
        )
        assert get_pr_branch(123) == "feat/my-branch"

    @patch("scripts.invoke_batch_pr_review.run_gh")
    def test_returns_none_on_failure(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = MagicMock(returncode=1, stdout="")
        assert get_pr_branch(999) is None

    @patch("scripts.invoke_batch_pr_review.run_gh")
    def test_returns_none_on_bad_json(self, mock_gh: MagicMock) -> None:
        mock_gh.return_value = MagicMock(returncode=0, stdout="not-json")
        assert get_pr_branch(123) is None


class TestWorktreeStatus:
    def test_dataclass_defaults(self) -> None:
        status = WorktreeStatus(pr=1, path=Path("/tmp/wt"), exists=False)
        assert status.clean is None
        assert status.branch is None
        assert status.commit is None
        assert status.unpushed is None


class TestGetWorktreeStatus:
    @patch("scripts.invoke_batch_pr_review.run_git")
    def test_nonexistent_path_returns_exists_false(self, mock_git: MagicMock) -> None:
        status = get_worktree_status(42, Path("/nonexistent"))
        assert status.exists is False
        assert status.pr == 42


class TestPrintStatusTable:
    def test_prints_without_error(self) -> None:
        statuses = [
            WorktreeStatus(pr=1, path=Path("/wt"), exists=True, clean=True, branch="main"),
        ]
        print_status_table(statuses)


class TestMain:
    @patch("scripts.invoke_batch_pr_review.run_git")
    def test_status_operation(self, mock_git: MagicMock) -> None:
        mock_git.return_value = MagicMock(
            returncode=0, stdout="/fake/repo\n"
        )
        result = main([
            "--pr-numbers", "1", "2",
            "--operation", "status",
            "--worktree-root", "/tmp",
        ])
        assert result == 0
