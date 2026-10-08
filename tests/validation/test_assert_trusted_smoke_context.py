#!/usr/bin/env python3
"""Tests for the trusted-context gate on the authenticated smoke (issue #2231 item 3, REQ-047).

The gate keeps the secret-bearing smoke from running attacker-controlled code.
These tests cover the authorized path, every denial reason, and the CLI argv
contract (stdout decision, exit code).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "validation"
    / "assert_trusted_smoke_context.py"
)
_spec = importlib.util.spec_from_file_location("assert_trusted_smoke_context", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

_REPO = "rjmurillo/ai-agents"
_REF = "refs/heads/main"


def test_trusted_when_dispatched_on_trusted_repo() -> None:
    trusted, reason = gate.is_trusted("workflow_dispatch", _REPO, _REPO, _REF, _REF)

    assert trusted is True
    assert "trusted context" in reason


def test_trusted_for_same_repo_pull_request() -> None:
    trusted, reason = gate.is_trusted(
        "pull_request", _REPO, _REPO, "refs/pull/7/merge", _REF, head_repository=_REPO
    )

    assert trusted is True
    assert "trusted context" in reason


def test_pull_request_ref_is_not_checked_against_the_default_branch() -> None:
    trusted, _ = gate.is_trusted(
        "pull_request", _REPO, _REPO, "refs/pull/7/merge", _REF, head_repository=_REPO
    )

    assert trusted is True


def test_trusted_repo_comparison_is_case_insensitive() -> None:
    trusted, _ = gate.is_trusted("workflow_dispatch", _REPO.upper(), _REPO.lower(), _REF, _REF)

    assert trusted is True


def test_head_repository_comparison_is_case_insensitive() -> None:
    trusted, _ = gate.is_trusted(
        "pull_request", _REPO, _REPO, "refs/pull/7/merge", _REF, head_repository=_REPO.upper()
    )

    assert trusted is True


def test_denied_for_fork_pull_request() -> None:
    trusted, reason = gate.is_trusted(
        "pull_request",
        _REPO,
        _REPO,
        "refs/pull/7/merge",
        _REF,
        head_repository="attacker/ai-agents",
    )

    assert trusted is False
    assert "fork" in reason


@pytest.mark.parametrize("head_repository", [None, "", "   "])
def test_denied_for_pull_request_without_a_head_repository(head_repository: str | None) -> None:
    trusted, reason = gate.is_trusted(
        "pull_request", _REPO, _REPO, "refs/pull/7/merge", _REF, head_repository=head_repository
    )

    assert trusted is False
    assert "head repository" in reason


def test_head_repository_does_not_help_a_dispatch_on_the_wrong_ref() -> None:
    trusted, reason = gate.is_trusted(
        "workflow_dispatch", _REPO, _REPO, "refs/heads/feature", _REF, head_repository=_REPO
    )

    assert trusted is False
    assert "not the trusted ref" in reason


def test_denied_for_schedule_event() -> None:
    trusted, reason = gate.is_trusted("schedule", _REPO, _REPO, _REF, _REF)

    assert trusted is False
    assert "not a trusted trigger" in reason


def test_denied_for_fork_repository() -> None:
    trusted, reason = gate.is_trusted("workflow_dispatch", "attacker/ai-agents", _REPO, _REF, _REF)

    assert trusted is False
    assert "not the trusted repo" in reason


def test_denied_when_pull_request_runs_in_a_fork_repository() -> None:
    trusted, reason = gate.is_trusted(
        "pull_request",
        "attacker/ai-agents",
        _REPO,
        "refs/pull/7/merge",
        _REF,
        head_repository="attacker/ai-agents",
    )

    assert trusted is False
    assert "not the trusted repo" in reason


def test_denied_for_unknown_event() -> None:
    trusted, _ = gate.is_trusted("push", _REPO, _REPO, _REF, _REF, head_repository=_REPO)

    assert trusted is False


def test_denied_for_untrusted_ref() -> None:
    trusted, reason = gate.is_trusted(
        "workflow_dispatch",
        _REPO,
        _REPO,
        "refs/heads/feature",
        _REF,
    )

    assert trusted is False
    assert "not the trusted ref" in reason


def test_main_prints_true_and_exits_zero_when_trusted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = gate.main(
        [
            "--event-name",
            "workflow_dispatch",
            "--repository",
            _REPO,
            "--ref",
            _REF,
            "--expected-repo",
            _REPO,
            "--expected-ref",
            _REF,
        ]
    )

    captured = capsys.readouterr()
    assert code == gate.EXIT_OK
    assert captured.out.strip() == "true"
    assert "trusted-context gate" in captured.err


def test_main_trusts_a_same_repo_pull_request(capsys: pytest.CaptureFixture[str]) -> None:
    code = gate.main(
        [
            "--event-name",
            "pull_request",
            "--repository",
            _REPO,
            "--ref",
            "refs/pull/7/merge",
            "--head-repository",
            _REPO,
        ]
    )

    assert code == gate.EXIT_OK
    assert capsys.readouterr().out.strip() == "true"


def test_main_denies_a_fork_pull_request(capsys: pytest.CaptureFixture[str]) -> None:
    code = gate.main(
        [
            "--event-name",
            "pull_request",
            "--repository",
            _REPO,
            "--ref",
            "refs/pull/7/merge",
            "--head-repository",
            "fork/ai-agents",
        ]
    )

    captured = capsys.readouterr()
    assert code == gate.EXIT_OK
    assert captured.out.strip() == "false"
    assert "fork/ai-agents" not in captured.err


def test_main_denies_a_pull_request_with_no_head_repository_arg(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = gate.main(
        ["--event-name", "pull_request", "--repository", _REPO, "--ref", "refs/pull/7/merge"]
    )

    assert code == gate.EXIT_OK
    assert capsys.readouterr().out.strip() == "false"


def test_main_prints_false_when_untrusted(capsys: pytest.CaptureFixture[str]) -> None:
    code = gate.main(
        [
            "--event-name",
            "workflow_dispatch",
            "--repository",
            "fork/ai-agents",
            "--ref",
            _REF,
            "--expected-repo",
            _REPO,
        ]
    )

    captured = capsys.readouterr()
    assert code == gate.EXIT_OK
    assert captured.out.strip() == "false"
    assert "fork/ai-agents" not in captured.err
    assert _REPO not in captured.err


def test_main_uses_default_expected_repo(capsys: pytest.CaptureFixture[str]) -> None:
    code = gate.main(["--event-name", "workflow_dispatch", "--repository", _REPO, "--ref", _REF])

    captured = capsys.readouterr()
    assert code == gate.EXIT_OK
    assert captured.out.strip() == "true"


def test_main_exits_two_when_required_arg_missing() -> None:
    with pytest.raises(SystemExit) as exc:
        gate.main(["--event-name", "workflow_dispatch"])

    assert exc.value.code == gate.EXIT_USAGE
