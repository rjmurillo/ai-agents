"""Tests for scripts/run_with_receipt.py: timed child lifetime and SIGTERM grace (issue #5851)."""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time

import pytest

from tests.run_with_receipt_helpers import (
    POSIX_ONLY,
    TREE_SCRIPT,
    _FakePopen,
    child_module,
    default_cancel_signals,  # noqa: F401
    default_sigterm,  # noqa: F401
    install_fake_popen,
    install_group_fakes,
    install_stubborn_group,
    kill_tree,
    pid_alive,
    py,
    receipt_module,
    start_wrapper,
    tree_pids,
    tree_ready,
    wait_until,
)


class TestTimedChildLifetime:
    """Blockers from the round 1 critic: cancellation and the SIGTERM grace window."""

    @POSIX_ONLY
    @pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT], ids=["sigterm", "sigint"])
    def test_cancelled_wrapper_stops_the_timed_child_tree(self, tmp_path, sig):
        wrapper = start_wrapper(tmp_path, TREE_SCRIPT, "plain")
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, grand = tree_pids(tmp_path)
            wrapper.send_signal(sig)
            wrapper.wait(timeout=10)
            assert wait_until(lambda: not pid_alive(child) and not pid_alive(grand)), (
                f"timed child tree survived wrapper cancellation by {sig.name}"
            )
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_sigterm_to_wrapper_exits_with_128_plus_signal(self, tmp_path):
        wrapper = start_wrapper(tmp_path, TREE_SCRIPT, "plain")
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            wrapper.send_signal(signal.SIGTERM)
            assert wrapper.wait(timeout=10) == 128 + signal.SIGTERM
        finally:
            if wrapper.poll() is None:
                wrapper.kill()
                wrapper.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_group_members_get_the_grace_window_after_the_leader_exits(self, tmp_path):
        (tmp_path / "tree.py").write_text(TREE_SCRIPT, encoding="utf-8")
        leader = subprocess.Popen(
            [sys.executable, str(tmp_path / "tree.py"), str(tmp_path), "cleanup"],
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, grand = tree_pids(tmp_path)
            child_module._terminate_child(leader)
            assert (tmp_path / "grace-completed").read_text(encoding="utf-8") == "cleaned"
            assert not pid_alive(child)
            assert wait_until(lambda: not pid_alive(grand))
        finally:
            leader.kill()
            leader.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_leader_is_reaped_during_the_grace_window(self, tmp_path):
        (tmp_path / "tree.py").write_text(TREE_SCRIPT, encoding="utf-8")
        leader = subprocess.Popen(
            [sys.executable, str(tmp_path / "tree.py"), str(tmp_path), "cleanup"],
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child_module._terminate_child(leader)
            assert leader.returncode == -signal.SIGTERM
        finally:
            leader.kill()
            leader.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_group_that_ignores_sigterm_is_killed_after_the_grace_window(self, tmp_path):
        (tmp_path / "tree.py").write_text(TREE_SCRIPT, encoding="utf-8")
        leader = subprocess.Popen(
            [sys.executable, str(tmp_path / "tree.py"), str(tmp_path), "ignore"],
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            assert wait_until(lambda: tree_ready(tmp_path)), "child tree never became ready"
            child, grand = tree_pids(tmp_path)
            started = time.monotonic()
            child_module._terminate_child(leader)
            elapsed = time.monotonic() - started
            assert wait_until(lambda: not pid_alive(child) and not pid_alive(grand))
            assert child_module._TERM_GRACE_S * 0.9 <= elapsed < child_module._TERM_GRACE_S + 5
        finally:
            leader.kill()
            leader.wait()
            kill_tree(tmp_path)

    @POSIX_ONLY
    def test_group_that_exits_on_sigterm_does_not_wait_out_the_window(self, tmp_path):
        leader = subprocess.Popen(
            py("import time; time.sleep(30)"), stdin=subprocess.DEVNULL, start_new_session=True
        )
        try:
            started = time.monotonic()
            child_module._terminate_child(leader)
            assert time.monotonic() - started < child_module._TERM_GRACE_S
            assert leader.returncode == -signal.SIGTERM
        finally:
            leader.kill()
            leader.wait()

    @POSIX_ONLY
    def test_grace_window_is_spent_while_group_members_remain(self, monkeypatch):
        proc = _FakePopen(waits=[-15])
        signals = install_group_fakes(monkeypatch, proc, group_alive_probes=3)
        sleeps: list[float] = []
        monkeypatch.setattr(child_module.time, "sleep", sleeps.append)
        monkeypatch.setattr(child_module.time, "monotonic", lambda: 100.0 + len(sleeps) * 0.25)

        child_module._terminate_child(proc)

        # The members left inside the window, so the group is empty and gets no SIGKILL.
        assert signals == [(proc.pid, signal.SIGTERM)]
        assert len(sleeps) == 3
        assert all(0 < step <= child_module._TERM_GRACE_S for step in sleeps)

    @POSIX_ONLY
    def test_grace_window_ends_at_its_deadline_even_if_members_remain(self, monkeypatch):
        proc = _FakePopen(waits=[-15])
        signals = install_group_fakes(monkeypatch, proc, group_alive_probes=10_000)
        clock = {"now": 100.0}

        def sleep(seconds: float) -> None:
            clock["now"] += seconds

        monkeypatch.setattr(child_module.time, "sleep", sleep)
        monkeypatch.setattr(child_module.time, "monotonic", lambda: clock["now"])

        child_module._terminate_child(proc)

        assert clock["now"] - 100.0 == pytest.approx(child_module._TERM_GRACE_S)
        assert signals == [(proc.pid, signal.SIGTERM), (proc.pid, signal.SIGKILL)]

    @POSIX_ONLY
    def test_interrupt_while_waiting_stops_a_timed_group(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[KeyboardInterrupt(), -15])
        signals = install_stubborn_group(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert signals == [(proc.pid, signal.SIGTERM), (proc.pid, signal.SIGKILL)]

    @POSIX_ONLY
    @pytest.mark.usefixtures("default_cancel_signals")
    def test_second_cancel_during_cleanup_does_not_preempt_the_group_signal(
        self, monkeypatch, tmp_path
    ):
        proc = _FakePopen(waits=[0])
        signals = install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        first_cancel = {"sent": False}
        real_wait = proc.wait

        def wait(timeout: float | None = None) -> int:
            if not first_cancel["sent"]:
                first_cancel["sent"] = True
                signal.raise_signal(signal.SIGTERM)
            return real_wait(timeout)

        cleanup_reached: list[bool] = []
        real_terminate = child_module._terminate_child

        def terminate(proc_arg, pgid=None) -> None:
            signal.raise_signal(signal.SIGHUP)
            cleanup_reached.append(True)
            real_terminate(proc_arg, pgid)

        monkeypatch.setattr(proc, "wait", wait)
        monkeypatch.setattr(child_module, "_terminate_child", terminate)

        with pytest.raises(SystemExit) as caught:
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert caught.value.code == 128 + signal.SIGHUP
        assert cleanup_reached == [True]
        assert signals == [(proc.pid, signal.SIGTERM)]

    def test_interrupt_while_waiting_stops_the_child_without_group_support(
        self, monkeypatch, tmp_path
    ):
        proc = _FakePopen(waits=[KeyboardInterrupt()])
        install_fake_popen(monkeypatch, proc)
        monkeypatch.setattr(child_module, "_SUPPORTS_PGROUP", False, raising=False)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30)

        assert proc.kill_calls == 1

    def test_interrupt_without_a_deadline_leaves_the_child_alone(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[KeyboardInterrupt()])
        install_fake_popen(monkeypatch, proc)
        signals = install_group_fakes(monkeypatch, proc)

        with pytest.raises(KeyboardInterrupt):
            receipt_module.run_command(["fake"], 16384, tmp_path)

        assert signals == []
        assert proc.kill_calls == 0

    @POSIX_ONLY
    @pytest.mark.usefixtures("default_sigterm")
    def test_timed_run_turns_sigterm_into_system_exit_then_restores_default(
        self, monkeypatch, tmp_path
    ):
        seen: list[object] = []

        class Probe(_FakePopen):
            def wait(self, timeout: float | None = None) -> int:
                seen.append(signal.getsignal(signal.SIGTERM))
                return super().wait(timeout)

        proc = Probe(waits=[0])
        install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0

        handler = seen[0]
        assert callable(handler)
        with pytest.raises(SystemExit) as info:
            handler(signal.SIGTERM, None)
        assert info.value.code == 128 + signal.SIGTERM
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL

    @pytest.mark.usefixtures("default_sigterm")
    def test_run_without_a_deadline_leaves_the_sigterm_action_alone(self, monkeypatch, tmp_path):
        seen: list[object] = []

        class Probe(_FakePopen):
            def wait(self, timeout: float | None = None) -> int:
                seen.append(signal.getsignal(signal.SIGTERM))
                return super().wait(timeout)

        install_fake_popen(monkeypatch, Probe(waits=[0]))
        assert receipt_module.run_command(["fake"], 16384, tmp_path) == 0
        assert seen == [signal.SIG_DFL]

    def test_timed_run_keeps_a_caller_installed_sigterm_handler(self, monkeypatch, tmp_path):
        def custom(_signum, _frame):
            return None

        previous = signal.signal(signal.SIGTERM, custom)
        try:
            proc = _FakePopen(waits=[0])
            install_group_fakes(monkeypatch, proc)
            install_fake_popen(monkeypatch, proc)
            assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0
            assert signal.getsignal(signal.SIGTERM) is custom
        finally:
            signal.signal(signal.SIGTERM, previous)

    def test_timed_run_off_the_main_thread_skips_the_sigterm_handler(self, monkeypatch, tmp_path):
        proc = _FakePopen(waits=[0])
        install_group_fakes(monkeypatch, proc)
        install_fake_popen(monkeypatch, proc)
        outcome: dict[str, object] = {}

        def work() -> None:
            try:
                outcome["code"] = receipt_module.run_command(
                    ["fake"], 16384, tmp_path, timeout_seconds=30
                )
            except BaseException as exc:
                outcome["error"] = exc

        thread = threading.Thread(target=work)
        thread.start()
        thread.join(timeout=10)
        assert outcome == {"code": 0}

    @pytest.mark.usefixtures("default_sigterm")
    def test_timed_run_without_group_support_skips_the_sigterm_handler(self, monkeypatch, tmp_path):
        monkeypatch.setattr(child_module, "_SUPPORTS_PGROUP", False, raising=False)
        seen: list[object] = []

        class Probe(_FakePopen):
            def wait(self, timeout: float | None = None) -> int:
                seen.append(signal.getsignal(signal.SIGTERM))
                return super().wait(timeout)

        install_fake_popen(monkeypatch, Probe(waits=[0]))
        assert receipt_module.run_command(["fake"], 16384, tmp_path, timeout_seconds=30) == 0
        assert seen == [signal.SIG_DFL]
