"""Tests for scripts/run_with_receipt.py: process-group stop on every exit path (issue #5851)."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
import time

import pytest

from tests.run_with_receipt_helpers import (
    EARLY_EXIT_SCRIPT,
    POSIX_ONLY,
    SIGCHLD_REAPING_LAUNCHER,
    TREE_SCRIPT,
    _FakePopen,
    child_module,
    default_sighup,  # noqa: F401
    default_sigterm,  # noqa: F401
    install_fake_popen,
    install_group_fakes,
    install_stubborn_group,
    kill_tree,
    pid_alive,
    pid_reaped,
    py,
    receipt_module,
    start_wrapper,
    tree_pids,
    tree_ready,
    wait_until,
)


class TestTimedGroupStopOnEveryExit:
    """Round 2 findings: a timed run leaves no group member running, on any exit path."""

    @POSIX_ONLY
    @pytest.mark.parametrize("leader_code", [0, 5])
    def test_leader_exit_before_the_deadline_stops_the_grandchild(self, tmp_path, leader_code):
        wrapper = start_wrapper(tmp_path, EARLY_EXIT_SCRIPT, "plain", str(leader_code))
        try:
            started = time.monotonic()
            assert wrapper.wait(timeout=20) == leader_code
            assert time.monotonic() - started < 20
            assert tree_ready(tmp_path)
            _, grand = tree_pids(tmp_path)
            assert wait_until(lambda: not pid_alive(grand), timeout=5), (
                "a grandchild outlived the timed wrapper after the leader exited early"
            )
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_sigchld_auto_reap_does_not_hide_a_live_group(self, tmp_path):
        wrapper = start_wrapper(
            tmp_path,
            EARLY_EXIT_SCRIPT,
            "quiet",
            "0",
            launcher=SIGCHLD_REAPING_LAUNCHER,
        )
        try:
            assert wrapper.wait(timeout=20) == 0
            _, grand = tree_pids(tmp_path)
            assert grand is not None
            assert wait_until(lambda: not pid_alive(grand), timeout=5), (
                "auto-reaping the leader hid its live process group"
            )
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_grandchild_that_ignores_sigterm_is_killed_after_an_early_leader_exit(self, tmp_path):
        started = time.monotonic()
        wrapper = start_wrapper(tmp_path, EARLY_EXIT_SCRIPT, "ignore", "0")
        try:
            assert wrapper.wait(timeout=20) == 0
            elapsed = time.monotonic() - started
            _, grand = tree_pids(tmp_path)
            assert grand is not None
            assert wait_until(lambda: not pid_alive(grand), timeout=5), (
                "a grandchild that ignores SIGTERM survived the grace window"
            )
            # SIGTERM was ignored, so the whole grace window was spent before SIGKILL,
            # and the 30 s deadline was never reached.
            assert child_module._TERM_GRACE_S * 0.9 <= elapsed < 20
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_sigterm_while_the_group_is_being_stopped_still_kills_the_grandchild(self, tmp_path):
        wrapper = start_wrapper(tmp_path, EARLY_EXIT_SCRIPT, "ignore", "0")
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, grand = tree_pids(tmp_path)
            # The leader is reaped by the wrapper, so its wait is over. The grandchild
            # is in the leader's group, ignores SIGTERM, and holds the output pipes, so
            # the wrapper is now inside its SIGTERM grace window. The pipes stay open
            # until the SIGKILL at the end of that window, so no drain starts before it.
            assert wait_until(lambda: pid_reaped(child))
            wrapper.send_signal(signal.SIGTERM)
            assert wrapper.wait(timeout=20) == 128 + signal.SIGTERM
            assert wait_until(lambda: not pid_alive(grand), timeout=5), (
                "SIGTERM during the early-exit stop left the grandchild running"
            )
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_sighup_to_a_timed_wrapper_stops_the_tree_and_exits_129(self, tmp_path):
        wrapper = start_wrapper(tmp_path, TREE_SCRIPT, "plain")
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, grand = tree_pids(tmp_path)
            wrapper.send_signal(signal.SIGHUP)
            assert wrapper.wait(timeout=20) == 128 + signal.SIGHUP == 129
            assert wait_until(lambda: not pid_alive(child) and not pid_alive(grand)), (
                "timed child tree survived SIGHUP to the wrapper"
            )
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_untimed_run_leaves_a_surviving_grandchild_alone(self, tmp_path):
        wrapper = start_wrapper(tmp_path, EARLY_EXIT_SCRIPT, "quiet", "0", timeout=None)
        try:
            assert wrapper.wait(timeout=20) == 0
            _, grand = tree_pids(tmp_path)
            assert grand is not None
            assert pid_alive(grand), "an untimed run stopped a grandchild"
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_empty_group_at_exit_is_neither_signalled_nor_waited_on(self, monkeypatch, tmp_path):
        signals: list[tuple[int, int]] = []
        stops: list[int | None] = []
        real_killpg = os.killpg
        real_terminate = child_module._terminate_child

        def killpg(pgid: int, sig: int) -> None:
            if sig != 0:
                signals.append((pgid, sig))
            real_killpg(pgid, sig)

        def terminate(proc, pgid=None) -> None:
            stops.append(pgid)
            real_terminate(proc, pgid)

        monkeypatch.setattr(child_module.os, "killpg", killpg)
        monkeypatch.setattr(child_module, "_terminate_child", terminate)

        started = time.monotonic()
        assert receipt_module.run_command(py("pass"), 16384, tmp_path, timeout_seconds=30) == 0
        elapsed = time.monotonic() - started

        # An empty group costs one existence probe: no stop sequence, so no signal
        # and no grace window. The time bound is loose and only catches a stalled
        # return; the stop count is the exact check.
        assert stops == []
        assert signals == []
        assert elapsed < 20

    @POSIX_ONLY
    def test_group_stop_after_the_leader_exits_uses_the_spawn_group_id(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[0])
        signals = install_stubborn_group(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)

        def forbidden_getpgid(_pid: int) -> int:
            raise AssertionError("the spawn group id already equals the leader pid")

        monkeypatch.setattr(child_module.os, "getpgid", forbidden_getpgid, raising=False)

        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0

        assert signals == [(proc.pid, signal.SIGTERM), (proc.pid, signal.SIGKILL)]

    @POSIX_ONLY
    @pytest.mark.usefixtures("default_sighup")
    def test_timed_run_turns_sighup_into_system_exit_then_restores_default(
        self, monkeypatch, tmp_path
    ):
        seen: list[object] = []

        class Probe(_FakePopen):
            def wait(self, timeout: float | None = None) -> int:
                seen.append(signal.getsignal(signal.SIGHUP))
                return super().wait(timeout)

        proc = Probe(waits=[0])
        install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0

        handler = seen[0]
        assert callable(handler)
        with pytest.raises(SystemExit) as info:
            handler(signal.SIGHUP, None)
        assert info.value.code == 128 + signal.SIGHUP
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_DFL

    @POSIX_ONLY
    @pytest.mark.usefixtures("default_sighup")
    def test_sighup_action_is_restored_after_an_interrupted_timed_run(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[KeyboardInterrupt(), -15])
        install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert signal.getsignal(signal.SIGHUP) is signal.SIG_DFL

    @POSIX_ONLY
    @pytest.mark.parametrize("kind", ["ignored", "custom"])
    def test_timed_run_keeps_a_caller_chosen_sighup_action(self, monkeypatch, tmp_path, kind):
        def custom(_signum, _frame):
            return None

        chosen = signal.SIG_IGN if kind == "ignored" else custom
        previous = signal.signal(signal.SIGHUP, chosen)
        try:
            proc = _FakePopen(waits=[0])
            install_group_fakes(monkeypatch, proc)
            install_fake_popen(monkeypatch, proc)
            assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0
            assert signal.getsignal(signal.SIGHUP) is chosen
        finally:
            signal.signal(signal.SIGHUP, previous)

    @pytest.mark.usefixtures("default_sigterm")
    def test_timed_run_without_sighup_on_the_platform_still_installs_sigterm(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delattr(child_module.signal, "SIGHUP", raising=False)
        proc = _FakePopen(waits=[0])
        install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        seen: list[object] = []
        real_wait = proc.wait

        def wait(timeout: float | None = None) -> int:
            seen.append(signal.getsignal(signal.SIGTERM))
            return real_wait(timeout)

        monkeypatch.setattr(proc, "wait", wait)

        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0

        assert callable(seen[0])
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL


class TestPostSpawnWindowAndStoppedGroup:
    """Round 3 findings: no unguarded window after spawn, no signal to a stopped group."""

    @POSIX_ONLY
    @pytest.mark.usefixtures("default_sigterm")
    def test_cancel_between_spawn_and_the_guard_still_stops_the_child(self, monkeypatch, tmp_path):
        spawned: list[subprocess.Popen[bytes]] = []
        real_popen = subprocess.Popen
        fired: list[bool] = []
        real_target = child_module.Capture

        def popen(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            spawned.append(proc)
            return proc

        def cancel_once(*args, **kwargs):
            # A SIGTERM that lands right after the child was spawned.
            if not fired:
                fired.append(True)
                signal.raise_signal(signal.SIGTERM)
            return real_target(*args, **kwargs)

        monkeypatch.setattr(child_module.subprocess, "Popen", popen)
        monkeypatch.setattr(child_module, "Capture", cancel_once)
        try:
            with pytest.raises(SystemExit) as info:
                receipt_module.run_command(
                    py("import time; time.sleep(20)"), 16384, tmp_path, timeout_seconds=30
                )
            assert info.value.code == 128 + signal.SIGTERM
            assert len(spawned) == 1
            assert spawned[0].poll() is not None, (
                "a cancel after spawn left the timed child running"
            )
        finally:
            for proc in spawned:
                if proc.poll() is None:
                    with contextlib.suppress(OSError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()

    @POSIX_ONLY
    def test_group_that_dies_on_sigterm_at_the_deadline_gets_no_sigkill(
        self, monkeypatch, tmp_path
    ):
        signals: list[tuple[int, int]] = []
        real_killpg = os.killpg

        def killpg(pgid: int, sig: int) -> None:
            if sig != 0:
                signals.append((pgid, sig))
            real_killpg(pgid, sig)

        monkeypatch.setattr(child_module.os, "killpg", killpg)

        code = receipt_module.run_command(
            py("import time; time.sleep(30)"), 16384, tmp_path, timeout_seconds=1
        )

        assert code == child_module.EXIT_TIMEOUT
        assert [sig for _, sig in signals] == [signal.SIGTERM]
        assert len({pgid for pgid, _ in signals}) == 1

    @POSIX_ONLY
    @pytest.mark.parametrize(
        ("waits", "probes", "expected"),
        [
            ([0], 0, []),
            ([0], 1, [signal.SIGTERM]),
            ([subprocess.TimeoutExpired("fake", 30), -15], 1, [signal.SIGTERM]),
        ],
        ids=["group-found-empty", "group-stopped-by-sigterm", "group-stopped-at-the-deadline"],
    )
    def test_cancel_after_the_group_is_stopped_sends_no_further_signal(
        self, monkeypatch, tmp_path, waits, probes, expected
    ):
        proc = _FakePopen(waits=waits)
        signals = install_group_fakes(monkeypatch, proc, group_alive_probes=probes)
        install_fake_popen(monkeypatch, proc)

        class CancelOnJoin(threading.Thread):
            def join(self, timeout: float | None = None) -> None:
                raise KeyboardInterrupt

        monkeypatch.setattr(child_module.threading, "Thread", CancelOnJoin)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert signals == [(proc.pid, sig) for sig in expected]

    @POSIX_ONLY
    def test_cancel_during_the_early_exit_probe_still_stops_the_group(self, monkeypatch, tmp_path):
        # The leader exited by itself. A cancel at the first probe of its group
        # comes before any stop ran, so the unwind must still run the stop. If the
        # stopped flag were set before the stop, the group would be left alive.
        proc = _FakePopen(waits=[0])
        signals = install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        probes: list[int] = []

        def group_alive(pgid: int) -> bool:
            probes.append(pgid)
            if len(probes) == 1:
                raise KeyboardInterrupt
            return False

        monkeypatch.setattr(child_module, "_group_alive", group_alive)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert signals == [(proc.pid, signal.SIGTERM)]

    @POSIX_ONLY
    def test_sigterm_during_the_pipe_drain_exits_promptly(self, tmp_path):
        # The grandchild leaves the leader's group and keeps the output pipes, so
        # the wrapper sits in its pipe drain once the leader is reaped.
        wrapper = start_wrapper(tmp_path, EARLY_EXIT_SCRIPT, "setsid", "0")
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, _ = tree_pids(tmp_path)
            assert child is not None
            assert wait_until(lambda: pid_reaped(child))
            assert wrapper.poll() is None, "the wrapper did not wait for the held pipes"
            sent = time.monotonic()
            wrapper.send_signal(signal.SIGTERM)
            assert wrapper.wait(timeout=20) == 128 + signal.SIGTERM
            assert time.monotonic() - sent < child_module._PIPE_DRAIN_GRACE_S
            # The leader's group is empty: the grandchild left it.
            with pytest.raises(ProcessLookupError):
                os.killpg(child, 0)
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)
