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
    module_name = f"issue_coordination_{name}"
    spec = importlib.util.spec_from_file_location(module_name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_check = _import("check_existing_pr_for_issue")
_claim = _import("claim_issue")


def _proc(rc: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["gh"], rc, stdout=stdout, stderr=stderr)


class TestReferencesIssue:
    def test_fixes_keyword(self):
        assert _check.references_issue("Fixes #2477 in this PR", 2477) is True

    def test_qualified_fixes_keyword_for_same_repo(self):
        assert (
            _check.references_issue(
                "Fixes rjmurillo/ai-agents#2477",
                2477,
                repo_slug="rjmurillo/ai-agents",
            )
            is True
        )

    def test_qualified_fixes_keyword_for_other_repo_not_matched(self):
        assert (
            _check.references_issue(
                "Fixes other/repo#2477",
                2477,
                repo_slug="rjmurillo/ai-agents",
            )
            is False
        )

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
                "user": {"login": "alice"},
            },
            {
                "number": 11,
                "title": "other",
                "body": "unrelated",
                "html_url": "u2",
                "head": {"ref": "b2"},
                "user": {"login": "bob"},
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
                "user": {"login": "alice"},
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
                "user": {"login": "alice"},
            },
            {
                "number": 11,
                "title": "feat",
                "body": "Fixes #2477",
                "html_url": "u2",
                "head": {"ref": "other"},
                "user": {"login": "bob"},
            },
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            out = _check.find_open_prs_for_issue(
                "o",
                "r",
                2477,
                current_branch_name="work",
                current_user_login="alice",
            )
        assert [m["number"] for m in out] == [11]

    def test_skips_own_pr_when_branch_context_missing(self):
        prs = [
            {
                "number": 10,
                "title": "feat",
                "body": "Fixes #2477",
                "html_url": "u",
                "head": {"ref": "work"},
                "user": {"login": "alice"},
            }
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            out = _check.find_open_prs_for_issue(
                "o",
                "r",
                2477,
                current_user_login="alice",
            )
        assert out == []

    def test_same_branch_from_different_author_still_blocks(self):
        prs = [
            {
                "number": 10,
                "title": "feat",
                "body": "Fixes #2477",
                "html_url": "u",
                "head": {"ref": "work"},
                "user": {"login": "bob"},
            }
        ]
        with patch.object(_check.subprocess, "run", return_value=_proc(0, json.dumps([prs]))):
            out = _check.find_open_prs_for_issue(
                "o",
                "r",
                2477,
                current_branch_name="work",
                current_user_login="alice",
            )
        assert [m["number"] for m in out] == [10]

    def test_handles_null_title_and_body(self):
        prs = [
            {
                "number": 10,
                "title": None,
                "body": None,
                "html_url": "u",
                "head": {"ref": "b"},
                "user": {"login": "alice"},
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


class TestClaimMain:
    def test_duplicate_pr_exits_without_invalid_error_type(self):
        prs = [
            {
                "number": 10,
                "title": "feat",
                "body": "Fixes #5",
                "html_url": "u",
                "head": {"ref": "other"},
                "user": {"login": "bob"},
            }
        ]
        calls = [
            _proc(0, "alice\n"),
            _proc(0, json.dumps([prs])),
        ]
        with (
            patch.object(_check, "assert_gh_authenticated", return_value=None),
            patch.object(_check, "resolve_repo_params") as resolve,
            patch.object(_check, "current_branch", return_value="work"),
            patch.object(_check.subprocess, "run", side_effect=calls),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            try:
                _check.main(["--issue", "5", "--output-format", "json"])
                raised = False
            except SystemExit as exc:
                raised = exc.code == 1
        assert raised

    def test_detects_competing_assignment_after_claim(self):
        calls = [
            _proc(0, "alice\n"),
            _proc(0, json.dumps({"assignees": []})),
            _proc(0, ""),
            _proc(0, json.dumps({"assignees": [{"login": "alice"}, {"login": "bob"}]})),
            _proc(0, ""),
        ]
        with (
            patch.object(_claim, "assert_gh_authenticated", return_value=None),
            patch.object(_claim, "resolve_repo_params") as resolve,
            patch.object(_claim.subprocess, "run", side_effect=calls),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            try:
                _claim.main(["--issue", "5", "--output-format", "json"])
                raised = False
            except SystemExit as exc:
                raised = exc.code == 1
        assert raised

    def test_cleanup_failure_after_competing_assignment_exits_external_error(self):
        calls = [
            _proc(0, "alice\n"),
            _proc(0, json.dumps({"assignees": []})),
            _proc(0, ""),
            _proc(0, json.dumps({"assignees": [{"login": "alice"}, {"login": "bob"}]})),
            _proc(1, stderr="remove failed"),
        ]
        with (
            patch.object(_claim, "assert_gh_authenticated", return_value=None),
            patch.object(_claim, "resolve_repo_params") as resolve,
            patch.object(_claim.subprocess, "run", side_effect=calls),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            try:
                _claim.main(["--issue", "5", "--output-format", "json"])
                raised = False
            except SystemExit as exc:
                raised = exc.code == 3
        assert raised

    def test_missing_self_after_claim_exits_external_error(self):
        calls = [
            _proc(0, "alice\n"),
            _proc(0, json.dumps({"assignees": []})),
            _proc(0, ""),
            _proc(0, json.dumps({"assignees": []})),
        ]
        with (
            patch.object(_claim, "assert_gh_authenticated", return_value=None),
            patch.object(_claim, "resolve_repo_params") as resolve,
            patch.object(_claim.subprocess, "run", side_effect=calls),
        ):
            resolve.return_value.owner = "o"
            resolve.return_value.repo = "r"
            try:
                _claim.main(["--issue", "5", "--output-format", "json"])
                raised = False
            except SystemExit as exc:
                raised = exc.code == 3
        assert raised

    def test_failure_raises(self):
        with patch.object(_claim.subprocess, "run", return_value=_proc(1, stderr="no auth")):
            try:
                _claim.current_login()
                raised = False
            except RuntimeError:
                raised = True
        assert raised
