"""Tests for set_issue_assignee.py."""

import json
from unittest.mock import patch

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "set_issue_assignee"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestSetIssueAssignee:
    def test_assign_single_user(self, _import_module, mock_subprocess_run):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process()

        result = mod.set_issue_assignee("o", "r", 1, ["user1"])

        assert result["Success"] is True
        assert result["Applied"] == ["user1"]
        assert result["Failed"] == []
        assert result["TotalApplied"] == 1

    def test_assign_multiple_users(self, _import_module, mock_subprocess_run):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process()

        result = mod.set_issue_assignee("o", "r", 1, ["u1", "u2", "u3"])

        assert result["TotalApplied"] == 3
        assert result["Applied"] == ["u1", "u2", "u3"]

    def test_partial_failure(self, _import_module, mock_subprocess_run):
        mod = _import_module

        def side_effect(*args, **kwargs):
            cmd = args[0]
            assignee = cmd[cmd.index("--add-assignee") + 1]
            if assignee == "bad":
                return make_completed_process(returncode=1, stderr="error")
            return make_completed_process()

        mock_subprocess_run.side_effect = side_effect

        result = mod.set_issue_assignee("o", "r", 1, ["good", "bad"])

        assert result["Success"] is False
        assert "good" in result["Applied"]
        assert "bad" in result["Failed"]

    def test_empty_assignees(self, _import_module, mock_subprocess_run):
        mod = _import_module

        result = mod.set_issue_assignee("o", "r", 1, [])

        assert result["Success"] is True
        assert result["TotalApplied"] == 0
        mock_subprocess_run.assert_not_called()

    def test_all_fail(self, _import_module, mock_subprocess_run):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process(
            returncode=1, stderr="fail"
        )

        result = mod.set_issue_assignee("o", "r", 1, ["x", "y"])

        assert result["Success"] is False
        assert result["Failed"] == ["x", "y"]
        assert result["Applied"] == []
