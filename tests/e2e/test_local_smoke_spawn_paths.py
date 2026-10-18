"""The os and shell=True spawn paths of the local Copilot smoke guard (issue #6506)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_smoke_guard as guard


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
