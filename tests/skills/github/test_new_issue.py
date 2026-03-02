"""Tests for new_issue.py."""

import json
import os
from unittest.mock import patch

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "new_issue"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestNewIssue:
    """Tests for the new_issue function."""

    def test_create_basic_issue(self, _import_module, mock_subprocess_run):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process(
            stdout="https://github.com/owner/repo/issues/42\n"
        )

        result = mod.new_issue("owner", "repo", "Test Title")

        assert result["Success"] is True
        assert result["IssueNumber"] == 42
        assert result["Title"] == "Test Title"

    def test_create_with_body_and_labels(
        self, _import_module, mock_subprocess_run,
    ):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process(
            stdout="https://github.com/o/r/issues/7\n"
        )

        result = mod.new_issue(
            "o", "r", "Title", body="Body text", labels="bug,P1"
        )

        assert result["IssueNumber"] == 7
        call_args = mock_subprocess_run.call_args[0][0]
        assert "--body" in call_args
        assert "--label" in call_args

    def test_api_error_exits_3(self, _import_module, mock_subprocess_run):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process(
            stderr="API error", returncode=1,
        )

        with pytest.raises(SystemExit) as exc:
            mod.new_issue("o", "r", "Title")

        assert exc.value.code == 3

    def test_unparseable_result_exits_3(
        self, _import_module, mock_subprocess_run,
    ):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process(
            stdout="no url here"
        )

        with pytest.raises(SystemExit) as exc:
            mod.new_issue("o", "r", "Title")

        assert exc.value.code == 3

    def test_empty_body_not_passed(
        self, _import_module, mock_subprocess_run,
    ):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process(
            stdout="https://github.com/o/r/issues/1\n"
        )

        mod.new_issue("o", "r", "Title", body="")

        call_args = mock_subprocess_run.call_args[0][0]
        assert "--body" not in call_args

    def test_empty_labels_not_passed(
        self, _import_module, mock_subprocess_run,
    ):
        mod = _import_module
        mock_subprocess_run.return_value = make_completed_process(
            stdout="https://github.com/o/r/issues/1\n"
        )

        mod.new_issue("o", "r", "Title", labels="")

        call_args = mock_subprocess_run.call_args[0][0]
        assert "--label" not in call_args
