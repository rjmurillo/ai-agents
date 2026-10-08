"""``--require-pass`` tests for the smoke-ran gate.

A required test must PASS: a marker skip, a miss, or a failure never satisfies
it. Report builders live in ``tests/lib/smoke_report.py``.
"""

from __future__ import annotations

from pathlib import Path

from tests.lib import smoke_report as sr

assert_smoke_ran = sr.load_gate()
EXIT_OK = assert_smoke_ran.EXIT_OK
EXIT_NOT_RUN = assert_smoke_ran.EXIT_NOT_RUN
EXIT_CONFIG = assert_smoke_ran.EXIT_CONFIG


def test_require_pass_accepts_a_passed_zero_token_test(tmp_path: Path) -> None:
    cases = sr.passed_case(sr.SMOKE_CLASS, "test_zero_token") + sr.marker_skipped_case(
        sr.SMOKE_CLASS, "test_prompt_probe"
    )
    report = sr.write_report(tmp_path, cases)

    code, _ = assert_smoke_ran.evaluate(
        report,
        "test_cli_hook_e2e",
        2,
        allow_skip_marker=sr.MARKER,
        require_pass=["test_zero_token"],
    )

    assert code == EXIT_OK


def test_require_pass_rejects_a_marker_skipped_required_test(tmp_path: Path) -> None:
    cases = sr.marker_skipped_case(sr.SMOKE_CLASS, "test_zero_token") + sr.passed_case(
        sr.SMOKE_CLASS, "test_prompt_probe"
    )
    report = sr.write_report(tmp_path, cases)

    code, message = assert_smoke_ran.evaluate(
        report,
        "test_cli_hook_e2e",
        2,
        allow_skip_marker=sr.MARKER,
        require_pass=["test_zero_token"],
    )

    assert code == EXIT_NOT_RUN
    assert "test_zero_token" in message
    assert "must PASS" in message


def test_require_pass_rejects_a_missing_required_test(tmp_path: Path) -> None:
    report = sr.write_report(tmp_path, sr.passed_case(sr.SMOKE_CLASS, "test_prompt_probe"))

    code, message = assert_smoke_ran.evaluate(
        report, "test_cli_hook_e2e", 1, require_pass=["test_zero_token"]
    )

    assert code == EXIT_NOT_RUN
    assert "no smoke test matched required" in message


def test_require_pass_rejects_a_failed_required_test(tmp_path: Path) -> None:
    report = sr.write_report(tmp_path, sr.failed_case(sr.SMOKE_CLASS, "test_zero_token"))

    code, _ = assert_smoke_ran.evaluate(
        report, "test_cli_hook_e2e", 1, require_pass=["test_zero_token"]
    )

    assert code == EXIT_NOT_RUN


def test_require_pass_blank_value_is_a_config_error(tmp_path: Path) -> None:
    report = sr.write_report(tmp_path, sr.passed_case(sr.SMOKE_CLASS, "test_a"))

    code = assert_smoke_ran.main([str(report), "--expected-count", "1", "--require-pass", " "])

    assert code == EXIT_CONFIG
