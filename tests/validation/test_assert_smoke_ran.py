"""Tests for the smoke-ran gate (issue #2231 item 4).

The gate proves the real-CLI smoke actually ran instead of skipping silently.
Each test builds a JUnit XML report (the format pytest's ``--junitxml`` writes)
and asserts the gate's verdict for the report shapes: passed, skipped, failed,
missing, incomplete, and malformed. Sibling files cover the CLI, skip markers,
and required passes; report builders live in ``tests/lib/smoke_report.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.lib import smoke_report as sr

assert_smoke_ran = sr.load_gate()
EXIT_OK = assert_smoke_ran.EXIT_OK
EXIT_NOT_RUN = assert_smoke_ran.EXIT_NOT_RUN
EXIT_CONFIG = assert_smoke_ran.EXIT_CONFIG

_OTHER_CLASS = "tests.unit.test_helpers"


def test_returns_ok_when_smoke_case_passed(tmp_path: Path) -> None:
    cases = sr.passed_case(
        sr.SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves"
    ) + sr.passed_case(sr.SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves")
    report = sr.write_report(
        tmp_path,
        cases,
    )

    exit_code, message = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_OK
    assert "ran and passed" in message


def test_returns_not_run_when_smoke_case_skipped(tmp_path: Path) -> None:
    cases = sr.passed_case(
        sr.SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves"
    ) + sr.skipped_case(sr.SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves")
    report = sr.write_report(
        tmp_path,
        cases,
    )

    exit_code, message = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_NOT_RUN
    assert "SKIPPED" in message


def test_returns_not_run_when_no_smoke_case_collected(tmp_path: Path) -> None:
    report = sr.write_report(tmp_path, sr.passed_case(_OTHER_CLASS, "test_something_else"))

    exit_code, message = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_NOT_RUN
    assert "not collected" in message or "no smoke test" in message


def test_returns_not_run_when_smoke_case_failed(tmp_path: Path) -> None:
    cases = sr.passed_case(sr.SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves") + sr.failed_case(
        sr.SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves"
    )
    report = sr.write_report(
        tmp_path,
        cases,
    )

    exit_code, message = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_NOT_RUN
    assert "FAILED" in message


def test_skipped_among_passed_smoke_cases_still_fails(tmp_path: Path) -> None:
    cases = sr.passed_case(
        sr.SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves"
    ) + sr.skipped_case(sr.SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves")
    report = sr.write_report(tmp_path, cases)

    exit_code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_NOT_RUN


def test_parses_testsuites_wrapper_shape(tmp_path: Path) -> None:
    cases = sr.passed_case(
        sr.SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves"
    ) + sr.passed_case(sr.SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves")
    report = sr.write_report(
        tmp_path,
        cases,
        wrap=True,
    )

    exit_code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_OK


def test_returns_not_run_when_smoke_set_is_incomplete(tmp_path: Path) -> None:
    report = sr.write_report(
        tmp_path, sr.passed_case(sr.SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves")
    )

    exit_code, message = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", expected_count=2)

    assert exit_code == EXIT_NOT_RUN
    assert "incomplete" in message


def test_rejects_report_with_doctype(tmp_path: Path) -> None:
    report = tmp_path / "evil.xml"
    report.write_text(
        '<?xml version="1.0"?>'
        '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        '<testsuite><testcase classname="x" name="y"></testcase></testsuite>',
        encoding="utf-8",
    )

    with pytest.raises(assert_smoke_ran.SmokeReportError, match="DTD or entity"):
        assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")


def test_raises_when_report_missing(tmp_path: Path) -> None:
    with pytest.raises(assert_smoke_ran.SmokeReportError, match="not found"):
        assert_smoke_ran.evaluate(tmp_path / "absent.xml", "test_cli_hook_e2e")


def test_raises_when_report_malformed(tmp_path: Path) -> None:
    report = tmp_path / "broken.xml"
    report.write_text("<testsuite><testcase>", encoding="utf-8")

    with pytest.raises(assert_smoke_ran.SmokeReportError, match="not valid XML"):
        assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")
