"""Tests for new_issue.py."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/github/scripts/issue/new_issue.py")
main = mod.main


def _make_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestNewIssue:
    """Tests for new_issue via main entry point."""

    @pytest.fixture(autouse=True)
    def _mock_auth(self):
        with patch.object(mod, "assert_gh_authenticated"), \
             patch.object(mod, "resolve_repo_params") as mock_resolve:
            info = MagicMock()
            info.owner = "owner"
            info.repo = "repo"
            mock_resolve.return_value = info
            yield

    def test_create_basic_issue(self, capsys):
        with patch("subprocess.run", return_value=_make_proc(
            stdout="https://github.com/owner/repo/issues/42\n"
        )):
            result = main(["--title", "Test Title"])
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["success"] is True
        assert data["issue_number"] == 42
        assert data["title"] == "Test Title"

    def test_create_with_body_and_labels(self, capsys):
        with patch("subprocess.run", return_value=_make_proc(
            stdout="https://github.com/o/r/issues/7\n"
        )) as mock_run:
            result = main(["--title", "Title", "--body", "Body text", "--labels", "bug,P1"])
        assert result == 0
        call_args = mock_run.call_args[0][0]
        assert "--body" in call_args
        assert "--label" in call_args

    def test_api_error_exits_3(self):
        with patch("subprocess.run", return_value=_make_proc(
            returncode=1, stderr="API error"
        )):
            with pytest.raises(SystemExit) as exc:
                main(["--title", "Title"])
        assert exc.value.code == 3

    def test_unparseable_result_exits_3(self):
        with patch("subprocess.run", return_value=_make_proc(
            stdout="no url here"
        )):
            with pytest.raises(SystemExit) as exc:
                main(["--title", "Title"])
        assert exc.value.code == 3

    def test_empty_body_not_passed(self):
        with patch("subprocess.run", return_value=_make_proc(
            stdout="https://github.com/o/r/issues/1\n"
        )) as mock_run:
            main(["--title", "Title", "--body", ""])
        call_args = mock_run.call_args[0][0]
        assert "--body" not in call_args

    def test_empty_labels_not_passed(self):
        with patch("subprocess.run", return_value=_make_proc(
            stdout="https://github.com/o/r/issues/1\n"
        )) as mock_run:
            main(["--title", "Title", "--labels", ""])
        call_args = mock_run.call_args[0][0]
        assert "--label" not in call_args
