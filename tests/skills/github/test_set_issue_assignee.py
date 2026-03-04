"""Tests for set_issue_assignee.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from test_helpers import make_completed_process

# Ensure importability
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (str(_lib_dir), str(_scripts_dir / "issue")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from github_core.api import RepoInfo  # noqa: E402


def _mock_repo():
    return RepoInfo(owner="o", repo="r")


@pytest.fixture
def _import_module():
    import importlib
    mod_name = "set_issue_assignee"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestSetIssueAssignee:
    """Tests for set_issue_assignee.main."""

    def test_assign_single_user(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_assignee.assert_gh_authenticated"),
            patch("set_issue_assignee.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process()),
        ):
            rc = mod.main(["--issue", "1", "--assignees", "user1"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["success"] is True
        assert result["applied"] == ["user1"]
        assert result["failed"] == []
        assert result["total_applied"] == 1

    def test_assign_multiple_users(self, _import_module, capsys):
        mod = _import_module
        with (
            patch("set_issue_assignee.assert_gh_authenticated"),
            patch("set_issue_assignee.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process()),
        ):
            rc = mod.main(["--issue", "1", "--assignees", "u1", "u2", "u3"])
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["total_applied"] == 3
        assert result["applied"] == ["u1", "u2", "u3"]

    def test_partial_failure(self, _import_module):
        mod = _import_module
        procs = [
            make_completed_process(),
            make_completed_process(returncode=1, stderr="error"),
        ]
        with (
            patch("set_issue_assignee.assert_gh_authenticated"),
            patch("set_issue_assignee.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", side_effect=procs),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--assignees", "good", "bad"])
        assert exc.value.code == 3

    def test_all_fail(self, _import_module):
        mod = _import_module
        with (
            patch("set_issue_assignee.assert_gh_authenticated"),
            patch("set_issue_assignee.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                returncode=1, stderr="fail"
            )),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "1", "--assignees", "x", "y"])
        assert exc.value.code == 3
