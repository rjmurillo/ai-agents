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
    except (OSError, RuntimeError):
        return None
    current = real_root
    for part in SCRATCH_REL.parts:
        current = current / part
        if current.is_symlink():
            return None
        if not current.exists():
            if not create:
                return None
            try:
                current.mkdir(mode=0o700)
            except OSError:
                return None
        if not current.is_dir():
            return None
    try:
        resolved = current.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved != real_root / SCRATCH_REL:
        return None
    return resolved


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
    if not raw or raw.startswith("-") or raw.startswith("@"):
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    scratch = scratch_dir(root)
    if scratch is None:
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if scratch not in resolved.parents or not resolved.is_file():
        return None
    return resolved
