"""Tests for invoke_batch_pr_review.py worktree management."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.invoke_batch_pr_review import (
    SUBPROCESS_TIMEOUT_SECONDS,
    WorktreeStatus,
    get_pr_branch,
    get_worktree_status,
    main,
    push_worktree_changes,
    print_status_table,
    run_gh,
    run_git,
)


class TestGetPrBranch:
    @patch("scripts.invoke_batch_pr_review.subprocess.run")
    def test_run_wrappers_pass_timeout(self, mock_run: MagicMock) -> None:
        run_git("status")
        run_gh("pr", "list")

        assert mock_run.call_count == 2
        assert all(
            call.kwargs["timeout"] == SUBPROCESS_TIMEOUT_SECONDS
            for call in mock_run.call_args_list
        )

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


def _prepare_pushable_worktree(root: Path) -> Path:
    """Create a pushable worktree with bot identity and an upstream remote."""
    origin = root / "origin.git"
    worktree = root / "worktree-pr-1"

    _git(["init", "--bare", "--initial-branch=main", str(origin)], root)
    _git(["clone", str(origin), str(worktree)], root)
    _git(["config", "user.name", "rjmurillo-bot"], worktree)
    _git(["config", "user.email", "rjmurillo-bot@users.noreply.github.com"], worktree)
    (worktree / "README.md").write_text("base\n")
    _git(["add", "README.md"], worktree)
    _git(["commit", "-m", "base"], worktree)
    _git(["push", "origin", "main"], worktree)
    return worktree


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

    @patch("scripts.invoke_batch_pr_review.get_worktree_status")
    def test_returns_3_on_subprocess_timeout(self, mock_status: MagicMock) -> None:
        mock_status.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=60)
        result = main([
            "--pr-numbers", "1",
            "--operation", "status",
            "--worktree-root", "/tmp",
        ])
        assert result == 3


class TestPushWorktreeChanges:
    def test_repins_leaked_identity_before_cleanup_commit(self, tmp_path: Path) -> None:
        """A leaked Test <test@test.com> identity must not reach the cleanup commit."""
        worktree = _prepare_pushable_worktree(tmp_path)

        _git(["config", "user.name", "Test"], worktree)
        _git(["config", "user.email", "test@test.com"], worktree)
        (worktree / "README.md").write_text("base\nchange\n")

        assert push_worktree_changes(1, tmp_path) is True

        author = _git(["log", "-1", "--format=%an <%ae>"], worktree).stdout.strip()
        assert author == "rjmurillo-bot <rjmurillo-bot@users.noreply.github.com>"
        local_email = _git(["config", "--local", "user.email"], worktree).stdout.strip()
        assert local_email == "rjmurillo-bot@users.noreply.github.com"

    def test_clean_and_pushed_worktree_skips_identity_reset(self, tmp_path: Path) -> None:
        """A clean, already-pushed worktree must not need a reset or commit."""
        _prepare_pushable_worktree(tmp_path)

        from scripts import invoke_batch_pr_review

        with patch.object(invoke_batch_pr_review, "reset_worktree_identity") as mock_reset:
            result = push_worktree_changes(1, tmp_path)

        assert result is True
        mock_reset.assert_not_called()

    def test_operator_identity_is_forwarded_to_reset(self, tmp_path: Path) -> None:
        """The human operator mode must still forward through the cleanup path."""
        from scripts import invoke_batch_pr_review

        status = WorktreeStatus(
            pr=1,
            path=tmp_path / "worktree-pr-1",
            exists=True,
            clean=False,
            branch="main",
            commit=None,
            unpushed=True,
        )
        with (
            patch.object(invoke_batch_pr_review, "get_worktree_status", return_value=status),
            patch.object(invoke_batch_pr_review, "reset_worktree_identity") as mock_reset,
            patch.object(invoke_batch_pr_review, "run_git") as mock_run_git,
        ):
            mock_run_git.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = push_worktree_changes(1, tmp_path, operator="rjmurillo")

        assert result is True
        mock_reset.assert_called_once_with(status.path, operator="rjmurillo")
