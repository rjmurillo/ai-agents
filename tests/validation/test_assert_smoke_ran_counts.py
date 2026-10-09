"""Quota-skip counting, all-skipped, and read-error tests for the smoke-ran gate.

Complements ``test_assert_smoke_ran.py``; report builders live in
``tests/lib/smoke_report.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.lib import smoke_report as sr

assert_smoke_ran = sr.load_gate()
EXIT_OK = assert_smoke_ran.EXIT_OK
EXIT_NOT_RUN = assert_smoke_ran.EXIT_NOT_RUN
EXIT_CONFIG = assert_smoke_ran.EXIT_CONFIG

Capsys = pytest.CaptureFixture[str]
_SMOKE = "test_cli_hook_e2e"
_ALLOW = ["--allow-skip-marker", sr.MARKER]


def test_all_cases_marker_skipped_without_require_pass_passes_and_reports_zero_ran(
    tmp_path: Path, capsys: Capsys
) -> None:
    report = sr.write_cases(
        tmp_path, sr.smoke_marker_skipped("test_a"), sr.smoke_marker_skipped("test_b")
    )

    code, message = assert_smoke_ran.evaluate(report, _SMOKE, 2, allow_skip_marker=sr.MARKER)

    assert code == EXIT_OK
    assert message.startswith("0 smoke test(s) ran and passed.")
    assert assert_smoke_ran.main([str(report), "--expected-count", "2", *_ALLOW]) == EXIT_OK
    assert "0 smoke test(s) ran" in capsys.readouterr().out


def test_all_cases_marker_skipped_with_require_pass_fails(tmp_path: Path) -> None:
    report = sr.write_cases(tmp_path, sr.smoke_marker_skipped("test_zero_token"))

    code, message = assert_smoke_ran.evaluate(report, _SMOKE, 1, sr.MARKER, ["test_zero_token"])

    assert code == EXIT_NOT_RUN
    assert "must PASS" in message


@pytest.mark.parametrize("count", [0, -1])
def test_expected_count_below_one_is_a_config_error(tmp_path: Path, count: int) -> None:
    report = sr.write_cases(tmp_path, sr.smoke_passed("test_a"))

    with pytest.raises(assert_smoke_ran.SmokeReportError, match="must be positive"):
        assert_smoke_ran.evaluate(report, _SMOKE, count)


def test_main_exits_two_for_expected_count_below_one(tmp_path: Path, capsys: Capsys) -> None:
    report = sr.write_cases(tmp_path, sr.smoke_passed("test_a"))

    assert assert_smoke_ran.main([str(report), "--expected-count", "0"]) == EXIT_CONFIG
    assert "must be positive" in capsys.readouterr().err


def test_raises_when_report_is_unreadable_but_present(tmp_path: Path) -> None:
    # A directory exists but cannot be read as a file: OSError, not FileNotFoundError.
    with pytest.raises(assert_smoke_ran.SmokeReportError, match="could not be read"):
        assert_smoke_ran.evaluate(tmp_path, _SMOKE)
