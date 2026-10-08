"""The plugin-cli-smoke preset must behave exactly like the generic flags it replaced."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.smoke_result import PRESETS, main

Capsys = pytest.CaptureFixture[str]

FORK_MESSAGE = (
    "Untrusted context: this change touches smoke paths from a fork pull request or a "
    "non-default ref. Forks get no secrets, so the CLI smoke cannot run. A maintainer "
    "must rerun it from a same-repo branch."
)
COUNT_MESSAGE = (
    "CLI smoke passed with {count} prompt checks quota-skipped. Load tests passed on every leg."
)
EXPECTED_ARGV = [
    "--check", "CHANGES_RESULT", "success", "Smoke path filter result: {value}",
    "--skip-when", "RUN", "false",
    "--skip-message", "No smoke path changed; CLI smoke legs skipped.",
    "--skippable-check", "AUTHORIZE_RESULT", "success", "Trusted-context gate result: {value}",
    "--guarded-check", "AUTHORIZE_RESULT", "success", "TRUSTED", "true", FORK_MESSAGE,
    "--skippable-check", "SMOKE_RESULT", "success", "Claude and Copilot smoke result: {value}",
    "--skippable-check", "CODEX_RESULT", "success", "Codex smoke result: {value}",
    "--success-message", "CLI smoke passed for Claude, Copilot, and Codex on all platforms.",
    "--count-dir", "quota-skips",
    "--count-message", COUNT_MESSAGE,
]  # fmt: skip

GREEN = {
    "RUN": "true",
    "CHANGES_RESULT": "success",
    "AUTHORIZE_RESULT": "success",
    "TRUSTED": "true",
    "SMOKE_RESULT": "success",
    "CODEX_RESULT": "success",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    for key, value in GREEN.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_preset_holds_the_original_argv() -> None:
    assert list(PRESETS["plugin-cli-smoke"]) == EXPECTED_ARGV


def test_preset_combines_with_generic_flags(env: pytest.MonkeyPatch, capsys: Capsys) -> None:
    env.setenv("EXTRA", "bad")
    assert main(["--preset", "plugin-cli-smoke", "--check", "EXTRA", "ok", "extra: {value}"]) == 1
    assert "::error::extra: bad" in capsys.readouterr().out


def test_unknown_preset_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--preset", "nope"])
    assert exc.value.code == 2


def test_preset_and_expanded_argv_agree(env: pytest.MonkeyPatch, capsys: Capsys) -> None:
    assert main(["--preset", "plugin-cli-smoke"]) == 0
    preset_out = capsys.readouterr().out
    assert main(EXPECTED_ARGV) == 0
    assert capsys.readouterr().out == preset_out


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
