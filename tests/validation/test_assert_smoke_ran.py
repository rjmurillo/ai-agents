#!/usr/bin/env python3
"""Tests for the smoke-ran gate (issue #2231 item 4).

The gate proves the real-CLI smoke actually ran instead of skipping silently.
Each test builds a JUnit XML report (the format pytest's ``--junitxml`` writes)
and asserts the gate's exit code and message, covering positive, negative, and
edge cases plus the CLI argv path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "validation" / "assert_smoke_ran.py"
)
_spec = importlib.util.spec_from_file_location("assert_smoke_ran", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
assert_smoke_ran = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(assert_smoke_ran)

EXIT_OK = assert_smoke_ran.EXIT_OK
EXIT_NOT_RUN = assert_smoke_ran.EXIT_NOT_RUN
EXIT_CONFIG = assert_smoke_ran.EXIT_CONFIG

_SMOKE_CLASS = "tests.e2e.test_cli_hook_e2e"
_OTHER_CLASS = "tests.unit.test_helpers"


def _write_report(tmp_path: Path, cases_xml: str, *, wrap: bool = False) -> Path:
    suite = f'<testsuite name="pytest" tests="1">{cases_xml}</testsuite>'
    body = f"<testsuites>{suite}</testsuites>" if wrap else suite
    report = tmp_path / "report.xml"
    report.write_text(f'<?xml version="1.0" encoding="utf-8"?>{body}', encoding="utf-8")
    return report


def _passed_case(classname: str, name: str) -> str:
    return f'<testcase classname="{classname}" name="{name}" time="0.1"></testcase>'


def _skipped_case(classname: str, name: str) -> str:
    return (
        f'<testcase classname="{classname}" name="{name}" time="0.0">'
        '<skipped type="pytest.skip" message="needs RUN_CLI_E2E=1"></skipped>'
        "</testcase>"
    )


def _failed_case(classname: str, name: str) -> str:
    return (
        f'<testcase classname="{classname}" name="{name}" time="0.2">'
        '<failure message="assert">hook never ran</failure>'
        "</testcase>"
    )


def test_returns_ok_when_smoke_case_passed(tmp_path: Path) -> None:
    cases = _passed_case(
        _SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves"
    ) + _passed_case(_SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves")
    report = _write_report(
        tmp_path,
        cases,
    )

    exit_code, message = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_OK
    assert "ran and passed" in message


def test_returns_not_run_when_smoke_case_skipped(tmp_path: Path) -> None:
    cases = _passed_case(_SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves") + _skipped_case(
        _SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves"
    )
    report = _write_report(
        tmp_path,
        cases,
    )

    exit_code, message = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_NOT_RUN
    assert "SKIPPED" in message


def test_returns_not_run_when_no_smoke_case_collected(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _passed_case(_OTHER_CLASS, "test_something_else"))

    exit_code, message = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_NOT_RUN
    assert "not collected" in message or "no smoke test" in message


def test_returns_not_run_when_smoke_case_failed(tmp_path: Path) -> None:
    cases = _passed_case(_SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves") + _failed_case(
        _SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves"
    )
    report = _write_report(
        tmp_path,
        cases,
    )

    exit_code, message = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_NOT_RUN
    assert "FAILED" in message


def test_skipped_among_passed_smoke_cases_still_fails(tmp_path: Path) -> None:
    cases = _passed_case(_SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves") + _skipped_case(
        _SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves"
    )
    report = _write_report(tmp_path, cases)

    exit_code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_NOT_RUN


def test_parses_testsuites_wrapper_shape(tmp_path: Path) -> None:
    cases = _passed_case(
        _SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves"
    ) + _passed_case(_SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves")
    report = _write_report(
        tmp_path,
        cases,
        wrap=True,
    )

    exit_code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

    assert exit_code == EXIT_OK


def test_returns_not_run_when_smoke_set_is_incomplete(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path, _passed_case(_SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves")
    )

    exit_code, message = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e")

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


def test_main_exits_zero_when_smoke_ran(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cases = _passed_case(
        _SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves"
    ) + _passed_case(_SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves")
    report = _write_report(
        tmp_path,
        cases,
    )

    code = assert_smoke_ran.main([str(report)])

    assert code == EXIT_OK
    assert "smoke gate OK" in capsys.readouterr().out


def test_main_exits_one_when_smoke_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _write_report(
        tmp_path, _skipped_case(_SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves")
    )

    code = assert_smoke_ran.main([str(report)])

    assert code == EXIT_NOT_RUN
    assert "::error::" in capsys.readouterr().err


def test_main_exits_two_when_report_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = assert_smoke_ran.main([str(tmp_path / "absent.xml")])

    assert code == EXIT_CONFIG
    assert "::error::" in capsys.readouterr().err


def test_main_honors_custom_smoke_substr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _write_report(tmp_path, _passed_case("custom.module", "test_my_smoke"))

    code = assert_smoke_ran.main(
        [str(report), "--smoke-substr", "test_my_smoke", "--expected-count", "1"]
    )

    assert code == EXIT_OK


_MARKER = "QUOTA_SKIP:"


def _marker_skipped_case(classname: str, name: str, marker: str = _MARKER) -> str:
    return (
        f'<testcase classname="{classname}" name="{name}" time="0.0">'
        f'<skipped type="pytest.skip" message="{marker} Copilot quota exhausted"></skipped>'
        "</testcase>"
    )


def test_marker_skip_is_allowed_and_reported_with_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = _passed_case(_SMOKE_CLASS, "test_zero_token") + _marker_skipped_case(
        _SMOKE_CLASS, "test_prompt_probe"
    )
    report = _write_report(tmp_path, cases)

    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "2", "--allow-skip-marker", _MARKER]
    )

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "test_prompt_probe" in captured.out
    assert "QUOTA_SKIP:" in captured.out


def test_marker_skip_without_the_flag_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = _passed_case(_SMOKE_CLASS, "test_zero_token") + _marker_skipped_case(
        _SMOKE_CLASS, "test_prompt_probe"
    )
    report = _write_report(tmp_path, cases)

    code = assert_smoke_ran.main([str(report), "--expected-count", "2"])

    assert code == EXIT_NOT_RUN
    assert "SKIPPED" in capsys.readouterr().err


def test_unmarked_skip_still_fails_with_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = _marker_skipped_case(_SMOKE_CLASS, "test_prompt_probe") + _skipped_case(
        _SMOKE_CLASS, "test_zero_token"
    )
    report = _write_report(tmp_path, cases)

    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "2", "--allow-skip-marker", _MARKER]
    )

    assert code == EXIT_NOT_RUN
    err = capsys.readouterr().err
    assert "test_zero_token" in err
    assert "test_prompt_probe" not in err


def test_marker_must_match_the_skip_message_not_the_test_name(tmp_path: Path) -> None:
    cases = _skipped_case(_SMOKE_CLASS, "test_QUOTA_SKIP:_named")
    report = _write_report(tmp_path, cases)

    code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 1, allow_skip_marker=_MARKER)

    assert code == EXIT_NOT_RUN


def test_marker_skip_does_not_mask_a_failure(tmp_path: Path) -> None:
    cases = _marker_skipped_case(_SMOKE_CLASS, "test_a") + _failed_case(_SMOKE_CLASS, "test_b")
    report = _write_report(tmp_path, cases)

    code, message = assert_smoke_ran.evaluate(
        report, "test_cli_hook_e2e", 2, allow_skip_marker=_MARKER
    )

    assert code == EXIT_NOT_RUN
    assert "FAILED" in message


def test_count_includes_marker_skips_and_rejects_a_short_set(tmp_path: Path) -> None:
    cases = _passed_case(_SMOKE_CLASS, "test_a") + _marker_skipped_case(_SMOKE_CLASS, "test_b")
    report = _write_report(tmp_path, cases)

    ok, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 2, allow_skip_marker=_MARKER)
    short, message = assert_smoke_ran.evaluate(
        report, "test_cli_hook_e2e", 3, allow_skip_marker=_MARKER
    )

    assert ok == EXIT_OK
    assert short == EXIT_NOT_RUN
    assert "1 of 3" not in message
    assert "2 of 3" in message


def test_empty_marker_is_a_config_error(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _passed_case(_SMOKE_CLASS, "test_a"))

    with pytest.raises(assert_smoke_ran.SmokeReportError):
        assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 1, allow_skip_marker="  ")


def test_main_writes_a_step_summary_line_when_marker_skips_were_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    cases = _passed_case(_SMOKE_CLASS, "test_zero_token") + _marker_skipped_case(
        _SMOKE_CLASS, "test_prompt_probe"
    )
    report = _write_report(tmp_path, cases)

    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "2", "--allow-skip-marker", _MARKER]
    )

    assert code == EXIT_OK
    text = summary.read_text(encoding="utf-8")
    assert "quota-skipped" in text
    assert "test_prompt_probe" in text
    assert "::notice::" in capsys.readouterr().out


def test_main_writes_no_summary_when_nothing_was_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    report = _write_report(tmp_path, _passed_case(_SMOKE_CLASS, "test_zero_token"))

    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "1", "--allow-skip-marker", _MARKER]
    )

    assert code == EXIT_OK
    assert not summary.exists()
