"""Tests for scripts.triage_batch_apply.

Covers the Phase 3 batch executor (issue #2261): the human-approval gate (no
mutation without approved manifest plus --apply), idempotent skipping when an
issue is already in the target state, partial-failure handling that does not
abort the rest, and the CLI entry point. GitHub I/O is mocked at the gateway
boundary with a fake; domain logic is never mocked.
"""

from __future__ import annotations

import json
import subprocess
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
    CliGitHubGateway,
    IssueState,
    ManifestAction,
    apply_action,
    is_mutation_authorized,
    main,
    parse_actions,
    run_batch,
)


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

    def test_epic_label_blocks_close(self):
        gw = FakeGateway({9: _open(9, labels=("epic", "enhancement"))})
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
        action = ManifestAction(issue=5, category=ACTION_CLOSE, rationale="closed via PR #1024")
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
        result = subprocess.CompletedProcess(["gh"], 0, stdout=json.dumps(["MERGED"]), stderr="")
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
