"""Process-tree kill tests for the shared subprocess wrapper (issue #6412).

``_run_subprocess`` stops a timed-out child's whole process group: SIGTERM, a
grace window, then SIGKILL. A descendant that started its own session, as
``run_workflow_local_test`` does for ``gh act``, is outside that group, so the
nested test proves the wrapper forwards the stop to it.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from scripts.validation import subprocess_runner
from scripts.validation.subprocess_runner import _run_subprocess
from tests.validation import subprocess_runner_helpers
from tests.validation.subprocess_runner_helpers import (
    POSIX_ONLY,
    alive,
    child,
    read_pid,
    wait_dead,
)


class _FakeLeader:
    """Stand-in for a ``Popen`` whose pid the test picks."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        self.killed = True


class TestTerminate:
    @POSIX_ONLY
    def test_signal_failures_are_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A group that vanished between getpgid and killpg raises; do not propagate."""
        signals: list[int] = []

        def vanished(_pgid: int, sig: int) -> None:
            signals.append(sig)
            raise ProcessLookupError

        monkeypatch.setattr(os, "getpgid", lambda pid: 0 if pid == 0 else 4242)
        monkeypatch.setattr(os, "killpg", vanished)
        subprocess_runner._terminate(_FakeLeader(pid=1))
        assert signals == [signal.SIGTERM, signal.SIGKILL], "both signals are still attempted"

    @POSIX_ONLY
    def test_a_child_in_the_callers_group_is_killed_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No group to signal still means the direct child dies, or the gate hangs."""
        signals: list[int] = []
        monkeypatch.setattr(os, "killpg", lambda _pgid, sig: signals.append(sig))
        leader = _FakeLeader(pid=os.getpid())
        subprocess_runner._terminate(leader)
        assert signals == [], "the caller's own group must never be signalled"
        assert leader.killed is True

    @POSIX_ONLY
    @pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
    def test_sigkill_follows_an_interrupted_grace_wait(
        self, monkeypatch: pytest.MonkeyPatch, interrupt: type[BaseException]
    ) -> None:
        """Ctrl-C or a forwarded SIGTERM during the wait must not skip SIGKILL."""
        signals: list[int] = []

        class _Interrupted(_FakeLeader):
            def wait(self, timeout: float | None = None) -> int:
                raise interrupt

        monkeypatch.setattr(os, "getpgid", lambda pid: 0 if pid == 0 else 4242)
        monkeypatch.setattr(os, "killpg", lambda _pgid, sig: signals.append(sig))
        with pytest.raises(interrupt):
            subprocess_runner._terminate(_Interrupted(pid=1))
        assert signals == [signal.SIGTERM, signal.SIGKILL]

    @POSIX_ONLY
    def test_reaped_pid_is_ignored(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "pass"])  # subprocess-encoding: strict-ok
        proc.wait()
        subprocess_runner._terminate(proc)  # must not raise

    @POSIX_ONLY
    def test_sigkill_waits_for_the_leader_to_exit_after_sigterm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SIGKILL must follow the grace wait, not the SIGTERM call (LOW-001)."""
        events: list[str] = []

        class _Leader(_FakeLeader):
            def wait(self, timeout: float | None = None) -> int:
                events.append(f"wait:{timeout}")
                return 0

        monkeypatch.setattr(os, "getpgid", lambda pid: 0 if pid == 0 else 4242)
        monkeypatch.setattr(
            os, "killpg", lambda _pgid, sig: events.append(f"signal:{signal.Signals(sig).name}")
        )
        subprocess_runner._terminate(_Leader(pid=1))
        assert events == [
            "signal:SIGTERM",
            f"wait:{subprocess_runner._TERM_GRACE}",
            "signal:SIGKILL",
        ]

    @POSIX_ONLY
    def test_a_leader_that_ignores_sigterm_is_still_killed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess_runner, "_TERM_GRACE", 0.2)
        proc = subprocess.Popen(  # subprocess-encoding: strict-ok
            child(
                "import signal, time;signal.signal(signal.SIGTERM, signal.SIG_IGN);time.sleep(60)"
            ),
            start_new_session=True,
        )
        try:
            time.sleep(0.5)
            subprocess_runner._terminate(proc)
            assert proc.wait(timeout=5) == -signal.SIGKILL
        finally:
            if proc.poll() is None:
                proc.kill()


_SIGTERM_CLEANUP_CHILD = """
import signal, sys, time
marker, ready = sys.argv[1], sys.argv[2]
def bye(*_):
    open(marker, "w").write("cleaned")
    sys.exit(0)
signal.signal(signal.SIGTERM, bye)
open(ready, "w").write("1")
time.sleep(60)
"""


@POSIX_ONLY
class TestTimeoutGivesTheChildAGraceWindow:
    def test_sigterm_handler_runs_before_sigkill(self, tmp_path: Path) -> None:
        """A child that cleans up on SIGTERM gets to finish (LOW-001)."""
        marker, ready = tmp_path / "marker", tmp_path / "ready"
        script = tmp_path / "child.py"
        script.write_text(_SIGTERM_CLEANUP_CHILD, encoding="utf-8")
        exit_code, _stdout, stderr = _run_subprocess(
            [sys.executable, str(script), str(marker), str(ready)], timeout=4
        )
        assert ready.exists(), "child never installed its handler; raise the timeout"
        assert exit_code == -1
        assert "Command timed out after 4s" in stderr
        assert marker.read_text(encoding="utf-8") == "cleaned"


# Mirrors the pre-PR workflow-local-run gate: a wrapper that starts ``gh act`` in
# a session of its own (run_workflow_local_test._run). The group kill from the
# outer gate reaches only the wrapper, so the wrapper has to forward the stop.
_NESTED_WRAPPER = """
import sys
sys.path.insert(0, sys.argv[1])
import run_workflow_local_test as w
w._install_sigterm_handler()
w._run([sys.executable, "-c", sys.argv[3], sys.argv[2]], timeout=60)
"""

_GH_ACT_STAND_IN = (
    "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)"
)

# A gh act that ignores SIGTERM keeps the wrapper in its grace window until the
# wrapper sends SIGKILL. The outer grace must outlast that window, or the outer
# SIGKILL ends the wrapper first and this stand-in survives.
_GH_ACT_IGNORES_SIGTERM = (
    "import os, signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN);"
    " open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)"
)


@POSIX_ONLY
class TestNestedSessionKill:
    @pytest.mark.parametrize(
        "stand_in",
        [_GH_ACT_STAND_IN, _GH_ACT_IGNORES_SIGTERM],
        ids=["exits-on-sigterm", "ignores-sigterm"],
    )
    def test_session_leader_grandchild_dies_with_the_outer_timeout(
        self, tmp_path: Path, stand_in: str
    ) -> None:
        """HIGH-001: gh act runs in its own session, so killpg on the wrapper misses it."""
        validation_dir = str(Path(subprocess_runner.__file__).resolve().parent)
        pid_file = tmp_path / "gh-act.pid"
        script = tmp_path / "wrapper.py"
        script.write_text(_NESTED_WRAPPER, encoding="utf-8")
        grandchild = 0
        try:
            exit_code, _stdout, _stderr = _run_subprocess(
                [sys.executable, str(script), validation_dir, str(pid_file), stand_in],
                timeout=5,
            )
            grandchild = read_pid(pid_file)
            survived = not wait_dead(grandchild)
        finally:
            if grandchild and alive(grandchild):
                os.kill(grandchild, 9)
        assert exit_code == -1
        assert survived is False, f"gh-act stand-in {grandchild} outlived the outer timeout"


@POSIX_ONLY
def test_outer_grace_outlasts_the_wrapper_grace() -> None:
    """The wrapper needs its whole grace window plus time to send SIGKILL."""
    validation_dir = str(Path(subprocess_runner.__file__).resolve().parent)
    sys.path.insert(0, validation_dir)
    try:
        import run_workflow_local_test as wrapper
    finally:
        sys.path.remove(validation_dir)
    assert subprocess_runner._TERM_GRACE >= wrapper._TERM_GRACE + 1.0


# A caller of ``_run_subprocess`` that is itself stopped with SIGTERM. Its child
# runs in a session of its own, so a signal aimed at the caller (or the caller's
# group) never reaches the child unless the wrapper forwards it.
_SIGTERMED_CALLER = """
import sys
sys.path.insert(0, sys.argv[1])
from scripts.validation.subprocess_runner import _run_subprocess
_run_subprocess([sys.executable, "-c", sys.argv[3], sys.argv[2]], timeout=60)
"""


@POSIX_ONLY
class TestCallerStoppedWithSigterm:
    def test_child_dies_when_the_caller_gets_sigterm(self, tmp_path: Path) -> None:
        repo_root = str(Path(subprocess_runner.__file__).resolve().parents[2])
        pid_file = tmp_path / "child.pid"
        script = tmp_path / "caller.py"
        script.write_text(_SIGTERMED_CALLER, encoding="utf-8")
        caller = subprocess.Popen(  # subprocess-encoding: strict-ok
            [sys.executable, str(script), repo_root, str(pid_file), _GH_ACT_STAND_IN]
        )
        grandchild = 0
        try:
            grandchild = read_pid(pid_file)
            caller.send_signal(signal.SIGTERM)
            caller_code = caller.wait(timeout=15)
            survived = not wait_dead(grandchild)
        finally:
            if caller.poll() is None:
                caller.kill()
            if grandchild and alive(grandchild):
                os.kill(grandchild, 9)
        assert caller_code == 128 + signal.SIGTERM
        assert survived is False, f"child {grandchild} outlived its SIGTERMed caller"

    def test_a_handler_the_caller_installed_is_kept(self) -> None:
        def mine(_signum: int, _frame: object) -> None:
            return None

        previous = signal.signal(signal.SIGTERM, mine)
        try:
            exit_code, _out, _err = _run_subprocess([sys.executable, "-c", "pass"], timeout=10)
            assert signal.getsignal(signal.SIGTERM) is mine
        finally:
            signal.signal(signal.SIGTERM, previous)
        assert exit_code == 0

    def test_default_handler_is_restored_after_the_child_exits(self) -> None:
        previous = signal.signal(signal.SIGTERM, signal.SIG_DFL)
        try:
            exit_code, _out, _err = _run_subprocess([sys.executable, "-c", "pass"], timeout=10)
            assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
        finally:
            signal.signal(signal.SIGTERM, previous)
        assert exit_code == 0

    def test_a_worker_thread_runs_without_touching_signals(self) -> None:
        """``signal.signal`` raises off the main thread; the wrapper must not call it."""
        results: list[tuple[int, str, str]] = []
        errors: list[BaseException] = []

        def work() -> None:
            try:
                results.append(_run_subprocess([sys.executable, "-c", "pass"], timeout=10))
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=work)
        worker.start()
        worker.join(timeout=15)
        assert errors == []
        assert results and results[0][0] == 0


class TestAliveHelper:
    @POSIX_ONLY
    def test_zombie_is_dead_without_proc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """macOS has no /proc; ``ps`` must still report the zombie as dead."""
        monkeypatch.setattr(subprocess_runner_helpers, "_proc_state", lambda _pid: None)
        proc = subprocess.Popen([sys.executable, "-c", "pass"])  # subprocess-encoding: strict-ok
        try:
            assert wait_dead(proc.pid), "an exited, unreaped child must read as dead"
        finally:
            proc.wait()

    @POSIX_ONLY
    def test_running_process_is_alive_without_proc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subprocess_runner_helpers, "_proc_state", lambda _pid: None)
        assert alive(os.getpid()) is True
