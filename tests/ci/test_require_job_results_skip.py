"""Skippable-check tests for scripts/ci/require_job_results.py.

A path-filtered workflow skips its smoke legs when no smoke path changed, while
a failed filter job must still fail the summary.
"""

from __future__ import annotations

import pytest

from scripts.ci.require_job_results import main


def _skip_args() -> list[str]:
    return [
        "--check",
        "CHANGES_RESULT",
        "success",
        "filter result: {value}",
        "--skippable-check",
        "SMOKE_RESULT",
        "success",
        "smoke result: {value}",
        "--skip-when",
        "RUN",
        "false",
        "--skip-message",
        "no smoke path changed",
        "--success-message",
        "all legs passed",
    ]


def test_skip_condition_passes_without_the_skippable_checks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHANGES_RESULT", "success")
    monkeypatch.setenv("RUN", "false")
    monkeypatch.setenv("SMOKE_RESULT", "skipped")

    assert main(_skip_args()) == 0
    assert capsys.readouterr().out.strip() == "no smoke path changed"


def test_skip_condition_still_enforces_the_always_checks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHANGES_RESULT", "failure")
    monkeypatch.setenv("RUN", "false")

    assert main(_skip_args()) == 1
    assert "::error::filter result: failure" in capsys.readouterr().out


def test_skippable_checks_run_when_the_skip_condition_is_false(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHANGES_RESULT", "success")
    monkeypatch.setenv("RUN", "true")
    monkeypatch.setenv("SMOKE_RESULT", "cancelled")

    assert main(_skip_args()) == 1
    assert "::error::smoke result: cancelled" in capsys.readouterr().out


def test_all_green_prints_the_success_message_not_the_skip_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHANGES_RESULT", "success")
    monkeypatch.setenv("RUN", "true")
    monkeypatch.setenv("SMOKE_RESULT", "success")

    assert main(_skip_args()) == 0
    assert capsys.readouterr().out.strip() == "all legs passed"


def test_unset_skip_variable_does_not_skip(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A path filter that never reported must not read as 'nothing to run'."""
    monkeypatch.setenv("CHANGES_RESULT", "success")
    monkeypatch.delenv("RUN", raising=False)
    monkeypatch.setenv("SMOKE_RESULT", "skipped")

    assert main(_skip_args()) == 1
    assert "::error::smoke result: skipped" in capsys.readouterr().out


def test_skip_when_without_an_always_check_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--skippable-check", "S", "success", "m", "--skip-when", "RUN", "false"])

    assert rc == 2
    assert "--skip-when needs at least one --check" in capsys.readouterr().err


def test_skippable_checks_alone_count_as_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S", "success")

    assert main(["--skippable-check", "S", "success", "m"]) == 0


def test_skippable_check_without_a_skip_condition_always_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S", "failure")

    assert main(["--skippable-check", "S", "success", "m"]) == 1
