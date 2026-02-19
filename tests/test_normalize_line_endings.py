"""Tests for normalize_line_endings.py line ending normalization script."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.normalize_line_endings import (
    get_line_ending_stats,
    is_git_repository,
    main,
)


class TestIsGitRepository:
    @patch("scripts.normalize_line_endings.run_git")
    def test_returns_true_when_in_git_repo(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        assert is_git_repository() is True

    @patch("scripts.normalize_line_endings.run_git")
    def test_returns_false_when_not_in_git_repo(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=128)
        assert is_git_repository() is False


class TestGetLineEndingStats:
    @patch("scripts.normalize_line_endings.run_git")
    def test_parses_eol_output(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="i/lf w/lf attr/ file1.py\ni/crlf w/crlf attr/ file2.ps1\n",
        )
        stats = get_line_ending_stats("TEST")
        assert stats["index_lf"] == 1
        assert stats["index_crlf"] == 1
        assert stats["working_lf"] == 1
        assert stats["working_crlf"] == 1

    @patch("scripts.normalize_line_endings.run_git")
    def test_returns_zeros_on_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1)
        stats = get_line_ending_stats("TEST")
        assert stats["index_lf"] == 0
        assert stats["index_crlf"] == 0


class TestMain:
    @patch("scripts.normalize_line_endings.is_git_repository", return_value=False)
    def test_exits_1_when_not_git_repo(self, _mock: MagicMock) -> None:
        assert main([]) == 1

    @patch("scripts.normalize_line_endings.save_line_ending_audit")
    @patch(
        "scripts.normalize_line_endings.get_line_ending_stats",
        return_value={"index_lf": 10, "index_crlf": 0, "working_lf": 10, "working_crlf": 0},
    )
    @patch("scripts.normalize_line_endings.is_git_repository", return_value=True)
    def test_exits_0_when_already_normalized(
        self, _git: MagicMock, _stats: MagicMock, _audit: MagicMock
    ) -> None:
        assert main([]) == 0

    @patch("scripts.normalize_line_endings.save_line_ending_audit")
    @patch(
        "scripts.normalize_line_endings.get_line_ending_stats",
        return_value={"index_lf": 5, "index_crlf": 3, "working_lf": 5, "working_crlf": 3},
    )
    @patch("scripts.normalize_line_endings.is_git_repository", return_value=True)
    def test_dry_run_does_not_renormalize(
        self, _git: MagicMock, _stats: MagicMock, _audit: MagicMock
    ) -> None:
        assert main(["--dry-run"]) == 0
