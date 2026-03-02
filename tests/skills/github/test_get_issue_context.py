"""Tests for get_issue_context.py."""

import json
import subprocess
from unittest.mock import patch

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    """Import the module under test."""
    import importlib
    import sys
    mod_name = "get_issue_context"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestGetIssueContext:
    """Tests for the get_issue_context function."""

    def test_success(self, _import_module, mock_subprocess_run):
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
        mock_subprocess_run.return_value = make_completed_process(
            stdout=json.dumps(issue_data)
        )

        result = mod.get_issue_context("owner", "repo", 42)

        assert result["Success"] is True
        assert result["Number"] == 42
        assert result["Title"] == "Test Issue"
        assert result["Body"] == "Some description"
        assert result["State"] == "OPEN"
        assert result["Author"] == "testuser"
        assert result["Labels"] == ["bug", "P1"]
        assert result["Milestone"] == "v1.0.0"
        assert result["Assignees"] == ["dev1"]
        assert result["Owner"] == "owner"
        assert result["Repo"] == "repo"

    def test_no_milestone(self, _import_module, mock_subprocess_run):
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
        mock_subprocess_run.return_value = make_completed_process(
            stdout=json.dumps(issue_data)
        )

        result = mod.get_issue_context("owner", "repo", 10)

        assert result["Milestone"] is None

    def test_not_found_exits_2(self, _import_module, mock_subprocess_run):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process(
            stderr="not found", returncode=1,
        )

        with pytest.raises(SystemExit) as exc:
            mod.get_issue_context("owner", "repo", 999)

        assert exc.value.code == 2

    def test_api_error_exits_2(self, _import_module, mock_subprocess_run):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process(
            stderr="some error", returncode=1,
        )

        with pytest.raises(SystemExit) as exc:
            mod.get_issue_context("owner", "repo", 999)

        assert exc.value.code == 2

    def test_empty_labels_and_assignees(
        self, _import_module, mock_subprocess_run,
    ):
        mod = _import_module
        issue_data = {
            "number": 5,
            "title": "Minimal",
            "state": "CLOSED",
            "author": {"login": "u"},
            "labels": [],
            "assignees": [],
            "createdAt": "",
            "updatedAt": "",
        }
        mock_subprocess_run.return_value = make_completed_process(
            stdout=json.dumps(issue_data)
        )

        result = mod.get_issue_context("o", "r", 5)

        assert result["Labels"] == []
        assert result["Assignees"] == []
        assert result["Body"] == ""
