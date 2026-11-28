"""The cross-session lock that serializes ``git push``, held only by the parent process.

Stdlib only, Python 3.10 floor. ``_ship_common`` loads this file by path and
re-exports ``push_lock``.
"""

from __future__ import annotations

import contextlib
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


def push_lock_path(branch: str) -> Path | None:
    """Return the shared push lock file for ``branch``, or None when HOME is unset."""
    home = os.environ.get("HOME", "")
    if not home:
        return None
    return Path(home) / PUSH_LOCK_REL / f"push-lock-{branch.replace('/', '-')}.lock"


@contextlib.contextmanager
def push_lock(branch: str) -> Iterator[str]:
    """Take the shared push lock for ``branch`` without waiting; yield its state.

    ``held`` means this process has it. Children never inherit it, so a daemon
    that git or a hook starts cannot keep it after the push. ``busy`` means
    another push of the branch holds it now. ``unavailable`` means this host
    cannot take it: no flock, no HOME, an unwritable lock directory, or a
    failed lock call.
    """
    path = push_lock_path(branch)
    fd = -1
    if _fcntl is not None and path is not None:
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    if fd < 0 or _fcntl is None:
        yield "unavailable"
        return
    state = "held"
    try:
        _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
    except BlockingIOError:
        state = "busy"
    except OSError:  # such as ENOLCK on a home directory with no lock support
        state = "unavailable"
    try:
        yield state
    finally:
        os.close(fd)
