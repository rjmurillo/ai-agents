"""Tests for triage_gateway.py and the wiring between the batch executor
and the scope/predicate checks.

Extracted from test_triage_batch_apply.py to keep both files under the
500-line size limit.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess

from scripts.triage_batch_apply import (
    ACTION_CLOSE,
    OUTCOME_APPLIED,
    OUTCOME_SKIPPED,
    IssueState,
    ManifestAction,
    apply_action,
)
from scripts.triage_gateway import CliGitHubGateway
from scripts.validation.verify_issue_close import IssueComment

# -- Helpers -----------------------------------------------------------------

class FakeGateway:
    """Minimal in-memory gateway for wiring tests."""

    def __init__(
        self,
        states: dict[int, IssueState] | None = None,
        merged_prs: frozenset[int] = frozenset(),
        close_ok: bool = True,
    ) -> None:
        self._states = states or {}
        self._merged_prs = merged_prs
        self._close_ok = close_ok
        self._comments: dict[int, list[IssueComment] | None] = {}
        self._merge_times: dict[int, dt.datetime] = {}
        self.closed: list[int] = []

    def get_issue_state(self, issue: int) -> IssueState | None:
        return self._states.get(issue)

    def close_issue(self, issue: int) -> bool:
        if self._close_ok:
            self.closed.append(issue)
        return self._close_ok

    def add_labels(self, issue: int, labels) -> bool:
        return True

    def commit_exists(self, sha: str) -> bool:
        return True

    def pr_is_merged(self, pr: int) -> bool:
        return pr in self._merged_prs

    def get_issue_comments(self, issue: int) -> list[IssueComment] | None:
        return self._comments.get(issue, [])

    def get_pr_merge_time(self, pr: int) -> dt.datetime | None:
        return self._merge_times.get(pr)


def _open(issue: int, labels: tuple[str, ...] = ()) -> IssueState:
    return IssueState(number=issue, state="OPEN", labels=frozenset(labels))


# -- TestCliGitHubGateway ----------------------------------------------------

class TestCliGitHubGateway:
    class StubGateway(CliGitHubGateway):
        def __init__(self, result: subprocess.CompletedProcess[str]) -> None:
            super().__init__("owner", "repo")
            self._result = result
            self.commands: list[list[str]] = []

        def _run(self, command: list[str]) -> subprocess.CompletedProcess[str] | None:
            self.commands.append(command)
            return self._result

    def test_null_payload_fields_fall_back_to_safe_values(self):
        result = subprocess.CompletedProcess(
            ["gh"], 0,
            stdout=json.dumps({"number": None, "state": None, "labels": None}),
            stderr="",
        )
        gateway = self.StubGateway(result)
        state = gateway.get_issue_state(42)
        assert state == IssueState(number=42, state="", labels=frozenset())

    def test_non_dict_labels_are_ignored(self):
        result = subprocess.CompletedProcess(
            ["gh"], 0,
            stdout=json.dumps({
                "number": 7,
                "state": "OPEN",
                "labels": [{"name": "bug"}, None, "bad", {"name": None}],
            }),
            stderr="",
        )
        gateway = self.StubGateway(result)
        state = gateway.get_issue_state(7)
        assert state == IssueState(number=7, state="OPEN", labels=frozenset({"bug", ""}))

    def test_pr_is_merged_rejects_null_state(self):
        result = subprocess.CompletedProcess(
            ["gh"], 0,
            stdout=json.dumps({"state": None}),
            stderr="",
        )
        gateway = self.StubGateway(result)
        assert gateway.pr_is_merged(5) is False

    def test_pr_is_merged_rejects_non_object_payload(self):
        result = subprocess.CompletedProcess(
            ["gh"], 0, stdout=json.dumps(["MERGED"]), stderr="",
        )
        gateway = self.StubGateway(result)
        assert gateway.pr_is_merged(5) is False

    def test_commit_exists_uses_remote_api(self):
        result = subprocess.CompletedProcess(["gh"], 0, stdout="", stderr="")
        gateway = self.StubGateway(result)
        assert gateway.commit_exists("abc1234") is True
        assert gateway.commands == [["gh", "api", "repos/owner/repo/commits/abc1234"]]

    def test_commit_exists_rejects_missing_remote_commit(self):
        result = subprocess.CompletedProcess(["gh"], 1, stdout="", stderr="")
        gateway = self.StubGateway(result)
        assert gateway.commit_exists("deadbeef") is False

    def test_run_uses_utf8_encoding_and_c_locale(self, monkeypatch):
        captured: dict[str, object] = {}

        def fake_run(command: list[str], **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        gateway = CliGitHubGateway("owner", "repo")
        result = gateway._run(["git", "status"])
        assert result is not None
        kwargs = captured["kwargs"]
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert kwargs["env"]["LC_ALL"] == "C"


# -- Predicate unification (issue 4624) --------------------------------------

class TestPredicateUnification:
    """Pinning tests: the batch path (CliGitHubGateway) must use the
    ancestry-checking verify_pr_merged, not a separate copy that only
    checks state. Regression guard for issue 4624."""

    class _TrackingGateway(CliGitHubGateway):
        def __init__(self, responses: list[subprocess.CompletedProcess[str]]) -> None:
            super().__init__("owner", "repo")
            self._responses = list(responses)
            self.commands: list[list[str]] = []

        def _run(self, command: list[str]) -> subprocess.CompletedProcess[str] | None:
            self.commands.append(command)
            return self._responses.pop(0) if self._responses else None

    def test_open_pr_rejected_through_batch_path(self):
        """An OPEN PR must not be treated as merged (issue 4624)."""
        pr_response = subprocess.CompletedProcess(
            ["gh"], 0,
            stdout=json.dumps({"state": "OPEN", "mergeCommit": None}),
            stderr="",
        )
        gw = self._TrackingGateway([pr_response])
        assert gw.pr_is_merged(99) is False

    def test_merged_pr_without_ancestry_rejected(self):
        """A MERGED PR whose merge commit is not on main must fail."""
        pr_response = subprocess.CompletedProcess(
            ["gh"], 0,
            stdout=json.dumps({
                "state": "MERGED",
                "mergeCommit": {"oid": "abc123"},
            }),
            stderr="",
        )
        ancestry_fail = subprocess.CompletedProcess(
            ["git"], 1, stdout="", stderr="",
        )
        gw = self._TrackingGateway([pr_response, ancestry_fail])
        assert gw.pr_is_merged(42) is False


# -- Unresolved scope wiring (issue 4625) ------------------------------------

class TestUnresolvedScopeWiring:
    """Wiring tests: verify check_unresolved_scope is consulted in _apply_close.

    Per convention from commit 43e2114e (#4281), a wiring test asserts that the
    production closure path actually calls the scope check.
    """

    def test_post_fix_human_comment_blocks_close(self):
        """End-to-end: human comment after fix prevents close."""
        fix_time = dt.datetime(2026, 7, 1, 10, 0, 0, tzinfo=dt.timezone.utc)
        comment = IssueComment(
            author="reviewer",
            author_type="User",
            created_at=dt.datetime(2026, 7, 2, 8, 0, 0, tzinfo=dt.timezone.utc),
            url="https://github.com/o/r/issues/5#issuecomment-1",
            body="the ARM64 path still panics",
        )
        gw = FakeGateway(states={5: _open(5)}, merged_prs=frozenset({100}))
        gw._comments = {5: [comment]}
        gw._merge_times = {100: fix_time}
        action = ManifestAction(
            issue=5, category=ACTION_CLOSE,
            rationale="Fixed via PR #100", reproduction_verified=True,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "unaddressed post-fix" in outcome.detail
        assert gw.closed == []

    def test_bot_comment_after_fix_does_not_block(self):
        fix_time = dt.datetime(2026, 7, 1, 10, 0, 0, tzinfo=dt.timezone.utc)
        comment = IssueComment(
            author="github-actions[bot]",
            author_type="Bot",
            created_at=dt.datetime(2026, 7, 2, 8, 0, 0, tzinfo=dt.timezone.utc),
            url="https://github.com/o/r/issues/5#issuecomment-2",
            body="auto triage complete",
        )
        gw = FakeGateway(states={5: _open(5)}, merged_prs=frozenset({100}))
        gw._comments = {5: [comment]}
        gw._merge_times = {100: fix_time}
        action = ManifestAction(
            issue=5, category=ACTION_CLOSE,
            rationale="Fixed via PR #100", reproduction_verified=True,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.closed == [5]

    def test_comment_fetch_failure_blocks_close(self):
        fix_time = dt.datetime(2026, 7, 1, 10, 0, 0, tzinfo=dt.timezone.utc)
        gw = FakeGateway(states={5: _open(5)}, merged_prs=frozenset({100}))
        gw._comments = {5: None}
        gw._merge_times = {100: fix_time}
        action = ManifestAction(
            issue=5, category=ACTION_CLOSE,
            rationale="Fixed via PR #100", reproduction_verified=True,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "comment fetch failed" in outcome.detail
        assert gw.closed == []

    def test_no_pr_cited_skips_scope_check(self):
        gw = FakeGateway(states={5: _open(5)})
        action = ManifestAction(
            issue=5, category=ACTION_CLOSE,
            rationale="stale, superseded by new design",
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.closed == [5]

    def test_scope_check_is_wired_into_close_path(self):
        """Wiring guard: removing the scope call breaks this test."""
        fix_time = dt.datetime(2026, 7, 1, 10, 0, 0, tzinfo=dt.timezone.utc)
        comment = IssueComment(
            author="human",
            author_type="User",
            created_at=dt.datetime(2026, 7, 2, 0, 0, 0, tzinfo=dt.timezone.utc),
            url="https://github.com/o/r/issues/7#issuecomment-42",
            body="fwiw the ARM64 path panics on the same input",
        )
        gw = FakeGateway(states={7: _open(7)}, merged_prs=frozenset({200}))
        gw._comments = {7: [comment]}
        gw._merge_times = {200: fix_time}
        action = ManifestAction(
            issue=7, category=ACTION_CLOSE,
            rationale="Resolved via PR #200", reproduction_verified=True,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert gw.closed == []
