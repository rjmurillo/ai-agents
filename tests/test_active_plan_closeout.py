"""Tests for active execution plan closeout warnings."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.validation.active_plan_closeout import (
    active_plan_warnings,
    gh_issue_state,
    issue_refs,
    validate_active_plan_closeout,
)
from scripts.validation.evidence import (
    REASON_ADVISORY_FINDINGS,
    REASON_LOOKUP_FAILED,
    EvidenceState,
    pre_pr_policy,
)


def write_active_plan(repo_root: Path, name: str, body: str) -> Path:
    """Create an active plan fixture."""
    path = repo_root / ".project-toolkit" / "plans" / "active" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_warns_when_every_tracking_issue_is_closed(tmp_path: Path) -> None:
    write_active_plan(
        tmp_path,
        "closed.md",
        "# Plan\n\nRelated: #101 and https://github.com/rjmurillo/ai-agents/issues/102\n",
    )

    warnings = active_plan_warnings(
        tmp_path,
        issue_state_lookup=lambda issue: "CLOSED",
    )

    assert [warning.format() for warning in warnings] == [
        ".project-toolkit/plans/active/closed.md: #101, #102 closed. Move the plan to "
        "completed/ or abandoned/."
    ]


def test_does_not_warn_when_any_tracking_issue_is_open(tmp_path: Path) -> None:
    write_active_plan(tmp_path, "mixed.md", "# Plan\n\nRelated: #101 and #102\n")

    warnings = active_plan_warnings(
        tmp_path,
        issue_state_lookup=lambda issue: "OPEN" if issue == 102 else "CLOSED",
    )

    assert warnings == []


def test_missing_or_unknown_tracking_issue_does_not_warn(tmp_path: Path) -> None:
    write_active_plan(tmp_path, "unknown.md", "# Plan\n\nRelated: #101\n")
    write_active_plan(tmp_path, "no-refs.md", "# Plan\n\nNo issue link yet.\n")

    warnings = active_plan_warnings(
        tmp_path,
        issue_state_lookup=lambda issue: None,
    )

    assert warnings == []


def test_issue_refs_are_unique_and_sorted() -> None:
    markdown = "Related: #3, #2, #3 and https://github.com/a/b/issues/1"

    assert issue_refs(markdown) == (1, 2, 3)


def test_validator_is_advisory_when_warning_exists(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    write_active_plan(tmp_path, "closed.md", "# Plan\n\nRelated: #101\n")
    monkeypatch.setattr(
        "scripts.validation.active_plan_closeout.gh_issue_state",
        lambda issue, repo: "CLOSED",
    )

    outcome = validate_active_plan_closeout(tmp_path)

    assert outcome.state is EvidenceState.FAIL
    assert outcome.reason == REASON_ADVISORY_FINDINGS
    assert outcome.findings == 1
    assert pre_pr_policy().accepts(outcome)
    captured = capsys.readouterr()
    assert "[WARNING] Active execution plans have closed tracking issues:" in captured.out
    assert ".project-toolkit/plans/active/closed.md: #101 closed." in captured.out


def test_evaluates_issue_and_pr_terminal_states_in_one_run(tmp_path: Path, capsys) -> None:
    write_active_plan(tmp_path, "closed-issue.md", "# Plan\n\nRelated: #101\n")
    write_active_plan(tmp_path, "merged-pr.md", "# Plan\n\nRelated: #102\n")
    write_active_plan(tmp_path, "open-issue.md", "# Plan\n\nRelated: #103\n")
    write_active_plan(tmp_path, "open-pr.md", "# Plan\n\nRelated: #104\n")
    write_active_plan(tmp_path, "unknown-state.md", "# Plan\n\nRelated: #105\n")

    states = {
        101: "CLOSED",
        102: "MERGED",
        103: "OPEN",
        104: "OPEN",
        105: "UNRECOGNIZED",
    }
    warnings = active_plan_warnings(
        tmp_path,
        issue_state_lookup=lambda issue: states[issue],
    )

    assert [warning.plan_path for warning in warnings] == [
        ".project-toolkit/plans/active/closed-issue.md",
        ".project-toolkit/plans/active/merged-pr.md",
    ]
    captured = capsys.readouterr()
    assert "unrecognized state UNRECOGNIZED for #105" in captured.out


def test_gh_absent_is_advisory(
    monkeypatch,
    capsys,
) -> None:
    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr("scripts.validation.active_plan_closeout.subprocess.run", raise_missing)

    assert gh_issue_state(101, repo="owner/repo") is None

    captured = capsys.readouterr()
    assert "gh executable unavailable" in captured.out


def test_gh_nonzero_is_advisory(monkeypatch, capsys) -> None:
    def fail_command(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 3, "", "network unavailable")

    monkeypatch.setattr("scripts.validation.active_plan_closeout.subprocess.run", fail_command)

    assert gh_issue_state(101, repo="owner/repo") is None

    captured = capsys.readouterr()
    assert "could not inspect #101: gh lookup failed" in captured.out
    assert "network unavailable" in captured.out


def test_gh_unrecognized_output_is_advisory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    write_active_plan(tmp_path, "bad-state.md", "# Plan\n\nRelated: #101\n")

    def bad_state(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, "SURPRISE\n", "")

    monkeypatch.setattr("scripts.validation.active_plan_closeout.subprocess.run", bad_state)

    outcome = validate_active_plan_closeout(tmp_path)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_LOOKUP_FAILED
    assert pre_pr_policy().accepts(outcome)
    captured = capsys.readouterr()
    assert "unrecognized state SURPRISE for #101" in captured.out


def test_gh_timeout_is_advisory(monkeypatch, capsys) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1)

    monkeypatch.setattr("scripts.validation.active_plan_closeout.subprocess.run", timeout)

    assert gh_issue_state(101, repo="owner/repo") is None

    captured = capsys.readouterr()
    assert "could not inspect #101: gh lookup timed out" in captured.out


def test_issue_refs_captures_pull_request_urls() -> None:
    markdown = (
        "Tracked by https://github.com/rjmurillo/ai-agents/pull/1633 "
        "and #1574."
    )

    assert issue_refs(markdown) == (1574, 1633)


def test_gh_issue_state_rejects_invalid_repo_format(capsys) -> None:
    result = gh_issue_state(101, repo="invalid repo; echo pwned")

    assert result is None
    captured = capsys.readouterr()
    assert "invalid repo format" in captured.out


def test_clean_run_is_a_pass_that_names_how_many_lookups_it_made(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    write_active_plan(tmp_path, "open.md", "# Plan\n\nRelated: #101 and #102\n")
    monkeypatch.setattr(
        "scripts.validation.active_plan_closeout.gh_issue_state",
        lambda issue, repo: "OPEN",
    )

    outcome = validate_active_plan_closeout(tmp_path)

    assert outcome.state is EvidenceState.PASS
    assert outcome.examined == 2
    assert "[PASS] Active plan closeout advisory" in capsys.readouterr().out


def test_unreachable_gh_is_blocked_not_a_pass(tmp_path: Path, monkeypatch, capsys) -> None:
    """The silent-pass case: a lookup that returns None used to print [PASS]."""
    write_active_plan(tmp_path, "open.md", "# Plan\n\nRelated: #101\n")
    monkeypatch.setattr(
        "scripts.validation.active_plan_closeout.gh_issue_state",
        lambda issue, repo: None,
    )

    outcome = validate_active_plan_closeout(tmp_path)

    assert outcome.state is EvidenceState.BLOCKED
    assert outcome.reason == REASON_LOOKUP_FAILED
    assert "1 of 1 issue lookup(s)" in outcome.detail
    out = capsys.readouterr().out
    assert "[PASS]" not in out
    assert "1 of 1 issue lookup(s) returned no usable state" in out


def test_no_active_plans_is_a_pass_with_zero_examined(tmp_path: Path) -> None:
    outcome = validate_active_plan_closeout(tmp_path)

    assert outcome.state is EvidenceState.PASS
    assert outcome.examined == 0


def test_findings_and_a_failed_lookup_report_both_in_the_detail(
    tmp_path: Path, monkeypatch
) -> None:
    write_active_plan(tmp_path, "closed.md", "# Plan\n\nRelated: #101\n")
    write_active_plan(tmp_path, "unknown.md", "# Plan\n\nRelated: #202\n")
    monkeypatch.setattr(
        "scripts.validation.active_plan_closeout.gh_issue_state",
        lambda issue, repo: "CLOSED" if issue == 101 else None,
    )

    outcome = validate_active_plan_closeout(tmp_path)

    assert outcome.state is EvidenceState.FAIL
    assert "1 of 2 lookup(s) returned no usable state" in outcome.detail
