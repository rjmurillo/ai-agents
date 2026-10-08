"""Tests for the quota-skip report of a passing smoke leg (REQ-047 D25, D26).

After ``assert_smoke_ran.py`` passes, ``smoke_quota_report.py`` keeps the
quota skips visible: a notice, a job summary line, and a per-leg count file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.lib import smoke_report as sr

report_script = sr.load_script("smoke_quota_report")

Capsys = pytest.CaptureFixture[str]
_MARKER_ARGS = ["--allow-skip-marker", sr.MARKER]


def _report_with_one_quota_skip(tmp_path: Path) -> Path:
    return sr.write_cases(
        tmp_path, sr.smoke_passed("test_zero_token"), sr.smoke_marker_skipped("test_prompt_probe")
    )


def test_notice_summary_and_count_name_the_quota_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    count_file = tmp_path / "quota-skips.txt"
    argv = [str(_report_with_one_quota_skip(tmp_path)), *_MARKER_ARGS]

    assert report_script.main([*argv, "--skip-count-file", str(count_file)]) == 0

    out = capsys.readouterr().out
    assert out.startswith("::notice::smoke gate: 1 best-effort test(s) quota-skipped")
    assert "test_prompt_probe" in out
    assert "quota-skipped" in summary.read_text(encoding="utf-8")
    assert count_file.read_text(encoding="utf-8") == "1\n"


def test_nothing_skipped_writes_a_zero_and_no_notice_or_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    count_file = tmp_path / "quota-skips.txt"
    report = sr.write_cases(tmp_path, sr.smoke_passed("test_a"))

    argv = [str(report), *_MARKER_ARGS, "--skip-count-file", str(count_file)]
    assert report_script.main(argv) == 0

    assert capsys.readouterr().out == ""
    assert not summary.exists()
    assert count_file.read_text(encoding="utf-8") == "0\n"


def test_count_file_is_appended_by_each_step_of_a_leg(tmp_path: Path) -> None:
    count_file = tmp_path / "quota-skips.txt"
    argv = [str(_report_with_one_quota_skip(tmp_path)), *_MARKER_ARGS]

    for _ in range(2):
        report_script.main([*argv, "--skip-count-file", str(count_file)])

    assert count_file.read_text(encoding="utf-8").split() == ["1", "1"]


@pytest.mark.parametrize(
    "case",
    [
        sr.smoke_skipped("test_unmarked"),
        sr.skipped_case("tests.other", "test_x"),
        sr.marker_skipped_case("tests.other", "test_x"),
    ],
    ids=["unmarked-skip", "unmarked-other-module", "marker-outside-the-smoke"],
)
def test_only_marker_skips_inside_the_smoke_are_counted(case: str, tmp_path: Path) -> None:
    report = sr.write_cases(tmp_path, case)

    assert report_script.quota_skips(report, "test_cli_hook_e2e", sr.MARKER) == []


@pytest.mark.parametrize("kind", ["missing", "doctype", "malformed"])
def test_unreadable_or_hostile_report_exits_two(kind: str, tmp_path: Path, capsys: Capsys) -> None:
    report = tmp_path / "report.xml"
    texts = {"doctype": '<!DOCTYPE x [<!ENTITY a "b">]><testsuite/>', "malformed": "<testsuite"}
    if kind != "missing":
        report.write_text(texts[kind], encoding="utf-8")

    assert report_script.main([str(report), *_MARKER_ARGS]) == report_script.EXIT_CONFIG
    assert "::error::smoke quota report" in capsys.readouterr().err


def test_reason_line_breaks_cannot_forge_a_workflow_command(tmp_path: Path, capsys: Capsys) -> None:
    """CWE-117: a CR or LF char reference in a reason must not start a new line."""
    case = (
        f'<testcase classname="{sr.SMOKE_CLASS}" name="t">'
        f'<skipped message="{sr.MARKER} quota&#10;::error::forged&#13;::warning::x"></skipped>'
        "</testcase>"
    )
    report = sr.write_cases(tmp_path, case)

    assert report_script.main([str(report), *_MARKER_ARGS]) == 0

    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert "\r" not in out
    assert "::notice::" in out
