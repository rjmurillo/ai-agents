"""Tests for the issue-coordination skill scripts (issue #2477).

Covers check_existing_pr_for_issue.py (duplicate-PR detection) and claim_issue.py
(self-assign with existing-claimant guard). gh I/O is mocked at the subprocess
boundary; the keyword-matching domain logic is exercised directly.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "issue"
)


def _import(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_check = _import("check_existing_pr_for_issue")
_claim = _import("claim_issue")


def _proc(rc: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["gh"], rc, stdout=stdout, stderr=stderr)


class TestReferencesIssue:
    def test_fixes_keyword(self):
        assert _check.references_issue("Fixes #2477 in this PR", 2477) is True

    def test_closes_resolves_refs(self):
        assert _check.references_issue("Closes #5", 5) is True
        assert _check.references_issue("Resolves #5", 5) is True
        assert _check.references_issue("Refs #5", 5) is True

    def test_case_insensitive(self):
        assert _check.references_issue("FIXES #5", 5) is True

    def test_bare_number_not_matched(self):
        assert _check.references_issue("see issue #5 maybe", 5) is False

    def test_different_issue_not_matched(self):
        assert _check.references_issue("Fixes #50", 5) is False

    def test_empty(self):
        assert _check.references_issue("", 5) is False


class TestFindOpenPrsForIssue:
    def test_match_in_body(self):
        prs = [
            {
                "number": 10,
                "title": "feat",
                "body": "Closes #2477",
                "html_url": "u",
                "head": {"ref": "b"},
            },
            {
                "number": 11,
                "title": "other",
                "body": "unrelated",
                "html_url": "u2",
                "head": {"ref": "b2"},
            },
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            out = _check.find_open_prs_for_issue("o", "r", 2477)
        assert [m["number"] for m in out] == [10]

    def test_no_match(self):
        prs = [
            {
                "number": 11,
                "title": "x",
                "body": "y",
                "html_url": "u",
                "head": {"ref": "b"},
            }
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            assert _check.find_open_prs_for_issue("o", "r", 2477) == []

    def test_skips_current_branch_pr(self):
        prs = [
            {
                "number": 10,
                "title": "feat",
                "body": "Fixes #2477",
                "html_url": "u",
                "head": {"ref": "work"},
            },
            {
                "number": 11,
                "title": "feat",
                "body": "Fixes #2477",
                "html_url": "u2",
                "head": {"ref": "other"},
            },
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            out = _check.find_open_prs_for_issue("o", "r", 2477, current_branch_name="work")
        assert [m["number"] for m in out] == [11]

    def test_handles_null_title_and_body(self):
        prs = [
            {
                "number": 10,
                "title": None,
                "body": None,
                "html_url": "u",
                "head": {"ref": "b"},
            }
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            assert _check.find_open_prs_for_issue("o", "r", 2477) == []

    def test_api_failure_raises(self):
        with patch.object(_check.subprocess, "run", return_value=_proc(1)):
            try:
                _check.find_open_prs_for_issue("o", "r", 1)
                raised = False
            except RuntimeError:
                raised = True
        assert raised

    def test_timeout_raises_runtime_error(self):
        timeout = subprocess.TimeoutExpired(["gh"], 30)
        with patch.object(_check.subprocess, "run", side_effect=timeout):
            try:
                _check.find_open_prs_for_issue("o", "r", 1)
                raised = False
            except RuntimeError:
                raised = True
        assert raised


class TestClaimIssueAssignees:
    def test_parses_assignees(self):
        payload = json.dumps({"assignees": [{"login": "alice"}, {"login": "bob"}]})
        with patch.object(_claim.subprocess, "run", return_value=_proc(0, payload)):
            assert _claim.issue_assignees("o", "r", 5) == ["alice", "bob"]

    def test_empty_assignees(self):
        payload = json.dumps({"assignees": []})
        with patch.object(_claim.subprocess, "run", return_value=_proc(0, payload)):
            assert _claim.issue_assignees("o", "r", 5) == []

    def test_null_assignees_treated_as_empty(self):
        payload = json.dumps({"assignees": None})
        with patch.object(_claim.subprocess, "run", return_value=_proc(0, payload)):
            assert _claim.issue_assignees("o", "r", 5) == []

    def test_view_failure_raises(self):
        with patch.object(_claim.subprocess, "run", return_value=_proc(1)):
            try:
                _claim.issue_assignees("o", "r", 5)
                raised = False
            except RuntimeError:
                raised = True
        assert raised


class TestCurrentLogin:
    def test_returns_login(self):
        with patch.object(_claim.subprocess, "run", return_value=_proc(0, "alice\n")):
            assert _claim.current_login() == "alice"

    def test_empty_login_raises(self):
        with patch.object(_claim.subprocess, "run", return_value=_proc(0, "\n")):
            try:
                _claim.current_login()
                raised = False
            except RuntimeError:
                raised = True
        assert raised

    def test_failure_raises(self):
        with patch.object(_claim.subprocess, "run", return_value=_proc(1, stderr="no auth")):
            try:
                _claim.current_login()
                raised = False
            except RuntimeError:
                raised = True
        assert raised
