"""Tests for the per-CLI disk readers and login probes.

Every reader must answer None and every probe False for a missing, corrupt, or
unusable source, so the shared order falls through instead of crashing.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from tests.eval._credential_test_support import _cli_credential_sources as src

TOKEN = "tok-" + "T" * 10


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")


def _claude(token: object = TOKEN, expires: object = None) -> dict[str, Any]:
    oauth: dict[str, Any] = {"accessToken": token}
    if expires is not None:
        oauth["expiresAt"] = expires
    return {"claudeAiOauth": oauth}


class TestClaudeDisk:
    def test_reads_the_token_under_claude_config_dir(self, tmp_path: Path) -> None:
        _write(tmp_path / ".credentials.json", _claude(f"  {TOKEN} "))

        assert src.claude_disk_token({"CLAUDE_CONFIG_DIR": str(tmp_path)}) == TOKEN

    def test_defaults_to_home_dot_claude(self, tmp_path: Path) -> None:
        _write(tmp_path / ".claude" / ".credentials.json", _claude())

        assert src.claude_disk_token({"HOME": str(tmp_path)}) == TOKEN

    def test_a_future_expiry_is_usable(self, tmp_path: Path) -> None:
        _write(tmp_path / ".credentials.json", _claude(expires=(time.time() + 600) * 1000))

        assert src.claude_disk_token({"CLAUDE_CONFIG_DIR": str(tmp_path)}) == TOKEN

    @pytest.mark.parametrize(
        "payload",
        [
            "{not json",
            [],
            {"claudeAiOauth": "x"},
            {"other": {}},
            _claude(token=""),
            _claude(token=5),
            _claude(expires=1),
        ],
    )
    def test_corrupt_expired_or_malformed_falls_through(
        self, tmp_path: Path, payload: object
    ) -> None:
        _write(tmp_path / ".credentials.json", payload)

        assert src.claude_disk_token({"CLAUDE_CONFIG_DIR": str(tmp_path)}) is None

    def test_missing_file_falls_through(self, tmp_path: Path) -> None:
        assert src.claude_disk_token({"CLAUDE_CONFIG_DIR": str(tmp_path)}) is None


class TestCodexDisk:
    def _auth(self, **extra: object) -> dict[str, Any]:
        return {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": None,
            "tokens": {"access_token": TOKEN},
            **extra,
        }

    def test_returns_the_plan_login_file_text(self, tmp_path: Path) -> None:
        _write(tmp_path / "auth.json", self._auth())

        text = src.codex_auth_file_text({"CODEX_HOME": str(tmp_path)})

        assert text is not None and json.loads(text)["tokens"]["access_token"] == TOKEN

    def test_defaults_to_home_dot_codex(self, tmp_path: Path) -> None:
        _write(tmp_path / ".codex" / "auth.json", self._auth())

        assert src.codex_auth_file_text({"HOME": str(tmp_path)}) is not None

    @pytest.mark.parametrize(
        "payload",
        [
            "{broken",
            [],
            {"OPENAI_API_KEY": "sk-metered", "tokens": {"access_token": TOKEN}},
            {"tokens": {}},
            {"tokens": "x"},
            {"tokens": {"access_token": " "}},
        ],
    )
    def test_corrupt_metered_or_empty_falls_through(self, tmp_path: Path, payload: object) -> None:
        _write(tmp_path / "auth.json", payload)

        assert src.codex_auth_file_text({"CODEX_HOME": str(tmp_path)}) is None

    def test_missing_file_falls_through(self, tmp_path: Path) -> None:
        assert src.codex_auth_file_text({"CODEX_HOME": str(tmp_path)}) is None


class _FakeRun:
    def __init__(self, stdout: str = "", returncode: int = 0, error: BaseException | None = None):
        self.stdout, self.returncode, self.error = stdout, returncode, error
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        self.calls.append((argv, kwargs))
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "")


class TestCopilotDisk:
    def test_reads_the_gh_token_with_a_minimal_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeRun(stdout=f"{TOKEN}\n")
        monkeypatch.setattr(src.subprocess, "run", fake)

        token = src.copilot_disk_token({"PATH": "/bin", "ANTHROPIC_API_KEY": "sk", "HOME": "/h"})

        assert token == TOKEN
        argv, kwargs = fake.calls[0]
        assert argv == ["gh", "auth", "token"]
        assert kwargs["env"] == {"PATH": "/bin", "HOME": "/h"}

    @pytest.mark.parametrize(
        "fake",
        [
            _FakeRun(stdout="", returncode=0),
            _FakeRun(stdout=TOKEN, returncode=1),
            _FakeRun(stdout="ghp_classic"),
            _FakeRun(stdout="two words"),
            _FakeRun(error=FileNotFoundError()),
            _FakeRun(error=subprocess.TimeoutExpired("gh", 1)),
        ],
    )
    def test_failure_classic_or_odd_output_falls_through(
        self, monkeypatch: pytest.MonkeyPatch, fake: _FakeRun
    ) -> None:
        monkeypatch.setattr(src.subprocess, "run", fake)

        assert src.copilot_disk_token({}) is None


class TestLoginProbes:
    def _probe(self, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> _FakeRun:
        fake = _FakeRun(**kwargs)
        monkeypatch.setattr(src.subprocess, "run", fake)
        return fake

    def test_claude_accepts_only_a_claude_ai_login(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = self._probe(
            monkeypatch, stdout=json.dumps({"loggedIn": True, "authMethod": "claude.ai"})
        )

        assert src.claude_login_probe("claude", {"PATH": "/bin", "ANTHROPIC_API_KEY": "sk"})
        assert fake.calls[0][0] == ["claude", "auth", "status"]
        assert "ANTHROPIC_API_KEY" not in fake.calls[0][1]["env"]

    @pytest.mark.parametrize(
        "stdout",
        [
            json.dumps({"loggedIn": True, "authMethod": "console"}),
            json.dumps({"loggedIn": False, "authMethod": "claude.ai"}),
            json.dumps([]),
            "not json",
            "",
        ],
    )
    def test_claude_rejects_other_logins(
        self, monkeypatch: pytest.MonkeyPatch, stdout: str
    ) -> None:
        self._probe(monkeypatch, stdout=stdout)

        assert not src.claude_login_probe("claude", {})

    def test_claude_probe_failure_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._probe(monkeypatch, returncode=1, stdout=json.dumps({"loggedIn": True}))

        assert not src.claude_login_probe("claude", {})

    def test_codex_accepts_the_chatgpt_login_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._probe(monkeypatch, stdout="Logged in using ChatGPT\n")
        assert src.codex_login_probe("codex", {})

        self._probe(monkeypatch, stdout="Logged in using an API key\n")
        assert not src.codex_login_probe("codex", {})

        self._probe(monkeypatch, error=OSError())
        assert not src.codex_login_probe("codex", {})

    def test_copilot_reads_the_last_logged_in_user(self, tmp_path: Path) -> None:
        body = (
            '// managed file\n{"lastLoggedInUser": {"host": "https://github.com", "login": "me"}}\n'
        )
        _write(tmp_path / "config.json", body)

        assert src.copilot_login_probe("copilot", {"COPILOT_HOME": str(tmp_path)})

    @pytest.mark.parametrize(
        "body",
        ["{broken", "[]", "{}", '{"lastLoggedInUser": {"login": ""}}', '{"lastLoggedInUser": 1}'],
    )
    def test_copilot_without_a_logged_in_user_is_false(self, tmp_path: Path, body: str) -> None:
        _write(tmp_path / "config.json", body)

        assert not src.copilot_login_probe("copilot", {"COPILOT_HOME": str(tmp_path)})

    def test_copilot_missing_config_is_false(self, tmp_path: Path) -> None:
        assert not src.copilot_login_probe("copilot", {"HOME": str(tmp_path)})


def test_read_regular_text_refuses_fifo_and_oversize(tmp_path):
    import os

    fifo = tmp_path / "auth.json"
    os.mkfifo(fifo)
    big = tmp_path / "big.json"
    big.write_text("x" * (64 * 1024 + 1), encoding="utf-8")
    for path in (fifo, big):
        try:
            src._read_regular_text(path)
        except OSError:
            continue
        raise AssertionError(f"{path.name} should have been refused")


def test_probe_env_drops_gh_host():
    env = src._probe_env({"GH_HOST": "ghe.example", "HOME": "/h"})
    assert "GH_HOST" not in env
