"""Skip-marker acceptance tests for the smoke-ran gate (owner decisions D25, D26).

Report builders live in ``tests/lib/smoke_report.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.lib import smoke_report as sr

assert_smoke_ran = sr.load_gate()
EXIT_OK = assert_smoke_ran.EXIT_OK
EXIT_NOT_RUN = assert_smoke_ran.EXIT_NOT_RUN

Capsys = pytest.CaptureFixture[str]
_SMOKE = "test_cli_hook_e2e"


def _judge(report: Path, expected: int, marker: str | None = sr.MARKER) -> tuple[int, str]:
    return assert_smoke_ran.evaluate(report, _SMOKE, expected, allow_skip_marker=marker)


def _probe_report(tmp_path: Path, second: str) -> Path:
    return sr.write_cases(tmp_path, sr.smoke_passed("test_zero_token"), second)


def test_marker_skip_is_allowed_and_reported_with_the_flag(tmp_path: Path, capsys: Capsys) -> None:
    report = _probe_report(tmp_path, sr.smoke_marker_skipped("test_prompt_probe"))
    argv = [str(report), "--expected-count", "2", "--allow-skip-marker", sr.MARKER]

    assert assert_smoke_ran.main(argv) == EXIT_OK
    out = capsys.readouterr().out
    assert "test_prompt_probe" in out
    assert "QUOTA_SKIP:" in out


def test_marker_skip_without_the_flag_fails(tmp_path: Path, capsys: Capsys) -> None:
    report = _probe_report(tmp_path, sr.smoke_marker_skipped("test_prompt_probe"))

    assert assert_smoke_ran.main([str(report), "--expected-count", "2"]) == EXIT_NOT_RUN
    assert "SKIPPED" in capsys.readouterr().err


def test_unmarked_skip_still_fails_with_the_flag(tmp_path: Path, capsys: Capsys) -> None:
    report = sr.write_cases(
        tmp_path, sr.smoke_marker_skipped("test_prompt_probe"), sr.smoke_skipped("test_zero_token")
    )
    argv = [str(report), "--expected-count", "2", "--allow-skip-marker", sr.MARKER]

    assert assert_smoke_ran.main(argv) == EXIT_NOT_RUN
    err = capsys.readouterr().err
    assert "test_zero_token" in err
    assert "test_prompt_probe" not in err


def test_marker_must_match_the_skip_message_not_the_test_name(tmp_path: Path) -> None:
    report = sr.write_cases(tmp_path, sr.smoke_skipped("test_QUOTA_SKIP:_named"))

    assert _judge(report, 1)[0] == EXIT_NOT_RUN


def test_marker_skip_does_not_mask_a_failure(tmp_path: Path) -> None:
    report = sr.write_cases(tmp_path, sr.smoke_marker_skipped("test_a"), sr.smoke_failed("test_b"))

    code, message = _judge(report, 2)

    assert code == EXIT_NOT_RUN
    assert "FAILED" in message


def test_count_includes_marker_skips_and_rejects_a_short_set(tmp_path: Path) -> None:
    report = _probe_report(tmp_path, sr.smoke_marker_skipped("test_b"))

    short, message = _judge(report, 3)

    assert _judge(report, 2)[0] == EXIT_OK
    assert short == EXIT_NOT_RUN
    assert "2 of 3" in message


def test_empty_marker_is_a_config_error(tmp_path: Path) -> None:
    report = sr.write_cases(tmp_path, sr.smoke_passed("test_a"))

    with pytest.raises(assert_smoke_ran.SmokeReportError):
        _judge(report, 1, marker="  ")
