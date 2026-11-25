"""Scratch-directory guards for the ship scripts.

Every file a ship script writes or reads in the consumer's scratch directory
goes through these helpers. A symlinked component, or a scratch directory
that resolves outside the real repository root, is refused, never followed.

Stdlib only, Python 3.10 floor. ``_ship_common`` loads this file by path and
re-exports its names.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

SCRATCH_REL = Path(".project-toolkit") / "scratch"


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


def stored_int(root: Path, name: str, initial: int) -> int:
    """Return the integer stored in scratch file ``name``, storing ``initial`` first.

    The first call creates the file; later calls read it, so the value
    survives reruns. A symlinked, unreadable, or corrupt file is not trusted:
    the call returns ``initial`` without overwriting it.
    """
    directory = scratch_dir(root, create=True)
    if directory is None:
        return initial
    path = directory / name
    if not path.is_symlink() and path.is_file():
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return initial
    if not path.exists() and not path.is_symlink():
        _create_private(path, str(initial))
    return initial


def confine_body_file(raw: str, root: Path) -> Path | None:
    """Return the resolved body file when it is a regular file in the scratch dir."""
    if not raw or raw.startswith(("-", "@")) or (scratch := scratch_dir(root)) is None:
        return None
    try:
        resolved = (root / raw).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return resolved if scratch in resolved.parents and resolved.is_file() else None
