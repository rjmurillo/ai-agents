"""Partial-failure reporting for add_pr_review_thread_reply.py (defect D30).

When the reply posts but a later step fails, the envelope must say the reply
was posted so a caller retry does not post it again.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
    / "add_pr_review_thread_reply.py"
)
if "add_pr_review_thread_reply" in sys.modules:
    _mod = sys.modules["add_pr_review_thread_reply"]
else:
    _spec = importlib.util.spec_from_file_location("add_pr_review_thread_reply", _SCRIPT)
    assert _spec is not None
    assert _spec.loader is not None
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _mod
    _spec.loader.exec_module(_mod)
main = _mod.main

_UNRESOLVED: dict = {
    "id": "PRRT_abc",
    "isResolved": False,
    "pullRequest": {
        "number": 42,
        "state": "OPEN",
        "headRefOid": "aaa111",
        "baseRefName": "main",
        "baseRefOid": "bbb222",
    },
}
_REPLY_DATA: dict = {
    "addPullRequestReviewThreadReply": {
        "comment": {
            "id": "node123",
            "databaseId": 456,
            "url": "https://example.com/c/456",
            "createdAt": "2025-01-01T00:00:00Z",
            "author": {"login": "user1"},
        },
    },
}
_NOOP_GUARD: dict = {"action": "NOOP", "reason": "auto_merge_not_armed"}
_ARGS = ["--thread-id", "PRRT_abc", "--pull-request", "42", "--body", "Fixed.", "--resolve"]


def _run(states, resolve_result=None, guard=None, args=None):
    """Run main() with scripted thread states; return the exit code and mutation calls."""
    calls: list[str] = []

    def fake_graphql(query: str, variables: dict):
        if "addPullRequestReviewThreadReply" in query:
            calls.append("reply")
            return _REPLY_DATA
        if "resolveReviewThread" in query:
            calls.append("resolve")
            if isinstance(resolve_result, Exception):
                raise resolve_result
            return resolve_result
        raise AssertionError(query[:80])

    guard_patch = (
        {"side_effect": guard}
        if isinstance(guard, Exception)
        else {"return_value": guard or _NOOP_GUARD}
    )
    with (
        patch.object(_mod, "assert_gh_authenticated"),
        patch.object(_mod, "query_thread_state", side_effect=states),
        patch.object(_mod, "guard_auto_merge_before_final_thread_resolution", **guard_patch),
        patch.object(_mod, "gh_graphql", side_effect=fake_graphql),
    ):
        try:
            rc = main(args or _ARGS)
        except SystemExit as exc:
            rc = int(exc.code)
    return rc, calls


def _data(capsys) -> dict:
    return json.loads(capsys.readouterr().out)["Data"]


def _assert_posted_not_resolved(data: dict) -> None:
    assert data["reply_posted"] is True
    assert data["thread_resolved"] is False
    assert data["comment_id"] == 456
    assert data["comment_node_id"] == "node123"
    assert data["html_url"] == "https://example.com/c/456"
    assert data["thread_id"] == "PRRT_abc"


class TestReplyPostedReportedOnPartialFailure:
    def test_requery_rate_limit_after_reply_reports_reply_posted(self, capsys):
        """The #6202 case: the post-reply requery hits the rate limit."""
        rc, calls = _run([_UNRESOLVED, RuntimeError("API rate limit exceeded")])

        assert rc == 3
        assert calls == ["reply"]
        out = json.loads(capsys.readouterr().out)
        assert out["Success"] is False
        _assert_posted_not_resolved(out["Data"])
        assert out["Data"]["reason"] == "resolve_state_query_failed"

    def test_resolve_mutation_failure_reports_reply_posted(self, capsys):
        rc, calls = _run([_UNRESOLVED, _UNRESOLVED], resolve_result=RuntimeError("boom"))

        assert rc == 3
        assert calls == ["reply", "resolve"]
        data = _data(capsys)
        _assert_posted_not_resolved(data)
        assert data["reason"] == "resolve_failed"

    def test_unconfirmed_resolve_reports_reply_posted(self, capsys):
        unconfirmed = {"resolveReviewThread": {"thread": {"id": "PRRT_abc", "isResolved": False}}}
        rc, _ = _run([_UNRESOLVED, _UNRESOLVED], resolve_result=unconfirmed)

        assert rc == 1
        data = _data(capsys)
        _assert_posted_not_resolved(data)
        assert data["reason"] == "resolve_not_confirmed"

    def test_guard_failure_emits_envelope_with_reply_posted(self, capsys):
        rc, calls = _run([_UNRESOLVED, _UNRESOLVED], guard=RuntimeError("pagination incomplete"))

        assert rc == 3
        assert calls == ["reply"]
        out = json.loads(capsys.readouterr().out)
        assert out["Success"] is False
        assert "pagination incomplete" in out["Error"]["Message"]
        _assert_posted_not_resolved(out["Data"])
        assert out["Data"]["reason"] == "auto_merge_guard_failed"

    def test_identity_change_after_reply_reports_reply_posted(self, capsys):
        moved = {**_UNRESOLVED, "pullRequest": {**_UNRESOLVED["pullRequest"], "headRefOid": "ccc"}}
        args = [*_ARGS, "--expected-head-sha", "aaa111"]
        rc, calls = _run([_UNRESOLVED, moved], args=args)

        assert rc == 1
        assert calls == ["reply"]
        data = _data(capsys)
        _assert_posted_not_resolved(data)
        assert data["reason"] == "pull_request_identity_changed"


class TestNoMutationReportsReplyNotPosted:
    def test_identity_change_before_reply_reports_not_posted(self, capsys):
        moved = {**_UNRESOLVED, "pullRequest": {**_UNRESOLVED["pullRequest"], "headRefOid": "ccc"}}
        args = [*_ARGS, "--expected-head-sha", "aaa111"]
        rc, calls = _run([moved], args=args)

        assert rc == 1
        assert calls == []
        assert _data(capsys)["reply_posted"] is False

    def test_initial_query_failure_reports_not_posted(self, capsys):
        rc, calls = _run([RuntimeError("rate limited")])

        assert rc == 3
        assert calls == []
        assert _data(capsys)["reply_posted"] is False

    @pytest.mark.parametrize("state", [None, {**_UNRESOLVED, "isResolved": True}])
    def test_skip_reports_not_posted(self, state, capsys):
        rc, calls = _run([state])

        assert rc == 0
        assert calls == []
        assert _data(capsys)["reply_posted"] is False


class TestSuccessReportsBothFields:
    def test_resolve_success(self, capsys):
        resolved = {"resolveReviewThread": {"thread": {"id": "PRRT_abc", "isResolved": True}}}
        rc, calls = _run([_UNRESOLVED, _UNRESOLVED], resolve_result=resolved)

        assert rc == 0
        assert calls == ["reply", "resolve"]
        data = _data(capsys)
        assert data["reply_posted"] is True
        assert data["thread_resolved"] is True

    def test_reply_without_resolve(self, capsys):
        rc, calls = _run([_UNRESOLVED], args=_ARGS[:-1])

        assert rc == 0
        assert calls == ["reply"]
        data = _data(capsys)
        assert data["reply_posted"] is True
        assert data["thread_resolved"] is False
