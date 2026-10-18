"""Tests for the guard that keeps Copilot out of the local CLI smoke."""

from __future__ import annotations

import os
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


@pytest.mark.parametrize(
    "args",
    [
        "echo hi; copilot",
        "true && copilot --help",
        "false || copilot",
        "echo x | copilot",
        "(copilot)",
        "echo $(copilot --version)",
        "echo `copilot`",
        "sleep 1 & copilot",
        "echo a\ncopilot",
        "cd x;FOO=1 copilot",
        "echo ok;env FOO=1 copilot -p hi",
        r"echo hi & C:\npm\copilot.cmd --version",
        r"echo hi && C:\npm\copilot.cmd",
        ["sh", "-c", "echo hi; copilot"],
        "bash -c 'echo hi && copilot'",
        ["pwsh", "-Command", "echo hi; copilot"],
        "sh -c 'ls | copilot'",
    ],
)
def test_refuses_copilot_anywhere_in_a_compound_command(args: object) -> None:
    with pytest.raises(guard.CopilotCallRefusedError, match="requires_copilot"):
        guard.refuse_copilot(args)


@pytest.mark.parametrize(
    "args",
    [
        "echo copilot; ls",
        "ls | grep copilot",
        "echo 'a; copilot'",
        'echo "x && copilot"',
        "claude -p hi && codex exec",
        "cd copilot && ls",
        "git status | head",
        ["sh", "-c", "echo hi; ls"],
        "bash -c 'echo hi && ls'",
        "echo $(date)",
        "echo hi >out.txt; cat out.txt",
        "a;;b",
        ";",
        "&&",
    ],
)
def test_allows_a_compound_command_that_never_starts_copilot(args: object) -> None:
    guard.refuse_copilot(args)


def test_program_names_lists_every_program_in_order() -> None:
    assert guard.program_names("a; b | env X=1 c && sh -c 'd; e'") == ["a", "b", "c", "d", "e"]


def test_program_name_keeps_returning_the_first_program() -> None:
    assert guard.program_name("echo hi; copilot") == "echo"
    assert guard.program_name("") == ""
    assert guard.program_name(["command", "-v", "copilot"]) == ""


def test_an_unbalanced_quote_still_finds_copilot_after_an_operator() -> None:
    """Edge: shlex rejects the line, so the fallback splitter must still see the second command."""
    with pytest.raises(guard.CopilotCallRefusedError):
        guard.refuse_copilot("echo 'oops; copilot")


def test_the_refusal_is_not_an_exception() -> None:
    """A broad ``except Exception`` in the code under test must not swallow it."""
    assert not issubclass(guard.CopilotCallRefusedError, Exception)
    assert issubclass(guard.CopilotCallRefusedError, BaseException)

    def swallow() -> str:
        try:
            guard.refuse_copilot(["copilot"])
        except Exception:
            return "swallowed"
        return "not reached"

    with pytest.raises(guard.CopilotCallRefusedError):
        swallow()


@pytest.fixture
def fake_copilot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A ``copilot`` on PATH that records a launch. The marker must never appear."""
    marker = tmp_path / "launched"
    exe = tmp_path / "bin" / "copilot"
    exe.parent.mkdir()
    exe.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{exe.parent}{os.pathsep}{os.environ['PATH']}")
    return marker


@pytest.mark.skipif(os.name == "nt", reason="the fake copilot is a POSIX shell script")
class TestInstalledGuardCoversTheOtherSpawnPaths:
    def test_os_system_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path
    ) -> None:
        guard.install(monkeypatch.setattr)

        with pytest.raises(guard.CopilotCallRefusedError):
            os.system("copilot --version")
        assert not fake_copilot.exists()

    def test_os_system_with_a_compound_line_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path
    ) -> None:
        guard.install(monkeypatch.setattr)

        with pytest.raises(guard.CopilotCallRefusedError):
            os.system("echo hi; copilot")
        assert not fake_copilot.exists()

    def test_os_popen_is_refused_through_popen(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path
    ) -> None:
        guard.install(monkeypatch.setattr)

        with pytest.raises(guard.CopilotCallRefusedError):
            os.popen("copilot --version")
        assert not fake_copilot.exists()

    @pytest.mark.skipif(not hasattr(os, "posix_spawn"), reason="needs posix_spawn")
    def test_posix_spawn_and_posix_spawnp_are_refused(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path
    ) -> None:
        guard.install(monkeypatch.setattr)
        exe = fake_copilot.parent / "bin" / "copilot"

        with pytest.raises(guard.CopilotCallRefusedError):
            os.posix_spawn(str(exe), [str(exe)], dict(os.environ))
        with pytest.raises(guard.CopilotCallRefusedError):
            os.posix_spawnp("copilot", ["copilot"], dict(os.environ))
        with pytest.raises(guard.CopilotCallRefusedError):
            os.posix_spawn("/bin/sh", ["sh", "-c", "echo hi; copilot"], dict(os.environ))
        assert not fake_copilot.exists()

    def test_exec_family_is_refused_before_the_process_image_is_replaced(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path
    ) -> None:
        guard.install(monkeypatch.setattr)
        exe = str(fake_copilot.parent / "bin" / "copilot")

        with pytest.raises(guard.CopilotCallRefusedError):
            os.execv(exe, [exe])
        with pytest.raises(guard.CopilotCallRefusedError):
            os.execve(exe, [exe], dict(os.environ))
        with pytest.raises(guard.CopilotCallRefusedError):
            os.execvp("copilot", ["copilot"])
        with pytest.raises(guard.CopilotCallRefusedError):
            os.execl(exe, exe)
        assert not fake_copilot.exists()

    def test_spawn_family_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path
    ) -> None:
        guard.install(monkeypatch.setattr)
        exe = str(fake_copilot.parent / "bin" / "copilot")

        with pytest.raises(guard.CopilotCallRefusedError):
            os.spawnv(os.P_WAIT, exe, [exe])
        with pytest.raises(guard.CopilotCallRefusedError):
            os.spawnvp(os.P_WAIT, "copilot", ["copilot"])
        with pytest.raises(guard.CopilotCallRefusedError):
            os.spawnl(os.P_WAIT, exe, exe)
        assert not fake_copilot.exists()

    def test_shell_true_with_a_command_line_in_a_list_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path
    ) -> None:
        guard.install(monkeypatch.setattr)

        with pytest.raises(guard.CopilotCallRefusedError):
            subprocess.run(["echo hi; copilot"], shell=True, check=False)
        with pytest.raises(guard.CopilotCallRefusedError):
            subprocess.run("echo hi; copilot", shell=True, check=False)
        assert not fake_copilot.exists()

    def test_other_programs_still_start_through_every_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        guard.install(monkeypatch.setattr)

        assert os.system("true") == 0
        assert os.spawnv(os.P_WAIT, sys.executable, [sys.executable, "-c", "pass"]) == 0
        assert os.spawnl(os.P_WAIT, sys.executable, sys.executable, "-c", "pass") == 0
        if hasattr(os, "posix_spawn"):
            pid = os.posix_spawn(sys.executable, [sys.executable, "-c", "pass"], dict(os.environ))
            assert os.waitpid(pid, 0)[1] == 0
        assert os.popen("echo ok").read().strip() == "ok"


def test_uninstall_restores_popen_and_the_os_entry_points() -> None:
    originals = dict(guard._ORIGINAL_OS)
    try:
        guard.install(lambda target, name, value: setattr(target, name, value))
        assert subprocess.Popen is guard.GuardedPopen
        assert os.system is not originals["system"]
    finally:
        guard.uninstall()

    assert subprocess.Popen is guard._ORIGINAL_POPEN
    assert all(getattr(os, name) is original for name, original in originals.items())
