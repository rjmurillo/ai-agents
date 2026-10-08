"""Outcomes of the plugin-cli-smoke preset: success, quota skips, skips, forks, failed legs."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.smoke_result import main
from tests.lib.smoke_result_env import FORK_MESSAGE, apply_green

Capsys = pytest.CaptureFixture[str]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    return apply_green(monkeypatch, tmp_path)


def test_success_prints_the_success_message(env: pytest.MonkeyPatch, capsys: Capsys) -> None:
    assert main(["--preset", "plugin-cli-smoke"]) == 0
    assert capsys.readouterr().out.strip() == (
        "CLI smoke passed for Claude, Copilot, and Codex on all platforms."
    )


def test_quota_skips_print_the_count_notice(
    env: pytest.MonkeyPatch, capsys: Capsys, tmp_path: Path
) -> None:
    (tmp_path / "quota-skips").mkdir()
    (tmp_path / "quota-skips" / "n.txt").write_text("2\n", encoding="utf-8")
    assert main(["--preset", "plugin-cli-smoke"]) == 0
    assert capsys.readouterr().out.strip() == (
        "::notice::CLI smoke passed with 2 prompt checks quota-skipped. "
        "Load tests passed on every leg."
    )


def test_run_false_skips_and_ignores_leg_results(env: pytest.MonkeyPatch, capsys: Capsys) -> None:
    env.setenv("RUN", "false")
    env.setenv("SMOKE_RESULT", "skipped")
    env.setenv("AUTHORIZE_RESULT", "skipped")
    assert main(["--preset", "plugin-cli-smoke"]) == 0
    assert capsys.readouterr().out.strip() == "No smoke path changed; CLI smoke legs skipped."


def test_run_false_still_fails_a_broken_path_filter(
    env: pytest.MonkeyPatch, capsys: Capsys
) -> None:
    env.setenv("RUN", "false")
    env.setenv("CHANGES_RESULT", "failure")
    assert main(["--preset", "plugin-cli-smoke"]) == 1
    assert "::error::Smoke path filter result: failure" in capsys.readouterr().out


def test_untrusted_context_names_the_fork(env: pytest.MonkeyPatch, capsys: Capsys) -> None:
    env.setenv("TRUSTED", "false")
    env.setenv("SMOKE_RESULT", "skipped")
    env.setenv("CODEX_RESULT", "skipped")
    assert main(["--preset", "plugin-cli-smoke"]) == 1
    out = capsys.readouterr().out
    assert f"::error::{FORK_MESSAGE}" in out


def test_guard_quiet_when_authorize_failed(env: pytest.MonkeyPatch, capsys: Capsys) -> None:
    env.setenv("AUTHORIZE_RESULT", "failure")
    env.setenv("TRUSTED", "false")
    assert main(["--preset", "plugin-cli-smoke"]) == 1
    assert "Untrusted context" not in capsys.readouterr().out


@pytest.mark.parametrize("leg", ["SMOKE_RESULT", "CODEX_RESULT"])
def test_failed_leg_exits_1_with_hint(env: pytest.MonkeyPatch, capsys: Capsys, leg: str) -> None:
    env.setenv(leg, "failure")
    assert main(["--preset", "plugin-cli-smoke"]) == 1
    out = capsys.readouterr().out
    assert f"[{leg}=failure]" in out
