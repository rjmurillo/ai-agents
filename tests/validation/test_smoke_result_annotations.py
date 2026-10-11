"""Failure-annotation tests for scripts/validation/smoke_result.py.

A failing `failure`, `cancelled`, or `skipped` result names the variable, the
likely cause, and the next action. Other values keep the bare message.
"""

from __future__ import annotations

import pytest

from scripts.validation.smoke_result import failing_checks, main


@pytest.mark.parametrize(
    ("value", "needle"),
    [
        ("failure", "environment approval"),
        ("cancelled", "newer push"),
        ("skipped", "`needs`"),
    ],
)
def test_known_result_values_name_the_variable_cause_and_next_action(
    value: str, needle: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SMOKE_RESULT", value)
    rc = main(["--check", "SMOKE_RESULT", "success", "smoke result: {value}"])
    line = capsys.readouterr().out.strip()
    assert rc == 1
    assert line.startswith(f"::error::smoke result: {value} [SMOKE_RESULT={value}]")
    assert "Cause:" in line and "Next:" in line
    assert needle in line


@pytest.mark.parametrize("value", ["", "false", "weird"])
def test_other_values_keep_the_bare_message(
    value: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("X", value)
    rc = main(["--check", "X", "success", "x bad"])
    assert rc == 1
    assert capsys.readouterr().out.splitlines() == ["::error::x bad"]


def test_failing_checks_returns_the_annotation_and_nothing_for_a_match() -> None:
    (line,) = failing_checks([("A", "success", "a {value}")], {"A": "failure"})

    assert line.startswith("a failure [A=failure] Cause:")
    assert failing_checks([("A", "success", "a")], {"A": "success"}) == []


def test_failing_checks_preserves_check_order() -> None:
    checks = [
        ("A", "success", "first"),
        ("B", "success", "second"),
        ("C", "success", "third"),
    ]
    assert failing_checks(checks, {"B": "success"}) == ["first", "third"]


def test_empty_expected_matches_unset_variable() -> None:
    assert failing_checks([("X", "", "unset ok")], {}) == []
