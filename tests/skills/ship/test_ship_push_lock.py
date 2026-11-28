"""Tests for the shared push lock ``ship_pr.py publish`` holds (PR #7737 Devin thread).

PRRT_kwDOQoWRls68cAlN, plus the lock defects later review rounds found: a
daemon the push leaves, a timed-out hook tree, and a signal mid-push.
"""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from tests.skills.ship.ship_helpers import publish, remote_has_branch, values

# The push lock is flock, which Windows does not have.
fcntl = pytest.importorskip("fcntl")


def _lock_file() -> Path:
    return (
        Path(os.environ["HOME"]) / "src" / "scratch" / "locks" / "push-lock-feat-ship-change.lock"
    )


def _hook(repo: Path, script: str) -> None:
    hook = repo / ".git" / "hooks" / "pre-push"
    hook.write_text(f"#!/bin/sh\n{script}", encoding="utf-8")
    hook.chmod(0o755)


def _alive(pid: int) -> bool:
    """True while ``pid`` runs; a zombie waiting for its reaper counts as gone."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True
    return stat.rsplit(")", 1)[1].split()[0] != "Z"


def _assert_dead(pid_file: Path) -> None:
    """The hook's child dies within a bounded poll, so a slow reaper cannot flake it."""
    pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 10
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(pid), "the hook's child outlived the push"


def _reap(pid_file: Path) -> None:
    if pid_file.exists():
        with contextlib.suppress(ProcessLookupError, ValueError):
            os.kill(int(pid_file.read_text(encoding="utf-8")), signal.SIGKILL)


def _assert_lock_free() -> None:
    fd = os.open(_lock_file(), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # raises BlockingIOError if held
    finally:
        os.close(fd)


_PROBE_HOOK = """\
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_RDWR)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = "free"
except BlockingIOError:
    state = "held"
open(sys.argv[2], "w").write(state)
"""


class TestPushLock:
    """PRRT_kwDOQoWRls68cAlN: publish holds the shared per-branch push lock."""

    def test_the_lock_is_held_for_the_whole_push(self, owner, scripts, capsys, tmp_path):
        repo, body = owner
        probe = tmp_path / "probe.py"
        probe.write_text(_PROBE_HOOK, encoding="utf-8")
        seen = tmp_path / "seen.txt"
        hook = repo / ".git" / "hooks" / "pre-push"
        hook.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{probe}" "{_lock_file()}" "{seen}"\n',
            encoding="utf-8",
        )
        hook.chmod(0o755)
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert values(lines, "PUSH_LOCK") == ["held"]
        assert seen.read_text(encoding="utf-8") == "held"
        assert remote_has_branch(tmp_path)

    def test_the_lock_is_released_after_the_push(self, owner, scripts, capsys):
        _repo, body = owner
        code, _lines = publish(scripts, capsys, body)
        assert code == 0
        _assert_lock_free()

    def test_a_push_already_in_flight_stops_without_pushing(self, owner, scripts, capsys, tmp_path):
        _repo, body = owner
        _lock_file().parent.mkdir(parents=True)
        fd = os.open(_lock_file(), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            code, lines = publish(scripts, capsys, body)
        finally:
            os.close(fd)
        assert code == 3
        assert lines[-1] == (
            "STOP: push-locked another push of this branch holds the shared push lock; "
            "rerun publish after it ends"
        )
        assert not remote_has_branch(tmp_path)

    def test_no_home_pushes_without_the_lock(self, owner, scripts, capsys, monkeypatch, tmp_path):
        _repo, body = owner
        monkeypatch.delenv("HOME")
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert values(lines, "PUSH_LOCK") == ["unavailable"]
        assert remote_has_branch(tmp_path)

    def test_an_unwritable_lock_directory_pushes_without_the_lock(
        self, owner, scripts, capsys, tmp_path
    ):
        _repo, body = owner
        home = Path(os.environ["HOME"])
        home.mkdir(parents=True)
        (home / "src").write_text("not a directory", encoding="utf-8")
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert values(lines, "PUSH_LOCK") == ["unavailable"]
        assert remote_has_branch(tmp_path)

    def test_a_host_without_flock_pushes_without_the_lock(
        self, owner, scripts, capsys, monkeypatch, tmp_path
    ):
        _repo, body = owner
        monkeypatch.setattr(scripts[0]._push_lock, "_fcntl", None)
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert values(lines, "PUSH_LOCK") == ["unavailable"]
        assert not _lock_file().exists()
        assert remote_has_branch(tmp_path)

    def test_a_daemon_a_hook_leaves_does_not_keep_the_lock(self, owner, scripts, capsys, tmp_path):
        """A credential cache or build server the push starts must not hold the lock."""
        repo, body = owner
        pid_file = tmp_path / "daemon.pid"
        _hook(repo, f"(sleep 60) </dev/null >/dev/null 2>&1 &\necho $! > '{pid_file}'\n")
        try:
            code, lines = publish(scripts, capsys, body)
            assert code == 0, lines
            assert _alive(int(pid_file.read_text(encoding="utf-8")))
            _assert_lock_free()
        finally:
            _reap(pid_file)

    def test_a_push_timeout_kills_the_hook_tree_before_the_lock_frees(
        self, owner, scripts, capsys, monkeypatch, tmp_path
    ):
        repo, body = owner
        pid_file = tmp_path / "hook-child.pid"
        _hook(repo, f"sleep 60 &\necho $! > '{pid_file}'\nwait\n")
        monkeypatch.setattr(scripts[3], "PUSH_TIMEOUT_SECONDS", 2)
        try:
            code, lines = publish(scripts, capsys, body)
            assert code == 3, lines
            assert lines[-1].startswith("STOP: push-failed git: timed out after 2s"), lines
            _assert_dead(pid_file)
            _assert_lock_free()
        finally:
            _reap(pid_file)

    @pytest.mark.parametrize(
        ("sig", "cause"),
        [
            (signal.SIGINT, "interrupted"),
            (signal.SIGTERM, "signal exit 143"),
            (signal.SIGHUP, "signal exit 129"),
            (signal.SIGQUIT, "signal exit 131"),
        ],
    )
    def test_a_signal_mid_push_kills_the_hook_tree_before_the_lock_frees(
        self, owner, scripts, capsys, tmp_path, sig, cause
    ):
        """Ctrl-C, Ctrl-backslash, SIGTERM, or a hangup must not leave the push running unlocked."""
        repo, body = owner
        pid_file = tmp_path / "hook-child.pid"
        trapped = (signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)
        before = [signal.getsignal(each) for each in trapped]
        script = f"sleep 60 &\necho $! > '{pid_file}'\nkill -{sig.name[3:]} {os.getpid()}\nwait\n"
        _hook(repo, script)
        try:
            code, lines = publish(scripts, capsys, body)
            assert code == 3, lines
            assert lines[-1] == (
                f"STOP: push-interrupted {cause}; check the remote, then rerun publish"
            ), lines
            _assert_dead(pid_file)
            _assert_lock_free()
            assert not remote_has_branch(tmp_path)
            assert [signal.getsignal(each) for each in trapped] == before
        finally:
            _reap(pid_file)

    def test_a_signal_mid_unlocked_push_still_kills_the_hook_tree(
        self, owner, scripts, capsys, monkeypatch, tmp_path
    ):
        """PUSH_LOCK: unavailable is no reason to orphan the push's hooks."""
        repo, body = owner
        monkeypatch.delenv("HOME")
        pid_file = tmp_path / "hook-child.pid"
        _hook(repo, f"sleep 60 &\necho $! > '{pid_file}'\nkill -TERM {os.getpid()}\nwait\n")
        try:
            code, lines = publish(scripts, capsys, body)
            assert code == 3, lines
            assert values(lines, "PUSH_LOCK") == ["unavailable"]
            assert lines[-1].startswith("STOP: push-interrupted signal exit 143"), lines
            _assert_dead(pid_file)
        finally:
            _reap(pid_file)

    def test_an_ignored_hangup_stays_ignored_and_the_push_lands(
        self, owner, scripts, capsys, tmp_path
    ):
        """Under nohup a hangup mid-push must not kill a push the operator kept alive."""
        repo, body = owner
        _hook(repo, f"kill -HUP {os.getpid()}\n")
        previous = signal.signal(signal.SIGHUP, signal.SIG_IGN)
        try:
            code, lines = publish(scripts, capsys, body)
            assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
        finally:
            signal.signal(signal.SIGHUP, previous)
        assert code == 0, lines
        assert values(lines, "PUSH") == ["pushed"]
        assert remote_has_branch(tmp_path)

    def test_a_failed_lock_call_pushes_without_the_lock(
        self, owner, scripts, capsys, monkeypatch, tmp_path
    ):
        _repo, body = owner

        class NoLocks:
            LOCK_EX, LOCK_NB = fcntl.LOCK_EX, fcntl.LOCK_NB

            @staticmethod
            def flock(fd, op):
                raise OSError(errno.ENOLCK, "No locks available")

        monkeypatch.setattr(scripts[0]._push_lock, "_fcntl", NoLocks)
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert values(lines, "PUSH_LOCK") == ["unavailable"]
        assert remote_has_branch(tmp_path)

    @pytest.mark.parametrize("branch", ["main", "feat/a/b", "fix-x/y"])
    def test_the_path_matches_the_commit_guard(self, scripts, monkeypatch, tmp_path, branch):
        guard_path = Path(__file__).resolve().parents[3] / "scripts" / "validation"
        spec = importlib.util.spec_from_file_location(
            "push_lock_guard", guard_path / "check_push_lock_before_commit.py"
        )
        assert spec is not None and spec.loader is not None
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        monkeypatch.setenv("HOME", str(tmp_path))
        assert scripts[0]._push_lock.push_lock_path(branch) == guard.lock_path_for_branch(branch)

    def test_a_branch_slug_replaces_each_slash(self, scripts, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        path = scripts[0]._push_lock.push_lock_path("feat/a/b")
        assert path == tmp_path / "src" / "scratch" / "locks" / "push-lock-feat-a-b.lock"
