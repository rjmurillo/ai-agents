"""The os and shell=True spawn paths of the local Copilot smoke guard (issue #6506)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
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


_REPLACING_OR_SPAWNING = (
    "posix_spawn",
    "posix_spawnp",
    "execv",
    "execve",
    "execvp",
    "execvpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
)


@pytest.fixture
def tripwire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the real exec and spawn functions for ones that fail the test.

    A real ``os.execv`` replaces the pytest process, so a guard regression would end
    the session with exit 0 instead of a failure. Install the guard after this.
    """

    def let_through(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"the guard let a Copilot launch through: {args!r}")

    for name in _REPLACING_OR_SPAWNING:
        if name in guard._ORIGINAL_OS:
            monkeypatch.setitem(guard._ORIGINAL_OS, name, let_through)


@pytest.mark.skipif(os.name == "nt", reason="the fake copilot is a POSIX shell script")
class TestInstalledGuardCoversTheOtherSpawnPaths:
    def test_os_system_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path
    ) -> None:
        guard.install(monkeypatch.setattr)

        with pytest.raises(guard.CopilotCallRefusedError):
            os.system("copilot --version")
        assert not fake_copilot.exists()

    def test_os_system_by_keyword_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path
    ) -> None:
        guard.install(monkeypatch.setattr)

        with pytest.raises(guard.CopilotCallRefusedError):
            os.system(command="copilot --version")
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
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path, tripwire: None
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
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path, tripwire: None
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
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path, tripwire: None
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

    def test_exec_and_spawn_by_keyword_are_refused(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path, tripwire: None
    ) -> None:
        guard.install(monkeypatch.setattr)
        exe = str(fake_copilot.parent / "bin" / "copilot")
        env = dict(os.environ)

        for call in (
            lambda: os.execve(path=exe, argv=[exe], env=env),
            lambda: os.execve(exe, argv=[exe], env=env),
            lambda: os.execvp(file="copilot", args=["copilot"]),
            lambda: os.execvpe(file="copilot", args=["copilot"], env=env),
            lambda: os.spawnv(os.P_WAIT, file=exe, args=[exe]),
            lambda: os.spawnv(mode=os.P_WAIT, file=exe, args=[exe]),
            lambda: os.spawnve(os.P_WAIT, file=exe, args=[exe], env=env),
            lambda: os.spawnvp(os.P_WAIT, file="copilot", args=["copilot"]),
            lambda: os.spawnvpe(os.P_WAIT, file="copilot", args=["copilot"], env=env),
            lambda: os.execvp(file="sh", args=["sh", "-c", "echo hi; copilot"]),
        ):
            with pytest.raises(guard.CopilotCallRefusedError):
                call()
        assert not fake_copilot.exists()

    def test_other_programs_by_keyword_reach_the_original(
        self, monkeypatch: pytest.MonkeyPatch, tripwire: None
    ) -> None:
        guard.install(monkeypatch.setattr)

        # The tripwire stands in for the real function, so reaching it proves the guard let
        # the call through.
        with pytest.raises(AssertionError, match="let a Copilot launch through"):
            os.execvp(file="true", args=["true"])
        with pytest.raises(AssertionError, match="let a Copilot launch through"):
            os.spawnv(os.P_WAIT, file="/bin/true", args=["true"])

    def test_shell_true_with_a_command_line_in_a_list_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, fake_copilot: Path
    ) -> None:
        guard.install(monkeypatch.setattr)

        # Popen is the one entry point under run, call, and check_output.
        with pytest.raises(guard.CopilotCallRefusedError):
            guard.GuardedPopen(["echo hi; copilot"], shell=True)
        with pytest.raises(guard.CopilotCallRefusedError):
            guard.GuardedPopen("echo hi; copilot", shell=True)
        # Positional order after args: bufsize, executable, stdin, stdout, stderr,
        # preexec_fn, close_fds, shell.
        with pytest.raises(guard.CopilotCallRefusedError):
            guard.GuardedPopen(["echo hi; copilot"], -1, None, None, None, None, None, True, True)
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


def _launched(*args: object, **kwargs: object) -> None:
    raise AssertionError("the guard let a Copilot launch through")


# Stand-ins that share the parameter names of the real functions.
def _execve_like(path: object, argv: object, env: object = None) -> None:
    _launched()


def _spawnv_like(mode: object, file: object, args: object) -> None:
    _launched()


def _execvp_like(file: object, args: object) -> None:
    _launched()


def _system_like(command: object) -> None:
    _launched()


@pytest.mark.parametrize(
    ("function", "program", "argv", "args", "kwargs"),
    [
        (_execve_like, 0, 1, (), {"path": "copilot", "argv": ["copilot"]}),
        (_execve_like, 0, 1, ("sh",), {"argv": ["sh", "-c", "echo hi; copilot"]}),
        (_spawnv_like, 1, 2, (0,), {"file": "copilot", "args": ["copilot"]}),
        (_spawnv_like, 1, 2, (), {"mode": 0, "file": "copilot", "args": ["copilot"]}),
        (_execvp_like, 0, 1, ("sh",), {"args": ["sh", "-c", "echo hi; copilot"]}),
        (_system_like, 0, None, (), {"command": "echo hi; copilot"}),
    ],
)
def test_guarded_os_reads_the_program_and_argv_from_keywords(
    function: Callable[..., None],
    program: int,
    argv: int | None,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(guard.CopilotCallRefusedError):
        guard._guarded_os(function, program, argv)(*args, **kwargs)


def test_guarded_os_lets_a_keyword_call_to_another_program_through() -> None:
    with pytest.raises(AssertionError, match="let a Copilot launch through"):
        guard._guarded_os(_execve_like, 0, 1)(path="true", argv=["true", "-v"])


@pytest.mark.parametrize(
    ("argv", "kwargs"),
    [(1, {"path": "true", "argv": ["true"]}), (None, {"command": "true"})],
)
def test_guarded_os_refuses_keywords_it_cannot_map_when_no_signature_resolves(
    monkeypatch: pytest.MonkeyPatch, argv: int | None, kwargs: dict[str, object]
) -> None:
    """Fail closed: without a signature a keyword program would otherwise go unchecked."""
    monkeypatch.setattr(guard, "_signature_of", lambda function: None)
    guarded = guard._guarded_os(_launched, 0, argv)

    with pytest.raises(guard.CopilotCallRefusedError):
        guarded(**kwargs)


def test_guarded_os_with_no_signature_still_reads_positional_calls() -> None:
    guarded = guard._guarded_os(_launched, 0, 1, None)

    with pytest.raises(guard.CopilotCallRefusedError):
        guarded("copilot", ["copilot"])


def test_guarded_os_passes_an_unbindable_call_to_the_original() -> None:
    """A call the signature rejects reaches the original, which raises its own TypeError."""

    def execve_like(path: object, argv: object, env: object) -> None:
        raise AssertionError("unreachable")

    with pytest.raises(TypeError, match="unexpected keyword"):
        guard._guarded_os(execve_like, 0, 1)(path="true", nope=1)


def test_uninstall_restores_popen_and_the_os_entry_points() -> None:
    """Leave the session as found: a run armed by the pre-push gate keeps its own guard."""
    before_popen = subprocess.Popen
    before_os = {name: getattr(os, name) for name in guard._ORIGINAL_OS}
    try:
        guard.install(lambda target, name, value: setattr(target, name, value))
        assert subprocess.Popen is guard.GuardedPopen
        assert os.system is not guard._ORIGINAL_OS["system"]

        guard.uninstall()

        assert subprocess.Popen is guard._ORIGINAL_POPEN
        assert all(getattr(os, name) is orig for name, orig in guard._ORIGINAL_OS.items())
    finally:
        setattr(subprocess, "Popen", before_popen)  # noqa: B010
        for name, value in before_os.items():
            setattr(os, name, value)
