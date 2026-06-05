#!/usr/bin/env python3
"""Tests for the trusted-context gate on the authenticated smoke (issue #2231 item 3).

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


def test_trusted_when_scheduled_on_trusted_repo() -> None:
    trusted, reason = gate.is_trusted("schedule", _REPO, _REPO, _REF, _REF)

    assert trusted is True
    assert "trusted context" in reason


def test_trusted_when_dispatched_on_trusted_repo() -> None:
    trusted, _ = gate.is_trusted("workflow_dispatch", _REPO, _REPO, _REF, _REF)

    assert trusted is True


def test_trusted_repo_comparison_is_case_insensitive() -> None:
    trusted, _ = gate.is_trusted("schedule", _REPO.upper(), _REPO.lower(), _REF, _REF)

    assert trusted is True


def test_denied_for_pull_request_event() -> None:
    trusted, reason = gate.is_trusted("pull_request", _REPO, _REPO, _REF, _REF)

    assert trusted is False
    assert "not a trusted trigger" in reason


def test_denied_for_fork_repository() -> None:
    trusted, reason = gate.is_trusted("schedule", "attacker/ai-agents", _REPO, _REF, _REF)

    assert trusted is False
    assert "not the trusted repo" in reason


def test_denied_for_unknown_event() -> None:
    trusted, _ = gate.is_trusted("push", _REPO, _REPO, _REF, _REF)

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
            "schedule",
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


def test_main_prints_false_when_untrusted(capsys: pytest.CaptureFixture[str]) -> None:
    code = gate.main(
        [
            "--event-name",
            "schedule",
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
        gate.main(["--event-name", "schedule"])

    assert exc.value.code == gate.EXIT_USAGE
