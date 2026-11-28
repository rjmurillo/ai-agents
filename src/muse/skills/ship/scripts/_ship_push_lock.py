"""The cross-session lock that serializes ``git push``, held only by the parent process.

Stdlib only, Python 3.10 floor. ``_ship_common`` loads this file by path and
re-exports ``push_lock``.
"""

from __future__ import annotations

import contextlib
import errno
import os
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

_fcntl: ModuleType | None
try:
    import fcntl as _fcntl_module

    _fcntl = _fcntl_module
except ImportError:  # pragma: no cover - Windows has no fcntl and no flock
    _fcntl = None

# The one shared push lock path: $HOME/src/scratch/locks/push-lock-<slug>.lock,
# where the slug is the branch with each / as -. The commit guard reads it.
PUSH_LOCK_REL = Path("src") / "scratch" / "locks"

# Why the lock is unavailable, in the order the checks run. The first cause wins.
CAUSES = ("no-flock", "no-home", "mkdir-failed", "open-failed", "flock-failed")
# The lock directory as the user reads it. The real home path never reaches the output.
_SHOWN_DIR = f"$HOME/{PUSH_LOCK_REL.as_posix()}"


class LockState(str):
    """A push lock state: ``held``, ``busy``, or ``unavailable``.

    It compares equal to that plain string. ``cause`` is one of ``CAUSES`` when
    the state is ``unavailable`` and empty otherwise. ``detail`` says what to
    fix: the errno name and the path under ``$HOME``, or the missing host feature.
    """

    __slots__ = ("cause", "detail")
    cause: str
    detail: str

    def __new__(cls, state: str, cause: str = "", detail: str = "") -> LockState:
        self = super().__new__(cls, state)
        self.cause = cause
        self.detail = detail
        return self


def push_lock_path(branch: str) -> Path | None:
    """Return the shared push lock file for ``branch``, or None when HOME is unset."""
    home = os.environ.get("HOME", "")
    if not home:
        return None
    return Path(home) / PUSH_LOCK_REL / f"push-lock-{branch.replace('/', '-')}.lock"


def _failed(cause: str, exc: OSError, shown: str) -> LockState:
    """The ``unavailable`` state for a failed system call on the path ``shown``."""
    name = errno.errorcode.get(exc.errno or 0, "OSError")
    return LockState("unavailable", cause, f"{name} at {shown}")


def _take(branch: str) -> tuple[LockState, int]:
    """Try the lock once; return its state and the open descriptor, or -1 for none.

    A host with no flock touches no file. A busy or failed lock call keeps the
    descriptor open, so the caller closes it.
    """
    flock = _fcntl
    if flock is None:
        return LockState("unavailable", "no-flock", "this host has no fcntl.flock"), -1
    path = push_lock_path(branch)
    if path is None:
        return LockState("unavailable", "no-home", "HOME is not set"), -1
    shown = f"{_SHOWN_DIR}/{path.name}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _failed("mkdir-failed", exc, _SHOWN_DIR), -1
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError as exc:
        return _failed("open-failed", exc, shown), -1
    try:
        flock.flock(fd, flock.LOCK_EX | flock.LOCK_NB)
    except BlockingIOError:
        return LockState("busy"), fd
    except OSError as exc:  # such as ENOLCK on a home directory with no lock support
        return _failed("flock-failed", exc, shown), fd
    return LockState("held"), fd


@contextlib.contextmanager
def push_lock(branch: str) -> Iterator[LockState]:
    """Take the shared push lock for ``branch`` without waiting; yield its state.

    ``held`` means this process has it. Children never inherit it, so a daemon
    that git or a hook starts cannot keep it after the push. ``busy`` means
    another push of the branch holds it now. ``unavailable`` means this host
    cannot take it, and the state's ``cause`` names which of ``CAUSES`` applies:
    no flock, no HOME, a failed mkdir of the lock directory, a failed open of
    the lock file, or a failed lock call.
    """
    state, fd = _take(branch)
    try:
        yield state
    finally:
        if fd >= 0:
            os.close(fd)
