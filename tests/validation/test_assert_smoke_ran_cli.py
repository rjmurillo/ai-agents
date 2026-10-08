"""CLI argv, exit-code, and step-summary tests for the smoke-ran gate.

Report builders live in ``tests/lib/smoke_report.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.lib import smoke_report as sr

assert_smoke_ran = sr.load_gate()
EXIT_OK = assert_smoke_ran.EXIT_OK
EXIT_NOT_RUN = assert_smoke_ran.EXIT_NOT_RUN
EXIT_CONFIG = assert_smoke_ran.EXIT_CONFIG

Capsys = pytest.CaptureFixture[str]
_TWO_CASES = ["--expected-count", "2", "--allow-skip-marker", sr.MARKER]


@pytest.mark.parametrize(
    ("make_report", "expected_code", "stream", "expected_text"),
    [
        (
            lambda d: sr.write_cases(d, sr.smoke_passed("test_a"), sr.smoke_passed("test_b")),
            EXIT_OK,
            "out",
            "smoke gate OK",
        ),
        (lambda d: sr.write_cases(d, sr.smoke_skipped("test_a")), EXIT_NOT_RUN, "err", "::error::"),
        (lambda d: d / "absent.xml", EXIT_CONFIG, "err", "::error::"),
    ],
    ids=["ran", "skipped", "report-missing"],
)
def test_main_reports_each_outcome_with_its_exit_code(
    make_report: Callable[[Path], Path],
    expected_code: int,
    stream: str,
    expected_text: str,
    tmp_path: Path,
    capsys: Capsys,
) -> None:
    report = make_report(tmp_path)

    assert assert_smoke_ran.main([str(report)]) == expected_code
    assert expected_text in getattr(capsys.readouterr(), stream)


def test_main_honors_custom_smoke_substr(tmp_path: Path) -> None:
    report = sr.write_cases(tmp_path, sr.passed_case("custom.module", "test_my_smoke"))
    argv = [str(report), "--smoke-substr", "test_my_smoke", "--expected-count", "1"]

    assert assert_smoke_ran.main(argv) == EXIT_OK


@pytest.mark.parametrize(
    ("required", "expected_code"),
    [(["test_a"], EXIT_OK), (["test_a", "test_b"], EXIT_NOT_RUN)],
    ids=["passed-only", "includes-marker-skipped"],
)
def test_require_pass_is_repeatable_on_the_command_line(
    required: list[str], expected_code: int, tmp_path: Path
) -> None:
    report = sr.write_cases(tmp_path, sr.smoke_passed("test_a"), sr.smoke_marker_skipped("test_b"))
    flags = [flag for name in required for flag in ("--require-pass", name)]

    assert assert_smoke_ran.main([str(report), *_TWO_CASES, *flags]) == expected_code
