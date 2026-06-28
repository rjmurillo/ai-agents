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
        assert data["Success"] is True
        assert data["Data"]["issue_number"] == 42
        assert data["Data"]["title"] == "Test Title"

    def test_data_number_is_positive_int_and_url_set_on_success(self, capsys):
        # Regression for issue #2767: callers read Data.number, which was null.
        with patch("subprocess.run", return_value=_make_proc(
            stdout="https://github.com/owner/repo/issues/2767\n"
        )):
            result = main(["--title", "Test Title", "--output-format", "json"])
        assert result == 0
        data = json.loads(capsys.readouterr().out)
        number = data["Data"]["number"]
        assert isinstance(number, int) and number > 0
        assert number == 2767
        assert data["Data"]["url"] == "https://github.com/owner/repo/issues/2767"

    def test_create_with_body_and_labels(self, capsys):
        with patch("subprocess.run", return_value=_make_proc(
            stdout="https://github.com/o/r/issues/7\n"
        )) as mock_run:
            result = main(["--title", "Title", "--body", "Body text", "--labels", "bug,P1"])
        assert result == 0
        all_calls = [call[0][0] for call in mock_run.call_args_list]
        create_call = next(c for c in all_calls if "create" in c)
        assert "--body" in create_call
        edit_call = next(c for c in all_calls if "edit" in c)
        assert "--add-label" in edit_call

    def test_api_error_exits_3(self, capsys):
        with patch("subprocess.run", return_value=_make_proc(
            returncode=1, stderr="API error"
        )):
            result = main(["--title", "Title", "--output-format", "json"])
        assert result == 3
        data = json.loads(capsys.readouterr().out)
        assert data["Success"] is False
        assert data["Error"]["Type"] == "ApiError"

    def test_unparseable_result_exits_3(self, capsys):
        with patch("subprocess.run", return_value=_make_proc(
            stdout="no url here"
        )):
            result = main(["--title", "Title", "--output-format", "json"])
        assert result == 3
        data = json.loads(capsys.readouterr().out)
        assert data["Success"] is False
        assert data["Error"]["Type"] == "ApiError"

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
