"""A second cancelling signal during the cleanup must not skip the process-group kill (CWE-364).

The raising handler switches back to recording, kills the child's group, and only then
raises, so no later signal can leave the child running after the push lock is released.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest

from tests.skills.ship.test_ship_signal_race import (
    _CANCEL,
    _SLEEPER,
    _assert_group_dead,
    _expect,
    _popen_that_signals,
    _reap_group,
)


def _signal_before_first_kill(monkeypatch, common, signum: int) -> dict[str, list[int]]:
    """Deliver ``signum`` to this process just before the first SIGKILL of a process group.

    That is the window between the cleanup starting and ``os.killpg`` running. ``sent``
    holds the group id once the signal went out. ``escaped`` holds it when a handler
    raised out of that window, so the real ``killpg`` would have been skipped. The helper
    then kills the group anyway, so the test never waits on a live child.
    """
    real = os.killpg
    seen: dict[str, list[int]] = {"sent": [], "escaped": []}

    def killpg(pgid, sig):
        if sig == signal.SIGKILL and not seen["sent"]:
            seen["sent"].append(pgid)
            try:
                os.kill(os.getpid(), signum)
            except BaseException:
                seen["escaped"].append(pgid)
                real(pgid, sig)
                raise
        real(pgid, sig)

    monkeypatch.setattr(common._signals.os, "killpg", killpg)
    return seen


def _run_catching(common, *args, **kwargs):
    """Run a grouped command; return the exception it raised, or its result."""
    try:
        return common.run(_SLEEPER, *args, group=True, **kwargs)
    except BaseException as exc:
        return exc


class TestSecondSignalDuringCleanup:
    """CWE-364: a signal that lands inside the cleanup must not skip ``killpg``."""

    def test_a_second_signal_before_killpg_still_kills_the_group(self, scripts, monkeypatch):
        common = scripts[0]
        popen = _popen_that_signals(signal.SIGINT)
        monkeypatch.setattr(common.subprocess, "Popen", popen)
        seen = _signal_before_first_kill(monkeypatch, common, signal.SIGTERM)
        try:
            outcome = _run_catching(common)
            assert seen["sent"] == popen.pids, "the second signal was never sent"
            assert seen["escaped"] == [], "a handler raised before killpg ran"
            _assert_group_dead(popen.pids[0])
            assert isinstance(outcome, KeyboardInterrupt), repr(outcome)
        finally:
            _reap_group(popen.pids)

    def test_a_second_signal_during_the_timeout_kill_still_kills_and_is_then_raised(
        self, scripts, monkeypatch
    ):
        common = scripts[0]
        seen = _signal_before_first_kill(monkeypatch, common, signal.SIGTERM)
        outcome = _run_catching(common, timeout=0.3)
        try:
            assert len(seen["sent"]) == 1, "the timeout path never reached killpg"
            assert seen["escaped"] == [], "a handler raised before killpg ran"
            _assert_group_dead(seen["sent"][0])
            assert isinstance(outcome, SystemExit), repr(outcome)
            assert outcome.code == 128 + signal.SIGTERM
        finally:
            _reap_group(seen["sent"])


def _sleeper_group() -> subprocess.Popen:
    return subprocess.Popen(_SLEEPER, start_new_session=True)


class TestCancellation:
    @pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
    def test_a_signal_in_raising_mode_kills_the_child_before_it_raises(self, scripts, sig):
        signals = scripts[0]._signals
        child = _sleeper_group()
        try:
            with signals.Cancellation() as cancel:
                cancel.arm(child)
                with _expect(sig) as raised:
                    os.kill(os.getpid(), sig)
                    time.sleep(5)  # the handler raises at once; the sleep never completes
                if sig != signal.SIGINT:
                    assert raised.value.code == 128 + sig
                assert child.wait(timeout=10) == -signal.SIGKILL
        finally:
            _reap_group([child.pid])

    def test_a_signal_after_the_child_exited_raises_without_a_kill(self, scripts, monkeypatch):
        signals = scripts[0]._signals
        child = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        child.wait()
        monkeypatch.setattr(signals.os, "killpg", pytest.fail)
        with signals.Cancellation() as cancel:
            cancel.arm(child)
            with pytest.raises(SystemExit):
                os.kill(os.getpid(), signal.SIGTERM)
                time.sleep(5)  # the handler raises at once; the sleep never completes

    def test_a_signal_after_kill_child_is_recorded_not_raised(self, scripts):
        signals = scripts[0]._signals
        child = _sleeper_group()
        try:
            with signals.Cancellation() as cancel:
                cancel.arm(child)
                signals.kill_child(child, cancel)
                os.kill(os.getpid(), signal.SIGTERM)
                child.wait(timeout=10)
                with pytest.raises(SystemExit) as raised:
                    cancel.raise_pending()
                assert raised.value.code == 128 + signal.SIGTERM
        finally:
            _reap_group([child.pid])

    def test_kill_child_without_a_cancellation_leaves_the_group_alone(self, scripts, monkeypatch):
        signals = scripts[0]._signals
        monkeypatch.setattr(signals.os, "killpg", pytest.fail)
        child = subprocess.Popen(_SLEEPER)
        signals.kill_child(child, None)
        assert child.wait(timeout=10) == -signal.SIGKILL

    @pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
    def test_exit_raises_a_recorded_signal_when_nothing_is_propagating(self, scripts, sig):
        signals = scripts[0]._signals
        with _expect(sig) as raised, signals.Cancellation():
            os.kill(os.getpid(), sig)
        if sig != signal.SIGINT:
            assert raised.value.code == 128 + sig

    def test_exit_keeps_an_exception_that_is_propagating(self, scripts):
        signals = scripts[0]._signals
        before = [signal.getsignal(each) for each in _CANCEL]
        with pytest.raises(ValueError, match="boom"), signals.Cancellation():
            os.kill(os.getpid(), signal.SIGTERM)
            raise ValueError("boom")
        assert [signal.getsignal(each) for each in _CANCEL] == before
