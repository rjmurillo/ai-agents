"""Tests for set_issue_labels.py."""

import json
from unittest.mock import patch, call

import pytest

from test_helpers import make_completed_process


@pytest.fixture
def _import_module():
    import importlib
    import sys
    mod_name = "set_issue_labels"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


class TestSetIssueLabels:
    def test_apply_existing_labels(self, _import_module):
        mod = _import_module
        with (
            patch("set_issue_labels._run_gh") as mock_run_gh,
            patch("subprocess.run") as mock_run,
        ):
            mock_run_gh.return_value = make_completed_process()
            mock_run.return_value = make_completed_process()

            result = mod.set_issue_labels("o", "r", 1, ["bug", "P1"])

        assert result["Success"] is True
        assert result["Applied"] == ["bug", "P1"]
        assert result["TotalApplied"] == 2

    def test_create_missing_label(self, _import_module):
        mod = _import_module

        call_count = {"check": 0, "create": 0, "apply": 0}

        def mock_run_gh_side(*args, **kwargs):
            if "labels/" in args[1]:
                call_count["check"] += 1
                return make_completed_process(returncode=1)
            return make_completed_process()

        def mock_run_side(cmd, **kwargs):
            if "-X" in cmd and "POST" in cmd:
                call_count["create"] += 1
                return make_completed_process()
            call_count["apply"] += 1
            return make_completed_process()

        with (
            patch("set_issue_labels._run_gh", side_effect=mock_run_gh_side),
            patch("subprocess.run", side_effect=mock_run_side),
        ):
            result = mod.set_issue_labels("o", "r", 1, ["new-label"])

        assert result["Created"] == ["new-label"]
        assert result["Applied"] == ["new-label"]

    def test_priority_label(self, _import_module):
        mod = _import_module
        with (
            patch("set_issue_labels._run_gh") as mock_run_gh,
            patch("subprocess.run") as mock_run,
        ):
            mock_run_gh.return_value = make_completed_process()
            mock_run.return_value = make_completed_process()

            result = mod.set_issue_labels(
                "o", "r", 1, [], priority="P1"
            )

        assert "priority:P1" in result["Applied"]

    def test_empty_labels(self, _import_module):
        mod = _import_module

        result = mod.set_issue_labels("o", "r", 1, [])

        assert result["Success"] is True
        assert result["TotalApplied"] == 0

    def test_skip_missing_when_no_create(self, _import_module):
        mod = _import_module
        with patch("set_issue_labels._run_gh") as mock_run_gh:
            mock_run_gh.return_value = make_completed_process(returncode=1)

            result = mod.set_issue_labels(
                "o", "r", 1, ["nonexistent"],
                create_missing=False,
            )

        assert result["Applied"] == []
        assert result["TotalApplied"] == 0

    def test_create_failure_adds_to_failed(self, _import_module):
        mod = _import_module
        with (
            patch("set_issue_labels._run_gh") as mock_run_gh,
            patch("subprocess.run") as mock_run,
        ):
            mock_run_gh.return_value = make_completed_process(returncode=1)
            mock_run.return_value = make_completed_process(returncode=1, stderr="err")

            result = mod.set_issue_labels("o", "r", 1, ["broken"])

        assert result["Failed"] == ["broken"]
        assert result["Success"] is False

    def test_whitespace_labels_filtered(self, _import_module):
        mod = _import_module
        with (
            patch("set_issue_labels._run_gh") as mock_run_gh,
            patch("subprocess.run") as mock_run,
        ):
            mock_run_gh.return_value = make_completed_process()
            mock_run.return_value = make_completed_process()

            result = mod.set_issue_labels("o", "r", 1, ["good", "  ", ""])

        assert result["Applied"] == ["good"]
