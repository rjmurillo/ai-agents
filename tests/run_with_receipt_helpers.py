"""Shared fakes, child-process scripts, and fixtures for the run_with_receipt tests."""

from __future__ import annotations

import io
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_with_receipt as receipt_module
import run_with_receipt_child as child_module
from run_with_receipt import (
    EXIT_EXTERNAL,
    EXIT_USAGE,
    main,
    resolve_out_dir,
)

__all__ = [
    "ARTIFACT_NAME",
    "BEARER",
    "EARLY_EXIT_SCRIPT",
    "EXIT_EXTERNAL",
    "EXIT_USAGE",
    "GITHUB_TOKEN",
    "POSIX_ONLY",
    "SIGCHLD_REAPING_LAUNCHER",
    "TREE_SCRIPT",
    "WRAPPER_LAUNCHER",
    "_FakePopen",
    "artifact_from",
    "artifacts",
    "child_module",
    "default_cancel_signals",
    "default_sighup",
    "default_sigterm",
    "install_fake_popen",
    "install_group_fakes",
    "install_stubborn_group",
    "kill_tree",
    "main",
    "pid_alive",
    "pid_reaped",
    "py",
    "receipt_module",
    "resolve_out_dir",
    "run",
    "start_wrapper",
    "tree_pids",
    "tree_ready",
    "wait_until",
]

GITHUB_TOKEN = "ghp_" + "A1b2C3d4E5" * 4  # 40 chars after prefix, matches github-token rule
ARTIFACT_NAME = "20260101T000000-deadbeef.log"
BEARER = "Bearer abcDEF123456xyz+/="
POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def run(args: list[str], out_dir: Path, *, inline: int = 16384, timeout: int | None = None) -> int:
    argv = ["run", "--max-inline-bytes", str(inline), "--out-dir", str(out_dir)]
    if timeout is not None:
        argv.extend(["--timeout-seconds", str(timeout)])
    return main([*argv, "--", *args])


class _FakePopen:
    """Popen test double with byte pipes and scripted wait results."""

    def __init__(
        self,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        waits: list[int | BaseException] | None = None,
    ) -> None:
        self.pid = 4321
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.waits = list(waits or [0])
        self.wait_timeouts: list[float | None] = []
        self.kill_calls = 0
        self.returncode: int | None = None

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        result = self.waits.pop(0) if self.waits else 0
        if isinstance(result, BaseException):
            raise result
        self.returncode = int(result)
        return self.returncode

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9


def install_fake_popen(
    monkeypatch: pytest.MonkeyPatch, proc: _FakePopen
) -> list[tuple[tuple[object, ...], dict[str, object]]]:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def factory(*args: object, **kwargs: object) -> _FakePopen:
        calls.append((args, kwargs))
        return proc

    monkeypatch.setattr(child_module.subprocess, "Popen", factory)
    return calls


def install_group_fakes(
    monkeypatch: pytest.MonkeyPatch, proc: _FakePopen, *, group_alive_probes: int = 0
) -> list[tuple[int, int]]:
    """Fake process-group support for `proc` and return the signals sent to it.

    The existence probe (signal 0) is not recorded. It reports a live group for
    `group_alive_probes` calls, then a gone group.
    """
    signals: list[tuple[int, int]] = []
    probes = {"left": group_alive_probes}

    def killpg(pgid: int, sig: int) -> None:
        if sig == 0:
            if probes["left"] <= 0:
                raise ProcessLookupError(pgid)
            probes["left"] -= 1
            return
        signals.append((pgid, sig))

    monkeypatch.setattr(child_module, "_SUPPORTS_PGROUP", True, raising=False)
    monkeypatch.setattr(child_module.os, "killpg", killpg, raising=False)
    monkeypatch.setattr(
        child_module.os,
        "getpgid",
        lambda pid: proc.pid if pid == proc.pid else proc.pid + 1,
        raising=False,
    )
    return signals


def install_stubborn_group(
    monkeypatch: pytest.MonkeyPatch, proc: _FakePopen
) -> list[tuple[int, int]]:
    """Fake a group that outlives SIGTERM, with a clock that skips the grace window.

    The group is still there at the end of the window, so the stop must send
    SIGKILL. Returns the signals sent to it.
    """
    signals = install_group_fakes(monkeypatch, proc, group_alive_probes=10_000)
    clock = {"now": 100.0}

    def sleep(seconds: float) -> None:
        clock["now"] += seconds

    monkeypatch.setattr(child_module.time, "sleep", sleep)
    monkeypatch.setattr(child_module.time, "monotonic", lambda: clock["now"])
    return signals


# A three-level tree for the real-process lifetime tests. The leader starts a
# grandchild in its own process group. Each process writes its pid file only
# after it has installed its SIGTERM disposition, so a pid file means "ready".
#   argv: ROOT MODE [grand]
#   MODE "plain"   default SIGTERM action
#   MODE "cleanup" the grandchild runs a 0.2 s cleanup handler on SIGTERM
#   MODE "ignore"  every process ignores SIGTERM
# Every process sleeps at most 30 s so a leaked tree expires by itself.
TREE_SCRIPT = """
import os, signal, subprocess, sys, time
from pathlib import Path

root, mode = Path(sys.argv[1]), sys.argv[2]
is_grand = sys.argv[3:] == ["grand"]
if mode == "ignore":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if is_grand and mode == "cleanup":
    def on_term(signum, frame):
        time.sleep(0.2)
        (root / "grace-completed").write_text("cleaned")
        os._exit(0)
    signal.signal(signal.SIGTERM, on_term)
if not is_grand:
    subprocess.Popen([sys.executable, __file__, str(root), mode, "grand"])
name = "grand.pid" if is_grand else "child.pid"
(root / name).write_text(str(os.getpid()))
time.sleep(30)
"""

# Runs the wrapper script under a controlled SIGINT disposition: a test runner
# started in the background inherits SIGINT ignored, which would hide the case.
WRAPPER_LAUNCHER = """
import os, runpy, signal, sys
signal.signal(signal.SIGINT, signal.default_int_handler)
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(sys.argv[0]))
runpy.run_path(sys.argv[0], run_name="__main__")
"""

SIGCHLD_REAPING_LAUNCHER = """
import os, runpy, signal, sys, time
signal.signal(signal.SIGCHLD, signal.SIG_IGN)
signal.signal(signal.SIGINT, signal.default_int_handler)
real_getpgid = os.getpgid
paused = False
def slow_getpgid(pid):
    global paused
    if not paused:
        paused = True
        time.sleep(0.3)
    return real_getpgid(pid)
os.getpgid = slow_getpgid
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(sys.argv[0]))
runpy.run_path(sys.argv[0], run_name="__main__")
"""

# A leader that exits by itself while its grandchild keeps running.
#   argv: ROOT MODE LEADER_EXIT_CODE   (the grandchild gets "grand" instead of the code)
#   MODE "plain"  the grandchild keeps the default SIGTERM action and the output pipes
#   MODE "ignore" the grandchild ignores SIGTERM and keeps the output pipes
#   MODE "quiet"  the grandchild keeps the default action but closes its output pipes
#   MODE "setsid" the grandchild leaves the leader's group and keeps the output pipes
# The leader writes child.pid and exits only once the grandchild is ready. The
# grandchild sleeps at most 30 s so a leaked one expires by itself.
EARLY_EXIT_SCRIPT = """
import os, signal, subprocess, sys, time
from pathlib import Path

root, mode = Path(sys.argv[1]), sys.argv[2]
if sys.argv[3] == "grand":
    if mode == "ignore":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if mode == "setsid":
        os.setsid()
    if mode == "quiet":
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
    (root / "grand.pid").write_text(str(os.getpid()))
    time.sleep(30)
    sys.exit(0)
subprocess.Popen([sys.executable, __file__, str(root), mode, "grand"])
while not (root / "grand.pid").exists():
    time.sleep(0.01)
(root / "child.pid").write_text(str(os.getpid()))
sys.exit(int(sys.argv[3]))
"""


def start_wrapper(
    tmp_path: Path,
    script: str,
    *args: str,
    timeout: str | None = "30",
    launcher: str = WRAPPER_LAUNCHER,
) -> subprocess.Popen[bytes]:
    """Start the wrapper on `script ROOT ARGS...`, with a deadline unless `timeout` is None."""
    (tmp_path / "script.py").write_text(script, encoding="utf-8")
    command = [sys.executable, "-c", launcher, receipt_module.__file__, "run"]
    if timeout is not None:
        command += ["--timeout-seconds", timeout]
    command += [
        "--out-dir",
        str(tmp_path / "out"),
        "--",
        sys.executable,
        str(tmp_path / "script.py"),
        str(tmp_path),
        *args,
    ]
    return subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    """True for a running process. A zombie counts as dead: it has stopped."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return True
    return stat.rpartition(")")[2].split()[0] != "Z"


def pid_reaped(pid: int) -> bool:
    """True once the pid is gone. Unlike `pid_alive`, a zombie awaiting its parent is not gone."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def wait_until(predicate: Callable[[], bool], timeout: float = 10.0) -> bool:
    """Poll `predicate` every 20 ms until it holds or `timeout` seconds pass."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def tree_pids(root: Path) -> tuple[int | None, int | None]:
    return read_pid(root / "child.pid"), read_pid(root / "grand.pid")


def tree_ready(root: Path) -> bool:
    return all(pid is not None for pid in tree_pids(root))


def kill_tree(root: Path) -> None:
    """Test cleanup: SIGKILL whatever a failing test left running."""
    for pid in tree_pids(root):
        if pid is not None and pid_alive(pid):
            os.kill(pid, signal.SIGKILL)


def artifacts(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("*.log")) if out_dir.exists() else []


def artifact_from(stdout: str) -> Path:
    line = next(item for item in stdout.splitlines() if item.startswith("artifact: "))
    return Path(line.removeprefix("artifact: "))


@pytest.fixture
def default_sigterm():
    """Run with the default SIGTERM action, then put back whatever was there."""
    previous = signal.signal(signal.SIGTERM, signal.SIG_DFL)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


@pytest.fixture
def default_sighup():
    """Run with the default SIGHUP action, then put back whatever was there."""
    previous = signal.signal(signal.SIGHUP, signal.SIG_DFL)
    try:
        yield
    finally:
        signal.signal(signal.SIGHUP, previous)


@pytest.fixture
def default_cancel_signals():
    """Run with the default SIGTERM, SIGHUP, and Ctrl-C actions, then put back what was there."""
    defaults = {
        signal.SIGTERM: signal.SIG_DFL,
        signal.SIGHUP: signal.SIG_DFL,
        signal.SIGINT: signal.default_int_handler,
    }
    previous = {sig: signal.signal(sig, handler) for sig, handler in defaults.items()}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
