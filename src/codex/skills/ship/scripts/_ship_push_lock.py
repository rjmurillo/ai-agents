"""The cross-session lock that serializes ``git push``, held only by the parent process.

Stdlib only, Python 3.10 floor. ``_ship_common`` loads this file by path and
re-exports ``push_lock``.
"""

from __future__ import annotations

import contextlib
import errno
import os
from collections.abc import Callable, Iterator
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


def push_lock_path(branch: str) -> Path | None:
    """Return the shared push lock file for ``branch``, or None when HOME is unset."""
    home = os.environ.get("HOME", "")
    if not home:
        return None
    return Path(home) / PUSH_LOCK_REL / f"push-lock-{branch.replace('/', '-')}.lock"


@contextlib.contextmanager
def push_lock(branch: str, report: Callable[[str], None] | None = None) -> Iterator[str]:
    """Take the shared push lock without waiting; yield held, busy, or unavailable.

    Children never inherit the lock. If unavailable, call ``report`` (when
    provided) with the first failing operation and, for OS errors, its errno name.
    """
    fd = -1
    state = "unavailable"
    cause = "no-flock"
    try:
        try:
            if _fcntl is not None:
                cause = "no-home"
                path = push_lock_path(branch)
                if path is not None:
                    cause = "mkdir-failed"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    cause = "open-failed"
                    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
                    cause = "flock-failed"
                    try:
                        _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                    except BlockingIOError:
                        state = "busy"
                    else:
                        state = "held"
        except OSError as exc:
            cause = f"{cause} {errno.errorcode.get(exc.errno, 'OSError')}"
        if state == "unavailable" and report is not None:
            report(cause)
        yield state
    finally:
        if fd >= 0:
            os.close(fd)
