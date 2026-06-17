"""Tests for scripts/validation/check_dual_priority_labels.py.

Covers the pure decision function ``find_priority_labels`` and the CLI
``main`` for the dual-priority-label gate (Issue #2623, part 1).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_project_root = Path(__file__).resolve().parents[1]
_script_path = _project_root / "scripts" / "validation" / "check_dual_priority_labels.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_dual_priority_labels", _script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mod = _load_module()


class TestFindPriorityLabels:
    """Pure decision logic over a label name list."""

    def test_no_priority_labels_returns_empty(self):
        assert mod.find_priority_labels(["bug", "automation"]) == []

    def test_single_priority_label_returns_one(self):
        assert mod.find_priority_labels(["bug", "priority:P2"]) == ["priority:P2"]

    def test_two_priority_labels_returns_both_sorted(self):
        # Order is deterministic (sorted) so the message is stable.
        assert mod.find_priority_labels(["priority:P2", "bug", "priority:P1"]) == [
            "priority:P1",
            "priority:P2",
        ]

    def test_case_insensitive_prefix_match(self):
        # GitHub label names are case-sensitive, but the prefix check must not
        # miss a "Priority:P1" stamped by a different tool.
        assert mod.find_priority_labels(["Priority:P1", "priority:P2"]) == [
            "Priority:P1",
            "priority:P2",
        ]

    def test_non_priority_prefixed_label_ignored(self):
        # "priority-board" is not a priority:* label.
        assert mod.find_priority_labels(["priority-board", "bug"]) == []

    def test_empty_list(self):
        assert mod.find_priority_labels([]) == []


class TestMainWithExplicitLabels:
    """CLI path that takes labels directly (no network)."""

    def test_clean_single_priority_exits_zero(self, capsys):
        rc = mod.main(["--labels", "bug", "priority:P1"])
        assert rc == 0

    def test_dual_priority_exits_one(self, capsys):
        rc = mod.main(["--labels", "priority:P1", "priority:P2"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "priority:P1" in out
        assert "priority:P2" in out

    def test_no_labels_exits_zero(self):
        rc = mod.main(["--labels"])
        assert rc == 0


class TestEvaluatePluralization:
    """Output message pluralizes 'priority label(s)' correctly."""

    def test_zero_priority_labels_uses_plural(self, capsys):
        exit_code, status = mod.evaluate([], "issue #1")
        assert exit_code == mod.EXIT_OK
        assert "0 priority labels" in status

    def test_one_priority_label_uses_singular(self, capsys):
        exit_code, status = mod.evaluate(["priority:P1"], "issue #1")
        assert exit_code == mod.EXIT_OK
        assert "1 priority label" in status
        assert "1 priority labels" not in status

    def test_two_priority_labels_uses_plural_in_fail(self, capsys):
        exit_code, status = mod.evaluate(["priority:P1", "priority:P2"], "issue #1")
        assert exit_code == mod.EXIT_DUAL
        assert "2 priority labels" in status


class TestFetchLabelsGhFailureModes:
    """gh-backed path: _fetch_labels fails closed on every gh error mode."""

    def test_gh_not_found_returns_external_error(self):
        with patch(
            "check_dual_priority_labels._run_gh_view",
            side_effect=FileNotFoundError("gh not found"),
        ):
            err_code, names, status = mod._fetch_labels("issue", 1)
        assert err_code == mod.EXIT_EXTERNAL
        assert names is None
        assert "not found" in status.lower()

    def test_gh_timeout_returns_external_error(self):
        with patch(
            "check_dual_priority_labels._run_gh_view",
            side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=15),
        ):
            err_code, names, status = mod._fetch_labels("issue", 1)
        assert err_code == mod.EXIT_EXTERNAL
        assert names is None
        assert "timed out" in status.lower()

    def test_gh_nonzero_exit_returns_external_error(self):
        proc = subprocess.CompletedProcess(
            args=["gh"], returncode=1, stdout="", stderr="auth error"
        )
        with patch("check_dual_priority_labels._run_gh_view", return_value=proc):
            err_code, names, status = mod._fetch_labels("issue", 1)
        assert err_code == mod.EXIT_EXTERNAL
        assert names is None
        assert "exit 1" in status

    def test_gh_bad_json_returns_external_error(self):
        proc = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="not-json", stderr="")
        with patch("check_dual_priority_labels._run_gh_view", return_value=proc):
            err_code, names, status = mod._fetch_labels("issue", 1)
        assert err_code == mod.EXIT_EXTERNAL
        assert names is None
        assert "unparseable" in status.lower()

    def test_gh_success_returns_label_names(self):
        payload = '{"labels": [{"name": "priority:P1"}, {"name": "bug"}]}'
        proc = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout=payload, stderr="")
        with patch("check_dual_priority_labels._run_gh_view", return_value=proc):
            err_code, names, status = mod._fetch_labels("issue", 1)
        assert err_code == mod.EXIT_OK
        assert names == ["priority:P1", "bug"]
        assert status == ""

    def test_main_with_issue_flag_propagates_gh_failure(self, capsys):
        with patch(
            "check_dual_priority_labels._run_gh_view",
            side_effect=FileNotFoundError("gh not found"),
        ):
            rc = mod.main(["--issue", "99"])
        assert rc == mod.EXIT_EXTERNAL
        out = capsys.readouterr().out
        assert "FAIL" in out

    def test_main_no_source_returns_config_error(self, capsys):
        rc = mod.main([])
        assert rc == mod.EXIT_CONFIG
        out = capsys.readouterr().out
        assert "FAIL" in out

    def test_main_rejects_issue_and_pr_together(self, capsys):
        rc = mod.main(["--issue", "99", "--pr", "100"])
        assert rc == mod.EXIT_CONFIG
        out = capsys.readouterr().out
        assert "only one" in out
