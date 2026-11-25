#!/usr/bin/env python3
"""
_path_guard.py - Shared CWE-22 containment and CLI parsing for skill validators

These helpers are used by:
- quick_validate.py (packaging validation)
- validate-skill.py (full structural validation)

Both validators confine the target skill to a trusted root (the current working
directory, or the directory passed with ``--root``). Keeping the containment
logic and the argument parser here means the two cannot drift.
"""

import os
from pathlib import Path
from typing import Protocol


class PathModule(Protocol):
    """Structural type for the ``os.path`` surface ``is_within`` needs.

    Lets tests substitute ``posixpath`` or ``ntpath`` for the host ``os.path``
    while keeping a precise return type (``commonpath`` yields ``str``, so the
    containment comparison stays ``bool`` instead of decaying to ``Any``).
    """

    sep: str
    altsep: str | None

    def commonpath(self, paths: list[str], /) -> str: ...

    def splitdrive(self, p: str, /) -> tuple[str, str]: ...


def is_within(child: str, root: str, pathmod: PathModule = os.path) -> bool:
    """Return True when case-normalized realpath ``child`` is ``root`` or nested inside it.

    Both arguments must already be ``os.path.normcase(os.path.realpath(...))``
    results. Containment is decided by ``os.path.commonpath`` rather than a
    separator-appended prefix match, because ``os.path.join(root, "")`` does NOT
    append a separator to a bare drive root (``C:\\``) or a bare UNC share root
    (``\\\\server\\share``) on Windows. With the old prefix match a sibling that
    merely shares a string prefix (``C:\\evil`` under ``C:\\``,
    ``\\\\server\\shareevil`` under ``\\\\server\\share``) passed the guard and
    escaped the CWD sandbox (CWE-22). ``commonpath`` compares whole path
    components, so only true descendants match.

    ``commonpath`` raises ``ValueError`` when the two paths cannot form a common
    base. Different drives or drive-vs-UNC genuinely mean "not contained". But a
    bare UNC share root (``\\\\server\\share``) has an empty root-relative part,
    so ``ntpath`` treats it as rootless and refuses to mix it with a rooted
    child, even though real descendants of that share ARE contained. On that
    ``ValueError`` the guard decides by drive identity: contained only when child
    and root share the same drive/share and root is that drive/share root itself.
    This keeps the CWE-22 sibling-share rejection while no longer false-rejecting
    a legitimate SKILL.md that lives directly under a bare share root.

    ``pathmod`` is injected only so tests can pin ``posixpath`` or ``ntpath`` and
    exercise both platforms' root semantics deterministically on any host;
    production always uses the default ``os.path``.
    """
    if child == root:
        return True
    try:
        return pathmod.commonpath([child, root]) == root
    except ValueError:
        # See the docstring: distinguish a genuine different-drive mismatch from
        # a bare UNC share root that ``ntpath`` cannot mix with a rooted child.
        child_drive, _ = pathmod.splitdrive(child)
        root_drive, root_rel = pathmod.splitdrive(root)
        if child_drive != root_drive:
            return False
        separators = {pathmod.sep, pathmod.altsep or pathmod.sep}
        return root_rel == "" or root_rel in separators


def contained_realpath(target: Path, root: str) -> str | None:
    """Resolve ``target`` and return its real path only if it stays within ``root``.

    ``root`` must already be an ``os.path.normcase(os.path.realpath(...))``
    result. Returns ``None`` when the resolved target escapes ``root`` (via a
    symlink or ``..``), letting the caller reject an out-of-root read (CWE-22).

    The containment check compares case-normalized paths so a Windows path that
    differs only by drive-letter or component casing (``C:\\`` vs ``c:\\``) is not
    misclassified as an escape. The original real path is returned unchanged so
    the caller reads the exact resolved target.
    """
    real = os.path.realpath(target)
    real_cmp = os.path.normcase(real)
    if is_within(real_cmp, root):
        return real
    return None


def resolve_root(root: str | None) -> str:
    """Return the case-normalized real path of ``root``, or of the cwd when ``None``.

    This is the form ``is_within`` and ``contained_realpath`` expect for their
    ``root`` argument.
    """
    return os.path.normcase(os.path.realpath(root if root is not None else os.getcwd()))


def parse_args(argv: list[str]) -> tuple[str, str | None] | None:
    """Parse ``<skill_directory> [--root DIR]``; return None on a usage error."""
    skill_path: str | None = None
    root: str | None = None
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--root":
            if not args or root is not None:
                return None
            root = args.pop(0)
        elif arg.startswith("--root="):
            if root is not None:
                return None
            root = arg[len("--root=") :]
        elif arg.startswith("-") or skill_path is not None:
            # Any other dash-prefixed argument (--bogus, -h) is an unknown flag,
            # not a skill path.
            return None
        else:
            skill_path = arg
    if skill_path is None or root == "":
        return None
    return skill_path, root
