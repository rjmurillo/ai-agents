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

    verdict = assert_smoke_ran.judge(report, _SMOKE, 2, allow_skip_marker=sr.MARKER)
    code = assert_smoke_ran.main([str(report), "--expected-count", "2", *_ALLOW])

    assert (verdict.exit_code, verdict.quota_skipped, code) == (EXIT_OK, 2, EXIT_OK)
    assert verdict.message.startswith("0 smoke test(s) ran and passed.")
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


@pytest.mark.parametrize(
    ("cases", "flags", "runs", "expected_code", "expected_file"),
    [
        (
            [sr.smoke_passed("a"), sr.smoke_marker_skipped("b")],
            ["2", *_ALLOW],
            2,
            EXIT_OK,
            "1\n1\n",
        ),
        ([sr.smoke_passed("a")], ["1"], 1, EXIT_OK, "0\n"),
        ([sr.smoke_skipped("a")], ["1"], 1, EXIT_NOT_RUN, None),
    ],
    ids=["records-the-skip-count", "records-zero", "not-written-on-failure"],
)
def test_skip_count_file_follows_the_gate_outcome(
    cases: list[str],
    flags: list[str],
    runs: int,
    expected_code: int,
    expected_file: str | None,
    tmp_path: Path,
) -> None:
    report = sr.write_cases(tmp_path, *cases)
    count_file = tmp_path / "quota-skips.txt"
    count, *allow = flags
    argv = [str(report), "--expected-count", count, *allow, "--skip-count-file", str(count_file)]

    # Two gate steps of one leg append to the same file.
    codes = {assert_smoke_ran.main(argv) for _ in range(runs)}

    assert codes == {expected_code}
    if expected_file is None:
        assert not count_file.exists()
    else:
        assert count_file.read_text(encoding="utf-8") == expected_file
