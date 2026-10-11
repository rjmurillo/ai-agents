"""Skip-marker prefix-matching tests for the smoke-ran gate.

The marker must lead the skip ``message`` attribute. Report builders live in
``tests/lib/smoke_report.py``.
"""

from __future__ import annotations

from pathlib import Path

from tests.lib import smoke_report as sr

assert_smoke_ran = sr.load_gate()
EXIT_OK = assert_smoke_ran.EXIT_OK
EXIT_NOT_RUN = assert_smoke_ran.EXIT_NOT_RUN
EXIT_CONFIG = assert_smoke_ran.EXIT_CONFIG


def _skipped_with_message(classname: str, name: str, message: str) -> str:
    return (
        f'<testcase classname="{classname}" name="{name}" time="0.0">'
        f'<skipped type="pytest.skip" message="{message}"></skipped></testcase>'
    )


def test_marker_must_be_a_prefix_of_the_skip_message(tmp_path: Path) -> None:
    """A marker quoted mid-message (for example inside a copied log) is not accepted."""
    cases = _skipped_with_message(
        sr.SMOKE_CLASS, "test_a", f"Copilot auth rejected; log said {sr.MARKER} earlier"
    )
    report = sr.write_report(tmp_path, cases)

    code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 1, allow_skip_marker=sr.MARKER)

    assert code == EXIT_NOT_RUN


def test_marker_prefix_ignores_leading_whitespace(tmp_path: Path) -> None:
    cases = _skipped_with_message(sr.SMOKE_CLASS, "test_a", f"  {sr.MARKER} quota")
    report = sr.write_report(tmp_path, cases)

    code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 1, allow_skip_marker=sr.MARKER)

    assert code == EXIT_OK


def test_marker_in_the_skip_body_only_is_not_accepted(tmp_path: Path) -> None:
    cases = (
        f'<testcase classname="{sr.SMOKE_CLASS}" name="test_a" time="0.0">'
        '<skipped type="pytest.skip" message="needs RUN_CLI_E2E=1">'
        f"{sr.MARKER} spoofed in the body</skipped></testcase>"
    )
    report = sr.write_report(tmp_path, cases)

    code, _ = assert_smoke_ran.evaluate(report, "test_cli_hook_e2e", 1, allow_skip_marker=sr.MARKER)

    assert code == EXIT_NOT_RUN
