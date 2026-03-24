"""Tests for new_validated_pr.py PR creation wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.github_core.repo import get_repo_root
from scripts.new_validated_pr import main


class TestGetRepoRoot:
    @patch("scripts.github_core.repo.subprocess.run")
    def test_returns_path_on_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="/fake/repo/.git\n")
        result = get_repo_root()
        assert result == Path("/fake/repo")

    @patch("scripts.github_core.repo.subprocess.run")
    def test_returns_none_on_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        assert get_repo_root() is None


class TestMain:
    @patch("scripts.new_validated_pr.get_repo_root", return_value=None)
    def test_exits_2_when_not_git_repo(self, _mock: MagicMock) -> None:
        assert main(["--title", "test"]) == 2

    @patch("scripts.new_validated_pr.shutil.which", return_value=None)
    @patch("scripts.new_validated_pr.get_repo_root", return_value=Path("/repo"))
    def test_exits_2_when_gh_not_found(self, _repo: MagicMock, _which: MagicMock) -> None:
        assert main(["--title", "test"]) == 2

    @patch("scripts.new_validated_pr.shutil.which", return_value="/usr/bin/gh")
    @patch("scripts.new_validated_pr.get_repo_root", return_value=Path("/repo"))
    def test_exits_2_when_no_title(self, _repo: MagicMock, _which: MagicMock) -> None:
        assert main([]) == 2

    @patch("scripts.new_validated_pr.subprocess.run")
    @patch("scripts.new_validated_pr.shutil.which", return_value="/usr/bin/gh")
    @patch("scripts.new_validated_pr.get_repo_root")
    def test_exits_2_when_skill_not_found(
        self, mock_root: MagicMock, _which: MagicMock, _run: MagicMock, tmp_path: Path
    ) -> None:
        mock_root.return_value = tmp_path
        assert main(["--title", "test: title"]) == 2
