"""``--require-pass`` tests for the smoke-ran gate.

A required test must PASS: a marker skip, a miss, or a failure never satisfies
it. Report builders live in ``tests/lib/smoke_report.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.lib import smoke_report as sr

assert_smoke_ran = sr.load_gate()
EXIT_OK = assert_smoke_ran.EXIT_OK
EXIT_NOT_RUN = assert_smoke_ran.EXIT_NOT_RUN
EXIT_CONFIG = assert_smoke_ran.EXIT_CONFIG

_REQUIRED = ["test_zero_token"]


def _evaluate(report: Path, expected: int) -> tuple[int, str]:
    return assert_smoke_ran.evaluate(
        report,
        "test_cli_hook_e2e",
        expected,
        allow_skip_marker=sr.MARKER,
        require_pass=_REQUIRED,
    )


def test_require_pass_accepts_a_passed_zero_token_test(tmp_path: Path) -> None:
    report = sr.write_cases(
        tmp_path, sr.smoke_passed("test_zero_token"), sr.smoke_marker_skipped("test_prompt_probe")
    )

    assert _evaluate(report, 2)[0] == EXIT_OK


@pytest.mark.parametrize(
    ("cases", "expected", "needle"),
    [
        (
            [sr.smoke_marker_skipped("test_zero_token"), sr.smoke_passed("test_prompt_probe")],
            2,
            "must PASS",
        ),
        ([sr.smoke_passed("test_prompt_probe")], 1, "no smoke test matched required"),
        ([sr.smoke_failed("test_zero_token")], 1, "FAILED"),
    ],
    ids=["marker-skipped", "missing", "failed"],
)
def test_require_pass_rejects_a_required_test_that_did_not_pass(
    cases: list[str], expected: int, needle: str, tmp_path: Path
) -> None:
    code, message = _evaluate(sr.write_cases(tmp_path, *cases), expected)

    assert code == EXIT_NOT_RUN
    assert needle in message


def test_require_pass_blank_value_is_a_config_error(tmp_path: Path) -> None:
    report = sr.write_cases(tmp_path, sr.smoke_passed("test_a"))
    argv = [str(report), "--expected-count", "1", "--require-pass", " "]

    assert assert_smoke_ran.main(argv) == EXIT_CONFIG
