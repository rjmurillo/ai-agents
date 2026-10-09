"""Outcomes of the plugin-cli-smoke preset: success, quota skips, skips, forks, failed legs."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.smoke_result import main
from tests.lib.smoke_result_env import FORK_MESSAGE, apply_green

Capsys = pytest.CaptureFixture[str]

SUCCESS = "CLI smoke passed for Claude, Copilot, and Codex on all platforms."
QUOTA_NOTICE = (
    "::notice::CLI smoke passed with 2 prompt checks quota-skipped. Load tests passed on every leg."
)
NO_CHANGE = "No smoke path changed; CLI smoke legs skipped."


@pytest.fixture
def run_preset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: Capsys):
    """Run the preset with every job green except the given overrides."""
    apply_green(monkeypatch, tmp_path)

    def _run(**overrides: str) -> tuple[int, str]:
        for key, value in overrides.items():
            monkeypatch.setenv(key, value)
        rc = main(["--preset", "plugin-cli-smoke"])
        return rc, capsys.readouterr().out

    return _run


@pytest.mark.parametrize(
    ("overrides", "rc", "out"),
    [
        ({}, 0, SUCCESS),
        ({"RUN": "false", "SMOKE_RESULT": "skipped", "AUTHORIZE_RESULT": "skipped"}, 0, NO_CHANGE),
    ],
    ids=["all-green", "no-smoke-path"],
)
def test_passing_outcomes_print_one_line(
    run_preset, overrides: dict[str, str], rc: int, out: str
) -> None:
    code, text = run_preset(**overrides)
    assert (code, text.strip()) == (rc, out)


def test_quota_skips_print_the_count_notice(run_preset, tmp_path: Path) -> None:
    (tmp_path / "quota-skips").mkdir()
    (tmp_path / "quota-skips" / "n.txt").write_text("2\n", encoding="utf-8")
    assert run_preset() == (0, QUOTA_NOTICE + "\n")


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"RUN": "false", "CHANGES_RESULT": "failure"},
            "::error::Smoke path filter result: failure",
        ),
        (
            {"TRUSTED": "false", "SMOKE_RESULT": "skipped", "CODEX_RESULT": "skipped"},
            f"::error::{FORK_MESSAGE}",
        ),
        ({"SMOKE_RESULT": "failure"}, "[SMOKE_RESULT=failure]"),
        ({"CODEX_RESULT": "failure"}, "[CODEX_RESULT=failure]"),
    ],
    ids=["broken-filter", "fork", "smoke-leg-failed", "codex-leg-failed"],
)
def test_failing_outcomes_exit_1_and_name_the_cause(
    run_preset, overrides: dict[str, str], expected: str
) -> None:
    code, text = run_preset(**overrides)
    assert code == 1
    assert expected in text


def test_fork_message_stays_quiet_when_authorize_failed(run_preset) -> None:
    code, text = run_preset(AUTHORIZE_RESULT="failure", TRUSTED="false")
    assert code == 1
    assert "Untrusted context" not in text
