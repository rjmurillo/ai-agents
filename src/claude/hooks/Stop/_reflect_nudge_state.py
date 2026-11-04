"""Per-user state helpers for the reflect nudge: state root, marker directory, claim, prune.

Imported by ``invoke_reflect_nudge.py`` from the same directory; registered as a
hook nowhere. The state lives outside any repository, in an owner-only
directory, and every marker is claimed with an exclusive create.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

STATE_SUBDIR = "ai-agents-reflect-nudge"
GIT_ENTRY = ".git"
THRESHOLD_ENV = "AI_AGENTS_RETRO_NUDGE_THRESHOLD"
MARKER_MAX_AGE_SECONDS = 30 * 24 * 3600
MARKER_PRUNE_LIMIT = 500


def default_state_root(env: Mapping[str, str], os_name: str = os.name) -> Path:
    """Per-user state directory root, outside any repository."""
    if os_name == "nt":
        base = env.get("LOCALAPPDATA")
        if base and Path(base).is_absolute():
            return Path(base)
        return Path.home() / "AppData" / "Local"
    xdg = env.get("XDG_STATE_HOME")
    if xdg and Path(xdg).is_absolute():
        return Path(xdg)
    return Path.home() / ".local" / "state"


def resolve_state_root(
    env: Mapping[str, str], state_root: Path | None = None, os_name: str = os.name
) -> tuple[Path | None, str]:
    """AC-24: return ``(resolved_root, "")``, or ``(None, reason)`` when the root is refused.

    Refused: ``HOME`` unset or empty on POSIX, or any directory from the
    resolved root up to the filesystem root holds a ``.git`` entry (directory,
    file, or symlink). The walk uses ``lstat`` only and runs before any
    ``mkdir``, so a refusal creates nothing. It resolves symlinks first, so a
    symlinked root that lands in a repository is refused, and it climbs past
    a root that does not exist yet.

    A caller-supplied ``state_root`` is a test seam: it skips the ``HOME``
    check and still gets the walk. ``main()`` never supplies one.

    Accepted gap: a bare-repository dotfile setup (yadm, for example) leaves
    no ``.git`` entry, so the walk cannot see it.
    """
    if state_root is None:
        if os_name != "nt" and not env.get("HOME"):
            return None, "HOME unset, state root refused"
        state_root = default_state_root(env, os_name)
    try:
        resolved = state_root.resolve()
    except (OSError, RuntimeError):  # symlink loop or unreadable component
        return None, "state root unresolvable, refused"
    if _repository_entry_at_or_above(resolved):
        return None, "state root inside a repository, refused"
    return resolved, ""


def _repository_entry_at_or_above(path: Path) -> bool:
    """True when ``path`` or an ancestor holds a ``.git`` entry, or the check cannot finish."""
    for directory in (path, *path.parents):
        try:
            os.lstat(directory / GIT_ENTRY)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            return True  # cannot tell, so refuse
        return True
    return False


def safe_marker_dir(state_root: Path) -> Path | None:
    """Create or validate the 0o700 marker directory, refusing symlinks.

    The state root is resolved first, so a symlinked state root (a dotfile
    manager, for example) works and every later check runs on the real path.
    The repository walk runs on that real path before any ``mkdir`` (AC-24).
    The root is not mode-checked: a 0o002 umask makes group-writable roots
    normal. A directory another user pre-creates under it fails the owner and
    0o700 checks below, which is what protects the marker.
    """
    root = state_root.resolve()
    if _repository_entry_at_or_above(root):
        return None
    root.mkdir(parents=True, exist_ok=True)
    if not _owned_by_current_user(root.lstat()):
        return None
    target = root / STATE_SUBDIR
    try:
        target.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = target.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return None
    return target if _owned_by_current_user(info) and _is_private(info) else None


def _owned_by_current_user(info: os.stat_result) -> bool:
    return not hasattr(os, "getuid") or info.st_uid == os.getuid()


def _is_private(info: os.stat_result) -> bool:
    """True when group and other have no access (the 0o700 rule)."""
    return os.name == "nt" or (info.st_mode & 0o077) == 0


def claim(directory: Path, name: str, body: Mapping[str, Any]) -> bool:
    """Create ``directory/name`` exclusively; False when it already exists.

    O_EXCL makes the create atomic across overlapping Stop events and
    refuses to follow a symlink planted at the leaf.
    """
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(directory / name, flags, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(body, handle)
    return True


def prune_markers(directory: Path, now: float) -> None:
    """Remove markers older than MARKER_MAX_AGE_SECONDS, bounded per run."""
    for index, entry in enumerate(directory.iterdir()):
        if index >= MARKER_PRUNE_LIMIT:
            return
        try:
            if now - entry.lstat().st_mtime > MARKER_MAX_AGE_SECONDS:
                entry.unlink()
        except OSError:
            continue


def is_off(env: Mapping[str, str]) -> bool:
    """AC-12 off values (``0`` or ``off``), read here so a missing lib still honors them.

    The classifier's ``parse_threshold`` owns every other value; ``00``, ``+0``,
    and ``-0`` are not off.
    """
    raw = env.get(THRESHOLD_ENV)
    return raw is not None and raw.strip().lower() in {"0", "off"}
