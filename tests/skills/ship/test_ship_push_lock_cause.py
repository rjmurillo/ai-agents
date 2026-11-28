"""``push_lock`` names why the lock is unavailable (issue #7807, gap 2).

``PUSH_LOCK: unavailable`` covered five causes with one word. Each cause now has
a token on the state the caller reads and a ``PUSH_LOCK_CAUSE`` line the user reads.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from tests.skills.ship.ship_helpers import publish, remote_has_branch, values

# The push lock is flock, which Windows does not have.
fcntl = pytest.importorskip("fcntl")

BRANCH = "feat/ship-change"
LOCK_NAME = "push-lock-feat-ship-change.lock"
SHOWN_DIR = "$HOME/src/scratch/locks"
SHOWN_FILE = f"{SHOWN_DIR}/{LOCK_NAME}"


def _locks() -> Path:
    return Path(os.environ["HOME"]) / "src" / "scratch" / "locks"


def _no_flock(monkeypatch, lock_mod) -> None:
    monkeypatch.setattr(lock_mod, "_fcntl", None)


def _no_home(monkeypatch, _lock_mod) -> None:
    monkeypatch.delenv("HOME")


def _mkdir_fails(_monkeypatch, _lock_mod) -> None:
    """A file where the ``src`` directory belongs: mkdir fails for root too."""
    home = Path(os.environ["HOME"])
    home.mkdir(parents=True)
    (home / "src").write_text("not a directory", encoding="utf-8")


def _open_fails(_monkeypatch, _lock_mod) -> None:
    """A directory at the lock file's path: open for writing fails for root too."""
    (_locks() / LOCK_NAME).mkdir(parents=True)


def _flock_fails(monkeypatch, lock_mod, code: int | None = errno.ENOLCK) -> list[int]:
    """Make the lock call fail with ``code``; return the descriptors it was given."""
    seen: list[int] = []

    class NoLocks:
        LOCK_EX, LOCK_NB = fcntl.LOCK_EX, fcntl.LOCK_NB

        @staticmethod
        def flock(fd, _op):
            seen.append(fd)
            raise OSError("no errno") if code is None else OSError(code, "refused")

    monkeypatch.setattr(lock_mod, "_fcntl", NoLocks)
    return seen


# (arrange, cause, detail): one row per cause in ``CAUSES``, in the same order.
CASES = [
    pytest.param(_no_flock, "no-flock", "this host has no fcntl.flock", id="no-flock"),
    pytest.param(_no_home, "no-home", "HOME is not set", id="no-home"),
    pytest.param(_mkdir_fails, "mkdir-failed", f"ENOTDIR at {SHOWN_DIR}", id="mkdir-failed"),
    pytest.param(_open_fails, "open-failed", f"EISDIR at {SHOWN_FILE}", id="open-failed"),
    pytest.param(_flock_fails, "flock-failed", f"ENOLCK at {SHOWN_FILE}", id="flock-failed"),
]


@pytest.fixture
def lock_mod(scripts, fakes):
    """The push lock module, with HOME on the fake home that ``fakes`` sets."""
    return scripts[0]._push_lock


class TestLockState:
    """What the caller reads from ``push_lock``."""

    def test_the_cases_cover_every_cause_in_order(self, lock_mod):
        assert tuple(case.values[1] for case in CASES) == lock_mod.CAUSES

    @pytest.mark.parametrize(("arrange", "cause", "detail"), CASES)
    def test_each_cause_has_its_own_token_and_detail(
        self, lock_mod, monkeypatch, arrange, cause, detail
    ):
        arrange(monkeypatch, lock_mod)
        with lock_mod.push_lock(BRANCH) as state:
            assert (state, state.cause, state.detail) == ("unavailable", cause, detail)

    def test_a_held_lock_has_no_cause(self, lock_mod):
        with lock_mod.push_lock(BRANCH) as state:
            assert (state, state.cause, state.detail) == ("held", "", "")
            assert isinstance(state, str) and type(str(state)) is str

    def test_a_busy_lock_has_no_cause(self, lock_mod):
        with lock_mod.push_lock(BRANCH) as first, lock_mod.push_lock(BRANCH) as second:
            assert first == "held"
            assert (second, second.cause, second.detail) == ("busy", "", "")

    def test_the_lock_frees_when_the_block_ends(self, lock_mod):
        with lock_mod.push_lock(BRANCH):
            pass
        with lock_mod.push_lock(BRANCH) as again:
            assert again == "held"

    def test_no_flock_wins_over_no_home_and_touches_no_file(self, lock_mod, monkeypatch):
        home = Path(os.environ["HOME"])
        _no_flock(monkeypatch, lock_mod)
        with lock_mod.push_lock(BRANCH) as state:
            assert state.cause == "no-flock"
        assert not home.exists()
        _no_home(monkeypatch, lock_mod)
        with lock_mod.push_lock(BRANCH) as state:
            assert state.cause == "no-flock"

    def test_an_empty_home_is_no_home(self, lock_mod, monkeypatch):
        monkeypatch.setenv("HOME", "")
        with lock_mod.push_lock(BRANCH) as state:
            assert (state, state.cause) == ("unavailable", "no-home")

    def test_a_symlink_at_the_lock_path_is_refused_and_not_followed(self, lock_mod, tmp_path):
        """O_NOFOLLOW: a planted link must not make publish open or create its target."""
        target = tmp_path / "victim.txt"
        _locks().mkdir(parents=True)
        (_locks() / LOCK_NAME).symlink_to(target)
        with lock_mod.push_lock(BRANCH) as state:
            assert (state.cause, state.detail) == ("open-failed", f"ELOOP at {SHOWN_FILE}")
        assert not target.exists()

    def test_the_detail_never_holds_the_real_home_path(self, lock_mod, monkeypatch):
        home = os.environ["HOME"]
        for arrange in (_mkdir_fails, _flock_fails):
            monkeypatch.setenv("HOME", f"{home}-{arrange.__name__}")
            arrange(monkeypatch, lock_mod)
            with lock_mod.push_lock(BRANCH) as state:
                assert state.detail.endswith(f" at {SHOWN_DIR}") or state.detail.endswith(
                    f" at {SHOWN_FILE}"
                )
                assert home not in state.detail

    def test_a_failed_lock_call_closes_the_file(self, lock_mod, monkeypatch):
        seen = _flock_fails(monkeypatch, lock_mod)
        with lock_mod.push_lock(BRANCH) as state:
            assert state.cause == "flock-failed"
            os.fstat(seen[0])  # open while the block runs
        with pytest.raises(OSError) as closed:
            os.fstat(seen[0])
        assert closed.value.errno == errno.EBADF

    def test_an_error_with_no_errno_still_names_the_cause(self, lock_mod, monkeypatch):
        _flock_fails(monkeypatch, lock_mod, code=None)
        with lock_mod.push_lock(BRANCH) as state:
            assert (state.cause, state.detail) == ("flock-failed", f"OSError at {SHOWN_FILE}")

    def test_an_errno_python_does_not_name_still_names_the_cause(self, lock_mod, monkeypatch):
        _flock_fails(monkeypatch, lock_mod, code=99999)
        with lock_mod.push_lock(BRANCH) as state:
            assert (state.cause, state.detail) == ("flock-failed", f"OSError at {SHOWN_FILE}")

    def test_a_slash_in_the_branch_shows_as_the_slug(self, lock_mod, monkeypatch):
        _flock_fails(monkeypatch, lock_mod)
        with lock_mod.push_lock("fix/a/b") as state:
            assert state.detail == f"ENOLCK at {SHOWN_DIR}/push-lock-fix-a-b.lock"


class TestPublishPrintsTheCause:
    """What the user reads from ``ship_pr.py publish``."""

    @pytest.mark.parametrize(("arrange", "cause", "detail"), CASES)
    def test_each_cause_prints_its_line_and_still_pushes(
        self, owner, scripts, capsys, monkeypatch, tmp_path, arrange, cause, detail
    ):
        _repo, body = owner
        arrange(monkeypatch, scripts[0]._push_lock)
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert values(lines, "PUSH_LOCK") == ["unavailable"]
        assert values(lines, "PUSH_LOCK_CAUSE") == [f"{cause} {detail}"]
        assert lines.index(f"PUSH_LOCK_CAUSE: {cause} {detail}") < lines.index("PUSH: pushed")
        assert remote_has_branch(tmp_path)

    def test_a_held_lock_prints_no_cause(self, owner, scripts, capsys, tmp_path):
        _repo, body = owner
        code, lines = publish(scripts, capsys, body)
        assert code == 0, lines
        assert values(lines, "PUSH_LOCK") == ["held"]
        assert values(lines, "PUSH_LOCK_CAUSE") == []
        assert remote_has_branch(tmp_path)

    def test_a_busy_lock_stops_with_no_cause_line(self, owner, scripts, capsys, tmp_path):
        _repo, body = owner
        with scripts[0].push_lock(BRANCH) as holder:
            assert holder == "held"
            code, lines = publish(scripts, capsys, body)
        assert code == 3
        assert lines[-1].startswith("STOP: push-locked ")
        assert values(lines, "PUSH_LOCK") == [] and values(lines, "PUSH_LOCK_CAUSE") == []
        assert not remote_has_branch(tmp_path)

    def test_the_json_output_carries_the_cause(self, owner, scripts, capsys, monkeypatch):
        _repo, body = owner
        _no_home(monkeypatch, scripts[0]._push_lock)
        code, lines = publish(scripts, capsys, body, "--output-format", "json")
        assert code == 0, lines
        data = scripts[0].parse_json("\n".join(lines))["Data"]
        assert data["PUSH_LOCK"] == "unavailable"
        assert data["PUSH_LOCK_CAUSE"] == "no-home HOME is not set"
