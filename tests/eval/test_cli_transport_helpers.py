"""Tests for `_cli_transport`, the machinery every CLI transport shares.

Offline: no CLI is launched. `subprocess.run` is replaced inside
`_cli_transport`, which is the one place every transport calls it.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.eval._cli_transport_test_support import (
    MESSAGES,
    Recorder,
    _cli_transport,
    install_runner,
)

# --- Shared helpers -----------------------------------------------------


@pytest.mark.parametrize("timeout", [0, -1.0, float("nan"), float("inf")])
def test_validate_timeout_rejects_an_unusable_value(timeout: float) -> None:
    with pytest.raises(RuntimeError, match="finite positive"):
        _cli_transport.validate_timeout(timeout)


def test_validate_timeout_accepts_a_positive_value() -> None:
    assert _cli_transport.validate_timeout(30) == 30.0


def test_blocked_env_wins_over_allowed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard rail: a credential in both lists must not be inherited."""
    monkeypatch.setenv("KEEP_ME", "yes")
    monkeypatch.setenv("DROP_ME", "secret")

    env = _cli_transport.minimal_process_env(
        allow=frozenset({"KEEP_ME", "DROP_ME"}),
        blocked=frozenset({"DROP_ME"}),
        overrides={"EXTRA": "1"},
    )

    assert env["KEEP_ME"] == "yes"
    assert "DROP_ME" not in env
    assert env["EXTRA"] == "1"
    assert env["NO_COLOR"] == "1"


def test_process_env_omits_a_variable_that_is_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ABSENT_ON_PURPOSE", raising=False)

    env = _cli_transport.minimal_process_env(
        allow=frozenset({"ABSENT_ON_PURPOSE"}), blocked=frozenset(), overrides={}
    )

    assert "ABSENT_ON_PURPOSE" not in env


def test_envelope_keeps_role_boundaries_and_the_trust_notice() -> None:
    envelope = json.loads(
        _cli_transport.build_envelope("Test CLI", MESSAGES, "Answer briefly.")
    )

    assert envelope["schema"] == "ai-agents-text-eval-v1"
    assert envelope["security_boundary"] == _cli_transport.TRUST_BOUNDARY
    assert envelope["system"]["content"] == "Answer briefly."
    assert envelope["messages"][0]["role"] == "user"
    assert envelope["messages"][0]["trust"] == "untrusted_repository_text"


def test_envelope_rejects_an_unsupported_role() -> None:
    with pytest.raises(RuntimeError, match="message role"):
        _cli_transport.build_envelope(
            "Test CLI", [{"role": "assistant", "content": "hi"}], ""
        )


def test_envelope_rejects_a_blank_prompt() -> None:
    with pytest.raises(RuntimeError, match="non-empty prompt"):
        _cli_transport.build_envelope("Test CLI", [{"role": "user", "content": " "}], "")


def test_envelope_drops_an_empty_message_but_keeps_the_system_text() -> None:
    envelope = json.loads(
        _cli_transport.build_envelope(
            "Test CLI", [{"role": "user", "content": "  "}], "Only this."
        )
    )

    assert envelope["messages"] == []
    assert envelope["system"]["content"] == "Only this."


@pytest.mark.parametrize(
    "stderr,expected",
    [
        ("You have hit the rate limit", "rate limit"),
        ("connection to backend timed out after 30s", "request timed out"),
        ("Not logged in", "authentication failed"),
        ("segmentation fault", "provider process failure"),
    ],
)
def test_process_error_reports_a_category_and_never_the_output(
    stderr: str, expected: str
) -> None:
    error = _cli_transport.safe_process_error("Test CLI", 3, stderr)

    assert expected in str(error)
    assert "redacted" in str(error)
    assert stderr not in str(error)


@pytest.mark.parametrize(
    "side_effect,expected",
    [
        (subprocess.TimeoutExpired("x", 1), "timed out"),
        (FileNotFoundError(), "executable_not_found"),
        (OSError(), "os_error"),
    ],
)
def test_run_cli_normalizes_every_launch_failure(
    monkeypatch: pytest.MonkeyPatch, side_effect: BaseException, expected: str
) -> None:
    install_runner(monkeypatch, Recorder(side_effect=side_effect))

    with pytest.raises(RuntimeError, match=expected):
        _cli_transport.run_cli(
            ["x"], "p", provider_label="Test CLI", env={}, timeout=5.0
        )


def test_run_cli_runs_prepare_inside_the_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Path] = []
    recorder = Recorder(stdout="ok")
    install_runner(monkeypatch, recorder)

    _cli_transport.run_cli(
        ["x"],
        None,
        provider_label="Test CLI",
        env={},
        timeout=5.0,
        prepare=seen.append,
    )

    assert len(seen) == 1
    assert str(seen[0]) == recorder.calls[-1]["cwd"]
    # The sandbox is removed once run_cli returns, so nothing a prepare hook
    # writes can outlive the call; a transport that needs an artifact back
    # owns its own directory (Codex does).
    assert not seen[0].exists()
    assert "input" not in recorder.calls[-1]
    assert recorder.calls[-1]["stdin"] is subprocess.DEVNULL
