"""CLI argv, exit-code, and step-summary tests for the smoke-ran gate.

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

_OTHER_CLASS = "tests.unit.test_helpers"


def test_main_exits_zero_when_smoke_ran(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cases = sr.passed_case(
        sr.SMOKE_CLASS, "test_copilot_vendor_install_hook_resolves"
    ) + sr.passed_case(sr.SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves")
    report = sr.write_report(
        tmp_path,
        cases,
    )

    code = assert_smoke_ran.main([str(report)])

    assert code == EXIT_OK
    assert "smoke gate OK" in capsys.readouterr().out


def test_main_exits_one_when_smoke_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = sr.write_report(
        tmp_path, sr.skipped_case(sr.SMOKE_CLASS, "test_claude_plugin_dir_hook_resolves")
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
    report = sr.write_report(tmp_path, sr.passed_case("custom.module", "test_my_smoke"))

    code = assert_smoke_ran.main(
        [str(report), "--smoke-substr", "test_my_smoke", "--expected-count", "1"]
    )

    assert code == EXIT_OK


def test_main_writes_a_step_summary_line_when_marker_skips_were_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    cases = sr.passed_case(sr.SMOKE_CLASS, "test_zero_token") + sr.marker_skipped_case(
        sr.SMOKE_CLASS, "test_prompt_probe"
    )
    report = sr.write_report(tmp_path, cases)

    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "2", "--allow-skip-marker", sr.MARKER]
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
    report = sr.write_report(tmp_path, sr.passed_case(sr.SMOKE_CLASS, "test_zero_token"))

    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "1", "--allow-skip-marker", sr.MARKER]
    )

    assert code == EXIT_OK
    assert not summary.exists()


def test_require_pass_is_repeatable_on_the_command_line(tmp_path: Path) -> None:
    cases = sr.passed_case(sr.SMOKE_CLASS, "test_a") + sr.marker_skipped_case(
        sr.SMOKE_CLASS, "test_b"
    )
    report = sr.write_report(tmp_path, cases)

    ok = assert_smoke_ran.main(
        [
            str(report),
            "--expected-count",
            "2",
            "--allow-skip-marker",
            sr.MARKER,
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
            sr.MARKER,
            "--require-pass",
            "test_a",
            "--require-pass",
            "test_b",
        ]
    )

    assert ok == EXIT_OK
    assert bad == EXIT_NOT_RUN
