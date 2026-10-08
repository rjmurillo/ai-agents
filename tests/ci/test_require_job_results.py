"""Tests for scripts/ci/require_job_results.py.

Covers the summary-job gate extracted from nightly-cli-smoke.yml, which read
`needs.*` results from the environment and exited 1 on the first mismatch.
These tests pin the replacement contract: every check is evaluated so one run
reports all failures, an unset variable fails its check rather than passing
silently, and `{value}` interpolation reproduces the original annotations.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parent.parent.parent / "scripts" / "ci"
_original_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    from require_job_results import failures, main
finally:
    sys.path[:] = _original_path


def test_all_checks_match_returns_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    monkeypatch.setenv("B", "true")
    rc = main(
        [
            "--check", "A", "success", "a failed",
            "--check", "B", "true", "b failed",
            "--success-message", "all green",
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "all green"


def test_mismatch_returns_one_and_annotates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "failure")
    rc = main(["--check", "A", "success", "gate result: {value}"])
    assert rc == 1
    assert "::error::gate result: failure" in capsys.readouterr().out


def test_reports_every_failure_not_just_the_first(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "failure")
    monkeypatch.setenv("B", "false")
    rc = main(
        ["--check", "A", "success", "a bad", "--check", "B", "true", "b bad"]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::a bad" in out
    assert "::error::b bad" in out


def test_unset_variable_fails_its_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MISSING_RESULT", raising=False)
    rc = main(["--check", "MISSING_RESULT", "success", "missing: {value}"])
    assert rc == 1
    # Exact line: an unset variable must render as empty, never as the value
    # it was expected to hold. "missing: success" would read in the CI log as
    # though the upstream job had reported success.
    assert capsys.readouterr().out.splitlines() == ["::error::missing: "]


def test_message_without_placeholder_is_verbatim(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TRUSTED", "false")
    rc = main(["--check", "TRUSTED", "true", "Untrusted context; smoke skipped."])
    assert rc == 1
    assert "::error::Untrusted context; smoke skipped." in capsys.readouterr().out


def test_no_checks_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "at least one --check" in capsys.readouterr().err


def test_success_message_is_optional(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    assert main(["--check", "A", "success", "nope"]) == 0
    assert capsys.readouterr().out == ""


def test_failures_helper_preserves_check_order() -> None:
    checks = [
        ("A", "success", "first"),
        ("B", "success", "second"),
        ("C", "success", "third"),
    ]
    assert failures(checks, {"B": "success"}) == ["first", "third"]


def test_empty_expected_matches_unset_variable() -> None:
    assert failures([("X", "", "unset ok")], {}) == []
