"""Scratch-directory guards for the ship scripts.

Every file a ship script writes or reads in the consumer's scratch directory
goes through these helpers. A symlinked component, or a scratch directory
that resolves outside the real repository root, is refused, never followed.

Stdlib only, Python 3.10 floor. ``_ship_common`` loads this file by path and
re-exports its names.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

_fcntl: ModuleType | None
try:
    import fcntl as _fcntl_module

    _fcntl = _fcntl_module
except ImportError:  # pragma: no cover - Windows has no fcntl and no flock
    _fcntl = None

SCRATCH_REL = Path(".project-toolkit") / "scratch"
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
    """Hold the shared push lock for ``branch`` without waiting; yield its state.

    ``held`` means this process holds it until the block ends. ``busy`` means
    another push of the branch holds it now. ``unavailable`` means this host
    cannot take it: no flock, no HOME, or an unwritable lock directory.
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
    try:
        yield state
    finally:
        os.close(fd)  # closing this only descriptor also releases the flock


def scratch_dir(root: Path, create: bool = False) -> Path | None:
    """Return the real scratch directory under ``root``, or None when it is unsafe.

    Each component (``.project-toolkit`` and ``scratch``) must be a real
    directory, not a symlink, and the result must resolve under the real
    repository root. A symlinked component could point the confinement anchor
    anywhere on disk, so it is refused rather than followed.
    """
    try:
        real_root = root.resolve(strict=True)
        current = real_root
        for part in SCRATCH_REL.parts:
            current /= part
            if current.is_symlink():
                return None
            if create and not current.exists():
                current.mkdir(mode=0o700)
            if not current.is_dir():
                return None
        resolved = current.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return resolved if resolved == real_root / SCRATCH_REL else None


def _create_private(path: Path, text: str) -> bool:
    """Create ``path`` as a new owner-only file holding ``text``; False on any failure."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        return False
    return True


def write_private(root: Path, prefix: str, suffix: str, text: str) -> Path | None:
    """Write ``text`` to a new owner-only file in the scratch directory."""
    directory = scratch_dir(root, create=True)
    if directory is None:
        return None
    path = directory / f"{prefix}-{uuid.uuid4().hex}{suffix}"
    return path if _create_private(path, text) else None


def stored_int(root: Path, name: str, initial: int, *, store: bool = True) -> int | None:
    """Return the integer stored in scratch file ``name``, else ``initial``.

    A symlinked, unreadable, or corrupt file is not trusted. Read-only
    (``store`` false), the call then returns ``initial`` and leaves the file.
    With ``store`` true, it replaces that file, or creates a missing one,
    holding ``initial``, so later calls read the same value. It returns None
    when the value could not be stored, so a caller can fail closed.
    """
    directory = scratch_dir(root, create=store)
    if directory is None:
        return None if store else initial
    path = directory / name
    if not path.is_symlink() and path.is_file():
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pass
    if not store:
        return initial
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()  # removes a link itself, never its target
    except OSError:
        return None
    return initial if _create_private(path, str(initial)) else None


def confine_body_file(raw: str, root: Path) -> Path | None:
    """Return the resolved body file when it is a regular file in the scratch dir."""
    if not raw or raw.startswith(("-", "@")) or (scratch := scratch_dir(root)) is None:
        return None
    try:
        resolved = (root / raw).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return resolved if scratch in resolved.parents and resolved.is_file() else None
