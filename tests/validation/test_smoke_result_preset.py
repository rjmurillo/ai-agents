"""The plugin-cli-smoke preset must behave exactly like the generic flags it replaced."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.smoke_result import PRESETS, main
from tests.lib.smoke_result_env import FORK_MESSAGE, apply_green

Capsys = pytest.CaptureFixture[str]

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


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    return apply_green(monkeypatch, tmp_path)


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
