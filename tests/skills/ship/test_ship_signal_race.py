"""A signal that lands while ``run(group=True)`` creates its child must still kill the child.

The child runs in its own session, so a signal to the script never reaches it.
A handler that raised inside ``Popen.__init__`` after the fork, or before the
``try`` that owns the cleanup, left the child alive after the push lock was
released. These tests land the signal at that exact point with no sleeps: a
``Popen`` subclass sends it to its own process right after the fork.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time

import pytest

from tests.skills.ship.ship_helpers import publish, remote_has_branch
from tests.skills.ship.test_ship_push_lock import _assert_lock_free, _hook

_SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]
_CANCEL = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)


def _popen_that_signals(*signums: int, only_push: bool = False, fail: bool = False):
    """A Popen subclass that signals this process right after it forks the child.

    ``fail`` signals first and then runs a binary that does not exist, so Popen
    itself fails. ``only_push`` leaves every other process this test starts alone.
    """

    class SignallingPopen(subprocess.Popen):
        pids: list[int] = []

        def __init__(self, command, **kwargs):
            if only_push and "push" not in command:
                super().__init__(command, **kwargs)
                return
            if fail:
                self._send()
                super().__init__(["/nonexistent-ship-binary"], **kwargs)
                return
            super().__init__(command, **kwargs)
            type(self).pids.append(self.pid)
            self._send()

        @staticmethod
        def _send() -> None:
            for signum in signums:
                os.kill(os.getpid(), signum)

    return SignallingPopen


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def _assert_group_dead(pgid: int) -> None:
    """The child's process group is gone within a bounded poll, so a slow reaper cannot flake it."""
    deadline = time.monotonic() + 10
    while _group_alive(pgid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _group_alive(pgid), "the child outlived the cancelled run"


def _reap_group(pids: list[int]) -> None:
    for pid in pids:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)


def _expect(sig: int):
    return pytest.raises(KeyboardInterrupt if sig == signal.SIGINT else SystemExit)


class TestSignalDuringCreation:
    @pytest.mark.parametrize("sig", _CANCEL)
    def test_the_child_dies_when_a_signal_lands_after_the_fork(self, scripts, monkeypatch, sig):
        common = scripts[0]
        popen = _popen_that_signals(sig)
        monkeypatch.setattr(common.subprocess, "Popen", popen)
        try:
            with _expect(sig) as raised:
                common.run(_SLEEPER, group=True)
            if sig != signal.SIGINT:
                assert raised.value.code == 128 + sig
            assert len(popen.pids) == 1
            _assert_group_dead(popen.pids[0])
        finally:
            _reap_group(popen.pids)

    def test_the_first_signal_wins_when_two_land(self, scripts, monkeypatch):
        common = scripts[0]
        popen = _popen_that_signals(signal.SIGTERM, signal.SIGHUP)
        monkeypatch.setattr(common.subprocess, "Popen", popen)
        try:
            with pytest.raises(SystemExit) as raised:
                common.run(_SLEEPER, group=True)
            assert raised.value.code == 128 + signal.SIGTERM
            _assert_group_dead(popen.pids[0])
        finally:
            _reap_group(popen.pids)

    @pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
    def test_a_failed_popen_still_raises_the_recorded_signal(self, scripts, monkeypatch, sig):
        common = scripts[0]
        monkeypatch.setattr(common.subprocess, "Popen", _popen_that_signals(sig, fail=True))
        with _expect(sig):
            common.run(_SLEEPER, group=True)

    def test_a_refused_command_still_raises_the_recorded_signal(self, scripts, monkeypatch):
        common = scripts[0]

        def refuse(_argv):
            os.kill(os.getpid(), signal.SIGTERM)

        monkeypatch.setattr(common._windows, "command", refuse)
        with pytest.raises(SystemExit) as raised:
            common.run(_SLEEPER, group=True)
        assert raised.value.code == 128 + signal.SIGTERM

    def test_the_signal_replaces_an_error_raised_while_it_was_deferred(self, scripts, monkeypatch):
        common = scripts[0]

        def explode(_argv):
            os.kill(os.getpid(), signal.SIGTERM)
            raise ValueError("boom")

        monkeypatch.setattr(common._windows, "command", explode)
        with pytest.raises(SystemExit) as raised:
            common.run(_SLEEPER, group=True)
        assert isinstance(raised.value.__context__, ValueError)

    @pytest.mark.parametrize(
        ("sig", "cause"),
        [(signal.SIGTERM, "signal exit 143"), (signal.SIGINT, "interrupted")],
    )
    def test_publish_stops_and_the_push_dies_before_the_lock_frees(
        self, owner, scripts, capsys, monkeypatch, tmp_path, sig, cause
    ):
        """The old handler raised in the constructor, so a push blocked in its hook ran unlocked."""
        repo, body = owner
        _hook(repo, "sleep 60\n")
        popen = _popen_that_signals(sig, only_push=True)
        monkeypatch.setattr(scripts[0].subprocess, "Popen", popen)
        try:
            code, lines = publish(scripts, capsys, body)
            assert code == 3, lines
            assert lines[-1] == (
                f"STOP: push-interrupted {cause}; check the remote, then rerun publish"
            ), lines
            assert len(popen.pids) == 1
            _assert_group_dead(popen.pids[0])
            _assert_lock_free()
            assert not remote_has_branch(tmp_path)
        finally:
            _reap_group(popen.pids)


_DISPOSITIONS = """\
import json, signal
print(json.dumps({
    "blocked": sorted(int(s) for s in signal.pthread_sigmask(signal.SIG_BLOCK, [])),
    "default": {
        name: signal.getsignal(getattr(signal, name)) == signal.SIG_DFL
        for name in ("SIGTERM", "SIGHUP", "SIGQUIT")
    },
    "interrupt": signal.getsignal(signal.SIGINT) is signal.default_int_handler,
}))
"""


class TestHandlers:
    def test_the_child_gets_no_blocked_signals_and_default_dispositions(self, scripts):
        done = scripts[0].run([sys.executable, "-c", _DISPOSITIONS], group=True)
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout) == {
            "blocked": [],
            "default": {"SIGTERM": True, "SIGHUP": True, "SIGQUIT": True},
            "interrupt": True,
        }

    def test_every_handler_is_restored_after_a_run(self, scripts):
        before = [signal.getsignal(each) for each in _CANCEL]
        scripts[0].run([sys.executable, "-c", "pass"], group=True)
        assert [signal.getsignal(each) for each in _CANCEL] == before

    def test_every_handler_is_restored_after_a_cancelled_run(self, scripts, monkeypatch):
        common = scripts[0]
        before = [signal.getsignal(each) for each in _CANCEL]
        popen = _popen_that_signals(signal.SIGINT)
        monkeypatch.setattr(common.subprocess, "Popen", popen)
        try:
            with pytest.raises(KeyboardInterrupt):
                common.run(_SLEEPER, group=True)
        finally:
            _reap_group(popen.pids)
        assert [signal.getsignal(each) for each in _CANCEL] == before

    @pytest.mark.parametrize("ignored", _CANCEL)
    def test_a_signal_the_caller_ignores_stays_ignored(self, scripts, monkeypatch, ignored):
        seen: dict[str, object] = {}

        class Spy(subprocess.Popen):
            def __init__(self, command, **kwargs):
                seen["during"] = signal.getsignal(ignored)
                super().__init__(command, **kwargs)

        monkeypatch.setattr(scripts[0].subprocess, "Popen", Spy)
        previous = signal.signal(ignored, signal.SIG_IGN)
        try:
            done = scripts[0].run([sys.executable, "-c", "pass"], group=True)
            assert done.returncode == 0
            assert seen["during"] is signal.SIG_IGN
            assert signal.getsignal(ignored) is signal.SIG_IGN
        finally:
            signal.signal(ignored, previous)

    def test_without_a_group_no_handler_is_touched(self, scripts, monkeypatch):
        calls: list[int] = []
        monkeypatch.setattr(signal, "signal", lambda signum, handler: calls.append(signum))
        done = scripts[0].run([sys.executable, "-c", "pass"])
        assert done.returncode == 0
        assert calls == []
