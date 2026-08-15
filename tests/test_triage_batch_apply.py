"""Tests for scripts.triage_batch_apply.

Covers the Phase 3 batch executor (issue #2261): the human-approval gate (no
mutation without approved manifest plus --apply), idempotent skipping when an
issue is already in the target state, partial-failure handling that does not
abort the rest, and the CLI entry point. GitHub I/O is mocked at the gateway
boundary with a fake; domain logic is never mocked.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from scripts.triage_batch_apply import (
    ACTION_BATCH,
    ACTION_CLOSE,
    ACTION_PRIORITIZE,
    ACTION_RELABEL,
    OUTCOME_APPLIED,
    OUTCOME_FAILED,
    OUTCOME_PLANNED,
    OUTCOME_SKIPPED,
    IssueState,
    ManifestAction,
    apply_action,
    is_mutation_authorized,
    main,
    parse_actions,
    run_batch,
)
from scripts.validation.verify_issue_close import IssueComment


class FakeGateway:
    """In-memory GitHub gateway. Records every mutation and serves fixed state."""

    def __init__(
        self,
        states: dict[int, IssueState] | None = None,
        *,
        close_ok: bool = True,
        label_ok: bool = True,
        known_commits: frozenset[str] | None = None,
        merged_prs: frozenset[int] | None = None,
    ) -> None:
        self._states = states or {}
        self._close_ok = close_ok
        self._label_ok = label_ok
        self._known_commits = known_commits or frozenset()
        self._merged_prs = merged_prs or frozenset()
        self.closed: list[int] = []
        self.labeled: list[tuple[int, tuple[str, ...]]] = []

    def get_issue_state(self, issue: int) -> IssueState | None:
        return self._states.get(issue)

    def close_issue(self, issue: int) -> bool:
        self.closed.append(issue)
        return self._close_ok

    def add_labels(self, issue: int, labels: Sequence[str]) -> bool:
        self.labeled.append((issue, tuple(labels)))
        return self._label_ok

    def commit_exists(self, sha: str) -> bool:
        return sha.lower() in self._known_commits

    def pr_is_merged(self, pr: int) -> bool:
        return pr in self._merged_prs

    def get_issue_comments(self, issue: int) -> list | None:
        comments_map = getattr(self, "_comments", {})
        if issue in comments_map:
            return comments_map[issue]
        # Default: no comments (successful empty fetch, safe to proceed)
        return []

    def get_commit_time(self, sha: str):
        """Mirror get_pr_merge_time: a known commit has an early timestamp.

        Tests that need the unavailable case pass commit_times={} explicitly.
        """
        import datetime as dt
        commit_times = getattr(self, "_commit_times", None)
        if commit_times is not None:
            return commit_times.get(sha)
        if sha in self._known_commits:
            return dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
        return None

    def get_pr_merge_time(self, pr: int):
        import datetime as dt
        merge_times = getattr(self, "_merge_times", {})
        if pr in merge_times:
            return merge_times[pr]
        # Default: if the PR is in merged_prs, return a very early timestamp
        # so existing tests pass without needing explicit merge times.
        if pr in self._merged_prs:
            return dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
        return None


def _open(issue: int, labels: tuple[str, ...] = ()) -> IssueState:
    return IssueState(number=issue, state="OPEN", labels=frozenset(labels))


def _closed(issue: int, labels: tuple[str, ...] = ()) -> IssueState:
    return IssueState(number=issue, state="CLOSED", labels=frozenset(labels))


def _manifest(actions: list[dict], *, approved: bool) -> dict:
    return {"version": 1, "approved": approved, "issues_triaged": len(actions), "actions": actions}


def _write_manifest(path: Path, actions: list[dict], *, approved: bool) -> Path:
    path.write_text(json.dumps(_manifest(actions, approved=approved)), encoding="utf-8")
    return path


class TestApprovalGate:
    def test_authorized_only_when_approved_and_apply(self):
        assert is_mutation_authorized({"approved": True}, True) is True

    def test_not_authorized_without_apply(self):
        assert is_mutation_authorized({"approved": True}, False) is False

    def test_not_authorized_without_approval(self):
        assert is_mutation_authorized({"approved": False}, True) is False

    def test_not_authorized_when_approved_missing(self):
        assert is_mutation_authorized({}, True) is False


class TestApplyActionDryRun:
    def test_close_plans_without_mutating(self):
        gw = FakeGateway({5: _open(5)})
        action = ManifestAction(issue=5, category=ACTION_CLOSE)
        outcome = apply_action(action, gw, mutate=False)
        assert outcome.outcome == OUTCOME_PLANNED
        assert gw.closed == []

    def test_relabel_plans_without_mutating(self):
        gw = FakeGateway({6: _open(6)})
        action = ManifestAction(issue=6, category=ACTION_RELABEL, labels=("agent-qa",))
        outcome = apply_action(action, gw, mutate=False)
        assert outcome.outcome == OUTCOME_PLANNED
        assert gw.labeled == []


class TestApplyActionMutate:
    def test_close_open_issue_applies(self):
        gw = FakeGateway({5: _open(5)})
        outcome = apply_action(ManifestAction(issue=5, category=ACTION_CLOSE), gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.closed == [5]

    def test_relabel_adds_missing_label(self):
        gw = FakeGateway({6: _open(6, labels=("bug",))})
        action = ManifestAction(issue=6, category=ACTION_RELABEL, labels=("agent-qa",))
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.labeled == [(6, ("agent-qa",))]

    def test_prioritize_adds_priority_label(self):
        gw = FakeGateway({7: _open(7)})
        action = ManifestAction(issue=7, category=ACTION_PRIORITIZE, priority="P1")
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.labeled == [(7, ("priority:P1",))]


class TestIdempotency:
    def test_close_already_closed_is_noop(self):
        gw = FakeGateway({5: _closed(5)})
        outcome = apply_action(ManifestAction(issue=5, category=ACTION_CLOSE), gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "already closed" in outcome.detail
        assert gw.closed == []

    def test_relabel_when_label_present_is_noop(self):
        gw = FakeGateway({6: _open(6, labels=("agent-qa",))})
        action = ManifestAction(issue=6, category=ACTION_RELABEL, labels=("agent-qa",))
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert gw.labeled == []

    def test_relabel_adds_only_missing_labels(self):
        gw = FakeGateway({6: _open(6, labels=("agent-qa",))})
        action = ManifestAction(
            issue=6, category=ACTION_RELABEL, labels=("agent-qa", "agent-implementer"),
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.labeled == [(6, ("agent-implementer",))]

    def test_rerun_after_apply_is_noop(self):
        # First run closes the issue; a re-run against the now-closed state mutates nothing.
        gw = FakeGateway({5: _open(5)})
        action = ManifestAction(issue=5, category=ACTION_CLOSE)
        apply_action(action, gw, mutate=True)
        gw_second = FakeGateway({5: _closed(5)})
        outcome = apply_action(action, gw_second, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert gw_second.closed == []


class TestAdvisoryAndUnknown:
    def test_batch_is_advisory_skip(self):
        gw = FakeGateway({1: _open(1)})
        outcome = apply_action(ManifestAction(issue=1, category=ACTION_BATCH), gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "advisory" in outcome.detail

    def test_missing_state_plans_in_dry_run(self):
        gw = FakeGateway({})
        outcome = apply_action(ManifestAction(issue=99, category=ACTION_CLOSE), gw, mutate=False)
        assert outcome.outcome == OUTCOME_PLANNED
        assert "state unavailable" in outcome.detail

    def test_missing_state_fails_in_apply_mode(self):
        gw = FakeGateway({})
        outcome = apply_action(ManifestAction(issue=99, category=ACTION_CLOSE), gw, mutate=True)
        assert outcome.outcome == OUTCOME_FAILED
        assert "state unavailable" in outcome.detail

    def test_missing_state_plans_label_action_in_dry_run(self):
        gw = FakeGateway({})
        action = ManifestAction(issue=99, category=ACTION_RELABEL, labels=("agent-qa",))
        outcome = apply_action(action, gw, mutate=False)
        assert outcome.outcome == OUTCOME_PLANNED
        assert "would add agent-qa" in outcome.detail


class TestPartialFailure:
    def test_one_failure_does_not_abort_the_rest(self):
        gw = FakeGateway({1: _open(1), 2: _open(2)}, close_ok=False)
        actions = [
            ManifestAction(issue=1, category=ACTION_CLOSE),
            ManifestAction(issue=2, category=ACTION_RELABEL, labels=("agent-qa",)),
        ]
        outcomes = run_batch(actions, gw, mutate=True)
        assert outcomes[0].outcome == OUTCOME_FAILED
        assert outcomes[1].outcome == OUTCOME_APPLIED
        assert gw.labeled == [(2, ("agent-qa",))]


class TestCloseVerificationGate:
    """Issue #2481: gate auto-close on epic label and on cited commit/PR truth."""

    def test_epic_label_blocks_close_case_insensitively(self):
        gw = FakeGateway({9: _open(9, labels=("Epic", "enhancement"))})
        action = ManifestAction(issue=9, category=ACTION_CLOSE, rationale="superseded")
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "epic" in outcome.detail
        assert gw.closed == []

    def test_close_with_no_citation_proceeds(self):
        gw = FakeGateway({5: _open(5)})
        action = ManifestAction(
            issue=5,
            category=ACTION_CLOSE,
            rationale="stale, no longer relevant",
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.closed == [5]

    def test_cited_existing_commit_proceeds(self):
        gw = FakeGateway({5: _open(5)}, known_commits=frozenset({"abc1234"}))
        action = ManifestAction(
            issue=5,
            category=ACTION_CLOSE,
            rationale="resolved by commit abc1234",
            reproduction_verified=True,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.closed == [5]

    def test_cited_missing_commit_aborts_close(self):
        gw = FakeGateway({5: _open(5)}, known_commits=frozenset())
        action = ManifestAction(
            issue=5,
            category=ACTION_CLOSE,
            rationale="resolved by commit 61c56cbe",
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "unverified" in outcome.detail
        assert "61c56cbe" in outcome.detail
        assert gw.closed == []

    def test_cited_merged_pr_proceeds(self):
        gw = FakeGateway({5: _open(5)}, merged_prs=frozenset({1024}))
        action = ManifestAction(
            issue=5, category=ACTION_CLOSE, rationale="closed via PR #1024",
            reproduction_verified=True,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.closed == [5]

    def test_cited_unmerged_pr_aborts_close(self):
        gw = FakeGateway({5: _open(5)}, merged_prs=frozenset())
        action = ManifestAction(issue=5, category=ACTION_CLOSE, rationale="closed via PR #1024")
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "PR #1024" in outcome.detail
        assert gw.closed == []

    def test_gate_applies_in_dry_run(self):
        gw = FakeGateway({5: _open(5)}, known_commits=frozenset())
        action = ManifestAction(
            issue=5,
            category=ACTION_CLOSE,
            rationale="resolved by commit deadbeef",
        )
        outcome = apply_action(action, gw, mutate=False)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "unverified" in outcome.detail


class TestReproductionGate:
    """Issue #4624: a merged-on-main PR still requires a green reproduction."""

    def test_cited_pr_without_reproduction_blocks_close(self):
        gw = FakeGateway({5: _open(5)}, merged_prs=frozenset({1024}))
        action = ManifestAction(
            issue=5, category=ACTION_CLOSE, rationale="closed via PR #1024",
            reproduction_verified=False,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "reproduction not verified" in outcome.detail
        assert gw.closed == []

    def test_cited_commit_without_reproduction_blocks_close(self):
        gw = FakeGateway({5: _open(5)}, known_commits=frozenset({"abc1234"}))
        action = ManifestAction(
            issue=5, category=ACTION_CLOSE,
            rationale="resolved by commit abc1234",
            reproduction_verified=False,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "reproduction not verified" in outcome.detail
        assert gw.closed == []

    def test_cited_pr_with_reproduction_verified_proceeds(self):
        gw = FakeGateway({5: _open(5)}, merged_prs=frozenset({1024}))
        action = ManifestAction(
            issue=5, category=ACTION_CLOSE, rationale="closed via PR #1024",
            reproduction_verified=True,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.closed == [5]

    def test_no_citation_does_not_require_reproduction(self):
        gw = FakeGateway({5: _open(5)})
        action = ManifestAction(
            issue=5, category=ACTION_CLOSE,
            rationale="stale, superseded by new design",
            reproduction_verified=False,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_APPLIED
        assert gw.closed == [5]

    def test_reproduction_gate_applies_in_dry_run(self):
        gw = FakeGateway({5: _open(5)}, merged_prs=frozenset({99}))
        action = ManifestAction(
            issue=5, category=ACTION_CLOSE, rationale="fixed via PR #99",
            reproduction_verified=False,
        )
        outcome = apply_action(action, gw, mutate=False)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "reproduction not verified" in outcome.detail

    def test_from_raw_parses_reproduction_verified_true(self):
        raw = {"issue": 1, "category": "close", "reproduction_verified": True}
        action = ManifestAction.from_raw(raw)
        assert action is not None
        assert action.reproduction_verified is True

    def test_from_raw_defaults_reproduction_verified_false(self):
        raw = {"issue": 1, "category": "close"}
        action = ManifestAction.from_raw(raw)
        assert action is not None
        assert action.reproduction_verified is False

    def test_from_raw_rejects_non_bool_reproduction_verified(self):
        raw = {"issue": 1, "category": "close", "reproduction_verified": "yes"}
        action = ManifestAction.from_raw(raw)
        assert action is not None
        assert action.reproduction_verified is False


class TestParseActions:
    def test_drops_invalid_entries(self):
        manifest = {
            "actions": [
                {"issue": 1, "category": "close"},
                {"category": "close"},          # missing issue
                {"issue": "x", "category": "close"},  # non-int issue
                {"issue": 2, "category": ""},    # empty category
                "not-a-dict",
            ],
        }
        actions = parse_actions(manifest)
        assert [a.issue for a in actions] == [1]

    def test_drops_non_string_labels(self):
        manifest = {
            "actions": [
                {
                    "issue": 1,
                    "category": ACTION_RELABEL,
                    "labels": ["agent-qa", None, 7, " "],
                },
            ],
        }
        actions = parse_actions(manifest)
        assert actions == [
            ManifestAction(issue=1, category=ACTION_RELABEL, labels=("agent-qa",)),
        ]

    def test_drops_fractional_issue_numbers(self):
        manifest = {"actions": [{"issue": 1.5, "category": ACTION_CLOSE}]}
        assert parse_actions(manifest) == []


class TestMain:
    def test_dry_run_does_not_mutate(self, tmp_path: Path, capsys):
        manifest_path = _write_manifest(
            tmp_path / "m.json",
            [{"issue": 5, "category": ACTION_CLOSE}],
            approved=True,
        )
        gw = FakeGateway({5: _open(5)})
        rc = main(["--manifest", str(manifest_path)], gateway=gw)
        assert rc == 0
        assert gw.closed == []
        assert "DRY-RUN" in capsys.readouterr().out

    def test_apply_without_approval_is_config_error(self, tmp_path: Path, capsys):
        manifest_path = _write_manifest(
            tmp_path / "m.json",
            [{"issue": 5, "category": ACTION_CLOSE}],
            approved=False,
        )
        gw = FakeGateway({5: _open(5)})
        rc = main(["--manifest", str(manifest_path), "--apply"], gateway=gw)
        assert rc == 2
        assert gw.closed == []
        assert "not approved" in capsys.readouterr().err

    def test_approved_apply_mutates(self, tmp_path: Path):
        manifest_path = _write_manifest(
            tmp_path / "m.json",
            [{"issue": 5, "category": ACTION_CLOSE}],
            approved=True,
        )
        gw = FakeGateway({5: _open(5)})
        rc = main(["--manifest", str(manifest_path), "--apply"], gateway=gw)
        assert rc == 0
        assert gw.closed == [5]

    def test_approved_manifest_json_apply_mutates(self):
        manifest = json.dumps(_manifest(
            [{"issue": 5, "category": ACTION_CLOSE}],
            approved=True,
        ))
        gw = FakeGateway({5: _open(5)})
        rc = main(["--manifest-json", manifest, "--apply"], gateway=gw)
        assert rc == 0
        assert gw.closed == [5]

    def test_approved_manifest_env_apply_mutates(self, monkeypatch):
        manifest = json.dumps(_manifest(
            [{"issue": 5, "category": ACTION_CLOSE}],
            approved=True,
        ))
        monkeypatch.setenv("APPROVED_MANIFEST_JSON", manifest)
        gw = FakeGateway({5: _open(5)})
        rc = main(["--manifest-env", "APPROVED_MANIFEST_JSON", "--apply"], gateway=gw)
        assert rc == 0
        assert gw.closed == [5]

    def test_invalid_manifest_json_is_config_error(self, capsys):
        rc = main(["--manifest-json", "{not json"])
        assert rc == 2
        assert "not valid JSON" in capsys.readouterr().err

    def test_missing_manifest_is_config_error(self, tmp_path: Path, capsys):
        rc = main(["--manifest", str(tmp_path / "absent.json")])
        assert rc == 2
        assert "cannot read manifest" in capsys.readouterr().err

    def test_malformed_manifest_is_config_error(self, tmp_path: Path, capsys):
        path = tmp_path / "m.json"
        path.write_text("{not json", encoding="utf-8")
        rc = main(["--manifest", str(path)])
        assert rc == 2
        assert "not valid JSON" in capsys.readouterr().err

    def test_manifest_without_actions_array_is_config_error(self, tmp_path: Path, capsys):
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"approved": True}), encoding="utf-8")
        rc = main(["--manifest", str(path)])
        assert rc == 2
        assert "'actions' array" in capsys.readouterr().err

    def test_failure_returns_external_error(self, tmp_path: Path, capsys):
        manifest_path = _write_manifest(
            tmp_path / "m.json",
            [{"issue": 5, "category": ACTION_CLOSE}],
            approved=True,
        )
        gw = FakeGateway({5: _open(5)}, close_ok=False)
        rc = main(["--manifest", str(manifest_path), "--apply"], gateway=gw)
        assert rc == 3
        assert "failed against the GitHub API" in capsys.readouterr().err

    def test_apply_authorized_without_owner_repo_is_config_error(self, tmp_path: Path, capsys):
        manifest_path = _write_manifest(
            tmp_path / "m.json",
            [{"issue": 5, "category": ACTION_CLOSE}],
            approved=True,
        )
        rc = main(["--manifest", str(manifest_path), "--apply"])
        assert rc == 2
        assert "owner" in capsys.readouterr().err




class TestCommitOnlyClosureScopeGate:
    """A rationale citing only a commit must still face the scope gate.

    The gate resolved a fix timestamp from cited pull requests alone. With no
    pull request cited, no timestamp existed, the gate was skipped, and the
    issue closed without ever checking for unresolved scope. That is the hole
    #4625 describes, reached by a different route. Refs #4625.
    """

    def test_comment_after_a_cited_commit_blocks_the_close(self):
        import datetime as dt

        gw = FakeGateway({5: _open(5)}, known_commits=frozenset({"abc1234"}))
        gw._commit_times = {"abc1234": dt.datetime(2026, 1, 1, tzinfo=dt.UTC)}
        gw._comments = {
            5: [
                IssueComment(
                    author="someone",
                    author_type="User",
                    created_at=dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
                    url="https://example.invalid/c/1",
                    body="This is still broken for the nested case.",
                )
            ]
        }
        action = ManifestAction(
            issue=5,
            category=ACTION_CLOSE,
            rationale="resolved by commit abc1234",
            reproduction_verified=True,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert gw.closed == []

    def test_unresolvable_commit_timestamp_blocks_rather_than_skips(self):
        """Fail closed: no timestamp means scope cannot be checked."""
        gw = FakeGateway({5: _open(5)}, known_commits=frozenset({"abc1234"}))
        gw._commit_times = {}
        action = ManifestAction(
            issue=5,
            category=ACTION_CLOSE,
            rationale="resolved by commit abc1234",
            reproduction_verified=True,
        )
        outcome = apply_action(action, gw, mutate=True)
        assert outcome.outcome == OUTCOME_SKIPPED
        assert "timestamp" in outcome.detail
        assert gw.closed == []
