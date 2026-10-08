"""Tests for scripts/ci/require_job_results.py.

Covers the summary-job gate first extracted from the nightly CLI smoke and now
used by plugin-cli-smoke.yml. The inline shell read `needs.*` results from the
environment and exited 1 on the first mismatch. These tests pin the
replacement contract: every check is evaluated so one run
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
    from require_job_results import failing_checks, failures, main, sum_counts
finally:
    sys.path[:] = _original_path


def test_all_checks_match_returns_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    monkeypatch.setenv("B", "true")
    rc = main(
        [
            "--check",
            "A",
            "success",
            "a failed",
            "--check",
            "B",
            "true",
            "b failed",
            "--success-message",
            "all green",
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
    rc = main(["--check", "A", "success", "a bad", "--check", "B", "true", "b bad"])
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


def test_failing_checks_returns_name_value_and_message() -> None:
    result = failing_checks([("A", "success", "a {value}")], {"A": "failure"})
    assert result == [("A", "failure", "a failure")]
    assert failing_checks([("A", "success", "a")], {"A": "success"}) == []


def test_sum_counts_adds_every_file_and_ignores_missing_dir(tmp_path: Path) -> None:
    (tmp_path / "leg-a").mkdir()
    (tmp_path / "leg-a" / "quota-skips.txt").write_text("1\n0\n", encoding="utf-8")
    (tmp_path / "leg-b.txt").write_text("2\n", encoding="utf-8")
    assert sum_counts(tmp_path) == 3
    assert sum_counts(tmp_path / "absent") == 0


def test_sum_counts_warns_on_a_non_integer_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "c.txt").write_text("2\nbogus\n", encoding="utf-8")
    assert sum_counts(tmp_path) == 2
    assert "::warning::ignoring non-integer count 'bogus'" in capsys.readouterr().out


def _count_args(count_dir: Path) -> list[str]:
    return [
        "--check",
        "A",
        "success",
        "a failed",
        "--success-message",
        "all green",
        "--count-dir",
        str(count_dir),
        "--count-message",
        "passed with {count} prompt checks quota-skipped",
    ]


def test_count_message_replaces_success_when_total_is_positive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    (tmp_path / "c.txt").write_text("1\n2\n", encoding="utf-8")
    assert main(_count_args(tmp_path)) == 0
    assert capsys.readouterr().out.strip() == "passed with 3 prompt checks quota-skipped"


def test_success_message_stays_when_total_is_zero_or_dir_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    (tmp_path / "c.txt").write_text("0\n0\n", encoding="utf-8")
    assert main(_count_args(tmp_path)) == 0
    assert capsys.readouterr().out.strip() == "all green"
    assert main(_count_args(tmp_path / "absent")) == 0
    assert capsys.readouterr().out.strip() == "all green"


def test_count_message_is_not_printed_when_a_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "failure")
    (tmp_path / "c.txt").write_text("5\n", encoding="utf-8")
    assert main(_count_args(tmp_path)) == 1
    assert "quota-skipped" not in capsys.readouterr().out


def test_count_dir_without_count_message_keeps_the_success_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("A", "success")
    (tmp_path / "c.txt").write_text("4\n", encoding="utf-8")
    rc = main(
        ["--check", "A", "success", "x", "--success-message", "ok", "--count-dir", str(tmp_path)]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "ok"
