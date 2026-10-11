"""Tests for the guard that keeps Copilot out of the local CLI smoke."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_smoke_guard as guard


@pytest.mark.parametrize(
    "args",
    [
        ["copilot", "--version"],
        ("copilot",),
        "copilot --help",
        b"copilot",
        ["/usr/local/bin/copilot", "-p", "x"],
        [r"C:\tools\Copilot.EXE"],
        [r"C:\npm\copilot.cmd", "skill", "list"],
        [Path("/opt/bin/copilot")],
        ["copilot.bat"],
        "COPILOT_MODEL=x copilot -p hi",
        "env FOO=1 copilot",
        ["env", "-i", "copilot"],
        ["npx", "-y", "@github/copilot"],
        "'/opt/my tools/copilot' --version",
        r"C:\npm\copilot.cmd --version",
        ["env", "-u", "FOO", "copilot"],
        ["sudo", "-u", "root", "copilot"],
        ["env", "--unset=FOO", "copilot"],
        ["sh", "-c", "copilot --help"],
        "bash -c 'FOO=1 copilot -p hi'",
        ["cmd.exe", "/c", "copilot.cmd"],
        ["pwsh", "-Command", "copilot"],
        ["npx", "@github/copilot@1.0.91"],
        ["npx", "-p", "@github/copilot", "copilot"],
        Path("/opt/my tools/copilot"),
    ],
)
def test_refuses_every_spelling_of_the_copilot_program(args: object) -> None:
    with pytest.raises(guard.CopilotCallRefusedError, match="requires_copilot"):
        guard.refuse_copilot(args)


@pytest.mark.parametrize(
    "args",
    [
        ["claude", "-p", "copilot"],
        ["codex", "exec"],
        "python -c 'print(1)'",
        ["copilot-language-server"],
        ["/usr/bin/copilotx"],
        ["gh", "copilot", "suggest"],
        "FOO=copilot claude -p hi",
        ["env", "-u", "copilot", "claude"],
        ["sudo", "-u", "copilot", "claude"],
        ["command", "-v", "copilot"],
        ["sh", "-c", "claude -p hi"],
        ["sh", "script.sh"],
        Path("/opt/my tools/claude"),
        [],
        "",
        None,
    ],
)
def test_allows_programs_that_are_not_copilot(args: object) -> None:
    guard.refuse_copilot(args)


def test_guard_is_armed_only_by_the_exact_flag() -> None:
    assert guard.guard_active({guard.LOCAL_SMOKE_ENV: "1"})
    assert not guard.guard_active({guard.LOCAL_SMOKE_ENV: "true"})
    assert not guard.guard_active({})


def test_installed_guard_stops_run_before_the_process_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard.install(monkeypatch.setattr)

    with pytest.raises(guard.CopilotCallRefusedError):
        subprocess.run(["copilot", "--version"], check=False)


def test_installed_guard_checks_the_executable_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge: ``executable=`` names the real program, whatever ``args[0]`` says."""
    guard.install(monkeypatch.setattr)

    with pytest.raises(guard.CopilotCallRefusedError):
        subprocess.run(["harmless"], executable="/usr/bin/copilot", check=False)


def test_installed_guard_checks_a_positional_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Edge: Popen's third positional argument is ``executable``."""
    guard.install(monkeypatch.setattr)

    with pytest.raises(guard.CopilotCallRefusedError):
        subprocess.Popen(["harmless"], -1, "/usr/bin/copilot")


def test_installed_guard_still_starts_other_programs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard.install(monkeypatch.setattr)

    result = subprocess.run(
        [sys.executable, "-c", "print('ok')"], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "ok"
    with subprocess.Popen([sys.executable, "-c", "pass"]) as proc:
        assert isinstance(proc, subprocess.Popen)
    assert proc.returncode == 0
