"""Skippable-check tests for scripts/ci/require_job_results.py.

A path-filtered workflow skips its smoke legs when no smoke path changed, while
a failed filter job must still fail the summary.
"""

from __future__ import annotations

import pytest

from scripts.ci.require_job_results import main

_SKIP_ARGS = [
    *("--check", "CHANGES_RESULT", "success", "filter result: {value}"),
    *("--skippable-check", "SMOKE_RESULT", "success", "smoke result: {value}"),
    *("--skip-when", "RUN", "false"),
    *("--skip-message", "no smoke path changed"),
    *("--success-message", "all legs passed"),
]
_BARE_SKIPPABLE = ["--skippable-check", "S", "success", "m"]


@pytest.mark.parametrize(
    ("changes", "run", "smoke", "expected_rc", "expected_line"),
    [
        ("success", "false", "skipped", 0, "no smoke path changed"),
        ("success", "true", "success", 0, "all legs passed"),
        ("failure", "false", None, 1, "::error::filter result: failure"),
        ("success", "true", "cancelled", 1, "::error::smoke result: cancelled"),
        # A path filter that never reported must not read as 'nothing to run'.
        ("success", None, "skipped", 1, "::error::smoke result: skipped"),
    ],
    ids=["skip-holds", "all-green", "skip-keeps-always-checks", "no-skip-runs-legs", "unset-run"],
)
def test_skip_condition_decides_which_checks_run(
    changes: str,
    run: str | None,
    smoke: str | None,
    expected_rc: int,
    expected_line: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name, value in (("CHANGES_RESULT", changes), ("RUN", run), ("SMOKE_RESULT", smoke)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    assert main(_SKIP_ARGS) == expected_rc
    assert expected_line in capsys.readouterr().out


def test_skip_when_without_an_always_check_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([*_BARE_SKIPPABLE, "--skip-when", "RUN", "false"]) == 2
    assert "--skip-when needs at least one --check" in capsys.readouterr().err


@pytest.mark.parametrize(("observed", "expected_rc"), [("success", 0), ("failure", 1)])
def test_skippable_check_without_a_skip_condition_always_runs(
    observed: str, expected_rc: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("S", observed)

    assert main(_BARE_SKIPPABLE) == expected_rc
