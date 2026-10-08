"""Quota-skip counting, all-skipped, and read-error tests for the smoke-ran gate.

Complements ``test_assert_smoke_ran.py``; report builders live in
``tests/lib/smoke_report.py``.
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


def test_all_cases_marker_skipped_without_require_pass_passes_and_reports_zero_ran(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = _marker_skipped_case(_SMOKE_CLASS, "test_a") + _marker_skipped_case(
        _SMOKE_CLASS, "test_b"
    )
    report = _write_report(tmp_path, cases)

    verdict = assert_smoke_ran.judge(report, "test_cli_hook_e2e", 2, allow_skip_marker=_MARKER)
    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "2", "--allow-skip-marker", _MARKER]
    )

    assert verdict.exit_code == EXIT_OK
    assert verdict.quota_skipped == 2
    assert verdict.message.startswith("0 smoke test(s) ran and passed.")
    assert code == EXIT_OK
    assert "0 smoke test(s) ran" in capsys.readouterr().out


def test_all_cases_marker_skipped_with_require_pass_fails(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _marker_skipped_case(_SMOKE_CLASS, "test_zero_token"))

    code, message = assert_smoke_ran.evaluate(
        report, "test_cli_hook_e2e", 1, _MARKER, ["test_zero_token"]
    )

    assert code == EXIT_NOT_RUN
    assert "must PASS" in message


@pytest.mark.parametrize("count", [0, -1])
def test_expected_count_below_one_is_a_config_error(tmp_path: Path, count: int) -> None:
    report = _write_report(tmp_path, _passed_case(_SMOKE_CLASS, "test_a"))

    with pytest.raises(assert_smoke_ran.SmokeReportError, match="must be positive"):
        assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", count)


def test_main_exits_two_for_expected_count_below_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _write_report(tmp_path, _passed_case(_SMOKE_CLASS, "test_a"))

    code = assert_smoke_ran.main([str(report), "--expected-count", "0"])

    assert code == EXIT_CONFIG
    assert "must be positive" in capsys.readouterr().err


def test_raises_when_report_is_unreadable_but_present(tmp_path: Path) -> None:
    # A directory exists but cannot be read as a file: OSError, not FileNotFoundError.
    with pytest.raises(assert_smoke_ran.SmokeReportError, match="could not be read"):
        assert_smoke_ran.evaluate(tmp_path, "test_cli_hook_e2e")


def test_skip_count_file_records_the_marker_skip_count(tmp_path: Path) -> None:
    cases = _passed_case(_SMOKE_CLASS, "test_a") + _marker_skipped_case(_SMOKE_CLASS, "test_b")
    report = _write_report(tmp_path, cases)
    count_file = tmp_path / "quota-skips.txt"

    for _ in range(2):  # two gate steps of one leg append to the same file
        code = assert_smoke_ran.main(
            [
                str(report),
                "--expected-count",
                "2",
                "--allow-skip-marker",
                _MARKER,
                "--skip-count-file",
                str(count_file),
            ]
        )
        assert code == EXIT_OK

    assert count_file.read_text(encoding="utf-8").split() == ["1", "1"]


def test_skip_count_file_records_zero_when_nothing_skipped(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _passed_case(_SMOKE_CLASS, "test_a"))
    count_file = tmp_path / "quota-skips.txt"

    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "1", "--skip-count-file", str(count_file)]
    )

    assert code == EXIT_OK
    assert count_file.read_text(encoding="utf-8") == "0\n"


def test_skip_count_file_is_not_written_when_the_gate_fails(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _skipped_case(_SMOKE_CLASS, "test_a"))
    count_file = tmp_path / "quota-skips.txt"

    code = assert_smoke_ran.main(
        [str(report), "--expected-count", "1", "--skip-count-file", str(count_file)]
    )

    assert code == EXIT_NOT_RUN
    assert not count_file.exists()
