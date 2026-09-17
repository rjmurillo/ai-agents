"""Tests for the Codex CLI transport, the codex/subscription cell.

Offline: no CLI is launched. The Codex binary is not installed in this
repository's container, so these cover the argv shape read from the
openai/codex source and every refusal path, not a live run.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.eval._cli_transport_test_support import (
    MESSAGES,
    Recorder,
    _codex_cli,
    install_runner,
    write_last_message,
)

# --- Codex CLI ----------------------------------------------------------


@pytest.fixture
def codex_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv(_codex_cli.UNVERIFIED_MODEL_ENV, "1")
    monkeypatch.setattr(_codex_cli, "_init_git_repository", lambda sandbox: None)
    for name in _codex_cli._BLOCKED_BILLING_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_codex_cli_returns_the_final_message_file(
    codex_env: pytest.MonkeyPatch,
) -> None:
    install_runner(codex_env, Recorder(on_call=write_last_message("PONG\n")))

    answer = _codex_cli._CodexCLIProvider().complete(messages=MESSAGES, model="gpt-5.6")

    assert answer == "PONG"


def test_codex_cli_argv_uses_exec_with_a_read_only_sandbox(
    codex_env: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder(on_call=write_last_message("PONG"))
    install_runner(codex_env, recorder)

    _codex_cli._CodexCLIProvider().complete(messages=MESSAGES, model="gpt-5.6")

    argv = recorder.argv
    assert argv[:2] == ["codex", "exec"]
    assert argv[argv.index("--model") + 1] == "gpt-5.6"
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in argv
    assert "--ignore-user-config" in argv
    assert argv[-1].startswith("{")


def test_codex_cli_gets_devnull_not_the_parent_stdin(
    codex_env: pytest.MonkeyPatch,
) -> None:
    """Codex takes the prompt positionally; inherited stdin could block."""
    recorder = Recorder(on_call=write_last_message("PONG"))
    install_runner(codex_env, recorder)

    _codex_cli._CodexCLIProvider().complete(messages=MESSAGES, model="gpt-5.6")

    assert "input" not in recorder.calls[-1]
    assert recorder.calls[-1]["stdin"] is subprocess.DEVNULL


def test_codex_cli_strips_metered_credentials_from_the_child(
    codex_env: pytest.MonkeyPatch,
) -> None:
    codex_env.setenv("CODEX_API_KEY", "codex-metered")
    codex_env.setenv("OPENAI_API_KEY", "sk-metered")
    codex_env.setenv("CODEX_ACCESS_TOKEN", "plan-token")
    recorder = Recorder(on_call=write_last_message("PONG"))
    install_runner(codex_env, recorder)

    _codex_cli._CodexCLIProvider().complete(messages=MESSAGES, model="gpt-5.6")

    env = recorder.calls[-1]["env"]
    assert "CODEX_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert env["CODEX_ACCESS_TOKEN"] == "plan-token"


def test_codex_cli_refuses_to_score_an_unattributed_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_codex_cli.UNVERIFIED_MODEL_ENV, raising=False)
    recorder = Recorder(on_call=write_last_message("PONG"))
    install_runner(monkeypatch, recorder)

    with pytest.raises(RuntimeError, match=_codex_cli.UNVERIFIED_MODEL_ENV):
        _codex_cli._CodexCLIProvider().complete(messages=MESSAGES, model="gpt-5.6")

    assert recorder.calls == []


@pytest.mark.parametrize("value", ["", "0", "no", "off", " "])
def test_codex_cli_optin_fails_closed_on_a_non_affirmative_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(_codex_cli.UNVERIFIED_MODEL_ENV, value)

    with pytest.raises(RuntimeError, match="cannot confirm which model"):
        _codex_cli._CodexCLIProvider().complete(messages=MESSAGES, model="gpt-5.6")


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_codex_cli_optin_accepts_an_affirmative_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(_codex_cli.UNVERIFIED_MODEL_ENV, value)
    monkeypatch.setattr(_codex_cli, "_init_git_repository", lambda sandbox: None)
    install_runner(monkeypatch, Recorder(on_call=write_last_message("PONG")))

    assert (
        _codex_cli._CodexCLIProvider().complete(messages=MESSAGES, model="gpt-5.6")
        == "PONG"
    )


def test_codex_cli_never_reports_a_model_fingerprint(
    codex_env: pytest.MonkeyPatch,
) -> None:
    install_runner(codex_env, Recorder(on_call=write_last_message("PONG")))
    provider = _codex_cli._CodexCLIProvider()

    provider.complete(messages=MESSAGES, model="gpt-5.6")

    assert provider.system_fingerprint is None


def test_codex_cli_reports_no_choices_when_the_file_is_missing(
    codex_env: pytest.MonkeyPatch,
) -> None:
    install_runner(codex_env, Recorder())

    with pytest.raises(RuntimeError, match="no choices"):
        _codex_cli._CodexCLIProvider().complete(messages=MESSAGES, model="gpt-5.6")


def test_codex_cli_reports_no_choices_when_the_file_is_blank(
    codex_env: pytest.MonkeyPatch,
) -> None:
    install_runner(codex_env, Recorder(on_call=write_last_message("   \n")))

    with pytest.raises(RuntimeError, match="no choices"):
        _codex_cli._CodexCLIProvider().complete(messages=MESSAGES, model="gpt-5.6")


def test_codex_cli_reports_a_failed_git_init_without_process_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise OSError("git: cannot execute /private/path")

    monkeypatch.setattr(_codex_cli.subprocess, "run", _boom)

    with pytest.raises(RuntimeError) as excinfo:
        _codex_cli._init_git_repository(tmp_path)

    assert "git_init_failed" in str(excinfo.value)
    assert "/private/path" not in str(excinfo.value)
