#!/usr/bin/env python3
"""Tests for the smoke-ran gate (issue #2231 item 4).

The gate proves the real-CLI smoke actually ran instead of skipping silently.
Each test builds a JUnit XML report (the format pytest's ``--junitxml`` writes)
and asserts the gate's exit code and message, covering positive, negative, and
edge cases plus the CLI argv path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.lib.smoke_report import (
    MARKER as _MARKER,
)
from tests.lib.smoke_report import (
    SMOKE_CLASS as _SMOKE_CLASS,
)
from tests.lib.smoke_report import (
    failed_case as _failed_case,
)
from tests.lib.smoke_report import (
    load_gate,
)
from tests.lib.smoke_report import (
    marker_skipped_case as _marker_skipped_case,
)
from tests.lib.smoke_report import (
    passed_case as _passed_case,
)
from tests.lib.smoke_report import (
    skipped_case as _skipped_case,
)
from tests.lib.smoke_report import (
    write_report as _write_report,
)

assert_smoke_ran = load_gate()

EXIT_OK = assert_smoke_ran.EXIT_OK
EXIT_NOT_RUN = assert_smoke_ran.EXIT_NOT_RUN
EXIT_CONFIG = assert_smoke_ran.EXIT_CONFIG

_OTHER_CLASS = "tests.unit.test_helpers"


def test_returns_ok_when_smoke_case_passed(tmp_path: Path) -> None:
    cases = _passed_case(_SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves") + _passed_case(
        _SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves"
    )
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
    cases = _passed_case(_SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves") + _passed_case(
        _SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves"
    )
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
    cases = _passed_case(_SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves") + _passed_case(
        _SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves"
    )
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


def _skipped_with_message(classname: str, name: str, message: str) -> str:
    return (
        f'<testcase classname="{classname}" name="{name}" time="0.0">'
        f'<skipped type="pytest.skip" message="{message}"></skipped></testcase>'
    )


def test_marker_must_be_a_prefix_of_the_skip_message(tmp_path: Path) -> None:
    """A marker quoted mid-message (for example inside a copied log) is not accepted."""
    cases = _skipped_with_message(
        _SMOKE_CLASS, "test_a", f"Copilot auth rejected; log said {_MARKER} earlier"
    )
    report = _write_report(tmp_path, cases)

    code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 1, allow_skip_marker=_MARKER)

    assert code == EXIT_NOT_RUN


def test_marker_prefix_ignores_leading_whitespace(tmp_path: Path) -> None:
    cases = _skipped_with_message(_SMOKE_CLASS, "test_a", f"  {_MARKER} quota")
    report = _write_report(tmp_path, cases)

    code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 1, allow_skip_marker=_MARKER)

    assert code == EXIT_OK


def test_marker_in_the_skip_body_only_is_not_accepted(tmp_path: Path) -> None:
    cases = (
        f'<testcase classname="{_SMOKE_CLASS}" name="test_a" time="0.0">'
        '<skipped type="pytest.skip" message="needs RUN_CLI_E2E=1">'
        f"{_MARKER} spoofed in the body</skipped></testcase>"
    )
    report = _write_report(tmp_path, cases)

    code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 1, allow_skip_marker=_MARKER)

    assert code == EXIT_NOT_RUN


def test_require_pass_accepts_a_passed_zero_token_test(tmp_path: Path) -> None:
    cases = _passed_case(_SMOKE_CLASS, "test_zero_token") + _marker_skipped_case(
        _SMOKE_CLASS, "test_prompt_probe"
    )
    report = _write_report(tmp_path, cases)

    code, _ = assert_smoke_ran.evaluate(
        report,
        "test_cli_hook_e2e",
        2,
        allow_skip_marker=_MARKER,
        require_pass=["test_zero_token"],
    )

    assert code == EXIT_OK


def test_require_pass_rejects_a_marker_skipped_required_test(tmp_path: Path) -> None:
    cases = _marker_skipped_case(_SMOKE_CLASS, "test_zero_token") + _passed_case(
        _SMOKE_CLASS, "test_prompt_probe"
    )
    report = _write_report(tmp_path, cases)

    code, message = assert_smoke_ran.evaluate(
        report,
        "test_cli_hook_e2e",
        2,
        allow_skip_marker=_MARKER,
        require_pass=["test_zero_token"],
    )

    assert code == EXIT_NOT_RUN
    assert "test_zero_token" in message
    assert "must PASS" in message


def test_require_pass_rejects_a_missing_required_test(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _passed_case(_SMOKE_CLASS, "test_prompt_probe"))

    code, message = assert_smoke_ran.evaluate(
        report, "test_cli_hook_e2e", 1, require_pass=["test_zero_token"]
    )

    assert code == EXIT_NOT_RUN
    assert "no smoke test matched required" in message


def test_require_pass_rejects_a_failed_required_test(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _failed_case(_SMOKE_CLASS, "test_zero_token"))

    code, _ = assert_smoke_ran.evaluate(
        report, "test_cli_hook_e2e", 1, require_pass=["test_zero_token"]
    )

    assert code == EXIT_NOT_RUN


def test_require_pass_is_repeatable_on_the_command_line(tmp_path: Path) -> None:
    cases = _passed_case(_SMOKE_CLASS, "test_a") + _marker_skipped_case(_SMOKE_CLASS, "test_b")
    report = _write_report(tmp_path, cases)

    ok = assert_smoke_ran.main(
        [
            str(report),
            "--expected-count",
            "2",
            "--allow-skip-marker",
            _MARKER,
            "--require-pass",
            "test_a",
        ]
    )
    bad = assert_smoke_ran.main(
        [
            str(report),
            "--expected-count",
            "2",
            "--allow-skip-marker",
            _MARKER,
            "--require-pass",
            "test_a",
            "--require-pass",
            "test_b",
        ]
    )

    assert ok == EXIT_OK
    assert bad == EXIT_NOT_RUN


def test_require_pass_blank_value_is_a_config_error(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _passed_case(_SMOKE_CLASS, "test_a"))

    code = assert_smoke_ran.main([str(report), "--expected-count", "1", "--require-pass", " "])

    assert code == EXIT_CONFIG
