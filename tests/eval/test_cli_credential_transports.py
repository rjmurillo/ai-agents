"""The shared credential order, exercised through each real transport.

One rig per CLI fakes only the process boundary. The credential order, the
child environment, and the recorded step are the production code. Every case
runs against all three transports, so the order cannot drift per CLI.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tests.eval._cli_transport_test_support import (
    MESSAGES,
    Recorder,
    _claude_cli,
    _codex_cli,
    claude_payload,
    install_runner,
)
from tests.eval._credential_test_support import (
    _cli_credentials as creds,
)
from tests.eval._credential_test_support import (
    _copilot_cli,
    set_sources,
)

DISK_VALUE = "disk-" + "D" * 10
ENV_VALUE = "env-" + "E" * 10
DOTENV_VALUE = "dotenv-" + "F" * 10
BILLING_ENV = {
    "ANTHROPIC_API_KEY": "sk-ant-" + "A" * 10,
    "ANTHROPIC_AUTH_TOKEN": "auth-" + "B" * 10,
    "OPENAI_API_KEY": "sk-" + "O" * 10,
    "CODEX_API_KEY": "codex-" + "C" * 10,
    "OPENAI_BASE_URL": "https://billing.invalid",
    "COPILOT_PROVIDER_API_KEY": "byok-" + "P" * 10,
}


@dataclass
class Rig:
    """One transport: how to run it once and what it names its credential."""

    name: str
    module: str
    token_env: str
    run: Callable[[pytest.MonkeyPatch], dict[str, Any]]
    disk_text: str = DISK_VALUE
    extra: dict[str, Any] = field(default_factory=dict)


def _run_claude(mp: pytest.MonkeyPatch) -> dict[str, Any]:
    recorder = Recorder(stdout=claude_payload())
    install_runner(mp, recorder)
    _claude_cli._ClaudeCLIProvider().complete(messages=MESSAGES, model="claude-haiku-4-5-20251001")
    return {"env": recorder.calls[-1]["env"]}


def _run_codex(mp: pytest.MonkeyPatch) -> dict[str, Any]:
    mp.setenv(_codex_cli.UNVERIFIED_MODEL_ENV, "1")
    mp.setattr(_codex_cli, "_init_git_repository", lambda sandbox: None)
    seen: dict[str, Any] = {}

    def on_call(record: dict[str, Any]) -> None:
        argv = record["argv"]
        Path(argv[argv.index("--output-last-message") + 1]).write_text("PONG", encoding="utf-8")
        home = record["env"].get("CODEX_HOME")
        auth = Path(home) / "auth.json" if home else None
        if auth is not None and auth.exists():
            seen["auth_text"] = auth.read_text(encoding="utf-8")
            seen["auth_mode"] = stat.S_IMODE(auth.stat().st_mode)
            seen["home_mode"] = stat.S_IMODE(auth.parent.stat().st_mode)

    recorder = Recorder(on_call=on_call)
    install_runner(mp, recorder)
    _codex_cli._CodexCLIProvider().complete(messages=MESSAGES, model="gpt-5.6")
    return {"env": recorder.calls[-1]["env"], **seen}


class _Completed:
    returncode = 0
    stdout = "PONG\n"
    stderr = ""


def _run_copilot(mp: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_run(argv: list[str], prompt: str, **kwargs: Any) -> Any:
        seen["env"] = kwargs["env"]
        return _Completed()

    mp.setattr(_copilot_cli, "run_acp_completion", fake_run)
    mp.setenv("COPILOT_SESSION_STATE_DIR", str(Path(tempfile.gettempdir()) / "__missing_state__"))
    mp.setenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", "1")
    _copilot_cli._CopilotCLIProvider().complete(messages=MESSAGES, model="claude-opus-5")
    return seen


RIGS = {
    "claude": Rig("claude", "_claude_cli", "CLAUDE_CODE_OAUTH_TOKEN", _run_claude),
    "codex": Rig(
        "codex",
        "_codex_cli",
        "CODEX_ACCESS_TOKEN",
        _run_codex,
        disk_text=json.dumps({"tokens": {"access_token": DISK_VALUE}}),
    ),
    "copilot": Rig("copilot", "_copilot_cli", "COPILOT_GITHUB_TOKEN", _run_copilot),
}
ALL_TOKEN_NAMES = (
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CODEX_ACCESS_TOKEN",
    "COPILOT_GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)


@pytest.fixture(params=sorted(RIGS))
def rig(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Rig:
    for name in (*ALL_TOKEN_NAMES, *BILLING_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return RIGS[request.param]


def _sources(mp: pytest.MonkeyPatch, rig: Rig, *, disk: bool, probe: bool) -> None:
    set_sources(
        mp,
        rig.module,
        disk=(lambda environ: rig.disk_text) if disk else None,
        probe=probe,
    )


def _dotenv(mp: pytest.MonkeyPatch, tmp_path: Path, rig: Rig) -> None:
    path = tmp_path / "creds.env"
    path.write_text(f"{rig.token_env}={DOTENV_VALUE}\n", encoding="utf-8")
    mp.setenv("EVAL_DOTENV_FILES", str(path))


def _injected(rig: Rig, result: dict[str, Any]) -> str | None:
    """The credential the child received, whichever way this CLI takes it."""
    if rig.name == "codex" and "auth_text" in result:
        return json.loads(result["auth_text"])["tokens"]["access_token"]
    return result["env"].get(rig.token_env)


def test_env_step_is_selected_and_recorded(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    _sources(monkeypatch, rig, disk=True, probe=True)
    monkeypatch.setenv(rig.token_env, ENV_VALUE)

    result = rig.run(monkeypatch)

    assert _injected(rig, result) == ENV_VALUE
    assert creds.recorded_steps() == [creds.STEP_ENV]


def test_env_beats_dotenv_beats_disk_beats_existing_login(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _sources(monkeypatch, rig, disk=True, probe=True)
    _dotenv(monkeypatch, tmp_path, rig)
    monkeypatch.setenv(rig.token_env, ENV_VALUE)
    assert _injected(rig, rig.run(monkeypatch)) == ENV_VALUE

    monkeypatch.delenv(rig.token_env)
    _sources(monkeypatch, rig, disk=True, probe=True)
    assert _injected(rig, rig.run(monkeypatch)) == DOTENV_VALUE
    assert creds.recorded_steps() == [creds.STEP_DOTENV]

    monkeypatch.setenv("EVAL_DOTENV_FILES", str(tmp_path / "gone.env"))
    _sources(monkeypatch, rig, disk=True, probe=True)
    assert _injected(rig, rig.run(monkeypatch)) == DISK_VALUE
    assert creds.recorded_steps() == [creds.STEP_DISK]

    _sources(monkeypatch, rig, disk=False, probe=True)
    assert _injected(rig, rig.run(monkeypatch)) is None
    assert creds.recorded_steps() == [creds.STEP_EXISTING_LOGIN]


def test_missing_or_corrupt_disk_credential_falls_through(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `read_disk` answers None for a missing, corrupt, or unusable source.
    _sources(monkeypatch, rig, disk=False, probe=True)

    rig.run(monkeypatch)

    assert creds.recorded_steps() == [creds.STEP_EXISTING_LOGIN]


def test_fifo_timeout_falls_through(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fifo = tmp_path / "op.env"
    os.mkfifo(fifo)
    monkeypatch.setenv("EVAL_DOTENV_FILES", str(fifo))
    monkeypatch.setattr(creds, "FIFO_TIMEOUT_SECONDS", 0.2)
    _sources(monkeypatch, rig, disk=True, probe=True)

    result = rig.run(monkeypatch)

    assert _injected(rig, result) == DISK_VALUE
    assert creds.recorded_steps() == [creds.STEP_DISK]


def test_non_terminal_at_the_last_step_exits_before_any_process(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources(monkeypatch, rig, disk=False, probe=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    recorder = Recorder()
    install_runner(monkeypatch, recorder)

    with pytest.raises(creds.CredentialNotFoundError, match=rig.token_env):
        rig.run(monkeypatch)

    assert recorder.calls == []


def test_existing_login_adds_no_token_and_no_relocation(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources(monkeypatch, rig, disk=False, probe=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/operator/claude")
    monkeypatch.setenv("CODEX_HOME", "/operator/codex")

    env = rig.run(monkeypatch)["env"]

    assert not any(name in env for name in ALL_TOKEN_NAMES)
    if rig.name == "claude":
        assert env["CLAUDE_CONFIG_DIR"] == "/operator/claude"
    if rig.name == "codex":
        assert env["CODEX_HOME"] == "/operator/codex"


def test_disk_step_matches_each_cli_s_own_mechanism(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sources(monkeypatch, rig, disk=True, probe=False)
    monkeypatch.setenv("CODEX_HOME", "/operator/codex")

    result = rig.run(monkeypatch)

    env = result["env"]
    if rig.name == "claude":
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == DISK_VALUE
        assert env["CLAUDE_CONFIG_DIR"] != "/operator/claude"
    if rig.name == "codex":
        assert "CODEX_ACCESS_TOKEN" not in env
        assert env["CODEX_HOME"] != "/operator/codex"
        assert (result["auth_mode"], result["home_mode"]) == (0o600, 0o700)
    if rig.name == "copilot":
        assert env["COPILOT_GITHUB_TOKEN"] == DISK_VALUE


@pytest.mark.parametrize("step", [creds.STEP_ENV, creds.STEP_DISK, creds.STEP_EXISTING_LOGIN])
def test_billing_env_is_stripped_on_every_step(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    for name, value in BILLING_ENV.items():
        monkeypatch.setenv(name, value)
    _sources(monkeypatch, rig, disk=step == creds.STEP_DISK, probe=True)
    if step == creds.STEP_ENV:
        monkeypatch.setenv(rig.token_env, ENV_VALUE)

    env = rig.run(monkeypatch)["env"]

    assert creds.recorded_steps() == [step]
    assert not set(BILLING_ENV) & set(env)
    assert not any(value in json.dumps(env) for value in BILLING_ENV.values())


@pytest.mark.parametrize("step", [creds.STEP_ENV, creds.STEP_DOTENV, creds.STEP_DISK])
def test_token_values_never_reach_output_logs_or_errors(
    rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    step: str,
) -> None:
    _sources(monkeypatch, rig, disk=step == creds.STEP_DISK, probe=False)
    if step == creds.STEP_ENV:
        monkeypatch.setenv(rig.token_env, ENV_VALUE)
    if step == creds.STEP_DOTENV:
        _dotenv(monkeypatch, tmp_path, rig)

    rig.run(monkeypatch)
    resolved = list(creds._RESOLVED.values())
    out, err = capsys.readouterr()

    secrets = (ENV_VALUE, DOTENV_VALUE, DISK_VALUE)
    for text in (out, err, caplog.text, repr(resolved)):
        assert not any(secret in text for secret in secrets)


def test_a_failed_process_error_does_not_carry_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", ENV_VALUE)
    install_runner(monkeypatch, Recorder(returncode=1, stderr=f"bad token {ENV_VALUE}"))

    with pytest.raises(RuntimeError) as excinfo:
        _claude_cli._ClaudeCLIProvider().complete(
            messages=MESSAGES, model="claude-haiku-4-5-20251001"
        )

    assert ENV_VALUE not in str(excinfo.value)


def test_copilot_reads_gh_token_after_its_own_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = RIGS["copilot"]
    for name in ALL_TOKEN_NAMES:
        monkeypatch.delenv(name, raising=False)
    _sources(monkeypatch, rig, disk=True, probe=True)
    monkeypatch.setenv("GH_TOKEN", ENV_VALUE)

    result = rig.run(monkeypatch)

    assert creds.recorded_steps() == [creds.STEP_ENV]
    assert result["env"]["COPILOT_GITHUB_TOKEN"] == ENV_VALUE
