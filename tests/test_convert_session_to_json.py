"""Tests for convert_session_to_json.py session migration wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.convert_session_to_json import get_repo_root, main


class TestGetRepoRoot:
    @patch("scripts.convert_session_to_json.subprocess.run")
    def test_returns_path_on_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="/repo\n")
        assert get_repo_root() == Path("/repo")

    @patch("scripts.convert_session_to_json.subprocess.run")
    def test_returns_none_on_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        assert get_repo_root() is None


class TestMain:
    @patch("scripts.convert_session_to_json.get_repo_root", return_value=None)
    def test_exits_1_when_not_git_repo(self, _mock: MagicMock) -> None:
        assert main(["some/path"]) == 1

    @patch("scripts.convert_session_to_json.get_repo_root")
    def test_exits_1_when_skill_missing(self, mock_root: MagicMock, tmp_path: Path) -> None:
        mock_root.return_value = tmp_path
        assert main(["some/path"]) == 1

    @patch("scripts.convert_session_to_json.subprocess.run")
    @patch("scripts.convert_session_to_json.get_repo_root")
    def test_delegates_to_skill(
        self, mock_root: MagicMock, mock_run: MagicMock, tmp_path: Path,
    ) -> None:
        mock_root.return_value = tmp_path
        skills_base = tmp_path / ".claude" / "skills" / "session-migration"
        skill = skills_base / "scripts" / "Convert-SessionToJson.ps1"
        skill.parent.mkdir(parents=True)
        skill.write_text("# skill", encoding="utf-8")
        mock_run.return_value = MagicMock(returncode=0)

        result = main(["some/path"])
        assert result == 0
        mock_run.assert_called_once()
