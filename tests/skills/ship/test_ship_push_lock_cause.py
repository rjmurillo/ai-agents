"""Each unavailable push lock cause reaches the caller and the publish output."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from tests.skills.ship.ship_helpers import publish, remote_has_branch, values

BRANCH = "feat/ship-change"
LOCK_NAME = "push-lock-feat-ship-change.lock"


def _arrange(monkeypatch, lock_mod, cause):
    if cause == "no-flock":
        monkeypatch.setattr(lock_mod, "_fcntl", None)
    elif cause == "no-home":
        monkeypatch.delenv("HOME")
    else:
        if lock_mod._fcntl is None:
            pytest.skip("requires flock")
        home = Path(os.environ["HOME"])
        if cause == "mkdir-failed":
            home.mkdir(parents=True)
            (home / "src").write_text("not a directory", encoding="utf-8")
        elif cause == "open-failed":
            (home / "src" / "scratch" / "locks" / LOCK_NAME).mkdir(parents=True)
        elif cause == "flock-failed":

            def fail(_fd, _op):
                raise OSError(errno.ENOLCK, "No locks available")

            monkeypatch.setattr(lock_mod._fcntl, "flock", fail)


CASES = [
    ("no-flock", "no-flock"),
    ("no-home", "no-home"),
    ("mkdir-failed", "mkdir-failed ENOTDIR"),
    ("open-failed", "open-failed EISDIR"),
    ("flock-failed", "flock-failed ENOLCK"),
]


@pytest.mark.parametrize(("cause", "expected"), CASES)
def test_cause_reaches_caller_and_preserves_state(scripts, fakes, monkeypatch, cause, expected):
    lock_mod = scripts[0]._push_lock
    if cause != "no-flock" and lock_mod._fcntl is None:
        pytest.skip("requires flock")
    _arrange(monkeypatch, lock_mod, cause)
    reported = []
    with lock_mod.push_lock(BRANCH, reported.append) as state:
        assert state == "unavailable"
    assert reported == [expected]


@pytest.mark.parametrize(("cause", "expected"), CASES)
def test_publish_reports_cause(owner, scripts, capsys, monkeypatch, tmp_path, cause, expected):
    _repo, body = owner
    lock_mod = scripts[0]._push_lock
    if cause != "no-flock" and lock_mod._fcntl is None:
        pytest.skip("requires flock")
    _arrange(monkeypatch, lock_mod, cause)
    code, lines = publish(scripts, capsys, body)
    assert code == 0, lines
    assert values(lines, "PUSH_LOCK") == ["unavailable"]
    assert values(lines, "PUSH_LOCK_CAUSE") == [expected]
    assert remote_has_branch(tmp_path)


def test_held_and_busy_do_not_report(scripts, fakes):
    lock_mod = scripts[0]._push_lock
    if lock_mod._fcntl is None:
        pytest.skip("requires flock")
    causes = []
    with lock_mod.push_lock(BRANCH, causes.append) as first:
        assert first == "held"
        with lock_mod.push_lock(BRANCH, causes.append) as second:
            assert second == "busy"
    assert causes == []
    with lock_mod.push_lock(BRANCH) as again:
        assert again == "held"


def test_unavailable_without_reporter(scripts, fakes, monkeypatch):
    _arrange(monkeypatch, scripts[0]._push_lock, "no-flock")
    with scripts[0].push_lock(BRANCH) as state:
        assert state == "unavailable"


def test_publish_held_has_no_cause(owner, scripts, capsys):
    _repo, body = owner
    if scripts[0]._push_lock._fcntl is None:
        pytest.skip("requires flock")
    code, lines = publish(scripts, capsys, body)
    assert code == 0, lines
    assert values(lines, "PUSH_LOCK") == ["held"]
    assert values(lines, "PUSH_LOCK_CAUSE") == []
