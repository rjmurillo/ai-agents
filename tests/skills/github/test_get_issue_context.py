"""Tests for get_issue_context.py."""

import json
import subprocess
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
    return RepoInfo(owner="owner", repo="repo")


@pytest.fixture
def _import_module():
    """Import the module under test."""
    import importlib
    mod_name = "get_issue_context"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestGetIssueContext:
    """Tests for get_issue_context.main."""

    def test_success(self, _import_module, capsys):
        mod = _import_module
        issue_data = {
            "number": 42,
            "title": "Test Issue",
            "body": "Some description",
            "state": "OPEN",
            "author": {"login": "testuser"},
            "labels": [{"name": "bug"}, {"name": "P1"}],
            "milestone": {"title": "v1.0.0"},
            "assignees": [{"login": "dev1"}],
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-02T00:00:00Z",
        }
        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch("get_issue_context.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps(issue_data)
            )),
        ):
            rc = mod.main(["--issue", "42"])

        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Success"] is True
        assert output["Data"]["number"] == 42
        assert output["Data"]["title"] == "Test Issue"
        assert output["Data"]["body"] == "Some description"
        assert output["Data"]["state"] == "OPEN"
        assert output["Data"]["author"] == "testuser"
        assert output["Data"]["labels"] == ["bug", "P1"]
        assert output["Data"]["milestone"] == "v1.0.0"
        assert output["Data"]["assignees"] == ["dev1"]
        assert output["Data"]["owner"] == "owner"
        assert output["Data"]["repo"] == "repo"

    def test_no_milestone(self, _import_module, capsys):
        mod = _import_module
        issue_data = {
            "number": 10,
            "title": "No Milestone",
            "body": "",
            "state": "OPEN",
            "author": {"login": "user"},
            "labels": [],
            "milestone": None,
            "assignees": [],
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch("get_issue_context.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps(issue_data)
            )),
        ):
            rc = mod.main(["--issue", "10"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["milestone"] is None

    def test_not_found_exits_2(self, _import_module):
        mod = _import_module
        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch("get_issue_context.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stderr="not found", returncode=1,
            )),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "999"])
        assert exc.value.code == 2

    def test_api_error_exits_2(self, _import_module):
        mod = _import_module
        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch("get_issue_context.resolve_repo_params", return_value=_mock_repo()),
            patch("subprocess.run", return_value=make_completed_process(
                stderr="some error", returncode=1,
            )),
        ):
            with pytest.raises(SystemExit) as exc:
                mod.main(["--issue", "999"])
        assert exc.value.code == 2

    def test_empty_labels_and_assignees(self, _import_module, capsys):
        mod = _import_module
        issue_data = {
            "number": 5,
            "title": "Minimal",
            "body": "",
            "state": "CLOSED",
            "author": {"login": "u"},
            "labels": [],
            "milestone": None,
            "assignees": [],
            "createdAt": "",
            "updatedAt": "",
        }
        with (
            patch("get_issue_context.assert_gh_authenticated"),
            patch("get_issue_context.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run", return_value=make_completed_process(
                stdout=json.dumps(issue_data)
            )),
        ):
            rc = mod.main(["--issue", "5"])
        assert rc == 0
        output = json.loads(capsys.readouterr().out)
        assert output["Data"]["labels"] == []
        assert output["Data"]["assignees"] == []
        assert output["Data"]["body"] == ""
