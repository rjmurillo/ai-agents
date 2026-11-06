"""An isolated Claude fixture run gets the stored login as a token (issue #5410)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.eval._credential_test_support import set_sources
from tests.eval._runtime_parity_test_support import parity

TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
DISK_TOKEN = "disk-token-for-test"


def _disk_login(monkeypatch: pytest.MonkeyPatch) -> None:
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: DISK_TOKEN)


def test_isolated_claude_run_receives_the_stored_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _disk_login(monkeypatch)

    env = parity._fixture_env(tmp_path, "claude", "claude")

    assert env[TOKEN_ENV] == DISK_TOKEN
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path / ".parity-profile" / "claude")


def test_runtime_env_itself_stays_login_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    _disk_login(monkeypatch)

    assert TOKEN_ENV not in parity.runtime_env(tmp_path, "claude")


def test_real_home_run_uses_the_cli_login_and_gets_no_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.setenv(parity.REAL_HOME_ENV, "1")
    _disk_login(monkeypatch)

    assert TOKEN_ENV not in parity._fixture_env(tmp_path, "claude", "claude")


def test_copilot_run_gets_no_claude_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    _disk_login(monkeypatch)

    assert TOKEN_ENV not in parity._fixture_env(tmp_path, "copilot", "copilot")


@pytest.mark.parametrize(
    ("name", "value"),
    [("ANTHROPIC_API_KEY", "operator-key"), (TOKEN_ENV, "operator-token")],
)
def test_an_exported_credential_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.setenv(name, value)
    _disk_login(monkeypatch)

    env = parity._fixture_env(tmp_path, "claude", "claude")

    assert env[name] == value
    assert env.get(TOKEN_ENV) != DISK_TOKEN


def test_existing_login_step_injects_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: None, probe=True)

    assert TOKEN_ENV not in parity._fixture_env(tmp_path, "claude", "claude")


def test_missing_credential_leaves_the_env_for_the_cli_to_fail_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: None, probe=False)

    assert TOKEN_ENV not in parity._fixture_env(tmp_path, "claude", "claude")
