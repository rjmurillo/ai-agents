"""Cross-process locks that keep two controllers off one state_dir or artifact.

Two controllers on one `state_dir` each read the other's writes as tampering,
and both can pass the fresh-session check before either writes `split.json`.
Two controllers on one artifact, each with its own `state_dir`, restore over
each other's accepted bytes. So a run holds two locks for its whole life: one
on `state_dir`, and one on the artifact's real path.

Both are operating-system file locks: `fcntl.flock` on POSIX, `msvcrt.locking`
on Windows. The system drops either when the holder exits, so a killed run
leaves nothing that blocks the next one. A platform with neither refuses to
run rather than run unlocked.

The state lock file is removed on release. A waiter could have opened the
file just before that removal and then locked an inode no longer at the path,
so every acquire checks that the file it locked is still the one at the path,
and retries if not. Windows refuses to delete a file another process holds
open, so the check is POSIX only. Artifact lock files stay in place.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import importlib
import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _controller_config import ControllerError


def _optional(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


_FCNTL = _optional("fcntl")
_MSVCRT = _optional("msvcrt")
STATE_LOCK = "controller.lock"
# A waiter retries only when a holder removed the file between its open and
# its lock, which needs a holder to finish in that gap. A loop that keeps
# losing that race is a fault, not contention.
_ATTEMPTS = 8
# `msvcrt.locking` reports a byte someone else holds as EACCES; EDEADLOCK is
# the same condition under its CRT name.
_WINDOWS_BUSY = {errno.EACCES, getattr(errno, "EDEADLOCK", errno.EDEADLK)}


def _try_lock(handle: int, path: Path) -> bool:
    """Lock `handle` without waiting. False means another process holds it."""
    try:
        if _FCNTL is not None:
            _FCNTL.flock(handle, _FCNTL.LOCK_EX | _FCNTL.LOCK_NB)
        elif _MSVCRT is not None:
            # Locks one byte from the current position, which is 0: the file
            # is never read, written, or seeked.
            _MSVCRT.locking(handle, _MSVCRT.LK_NBLCK, 1)
        else:
            raise ControllerError(
                "this platform has neither fcntl nor msvcrt file locks; "
                "the controller will not run without one"
            )
    except BlockingIOError:
        return False
    except OSError as exc:
        if _FCNTL is None and exc.errno in _WINDOWS_BUSY:
            return False
        raise ControllerError(f"could not lock {path}: {exc.strerror or exc}") from exc
    return True


def _still_at(handle: int, path: Path) -> bool:
    if _FCNTL is None:
        return True
    try:
        here = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return False
    held = os.fstat(handle)
    return (here.st_dev, here.st_ino) == (held.st_dev, held.st_ino)


def _open(path: Path) -> int:
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        if os.path.islink(path):
            raise ControllerError(f"could not open lock file {path}: symbolic link")
        handle = os.open(path, flags, 0o600)
        try:
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ControllerError(f"could not open lock file {path}: expected one regular file")
        except BaseException:
            os.close(handle)
            raise
        return handle
    except OSError as exc:
        # ELOOP is what O_NOFOLLOW reports for a link planted at the path.
        raise ControllerError(f"could not open lock file {path}: {exc.strerror or exc}") from exc


def _release(handle: int, path: Path) -> None:
    if _FCNTL is not None:
        # Removed while still held, so no other process can lock this inode
        # and believe it holds the path.
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)
        os.close(handle)
        return
    with contextlib.suppress(OSError):
        if _MSVCRT is not None:
            _MSVCRT.locking(handle, _MSVCRT.LK_UNLCK, 1)
    os.close(handle)
    # Fails while another process has the file open, which is the waiter
    # that will lock it next; leaving the file then is correct.
    with contextlib.suppress(OSError):
        os.unlink(path)


@contextlib.contextmanager
def exclusive(path: Path, busy: str, *, keep_file: bool = False) -> Iterator[None]:
    """Hold an exclusive lock on `path`, or raise `ControllerError(busy)`."""
    for _ in range(_ATTEMPTS):
        handle = _open(path)
        try:
            locked = _try_lock(handle, path)
        except BaseException:
            os.close(handle)
            raise
        if not locked:
            os.close(handle)
            raise ControllerError(busy)
        if _still_at(handle, path):
            break
        os.close(handle)
    else:
        raise ControllerError(f"lock file {path} kept being replaced; refusing to run")
    try:
        yield
    finally:
        if keep_file:
            os.close(handle)
        else:
            _release(handle, path)


@contextlib.contextmanager
def state_lock(state: Path) -> Iterator[None]:
    """Hold the one-controller lock on `state`, creating it private if absent."""
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    busy = f"another controller is running against {state}; wait for it or use a fresh state_dir"
    with exclusive(state / STATE_LOCK, busy):
        yield


def artifact_lock_path(artifact: Path) -> Path:
    path = Path(os.path.realpath(artifact))
    # The directory anchors the lock. Case folding also covers case aliases
    # on filesystems where Python's normcase does not fold (such as APFS).
    key = hashlib.sha256(os.fsencode(path.name.casefold())).hexdigest()
    return path.with_name(f".eval-controller-{key}.lock")


@contextlib.contextmanager
def artifact_lock(artifact: Path) -> Iterator[None]:
    """Hold the one-controller lock on `artifact`, keyed by its real path."""
    busy = (
        f"another controller is running against {artifact}; "
        "run one controller per artifact, whatever its state_dir"
    )
    with exclusive(artifact_lock_path(artifact), busy, keep_file=True):
        yield
