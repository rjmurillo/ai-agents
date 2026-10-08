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
EXIT_CONFIG = assert_smoke_ran.EXIT_CONFIG


def test_marker_skip_is_allowed_and_reported_with_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = sr.passed_case(sr.SMOKE_CLASS, "test_zero_token") + sr.marker_skipped_case(
        sr.SMOKE_CLASS, "test_prompt_probe"
    )
    report = sr.write_report(tmp_path, cases)

    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "2", "--allow-skip-marker", sr.MARKER]
    )

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "test_prompt_probe" in captured.out
    assert "QUOTA_SKIP:" in captured.out


def test_marker_skip_without_the_flag_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = sr.passed_case(sr.SMOKE_CLASS, "test_zero_token") + sr.marker_skipped_case(
        sr.SMOKE_CLASS, "test_prompt_probe"
    )
    report = sr.write_report(tmp_path, cases)

    code = assert_smoke_ran.main([str(report), "--expected-count", "2"])

    assert code == EXIT_NOT_RUN
    assert "SKIPPED" in capsys.readouterr().err


def test_unmarked_skip_still_fails_with_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = sr.marker_skipped_case(sr.SMOKE_CLASS, "test_prompt_probe") + sr.skipped_case(
        sr.SMOKE_CLASS, "test_zero_token"
    )
    report = sr.write_report(tmp_path, cases)

    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "2", "--allow-skip-marker", sr.MARKER]
    )

    assert code == EXIT_NOT_RUN
    err = capsys.readouterr().err
    assert "test_zero_token" in err
    assert "test_prompt_probe" not in err


def test_marker_must_match_the_skip_message_not_the_test_name(tmp_path: Path) -> None:
    cases = sr.skipped_case(sr.SMOKE_CLASS, "test_QUOTA_SKIP:_named")
    report = sr.write_report(tmp_path, cases)

    code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 1, allow_skip_marker=sr.MARKER)

    assert code == EXIT_NOT_RUN


def test_marker_skip_does_not_mask_a_failure(tmp_path: Path) -> None:
    cases = sr.marker_skipped_case(sr.SMOKE_CLASS, "test_a") + sr.failed_case(
        sr.SMOKE_CLASS, "test_b"
    )
    report = sr.write_report(tmp_path, cases)

    code, message = assert_smoke_ran.evaluate(
        report, "test_cli_hook_e2e", 2, allow_skip_marker=sr.MARKER
    )

    assert code == EXIT_NOT_RUN
    assert "FAILED" in message


def test_count_includes_marker_skips_and_rejects_a_short_set(tmp_path: Path) -> None:
    cases = sr.passed_case(sr.SMOKE_CLASS, "test_a") + sr.marker_skipped_case(
        sr.SMOKE_CLASS, "test_b"
    )
    report = sr.write_report(tmp_path, cases)

    ok, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 2, allow_skip_marker=sr.MARKER)
    short, message = assert_smoke_ran.evaluate(
        report, "test_cli_hook_e2e", 3, allow_skip_marker=sr.MARKER
    )

    assert ok == EXIT_OK
    assert short == EXIT_NOT_RUN
    assert "1 of 3" not in message
    assert "2 of 3" in message


def test_empty_marker_is_a_config_error(tmp_path: Path) -> None:
    report = sr.write_report(tmp_path, sr.passed_case(sr.SMOKE_CLASS, "test_a"))

    with pytest.raises(assert_smoke_ran.SmokeReportError):
        assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 1, allow_skip_marker="  ")
