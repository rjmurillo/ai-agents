"""Tests for scripts/validation/smoke_result.py.

Covers the summary-job gate first extracted from the nightly CLI smoke and now
used by plugin-cli-smoke.yml. The inline shell read `needs.*` results from the
environment and exited 1 on the first mismatch. These tests pin the
replacement contract: every check is evaluated so one run
reports all failures, an unset variable fails its check rather than passing
silently, and `{value}` interpolation reproduces the original annotations.
Sibling files cover skippable checks, result annotations, and count notes.
"""

from __future__ import annotations

import pytest

from scripts.validation.smoke_result import main

Capsys = pytest.CaptureFixture[str]


def test_all_checks_match_returns_success(monkeypatch: pytest.MonkeyPatch, capsys: Capsys) -> None:
    monkeypatch.setenv("A", "success")
    monkeypatch.setenv("B", "true")
    argv = ["--check", "A", "success", "a failed", "--check", "B", "true", "b failed"]

    assert main([*argv, "--success-message", "all green"]) == 0
    assert capsys.readouterr().out.strip() == "all green"
    assert main(argv) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("observed", "message", "expected"),
    [
        ("failure", "gate result: {value}", "::error::gate result: failure"),
        (
            "false",
            "Untrusted context; smoke skipped.",
            "::error::Untrusted context; smoke skipped.",
        ),
        # An unset variable must render as empty, never as the value it was
        # expected to hold: "missing: success" would read as an upstream success.
        (None, "missing: {value}", "::error::missing: "),
    ],
    ids=["interpolated", "verbatim", "unset"],
)
def test_mismatch_returns_one_and_annotates(
    observed: str | None,
    message: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Capsys,
) -> None:
    if observed is None:
        monkeypatch.delenv("RESULT", raising=False)
    else:
        monkeypatch.setenv("RESULT", observed)

    assert main(["--check", "RESULT", "success", message]) == 1
    assert capsys.readouterr().out.splitlines()[0].startswith(expected)


def test_reports_every_failure_not_just_the_first(
    monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    monkeypatch.setenv("A", "failure")
    monkeypatch.setenv("B", "false")

    assert main(["--check", "A", "success", "a bad", "--check", "B", "true", "b bad"]) == 1
    out = capsys.readouterr().out
    assert "::error::a bad" in out
    assert "::error::b bad" in out


def test_no_checks_is_a_usage_error(capsys: Capsys) -> None:
    assert main([]) == 2
    assert "at least one --check" in capsys.readouterr().err
